"""The window with a known model variant (pccomfy/variants.py, user 20.11.): its values stand in the fields, Qwen Turbo greys
out the Turbo LoRA and Steps, and the request names the variant.

    python tests/test_variants_gui.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
from pccomfy import inventory, manifest, models  # noqa: E402

QWEN, QWEN_T = "qwen_image_2.1_int8_convrot.safetensors", "qwen_image_2.1_turbo_int8_convrot.safetensors"


def inv(swap=(), extra=(), mapping=None):
    """An inventory with every manifest file; ``swap`` = our files replaced by these variants, ``extra`` = variants added."""
    from pccomfy import variants
    lists = {k: [] for k in manifest.KINDS}
    gone = {variants.get(n).base for n in swap}
    for f in manifest.FILES.values():
        if f.name not in gone:
            lists[f.kind].append(f.name)
    lists["unet"] += list(swap) + list(extra)
    return inventory.Inventory(lists, mapping=mapping)


def pick(app, model, mode):
    app.v_model.set(model)
    app.v_mode.set(mode)
    app._on_model()
    app._on_workflow()


def main():
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names

    # our own Qwen file: the LoRA box works, Steps 25 without the LoRA, nothing named in the request
    app.inv = inv(extra=[QWEN_T])
    pick(app, "qwen", "txt2img")
    assert app.v_workflow.get() == "qwen-image-21-t2i.json", app.v_workflow.get()
    assert app._variant() is None and str(app.cb_turbo["state"]) == "normal"
    assert app.v_steps.get() == 25 and str(app.w_steps["state"]) == "normal" and app._request().variant == ""

    # Qwen Turbo alone: LoRA off and grey with its tooltip, Steps 8 and grey, CFG 1, euler
    app.inv = inv(swap=[QWEN_T])
    app.v_turbo.set(True)
    pick(app, "qwen", "txt2img")
    assert app._variant().file == QWEN_T
    assert app.v_turbo.get() is False and str(app.cb_turbo["state"]) == "disabled"
    assert app.tt_turbo.text == "Turbo is built into this file"
    assert (app.v_steps.get(), float(app.v_cfg.get()), app.v_sampler.get()) == (8, 1.0, "euler")
    assert str(app.w_steps["state"]) == "disabled" and app.tt_steps.text == gui.STEPS_FIXED_TIP
    r = app._request()
    assert r.variant == QWEN_T and r.sampler_override == {} and r.turbo is False
    # Refine (denoise below 1): no schedule, Steps can be changed
    pick(app, "qwen", "refine")
    assert app.v_steps.get() == 8 and str(app.w_steps["state"]) == "normal"
    # linked in Model Links while both are there: the same
    app.inv = inv(extra=[QWEN_T], mapping={QWEN: QWEN_T})
    pick(app, "qwen", "inpaint")
    assert app._variant().file == QWEN_T and app.v_steps.get() == 8 and str(app.w_steps["state"]) == "disabled"

    # a new reading of ComfyUI's lists (Model Links, Refresh) brings the variant's values into the open window
    app.inv = inv()
    pick(app, "qwen", "txt2img")
    assert app.v_steps.get() == 25 and str(app.cb_turbo["state"]) == "normal"
    app._set_inventory(inv(swap=[QWEN_T]))
    assert app.v_workflow.get() == "qwen-image-21-t2i.json" and app.v_steps.get() == 8 and str(app.cb_turbo["state"]) == "disabled"
    app._set_inventory(inv())
    assert app.v_steps.get() == 25 and str(app.cb_turbo["state"]) == "normal"

    # Fibo Dev: 30 steps, CFG 5 in the fields; a typed CFG goes along as an override
    app.inv = inv(swap=["fibo2_dev_int8_convrot.safetensors"])
    pick(app, "fibo", "edit")
    assert (app.v_steps.get(), float(app.v_cfg.get())) == (30, 5.0) and str(app.w_steps["state"]) == "normal"
    assert app._request().variant == "fibo2_dev_int8_convrot.safetensors" and app._request().sampler_override == {}
    app.v_cfg.set(4.0)
    assert app._request().sampler_override == {"cfg": 4.0}

    # MOSS Base: with DMD2 8 / CFG 1 / euler; without it our SFT values (25, CFG 3)
    app.inv = inv(swap=["moss_image_base_int8_convrot.safetensors"])
    pick(app, "moss", "txt2img")
    assert app.v_turbo.get() is False and (app.v_steps.get(), float(app.v_cfg.get())) == (25, 3.0)
    app.v_turbo.set(True)
    app._on_turbo()
    assert (app.v_steps.get(), float(app.v_cfg.get()), app.v_sampler.get(), app.v_scheduler.get()) == (8, 1.0, "euler", "simple")
    assert app._request().sampler_override == {}
    print("ALL OK (model variants in the window)")


if __name__ == "__main__":
    main()
