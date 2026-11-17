"""Small window changes of 16.11., measured in the real Tk window (skipped when Tk cannot open one): the run bar half as high
(9 px instead of 18), the Generate row under the prompt and its tip for every function, no "Reset page" button in the
footer (the two resets are in the hamburger menu, tests/test_batch_gui.py).

    python tests/test_ui_tweaks_16_11.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-tweaks-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from tkinter import ttk  # noqa: E402

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, gui_theme, models  # noqa: E402


def make_app():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    return app


def main():
    app = make_app()
    try:
        # the run bar: its own thin style, half the height of the usual clam bar
        assert str(app.pb.cget("style")) == "Thin.Horizontal.TProgressbar"
        plain = ttk.Progressbar(app.root)
        plain.pack()
        app.root.update()
        assert app.pb.winfo_reqheight() * 2 == plain.winfo_reqheight(), (app.pb.winfo_reqheight(), plain.winfo_reqheight())
        plain.destroy()
        assert gui_theme.THIN_BAR_ARROW == 5
        # no "Reset page" button in the footer any more
        assert not hasattr(app, "b_reset")
        assert not any(str(w.cget("text")) == "Reset page" for w in app.f_foot.winfo_children() if "text" in w.keys())
        # the Generate row: under the grip, the tip and Describe, above the boxes under the prompt, for every function
        seen = 0
        for m in models.MODELS:
            for mode in m.modes:
                app.v_model.set(m.key)
                app.v_mode.set(mode)
                app._on_model()
                app.root.update_idletasks()
                order = [w for w in app.f_go.master.pack_slaves()]
                i_go = order.index(app.f_go)
                assert order.index(app.grip) < i_go, (m.key, mode)
                assert app.sep_prompt in order and order.index(app.sep_prompt) < order.index(app.grip)
                for w in (app.f_hint, app.b_describe):
                    if w in order:
                        assert order.index(w) < i_go, (m.key, mode, w)
                for w in (app.f_neg, app.f_enh, app.f_scale, app.f_gen):
                    if w in order:
                        assert order.index(w) > i_go, (m.key, mode, w)
                seen += 1
        assert seen > 20, seen
    finally:
        app.root.destroy()
    print("ok")


if __name__ == "__main__":
    main()
