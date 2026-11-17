"""At every start the sliders, sampler, steps and LoRAs are the standard ones; model, function and prompt stay (user 4.11.).

    python tests/test_start_factory.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = tempfile.mkdtemp(prefix="pccomfy-start-")
os.environ["PCCOMFY_HOME"] = HOME
os.environ["PCCOMFY_NO_TIPS"] = "1"
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models  # noqa: E402


def start(state: dict):
    cfgmod.save_state(state)
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    try:
        app.root.attributes("-alpha", 0.0)
    except Exception:
        pass
    app.root.update()
    return app


def every_page_keeps_saved_steps():
    """Saved Steps (chip menu "My settings") come back for EVERY model and function: at the start, after "Reset page" and when
    the function is opened by a click (PLAN 2.5, 4.11.). Pages whose workflow has no steps field are skipped."""
    done = []
    for key, m in models.BY_KEY.items():
        for mode in m.modes:
            wf = m.modes[mode].workflow
            if not wf:
                continue
            cfgmod.set_saved_page(key, mode, {"steps": 13})
            app = start({"model": key, "mode": mode, "workflow": wf})
            try:
                if str(app.w_steps.cget("state")) == "disabled":
                    continue
                if app.v_model.get() != key or app.v_mode.get() != mode:
                    continue        # a tab of another function (Insert reference, Sketch ...): no page of its own
                assert app.v_steps.get() == 13, ("start", key, mode, app.v_steps.get())
                app._start_fresh()
                assert app.v_steps.get() == 13, ("_start_fresh", key, mode, app.v_steps.get())
                app.reset_settings()
                assert app.v_steps.get() == 13, ("reset", key, mode, app.v_steps.get())
                app.reset_settings(factory=True)
                assert app.v_steps.get() != 13 or int(app._wf_vals.get("steps", 0)) == 13, ("factory", key, mode)
                assert cfgmod.saved_page(key, mode) == {}, ("factory forgets the saved page", key, mode)      # 12.11.
                cfgmod.set_saved_page(key, mode, {"steps": 13})
                app.v_mode.set(mode)
                app._on_mode()
                assert app.v_steps.get() == 13 or int(app._wf_vals.get("steps", 0)) == 13, ("click", key, mode, app.v_steps.get())
                done.append((key, mode))
            finally:
                app.root.destroy()
                cfgmod.set_saved_page(key, mode, None)
    assert done, "no page checked"
    return len(done)


def main():
    spec = models.BY_KEY["qwen"].modes["inpaint"]
    left_over = {"model": "qwen", "mode": "inpaint", "workflow": spec.workflow, "prompt": "my own words", "steps": 77, "cfg": 9.5, "sampler": "dpmpp_2m",
                 "sharpen": 0.9, "context": 0.9, "detail": 0.3, "variants": 3, "loras": [["x/y.safetensors", 0.5]],
                 "lora_strength": 0.4, "mask_grow": 40, "mask_blur": 33}
    app = start(left_over)
    try:
        assert app.v_model.get() == "qwen" and app.v_mode.get() == "inpaint"      # model and function stay
        app.t_prompt.insert("1.0", "my own words")          # a prompt in the field stays through the start routine
        app._start_fresh()
        assert app.t_prompt.get("1.0", "end").strip() == "my own words"
        assert app.v_variants.get() == 3
        assert app.v_steps.get() != 77 and abs(app.v_cfg.get() - 9.5) > 1e-6 and app.v_sampler.get() != "dpmpp_2m"
        assert app.v_detail.get() == 1.0
        assert app.v_context.get() != 0.9 and app.v_grow.get() != 40 and app.v_blur.get() != 33
        assert app._loras() == [], app._loras()
        assert app.v_status.get() == "Ready"
    finally:
        app.root.destroy()
    # "Set current settings as my standard settings" is loaded at the start (user 4.11., evening); a value not saved stays at the standard
    cfgmod.set_saved_page("qwen", "inpaint", {"sharpen": 0.4, "context": 0.65, "steps": 13})   # (an old save may still hold "sharpen": ignored)
    app = start(left_over)
    try:
        app._start_fresh()
        assert abs(app.v_context.get() - 0.65) < 1e-6, app.v_context.get()
        assert app.v_steps.get() == 13, app.v_steps.get()        # the saved steps come back too (PLAN 2.5, 4.11.: "steps did not come back")
    finally:
        app.root.destroy()
    cfgmod.set_saved_page("qwen", "inpaint", None)
    n = every_page_keeps_saved_steps()
    print(f"ALL OK ({n} pages keep their saved steps; start with the standard settings, saved pages loaded)")


if __name__ == "__main__":
    main()
