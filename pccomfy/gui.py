"""The Tk window. App is assembled from the mixins in gui_*.py; this file keeps the start-up, the layout (_build) and the window handling."""
from __future__ import annotations

from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _COMMON  # noqa: F401
from .gui_theme import ThemeMixin, HEADER_H, HINT_ICON_PX, HINT_TEXT_DROP, ICON_PX, SMALL_ICON_PX, FOOT_BTN_PX
from .gui_prompt import PromptMixin
from .gui_lora import LoraMixin
from .gui_modes import ModeMixin
from .gui_state import COMFY_WATCH_MS, WATCH_MS, StateMixin
from .gui_run import RunMixin
from .gui_tips import TipsMixin
from .ui_settings import SettingsMixin, GEAR_PX, GEAR_HEAD_PX, FOOT_REFRESH_PADX, FOOT_RESET_PADX
from .refslots import RefSlotsMixin
from .gui_batch import BatchMixin
from .gui_queuewin import QueueWinMixin
from . import clipboard
from .popmenu import PopMenu
from . import hostos, icons, jobqueue, savefile, spacing, startlog, x11link
from .appname import HEADER_TITLE, WINDOW_TITLE

REVEAL_MS = 3000        # the window is shown at the latest this long after the start, linked to PhotoCraft or not (user 22.11.)


class App(SettingsMixin, RefSlotsMixin, ThemeMixin, PromptMixin, LoraMixin, ModeMixin, StateMixin, RunMixin, TipsMixin, BatchMixin, QueueWinMixin):
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.state = cfgmod.load_state()
        self._version_note = cfgmod.check_version()       # "Updated from X to Y" / newer settings / unwritable folder: shown once at the start (gui_state._apply_refresh)
        d = cfg["defaults"]
        pcc, cc = cfg["photocraft"], cfg["comfyui"]
        self.pc = PhotoCraft(pcc["host"], int(pcc["port"]), token_file=pcc["token_file"], headless=bool(pcc["headless"]))
        winlink.set_control_port(pcc["port"])      # the window sits only on the PhotoCraft with this control port (16.11.)
        self.comfy = ComfyUI(cfgmod.get_setting("comfyui_url") or cc["url"])      # the address from Other settings wins over config.toml
        self.bridge = Bridge(self.pc, self.comfy, pcc["exchange_dir"])
        self.workflows_dir, self._wf_dir_note = cfgmod.effective_workflows_dir(cc["workflows_dir"])
        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        # the batch queue (jobqueue.py, gui_batch.py, gui_queuewin.py): no batch job starts while the window's own worker runs; Generate sends
        # the owner's name too, so the queue window of every PC shows who sent each run (decision 18.11., replaces 12.11.)
        self.runner = jobqueue.QueueRunner(self.bridge, events=self.events,
                                           gate=lambda: not (self.worker and self.worker.is_alive())
                                           and not getattr(self, "_direct_pending", False))
        self.comfy.owner = self.runner.owner

        _dpi_aware()   # without it Windows stretches the window as a bitmap on a scaled display: blurry text
        self.root = tk.Tk(**hostos.ROOT_KW)
        try:            # invisible from the first moment, shown when it is in its place (_hide_until_placed, user 22.11.)
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        def tk_error(exc, val, tb):         # an error inside a button or timer: Tk only prints it, and without a console nobody sees it
            import traceback
            traceback.print_exception(exc, val, tb)      # as before, for a console
            try:
                f = cfgmod.EXCHANGE_DIR / "error.log"
                f.parent.mkdir(parents=True, exist_ok=True)
                old = f.read_text(encoding="utf-8").splitlines()[-150:] if f.exists() else []
                f.write_text("\n".join(old + "".join(traceback.format_exception(exc, val, tb)).splitlines()) + "\n", encoding="utf-8")
            except Exception:
                pass
        self.root.report_callback_exception = tk_error
        # Linux has the window manager's title bar: no text in it (user 4.11.; one space, because an empty title makes some
        # desktops show the program's class name instead). Windows has no title bar; the title stays for the task bar.
        self.root.title(WINDOW_TITLE if hostos.IS_WINDOWS else " ")
        self.root.configure(bg=BG)
        self._apply_linux_scale()       # Linux: the detected scale; everywhere: the user's own choice (Other settings)
        try:
            # display scaling (150 % = 1.5); never below 100 % unless the user chose a smaller scale (Interface scale)
            self.ui = max(0.5 if self._own_scale else 1.0, float(self.root.winfo_fpixels("1i")) / 96)
        except Exception:
            self.ui = 1.0
        spacing.install(self.ui / spacing.REF)      # the gaps keep the proportion to the text at every scale (spacing.py)
        self.root.resizable(False, False)       # a fixed width; the height is set from the content (_fit_height)
        self._sized = False
        # no title bar (user 31.10.): the header is the handle (drag, minimise, close). PCCOMFY_TITLEBAR=1 brings the
        # Windows title bar back. Linux always has the window manager's title bar (PLAN.md 18c, A).
        self._frameless = hostos.IS_WINDOWS and not os.environ.get("PCCOMFY_TITLEBAR")
        if self._frameless:
            self.root.wm_overrideredirect(True)
            self.root.configure(highlightthickness=1, highlightbackground=WINDOW_BORDER, highlightcolor=WINDOW_BORDER)
            # the 1 px frame turns blue while the plugin has the focus (user 18.11.); a popup of the plugin counts as focus
            self.root.bind("<FocusIn>", lambda e: self._focus_frame(), add="+")
            self.root.bind("<FocusOut>", lambda e: self.root.after(1, self._focus_frame), add="+")
        self._style()
        if not self._frameless:
            self.root.after(200, lambda: winlink.caption(self.root, (0x40, 0x40, 0x40), (0xee, 0xee, 0xee)))

        g = lambda k, default: self.state.get(k, default)  # noqa: E731
        start_mode = g("mode", "inpaint")
        self.v_mode = tk.StringVar(value="edit" if start_mode in ("multi_edit", "sketch", "scribble") else start_mode)     # Edit starts on the tab Edit canvas (user 7.11.)
        self.v_workflow = tk.StringVar(value=g("workflow", BUILTIN))
        self.v_ckpt = tk.StringVar(value=g("checkpoint", d["checkpoint"]))
        self.v_clip = tk.StringVar(value=g("clip", "") or CLIP_DEFAULT)
        self.v_steps = tk.IntVar(value=g("steps", d["steps"]))
        self.v_cfg = tk.DoubleVar(value=g("cfg", d["cfg"]))
        self.v_denoise = tk.DoubleVar(value=g("denoise", d["denoise"]))
        self.v_seed = tk.IntVar(value=-1)
        self.v_writer_seed = tk.IntVar(value=max(0, int(g("writer_seed", WRITER_SEED_DEFAULT) or 0)))     # hidden writer seed (17.11.; no field since 18.11.: -1 of an old save = 0)
        self.v_variants = tk.IntVar(value=g("variants", d["variants"]))
        self.v_sampler = tk.StringVar(value=g("sampler", d["sampler"]))
        self.v_scheduler = tk.StringVar(value=g("scheduler", d["scheduler"]))
        self.v_res = tk.IntVar(value=g("base_res", d["base_res"]))
        self.v_native = tk.BooleanVar(value=bool(g("native", True)))      # "Original size" (Advanced settings)
        self.v_native_mp = tk.DoubleVar(value=float(g("native_mp", native_mp_default(g("mode", "inpaint")))))
        self.v_ref_native = tk.BooleanVar(value=bool(g("ref_native", REF_NATIVE_DEFAULT)))   # Multi Image Edit: reference images in original size
        self.v_ref_mp = tk.DoubleVar(value=float(g("ref_mp", REF_MP)))
        self.v_gen_mp = tk.IntVar(value=int(g("gen_mp", models.GEN_MP_STEPS[0])))   # MiniMax: the area the model draws (PLAN 2.0b)
        self.v_downsize = tk.BooleanVar(value=bool(g("downsize", False)))   # MiniMax: off = a new document, on = a layer in the canvas
        self.v_context = tk.DoubleVar(value=g("context", d["context"]))
        # Context is remembered per mode. Fill Selection starts at 0.2: with a wide margin Fibo lets the new object grow
        # beyond the selection or doubles it (live test); the other modes keep the global default.
        self._ctx_default = d["context"]
        self._ctx_mode = self.v_mode.get()
        self._ctx = {"inpaint": FILL_CONTEXT}
        if self._ctx_mode == "inpaint":
            if abs(self.v_context.get() - self._ctx_default) < 1e-9:   # the old default, never chosen on purpose
                self.v_context.set(FILL_CONTEXT)
        else:
            self._ctx["inpaint"] = FILL_CONTEXT
        self.v_grow = tk.IntVar(value=g("mask_grow", d["mask_grow"]))
        self.v_blur = tk.IntVar(value=g("mask_blur", d["mask_blur"]))
        self.v_overlap = tk.IntVar(value=g("overlap", d["overlap"]))
        self.v_scale = tk.StringVar(value=scale_text(g("scale", 1.5)))
        self.v_fac = tk.StringVar(value=scale_text(g("scale", 1.5)))     # the factor buttons: "none" (Refine) or the factor; follows v_scale and the mode
        self.v_fn = tk.StringVar(value="")        # the function button that is lit for a function with tabs (Edit, Fill)
        self.v_top = tk.BooleanVar(value=True)      # the window always belongs to PhotoCraft (no switch any more)
        self.v_feather = tk.DoubleVar(value=2.0)    # the function's own value is set after the build (see below)
        self.v_density = tk.IntVar(value=100)       # the same
        self.v_live = tk.BooleanVar(value=True)     # live preview of the sampler under the plugin: on at every start (T3a)
        self.v_enhance = tk.BooleanVar(value=g("enhance", False))   # off at the first start, like Reset
        self.v_turbo = tk.BooleanVar(value=g("turbo", True))
        self.v_lora_str = tk.DoubleVar(value=g("lora_strength", 1.0))
        self.v_model = tk.StringVar(value=g("model", ""))   # the tab; "" = a workflow of your own (everything enabled)
        self.v_cmp_res = tk.StringVar(value="")
        self.v_cmp_ctx = tk.StringVar(value="")
        self.v_stage = tk.BooleanVar(value=g("stage_on", True))
        self.v_stage2 = tk.BooleanVar(value=g("stage2_on", False))
        self.v_stage3 = tk.BooleanVar(value=g("stage3_on", False))
        self._stage_wf = g("workflow", "")   # the workflow the stage checkboxes were last set for
        try:
            sstr = [float(x) for x in g("stage_strengths", [1.0, 1.0, 1.0])][:3]
        except (TypeError, ValueError):
            sstr = []
        self.v_sstr = [tk.DoubleVar(value=(sstr[i] if i < len(sstr) else 1.0)) for i in range(3)]   # strength of a stage that is a LoRA
        self.v_detail = tk.DoubleVar(value=g("detail", 1.0))
        self._vals_key = None                # (workflow, speed LoRA on) the steps / CFG / denoise fields were last read for
        self._wf_vals: dict = {}
        self._lora_wf = g("workflow", "")   # the workflow the LoRA strength slider was last set for
        self.v_lmask = tk.StringVar(value=LAYER_MASKS[layer_mask_key(g("layer_mask", "soft"))])
        self.v_status = tk.StringVar(value="")       # no "Ready" (user 21.11.)
        self.v_conn = tk.StringVar(value="")

        self._build(d)
        self._initial_comfy_state()          # the dot shows the real state from the first moment
        self._set_loras(self.state.get("loras"))
        self._booting = True    # the saved window state is shown as it was: the model's starting settings are not applied
        self._on_mode()
        self._booting = False
        self._start_fresh()
        # the edge feather is not kept from the last time: every start has the function's own value (decision of the
        # user 28.10.; before, every start showed 2 % and Fibo Fill / Qwen Fill looked hard until the function was chosen again)
        spec = self._model().modes.get(self.v_mode.get()) if self._model() else None
        self.v_feather.set(float(spec.settings.get("feather_pct", 2.0)) if spec else 2.0)
        self._on_feather()
        self.v_density.set(int(spec.settings.get("mask_density", 100)) if spec else 100)
        self._on_density()
        self._on_top()
        self._fit_height(self._px(MIN_W))
        self._place_window()
        self._hide_until_placed()           # no first picture in the top left corner and then a jump (user 22.11.)
        self._start_log_begin()             # data/exchange/window-start.log: the first 30 s of the window (startlog.py)
        self._sized = True
        self.root.after(100, self._poll)
        self.root.after(200, self.refresh)
        self.root.after(1500, self._batch_recover)      # results of batch jobs that finished while the plugin was closed
        self.root.after(COMFY_WATCH_MS, self._watch_comfy)
        self.root.after(WATCH_MS, self._watch_photocraft)
        self._schedule_tip()
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self.root.bind("<Configure>", self._remember_pos, add="+")
        self.root.bind("<Configure>", self._settings_follow, add="+")      # the settings window moves with the plugin (user 7.11.)

    def _build(self, d):
        r = self.root
        pad = {"padx": 10, "pady": 4}

        # the head: the function chip and the model chip beside it (user 20.11., before: function buttons two per row and model
        # chips three per row below them; a model that cannot do the chosen function is greyed out in its list).
        # See docs/archiv/ux-funktion-zuerst.md.
        # the header above the functions (user 29.10.): as high as a function button, empty for now (the user's picture
        # comes later into f_logo); on its right the minimise button. Minimised, only this header stays (option A)
        self.f_header = ttk.Frame(r)
        self.f_header.pack(fill="x", padx=10, pady=(8, 0))
        self.f_logo = ttk.Frame(self.f_header, height=self._px(HEADER_H))
        self.f_logo.pack(side="left", fill="x", expand=True)
        self.f_logo.pack_propagate(False)       # the title never makes the header higher
        # a makeshift title until the user's picture comes (user 3.11., variant B): the two names white and thin, the sign
        # between them in the light blue of the prompt tip (ACCENT_TEXT, user 4.11.) and bold, 12 pt; the texts come from appname.py
        left, sign, right = HEADER_TITLE
        # "P × C" (user 11.11.): 20 % larger than the 12 pt of before (HEADER_PT), the gaps 20 % smaller (5 -> 4 px);
        # f_logo keeps its height (pack_propagate off), so nothing else moves
        self.lbl_title = [ttk.Label(self.f_logo, text=left, foreground="#ffffff", font=font(HEADER_PT)),
                          ttk.Label(self.f_logo, text=sign, foreground=ACCENT_TEXT, font=sign_font()),
                          ttk.Label(self.f_logo, text=right, foreground="#ffffff", font=font(HEADER_PT))]
        self.lbl_title[0].pack(side="left", padx=(2, HEADER_GAP))
        self.lbl_title[1].pack(side="left", padx=(0, HEADER_GAP))
        self.lbl_title[2].pack(side="left")
        self._minimized = False
        if self._frameless:         # far right: closes the plugin (what the title bar's cross did)
            self.b_close = ttk.Button(self.f_header, image=self._icon("close", px=SMALL_ICON_PX), style="Link.TButton", command=self._quit)
            self.b_close.pack(side="right", padx=(6, 0))
            Tooltip(self.b_close, "Close PxC.")
            for w in (self.f_header, self.f_logo, *self.lbl_title):     # drag the window by its header
                w.bind("<ButtonPress-1>", self._drag_start, add="+")
                w.bind("<B1-Motion>", self._drag_move, add="+")
        # minimised: the progress as a thin blue line along the bottom edge (user 24.11. evening, gui_run._mini_bar_sync)
        self.f_mini_bar = tk.Frame(r, bg=ACCENT, bd=0, highlightthickness=0, height=self._px(3))
        self.b_min = ttk.Button(self.f_header, image=self._icon("minimize", px=SMALL_ICON_PX), style="Link.TButton", command=self.toggle_minimize)
        self.b_min.pack(side="right")
        self.tt_min = Tooltip(self.b_min, "Minimise: only this header stays. Click again to show PxC.")
        # left of it comes the gear (ui_settings.py, user 4.11.); the clock and Copy canvas sit at the right end of the footer
        self._history_popup = None
        self._cut_popup = None
        for w in (self.f_header, self.f_logo, *self.lbl_title):      # a double click on the header does the same (user 29.10., option C)
            w.bind("<Double-Button-1>", lambda e: self.toggle_minimize(), add="+")
        self.f_tabs = ttk.Frame(r)
        self.f_tabs.pack(fill="x", padx=10, pady=(8, 2))
        # the head (user 20.11.): ONE chip for the function, on the left, and one for the model right beside it, grey like the
        # function buttons were, with the arrow of the variants piece of Generate; a click opens the list (the functions in the
        # order of the former buttons, the models in the order of the former chips). Each is as wide as its longest entry, so
        # the model chip does not move. The lists' entries (rb_modes, rb_tabs) keep what the buttons had: state,
        # listed or not, files missing (PickItem); the lists are built from them when they open (gui_modes.py _mode_menu).
        self.rb_modes = {key: PickItem(label) for key, label in MODE_LABELS}
        self.rb_tabs = {m.key: PickItem(m.label) for m in models.MODELS}
        self._mode_order = []
        self.b_mode = ttk.Button(self.f_tabs, style="Pick.TButton", compound="left", command=self._mode_menu)
        gap = self._px(PICK_GAP)
        self.b_mode.grid(row=0, column=0, sticky="ew", padx=(1, gap - gap // 2))      # 1: the left edge of the former chips and of the tabs below
        # the model chip as high and as wide as the function chip, together they fill the width (user 20.11.): an empty picture
        # as high as the function symbol gives it the same height, the two columns share the width
        self._pick_strut = tk.PhotoImage(master=self.root, width=1, height=self._px(ICON_PX))
        self.b_model = ttk.Button(self.f_tabs, style="Pick.TButton", command=self._model_menu, image=self._pick_strut, compound="left")
        self.b_model.grid(row=0, column=1, sticky="ew", padx=(gap // 2, 0))     # the gap split, so both cells are equally wide
        for c in (0, 1):
            self.f_tabs.columnconfigure(c, weight=1, uniform="pick")
        for b in (self.b_mode, self.b_model):        # the arrow sits at the right edge of the chip's real width
            b.bind("<Configure>", lambda e: self._show_picks(), add="+")
        self.b_model.bind("<Button-3>", lambda e: self._chip_menu(self.v_model.get(), e), add="+")   # save / reset settings, hide (gui_modes.py)
        self.v_pick_mode = tk.StringVar(value="")       # the chosen entry of the function list (light blue, normal weight since 20.11.)
        # no dot in the two lists: the chosen entry is light blue (user 20.11.; not bold since the evening); the list's symbols start where the
        # chip's symbol does (_pick_menu_pad)
        # font_size 10: the entries as big as the chip's text (Pick.TButton, user 21.11.)
        pick_kw = dict(scale=getattr(self, "ui", 1.0), checks=False, chosen_fg=PICK_CHOSEN, icon_gap=PICK_ICON_GAP, font_size=10)
        self.m_mode = PopMenu(self.root, **pick_kw)
        self.m_model = PopMenu(self.root, **pick_kw)
        self.m_chip = PopMenu(self.root, scale=getattr(self, "ui", 1.0))
        for v in (self.v_mode, self.v_model, self.v_fn):
            v.trace_add("write", lambda *a: self._show_picks())
        self._show_picks()

        # everything under the tabs: hidden while no model is chosen (ui_settings.py). It sits in a Canvas, so it can scroll
        # with a thin bar when the window would be taller than the screen (Advanced open, many slots): _fit_height decides.
        self.f_scrollbox = ttk.Frame(self.root)
        self.f_scrollbox.pack(fill="x")
        try:
            body_bg = ttk.Style().lookup("TFrame", "background") or BG
        except Exception:
            body_bg = BG
        self.cv_body = tk.Canvas(self.f_scrollbox, bg=body_bg, highlightthickness=0, bd=0)
        self.cv_body.pack(side="left", fill="both", expand=True)
        self.sb_body = ThinScrollbar(self.f_scrollbox, self.cv_body, self._px(6), body_bg)
        self.f_body = ttk.Frame(self.cv_body)
        self._body_win = self.cv_body.create_window(0, 0, window=self.f_body, anchor="nw")
        self.cv_body.bind("<Configure>", lambda e: self.cv_body.itemconfigure(self._body_win, width=e.width), add="+")
        self.f_body.bind("<Configure>", self._on_body_size, add="+")
        bind_wheel(self.root, self.sb_body.wheel, all_=True)
        r = self.f_body

        mf = ttk.Frame(r)
        mf.columnconfigure(1, weight=1)
        # Workflow and Text model live under "Advanced" (built below): the model tabs choose them.
        self.f_adv = ttk.Frame(r)
        self.adv_body = ttk.Frame(self.f_adv)
        self.adv_body.columnconfigure(1, weight=1)
        # Advanced settings in groups (user 20.11., B): the function's rows, "Sampling", "Custom LoRAs"; adv_body rows:
        # 1 f_post, 2 "Sampling", 3 a stage marked advanced, 4 f_samp (Qwen's / MOSS' Turbo LoRA), 5 Steps/CFG/Seed,
        # 6 Sampler/Scheduler, 7 the switch box (Flux upscale), 9 Custom LoRAs, 10 Save settings / Load defaults. The function's
        # heading over its rows ("EXPAND IMAGE") is gone (user 25.11.: "they are useless")
        self.lbl_grp_samp = ttk.Label(self.adv_body, text="SAMPLING", style="Group.TLabel")
        self.lbl_grp_samp.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 2))
        self.f_samp = ttk.Frame(self.adv_body)
        self.f_samp.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.f_samp.grid_remove()          # in the grid only while a row is packed in it (_sync_post_box)
        # the captions a blue "changed" dot sits beside (user 20.11., C; _adv_dots)
        self._adv_anchor = {}
        # the finishing options at the top of "Advanced settings": Mix source/new, Qwen's switches, Context, Edge feather, Layer mask
        self.f_post = ttk.Frame(self.adv_body)
        self.f_post.grid(row=1, column=0, columnspan=2, sticky="ew")      # row 0: a stage marked advanced (skip-layer guidance)
        # Workflow is not shown: the model tabs choose the workflow and its settings (the widgets stay, the code
        # behind them is the same)
        self.cb_workflow = ttk.Combobox(self.adv_body, textvariable=self.v_workflow, state="readonly", width=8)
        self.cb_workflow.bind("<<ComboboxSelected>>", lambda e: self._workflow_picked())
        # the text model is chosen by the workflow / the LLM list under the prompt: no picker (the widget stays, never gridded)
        self.cb_clip = ttk.Combobox(self.adv_body, textvariable=self.v_clip, state="readonly", width=8)
        self._icons = {}

        # "Compare base res / context" (a test series) are not shown; the code behind them stays (the fields are never gridded)
        e1 = ttk.Entry(self.adv_body, textvariable=self.v_cmp_res)
        e2 = ttk.Entry(self.adv_body, textvariable=self.v_cmp_ctx)
        self.f_enh = ttk.Frame(r)       # packed under Seed / Variants, above the prompt writer drop-down (see below)
        self.cb_enhance = ttk.Checkbutton(self.f_enh, text="Enhance my Prompt with LLM", variable=self.v_enhance, command=self._on_workflow)
        self.cb_enhance.pack(side="left")
        self.tt_enhance = Tooltip(self.cb_enhance, "")      # filled per model by _on_workflow (enhance_tip)
        self._icons["copy"] = self._icon("copy", px=round(ICON_PX * 0.8))     # 80 % of the usual icon, flat like the other icons: white, blue under the mouse (user 1.11.)
        self._last_vgl = ""             # the prompt the text model wrote in the last run
        self._written_for = ""          # Sketch: the model whose written prompt the history put into the field (runs without the upsampler)
        # shown only once the text model wrote a prompt that can be copied (user 20.11.; _sync_copy), before that not there
        self.b_copy = ttk.Button(self.f_enh, image=self._icons["copy"], style="Copy.Link.TButton", command=self._copy_enhanced)
        self.tt_copy = Tooltip(self.b_copy, "Copy the prompt the text model wrote in the last run.")
        # "Reroll prompt" (user 18.11., choice A): a new writer seed, the next run writes a new prompt; only while Enhance is on
        self.b_reroll = ttk.Button(self.f_enh, text="Reroll prompt", style="Copy.Link.TButton", command=self.reroll_prompt)
        self.tt_reroll = Tooltip(self.b_reroll, REROLL_TIP)
        self.v_enhance.trace_add("write", lambda *a: self._update_reroll())
        # the workflow's own LoRA (Turbo, DMD2 ...) in its own row: in the switch box (row 1) or, for MOSS, alone at the top of
        # the Advanced settings while UltraReal stays under the prompt (user 20.11.; _update_options_box). A child of the body,
        # so it can be placed in either box.
        self.f_turbo = ttk.Frame(r)
        self.f_turbo.columnconfigure(0, weight=1)
        self.cb_turbo = ttk.Checkbutton(self.f_turbo, text="LoRA", variable=self.v_turbo, command=self._on_turbo)
        self.cb_turbo.grid(row=0, column=0, sticky="w", padx=(0, 6))   # flush left like the LLM row (user 30.10.)
        self.tt_turbo = Tooltip(self.cb_turbo, LORA_TIP)

        self.f_lora = ttk.Frame(self.f_turbo)    # strength of that LoRA: on the right of its checkbox, like every slider
        self.f_lora.grid(row=0, column=1, sticky="e")
        self.w_lora_str = Slider(self.f_lora, scale=self.ui, from_=0.0, to=1.0, variable=self.v_lora_str, command=self._on_lora_str,
                                 length=self._px(SLIDER_W))
        self.w_lora_str.grid(row=0, column=0)
        self.lbl_lora_str = ValueBox(self.f_lora, self.w_lora_str, self._on_lora_str)
        self.lbl_lora_str.grid(row=0, column=1, sticky="e", padx=(8, 0))
        Tooltip(self.w_lora_str, "LoRA strength (0 = off, 1 = full).")
        # up to three switchable stages of a workflow (SeedVR2, an optional LoRA, skip-layer guidance ...), each its own checkbox
        self.stage_vars = [self.v_stage, self.v_stage2, self.v_stage3]
        self.stage_cbs, self.stage_tips = [], []
        self.stage_scales, self.stage_lbls = [], []     # a stage that is a LoRA (MOSS' Lenovo) also has a strength slider
        for i, var in enumerate(self.stage_vars):
            cb = ttk.Checkbutton(mf, text="Stage", variable=var, command=lambda i=i: self._on_stage(i))
            cb.grid(row=3 + i, column=1, sticky="w", padx=(0, 6), pady=(2, 0))
            self.stage_tips.append(Tooltip(cb, STAGE_TIP))
            self.stage_cbs.append(cb)
            sf = ttk.Frame(mf)
            sf.grid(row=3 + i, column=2, sticky="e", pady=(2, 0))
            sc = Slider(sf, scale=self.ui, from_=0.0, to=1.0, variable=self.v_sstr[i], length=self._px(SLIDER_W),
                        command=lambda _v=None: self._update_stage_scales())
            sc.pack(side="left")
            lb = ValueBox(sf, sc, lambda: self._update_stage_scales())
            lb.pack(side="left", padx=(8, 0))
            Tooltip(sc, "LoRA strength (0 = off, 1 = full).")
            sf.grid_remove()
            self.stage_scales.append((sf, sc, lb))
        # a stage marked "advanced" (MOSS' skip-layer guidance, user 7.11.) shows its checkbox at the top of the Advanced settings: a twin of
        # the one above (same variable), made when the workflow has such a stage (gui_modes._show_stage_cbs)
        self.stage_adv_cbs = [ttk.Checkbutton(self.adv_body, text="Stage", variable=var, command=lambda i=i: self._on_stage(i))
                              for i, var in enumerate(self.stage_vars)]
        self.stage_adv_tips = [Tooltip(cb, STAGE_TIP) for cb in self.stage_adv_cbs]
        self.cb_stage = self.stage_cbs[0]
        for cb in self.stage_cbs:
            cb.grid_remove()
        self._on_lora_str()

        self.f_opts = mf                # LoRA and stage switches of the workflow: shown only when it has some (_update_options_box)

        ff = ttk.Frame(self.f_post)     # shown only while a soft layer mask is used (see _update_feather_state)
        self.f_feather = ff
        self._slider_row(ff)
        lbl_f = self._adv_anchor["feather"] = ttk.Label(ff, text="Edge feather", style="Muted.TLabel")
        lbl_f.grid(row=0, column=0, sticky="w")
        self.w_feather = sc = Slider(ff, scale=self.ui, from_=0, to=10, variable=self.v_feather, command=self._on_feather,
                                     length=self._px(SLIDER_W))
        sc.grid(row=0, column=1, sticky="e", padx=8)
        self.lbl_feather = ValueBox(ff, sc, self._on_feather)
        self.lbl_feather.grid(row=0, column=2, sticky="e")
        self._on_feather()
        for w in (lbl_f, sc):
            Tooltip(w, "Softens the seam between the new area and your picture, in % of the selection's shorter side. 0 = hard edge.")

        fd = ttk.Frame(self.f_post)     # shown with Edge feather (see _update_feather_state)
        self.f_density = fd
        self._slider_row(fd)
        lbl_d = self._adv_anchor["density"] = ttk.Label(fd, text="Mask density", style="Muted.TLabel")
        lbl_d.grid(row=0, column=0, sticky="w")
        self.w_density = sc = Slider(fd, scale=self.ui, from_=0, to=100, variable=self.v_density, command=self._on_density,
                                     length=self._px(SLIDER_W))
        sc.grid(row=0, column=1, sticky="e", padx=8)
        self.lbl_density = ValueBox(fd, sc, self._on_density)
        self.lbl_density.grid(row=0, column=2, sticky="e")
        self._on_density()
        for w in (lbl_d, sc):
            Tooltip(w, "How strongly the soft layer mask hides the redrawn area around your selection. "
                       "0 % = the whole redrawn area shows, 100 % = only the selection with its soft edge. "
                       "You can change it later in PhotoCraft's layer mask properties.")

        # the gap above "Prompt": no line any more under the function and model chips (user 20.11.), the room stays the same
        self.sep_prompt = ttk.Frame(r, height=1)
        self.sep_prompt.pack(fill="x", padx=10, pady=(6, 4))
        # the row over the field holds only the choice buttons (f_pchoice). The icons Styles, Save, Describe Canvas (only in Text to
        # image and Upscale / Refine without tiles) and the bin sit in ONE narrow column at the right of the field, from its top
        # down in this order, all in the size of the bin (user 12.11., window test)
        self.f_ptop = ttk.Frame(r)
        self.f_ptop.pack(fill="x", padx=10, pady=(0, 4))
        self.f_ptop.columnconfigure(1, weight=1)
        self.f_pleft = ttk.Frame(self.f_ptop)
        self.f_pleft.grid(row=0, column=0, sticky="nsw")
        self.f_prompt = ttk.Frame(r)
        self.f_prompt.pack(fill="x", padx=10)
        self.f_picons = ttk.Frame(self.f_prompt)
        self.f_picons.pack(side="right", anchor="n", padx=(self._px(2), 0))
        icon_px = round(SMALL_ICON_PX * 0.9)      # the bin's size (90 % of the other flat icons, user 6.11.)
        # "Styles" (user 1.11.): style prompts (styles.json) and Custom prompts, shown by _update_styles_button
        self._icons["styles"] = self._icon("palette", px=icon_px)
        self.b_styles = ttk.Button(self.f_picons, image=self._icons["styles"], style="Link.TButton", command=self._styles_menu,
                                   takefocus=False)
        Tooltip(self.b_styles, STYLES_TIP)
        self._styles_shown = False
        self._build_styles_menus()
        # "Save" (user 11.11., the Prompt-Saver): in every function (grey while the field is off); the saved prompts are under
        # Style prompts > Custom prompts
        self._icons["save_prompt"] = self._icon("save", px=icon_px)
        self.b_save = ttk.Button(self.f_picons, image=self._icons["save_prompt"], style="Link.TButton", command=self.save_prompt,
                                 takefocus=False)
        self.b_save.pack(side="top", pady=(0, self._px(2)))
        Tooltip(self.b_save, SAVE_PROMPT_TIP)
        # "Describe Canvas" (user 30.10., named "LLM" until 3.11., an icon since 6.11.): the model's own text model describes the
        # picture, the text goes in front of the prompt; below Save
        self._icons["llm"] = self._icon("describe", px=icon_px)
        self.b_llm = ttk.Button(self.f_picons, image=self._icons["llm"], style="Link.TButton", command=self.describe_canvas,
                                takefocus=False)
        self.b_llm.pack(side="top", pady=(0, self._px(2)))
        self._llm_shown = True
        self.tt_llm = Tooltip(self.b_llm, LLM_TIP)
        # the bin, last in the column (user 12.11.; was in the field, bottom right, since 10.11.)
        self._icons["clear"] = self._icon("trash", px=icon_px)
        self.b_clear = ttk.Button(self.f_picons, image=self._icons["clear"], style="Link.TButton", command=self._clear_prompt,
                                  takefocus=False)
        self.b_clear.pack(side="top")
        Tooltip(self.b_clear, "Delete the prompt (Ctrl+Z in the field brings it back).")
        self.f_pchoice = ttk.Frame(self.f_pleft)
        self.f_pchoice.pack(side="left", padx=(10, 0))
        self._pchoice_key = None
        try:
            lines = max(3, min(30, int(self.state.get("prompt_h", PROMPT_LINES))))
        except (TypeError, ValueError):
            lines = PROMPT_LINES
        self.t_prompt = self._text(self.f_prompt, lines)
        self.t_prompt.configure(highlightcolor="#454545")       # no blue frame in focus either (user 20.11.)
        self._build_prompt_placeholder()
        # fills its frame: with fill="x" only it was centred in a frame that still had the old height while the grip was
        # dragged, so its top edge jumped by half a line
        self.t_prompt.pack(side="left", fill="both", expand=True)
        # the same thin bar as the body (design list, point 10): only while the text is longer than the field
        self.sb_prompt = ThinScrollbar(self.f_prompt, self.t_prompt, self._px(6), BG, auto=True)
        self.grip = ttk.Frame(r, style="Grip.TFrame", height=self._px(7), cursor="sb_v_double_arrow")
        self.grip.pack(fill="x", padx=10, pady=(1, 0))
        self._grip_drag(self.grip, self.t_prompt)
        # the grip belongs under the text field only, not under the icon column at its right (user 12.11.): its right margin
        # grows by the width of that column whenever the column changes
        self.f_picons.bind("<Configure>", self._fit_grip, add="+")
        Tooltip(self.grip, "Drag to resize the prompt field.")
        # the tip under the prompt: orange text with an orange info icon in front, level with its first line (user 29.10.)
        self.f_hint = ttk.Frame(r)
        self.lbl_hint_icon = ttk.Label(self.f_hint, image=self._icon("info", HINT_TEXT, px=HINT_ICON_PX))
        self.lbl_hint_icon.pack(side="left", anchor="n", padx=(0, 6), pady=(self._keep(4), 0))
        # selectable text (user 1.11.), not the icon; the wrap width is the row's width
        self.lbl_hint = SelectableLabel(self.f_hint, text=EXPAND_HINT, fg=HINT_TEXT, bg=BG, fnt=font(10))   # every mode's tip (see _update_prompt_hint)
        self.lbl_hint.pack(side="left", anchor="n", fill="x", expand=True, pady=(self._keep(4 + HINT_TEXT_DROP), 0))   # the first line a little lower, level with the icon (user 3.11.; 1 px more 13.11.)
        # Krea 2 / MOSS Expand: writes a description of the surroundings into the field (under the tip, user 29.10.)
        self.b_describe = ttk.Button(r, text="Describe", style="Small.TButton", command=self.describe_scene)
        Tooltip(self.b_describe, "The text model describes the surroundings of your picture (not the main subject) and writes "
                                 "it into the prompt. Edit it as you like.")
        # the prompt field starts empty: the function's default fills it (_apply_model_mode); the last session's text is not
        # restored (user 3.11.: after a start every prompt field is on its default)
        # "Sharpen result" removed everywhere (user 17.11.), Fibo Refine's 10 % too
        self.f_neg = ttk.Frame(r)
        self.f_neg.pack(fill="x")     # no negative prompt in the window (user 2.11.): an empty frame, only the others are packed after it
        self.f_enh.pack(fill="x", padx=10, pady=(6, 0))     # the LLM row: directly under the negative prompt (user 30.10.)
        self.v_neg_open = tk.BooleanVar(value=bool(self.state.get("neg_open", False)))
        self.btn_neg = ttk.Button(self.f_neg, command=self._toggle_negative, style="Link.TButton")
        self.neg_body = ttk.Frame(self.f_neg)
        self.t_neg = self._text(self.neg_body, 2)
        self.t_neg.pack(fill="x")
        self.t_neg.insert("1.0", self.state.get("negative", d["negative"]))

        self.f_xl = ttk.Frame(self.adv_body)       # extra LoRAs: a search box with a drop-down and a strength each (under Advanced)
        self.f_xl.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))     # the very last row of the Advanced settings (user 6.11.)
        self.all_loras: list[str] = []
        self.lora_rows: list[dict] = []
        head = ttk.Frame(self.f_xl)
        head.pack(fill="x")
        self._adv_anchor["loras"] = ttk.Label(head, text="CUSTOM LORAS", style="Group.TLabel")
        self._adv_anchor["loras"].pack(side="left")
        self.b_addlora = ttk.Button(head, text="Add", image=self._icon("plus", MUTED, px=round(ICON_PX * 0.85 * 0.85)), compound="left", style="Link.TButton",   # 85 % of the usual icon (user 6.11.), 85 % of that again (25.11.)
                                    command=self._add_lora_row)
        self.b_addlora.pack(side="right")
        Tooltip(self.b_addlora, "Adds an extra LoRA (strength 0 to 1.5).")
        self.f_xl_rows = ttk.Frame(self.f_xl)
        self.f_xl_rows.pack(fill="x")
        # the last row (user 25.11.): "Save settings" with the disk and "Load defaults", together the whole width
        f_page = self.f_page_btns = ttk.Frame(self.adv_body)
        f_page.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(2, 0))     # 10, then 4 were too far from the LoRAs (user 25.11.)
        f_page.columnconfigure((0, 1), weight=1, uniform="page")
        self.b_save_page = ttk.Button(f_page, text="Save settings", image=self._icon("save", px=round(SMALL_ICON_PX * 0.85)), compound="left",   # 85 % (user 25.11.)
                                      command=self.save_settings)
        self.b_save_page.grid(row=0, column=0, sticky="nsew", padx=(0, self._keep(3)))     # nsew: both as high as the one with the disk
        self.b_load_std = ttk.Button(f_page, text="Load defaults", command=lambda: self.reset_settings(factory=True))
        self.b_load_std.grid(row=0, column=1, sticky="nsew", padx=(self._keep(3), 0))
        Tooltip(self.b_save_page, SAVE_PAGE_TIP)
        Tooltip(self.b_load_std, LOAD_STD_TIP)
        mf.pack(fill="x", padx=10, pady=(0, 4), after=self.f_enh)     # the LoRA / stage box: under the LLM row
        af = ttk.Frame(self.adv_body)
        af.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        # Seed sits in the Advanced settings beside Steps and CFG (user 29.10.)
        items = [("Steps", self._spin(af, self.v_steps, 1, 99, 1, 3, steps_typed_ok)),
                 ("CFG", self._spin(af, self.v_cfg, 1, 9.9, 0.5, 3, cfg_typed_ok)),
                 ("Seed (-1 random)", self._spin(af, self.v_seed, -1, 10**SEED_DIGITS - 1, 1, 9, seed_typed_ok)),
                 ("Denoise", self._spin(af, self.v_denoise, 0.05, 1.0, 0.05, 5))]
        # Denoise is not shown (the user, 28.10.: "there is no use for it"): the widget stays ungridded, so the workflow's /
        # the function's value, presets, Reset and the requests work as before
        for col, (lbl, w) in enumerate(items):
            if lbl == "Denoise":
                continue
            cap = ttk.Label(af, text=lbl, style="Muted.TLabel")
            cap.grid(row=0, column=col, sticky="sw", padx=(0, 6))
            self._adv_anchor[("steps", "cfg", "seed")[col]] = cap
            w.grid(row=1, column=col, sticky="nw", padx=(0, 6))     # at the top of its row: the taller seed button pushed it down, away from its label
        # beside the seed: the seed of the last run again (user 1.11.), grey until a run has finished; 80 % like the copy icon (user 18.11.)
        self._last_seed = None
        self.b_last_seed = ttk.Button(af, image=self._icon("seed-last", px=round(ICON_PX * 0.8)), style="Link.TButton", command=self.use_last_seed, state="disabled")
        # level with the seed box: the button is higher than the box, so it spans both rows and starts above it (column 3 has no label)
        up = max(0, cap.winfo_reqheight() + (items[2][1].winfo_reqheight() - self.b_last_seed.winfo_reqheight()) // 2)
        self.b_last_seed.grid(row=0, rowspan=2, column=3, sticky="nw", pady=(spacing.Keep(up), 0))
        af.rowconfigure(1, weight=1)      # what the button needs beyond the box goes to the lower row, the label stays on the box
        Tooltip(self.b_last_seed, "Use the seed of the last run again: the same settings then give the same result. "
                                  "Grey until a run has finished.")
        self.w_denoise = items[3][1]
        self.w_steps, self.w_cfg, self.w_seed = items[0][1], items[1][1], items[2][1]
        self.tt_steps = Tooltip(self.w_steps, "")      # a hint of the mode, when it has one (MOSS: 25 steps)
        self.recipe_widgets = [items[0][1], items[1][1]]
        # (the "Prompt writer seed" row of 17.11. is gone: the seed is hidden, "Reroll prompt" in the LLM row draws a new one, 18.11.)

        sm = ttk.Frame(self.adv_body)
        sm.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        sm.columnconfigure((1, 3), weight=1)
        self._adv_anchor["sampler"] = ttk.Label(sm, text="Sampler", style="Muted.TLabel")
        self._adv_anchor["sampler"].grid(row=0, column=0, sticky="w")
        self.cb_sampler = ttk.Combobox(sm, textvariable=self.v_sampler, width=8)
        self.cb_sampler.grid(row=0, column=1, sticky="ew", padx=6)
        self._adv_anchor["scheduler"] = ttk.Label(sm, text="Scheduler", style="Muted.TLabel")
        self._adv_anchor["scheduler"].grid(row=0, column=2, sticky="w")
        self.cb_sched = ttk.Combobox(sm, textvariable=self.v_scheduler, width=7)
        self.cb_sched.grid(row=0, column=3, sticky="ew", padx=(6, 0))     # its right edge on the line of the other boxes (user 12.11.)
        self.recipe_widgets += [self.cb_sampler, self.cb_sched]

        self.v_adv_open = tk.BooleanVar(value=False)     # Advanced settings are closed at every start (user 1.11.)
        self.sep_adv = ttk.Frame(self.f_adv, style="Sep.TFrame", height=1)     # a light line above "Advanced settings"
        self.sep_adv.pack(fill="x", pady=(0, 2))
        # the head row (user 20.11., A and C): "Advanced settings" on the left, on the right the model and function these values
        # belong to (_show_adv_context); "Reset" there was removed 25.11. (user): "Load defaults" at the bottom does it
        self.f_adv_head = ttk.Frame(self.f_adv)
        self.f_adv_head.pack(fill="x")
        self.btn_adv = ttk.Button(self.f_adv_head, command=self._toggle_advanced, style="Adv.Link.TButton")     # no inner padding (gui_theme)
        self.btn_adv.pack(side="left")
        self.lbl_adv_ctx = ttk.Label(self.f_adv_head, text="", style="Muted.TLabel")
        self.lbl_adv_ctx.pack(side="right")
        self.lbl_adv_ctx.bind("<Button-1>", lambda e: self._toggle_advanced(), add="+")
        # less room around the closed row (user 12.11., second round: 6 px free above and below the text, measured in the picture at
        # PC A's scale, formerly 10): no inner padding in the button, 2 under the line, no gap under the row
        self.f_adv.pack(fill="x", padx=10, pady=(2, 0))
        self._show_advanced()
        self._show_negative()

        self.f_scale = ttk.Frame(r)
        # the factor as four small switches (user 29.10.): the chosen one is orange; a new document is said in the tooltip
        scale_tip = "How much larger the result is. Upscale opens it as a new document."
        lb = self.lbl_fac = ttk.Label(self.f_scale, text="Upscale factor")
        lb.grid(row=0, column=0, sticky="w")
        Tooltip(lb, scale_tip)
        f_sw = self.f_fac = ttk.Frame(self.f_scale)
        f_sw.grid(row=0, column=1, sticky="e")
        self.rb_scale = {}
        for i, f in enumerate(("1.5", "2", "3", "4")):
            rb = ttk.Radiobutton(f_sw, text=f"{f}x", value=scale_text(f), variable=self.v_fac, style="Small.Toolbutton", command=self._on_factor)
            rb.pack(side="left", padx=(0 if i == 0 else 4, 0))
            Tooltip(rb, scale_tip)
            self.rb_scale[scale_text(f)] = rb
        # the Refine row (user 6.11.; since 22.11. shown only in the function Refine, the factors only in Upscale): the ready-made
        # prompts of the model (Default, Neutral ...); one variable for both rows (v_fac): a factor or "r:<prompt>"
        # the stages of the Upscale workflow in one row under the factors (Fibo, 8.11.): twins of the stage checkboxes (same variables),
        # only in Upscale (22.11.); a line under them like the one above "Advanced settings"
        self.f_stage_row = ttk.Frame(self.f_scale)
        self.f_stage_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.stage_row_cbs = [ttk.Checkbutton(self.f_stage_row, text="Stage", variable=var, command=lambda i=i: self._on_stage(i))
                              for i, var in enumerate(self.stage_vars)]
        self.stage_row_tips = [Tooltip(cb, STAGE_TIP) for cb in self.stage_row_cbs]
        self.sep_stage_row = ttk.Frame(self.f_scale, style="Sep.TFrame", height=1)
        self.sep_stage_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.f_stage_row.grid_remove()
        self.sep_stage_row.grid_remove()
        self._stage_row_live = False    # the row holds the stages of the running workflow (Upscale), not grey copies (Refine)
        refine_tip = "Refine keeps the size and redraws fine detail, as a new layer."
        lb2 = self.lbl_refine = ttk.Label(self.f_scale, text="Refine")
        lb2.grid(row=3, column=0, sticky="w", pady=(4, 0))
        Tooltip(lb2, refine_tip)
        self.f_refine = ttk.Frame(self.f_scale)
        self.f_refine.grid(row=3, column=1, sticky="e", pady=(4, 0))
        lb2.grid_remove()               # never shown since 24.11.: Refine Image has one prompt per model (user: "keine schalter mehr")
        self.f_refine.grid_remove()
        self.rb_refine = {}             # label -> button, built by _update_prompt_choices for the model
        self._rpick = ""                # the Refine button that was chosen ("" = the first one)
        self.f_scale.columnconfigure(0, weight=1)
        # MiniMax H3 Image, Text to image (PLAN 2.0b, user 10.11.): the size row like "Upscale factor", and the tick
        # "Downsize to canvas" under it (off = a new document in the chosen size); only shown for a mode with gen_mp
        self.f_gen = ttk.Frame(r)
        f_mp = ttk.Frame(self.f_gen)      # no "Size" label: the MP buttons start at the left edge (user 13.11.)
        f_mp.grid(row=0, column=0, columnspan=2, sticky="w")
        self.rb_gen = {}
        for i, mp in enumerate(models.GEN_MP_STEPS):
            rb = ttk.Radiobutton(f_mp, text=f"{mp} MP", value=mp, variable=self.v_gen_mp, style="Small.Toolbutton")
            rb.pack(side="left", padx=(0 if i == 0 else 4, 0))
            Tooltip(rb, GEN_MP_TIP)
            self.rb_gen[mp] = rb
        self.cb_downsize = ttk.Checkbutton(self.f_gen, text="Downsize to canvas", variable=self.v_downsize)
        self.cb_downsize.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        Tooltip(self.cb_downsize, DOWNSIZE_TIP)
        self.f_gen.columnconfigure(0, weight=1)
        self.v_scale.trace_add("write", lambda *x: self._sync_fac())     # presets, Reset and a tab change set the factor too
        self.f_detail = ttk.Frame(self.f_post)      # Upscale and Refine: under Advanced settings, at the top of the finishing options (user 28.10.)
        self._slider_row(self.f_detail)
        self._adv_anchor["detail"] = ttk.Label(self.f_detail, text="Mix Source/New", style="Muted.TLabel")
        self._adv_anchor["detail"].grid(row=0, column=0, sticky="w")
        self.w_detail = Slider(self.f_detail, scale=self.ui, from_=0.0, to=1.0, variable=self.v_detail, command=self._on_detail,
                               length=self._px(SLIDER_W))
        self.w_detail.grid(row=0, column=1, sticky="e", padx=8)
        self.lbl_detail = ValueBox(self.f_detail, self.w_detail, self._on_detail, factor=100)
        self.lbl_detail.grid(row=0, column=2, sticky="e")
        Tooltip(self.w_detail, "100 % = only the new image; less mixes in the plain scaled original (tames over-sharp results).")
        self._on_detail()

        # "Image and mask" (Base res., Mask grow, Mask blur) is not shown (the user's choice, 28.10.): each model's
        # function sets these values; the widgets stay, so presets, Reset and the requests work as before
        self.f_img = ttk.LabelFrame(self.adv_body, text="Image and mask")
        tips = {
            "Base res.": "Size (px) the model works at. Higher = more detail, slower.",
            "Context": "How much of the surroundings the model sees around your selection, on each side. More often fits "
                       "the new part better, but it takes longer.",
            "Mask grow": "Grows the model's mask by this many px (mask workflows only).",
            "Mask blur": "Softens the model's mask edge (mask workflows only).",
        }
        self.w_adv = {}
        self.l_adv = {}
        for i, (lbl, var, lo, hi, inc) in enumerate((("Base res.", self.v_res, 256, 2048, 64),
                                                    ("Mask grow", self.v_grow, 0, 128, 2),
                                                    ("Mask blur", self.v_blur, 0, 128, 2))):
            lb = ttk.Label(self.f_img, text=lbl, style="Muted.TLabel")
            lb.grid(row=0, column=i, sticky="w", padx=6)
            sp = self._spin(self.f_img, var, lo, hi, inc, 6)
            sp.grid(row=1, column=i, padx=6, pady=(0, 6))
            self.w_adv[lbl] = sp
            self.l_adv[lbl] = lb
            Tooltip(lb, tips[lbl])
            Tooltip(sp, tips[lbl])
        # Context: a slider like the others (0 to 1 in steps of 0.05, shown as 0 to 100 % in steps of 5 %, user 29.10.),
        # above Edge feather (the user's order, 28.10.); shown for Fill, Remove and Expand only (see
        # _update_availability)
        fc = ttk.Frame(self.f_post)
        self.f_ctx = fc
        fc.pack(fill="x", pady=(2, 0))
        self._slider_row(fc)
        lb = self._adv_anchor["context"] = ttk.Label(fc, text="Context", style="Muted.TLabel")
        lb.grid(row=0, column=0, sticky="w")
        sc = Slider(fc, scale=self.ui, from_=0.0, to=1.0, variable=self.v_context, command=self._on_context,
                    length=self._px(SLIDER_W))
        sc.grid(row=0, column=1, sticky="e", padx=8)
        self.lbl_context = ValueBox(fc, sc, self._on_context, factor=100, step=5)
        self.lbl_context.grid(row=0, column=2, sticky="e")
        self.w_adv["Context"], self.l_adv["Context"] = sc, lb
        for w in (lb, sc):
            Tooltip(w, tips["Context"])
        try:
            self.v_context.trace_add("write", lambda *a: self._show_context())   # also after Reset, presets, a tab change
        except (AttributeError, tk.TclError):
            pass
        self._show_context()
        lm = ttk.Frame(self.f_post)     # the last row of the finishing options (Advanced settings)
        self.f_lm = lm
        lm.pack(fill="x", pady=(2, 0))
        lb = self._adv_anchor["lmask"] = ttk.Label(lm, text="Layer mask", style="Muted.TLabel")
        lb.pack(side="left")
        self.cb_lm = cb_lm = ttk.Combobox(lm, textvariable=self.v_lmask, values=list(LAYER_MASKS.values()), state="readonly", width=18)
        cb_lm.pack(side="left", padx=6)
        cb_lm.bind("<<ComboboxSelected>>", lambda e: self._update_feather_state())
        # beside the menu, with the dark background of a button; shown with Edge feather (see _update_feather_state)
        self.b_fprev = ttk.Button(lm, text="Show feather", style="Small.TButton", command=self.toggle_feather_preview)
        Tooltip(self.b_fprev, "Shows in PhotoCraft (in red) where the result will blend in, with this soft edge. "
                              "Click again, or Generate, to get your selection back.")
        for w in (lb, cb_lm):
            Tooltip(w, "How the result is blended into your picture: soft (soft edge), hard (the selection as it is), none (the whole redrawn area).")

        # "Original size": the picture goes to the model as large as it is (up to a number of megapixels) instead of at about
        # 1 MP, and comes back without being scaled up (user 4.11.); not for Upscale and Refine, which always work at full size
        nf = self.f_native = ttk.Frame(self.f_post)
        nf.pack(fill="x", pady=(2, 0))
        # both texts in the font of the other Advanced settings (Muted, 9 pt), the box only as wide as "x.x" (user 6.11.)
        self.cb_native = ttk.Checkbutton(nf, text="Original size, up to", variable=self.v_native, style="Muted.TCheckbutton")
        self.cb_native.pack(side="left")
        self.lbl_canvas = ttk.Label(nf, text="Use canvas size up to", style="Muted.TLabel")      # Text to image: no switch, it always uses the canvas size
        self.w_native_mp = self._spin(nf, self.v_native_mp, 1, NATIVE_MAX_MP, 0.5, 3)
        self.w_native_mp.pack(side="left", padx=6)
        self.lbl_native = ttk.Label(nf, text="MP", style="Muted.TLabel")
        self.lbl_native.pack(side="left")
        # text and label follow the function (_update_native_text)
        self.tt_native = [Tooltip(w, NATIVE_TIP + NATIVE_TIP_END) for w in (self.cb_native, self.lbl_canvas, self.w_native_mp, self.lbl_native)]
        self.v_native.trace_add("write", lambda *a: self._on_native())
        self._on_native()

        # Generate (Stop during a run), Undo, Redo: under the prompt field and its tip (and Describe) for every function, above the LLM row
        # and the boxes under the prompt (user 16.11., on trial; was above the line over "Prompt"). The tip and Describe are
        # packed right after the grip, so they always land above this row
        bf = self.f_go = ttk.Frame(r)
        bf.pack(fill="x", padx=10, pady=(6, 2), before=self.f_neg)
        # one grid over the full width (user 18.11., decision 1a): Generate, the variants piece and (at times) "Stop batch"
        # on the left, an empty column that takes what is left, Undo and Redo as two squares at the right edge; the widths
        # come from _fit_go_row
        self.b_go = ttk.Button(bf, text="Generate", width=GO_WIDTH_CH, style="Accent.TButton", command=self.generate)
        self.b_go.grid(row=0, column=0, sticky="nsew")
        self.tt_go = Tooltip(self.b_go, GO_TIP)
        # Variants are part of Generate (user 29.10.): a narrow piece on its right, like a split button, grey like the function
        # and model chips (user 20.11., was blue); a click opens the choice 1 to 8. It shows "×n ▾", also at 1
        self.w_variants = ttk.Button(bf, style="Split.Pick.TButton", width=0, command=self._variants_menu)
        self.w_variants.grid(row=0, column=1, sticky="nsew", padx=(self._keep(GO_ROW_GAP_PX), 0))     # the gap of the whole row (user 25.11.)
        Tooltip(self.w_variants, "Variants: how many pictures one Generate makes (1 to 8).")
        self.m_variants = PopMenu(self.root, scale=getattr(self, "ui", 1.0))
        for n in range(1, 9):
            self.m_variants.add_radiobutton(label=str(n), value=n, variable=self.v_variants)
        self.v_variants.trace_add("write", lambda *a: self._show_variants())
        # no Stop button (user 20.11.): Generate turns into a grey "Stop" during a run (_go_stop); while several runs follow one
        # another (variants of Upscale / Refine, a comparison) it says "Stop run" and "Stop batch" shows up beside it
        self.b_stop_all = ttk.Button(bf, text=STOP_BATCH_TEXT, style="Fit.TButton", command=lambda: self._stop_click(True))
        Tooltip(self.b_stop_all, "Stop this run and the variants still to come; in a batch, the rest of this batch. "
                                 "Other batches and queued runs go on.")      # user 23.11. evening: only the running batch
        # while Generate is "Add to queue" (a run is on, the function can wait in the queue; docs/plan/generate-queue.md,
        # Variant 1): a grey "Stop run" of its own between the variants piece and "Stop batch"
        self.b_stop_run = ttk.Button(bf, text=GO_STOP_RUN_TEXT, style="Fit.TButton", command=lambda: self._stop_click(False))
        Tooltip(self.b_stop_run, STOP_RUN_TIP)
        for var in (self.v_mode, self.v_model):         # another function during a run: Add to queue or Stop (_go_follow)
            var.trace_add("write", lambda *a: self._go_follow())
        bf.grid_columnconfigure(GO_COL_GAP, weight=1)
        # Undo and Redo (user 18.11., decision 2a; since 25.11. in the header left of the gear, flat icons like it, a thin
        # vertical line between them and the gear): light while they can be used, grey otherwise (_sync_history_buttons);
        # packed by _pack_history_head once the gear is there
        self.b_undo = ttk.Button(self.f_header, image=self._icon("undo", px=GEAR_HEAD_PX), style="Link.TButton", command=self.undo_edit, takefocus=False)
        self.b_redo = ttk.Button(self.f_header, image=self._icon("redo", px=GEAR_HEAD_PX), style="Link.TButton", command=self.redo_edit, takefocus=False)
        self.sep_history = ttk.Frame(self.f_header, style="Sep.TFrame", width=1)
        self.tt_redo = Tooltip(self.b_redo, HISTORY_REDO_TIP)
        self.tt_undo = Tooltip(self.b_undo, HISTORY_UNDO_TIP)
        # a grey ttk button calls no command: a click on it during a run says why there (user 25.11., "Klick + Tooltip")
        self.b_undo.bind("<ButtonRelease-1>", lambda e: self._history_grey_click(e, "undo"), add="+")
        self.b_redo.bind("<ButtonRelease-1>", lambda e: self._history_grey_click(e, "redo"), add="+")
        self._last_step = None              # None, "undo" or "redo": which of the two was used last (decides the blue one)
        self._show_variants()
        self._sync_history_buttons()
        bf.bind("<Configure>", lambda e: self._fit_go_row(), add="+")

        # one bar for the whole run (prompt, then image) with the current step written next to it
        self.v_pl = tk.StringVar(value="")
        # no line above the progress line any more (user 25.11.: "could be deleted, so the plugin has less height")
        row = self.f_pl_row = ttk.Frame(r)
        row.pack(fill="x", padx=10, pady=(PL_GAP_OPEN if self.v_adv_open.get() else PL_GAP_CLOSED, 0))     # under closed Advanced settings less (_show_advanced, user 25.11.)
        top = self.f_pl_top = ttk.Frame(row)                  # above the bar, text on the left: shown only while it has text
        self.lbl_pl = ttk.Label(top, textvariable=self.v_pl, style="Muted.TLabel", anchor="w", justify="left")    # the step, or the green word "Done"
        self.lbl_pl.pack(side="left")
        self.v_pl_rest = tk.StringVar(value="")
        self.lbl_pl_rest = ttk.Label(top, textvariable=self.v_pl_rest, style="DoneRest.TLabel", anchor="w")      # after "Done": seed, layers, time
        self.lbl_pl_rest.pack(side="left")
        self.pb = ttk.Progressbar(row, mode="determinate", maximum=1.0, style="Thin.Horizontal.TProgressbar")   # half as high (user 16.11.)
        self.pb.pack(fill="x", pady=(2, 0))
        self._show_pl_line()
        self._bar_value = 0.0
        # the live preview (T3a, user 29.10.): only while a run sends frames, above the status line (gui_run.py _show_preview)
        self.f_preview = ttk.Frame(self.root)
        self.lbl_preview = ttk.Label(self.f_preview, anchor="center")
        self.lbl_preview.pack(fill="x")
        st = self.f_status = ttk.Frame(self.root)
        st.pack(fill="x", padx=10, pady=(4, 0))
        # a clean red circle with a white "!" (user 12.11.), drawn at the real pixel size like the other icons
        self._err_img = icons.photo(self.root, "", "", self._px(ERR_BADGE_PX), image=icons.error_badge(self._px(ERR_BADGE_PX)))
        self.lbl_err = ttk.Label(st, image=self._err_img, anchor="center")
        self.lbl_status = ttk.Label(st, textvariable=self.v_status, wraplength=self._px(MIN_W - 20), justify="left")     # as wide as the lines above (user 13.11.; was 20 px short)
        self.lbl_status.pack(side="left", fill="x", expand=True)
        st.bind("<Configure>", self._fit_status_wrap, add="+")
        for w in (self.lbl_status, self.lbl_err):      # a click on an error message clears it (user 12.11.); right-click Copy stays
            w.bind("<Button-1>", self._dismiss_error, add="+")
        # an empty status line takes no room (user 8.11., decision D: b): the frame stays packed as the anchor the preview and the
        # tabs are placed before, but 1 px high and without its gap; it opens again with the next message (_show_status_line)
        self.v_status.trace_add("write", lambda *a: self._show_status_line())
        self._show_status_line()
        foot = self.f_foot = ttk.Frame(self.root)
        foot.pack(fill="x", side="bottom", padx=10, pady=6)
        self.lbl_conn, self.lbl_dot = conn_status(foot, dot_first=True)        # "● ComfyUI": green = connected, red = not (the dot in front, user 6.11.)
        self.lbl_conn.pack(side="left")
        # Refresh = a flat circle arrow beside the dot (user 30.10.); the page resets are "Save settings" / "Load defaults" (25.11.)
        b_refresh = self.b_refresh = ttk.Button(foot, image=self._icon("refresh", px=GEAR_PX), style="Link.TButton",
                                                command=self.refresh)
        b_refresh.pack(side="left", padx=FOOT_REFRESH_PADX)
        Tooltip(b_refresh, "Refresh: reads PhotoCraft's and ComfyUI's state again: connection, installed LoRAs, samplers, text models, workflows.")
        # Live preview sits beside the refresh arrow (user 30.10.); greyed out while the model's preview decoder is missing
        self.cb_live = ttk.Checkbutton(foot, text="Live preview", variable=self.v_live)
        self.cb_live.pack(side="left", padx=FOOT_RESET_PADX)
        self.tt_live = Tooltip(self.cb_live, LIVE_TIP)
        # the right end of the footer (user 4.11.): the menu at the far right, left of it the scissors and the queue window
        # (user 24.11. evening: "queue gegen history tauschen", the last runs went into the menu; the menu is three dots, no
        # hamburger any more); 90 % of the usual small icon. Visually: queue, scissors, three dots.
        self.b_menu = ttk.Button(foot, image=self._icon("dots", px=FOOT_BTN_PX), style="Link.TButton", command=self._footer_menu)
        self.b_menu.pack(side="right", padx=(6, 0))
        Tooltip(self.b_menu, "More: save or copy the picture of PhotoCraft, batch processing, the last runs, reset the page.")
        self.b_cut = ttk.Button(foot, image=self._icon("cut", px=FOOT_BTN_PX), style="Link.TButton", command=self._cutout_menu)
        self.b_cut.pack(side="right", padx=(6, 0))     # the scissors: left of the clock (user 5.11.)
        self.tt_cut = Tooltip(self.b_cut, CUTOUT_TIP)
        self.b_queue = ttk.Button(foot, image=self._icon("list", px=FOOT_BTN_PX), style="Link.TButton", command=self._queue_toggle)
        self.b_queue.pack(side="right", padx=(6, 0))
        Tooltip(self.b_queue, "Queue (Q): every run at ComfyUI, yours and others'. A second click closes it.")
        self._build_settings(foot)      # the gear sits in the header (ui_settings.py)

        for cb in (self.cb_lm, self.cb_sampler, self.cb_sched):
            self._open_on_click(cb)         # the list opens on a click anywhere in the box, not only on the arrow
        self._fit_job = None
        self.root.bind("<Configure>", self._on_content_size, add="+")      # the window follows its content: nothing hangs off the bottom
        self.root.bind("<Button-1>", self._lora_outside, add="+")
        self.root.bind("<Control-Return>", lambda e: (self.generate(), "break")[1])
        self.root.bind("<Control-Alt-Return>", lambda e: (self.stop(), "break")[1])      # interrupts a run (user 30.10.)
        self.root.bind("<Escape>", self._escape_key)      # closes the queue or the settings window, never stops a run (user 20.11.)
        for key in ("<KeyPress-q>", "<KeyPress-Q>"):            # Q toggles the queue (user 13.11.), not while typing in a field
            self.root.bind(key, self._queue_key, add="+")
        self.root.bind("<Control-s>", lambda e: (self.save_image(), "break")[1])      # Save image (the prompt field has no Ctrl+S of its own)
        self.root.bind("<Control-S>", lambda e: (self.save_image(), "break")[1])

    def toggle_minimize(self):
        """The button in the header: minimised, the window shrinks to the header (title bar, header, the button); a second
        click brings everything back as it was."""
        self._minimized = not self._minimized
        self.b_min.configure(image=self._icon("chevron-down" if self._minimized else "minimize", px=SMALL_ICON_PX))
        self.tt_min.text = ("Show PxC again." if self._minimized else
                            "Minimise: only this header stays. Click again to show PxC.")
        self.f_header.pack_configure(pady=(8, 8 if self._minimized else 0))     # alone, the header gets room below too
        self._mini_bar_sync()
        if self._minimized:
            # the live preview goes too (user 24.11.: it stayed under the header); its frame is kept for the way back
            for w in (self.f_tabs, self.lbl_empty, self.f_scrollbox, self.f_preview, self.f_status, self.f_foot):
                w.pack_forget()
            self._fit_height()
        else:
            self.f_foot.pack(fill="x", side="bottom", padx=10, pady=6)
            self.f_status.pack(fill="x", padx=10, pady=(4, 0))
            if getattr(self, "_preview_photo", None) is not None:      # a run is on: its preview comes back above the status
                self.f_preview.pack(fill="x", padx=10, pady=(6, 0), before=self.f_status)
            self._show_status_line()
            self._apply_start_state()

    def copy_canvas(self):
        """The copy button in the header: what is visible in PhotoCraft's active picture goes onto the Windows clipboard as
        one image (PNG with transparency, and DIB). Runs in the worker like undo (PhotoCraft is busy for a moment)."""
        if (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        self._status("Copying the canvas…")
        other = self._other_photocraft()

        def work():
            try:
                ok = clipboard.write_image(self.bridge.canvas_image())
                self.events.put(self._note_done("Canvas copied to the clipboard.", other) if ok else
                                ("note-error", "The clipboard could not be set. Try again."))
            except (BridgeError, PhotoCraftError) as e:
                self.events.put(("note-error", f"Error: {e}"))
            except Exception as e:
                self.events.put(("note-error", f"Unexpected error: {type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    # a second PhotoCraft (a PSD opened by a double click) has no control channel: the plugin reads and writes only the one
    # it sits on (user 16.11., bug: Ctrl+S saved the picture of the other PhotoCraft; choice 1: link to the right one and warn)
    OTHER_PC_HINT = ("Another PhotoCraft is open. PxC only works with the PhotoCraft window it sits on: "
                     "open your images there (File > Open).")  # approved by the user 16.11.

    def _other_photocraft(self) -> bool:
        """Is another PhotoCraft open besides the one with the control channel? False when it cannot tell."""
        return bool(winlink.others_open(api=self._x11()))

    def _note_done(self, text: str, other: bool) -> tuple[str, str]:
        """The status event after Copy canvas or Save image: with another PhotoCraft open, red and with the hint."""
        return ("note-error", f"{text} {self.OTHER_PC_HINT}") if other else ("note", text)

    def _active_doc_name(self) -> str:
        """The name of PhotoCraft's active document, "" when it cannot be read (worker thread)."""
        try:
            sess = self.bridge.pc.session()
            return str(sess["documents"][sess["active"]]["name"])
        except Exception:
            return ""

    SAVE_IMAGE_TIP = ("Saves the visible image to your save folder. Folder, file name and format are set in the settings "
                      "under Save image.")  # approved by the user 12.11.
    COPY_CANVAS_TIP = "Copies the visible image to the clipboard."      # the user's text, 21.11.
    HISTORY_TIP = "Last runs: click one to load all its settings with a new seed. Nothing starts by itself."

    def _footer_menu(self):
        """The hamburger at the right end of the footer: a small menu above it (Save image, Copy canvas, the two batch sources,
        the queue window, gui_batch.py and gui_queuewin.py, History). The two resets of the page are "Save settings" and "Load
        defaults" at the bottom of the Advanced settings since 25.11. (user)."""
        px = SMALL_ICON_PX
        m = self._footer_popup = PopMenu(self.root, scale=getattr(self, "ui", 1.0))
        rows = [("Save image (Ctrl+S)", "save", self.save_image, self.SAVE_IMAGE_TIP, False),
                ("Copy canvas", "copy", self.copy_canvas, self.COPY_CANVAS_TIP, False),
                ("Batch: open images", "images", lambda: self.open_batch(jobqueue.SOURCE_OPEN), None, False),
                ("Batch: folder…", "folder", lambda: self.open_batch(jobqueue.SOURCE_FOLDER), None, False),
                # the last runs (PLAN point 13, user 30.10.), in the menu since 24.11. evening (the queue took their place outside)
                ("History", "clock", lambda: self._history_menu(), self.HISTORY_TIP, False)]
        # the two page resets went to the bottom of the Advanced settings as "Save settings" / "Load defaults" (user 25.11.)
        for row in rows:
            if row is None:
                m.add_separator()
                continue
            label, kind, cmd, tip, off = row
            m.add_command(label=label, icon=self._icon(kind, px=px)[0], icon_hot=self._icon(kind, ON_ACCENT, px=px)[0], command=cmd,  # white on the blue hover (user 12.11.)
                          tip=tip, state="disabled" if off else "normal")
        m.tk_popup(0, 0, above_w=self.b_menu)

    def save_image(self):
        """Save image (hamburger menu, Ctrl+S): what is visible in PhotoCraft's active picture as one file in the save folder
        (settings: folder, format, name pattern; savefile.py). The file is named after the document; function and seed only when
        the document is what the last run of this session made (self._last_result: its mode, seed and the document's name then);
        else they stay empty. Runs in the worker like Copy canvas."""
        if (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        self._status("Saving the image…")
        other = self._other_photocraft()

        def work():
            try:
                img = self.bridge.canvas_image()
                doc = self._active_doc_name()
                last = getattr(self, "_last_result", None) or {}
                mine = bool(doc) and doc == last.get("doc")
                path = savefile.save_image(img, name=Path(doc).stem if doc else "", seed=last.get("seed") if mine else None,
                                           function=savefile.function_label(last.get("mode")) if mine else "")
                self.events.put(self._note_done(f"Saved: {path.name}", other))
            except (BridgeError, PhotoCraftError) as e:
                self.events.put(("note-error", f"Error: {e}"))
            except OSError as e:
                self.events.put(("note-error", f"The image could not be saved: {e}"))
            except Exception as e:
                self.events.put(("note-error", f"Unexpected error: {type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _x11(self):
        """The X11 link (x11link.X11Api) where the plugin runs under X11, else None (Windows uses winlink's own api)."""
        return None if winlink.available() else x11link.api()

    def _on_top(self):
        x11 = self._x11()
        if not winlink.available() and x11 is None:
            self.root.attributes("-topmost", bool(self.v_top.get()))
            return
        # Windows: owned window instead, above PhotoCraft only. X11: "always on top" until the link holds (_try_link), then
        # transient for PhotoCraft (user 15.11.: it minimizes with PhotoCraft and leaves other programs alone)
        self.root.attributes("-topmost", bool(self.v_top.get()) and x11 is not None)
        if getattr(self, "_link_job", None):
            self.root.after_cancel(self._link_job)
            self._link_job = None
        self._link_tries = 0
        if self.v_top.get():
            # not now: Tk's real window exists only once the event loop runs. After that the link is checked again
            # and again (watchdog): PhotoCraft's window may appear later, or Tk may rebuild its own.
            self._link_job = self.root.after(300, self._try_link)
        else:
            winlink.unlink(self.root, api=x11)
            self._reveal("stay with PhotoCraft is off")

    def _hide_until_placed(self):
        """The window stays invisible (alpha 0, Tk's window exists, so it can be tied to PhotoCraft) until the first link has
        put it in its place; before, it showed for a moment in the top left corner of the screen and then jumped there (user
        22.11.). Shown at the latest after REVEAL_MS, also when PhotoCraft's window is not found. The window is made invisible
        right where Tk creates it (__init__): the layout passes of the start already put it on the screen at 0,0."""
        self._revealed = False
        if not self.v_top.get() or not (winlink.available() or self._x11() is not None):
            self._reveal("not tied to PhotoCraft")
            return
        self.root.after(REVEAL_MS, lambda: self._reveal("PhotoCraft not linked within 3 s"))

    def _reveal(self, why: str):
        if getattr(self, "_revealed", True):
            return
        self._revealed = True
        try:
            self.root.update_idletasks()        # the new place is applied before the window becomes visible
            self.root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self._slog(f"shown ({why})")

    # ---------- start log (startlog.py, user 22.11.) ----------

    def _start_log_begin(self):
        try:
            self._startlog = startlog.StartLog(cfgmod.EXCHANGE_DIR / startlog.LOG_NAME)
        except Exception:
            self._startlog = None
            return
        self._slog(f"saved position={self.state.get('win_pos')} used={getattr(self, '_placed', False)} "
                   f"stay with PhotoCraft={bool(self.v_top.get())} hidden until placed={not getattr(self, '_revealed', True)}")
        self.root.after(startlog.TICK_MS, self._start_log_tick)

    def _slog(self, text: str):
        lg = getattr(self, "_startlog", None)
        if lg is not None and lg.active():
            lg.note(text)

    def _start_log_tick(self):
        lg = getattr(self, "_startlog", None)
        if lg is None:
            return
        if not lg.active():
            lg.note("end of the start log")
            self._startlog = None
            return
        if winlink.available():
            lg.state(winlink.window_state(self.root))
        self.root.after(startlog.TICK_MS, self._start_log_tick)

    def _place_window(self):
        """The window starts where it was last (saved in the state), if that is still on a screen. Otherwise it is placed
        at the first link: top left inside PhotoCraft, under its menu bar (winlink.first_position)."""
        self._placed = False
        self._win_pos = None
        pos = self.state.get("win_pos")
        try:
            x, y = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            return
        if winlink.on_screen(x + self._px(40), y + self._px(10)) is False:    # the title bar must be reachable
            return
        self.root.geometry(f"+{x}+{y}")
        self._win_pos = (x, y)
        self._placed = True
        self._checked_band = False

    def _place_at_owner(self):
        """Called once PhotoCraft's window is known: a first start goes to its top left corner; a saved position that
        lies in its menu bar moves just below it."""
        rect = winlink.owner_rect(api=self._x11())
        if rect is None:
            return
        w = self.root.winfo_width()
        if not getattr(self, "_placed", True):
            x, y = winlink.first_position(rect, w, self.ui)
        elif not getattr(self, "_checked_band", True) and self._win_pos:
            x, y = winlink.below_menu_bar(self._win_pos, w, rect, self.ui)
        else:
            return
        self._placed, self._checked_band = True, True
        if (x, y) != self._win_pos:
            self.root.geometry(f"+{x}+{y}")
            self._win_pos = (x, y)
            self._slog(f"moved to {x},{y}")

    def _drag_start(self, e):
        self._drag_from = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        """Moves the title-bar-less window with the mouse; the top edge stays on the screen so the header can be grabbed again."""
        try:
            ox, oy = self._drag_from
            top = self.root.winfo_vrooty()
            self.root.geometry(f"+{e.x_root - ox}+{max(top, e.y_root - oy)}")
        except (AttributeError, tk.TclError):
            pass

    def _remember_pos(self, e=None):
        """Keeps the window's place for the next start (saved with the state)."""
        if e is not None and e.widget is not self.root:
            return
        try:
            if self.root.state() != "normal":
                return
            m = re.match(r"\d+x\d+([+-]-?\d+)([+-]-?\d+)", self.root.geometry())
        except tk.TclError:
            return
        if m:
            x, y = int(m.group(1).replace("+", "")), int(m.group(2).replace("+", ""))
            if x > -10000 and y > -10000:       # a minimized window reports -32000
                self._win_pos = (x, y)

    def _yield_popups(self):
        """PhotoCraft draws its menus inside its own window, so this window cannot be put below them. Instead (Windows):
        a click in PhotoCraft's menu bar hides this window while the menu is in use; it returns with the next click
        outside the menu bar, Escape or when the pointer leaves PhotoCraft (winlink.menu_step)."""
        self._popup_job = None
        x11 = self._x11()
        if self.v_top.get() and (winlink.available() or x11 is not None):
            self._menu_state = winlink.guard_menus(self.root, getattr(self, "_menu_state", {}), self.ui, api=x11)
            self._popup_job = self.root.after(80, self._yield_popups)

    def _try_link(self):
        self._link_job = None
        if not self.v_top.get():
            return
        x11 = self._x11()
        if winlink.link(self.root, api=x11):
            if x11 is not None and self.root.attributes("-topmost"):
                self.root.attributes("-topmost", False)      # tied to PhotoCraft now: above it only
            if not getattr(self, "_pc_seen", False):
                self._slog(f"linked to PhotoCraft (try {getattr(self, '_link_tries', 0) + 1})")
            self._place_at_owner()
            self._reveal("placed at PhotoCraft")
            if x11 is None:          # Windows: tied, but still under PhotoCraft (user 22.11.): put it above
                lifted = winlink.lift_above_owner(self.root)
                if lifted:
                    self._slog(lifted)
            self._link_tries = 0
            self._pc_seen, self._pc_gone = True, 0
            if not getattr(self, "_popup_job", None):
                self._popup_job = self.root.after(300, self._yield_popups)
        else:
            if getattr(self, "_pc_seen", False) and winlink.owner_present(api=x11) is False:
                self._pc_gone = getattr(self, "_pc_gone", 0) + 1
                if self._pc_gone >= 2:       # PhotoCraft was closed: this window closes with it
                    self._quit(ask=False)    # no question, the window's runs stop (user 25.11.)
                    return
            self._link_tries = getattr(self, "_link_tries", 0) + 1
            if self._link_tries == 20:
                self.v_status.set("PhotoCraft window not found - this window stays free until it appears")
        self._link_job = self.root.after(1500, self._try_link)

    def _dialog(self, fn, **kw):
        """A Windows dialog (file picker ...) owned by this window. The link watchdog and the menu guard pause while it is
        open: re-linking this owned window under the dialog made Tk redraw it (the window showed twice, garbled)."""
        for name in ("_link_job", "_popup_job"):
            job = getattr(self, name, None)
            if job:
                self.root.after_cancel(job)
                setattr(self, name, None)
        try:
            return fn(parent=self.root, **kw)
        finally:
            if self.v_top.get() and winlink.available() and not getattr(self, "_closing", False):
                self._link_job = self.root.after(300, self._try_link)    # links again and restarts the menu guard

    def _on_destroy(self, e):
        if e.widget is not self.root or getattr(self, "_closing", False):
            return
        self._closing = True   # PhotoCraft closed: Windows destroys owned windows without asking
        try:
            self._save_state(self._request())
        except Exception:
            pass
        self._stop_own_runs()      # PhotoCraft is gone: the window's runs stop at ComfyUI too (user 25.11.)
        if not self._batch_shutdown():
            self.bridge.cancel()

    def _quit(self, ask: bool = True):
        """Closes PxC. With a run of the window on, closing it by hand asks first (user 25.11., choice "Ask when closing
        PxC"): Yes stops it at ComfyUI, No lets ComfyUI finish it, Cancel keeps PxC open. ask=False (PhotoCraft is gone):
        the window's runs stop without a question."""
        if getattr(self, "_closing", False):
            return
        stop = not ask
        if ask and self._own_runs_on():
            answer = self._dialog(messagebox.askyesnocancel, title=WINDOW_TITLE, message=CLOSE_RUN_ASK, icon="warning")
            if answer is None:
                return
            stop = bool(answer)
        self._closing = True
        try:
            self._save_state(self._request())
        except Exception:
            pass
        if stop:
            self._stop_own_runs()
        if not self._batch_shutdown():      # a batch job at ComfyUI is not stopped: the next start picks its result up
            self.bridge.cancel()
        if self.bridge.feather_shown and not (self.worker and self.worker.is_alive()):
            try:    # the user's selection comes back before the window goes
                self.bridge.hide_feather()
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_gui(cfg: dict) -> int:
    try:
        App(cfg).run()
    except tk.TclError as e:
        print(f"Can't open the window ({e}). Is the `tk` package installed?")
        return 1
    return 0
