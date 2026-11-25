# tags: window
"""Main window layout wishes of 13.11., measured in the real Tk window (shown for a moment; skipped when Tk cannot open one):
the status line as wide as the lines above Advanced settings, the tip text level with its icon, the placeholder where typed
text starts, the MiniMax size row without a label and left-aligned.

    python tests/test_main_window_layout_13_11.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-layout-")
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


def make_app():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    return app


def left(w):
    return w.winfo_rootx()


def right(w):
    return w.winfo_rootx() + w.winfo_width()


def status_checks(app):
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.v_status.set("A long message that has to wrap onto a second line because it is longer than the window is wide. " * 2)
    app.root.update()
    # the text wraps at the right edge of that line (it used to wrap 20 px short), less the red "!" and its gap while an
    # error shows it. Since T5 (24.11.) port 1 fails at once, so "ComfyUI is not running" (with "!") can arrive during this
    # check; before, it came 4 s later. The window sets the length in its <Configure> handler: wait for it, at most 2 s.
    def wanted():
        w = app.f_status.winfo_width()
        return w - (app.lbl_err.winfo_reqwidth() + app._px(8)) if app.lbl_err.winfo_manager() else w
    end = time.time() + 2
    while time.time() < end and int(app.lbl_status.cget("wraplength")) != wanted():
        app.root.update()
        time.sleep(0.02)
    assert abs(left(app.f_status) - left(app.sep_adv)) <= 1 and abs(right(app.f_status) - right(app.sep_adv)) <= 1, \
        (left(app.f_status), right(app.f_status), left(app.sep_adv), right(app.sep_adv))
    assert int(app.lbl_status.cget("wraplength")) == wanted(), (app.lbl_status.cget("wraplength"), wanted(), app.f_status.winfo_width())
    app.v_status.set("")
    app.root.update()


def hint_checks(app):
    """The tip's first line sits HINT_TEXT_DROP px (scaled) lower than the top of its icon."""
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    if not app.f_hint.winfo_manager():
        print("  (no tip shown here, hint check skipped)")
        return
    ipad = app.lbl_hint_icon.pack_info()["pady"]
    tpad = app.lbl_hint.pack_info()["pady"]
    top = lambda p: int(p if isinstance(p, (int, str)) and str(p).lstrip("-").isdigit() else p[0])   # noqa: E731
    drop = top(tpad) - top(ipad)
    assert drop == app._px(4 + gui_theme_drop()) - app._px(4), (drop, tpad, ipad)
    assert drop >= 1


def gui_theme_drop():
    from pccomfy import gui_theme
    return gui_theme.HINT_TEXT_DROP


def placeholder_checks(app):
    """The placeholder label starts where typed text starts: place() counts from inside the Text's border and padding."""
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.t_prompt.delete("1.0", "end")
    app.root.update()
    app._prompt_placeholder(focused=False)
    app.root.update()
    assert app._ph_on
    info = app._ph.place_info()
    assert int(info["x"]) == 0 and int(info["y"]) == 0, info
    assert str(app._ph.cget("font")) == str(app.t_prompt.cget("font")), (app._ph.cget("font"), app.t_prompt.cget("font"))
    assert app._ph.cget("fg") == gui.DISABLED


def minimax_checks(app):
    app.v_model.set("minimax")
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    assert app.f_gen.winfo_manager(), "size row shown"
    kids = [str(k) for k in app.f_gen.winfo_children()]
    assert not [k for k in kids if k.rsplit(".", 1)[-1].startswith("!label")], kids      # no "Size" caption
    first = app.rb_gen[models.GEN_MP_STEPS[0]]
    assert abs(left(first) - left(app.f_gen)) <= 1, (left(first), left(app.f_gen))


def minimax_advanced_checks(app):
    """MiniMax, Advanced settings (user 18.11.): no empty line before Steps. The finishing rows' box (f_post) has no row for
    MiniMax; Tk kept its last height, so it stayed in the grid as a blank line. It is in the grid only while a row is in it."""
    import time

    def settle():
        for _ in range(15):
            app.root.update()
            time.sleep(0.03)
    if not app.v_adv_open.get():
        app._toggle_advanced()
    for model, mode in (("qwen", "inpaint"), ("minimax", "txt2img"), ("minimax", "edit")):
        app.v_model.set(model)           # qwen Fill first: the box has rows and a height that could be left over
        app.v_mode.set(mode)
        app._on_model()
        settle()
        if model == "qwen":
            assert app.f_post.winfo_manager() == "grid" and app.f_post.winfo_height() > 1
            continue
        assert not app.f_post.pack_slaves() and not app.f_post.winfo_manager(), (mode, "empty box must leave the grid")
        assert not app.lbl_grp_fn.winfo_manager(), (mode, "no function heading over an empty box (20.11.)")
        top = min(w.winfo_y() for w in app.adv_body.grid_slaves() if w.winfo_ismapped())
        assert app.lbl_grp_samp.winfo_y() == top, (mode, "the heading Sampling starts the Advanced settings")
        steps = app.w_steps.winfo_y() + app.w_steps.master.winfo_y()
        under = app.lbl_grp_samp.winfo_y() + app.lbl_grp_samp.winfo_height()
        assert top <= 10 and steps - under < 30, (mode, "Steps must follow right under Sampling", top, under, steps)
    app.v_model.set("qwen")              # and the box comes back with its rows
    app.v_mode.set("inpaint")
    app._on_model()
    settle()
    assert app.f_post.winfo_manager() == "grid" and app.f_post.winfo_height() > 1


def main():
    app = make_app()
    app.root.deiconify()
    app.root.update()
    status_checks(app)
    hint_checks(app)
    placeholder_checks(app)
    minimax_checks(app)
    minimax_advanced_checks(app)
    print("ALL OK (main window layout 13.11.)")


if __name__ == "__main__":
    main()
