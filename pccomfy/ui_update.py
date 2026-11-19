"""Update check in the window (docs/plan/update.md, user 19.11.): the check at the start (A1, once a day, the tick "Check for
updates" in Other settings, ticked from the factory) and the button "Check now" (A2); a newer release shows as a blue dot on
the gear and a line at the top of Other settings with "What's new" and "Skip this version" (H2). Installing: the release page
and the steps (B1), or "Update now" (git pull) in a clone of the public repo (B3). The network part is pccomfy/update.py."""
from __future__ import annotations

import webbrowser

from . import update
from .gui_common import *  # noqa: F401,F403

CHECK_TEXT = "Check for updates"
CHECK_TIP = ("Once a day at the start, PxC asks GitHub (github.com/phil-haderer/pxc) whether a newer version is out. "
             "GitHub sees your IP address and the PxC version, nothing else. Untick to stop it; Check now still works.")


class UpdateMixin:
    _update_found = None        # {"version", "url"} of a newer release, or None
    _update_busy = False

    # ---- start and check ----

    def _update_init(self):
        """At the start (called from _build_settings): the blue dot of a release found earlier, then the daily check."""
        self._update_found = update.to_show(self.state.get(update.KEY_FOUND), cfgmod.get_setting(update.KEY_SKIP, ""))
        self.lbl_update_dot = tk.Label(self.b_gear.master, text="●", bg=BG, fg=ACCENT, font=font(7), bd=0, padx=0, pady=0)
        self._update_dot_tip = Tooltip(self.lbl_update_dot, "")
        self._update_dot_sync()
        if not os.environ.get("PCCOMFY_NO_UPDATE_CHECK"):
            later(self.root, update.START_DELAY_MS, self._update_check_auto)

    def _update_check_auto(self):
        if cfgmod.get_setting(update.KEY_OFF) or not update.due(self.state.get(update.KEY_LAST)):
            return
        self._update_check(manual=False)

    def _update_check(self, manual: bool = True):
        """In the background; the answer comes back as the event "update" (_update_done)."""
        if self._update_busy:
            return
        self._update_busy = True
        if manual:
            self._update_status("Checking…")
        url = getattr(self, "_update_url", update.RELEASES_API)       # tests point it at their own server

        def work():
            try:
                res = {"release": update.fetch_latest(url), "manual": manual}
            except update.UpdateError as e:
                res = {"error": str(e), "manual": manual}
            self.events.put(("update", res))
        threading.Thread(target=work, daemon=True).start()

    def _update_done(self, res: dict):
        self._update_busy = False
        if not res.get("manual"):
            self.state[update.KEY_LAST] = time.time()
        if "error" in res:
            if res.get("manual"):
                self._update_status(res["error"], error=True)
            self._save_update_state()
            return
        rel = res["release"]
        if update.is_newer(rel.version):
            self.state[update.KEY_FOUND] = {"version": rel.version, "url": rel.url}
            skipped = cfgmod.get_setting(update.KEY_SKIP, "")
            if res.get("manual") and skipped == rel.version:
                cfgmod.set_setting(update.KEY_SKIP, None)      # asked by hand: a skipped version is shown again
                skipped = ""
            self._update_found = update.to_show(self.state[update.KEY_FOUND], skipped)
            if res.get("manual"):
                self._update_status("")
        else:
            self.state.pop(update.KEY_FOUND, None)
            self._update_found = None
            if res.get("manual"):
                self._update_status(f"PxC {update.__version__} is the latest version.")
        self._save_update_state()
        self._update_dot_sync()
        self._update_note_sync()

    def _save_update_state(self):
        try:
            cfgmod.save_state(self.state)
        except Exception:
            pass

    # ---- the blue dot (H2) ----

    def _update_dot_sync(self):
        dot = getattr(self, "lbl_update_dot", None)
        if dot is None:
            return
        try:
            if self._update_found:
                dot.place(in_=self.b_gear, relx=1.0, rely=0.0, anchor="ne")
                dot.lift()
                self._update_dot_tip.text = f"PxC {self._update_found['version']} is available: Settings › Other settings."
            else:
                dot.place_forget()
        except tk.TclError:
            pass

    # ---- Other settings ----

    def _update_note_row(self, parent):
        """The line at the top of Other settings (H2): shown only while a newer release is known."""
        self.f_update_note = ttk.Frame(parent)
        self._update_note_parent = parent
        self._update_note_sync()

    def _update_note_sync(self):
        box = getattr(self, "f_update_note", None)
        if box is None:
            return
        try:
            for w in (box.winfo_children() or ()):
                w.destroy()
            found = self._update_found
            if not found:
                box.pack_forget()
                return
            kids = list(box.master.pack_slaves() or ())
            box.pack(side="top", fill="x", padx=14, pady=(10, 0), **({"before": kids[0]} if kids and kids[0] is not box else {}))
            head = ttk.Frame(box)
            head.pack(fill="x")
            ttk.Label(head, text=f"Update {found['version']} available", style="SetHead.TLabel").pack(side="left")
            row = ttk.Frame(box)
            row.pack(fill="x", pady=(4, 0))
            kind = update.install_kind()
            b = self.b_update_news = ttk.Button(row, text="What's new", style="SetSmall.TButton",
                                                command=lambda: webbrowser.open(found.get("url") or update.RELEASES_PAGE))
            b.pack(side="left")
            Tooltip(b, "Opens the release page: what changed and the ZIP to download.")
            if kind == "git":
                b = self.b_update_now = ttk.Button(row, text="Update now", style="SetSmall.TButton", command=self._update_git)
                b.pack(side="left", padx=(6, 0))
                Tooltip(b, "Runs git pull in the PxC folder (only when no file there was changed).")
            b = self.b_update_skip = ttk.Button(row, text="Skip this version", style="SetSmall.TButton", command=self._update_skip)
            b.pack(side="left", padx=(6, 0))
            Tooltip(b, "Hides this version; a newer one is shown again.")
            self.lbl_update_steps = ttk.Label(box, text=update.UPDATE_STEPS[kind], style="SetMuted.TLabel",
                                              wraplength=self._px(380), justify="left")
            self.lbl_update_steps.pack(anchor="w", pady=(4, 0))
        except tk.TclError:
            pass

    def _update_check_row(self, parent):
        """The tick "Check for updates" (A1, ticked from the factory) and "Check now" (A2) with its answer."""
        row = ttk.Frame(parent)
        row.pack(side="top", fill="x", padx=14, pady=(12, 0))
        self.v_update_check = tk.BooleanVar(value=not cfgmod.get_setting(update.KEY_OFF))
        cb = self.cb_update_check = ttk.Checkbutton(
            row, text=CHECK_TEXT, variable=self.v_update_check, style="SetText.TCheckbutton",
            command=lambda: cfgmod.set_setting(update.KEY_OFF, None if self.v_update_check.get() else True))
        cb.pack(side="left")
        Tooltip(cb, CHECK_TIP)
        b = self.b_update_check = ttk.Button(row, text="Check now", style="SetSmall.TButton", command=self._update_check)
        b.pack(side="left", padx=(8, 0))
        Tooltip(b, "Asks GitHub now whether a newer PxC is out.")
        self.lbl_update_status = ttk.Label(parent, text="", style="SetMuted.TLabel")
        self.lbl_update_status.pack(side="top", anchor="w", padx=14, pady=(2, 0))

    def _update_status(self, text: str, error: bool = False):
        lbl = getattr(self, "lbl_update_status", None)
        try:
            if lbl is not None and lbl.winfo_exists():
                lbl.configure(text=text, style="SetRed.TLabel" if error else "SetMuted.TLabel")
        except tk.TclError:
            pass

    def _update_skip(self):
        if self._update_found:
            cfgmod.set_setting(update.KEY_SKIP, self._update_found["version"])
        self._update_found = None
        self._update_dot_sync()
        self._update_note_sync()

    def _update_git(self):
        """B3: git pull in the background; the answer stands under the line."""
        b = getattr(self, "b_update_now", None)
        if b is not None:
            b.configure(state="disabled")
        self._update_status("Updating with git pull…")

        def work():
            ok, text = update.git_update()
            self.events.put(("update-git", (ok, text)))
        threading.Thread(target=work, daemon=True).start()

    def _update_git_done(self, ok: bool, text: str):
        self._update_status(text, error=not ok)
        b = getattr(self, "b_update_now", None)
        try:
            if b is not None and b.winfo_exists():
                b.configure(state="disabled" if ok else "normal")
        except tk.TclError:
            pass
