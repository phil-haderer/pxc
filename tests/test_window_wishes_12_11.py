"""Small window wishes of 12.11. (PC A), measured in the real Tk window (hidden; skipped when Tk cannot open a window):
the Advanced settings boxes and captions, the gap under the LLM row, the closed Advanced settings row, the spin box arrows.

    python tests/test_window_wishes_12_11.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-wishes-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models  # noqa: E402


def right(w) -> int:
    return w.winfo_rootx() + w.winfo_width()


def bottom(w) -> int:
    return w.winfo_rooty() + w.winfo_height()


def make_app():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    return app


def advanced_checks(app):
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.v_adv_open.set(True)
    app._show_advanced()
    app.root.update()
    # Scheduler ends on the line of the other boxes (the slider percent boxes, the Advanced settings frame), not 6 px short
    assert abs(right(app.cb_sched) - right(app.f_adv)) <= 1, (right(app.cb_sched), right(app.f_adv))
    # Steps / CFG / Seed: the caption ends where its box begins (the seed button used to make the row taller and push the box down)
    for w in (app.w_steps, app.w_cfg, app.w_seed):
        cap = [c for c in w.master.grid_slaves(row=0, column=int(w.grid_info()["column"]))][0]
        assert 0 <= w.winfo_rooty() - bottom(cap) <= 1, (cap.cget("text"), w.winfo_rooty(), bottom(cap))
    # the seed button sits level with the box (centres within 2 px)
    mid = lambda w: w.winfo_rooty() + w.winfo_height() / 2      # noqa: E731
    assert abs(mid(app.b_last_seed) - mid(app.w_seed)) <= 2, (mid(app.b_last_seed), mid(app.w_seed))


def llm_gap_checks(app):
    """MOSS Text to image: under "Enhance my Prompt with LLM" the LoRA rows follow with the same 2 px as between two of them."""
    app.v_model.set("moss")
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    rows = [w for w in [app.cb_turbo] + app.stage_cbs if w.winfo_ismapped()]
    assert app.f_enh.winfo_ismapped() and len(rows) >= 2, ([str(w) for w in rows])
    below_llm = rows[0].winfo_rooty() - bottom(app.f_enh)
    between = rows[1].winfo_rooty() - bottom(rows[0])
    assert abs(below_llm - between) <= 1, (below_llm, between)
    # the copy icon must not make the LLM row taller than its checkbox (at 150 % it did: 30 px against 26, 4 px more gap; 13.11.)
    assert app.b_copy.winfo_reqheight() <= app.cb_enhance.winfo_reqheight(), (app.b_copy.winfo_reqheight(), app.cb_enhance.winfo_reqheight())
    assert app.f_enh.winfo_height() == app.cb_enhance.winfo_height(), (app.f_enh.winfo_height(), app.cb_enhance.winfo_height())


def closed_advanced_checks(app):
    """The closed "Advanced settings" row takes 20 % less room above and below its text, measured on screen (user 12.11.; the first
    try changed pads that spacing.scale rounded back to the old values): no inner padding in the button, the outer gap 2."""
    from pccomfy import spacing
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.v_adv_open.set(False)
    app._show_advanced()
    app.root.update()
    assert str(app.btn_adv.cget("style")) == "Adv.Link.TButton"
    pad = app.root.tk.call("ttk::style", "lookup", "Adv.Link.TButton", "-padding")
    assert [int(str(p)) for p in (pad if isinstance(pad, (tuple, list)) else str(pad).split())] in ([0], [0, 0]), pad
    v = app.f_adv.pack_info()["pady"]
    assert [int(x) for x in (v if isinstance(v, (tuple, list)) else (v, v))] == [spacing.scale(2), 0], v
    par = app.f_adv.master
    rows = sorted([w for w in par.pack_slaves() if w.winfo_ismapped()], key=lambda w: w.winfo_rooty())
    below = rows[rows.index(app.f_adv) + 1]
    assert below is app.sep_status, below           # the line above the progress line follows directly
    if abs(spacing._factor - 0.5719) < 0.01:     # the scale of the user's PC A, where the picture was measured
        import tkinter.font as tkf
        from pccomfy.gui_common import font
        f = tkf.Font(root=app.root, font=font(9))
        th = f.metrics("linespace")
        text_top = app.btn_adv.winfo_rooty() + (app.btn_adv.winfo_height() - th) / 2
        # free rows in the picture: line to text and text to line, both 10 before (user: 6, second round 12.11.)
        assert text_top - bottom(app.sep_adv) <= 6, text_top - bottom(app.sep_adv)
        assert app.sep_status.winfo_rooty() - (text_top + th) <= 7, app.sep_status.winfo_rooty() - (text_top + th)


def small_window_place_checks(app):
    """Queue: where the settings window opens (beside the plugin window, tops level). Batch: beside the plugin window on the side
    of the ⋯ button with the same gap, bottom edges level, and it keeps that bottom edge when it grows (user 12.11.)."""
    app.root.deiconify()
    app.root.update()
    try:
        app.open_queue()
        app.root.update()
        q = app._queue_win
        want = (app.root.winfo_rootx() + app.root.winfo_width() + 8, app.root.winfo_rooty())
        assert abs(q.winfo_rootx() - want[0]) <= 2 and abs(q.winfo_rooty() - want[1]) <= 2, ((q.winfo_rootx(), q.winfo_rooty()), want)
        app._queue_close()
        app.open_batch()
        app.root.update()
        w, r = app._batch_dlg, app.root
        assert w.winfo_ismapped()
        assert abs(w.winfo_rootx() - (right(r) + 8)) <= 2, (w.winfo_rootx(), right(r))
        assert abs(bottom(w) - bottom(r)) <= 2, (bottom(w), bottom(r))
        import tkinter.ttk as ttk
        ttk.Label(w, text="one more line\nand another\nand a third").pack()     # the content grows (a folder was chosen …)
        for _ in range(5):
            app.root.update()
        assert abs(bottom(w) - bottom(r)) <= 2, ("after growing", bottom(w), bottom(r))
        app._batch_close()
        # the dry run opens where the batch window was: beside the plugin, bottom edges level (user 13.11.)
        from PIL import Image
        app._batch_dry_dialog({"batch": "b1", "job": {}, "results": [], "placed": "layer",
                               "image": Image.new("RGB", (64, 64), "red"), "error": ""})
        app.root.update()
        d = app._dry_dlg
        assert d.winfo_ismapped()
        assert abs(d.winfo_rootx() - (right(r) + 8)) <= 2, (d.winfo_rootx(), right(r))
        assert abs(bottom(d) - bottom(r)) <= 2, (bottom(d), bottom(r))
        app._dry_close()
    finally:
        app.root.withdraw()


def spin_arrow_checks():
    """The spin box arrows: filled triangles in full white, no outline, 10 % smaller than the former 19 px."""
    from pccomfy import icons
    from pccomfy.gui_theme import SPIN_ARROW, SPIN_PX
    assert SPIN_ARROW == "#ffffff" and SPIN_PX == round(19 * 0.9), (SPIN_ARROW, SPIN_PX)
    for up in (True, False):
        im = icons.spin_arrow(up, SPIN_ARROW, SPIN_PX)
        assert im.width == SPIN_PX and im.height < SPIN_PX
        px = [im.getpixel((x, y)) for y in range(im.height) for x in range(im.width) if im.getpixel((x, y))[3] > 0]
        assert px and all(p[:3] == (255, 255, 255) for p in px)            # white everywhere: no dark fringe, no second colour
        full = [p for p in px if p[3] == 255]
        assert len(full) >= 8                                                 # a filled area, not a line
        rows = [sum(1 for x in range(im.width) if im.getpixel((x, y))[3] > 128) for y in range(im.height)]
        rows = [n for n in rows if n]
        assert rows == sorted(rows, reverse=not up)   # the triangle widens towards its base (up: base below)
        assert rows[0] != rows[-1]


def main():
    spin_arrow_checks()
    app = make_app()
    advanced_checks(app)
    closed_advanced_checks(app)
    llm_gap_checks(app)
    small_window_place_checks(app)
    print("ALL OK (window wishes 12.11.)")


if __name__ == "__main__":
    main()
