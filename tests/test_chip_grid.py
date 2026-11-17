"""Model chips without gaps (user 11.12.): neighbours share one grey 1 px line, missing slots have no lines, and the longest
chip label ("Fibo 2.0 Edit Turbo", bold when chosen) fits at the narrow window width MIN_W.

    python tests/test_chip_grid.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui = t.gui
models = gui.models


class W:
    def __init__(self):
        self.g = None

    def grid(self, **k):
        self.g = k


class Fake:
    _grid_chip = gui.App._grid_chip


def layout(n):
    f = Fake()
    f.chip_lines = {i: W() for i in range(n)}
    f.rb_tabs = {i: W() for i in range(n)}
    for i in range(n):
        f._grid_chip(i, i, n)
    return f


def main():
    # 7 chips: rows 3 + 3 + 1. Left/top line on every chip; right line only at the end of a row; bottom only with nothing below
    f = layout(7)
    p = {i: (f.rb_tabs[i].g["padx"], f.rb_tabs[i].g["pady"]) for i in range(7)}
    assert p[0] == ((1, 0), (1, 0)) and p[1] == ((1, 0), (1, 0))        # shared lines: none of its own right / bottom
    assert p[2] == ((1, 1), (1, 0))                                     # end of the row: right line
    assert p[3] == ((1, 0), (1, 0)) and p[4] == ((1, 0), (1, 1)) and p[5] == ((1, 1), (1, 1))   # nothing below chips 4 and 5
    assert p[6] == ((1, 1), (1, 1))                                     # the single chip of the last row is closed on all sides
    assert all(f.chip_lines[i].g["sticky"] == "nsew" and (f.chip_lines[i].g["row"], f.chip_lines[i].g["column"]) ==
               (f.rb_tabs[i].g["row"], f.rb_tabs[i].g["column"]) for i in range(7))
    # a short row has no cells (so no lines) beyond its chips: two chips only use columns 0 and 1
    f = layout(2)
    assert [f.rb_tabs[i].g["column"] for i in range(2)] == [0, 1] and f.rb_tabs[1].g["padx"] == (1, 1)

    # Fibo's label fits: the chosen (SemiBold) text at the font size of the chips against one third of the window
    try:
        from PIL import ImageFont
    except ImportError:
        print("ALL OK (chip grid; PIL missing, width not measured)")
        return
    fonts = Path(gui.__file__).resolve().parent / "assets" / "fonts" / "Inter-SemiBold.ttf"
    # BASIC layout on every PC: with raqm (found on some PCs, e.g. through a fribidi DLL) Pillow measures 100.0 px, without it
    # 104.0 px (hinted whole-pixel advances, no kerning), so the test was green on PC B and red on PC A (12.11.)
    ft = ImageFont.truetype(str(fonts), 11, layout_engine=ImageFont.Layout.BASIC)   # font(9) = Inter 8 pt = 11 px at 96 dpi
    text = max(ft.getlength(m.label) for m in models.MODELS)
    inner = (gui.MIN_W - 2 * 10) / 3 - 1 - 1 - 2             # cell minus left line, right line (last chip), clam border 1 px a side
    # User 12.11.: "Fibo 2.0 Edit Turbo" looks fine at MIN_W 333 (Tk at 175 %: 179 px text in 179 px; at 100 % about 2 px
    # short, accepted). The allowance keeps today's state and stops any longer label or narrower window.
    allowance = 4
    print(f"longest label {text:.1f} px, room {inner:.1f} px + {allowance} px allowance")
    assert gui.CHIP_PAD_X == 0 and text + 2 * gui.CHIP_PAD_X <= inner + allowance, (text, inner)
    print("ALL OK (chip grid)")


if __name__ == "__main__":
    main()
