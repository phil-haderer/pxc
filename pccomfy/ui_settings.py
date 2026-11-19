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

import difflib
import tkinter.font as tkfont
import webbrowser

from . import comfyaddr, comfydir, hostos, icons, inventory, jobqueue, linkpicker, manifest, namematch, savefile, spacing, sthead
from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from .gui_theme import HEADER_H, ICON_PX
from .popmenu import PopMenu
from .ui_downloads import DownloadMixin, browser_only, site_hint, size_text
from .ui_update import UpdateMixin

EMPTY_TEXT = {"choose": "Choose a model", "none_linked": "Link your models in the settings"}
STATE_TEXT = {"ready": "ready", "partial": "not ready", "missing": "not ready"}      # small after the model name (user 19.11.; before "is ready.", 1.11.)
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
HINT_EXPLAIN = "Marked files have the same size and safetensors header as another file PxC expects."
DOT_RED = "#e5484d"                   # the dot in front of a model that is not available (nothing in front of a ready one)
DOT_PAD = 4                            # px of room to the left of the dot (user 1.11.)
SETTINGS_W, SETTINGS_H = 520, 700      # the settings window at first (before the display scaling; 640 until 19.11.); then the size it was closed at
SET_ICON_PX = 16                       # the download symbol next to a file
SET_STYLES = {"head": "SetHead.TLabel", "ok": "SetOk.TLabel", "bad": "SetBad.TLabel", "note": "SetNote.TLabel",
              "muted": "SetMuted.TLabel", "green": "SetGreen.TLabel", "red": "SetRed.TLabel",
              "head9": "SetHead9.TLabel", "warn": "SetWarn.TLabel", "hint": "SetHint.TLabel", "section": "SetSection.TLabel"}
SET_MIN_W, SET_MIN_H = 440, 300        # the smallest the settings window can be dragged to (480 until 19.11.)
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

LINK_MSG_MS = 10_000                             # the message with Undo after a change of the links shows this long (user 19.11.)
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


class SettingsMixin(DownloadMixin, UpdateMixin):
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
            rb.configure(style="Missing.Chip.Toolbutton" if not self._model_usable(m.key, self.v_mode.get()) else "Chip.Toolbutton")

    def _model_usable(self, key: str, mode: str) -> bool:
        """Has ComfyUI the files this model needs? The whole model counts, not only the chosen function: a model with one
        function lacking its files is locked (user 30.10.), so nothing is offered that was not tested with its standard settings."""
        if self.inv is None:
            return True
        return self.inv.tab_status(key).state != "missing"

    def _update_mode_radios(self):
        super()._update_mode_radios()
        self._update_tabs()                 # a model chip turns red when its files for the chosen function are missing
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
        """"none_linked": ComfyUI was read and not one tab can run; "choose": no tab is chosen; "": a model is chosen. The window
        shows no parameters in the first two (the look of those states is decided in FRAGEN.md / docs, see entscheidungen)."""
        if self.inv is not None and all(self.inv.tab_status(m.key).state == "missing" for m in models.MODELS):
            return "none_linked"
        return "choose" if (not self.v_model.get() and self.v_workflow.get() in ("", BUILTIN)) else ""      # (a workflow of your own is no "no model")

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
        # no model chosen or linked: no "Live preview" tick and no idle "Ready" (user 2.11.)
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
            self._idle_text = msg               # counts as an idle line: the next working model replaces it with "Ready"
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

    def _reread_inventory(self):
        """A fresh reading, in the calling thread (only used when the cached one says something is missing)."""
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
        """The idle line at the bottom: "Ready" only when the chosen model and function can run; else what to get (user 3.11.)."""
        m = self._model()
        if m is None or self.inv is None:
            return "Ready"
        st = self.inv.mode_status(m.key, self.v_mode.get())
        names = [f.name for f in st.missing]
        packs = list(dict.fromkeys([p for _c, p, _u in self._pack_missing(self.inv)] +
                                   [p[0] for c in st.nodes if (p := manifest.node_pack(c))]))
        if not names and not packs and not st.nodes:
            return "Ready"
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

    # ---------- the overlay: content as plain data (tested without Tk) ----------

    def _settings_rows(self) -> list[tuple]:
        """The "Models" tab as rows (kind, data), drawn by _settings_draw; no Tk here. Kinds (user 19.11.): "links" (the top row:
        Undo and Reset; no count, choice A), "error" (text, detail), "model" (key, label, state, focus, can be shown), "modes" (key, cover),
        "download" (key, what is missing), "file" (a dict, see below), "gguf" (url), "node" (class, pack, url), "head" (text),
        "stop" (file names). A file row: expected name, path with its folder ("/vae/flux2-vae.safetensors"), kind, found (your
        file's name or None), linked, level (required / optional), size text, download url, found on disk (a path or "")."""
        self._fill_ctx = {"extra": {}, "disk": {}, "cands": {}}      # models folder, yaml, disk files, candidates: once per fill
        try:
            return self._settings_rows_now()
        finally:
            self._fill_ctx = None

    def _settings_rows_now(self) -> list[tuple]:
        rows: list[tuple] = []
        links = cfgmod.model_map()
        if self._fill_ctx is not None:
            self._fill_ctx["links"] = links
        # the top row: how many files are linked, with Undo and Reset (user 19.11.: no intro text and no list; a linked file is
        # blue in its own field)
        rows.append(("links", len(links)))      # no "N files linked" (user 19.11., choice A: it read as wrong; a linked file is blue)
        if self.inv is None:
            rows.append(("error", "ComfyUI could not be read.", (self._inv_error or "Not connected yet.")
                         + "\nStart ComfyUI, then click the refresh arrow (⟳) at the bottom of PxC."))
            rows += [("model", m.key, m.label, "", False, True) for m in models.MODELS]      # only "Show in PxC" (no mark, no state)
        else:
            for row in self.inv.rows():
                miss = [f for f, found, lv in row["files"] if found is None and f.url and not self._dl_done(f)]      # every file of the package (user 3.11.)
                direct = [f for f in miss if not browser_only(f)]
                # the head: mark, name, state and "Show in PxC" in one line (user 19.11.); the last value: can it be shown
                rows.append(("model", row["key"], row["label"], row["status"].state, row["key"] == self._settings_focus,
                             row["status"].state != "missing"))
                rows.append(("modes", row["key"], self._mode_cover(row["key"])))      # small tiles (user 19.11.)
                if miss:      # the one blue button of the page (user 19.11.)
                    rows.append(("download", row["key"], {"count": len(direct), "site": len(miss) - len(direct),
                                                          "size": size_text(sum(f.size for f in direct))}))
                needed = [x for x in row["files"] if x[2] == "required"]
                extra = [x for x in row["files"] if x[2] != "required"]
                rows.append(("head", REQUIRED_HEAD))
                last_unet = max((i for i, x in enumerate(needed) if x[0].kind == "unet"), default=-1)
                for i, (f, found, level) in enumerate(needed):
                    rows.append(("file", self._file_data(f, found, level)))
                    if i == last_unet and row["key"] in manifest.GGUF_PAGES:      # under the main model's weights (user 5.11.)
                        rows.append(("gguf", manifest.GGUF_PAGES[row["key"]]))
                for c in row["status"].nodes:
                    pack = manifest.node_pack(c)
                    rows.append(("node", c, pack[0] if pack else "", pack[1] if pack else ""))
                if extra:       # the files of the extra features, apart from the ones the standard settings need (user 2.11.)
                    rows.append(("head", OPTIONAL_HEAD))
                    for f, found, level in extra:      # what each file is for, in brackets after it (user 16.11.)
                        rows.append(("file", {**self._file_data(f, found, level), "feature": manifest.feature_use(row["key"], f.name)}))
                rows.append(("stop", [f.name for f, _fd, _lv in row["files"]]))
            rows.append(("head", ADDITIONAL_HEAD))
            add_names = []
            for f, found, use, keys in self.inv.additional_rows():
                add_names.append(f.name)
                rows.append(("file", {**self._file_data(f, found, "optional"),
                                      "use": manifest.ADDITIONAL_USE.get(f.name) or f"{use}: " + ", ".join(models.SHORT[k] for k in keys)}))
            rows.append(("stop", add_names))
        return rows

    def _mode_cover(self, key: str) -> list[tuple]:
        """The functions a model covers: (mode key, label, state, tooltip); state ready / missing (a file or node is missing) /
        none (the model does not offer it). Named as in the main window (user 19.11.): the tab "Edit canvas" for the whole-picture
        edit, and the two tabs that are no mode of their own: "Insert reference" (Flux 3, under Fill; runs as Multi image edit)
        and "Scribble with reference" (runs as Scribble on photo)."""
        m = models.BY_KEY[key]
        names = {"edit": "Edit canvas", "multi_edit": "Multi image edit"}      # the tab names under the prompt
        extra = {"inpaint": ("bbox", "Insert reference", "multi_edit", bool(m.bbox)),
                 "scribble": ("refscribble", models.REF_SCRIBBLE_LABEL, "scribble", "scribble" in m.modes and models.offers_ref_scribble(m))}
        out = []

        def add(mode, label, status_of, offered):
            if not offered:
                out.append((mode, label, "none", "This model does not offer this function."))
                return
            st = self.inv.mode_status(key, status_of) if self.inv is not None else None
            if st is None or st.state == "ready":
                out.append((mode, label, "ready", "Ready."))
            else:
                need = [f.name for f in st.missing] + list(st.nodes)
                out.append((mode, label, "missing", "Missing: " + ", ".join(need[:3]) + (" ..." if len(need) > 3 else "")))

        for mode, label in MODE_LABELS:           # noqa: F405
            if mode == "img2img":
                continue
            add(mode, names.get(mode, label), mode, mode in m.modes)
            if mode in extra:
                add(*extra[mode])
        return out

    def _file_data(self, f, found, level) -> dict:
        """One file row: expected name, path, found (your file's name or None), level, size, url, note, the download state
        (see DownloadMixin._dl_info), "restart" (loaded, ComfyUI does not list it yet) and "browser" (its page opens instead)."""
        probable = self._probable_file(f) if found is None else ""
        ctx = getattr(self, "_fill_ctx", None)
        links = ctx["links"] if (ctx and "links" in ctx) else cfgmod.model_map()
        return {"name": f.name, "path": file_path(f), "found": found, "level": level, "size": f.size_text, "url": f.url,
                "kind": manifest.KIND_LABEL.get(f.kind, f.kind), "linked": f.name in links,      # the field of the file (user 19.11.)
                "dl": self._dl_info(f.name),        # no note of models.json under a file (user 16.11. evening; before: no licence, 2.11.)
                "restart": found is None and f.name in self._dl_restart, "browser": browser_only(f) if f.url else False,
                "hint": site_hint(f) if (found is None and f.url and browser_only(f)) else "",
                "other": found is not None and self._is_other_file(f, found),
                "probable": probable,
                "similar": self._similar_file(f) if (found is None and not probable) else ""}

    def _probable_file(self, f) -> str:
        """A file ComfyUI lists under another name that is the missing ``f`` (same size, complete safetensors header), or "".
        Needs the models folder (not asked for here) and, for a file that was just renamed, a ComfyUI restart."""
        base = self.models_dir(ask=False) if f.size else None
        if base is None:
            return ""
        same = []
        for n in self._link_candidates(f.name):
            p = self._disk_file(f, n)
            if p is not None and p.stat().st_size == f.size:
                same.append(n)
        hints = self._link_hints(f.name, same)
        return next((n for n in same if hints.get(n) == HINT_SAME + f.name), "")

    def _similar_file(self, f) -> str:
        """A file ComfyUI lists whose NAME is like the missing ``f`` (same model in another precision or spelling: namematch.py), or "".
        Files the plugin itself knows (another entry of models.json) are no stand-ins. A hint only; a renamed copy found by size
        and header (``_probable_file``) is named first and wins (the caller asks only when there is none)."""
        known = [g.name for g in manifest.FILES.values() if g.name != f.name]
        return namematch.suggest(f.name, self._link_candidates(f.name), known)

    @staticmethod
    def _is_other_file(f, found: str) -> bool:
        """Show "your file: ..." when ComfyUI's file is not the expected one by name, folder included (user 7.11.: a tester's file in
        ``flux/`` was found but looked missing; before, a main diffusion model in another folder was left out). Only case and the
        kind of slash do not count."""
        return inventory.norm(found) != inventory.norm(f.name)

    def _link_candidates(self, expected: str) -> list[str]:
        """The files ComfyUI lists for the kind of ``expected`` that can stand in for it (itself left out), the ones with a
        name most like it first. ComfyUI's own list: it knows its folders, the default one, the extra ones and links."""
        f = manifest.FILES.get(expected)
        if f is None or self.inv is None:
            return []
        ctx = getattr(self, "_fill_ctx", None)
        if ctx is not None and expected in ctx["cands"]:
            return list(ctx["cands"][expected])
        avail = list(self.inv.lists.get(f.kind, []))
        own = inventory.resolve(f.name, avail, None, f.aliases)
        base = lambda n: n.replace("\\", "/").rpartition("/")[2].lower()      # noqa: E731
        out = sorted((n for n in avail if n != own),
                     key=lambda n: -difflib.SequenceMatcher(None, base(n), base(f.name)).ratio())
        if ctx is not None:
            ctx["cands"][expected] = out
        return list(out)

    def _disk_file(self, f, name: str):
        """The path on disk of ``name`` (as ComfyUI lists it) for the kind of ``f``: in ComfyUI's models folder or in one of the extra
        folders of its extra_model_paths.yaml; None when it is in none of them."""
        base = self.models_dir(ask=False)
        if base is None:
            return None
        ctx = getattr(self, "_fill_ctx", None)
        if ctx is not None and (f.folder, name) in ctx["disk"]:
            return ctx["disk"][f.folder, name]
        if ctx is not None:
            if f.folder not in ctx["extra"]:          # extra_model_paths.yaml: read once per folder and fill
                ctx["extra"][f.folder] = comfydir.extra_model_dirs(base, f.folder)
            dirs = [Path(base) / f.folder, *ctx["extra"][f.folder]]
        else:
            dirs = [Path(base) / f.folder, *comfydir.extra_model_dirs(base, f.folder)]
        rel, found = name.replace("\\", "/"), None
        for d in dirs:
            try:
                if (d / rel).is_file():
                    found = d / rel
                    break
            except OSError:
                continue
        if ctx is not None:
            ctx["disk"][f.folder, name] = found
        return found

    def _link_hints(self, expected: str, cands: list[str]) -> dict[str, str]:
        """For the files of the chain list: "same size and header as <file>" when the file's size and its safetensors header match a file of
        the manifest (a renamed copy; for the expected file itself it names <expected>), "incomplete? ..." when the header promises
        more bytes than the file has. Files in the extra folders of extra_model_paths.yaml count too."""
        f = manifest.FILES.get(expected)
        base = self.models_dir(ask=False) if f is not None else None
        if base is None:
            return {}
        by_size = {g.size: g.name for g in manifest.FILES.values() if g.kind == f.kind and g.size}
        out: dict[str, str] = {}
        for n in cands:
            p = self._disk_file(f, n)
            if p is None:
                continue
            size = p.stat().st_size
            head = sthead.read_header(p)
            if head is None:
                continue
            if not sthead.is_complete(p):
                out[n] = HINT_INCOMPLETE
            elif size in by_size:
                out[n] = HINT_SAME + by_size[size]
        return out

    @staticmethod
    def _menu_hints(expected: str, hints: dict[str, str]) -> dict[str, str]:
        """The hints shown in the chain list: "same size and header as <file>" only for a file that equals ANOTHER file of the manifest
        than the expected one (a warning against mixing them up); a copy of the expected file is already named under the missing
        file ("This is probably the right file"). "incomplete?" always stays (user 6.11.)."""
        return {n: h for n, h in hints.items() if h != HINT_SAME + expected}

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
            w, h = self._settings_size()
            h = self._root_height(h)           # as high as the plugin window (user 12.11.)
            win.geometry(f"{w}x{h}+{x}+{self.root.winfo_rooty()}")
            self._set_root_h = self.root.winfo_height()
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
            fn_h = self.rb_modes["edit"].winfo_reqheight()
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
        Tooltip(self.b_set_more, "Undo, reset the links, check the files")
        for seq in ("<Button-1>", "<Return>", "<space>"):
            self.b_set_more.bind(seq, lambda e: (self._links_menu(), "break")[1], add="+")
        self.b_set_more.bind("<Enter>", lambda e: self.b_set_more.configure(fg=ACCENT), add="+")
        self.b_set_more.bind("<Leave>", lambda e: self.b_set_more.configure(fg=FG), add="+")

        def tab_changed(e=None):
            try:
                i = nb.index(nb.select())
                self._set_tab.set(i)               # also when a page is chosen in code (the ComfyUI address opens Other settings)
                if i == 0:
                    self.b_set_more.pack(side="right")
                else:
                    self.b_set_more.pack_forget()
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
        self._set_pages = {m.key: self._scroll_page(m.key, m.label) for m in models.MODELS}
        self._set_pages["additional"] = self._scroll_page("additional", "Additional")
        keys = {str(p["page"]): k for k, p in self._set_pages.items()}
        self.nb_models.on_select = lambda page: self._draw_page(keys.get(str(page), ""))
        bind_wheel(win, self._settings_wheel)      # only this window: the plugin's body has its own
        self._set_widgets = []
        self._page_rows = {}               # nothing to draw yet: the page of the focus is chosen first, then only it is drawn
        self._link_msg = ""                # the message with Undo shows only after a change in this window
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

    def _other_settings(self, parent):
        """The tab "Other settings" (user 1.11.): the tip tick, and two buttons that undo things done elsewhere in the plugin."""
        self._update_note_row(parent)         # "Update X available" at the very top, only while one is known (user 19.11., H2)
        self._comfy_address_row(parent)
        self._other_sep(parent)
        self._save_image_row(parent)
        self._other_sep(parent)
        self._owner_name_row(parent)
        for text, tip, command in (
                ("Show all hidden models", "Brings back every model chip that was hidden (right-click menu of a chip or the tick in the model tab).",
                 self._show_hidden_models),
                ("Reset all modes to default settings", "Forgets every page you saved with “Set current settings as startup settings (for this mode and model)” (right-click on a model chip): "
                 "all models and functions start with the PxC standard settings again. Asks first.", self._reset_all_modes),
                ("Copy report", "Copies a report to the clipboard for a bug report: PxC version, where it is installed, Python, "
                 "which config files it reads and what they change, the ComfyUI address, which model files are missing. No prompts, "
                 "no passwords; your user folder is shown as ~.", self._copy_report)):
            b = ttk.Button(parent, text=text, style="SetSmall.TButton", command=command)
            b.pack(side="top", anchor="w", padx=14, pady=(8, 0))
            Tooltip(b, tip)
        self._ui_scale_row(parent)
        self._update_check_row(parent)        # "Check for updates" and "Check now" (user 19.11., A1 + A2)
        self._tips_setting_row(parent)        # the very bottom of the tab (user 13.11.)

    @staticmethod
    def _other_sep(parent):
        """The light line (style Sep.TFrame, as in the model tabs) above and below the Save image block (user 12.11.)."""
        ttk.Frame(parent, style="Sep.TFrame", height=1).pack(side="top", fill="x", padx=14, pady=(14, 0))

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
        ttk.Label(box, text="ComfyUI address", style=SET_STYLES["head"]).pack(anchor="w")
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
        # a line under the address block, as above "Prompt" in the main window (window test F, 11.11.)
        ttk.Frame(parent, style="Sep.TFrame", height=1).pack(side="top", fill="x", padx=14, pady=(10, 0))

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

    def _root_height(self, default: int) -> int:
        """The plugin window's height (the settings window is as high); `default` when it cannot be read."""
        try:
            h = self.root.winfo_height()
        except tk.TclError:
            return default
        return h if isinstance(h, int) and h >= 100 else default

    def _settings_follow(self, e=None):
        """The settings window moves with the plugin (user 7.11.): dragged by its header, or moved with PhotoCraft's window."""
        if e is not None and e.widget is not self.root:
            return
        win = self._settings_win
        if win is None:
            return
        rh = self._root_height(0)
        if rh and rh != getattr(self, "_set_root_h", None):      # the plugin's height changed: the settings window follows (user 12.11.)
            self._set_root_h = rh
            try:
                win.geometry(f"{win.winfo_width()}x{rh}")
            except tk.TclError:
                pass
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
                cb.pack(side="right")
                made.append(cb)
                if usable:
                    Tooltip(cb, "Untick to hide this model in PxC, tick to show it again.")
                else:
                    cb.configure(state="disabled")
                    Tooltip(cb, NOT_ALL_WEIGHTS.format(name=name))
                # the name stands in the field above (user 19.11.): here only the tick or X and the state (user 3.11.)
                if state:
                    label(box, "✓" if state == "ready" else "✗", "green" if state == "ready" else "red", padx=(0, 6))
                    label(box, STATE_TEXT[state], "muted")
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
                if not msg:
                    continue
                box = line()
                box.grid_configure(pady=(12, 0))
                if self._map_undo:
                    b = ttk.Button(box, text="Undo", command=self._link_undo, style="SetSmall.TButton")
                    b.pack(side="right", padx=(8, 0))
                    Tooltip(b, "Takes back the last change of the links.")
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

    def _link_msg_gone(self):
        """The message with Undo goes after LINK_MSG_MS (user 19.11.); Undo stays in the menu "⋯". Only the top row is drawn
        again, the page keeps its place."""
        self._link_msg_job = None
        if not getattr(self, "_link_msg", ""):
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
        """What the menu "⋯" of Model Links offers (user 19.11., choice K2): (label, command, usable now, tooltip); None = a line."""
        can = self._link_resets()
        return [("Undo", self._link_undo, bool(self._map_undo), "Takes back the last change of the links."),
                None,
                ("Reset to startup", self._link_reset, can["startup"], "All links as they were when PxC started."),
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
        # a search window instead of a menu (user 7.11.): typing filters, the list is alphabetical, the wheel does not close it
        self._link_picker = linkpicker.LinkPicker(
            win, at, cands, pinned, hints, mapped,
            explain=HINT_EXPLAIN if any(h.startswith(HINT_SAME) for h in hints.values()) else "",
            unlink="Use the expected file again" if mapped else "",
            on_pick=lambda n: self._link_models(expected, n), scale=getattr(self, "ui", 1.0), strong=[current] if current else ())

    def _link_models(self, expected: str, actual: str):
        """The plugin uses ``actual`` from now on for ``expected`` ("" removes the link)."""
        before = cfgmod.model_map()
        cfgmod.set_model_link(expected, actual)
        if cfgmod.model_map() != before:
            self._map_undo.append(before)
        self._after_link_change("Linked: " + (f"{expected} → {actual}." if actual else f"{expected} is used again."))

    def _link_undo(self):
        if self._map_undo:
            cfgmod.set_model_map(self._map_undo.pop())
            self._after_link_change("Undone: the links are as before the last change.")

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
        self._link_msg = msg                 # shown in the settings window with Undo (user 19.11.), for LINK_MSG_MS
        job = getattr(self, "_link_msg_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except (tk.TclError, ValueError):
                pass
        try:
            self._link_msg_job = self.root.after(LINK_MSG_MS, self._link_msg_gone)
        except (tk.TclError, AttributeError):
            self._link_msg_job = None
        if self.inv is not None:
            self.inv.mapping = cfgmod.model_map()
            self._set_inventory(self.inv, self._inv_error)      # statuses, tabs and the overlay follow at once
        self._status(msg)
