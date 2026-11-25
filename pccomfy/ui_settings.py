"""Settings overlay, model detection in the window, greyed tabs (lane L1, PLAN.md tasks 6 to 8).

``SettingsMixin`` stands first in ``App``'s bases, so its methods wrap the ones of the other mixins (it calls ``super()``):

* ``refresh`` / ``_apply_refresh``: also read ComfyUI's installed files (in a thread, the result arrives as a "refresh" event);
* ``_update_mode_radios``: a mode whose files are missing is greyed out, its tooltip says what is missing;
* ``_on_model``: a click on a greyed tab opens the settings instead of switching to it;
* ``generate``: the preflight; a missing file stops the run with one clear line (file, folder, link).

The gear button next to the tabs opens the overlay: what is installed per tab, links to download, "link a file of another
name" and other settings. All decisions live in ``inventory.py`` and ``manifest.py`` (no Tk there).
"""
from __future__ import annotations

import tkinter.font as tkfont
import webbrowser

from . import hostos, icons, inventory, linkpicker, manifest, namematch, spacing
from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from .gui_theme import HEADER_H, ICON_PX
from .popmenu import PopMenu
from .ui_downloads import DownloadMixin
from .ui_update import UpdateMixin

EMPTY_TEXT = {"choose": "Choose a model", "none_linked": "Link your models in the settings",
              "no_comfy": "ComfyUI is not running. Start it, then press Refresh."}      # user 22.11., choice A
STATE_TEXT = {"ready": "ready", "partial": "not ready", "missing": "not ready"}      # small after the model name (user 19.11.; before "is ready.", 1.11.)
# the state of a model in Model Links as a coloured chip right of "Show in PxC" (user 20.11.; before a small tick and grey word):
# white bold text on green or red, as high as the mode tiles
STATE_CHIP = {True: "✓ Ready", False: "✗ Not ready"}
STATE_CHIP_BG = {True: "#2f8a4e", False: "#c9393e"}
HINT_SAME = "same size and header as "          # behind a file in the chain list (user 3.11.)
HINT_INCOMPLETE = "incomplete? shorter than its header says"
GGUF_ALT = "Alternatively:"
GGUF_LINK = "Download GGUF-weights"      # under the weights of a main model (user 5.11.)
SIMILAR_FILE = "Similar name (check it): "      # under a missing file with no renamed copy: same model name, other precision or spelling (user 7.11.; short 19.11.)
PROBABLE_FILE = "Probably right: "      # under a missing file, when a renamed copy of it is in the models folder (user 3.11.; short 19.11.)
FIELD_MISSING = "Missing · choose your file"      # the link field of a missing file (user 19.11.)
FIELD_LINKED = " · linked"                       # after your file in the link field (blue)
RESTART_NOTE = "Loaded: restart ComfyUI, then click refresh (⟳) at the bottom of PxC."      # under a file just downloaded
HINT_IN_USE = "in use"            # behind the file the plugin uses now in the list of the chain symbol (user 7.11.)
HINT_EXPECTED = "the expected file"      # in the chain list, when another file is linked: the way back
HINT_SIMILAR = "similar name"
DOT_RED = "#e5484d"                   # the dot in front of a model that is not available (nothing in front of a ready one)
DOT_PAD = 4                            # px of room to the left of the dot (user 1.11.)
SETTINGS_W, SETTINGS_H = 520, 700      # the settings window (before the display scaling; 640 wide until 19.11.); the width it was closed at comes back, the height is always 700 (user 20.11.)
SET_ICON_PX = 16                       # the download symbol next to a file
SET_STYLES = {"head": "SetHead.TLabel", "ok": "SetOk.TLabel", "bad": "SetBad.TLabel", "note": "SetNote.TLabel",
              "muted": "SetMuted.TLabel", "green": "SetGreen.TLabel", "red": "SetRed.TLabel",
              "head9": "SetHead9.TLabel", "warn": "SetWarn.TLabel", "hint": "SetHint.TLabel", "section": "SetSection.TLabel"}
SET_MIN_W, SET_MIN_H = 440, 300        # the smallest the settings window can be dragged to (480 until 19.11.)


def fit_height(y: int, h: int, top: int, bottom: int, min_h: int = 0) -> tuple[int, int]:
    """(y, h) of a window that wants height ``h`` at ``y`` inside the work area ``top`` .. ``bottom`` (review 21.11.): moved
    up first, then made lower (never below ``min_h``, never above the area's height)."""
    room = max(1, int(bottom) - int(top))
    h = max(min(int(h), room), min(int(min_h), room))
    y = max(int(top), min(int(y), int(bottom) - h))
    return y, h
# the spacing of Model Links (user 19.11.): page margin, inside one file, between two files, before a section
SET_PAD, SET_IN, SET_ITEM, SET_SECTION = 16, 4, 12, 20
MODEL_GAP = 24                         # between the model chips and the name of the model (user 19.11.)


class ModelPicker(ttk.Frame):
    """The model pages of the settings window behind one field like the link fields of the files (user 19.11., choice C;
    before a grid of chips that took three rows): "● Qwen Image 2.1 ▾". A click opens a list of every model and "Additional",
    a red dot in front of a model whose files are missing. Used like the part of ttk.Notebook the window needs: add, select,
    index, tab; ``on_select`` is called with a page after it is shown (the window draws a page then)."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        px = app._px
        self.bar = tk.Frame(self, bg=PANEL, highlightthickness=1, highlightbackground=CHIP_LINE, highlightcolor=CHIP_LINE,
                            cursor="hand2", takefocus=1)
        self.bar.pack(fill="x")
        self.arrow = tk.Label(self.bar, text="▾", bg=PANEL, fg=FG, font=font(9), padx=px(8), cursor="hand2")
        self.arrow.pack(side="right")
        self.name = tk.Label(self.bar, text="", bg=PANEL, fg=FG, font=font(10), anchor="w", compound="left",
                             padx=px(8), pady=px(4), cursor="hand2")
        self.name.pack(side="left", fill="x", expand=True)
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        self.pages: list = []
        self.titles: dict = {}             # str(page) -> {"text": ..., "image": ...}
        self.current = tk.StringVar(value="")
        self.on_select = None
        self.menu = None
        for w in (self.bar, self.name, self.arrow):
            w.bind("<Button-1>", self.open_list, add="+")
            w.bind("<Enter>", lambda e: self._hover(True), add="+")
            w.bind("<Leave>", lambda e: self._hover(False), add="+")
        self.bar.bind("<Return>", self.open_list, add="+")
        self.bar.bind("<space>", self.open_list, add="+")
        Tooltip(self.name, "Choose the model whose files you want to see.")

    def _hover(self, on: bool):
        try:
            self.bar.configure(highlightbackground="#9a9a9a" if on else CHIP_LINE)
        except tk.TclError:
            pass

    def add(self, page, text: str = ""):
        self.pages.append(page)
        self.titles[str(page)] = {"text": text, "image": ""}
        if len(self.pages) == 1:
            self.select(page)

    def select(self, page=None):
        if page is None:
            return next((p for p in self.pages if str(p) == self.current.get()), None)
        if page not in self.pages:
            raise tk.TclError("no such tab")
        for p in self.pages:
            p.pack_forget()
        page.pack(in_=self.body, fill="both", expand=True)
        self.current.set(str(page))
        self._show_name()
        if self.on_select is not None:
            self.on_select(page)
        return None

    def index(self, page) -> int:
        return self.pages.index(page)

    def tab(self, page, **kw):
        t = self.titles.setdefault(str(page), {"text": "", "image": ""})
        for k in ("text", "image"):
            if k in kw:
                t[k] = kw[k] or ""
        if str(page) == self.current.get():
            self._show_name()

    def _show_name(self):
        t = self.titles.get(self.current.get(), {"text": "", "image": ""})
        try:
            self.name.configure(text=t["text"], image=t["image"] or "")
        except tk.TclError:
            pass
        self.field_text = t["text"]          # for the tests

    def open_list(self, e=None):
        """The list under the field: every page, with the red dot as in the field."""
        menu = PopMenu(self.app._settings_win or self.app.root, scale=getattr(self.app, "ui", 1.0))
        for p in self.pages:
            t = self.titles.get(str(p), {"text": "", "image": ""})
            menu.add_command(label=t["text"], icon=t["image"] or None, command=lambda pg=p: self.select(pg))      # no tick: the field names it
        menu.tk_popup(self.bar.winfo_rootx(), self.bar.winfo_rooty() + self.bar.winfo_height())
        self.menu = menu
        return "break"

MODES_HEAD = "Supported Modes"                    # before the mode tiles of a model (user 19.11.; before "Modes")
ALL_FILES_BUTTON = "Download missing files"      # one model's missing files, the optional ones too (user 3.11.; name 19.11.)
REQUIRED_HEAD = "Required"                        # the files of the standard settings (user 19.11.; before "Standard settings need these weights:")
OPTIONAL_HEAD = "Optional"                        # the files of extra features; what for stands small after each file (user 19.11.)
ADDITIONAL_HEAD = "Used by several models"        # the page "Additional"
NOT_ALL_WEIGHTS = "Files for the standard settings of {name} are missing."      # the tooltip of a locked "Show in PxC"


def file_path(f) -> str:
    """Where a file lies inside ComfyUI's models folder, as the window shows it: "/loras/Flux 3/flux-3-...safetensors"."""
    return "/" + f.folder + "/" + f.name.replace("\\", "/")
GEAR_PX = round(ICON_PX * 0.6)     # the footer refresh arrow: about 60 % of the other button icons, flat without a button background (user 28.10.)
GEAR_HEAD_PX = round(ICON_PX * 0.6 * 1.2)      # the gear, now in the header: 120 % of that size (user 4.11.)
FOOT_REFRESH_PADX, FOOT_RESET_PADX = (4, 0), (12, 0)     # footer: the refresh arrow close to the ComfyUI dot, "Reset page" apart


from .ui_settings_data import SettingsDataMixin  # noqa: E402  (after the names it takes from here, see its module text)
from .ui_other_settings import OtherSettingsMixin  # noqa: E402  (the same)


class SettingsMixin(DownloadMixin, UpdateMixin, SettingsDataMixin, OtherSettingsMixin):
    inv = None                  # inventory.Inventory of the last successful reading (None = ComfyUI not read / not reachable)
    _inv_error = ""
    _settings_win = None
    _page_w: dict = {}          # the width of each settings tab (wrapping texts follow it)
    _settings_focus = None
    _last_model = ""
    _refreshing = False         # inside StateMixin._apply_refresh (its "open on the first model" step is not wanted here)
    _startup_checked = False    # the first reading after start has been looked at (a last model that is gone is let go once)
    _live_off_missing = False   # "Live preview" was switched off because the model's preview decoder is missing

    # ---------- build (one call at the end of App._build) ----------

    def _build_settings(self, foot):
        """The gear button in the header, left of the minimise button (user 4.11.; it used to end the footer row)."""
        self._last_model = self.v_model.get()
        self._dl_init()
        self._page_w = {}
        self._map_start = cfgmod.model_map()       # the links at startup ("Reset to startup")
        self._map_undo: list[dict] = []            # the links before each change ("Undo")
        style = ttk.Style()
        style.configure("Missing.Tab.Toolbutton", foreground=NA_RED)      # a tab that is not available: red text, the background of an inactive tab
        self.b_gear = ttk.Button(self.f_header, image=self._icon("gear", px=GEAR_HEAD_PX), style="Link.TButton", command=self.toggle_settings)
        self.b_gear.pack(side="right", padx=(0, 6))
        Tooltip(self.b_gear, "Settings: model files and downloads, where Save image puts files, ComfyUI address, "
                                 "interface scale, Copy report.")
        style.configure("Empty.TLabel", foreground="#ffffff", font=font(10, bold=True))      # H2, white (user 6.11.)
        self.v_empty = tk.StringVar(value="")
        self.lbl_empty = ttk.Label(self.root, textvariable=self.v_empty, style="Empty.TLabel", anchor="center", justify="center",
                                   wraplength=self._px(MIN_W - 40))
        self._foot_hidden = False
        self._apply_start_state(fit=False)
        self._update_init()             # the blue dot of a newer release and the daily check (ui_update.py)

    # ---------- reading ComfyUI ----------

    def refresh(self):
        super().refresh()
        self._detect_async()

    def _detect_async(self):
        self._reread_at = None             # a full reading follows: Generate may look again at once afterwards (P4)
        mapping, comfy = cfgmod.model_map(), self.comfy
        self._comfy_root_start()           # ComfyUI's folder, looked up once in the background (not on the Tk thread)

        def work():
            res = {"_detect": True}
            try:
                res["_inv"], res["_inv_error"] = inventory.fetch(comfy, mapping), ""
            except ComfyError as e:
                res["_inv"], res["_inv_error"] = None, str(e)
            self.events.put(("refresh", res))
        threading.Thread(target=work, daemon=True).start()

    def _apply_refresh(self, info):
        if not info.get("_detect"):
            self._refreshing = True
            try:
                super()._apply_refresh(info)
            finally:
                self._refreshing = False
            return
        self._set_inventory(info["_inv"], info.get("_inv_error", ""))

    def _set_inventory(self, inv, err: str = ""):
        self.inv, self._inv_error = inv, err
        self._let_go_unavailable_model()
        self.comfy.name_fixer = inv.apply_names if inv is not None else None    # a linked or differently written file name is renamed when a graph is queued
        self._update_tabs()
        self._apply_start_state()
        self._update_cut_button()
        try:
            self._refs_redraw()           # the Cut out icon of a slot follows the file lists (grey without birefnet)
        except (AttributeError, tk.TclError):
            pass
        try:
            self._update_mode_radios()
        except (AttributeError, tk.TclError):      # the window is still being built
            pass
        try:
            self._on_workflow()           # a model variant came or went (Model Links): its values and switches (user 20.11.)
        except (AttributeError, tk.TclError):
            pass
        if self._settings_win is not None:
            self._settings_fill()

    # ---------- tabs and modes ----------

    def _update_tabs(self):
        hidden = cfgmod.hidden_tabs()
        for key, var in (getattr(self, "_shown_vars", None) or {}).items():    # the gear window follows the right-click menu
            var.set(key not in hidden)
        for m in models.MODELS:
            rb = self.rb_tabs.get(m.key)
            if rb is None:
                continue
            rb.missing = not self._model_usable(m.key, self.v_mode.get())     # red in the model list (gui_modes._model_menu)

    def _model_usable(self, key: str, mode: str) -> bool:
        """Has ComfyUI the files this model needs? The whole model counts, not only the chosen function: a model with one
        function lacking its files is locked (user 30.10.), so nothing is offered that was not tested with its standard settings."""
        if self.inv is None:
            return True
        return self.inv.tab_status(key).state != "missing"

    def _update_mode_radios(self):
        super()._update_mode_radios()
        self._update_tabs()                 # a model turns red in the model list when its files are missing
        self._update_live_preview()
        self._update_llm_button()
        self._enforce_switch_files()
        self._update_ready()

    def _update_live_preview(self):
        """ "Live preview" needs the model's preview decoder: while it is missing the switch is off and cannot be clicked
        (user 30.10.); once the file is there it is on again, as at every start."""
        m = self._model()
        dec = manifest.preview_decoder(m.key) if m is not None else ""
        missing = bool(dec) and self.inv is not None and self.inv.found(dec) is None
        cb = getattr(self, "cb_live", None)
        if cb is None:
            return
        if missing:
            if not self._live_off_missing:
                self._live_off_missing = True
                self.v_live.set(False)
            cb.configure(state="disabled")
            self.tt_live.text = LIVE_TIP + f"\n\nNeeds {dec}: download it in the settings (gear), under Additional models."
        else:
            if self._live_off_missing:
                self._live_off_missing = False
                self.v_live.set(True)
            cb.configure(state="normal")
            self.tt_live.text = LIVE_TIP

    # ---------- no model chosen ----------

    def start_state(self) -> str:
        """"none_linked": ComfyUI was read and not one tab can run; "no_comfy": no tab is chosen and ComfyUI could not be read
        (not running, so it is unknown which models are there; user 22.11.); "choose": no tab is chosen; "": a model is chosen.
        The window shows no parameters in the first three (the look of those states is decided in FRAGEN.md / docs, see
        entscheidungen); "no_comfy" looks like "choose", only its sentence differs."""
        if self.inv is not None and all(self.inv.tab_status(m.key).state == "missing" for m in models.MODELS):
            return "none_linked"
        if self.v_model.get() or self.v_workflow.get() not in ("", BUILTIN):      # (a workflow of your own is no "no model")
            return ""
        # not read and either the reading failed or the short probe before the window appeared (gui_state._initial_comfy_state)
        # found no ComfyUI: the sentence is right from the first moment, not only after the reading's 2 s (user 22.11.)
        down = self._inv_error or getattr(self, "_comfy_up", None) is False
        return "no_comfy" if (self.inv is None and down) else "choose"

    def _apply_start_state(self, fit: bool = True):
        """Show what belongs to the state: a model is chosen = everything; none chosen = the tabs, one sentence, the footer; no model
        linked = only the sentence and the gear (the footer's connection dots, Refresh and Reset go too). Stacking order stays
        tabs, sentence, body, status line (the footer is packed at the bottom)."""
        state = self.start_state()
        self.v_empty.set(EMPTY_TEXT.get(state, ""))
        for w in (self.f_tabs, self.lbl_empty, self.f_scrollbox):
            w.pack_forget()
        if getattr(self, "_minimized", False):      # minimised: only the header stays (gui.py toggle_minimize)
            if fit and getattr(self, "_sized", False):
                self._fit_height()
            return
        below = self.f_preview if self.f_preview.winfo_manager() else self.f_status   # the live preview sits above the status line:
        if state != "none_linked":                                                     # the tabs must not slip under it
            self.f_tabs.pack(fill="x", padx=10, pady=(8, 2), before=below)
        if state:
            self.lbl_empty.pack(fill="x", padx=10, pady=(26, 22), before=below)
        else:
            self.f_scrollbox.pack(fill="x", before=below)     # the body sits in its scroll box (gui.py)
        hide_foot = state == "none_linked"
        foot_changed = hide_foot != self._foot_hidden
        if foot_changed:
            self._foot_hidden = hide_foot
            for w in (self.lbl_conn, self.b_refresh):
                w.pack_forget()
            if not hide_foot:
                self.lbl_conn.pack(side="left")
                self.b_refresh.pack(side="left", padx=FOOT_REFRESH_PADX)
        # no model chosen or linked: no "Live preview" tick (user 2.11.)
        show_live = not state
        if foot_changed or show_live != getattr(self, "_live_shown", True):
            self._live_shown = show_live
            self.cb_live.pack_forget()
            if show_live:
                self.cb_live.pack(side="left", padx=FOOT_RESET_PADX)
        self._update_ready()
        if fit and getattr(self, "_sized", False):
            self._fit_height()

    def _let_go_unavailable_model(self):
        """At start only: the model of the last session may have lost its files meanwhile. Then no tab is chosen (instead of a
        broken one). Later readings never take the tab away under the user's hands: the preflight explains a missing file."""
        if self._startup_checked or self.inv is None:
            return
        self._startup_checked = True
        m = self._model()
        if m is not None and self.inv.tab_status(m.key).state == "missing":
            self.v_model.set("")
            self.v_workflow.set(BUILTIN)        # _sync_model would pick the model of the workflow again
            self._last_model = ""
            self._status(f"{m.label} is not available (model files missing). Choose a model.")

    def _on_model_core(self):
        if self._refreshing and not self._last_model:
            self.v_model.set("")                # first start: StateMixin would open on the first model; the user chooses
            return
        key, prev = self.v_model.get(), self._last_model
        if key and self.inv is not None and key != prev and self.inv.tab_status(key).state == "missing":
            self.v_model.set(prev)              # a tab that is not available does not open; the settings do not pop up either (user 7.11.)
            label = next((m.label for m in models.MODELS if m.key == key), key)
            msg = f"{label} is not set up yet (model files missing). Open the settings (gear) to see what is needed."
            self._status(msg)
            self._idle_text = msg               # counts as an idle line: the next working model clears it
            return True
        self._last_model = self.v_model.get()
        if key:                                  # the last model comes back at the next start (state.json, like the other settings)
            self.state["model"] = key
            cfgmod.save_state(self.state)
        super()._on_model()

    def _on_model(self):
        if self._on_model_core():               # a tab without files: nothing changed, the message stays
            return
        self._apply_start_state()

    # ---------- preflight ----------

    # Generate with a missing file reads ComfyUI's lists again in the window's thread (P4, user 24.11. choice D): not while the
    # dot says ComfyUI is off (the 0.3 s of a refused connection, or a timeout), and at most once per PREFLIGHT_REREAD_S, so
    # clicking again gives the same message at once. A full reading (Refresh, ComfyUI back, a download) resets the wait.
    PREFLIGHT_REREAD_S = 10.0

    def _reread_inventory(self):
        """A fresh reading, in the calling thread (only used when the cached one says something is missing); None = not read."""
        if getattr(self, "_comfy_up", None) is False:
            return None
        last = getattr(self, "_reread_at", None)
        now = time.monotonic()
        if last is not None and now - last < self.PREFLIGHT_REREAD_S:
            return None
        self._reread_at = now
        try:
            return inventory.fetch(self.comfy, cfgmod.model_map())
        except ComfyError:
            return None

    def _pack_missing(self, inv) -> list[tuple]:
        """(class, pack, link) of node classes of the chosen workflow that a custom node pack brings and ComfyUI does not list
        (manifest.NODE_PACKS: e.g. ComfyUI-KJNodes for Flux 3 Upscale). Classes without a known pack are not reported (new core
        nodes of a newer ComfyUI)."""
        if inv is None or inv.nodes is None:
            return []
        out = []
        for t in self._wf_templates()[:1]:
            for node in t.values():
                cls = node.get("class_type", "") if isinstance(node, dict) else ""
                pack = manifest.node_pack(cls) if cls and cls not in inv.nodes else None
                if pack and pack[0].startswith("ComfyUI itself"):
                    pack = None          # a core node of a newer ComfyUI (SeedVR2): its switch greys itself out (_enforce_switch_files)
                if pack and cls not in {c for c, _p, _u in out}:
                    out.append((cls, pack[0], pack[1]))
        return out

    def _pack_lines(self, inv) -> list[str]:
        return [f"missing node {c}: install {p} ({u})" for c, p, u in self._pack_missing(inv)]

    def _preflight(self) -> list[str]:
        m = self._model()
        if m is None or self.inv is None:
            return []
        mode = self.v_mode.get()
        lines = inventory.preflight(self.inv, m.key, mode) + self._pack_lines(self.inv)
        if lines:       # the cached reading may be old (a file was copied and ComfyUI restarted since): look again first
            fresh = self._reread_inventory()
            if fresh is not None:
                self._set_inventory(fresh)
                lines = inventory.preflight(fresh, m.key, mode) + self._pack_lines(fresh)
        return lines

    def _ready_text(self) -> str:
        """The idle line at the bottom: empty when the chosen model and function can run (no "Ready" any more, user 21.11.);
        else what to get (user 3.11.)."""
        m = self._model()
        if m is None or self.inv is None:
            return ""
        st = self.inv.mode_status(m.key, self.v_mode.get())
        names = [f.name for f in st.missing]
        packs = list(dict.fromkeys([p for _c, p, _u in self._pack_missing(self.inv)] +
                                   [p[0] for c in st.nodes if (p := manifest.node_pack(c))]))
        if not names and not packs and not st.nodes:
            return ""
        parts = []
        if names:
            parts.append(f"download {', '.join(names[:2])}{f' (+{len(names) - 2} more)' if len(names) > 2 else ''} in the settings")
        if packs:
            parts.append(f"install {', '.join(packs)} in ComfyUI")
        return "You need to " + " and ".join(parts or ["download the missing files in the settings"]) + " to run with these options"

    def _update_ready(self):
        """Keep the idle status line right: it is replaced only while it shows an earlier idle text, never a message or an error."""
        cur = self.v_status.get()
        if cur not in ("", "Ready", getattr(self, "_idle_text", "")):
            return
        new = "" if self.start_state() else self._ready_text()
        self._idle_text = new
        if new != cur:
            self.v_status.set(new)

    def generate(self):
        if self.start_state():
            self._status("Choose a model first.")      # Ctrl+Enter must not run with nothing chosen
            return
        if self.v_model.get() and self.v_workflow.get() == BUILTIN:
            # a model is chosen but the workflow fell back to the built-in SD1.5/SDXL graph: that would run the first
            # checkpoint of ComfyUI (a Realistic Vision picture under the name of MOSS; tester 7.11.). Put the model's own back.
            self._apply_model_mode(force=True)
            if self.v_workflow.get() == BUILTIN:
                m = self._model()
                self._status(f"The workflow of {m.label if m else 'this model'} was not found, so nothing was started. "
                             "Check the workflows folder, or choose the model again.", error=True)
                return
        lines = self._preflight()
        if lines:
            self._status(inventory.short_message(lines, self._model().label), error=True)
            return
        super().generate()

    # ---------- the overlay window ----------

    def toggle_settings(self):
        """The gear: opens the settings window, or closes it when it is open (user 28.10.)."""
        win = self._settings_win
        if win is not None:
            try:
                alive = bool(win.winfo_exists())
            except tk.TclError:
                alive = False
            if alive:
                self._settings_close()
                return
            self._settings_win = None
        self.open_settings()

    def open_settings(self, focus: str | None = None):
        self._settings_focus = focus
        if self._settings_win is not None:
            try:
                self._settings_win.lift()
                self._settings_fill()
                return
            except tk.TclError:
                self._settings_win = None
        win = tk.Toplevel(self.root, **hostos.TOP_KW)
        win.title("Settings")
        win.wm_overrideredirect(True)                  # no Windows title bar, only an X (user 1.11.); a thin frame keeps it visible
        win.configure(bg=BG, highlightthickness=1, highlightbackground="#5c5c5c")
        try:
            win.transient(self.root)
            win.minsize(self._px(SET_MIN_W), self._px(SET_MIN_H))      # narrower than this the model tabs would be cut off
            x = self.root.winfo_rootx() + self.root.winfo_width() + 8
            w, h = self._settings_size()[0], self._px(SETTINGS_H)      # always 700 px high, no longer as high as the plugin (user 20.11.)
            y = self.root.winfo_rooty()
            area = self._monitor_at(x, y, work=True) if hasattr(self, "_monitor_at") else None
            if area:      # never below the taskbar or off the screen (150 % on Full HD: 1050 px, review 21.11.)
                y, h = fit_height(y, h, area[1], area[3], self._px(SET_MIN_H))
            win.geometry(f"{w}x{h}+{x}+{y}")
        except (tk.TclError, TypeError):
            pass
        win.protocol("WM_DELETE_WINDOW", self._settings_close)
        win.bind("<Escape>", lambda e: self._settings_close())
        self._settings_win = win
        self._set_anchor = self._root_xy()
        self._own_settings(win)
        self._settings_frame(win)
        idle(win, win.lift)           # without a title bar the window opened far behind the others (z-order 350 against 45)

        # no ComfyUI dot and no Refresh here: the plugin's footer has both

        # the pages Model Links / Other settings: a ttk.Notebook without its own tabs, chosen by two chips like the model chips of
        # the main window (user 19.11.: blue when chosen, no lines above or below). The title, the chips and the content of a page
        # stand on one line from the left edge: the notebook's 4, the 2 px of the theme's frame around a page, the page's 12.
        self._set_left = spacing.Keep(spacing.scale(4) + 2 + spacing.scale(12))
        st = ttk.Style()
        st.layout("Plain.TNotebook.Tab", [])
        st.configure("Plain.TNotebook", tabmargins=(0, 0, 0, 0))
        # as large as the function buttons of the main window (user 19.11.): their font (10 pt, bold when chosen) and their
        # height, and their top edge level with theirs when the two windows stand side by side, tops level: the plugin has
        # 8 + 2 below its header (f_tabs, the grid of the functions), here the chips' grey line of 1 takes one of them
        st.configure("SetTab.Chip.Toolbutton", padding=(14, 3), font=font(10))
        st.map("SetTab.Chip.Toolbutton", font=[("selected", font(10, bold=True))])
        row = ttk.Frame(win)
        row.pack(fill="x", padx=(self._set_left, self._set_left),
                 pady=(spacing.Keep(spacing.scale(8) + spacing.scale(2) - spacing.scale(1)), 0))
        chips = tk.Frame(row, bg=CHIP_LINE, bd=0, highlightthickness=0)      # its colour shows as the lines around the chips
        chips.pack(side="left")
        try:
            fn_h = self.b_mode.winfo_reqheight()
            chips.rowconfigure(0, minsize=fn_h + 2 * spacing.scale(1))      # the chip itself as high as a function button
        except (AttributeError, KeyError, tk.TclError):
            pass
        nb = ttk.Notebook(win, style="Plain.TNotebook")      # tab 1: the models; tab 2: other settings (no credits tab since 16.11.)
        nb.pack(fill="both", expand=True, padx=4, pady=(0, 8))      # 4 + 2 + 12 inside the page: the line of _set_left
        tab_models, tab_other = ttk.Frame(nb), ttk.Frame(nb)
        self._set_tab = tk.IntVar(value=0)
        self.set_tab_chips = []
        for i, (page, text) in enumerate(((tab_models, "Model Links"), (tab_other, "Other settings"))):
            nb.add(page, text=text)
            c = ttk.Radiobutton(chips, text=text, value=i, variable=self._set_tab, style="SetTab.Chip.Toolbutton",
                                command=lambda i=i: nb.select(i))
            c.grid(row=0, column=i, sticky="nsew", padx=(1, 1 if i == 1 else 0), pady=1)
            # room for its text in bold inside the raised border of a chosen chip (border and ring, 3 px a side), else it is cut off
            try:
                bold = tkfont.Font(root=win, font=font(10, bold=True)).measure(text)
                chips.columnconfigure(i, minsize=bold + 2 * spacing.scale(14) + 2 * self._px(4))
            except (tk.TclError, AttributeError, TypeError):
                pass
            self.set_tab_chips.append(c)
        self._other_settings(tab_other)
        self.nb_settings = nb
        # "⋯" at the right end of the chip row, only on Model Links (user 19.11., choice K2): Undo, Reset, Check files
        self.b_set_more = tk.Label(row, text="⋯", bg=BG, fg=FG, font=font(14), padx=self._px(4), pady=0, cursor="hand2", takefocus=1)
        Tooltip(self.b_set_more, "Reset the links, check the files")
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.b_set_more.bind(seq, lambda e: (self._links_menu(), "break")[1], add="+")
        self.b_set_more.bind("<Enter>", lambda e: self.b_set_more.configure(fg=ACCENT), add="+")
        self.b_set_more.bind("<Leave>", lambda e: self.b_set_more.configure(fg=FG), add="+")
        upd = self._update_check_row(row)        # "Check for updates" and "Check now", only on Other settings (user 20.11.)

        def tab_changed(e=None):
            try:
                i = nb.index(nb.select())
                self._set_tab.set(i)               # also when a page is chosen in code (the ComfyUI address opens Other settings)
                if i == 0:
                    upd.pack_forget()
                    self.b_set_more.pack(side="right")
                else:
                    self.b_set_more.pack_forget()
                    upd.pack(side="right")
            except tk.TclError:
                pass
        nb.bind("<<NotebookTabChanged>>", tab_changed, add="+")
        tab_changed()

        # which models the plugin shows (user 29.10.): after installing, all are shown; untick to hide one (the right-click
        # menu of a chip hides too, only here a model comes back). The tick sits in the tab of its model (user 31.10.)
        hidden = cfgmod.hidden_tabs()
        self._shown_vars = {m.key: tk.BooleanVar(value=m.key not in hidden) for m in models.MODELS}

        # on top of "Models": the message after a change of the links with its Undo (only then), the line of Check files while
        # it runs or has something to say, then the field with the model and the page of the model
        self.f_set_top = ttk.Frame(tab_models)
        self.f_set_top.pack(fill="x", side="top", padx=12)
        self.f_set_top.bind("<Configure>", lambda e: self._settings_wrap("top", e.width), add="+")
        self._check_row(tab_models)        # "Check files" (user 17.11.): the checksums of the files on the disk
        self.nb_models = ModelPicker(tab_models, self)
        self.nb_models.pack(fill="both", expand=True, padx=(12, 0), pady=(12, 0))      # the field 12 px in; the page's scroll bar at the right edge
        self.nb_models.bar.pack_configure(padx=(0, 12))      # the field ends 12 px before the right edge too
        self.nb_models.body.pack_configure(pady=(MODEL_GAP, 0))      # room between the field and the model's name
        self._set_pages = {m.key: self._scroll_page(m.key, m.label) for m in models.PICK_ORDER}      # order of the model chip (22.11.)
        self._set_pages["additional"] = self._scroll_page("additional", "Additional")
        keys = {str(p["page"]): k for k, p in self._set_pages.items()}
        self.nb_models.on_select = lambda page: self._draw_page(keys.get(str(page), ""))
        bind_wheel(win, self._settings_wheel)      # only this window: the plugin's body has its own
        self._set_widgets = []
        self._page_rows = {}               # nothing to draw yet: the page of the focus is chosen first, then only it is drawn
        if not self._map_undo:             # the message with Undo stays while there is something to take back (user 21.11.)
            self._link_msg = ""
        if focus in self._set_pages:
            self._select_model_tab(focus)

        self._settings_fill()
        self._detect_async()       # a model copied in since the last reading is listed when the window opens (if ComfyUI sees it)

    def _settings_frame(self, win):
        """What the missing title bar leaves to us: a thin strip on top with the X (dragging it moves the window) and a grip
        in the lower right corner (dragging it resizes the window)."""
        # the header as the plugin's header (user 6.11.): the same height (as a function button), the same top margin, the title
        # in the same size (H1: 12 pt, white, thin) and at the same distance from the left edge
        bar = ttk.Frame(win, height=self._px(HEADER_H))
        # no blue line on top any more (user 19.11.): its 3 px go into the gap, the title stays level with the plugin's title (user 7.11.)
        bar.pack(fill="x", side="top", pady=(spacing.Keep(spacing.scale(max(0, 8 - self._px(3))) + self._px(3)), 0))
        bar.pack_propagate(False)
        title = ttk.Label(bar, text="Settings", foreground="#ffffff", font=font(12))
        title.pack(side="left", padx=(spacing.Keep(spacing.scale(4) + 2 + spacing.scale(12)), 0))      # on the line of the chips and the page (user 19.11.)
        x = ttk.Button(bar, text="✕", style="Link.TButton", width=2, command=self._settings_close)
        x.pack(side="right", padx=(0, 6))
        Tooltip(x, "Close the settings.")
        drag = {}

        def start(e):
            drag["pos"] = (e.x_root - win.winfo_x(), e.y_root - win.winfo_y())

        def move(e):
            if "pos" in drag:
                win.geometry(f"+{e.x_root - drag['pos'][0]}+{e.y_root - drag['pos'][1]}")

        for w in (bar, title):
            w.bind("<ButtonPress-1>", start)
            w.bind("<B1-Motion>", move)
        grip = tk.Frame(win, width=self._px(14), height=self._px(14), bg=BG, cursor=hostos.GRIP_CURSOR)
        grip.place(relx=1.0, rely=1.0, anchor="se")
        size = {}

        def grip_start(e):
            size["from"] = (e.x_root, e.y_root, win.winfo_width(), win.winfo_height())

        def grip_move(e):
            if "from" in size:
                x0, y0, w0, h0 = size["from"]
                w, h = max(self._px(SET_MIN_W), w0 + e.x_root - x0), max(self._px(SET_MIN_H), h0 + e.y_root - y0)
                win.geometry(f"{w}x{h}")

        grip.bind("<ButtonPress-1>", grip_start)
        grip.bind("<B1-Motion>", grip_move)
        self._set_bar, self._set_grip = bar, grip

    def _show_hidden_models(self):
        hidden = cfgmod.hidden_tabs()
        if not hidden:
            self._status("No model is hidden.")
            return
        for key in hidden:
            cfgmod.set_tab_hidden(key, False)
        self._update_mode_radios()
        self._fit_height()
        if self._settings_win is not None:
            self._settings_fill()
        self._status(f"{len(hidden)} hidden model{'s' if len(hidden) != 1 else ''} shown again.")

    def _reset_all_modes(self):
        saved = cfgmod.get_setting("saved_pages", {})
        if not saved:
            self._status("No page has saved settings, all modes already use the standard ones.")
            return
        n = len(saved)
        if not messagebox.askyesno("Reset all modes", f"Forget the saved settings of {n} page{'s' if n != 1 else ''}?\n\n"      # noqa: F405
                                   "Every model and function will start with its standard settings again.",
                                   parent=self._settings_win or self.root):
            return
        cfgmod.set_setting("saved_pages", None)
        self._apply_model_mode()          # the page on screen follows at once (prompt and negative prompt stay)
        self._status("All saved page settings are gone: every mode starts with its standard settings.")

    def _scroll_page(self, key: str, title: str) -> dict:
        """One tab of the model notebook: a canvas that scrolls, its rows in a frame (the rows: one per file, in a frame each)."""
        box = ttk.Frame(self.nb_models)
        self.nb_models.add(box, text=title)
        cv = tk.Canvas(box, bg=BG, highlightthickness=0, bd=0)
        cv.pack(side="left", fill="both", expand=True)
        sb = ThinScrollbar(box, cv, self._px(6), BG, auto=True)
        rows = ttk.Frame(cv)
        win_id = cv.create_window(0, 0, window=rows, anchor="nw")      # the notebook is 12 px in already (user 19.11.)
        cv.bind("<Configure>", lambda e: (cv.itemconfigure(win_id, width=max(1, e.width - self._px(12))), self._settings_wrap(key, e.width - self._px(12))), add="+")
        rows.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")), add="+")
        return {"page": box, "cv": cv, "sb": sb, "rows": rows}

    def _settings_wheel(self, e):
        """The mouse wheel scrolls the model tab that is open."""
        try:
            key = list(self._set_pages)[self.nb_models.index(self.nb_models.select())]
        except (tk.TclError, TypeError, IndexError, AttributeError):
            return
        self._set_pages[key]["sb"].wheel(e)

    def _select_model_tab(self, key: str):
        try:
            self.nb_models.select(self._set_pages[key]["page"])
        except (tk.TclError, KeyError, AttributeError):
            pass

    def _settings_size(self) -> tuple[int, int]:
        """The window's size: the one it had when it was last closed, else about 640 x 700 (user 2.11.: 16 % narrower than before, remembered)."""
        saved = cfgmod.get_setting("settings_size3")      # a new key with the narrower window (19.11.): the old size is not used
        if isinstance(saved, list) and len(saved) == 2 and all(isinstance(v, int) and v >= 300 for v in saved):
            return saved[0], saved[1]
        return self._px(SETTINGS_W), self._px(SETTINGS_H)

    def _own_settings(self, win):
        """The settings window behaves like the bridge window: an owned window of it (and so, through it, of PhotoCraft). It lies
        above them, never above other programs, and is hidden, minimised and closed together with them. Never "always on top":
        that would keep it on screen when PhotoCraft is closed or minimised."""
        if not winlink.available():
            return
        try:
            api = winlink.Win32Api()
            top, owner = api.toplevel(win), api.toplevel(self.root)
            if top and owner and api.owner_of(top) != owner:
                api.set_owner(top, owner)
        except Exception:
            pass

    def _root_xy(self):
        try:
            return self.root.winfo_x(), self.root.winfo_y()
        except tk.TclError:
            return None

    def _settings_follow(self, e=None):
        """The settings window moves with the plugin (user 7.11.): dragged by its header, or moved with PhotoCraft's window."""
        if e is not None and e.widget is not self.root:
            return
        win = self._settings_win
        if win is None:
            return
        now, was = self._root_xy(), getattr(self, "_set_anchor", None)
        if now is None or was is None or now == was or min(now) < -10000:      # a minimised window reports -32000
            return
        self._set_anchor = now
        try:
            win.geometry(f"+{win.winfo_x() + now[0] - was[0]}+{win.winfo_y() + now[1] - was[1]}")
        except tk.TclError:
            pass

    def _settings_close(self):
        win, self._settings_win = self._settings_win, None
        try:
            w, h = win.winfo_width(), win.winfo_height()
            if isinstance(w, int) and isinstance(h, int) and w >= 300 and h >= 300 and [w, h] != cfgmod.get_setting("settings_size3"):
                cfgmod.set_setting("settings_size3", [w, h])      # the size you gave it comes back next time (user 30.10.)
        except (tk.TclError, AttributeError):
            pass
        try:
            win.destroy()
        except (tk.TclError, AttributeError):
            pass

    def _fill_key(self):
        """What the drawing reads besides the rows (not in the rows): hidden models, the state of the link buttons, running downloads."""
        return (tuple(sorted(cfgmod.hidden_tabs())), bool(self._map_undo), cfgmod.model_map() != self._map_start, tuple(sorted(self._dl)),
                getattr(self, "_link_msg", ""))

    def _settings_fill(self):
        rows = self._settings_rows()
        key, top = (rows, self._fill_key()), getattr(self, "f_set_top", None)
        last = getattr(self, "_drawn", None)
        if last is not None and top is not None and last[0] is top and last[1] == key:
            self._settings_titles()          # nothing shown changed: no new widgets (they would be the same ones)
        else:
            self._settings_draw(rows)
            self._drawn = (top, key)

    def _settings_sections(self, rows):
        """The flat rows split for the tabs: (the rows above the models, {model key: its rows}, the rows of "Additional")."""
        top, per, extra, cur = [], {}, [], None
        for row in rows:
            if row[0] == "model" and row[1] != cur:
                cur = row[1]
                per[cur] = []
            elif row[0] == "head" and row[1] == ADDITIONAL_HEAD:
                cur = "additional"
            if cur is None:
                top.append(row)
            elif cur == "additional":
                extra.append(row)
            else:
                per[cur].append(row)
        return top, per, extra

    def _settings_draw(self, rows):
        """The rows of _settings_rows as widgets: the linked files on top, the rest in the tab of its model (or "Additional")."""
        for w in getattr(self, "_set_widgets", []):
            try:
                w.destroy()
            except (tk.TclError, AttributeError):
                pass
        self._set_widgets = []
        self._wrap_labels = []
        self._dl_widgets = {}
        top_frame, pages = getattr(self, "f_set_top", None), getattr(self, "_set_pages", None)
        if top_frame is None or pages is None:
            return
        top, per, extra = self._settings_sections(rows)
        self._draw_rows(top, top_frame, "top")
        # a page is drawn when it is first shown (user 19.11., choice A: all 8 at once took seconds); the one on screen now
        self._page_rows = {key: extra if key == "additional" else per.get(key, []) for key in pages}
        self._pages_drawn = set()
        self._settings_titles()
        self._settings_wrap("top")
        try:
            shown = self.nb_models.select()
        except (tk.TclError, AttributeError):
            shown = None
        self._draw_page(next((k for k, p in pages.items() if p["page"] is shown), ""))

    def _draw_page(self, key: str):
        """The rows of one model page as widgets, once per drawing of the window (_settings_draw forgets them all)."""
        pages, rows = getattr(self, "_set_pages", None), getattr(self, "_page_rows", {})
        if not pages or key not in pages or key not in rows or key in self._pages_drawn:
            return
        self._pages_drawn.add(key)
        self._draw_rows(rows[key], pages[key]["rows"], key)
        self._settings_wrap(key)

    def state_dot(self, state: str):
        """The red dot in front of a model that is not active or available (some or all of its files are missing), with
        DOT_PAD px of room on its left; "" for a ready model (no mark)."""
        if state not in ("partial", "missing"):
            return ""
        cache = self.__dict__.setdefault("_icon_cache", {})
        if ("dot", state) not in cache:
            from PIL import Image, ImageDraw
            sc, d, pad = 4, max(3, round(self._px(9) * 0.7)), self._px(DOT_PAD)      # 70 % of the first size (user 3.11.)
            im = Image.new("RGBA", ((d + pad) * sc, d * sc), (0, 0, 0, 0))
            ImageDraw.Draw(im).ellipse([pad * sc, 0, (pad + d) * sc - 1, d * sc - 1], fill=DOT_RED)
            cache[("dot", state)] = icons.photo(self.root, None, DOT_RED, d, image=im.resize((d + pad, d), Image.LANCZOS))
        return cache[("dot", state)]

    def _settings_titles(self):
        """The tab of a model carries its state: a red dot in front of the name when it is not available, nothing when ready."""
        for key, page in getattr(self, "_set_pages", {}).items():
            if key == "additional":
                continue
            st = self.inv.tab_status(key).state if self.inv is not None else ""
            try:
                self.nb_models.tab(page["page"], text=models.BY_KEY[key].label, image=self.state_dot(st), compound="left")
            except (tk.TclError, AttributeError):
                pass

    def _draw_rows(self, rows, parent, page: str):
        """One frame per row in ``parent``, with the gaps of the page (user 19.11.: SET_IN inside a file, SET_ITEM between two
        files, SET_SECTION before a section): a model's head line, its modes as tiles, the download button, then its files.
        A file: mark, kind and size (and the download symbol) on one line, the link field below it."""
        made, count, prev = self._set_widgets, [0], [""]
        parent.columnconfigure(0, weight=1)
        px = self._px
        slot = px(24)
        indent = 20              # a gap of pack: spacing.py scales it; the field and the notes of a file stand under its kind, right of the mark

        def line(top: int = 0):
            f = ttk.Frame(parent)
            f.grid(row=count[0], column=0, sticky="ew", pady=(top if count[0] else 0, 0))
            count[0] += 1
            made.append(f)
            return f

        def label(box, text, style, side="left", padx=(0, 0), pady=(0, 0), wrap=0, anchor="center", **kw):
            lb = ttk.Label(box, text=text, style=SET_STYLES.get(style, "SetText.TLabel"), **kw)
            lb.pack(side=side, padx=padx, pady=pady, anchor=anchor)
            if wrap:                                    # follows the width of the tab (see _settings_wrap)
                lb.configure(justify="left")
                self._wrap_labels.append((lb, wrap, page))
            return lb

        def fit_to_row(box, lb):
            """``lb`` wraps at the width its row leaves it: the row's width minus what the other widgets of the row really
            take (mark, size, symbols, with their padding), measured, not guessed (user 16.11.: 280 px left a wide gap).
            Measured once when the row is made (they are all packed by then); _settings_wrap applies it with the page's width
            (19.11.: a <Configure> handler on every row set off a chain of resizes, a page took half a second to show)."""
            lb.configure(justify="left")

            def pads(w):          # pack_info gives padx as a number (both sides) or a pair (left, right), as Tk objects or text
                p = w.pack_info().get("padx", 0)
                p = list(p) if isinstance(p, (tuple, list)) else str(p).replace("{", "").replace("}", "").split()
                return sum(int(float(str(x))) for x in p) * (2 if len(p) == 1 else 1)

            try:
                used = sum(k.winfo_reqwidth() + pads(k) for k in (box.pack_slaves() or []) if k is not lb)
                self._wrap_labels.append((lb, used + pads(lb) + px(4), page))
            except (tk.TclError, ValueError, TypeError, AttributeError):
                pass

        def icon(box, kind, tip, command, menu=None, copy=""):
            b = ttk.Button(box, image=self._icon(kind, px=SET_ICON_PX), style="Link.TButton", command=command)
            b.pack(side="right", padx=(4, 0))
            Tooltip(b, tip)
            if copy:
                b.copy_text = copy                      # right-click: Copy link (gui_theme._copy_menu)
            if menu is not None:
                b.bind("<Button-3>", menu, add="+")

        def note(text, style, button="", command=None):
            """A line under a file's field: a hint, with a small button after it (Use) when one click settles it."""
            box = line(SET_IN)
            if button:
                b = ttk.Button(box, text=button, style="SetSmall.TButton", command=command)
                b.pack(side="right", padx=(8, 0), anchor="n")
            lb = label(box, text, style, padx=(indent, 0), anchor="w")
            fit_to_row(box, lb)

        for row in rows:
            kind = row[0]
            if kind == "error":
                box = line()
                label(box, row[1], "bad", padx=(0, 0))
                box = line()
                label(box, row[2], "muted", pady=(0, 8), wrap=px(20))
            elif kind == "model":
                _k, key, name, state, focus, usable = row
                box = line(SET_ITEM)
                var = self._shown_vars[key]
                var.set(key not in cfgmod.hidden_tabs() if usable else False)     # a model without its files is not in PxC
                cb = ttk.Checkbutton(box, text="Show in PxC", variable=var, style="SetText.TCheckbutton",
                                     command=lambda k=key, v=var: self._set_model_hidden(k, not v.get()))
                cb.pack(side="left")          # left, the state as a chip on the right (user 20.11.)
                made.append(cb)
                if usable:
                    Tooltip(cb, "Untick to hide this model in PxC, tick to show it again.")
                else:
                    cb.configure(state="disabled")
                    Tooltip(cb, NOT_ALL_WEIGHTS.format(name=name))
                # the name stands in the field above (user 19.11.): here only the tick or X and the state (user 3.11.)
                if state:
                    ok = state == "ready"
                    chip = tk.Label(box, text=STATE_CHIP[ok], bg=STATE_CHIP_BG[ok], fg=ON_ACCENT, font=font(9, bold=True),
                                    padx=self._px(8), pady=self._px(1), bd=0)
                    chip.pack(side="right")
                    box.state_chip = chip            # for the tests
            elif kind == "modes":
                self._mode_tiles(line(SET_ITEM), row[2])
            elif kind == "download":
                allm = row[2]
                box = line(SET_ITEM)
                b = ttk.Button(box, text=f"{ALL_FILES_BUTTON} · {allm['size']}", style="SetAccent.TButton",
                               command=lambda k=row[1]: self.download_missing(k))
                b.pack(side="left")
                Tooltip(b, f"Download the missing files of this model ({allm['count']}, {allm['size']})"
                           + (f"; {allm['site']} open their page in the browser." if allm["site"] else "."))
            elif kind == "file":
                f = row[1]
                ok = f["found"] is not None
                box = line(8 if prev[0] == "head" else SET_ITEM)
                # the symbols first: pack gives the space to what is packed first, the kind takes what is left
                dl = f["dl"]
                if dl:                                  # loading: a bar and a cross instead of size and disk symbol
                    cancel = ttk.Button(box, text="✕", style="Link.TButton", width=2,
                                        command=lambda n=f["name"]: self.download_cancel(n))
                    cancel.pack(side="right", padx=(4, 0))
                    Tooltip(cancel, "Stop this download. What is loaded stays, loading it again goes on where it stopped.")
                    lb = ttk.Label(box, text="", style=SET_STYLES["muted"], width=8, anchor="e")
                    lb.pack(side="right")
                    bar = ttk.Progressbar(box, length=px(90), maximum=max(dl["total"], 1), value=dl["done"])
                    bar.pack(side="right", padx=(8, 4))
                    self._dl_widgets[f["name"]] = {"bar": bar, "label": lb}
                    self._dl_paint(f["name"])
                else:
                    if f["url"] and not ok:
                        tip = ("Opens the page in your browser (needs a login or comes from another site). Right-click: copy the link."
                               if f["browser"] else f"Download ({f['size'] or 'size unknown'}). Right-click: copy the download link.")
                        icon(box, "save", tip, lambda n=f["name"]: self.download_file(n), menu=lambda e, u=f["url"]: self._link_menu(e, u))
                    else:
                        ttk.Frame(box, width=slot, height=1).pack(side="right", padx=(4, 0))
                    lb = ttk.Label(box, text=f["size"] or "", style=SET_STYLES["muted"], width=8, anchor="e")
                    lb.pack(side="right")
                label(box, "✓" if ok else "✗", "ok" if ok else ("bad" if f["level"] == "required" else "note"),
                      padx=(0, 6), anchor="n", width=2)
                what = f.get("feature") or f.get("use") or ""      # what an optional or shared file is for, small after its kind
                lb_kind = label(box, f["kind"] + (f"   {what}" if what else ""), "", anchor="w")
                fit_to_row(box, lb_kind)
                fbox = line(SET_IN)
                self._link_field(fbox, f, page, spacing.scale(indent)).pack(fill="x", padx=(indent, 0))
                if f["probable"]:          # a renamed copy of it: one click links it (user 19.11.: a Use button)
                    note(PROBABLE_FILE + f["probable"], "hint", "Use", lambda n=f["name"], p=f["probable"]: self._link_models(n, p))
                elif f.get("similar"):
                    note(SIMILAR_FILE + f["similar"], "hint", "Use", lambda n=f["name"], p=f["similar"]: self._link_models(n, p))
                if f["hint"]:
                    note(f["hint"], "note")               # a website is needed
                if f["restart"]:
                    note(RESTART_NOTE, "note")
            elif kind == "gguf":
                box = line(SET_IN)
                label(box, GGUF_ALT, "muted", padx=(indent, 4), anchor="n")
                b = ttk.Button(box, text=GGUF_LINK, style="SetLink.TButton", command=lambda u=row[1]: webbrowser.open(u))
                b.pack(side="left", anchor="n")
                b.copy_text = row[1]                      # right-click: Copy link
                Tooltip(b, "Opens the Hugging Face page of the GGUF files in your browser (smaller files for little VRAM). "
                           "Put the file in ComfyUI's models/unet folder, restart ComfyUI and choose it in the field above; "
                           "needs the ComfyUI-GGUF node pack.")
            elif kind == "node":
                _k, cls, pack, url = row
                box = line(SET_ITEM)
                if url:
                    icon(box, "link", f"Get {pack or 'the node pack'}: opens its page.", lambda u=url: webbrowser.open(u), copy=url)
                label(box, "✗", "bad", padx=(0, 6), anchor="n")
                label(box, f"node {cls}" + (f"   → {pack}" if pack else ""), "", wrap=px(120), anchor="n")
            elif kind == "head":
                label(line(SET_SECTION), row[1], "section")
            elif kind == "stop":         # bottom right of every page: stops every running download of this page's files (user 2.11.)
                names = list(row[1])
                if not any(n in self._dl for n in names):         # only while a download of this page runs (user 2.11.)
                    continue
                b = ttk.Button(line(SET_ITEM), text="Stop downloads", style="SetSmall.TButton",
                               command=lambda n=names: self.download_cancel_all(n))
                b.pack(side="right", padx=(4, 0))
                Tooltip(b, "Stops every download that is running for the files on this page. What is loaded stays, loading it again goes on where it stopped.")
            elif kind == "links":          # after a change of the links: its message and Undo (user 19.11., K2); else nothing
                msg = getattr(self, "_link_msg", "")
                if not msg and not self._map_undo:
                    continue
                box = line()
                box.grid_configure(pady=(12, 0))
                if self._map_undo:         # no time limit; one change per click until none is left (user 21.11.)
                    b = ttk.Button(box, text="Undo", command=self._link_undo, style="SetSmall.TButton")
                    b.pack(side="right", padx=(8, 0))
                    Tooltip(b, self.LINK_UNDO_TIP)
                    self.b_link_undo = b
                lb = label(box, msg, "muted", anchor="w")
                fit_to_row(box, lb)
            prev[0] = kind
        if page != "top":          # room under the last row, so the end of a page does not stick to the window's edge
            ttk.Frame(line(SET_SECTION), height=1).pack()

    def _mode_tiles(self, box, cover):
        """The modes of a model as small tiles that wrap with the window (user 19.11.; before one line of text): "Modes", then
        one tile per mode the model offers, a mode with missing files red with an X. The tooltip says what is missing."""
        px = self._px
        head = ttk.Label(box, text=MODES_HEAD, style=SET_STYLES["section"])      # the font of "Required" (user 19.11.)
        head.place(x=0, y=0)
        tiles = []
        for _m, text, st, tip in cover:
            if st == "none":
                continue
            t = tk.Label(box, text=("✗ " if st == "missing" else "") + text, bg=BG, fg=NA_RED if st == "missing" else FG,
                         font=font(9), padx=px(6), pady=px(1), highlightthickness=1, highlightbackground=CHIP_LINE, bd=0)
            Tooltip(t, tip)
            tiles.append(t)
        box.mode_tiles = tiles          # for the tests

        def flow(e=None):
            try:
                width = box.winfo_width()
                if width <= 1:
                    return
                gap = px(6)
                x0 = 0                   # the heading stands above the tiles (user 19.11.): they take the whole width
                h = max([t.winfo_reqheight() for t in tiles] or [head.winfo_reqheight()])
                x, y = x0, head.winfo_reqheight() + px(4)
                for t in tiles:
                    w = t.winfo_reqwidth()
                    if x > x0 and x + w > width:
                        x, y = x0, y + h + gap
                    t.place(x=x, y=y)
                    x += w + gap
                if box.cget("height") != y + h:
                    box.configure(height=y + h)
            except tk.TclError:
                pass
        box.configure(height=px(48))
        box.bind("<Configure>", flow, add="+")

    def _link_field(self, parent, f, page: str = "", indent: int = 0):
        """The field of a file (user 19.11.; replaces the chain symbol): it shows the file PxC uses, looks like a dropdown and opens
        the search window of the files ComfyUI has right below it. Missing: a red frame and "Missing · choose your file";
        linked to a file of yours: blue with "· linked" and ↺, which brings back the expected file. The folder is in its tooltip."""
        px = self._px
        found, linked = f["found"], f.get("linked")
        frame = NA_RED if found is None else (ACCENT_TEXT if linked else CHIP_LINE)
        box = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=frame, highlightcolor=frame, cursor="hand2", takefocus=1)
        arrow = tk.Label(box, text="▾", bg=PANEL, fg=FG, font=font(9), padx=px(8), cursor="hand2")
        arrow.pack(side="right")
        back = None
        if linked:
            back = tk.Label(box, text="↺", bg=PANEL, fg=FG, font=font(10), padx=px(2), cursor="hand2")
            back.pack(side="right")
            back.bind("<Button-1>", lambda e, n=f["name"]: (self._link_models(n, ""), "break")[1])
            Tooltip(back, "Use the expected file again: " + f["name"])
        text = FIELD_MISSING if found is None else found + (FIELD_LINKED if linked else "")
        lb = tk.Label(box, text=text, bg=PANEL, fg=MUTED if found is None else (HINT_TEXT if linked else FG), font=font(9),
                      anchor="w", justify="left", padx=px(8), pady=px(4), cursor="hand2")
        lb.pack(side="left", fill="x", expand=True)
        box.field_text = text            # for the tests
        # the name wraps at the page's width less the indent, the arrows and the frame, set by _settings_wrap with the other labels
        # (19.11.: a handler of its own on every field set off a chain of resizes, the window took seconds to open)
        margin = indent + (arrow.winfo_reqwidth() or 0) + ((back.winfo_reqwidth() or 0) if back else 0) + px(20)
        self.__dict__.setdefault("_wrap_labels", []).append((lb, margin, page))

        def hover(on):
            if found is not None and not linked:
                try:
                    box.configure(highlightbackground="#9a9a9a" if on else CHIP_LINE)
                except tk.TclError:
                    pass

        def pick(e=None):
            self._choose_for(f["name"], below=box)
            return "break"
        for w in (box, lb, arrow):
            w.bind("<Button-1>", pick, add="+")
            w.bind("<Enter>", lambda e: hover(True), add="+")
            w.bind("<Leave>", lambda e: hover(False), add="+")
        box.bind("<Return>", pick, add="+")
        box.bind("<space>", pick, add="+")
        Tooltip(lb, f"Expected: {f['path']}. Click to choose another file of yours.")
        return box

    def _fit_text(self, t, width: int | None = None):
        """A read-only text box is as high as its wrapped text (so it never scrolls on its own). Measured only when its width changed
        (``width`` from the <Configure> event): a change of its own height fires <Configure> again with the same width."""
        if width is not None:
            if getattr(t, "_fit_width", None) == width:
                return
            t._fit_width = width
        try:
            n = t.count("1.0", "end", "displaylines")
            n = max(1, int(n[0] if isinstance(n, tuple) else n))
            if int(t.cget("height")) != n:
                t.configure(height=n)
        except (tk.TclError, TypeError, ValueError, AttributeError):
            pass

    def _settings_wrap(self, page: str | None = None, width: int | None = None):
        """Wrapping labels follow their tab: the width of the tab minus what stands beside them."""
        if page is not None and isinstance(width, int):
            self._page_w[page] = width
        for lb, margin, pg in getattr(self, "_wrap_labels", []):
            if page is not None and pg != page:
                continue
            w = self._page_w.get(pg)
            if (not isinstance(w, int) or w < 50) and pg != "top":
                w = next((v for k, v in self._page_w.items() if k != "top" and isinstance(v, int) and v >= 50), None)
            if not isinstance(w, int) or w < 50:
                w = self._px(SETTINGS_W - 40)
            try:
                lb.configure(wraplength=max(self._px(120), w - margin))
            except tk.TclError:
                pass

    def _link_menu(self, e, url: str):
        """Right-click on a download symbol: copy its link (user 30.10.)."""
        menu = PopMenu(self._settings_win or self.root, scale=getattr(self, "ui", 1.0))
        menu.add_command(label="Copy download link", command=lambda: self._copy_text(url, "Download link copied."))
        menu.tk_popup(e.x_root, e.y_root)

    def _copy_report(self):
        """"Copy report" (user 7.11.): the diagnostic text of appinfo.build_report on the clipboard."""
        from . import appinfo
        self._copy_text(appinfo.build_report(self), "Report copied. Paste it into your message.")

    def _copy_text(self, text: str, msg: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._status(msg)

    # ---------- link a file of another name ----------

    def _link_resets(self) -> dict:
        """Which resets of the menu "⋯" can act: back to the links of the start, no links at all."""
        now = cfgmod.model_map()
        return {"startup": now != self._map_start, "default": bool(now)}

    LINK_UNDO_TIP = "Takes back the last change of the links. Click again for the change before, until none is left."

    def _link_msg_gone(self):
        """The message over the page goes (only when nothing is left to take back: Undo stays without a time limit, user 21.11.).
        Only the top row is drawn again, the page keeps its place."""
        if not getattr(self, "_link_msg", "") or self._map_undo:
            return
        self._link_msg = ""
        top = getattr(self, "f_set_top", None)
        if top is None:
            return
        try:
            for w in top.winfo_children():
                w.destroy()
        except tk.TclError:
            return
        d = getattr(self, "_drawn", None)
        if d is not None and d[0] is top:
            self._drawn = (top, (d[1][0], self._fill_key()))      # the rows are the same: no full drawing next time

    def _links_menu_entries(self) -> list:
        """What the menu "⋯" of Model Links offers (user 19.11., choice K2; Undo is only the button over the page since 21.11.):
        (label, command, usable now, tooltip); None = a line."""
        can = self._link_resets()
        return [("Reset to startup", self._link_reset, can["startup"], "All links as they were when PxC started."),
                ("Reset to default models", self._link_default, can["default"], "Every model uses its own standard file again."),
                None,
                (self._check_label(), self.check_files, True, self.CHECK_TIP)]

    def _links_menu(self):
        """The button "⋯" at the right end of the tab row: the menu under it, its right edge at the button's."""
        menu = PopMenu(self._settings_win or self.root, scale=getattr(self, "ui", 1.0))
        for e in self._links_menu_entries():
            if e is None:
                menu.add_separator()
            else:
                menu.add_command(label=e[0], command=e[1], state="normal" if e[2] else "disabled", tip=e[3])
        menu.tk_popup(0, 0, below_w=self.b_set_more)
        self._set_menu = menu            # for the tests

    def _link_entries(self, expected: str):
        """What the window of the chain symbol lists for ``expected``: (files, likely right files in order, hints, linked file, file in use),
        or None when ComfyUI lists no other file of this kind. Likely right files go on top (user 7.11.): the expected file itself
        (it was missing from the list after a wrong link), the file in use, renamed copies (same size and header), then names like
        the expected one, best first; all the others follow alphabetically. The file in use is marked "in use" and shown in green."""
        cands, mapped = self._link_candidates(expected), cfgmod.model_map().get(expected)
        if not cands and not mapped:
            return None
        f = manifest.FILES.get(expected)
        all_hints = self._link_hints(expected, cands)
        copies = [n for n in cands if all_hints.get(n, "").startswith(HINT_SAME + expected)]
        hints = self._menu_hints(expected, all_hints)
        self._link_copies = copies        # the blue dot of the window (user 21.11., 10A)
        avail = list(self.inv.lists.get(f.kind, [])) if (f is not None and self.inv is not None) else []
        own = inventory.resolve(f.name, avail, None, f.aliases) if f is not None else None      # the expected file itself (not in ``cands``)
        used = self.inv.found(expected) if self.inv is not None else None
        known = [g.name for g in manifest.FILES.values() if g.name != expected]
        similar = sorted((n for n in cands if n not in copies and namematch.suggest(expected, [n], known)),
                         key=lambda n: -namematch.confidence(expected, n))
        pinned = list(dict.fromkeys(n for n in (own, used, *copies, *similar) if n))
        if own and own not in cands:
            cands = [*cands, own]
        if used and used not in cands:
            cands = [*cands, used]
        for n in similar:
            hints.setdefault(n, HINT_SIMILAR)
        current = mapped or used          # the file the plugin uses now
        if own and own != current:
            hints[own] = HINT_EXPECTED
        if current:
            hints[current] = HINT_IN_USE
        return cands, pinned, hints, mapped, current

    # a kind that needs a ComfyUI with a node of its own: said in the note when its list is empty
    LINK_EMPTY_EXTRA = {"bg_removal": " It needs a current ComfyUI (the node LoadBackgroundRemovalModel).",
                        "upscale_model": " It needs a ComfyUI with the node UpscaleModelLoader."}

    def _link_empty_note(self, expected: str) -> str:
        """The note of the chain window when ComfyUI lists no file of the kind: where the file belongs, what to do after."""
        f = manifest.FILES.get(expected)
        if f is None:
            return "ComfyUI lists no other file of this kind. Put yours into its models folder, restart ComfyUI, then click Refresh."
        what = manifest.KIND_LABEL.get(f.kind, f.kind).lower()
        return (f"ComfyUI lists no {what} file yet. Put your file into ComfyUI's models/{f.folder} folder, restart ComfyUI, then click Refresh."
                + self.LINK_EMPTY_EXTRA.get(f.kind, ""))

    def _choose_for(self, expected: str, below=None):
        """The chain next to a file: a search window with the files ComfyUI has for its kind (typing filters, alphabetical, "Use the expected file again"
        at the bottom when the file is linked). A click links at once (Undo and Reset are in "Linked files")."""
        entries = self._link_entries(expected)
        win = self._settings_win or self.root
        try:          # right below the field that was clicked (user 19.11.), else at the mouse
            at = ((below.winfo_rootx(), below.winfo_rooty() + below.winfo_height()) if below is not None
                  else (win.winfo_pointerx(), win.winfo_pointery()))
        except tk.TclError:
            at = (win.winfo_pointerx(), win.winfo_pointery())
        old = getattr(self, "_link_picker", None)
        if old is not None:
            old.close()
        if entries is None:      # nothing to choose from: a note in the window, no red message in the status line (user 7.11.)
            self._link_picker = linkpicker.LinkPicker(win, at, [], note=self._link_empty_note(expected),
                                                      scale=getattr(self, "ui", 1.0))
            return
        cands, pinned, hints, mapped, current = entries
        # dots instead of texts (user 21.11., choice 10A): green = in use, blue = a copy of the expected file (same size); a file
        # that equals ANOTHER file PxC knows (e.g. another model's) is no replacement and gets no dot (user 21.11.)
        same = set(getattr(self, "_link_copies", ()))
        hints = {n: h for n, h in hints.items() if not h.startswith(HINT_SAME) and h != HINT_IN_USE}
        # a search window instead of a menu (user 7.11.): typing filters, the list is alphabetical, the wheel does not close it
        self._link_picker = linkpicker.LinkPicker(
            win, at, cands, pinned, hints, mapped,
            unlink="Use the expected file again" if mapped else "",
            on_pick=lambda n: self._link_models(expected, n), scale=getattr(self, "ui", 1.0), strong=[current] if current else (),
            same=sorted(same - {current}))

    def _link_models(self, expected: str, actual: str):
        """The plugin uses ``actual`` from now on for ``expected`` ("" removes the link)."""
        before = cfgmod.model_map()
        cfgmod.set_model_link(expected, actual)
        if cfgmod.model_map() != before:
            self._map_undo.append(before)
        self._after_link_change("Linked: " + (f"{expected} → {actual}." if actual else f"{expected} is used again."))

    def _link_undo(self):
        """One change back per click, until none is left (user 21.11.); then the button goes, the message stays."""
        if self._map_undo:
            cfgmod.set_model_map(self._map_undo.pop())
            left = len(self._map_undo)
            self._after_link_change("Undone: the links are as before the last change." if left else
                                    "Undone: nothing more to take back.")

    def _link_default(self):
        """"Reset to default models" (user 5.11.): all links removed, every model uses its own standard file again."""
        before = cfgmod.model_map()
        if before:
            self._map_undo.append(before)
            cfgmod.set_model_map({})
            self._after_link_change("All links are removed: the models use their standard files again.")

    def _link_reset(self):
        if cfgmod.model_map() != self._map_start:
            self._map_undo.clear()           # Undo takes back relinks only, not the reset (user, 27.10.)
            cfgmod.set_model_map(dict(self._map_start))
            self._after_link_change("The links are as they were at startup.")

    def _after_link_change(self, msg: str = "Link saved."):
        self._link_msg = msg                 # shown in the settings window with Undo (user 19.11.), no time limit (21.11.)
        if self.inv is not None:             # only there, not in the status line (user 21.11.)
            self.inv.mapping = cfgmod.model_map()
            self._set_inventory(self.inv, self._inv_error)      # statuses, tabs and the overlay follow at once
