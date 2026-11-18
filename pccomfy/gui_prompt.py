"""The prompt field: editor keys, hints, ready-made prompts, enhance and negative boxes. (moved out of gui.py unchanged; see PLAN.md, phase 0)."""
from __future__ import annotations

import random

from . import custom_prompts, hostos, manifest, spacing, styles, workflows
from .popmenu import PopMenu, place_right_of
from .refslots import BBOX_TIP, MULTI_MODE, SCRIBBLE_MODE, TAB_MODE, retag
from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401

REFINE_DEFAULT_TIP = "Refine with the default prompt: same size, as a new layer."


def put_in_front(t, text: str) -> None:
    """A generated text (Describe, the LLM button) goes in front of the prompt, followed by a line break; an empty prompt
    gets just the text (user 3.11.). One undo step: Ctrl+Z in the field takes it away."""
    t.edit_separator()
    rest = t.get("1.0", "end").strip()
    t.delete("1.0", "end")
    t.insert("1.0", text + ("\n" + rest if rest else ""))
    t.edit_separator()


class PromptMixin:
    def _editor_keys(self, t):
        """Text-editor keys in a prompt field: Ctrl+Left/Right jump by word (Shift selects), Ctrl+Backspace/Delete delete a
        word, Ctrl+A selects all, Ctrl+Z / Ctrl+Y undo and redo. Ctrl+Enter generates and writes no line break."""
        def cursor(extend, idx):
            proc = "tk::TextKeySelect" if extend else "tk::TextSetCursor"
            try:
                t.tk.call(proc, str(t), idx)
            except tk.TclError:
                t.mark_set("insert", idx)
            t.see("insert")
            return "break"

        def jump(direction, extend):
            def h(_e=None):
                if direction < 0:
                    n = word_left(t.get("1.0", "insert"))
                    return cursor(extend, f"insert-{n}c")
                n = word_right(t.get("insert", "end-1c"))
                return cursor(extend, f"insert+{n}c")
            return h

        def kill(direction):
            def h(_e=None):
                if t.tag_ranges("sel"):
                    t.delete("sel.first", "sel.last")
                elif direction < 0:
                    t.delete(f"insert-{word_left(t.get('1.0', 'insert'))}c", "insert")
                else:
                    t.delete("insert", f"insert+{word_right(t.get('insert', 'end-1c'))}c")
                return "break"
            return h

        def select_all(_e=None):
            t.tag_add("sel", "1.0", "end-1c")
            t.mark_set("insert", "end-1c")
            return "break"

        def history(redo):
            def h(_e=None):
                try:
                    (t.edit_redo if redo else t.edit_undo)()
                except tk.TclError:
                    pass
                return "break"
            return h

        def generate(_e=None):
            self.generate()
            return "break"          # the Text's own Return binding must not add a line break

        for seq, fn in (("<Control-Left>", jump(-1, False)), ("<Control-Right>", jump(1, False)),
                        ("<Control-Shift-Left>", jump(-1, True)), ("<Control-Shift-Right>", jump(1, True)),
                        ("<Control-BackSpace>", kill(-1)), ("<Control-Delete>", kill(1)),
                        ("<Control-a>", select_all), ("<Control-A>", select_all),
                        ("<Control-z>", history(False)), ("<Control-Z>", history(True)), ("<Control-y>", history(True)),
                        ("<Control-Return>", generate), ("<Control-KP_Enter>", generate)):
            t.bind(seq, fn)

    def _show_enhance_box(self, on: bool):
        """The "Enhance my Prompt with LLM" row (with the copy button): not in Expand, Remove, Refine and Upscale (NO_LLM_MODES). It sits directly under the negative
        prompt, above the Upscale factor and the LoRA switches (user 30.10.)."""
        shown = bool(self.f_enh.winfo_manager())
        if on and not shown:
            self.f_enh.pack(fill="x", padx=10, pady=(6, 0), after=self.f_neg)
        elif not on and shown:
            self.f_enh.pack_forget()
        self._update_reroll()           # "Reroll prompt" follows the row and the Enhance tick (user 18.11.)
        if on != shown and getattr(self, "_sized", False):
            self._fit_height()

    def _below_prompt(self):
        """What the next box under the prompt goes after: the LLM row when it is shown, else the negative prompt."""
        return self.f_enh if self.f_enh.winfo_manager() else self.f_neg

    def _prompt_text(self) -> str:
        """The prompt to save: in Remove object the field is empty, the user's own text is kept aside."""
        if str(self.t_prompt.cget("state")) == "disabled":
            return getattr(self, "_prompt_kept", "")
        return self.t_prompt.get("1.0", "end").strip()

    def _fit_grip(self, _e=None):
        """The grip is as wide as the text field: its right margin is the one of the field row plus the icon column (and its
        2 px gap). The side margin is read from the field row, which is packed with the same one (the window scales pads)."""
        try:
            w = self.f_picons.winfo_width()
            side = self.f_prompt.pack_info()["padx"]
            side = side if isinstance(side, int) else int(side[0])
            gap = self.f_picons.pack_info()["padx"]       # the real gap left of the column (the window scales pads once already)
            gap = gap if isinstance(gap, int) else int(gap[0])
            right = side + (w + gap if w > 1 else 0)
            cur = self.grip.pack_info()["padx"]
            if (side, right) != ((cur, cur) if isinstance(cur, int) else tuple(int(v) for v in cur)):
                self.grip.pack_configure(padx=(spacing.Keep(side), spacing.Keep(right)))   # already pixels: _keep would scale them again
        except (tk.TclError, AttributeError, TypeError, ValueError, KeyError):
            pass

    def _grip_drag(self, grip, t):
        """The strip under the prompt field: drag it to change the field's height (in lines)."""
        st: dict = {}

        def line_h():
            try:
                return max(8, int(t.tk.call("font", "metrics", t.cget("font"), "-linespace")))
            except Exception:
                return self._px(16)

        def press(e):
            st.update(y=e.y_root, h=self._prompt_lines(), lh=line_h())

        def move(e):
            if "y" not in st:
                return
            n = max(3, min(30, st["h"] + round((e.y_root - st["y"]) / st["lh"])))
            if n != self._prompt_lines():
                t.configure(height=n)
                self._fit_height()
        grip.bind("<ButtonPress-1>", press)
        grip.bind("<B1-Motion>", move)

    def _prompt_lines(self) -> int:
        try:
            return int(self.t_prompt.cget("height"))
        except (TypeError, ValueError, tk.TclError):
            return PROMPT_LINES

    def _update_prompt_hint(self):
        """The prompt field turns orange with a hint under it: Expand (an empty prompt often fills best), and the modes whose
        prompt starts with the workflow's own text (Upscale / Refine: describe the image in front of it)."""
        mode = self.v_mode.get()
        m = self._model()
        spec = m.modes.get(mode) if m else None
        text = (spec.prompt_tip if spec and spec.prompt_tip else "") or (EXPAND_HINT if mode == "outpaint" else "")
        if mode == "multi_edit" and getattr(self, "v_bbox", None) is not None and self._bbox_on():
            text = BBOX_TIP              # BBOX ticked: its tip instead of the Multi Image Edit one, only here (user 3.11.)
        if mode == "scribble" and getattr(self, "_ref_scribble", None) is not None and self._ref_scribble():
            text = models.REF_SCRIBBLE_TIP     # Reference at scribble: the slot and the object to type (user 15.11.)
        if mode in ("sketch", "scribble") and self._written_active():
            text = models.WRITTEN_TIP    # a written prompt from the history: no upsampler (user 10.11.)
        if "{tag}" in text:      # Multi Image Edit: the example names the first reference the way this model does
            text = text.replace("{tag}", m.tag_style.format(n=2, i=1) if m and m.tag_style else "the reference image")
        on = bool(text)
        self._hint_text = text
        self._update_llm_button()
        self._update_styles_button()
        self.t_prompt.configure(highlightbackground=ACCENT if on else "#454545", highlightthickness=2 if on else 1)
        if on:
            self.lbl_hint.configure(text=text)
            self.f_hint.pack(fill="x", padx=10, after=self.grip)      # the text with its info icon (gui.py)
        else:
            self.f_hint.pack_forget()
        b = getattr(self, "b_describe", None)
        if b is not None:
            if self._needs_description():
                b.pack(anchor="w", padx=10, pady=(4, 0), after=self.f_hint)
            else:
                b.pack_forget()

    def _needs_description(self) -> bool:
        """Krea 2 / MOSS Expand: the model needs a prompt (an empty one fills the margin with unrelated things)."""
        m = self._model()
        spec = m.modes.get(self.v_mode.get()) if m else None
        return bool(spec and spec.describe)

    def describe_scene(self):
        """The Describe button: Qwen 3.5 9B describes the surroundings of the picture in PhotoCraft (Bridge.describe_scene);
        the text replaces the field's content in one undo step (Ctrl+Z in the field brings the old text back)."""
        import threading
        if getattr(self, "_describing", False) or (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        self._describing = True
        self.b_describe.configure(state="disabled")
        self.b_stop.configure(state="normal")          # Cancel stops the text model too (user 2.11.)
        self._status("Describing the surroundings …")
        box: dict = {}

        def work():
            try:
                box["text"] = self.bridge.describe_scene()
            except Cancelled:
                box["error"] = "Cancelled."
            except Exception as e:   # PhotoCraft or ComfyUI not running, no text model ...
                box["error"] = str(e)

        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box and "error" not in box:
                self.root.after(200, check)
                return
            self._describing = False
            self.b_describe.configure(state="normal")
            self.b_stop.configure(state="disabled")
            if "error" in box:
                self._status(box["error"] if box["error"] == "Cancelled." else "Describe failed: " + box["error"], error=box["error"] != "Cancelled.")
                return
            put_in_front(self.t_prompt, box["text"])
            self._status("Described. Edit the text as you like, then Generate.")
        self.root.after(200, check)

    def _llm_file(self) -> str:
        """The text model file the LLM button uses: the first of the model's describe writers that ComfyUI lists ("" = none)."""
        m = self._model()
        if m is None or self.inv is None:
            return ""
        for name in manifest.describe_writers(m.key):
            found = self.inv.found(name)
            if found:
                return found
        return ""

    def _llm_wanted(self) -> bool:
        """Where Describe Canvas is shown (user 10.11. evening, P4): Text to image, and Refine while the picture is not made in
        tiles (every tile gets the whole prompt, so a description puts its objects into every tile). Never in Upscale (user
        12.11. after the P8 round, docs/tests/p8-upscale-prompt-ergebnis.md: a description helped nowhere there). Hidden in
        every other function."""
        mode = self.v_mode.get()
        if mode == "txt2img":
            return True
        return mode == "refine" and not self._tiles_on()

    def _tiles_on(self) -> bool:
        """The selected workflow makes the picture in tiles: it has a tile split (SplitImageToTileList) that is not part of a
        stage switched off. Flux 3 and Flux 2 Upscale always tile; Fibo has the stage "Tiles". (Fibo also tiles by itself
        above 3 MP; the window does not know the picture's size before the run, so that case is not counted.)"""
        try:
            templates = self._wf_templates()
        except Exception:
            return False
        split = {nid for t in templates for nid, node in t.items()
                 if isinstance(node, dict) and node.get("class_type") == "SplitImageToTileList"}
        if not split:
            return False
        stages = self._stages()
        for i, st in enumerate(stages):
            if "tile" in str(st.get("label", "")).lower() and i < len(getattr(self, "stage_vars", ())):
                return bool(self.stage_vars[i].get())
        return True

    def _update_llm_button(self):
        """The LLM button is grey while no function is chosen, the prompt is switched off (Remove object) or the model's text
        model is missing; the tooltip says which file."""
        b = getattr(self, "b_llm", None)
        if b is None:
            return
        want = self._llm_wanted()
        if want != getattr(self, "_llm_shown", True):
            if want:
                b.pack(side="top", pady=(0, self._px(2)), after=self.b_save)      # below Save, above the bin (12.11.)
            else:
                b.pack_forget()
            self._llm_shown = want
        m = self._model()
        off = str(self.t_prompt.cget("state")) == "disabled"
        if m is None or off:
            b.configure(state="disabled")
            self.tt_llm.text = LLM_TIP
        elif self.inv is not None and not self._llm_file():
            b.configure(state="disabled")
            self.tt_llm.text = LLM_TIP + f"\n\nNeeds {manifest.describe_writers(m.key)[0]}: download it in the settings (gear)."
        else:
            b.configure(state="normal")
            self.tt_llm.text = LLM_TIP

    def describe_canvas(self):
        """The LLM button: the model's text model describes the picture in PhotoCraft (Bridge.describe_canvas); the text goes
        in front of the prompt, followed by a line break, in one undo step (Ctrl+Z in the field takes it away)."""
        import threading
        if getattr(self, "_describing", False) or (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        clip = self._llm_file()
        self._describing = True
        self.b_llm.configure(state="disabled")
        self.b_stop.configure(state="normal")          # Cancel stops the text model too (user 2.11.)
        self._status("Describing the picture …")
        box: dict = {}

        def work():
            try:
                box["text"] = self.bridge.describe_canvas(clip)
            except Cancelled:
                box["error"] = "Cancelled."
            except Exception as e:   # PhotoCraft or ComfyUI not running, no text model ...
                box["error"] = str(e)

        threading.Thread(target=work, daemon=True).start()

        def check():
            if "text" not in box and "error" not in box:
                self.root.after(200, check)
                return
            self._describing = False
            self._update_llm_button()
            self.b_stop.configure(state="disabled")
            if "error" in box:
                self._status(box["error"] if box["error"] == "Cancelled." else "Describe failed: " + box["error"], error=box["error"] != "Cancelled.")
                return
            put_in_front(self.t_prompt, box["text"])
            self._status("Described. The text is at the start of the prompt.")
        self.root.after(200, check)

    def _reroll_wanted(self) -> bool:
        """"Reroll prompt" (user 18.11., choice A): wherever the "Enhance my Prompt with LLM" row is shown (MiniMax too), while
        Enhance is ticked, and only when the writer samples (Fibo's takes the likeliest words: a new seed would change nothing)."""
        if not (self._llm_row_wanted() and bool(self.v_enhance.get())):
            return False
        try:
            return any(workflows.writer_samples(load_template(w)) for w in resolve(self.workflows_dir / self.v_workflow.get()))
        except (OSError, ValueError, KeyError):
            return False

    def _update_reroll(self):
        """Show or hide "Reroll prompt" right of the copy icon."""
        if not hasattr(self, "b_reroll"):
            return
        if self._reroll_wanted():
            if not self.b_reroll.winfo_manager():
                self.b_reroll.pack(side="left", padx=(10, 0), after=self.b_copy)
        elif self.b_reroll.winfo_manager():
            self.b_reroll.pack_forget()

    def reroll_prompt(self):
        """A new writer seed (hidden, user 18.11.): the next run writes a new prompt, the runs after it keep that one again."""
        old = self._writer_seed_value()
        new = old
        while new == old:
            new = random.randint(0, 10**SEED_DIGITS - 1)
        self.v_writer_seed.set(new)
        self._status("The next run writes a new prompt.")

    def _copy_enhanced(self):
        """The prompt the text model wrote in the last run goes to the clipboard."""
        text = (self._last_vgl or "").strip()
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
            self._status("Copied to the clipboard.")
        except tk.TclError as e:
            self._status(f"Could not copy: {e}", error=True)

    def _update_prompt_choices(self):
        """The Refine row under the Upscale factor (user 6.11.): one small switch per ready-made prompt of the model's Refine
        (Flux 2: Default, Neutral, Studio portrait; Flux 3: Default, Restore), a lone "Default" for the others. The lit one is the
        Refine button that was chosen (v_fac); the prompt may be edited afterwards."""
        m = self._model()
        spec = m.modes.get("refine") if m else None
        choices = (spec.prompts or (("Default", None, REFINE_DEFAULT_TIP),)) if spec else ()
        key = (m.key, tuple(c[0] for c in choices)) if m else None
        if key != self._pchoice_key:
            self._pchoice_key = key
            self._rpick = ""
            for w in (self.f_refine.winfo_children() or []):
                w.destroy()
            self.rb_refine = {}
            for label, _text, tip in choices:
                rb = ttk.Radiobutton(self.f_refine, text=label, value="r:" + label, variable=self.v_fac,
                                     command=self._on_factor, style="Small.Toolbutton")
                rb.pack(side="left", padx=(0 if not self.rb_refine else 4, 0))
                Tooltip(rb, tip)
                self.rb_refine[label] = rb
        self._sync_fac()
        self._update_factor_buttons()

    def _insert_prompt(self, text: str):
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        t.delete("1.0", "end")
        t.insert("1.0", text)

    # ---------- Styles (styles.json) ----------

    def _build_styles_menus(self):
        """One menu per mode that has styles: a submenu per group, an entry per style (its name). The whole text shows in a box
        right of the menu while the mouse is on an entry (user 1.11.; a menu entry has no tooltip of its own)."""
        self._styles = styles.load()
        self.m_styles: dict = {}
        self._style_texts: dict = {}        # (submenu, entry number) -> the style's text
        self._style_tip = None
        self._style_menus: list = []        # kept, so the submenus (and their names) stay alive
        kw = dict(scale=getattr(self, "ui", 1.0))     # the self-drawn menu (popmenu.py): own margins, grey arrow, accent hover
        self._mode_styles: dict = {}        # mode -> {style name: text} (Edit canvas and Sketch to image remember the style chosen last)
        self._custom_kw = kw
        self.m_custom: dict = {}            # mode -> its "Custom prompts" submenu (filled again each time the menu opens)
        self._custom_menus: dict = {}       # mode -> the menus below it (one per saved prompt), destroyed on refresh
        for mode in dict.fromkeys([k for k, _l in MODE_LABELS] + list(self._styles)):
            groups = self._styles.get(mode, [])
            top = PopMenu(self.root, **kw)
            cm = PopMenu(self.root, **kw)
            self.m_custom[mode] = cm
            self._custom_menus[mode] = []
            top.add_cascade(label="Custom prompts", menu=cm)     # at the very top (user 11.11.); the style groups follow
            cm.bind("<<MenuSelect>>", lambda e, m=cm: self._style_preview(m), add="+")
            cm.bind("<Unmap>", lambda e: self._style_tip_hide(), add="+")
            self._refresh_custom_menu(mode, entries=[])
            if groups:
                top.add_separator()
            self._mode_styles[mode] = {s["name"]: s["text"] for g in groups for s in g["styles"]}
            if mode in SET_STYLE_MODES:     # a whole sentence: the window may replace it like a stock text when the tab changes
                models.STOCK_PROMPTS.update(self._mode_styles[mode].values())
            for g in groups:
                sub = PopMenu(self.root, **kw)
                self._style_menus.append(sub)
                for i, s in enumerate(g["styles"]):
                    sub.add_command(label=s["name"], command=lambda t=s["text"], n=s["name"]: self._apply_style(t, n))
                    self._style_texts[(str(sub), i)] = s["text"]
                sub.bind("<<MenuSelect>>", lambda e, m=sub: self._style_preview(m), add="+")
                sub.bind("<Unmap>", lambda e: self._style_tip_hide(), add="+")
                top.add_cascade(label=g["name"], menu=sub)
            top.bind("<<MenuSelect>>", lambda e: self._style_tip_hide(), add="+")
            top.bind("<Unmap>", lambda e: self._style_tip_hide(), add="+")
            self.m_styles[mode] = top

    def _build_prompt_placeholder(self):
        """The word "Prompt" in grey inside the empty field; it goes when the field has the focus or any text (user 6.11.)."""
        from .gui_common import DISABLED, PANEL
        t = self.t_prompt
        # the grey of the disabled Stop button (TButton disabled foreground), the Text's own font. Placed at 0, 0: place() measures from
        # inside the Text's border plus its padx / pady, so an extra PROMPT_PADX / PADY (the first tries, 12.11. and before) put the word
        # 6 px right and 4 px lower than typed text at 100 %, 9 and 6 at 150 % (measured on screen, 13.11.)
        self._ph = tk.Label(t, text="Prompt", fg=DISABLED, bg=PANEL, bd=0, padx=0, pady=0, font=t.cget("font"), cursor="xterm")
        self._ph.bind("<Button-1>", lambda e: (t.focus_set(), "break")[1])
        self._ph_on = False
        t.bind("<FocusIn>", lambda e: self._prompt_placeholder(focused=True), add="+")
        for ev in ("<FocusOut>", "<KeyRelease>"):
            t.bind(ev, lambda e: self._prompt_placeholder(), add="+")
        self._prompt_placeholder_poll()

    def _prompt_placeholder(self, focused: bool | None = None):
        t = self.t_prompt
        word = models.SKETCH_PLACEHOLDER if self.v_mode.get() == "sketch" else "Prompt"    # Sketch to image: plan B, 10.11.
        if self.v_mode.get() == "remove":       # Remove with a named object (user 16.11.): Flux 3, Flux 2, Fibo; Qwen too (17.11.)
            m = self._model()
            spec = m.modes.get("remove") if m else None
            if spec is not None and spec.remove_text:
                word = models.REMOVE_PLACEHOLDER
        if self._ph.cget("text") != word:
            self._ph.configure(text=word)
        try:
            if focused is None:
                focused = self.root.focus_get() is t
            empty = not t.get("1.0", "end-1c")
        except (tk.TclError, KeyError):
            return
        want = empty and not focused
        if want and not self._ph_on:
            self._ph.place(x=0, y=0)       # Tk's place counts from inside the Text's border AND its padx / pady: 0, 0 is where typed text starts
            self._ph_on = True
        elif not want and self._ph_on:
            self._ph.place_forget()
            self._ph_on = False

    def _prompt_placeholder_poll(self):
        """Text set by the program (a style, Describe, history, a new function) does not fire a key event: look again now and then."""
        self._prompt_placeholder()
        try:
            self.root.after(300, self._prompt_placeholder_poll)
        except Exception:
            pass

    def _update_styles_button(self):
        """The Styles button is there in every function (its menu starts with Custom prompts, then come the style groups of
        the modes that have them: Text to image, Edit canvas, Sketch to image), in the middle of the row over the field (P2,
        10.11. evening; user 11.11.). Grey, like Save, while the prompt field is off (Remove)."""
        b = getattr(self, "b_styles", None)
        if b is None:
            return
        want = self.v_mode.get() in self.m_styles
        if want and not self._styles_shown:
            b.pack(side="top", pady=(0, self._px(2)), before=self.b_save)       # first in the column (12.11.)
            self._styles_shown = True
        elif not want and self._styles_shown:
            b.pack_forget()
            self._styles_shown = False
        off = str(self.t_prompt.cget("state")) == "disabled"
        for w in (b, getattr(self, "b_save", None)):
            if w is not None:
                w.configure(state="disabled" if off else "normal")

    def _styles_menu(self):
        """A click on the Styles button: Custom prompts, then the groups, opening right of the button (it sits in the icon column
        right of the prompt field), top-aligned with it. The popup does not block; the hover box goes with the menu's <Unmap>."""
        mode = self.v_mode.get()
        m = self.m_styles.get(mode)
        if m is None or str(self.t_prompt.cget("state")) == "disabled":
            return
        self._refresh_custom_menu(mode)
        place_right_of(m, self.b_styles)

    # ---------- Custom prompts (custom_prompts.py, docs/prompt-saver-konzept.md; user 11.11.) ----------

    def _cp_tag(self) -> tuple:
        """(model, function) as the window shows them, for the tag of a saved prompt."""
        m = self._model()
        mode = self.v_mode.get()
        fn = "Edit canvas" if mode == "edit" else SCALE_FN_LABEL if mode in SCALE_MODES else dict(MODE_LABELS).get(mode, mode)
        return (m.label if m else "Own workflow"), fn

    def _cp_context(self) -> dict:
        """The keys behind the tag (model, function, tab under Edit / Fill), so "Use" can go back to them (user 15.11.)."""
        v = getattr(self, "v_edtab", None)
        return {"model_key": self.v_model.get(), "mode": self.v_mode.get(), "tab": v.get() if v is not None else ""}

    def _cp_switch(self, ctx: dict) -> str:
        """"Use" of a saved prompt: function, model and tab as they were when it was saved, like clicks on them (user 15.11.).
        A model that cannot be chosen now (hidden, files missing, not for this function): the function picks its model.
        Returns a note for the status line ("" = nothing to say)."""
        mode, key, tab = ctx.get("mode", ""), ctx.get("model_key", ""), ctx.get("tab", "")
        if not mode or self._custom_workflow() or not any(mode in m.modes for m in models.MODELS):
            return ""
        m = models.BY_KEY.get(key)
        ok = getattr(self, "_model_usable", lambda k, md: True)
        usable = (m is not None and mode in m.modes and key in getattr(self, "rb_tabs", {m.key: None})
                  and key not in cfgmod.hidden_tabs() and ok(key, mode))
        if self.v_mode.get() != mode:
            self.v_mode.set(mode)
            self._on_mode()
        if usable and self.v_model.get() != key:
            self.v_model.set(key)
            self._on_model()
        if mode in (MULTI_MODE, SCRIBBLE_MODE) and getattr(self, "v_edtab", None) is not None and hasattr(self, "_edtab_clicked"):
            cur = self._model()       # Multi image edit or Insert reference; Scribble on photo or Scribble with reference
            if TAB_MODE.get(tab, MULTI_MODE) != mode:
                tab = ""
            if tab == "bbox" and not (cur is not None and cur.bbox):
                tab = ""
            if tab == "refscribble" and not models.offers_ref_scribble(cur):
                tab = ""
            self.v_edtab.set(tab or ("multi" if mode == MULTI_MODE else "scribble"))
            self._edtab_clicked()
        if key and not usable and self._model() is not None and self.v_model.get() != key:
            return f"{m.label if m else 'The saved model'} is not available here, {self._model().label} is used. "
        return ""

    def _cp_load(self) -> list:
        entries = custom_prompts.load()
        note = custom_prompts.load_note()
        if note:
            custom_prompts.clear_note()
            self._status(note, error=True)
        return entries

    def _refresh_custom_menu(self, mode: str, entries: list | None = None):
        """Fills the Custom prompts submenu of `mode` from the file (a normal Tk submenu): each saved prompt is a submenu of its
        own with Use, Append, Edit and Delete; no prompts: one greyed-out line."""
        cm = self.m_custom.get(mode)
        if cm is None:
            return
        if entries is None:
            entries = self._cp_load()
        cm.delete(0, "end")
        for old in self._custom_menus.get(mode, []):
            self._style_texts = {k: v for k, v in self._style_texts.items() if k[0] != str(old)}
            try:
                old.destroy()
            except Exception:
                pass
        self._custom_menus[mode] = []
        if not entries:
            cm.add_command(label=custom_prompts.EMPTY_LABEL, state="disabled")
            return
        for e in entries:
            sub = PopMenu(self.root, **self._custom_kw)
            self._custom_menus[mode].append(sub)
            n = e["name"]
            sub.add_command(label="Use", command=lambda n=n: self._cp_use(n))
            sub.add_command(label="Append", command=lambda n=n: self._cp_use(n, append=True))
            sub.add_command(label="Edit", command=lambda n=n: self._cp_edit(n))
            sub.add_command(label="Delete", command=lambda n=n: self._cp_delete(n))
            for i in (0, 1):
                self._style_texts[(str(sub), i)] = e["text"]      # the hover box shows the whole text
            sub.bind("<<MenuSelect>>", lambda ev, m=sub: self._style_preview(m), add="+")
            sub.bind("<Unmap>", lambda ev: self._style_tip_hide(), add="+")
            cm.add_cascade(label=custom_prompts.label(e), menu=sub)

    def _cp_use(self, name: str, append: bool = False):
        """Use: the saved text replaces the prompt; Append: it goes to the end after a line break. One undo step each."""
        self._style_tip_hide()           # the hover box (topmost) must not stay over the field (window test E, 11.11.)
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        entries = self._cp_load()
        i = custom_prompts.find(entries, name)
        if i < 0:
            return
        e = entries[i]
        ctx = custom_prompts.context(e, {x.label: x.key for x in models.MODELS},
                                     {**{lab: k for k, lab in MODE_LABELS}, "Edit canvas": "edit"})
        note = "" if append else self._cp_switch(ctx)       # only Use goes back to function, model and tab (user 15.11.)
        if str(t.cget("state")) == "disabled":            # (Remove: the field is off)
            self._status(note + "This function takes no prompt.")
            return
        saved = models.BY_KEY.get(ctx["model_key"])
        now = self._model()
        # the image names as the chosen model writes them ("<image2>" <-> "image 2" ...), also for Append (user 15.11.)
        text = retag(e["text"], saved.tag_style if saved else "", now.tag_style if now else "")
        auto = t.cget("autoseparators")      # Tk would otherwise split delete + insert into two undo steps
        t.configure(autoseparators=False)
        appended = False
        try:
            t.edit_separator()
            old = t.get("1.0", "end").rstrip()
            if append and old:
                t.insert("end-1c", ("" if t.get("end-2c", "end-1c") == "\n" else "\n") + text)
                appended = True
            else:
                t.delete("1.0", "end")
                t.insert("1.0", text)
            t.edit_separator()
        finally:
            t.configure(autoseparators=auto)
        self._written_for = ""
        t.focus_set()
        self._update_prompt_hint()
        self._status(note + f"Prompt “{name}” {'appended' if appended else 'set'}. Ctrl+Z in the field brings the text before back.")

    def save_prompt(self):
        """The Save button: asks for a name and keeps the text of the field (user 11.11.)."""
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        text = t.get("1.0", "end").strip()
        if not text:
            self._status("Write a prompt first")
            return
        model, fn = self._cp_tag()
        ctx = self._cp_context()

        def done(name, _text):
            entries = self._cp_load()
            r = custom_prompts.add(entries, name, text, model, fn, context=ctx)
            if r == "exists":
                if not messagebox.askyesno("Save prompt", f"“{name.strip()}” exists. Replace it?", parent=self.root):
                    return False
                r = custom_prompts.add(entries, name, text, model, fn, replace=True, context=ctx)
            return self._cp_finish(r, entries, f"Prompt saved as “{name.strip()[:custom_prompts.MAX_NAME]}”. Find it under Style prompts > Custom prompts.")
        self._cp_dialog("Save prompt", "", None, done)

    def _cp_edit(self, name: str):
        entries = self._cp_load()
        i = custom_prompts.find(entries, name)
        if i < 0:
            return

        def done(new_name, new_text):
            entries = self._cp_load()
            j = custom_prompts.find(entries, name)
            if j < 0:
                return True
            r = custom_prompts.edit(entries, j, new_name, new_text)
            if r == "exists":
                if not messagebox.askyesno("Edit prompt", f"“{new_name.strip()}” exists. Replace it?", parent=self.root):
                    return False
                r = custom_prompts.edit(entries, j, new_name, new_text, replace=True)
            return self._cp_finish(r, entries, f"Prompt “{new_name.strip()[:custom_prompts.MAX_NAME]}” changed.")
        self._cp_dialog("Edit prompt", entries[i]["name"], entries[i]["text"], done)

    def _cp_delete(self, name: str):
        if not messagebox.askyesno("Delete prompt", f"Delete “{name}”?", parent=self.root):
            return
        entries = self._cp_load()
        i = custom_prompts.find(entries, name)
        if i < 0:
            return
        custom_prompts.delete(entries, i)
        self._cp_finish("", entries, f"Prompt “{name}” deleted.")

    def _cp_finish(self, result: str, entries: list, ok_text: str) -> bool:
        """Writes the list after add/edit/delete and says what happened in the status line; True = the dialog may close."""
        msgs = {"name": "Give the prompt a name.", "text": "The text is empty.",
                "full": f"{custom_prompts.MAX_ENTRIES} prompts are saved: delete one first."}
        if result:
            self._status(msgs.get(result, "Not saved."), error=True)
            return False
        if not custom_prompts.save(entries):
            self._status(f"Could not write {custom_prompts.path()}.", error=True)
            return False
        self._refresh_custom_menu(self.v_mode.get(), entries)
        self._status(ok_text)
        return True

    def _cp_dialog(self, title: str, name: str, text, done):
        """A small window in the style of the gear windows: Name (40 characters at most) and, when `text` is not None, the
        text; Save / Cancel. `done(name, text)` returns False to keep it open. It does not block (the tests drive
        self._cp_win.ok())."""
        old = getattr(self, "_cp_win", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        win = tk.Toplevel(self.root, **hostos.TOP_KW)
        win.withdraw()                   # placed first, then shown: a shown window without a title bar ignored the move (window test F)
        win.title(title)
        win.wm_overrideredirect(True)
        win.configure(bg=BG, highlightthickness=1, highlightbackground="#5c5c5c")
        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=self._keep(14), pady=self._keep(12))
        ttk.Label(box, text=title, font=font(10, bold=True), foreground="#ffffff").pack(anchor="w")
        ttk.Label(box, text="Name", style="Muted.TLabel").pack(anchor="w", pady=(self._keep(8), 0))
        v_name = tk.StringVar(value=name)
        e = ttk.Entry(box, textvariable=v_name, width=44)
        e.pack(fill="x")
        mx = custom_prompts.MAX_NAME
        v_name.trace_add("write", lambda *_a: v_name.set(v_name.get()[:mx]) if len(v_name.get()) > mx else None)
        t = None
        if text is not None:
            ttk.Label(box, text="Text", style="Muted.TLabel").pack(anchor="w", pady=(self._keep(8), 0))
            t = tk.Text(box, height=7, width=44, wrap="word", bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                        highlightthickness=1, highlightbackground="#454545", highlightcolor=ACCENT, font=font(10), padx=6, pady=4,
                        undo=True)
            t.pack(fill="both", expand=True)
            t.insert("1.0", text)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(self._keep(12), 0))

        def close():
            self._cp_win = None
            try:
                win.destroy()
            except tk.TclError:
                pass
            # the keyboard goes back to the plugin and its prompt field (window test F, 11.11.: after Save the field took no
            # clicks for a moment: Windows had left no window of the plugin active)
            try:
                self.root.after_idle(self._prompt_focus_back)
            except tk.TclError:
                pass

        def ok(_e=None):
            if done(v_name.get(), t.get("1.0", "end").strip() if t is not None else ""):
                close()
        win.ok, win.close, win.v_name, win.t_text = ok, close, v_name, t     # for the tests
        ttk.Button(row, text="Cancel", command=close, style="TipOk.TButton").pack(side="right")
        ttk.Button(row, text="Save", command=ok, style="TipOk.TButton").pack(side="right", padx=(0, self._keep(8)))
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Escape>", lambda ev: close())
        if t is None:
            win.bind("<Return>", ok)
        self._cp_win = win
        try:
            win.transient(self.root)
            win.update_idletasks()
            w, h = max(self._px(360), win.winfo_reqwidth()), win.winfo_reqheight()
            # beside the window, top edges level, like the settings window (window test E, 11.11.); no room on the right of
            # the screen: on the left of the window
            x = self.root.winfo_rootx() + self.root.winfo_width() + 8
            try:
                vx0, _vy0, vx1, _vy1 = self._monitor_at(self.root.winfo_rootx(), self.root.winfo_rooty(), work=True)
                if x + w > vx1:
                    x = max(vx0, self.root.winfo_rootx() - w - 8)
            except Exception:
                pass
            y = self.root.winfo_rooty()
            self._cp_pos = (x, y)                # (a hidden test window reports +0+0, so the tests read this)
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.deiconify()
            win.lift()
            win.focus_force()
            e.focus_set()
            e.selection_range(0, "end")
        except tk.TclError:
            pass

    def _prompt_focus_back(self):
        try:
            self.root.focus_force()
            if str(self.t_prompt.cget("state")) != "disabled":
                self.t_prompt.focus_set()
        except tk.TclError:
            pass

    def _apply_style(self, text: str, name: str = ""):
        """A style entry is added to the prompt after a line break (user 1.11.; an empty field just gets the style), in one undo
        step: Ctrl+Z in the field takes it away again. In Edit canvas and Sketch to image the style is the whole sentence (plan B, 10.11.)."""
        self._style_tip_hide()
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        if self.v_mode.get() in SET_STYLE_MODES:
            self._set_style(text, name)
            return
        auto = t.cget("autoseparators")      # Tk would otherwise split delete + insert into two undo steps
        t.configure(autoseparators=False)
        try:
            t.edit_separator()
            old = t.get("1.0", "end").rstrip()
            if old:
                t.insert("end-1c", ("" if t.get("end-2c", "end-1c") == "\n" else "\n") + text)
            else:
                t.delete("1.0", "end")
                t.insert("1.0", text)
            t.edit_separator()
        finally:
            t.configure(autoseparators=auto)
        t.focus_set()
        self._status("Style added to the prompt. Ctrl+Z in the field takes it away again.")

    def _set_style(self, text: str, name: str = ""):
        """Edit canvas and Sketch to image (plan B, 10.11.): the style replaces the whole field; what was typed for <WHAT IT SHOWS>
        in the style before goes along into the new one. The style is remembered (settings.json); only Sketch to image puts it
        back into the field on opening (_sketch_style_fill; Edit canvas stays as it was, user 10.11.)."""
        t = self.t_prompt
        mode = self.v_mode.get()
        subject = styles.subject_of(t.get("1.0", "end"), self._mode_styles.get(mode, {}).values(), models.SKETCH_MARK)
        new = styles.fill(text, None if subject == models.SKETCH_MARK else subject, models.SKETCH_MARK)
        self._written_for = ""              # a style: the writer runs again (Sketch from the history)
        auto = t.cget("autoseparators")
        t.configure(autoseparators=False)
        try:
            t.edit_separator()
            t.delete("1.0", "end")
            t.insert("1.0", new)
            t.edit_separator()
        finally:
            t.configure(autoseparators=auto)
        if name:
            cfgmod.set_setting(STYLE_KEY + mode, name)
        t.focus_set()
        self._update_prompt_hint()
        self._status(f"Style “{name or 'chosen'}” set. Ctrl+Z in the field brings the text before back.")

    def _sketch_style_fill(self):
        """Opening Sketch to image: an empty field (or one with a stock text of another tab) gets the style chosen last, with
        <WHAT IT SHOWS> to replace; without one it stays empty and shows "Choose a style under Styles" (plan B, 10.11.)."""
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        cur = t.get("1.0", "end").strip()
        if cur and cur not in models.STOCK_PROMPTS:
            return
        texts = getattr(self, "_mode_styles", {}).get("sketch", {})
        name = cfgmod.get_setting(STYLE_KEY + "sketch", "")
        new = texts.get(name, "") if isinstance(name, str) else ""
        if new == cur:
            return
        t.edit_separator()
        t.delete("1.0", "end")
        if new:
            t.insert("1.0", new)
        t.edit_separator()

    def _style_text_at(self, menu, active):
        """The text of entry number `active` of a style submenu ("" for none)."""
        return self._style_texts.get((str(menu), active), "") if isinstance(active, int) else ""

    def _style_preview(self, menu):
        """<<MenuSelect>> of a group menu: the whole text of the entry under the mouse in a small box right of the menu that
        shows the row, level with that row (left of the menu when there is no room)."""
        self._style_tip_hide()
        try:
            i = menu.index("active")
            text = self._style_text_at(menu, i)
            geo = menu.geometry() if text else None
            if not text or geo is None:
                return
            mx, my, mw, _mh = geo
            x, y = mx + mw + 4, my + menu.row_top(i)
            tip = tk.Toplevel(self.root, **hostos.TOP_KW)
            tip.withdraw()
            tip.wm_overrideredirect(True)
            tk.Label(tip, text=text, justify="left", wraplength=340, background="#ffffe0", foreground="#000000",
                     relief="solid", borderwidth=1, padx=6, pady=4, font=font(9)).pack()
            tip.update_idletasks()
            vx0, vy0, vx1, vy1 = self._monitor_at(mx, my)
            if x + tip.winfo_reqwidth() > vx1:
                x = max(vx0, mx - tip.winfo_reqwidth() - 4)
            y = max(vy0, min(y, vy1 - tip.winfo_reqheight()))
            tip.wm_geometry(f"+{x}+{y}")
            self._style_tip_pos = (x, y)         # (a tip of a hidden window reports +0+0, so the tests read this)
            tip.wm_attributes("-topmost", True)
            tip.deiconify()
            self._style_tip = tip
        except tk.TclError:
            self._style_tip_hide()

    def _monitor_at(self, px: int, py: int, work: bool = False) -> tuple:
        """(x0, y0, x1, y1) of the monitor under the point (Windows API); the window may sit on a second monitor, where Tk's
        screen size (the first monitor) is wrong. Falls back to Tk's screen. ``work``: the work area, i.e. without the
        taskbar (as Windows reports it, whatever its height or side); without the API a guessed taskbar is taken off."""
        try:
            import ctypes
            from ctypes import wintypes
            u = ctypes.windll.user32
            u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            u.MonitorFromPoint.restype = wintypes.HANDLE

            class MI(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD)]
            mi = MI()
            mi.cbSize = ctypes.sizeof(MI)
            hm = u.MonitorFromPoint(wintypes.POINT(px, py), 2)       # 2 = the nearest monitor
            if hm and u.GetMonitorInfoW(hm, ctypes.byref(mi)):
                r = mi.rcWork if work else mi.rcMonitor
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - (self._px(56) if work else 0)

    def _style_tip_hide(self):
        tip, self._style_tip = getattr(self, "_style_tip", None), None
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass

    def _clear_prompt(self):
        """The bin next to "Prompt": empties the field (one undo step, so Ctrl+Z in the field brings the text back)."""
        t = self.t_prompt
        if str(t.cget("state")) == "disabled":
            return
        t.edit_separator()
        t.delete("1.0", "end")
        t.edit_separator()
        t.focus_set()

    def _sync_prompt_field(self, mode: str):
        """Remove object ignores the text: the field is emptied and greyed out, the typed text comes back afterwards."""
        t = self.t_prompt
        m = self._model()
        spec = m.modes.get(mode) if m else None
        if mode == "remove" and not (spec is not None and spec.remove_text):
            if str(t.cget("state")) != "disabled":
                self._prompt_kept = t.get("1.0", "end").strip()
            t.configure(state="normal")
            t.delete("1.0", "end")
            t.configure(state="disabled")
        elif str(t.cget("state")) == "disabled":
            t.configure(state="normal")
            t.delete("1.0", "end")
            if getattr(self, "_prompt_kept", ""):
                t.insert("1.0", self._prompt_kept)
            self._prompt_kept = ""
        self._update_styles_button()        # Styles and Save are grey while the field is off

    def _show_negative(self):
        opened = bool(self.v_neg_open.get())
        self.btn_neg.configure(text="Negative prompt", compound="left",
                               image=self._icon("chevron-down" if opened else "chevron-right", MUTED))
        self.neg_body.pack_forget()          # never shown (user 2.11.)

    def _toggle_negative(self):
        self.v_neg_open.set(not self.v_neg_open.get())
        self._show_negative()
        self._fit_height()
