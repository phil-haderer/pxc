"""The chip, Variants, Copy and "Copy download link" menus are self-drawn PopMenus (user 12.11.): real popups, blue hover row
with white text, the chosen Variants number shows the tick, no tk.Menu( left in the files of these menus. Hidden Tk window.

    python tests/test_ported_menus.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-ported-menus-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod, gui, popmenu  # noqa: E402
from pccomfy.gui_common import ACCENT, ON_ACCENT  # noqa: E402
from pccomfy.popmenu import PopMenu  # noqa: E402

MINE = ("gui_modes.py", "gui_run.py", "gui_theme.py", "ui_settings.py")


class Ev:
    x_root, y_root = 40, 40


def hover(m, i):
    x, y, w, h = m.geometry()
    mg = m._px(popmenu.MARGIN)      # vertical margin; none on the left and right
    m._pointer(x + 1 + mg + 8, y + 1 + mg + (m._rows[i][0] + m._rows[i][1]) // 2)
    assert m._cv.itemcget(f"bg{i}", "fill") == ACCENT and m._cv.itemcget(f"fg{i}", "fill") == ON_ACCENT


def main():
    for f in MINE:
        assert "tk.Menu(" not in (ROOT / "pccomfy" / f).read_text(encoding="utf-8"), f
    assert "install_menu_look" not in (ROOT / "pccomfy" / "gui_theme.py").read_text(encoding="utf-8")
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.root.update()
    assert isinstance(app.m_chip, PopMenu) and isinstance(app.m_variants, PopMenu)

    # chip menu: opens, hover is blue
    from pccomfy import models
    key = models.MODELS[0].key
    app._chip_menu(key, Ev())
    m = app.m_chip
    assert m.geometry() is not None and m.entrycget("end", "label") == "Hide this model"
    hover(m, m.index("end"))
    m.unpost()
    assert m.geometry() is None

    # Variants: under the split button, the chosen number has the tick
    app.v_variants.set(3)
    app._variants_menu()
    v = app.m_variants
    assert v.geometry() is not None and [v.entrycget(i, "label") for i in range(8)] == [str(n) for n in range(1, 9)]
    assert v._cv.find_withtag("tick2") and not v._cv.find_withtag("tick0")
    hover(v, 4)
    v._click(*_row_point(v, 4))
    app.root.update()
    app.root.update()
    assert app.v_variants.get() == 5 and v.geometry() is None
    assert app.w_variants.cget("text") == "×5 ▾"

    # Copy menu
    lb = tkinter.Label(app.root, text="some text to copy")
    e = Ev()
    e.widget = lb
    assert app._copy_menu(e) == "break"
    tops = [w for w in app.root.winfo_children() if w.winfo_class() == "Toplevel"]
    assert tops, "copy menu shown"
    for w in tops:
        w.destroy()

    # "Copy download link" over the settings window
    app._settings_win = win = tkinter.Toplevel(app.root)
    app._link_menu(e, "https://example.org/x")
    pops = [w for w in win.winfo_children() if w.winfo_class() == "Toplevel"]
    assert pops, "the link menu is a child of the settings window"
    for w in pops:
        w.destroy()
    win.destroy()
    app.root.destroy()
    print("test_ported_menus: ok")


def _row_point(m, i):
    x, y, w, h = m.geometry()
    mg = m._px(popmenu.MARGIN)      # vertical margin; none on the left and right
    return x + 1 + mg + 8, y + 1 + mg + (m._rows[i][0] + m._rows[i][1]) // 2


if __name__ == "__main__":
    main()
