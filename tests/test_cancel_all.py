# tags: queue
"""Cancel and Cancel all with variants that run one after the other (Bridge._run_sequence, user 3.11.): Cancel ends only the
variant that is running, Cancel all ends it and the ones still to come. Also the buttons of the window.

    python tests/test_cancel_all.py
"""
import os
import sys
import time
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


def equal_gaps(app):
    """Every two buttons of the Generate row have the same gap (user 25.11.: "die abstände zwischen den buttons in dieser
    zeile sollen immer gleich sein"), GO_ROW_GAP_PX after the display scaling."""
    from pccomfy import gui
    shown = sorted((w for w in (app.b_go, app.w_variants, app.b_stop_run, app.b_stop_all) if w.winfo_manager() == "grid"),
                   key=lambda w: w.winfo_x())
    gaps = [b.winfo_x() - (a.winfo_x() + a.winfo_width()) for a, b in zip(shown, shown[1:])]
    assert all(g == app._keep(gui.GO_ROW_GAP_PX) for g in gaps), (gaps, app._keep(gui.GO_ROW_GAP_PX))


def row_checks(app, gui, stop_all=False):
    """The Generate row (user 18.11., decision 1a; no Stop button since 20.11.; Undo and Redo went to the header 25.11.):
    over the full width, Generate takes what the variants piece (natural width up to 1.2x) and "Stop batch" leave."""
    row = app.f_go.winfo_width()
    go, var = app.b_go, app.w_variants
    assert app.b_undo.master is not app.f_go and app.b_redo.master is not app.f_go
    last = app.b_stop_all if stop_all else (var if var.winfo_manager() else go)
    assert go.winfo_x() == 0
    assert abs(last.winfo_x() + last.winfo_width() - row) <= 1, (last.winfo_x(), last.winfo_width(), row)   # no room left
    assert go.winfo_width() >= go.winfo_reqwidth()
    if not var.winfo_manager():     # during a run the variants piece is gone (user 20.11.): Generate takes its room
        return
    assert var.winfo_reqwidth() <= var.winfo_width() <= var.winfo_reqwidth() * gui.VARIANTS_GROW_MAX + 1
    equal_gaps(app)
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
    # a text model run (Describe): Generate is the grey "Stop"; with "Stop batch" beside it, "Stop run". Since 23.11. a run
    # of a function always shows the queue row (queue_row_checks), Fill too (grey "Add to queue", user 23.11.)
    app._queue_refusal = lambda: "can't wait"
    app._describing = True
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
    assert app.b_go.winfo_x() < app.b_stop_all.winfo_x()     # "Stop batch" right of Generate (Undo went to the header 25.11.)
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
    app._describing = False
    app._show_stop_all(False)
    app._go_stop(False)
    app.root.update()
    assert not app.b_stop_all.winfo_manager()
    assert str(app.b_go.cget("text")) == "Generate" and str(app.b_go.cget("style")) == "Accent.TButton"
    assert app.tt_go.text == gui.GO_TIP
    assert app.w_variants.winfo_manager() == "grid"                 # the variants piece is back
    row_checks(app, gui)                    # back as before
    # a batch of the ⋯ menu (user 20.11.) while a function is picked that can't wait in the queue: the queue row with a grey
    # "Add to queue" (user 23.11.); Stop run cancels the picture at ComfyUI, Stop batch only the batch of that picture
    # (21.11.); afterwards Generate comes back
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
    assert str(app.b_go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and app.b_stop_all.winfo_manager() == "grid"
    assert str(app.b_go.cget("state")) == "disabled" and app.b_stop_run.winfo_manager() == "grid"
    app._go_stop(False)                     # a Describe ends while the batch is on: the row stays (review 21.11.)
    assert str(app.b_go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and app.b_stop_all.winfo_manager() == "grid"
    app._stop_armed -= gui.STOP_GUARD_S
    app.b_stop_run.invoke()
    app.b_stop_all.invoke()
    # only the batch of the running picture (user 21.11.; 23.11. evening: also no other queued Generate)
    assert done == [("job", "j1"), ("batch", "b2")], done
    Runner.running_job = None               # between two pictures: the batch of the next one in the line
    app.stop_all()
    assert done[-1:] == [("batch", "b1")], done
    Runner.busy = False
    app._batch_sync()
    app.root.update()
    assert str(app.b_go.cget("text")) == "Generate" and not app.b_stop_all.winfo_manager()
    assert app.w_variants.winfo_manager() == "grid" and str(app.b_go.cget("state")) == "normal"
    del app._queue_refusal
    queue_row_checks(app, gui, Runner, done)
    app.runner = real_runner
    app.root.withdraw()
    app.root.destroy()


def queue_row_checks(app, gui, Runner, done):
    """Generate while something runs, for a function that can wait in the queue (user 22.11., Variant 1): blue "Add to
    queue", the variants piece, grey "Stop run" and "Stop batch", all in the row (Undo and Redo in the header since 25.11.),
    every text whole."""
    from tkinter import font as tkfont
    # a run of the window alone, no batch, no variants: "Add to queue" without "Stop batch" (user 25.11.: "stop batch nur
    # bei batch zeigen"), and the row fits at the smallest scales too (it did not at 60, 80 and 90 %)
    wanted = app._stop_all_wanted
    app._stop_all_wanted = False
    app._go_queue_row()
    for _ in range(5):
        app.root.update()
    assert str(app.b_go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and app.b_stop_run.winfo_manager() == "grid"
    assert not app.b_stop_all.winfo_manager(), "Stop batch only with a batch or variants (user 25.11.)"
    assert app.b_stop_run.winfo_x() + app.b_stop_run.winfo_width() <= app.f_go.winfo_width()
    assert app.b_go.winfo_width() >= app.b_go.winfo_reqwidth(), (app.b_go.winfo_width(), app.b_go.winfo_reqwidth())
    app._stop_all_wanted = wanted
    Runner.busy, Runner.running_job = True, {"id": "j1", "batch_id": "b2"}
    app._batch_sync()
    for _ in range(5):
        app.root.update()
    go, var, run, stop_all = app.b_go, app.w_variants, app.b_stop_run, app.b_stop_all
    assert str(go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and str(go.cget("style")) == "Accent.TButton"
    assert app.tt_go.text == gui.ADD_QUEUE_TIP and str(go.cget("state")) == "normal"
    assert var.winfo_manager() == run.winfo_manager() == stop_all.winfo_manager() == "grid"
    assert str(run.cget("text")) == gui.GO_STOP_RUN_TEXT and str(stop_all.cget("text")) == gui.STOP_BATCH_TEXT
    row = app.f_go.winfo_width()
    order = [go, var, run, stop_all]
    equal_gaps(app)
    for a, b in zip(order, order[1:]):
        assert a.winfo_x() + a.winfo_width() <= b.winfo_x(), [(w.winfo_x(), w.winfo_width()) for w in order]
    assert stop_all.winfo_x() + stop_all.winfo_width() <= row, (row, [(w.winfo_x(), w.winfo_width(), w.winfo_reqwidth()) for w in order])
    f = tkfont.Font(root=app.root, font=gui.font(9))
    # "Queue" only where "Add to queue" does not fit (user 25.11.); at 100 % and more it always fits
    assert app._px(100) < 100 or str(go.cget("text")) == gui.ADD_QUEUE_TEXT, (app._px(100), go.cget("text"))
    for b, text in ((run, "Stop run"), (stop_all, "Stop batch"), (go, str(go.cget("text")))):
        assert b.winfo_width() >= f.measure(text) + 8, (text, b.winfo_width(), f.measure(text))
    # Stop run: the picture at ComfyUI; Stop batch: its batch only
    done.clear()
    app._stop_armed -= gui.STOP_GUARD_S
    run.invoke()
    stop_all.invoke()
    assert done == [("job", "j1"), ("batch", "b2")], done
    # another function meanwhile: Fill can't wait in the queue; the same row with a grey "Add to queue" and ×n, the
    # status line says why (user 23.11., choice A; it was "Stop run" and the reason never showed)
    app.v_mode.set("inpaint")
    why = app._queue_refusal()
    end = time.monotonic() + 5                 # under load (six test files at once) the idle call comes late
    while time.monotonic() < end and not (str(go.cget("state")) == str(var.cget("state")) == "disabled"
                                          and app.v_status.get() == why):
        app.root.update()
        time.sleep(0.02)
    assert str(go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and str(go.cget("state")) == "disabled", go.cget("state")
    assert str(var.cget("state")) == "disabled" and run.winfo_manager() == stop_all.winfo_manager() == "grid"
    assert why.startswith("Fill") and app.v_status.get() == why and app.tt_go.text == why, (why, app.v_status.get())
    app.v_mode.set("edit")
    end = time.monotonic() + 5
    while time.monotonic() < end and str(go.cget("state")) != "normal":
        app.root.update()
        time.sleep(0.02)
    assert str(go.cget("text")) in (gui.ADD_QUEUE_TEXT, gui.ADD_QUEUE_SHORT) and run.winfo_manager() == "grid"
    assert str(go.cget("state")) == "normal" and str(var.cget("state")) == "normal"
    app.v_mode.set("inpaint")                   # the run ends while Fill is picked: Generate and ×n can be clicked again
    for _ in range(5):
        app.root.update()
    Runner.busy = False
    app._batch_sync()
    app.root.update()
    assert str(go.cget("text")) == "Generate" and not run.winfo_manager() and not stop_all.winfo_manager()
    assert var.winfo_manager() == "grid" and str(go.cget("state")) == "normal" and str(var.cget("state")) == "normal"
    app.v_mode.set("edit")


if __name__ == "__main__":
    bridge_tests()
    window_tests()
    print("ALL OK (cancel all)")
