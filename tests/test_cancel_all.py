"""Cancel and Cancel all with variants that run one after the other (Bridge._run_sequence, user 3.11.): Cancel ends only the
variant that is running, Cancel all ends it and the ones still to come. Also the buttons of the window.

    python tests/test_cancel_all.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-ca-")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as T  # noqa: E402
from pccomfy import workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402
from pccomfy.comfy import Cancelled  # noqa: E402

REFINE = ROOT / "workflows" / "flux3-klein-refine.json"


class CancelAt(T.FakeComfy):
    """Raises Cancelled in the wait of the given runs (0-based), as the real wait does once the cancel flag is set."""
    def __init__(self, bridge, at, how):
        super().__init__()
        self.bridge, self.at, self.how, self.n = bridge, set(at), how, 0

    def wait(self, pid, on_progress=None, cancelled=None, timeout=0, on_preview=None):
        k, self.n = self.n, self.n + 1
        if k in self.at:
            getattr(self.bridge, self.how)()
            assert cancelled()
            raise Cancelled()
        return super().wait(pid, on_progress, cancelled, timeout, on_preview)


def run(at, how, variants=3):
    pc, _, b = T.make(tempfile.mkdtemp(), with_sel=False)
    b.comfy = CancelAt(b, at, how)
    req = Request(mode="refine", workflow=str(REFINE), scale=1.0, variants=variants)
    req.params = workflows.GenParams(prompt="", seed=7)
    try:
        return b, b.run(req)
    except Cancelled:
        return b, None


def bridge_tests():
    b, res = run({1}, "cancel")                     # Cancel in the middle one: the first and the last still come
    assert res and len(res["layers"]) == 2 and not b.cancel_all_requested(), res
    b, res = run({1}, "cancel_all")                 # Cancel all: nothing after it
    assert res is None and b.cancel_all_requested() and len(b.comfy.graphs) == 2, len(b.comfy.graphs)   # the third never starts
    b, res = run({0, 1, 2}, "cancel")               # every variant cancelled one by one: the run is cancelled
    assert res is None
    b, res = run({2}, "cancel")                     # the last one cancelled, two results stay
    assert res and len(res["layers"]) == 2
    b, res = run({0}, "cancel", variants=1)         # a single run: Cancel ends it
    assert res is None
    b.reset_cancel_all()
    assert not b.cancel_all_requested()


def row_checks(app, gui, stop_all=False):
    """The Generate row (user 18.11., decisions 1a, 2a and 3): over the full width with no room left but the gap before
    Undo; Generate + the variants piece exactly as wide as the tab "Edit canvas"; the variants piece and Stop within their
    caps (natural width up to 1.2x); Undo and Redo squares as high as Generate at the right edge."""
    row = app.f_go.winfo_width()
    go, var, stop, undo, redo = app.b_go, app.w_variants, app.b_stop, app.b_undo, app.b_redo
    tab = app.rb_edtabs["edit"]
    assert tab.winfo_ismapped()
    pair_w = var.winfo_x() + var.winfo_width() - go.winfo_x()
    if stop_all:        # the row may be short then (100 %: 7 px): Generate gives that back, never more than the tab
        assert tab.winfo_width() - app._px(12) <= pair_w <= tab.winfo_width(), (pair_w, tab.winfo_width())
    else:
        assert pair_w == tab.winfo_width(), (go.winfo_width(), var.winfo_width(), tab.winfo_width())
    assert go.winfo_x() == 0 and redo.winfo_x() + redo.winfo_width() == row, (redo.winfo_x(), redo.winfo_width(), row)
    for w, cap in ((var, gui.VARIANTS_GROW_MAX), (stop, gui.STOP_GROW_MAX)):
        assert w.winfo_reqwidth() <= w.winfo_width() <= w.winfo_reqwidth() * cap + 1, (w, w.winfo_width(), w.winfo_reqwidth())
    assert go.winfo_width() >= go.winfo_reqwidth()
    assert go.winfo_width() > go.winfo_reqwidth() * 1.2              # it did grow: the row is not packed to the left any more
    assert var.winfo_x() == go.winfo_x() + go.winfo_width() + 1 and stop.winfo_x() == var.winfo_x() + var.winfo_width() + 1
    side = go.winfo_height()
    for b in (undo, redo):
        assert b.winfo_width() == b.winfo_height() == side, (b.winfo_width(), b.winfo_height(), side)
        assert str(b.cget("style")) == "Square.TButton" and b.cget("image")
    assert 0 < redo.winfo_x() - (undo.winfo_x() + undo.winfo_width()) <= app._px(gui.GO_PAIR_GAP_PX) + 2
    last = app.b_stop_all if stop_all else stop
    gap = undo.winfo_x() - (last.winfo_x() + last.winfo_width())
    assert gap >= app._px(gui.GO_GAP_MIN_PX), gap                    # the only free room: before Undo
    if stop_all:
        assert app.b_stop_all.winfo_width() >= app.b_stop_all.winfo_reqwidth()


def window_tests():
    try:
        import tkinter
        tkinter.Tk().destroy()
    except Exception as e:
        print(f"(window part skipped: no Tk window: {e})")
        return
    import time
    from pccomfy import config as cfgmod, gui
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    for _ in range(25):
        app.root.update()
        time.sleep(0.02)
    assert not app.b_stop_all.winfo_manager()                       # not shown at rest
    from pccomfy import models
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("flux3")
    app.v_mode.set("edit")                  # the tabs under the prompt are there: Generate + variants = "Edit canvas"
    app._on_model()
    app.root.deiconify()                    # shown for the row checks: a withdrawn window does not give the body its full width
    for _ in range(25):
        app.root.update()
        time.sleep(0.02)
    row_checks(app, gui)
    app._show_stop_all(True)
    app.root.update()
    assert app.b_stop_all.winfo_manager() == "grid"
    assert app.b_stop.winfo_x() < app.b_stop_all.winfo_x() < app.b_undo.winfo_x()     # "Stop all" sits between Stop and Undo
    from tkinter import font as tkfont
    assert app.b_stop_all.winfo_width() >= tkfont.Font(root=app.root, font=gui.font(9)).measure("Stop all") + 10   # the whole text shows
    row_checks(app, gui, stop_all=True)
    calls = []
    app.bridge.cancel_all = lambda: calls.append("all")
    app.bridge.cancel = lambda: calls.append("one")
    app.worker = type("W", (), {"is_alive": lambda self: True})()
    app.stop()
    app.stop_all()
    assert calls == ["one", "all"], calls
    app.worker = None
    app._show_stop_all(False)
    app.root.update()
    assert not app.b_stop_all.winfo_manager()
    row_checks(app, gui)                    # back as before
    app.root.withdraw()
    assert int(str(app.b_stop.cget("width"))) == gui.STOP_W      # as wide as its text, not 9 any more (user 12.11.)
    assert str(app.b_stop.cget("text")) == "Stop" and str(app.b_stop_all.cget("text")) == "Stop all"
    app.root.destroy()


if __name__ == "__main__":
    bridge_tests()
    window_tests()
    print("ALL OK (cancel all)")
