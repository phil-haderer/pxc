"""The page "Other settings" of the settings window (moved out of ui_settings.py unchanged, tempo plan S2, 24.11.): its
sections Connection (the ComfyUI address with its check, history and reset; your name in the queue), Save image (folder,
format, file name pattern), Appearance (UI scale) and Maintenance. SettingsMixin inherits OtherSettingsMixin; the window
itself and the "Models" page stay in ui_settings.py.

The names of ui_settings.py these methods use are imported at the end of this file: ui_settings.py imports this module just
before its class SettingsMixin, so the class must already stand here then (the methods look the names up only when they run)."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import comfyaddr, jobqueue, savefile, spacing
from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401


class OtherSettingsMixin:
    def _other_settings(self, parent):
        """The tab "Other settings" (user 1.11.; sections since 20.11.): the update line on top (only while one is known) and the
        answer of Check now, then Connection, Save image, Appearance and Maintenance, one line between two sections.
        "Check for updates" and "Check now" sit at the right end of the chip row (_update_check_row, user 20.11.)."""
        self._update_note_row(parent)         # "Update X available" at the very top, only while one is known (user 19.11., H2)
        self._update_status_row(parent)       # the answer of Check now, only while it has text
        self._other_head(parent, "Connection", first=True)
        self._comfy_address_row(parent)
        self._owner_name_row(parent)
        self._other_sep(parent)
        self._save_image_row(parent)
        self._other_sep(parent)
        self._other_head(parent, "Appearance")
        self._ui_scale_row(parent)
        self._tips_setting_row(parent, pady=(10, 0))
        self._other_sep(parent)
        self._other_head(parent, "Maintenance")
        self._maintenance_row(parent)

    @staticmethod
    def _other_sep(parent):
        """The light line (style Sep.TFrame, as in the model tabs) between two sections of Other settings (user 12.11., 20.11.)."""
        ttk.Frame(parent, style="Sep.TFrame", height=1).pack(side="top", fill="x", padx=14, pady=(14, 0))

    @staticmethod
    def _other_head(parent, text: str, first: bool = False):
        """The name of a section of Other settings, in the style of "Save image" (user 20.11.)."""
        ttk.Label(parent, text=text, style=SET_STYLES["head"]).pack(side="top", anchor="w", padx=14, pady=(10 if first else 12, 0))

    MAINTENANCE = (
        ("Show all hidden models", "Brings back every model chip that was hidden (right-click menu of a chip or the tick in the model tab).",
         "_show_hidden_models"),
        ("Reset all modes to default settings", "Forgets every page you saved with “Save settings” (bottom of the Advanced settings): "
         "all models and functions start with the PxC standard settings again. Asks first.", "_reset_all_modes"),
        ("Copy report", "Copies a report to the clipboard for a bug report: PxC version, where it is installed, Python, "
         "which config files it reads and what they change, the ComfyUI address, which model files are missing. No prompts, "
         "no passwords; your user folder is shown as ~.", "_copy_report"))

    def _maintenance_row(self, parent):
        """The buttons of Maintenance side by side; one that does not fit any more goes into the next line (user 20.11.)."""
        box = ttk.Frame(parent)
        box.pack(side="top", fill="x", padx=14, pady=(8, 12))
        self.b_maintenance = []
        for text, tip, name in self.MAINTENANCE:
            b = ttk.Button(box, text=text, style="SetSmall.TButton", command=getattr(self, name))
            Tooltip(b, tip)
            self.b_maintenance.append(b)
        gap = spacing.scale(6)

        def flow(e=None):
            width = (e.width if e is not None else box.winfo_width()) or 0
            x = y = line_h = 0
            for b in self.b_maintenance:
                w, h = b.winfo_reqwidth() or 0, b.winfo_reqheight() or 0
                if x and x + w > width:
                    x, y, line_h = 0, y + line_h + gap, 0
                b.place(x=x, y=y)
                x, line_h = x + w + gap, max(line_h, h)
            box.configure(height=y + line_h)
        box.bind("<Configure>", flow, add="+")
        flow()

    # ---- Save image: folder, format and file name (the hamburger menu and Ctrl+S, savefile.py) ----

    SAVE_CUSTOM = "Custom…"
    SAVE_FORMATS = {"png": "PNG", "jpg": "JPG", "webp": "WebP"}

    def _save_image_row(self, parent):
        """The section "Save image": the folder (Change… / Default), the format and the file name (one of the patterns of
        savefile.PATTERNS or your own with clickable placeholders), and a live example line under them."""
        cur = savefile.load_settings()
        box = ttk.Frame(parent)
        box.pack(side="top", fill="x", padx=14, pady=(10, 0))
        ttk.Label(box, text="Save image", style=SET_STYLES["head"]).pack(anchor="w")
        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=(4, 0))
        ttk.Label(grid, text="Folder", style="SetText.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        folder = ttk.Frame(grid)
        folder.grid(row=0, column=1, sticky="w", pady=2)
        self.lbl_save_folder = ttk.Label(folder, text=str(cur.folder), style=SET_STYLES["muted"])
        self.lbl_save_folder.pack(side="left", padx=(0, 8))
        b = self.b_save_folder = ttk.Button(folder, text="Change…", style="SetSmall.TButton", command=self._save_folder_pick)
        b.pack(side="left")
        Tooltip(b, "Where Save image puts the files.")
        b = self.b_save_default = ttk.Button(folder, text="Default", style="SetSmall.TButton", command=self._save_folder_default)
        b.pack(side="left", padx=(6, 0))
        Tooltip(b, "Back to your Downloads folder.")
        ttk.Label(grid, text="Format", style="SetText.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        fmt = cur.fmt if cur.fmt in savefile.FORMATS else savefile.DEFAULT_FORMAT
        self.v_save_fmt = tk.StringVar(value=self.SAVE_FORMATS[fmt])
        cb = self.cb_save_fmt = ttk.Combobox(grid, textvariable=self.v_save_fmt, values=list(self.SAVE_FORMATS.values()),
                                             state="readonly", width=8)
        cb.grid(row=1, column=1, sticky="w", pady=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self._save_format_pick())
        ttk.Label(grid, text="File name", style="SetText.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        custom = cur.pattern not in savefile.PATTERNS
        self.v_save_pattern = tk.StringVar(value=self.SAVE_CUSTOM if custom else cur.pattern)
        cb = self.cb_save_pattern = ttk.Combobox(grid, textvariable=self.v_save_pattern,
                                                 values=list(savefile.PATTERNS) + [self.SAVE_CUSTOM], state="readonly", width=34)
        cb.grid(row=2, column=1, sticky="w", pady=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self._save_pattern_pick())
        Tooltip(cb, "How the file is called. The extension follows the format.")
        # your own pattern: a field and the placeholders as buttons (a click puts one in at the cursor)
        self.f_save_custom = ttk.Frame(box)
        self.v_save_custom = tk.StringVar(value=cur.pattern)
        self.e_save_custom = ttk.Entry(self.f_save_custom, textvariable=self.v_save_custom, width=44)
        self.e_save_custom.pack(anchor="w", pady=(2, 0))
        self.v_save_custom.trace_add("write", lambda *a: self._save_custom_changed())
        self.e_save_custom.bind("<ButtonPress-1>", lambda e: idle(self.e_save_custom, self._force_focus, self.e_save_custom), add="+")
        chips = ttk.Frame(self.f_save_custom)
        chips.pack(anchor="w", pady=(4, 0))
        self.b_save_chips = []
        for name in savefile.PLACEHOLDERS:
            b = ttk.Button(chips, text="{" + name + "}", style="SetSmall.TButton", command=lambda n=name: self._save_insert(n))
            b.pack(side="left", padx=(0, 4))
            self.b_save_chips.append(b)
        self.lbl_save_example = ttk.Label(box, text="", style=SET_STYLES["muted"])
        self.lbl_save_example.pack(anchor="w", pady=(4, 0))
        if custom:
            self.f_save_custom.pack(fill="x", before=self.lbl_save_example)
        self._save_example_update()

    def _save_pattern_now(self) -> str:
        """The pattern the section shows right now (the picked one, or the text of the custom field)."""
        v = self.v_save_pattern.get()
        return self.v_save_custom.get() if v == self.SAVE_CUSTOM else v

    def _save_format_now(self) -> str:
        shown = self.v_save_fmt.get()
        return next((k for k, v in self.SAVE_FORMATS.items() if v == shown), savefile.DEFAULT_FORMAT)

    def _save_example_update(self):
        """"Example: beach-upscale-…png", or the error in its place while the pattern is invalid."""
        pattern = self._save_pattern_now()
        err = savefile.validate_pattern(pattern)
        self.lbl_save_example.configure(text=err if err else "Example: " + savefile.example_name(pattern, self._save_format_now()),
                                        style=SET_STYLES["red"] if err else SET_STYLES["muted"])

    def _save_folder_pick(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self._settings_win or self.root, title="Folder for saved images",
                                         initialdir=str(savefile.load_settings().folder))
        if chosen:
            cfgmod.set_setting(savefile.SAVE_FOLDER_KEY, str(Path(chosen)))
            self.lbl_save_folder.configure(text=str(savefile.load_settings().folder))

    def _save_folder_default(self):
        cfgmod.set_setting(savefile.SAVE_FOLDER_KEY, None)
        self.lbl_save_folder.configure(text=str(savefile.load_settings().folder))

    def _save_format_pick(self):
        cfgmod.set_setting(savefile.SAVE_FORMAT_KEY, self._save_format_now())
        self._save_example_update()

    def _save_pattern_pick(self):
        if self.v_save_pattern.get() == self.SAVE_CUSTOM:
            self.f_save_custom.pack(fill="x", before=self.lbl_save_example)
            self._save_custom_changed()
        else:
            self.f_save_custom.pack_forget()
            cfgmod.set_setting(savefile.SAVE_PATTERN_KEY, self.v_save_pattern.get())
            self.v_save_custom.set(self.v_save_pattern.get())       # "Custom…" later starts from the last pick
            self._save_example_update()

    def _save_custom_changed(self):
        """Typing in the custom field: a valid pattern is saved, an invalid one only shows its error."""
        pattern = self.v_save_custom.get()
        if savefile.validate_pattern(pattern) is None and self.v_save_pattern.get() == self.SAVE_CUSTOM:
            cfgmod.set_setting(savefile.SAVE_PATTERN_KEY, pattern)
        self._save_example_update()

    def _save_insert(self, name: str):
        """A placeholder button: {name} goes into the custom field at the cursor."""
        e = self.e_save_custom
        e.insert(e.index("insert"), "{" + name + "}")
        e.focus_set()

    # ---- the name on the batch jobs (the queue, jobqueue.py; 12.11.) ----

    def _owner_name_row(self, parent):
        """"Name in the queue": the name other PCs on the same ComfyUI see on this plugin's runs, batch and Generate (setting owner_name);
        empty = the login name."""
        box = ttk.Frame(parent)
        box.pack(side="top", fill="x", padx=14, pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Name in the queue", style="SetText.TLabel").pack(side="left", padx=(0, 8))
        saved = cfgmod.get_setting(jobqueue.OWNER_SETTING)
        self.v_owner_name = tk.StringVar(value=saved.strip() if isinstance(saved, str) else "")
        e = self.e_owner_name = ttk.Entry(row, textvariable=self.v_owner_name, width=24)
        e.pack(side="left")
        e.bind("<ButtonPress-1>", lambda ev: idle(e, self._force_focus, e), add="+")
        Tooltip(e, "Other PCs on the same ComfyUI see this name on your batch jobs. Empty: your login name.")
        self.lbl_owner_name = ttk.Label(row, text="", style=SET_STYLES["muted"])
        self.lbl_owner_name.pack(side="left", padx=(8, 0))
        self.v_owner_name.trace_add("write", lambda *a: self._owner_name_changed())
        self._owner_name_hint()

    def _owner_name_changed(self):
        name = self.v_owner_name.get().strip()[:64]
        cfgmod.set_setting(jobqueue.OWNER_SETTING, name or None)
        runner = getattr(self, "runner", None)
        if runner is not None:
            runner.owner = jobqueue.owner_name()      # the next batch carries it
        comfy = getattr(getattr(self, "bridge", None), "comfy", None)
        if comfy is not None:
            comfy.owner = jobqueue.owner_name()       # and the next Generate run (18.11.)
        self._owner_name_hint()

    def _owner_name_hint(self):
        self.lbl_owner_name.configure(text="" if self.v_owner_name.get().strip() else f"Empty: {jobqueue.owner_name()}")

    # ---- the interface scale (user 4.11.; Linux and Windows) ----

    UI_SCALE_CHOICES = ("Auto", "50 %", "60 %", "70 %", "80 %", "90 %", "100 %", "110 %", "120 %", "125 %", "150 %", "175 %", "200 %", "250 %", "300 %")

    def _ui_scale_row(self, parent):
        """"Interface scale": Auto takes the scale from the system (Linux: the first source that names one, uiscale.py; Windows: the
        display's own scale, as before). A value here sets the size of the whole window, also below 100 %, and wins over everything
        but the environment variable PCCOMFY_SCALE. The window is built once, so the value counts from the next start."""
        box = ttk.Frame(parent)
        box.pack(side="top", fill="x", padx=14, pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Interface scale", style="SetText.TLabel").pack(side="left", padx=(0, 8))
        saved = cfgmod.get_setting("ui_scale")
        shown = f"{round(float(saved) * 100) if float(saved) < 10 else int(float(saved))} %" if saved else "Auto"
        self.v_ui_scale = tk.StringVar(value=shown if shown in self.UI_SCALE_CHOICES else "Auto")
        cb = ttk.Combobox(row, textvariable=self.v_ui_scale, values=self.UI_SCALE_CHOICES, state="readonly", width=8)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._ui_scale_pick())
        Tooltip(cb, "Size of the PxC window, from 50 % to 300 %. Auto follows your system. Pick a value if the window is too big or too small. 100 % is the size your system gives; 120 % is a fifth bigger, 80 % a fifth smaller (on Windows). Counts from the next start.")
        self.lbl_ui_scale = ttk.Label(row, text="", style=SET_STYLES["muted"])
        self.lbl_ui_scale.pack(side="left", padx=(8, 0))

    def _ui_scale_pick(self):
        """Saves the choice ("Auto" forgets it) and says that the plugin has to be started again."""
        v = self.v_ui_scale.get()
        cfgmod.set_setting("ui_scale", None if v == "Auto" else int(v.split()[0]) / 100)
        try:
            self.lbl_ui_scale.configure(text="Applies the next time you start PxC.")
        except (tk.TclError, AttributeError):
            pass

    # ---- the ComfyUI address (user 3.11.) ----

    def _comfy_address_row(self, parent):
        """"ComfyUI address": the field, Refresh and, beside them, what the check found (green tick, red cross, or a yellow hint)."""
        box = ttk.Frame(parent)
        box.pack(side="top", fill="x", padx=14, pady=(10, 0))
        ttk.Label(box, text="ComfyUI address", style="SetText.TLabel").pack(anchor="w")     # not bold, like "Name in the queue" (user 22.11.)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        self.v_comfy_url = tk.StringVar(value=self.comfy.url)
        # a field with a drop-down list of the addresses that worked before, so one click brings an old one back (user 6.11.)
        ent = ttk.Combobox(row, textvariable=self.v_comfy_url, values=self._url_history(), width=30)
        self.cb_comfy_url = ent
        ent.pack(side="left")
        ent.bind("<<ComboboxSelected>>", lambda e: self._comfy_address_check())
        ent.bind("<Return>", lambda e: self._comfy_address_check())
        # The settings window has no title bar (overrideredirect): Windows does not always make it the active window when the
        # mouse goes into it, so the field got no keyboard (user 5.11.: "the cursor cannot be placed", also after Refresh). A click
        # into the field takes the keyboard (focus -force), after Tk's own focus change.
        ent.bind("<ButtonPress-1>", lambda e: idle(ent, self._force_focus, ent), add="+")
        # Refresh and Reset to default side by side, equally high (window test F, 11.11.); the refresh arrow at 90 %
        btns = ttk.Frame(row)
        btns.pack(side="left", fill="y", padx=(8, 0))
        b = ttk.Button(btns, text="Refresh", image=self._icon("refresh", px=round(SET_ICON_PX * 0.9)), compound="left",
                       style="SetSmall.TButton", command=self._comfy_address_check)
        b.pack(side="left", fill="y")
        Tooltip(b, "Checks the address and, if it is ComfyUI, uses it from now on: PxC reads its models and nodes again.")
        reset = ttk.Button(btns, text="Reset to default", style="SetSmall.TButton", command=self._comfy_address_reset)      # a button like the others (user 6.11.)
        reset.pack(side="left", fill="y", padx=(8, 0))
        Tooltip(reset, "Goes back to the standard address of ComfyUI on this PC.")
        self.b_comfy_refresh, self.b_comfy_reset = b, reset
        # what the check found ("✓ ComfyUI found …"), in its own line under the field (11.11.)
        found = ttk.Frame(box)
        found.pack(fill="x", pady=(4, 0))
        self.lbl_comfy_mark = ttk.Label(found, text="", style=SET_STYLES["green"])
        self.lbl_comfy_mark.pack(side="left")
        self.lbl_comfy_msg = ttk.Label(found, text="", style=SET_STYLES["muted"])
        self.lbl_comfy_msg.pack(side="left", padx=(4, 0))
        self.lbl_comfy_note = ttk.Label(box, text="", style=SET_STYLES["muted"], justify="left", wraplength=self._px(520))
        self._comfy_seq = 0      # the note below is packed only while it has text (no empty line, user 6.11.)
        self._comfy_address_check(apply=False)          # shows at once whether the address in use answers

    URL_HISTORY_MAX = 10

    @staticmethod
    def _url_history() -> list[str]:
        """The addresses that worked before, the newest first (settings.json "comfyui_url_history")."""
        v = cfgmod.get_setting("comfyui_url_history", [])
        return [u for u in v if isinstance(u, str)] if isinstance(v, list) else []

    def _url_remember(self, url: str):
        """Puts an address that answered as ComfyUI at the top of the history (once, at most URL_HISTORY_MAX)."""
        hist = [url] + [u for u in self._url_history() if u != url]
        cfgmod.set_setting("comfyui_url_history", hist[:self.URL_HISTORY_MAX])
        try:
            self.cb_comfy_url.configure(values=self._url_history())
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _force_focus(widget):
        try:
            if widget.winfo_exists():
                widget.focus_force()
        except tk.TclError:
            pass

    def _comfy_address_show(self, mark: str, msg: str, style: str, note: str = ""):
        try:
            self.lbl_comfy_mark.configure(text=mark, style=SET_STYLES["green" if mark == "✓" else "red"])
            self.lbl_comfy_msg.configure(text=msg, style=SET_STYLES[style])
            self.lbl_comfy_note.configure(text=note, style=SET_STYLES["warn" if note.startswith("Unencrypted") else "muted"])
            if note:
                self.lbl_comfy_note.pack(anchor="w", pady=(4, 0))
            else:
                self.lbl_comfy_note.pack_forget()
        except (tk.TclError, AttributeError):
            pass

    def _comfy_address_check(self, apply: bool = True):
        """Refresh: check what is typed, ask the server in the background, and use the address when it is ComfyUI."""
        url, err, warn = comfyaddr.check_format(self.v_comfy_url.get())
        if url is None:
            self._comfy_address_show("✗", err, "bad")
            return
        self._comfy_seq += 1
        seq = self._comfy_seq
        self._comfy_address_show("", "Checking…", "muted")
        import threading

        def work():
            ok, msg = comfyaddr.probe(url)
            self.events.put(("comfyaddr", (seq, url, ok, msg, warn, apply)))
        threading.Thread(target=work, daemon=True).start()

    def _comfy_address_done(self, data):
        seq, url, ok, msg, warn, apply = data
        if seq != self._comfy_seq:
            return              # a newer check is on its way
        note = (f"Unencrypted: {warn.split(': ', 1)[1]}. " if warn else "") + (comfyaddr.REMOTE_NOTE if not comfyaddr.is_local(url) else "")
        if not ok:
            self._comfy_address_show("✗", msg, "bad", note)
            return
        self._comfy_address_show("✓", msg, "muted", note)
        if apply:
            self._url_remember(url)
        if apply and url != self.comfy.url:
            cfgmod.set_setting("comfyui_url", None if url == comfyaddr.DEFAULT_URL else url)
            self.comfy.set_url(url)
            self._comfy_root_reset()
            self.v_comfy_url.set(url)
            self.refresh()
            self._status(f"Using ComfyUI at {url}.")
        elif apply:
            self.refresh()

    def _comfy_address_reset(self):
        self.v_comfy_url.set(comfyaddr.DEFAULT_URL)
        self._comfy_address_check()


from .ui_settings import SET_ICON_PX, SET_STYLES  # noqa: E402
