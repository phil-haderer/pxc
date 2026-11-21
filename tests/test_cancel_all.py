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
    """The Generate row (user 18.11., decisions 1a, 2a and 3; no Stop button since 20.11.): over the full width with no
    room left but the gap before Undo; Generate + the variants piece half the row (the Edit tabs are a list since 20.11.);
    the variants piece within its cap (natural width up to 1.2x); Undo and Redo squares as high as Generate at the right
    edge."""
    row = app.f_go.winfo_width()
    go, var, undo, redo = app.b_go, app.w_variants, app.b_undo, app.b_redo
    assert app.b_edtab.winfo_ismapped()
    half = (row - 2 * 2 * gui.EDTAB_PADX) // 2
    if not var.winfo_manager():     # during a run the variants piece is gone (user 20.11.): Generate takes its room
        assert go.winfo_x() == 0 and redo.winfo_x() + redo.winfo_width() == row
        assert half - app._px(40) <= go.winfo_width() <= half + 1, (go.winfo_width(), half)
        last = app.b_stop_all if stop_all else go
        assert undo.winfo_x() - (last.winfo_x() + last.winfo_width()) >= app._px(gui.GO_GAP_MIN_PX)
        return
    pair_w = var.winfo_x() + var.winfo_width() - go.winfo_x()
    if stop_all:        # the row may be short then: Generate gives that back, never more than half the row
        assert half - app._px(40) <= pair_w <= half + 1, (pair_w, half)
    else:
        assert abs(pair_w - half) <= 1, (go.winfo_width(), var.winfo_width(), half)
    assert go.winfo_x() == 0 and redo.winfo_x() + redo.winfo_width() == row, (redo.winfo_x(), redo.winfo_width(), row)
    assert var.winfo_reqwidth() <= var.winfo_width() <= var.winfo_reqwidth() * gui.VARIANTS_GROW_MAX + 1
    assert go.winfo_width() >= go.winfo_reqwidth()
    assert var.winfo_x() == go.winfo_x() + go.winfo_width() + 1
    side = go.winfo_height()
    for b in (undo, redo):
        assert b.winfo_width() == b.winfo_height() == side, (b.winfo_width(), b.winfo_height(), side)
        assert str(b.cget("style")) == "Square.TButton" and b.cget("image")
    assert 0 < redo.winfo_x() - (undo.winfo_x() + undo.winfo_width()) <= app._px(gui.GO_PAIR_GAP_PX) + 2
    last = app.b_stop_all if stop_all else var
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
    assert not hasattr(app, "b_stop")                               # no Stop button since 20.11. (user)
    assert str(app.b_go.cget("text")) == "Generate" and str(app.b_go.cget("style")) == "Accent.TButton"
    # a run: Generate is the grey "Stop"; several runs one after another: "Stop run" and "Stop batch" beside it
    app._running = True
    app._go_stop(True)
    app.root.update()
    assert str(app.b_go.cget("text")) == gui.GO_STOP_TEXT and str(app.b_go.cget("style")) == "GoStop.TButton"
    assert str(app.b_go.cget("state")) == "normal" and app.tt_go.text == gui.GO_STOP_TIP
    assert not app.w_variants.winfo_manager(), "the variants piece is gone while a run is on (user 20.11.)"
    row_checks(app, gui)
    app._show_stop_all(True)
    app.root.update()
    assert app.b_stop_all.winfo_manager() == "grid" and str(app.b_go.cget("text")) == gui.GO_STOP_RUN_TEXT
    assert str(app.b_stop_all.cget("text")) == gui.STOP_BATCH_TEXT == "Stop batch"
    assert app.b_go.winfo_x() < app.b_stop_all.winfo_x() < app.b_undo.winfo_x()     # "Stop batch" between Generate and Undo
    from tkinter import font as tkfont
    assert app.b_stop_all.winfo_width() >= tkfont.Font(root=app.root, font=gui.font(9)).measure("Stop batch") + 10   # the whole text shows
    row_checks(app, gui, stop_all=True)
    calls = []
    app.bridge.cancel_all = lambda: calls.append("all")
    app.bridge.cancel = lambda: calls.append("one")
    app.worker = type("W", (), {"is_alive": lambda self: True})()
    app.b_go.invoke()                       # a double click on Generate: the second click comes right after the start
    app.b_stop_all.invoke()
    assert calls == [], "a click within STOP_GUARD_S of the start stops nothing (user 20.11.)"
    app.stop()                              # the keys (Ctrl+Alt+Enter) stop at once
    assert calls == ["one"], calls
    calls.clear()
    app._stop_armed -= gui.STOP_GUARD_S     # later on, a click stops
    app.b_go.invoke()                       # "Stop run": the run that is on
    app.b_stop_all.invoke()                 # "Stop batch": it and the ones still to come
    assert calls == ["one", "all"], calls
    app._go_stop(False)                     # still running: it stays "Stop run"
    assert str(app.b_go.cget("text")) == gui.GO_STOP_RUN_TEXT
    app.worker = None
    app._running = False
    app._show_stop_all(False)
    app._go_stop(False)
    app.root.update()
    assert not app.b_stop_all.winfo_manager()
    assert str(app.b_go.cget("text")) == "Generate" and str(app.b_go.cget("style")) == "Accent.TButton"
    assert app.tt_go.text == gui.GO_TIP
    assert app.w_variants.winfo_manager() == "grid"                 # the variants piece is back
    row_checks(app, gui)                    # back as before
    # a batch of the ⋯ menu (user 20.11.): Generate is "Stop run" with "Stop batch" beside it; Stop run cancels the picture
    # at ComfyUI, Stop batch only the batch of that picture (21.11.); afterwards Generate comes back
    done = []

    class Runner:
        busy = True
        running_job = {"id": "j1", "batch_id": "b2"}

        def jobs(self):
            return [{"id": "j3", "status": "waiting", "batch_id": "b1"}]

        def cancel(self, jid):
            done.append(("job", jid))

        def batches(self):
            return [{"id": "b0", "state": "done"}, {"id": "b1", "state": "running"}, {"id": "b2", "state": "running"}]

        def cancel_batch(self, bid):
            done.append(("batch", bid))
    real_runner, app.runner = app.runner, Runner()
    app._batch_sync()
    app.root.update()
    assert str(app.b_go.cget("text")) == gui.GO_STOP_RUN_TEXT and app.b_stop_all.winfo_manager() == "grid"
    assert str(app.b_go.cget("state")) == "normal" and not app.w_variants.winfo_manager()
    app._go_stop(False)                     # a Describe ends while the batch is on: it stays "Stop run" (review 21.11.)
    assert str(app.b_go.cget("text")) == gui.GO_STOP_RUN_TEXT and app.b_stop_all.winfo_manager() == "grid"
    app._stop_armed -= gui.STOP_GUARD_S
    app.b_go.invoke()
    app.b_stop_all.invoke()
    assert done == [("job", "j1"), ("batch", "b2")], done     # only the batch of the running picture (user 21.11.)
    Runner.running_job = None               # between two pictures: the batch of the next one in the line
    app.stop_all()
    assert done[-1] == ("batch", "b1"), done
    Runner.busy = False
    app._batch_sync()
    app.root.update()
    assert str(app.b_go.cget("text")) == "Generate" and not app.b_stop_all.winfo_manager()
    assert app.w_variants.winfo_manager() == "grid"
    app.runner = real_runner
    app.root.withdraw()
    app.root.destroy()


if __name__ == "__main__":
    bridge_tests()
    window_tests()
    print("ALL OK (cancel all)")
