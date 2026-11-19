"""The download symbols of the settings window (14c step 5): one file, or "all missing" of a model.

The file goes into the sub-folder of its kind in ComfyUI's ``models`` folder (``comfydir.py`` finds it, the window asks once if it
cannot), after an OK that names file, size and target. Every file loads in its own thread, all at the same time (``downloads.py``);
progress, end and errors come back as "download" events. Files that need a login (gated) or come from another site open their page in the browser.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from . import comfyaddr, comfydir, downloads, inventory, manifest
from .gui_common import *  # noqa: F401,F403

COMFY_NOT_RUNNING = "ComfyUI is not running: start it, then click again."
DIRECT_HOSTS = ("huggingface.co", "githubusercontent.com")      # the plugin loads from these itself (Civitai: its page opens)


def browser_only(f) -> bool:
    """A file the plugin does not load itself: gated at Hugging Face (needs a login, the token panel comes later) or from Civitai."""
    return "gated" in f.note.lower() or not downloads._host_ok(f.url, DIRECT_HOSTS)


def site_hint(f) -> str:
    """The orange note of a file that cannot be loaded by the plugin: where to go and where to put it."""
    if "gated" in f.note.lower():
        return "Log in at Hugging Face and accept the licence. The disk symbol opens the page."
    host = urllib.parse.urlsplit(f.url).hostname or "the website"
    return f"The disk symbol opens {host} in your browser. Save the file in {f.target}."


def size_text(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


class DownloadMixin:
    # ---------- state ----------

    def _dl_init(self):
        self._dl: dict[str, dict] = {}              # file name -> {"file", "target", "done", "total", "phase", "cancel"} (running)
        self._dl_restart: set[str] = set()          # loaded, but ComfyUI does not list it yet
        self._dl_widgets: dict[str, dict] = {}      # file name -> the progress widgets of its row
        self._comfy_root: Path | None = None        # found for this session (Path("") = looked up, none found); None = not known yet
        self._comfy_root_seq = 0                    # the lookup runs in a thread; an answer of an older address is dropped
        self._comfy_root_busy = False
        self._fill_ctx: dict | None = None          # while the settings rows are made: models folder, disk files, candidates, once each

    def _dl_info(self, name: str) -> dict | None:
        """For a row: None, or {"state": loading / verifying, "done", "total"}."""
        st = self._dl.get(name)
        if st is None:
            return None
        return {"state": "verifying" if st["phase"] == "verifying" else "loading", "done": st["done"], "total": st["total"]}

    # ---------- where the files go ----------

    def models_dir(self, ask: bool = True) -> Path | None:
        """ComfyUI's ``models`` folder: the test override (the "without models" test start uses a sandbox folder), the folder you chose once, the one of the running ComfyUI, else ask.
        While the settings rows are made the answer is worked out once (``_fill_ctx``)."""
        ctx = None if ask else getattr(self, "_fill_ctx", None)
        if ctx is not None and "base" in ctx:
            return ctx["base"]
        res = self._models_dir_now(ask)
        if ctx is not None:
            ctx["base"] = res
        return res

    def _root_lookup_needed(self) -> bool:
        """Does the folder of the running ComfyUI have to be looked up (no test override, not remote, no folder saved)?"""
        if os.environ.get("PCCOMFY_MODELS_DIR") or os.environ.get("PCCOMFY_SIMULATE_NO_MODELS"):
            return False
        if not comfyaddr.is_local(self.comfy.url):
            return False
        saved = cfgmod.get_setting("comfy_models_dir")      # noqa: F405
        return not (saved and Path(saved).is_dir())

    def _comfy_root_start(self):
        """Looks up ComfyUI's folder in a thread (PowerShell on Windows takes seconds, never on the Tk thread); the answer comes back as
        a "comfyroot" event. Does nothing when it is known, already running or not needed."""
        if not hasattr(self, "_comfy_root_busy") or self._comfy_root is not None or self._comfy_root_busy or not self._root_lookup_needed():
            return
        self._comfy_root_seq += 1
        seq, url = self._comfy_root_seq, self.comfy.url
        self._comfy_root_busy = True

        def work():
            try:
                root = comfydir.find_root(url) or Path("")
            except Exception:
                root = Path("")
            self.events.put(("comfyroot", (seq, url, root)))
        threading.Thread(target=work, daemon=True).start()

    def _comfy_root_reset(self):
        """The address of ComfyUI changed: forget the folder and look it up again in the background."""
        self._comfy_root = None
        self._comfy_root_seq += 1          # an answer for the old address is dropped
        self._comfy_root_busy = False
        self._comfy_root_start()

    def _comfy_root_done(self, data):
        seq, url, root = data
        if seq != self._comfy_root_seq:
            return
        self._comfy_root_busy = False
        self._comfy_root = root
        if getattr(self, "_settings_win", None) is not None:
            self._settings_fill()          # draws only when the rows changed

    def _models_dir_now(self, ask: bool) -> Path | None:
        env = os.environ.get("PCCOMFY_MODELS_DIR")
        if not env and os.environ.get("PCCOMFY_SIMULATE_NO_MODELS"):      # the "ComfyUI without models" test start: a sandbox folder
            env = str(cfgmod.CONFIG_DIR / "test-downloads")                # noqa: F405
        if env:
            p = Path(env)
            p.mkdir(parents=True, exist_ok=True)
            return p
        remote = not comfyaddr.is_local(self.comfy.url)      # ComfyUI on another computer: its folder is the one you choose for it
        saved = cfgmod.get_setting("comfy_models_dir_remote" if remote else "comfy_models_dir")      # noqa: F405
        if saved and Path(saved).is_dir():
            return Path(saved)
        if remote:
            return self._ask_models_dir(ask, True)
        none_found = self._comfy_root is not None and str(self._comfy_root) in ("", ".")
        if self._comfy_root is None or (ask and none_found):
            if not ask:                    # a window being drawn must not wait for PowerShell: same as "no folder known" until the thread answers
                self._comfy_root_start()
                return None
            # a click that needs the folder now; an earlier "none found" is looked up again (user 17.11.: it stayed for the session)
            self._comfy_root = comfydir.find_root(self.comfy.url) or Path("")
        found = comfydir.models_dir_of(self._comfy_root) if str(self._comfy_root) not in ("", ".") else None
        if found is not None:
            return found
        if ask and getattr(self, "_comfy_up", None) is False:      # not running: a short note, no folder window (user 17.11.)
            self._status(COMFY_NOT_RUNNING, error=True)
            return None
        return self._ask_models_dir(ask, False)

    def _ask_models_dir(self, ask: bool, remote: bool) -> Path | None:
        if not ask:
            return None
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self._settings_win or self.root, title="Where is your ComfyUI? Choose its folder "
                                         "(the one with main.py and models)")
        p = comfydir.models_dir_of(chosen) if chosen else None
        if chosen and p is None:
            self._status("There is no models folder in that folder.", error=True)
        if p is not None:
            cfgmod.set_setting("comfy_models_dir_remote" if remote else "comfy_models_dir", str(p))      # noqa: F405
        return p

    # ---------- the buttons ----------

    def _dl_done(self, f) -> bool:
        """Is the file already on the disk although ComfyUI does not list it yet (loaded in this session, or copied in; ComfyUI reads
        its folders only at start)? "Download needed models" leaves such files out (user 2.11.)."""
        if f.name in self._dl_restart:
            return True
        base = self.models_dir(ask=False)
        if base is None:
            return False
        try:
            return downloads.target_for(base, f).exists()
        except downloads.DownloadError:
            return False

    def download_cancel_all(self, names):
        """The "Stop downloads" button of a page: stops every running download among these file names."""
        stopped = [n for n in names if n in self._dl]
        for n in stopped:
            self.download_cancel(n)
        if stopped:
            self._status(f"Stopping {len(stopped)} download{'s' if len(stopped) != 1 else ''}. Loading again goes on where it stopped.")

    def download_file(self, name: str):
        """The disk symbol of a file."""
        f = manifest.FILES.get(name)
        if f is None or not f.url or name in self._dl:
            return
        if browser_only(f):
            webbrowser.open(f.url)
            self._status(f"{name}: needs a login or comes from another site, so its page is open in your browser.")
            return
        base = self.models_dir()
        if base is None:
            return
        try:
            target = downloads.target_for(base, f)
        except downloads.DownloadError as e:
            self._status(str(e), error=True)
            return
        if target.exists():
            self._status(f"{name} is already in {target.parent}. Restart ComfyUI if it does not list it.")
            return
        if not messagebox.askokcancel("Download", f"Download {name}?\n\nSize: {f.size_text or 'unknown'}\nTo: {target}\n\n"        # noqa: F405
                                      "If it is interrupted, starting it again goes on where it stopped.",
                                      parent=self._settings_win or self.root):
            return
        self._dl_add([(f, target)])

    def download_missing(self, key, required_only: bool = False):
        """The disk symbol in a model's head: every file of it that is missing (all of them load at the same time). Files that
        need a website (gated, Civitai) are named in the OK window and their pages open in the browser. `key` may be several
        models (a file two models share is listed once)."""
        if self.inv is None:
            return
        keys = (key,) if isinstance(key, str) else tuple(key)
        todo = []
        for row in (r for r in self.inv.rows() if r["key"] in keys):
            for f, found, lv in row["files"]:
                if found is None and f.url and f.name not in self._dl and f not in todo and (lv == "required" or not required_only) and not self._dl_done(f):
                    todo.append(f)
        own = [f for f in todo if not browser_only(f)]
        site = [f for f in todo if browser_only(f)]
        if not own and not site:
            return
        pairs, base = [], None
        if own:
            base = self.models_dir()
            if base is None:
                return
            for f in own:
                try:
                    t = downloads.target_for(base, f)
                except downloads.DownloadError as e:
                    self._status(str(e), error=True)
                    return
                if not t.exists():
                    pairs.append((f, t))
        parts = []
        if pairs:
            names = "\n".join(f"  {f.name}  {f.size_text}" for f, _t in pairs)
            parts.append(f"Download {len(pairs)} file(s), {size_text(sum(f.size for f, _t in pairs))} in all?\n\n{names}\n\nTo: {base}")
        if site:
            parts.append("These need a website and open in your browser:\n" + "\n".join(f"  {f.name}  ({f.target})" for f in site))
        if not parts:
            self._status("The files are already in the folder. Restart ComfyUI if it does not list them.")
            return
        if not messagebox.askokcancel("Download", "\n\n".join(parts), parent=self._settings_win or self.root):         # noqa: F405
            return
        for f in site:
            webbrowser.open(f.url)
        if pairs:
            self._dl_add(pairs)

    def _dl_add(self, pairs):
        for f, target in pairs:
            self._dl[f.name] = {"file": f, "target": target, "done": 0, "total": f.size, "phase": "downloading", "cancel": threading.Event()}
            threading.Thread(target=self._dl_work, args=(f.name,), daemon=True).start()
        self._settings_fill()

    def download_cancel(self, name: str):
        """The cross of a row: stops it (what is loaded stays for a later resume)."""
        st = self._dl.get(name)
        if st is not None:
            st["cancel"].set()

    def _dl_work(self, name: str):
        put, st = self.events.put, self._dl.get(name)
        if st is None:
            return
        f, last = st["file"], [0.0]

        def progress(done, total, phase):
            now = time.monotonic()
            if now - last[0] >= 0.15 or done >= total:
                last[0] = now
                put(("download", ("progress", name, done, total, phase)))
        try:
            downloads.download(f.url, st["target"], size=f.size, sha256=f.sha256, progress=progress, cancel=st["cancel"].is_set)
            put(("download", ("end", name, "ok", "")))
        except downloads.Cancelled:
            put(("download", ("end", name, "cancelled", "")))
        except downloads.DownloadError as e:
            put(("download", ("end", name, "error", str(e))))
        except Exception as e:      # noqa: BLE001  (a worker must not die silently)
            put(("download", ("end", name, "error", f"Unexpected: {e}")))

    def _download_event(self, data):
        kind, name = data[0], data[1]
        st = self._dl.get(name)
        if st is None:
            return
        if kind == "progress":
            st["done"], st["total"], st["phase"] = data[2], data[3] or st["total"], data[4]
            self._dl_paint(name)
            return
        _k, _n, result, text = data
        self._dl.pop(name, None)
        if result == "ok":
            self._dl_restart.add(name)
            self._status(f"Loaded {name}. If ComfyUI does not list it, restart ComfyUI.")
            self.comfy.invalidate()
            self._detect_async()
        elif result == "cancelled":
            self._status(f"Cancelled: {name}. Loading it again goes on where it stopped.")
        else:
            self._status(f"{name}: {text}", error=True)
        self._settings_fill()

    def _dl_paint(self, name: str):
        info = self._dl_info(name)
        for widgets in (self._dl_widgets,):
            w = widgets.get(name)
            if not w or not info:
                continue
            total = info["total"]
            try:
                w["bar"].configure(maximum=max(total, 1), value=info["done"])
                pct = f"{round(100 * info['done'] / total)} %" if total else size_text(info["done"])
                w["label"].configure(text="checking" if info["state"] == "verifying" else pct)
            except (tk.TclError, KeyError):      # noqa: F405
                pass

    # ---------- "Check files" (user 17.11.): the files on the disk against the checksums of models.json ----------

    CHECK_TIP = ("Reads every model file of PxC that is in ComfyUI's models folder and compares it with the checksum in "
                 "models.json (in the background; large files take a while). Nothing is changed or deleted.")
    CHECK_DAMAGED_HINT = ("A damaged file is not deleted by PxC. Delete it yourself in the folder shown, then load it "
                          "again with its disk symbol (or download it by hand).")

    def _check_label(self) -> str:
        """The entry of the menu "⋯" (user 19.11., choice K2; before a button): it stops a check that runs."""
        return "Stop checking" if getattr(self, "_check", None) is not None else "Check files"

    def _check_row(self, parent):
        """What "Check files" (an entry of the menu "⋯") shows on the tab Model Links: a progress bar with a short line (only
        while there is something to say) and, after a check, the result per file."""
        box = ttk.Frame(parent)      # noqa: F405
        box.pack(fill="x", side="top", padx=12)
        head = self.f_check_head = ttk.Frame(box)      # noqa: F405
        running = getattr(self, "_check", None) is not None
        self.pb_check = ttk.Progressbar(head, length=self._px(120), maximum=1, value=0)      # noqa: F405
        self.l_check = ttk.Label(head, text=getattr(self, "_check_line", ""), style="SetText.TLabel")      # noqa: F405
        self.l_check.pack(side="left", padx=(8, 0))
        if running:
            self.pb_check.pack(side="left", padx=(0, 0), before=self.l_check)
        self._check_head()
        self.t_check = tk.Text(box, height=1, wrap="word", relief="flat", borderwidth=0, highlightthickness=0,      # noqa: F405
                               bg=BG, fg=FG, font=font(9))      # noqa: F405
        self._check_show(getattr(self, "_check_result", None))

    def _check_entries(self, base) -> list[dict]:
        """What "Check files" reads: every file of models.json, where ComfyUI has it. A file found under another name (linked with the
        chain symbol, an alias, a GGUF) is the user's own file: its checksum is not known, it is not read (named in the result)."""
        out = []
        for f in manifest.FILES.values():
            found = self.inv.found(f.name) if self.inv is not None else None
            e = {"name": f.name, "sha256": f.sha256, "size": f.size, "path": None, "where": file_path_of(f)}
            same = found is None or inventory.norm(found).rpartition("/")[2] == inventory.norm(f.name).rpartition("/")[2]
            if not same:
                e.update(sha256="", path=self._disk_file(f, found), where=f"/{f.folder}/" + found.replace("\\", "/"),
                         note=f"your own file {found} (linked or another name): no checksum known, not checked")
            else:
                e["path"] = (self._disk_file(f, found) if found else None) or self._disk_file(f, f.name)
            if e["path"] is not None:
                e["where"] = str(e["path"])
            out.append(e)
        return out

    def check_files(self):
        """The button: starts the check in a thread, or stops the one that runs."""
        st = getattr(self, "_check", None)
        if st is not None:
            st["cancel"].set()
            return
        base = self.models_dir()
        if base is None:
            return
        entries = self._check_entries(base)
        self._check = {"cancel": threading.Event(), "entries": entries}
        self._check_result, self._check_line = None, "checking"
        self._check_paint(0, 1, "")
        threading.Thread(target=self._check_work, args=(entries, self._check["cancel"]), daemon=True).start()

    def _check_work(self, entries, cancel):
        put, last = self.events.put, [0.0]

        def progress(done, total, name):
            now = time.monotonic()
            if now - last[0] >= 0.15 or done >= total:     # a 45 GB file sends about 45000 steps: a few per second are enough
                last[0] = now
                put(("filecheck", ("progress", done, total, name)))
        try:
            res = downloads.check_files(entries, progress, cancel.is_set)
            put(("filecheck", ("end", res, "")))
        except downloads.Cancelled:
            put(("filecheck", ("end", None, "cancelled")))
        except Exception as e:      # noqa: BLE001  (a worker must not die silently)
            put(("filecheck", ("end", None, f"Unexpected: {e}")))

    def _check_event(self, data):
        if data[0] == "progress":
            _k, done, total, name = data
            if getattr(self, "_check", None) is not None:
                self._check_paint(done, total, name)
            return
        _k, res, err = data
        entries = (getattr(self, "_check", None) or {}).get("entries", [])
        self._check = None
        if err == "cancelled":
            self._check_line = "Check stopped."
        elif err:
            self._check_line = f"Check failed: {err}"
        else:
            where = {e["name"]: e["where"] for e in entries}
            for r in res:
                r["where"] = where.get(r["name"], "")
            self._check_result = res
            self._check_line = self.check_summary(res)
        bad = bool(err and err != "cancelled") or any(r["state"] == "damaged" for r in (res or []))
        self._status(self._check_line, error=bad)
        self._check_paint(0, 0, "")

    @staticmethod
    def check_summary(res) -> str:
        n = {s: sum(1 for r in res if r["state"] == s) for s in downloads.CHECK_STATES}
        parts = [f"{n['ok']} ok"]
        if n["damaged"]:
            parts.insert(0, f"{n['damaged']} damaged")
        if n["unknown"]:
            parts.append(f"{n['unknown']} not checked (no checksum known)")
        parts.append(f"{n['missing']} missing")
        return "Files checked: " + ", ".join(parts) + "."

    @classmethod
    def check_report(cls, res) -> str:
        """The result per file: damaged first (with the hint what to do), then the ones that are fine, the ones without a
        checksum and the missing ones."""
        mark = {"damaged": "✗ damaged", "ok": "✓ ok", "unknown": "? not checked", "missing": "– missing"}
        lines = []
        for state in ("damaged", "ok", "unknown", "missing"):
            for r in (r for r in res if r["state"] == state):
                line = f"{mark[state]}: {r['name']}"
                if state in ("damaged", "unknown"):
                    line += f"  ({r['text']})"
                    if r.get("where"):
                        line += f"\n    {r['where']}"
                lines.append(line)
        if any(r["state"] == "damaged" for r in res):
            lines.insert(0, cls.CHECK_DAMAGED_HINT)
        return "\n".join(lines)

    def _check_paint(self, done, total, name):
        running = getattr(self, "_check", None) is not None
        if running and total and name:
            self._check_line = f"{round(100 * done / total)} %  " + name.replace("\\", "/").rpartition("/")[2]
        try:
            if running:
                self.pb_check.configure(maximum=max(total, 1), value=done)
                self.pb_check.pack(side="left", padx=(0, 0), before=self.l_check)
            else:
                self.pb_check.pack_forget()
            self.l_check.configure(text=self._check_line)
            self._check_head()
            if not running:
                self._check_show(getattr(self, "_check_result", None))
        except (AttributeError, tk.TclError):      # noqa: F405  (the settings window is closed: the status line says the end)
            pass

    def _check_head(self):
        """The line with the bar under the top row only while a check runs or its last line is to be read (no empty gap)."""
        head = getattr(self, "f_check_head", None)
        if head is None:
            return
        try:
            if getattr(self, "_check", None) is not None or getattr(self, "_check_line", ""):
                if head.winfo_manager() != "pack":
                    others = head.master.pack_slaves()          # the result text: the line stays above it
                    head.pack(fill="x", pady=(8, 0), **({"before": others[0]} if others else {}))
            else:
                head.pack_forget()
        except tk.TclError:      # noqa: F405
            pass

    def _check_show(self, res):
        """The result under the button (read-only text, at most 12 lines high)."""
        t = getattr(self, "t_check", None)
        if t is None:
            return
        try:
            if not res:
                t.pack_forget()
                return
            text = self.check_report(res)
            t.configure(state="normal")
            t.delete("1.0", "end")
            t.insert("1.0", text)
            t.configure(state="disabled", height=min(12, text.count("\n") + 1))
            t.pack(fill="x", pady=(6, 0))
        except tk.TclError:      # noqa: F405
            pass


def file_path_of(f) -> str:
    """Where a file lies inside ComfyUI's models folder (as ui_settings.file_path)."""
    return "/" + f.folder + "/" + f.name.replace("\\", "/")
