# tags: window
"""Minimised during a run (user 24.11. evening, choice A, "nur die blaue linie"): the progress is a thin blue line along the
window's bottom edge, as wide as the progress, with nothing behind it; it goes at the end, when the run is cancelled and when
the window is shown again. Hidden real Tk window.

    python tests/test_mini_bar.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-minibar-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui  # noqa: E402


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    line = app.f_mini_bar
    on = lambda: line.winfo_manager() == "place"      # noqa: E731
    app._reset_progress()
    app._set_progress(0.3, "", "image", 0.3, 2.0)
    assert not on(), "not minimised: the normal bar only"
    app.toggle_minimize()
    info = line.place_info()
    assert on() and abs(float(info["relwidth"]) - 0.3) < 1e-6 and info["anchor"] == "sw" and float(info["rely"]) == 1.0, info
    assert int(info["height"]) == app._px(3) and str(line.cget("bg")) == gui.ACCENT and line.master is app.root, info
    app._set_progress(0.7, "", "image", 0.7, 5.0)
    assert abs(float(line.place_info()["relwidth"]) - 0.7) < 1e-6
    app.toggle_minimize()
    assert not on(), "shown again: the normal bar, no line"
    app.toggle_minimize()
    assert on() and abs(float(line.place_info()["relwidth"]) - 0.7) < 1e-6, "minimised again during the run: the line is back"
    app._reset_progress(done=True)
    assert not on(), "the run is done: the line goes"
    app._reset_progress()                                # the next run starts at 0
    app._set_progress(0.2, "", "image", 0.2, 1.0)
    assert on()
    app._reset_progress()                                # cancelled
    assert not on()
    app.toggle_minimize()
    app.root.destroy()
    print("test_mini_bar: ok")


if __name__ == "__main__":
    main()
