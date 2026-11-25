"""The queue window (⋯ menu: "Queue"; docs/plan/speichern-queue-batch.md, step 4; moved out of gui_batch.py, tempo plan S1,
24.11.): one flat list of our batch jobs, our direct runs and the runs of others at ComfyUI, with the symbols of each row
(pause / resume, ↻, ✕), the buttons below it, its columns (widths, drag, double click, saved per user) and the light lines
between them, and "At ComfyUI" read again while the window is open. The runner and the batch dialogs are gui_batch.py."""
from __future__ import annotations

import tkinter.font as tkfont

from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from . import comfyaddr, hostos, jobqueue
from .gui_batch import BATCH_WINDOW_MODES, PLACED_TEXT
from .popmenu import PopMenu
from .ui_settings import SET_STYLES

Q_PICTURE_MIN = 90      # the Picture column of the queue never gets narrower (px before scaling)
Q_COL_MIN = 40          # a text column of the queue never gets narrower ("#": 30; px before scaling)
Q_FILLER = "pic"        # the column that takes what the others leave (user 13.11.: no gap, the symbols stay in sight)
# Status and the symbols ⏸ ↻ ✕ are one block of a fixed width (user 24.11. evening: "füge die letzten zwei spalten zu einer
# zusammen ... gebe der sammelspalte eine fixe breite die ausreicht für alles"): Status is not dragged, saved or squeezed
Q_FIXED = "status"
Q_STATUS_TEXTS = ("▰▰▰▰▰ 100 %", "Cancelled", "Waiting", "Running", "Skipped", "Paused", "Error", "Done", "Status")
Q_COL_DEFAULT = {"idx": 34, "who": 100, "pic": 200, "status": 110, "fn": 130, "time": 110}   # px before scaling; Status holds the bar
Q_TREE_INSET = 4         # the list's frame in the clam theme: 2 px on each side (measured 19.11.; with 2 Tk squeezed Picture)
Q_GRID_HEAD, Q_GRID_BODY = "#6e6e6e", "#3d3d3d"   # the light lines between the columns (user 19.11.): heading, rows
Q_NOT_CONNECTED_LOCAL = "ComfyUI not connected. Is ComfyUI running?"
Q_NOT_CONNECTED_NET = "ComfyUI not connected. Set its host address in: Settings › Other settings."
TYPING = ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox", "TCombobox", "Listbox")     # widgets where Q is a letter, not the queue
QUEUE_COMFY_MS = 2000        # the queue window: "At ComfyUI" is read again this often, only while the window is open
Q_OWN_RETRY_MAX = 8         # the newest direct runs that keep their picture for ↻ in the queue window (23.11. late)
Q_FOREIGN_DONE_MAX = 200    # finished runs of others kept in the queue window until "Clear finished" (Paket 3, 19.11.)
BAR_CELLS = 5                # the text bar of the Progress column: "▰▰▰▱▱ 60 %"
STATUS_TEXT = {jobqueue.WAITING: "Waiting", jobqueue.RUNNING: "Running", jobqueue.PAUSED: "Paused", jobqueue.DONE: "Done",
               jobqueue.ERROR: "Error", jobqueue.CANCELLED: "Cancelled"}
# the Status word in colour (user 23.11. evening, choice "Nur Status-Text"): done green, cancelled and failed red
Q_STATUS_COLORS = {"Done": DONE_GREEN, "Cancelled": ERROR, "Error": ERROR}
BATCH_STATE_TEXT = {jobqueue.B_PREPARING: "Collecting", jobqueue.B_RUNNING: "Running", jobqueue.B_CONFIRM: "Dry run",
                    jobqueue.B_DONE: "Done", jobqueue.B_CANCELLED: "Cancelled"}


def batch_state_text(b: dict) -> str:
    """The state of a batch row: "Waiting" until the batch really starts: a preparing batch before it collects its pictures
    (that happens only between two jobs; user 13.11.), and a batch whose pictures are all there but none has begun, because
    the batch before it still runs (user 13.11.: its pictures said Waiting, the batch said Running). "Collecting" while it
    collects, "Running" from its first picture on."""
    state = b.get("state")
    if state == jobqueue.B_PREPARING and not b.get("collecting"):
        return "Waiting"
    if state == jobqueue.B_RUNNING:
        counts = (b.get("progress") or {}).get("counts")
        if counts is not None and not counts.get(jobqueue.RUNNING) and not counts.get(jobqueue.DONE)                 and counts.get(jobqueue.WAITING):
            return "Waiting"
    return BATCH_STATE_TEXT.get(state, state)


def progress_text(fraction) -> str:
    """The Progress column of our own run that runs (19.11.): a text bar and the percent, "▰▰▰▱▱ 60 %"."""
    try:
        f = min(1.0, max(0.0, float(fraction or 0.0)))
    except (TypeError, ValueError):
        f = 0.0
    full = int(round(f * BAR_CELLS))
    return "▰" * full + "▱" * (BAR_CELLS - full) + f" {int(f * 100)} %"


def generate_label(e: dict) -> str:
    """The Picture text of a Generate run in the queue window: how many pictures it makes, or which variant of how many
    it is when they run one after the other (user 18.11.: "2 variants sent, I want to see that")."""
    k, _, n = str(e.get("variant") or "").partition("/")
    if k.isdigit() and n.isdigit():
        return f"Generate · variant {int(k)} of {int(n)}"
    images = int(e.get("images") or 1)
    return f"Generate · {images} variants" if images > 1 else "Generate"


def q_values(idx, who, doc, status, fn, took) -> list:
    """One row of the queue list in the order of QueueWinMixin.Q_TEXT_COLS (Status last since 23.11.; while a run of ours runs
    the Status cell shows its bar, user 23.11.)."""
    by = {"idx": idx, "who": who, "pic": doc, "status": status, "fn": fn, "time": took}
    return [by[c] for c in QueueWinMixin.Q_TEXT_COLS]


class QueueWinMixin:
    # ---------- the queue window ----------

    # what a row can do sits in the row itself (user 13.11.): pause / resume and ✕ as small columns at the end; ↻ stands
    # where ✕ was, so ⏸ sits right next to ✕ (user 25.11.: a row never offers ✕ and ↻ at once)
    Q_ACT_COLS = ("pr", "x")
    # what a run is on the left, how far it is on the right (user 23.11., choice A): "#", Function, Document, Sent by, Time,
    # Progress, and Status last, next to the symbols it decides (replaces "Sent by" second, 19.11.)
    # Progress and Status are one column (user 23.11.: "während running steht dort der progress, danach done bzw. cancelled")
    Q_TEXT_COLS = ("idx", "fn", "pic", "who", "time", "status")
    Q_GLYPH = {"pause": "⏸", "resume": "▶", "retry": "↻", "cancel": "✕", "pause_batch": "⏸", "resume_batch": "▶",
               "cancel_batch": "✕"}

    def open_queue(self):
        """⋯ menu (and the start of a batch): the queue window. It can stay open; opening it again brings it to the front."""
        win = getattr(self, "_queue_win", None)
        if self._alive(win):
            self._raise_small(win)
            self._queue_fill()
            return
        self._queue_style()
        win, body = self._small_window("Queue", self._queue_close, at="settings")     # where the settings open (user 12.11.)
        self._queue_win = win
        self._queue_apply_size(win)
        for key in ("<KeyPress-q>", "<KeyPress-Q>"):        # a small window is no part of the plugin window's bindings
            win.bind(key, self._queue_key)
        self._q_fill_job = self._q_tick = None
        self._q_fetching = False
        self._q_entries = None         # ComfyUI's queue as last read (comes within the first tick)
        self._q_drag = None
        self._q_anchor = self._root_xy()
        if not getattr(self, "_q_follow_bound", False):          # the queue moves with the plugin (user 13.11.)
            self.root.bind("<Configure>", self._queue_follow, add="+")
            self._q_follow_bound = True
        # the list takes the whole height; the "Participants" list under it is gone (user 24.11.: "Sent by" names who sent
        # each run). Without ComfyUI a grey line under the list says so (it stood in that list before).
        top = ttk.Frame(body)
        top.pack(fill="both", expand=True)
        # every run on the ComfyUI of the network in one flat list, own and others', batch and Generate; "#" is the order
        # in which they run, "Sent by" the participant (user 18.11.); "#" first, no folding (user 19.11.)
        cols = self.Q_TEXT_COLS + self.Q_ACT_COLS
        tree = self.tv_queue = ttk.Treeview(top, columns=cols, show="headings", style="Queue.Treeview",
                                            height=10, selectmode="browse")
        saved = self._q_saved_cols()
        # "Document": the document the run was started in (user 23.11.; was "Picture")
        for c, text in (("idx", "#"), ("fn", "Function"), ("pic", "Document"), ("who", "Sent by"), ("time", "Time"),
                        ("status", "Status")):
            tree.heading(c, text=text, anchor="w")
            w = self._q_status_w() if c == Q_FIXED else saved.get(c, self._px(Q_COL_DEFAULT[c]))
            tree.column(c, width=w, minwidth=self._q_min(c), stretch=c == Q_FILLER, anchor="w")
        tree.tag_configure("other", foreground=DISABLED)       # runs of other participants: only to look at
        for c in self.Q_ACT_COLS:
            tree.heading(c, text="")
            tree.column(c, width=self._px(24), minwidth=self._px(24), stretch=False, anchor="center")
        self._q_want = {c: int(tree.column(c, "width")) for c in self._q_free_cols()}   # set at the headings
        self._q_coldrag = None
        self._q_lines = []
        self._q_seen = {}                      # prompt id of another's run -> when PxC first saw it running
        tree.bind("<Configure>", lambda e: self._queue_fit_cols(), add="+")
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", lambda e: (self._queue_buttons(), self._queue_marks()))
        for wheel in ("<MouseWheel>", "<Button-4>", "<Button-5>"):     # the coloured Status words follow the rows
            tree.bind(wheel, lambda e: self.root.after_idle(self._queue_marks), add="+")
        self._q_marks = []
        tree.bind("<ButtonPress-1>", self._queue_press, add="+")
        tree.bind("<B1-Motion>", self._queue_motion, add="+")
        tree.bind("<ButtonRelease-1>", self._queue_release, add="+")
        tree.bind("<Motion>", self._queue_hover, add="+")
        tree.bind("<Double-Button-1>", self._queue_double, add="+")
        tree.bind("<Button-3>", self._queue_head_menu, add="+")
        tree.bind("<KeyPress-Delete>", lambda e: self._queue_key_act("x"))
        tree.bind("<KeyPress-space>", lambda e: self._queue_key_act("pr"))
        self.lbl_q_detail = ttk.Label(top, text="", style=SET_STYLES["muted"], wraplength=self._px(480), justify="left")
        self.lbl_q_detail.pack(anchor="w", fill="x", pady=(4, 0))
        self.q_buttons = {}
        row = ttk.Frame(top)
        row.pack(fill="x", pady=(4, 6))
        # "Pause all" / "Resume all" act on every queued picture, whatever row is selected; no "Cancel batch" here: Stop batch
        # of the window does that (user 25.11.)
        for key, text in (("pause_all", "Pause all"), ("resume_all", "Resume all")):
            b = ttk.Button(row, text=text, style="SetSmall.TButton", command=lambda k=key: self._queue_do(k))
            b.pack(side="left", padx=(0, 4))
            self.q_buttons[key] = b
        # "Clear finished" takes only Done, "Clear all" Done, Cancelled and Error too (user 24.11.); waiting rows stay
        b = ttk.Button(row, text="Clear all", style="SetSmall.TButton", command=lambda: self._queue_do("clear_all"))
        b.pack(side="right")
        self.q_buttons["clear_all"] = b
        b = ttk.Button(row, text="Clear finished", style="SetSmall.TButton", command=lambda: self._queue_do("clear"))
        b.pack(side="right", padx=(0, 4))
        self.q_buttons["clear"] = b
        self.lbl_q_conn = ttk.Label(top, text="", style=SET_STYLES["muted"])      # packed only while ComfyUI is away
        self._queue_grip(win)
        self._queue_fill()
        self._queue_comfy_tick()

    def _queue_grip(self, win):
        """A grip in the lower right corner: the queue window has no frame of Windows, so this is how it is resized (user 13.11.)."""
        grip = self.lbl_q_grip = tk.Label(win, text="◢", bg=BG, fg=DISABLED, font=font(9), cursor=hostos.GRIP_CURSOR, bd=0)
        grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-1)
        drag = {}

        def start(e):
            drag["at"] = (e.x_root, e.y_root, win.winfo_width(), win.winfo_height())

        def move(e):
            if "at" not in drag:
                return
            x0, y0, w0, h0 = drag["at"]
            w = max(self._px(360), w0 + e.x_root - x0)
            h = max(self._px(260), h0 + e.y_root - y0)
            try:
                win.geometry(f"{w}x{h}")
            except tk.TclError:
                return
            sc = self._q_scale()
            self.state["queue_size"] = [round(w / sc), round(h / sc)]        # kept for the next start (user 19.11.)
        grip.bind("<ButtonPress-1>", start)
        grip.bind("<B1-Motion>", move)
        grip.bind("<ButtonRelease-1>", lambda e: drag.clear())

    def _queue_follow(self, e=None):
        """The queue window moves with the plugin window (user 13.11.), like the settings window."""
        if e is not None and e.widget is not self.root:
            return
        win = getattr(self, "_queue_win", None)
        if not self._alive(win):
            return
        now, was = self._root_xy(), getattr(self, "_q_anchor", None)
        if now is None or was is None or now == was or min(now) < -10000:      # a minimised window reports -32000
            return
        self._q_anchor = now
        try:
            win.geometry(f"+{win.winfo_x() + now[0] - was[0]}+{win.winfo_y() + now[1] - was[1]}")
        except tk.TclError:
            pass

    def _queue_style(self):
        if getattr(self, "_queue_styled", False):
            return
        s = ttk.Style(self.root)
        s.configure("Queue.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, font=font(9),
                    rowheight=self._px(20), borderwidth=0)
        s.map("Queue.Treeview", background=[("selected", ACCENT)], foreground=[("selected", ON_ACCENT)])
        s.configure("Queue.Treeview.Heading", background=BG, foreground="#ffffff", font=font(9, bold=True), relief="flat")
        s.map("Queue.Treeview.Heading", background=[("active", BG)])
        self._queue_styled = True

    def _queue_close(self):
        win, self._queue_win = getattr(self, "_queue_win", None), None
        self._q_drag = None
        try:        # had the queue the keyboard focus (it takes it when it opens)?
            f = self.root.focus_get()
            had_focus = self._alive(win) and f is not None and f.winfo_toplevel() is win
        except (tk.TclError, KeyError):
            had_focus = False
        for name in ("_q_tick", "_q_fill_job"):
            job = getattr(self, name, None)
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)
        if self._alive(win):
            win.destroy()
        if had_focus:
            self._focus_plugin()

    def _focus_plugin(self):
        """The focus back to the plugin window, not into a field: a closed window without a title bar left it to Windows,
        which gave it to no window of the plugin, and after a few rounds Q did nothing (user 13.11.)."""
        try:
            self.root.focus_force()
            f = self.root.focus_get()
            if f is None or f.winfo_class() in TYPING:
                self.root.focus_set()
        except (tk.TclError, KeyError):
            pass

    def _queue_dirty(self):
        """A runner event: the open queue window is filled anew once (not for every event of a burst)."""
        if self._alive(getattr(self, "_queue_win", None)) and not getattr(self, "_q_fill_job", None):
            self._q_fill_job = self.root.after(150, self._queue_fill)

    @staticmethod
    def _job_status_text(j: dict, entries: list | None = None) -> str:
        """The Status column; a picture PxC has sent but ComfyUI still keeps waiting reads "Waiting" (`entries`: ComfyUI's
        queue as last read), not "Running" (laptop test 18.11.)."""
        if j["status"] == jobqueue.ERROR and str(j.get("error", "")).startswith(jobqueue.SKIPPED):
            return "Skipped"
        if j["status"] == jobqueue.RUNNING and j.get("prompt_id"):
            if any(e["prompt_id"] == j["prompt_id"] and not e.get("running") for e in entries or ()):
                return "Waiting"
        return STATUS_TEXT.get(j["status"], j["status"])

    @staticmethod
    def _queue_index(jobs: list, entries: list) -> tuple[dict, set]:
        """The "#" column: ({job id: (place, text)}, the prompt ids of our own batch jobs). A place at ComfyUI is exact (1 runs
        first, in ComfyUI's order); a picture still waiting in PxC is counted on behind them as "~4": others can still queue
        in between (decision 18.11.). A paused picture shows no number but keeps its row between the ones around it in the
        queue (sort key n + 0.5): it went to the end of the list before, and the next picture slid under the mouse, so ⏸
        looked as if it paused another row (bug of 23.11.)."""
        place = {e["prompt_id"]: k for k, e in enumerate(entries, 1)}
        own = {j["prompt_id"] for j in jobs if j.get("prompt_id")}
        index = {}
        for j in jobs:
            if j.get("prompt_id") in place and j["status"] in jobqueue.ACTIVE:
                index[j["id"]] = (place[j["prompt_id"]], str(place[j["prompt_id"]]))
        n = len(entries)
        for j in jobs:
            if j["id"] in index:
                continue
            if j["status"] in (jobqueue.RUNNING, jobqueue.WAITING):
                n += 1
                index[j["id"]] = (n, f"~{n}")
            elif j["status"] == jobqueue.PAUSED:
                index[j["id"]] = (n + 0.5, "")
        return index, own

    def _job_time_text(self, j: dict) -> str:
        st = j["status"]
        if st == jobqueue.RUNNING:
            try:
                eta = self.runner.job_eta(j["id"])
            except Exception:
                eta = None
            return jobqueue.format_eta(eta) or (duration_text(time.time() - j["started"]) if j.get("started") else "")
        if st in (jobqueue.WAITING, jobqueue.PAUSED):
            return jobqueue.format_eta(j.get("eta"))
        if st in jobqueue.FINISHED and j.get("started") and j.get("finished"):   # the whole run (user 23.11.), cancelled too
            return duration_text(j["finished"] - j["started"])
        return ""

    @staticmethod
    def _job_actions(j: dict) -> dict:
        """What the row of a picture offers, by column: {"pr": "pause"|"resume", "x": "cancel"|"retry"}."""
        st = j["status"]
        acts = {}
        if st == jobqueue.WAITING:
            acts["pr"] = "pause"
        elif st == jobqueue.PAUSED:
            acts["pr"] = "resume"
        if st in (jobqueue.ERROR, jobqueue.CANCELLED) and not str(j.get("error", "")).startswith(jobqueue.SKIPPED):
            acts["x"] = "retry"          # in the column of ✕ (user 25.11.); ✕ is only for what is still on
        if st in jobqueue.ACTIVE:
            acts["x"] = "cancel"
        return acts

    @staticmethod
    def _batch_actions(b: dict, bjobs: list) -> dict:
        """What the row of a batch offers: pause or resume all its pictures, ✕ cancels the batch."""
        acts = {}
        if b.get("state") == jobqueue.B_CONFIRM and any(x["status"] in (jobqueue.WAITING, jobqueue.PAUSED) for x in bjobs):
            acts["pr"] = "resume_batch"        # the dry run waits for an answer (its window was closed): ▶ starts the rest (user 13.11.)
        elif any(x["status"] == jobqueue.WAITING for x in bjobs):
            acts["pr"] = "pause_batch"
        elif any(x["status"] == jobqueue.PAUSED for x in bjobs):
            acts["pr"] = "resume_batch"
        if b["state"] not in (jobqueue.B_DONE, jobqueue.B_CANCELLED):
            acts["x"] = "cancel_batch"
        return acts

    @staticmethod
    def _own_actions(d: dict | None) -> dict:
        """The row of a direct run of this window that ended: ↻ when it was cancelled or failed (and its settings are kept)."""
        return {"x": "retry"} if d and d.get("retry") else {}

    def _own_row(self, iid: str) -> dict | None:
        return next((d for d in getattr(self, "_q_own_done", None) or () if "o:" + str(d["id"]) == iid), None)

    def _entry_actions(self, e: dict | None) -> dict:
        """A ComfyUI entry: ✕ on the window's own direct run while it is on (window test 24.11.: "der erste lauf kann in
        der queue nicht abgebrochen werden, nur bei 2 und 3 kommt ein x"); it stops that run only, like "Stop run".
        Not on another participant's run, nor on a picture of a queued job (its job row has the ✕)."""
        if not e or not getattr(self, "_running", False):
            return {}
        me = getattr(getattr(self.bridge, "comfy", None), "client_id", None)
        if not me or e.get("client_id") != me:
            return {}
        try:
            queued = {j.get("prompt_id") for j in self.runner.jobs()}
        except Exception:
            queued = set()
        return {} if e.get("prompt_id") in queued else {"x": "cancel"}

    def _seq_rows(self) -> list:
        """The variants of the window's own run that goes one after the other (Sketch, Scribble, Multi Edit, Upscale, Refine
        with ×n; user 24.11. evening, choice C): the bridge's entry per variant while the run is on, else []."""
        if not getattr(self, "_running", False) or not getattr(self, "_run_seq", 0):
            return []
        return list(getattr(self.bridge, "seq_rows", None) or [])

    @staticmethod
    def _seq_actions(r: dict | None) -> dict:
        """✕ on a variant that waits (skips it) or runs (stops it, like "Stop run"); nothing on one that is over."""
        return {"x": "cancel"} if r and r.get("status") in ("waiting", "running") else {}

    def _row_actions(self, iid: str) -> dict:
        if iid.startswith("s:"):
            rows = self._seq_rows()
            k = int(iid[2:])
            return self._seq_actions(rows[k - 1] if 1 <= k <= len(rows) else None)
        if iid.startswith("j:"):
            j = self._q_jobs.get(iid[2:])
            return self._job_actions(j) if j else {}
        if iid.startswith("o:"):
            return self._own_actions(self._own_row(iid))
        if iid.startswith("c:"):
            e = next((x for x in getattr(self, "_q_entries", None) or () if x.get("prompt_id") == iid[2:]), None)
            return self._entry_actions(e)
        b = self._q_batches.get(iid[2:])
        if b is None:
            return {}
        return self._batch_actions(b, [x for x in self._q_jobs.values() if x["batch_id"] == b["id"]])

    def _queue_fill(self):
        self._q_fill_job = None
        tree = getattr(self, "tv_queue", None)
        if tree is None or not self._alive(getattr(self, "_queue_win", None)):
            return
        if getattr(self, "_q_drag", None):          # never redraw under a row that is being dragged: later
            self._q_fill_job = self.root.after(150, self._queue_fill)
            return
        jobs, batches = self.runner.jobs(), self.runner.batches()
        sel = tree.selection()
        tree.delete(*tree.get_children())
        self._q_jobs = {j["id"]: j for j in jobs}
        self._q_batches = {b["id"]: b for b in batches}
        entries = getattr(self, "_q_entries", None) or []
        me = getattr(self.bridge.comfy, "client_id", None)
        you = (getattr(self.runner, "owner", "") or "") + " (you)"
        index, own_pids = self._queue_index(jobs, entries)
        rows = []        # [sort key, iid, values (# … Time), symbols, tags, (kind, job or entry)]; flat (user 19.11.)
        far = float("inf")

        def glyphs(acts):
            return tuple(self.Q_GLYPH.get(acts.get(c, ""), "") for c in self.Q_ACT_COLS)
        for b in batches:
            mine = [j for j in jobs if j["batch_id"] == b["id"]]
            for n, j in enumerate(mine, 1):
                k, idx_text = index.get(j["id"], (far, ""))
                if j["status"] in jobqueue.FINISHED:
                    k = -far                       # finished: placed by when it was queued (_queue_order)
                if b.get("kind") == jobqueue.K_GENERATE:     # a queued Generate: function and model, its ×n
                    # the rest of a direct ×n: the direct run is 1/n, these count on from 2 (window test 23.11. late)
                    of = (getattr(self, "_rest_of", None) or {}).get(b["id"])
                    no, total = (n + 1, of) if of else (n, len(mine))
                    fn = str(b.get("label") or BATCH_WINDOW_MODES.get(j["mode"], j["mode"])) + (f" · {no}/{total}" if total > 1 else "")
                else:
                    fn = f"{BATCH_WINDOW_MODES.get(j['mode'], j['mode'])} · batch {n}/{len(mine)}"    # user 19.11.
                rows.append([k, "j:" + j["id"], q_values(idx_text, you, str(j["source"].get("name") or "?"),
                                                         self._job_status_text(j, entries), fn, ""),
                             glyphs(self._job_actions(j)), (), ("job", j)])
        gone = {pid for d in getattr(self, "_q_own_done", None) or () for pid in d.get("pids") or ()}
        seq = self._seq_rows()
        own_live = [k for k, e in enumerate(entries, 1) if me and e.get("client_id") == me
                    and e["prompt_id"] not in own_pids and e["prompt_id"] not in gone]
        if seq:         # every variant has its row from the start; the one at ComfyUI too (its entry is left out below)
            run_fn, run_doc = str(getattr(self, "_run_fn", "") or ""), str(getattr(self, "_run_doc", "") or "")
            # the rows stay one block in the order 1/n ... n/n at the place of the variant at ComfyUI (window test 24.11. late
            # evening: "ein teillauf wandert bei klick auf x plötzlich nach oben"): a finished variant is not sorted by time
            if own_live:
                self._seq_base = own_live[0]
            base = getattr(self, "_seq_base", None) or len(entries) + 1
            for v, r in enumerate(seq, 1):
                st = r["status"]
                key = base + v * 1e-3
                idx_text = str(own_live[0]) if st == "running" and own_live else ""
                status = {"waiting": STATUS_TEXT[jobqueue.WAITING], "running": STATUS_TEXT[jobqueue.RUNNING],
                          "done": STATUS_TEXT[jobqueue.DONE], "cancelled": STATUS_TEXT[jobqueue.CANCELLED],
                          "error": STATUS_TEXT[jobqueue.ERROR]}.get(st, st)
                took = duration_text(r["t1"] - r["t0"]) if r.get("t0") and r.get("t1") else ""
                rows.append([key, f"s:{v}", q_values(idx_text, you, run_doc, status, f"{run_fn} · {v}/{len(seq)}", took),
                             glyphs(self._seq_actions(r)), (), ("seq", dict(r, no=v))])
        for k, e in enumerate(entries, 1):
            if e["prompt_id"] in own_pids or e["prompt_id"] in gone:    # gone: the window's own run that has ended
                continue
            ours = bool(me) and e.get("client_id") == me
            if ours and seq:            # the variant rows above stand for it
                continue
            who = you if ours else (e.get("owner") or "unknown")
            what = generate_label(e) if ours else self._foreign_what(e)
            # the window's own run: its document, function and model, as the queued ones show them (window test 23.11.)
            fn = ""
            if ours and getattr(self, "_running", False):
                fn = str(getattr(self, "_run_fn", "") or "")
                what = str(getattr(self, "_run_doc", "") or "") or what
            rows.append([k, "c:" + e["prompt_id"], q_values(str(k), who, what, "Running" if e.get("running") else "Waiting", fn, ""),
                         glyphs(self._entry_actions(e)), () if ours else ("other",), ("entry", e)])
        for d in getattr(self, "_q_own_done", None) or ():         # the window's own runs that ended (user 23.11.)
            rows.append([-far, "o:" + str(d["id"]), q_values("", you, d["doc"], d["status"], d["fn"], d["took"]),
                         glyphs(self._own_actions(d)), (), ("own", d)])
        for d in getattr(self, "_q_foreign_done", None) or ():     # Paket 3 (user 19.11., choice A): others' runs PxC saw
            took = duration_text(d["finished"] - d["started"]) if d.get("started") else ""
            rows.append([-far, "d:" + d["prompt_id"], q_values("", d.get("owner") or "unknown", self._foreign_what(d), "Done", "", took),
                         glyphs({}), ("other",), ("done", d)])
        rows = self._queue_order(rows, jobs, me)
        self._queue_times(rows, jobs)
        for _key, iid, values, acts, tags, _what in rows:
            tree.insert("", "end", iid=iid, values=tuple(values) + acts, tags=tags)
        keep = [i for i in sel if tree.exists(i)]
        if keep:
            tree.selection_set(keep)
        self._queue_buttons()
        self._queue_marks()

    def _row_time(self, row, jobs_by_id: dict, me) -> float:
        """When a row came into the queue: a job when it was queued, the window's own run when it started, another's
        run when PxC first saw it (or ended)."""
        kind, what = row[5]
        if kind == "job":       # its batch's time (the jobs are made later, when the batch is prepared), then its order
            b = (getattr(self, "_q_batches", None) or {}).get(what.get("batch_id")) or {}
            base = float(b.get("created") or what.get("created") or 0.0)
            return base + float(what.get("order") or 0) * 1e-6
        if kind == "own":
            return float(what.get("t0") or 0.0)
        if kind == "seq":
            return float(what.get("t0") or getattr(self, "_run_t0", None) or 0.0) + what.get("no", 0) * 1e-6
        if kind == "entry":
            if me and what.get("client_id") == me and getattr(self, "_run_t0", None):
                return float(self._run_t0)
            return float((getattr(self, "_q_seen", {}) or {}).get(what["prompt_id"]) or time.time())
        return float(what.get("started") or what.get("finished") or 0.0)

    def _queue_order(self, rows: list, jobs: list, me) -> list:
        """The order of the list (user 23.11. late, replaces "what is through stands on top" of 19.11.): what runs and
        waits in the queue's order; a finished row (Done, Cancelled, Error) keeps its place among them, by when it was
        queued: it goes in front of the first running or waiting row that came later. "Clear finished" removes it."""
        far = float("inf")
        jobs_by_id = {j["id"]: j for j in jobs}
        live = sorted((r for r in rows if r[0] != -far), key=lambda r: r[0])     # stable: no place keeps its order
        done = sorted((r for r in rows if r[0] == -far), key=lambda r: self._row_time(r, jobs_by_id, me))
        out = []
        for r in live:
            t = self._row_time(r, jobs_by_id, me)
            while done and self._row_time(done[0], jobs_by_id, me) <= t:
                out.append(done.pop(0))
            out.append(r)
        return out + done

    def _queue_marks(self):
        """Done green, Cancelled and Error red, only the word in Status (user 23.11. evening). A Treeview colours only
        whole rows, so each word is a small label laid over its cell (like the column lines); clicks, drags and the wheel
        on it go on to the list. Called after every fill, selection, scroll and column change."""
        tree = getattr(self, "tv_queue", None)
        marks = getattr(self, "_q_marks", None)
        if tree is None or marks is None:
            return
        want = []
        try:
            sel = set(tree.selection())
            for iid in tree.get_children(""):
                text = str(tree.set(iid, "status"))
                color = Q_STATUS_COLORS.get(text)
                box = tree.bbox(iid, "status") if color else ""
                if box:
                    want.append((text, color, iid in sel, box))
        except tk.TclError:
            return
        while len(marks) < len(want):
            lab = tk.Label(tree, bd=0, highlightthickness=0, padx=self._px(3), pady=0, anchor="w", font=font(9))
            self._queue_mark_events(lab)
            marks.append(lab)
        for k, lab in enumerate(marks):
            try:
                if k < len(want):
                    text, color, on, (x, y, w, h) = want[k]
                    lab.configure(text=text, bg=ACCENT if on else PANEL, fg=ON_ACCENT if on else color)
                    lab.place(x=x + 1, y=y, width=max(1, w - 2), height=h)
                elif lab.winfo_manager():
                    lab.place_forget()
            except tk.TclError:
                pass

    def _queue_mark_events(self, lab):
        """A click, drag, double-click, right-click or wheel on a coloured Status word acts on the list under it."""
        tree = self.tv_queue

        def ev(e):
            return type("E", (), {"x": lab.winfo_x() + e.x, "y": lab.winfo_y() + e.y, "x_root": e.x_root,
                                  "y_root": e.y_root, "delta": getattr(e, "delta", 0), "num": getattr(e, "num", 0)})()

        def press(e):
            r = self._queue_press(ev(e))
            if r is None:                                   # the row under the word is selected as on the list
                iid = tree.identify_row(ev(e).y)
                if iid:
                    tree.selection_set(iid)
                    tree.focus(iid)
            return r

        def wheel(e):
            step = -1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 1
            tree.yview_scroll(step, "units")
            self.root.after_idle(self._queue_marks)
            return "break"
        lab.bind("<ButtonPress-1>", press)
        lab._q_press = press                                # for the test (a hidden window gets no generated clicks)
        lab.bind("<B1-Motion>", lambda e: self._queue_motion(ev(e)))
        lab.bind("<ButtonRelease-1>", lambda e: self._queue_release(ev(e)))
        lab.bind("<Double-Button-1>", lambda e: self._queue_double(ev(e)))
        lab.bind("<Button-3>", lambda e: self._queue_head_menu(ev(e)))
        lab.bind("<Motion>", lambda e: self._queue_hover(ev(e)))
        for w in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            lab.bind(w, wheel)

    @staticmethod
    def _foreign_what(e: dict) -> str:
        """The Picture text of another's run: "Batch" (no picture names of others), a Generate run's count, "ComfyUI"
        for a run not sent by PxC."""
        if e.get("kind") == "batch":
            return "Batch"
        return generate_label(e) if e.get("kind") == "generate" else "ComfyUI"

    def _queue_note_own_done(self, text: str) -> None:
        """A run of this window ended ("done" event): it stays in the queue window as Done, Cancelled or Error with its
        whole run time (user 23.11.: a cancelled first run vanished, the queued ones stayed), until "Clear finished"."""
        t0 = getattr(self, "_run_t0", None)
        if not t0:
            return
        self._run_t0 = None
        st = (jobqueue.DONE if not text.startswith(("Error", "Cancel", "Unexpected"))
              else jobqueue.CANCELLED if text.startswith("Cancel") else jobqueue.ERROR)
        done = getattr(self, "_q_own_done", None)
        if done is None:
            done = self._q_own_done = []
        self._q_own_n = getattr(self, "_q_own_n", 0) + 1
        # its prompt at ComfyUI: ComfyUI's queue as last read still lists it for up to ~2 s (a stopped run showed twice,
        # window test 23.11. evening); the fill leaves that entry out
        me = getattr(getattr(self.bridge, "comfy", None), "client_id", None)
        try:
            queued = {j.get("prompt_id") for j in self.runner.jobs()}
        except Exception:
            queued = set()
        pids = [e["prompt_id"] for e in getattr(self, "_q_entries", None) or ()
                if me and e.get("client_id") == me and e.get("prompt_id") not in queued]
        keep, self._run_retry = getattr(self, "_run_retry", None), None
        if keep is not None:
            keep.pop("capture", None)
        seq = list(getattr(self.bridge, "seq_rows", None) or []) if getattr(self, "_run_seq", 0) else []
        self._run_seq, self._seq_base = 0, None
        if seq:         # ×n one after the other: each variant keeps its own row (user 24.11. evening, choice C); no ↻ (it would run all n)
            fn = str(getattr(self, "_run_fn", "") or "")
            for v, r in enumerate(seq, 1):
                vst = {"done": jobqueue.DONE, "error": jobqueue.ERROR}.get(r["status"], jobqueue.CANCELLED)
                if v > 1:
                    self._q_own_n += 1
                done.append({"id": self._q_own_n, "doc": str(getattr(self, "_run_doc", "") or ""), "fn": f"{fn} · {v}/{len(seq)}",
                             "status": STATUS_TEXT.get(vst, vst), "pids": pids if v == 1 else [],
                             "took": duration_text(r["t1"] - r["t0"]) if r.get("t0") and r.get("t1") else "",
                             "t0": t0 + v * 1e-6, "retry": None})      # in the order 1/n ... n/n (a skipped one has no start)
        else:
            done.append({"id": self._q_own_n, "doc": str(getattr(self, "_run_doc", "") or ""), "fn": str(getattr(self, "_run_fn", "") or ""),
                         "status": STATUS_TEXT.get(st, st), "took": duration_text(time.time() - t0), "pids": pids, "t0": t0,
                         "retry": keep if st != jobqueue.DONE else None})      # ↻ like a queued picture (window test 23.11. late)
        del done[:-Q_FOREIGN_DONE_MAX]
        for old in done[:-Q_OWN_RETRY_MAX]:         # a picture per row: only the newest rows keep their ↻
            old["retry"] = None
        self._queue_dirty()

    def _queue_note_foreign_done(self, old: list | None, new: list | None) -> None:
        """Paket 3 (user 19.11., choice A): a run of another participant that PxC saw running and that has left ComfyUI's
        queue stays in the list as "Done", with the time since PxC saw it start, until "Clear finished" (which removes
        them too, user 19.11.). No extra request to ComfyUI: what ran while the queue window was closed is missing, and a
        run the other one cancelled while it ran also reads "Done" (ComfyUI's /queue does not tell)."""
        if old is None or new is None:              # not read (ComfyUI away): nothing can be said about what ended
            return
        me = getattr(getattr(getattr(self, "bridge", None), "comfy", None), "client_id", None)
        still = {e["prompt_id"] for e in new}
        done = getattr(self, "_q_foreign_done", None)
        if done is None:
            done = self._q_foreign_done = []
        done[:] = [d for d in done if d["prompt_id"] not in still]      # back at ComfyUI (never seen live): not done after all
        known = {d["prompt_id"] for d in done}
        seen = getattr(self, "_q_seen", {})
        now = time.time()
        for e in old:
            pid = e["prompt_id"]
            if not e.get("running") or pid in still or pid in known or (me and e.get("client_id") == me):
                continue
            done.append(dict(e, running=False, started=seen.get(pid), finished=now))
        del done[:-Q_FOREIGN_DONE_MAX]

    def _queue_times(self, rows: list, jobs: list) -> None:
        """The Time column, in the order the rows run (user 19.11.): what is done, its duration; what runs, the time it still
        needs (another's run: the time since PxC saw it start); what waits, when it starts ("starts in ~3 min"), from the
        estimates of everything ahead of it. Others' runs count with the average of our own; without any estimate the
        start times stop there (no guess).
        The Status cell of a run that runs (user 23.11.: one column with Progress): our own run, the bar of the window as a
        text bar ("▰▰▰▱▱ 60 %"; the progress PxC gets for its own runs, batch and Generate); another's run keeps "Running"
        (ComfyUI sends the progress only to the one who queued it; its time since the start is in Time)."""
        done = [j["finished"] - j["started"] for j in jobs if j["status"] == jobqueue.DONE and j.get("started") and j.get("finished")]
        avg = sum(done) / len(done) if done else None
        now = time.time()
        seen = getattr(self, "_q_seen", {})
        running = {e["prompt_id"] for _k, _i, _v, _a, _t, (kind, e) in rows if kind == "entry" and e.get("running")}
        for pid in [p for p in seen if p not in running]:
            del seen[pid]
        ahead = 0.0                 # seconds until the next row starts; None = unknown
        me = getattr(getattr(getattr(self, "bridge", None), "comfy", None), "client_id", None)
        bar = progress_text(getattr(self, "_bar_value", 0.0))
        generating = bool(getattr(self, "_running", False))
        S, T = (self.Q_TEXT_COLS.index(c) for c in ("status", "time"))
        for row in rows:
            kind, x = row[5]
            values = row[2]
            if kind in ("done", "own"):             # a run that is through: its time is set already
                continue
            if kind == "seq":                       # a variant of the window's own run (choice C, 24.11.)
                st = x["status"]
                if st == "running":
                    values[T] = duration_text(now - x["t0"]) if x.get("t0") else ""
                    n_seq = max(1, int(getattr(self, "_run_seq", 0) or 1))      # the bar runs over all n: this variant's part
                    part = float(getattr(self, "_bar_value", 0.0) or 0.0) * n_seq - (x.get("no", 1) - 1)
                    values[S] = progress_text(min(1.0, max(0.0, part)))
                    need = None if avg is None or not x.get("t0") else max(0.0, avg - (now - x["t0"]))
                elif st == "waiting":
                    values[T] = f"starts in {jobqueue.format_eta(ahead)}" if ahead is not None else ""
                    need = avg
                else:
                    continue
                ahead = None if ahead is None or need is None else ahead + need
                continue
            if kind == "job":
                st = x["status"]
                if st in (jobqueue.DONE, jobqueue.ERROR, jobqueue.CANCELLED, jobqueue.PAUSED):
                    values[T] = self._job_time_text(x) if st != jobqueue.PAUSED else ""
                    continue
                try:
                    need = self.runner.job_eta(x["id"])
                except Exception:
                    need = None
                if st == jobqueue.RUNNING and values[S] == STATUS_TEXT[jobqueue.RUNNING]:
                    values[T] = self._job_time_text(x)
                    values[S] = bar
                else:
                    values[T] = f"starts in {jobqueue.format_eta(ahead)}" if ahead is not None else ""
                ahead = None if ahead is None or need is None else ahead + need
            else:
                pid = x["prompt_id"]
                if x.get("running"):
                    t0 = seen.setdefault(pid, now)
                    values[T] = duration_text(now - t0)
                    ours = bool(me) and x.get("client_id") == me
                    if ours and generating:         # another's run keeps "Running"; its time since the start is in Time
                        values[S] = bar
                    need = None if avg is None else max(0.0, avg - (now - t0))
                else:
                    values[T] = f"starts in {jobqueue.format_eta(ahead)}" if ahead is not None else ""
                    need = avg
                ahead = None if ahead is None or need is None else ahead + need
        self._q_seen = seen

    def _queue_selected(self) -> tuple[dict | None, dict | None]:
        """(the selected job, its batch) or (None, the selected batch); (None, None) without a selection."""
        tree = getattr(self, "tv_queue", None)
        sel = tree.selection() if tree is not None else ()
        if not sel:
            return None, None
        iid = sel[0]
        if iid.startswith("j:"):
            j = self._q_jobs.get(iid[2:])
            return j, (self._q_batches.get(j["batch_id"]) if j else None)
        return None, self._q_batches.get(iid[2:])

    def _queue_buttons(self):
        """The buttons under the list act on the batch of the selected row; each only where it can do something."""
        if not getattr(self, "q_buttons", None):
            return
        j, b = self._queue_selected()
        can = {
            "pause_all": any(x["status"] == jobqueue.WAITING for x in self._q_jobs.values()),
            "resume_all": any(x["status"] == jobqueue.PAUSED for x in self._q_jobs.values()),
            "clear": any(x["status"] == jobqueue.DONE for x in self._q_jobs.values())
                     or bool(getattr(self, "_q_foreign_done", None))
                     or any(d.get("status") == STATUS_TEXT[jobqueue.DONE] for d in getattr(self, "_q_own_done", None) or ()),
            "clear_all": any(x["status"] in jobqueue.FINISHED for x in self._q_jobs.values())
                         or bool(getattr(self, "_q_foreign_done", None)) or bool(getattr(self, "_q_own_done", None)),
        }
        for key, b_ in self.q_buttons.items():
            b_.configure(state="normal" if can.get(key) else "disabled")
        detail = ""
        if j:
            if j.get("error"):
                detail = j["error"]
            elif j.get("results"):
                detail = "Saved: " + ", ".join(Path(p).name for p in j["results"])
            elif j.get("placed"):
                detail = PLACED_TEXT.get(j["placed"], "")
        elif b and b.get("skipped"):
            detail = "Skipped: " + "; ".join(b["skipped"])
        self.lbl_q_detail.configure(text=detail)

    def _queue_do(self, action: str, iid: str | None = None):
        """A button under the list (for the selected row's batch) or a click on a row's own symbol (`iid`)."""
        if iid is not None and iid.startswith("o:"):         # the row of a direct run: only ↻
            d = self._own_row(iid)
            if action == "retry" and d is not None:
                self._own_retry(d)
            self._queue_fill()
            return
        if iid is not None and iid.startswith("s:"):         # ✕ on a variant: skip it, or Stop run when it runs
            rows = self._seq_rows()
            k = int(iid[2:])
            r = rows[k - 1] if 1 <= k <= len(rows) else None
            if action == "cancel" and r is not None:
                if r["status"] == "running":
                    self.stop()
                else:
                    self.bridge.skip_variant(k)
            self._queue_fill()
            return
        if iid is not None and iid.startswith("c:"):         # ✕ on the window's own direct run: Stop run
            if action == "cancel" and self._row_actions(iid).get("x") == "cancel":
                self.stop()
            self._queue_fill()
            return
        if iid is not None:
            j = self._q_jobs.get(iid[2:]) if iid.startswith("j:") else None
            b = self._q_batches.get(iid[2:]) if iid.startswith("b:") else (self._q_batches.get(j["batch_id"]) if j else None)
        else:
            j, b = self._queue_selected()
        r = self.runner
        ok = True
        if action in ("clear", "clear_all"):    # "Clear finished": Done only; "Clear all": Cancelled and Error too (24.11.)
            every = action == "clear_all"
            r.clear_finished(jobqueue.FINISHED if every else (jobqueue.DONE,))
            self._q_foreign_done = []           # the finished runs of others go too (user 19.11.; they read "Done")
            self._q_own_done = [] if every else [   # and the window's own (user 23.11.)
                d for d in getattr(self, "_q_own_done", None) or () if d.get("status") != STATUS_TEXT[jobqueue.DONE]]
        elif action in ("pause_all", "resume_all"):     # every batch with a waiting / paused picture (user 25.11.)
            want = jobqueue.WAITING if action == "pause_all" else jobqueue.PAUSED
            for bid in dict.fromkeys(x["batch_id"] for x in self._q_jobs.values() if x["status"] == want):
                getattr(r, action.replace("_all", "_batch"))(bid)
        elif action in ("pause_batch", "resume_batch", "cancel_batch"):
            if b is None:
                return
            getattr(r, action)(b["id"])
        elif j is not None:
            ok = getattr(r, action)(j["id"])
        self._queue_fill()
        if action == "retry" and not ok:
            self.lbl_q_detail.configure(text="Can't retry: the settings of this batch are gone (PxC was restarted).")
        self._batch_sync_soon()

    # clicks in the list: a row's symbol does its action; a waiting or paused picture can be dragged to a new place (user 13.11.)

    def _queue_cell(self, e) -> tuple[str, str]:
        """(row iid, action column name or "") under the mouse."""
        tree = self.tv_queue
        iid = tree.identify_row(e.y)
        col = tree.identify_column(e.x)              # "#0", "#1" …
        name = ""
        try:
            k = int(col.lstrip("#")) - 1
            cols = tree.cget("columns")
            if 0 <= k < len(cols) and cols[k] in self.Q_ACT_COLS:
                name = cols[k]
        except (ValueError, tk.TclError):
            pass
        return iid, name

    def _queue_toggle(self):
        """The queue symbol in the footer (user 24.11. evening, where the clock was): opens the queue window, closes it
        when it is open, like Q."""
        if self._alive(getattr(self, "_queue_win", None)):
            self._queue_close()
        else:
            self.open_queue()

    def _queue_key(self, e=None):
        """Q in the plugin window or in the queue itself toggles the queue: opens it, closes it when it is open (user 13.11.);
        typed into a field it is just a letter."""
        try:
            w = self.root.focus_get()
            cls = w.winfo_class() if w is not None else ""
        except (tk.TclError, KeyError):
            cls = ""
        if cls in TYPING:
            return None
        if self._alive(getattr(self, "_queue_win", None)):
            self._queue_close()
        else:
            self.open_queue()
        return "break"

    def _escape_key(self, e=None):
        """Escape in the plugin window only closes windows (user 20.11.): the queue when it is open, else the settings
        window; it never stops a run (that is the grey "Stop" on Generate or Ctrl+Alt+Enter)."""
        if self._alive(getattr(self, "_queue_win", None)):
            self._queue_close()
            return "break"
        if self._alive(getattr(self, "_settings_win", None)):
            self._settings_close()
            return "break"
        return None

    def _queue_hover(self, e):
        iid, col = self._queue_cell(e)
        want = "hand2" if iid and col and self._row_actions(iid).get(col) else ""
        try:
            if str(self.tv_queue.cget("cursor")) != want:
                self.tv_queue.configure(cursor=want)
        except tk.TclError:
            pass

    def _queue_press(self, e):
        self._q_drag = None
        self._q_coldrag = None
        try:
            self.tv_queue.focus_set()        # Escape closes the window: the list keeps the keyboard focus, also on a symbol
        except tk.TclError:
            pass
        tree = self.tv_queue
        if tree.identify_region(e.x, e.y) == "separator":
            col = self._queue_sep_col(e.x)
            if col is not None:              # PxC drags the line itself, not Tk (user 19.11.: the columns jumped)
                self._q_coldrag = {"col": col, "x": e.x, "w": self._queue_widths()}
            return "break"                   # the symbol columns keep their width
        iid, col = self._queue_cell(e)
        if not iid:
            return None
        if col:
            action = self._row_actions(iid).get(col)
            if action:
                self._queue_do(action, iid)
                return "break"                       # the symbol does not also select the row
            return None
        j = self._q_jobs.get(iid[2:]) if iid.startswith("j:") else None
        if self._q_movable(j):
            self._q_drag = {"iid": iid, "batch": j["batch_id"], "moved": False}
        return None

    @staticmethod
    def _q_movable(j: dict | None) -> bool:
        """A picture that can be dragged: waiting or paused in PxC."""
        return bool(j) and j["status"] in (jobqueue.WAITING, jobqueue.PAUSED)

    def _queue_motion(self, e):
        if getattr(self, "_q_coldrag", None):
            self._queue_drag_col(e.x)
            return "break"                   # Tk's own column drag stays out
        d = getattr(self, "_q_drag", None)
        if not d:
            return
        tree = self.tv_queue
        target = tree.identify_row(e.y)
        if not target or target == d["iid"] or not target.startswith("j:"):
            return
        t = self._q_jobs.get(target[2:])
        if not self._q_movable(t) or t["batch_id"] != d["batch"]:
            return
        tree.move(d["iid"], "", tree.index(target))
        d["moved"] = True
        tree.configure(cursor="sb_v_double_arrow")

    def _q_min(self, c: str) -> int:
        if c == Q_FIXED:
            return self._q_status_w()
        return self._px(Q_PICTURE_MIN if c == Q_FILLER else 30 if c == "idx" else Q_COL_MIN)

    def _q_status_w(self) -> int:
        """The fixed width of Status (user 24.11. evening): its longest text (the bar at 100 %, "Cancelled", the heading in
        bold) and the cell's padding; the symbols keep their own 24 px each right of it, with no line in between."""
        try:
            body = tkfont.Font(root=self.root, font=font(9))
            head = tkfont.Font(root=self.root, font=font(9, bold=True))
            need = max(max(body.measure(t) for t in Q_STATUS_TEXTS), head.measure("Status"))
        except tk.TclError:
            return self._px(Q_COL_DEFAULT[Q_FIXED])
        return need + self._px(14)

    def _q_free_cols(self) -> tuple:
        """The text columns whose width is set at the headings (not Document, which takes the rest, and not Status)."""
        return tuple(c for c in self.Q_TEXT_COLS if c not in (Q_FILLER, Q_FIXED))

    def _q_scale(self) -> float:
        return self._px(1000) / 1000.0

    def _q_saved_cols(self) -> dict:
        """The widths set at the headings last time (state.json "queue_cols", px before scaling; user 19.11.)."""
        d = self.state.get("queue_cols")
        out = {}
        if isinstance(d, dict):
            for c, v in d.items():
                if c in self._q_free_cols() and isinstance(v, (int, float)) and v > 0:
                    out[c] = max(self._q_min(c), self._px(int(v)))
        return out

    def _queue_remember_cols(self):
        sc = self._q_scale()
        self.state["queue_cols"] = {c: round(w / sc) for c, w in self._q_want.items()}

    def _queue_apply_size(self, win):
        """The size the queue window had when it was last resized (state.json "queue_size"; user 19.11.)."""
        size = self.state.get("queue_size")
        if not (isinstance(size, (list, tuple)) and len(size) == 2):
            return
        try:
            w, h = max(self._px(360), self._px(int(size[0]))), max(self._px(260), self._px(int(size[1])))
            win.geometry(f"{w}x{h}")
        except (tk.TclError, TypeError, ValueError):
            pass

    def _queue_widths(self) -> dict:
        tree = self.tv_queue
        return {c: int(tree.column(c, "width")) for c in tree.cget("columns")}

    def _queue_sep_col(self, x: int):
        """The text column whose right edge is nearest to x; None for the edge of a symbol column."""
        edge, best, dist = 0, None, 10 ** 6
        for c, w in self._queue_widths().items():
            edge += w
            if abs(edge - x) < dist:
                best, dist = c, abs(edge - x)
        return None if best in self.Q_ACT_COLS or best == Q_FIXED else best

    def _queue_col_at(self, x: int):
        """The text column under x (None: a symbol column or nothing)."""
        try:
            k = int(self.tv_queue.identify_column(x).lstrip("#")) - 1
        except (ValueError, tk.TclError):
            return None
        cols = self.tv_queue.cget("columns")
        return cols[k] if 0 <= k < len(cols) and cols[k] in self.Q_TEXT_COLS and cols[k] != Q_FIXED else None

    def _queue_drag_col(self, x: int):
        """A heading line is dragged (user 19.11.): the line follows the mouse and the column left of it gets exactly that
        width; the column to its right gives way (at its minimum the next one); only "Time", which has the symbols on its
        right, takes its room from Picture. The widths that come out are the ones set (_q_want)."""
        d = self._q_coldrag
        w = dict(d["w"])
        col, dx = d["col"], x - d["x"]
        order = tuple(c for c in self.Q_TEXT_COLS if c != Q_FIXED)
        right = list(order[order.index(col) + 1:])
        if not right:                                   # "Time", left of the fixed Status: Picture gives and takes
            dx = max(self._q_min(col) - w[col], min(dx, w[Q_FILLER] - self._q_min(Q_FILLER)))
            w[col] += dx
            w[Q_FILLER] -= dx
        elif dx >= 0:                                   # wider: the columns to the right give way, nearest first
            dx = min(dx, sum(w[c] - self._q_min(c) for c in right))
            w[col] += dx
            need = dx
            for c in right:
                give = max(0, min(need, w[c] - self._q_min(c)))
                w[c] -= give
                need -= give
        else:                                           # narrower: the neighbour on the right takes the room
            dx = max(dx, self._q_min(col) - w[col])
            w[col] += dx
            w[right[0]] -= dx
        tree = self.tv_queue
        for c in order:
            if int(tree.column(c, "width")) != w[c]:
                tree.column(c, width=w[c])
        self._q_want.update({c: w[c] for c in order if c != Q_FILLER})
        self._queue_grid()

    def _queue_fit_cols(self):
        """The columns always fill the list exactly (user 13.11.: the symbols never slide out of sight, no gap): the text
        columns get the widths set at the headings (_q_want, user 19.11.), Picture takes what is left; when it would get
        narrower than its minimum, the text columns give way, the one next to the symbols first, and get their set widths
        back as soon as the window is wide enough again."""
        tree = getattr(self, "tv_queue", None)
        try:
            avail = tree.winfo_width() - Q_TREE_INSET if tree is not None else 0
        except tk.TclError:
            return
        if avail < 50:
            return
        want = getattr(self, "_q_want", None) or {c: int(tree.column(c, "width")) for c in self._q_free_cols()}
        w = {c: v for c, v in want.items() if c in self._q_free_cols()}
        fixed = sum(int(tree.column(c, "width")) for c in self.Q_ACT_COLS) + self._q_status_w()
        pic = avail - fixed - sum(w.values())
        low = self._q_min(Q_FILLER)
        if pic < low:
            short = low - pic
            pic = low
            for c in ("time", "fn", "who", "idx"):     # the column next to Status gives way first (Status keeps its width)
                give = max(0, min(short, w[c] - self._q_min(c)))
                w[c] -= give
                short -= give
                if short <= 0:
                    break
        w[Q_FILLER] = pic
        w[Q_FIXED] = self._q_status_w()
        for c, v in w.items():
            if int(tree.column(c, "width")) != v:
                tree.column(c, width=v)
        self._queue_grid()

    def _queue_head_h(self) -> int:
        """The height of the heading row (where the list's own separators are)."""
        tree = self.tv_queue
        try:
            for y in range(1, self._px(80)):
                if tree.identify_region(self._px(5), y) != "heading":
                    return y if y > 4 else self._px(22)
        except tk.TclError:
            pass
        return self._px(22)

    def _queue_grid(self):
        """Light lines between the columns, in the heading and in the rows (user 19.11.: the separators were hardly visible).
        They are 1 px frames on the list; a click or drag on one goes on to the list as if it were on the list itself."""
        tree = getattr(self, "tv_queue", None)
        if tree is None:
            return
        try:
            head = self._queue_head_h()
            xs, edge = [], 0
            for c in tuple(tree.cget("columns"))[:-1]:
                edge += int(tree.column(c, "width"))
                # no lines between the symbols ⏸ ↻ ✕ (user 19.11.), none between Status and them either (window test
                # 23.11. evening: "nach der jetzigen spalte status sind noch linien"); the edge can still be dragged
                if c in self.Q_TEXT_COLS[:-1]:
                    xs.append(edge)
        except tk.TclError:
            return
        lines = self._q_lines
        while len(lines) < len(xs):
            pair = (tk.Frame(tree, bg=Q_GRID_HEAD, width=1, bd=0, highlightthickness=0, cursor="sb_h_double_arrow"),
                    tk.Frame(tree, bg=Q_GRID_BODY, width=1, bd=0, highlightthickness=0))
            for line in pair:
                self._queue_line_events(line)
            lines.append(pair)
        for k, (hl, bl) in enumerate(lines):
            if k < len(xs):
                hl.place(x=xs[k] - 1, y=0, width=1, height=head)
                bl.place(x=xs[k] - 1, y=head, width=1, relheight=1.0, height=-head)
            else:
                hl.place_forget()
                bl.place_forget()
        self._queue_marks()              # the coloured Status words follow a column that changed its width

    def _queue_line_events(self, line):
        def ev(e):
            return type("E", (), {"x": line.winfo_x() + 1, "y": line.winfo_y() + e.y, "x_root": e.x_root, "y_root": e.y_root})()

        def motion(e):
            d = getattr(self, "_q_coldrag", None)
            if d:                                           # the line follows the mouse, not the frame's own place
                self._queue_drag_col(e.x_root - d["x_root"] + d["x"])
            else:
                self._queue_motion(ev(e))

        def press(e):
            r = self._queue_press(ev(e))
            if getattr(self, "_q_coldrag", None):
                self._q_coldrag["x_root"] = e.x_root
            elif r is None:                                 # a row under the line: it is selected as on the list
                iid = self.tv_queue.identify_row(ev(e).y)
                if iid:
                    self.tv_queue.selection_set(iid)
            return r
        line.bind("<ButtonPress-1>", press)
        line.bind("<B1-Motion>", motion)
        line.bind("<ButtonRelease-1>", lambda e: self._queue_release(ev(e)))
        line.bind("<Double-Button-1>", lambda e: self._queue_double(ev(e)))
        line.bind("<Button-3>", lambda e: self._queue_head_menu(ev(e)))

    def _queue_double(self, e):
        """A double-click on a heading or its line sets the column to the width of its longest text (user 19.11.)."""
        tree = self.tv_queue
        region = tree.identify_region(e.x, e.y)
        if region == "separator":
            col = self._queue_sep_col(e.x)
        elif region == "heading":
            col = self._queue_col_at(e.x)
        else:
            return None
        if col:
            self._queue_autofit(col)
        return "break"

    def _queue_autofit(self, col: str):
        tree = self.tv_queue
        body, head = tkfont.Font(root=self.root, font=font(9)), tkfont.Font(root=self.root, font=font(9, bold=True))
        texts = [str(tree.set(i, col)) for i in tree.get_children("")]
        want = max([body.measure(t) for t in texts] + [head.measure(str(tree.heading(col, "text")))]) + self._px(14)
        want = max(want, self._q_min(col))
        self._q_coldrag = {"col": col, "x": 0, "w": self._queue_widths()}
        self._queue_drag_col(want - int(tree.column(col, "width")))       # the columns to the right give way first
        self._q_coldrag = None
        short = want - int(tree.column(col, "width"))
        if short > 0 and col != Q_FILLER:                                  # then Picture, down to its minimum
            give = max(0, min(short, int(tree.column(Q_FILLER, "width")) - self._q_min(Q_FILLER)))
            self._q_want[col] = int(tree.column(col, "width")) + give
        self._queue_fit_cols()
        self._queue_remember_cols()

    def _queue_head_menu(self, e):
        """Right-click on a heading: "Reset column widths" (user 19.11.)."""
        if self.tv_queue.identify_region(e.x, e.y) not in ("heading", "separator"):
            return None
        m = self._q_menu = PopMenu(self.root, scale=getattr(self, "ui", 1.0))
        m.add_command(label="Reset column widths", command=self._queue_reset_cols)
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def _queue_reset_cols(self):
        self._q_want = {c: self._px(Q_COL_DEFAULT[c]) for c in self._q_free_cols()}
        self.state.pop("queue_cols", None)
        self._queue_fit_cols()

    def _queue_key_act(self, col: str):
        """Delete = ✕, Space = pause / resume of the selected row (user 19.11.); nothing where the row offers nothing."""
        sel = self.tv_queue.selection()
        if sel:
            act = self._row_actions(sel[0]).get(col)
            if act in ("cancel", "pause", "resume"):
                self._queue_do(act, sel[0])
        return "break"

    def _queue_release(self, e):
        if getattr(self, "_q_coldrag", None):
            self._q_coldrag = None
            self._queue_fit_cols()
            self._queue_remember_cols()
            return "break"
        d, self._q_drag = getattr(self, "_q_drag", None), None
        if not d or not d["moved"]:
            return
        tree = self.tv_queue
        tree.configure(cursor="")
        jid = d["iid"][2:]
        shown = [i[2:] for i in tree.get_children("") if i.startswith("j:") and self._q_movable(self._q_jobs.get(i[2:]))
                 and (self._q_jobs.get(i[2:]) or {}).get("batch_id") == d["batch"]]
        line = [x["id"] for x in self._q_jobs.values() if self._q_movable(x)]         # queue order, all batches
        mine = [x for x in line if x in shown]                                           # this batch, before the drag
        try:
            target = mine[shown.index(jid)]
            delta = line.index(target) - line.index(jid)
        except ValueError:
            delta = 0
        if delta:
            self.runner.move(jid, delta)
        self._queue_fill()

    # "At ComfyUI": what waits there, read in a thread about every 2 s while the window is open

    def _queue_comfy_tick(self):
        self._q_tick = None
        if not self._alive(getattr(self, "_queue_win", None)):
            return
        if not getattr(self, "_q_fetching", False):
            self._q_fetching = True
            comfy = self.bridge.comfy

            def work():
                try:
                    entries = comfy.queue_entries()
                except Exception:
                    entries = None
                self.events.put(("batch-ui", lambda: self._queue_comfy_show(entries)))
            threading.Thread(target=work, daemon=True, name="pcc-queue-read").start()
        self._q_tick = self.root.after(QUEUE_COMFY_MS, self._queue_comfy_tick)

    def _queue_comfy_show(self, entries):
        """ComfyUI's queue was read: the list is filled anew (its "#" and the runs of others come from it). Without an
        answer a grey line under the list says ComfyUI is not connected (the "Participants" list is gone, user 24.11.)."""
        self._q_fetching = False
        self._queue_note_foreign_done(getattr(self, "_q_entries", None), entries)
        self._q_entries = entries
        lab = getattr(self, "lbl_q_conn", None)
        if lab is None or not self._alive(getattr(self, "_queue_win", None)):
            return
        try:
            if entries is None:
                url = getattr(self.bridge.comfy, "url", None)
                local = comfyaddr.is_local(url if isinstance(url, str) else comfyaddr.DEFAULT_URL)    # alone: no address talk
                lab.configure(text=Q_NOT_CONNECTED_LOCAL if local else Q_NOT_CONNECTED_NET)
                if not lab.winfo_manager():
                    lab.pack(anchor="w", fill="x", pady=(0, 4))
            elif lab.winfo_manager():
                lab.pack_forget()
                lab.configure(text="")
        except tk.TclError:
            pass
        self._queue_fill()
