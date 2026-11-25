# tags: window
"""The head chips fill their text in one step, with exactly the result of adding one thin space at a time (tempo plan P3,
24.11.; the window head is "perfect", CLAUDE.md), and with far fewer measures.

    python tests/test_chip_fill_same.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.withdraw()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import gui_modes, models  # noqa: E402
from pccomfy.gui_modes import ModeMixin  # noqa: E402


class Head(ModeMixin):
    def __init__(self, root):
        self.root = root
        self.calls = 0

    def _pick_measure(self, text):
        self.calls += 1
        return ModeMixin._pick_measure(self, text)


def old_text(app, text, width):
    """The code before 24.11., unchanged."""
    fill = " " if app._pick_measure(" ") > 0 else " "
    out, n = text, 0
    while app._pick_measure(out + fill) <= width and n < 400:
        out += fill
        n += 1
    return out + gui_modes.PICK_ARROW


def main():
    app = Head(_r)
    texts = {m.label for m in models.BY_KEY.values()} | {"", "x", gui_modes.MODEL_PICK_EMPTY}
    for m in models.BY_KEY.values():
        texts |= set(m.modes)
    texts |= {"Text to Image", "Multi image edit", "Scribble with reference", "Upscale", "Refine Image"}
    old_calls = new_calls = checked = 0
    for t in sorted(texts):
        for width in list(range(0, 260, 19)) + [2000]:          # the old way needs a measure per space: keep the list short
            app.calls = 0
            want = old_text(app, t, width)
            old_calls += app.calls
            app.calls = 0
            got = app._pick_text(t, width)
            new_calls += app.calls
            assert got == want, (t, width, len(got), len(want))
            checked += 1
    assert new_calls * 5 < old_calls, f"far fewer measures: {new_calls} against {old_calls}"
    print(f"ok: {checked} chip texts the same as before, {new_calls} measures instead of {old_calls}")


if __name__ == "__main__":
    try:
        main()
    finally:
        _r.destroy()
