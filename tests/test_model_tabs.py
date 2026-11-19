"""The model tabs: a tab enables only its model's modes, brings its workflow and starting settings, follows presets.

    python tests/test_model_tabs.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
from pccomfy import models  # noqa: E402


def main():
    # the registry: every workflow exists, every mode is a known one
    for m in models.MODELS:
        for w in m.workflows():
            assert (t.ROOT / "workflows" / w).exists(), (m.key, w)
        for mode in m.modes:
            assert mode in dict(gui.MODE_LABELS), (m.key, mode)
    assert [m.label for m in models.MODELS] == ["Flux 3 Klein Edit", "Flux 2 Klein Edit", "Qwen Image 2.1", "Fibo 2.0 Edit Turbo", "Krea 2 Turbo", "MOSS Image", "MiniMax H3 Image"]

    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names

    # the function buttons and the model chips have no tooltips (user 11.11.); the tabs under Edit keep theirs (see below)
    assert not hasattr(gui, "CHIP_TIPS") and not hasattr(gui, "ChipTooltip") and not hasattr(app, "tt_tabs") and not hasattr(app, "tt_modes")
    assert not any(hasattr(m, "tip") for m in models.MODELS)

    # Qwen: fill, remove, reference, expand, edit, upscale (2.11.) - no refine
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app.v_workflow.get() == "qwen-image-21-edit.json" and app.v_res.get() == 1024 and app.v_turbo.get() is False    # Qwen: Turbo off by default (27.10.)
    assert app.rb_modes["edit"]["state"] == "normal" and app.rb_modes["upscale"]["state"] == "normal"     # functions: never grey
    assert [k for k, rb in app.rb_tabs.items() if rb["state"] == "normal"] == ["flux3", "flux2", "qwen", "fibo"]          # models that can fill (Flux 2 since 10.11., Flux 3 since 11.11.)
    app.v_mode.set("upscale"); app._on_mode()
    assert app.v_model.get() == "qwen" and app.v_workflow.get() == "qwen-image-21-upscale.json"      # Qwen can upscale: stays
    app.v_mode.set("refine"); app._on_mode()
    assert app.v_model.get() == "qwen" and app.v_workflow.get() == "qwen-image-21-refine.json"      # the upscale graph at the canvas size, with the Turbo LoRA switch
    assert app._has_lora_switch() and app.v_turbo.get() is False       # the switch shows, starts off (25 steps)
    app.v_mode.set("upscale"); app._on_mode()
    assert not app._has_lora_switch()                                    # Upscale keeps its graph without a LoRA
    app.v_mode.set("refine"); app._on_mode()
    app.v_mode.set("inpaint"); app._on_mode()
    assert app.v_model.get() == "qwen"                                                                   # the last model of Fill
    app.v_mode.set("txt2img"); app._on_mode()
    assert app.v_model.get() == "qwen"                                                                   # Qwen can do it: stays
    app.v_mode.set("inpaint"); app._on_mode()

    # the modes follow each other in the order text, edit, fill, remove, expand, reference, upscale, refine
    assert [k for k, _ in gui.MODE_LABELS] == ["txt2img", "outpaint", "inpaint", "remove", "edit", "multi_edit", "sketch", "scribble", "upscale", "refine", "img2img"]

    # MOSS: text to image, Generative fill, Expand (a test); the DMD2 LoRA is its own LoRA, Lenovo and SLG are switches
    app.v_model.set("moss")
    app.v_mode.set("txt2img")
    app._on_model()
    assert app.v_mode.get() == "txt2img" and app.v_workflow.get() == "moss-image-t2i.json" and app.v_res.get() == 1280
    assert app.v_enhance.get() is False and "Qwen 3.5 9B" in app.tt_enhance.text      # which text model writes the prompt (starts off)
    assert app.cb_enhance["text"] == "Enhance my Prompt with LLM" and "Qwen 3.5 9B" in app.tt_enhance.text   # name only in the tooltip
    assert app.v_turbo.get() is False and app.cb_turbo["text"] == "Turbo LoRA" and app.v_lora_str.get() == 1.0   # DMD2 starts off (user 29.10.)
    assert list(models.MOSS.modes) == ["txt2img"]                                                       # Fill off (not good enough), Expand parked 29.10.
    assert [c["text"] for c in app.stage_cbs][:2] == ["UltraReal LoRA", "Skip-layer guidance (SLG)"]
    assert app.v_stage.get() and not app.v_stage2.get()      # Lenovo on, SLG off (user 29.10.)
    r = app._request()
    assert r.stage_on is True and r.stages_off == ["7"] and r.turbo is False
    assert r.stage_strengths == {"5": 1.0}                                             # the Lenovo LoRA has a strength slider
    app.v_sstr[0].set(0.6)
    assert app._request().stage_strengths == {"5": 0.6}
    app.v_sstr[0].set(1.0)
    assert r.sampler_override == {} and (app.v_steps.get(), app.v_cfg.get()) == (25, 3.0)  # without DMD2: the full recipe
    app.v_turbo.set(True)
    app._on_workflow()
    assert (app.v_steps.get(), app.v_cfg.get()) == (8, 1.5)                               # with DMD2: its own values
    app.v_turbo.set(False)
    app._on_workflow()
    app.v_steps.set(30)
    assert app._request().sampler_override == {"steps": 30}
    app.v_turbo.set(True)
    app._on_workflow()
    assert app._request().mode == "txt2img" and app._layer_prefix() == "MOSS Image Text"
    assert "outpaint" not in models.BY_KEY["moss"].modes and "outpaint" not in models.BY_KEY["krea2"].modes   # MOSS and Krea 2 Expand are parked

    # Flux 3: text to image and edit share the settings (base res 1536); Flux 2 edit starts at 1024
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    assert app.v_workflow.get() == "flux3-klein-t2i.json" and app.v_res.get() == 1536
    app.v_mode.set("edit")
    app._on_mode()
    assert app.v_workflow.get() == "flux3-klein-edit.json" and app.v_res.get() == 1536
    app.v_model.set("flux2")
    app._on_model()
    assert app.v_res.get() == 1024
    assert len(app.rb_tabs) == 7 and app.f_tabs is not None      # + MiniMax H3 Image (PLAN 2.0b)

    # Flux 3: upscale brings its workflow, 1.5 and the placeholder; edit takes the placeholder away again
    app.v_model.set("flux3")
    app.v_mode.set("upscale")
    app._on_model()
    assert app.v_workflow.get() == "flux3-klein-upscale.json" and app.v_scale.get() == "x 1.5"
    assert app.t_prompt.get("1.0", "end").strip() == models.FLUX3_DEFAULT            # the workflow's own prompt, to describe in front of
    assert app._hint_text == ""                                                         # no tip since 12.11. (P8)
    app.v_mode.set("edit")
    app._on_mode()
    assert app._hint_text == models.EDIT_TIP    # the tip under the prompt in Edit Canvas, the same for every model (user 3.11.)
    assert app.v_workflow.get() == "flux3-klein-edit.json" and app.t_prompt.get("1.0", "end").strip() == ""
    app.t_prompt.insert("1.0", "make it night")
    app.v_mode.set("upscale")
    app._on_mode()
    assert app.v_workflow.get() == "flux3-klein-upscale.json" and app.t_prompt.get("1.0", "end").strip() == models.FLUX3.modes["upscale"].prompt_hint  # the stock text wins (user 11.11.)
    assert "refine" in models.BY_KEY["flux3"].modes                                      # Flux 3 Refine (after Pixaroma, 1.11.)

    # a model without the current mode: the first one it has
    app.v_model.set("flux3")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app.v_mode.get() == "inpaint" and app.v_workflow.get() == "flux3-klein-edit.json"     # Flux 3 Fill through the box (11.11.)
    app.v_model.set("krea2")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app.v_mode.get() == "txt2img"                                                          # a model without Fill: its first function
    app.v_model.set("flux2")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app.v_mode.get() == "inpaint" and app.v_workflow.get() == "flux2-klein-edit.json"     # Flux 2 Fill (user 10.11.)
    assert app._hint_text == models.FILL_TIP

    # Fibo: one workflow with the LLM checkbox; its state stays while the mode changes; the tab follows a loaded workflow
    app.v_model.set("fibo")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app.v_workflow.get() == "fibo2-edit.json" and app.v_enhance.get() is False
    assert app.cb_enhance["text"] == "Enhance my Prompt with LLM" and "Qwen3-VL 4B" in app.tt_enhance.text   # name only in the tooltip (Fibo's writer is the smallest text encoder since 6.11.)
    app.v_enhance.set(True)
    app.v_mode.set("edit")
    app._on_mode()
    assert app.v_enhance.get() is True and app._request().enhance is True                # the choice survives a mode change
    app.v_mode.set("outpaint")
    app._on_mode()
    assert app.v_workflow.get() == "fibo2-edit.json" and app.v_model.get() == "fibo"
    assert app._request().enhance is False                                               # Expand: no prompt writer
    app.v_mode.set("edit")
    app._on_mode()
    assert app._request().enhance is True
    app.v_enhance.set(False)
    app._apply_settings({"workflow": "qwen-image-21-edit.json", "mode": "inpaint"})
    assert app.v_model.get() == "qwen"

    # extra LoRAs: rows, search order (the model's folder first), request, state
    app.all_loras = ["flux 3\\b.safetensors", "qwen\\style_a.safetensors", "qwen\\Style_B.safetensors", "misc\\c.safetensors"]
    app.v_model.set("qwen")
    assert app._lora_choices()[:2] == ["qwen\\style_a.safetensors", "qwen\\Style_B.safetensors"]
    assert app._lora_choices("style b") == ["qwen\\Style_B.safetensors"]
    app._add_lora_row("qwen\\style_a.safetensors", 0.6)
    app._add_lora_row("", 1.0)                       # an empty row is not a LoRA
    row0 = app.lora_rows[0]
    row0["name"].set("style b")
    app._lora_show(row0, "style b")                  # typing opens the list, narrowed to what was typed
    assert row0["box"] is not None
    app._lora_show(row0, "zzz-no-such")              # nothing matches: the list goes away
    assert row0["box"] is None
    app._lora_toggle(row0)                            # the arrow lists everything
    assert row0["box"] is not None
    app._lora_hide(row0)
    row0["name"].set("qwen\\style_a.safetensors")
    assert app._request().loras == [("qwen\\style_a.safetensors", 0.6)]
    assert app._collect()["loras"] == [["qwen\\style_a.safetensors", 0.6]]
    for _ in range(6):
        app._add_lora_row("misc\\c.safetensors")
    assert len(app.lora_rows) == app.LORA_MAX and app.b_addlora["state"] == "disabled"
    app._set_loras([["x", 0.3]])
    assert len(app.lora_rows) == 1 and app._loras() == [["x", 0.3]] and app.b_addlora["state"] == "normal"
    app._apply_settings({"loras": []})
    assert app._loras() == []
    app._set_loras([["qwen\\style_a.safetensors", 0.6]])

    # text to image for Qwen, Expand for Flux 2 and Flux 3, not for Krea 2 (off 29.10.); Fibo Remove starts with a soft mask and 10 % feather
    for key, mode in (("qwen", "txt2img"), ("flux2", "outpaint"), ("flux3", "outpaint")):
        assert mode in models.BY_KEY[key].modes, (key, mode)
    assert "outpaint" not in models.BY_KEY["krea2"].modes
    app.v_model.set("fibo")
    app.v_mode.set("remove")
    app._on_model()
    assert app.v_lmask.get() == gui.LAYER_MASKS["soft"] and app.v_feather.get() == 10.0
    assert gui.LAYER_MASKS["soft"] == "soft"
    # Flux 2 refine: ready-made prompts as radio buttons that fill the field; upscale starts at 1.5
    app.v_model.set("flux2")
    app.v_mode.set("refine")
    app._on_model()
    assert app._pchoice_key == ("flux2", ("Default", "Neutral", "Studio portrait")) and list(app.rb_refine) == ["Default", "Neutral", "Studio portrait"]
    app._insert_prompt(models.RELIGHT_NEUTRAL)
    assert app._prompt_text().startswith("A crystal-clear, high-fidelity photograph")
    app.v_mode.set("upscale")
    app._on_model()
    assert app._scale() == 1.5 and app.v_scale.get() == "x 1.5" and app._pchoice_key == ("flux2", ("Default", "Neutral", "Studio portrait"))
    # Expand image: the prompt field turns orange with a hint
    app.v_mode.set("outpaint")
    app._on_model()
    assert app.t_prompt["highlightbackground"] == gui.ACCENT
    app.v_mode.set("edit")
    app._on_model()
    assert app._hint_text.startswith(models.EDIT_TIP)   # Edit Canvas: the tip under the prompt, also orange
    app.v_mode.set("txt2img")
    app._on_model()
    assert app._hint_text == models.T2I_TIP             # Text to image: says that a new image is added, also orange
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    assert app._hint_text == models.FILL_TIP + " " + models.QWEN_SMALL and app.t_prompt["highlightbackground"] == gui.ACCENT   # Fill: the tip under the prompt (28.10.)
    app.v_model.set("flux2")
    app.v_mode.set("txt2img")
    app._on_model()
    assert models.BY_KEY["moss"].modes["txt2img"].settings["enhance"] is False   # MOSS: the prompt enhancer starts off
    assert gui.PROMPT_LINES == 5
    mm = models.BY_KEY
    assert mm["qwen"].modes["txt2img"].workflow == "qwen-image-21-t2i.json" and mm["qwen"].modes["txt2img"].settings["enhance"] is False and mm["qwen"].modes["txt2img"].settings["turbo"] is False
    assert mm["qwen"].modes["remove"].settings["feather_pct"] == 10.0 and mm["fibo"].modes["inpaint"].settings["feather_pct"] == 10.0
    assert mm["fibo"].modes["inpaint"].settings["layer_mask"] == "soft" == mm["qwen"].modes["inpaint"].settings["layer_mask"]   # soft edge outside the selection (28.10.)
    assert mm["flux3"].modes["txt2img"].settings["enhance"] is False
    # "auto" left the menu (28.10.): no mode uses it, and Expand keeps exactly what "auto" gave it before
    from pccomfy.bridge import effective_layer_mask, is_editor
    from pccomfy import workflows as _wfs
    for m in models.MODELS:
        for key, spec in m.modes.items():
            assert spec.settings.get("layer_mask") != "auto", (m.key, key)
        if "outpaint" in m.modes:
            spec = m.modes["outpaint"]
            ed = is_editor(_wfs.resolve(str(t.ROOT / "workflows" / spec.workflow)))
            # Expand returns only the new area through a soft layer mask (user 4.11.), every model that has Expand
            want = "soft"
            assert spec.settings["layer_mask"] == want, m.key
    assert models.BY_KEY["fibo"].modes["outpaint"].settings["context"] == 1.0          # user 4.11.
    assert models.BY_KEY["flux3"].modes["outpaint"].settings["context"] == 1.0
    assert models.BY_KEY["qwen"].modes["outpaint"].settings["context"] == 0.4
    assert mm["fibo"].modes["inpaint"].prompt_tip == models.FILL_TIP   # the user's wording
    assert mm["qwen"].modes["inpaint"].prompt_tip == models.FILL_TIP + " Small selections don't work well with Qwen."   # user 30.10.
    assert models.FILL_TIP == "Draw a selection and prompt e.g. “add a red flower”."   # user 3.11., second sentence dropped 17.11.
    assert [p[0] for p in mm["flux2"].modes["refine"].prompts] == ["Default", "Neutral", "Studio portrait"]
    assert mm["flux3"].modes["upscale"].prompts == () and mm["flux2"].modes["upscale"].prompts == ()   # Flux 3: the workflow's own prompt only
    # the prompt a refine starts with is the one the workflow sends by default
    import json as _j
    wf2 = _j.loads((t.ROOT / "workflows" / "flux2-klein-upscale.json").read_text(encoding="utf-8"))
    wf3 = _j.loads((t.ROOT / "workflows" / "flux3-klein-upscale.json").read_text(encoding="utf-8"))
    assert wf2["206"]["_meta"]["pc_default_prompt"] == models.FLUX2_DEFAULT == mm["flux2"].modes["refine"].prompt_hint
    assert wf3["159"]["_meta"]["pc_default_prompt"] == models.FLUX3_DEFAULT == mm["flux3"].modes["upscale"].prompt_hint
    assert wf3["159"]["inputs"]["text"] == ""          # the pc:prompt node itself (no AusBoss text node since 2.11.)
    assert {m.modes["upscale"].prompt_tip for m in models.MODELS if "upscale" in m.modes} == {""}     # no description advice (user 12.11., P8)
    assert {m.modes["refine"].prompt_tip for m in models.MODELS if "refine" in m.modes} == {models.REFINE_TIP}
    assert not hasattr(models, "DESCRIBE_TIP")          # dropped 12.11. (docs/tests/p8-upscale-prompt-ergebnis.md)
    assert models.REFINE_TIP == "Refine keeps the size and redraws fine detail."
    # Remove (a test) for Flux 2 and 3: the Qwen way, soft mask with 10 % feather
    for k in ("flux2", "flux3"):
        assert mm[k].modes["remove"].settings["feather_pct"] == 10.0 and mm[k].modes["remove"].settings["layer_mask"] == "soft"
    # the tooltips of the tabs under Edit name no model (user 28.10.); model notes go under the prompt
    names = ("Qwen", "Fibo", "Flux", "MOSS", "Krea", "SeedVR")
    assert set(models.FUNCTION_TIPS) == {"edit", "multi_edit", "sketch", "scribble", "inpaint"}     # inpaint: the tab Fill selection (Flux 3)
    assert not [n for n in names for tip in models.FUNCTION_TIPS.values() if n.lower() in tip.lower()]
    assert {m.key: m.modes["remove"].prompt_tip for m in models.MODELS if "remove" in m.modes} == {
        "qwen": models.REMOVE_TIP, "flux3": models.REMOVE_AGAIN, "flux2": models.REMOVE_AGAIN, "fibo": models.REMOVE_AGAIN}   # user 16.11.: the placeholder names it
    assert models.REMOVE_TIP == "Name what to remove (e.g. “car”). If the first try doesn't work, try removing it a second time."
    assert all(k in models.SHORT for k in models.BY_KEY)      # no ranking anywhere (removed 7.11.)
    # "Sharpen result" removed everywhere (user 17.11.; Fibo Refine had 10 %): no function brings a value of its own
    assert not [m.key for m in models.MODELS for s in m.modes.values() if "sharpen" in s.settings]
    assert not hasattr(app, "v_sharpen") and not hasattr(app, "f_sharp")
    app.v_model.set("fibo"); app.v_mode.set("txt2img"); app._on_model(); app.reset_settings()     # a fresh page, as the old Sharpen loop left it
    # Fibo: text to image has its own workflow (no image inputs), Refine runs as a whole-image edit with a ready prompt
    assert mm["fibo"].modes["txt2img"].workflow == "fibo2-t2i.json" and mm["fibo"].modes["refine"].run_as == "edit"
    assert mm["fibo"].modes["refine"].prompt_hint == models.FLUX2_DEFAULT      # the Flux 2 Refine default (user 28.10.)
    assert models.FIBO_REFINE in models.STOCK_PROMPTS     # the old Fibo Refine text in a saved field is still replaced
    app.v_model.set("fibo")
    app.v_mode.set("refine")
    app._on_model()
    assert app.v_workflow.get() == "fibo2-edit.json" and app._request().mode == "edit"
    assert app._prompt_text() == models.FLUX2_DEFAULT and app.v_mode.get() == "refine" and app._layer_prefix().endswith("Refine")
    app.v_mode.set("txt2img")
    app._on_mode()
    assert app.v_workflow.get() == "fibo2-t2i.json" and app._request().mode == "txt2img" and app._prompt_text() == ""
    app.v_mode.set("edit")
    app._on_mode()
    assert app.v_workflow.get() == "fibo2-edit.json"
    # Remove Selection for Flux: the field is free for an optional name of the object; it travels as remove_target
    for k in ("flux2", "flux3"):
        app.v_model.set(k)
        app.v_mode.set("remove")
        app._on_model()
        assert str(app.t_prompt.cget("state")) == "normal" and app._hint_text.startswith(models.REMOVE_AGAIN), k
        assert app._request().remove_target == ""
        app.t_prompt.insert("1.0", "the dog")
        assert app._request().remove_target == "the dog" and app._request().mode == "remove"
        app.t_prompt.delete("1.0", "end")
        app.v_mode.set("edit")
        app._on_mode()
        assert app._request().remove_target == ""
    app.v_model.set("qwen")
    app.v_mode.set("remove")
    app._on_model()
    assert app.t_prompt.get("1.0", "end").strip() == ""
    # the copy button for the enhanced prompt
    assert app._last_vgl == ""
    app.root.clipboard_clear = lambda: None
    got = []
    app.root.clipboard_append = lambda x: got.append(x)
    app._last_vgl = "a long enhanced prompt"
    app._copy_enhanced()
    assert got == ["a long enhanced prompt"]

    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    app._set_loras([["qwen\\style_a.safetensors", 0.6]])
    # saved with the state
    app._save_state(app._request())
    import json
    assert json.loads((Path(t.TMP) / "state.json").read_text(encoding="utf-8"))["model"] == "qwen"
    assert json.loads((Path(t.TMP) / "state.json").read_text(encoding="utf-8"))["loras"] == [["qwen\\style_a.safetensors", 0.6]]
    from pccomfy import ui_settings
    assert ui_settings.ALL_FILES_BUTTON == "Download missing files" and not hasattr(ui_settings, "tab_title")
    # the model pages of the settings window behind one field (user 19.11., choice C; before a grid of chips)
    assert not hasattr(ui_settings, "ButtonTabs") and hasattr(ui_settings, "ModelPicker")

    class Name:
        def __init__(self):
            self.kw = {}

        def configure(self, **kw):
            self.kw.update(kw)

    class Var:
        def __init__(self, v=""):
            self.v = v

        def get(self):
            return self.v

        def set(self, v):
            self.v = v
    mp = ui_settings.ModelPicker.__new__(ui_settings.ModelPicker)
    mp.name, mp.current, mp.titles, mp.pages = Name(), Var("p1"), {}, []
    mp.tab("p2", text="Flux 2 Klein Edit", image="dot")            # not the page shown: the field stays
    assert mp.name.kw == {} and mp.titles["p2"] == {"text": "Flux 2 Klein Edit", "image": "dot"}
    mp.tab("p1", text="Qwen Image 2.1", image="dot", compound="left")
    assert mp.name.kw == {"text": "Qwen Image 2.1", "image": "dot"} and mp.field_text == "Qwen Image 2.1"
    mp.tab("p1", image="")                                         # ready: no dot
    assert mp.name.kw["image"] == "" and mp.name.kw["text"] == "Qwen Image 2.1"
    shutil.rmtree(t.TMP, ignore_errors=True)
    print("ALL OK (model tabs)")


if __name__ == "__main__":
    main()
