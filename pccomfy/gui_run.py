"""A run: build the request, generate, undo/redo, stop, poll, progress and status line. (moved out of gui.py unchanged; see PLAN.md, phase 0)."""
from __future__ import annotations
import copy

from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from . import icons
from . import jobqueue
from . import workflows
from . import history as runhistory
from .listpopup import ListPopup


class RunMixin:
    def _status(self, msg: str, error: bool = False):
        """The status line. An error gets a red "!" badge and red text, it never opens a dialog."""
        self._status_error = bool(error and msg)
        self._status_stale = False      # a message of its own: the progress of the run that is on leaves it (_poll)
        self.lbl_status.configure(style="Error.TLabel" if error else "TLabel")
        self.v_status.set(msg)          # shows or hides the line (_show_status_line, a trace on v_status)

    def _dismiss_error(self, event=None):
        """A left click on the status line (its text or the red "!") clears it: an error always (user 12.11.), any other
        message too, except while a run or a batch works, whose progress text would come right back (user 13.11.).
        Right-click Copy (gui_theme._copy_menu) is a separate binding and still works."""
        if getattr(self, "_status_error", False):
            self._status("")
            return
        worker = getattr(self, "worker", None)
        busy_batch = getattr(self, "_batch_busy", None)
        if (getattr(self, "_running", False) or (worker is not None and worker.is_alive())
                or (busy_batch is not None and busy_batch())):
            return
        self._status("")

    def _fit_status_wrap(self, _e=None):
        """A long message wraps at the right edge of the status line (the width of the separator lines above), less the red "!" and
        its gap while an error shows it: the wrap width was a fixed 20 px short (user 13.11.)."""
        try:
            w = int(self.f_status.winfo_width())
            if w > 1:
                if self.lbl_err.winfo_manager():
                    w -= int(self.lbl_err.winfo_reqwidth()) + self._px(8)
                if int(self.lbl_status.cget("wraplength")) != w:
                    self.lbl_status.configure(wraplength=max(1, w))
        except (tk.TclError, ValueError, AttributeError):
            pass

    def _show_status_line(self):
        """The status line between the progress bar and the footer is shown only while it has text (user 8.11.): empty, it
        shrinks to 1 px without its gap, so the footer sits right under the bar; the window is one line higher during a message."""
        if not hasattr(self, "f_status"):
            return
        text = bool(str(self.v_status.get()).strip())
        packed = bool(self.lbl_status.winfo_manager())
        if text:
            if getattr(self, "_status_error", False):
                self.lbl_err.pack(side="left", anchor="n", padx=(0, 8), before=self.lbl_status if packed else None)
            else:
                self.lbl_err.pack_forget()
            if not packed:
                self.lbl_status.pack(side="left", fill="x", expand=True)
            self._fit_status_wrap()
        else:
            self._status_error = False          # the error is over: a later plain text (a direct set) gets no red "!"
            self.lbl_err.pack_forget()
            self.lbl_status.pack_forget()
            self.f_status.configure(height=1)       # a frame keeps its last size when its last child goes (Tk)
        if self.f_status.winfo_manager():       # (the window follows by itself: <Configure> -> _on_content_size)
            self.f_status.pack_configure(pady=(4, 0) if text else 0)

    # ---------- generation ----------

    def _writer_runs(self) -> bool:
        """Does the run's text model write the prompt? Sketch and Scribble: always (not Fibo, not with a prompt loaded back from
        the history); elsewhere "Enhance my Prompt with LLM" decides."""
        m = self._model()
        spec = m.modes.get(self.v_mode.get()) if m else None
        if self.v_mode.get() in ("sketch", "scribble"):
            return bool(spec is not None and spec.settings.get("enhance", True)) and self._has_text_model() and not self._written_active()
        return bool(self.v_enhance.get()) and self._llm_row_wanted()

    def _writer_seed_value(self) -> int:
        """The Prompt writer seed in the box; an empty or broken box counts as the start value."""
        try:
            return int(self.v_writer_seed.get())
        except (tk.TclError, ValueError):
            return WRITER_SEED_DEFAULT

    def _request(self) -> Request:
        wf = self.v_workflow.get()
        wf_path = None if wf == BUILTIN else str(self.workflows_dir / wf)
        p = GenParams(prompt=self.t_prompt.get("1.0", "end").strip(), negative=self.t_neg.get("1.0", "end").strip(),
                      checkpoint=self.v_ckpt.get().strip(), steps=int(self.v_steps.get()), cfg=float(self.v_cfg.get()),
                      sampler=self.v_sampler.get(), scheduler=self.v_scheduler.get(), seed=int(self.v_seed.get()),
                      denoise=1.0 if self.v_mode.get() == "txt2img" else float(self.v_denoise.get()))
        p.clip = "" if self.v_clip.get() in ("", CLIP_DEFAULT) else self.v_clip.get().strip()
        p.writer_seed = self._writer_seed_value()
        m = self._model()
        spec = m.modes.get(self.v_mode.get()) if m else None
        target = p.prompt if (self.v_mode.get() == "remove" and spec is not None and spec.remove_text) else ""
        style = spec.remove_style if (self.v_mode.get() == "remove" and spec is not None and spec.remove_text) else ""
        req = Request(mode=self._run_mode(), params=p, remove_target=target, remove_style=style,
                      remove_writer=self._llm_file() if style else "", workflow=wf_path, base_res=int(self.v_res.get()),
                       native=(bool(self.v_native.get()) or self.v_mode.get() == "outpaint") and self._native_wanted(), native_mp=self._native_mp(),
                       gen_mp=float(self.v_gen_mp.get()) if self._gen_wanted() else 0.0,
                       new_document=self._gen_wanted() and not bool(self.v_downsize.get()),
                       full_size=self.v_mode.get() in SCALE_MODES,
                       context=min(1.0, max(0.0, round(float(self.v_context.get()) * 20) / 20)),   # the slider's range and steps (an old saved 2.0 too)
                       mask_grow=int(self.v_grow.get()), mask_blur=int(self.v_blur.get()),
                       overlap=int(self.v_overlap.get()), variants=int(self.v_variants.get()),
                       enhance=self._writer_runs(),
                       turbo=bool(self.v_turbo.get()), scale=self._scale(),
                       lora_strength=(round(float(self.v_lora_str.get()), 2) if self._has_lora_switch() else None),
                       stage_on=bool(self.v_stage.get()) or not self._stage_label(), stages_off=self._stages_off(), stage_strengths=self._stage_strengths(), sampler_override=self._sampler_override(), variant=getattr(self._variant(), "file", ""), doc_tag=self._doc_tag(), loras=[tuple(x) for x in self._loras()], detail=round(float(self.v_detail.get()), 2) if self.v_mode.get() in SCALE_MODES else 1.0,
                       layer_mask=layer_mask_key(self.v_lmask.get()),
                       feather_pct=round(float(self.v_feather.get()) * 2) / 2,
                       mask_density=min(100, max(0, int(self.v_density.get()))),
                       seam_fixed=self._seam_mode() == "on" and self._run_mode() in ("inpaint", "remove", "outpaint"),
                       preview=bool(self.v_live.get()), preview_method=m.preview if m else "taesd")
        req.scribble = self.v_mode.get() == "scribble"      # its own tab since plan B (10.11.)
        req.one_by_one = self.v_mode.get() in ("sketch", "scribble", "multi_edit")   # ×n one after the other (user 24.11., A)
        req.scribble_object = bool(req.scribble and spec is not None and spec.scribble_object_mask)   # MiniMax (user 21.11.)
        req.fill_object = bool(spec is not None and spec.fill_object_mask and req.mode == "inpaint" and not req.remove)   # Qwen (user 21.11.)
        req.fill_box = bool(spec is not None and spec.fill_box and req.mode == "inpaint")    # Flux 3 Fill: the box <obj_1> (plan B step 4)
        return req

    def _doc_tag(self) -> str:
        """Model and options for the name of an upscaled document: "Flux3Klein x1.5 SeedVR2 Restore0.8"."""
        m = self._model()
        parts = [re.sub(r'[\\/:*?"<>|]+', "", m.label) if m else "AI"]
        if self.v_mode.get() == "upscale":
            parts.append(f"x{self._scale():g}")
        for var, st in zip(self.stage_vars, self._stages()):
            if var.get():
                parts.append(st["label"].split()[0])
        if self._has_lora_switch() and self.v_turbo.get():
            try:
                parts.append(f"{self._lora_label().split()[0]}{float(self.v_lora_str.get()):.2g}")
            except (tk.TclError, ValueError):
                pass
        try:
            if self._run_mode() in SCALE_MODES and float(self.v_detail.get()) < 0.995:
                parts.append(f"mix{round(float(self.v_detail.get()) * 100)}")
        except (tk.TclError, ValueError):
            pass
        return " ".join(parts)

    def _layer_prefix(self) -> str:
        """The name the result layers start with (presets are hidden): "Qwen Image 2.1 Fill", then " #<running number>"."""
        m = self._model()
        name, short = (m.label if m else "AI"), SHORT_MODES.get(self.v_mode.get(), self.v_mode.get())
        return name if short in name.split() else f"{name} {short}"      # "Fibo 2.0 Edit Turbo" + Edit stays "Fibo 2.0 Edit Turbo"

    def _stages_off(self) -> list[str]:
        """Node ids of the second and third switchable stage when their checkboxes are off (the first one is stage_on)."""
        st = self._stages()
        return [s["id"] for s, var in zip(st[1:], self.stage_vars[1:]) if not var.get()]

    def _show_variants(self):
        """The grey piece on the right of Generate says how many pictures a run makes: "×3 ▾", also "×1 ▾" (user 30.10.)."""
        try:
            n = int(self.v_variants.get())
        except (TypeError, ValueError, tk.TclError):
            n = 1
        self.w_variants.configure(text=f"×{n} ▾")
        self._fit_go_row()          # its natural width may change with the number

    def _variants_menu(self):
        """A click on the piece beside Generate: the choice 1 to 8, opening under it."""
        b = self.w_variants
        self.m_variants.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    # ---------- Generate while a run is on: "Add to queue" (docs/plan/generate-queue.md, step 1) ----------

    def _something_runs(self) -> bool:
        """A run of this window or the queue (a batch, queued Generate clicks) is on: Generate queues instead of running."""
        return bool(getattr(self, "_running", False)) or self._batch_busy()

    def _queue_refusal(self) -> str:
        """Why Generate can't wait in the queue with this function ("" = it can). User 23.11. evening (choice D): only
        Refine, Upscale, Edit and Text to image, and only behind the same function (the model may differ); Fill, Remove,
        Expand need the selection of the moment the run starts (user 22.11.), Insert reference too; Multi Edit, Sketch and
        Scribble never queue."""
        mode = self.v_mode.get()
        fn = FN_NAMES.get(mode, mode)          # as the picker names it (user 25.11.)
        if mode in ("inpaint", "remove", "outpaint"):
            return QUEUE_LOCKED.format(fn=fn)
        try:
            if self._bbox_on():
                return QUEUE_NO_BBOX
        except Exception:
            pass
        if mode not in QUEUE_WINDOW_MODES or self._run_mode() not in jobqueue.QUEUE_MODES:
            return QUEUE_LOCKED.format(fn=fn)
        other = sorted(m for m in self._open_modes() if m != mode)
        if other:
            return QUEUE_OTHER_FN.format(run=QUEUE_FN_NAMES.get(other[0], other[0]))
        return ""

    def _open_modes(self) -> set:
        """The functions that run or wait now: the direct run of this window (its window mode) and the batches and queued
        Generate clicks of the queue (their run mode; for the four queue functions it is the window mode)."""
        modes = set()
        if getattr(self, "_running", False):
            modes.add(str(getattr(self, "_run_wmode", "") or ""))
        runner = getattr(self, "runner", None)
        try:
            if runner is not None:
                modes |= set(runner.open_modes())
        except Exception:
            pass
        modes.discard("")
        return modes

    def _enqueue(self, rest: int = 0, shared: dict | None = None) -> str:
        """Generate while a run is on (user 22.11., choice A): the picture of the document in front and every setting are
        taken now and wait in the queue as a "batch" of its own (×n = n jobs); each result comes as a new layer (Upscale: a
        new document), and Undo hides it again. rest: a direct Generate with ×n has just started its first picture; the
        other rest pictures wait here as jobs of their own (user 23.11., choice A). Returns the batch id ("" = none)."""
        jobqueue.qlog(self.bridge, "q_click", rest=rest)
        reason = self._queue_refusal()
        if reason:
            self._status(reason, error=True)
            return
        if not rest and time.monotonic() - getattr(self, "_stop_armed", 0.0) < STOP_GUARD_S:
            return                  # a double click on Generate: the second click comes right after the run started
        try:
            req = self._request()
            n = rest or max(1, int(self.v_variants.get()))
        except (tk.TclError, ValueError) as e:
            self._status(f"Invalid value: {e}", error=True)
            return
        seed = req.params.seed
        if rest and seed is not None and int(seed) >= 0:       # a fixed seed: the direct picture has it, these the next ones
            req.params.seed = (int(seed) + 7919) % (2**31)
        req.preset = self._layer_prefix()
        runs = dict(self.state.get("runs", {}))
        short = SHORT_MODES.get(self.v_mode.get(), self.v_mode.get())
        if req.preset:      # n running numbers, one per job ("Refine 7", "Refine 8")
            req.run_no = int(runs.get(req.preset, 0)) + 1
            runs[req.preset] = req.run_no + n - 1
            req.group_name = f"{short} {req.run_no}"
        m = self._model()
        label = self._fn_label()
        spec = jobqueue.BatchSpec(request=req, source=jobqueue.SOURCE_ACTIVE, dry_run=False, kind=jobqueue.K_GENERATE,
                                  copies=n, label=label, model=m.label if m else "", shared=shared)
        try:
            bid = self.runner.start_batch(spec)
        except (ValueError, BridgeError) as e:
            self._status(str(e), error=True)
            return
        self.state["runs"] = runs
        try:
            self._save_state(req)
        except Exception:
            pass
        self._batch_mine = getattr(self, "_batch_mine", set()) | {bid}
        try:            # the history entry of each job is written when it is done, with the prompt its writer wrote
            settings = self._collect()
            self._queued_hist = dict(getattr(self, "_queued_hist", {}) or {})
            self._queued_hist[bid] = runhistory.entry(req.group_name or short, m.label if m else "", settings,
                                                      llm=settings.get("prompt", "") if self._written_active() else "")
        except (tk.TclError, ValueError, TypeError):
            pass
        if rest:
            self._status(VARIANTS_QUEUED.format(n=n))
        else:
            self._status(f"Added to the queue: {label}" + (f" ×{n}" if n > 1 else "") + ".")
        self._batch_sync()
        self._queue_dirty()
        return bid

    def _fn_label(self) -> str:
        """Function and model of the settings now ("Refine Image · Qwen Image 2.1"): the queue window's Function column, with
        the function as the picker names it (user 25.11.)."""
        short = FN_NAMES.get(self.v_mode.get(), self.v_mode.get())
        m = self._model()
        return f"{short} · {m.label}" if m else short

    def _queued_done(self, job: dict):
        """A job of a queued Generate is done: its run goes in front of the last runs (the clock), with the prompt its
        writer wrote and its own group name."""
        e = (getattr(self, "_queued_hist", None) or {}).get(job.get("batch_id"))
        seen = self._queued_seen = getattr(self, "_queued_seen", set())
        if not e or job.get("id") in seen:
            return
        seen.add(job.get("id"))
        e = dict(e)
        if job.get("group"):
            e["title"] = job["group"]
        if str(job.get("written") or "").strip():
            e["llm"] = str(job["written"]).strip()
        runhistory.add(cfgmod.HISTORY_FILE, e)

    def generate(self):
        jobqueue.qlog(self.bridge, "q_generate_click")
        if self._something_runs():          # Add to queue (user 22.11.; replaces "Generate locked while a batch is on", 12.11.)
            self._enqueue()
            return
        if self.worker and self.worker.is_alive():
            return
        if self._blocked_by_batch():
            return
        if self._needs_description() and not self.t_prompt.get("1.0", "end").strip():
            # an empty prompt fills the margin with unrelated things (A/B test 29.10.): no run, say what to do
            m = self._model()
            self._status(f"{m.label if m else 'This model'} needs a description of the surroundings: "
                         "click Describe or type one.", error=True)
            return
        if self.v_mode.get() == "sketch" and not self.t_prompt.get("1.0", "end").strip():
            self._status(models.NO_STYLE, error=True)       # Sketch to image without a style or text: no run (plan B, 10.11.)
            return
        try:
            req = self._request()
        except (tk.TclError, ValueError) as e:
            self._status(f"Invalid value: {e}", error=True)
            return
        rest = self._variants_rest(req)
        if rest:
            req.variants = 1        # ×n: this picture now, the others as jobs of their own in the queue (user 23.11.)
        req.preset = self._layer_prefix()
        if req.preset:   # running number per model and function, kept between sessions
            runs = dict(self.state.get("runs", {}))
            req.run_no = int(runs.get(req.preset, 0)) + 1
            runs[req.preset] = req.run_no
            req.group_name = f"{SHORT_MODES.get(self.v_mode.get(), self.v_mode.get())} {req.run_no}"   # "Fill Selection 3"
            self.state["runs"] = runs
        self._save_state(req)
        self._history_begin(req)
        if getattr(self, "_fprev_on", False):   # the run ends the feather preview first (Bridge._run): the button follows
            if getattr(self, "_fprev_after", None):
                self.root.after_cancel(self._fprev_after)
                self._fprev_after = None
            self._fprev_on, self._fprev_dirty = False, None
            self.b_fprev.configure(text="Show feather")
        self._running = True
        self._status_stale = True      # the first progress of this run clears what the status line said before (_poll)
        self._run_req_mode = "remove" if req.remove else req.mode     # Undo after it: a history snapshot (not Upscale)
        self._other_pc = self._other_photocraft()       # a second PhotoCraft open: the hint after the run (gui.py, 16.11.)
        self._run_label = self._model_label()           # the bar names the model of this run, not one picked meanwhile (window test E)
        self._run_fn = self._fn_label()                 # the queue window's Function of this run (window test 23.11.)
        self._run_wmode = self.v_mode.get()             # only this function may wait in the queue meanwhile (user 23.11., D)
        self._run_doc, self._run_t0 = "", time.time()   # its Document (set by the worker) and start: the row stays when it ends
        self._run_placed = None                         # the result layer of this run, for Undo (set by the worker)
        self.w_variants.configure(state="disabled")     # part of Generate: grey while a run is on
        self._sync_history_buttons()
        self._go_stop(True)
        self.bridge.reset_cancel_all()
        self._reset_progress()

        def progress(f, msg, phase="", phase_fraction=-1.0, elapsed=0.0):
            self.events.put(("progress", (f, msg, phase, phase_fraction, elapsed)))
        self.bridge.on_preview = lambda im: self.events.put(("preview", im))

        runs = sweep_requests(req, parse_list(self.v_cmp_res.get(), int), parse_list(self.v_cmp_ctx.get(), float))
        if len(runs) > 1:
            if req.params.seed is None or req.params.seed < 0:
                req.params.seed = random.randint(0, 10**8 - 1)   # one seed for the whole series: only the value differs

        # runs that follow one another (variants of Upscale / Refine, a comparison): Generate says "Stop run", "Stop batch" beside it
        seq = (req.mode in SCALE_MODES or req.one_by_one) and int(req.variants) > 1
        if len(runs) > 1 or seq:
            self._show_stop_all(True)
        # ×n one after the other: the queue window shows a row per variant at once (user 24.11. evening, choice C)
        self._run_seq = int(req.variants) if seq and len(runs) == 1 else 0
        self.bridge.seq_rows = []
        self._seq_base = None          # where the block of variant rows stands in the queue window (gui_queuewin.py)

        def work():
            jobqueue.qlog(self.bridge, "q_direct_begin")
            try:
                self._run_doc = self._active_doc_name()      # the queue window's Document of this run (user 23.11.)
            except Exception:
                pass
            try:
                total = docs = 0
                res = None
                t_start = time.monotonic()
                for k, rq in enumerate(runs):
                    if self.bridge.cancel_all_requested():
                        raise Cancelled()
                    if len(runs) > 1:
                        self.events.put(("progress", (0.0, f"Comparison {k + 1}/{len(runs)}: {rq.label}", "prepare", -1.0, 0.0)))
                    try:
                        res = self.bridge.run(rq, progress)
                    except Cancelled:
                        if len(runs) == 1 or self.bridge.cancel_all_requested():
                            raise
                        continue          # "Stop" ends this comparison run only
                    total += len(res["layers"])
                    docs += int(res.get("documents") or 0)      # Upscale: new documents, no layers
                if res is not None and len(runs) == 1 and res.get("layers"):
                    # Undo hides this result like a queued one (user 23.11.: "jedes undo blendet die zuletzt generierte
                    # ebene aus"); a comparison series keeps the snapshot
                    self._run_placed = {"doc": self._run_doc, "layer": res.get("group") or res["layers"][0],
                                        "name": f"{req.preset} #{req.run_no}" if req.preset else "",
                                        "scribble": res.get("scribble_layer")}
                if res is None:
                    raise Cancelled()
                self.events.put(("vgl", res.get("vgl", "")))
                self.events.put(("seed", res.get("seed")))
                self.events.put(("lastrun", {"mode": "remove" if req.remove else req.mode, "seed": res.get("seed"),
                                             "doc": self._active_doc_name()}))      # Save image names the file after it (gui.py)
                seam = res.get("seam")     # the seam correction's A/B: the tone jump of #1 in levels, before → after
                seam_text = f" · seam {seam[0]:.0f} → {seam[1]:.0f}" if seam else ""
                # how Scribble on photo found the scribble is no longer in the line (user 10.11.: it made the line too long, cut off)
                self.events.put(("done", f"Done · seed {res['seed']} · {made_text(total, docs)}{seam_text} · {duration_text(time.monotonic() - t_start)}"))
            except Cancelled:
                self.events.put(("done", "Cancelled."))
            except (BridgeError, ComfyError, PhotoCraftError, ValueError, OSError) as e:
                self.events.put(("done", f"Error: {e}"))
            except Exception as e:  # unexpected – show it instead of dying silently
                self.events.put(("done", f"Unexpected error: {type(e).__name__}: {e}"))
            finally:
                if shared is not None and not shared["done"].is_set():
                    self.bridge.on_taken = None     # no picture (an error before the export): the variants export their own
                    shared["done"].set()
                keep = getattr(self, "_run_retry", None)
                if keep is not None and self.bridge.on_taken is keep.get("capture"):
                    self.bridge.on_taken = None     # never let a queue job's export land in this run's ↻
        self._run_rest_bid = None          # the variants of this run in the queue: Stop batch ends them with it
        shared = None
        if rest:        # queued before the run starts: begin() of the check must not meet the run's own (Scribble layer)
            self._direct_pending = True         # the queue waits for this run (gate in gui.py)
            if req.mode not in jobqueue.NO_PICTURE_MODES:
                # the variants take the picture this run exports, not one of their own: the run waited for that second
                # export (window test 23.11. evening: "wenn ich 2 varianten starte, dann starten sie erst nach einer pause")
                shared = {"done": threading.Event(), "pic": None, "index": None, "name": ""}

                def taken(pic, index, name, shared=shared):
                    shared.update(pic=pic.copy(), index=index, name=name)
                    shared["done"].set()
                self.bridge.on_taken = taken
            self._run_rest_bid = self._enqueue(rest, shared=shared)
            if not self._run_rest_bid and shared is not None:
                self.bridge.on_taken = None
            if self._run_rest_bid:      # ×3: this run is 1/3, its queued pictures 2/3 and 3/3 (window test 23.11. late)
                self._rest_of = dict(getattr(self, "_rest_of", {}) or {})
                self._rest_of[self._run_rest_bid] = rest + 1
                self._run_fn = f"{self._run_fn} · 1/{rest + 1}"
        self._run_retry = keep = self._retry_keep(req, runs)
        if keep is not None and req.mode not in jobqueue.NO_PICTURE_MODES:
            prev = self.bridge.on_taken         # the variants' hand-over (above) still gets the picture

            def capture(pic, index, name, keep=keep, prev=prev):
                keep.update(pic=pic.copy(), index=index, name=name)
                if prev is not None:
                    prev(pic, index, name)
            self.bridge.on_taken = capture
            keep["capture"] = capture
        try:
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()
        finally:
            self._direct_pending = False
        self._ahead_start()         # "N jobs of others ahead" while the job waits at ComfyUI (gui_batch.py)

    def _retry_keep(self, req, runs) -> dict | None:
        """What ↻ in the queue window needs to send a cancelled or failed direct run again (window test 23.11. late: after
        "Stop batch" only the queued picture had ↻): its settings and, filled by the run's export, its picture with the
        document. Only for a function that can wait in the queue, one picture, no comparison series; None otherwise."""
        try:
            if self._queue_refusal() or len(runs) != 1 or int(req.variants or 1) != 1:
                return None
            m = self._model()
            return {"req": copy.deepcopy(req), "label": self._fn_label(), "model": m.label if m else "",
                    "pic": None, "index": None, "name": ""}
        except Exception:
            return None

    def _own_retry(self, d: dict) -> bool:
        """↻ on a row of a direct run that was cancelled or failed: the same settings and the same picture of the same
        document wait in the queue as a new job (as ↻ on a queued picture does). Text to image takes the document in front."""
        keep = d.get("retry")
        if not keep:
            return False
        req = copy.deepcopy(keep["req"])
        runs = dict(self.state.get("runs", {}))
        if req.preset:          # a new running number, like every run ("Edit 8")
            req.run_no = int(runs.get(req.preset, 0)) + 1
            runs[req.preset] = req.run_no
            req.group_name = f"{SHORT_MODES.get(req.mode, req.mode)} {req.run_no}"
        shared = None
        if keep.get("pic") is not None:
            shared = {"done": threading.Event(), "pic": keep["pic"].copy(), "index": keep.get("index"), "name": keep.get("name", "")}
            shared["done"].set()
        spec = jobqueue.BatchSpec(request=req, source=jobqueue.SOURCE_ACTIVE, dry_run=False, kind=jobqueue.K_GENERATE,
                                  copies=1, label=keep["label"], model=keep["model"], shared=shared)
        try:
            bid = self.runner.start_batch(spec)
        except (ValueError, BridgeError) as e:
            self._status(str(e), error=True)
            return False
        self.state["runs"] = runs
        self._batch_mine = getattr(self, "_batch_mine", set()) | {bid}
        d["retry"] = None           # its ↻ is used: the new job has its own row
        self._status(f"Added to the queue: {keep['label']}.")
        self._batch_sync()
        self._queue_dirty()
        return True

    def _variants_rest(self, req) -> int:
        """A direct Generate with ×n of a function that can wait in the queue (user 23.11., choice A: "einzelne Einträge,
        die ich einzeln abbrechen kann"): how many pictures go to the queue after the first one (n - 1); 0 = one run as
        before (×1, Fill, Remove, Expand, Multi Edit with BBOX, a comparison over several values)."""
        try:
            n = int(req.variants or 1)
            if n < 2 or self._queue_refusal():
                return 0
            if len(sweep_requests(req, parse_list(self.v_cmp_res.get(), int), parse_list(self.v_cmp_ctx.get(), float))) > 1:
                return 0
        except (tk.TclError, ValueError, AttributeError):
            return 0
        return n - 1

    # ---------- Undo / Redo: result layers of queued runs and the history snapshot (docs/plan/generate-queue.md, choice B) ----------
    #
    # Two stacks, newest last. An entry is {"kind": "layers", "doc", "layer", "name"} (a queued result: Undo hides its layer or
    # group, Redo shows it again; no limit) or {"kind": "snap"} (where the history snapshot of a run of this window stands:
    # Bridge.undo_last / redo_last as before, one step). With no entry the snapshot rule of 18.11. decides alone (_last_step and
    # the bridge), as after a batch of the ⋯ menu.

    def _stacks(self) -> tuple[list, list]:
        if not hasattr(self, "_undo_stack"):
            self._undo_stack, self._redo_stack = [], []
        return self._undo_stack, self._redo_stack

    @staticmethod
    def _is_layers(e) -> bool:
        return isinstance(e, dict) and e.get("kind") == "layers"

    def _undo_new_run(self, mode: str, placed: dict | None = None):
        """A run of this window is done: its snapshot is the newest step back (Upscale takes none: a new document); older
        snapshot entries no longer count (the bridge keeps one), and the redo chain ends. placed: the result layer of a
        function that can wait in the queue (user 23.11.), and of Fill and Remove (user 23.11. late: "wenn ich nach remove
        "undo" mache, wird die jüngste ebene nicht ausgeblendet sondern gelöscht"): Undo hides it like a queued result, no
        snapshot step; Expand (it changes the canvas) and Cut out keep the snapshot (decision 22.11.)."""
        undo, redo = self._stacks()
        undo[:] = [e for e in undo if self._is_layers(e)]
        redo.clear()
        self._run_placed = None
        if placed and placed.get("layer") is not None and mode in jobqueue.QUEUE_MODES + UNDO_HIDE_MODES:   # run modes:
            # Multi Edit, Sketch and Scribble run as "edit" and keep this Undo
            self._undo_push_layers(placed)
            return
        if mode != "upscale":
            undo.append({"kind": "snap"})

    def _undo_push_layers(self, d: dict):
        """A queued run placed its result layer (jobqueue "batch-placed"): Undo hides it next; the redo chain ends, also a
        snapshot's redo (it would bring back a state without this layer)."""
        undo, redo = self._stacks()
        entry = {"kind": "layers", "doc": str(d.get("doc") or ""), "layer": d.get("layer"), "name": str(d.get("name") or "")}
        if d.get("scribble") is not None:       # a direct Scribble on photo: Undo shows its scribble layer again
            entry["scribble"] = d.get("scribble")
        undo.append(entry)
        redo.clear()
        if getattr(self, "_last_step", None) == "undo":
            self._last_step = "stale"
        self._sync_history_buttons()

    def undo_edit(self):
        self._history_go("undo")

    def redo_edit(self):
        self._history_go("redo")

    def _history_locked(self) -> bool:
        """A run or a batch is on: Undo and Redo are locked (user 24.11.)."""
        try:
            return bool(getattr(self, "_running", False) or self._batch_busy())
        except Exception:
            return bool(getattr(self, "_running", False))

    def _history_grey_click(self, e, step: str):
        """A click on the grey Undo or Redo (a grey ttk button calls no command): during a run the status line says why,
        like the key does (user 25.11., "Klick + Tooltip"). Grey for another reason (nothing to undo, a step on): silent."""
        b = e.widget
        try:
            if not b.instate(["disabled"]) or not (0 <= e.x < b.winfo_width() and 0 <= e.y < b.winfo_height()):
                return
        except tk.TclError:
            return
        if self._history_locked():
            self._history_go(step)

    def _history_go(self, step: str):
        on = self._history_locked()
        if on:          # also by a key while the buttons are grey (user 24.11.: Undo and Redo locked during a run)
            if getattr(self, "_running", False) or getattr(self.runner, "only_generate", False) or not self._blocked_by_batch():
                self._status(CUT_NOT_IN_RUN)       # (a batch of the ⋯ menu says so itself, _blocked_by_batch)
            return
        undo, redo = self._stacks()
        stack = undo if step == "undo" else redo
        top = stack[-1] if stack else None
        if not self._is_layers(top):
            self._history_step(self.bridge.undo_last if step == "undo" else self.bridge.redo_last, step)
            return
        if self.worker and self.worker.is_alive():
            return
        self._history_busy = True
        self._sync_history_buttons()
        bridge = self.bridge

        def work():
            try:
                res = bridge.set_result_visible(top, step == "redo")
                self.events.put(("undo-layer", (step, top, res)))
            except (BridgeError, PhotoCraftError) as e:
                self.events.put(("note-error", f"Error: {e}"))
            except Exception as e:
                self.events.put(("note-error", f"Unexpected error: {type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _undo_layer_done(self, step: str, entry: dict, res: str):
        """The answer of a layer step (the worker): the entry moves to the other stack, or goes when it can't be used."""
        undo, redo = self._stacks()
        src, dst = (undo, redo) if step == "undo" else (redo, undo)
        if src and src[-1] is entry:
            src.pop()
        name, doc = entry.get("name") or "the result", entry.get("doc") or "?"
        error = res in ("gone", "closed")
        if res == "ok":
            dst.append(entry)
            msg = f"Undo: “{name}” is hidden." if step == "undo" else f"Redo: “{name}” is visible again."
        elif res == "already":
            msg = f"“{name}” was {'hidden' if step == 'undo' else 'visible'} already: nothing changed."
        elif res == "gone":
            msg = f"“{name}” is no longer in “{doc}” (deleted or merged): nothing to {'hide' if step == 'undo' else 'show'}."
        else:
            msg = f"“{doc}” is not open any more: “{name}” stays as it is."
        self._history_busy = False
        self._status(msg, error=error)
        self._sync_history_buttons()
        self._batch_sync()

    def _undo_snap_done(self, step: str):
        """A snapshot step worked: its entry moves to the other stack."""
        undo, redo = self._stacks()
        src, dst = (undo, redo) if step == "undo" else (redo, undo)
        if src and not self._is_layers(src[-1]):
            src.pop()
        dst.append({"kind": "snap"})

    def _history_step(self, fn, step: str | None = None):
        if (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        self._history_busy = True
        self._sync_history_buttons()
        step = step or ("undo" if fn == self.bridge.undo_last else "redo")

        def work():
            try:
                note = fn()
                self._last_step = step          # only after a step that worked: a failed one ("note-error") leaves it
                self.events.put(("undo-snap", step))
                self.events.put(("note", note))
            except (BridgeError, PhotoCraftError) as e:
                self.events.put(("note-error", f"Error: {e}"))
            except Exception as e:
                self.events.put(("note-error", f"Unexpected error: {type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    # ---------- the last runs (the clock in the header, history.py) ----------

    def _history_begin(self, req):
        """Generate was clicked: keep every setting of the window for the history; written once the run is done."""
        try:
            settings = self._collect()
        except (tk.TclError, ValueError, TypeError):
            self._hist_run = None
            return
        m = self._model()
        title = req.group_name or SHORT_MODES.get(self.v_mode.get(), self.v_mode.get())
        self._hist_run = runhistory.entry(title, m.label if m else "", settings,
                                          llm=settings.get("prompt", "") if self._written_active() else "")   # loads back without the upsampler

    def _history_end(self, ok: bool):
        """The run is over: a finished one goes in front of the last runs; a cancelled or failed one is left out."""
        e, self._hist_run = getattr(self, "_hist_run", None), None
        if ok and e:
            runhistory.add(cfgmod.HISTORY_FILE, e)

    def _history_rows(self) -> list[tuple[str, object, str]]:
        """The rows of the list: "Erase history" first, then the last 20 runs, newest first (listpopup.py kinds)."""
        runs = runhistory.load(cfgmod.HISTORY_FILE)
        rows = [("Erase history", self.erase_history, "action" if runs else "disabled")]
        rows += [(runhistory.label(e), lambda e=e: self.load_history(e), "item") for e in runs]
        if not runs:
            rows.append(("No runs yet.", None, "disabled"))
        return rows

    def _history_menu(self):
        """"History" in the ⋯ menu (the clock in the footer until 24.11. evening): the list of the last runs above the menu
        button; with the mouse wheel and a scroll bar when it is long. Picked again while it is open, it closes."""
        old, self._history_popup = self._history_popup, None
        if old is not None and not old.closed:
            old.close()
            return
        self._history_popup = ListPopup(self.root, self.b_menu, self._history_rows(), scale=getattr(self, "ui", 1.0), above=True)

    def erase_history(self):
        runhistory.clear(cfgmod.HISTORY_FILE)
        self._status("History erased.")

    def load_history(self, e: dict):
        """A run from the clock's menu back into the window: every setting, a new seed, the text model's prompt with Enhance
        off when there was one (user 30.10.). Nothing starts; Ctrl+Z in the prompt field brings the old text back."""
        s = runhistory.settings_to_load(e)
        prompt, negative = str(s.pop("prompt", "")), str(s.pop("negative", ""))
        notes = self._apply_settings(s)
        if str(self.t_prompt.cget("state")) == "disabled":      # Remove object: the field is empty, the text is kept aside
            self._prompt_kept = prompt
        else:
            self.t_prompt.edit_separator()
            self.t_prompt.delete("1.0", "end")
            self.t_prompt.insert("1.0", prompt)
            self.t_prompt.edit_separator()
        self.t_neg.delete("1.0", "end")
        self.t_neg.insert("1.0", negative)
        # Sketch: the prompt the upsampler wrote runs as it is, not expanded a second time (user 10.11., way A)
        self._written_for = self.v_model.get() if (e.get("llm") and self.v_mode.get() in ("sketch", "scribble")) else ""
        self._update_prompt_hint()
        name = e.get("title") or "the run"
        if notes:
            self._status(f"Loaded “{name}”, but: {', '.join(notes)}.", error=True)
        else:
            self._status(f"Loaded “{name}” with a new seed. Click Generate to run it.")

    # ---------- feather preview ----------

    def toggle_feather_preview(self, show: bool | None = None):
        """Show feather / Hide feather: the bridge shows the soft edge as Quick Mask in PhotoCraft and brings the user's
        selection back afterwards. Runs in the worker like undo (PhotoCraft is busy for a moment)."""
        show = (not getattr(self, "_fprev_on", False)) if show is None else show
        if self._blocked_by_batch():
            return
        if self.worker and self.worker.is_alive():
            if getattr(self, "_fprev_on", False):
                self._fprev_dirty = show   # a shown preview is busy: done once the worker is free (see _feather_done)
            return
        try:
            req = self._request()
        except (tk.TclError, ValueError) as e:
            self._status(f"Invalid value: {e}", error=True)
            return
        self._fprev_dirty = None
        self.b_fprev.configure(state="disabled")

        def work():
            try:
                msg = self.bridge.show_feather(req) if show else self.bridge.hide_feather()
                self.events.put(("feather", (self.bridge.feather_shown, msg, False)))
            except (BridgeError, PhotoCraftError) as e:
                self.events.put(("feather", (self.bridge.feather_shown, f"Error: {e}", True)))
            except Exception as e:
                self.events.put(("feather", (self.bridge.feather_shown, f"Unexpected error: {type(e).__name__}: {e}", True)))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _refresh_feather_preview(self):
        """A setting changed while the preview is shown: show it anew, once the slider has stopped for a moment."""
        if not getattr(self, "_fprev_on", False):
            return
        if getattr(self, "_fprev_after", None):
            self.root.after_cancel(self._fprev_after)
        self._fprev_after = self.root.after(400, lambda: (setattr(self, "_fprev_after", None),
                                                          self.toggle_feather_preview(show=True)))

    def _feather_done(self, shown: bool, msg: str, error: bool):
        self._fprev_on = shown
        self.b_fprev.configure(text="Hide feather" if shown else "Show feather", state="normal")
        if msg:
            self._status(msg, error=error)
        pending, self._fprev_dirty = getattr(self, "_fprev_dirty", None), None
        if pending is not None and shown:    # the slider moved (show anew) or Hide was clicked while it was busy
            self.toggle_feather_preview(show=pending)

    def _set_last_seed(self, seed):
        """The seed of the run that just finished: the icon beside the seed field can put it back (user 1.11.)."""
        try:
            self._last_seed = int(seed)
        except (TypeError, ValueError):
            return
        self.b_last_seed.configure(state="normal")

    def use_last_seed(self):
        """The icon beside the seed field: the next run uses the seed of the last one (same settings, same picture)."""
        if getattr(self, "_last_seed", None) is not None:
            self.v_seed.set(self._last_seed)

    def _cutout_ok(self, key: str) -> bool:
        """False only when ComfyUI was read and the model's file is not there; not read yet (or not reachable): the click tries."""
        inv = getattr(self, "inv", None)
        return inv is None or inv.has(workflows.cutout_model(key)[2])

    def _cutout_available(self) -> bool:
        """At least one cut-out model can run (the scissors is greyed out only when none can)."""
        return any(self._cutout_ok(m[0]) for m in workflows.CUTOUT_MODELS)

    def _cutout_rows(self) -> list[tuple[str, object, str]]:
        """The menu of the scissors (user 6.11.): BiRefNet, RMBG-2.0, Both; an entry whose file is missing is greyed out."""
        rows = []
        for key, label, _file, _wf in workflows.CUTOUT_MODELS:
            ok = self._cutout_ok(key)
            rows.append((label if ok else f"{label} (file missing)", (lambda k=key: self.cut_background((k,))) if ok else None,
                         "item" if ok else "disabled"))
        both = all(self._cutout_ok(k) for k in workflows.CUTOUT_BOTH)
        rows.append((CUTOUT_BOTH_LABEL if both else f"{CUTOUT_BOTH_LABEL} (file missing)",
                     (lambda: self.cut_background(workflows.CUTOUT_BOTH)) if both else None, "item" if both else "disabled"))
        return rows

    def _cutout_menu(self):
        """A click on the scissors opens the list of models above it (every time, user 6.11.); a second click closes it."""
        if self._something_runs():         # no Cut out during a run or a queue job (user 23.11.)
            self._status(CUT_NOT_IN_RUN)
            return
        old, self._cut_popup = getattr(self, "_cut_popup", None), None
        if old is not None and not old.closed:
            old.close()
            return
        if not self._cutout_available():
            self._status(CUTOUT_MISSING, error=True)
            return
        self._cut_popup = ListPopup(self.root, self.b_cut, self._cutout_rows(), scale=getattr(self, "ui", 1.0), above=True)

    def cut_background(self, models: tuple = ("birefnet",)):
        """The scissors in the footer (user 5.11.; the model menu 6.11.): a copy of the visible picture with a layer mask that hides
        its background (17.11.), as a new layer on top (Bridge.remove_background_layer, ComfyUI's BiRefNet and/or RMBG-2.0; Both: two layers, RMBG-2.0 above). Runs like a
        generation: progress bar, Cancel, Undo afterwards."""
        if (self.worker and self.worker.is_alive()) or self._blocked_by_batch():
            return
        models = tuple(models)
        missing = [workflows.cutout_model(k)[2] for k in models if not self._cutout_ok(k)]
        if missing:
            self._status(f"{', '.join(missing)} is missing (optional file): download it in the gear window, Models, Additional.", error=True)
            return
        self._running = True
        self._status_stale = True      # the first progress of this run clears what the status line said before (_poll)
        self._run_req_mode = "cut"          # one snapshot, like a run: Undo afterwards
        self.w_variants.configure(state="disabled")
        self._sync_history_buttons()
        self._go_stop(True)
        self.bridge.reset_cancel_all()
        self._reset_progress()

        def progress(f, msg, phase="", phase_fraction=-1.0, elapsed=0.0):
            if phase == "image":        # BiRefNet is no image model run: say what happens (user 5.11.), not "<model> is generating"
                phase, msg = "stage", "Removing background"
            self.events.put(("progress", (f, msg, phase, phase_fraction, elapsed)))

        def work():
            t_start = time.monotonic()
            try:
                self.bridge.remove_background_layer(progress, models)
                what = "new layer on top" if len(models) == 1 else f"{len(models)} new layers on top"
                self.events.put(("done", f"Done · background removed, {what} · {duration_text(time.monotonic() - t_start)}"))
            except Cancelled:
                self.events.put(("done", "Cancelled."))
            except (BridgeError, ComfyError, PhotoCraftError, ValueError, OSError) as e:
                self.events.put(("done", f"Error: {e}"))
            except Exception as e:
                self.events.put(("done", f"Unexpected error: {type(e).__name__}: {e}"))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _update_cut_button(self):
        """The scissors is greyed out while no model file is there; its tooltip then names the files."""
        b = getattr(self, "b_cut", None)
        if b is None:
            return
        ok = self._cutout_available()
        busy = self._something_runs()
        b.configure(state="normal" if ok and not busy else "disabled")
        self.tt_cut.text = CUTOUT_TIP + ("\n\n" + CUTOUT_MISSING if not ok else "\n\n" + CUT_NOT_IN_RUN if busy else "")

    def _cut_lock_sync(self):
        """A run or a queue job starts or ends: the scissors and the Cut out icons of the slots follow (grey while
        something runs, user 23.11.: "während eines laufs soll kein cutout möglich sein"); an open scissors menu closes."""
        on = self._something_runs()
        pop = getattr(self, "_cut_popup", None)
        if on and pop is not None and not pop.closed:
            pop.close()
            self._cut_popup = None
        self._update_cut_button()
        if on == getattr(self, "_cut_locked", False):
            return              # the slots are redrawn only when it changes
        self._cut_locked = on
        try:
            self._refs_redraw()
        except Exception:
            pass

    def stop(self):
        """Stop: the run, or the text model while it describes a picture (the LLM and Describe buttons, the slots' Describe);
        while a batch of the ⋯ menu is on, its picture at ComfyUI now (the next one follows, user 20.11.)."""
        if (self.worker and self.worker.is_alive()) or getattr(self, "_describing", False) or getattr(self, "_ref_busy", None):
            self.bridge.cancel()
            self._status("Cancelling…")
        elif self._batch_busy():
            job = self.runner.running_job
            if job:
                self.runner.cancel(job["id"])
                self._status("Cancelling…")
            else:
                self._status("No picture of the batch is running right now.")

    def _stop_click(self, batch: bool = False):
        """A click on the grey "Stop" / "Stop run" (batch=False) or "Stop batch" (user 20.11.): taken only STOP_GUARD_S after
        the run started, so a double click on Generate does not stop the run it just started. The keys stop at once."""
        if time.monotonic() - getattr(self, "_stop_armed", 0.0) < STOP_GUARD_S:
            return
        (self.stop_all if batch else self.stop)()

    def _go_stop(self, on: bool):
        """Generate during a run (user 20.11., no Stop button any more): grey, "Stop" (or "Stop run" while "Stop batch" is
        shown), a click stops; afterwards blue "Generate" again. A text model run (Describe) makes it "Stop" too; it stays
        "Stop" while a run or a text model run is still on."""
        self._cut_lock_sync()
        if not on and (getattr(self, "_running", False) or getattr(self, "_describing", False)
                       or getattr(self, "_ref_busy", None) or self._batch_keeps_stop()):
            return
        row = self._queue_row_kind() if on else ""
        if row:
            self._go_queue_row(locked=row == "locked")
            return
        self._go_queueing = False
        self._grid_stop_run(False)
        self._grid_stop_all(bool(getattr(self, "_stop_all_wanted", False)) or (on and self._batch_busy()))
        batch = on and self.b_stop_all.winfo_manager() == "grid"
        try:
            if on:
                if not getattr(self, "_go_stopping", False):
                    self._stop_armed = time.monotonic()       # the double-click guard starts when Generate turns into Stop
                self.b_go.configure(text=GO_STOP_RUN_TEXT if batch else GO_STOP_TEXT, style="GoStop.TButton",
                                    command=self._stop_click, state="normal")
                if self.w_variants.winfo_manager():
                    self.w_variants.grid_remove()           # the variants piece is gone while a run is on (user 20.11.)
            else:
                self.b_go.configure(text="Generate", style="Accent.TButton", command=self.generate, state="normal")
                if not self.w_variants.winfo_manager():
                    self.w_variants.grid()
                if not getattr(self, "_running", False):
                    self.w_variants.configure(state="normal")       # grey in the locked queue row (user 23.11.)
        except (tk.TclError, AttributeError):
            return
        tt = getattr(self, "tt_go", None)
        if tt is not None:
            tt.text = (GO_STOP_RUN_TIP if batch else GO_STOP_TIP) if on else GO_TIP
        self._go_stopping = on
        self._fit_go_row()

    def _batch_keeps_stop(self) -> bool:
        """A batch of the ⋯ menu is still on: Generate stays "Stop run" when a Describe ends meanwhile (review 21.11.; it was
        blue and clickable until the next _batch_sync)."""
        try:
            return bool(getattr(self, "_batch_stopping", False) and self._batch_busy())
        except Exception:
            return False

    def _show_stop_all(self, on: bool):
        """"Stop batch" beside Generate (which says "Stop run" then); the row shares out its width anew, so it still fits
        the window with Undo and Redo. While Generate is "Add to queue" it is shown anyway."""
        self._stop_all_wanted = bool(on)
        self._grid_stop_all(on or getattr(self, "_go_queueing", False))
        if getattr(self, "_go_stopping", False):
            self._go_stop(True)          # the text follows: "Stop run" with "Stop batch", "Stop" without
        self._fit_go_row()

    def _grid_stop_all(self, on: bool, gap: int = 6):
        """gap: px before it (before the display scaling); 4 in the queue row, where four buttons share the width."""
        try:
            if on:
                if self.b_stop_all.winfo_manager() != "grid":
                    self.b_stop_all.grid(row=0, column=GO_COL_STOP_ALL, sticky="nsew")
                self.b_stop_all.grid_configure(padx=(self._keep(gap), 0))
            elif self.b_stop_all.winfo_manager():
                self.b_stop_all.grid_forget()
        except (tk.TclError, AttributeError):
            pass

    def _grid_stop_run(self, on: bool):
        b = getattr(self, "b_stop_run", None)
        if b is None:
            return
        try:
            if on and b.winfo_manager() != "grid":
                b.grid(row=0, column=GO_COL_STOP_RUN, sticky="nsew", padx=(self._keep(QUEUE_ROW_GAP_PX), 0))
            elif not on and b.winfo_manager():
                b.grid_forget()
        except (tk.TclError, AttributeError):
            pass

    def _queue_row_kind(self) -> str:
        """The Generate row while something runs: "open" (the function can wait in the queue), "locked" (Fill, Remove,
        Expand, Multi Edit with BBOX: the same row with a grey "Add to queue", user 23.11.), "" (nothing runs)."""
        try:
            if not self._something_runs():
                return ""
            return "locked" if self._queue_refusal() else "open"
        except (tk.TclError, AttributeError):
            return ""

    def _go_queue_row(self, locked: bool = False):
        """Generate during a run (user 22.11., Variant 1): blue "Add to queue", the variants piece (×n = n jobs), then grey
        "Stop run" and "Stop batch". locked: the function can't wait in the queue (user 23.11., choice A): the same row,
        "Add to queue" and ×n grey; the status line says why when the function is picked (_go_follow)."""
        try:
            if not getattr(self, "_go_stopping", False):
                self._stop_armed = time.monotonic()       # a double click on Generate must not queue a second run
            self.b_go.configure(text=ADD_QUEUE_TEXT, style="Accent.TButton", command=self.generate,
                                state="disabled" if locked else "normal")
            if not self.w_variants.winfo_manager():
                self.w_variants.grid()
            self.w_variants.configure(state="disabled" if locked else "normal")
            self._grid_stop_run(True)
            self._grid_stop_all(True, QUEUE_ROW_GAP_PX)
        except (tk.TclError, AttributeError):
            return
        tt = getattr(self, "tt_go", None)
        if tt is not None:
            tt.text = (self._queue_refusal() or ADD_QUEUE_TIP) if locked else ADD_QUEUE_TIP
        self._go_stopping = self._go_queueing = True
        self._fit_go_row()

    def _go_follow(self):
        """Another function or model while a run is on: the row becomes "Add to queue" or "Stop" (Fill, Remove, Expand)."""
        if getattr(self, "_go_stopping", False) and not getattr(self, "_go_follow_job", None):
            def later():
                self._go_follow_job = None
                if getattr(self, "_go_stopping", False):
                    self._go_stop(True)
                    self._batch_sync_soon()
                    if self._queue_row_kind() == "locked":     # why "Add to queue" is grey (user 23.11.)
                        self._status(self._queue_refusal())
            try:
                self._go_follow_job = self.root.after_idle(later)
            except (tk.TclError, AttributeError):
                self._go_follow_job = None

    def _fit_go_row(self):
        """The Generate row over the full width (user 18.11., decisions 1a and 3): Generate and the variants piece together
        are half the row less the tabs' padding (user 18.11.: as wide as the tab "Edit canvas"; since 20.11. the Edit tabs are
        a list and never shown, so the half row is what counts), the
        variants piece at VARIANTS_GROW_MAX of its natural width, Generate the rest; what is left goes to the empty column
        before Undo. Undo and Redo are squares as high as Generate. Where the row is short ("Stop batch" shown, a large
        scale), Generate, then the variants piece give room back, down to their natural width."""
        bf = getattr(self, "f_go", None)
        if bf is None or not hasattr(self, "b_redo"):
            return

        def pad(w) -> int:
            """The padding a button has in its grid cell (both sides): a column's minsize includes it, and spacing.py may
            have scaled a gap given at build time, so it is read back rather than worked out."""
            v = w.grid_info().get("padx", 0)
            v = v if isinstance(v, (tuple, list)) else str(v).split() or [0]
            return sum(int(float(str(x))) for x in v) if len(v) > 1 else 2 * int(float(str(v[0])))

        try:
            total = int(bf.winfo_width())
            side = int(self.b_go.winfo_reqheight())
            n_go, n_var = (int(w.winfo_reqwidth()) for w in (self.b_go, self.w_variants))
            p_go, p_var = (pad(w) for w in (self.b_go, self.w_variants))
            if not self.w_variants.winfo_manager():     # hidden during a run (user 20.11.): Generate takes its room
                n_var = p_var = 0
            tabs = getattr(self, "rb_edtabs", None)          # the tabs' padding (refslots.py), read back once they exist
            p_tab = pad(tabs["edit"]) if tabs and tabs["edit"].winfo_manager() == "grid" else 2 * EDTAB_PADX
            tab_w = 0           # the tab "Edit canvas" as it really is on screen (user 19.11.: the pair was a little narrower)
            if tabs and tabs["edit"].winfo_ismapped() and tabs["edit"].winfo_width() > 1:
                tab_w = int(tabs["edit"].winfo_width())
                if not getattr(tabs["edit"], "_pcc_go_bound", False):        # the tab changes its width: the row follows
                    tabs["edit"].bind("<Configure>", lambda e: self._fit_go_row(), add="+")
                    tabs["edit"]._pcc_go_bound = True
            pair = pad(self.b_redo)
            fixed = self._px(GO_GAP_MIN_PX) + 2 * side + pair      # beside Generate and the variants piece
            for b in (self.b_stop_all, getattr(self, "b_stop_run", None)):
                if b is not None and b.winfo_manager() == "grid":
                    fixed += pad(b) + int(b.winfo_reqwidth())
        except (tk.TclError, AttributeError, ValueError, KeyError, TypeError):      # TypeError: no real Tk (the test stubs)
            return
        key = (total, side, n_go, n_var, p_tab, tab_w, fixed)
        if total <= 1 or key == getattr(self, "_go_row_key", None):
            return
        self._go_row_key = key
        var = n_var + int(n_var * (VARIANTS_GROW_MAX - 1)) + p_var       # the variants column (its padding included)
        go = max(n_go + p_go, (tab_w or (total - 2 * p_tab) // 2) - var)  # Generate + variants = the tab "Edit canvas"
        short = max(0, go + var + fixed - total)                           # the row is too short: Generate, then variants give back
        cut = min(short, max(0, go - n_go - p_go))
        go, short = go - cut, short - cut
        var -= min(short, max(0, var - n_var - p_var))
        bf.grid_columnconfigure(0, minsize=go)
        bf.grid_columnconfigure(1, minsize=var)
        bf.grid_columnconfigure(GO_COL_GAP, minsize=self._px(GO_GAP_MIN_PX))
        bf.grid_columnconfigure(GO_COL_UNDO, minsize=side)
        bf.grid_columnconfigure(GO_COL_UNDO + 1, minsize=side + pair)
        bf.grid_rowconfigure(0, minsize=side)

    def _sync_history_buttons(self):
        """Undo and Redo (user 18.11., decision 2a): grey while a run, an Undo/Redo step or a batch is on; otherwise one of
        them is blue at a time: after a run Undo, after Undo Redo, after Redo Undo again; at the start both grey. The bridge
        has to agree too (can_undo / can_redo): undo_last keeps its snapshot and redo_last its redo, so those alone do not
        say which one comes next."""
        if not hasattr(self, "b_redo"):
            return
        # flags, not worker.is_alive(): the worker may still be ending when its last event ("done", "note") is read here
        busy = getattr(self, "_running", False) or getattr(self, "_history_busy", False)
        queue = False
        try:
            # grey while anything runs, queued Generate clicks too (user 24.11.: "am besten sperren wir redo/undo während
            # eines laufs komplett"; until then a queued result layer could be hidden meanwhile, 22.11.)
            busy = busy or bool(self._batch_busy())
        except Exception:
            pass
        undo = redo = False
        if not busy:
            last = getattr(self, "_last_step", None)
            bridge = getattr(self, "bridge", None)
            ustack, rstack = self._stacks()
            ut, rt = (ustack[-1] if ustack else None), (rstack[-1] if rstack else None)
            try:
                if self._is_layers(ut):
                    undo = True
                elif not queue and (ut is not None or last not in ("undo", "stale")):
                    undo = bool(bridge and bridge.can_undo())
            except Exception:
                undo = False
            try:
                if self._is_layers(rt):
                    redo = True
                elif not queue and (rt is not None or last == "undo"):
                    redo = bool(bridge and bridge.can_redo())
            except Exception:
                redo = False
        try:
            self.b_undo.configure(state="normal" if undo else "disabled")
            self.b_redo.configure(state="normal" if redo else "disabled")
        except tk.TclError:
            pass
        # the tooltip names the lock during a run, like the scissors (user 25.11.)
        extra = "\n\n" + CUT_NOT_IN_RUN if self._history_locked() else ""
        for tt, base in ((getattr(self, "tt_undo", None), HISTORY_UNDO_TIP), (getattr(self, "tt_redo", None), HISTORY_REDO_TIP)):
            if tt is not None:
                tt.text = base + extra

    def stop_all(self):
        """Stop batch: only the batch that runs now (user 23.11. evening, choice "Den laufenden"; a batch = one Generate with
        its ×n): a direct run with its comparison runs and the variants it sent to the queue; else the batch of the
        picture at ComfyUI (user 21.11.). Other batches and queued Generate clicks go on."""
        if self.worker and self.worker.is_alive():
            self.bridge.cancel_all()
            rest = getattr(self, "_run_rest_bid", None)
            if rest:
                self.runner.cancel_batch(rest)
            self._status("Cancelling…")
        elif self._batch_busy():
            bid = self._batch_now()
            if bid:
                self.runner.cancel_batch(bid)
            self._status("Cancelling the batch…")

    def _batch_now(self) -> str:
        """The batch "Stop batch" ends (user 21.11.: only this one, other batches go on): the batch of the picture at
        ComfyUI now; between two pictures, the batch of the next one in the line; else the oldest one not over."""
        job = self.runner.running_job
        if job and job.get("batch_id"):
            return str(job["batch_id"])
        try:
            for j in self.runner.jobs():
                if j.get("status") == "waiting" and j.get("batch_id"):
                    return str(j["batch_id"])
        except Exception:
            pass
        for b in self.runner.batches():
            if b.get("state") not in ("done", "cancelled"):
                return str(b["id"])
        return ""

    def _poll(self):
        frame = None                # the newest live preview frame of this round (older ones are skipped)
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "preview":
                    frame = data
                elif kind == "progress":
                    f, msg, phase, pf, elapsed = data
                    self._set_progress(f, msg, phase, pf, elapsed)
                    # the bar's label names the step, the line below it says nothing then (no second copy of the same words);
                    # only what was there when the run started (or a step text of its own) goes, once: a message written
                    # meanwhile stays (window test 23.11.: "Insert reference can't wait in the queue" was gone at once)
                    if msg and msg.startswith(("Comparison", "Object still")):
                        self._status(msg)
                        self._status_stale = True
                    elif getattr(self, "_status_stale", False):
                        self._status("")
                elif kind in ("note", "note-error"):
                    self._status(data, error=(kind == "note-error"))
                    self._history_busy = False
                    self._sync_history_buttons()
                    self._batch_sync()          # a batch that started meanwhile keeps Undo and Redo grey
                elif kind == "done":
                    frame = None
                    self._hide_preview()            # the result is in PhotoCraft now (user 29.10., option A)
                    ok = not data.startswith(("Error", "Cancel", "Unexpected"))
                    self._reset_progress(done=ok, text=data if ok else "")      # the success line sits above the bar, nothing below it
                    self._status("" if ok else data, error=data.startswith(("Error", "Unexpected")))
                    if ok and getattr(self, "_other_pc", False):
                        self._status(self.OTHER_PC_HINT, error=True)
                    self._running = False
                    self._queue_note_own_done(data)    # the run stays in the queue window as Done / Cancelled (user 23.11.)
                    self.w_variants.configure(state="normal")
                    if ok and getattr(self, "_run_req_mode", "") != "upscale":
                        # Upscale stays out of Undo / Redo (user 24.11.: "upscale sollte aus redo/undo ausgenommen werden"):
                        # its new document has nothing to undo, and the steps of before keep their state
                        self._last_step = None      # a new result: Undo is the blue one again (decision 2a, 18.11.)
                        self._undo_new_run(getattr(self, "_run_req_mode", ""), getattr(self, "_run_placed", None))
                    self._sync_history_buttons()
                    self._show_stop_all(False)
                    self._go_stop(False)
                    self._history_end(ok)
                    self._ahead_stop()
                    self._batch_sync()          # a batch that waited for this run keeps Generate grey
                elif kind == "undo-snap":
                    self._undo_snap_done(data)
                elif kind == "undo-layer":
                    self._undo_layer_done(*data)
                elif kind == "seed":
                    self._set_last_seed(data)
                elif kind == "lastrun":
                    self._last_result = data
                elif kind == "vgl":
                    self._last_vgl = str(data or "")      # not shown in the window; the copy button next to the LLM checkbox takes it
                    self._sync_copy()
                    if getattr(self, "_hist_run", None):
                        self._hist_run["llm"] = self._last_vgl.strip()
                elif kind == "refresh":
                    self._apply_refresh(data)
                elif kind == "pc-alive":
                    self._photocraft_alive(data)
                elif kind == "alive":
                    self._comfy_alive(*data)
                elif kind == "comfyroot":
                    self._comfy_root_done(data)
                elif kind == "comfyaddr":
                    self._comfy_address_done(data)
                elif kind == "download":
                    self._download_event(data)
                elif kind == "filecheck":
                    self._check_event(data)
                elif kind == "update":
                    self._update_done(data)
                elif kind == "update-git":
                    self._update_git_done(*data)
                elif kind == "feather":
                    self._feather_done(*data)
                elif kind.startswith(("queue-", "batch-", "gen-")):
                    self._batch_event(kind, data)       # the batch queue and the hint at the bar (gui_batch.py)
        except queue.Empty:
            pass
        if frame is not None:
            self._show_preview(frame)
        self.root.after(100, self._poll)

    def _show_preview(self, im):
        """A live preview frame: as wide as the window and at most PREVIEW_MAX_H high (a tall picture stays narrower), above
        the status line. The area appears with the first frame and the window grows with it; minimised, nothing is shown."""
        if getattr(self, "_minimized", False):
            return
        try:
            w = max(int(self.root.winfo_width()), self._px(MIN_W)) - self._px(20)
        except (tk.TclError, TypeError, ValueError):
            w = self._px(MIN_W - 20)
        from PIL import ImageOps
        try:
            screen_h = int(self.root.winfo_screenheight())
        except (tk.TclError, TypeError, ValueError):
            screen_h = 1080
        shown = ImageOps.contain(im, (w, max(1, min(self._px(PREVIEW_MAX_H), round(screen_h * 0.245)))))
        self._preview_photo = icons.photo(self.root, None, "", 0, image=shown)     # Tk drops an image Python no longer holds
        self.lbl_preview.configure(image=self._preview_photo)
        if not self.f_preview.winfo_manager():
            self.f_preview.pack(fill="x", padx=10, pady=(6, 0), before=self.f_status)
            self._fit_height()

    def _hide_preview(self):
        self.lbl_preview.configure(image="")
        self._preview_photo = None          # also when minimised (the frame is not packed then): nothing old comes back
        if self.f_preview.winfo_manager():
            self.f_preview.pack_forget()
            self._fit_height()

    def _reset_progress(self, done: bool = False, text: str = ""):
        self._bar_value = 1.0 if done else 0.0
        self.pb.configure(value=self._bar_value)
        self._mini_bar_sync()
        full = (text or "Done") if done else ""
        word, rest = (full[:4], full[4:]) if full.startswith("Done") else (full, "")      # only the word "Done" is green
        self.v_pl.set(word)
        self._set_rest(rest)
        self._pl_style("Done.TLabel" if done else "Muted.TLabel")
        self._show_pl_line()

    MINI_BAR_PX = 3

    def _mini_bar_sync(self):
        """Minimised, the progress is a thin blue line along the window's bottom edge, growing from the left (user 24.11.
        evening, choice A: "nur die blaue linie", no grey track behind it, no text, the header no higher). Shown while the
        bar is between 0 and 1 (a run, a queued job or a batch); gone at the end, when cancelled and when shown again."""
        line = getattr(self, "f_mini_bar", None)
        if line is None:
            return
        f = float(getattr(self, "_bar_value", 0.0) or 0.0)
        try:
            if getattr(self, "_minimized", False) and 0.0 < f < 1.0:
                line.place(relx=0, rely=1.0, anchor="sw", relwidth=f, height=self._px(self.MINI_BAR_PX))
                line.lift()
            elif line.winfo_manager():
                line.place_forget()
        except tk.TclError:
            pass

    def _show_pl_line(self):
        """The line above the bar takes room only while it says something (the step, or "Done"): no empty line before the
        first run."""
        top = getattr(self, "f_pl_top", None)
        if top is None:
            return
        shown = bool(top.winfo_manager())
        if self.v_pl.get() and not shown:
            top.pack(fill="x", before=self.pb)
        elif not self.v_pl.get() and shown:
            top.pack_forget()

    def _set_rest(self, text: str):
        v = getattr(self, "v_pl_rest", None)
        if v is not None and v.get() != text:
            v.set(text)

    def _model_label(self) -> str:
        try:
            m = self._model()
        except Exception:
            m = None
        return m.label if m is not None else ""

    def _generating_word(self) -> str:
        """The words before the step while the image model works: "<model> is generating" (user 4.11.), with the model the run
        started with: a model chosen during the run must not rename it (window test E, 11.11.)."""
        label = getattr(self, "_run_label", None)
        if not getattr(self, "_running", False):
            # a job of the queue: the model it was queued with (docs/plan/generate-queue.md)
            label = getattr(self, "_queue_label", None) if getattr(self, "_batch_shown", None) else None
        if not label:
            label = self._model_label()
        return f"{label} is generating" if label else "Generating"

    def _set_progress(self, fraction: float, msg: str | None, phase: str, phase_fraction: float, elapsed: float | None):
        """Move the single bar and name the step. Idempotent and only forward: Tk is touched only when the value or the
        text really changed (stop()/mode switches on the bar made it blink), and the bar never jumps back when a
        phase has no real progress (-1)."""
        secs = f"{elapsed:.0f} s" if elapsed is not None else ""
        if phase == "prompt":
            text = f"Expanding Prompt · {secs}"
        elif phase == "image":
            step = (msg or "").split("…")[0].strip()
            text = f"{self._generating_word()} · " + (step if phase_fraction >= 0 and step else secs)
        elif phase == "stage":
            text = f"{msg} · {secs}" if secs else (msg or "Working")
        elif phase == "place":
            text = "Placing the result"
        else:
            text = "Preparing"
        self._pl_args = (fraction, msg, phase, phase_fraction, elapsed)     # the hint below can change on its own (gui_batch.py)
        hint = getattr(self, "_progress_hint", None)
        text += hint() if hint else ""      # " · Batch 3 of 12 · ~4 min", " · 2 jobs of others ahead"
        if self.v_pl.get() != text:
            self.v_pl.set(text)
            self._show_pl_line()
        self._set_rest("")
        self._pl_style("Muted.TLabel")
        if fraction is not None and fraction > self._bar_value:
            self._bar_value = round(fraction, 3)
            self.pb.configure(value=self._bar_value)
            self._mini_bar_sync()
