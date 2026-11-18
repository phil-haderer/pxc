"""Model chips without gaps (user 11.12.): neighbours share one grey 1 px line, missing slots have no lines, a short last row
(one or two chips) is centred (user 18.11.), and the longest
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
        self.cols = {}

    def grid(self, **k):
        self.g = k

    def grid_remove(self):
        self.g = None

    def columnconfigure(self, c, **k):
        self.cols[c] = k


class Fake:
    _grid_chip = gui.App._grid_chip


def layout(n, f=None):
    f = f or Fake()
    if not hasattr(f, "f_models"):
        f.f_models, f.f_chip_short = W(), W()
    f.chip_lines = {i: W() for i in range(n)}
    f.rb_tabs = {i: W() for i in range(n)}
    for i in range(n):
        f._grid_chip(i, i, n)
    return f


def at(f, i):
    """(frame, row, column) of chip i: "grid" = the 3-column grid, "short" = the centred frame of a short last row."""
    g = f.rb_tabs[i].g
    return ("grid" if g["in_"] is f.f_models else "short" if g["in_"] is f.f_chip_short else "?", g["row"], g["column"])


def short_weights(f, cols=3):
    return [f.f_chip_short.cols[c]["weight"] for c in range(cols + 2)]


def main():
    # 7 chips: rows 3 + 3 + 1. Left/top line on every chip; right line only at the end of a row; bottom only with nothing below
    f = layout(7)
    p = {i: (f.rb_tabs[i].g["padx"], f.rb_tabs[i].g["pady"]) for i in range(7)}
    assert p[0] == ((1, 0), (1, 0)) and p[1] == ((1, 0), (1, 0))        # shared lines: none of its own right / bottom
    assert p[2] == ((1, 1), (1, 0))                                     # end of the row: right line
    # the row above a short (centred) row draws every bottom line itself; the centred chip has no top line of its own,
    # so where the rows meet the line stays 1 px
    assert p[3] == ((1, 0), (1, 1)) and p[4] == ((1, 0), (1, 1)) and p[5] == ((1, 1), (1, 1))
    assert p[6] == ((1, 1), (0, 1))                                     # the single chip of the last row: right and bottom
    assert all(f.chip_lines[i].g["sticky"] == "nsew" and all(f.chip_lines[i].g[x] == f.rb_tabs[i].g[x]
               for x in ("in_", "row", "column")) for i in range(7))
    # centred short row (user 18.11.): full rows stay in the 3-column grid, the last chip goes into the frame of the short
    # row, which spans the whole grid width under row 1; its side columns weigh cols - k = 2, the chip 2 (one third)
    assert [at(f, i) for i in range(7)] == [("grid", 0, 0), ("grid", 0, 1), ("grid", 0, 2),
                                            ("grid", 1, 0), ("grid", 1, 1), ("grid", 1, 2), ("short", 0, 1)]
    assert f.f_chip_short.g == {"row": 2, "column": 0, "columnspan": 3, "sticky": "ew"}
    assert short_weights(f) == [2, 2, 2, 0, 0] and f.f_chip_short.cols[0]["uniform"] == f.f_chip_short.cols[1]["uniform"] != ""
    # two chips in the last row: sides 1, chips 2 each (1/6 + 1/3 + 1/3 + 1/6)
    f = layout(5)
    assert [at(f, i) for i in range(3, 5)] == [("short", 0, 1), ("short", 0, 2)] and f.f_chip_short.g["row"] == 1
    assert short_weights(f) == [1, 2, 2, 1, 0]
    assert [f.rb_tabs[i].g["pady"] for i in range(5)] == [(1, 1)] * 3 + [(0, 1)] * 2
    assert f.rb_tabs[3].g["padx"] == (1, 0) and f.rb_tabs[4].g["padx"] == (1, 1)
    # full grid: nothing moves, no short-row frame, bottom line only on the last row
    f = layout(6)
    assert [at(f, i) for i in range(6)] == [("grid", r, c) for r in range(2) for c in range(3)] and f.f_chip_short.g is None
    assert [f.rb_tabs[i].g["pady"] for i in range(6)] == [(1, 0)] * 3 + [(1, 1)] * 3
    # re-flow (a model hidden, then shown again): the short-row frame comes and goes, its weights follow the count
    f = layout(5, layout(7))
    assert short_weights(f) == [1, 2, 2, 1, 0] and f.f_chip_short.g["row"] == 1
    f = layout(6, f)
    assert f.f_chip_short.g is None
    # a single short row (models hidden): centred, closed on all sides, no cells (so no lines) beyond its chips
    f = layout(2)
    assert [at(f, i) for i in range(2)] == [("short", 0, 1), ("short", 0, 2)] and f.rb_tabs[1].g["padx"] == (1, 1)
    assert all(f.rb_tabs[i].g["pady"] == (1, 1) for i in range(2)) and f.f_chip_short.g["row"] == 0
    f = layout(1)
    assert at(f, 0) == ("short", 0, 1) and short_weights(f) == [2, 2, 2, 0, 0]
    assert f.rb_tabs[0].g["padx"] == (1, 1) and f.rb_tabs[0].g["pady"] == (1, 1)

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
