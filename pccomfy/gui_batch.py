"""Batch and the local queue in the window (docs/plan/speichern-queue-batch.md, steps 3 and 4; decisions of 12.11.).

The window owns one jobqueue.QueueRunner (self.runner, made in gui.py). This mixin builds the batch dialog (⋯ menu: "Batch:
open images", "Batch: folder…"), the dry-run dialog, the small windows in the look of the settings window, the hint at the
progress bar ("Batch 3 of 12 · ~4 min", "N jobs of others ahead"), and the lock of Generate and the other worker actions
while a batch is on. The queue window itself (⋯ menu: "Queue") is gui_queuewin.py (tempo plan S1, 24.11.). The runner's
events arrive through RunMixin._poll (_batch_event); nothing here waits for ComfyUI or PhotoCraft in the Tk thread."""
from __future__ import annotations

import sys

from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from . import hostos, icons, inventory, jobqueue, savefile, winlink
from .ui_settings import SET_STYLES

# the window modes a batch can run (the run mode must be one of jobqueue.BATCH_MODES too: Fibo Refine runs as Edit)
BATCH_WINDOW_MODES = {"refine": "Refine Image", "upscale": "Upscale", "edit": "Edit", "multi_edit": "Edit"}
BATCH_ONLY = "Batch works with Refine Image, Upscale and Edit. Choose one of them first."
BATCH_NO_BBOX = "Batch can't use Insert reference: it needs a selection in each picture. Pick another Edit tab first."   # the tab's name (user 23.11.)
BATCH_BUSY = "A batch is running. Wait for it, or click Stop batch."
AHEAD_POLL_S = 2.0           # Generate: GET /queue this often while our job waits at ComfyUI (decisions 12.11.)
SYNC_MS = 1000               # while a batch is on: Generate's lock is checked again this often
THUMB_PX = 320               # the dry run's picture fits in this square (before the display scaling)

PLACED_TEXT = {"layer": "Added as a new layer.", "document": "Opened as a new document.", "file": "Saved as a file."}


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def folder_counts(folder) -> tuple[int, int]:
    """(pictures a folder batch takes, other files it leaves out) of a folder (no subfolders)."""
    pics = jobqueue.scan_folder(folder)
    try:
        files = sum(1 for f in Path(folder).iterdir() if f.is_file())
    except OSError:
        files = len(pics)
    return len(pics), max(0, files - len(pics))


def _recover_allowed() -> bool:
    """A test script that did not give the plugin a data folder of its own must not touch the user's real queue."""
    try:
        script = Path(sys.argv[0]).resolve()
    except (IndexError, OSError, ValueError):
        return True
    return not (script.parent.name == "tests" and not os.environ.get("PCCOMFY_HOME"))


class BatchMixin:
    # ---------- the runner and the lock ----------

    def _batch_busy(self) -> bool:
        runner = getattr(self, "runner", None)
        try:
            return bool(runner is not None and runner.busy)
        except Exception:
            return False

    def _blocked_by_batch(self) -> bool:
        """True (and says why in the status line) while a batch is on: Generate and the other worker actions wait."""
        if not self._batch_busy():
            return False
        self._status(BATCH_BUSY)
        return True

    def _batch_sync(self):
        """While a batch is on, Generate is the grey "Stop run" with "Stop batch" beside it, as with the variants of Upscale
        (user 20.11.; was a locked grey Generate, decision 12.11.), and comes back when it is over and no run of the window
        is on. Undo and Redo are grey with it: a batch adds layers and documents in PhotoCraft meanwhile, a step back would
        take the wrong one (they refuse anyway, _history_step)."""
        self._batch_sync_job = None
        busy = self._batch_busy()
        own = getattr(self, "_running", False) or bool(self.worker and self.worker.is_alive())
        try:
            if busy and not own:
                self._batch_stopping = True
                if not (getattr(self, "_go_stopping", False) and self.b_stop_all.winfo_manager()):
                    self._show_stop_all(True)
                    self._go_stop(True)
            elif not busy and getattr(self, "_batch_stopping", False):
                self._batch_stopping = False
                if not own:
                    self._show_stop_all(False)
                    self._go_stop(False)
            widgets = (self.w_variants,) if getattr(self, "_go_stopping", False) else (self.b_go, self.w_variants)   # "Stop" stays usable
            if getattr(self, "_go_queueing", False):
                widgets = ()            # "Add to queue" and ×n stay usable (docs/plan/generate-queue.md) ...
                locked = self._queue_row_kind() == "locked"     # ... or grey for Fill, Remove, Expand (user 23.11.)
                for w in (self.b_go, self.w_variants):
                    if str(w.cget("state")) != ("disabled" if locked else "normal"):
                        w.configure(state="disabled" if locked else "normal")
            if busy:
                for w in widgets:
                    w.configure(state="disabled")
            elif not getattr(self, "_running", False) and not (self.worker and self.worker.is_alive()):
                for w in widgets:
                    w.configure(state="normal")
            self._sync_history_buttons()        # Undo and Redo follow their own rule (gui_run.py, 18.11.)
        except (tk.TclError, AttributeError):
            return
        if busy:
            self._batch_sync_job = self.root.after(SYNC_MS, self._batch_sync)

    def _batch_sync_soon(self):
        if not getattr(self, "_batch_sync_job", None):
            self._batch_sync_job = self.root.after(200, self._batch_sync)

    def _batch_recover(self):
        """Once after the start: results a batch job finished at ComfyUI while PxC was closed are picked up (runner thread)."""
        runner = getattr(self, "runner", None)
        if runner is None or not _recover_allowed():
            return
        try:
            self._rescue_ids = {j["id"] for j in runner.jobs() if j["status"] == jobqueue.RUNNING}
        except Exception:
            self._rescue_ids = set()
        self._rescued = 0
        threading.Thread(target=runner.recover, daemon=True, name="pcc-recover").start()

    def _batch_shutdown(self) -> bool:
        """The window closes: the runner stops after its current step. True when a batch job is at ComfyUI and the window's
        own work is not running: then the caller must not cancel the bridge (that would stop the job at ComfyUI; left alone,
        the next start picks its result up through its prompt id)."""
        self._ahead_stop()
        runner = getattr(self, "runner", None)
        if runner is None:
            return False
        keep = False
        try:
            keep = (runner.running_job is not None and not (self.worker and self.worker.is_alive())
                    and not getattr(self, "_describing", False))
            runner.shutdown()
        except Exception:
            pass
        return keep

    # ---------- the events (RunMixin._poll) ----------

    def _batch_event(self, kind: str, data):
        if kind == "batch-ui":           # a step of this mixin's own threads, run in the Tk thread
            data()
            return
        if kind == "gen-ahead":
            self._ahead_n = int(data or 0)
            self._refresh_bar_text()
            return
        if kind == "batch-placed":           # a queued Generate's result layer: Undo hides it next
            if data.get("batch") in getattr(self, "_batch_mine", set()):
                self._undo_push_layers(data)
        elif kind == "queue-job":
            self._batch_job_event(data)
        elif kind == "batch-progress":
            if data.get("id") == getattr(self, "_batch_shown", None):
                self._refresh_bar_text()
        elif kind == "batch-step":
            self._set_progress(*data)
        elif kind == "batch-ahead":
            if data.get("batch") == getattr(self, "_batch_shown", None):
                self._ahead_n = int(data.get("ahead") or 0)
                self._refresh_bar_text()
        elif kind == "batch-dry":
            self._batch_dry_dialog(data)
        elif kind == "batch-dry-over":          # resumed in the queue: the dry run is confirmed, its window has nothing to ask
            if data.get("batch") == getattr(self, "_dry_batch", None):
                self._dry_close()
        elif kind == "batch-done":
            self._batch_done(data)
        elif kind == "batch-error":
            msg = str(data.get("message") or "")
            if msg and data.get("batch") in getattr(self, "_batch_mine", set()) | {""}:
                word = "Queue" if self._batch_kind(data.get("batch")) == jobqueue.K_GENERATE else "Batch"
                self._status(f"{word}: {msg}", error=True)
        self._queue_dirty()
        self._batch_sync_soon()

    def _batch_kind(self, bid) -> str:
        """K_GENERATE for a queued Generate, K_BATCH otherwise (also when the runner does not know it)."""
        try:
            b = self.runner.batch(bid) if bid else None
        except Exception:
            b = None
        return str((b or {}).get("kind") or jobqueue.K_BATCH)

    def _batch_job_event(self, job: dict):
        if job.get("id") in getattr(self, "_rescue_ids", set()) and job.get("status") == jobqueue.DONE:
            self._rescue_ids.discard(job["id"])
            self._rescued = getattr(self, "_rescued", 0) + 1
            self._status(f"Picked up {plural(self._rescued, 'batch result')} that finished while PxC was closed.")
        if job.get("status") == jobqueue.DONE and job.get("batch_id") in getattr(self, "_batch_mine", set()):
            self._queued_done(job)          # a queued Generate: its run goes into the history (the clock)
        if job.get("status") == jobqueue.RUNNING and job.get("batch_id") in getattr(self, "_batch_mine", set()):
            if job.get("batch_id") != getattr(self, "_batch_shown", None) or job.get("id") != getattr(self, "_batch_job", None):
                self._batch_shown, self._batch_job, self._ahead_n = job["batch_id"], job["id"], 0
                try:            # the bar names the model the job was queued with
                    self._queue_label = str((self.runner.batch(job["batch_id"]) or {}).get("model") or "") or None
                except Exception:
                    self._queue_label = None
                self._reset_progress()
                self._set_progress(0.0, "", "prepare", -1.0, None)

    def _batch_done(self, b: dict):
        if b.get("id") not in getattr(self, "_batch_mine", set()):
            return
        if b.get("id") == getattr(self, "_batch_shown", None):
            self._batch_shown, self._batch_job, self._ahead_n = None, None, 0
        counts = (b.get("progress") or {}).get("counts") or {}
        done, failed = int(counts.get(jobqueue.DONE, 0)), int(counts.get(jobqueue.ERROR, 0))
        total = int((b.get("progress") or {}).get("total") or b.get("total") or 0)
        if b.get("kind") == jobqueue.K_GENERATE:     # a queued Generate (docs/plan/generate-queue.md)
            label = str(b.get("label") or "queued run")
            if b.get("state") == jobqueue.B_CANCELLED:
                self._reset_progress()
                self._status(f"Cancelled: {label}" + (f" ({done} of {total} done)." if total > 1 else "."))
            else:
                self._reset_progress(done=True, text=f"Done · {label}" + (f" · {done} of {total}" if total > 1 else "")
                                     + (f" · {failed} failed" if failed else ""))
                if not failed:
                    self._status("")
            return
        if b.get("state") == jobqueue.B_CANCELLED:
            self._reset_progress()
            self._status(f"Batch cancelled ({done} of {total} done).")
        else:
            self._reset_progress(done=True, text=f"Done · batch: {done} of {total} done" + (f" · {failed} failed" if failed else ""))
            if not failed:
                self._status("")

    # ---------- the hint at the bar ----------

    def _progress_hint(self) -> str:
        """What follows the step above the bar: " · Batch 3 of 12 · ~4 min" during a batch, " · 2 jobs of others ahead" while
        ComfyUI has jobs of other users before ours (batch and Generate); "" when only we use ComfyUI."""
        parts = []
        bid = getattr(self, "_batch_shown", None)
        runner = getattr(self, "runner", None)
        if bid and runner is not None:
            try:
                hint = runner.batch_hint(bid)
            except Exception:
                hint = ""
            if hint:
                parts.append(hint)
        n = int(getattr(self, "_ahead_n", 0) or 0)
        if n > 0:
            parts.append(f"{plural(n, 'job')} of others ahead")
        return "".join(" · " + p for p in parts)

    def _refresh_bar_text(self):
        args = getattr(self, "_pl_args", None)
        if args is not None and (getattr(self, "_running", False) or getattr(self, "_batch_shown", None)):
            f, msg, phase, pf, elapsed = args
            self._set_progress(None, msg, phase, pf, elapsed)

    # ---------- Generate: "N jobs of others ahead" while our job waits at ComfyUI ----------

    def _ahead_start(self):
        """Started with a Generate run: about every AHEAD_POLL_S, while the run's job waits at ComfyUI, ask /queue how many
        jobs of other clients are before it. Stops when the job runs (that prompt id is not asked again) or the run ends."""
        self._ahead_stop()
        self._ahead_n = 0
        stop = self._ahead_ev = threading.Event()
        comfy, worker = self.bridge.comfy, self.worker
        before = getattr(comfy, "last_prompt_id", None)

        def work():
            started, last = set(), 0
            while not stop.wait(AHEAD_POLL_S):
                if worker is None or not worker.is_alive():
                    break
                pid = getattr(comfy, "last_prompt_id", None)
                if not pid or pid == before or pid in started:
                    continue
                try:
                    entries = comfy.queue_entries()
                except Exception:
                    continue
                mine = next((e for e in entries if e.get("prompt_id") == pid), None)
                n = 0
                if mine is None or mine.get("running"):
                    started.add(pid)            # it runs (or is over): no more asking for this job
                else:
                    n = comfy.jobs_ahead(pid, entries)
                if n != last:
                    last = n
                    self.events.put(("gen-ahead", n))
            if last:
                self.events.put(("gen-ahead", 0))
        self._ahead_thread = threading.Thread(target=work, daemon=True, name="pcc-ahead")
        self._ahead_thread.start()

    def _ahead_stop(self):
        ev = getattr(self, "_ahead_ev", None)
        if ev is not None:
            ev.set()
        self._ahead_ev = None
        if not getattr(self, "_batch_shown", None):
            self._ahead_n = 0

    # ---------- a small window in the look of the settings window ----------

    def _small_window(self, title: str, on_close, at: str = ""):
        """A Toplevel like the settings window: no title bar, no blue line on top (user 22.11.), the title and an X (dragging the header
        moves it). Returns (window, body frame). `at`: "settings" opens it where the settings window opens (the queue,
        user 12.11.); "menu" keeps it hidden until the caller has filled it and calls _place_at_menu (the batch window);
        "" a little inside the plugin window (the dry run)."""
        win = tk.Toplevel(self.root, **hostos.TOP_KW)
        if at == "menu":
            win.withdraw()          # its height is known only once it is filled: no flash at a wrong place
        win.title(title)
        win.wm_overrideredirect(True)
        win.configure(bg=BG, highlightthickness=1, highlightbackground="#5c5c5c")
        try:
            win.transient(self.root)
        except tk.TclError:
            pass
        bar = ttk.Frame(win)
        bar.pack(fill="x", side="top", pady=(self._px(4), 0))
        head = ttk.Label(bar, text=title, foreground="#ffffff", font=font(12))
        head.pack(side="left", padx=(12, 0))
        x = ttk.Button(bar, text="✕", style="Link.TButton", width=2, command=on_close)
        x.pack(side="right", padx=(0, 6))
        drag = {}

        def start(e):
            drag["pos"] = (e.x_root - win.winfo_x(), e.y_root - win.winfo_y())

        def move(e):
            if "pos" in drag:
                win._pcc_moved = True       # moved by hand: _place_at_menu no longer keeps its bottom edge in place
                win.geometry(f"+{e.x_root - drag['pos'][0]}+{e.y_root - drag['pos'][1]}")
        for w in (bar, head):
            w.bind("<ButtonPress-1>", start)
            w.bind("<B1-Motion>", move)
        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=14, pady=(6, 12))
        win.protocol("WM_DELETE_WINDOW", on_close)
        win.bind("<Escape>", lambda e: on_close())
        try:
            if at == "settings":     # like open_settings: beside the plugin window, top edges level
                win.geometry(f"+{self.root.winfo_rootx() + self.root.winfo_width() + 8}+{self.root.winfo_rooty()}")
            elif at != "menu":
                win.geometry(f"+{self.root.winfo_rootx() + self._px(30)}+{self.root.winfo_rooty() + self._px(80)}")
        except (tk.TclError, TypeError):
            pass
        if at != "menu":
            idle(win, self._raise_small, win)
        win._pcc_close = x
        return win, body

    def _raise_small(self, win, tries: int = 3):
        """Brings a small window up above the plugin window: on Windows it becomes an owned window of the plugin (winlink.own),
        so it can never lie under the plugin or under PhotoCraft (the dry-run window did, user 12.11.); elsewhere Tk's lift.
        Tk's window may not exist on the first try: a few more after 100 ms."""
        if not self._alive(win):
            return
        try:
            win.lift()
            win.focus_force()       # a window without a title bar gets no keyboard focus by itself: Escape did nothing (user 13.11.)
        except tk.TclError:
            return
        others = [w for w in self._small_windows() if w is not win]
        if winlink.available() and not winlink.own(win, self.root, others=others) and tries > 1:
            later(win, 100, self._raise_small, win, tries - 1)

    def _small_windows(self) -> list:
        """The small windows open now (batch, dry run, queue), for the order in front of the plugin."""
        return [w for w in (getattr(self, n, None) for n in ("_dry_dlg", "_batch_dlg", "_queue_win", "_tip_win")) if self._alive(w)]

    def _place_at_menu(self, win):
        """The batch window (user 12.11.): beside the plugin window on the side of the ⋯ button, with the gap of the settings
        window, its bottom edge on the plugin window's bottom edge (the first try aligned it with the button itself: it touched the
        plugin and ended a few pixels higher). It keeps that bottom edge when its content grows (Choose folder…), until it is moved
        by hand. Shows the window that _small_window(at="menu") kept hidden."""
        def place(h=None):
            if getattr(win, "_pcc_moved", False):
                return
            try:
                r = self.root
                x = r.winfo_rootx() + r.winfo_width() + 8
                y = r.winfo_rooty() + r.winfo_height() - (h if h is not None else win.winfo_reqheight())
                win.geometry(f"+{x}+{max(0, y)}")
            except (tk.TclError, TypeError):
                pass
        try:
            win.update_idletasks()
        except tk.TclError:
            return
        place()
        seen = {"h": win.winfo_reqheight()}

        def grew(e):
            if e.widget is win and e.height != seen["h"]:
                seen["h"] = e.height
                if hostos.IS_WINDOWS:
                    place(e.height)
                else:
                    # X11 ignores a move of this window without title bar asked for inside its own <Configure>: it grew
                    # downward (Mint laptop 19.11.); asked a moment later it moves
                    idle(win, place, e.height)
        win.bind("<Configure>", grew, add="+")
        try:
            win.deiconify()
            idle(win, self._raise_small, win)
        except tk.TclError:
            pass

    @staticmethod
    def _alive(win) -> bool:
        try:
            return win is not None and bool(win.winfo_exists())
        except tk.TclError:
            return False

    # ---------- the batch dialog ----------

    def _batch_function(self) -> str:
        mode = self.v_mode.get()
        return BATCH_WINDOW_MODES.get(mode) or FN_NAMES.get(mode, mode)

    def _batch_refusal(self) -> str:
        """Why the chosen function cannot run as a batch ("" = it can)."""
        if self.v_mode.get() not in BATCH_WINDOW_MODES or self._run_mode() not in jobqueue.BATCH_MODES:
            return BATCH_ONLY
        if self._bbox_on():
            return BATCH_NO_BBOX
        if self.start_state():
            return "Choose a model first."
        return ""

    def _batch_problem(self) -> str:
        """What Generate would refuse before a run (SettingsMixin.generate, RefSlotsMixin.generate), "" = nothing."""
        refusal = self._batch_refusal()
        if refusal:
            return refusal
        m = self._model()
        if self.v_model.get() and self.v_workflow.get() == BUILTIN:
            return (f"The workflow of {m.label if m else 'this model'} was not found. Check the workflows folder, "
                    "or choose the model again.")
        lines = self._preflight()
        if lines:
            return inventory.short_message(lines, m.label if m else "")
        slots = getattr(self, "refslots", None)
        if self._refs_wanted() and (slots is None or not slots.active):
            return "Multi image edit needs at least one reference image: drop, paste or add one in a slot."
        return ""

    def _batch_request(self):
        """The settings of the batch: the request Generate would send now (RunMixin._request plus what generate() adds:
        the layer name and the running number). Returns (request, the new run counters for the state)."""
        req = self._request()
        req.preset = self._layer_prefix()
        runs = dict(self.state.get("runs", {}))
        if req.preset:
            req.run_no = int(runs.get(req.preset, 0)) + 1
            runs[req.preset] = req.run_no
            req.group_name = f"{SHORT_MODES.get(self.v_mode.get(), self.v_mode.get())} {req.run_no}"
        return req, runs

    def open_batch(self, source: str = jobqueue.SOURCE_OPEN):
        """⋯ menu: the batch dialog for the open images (source "open") or a folder ("folder")."""
        old = getattr(self, "_batch_dlg", None)
        if self._alive(old):
            old.destroy()
        win, body = self._small_window("Batch mode", self._batch_close, at="menu")
        self._batch_dlg, self._batch_source, self._batch_body = win, source, body
        self._batch_folder_sel = None
        self.b_batch_start = None
        if not getattr(self, "_batch_traced", False):           # the open window follows the function and the model (user 13.11.)
            for var in (self.v_mode, self.v_model):
                var.trace_add("write", lambda *a: self._batch_follow_soon())
            self._batch_traced = True
        try:
            self._batch_fill(body, source)
        finally:
            self._place_at_menu(win)

    def _batch_follow_soon(self):
        """A change of function or model: the open batch window is filled anew once (a mode change also sets the model)."""
        if self._alive(getattr(self, "_batch_dlg", None)) and not getattr(self, "_batch_follow_job", None):
            self._batch_follow_job = self.root.after_idle(self._batch_follow)

    def _batch_follow(self):
        self._batch_follow_job = None
        win, body = getattr(self, "_batch_dlg", None), getattr(self, "_batch_body", None)
        if not self._alive(win) or body is None:
            return
        keep = {"folder": self._batch_folder_sel,
                "dry": self.v_batch_dry.get() if getattr(self, "v_batch_dry", None) is not None else None,
                "save": self.v_batch_save.get() if getattr(self, "v_batch_save", None) is not None else None}
        for w in body.winfo_children():
            w.destroy()
        self.b_batch_start = None
        self.v_batch_dry = self.v_batch_save = None
        self._batch_fill(body, self._batch_source)
        if self.v_batch_dry is not None:
            if keep["dry"] is not None:
                self.v_batch_dry.set(keep["dry"])
            if keep["save"] is not None:
                self.v_batch_save.set(keep["save"])
            if keep["folder"] and self._batch_source == jobqueue.SOURCE_FOLDER:
                self._batch_set_folder(keep["folder"])

    def _batch_fill(self, body, source: str):
        """The content of the batch window (open_batch)."""
        m = self._model()
        refusal = self._batch_refusal()
        head = ttk.Frame(body)
        head.pack(anchor="w")
        self.lbl_batch_warn = None
        if refusal:                 # the red "!" of the status line in front of the function (user 13.11.)
            px = self._px(ERR_BADGE_PX)
            self._batch_warn_img = icons.photo(self.root, "", "", px, image=icons.error_badge(px))
            self.lbl_batch_warn = ttk.Label(head, image=self._batch_warn_img, anchor="center")
            self.lbl_batch_warn.pack(side="left", padx=(0, 6))
        self.lbl_batch_fn = ttk.Label(head, text=f"{self._batch_function()} · {m.label if m else 'no model'}",
                                      style=SET_STYLES["head"])
        self.lbl_batch_fn.pack(side="left")
        wrap = self._px(340)
        if refusal:
            self.lbl_batch_msg = ttk.Label(body, text=refusal, style="SetText.TLabel", wraplength=wrap, justify="left")
            self.lbl_batch_msg.pack(anchor="w", pady=(8, 0))
            row = self._button_row(body)
            self.b_batch_cancel = ttk.Button(row, text="Close", style="SetSmall.TButton", command=self._batch_close)
            self.b_batch_cancel.pack(side="left")
            return
        self.lbl_batch_msg = None
        if source == jobqueue.SOURCE_FOLDER:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=(8, 0))
            self.b_batch_folder = ttk.Button(row, text="Choose folder…", style="SetSmall.TButton", command=self._batch_pick_folder)
            self.b_batch_folder.pack(side="left")
            self.lbl_batch_count = ttk.Label(row, text="", style="SetText.TLabel")
            self.lbl_batch_count.pack(side="left", padx=(8, 0))
            Tooltip(self.lbl_batch_count, "Skipped: files that are no PNG, JPG or WebP picture, and results of an earlier batch "
                                          "(_upscaled, _refined, _edited).")
            self.lbl_batch_src = ttk.Label(body, text="No folder chosen.", style=SET_STYLES["muted"], wraplength=wrap, justify="left")
            self.lbl_batch_src.pack(anchor="w", pady=(4, 0))
        else:
            self.lbl_batch_src = ttk.Label(body, text="Open images: counting…", style="SetText.TLabel")
            self.lbl_batch_src.pack(anchor="w", pady=(8, 0))
            self._batch_count_open()
        self.v_batch_dry = tk.BooleanVar(value=False)      # off at the start (user 13.11.)
        cb = self.cb_batch_dry = ttk.Checkbutton(body, text="Dry run on the first picture", variable=self.v_batch_dry,
                                                 style="SetText.TCheckbutton")
        cb.pack(anchor="w", pady=(10, 0))
        Tooltip(cb, "The first picture runs alone. You see its result and then start the rest, or cancel.")
        self.v_batch_save = tk.BooleanVar(value=False)
        self.cb_batch_save = None
        folder = savefile.load_settings().folder
        if source == jobqueue.SOURCE_OPEN:
            cb = self.cb_batch_save = ttk.Checkbutton(body, text="Also save to the save folder", variable=self.v_batch_save,
                                                      style="SetText.TCheckbutton")
            cb.pack(anchor="w", pady=(4, 0))
            Tooltip(cb, f"Each result also goes into the save folder ({folder}), named like the picture with "
                        "_upscaled, _refined or _edited at the end.")
            out = "Results appear as a new layer in each open picture (Upscale: as a new document)."
        else:
            out = f"Results: files in {folder}, named like the picture with _upscaled, _refined or _edited."
        self.lbl_batch_out = ttk.Label(body, text=out, style=SET_STYLES["muted"], wraplength=wrap, justify="left")
        self.lbl_batch_out.pack(anchor="w", pady=(8, 0))
        self.lbl_batch_err = ttk.Label(body, text="", style="Error.TLabel", wraplength=wrap, justify="left")
        row = self._button_row(body, side="bottom")
        self.b_batch_start = ttk.Button(row, text="Start", style="Accent.TButton", command=self._batch_start)
        self.b_batch_start.pack(side="left")
        self.b_batch_cancel = ttk.Button(row, text="Cancel", style="SetSmall.TButton", command=self._batch_close)
        self.b_batch_cancel.pack(side="left", padx=(8, 0))
        if source == jobqueue.SOURCE_FOLDER:
            self.b_batch_start.configure(state="disabled")

    def _button_row(self, body, side: str = "top"):
        """The buttons of a small window, centred, the main one on the left (user 13.11.). Returns the frame to pack them into."""
        row = ttk.Frame(body)
        row.pack(fill="x", side=side, pady=(12, 0))
        inner = ttk.Frame(row)
        inner.pack(anchor="center")
        return inner

    def _batch_close(self):
        win, self._batch_dlg = getattr(self, "_batch_dlg", None), None
        if self._alive(win):
            win.destroy()

    def _batch_error(self, msg: str):
        lbl = getattr(self, "lbl_batch_err", None)
        if lbl is None or not self._alive(getattr(self, "_batch_dlg", None)):
            self._status(msg, error=bool(msg))
            return
        lbl.configure(text=msg)
        if msg and not lbl.winfo_manager():
            lbl.pack(anchor="w", pady=(8, 0))
        elif not msg:
            lbl.pack_forget()

    def _batch_count_open(self):
        """How many documents are open in PhotoCraft (read in a thread; PhotoCraft may be slow)."""
        pc = self.bridge.pc

        def work():
            try:
                n = len(pc.session().get("documents") or [])
            except Exception:
                n = None
            self.events.put(("batch-ui", lambda: self._batch_show_open(n)))
        threading.Thread(target=work, daemon=True, name="pcc-batch-count").start()

    def _batch_show_open(self, n):
        if not self._alive(getattr(self, "_batch_dlg", None)) or self._batch_source != jobqueue.SOURCE_OPEN:
            return
        lbl = getattr(self, "lbl_batch_src", None)
        if not self._alive(lbl) or self.b_batch_start is None:      # filled anew meanwhile (another function chosen)
            return
        if n is None:
            lbl.configure(text="Open images: PhotoCraft did not answer.")
        elif n == 0:
            lbl.configure(text="Open images: none open in PhotoCraft.")
            self.b_batch_start.configure(state="disabled")
        else:
            lbl.configure(text=f"Open images: {n} in PhotoCraft")

    def _batch_pick_folder(self):
        from tkinter import filedialog
        start = self._batch_folder_sel or getattr(self, "_batch_last_folder", None) or str(savefile.load_settings().folder)
        chosen = self._dialog(filedialog.askdirectory, title="Folder with pictures for the batch", initialdir=start)
        if chosen:
            self._batch_set_folder(chosen)

    def _batch_set_folder(self, folder):
        folder = str(Path(folder))
        self._batch_folder_sel = self._batch_last_folder = folder
        n, skipped = folder_counts(folder)
        self.lbl_batch_count.configure(text=f"{plural(n, 'picture')}, {skipped} skipped")
        self.lbl_batch_src.configure(text=folder)
        self.b_batch_start.configure(state="normal" if n else "disabled")
        self._batch_error("" if n else "No PNG, JPG or WebP pictures in this folder.")

    def _batch_start(self):
        """Start: the request as Generate builds it, handed to the runner (it checks it at once; an error stays in the dialog)."""
        problem = self._batch_problem()
        if problem:
            self._batch_error(problem)
            return
        source = self._batch_source
        if source == jobqueue.SOURCE_FOLDER and not self._batch_folder_sel:
            self._batch_error("Choose a folder first.")
            return
        try:
            req, runs = self._batch_request()
        except (tk.TclError, ValueError) as e:
            self._batch_error(f"Invalid value: {e}")
            return
        spec = jobqueue.BatchSpec(request=req, source=source,
                                  folder=self._batch_folder_sel if source == jobqueue.SOURCE_FOLDER else None,
                                  dry_run=bool(self.v_batch_dry.get()),
                                  also_save_file=bool(self.v_batch_save.get()) if source == jobqueue.SOURCE_OPEN else False)
        try:
            bid = self.runner.start_batch(spec)
        except (ValueError, BridgeError) as e:
            self._batch_error(str(e))
            return
        self.state["runs"] = runs
        try:
            self._save_state(req)
        except Exception:
            pass
        self._batch_mine = getattr(self, "_batch_mine", set()) | {bid}
        self._batch_close()
        self._status("Batch started.")
        self._batch_sync()
        self.open_queue()           # the queue opens with the batch (user 13.11.)

    # ---------- the dry run ----------

    def _batch_dry_dialog(self, d: dict):
        """The dry run's first result: its picture and "Start remaining N" / "Cancel batch"; a failure: the error and Close
        (the batch is cancelled then; it would otherwise wait forever and keep Generate locked)."""
        old = getattr(self, "_dry_dlg", None)
        if self._alive(old):
            old.destroy()
        bid = d.get("batch", "")
        err = str(d.get("error") or "")
        self._dry_batch = bid
        # X / Escape only close the window while the batch waits for an answer; it keeps waiting in the queue, where ▶ starts
        # the rest and ✕ cancels it (user 13.11.); after a failure X still cancels (the batch is stopped anyway)
        win, body = self._small_window("Dry run", lambda: self._dry_finish() if getattr(self, "b_dry_start", None) is not None else self._dry_cancel(), at="menu")    # where the batch window was (user 13.11.)
        self._dry_dlg = win
        self.b_dry_start = self.b_dry_cancel = self.b_dry_close = None
        try:
            self._dry_fill(body, d, bid, err)
        finally:
            self._place_at_menu(win)

    def _dry_fill(self, body, d: dict, bid: str, err: str):
        """The content of the dry-run window (_batch_dry_dialog)."""
        wrap = self._px(THUMB_PX)
        if err:
            self.lbl_dry = ttk.Label(body, text=f"The first picture failed: {err}", style="Error.TLabel", wraplength=wrap, justify="left")
            self.lbl_dry.pack(anchor="w")
            ttk.Label(body, text="The batch is stopped.", style="SetText.TLabel").pack(anchor="w", pady=(6, 0))
            row = self._button_row(body)
            self.b_dry_close = ttk.Button(row, text="Close", style="SetSmall.TButton", command=self._dry_cancel)
            self.b_dry_close.pack(side="left")
            return
        im = d.get("image")
        if im is None:
            for f in d.get("results") or []:
                try:
                    from PIL import Image
                    with Image.open(f) as src:
                        src.load()
                        im = src.copy()
                    break
                except Exception:
                    continue
        self._dry_photo = None
        if im is not None:
            from PIL import ImageOps
            try:
                shown = ImageOps.contain(im.convert("RGBA"), (self._px(THUMB_PX), self._px(THUMB_PX)))
                self._dry_photo = icons.photo(self.root, None, "", 0, image=shown)
            except Exception:
                self._dry_photo = None
        if self._dry_photo is not None:
            self.lbl_dry_img = ttk.Label(body, image=self._dry_photo, anchor="center")
            self.lbl_dry_img.pack(pady=(4, 0))
        try:
            left = sum(1 for j in self.runner.jobs(bid) if j["status"] in (jobqueue.WAITING, jobqueue.PAUSED))
        except Exception:
            left = 0
        info = PLACED_TEXT.get(str(d.get("placed") or ""), "")
        text = (info + " " if info else "") + ("Is the result ok?" if left else "")
        self.lbl_dry = ttk.Label(body, text=text.strip(), style="SetText.TLabel", wraplength=wrap, justify="left")
        self.lbl_dry.pack(anchor="w", pady=(8, 0))
        row = self._button_row(body)
        if not left:                    # one picture only: nothing to start or cancel, the batch is done
            self.b_dry_close = ttk.Button(row, text="Close", style="Accent.TButton", command=self._dry_finish)
            self.b_dry_close.pack(side="left")
            return
        self.b_dry_start = ttk.Button(row, text=f"Start remaining {left}", style="Accent.TButton", command=self._dry_confirm)
        self.b_dry_start.pack(side="left")
        self.b_dry_cancel = ttk.Button(row, text="Cancel batch", style="SetSmall.TButton", command=self._dry_cancel)
        self.b_dry_cancel.pack(side="left", padx=(8, 0))

    def _dry_close(self):
        win, self._dry_dlg = getattr(self, "_dry_dlg", None), None
        self._dry_photo = None
        if self._alive(win):
            win.destroy()

    def _dry_finish(self):
        """Close for a batch of one picture: it is finished already (done, not cancelled); only the window goes."""
        self._dry_close()
        self._batch_sync()

    def _dry_confirm(self):
        self.runner.confirm(getattr(self, "_dry_batch", ""))
        self._dry_close()
        self._batch_sync()

    def _dry_cancel(self):
        self.runner.discard(getattr(self, "_dry_batch", ""))
        self._dry_close()
        self._batch_sync_soon()
