# tags: upscale, refine, window
"""Upscale and Refine are two functions again (user 22.11.; one button "Upscale / Refine" with the factor None from 6.11.):
Refine below Edit with its own symbol and its row of ready-made prompts, Upscale with the factors. Real Tk window
(hidden); skipped when Tk cannot open a window.

    python tests/test_scale_function.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-scalefn-")
os.environ["PCCOMFY_HOME"] = TMP
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


def shown(w) -> bool:
    return bool(w.winfo_manager())


def no_licence_notes():
    """No stage tooltip of a workflow warns about a licence any more (user 7.11.: licence warnings removed; 8.11.: the
    UltraSharp tips of Flux 3 and Fibo Upscale still said "non-commercial")."""
    from pccomfy import workflows
    for wf in sorted((ROOT / "workflows").glob("*.json")):
        for st in workflows.stage_info(workflows.load_template(wf)):
            assert "commercial" not in st["tip"].lower() and "licen" not in st["tip"].lower(), (wf.name, st["tip"])


def main():
    no_licence_notes()
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    app.root.update()

    # the function list (one chip since 20.11.): Refine below Edit, then Upscale, two functions again (user 22.11.; one
    # entry "Upscale / Refine" from 6.11. until then)
    assert app.rb_modes["upscale"].shown and app.rb_modes["refine"].shown and not hasattr(app, "rb_scale_fn")
    assert app._mode_order == ["txt2img", "outpaint", "inpaint", "remove", "edit", "refine", "upscale"], app._mode_order
    assert app.rb_modes["refine"]["text"] == "Refine Image" and app.rb_modes["upscale"]["text"] == "Upscale"
    assert app.v_fn.get() == "inpaint"                                  # Fill lights its own button
    assert not shown(app.f_scale)

    def rows():
        """(factor row shown, Refine row shown)"""
        app.root.update()
        return shown(app.lbl_fac) and shown(app.f_fac), shown(app.lbl_refine) and shown(app.f_refine)

    # Refine Image: one prompt per model (user 24.11.), no row of its own and no factors
    app._pick_mode("refine")
    assert app.v_mode.get() == "refine" and app.v_fac.get() == "r:Default" and not shown(app.f_scale)
    assert app.v_fn.get() == "" and not shown(app.lbl_refine) and not shown(app.f_refine)
    assert app.v_workflow.get() == models.QWEN.modes["refine"].workflow
    assert app.b_mode["text"].startswith("Refine")

    # Upscale: only the factors (the mode's start factor 1.5), a factor changes the request
    app._pick_mode("upscale")
    assert app.v_mode.get() == "upscale" and rows() == (True, False) and app.v_fac.get() == "x 1.5"
    assert app.v_workflow.get() == models.QWEN.modes["upscale"].workflow and app.b_mode["text"].startswith("Upscale")
    app.v_fac.set("x 3")
    app._on_factor()
    assert app.v_mode.get() == "upscale" and app._scale() == 3.0 and app._request().scale == 3.0
    app.v_fac.set("x 2")
    app._on_factor()
    assert app.v_mode.get() == "upscale" and app._scale() == 2.0
    app.v_scale.set("x 4")                                              # set from outside (a saved page): the buttons follow
    assert app.v_fac.get() == "x 4"
    app._pick_mode("inpaint")
    assert not shown(app.f_scale)

    # Fibo enlarges up to 3x (10.11.): 4x is greyed out; its stages in ONE row under the factors (8.11.), only in Upscale
    app.v_model.set("fibo")
    app._on_model()
    app._pick_mode("upscale")
    assert app.v_mode.get() == "upscale" and app._scale() == 1.5, (app.v_mode.get(), app._scale())
    assert [str(app.rb_scale[k]["state"]) for k in ("x 1.5", "x 2", "x 3", "x 4")] == ["normal", "normal", "normal", "disabled"]
    # ... and they look greyed out like a greyed-out model chip (8.11.): grey text, no fill, a dark outline
    st = gui.ttk.Style(app.root)
    assert st.lookup("Small.Toolbutton", "foreground", ["disabled"]) == gui.DISABLED
    assert st.lookup("Small.Toolbutton", "background", ["disabled"]) == gui.BG
    assert st.lookup("Small.Toolbutton", "bordercolor", ["disabled"]) == "#4a4a4a"
    assert st.lookup("Small.Toolbutton", "foreground", ["disabled"]) == st.lookup("Chip.Toolbutton", "foreground", ["disabled"])
    assert app.t_prompt.get("1.0", "end").strip() == models.QWEN_UPSCALE_DEFAULT and app._request().mode == "upscale"
    assert app.v_workflow.get() == "fibo2-upscale.json"
    # Fibo Upscale stages (7.11.): "4x UltraSharp first" on, "Tiles" off, and they exclude each other
    assert [x["label"] for x in app._stages()] == ["4x UltraSharp first", "Tiles"] and [v.get() for v in app.stage_vars[:2]] == [True, False]
    r = app._request()
    assert r.stage_on and r.stages_off == ["102"]
    app.stage_vars[1].set(True)
    app._on_stage(1)
    assert [v.get() for v in app.stage_vars[:2]] == [False, True] and not app._request().stage_on and app._request().stages_off == []
    app.stage_vars[0].set(True)
    app._on_stage(0)
    assert [v.get() for v in app.stage_vars[:2]] == [True, False]
    app.root.update()
    assert shown(app.f_stage_row) and shown(app.sep_stage_row)
    assert app.f_stage_row.grid_info()["row"] == 1 and app.sep_stage_row.grid_info()["row"] == 2
    assert [cb["text"] for cb in app.stage_row_cbs if shown(cb)] == ["4x UltraSharp first", "Tiles"]
    assert all(str(cb["state"]) == "normal" for cb in app.stage_row_cbs[:2])
    assert not any(shown(cb) for cb in app.stage_cbs) and not shown(app.f_opts)
    assert app.stage_row_cbs[0]["variable"] == app.stage_cbs[0]["variable"]      # the same switch: the request follows the row
    app.stage_row_cbs[1].invoke()
    assert [v.get() for v in app.stage_vars[:2]] == [False, True] and app._request().stages_off == []
    app.stage_row_cbs[0].invoke()
    assert [v.get() for v in app.stage_vars[:2]] == [True, False]
    # Fibo Refine (the edit workflow): no stage row and no factors (22.11.; until then the row stayed there, greyed out)
    app._pick_mode("refine")
    app.root.update()
    assert app.v_mode.get() == "refine" and app.v_workflow.get() == "fibo2-edit.json"
    assert not shown(app.f_stage_row) and not shown(app.sep_stage_row) and not shown(app.f_scale)
    app.v_model.set("qwen")
    app._on_model()
    app._pick_mode("upscale")
    assert all(str(rb["state"]) == "normal" for rb in app.rb_scale.values())
    app.root.update()
    assert not shown(app.f_stage_row) and not shown(app.sep_stage_row)       # Qwen has no stage row (user 10.11.)
    # Flux 2 Upscale: always in tiles, no switch and no row (user 12.11.); Refine runs its own graph without tiles
    app.v_model.set("flux2")
    app._on_model()
    app.v_mode.set("upscale")
    app._on_mode()
    app.root.update()
    assert not shown(app.f_stage_row) and not [cb for cb in app.stage_row_cbs if shown(cb)] and not app._stages()
    assert app._request().stage_on and app.v_workflow.get() == "flux2-klein-upscale.json"
    app.v_mode.set("refine")
    app._on_mode()
    assert app.v_workflow.get() == "flux2-klein-refine.json"

    # the request through the function list is the request of setting the mode directly (PLAN.md 5.3 of 6.11.)
    import dataclasses

    def snap(model, mode, factor):
        app.v_model.set(model)
        app.v_mode.set("inpaint")
        app._on_model()
        app.v_mode.set(mode)
        app._on_mode()
        if factor:
            app.v_scale.set(factor)
            app._on_scale_pick()
        req = app._request()
        return dataclasses.asdict(req), app.t_prompt.get("1.0", "end").strip(), app.v_steps.get()

    for model in ("qwen", "flux2", "flux3"):
        for factor in ("x 1.5", "x 2", "x 3", "x 4"):
            old = snap(model, "upscale", factor)
            app.v_model.set(model)
            app.v_mode.set("inpaint")
            app._on_model()
            app._pick_mode("upscale")
            app.v_fac.set(factor)
            app._on_factor()
            new = (dataclasses.asdict(app._request()), app.t_prompt.get("1.0", "end").strip(), app.v_steps.get())
            assert new == old, (model, factor, [k for k in old[0] if old[0][k] != new[0][k]], old[1:], new[1:])
        old = snap(model, "refine", None)
        app.v_mode.set("inpaint")
        app._on_model()
        app._pick_mode("refine")
        new = (dataclasses.asdict(app._request()), app.t_prompt.get("1.0", "end").strip(), app.v_steps.get())
        assert new == old, (model, "refine", [k for k in old[0] if old[0][k] != new[0][k]])

    # Refine Image: one prompt per model (user 24.11.): Qwen Keep colors, Flux 2 Neutral, Flux 3 Restore; its text wins over yours
    app.v_model.set("flux2")
    app.v_mode.set("inpaint")
    app._on_model()
    app._pick_mode("refine")
    assert app._prompt_text() == models.RELIGHT_NEUTRAL and not shown(app.f_scale)
    app._pick_mode("upscale")
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "my own text")
    app._pick_mode("refine")                                            # Refine's stock text wins over your own text (user 11.11.)
    assert app.v_mode.get() == "refine" and app._prompt_text() == models.RELIGHT_NEUTRAL
    app.v_model.set("flux3")
    app._on_model()
    assert app._prompt_text() == models.FLUX3_RESTORE
    app.v_model.set("qwen")
    app._on_model()
    assert app._prompt_text() == models.QWEN_KEEP_COLORS

    assert app.b_mode["text"].startswith("Refine")
    app.root.destroy()
    print("ALL OK (Upscale and Refine, two functions)")


if __name__ == "__main__":
    main()
