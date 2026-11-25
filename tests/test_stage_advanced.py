# tags: window, moss
"""Layout checks in the real window (hidden Tk): a stage marked `advanced` (MOSS' skip-layer guidance) has its checkbox at the top of the
Advanced settings, Fibo Upscale shows its two stages in the switch box, and the reference images show the BBOX row only for Flux 3.

    python tests/test_stage_advanced.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-sa-")
os.environ["PCCOMFY_NO_TIPS"] = "1"
sys.path.insert(0, str(ROOT))
try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models  # noqa: E402


def shown(w) -> bool:
    return bool(w.winfo_manager())


def tab_shown(app, key) -> bool:
    """An Edit / Fill tab is offered: the list chip is shown and has it (a list instead of tabs since 20.11.)."""
    return getattr(app, "f_edtabs", None) is not None and shown(app.f_edtabs) and key in app._edtab_shown


def pick(app, model, mode):
    app.v_model.set(model)
    app.v_mode.set(mode)
    app._on_model()
    app.root.update()


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.cb_workflow["values"] = [gui.BUILTIN] + sorted({w for m in models.MODELS for w in m.workflows()})
    for _ in range(10):
        app.root.update()
        time.sleep(0.02)

    pick(app, "moss", "txt2img")        # skip-layer guidance: a twin at the top of the Advanced settings, the UltraReal LoRA stays in the box
    assert shown(app.stage_adv_cbs[1]) and app.stage_adv_cbs[1].grid_info()["row"] == 3 and int(app.f_post.grid_info()["row"]) == 1   # under "Sampling" (20.11.)
    assert not shown(app.stage_cbs[1]) and shown(app.stage_cbs[0]) and not shown(app.stage_adv_cbs[0])
    app.stage_adv_cbs[1].invoke()
    assert app.v_stage2.get() and app._request().stages_off == []        # the twin switches the same stage
    app.stage_adv_cbs[1].invoke()
    assert not app.v_stage2.get()
    # MOSS' Turbo LoRA alone at the top of the Advanced settings (finishing box), UltraReal stays under the prompt (user 20.11.)
    assert app.f_turbo.winfo_manager() == "pack" and str(app.f_turbo.pack_info()["in"]) == str(app.f_samp), app.f_turbo.winfo_manager()
    assert shown(app.f_opts) and app.f_opts.winfo_manager() == "pack" and getattr(app, "_opts_place", "") == ""
    assert shown(app.f_samp) and shown(app.lbl_grp_samp)      # the groups (20.11., B)
    assert int(app.f_samp.grid_info()["row"]) == 4 and not hasattr(app, "lbl_grp_fn")   # no function heading (user 25.11.)
    for model, mode in (("qwen", "inpaint"), ("moss", "txt2img"), ("qwen", "txt2img")):   # back in the switch box for Qwen, and above it
        pick(app, model, mode)
        if model == "qwen":
            assert app.f_turbo.winfo_manager() == "grid" and str(app.f_turbo.grid_info()["in"]) == str(app.f_opts)
        else:
            assert app.f_turbo.winfo_manager() == "pack"
    pick(app, "flux3", "edit")          # no LoRA of its own: no row anywhere
    assert not shown(app.f_turbo)

    pick(app, "fibo", "upscale")        # two stages in the row of the Upscale / Refine box (8.11.), none in the box or the Advanced settings
    assert shown(app.stage_row_cbs[0]) and shown(app.stage_row_cbs[1]) and not shown(app.stage_cbs[0]) and not shown(app.stage_cbs[1])
    assert not shown(app.stage_adv_cbs[0]) and not shown(app.stage_adv_cbs[1])
    assert [c["text"] for c in app.stage_row_cbs[:2]] == ["4x UltraSharp first", "Tiles"]

    pick(app, "flux2", "multi_edit")
    app._refs_update()
    app.root.update()
    # the BBOX tick is a tab now (user 7.11.): no tick, no empty row; the tab only with Flux 3
    app._refs_update()
    app.root.update()
    assert not shown(app.f_refhead2) and not shown(app.cb_bbox) and not tab_shown(app, "bbox")
    pick(app, "flux3", "multi_edit")
    app._refs_update()
    app.root.update()
    assert not shown(app.f_refhead2) and not shown(app.cb_bbox) and not tab_shown(app, "bbox")   # under Fill since 11.11.
    pick(app, "flux3", "inpaint")
    app._refs_update()
    app.root.update()
    assert tab_shown(app, "bbox") and tab_shown(app, "fill")

    # Advanced settings (user 20.11.): A the head row names model and function, C a blue dot beside a changed value and
    # "Reset" in the head row (also closed); Reset keeps the prompt and the switches under the prompt
    def settle():
        for _ in range(8):
            app.root.update()
            time.sleep(0.02)
    if not app.v_adv_open.get():
        app._toggle_advanced()
    pick(app, "qwen", "inpaint")
    settle()
    assert "Fill" in str(app.lbl_adv_ctx.cget("text"))
    ctx = str(app.lbl_adv_ctx.cget("text"))
    assert ctx == "Fill Selection" or ctx.startswith("Fill Selection · "), ctx     # the function first, then the model (user 22.11.); picker name (25.11.)
    # the last row (user 25.11.): "Save settings" with the disk and "Load defaults", equal halves of the whole width
    settle()
    sv, ld = app.b_save_page, app.b_load_std
    assert str(sv.cget("text")) == "Save settings" and sv.cget("image") and str(ld.cget("text")) == "Load defaults"
    assert int(app.f_page_btns.grid_info()["row"]) == 10
    assert abs(sv.winfo_width() - ld.winfo_width()) <= 1, (sv.winfo_width(), ld.winfo_width())
    assert sv.winfo_rootx() == app.adv_body.winfo_rootx(), (sv.winfo_rootx(), app.adv_body.winfo_rootx())
    assert ld.winfo_rootx() + ld.winfo_width() == app.adv_body.winfo_rootx() + app.adv_body.winfo_width()
    assert sv.winfo_rooty() == ld.winfo_rooty() and sv.winfo_height() == ld.winfo_height() and sv.winfo_rooty() > app.f_xl.winfo_rooty(), (sv.winfo_rooty(), ld.winfo_rooty(), app.f_xl.winfo_rooty(), sv.winfo_ismapped(), app.f_xl.winfo_ismapped())
    # Save keeps the window as it is (a real round trip through the standard settings, prompt and Ctrl+Z history included)
    app.v_feather.set(7.0)
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a blue door")
    before = app._collect()
    sv.invoke()
    settle()
    assert app._collect() == before, [k for k in before if app._collect().get(k) != before[k]]
    assert cfgmod.saved_page("qwen", "inpaint") == {"feather_pct": 7.0}, cfgmod.saved_page("qwen", "inpaint")
    assert not [w for w, d in getattr(app, "_dot_w", {}).items() if d.winfo_manager()], "saved = start values: no blue dot"
    ld.invoke()
    settle()
    assert cfgmod.saved_page("qwen", "inpaint") == {} and app.v_feather.get() != 7.0
    # a narrow row cuts the model name with "…" instead of dropping it (user 25.11.: "Remove Selection Fibo 2.0 Edit T.")
    app.v_model.set("fibo")
    app.v_mode.set("remove")
    app._on_model()
    real = app.f_adv_head.winfo_width
    from tkinter import font as tkfont
    fnt = tkfont.Font(root=app.root, font=gui.ttk.Style().lookup("Muted.TLabel", "font") or None)
    want = "Remove Selection · Fibo 2.0 Edit T…"
    room = fnt.measure(want) + 2
    extra = int(app.btn_adv.winfo_reqwidth()) + app._px(16)
    app.f_adv_head.winfo_width = lambda: room + extra
    app._show_adv_context()
    got = str(app.lbl_adv_ctx.cget("text"))
    assert got.startswith("Remove Selection · Fibo") and got.endswith("…") and fnt.measure(got) <= room, got
    app.f_adv_head.winfo_width = lambda: fnt.measure("Remove Selection") + 2 + extra
    app._show_adv_context()
    assert str(app.lbl_adv_ctx.cget("text")) == "Remove Selection", app.lbl_adv_ctx.cget("text")
    app.f_adv_head.winfo_width = real
    dots = lambda: [w for w, d in getattr(app, "_dot_w", {}).items() if d.winfo_manager()]     # noqa: E731
    assert not dots(), "startup values: no dot"
    assert not hasattr(app, "b_adv_reset") and not hasattr(app, "_reset_advanced"), "no Reset in the head row (user 25.11.)"
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red flower")
    app.v_context.set(0.7)
    settle()
    assert dots() == [app._adv_anchor["context"]], dots()
    app.v_context.set(0.4)
    settle()
    assert not dots()
    pick(app, "moss", "txt2img")       # UltraReal sits under the prompt: switching it is no change of the Advanced settings
    settle()
    app.v_stage.set(not app.v_stage.get())
    settle()
    assert not dots()
    app.v_turbo.set(not app.v_turbo.get())       # MOSS' Turbo LoRA is in the Advanced settings
    settle()
    assert app.cb_turbo in dots(), dots()
    print("ALL OK (stage in Advanced, Fibo stages, reference row, Advanced head row and changed dots)")


if __name__ == "__main__":
    main()
