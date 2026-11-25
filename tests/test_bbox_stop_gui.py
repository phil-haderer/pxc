# tags: queue, window, multiedit, flux3
"""Generate comes back after a run that ended while a slot job was on (bug 23.11.: Flux 3 Insert reference, Cut out in the
slot during the run, the run stopped: Generate stayed "Stop"). Hidden real Tk window; the bridge and the runner are faked
(no PhotoCraft, no ComfyUI, nothing goes to the network).

    python tests/test_bbox_stop_gui.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-bbox-stop-")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from PIL import Image  # noqa: E402

from pccomfy import config as cfgmod, gui, models, popmenu  # noqa: E402
from pccomfy.bridge import Cancelled  # noqa: E402
import test_batch_gui as tb  # noqa: E402


class Bridge(tb.FakeBridge):
    """The run waits until Stop; the cut-out waits until the test lets it end."""

    def __init__(self):
        super().__init__()
        self.stop, self.cut_go = threading.Event(), threading.Event()
        self.on_preview = None

    def reset_cancel_all(self): pass
    def cancel_all_requested(self): return False
    def cancel(self): self.stop.set()
    def cancel_all(self): self.stop.set()

    def run(self, rq, progress):
        self.stop.wait(10)
        raise Cancelled()

    def remove_background(self, image):
        self.cut_go.wait(10)
        return image.convert("RGBA")

    def __getattr__(self, name):
        return lambda *a, **k: None


def main():
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if ms != 100 else "poll"))(app.root.after)
    app.runner = tb.FakeRunner()
    app.runner._jobs, app.runner._batches = [], []
    app.bridge = br = Bridge()
    app._other_photocraft = lambda: False
    app._active_doc_name = lambda: "photo.png"
    app._cutout_ok = lambda name: True
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("flux3")
    app.v_mode.set("multi_edit")
    app._on_model()
    app.v_edtab.set("bbox")                    # Insert reference
    app._edtab_clicked()
    app.refslots.add(Image.new("RGB", (40, 30), "red"), "bag.png")
    assert app._bbox_on()

    def pump(until, timeout=5.0):
        end = time.monotonic() + timeout
        while not until() and time.monotonic() < end:
            app._poll()
            app.root.update()
            time.sleep(0.03)
        return until()

    go = lambda: (str(app.b_go.cget("text")), str(app.b_go.cget("state")))     # noqa: E731
    app.generate()
    assert app._running and go() != ("Generate", "normal"), go()
    said = []
    real_say, app._refs_say = app._refs_say, lambda msg: said.append(msg)
    app._refs_cut(0)                            # Cut out in the slot while the run is on: not any more (user 23.11.)
    app._refs_describe(0)                       # Describe neither (user 24.11. evening)
    app._refs_say = real_say
    assert not app._ref_busy and said == [gui.CUT_NOT_IN_RUN] * 2, said
    assert app._describe_slot_off() == gui.CUT_NOT_IN_RUN
    app.stop()
    assert pump(lambda: not app._running) and pump(lambda: go() == ("Generate", "normal")), go()
    assert app._describe_slot_off() == "", "Describe is back after the run"
    # a slot cut-out that was on before the run (a queue job can start meanwhile): the run ends first, Generate waits for the cut
    app._refs_cut(0)
    assert 0 in app._ref_busy
    br.stop.clear()
    app._running = True
    app._go_stop(True)
    app._running = False
    app.stop()                               # the run ends (cancelled) while the cut-out is still on
    assert pump(lambda: not app._running), "the run did not end"
    assert go() != ("Generate", "normal"), go()       # the cut-out still runs: Generate stays "Stop"
    br.cut_go.set()
    assert pump(lambda: not app._ref_busy), "the cut-out did not end"
    assert pump(lambda: go() == ("Generate", "normal")), go()
    assert not app.b_stop_run.winfo_manager() and not app.b_stop_all.winfo_manager()
    assert app.refslots.items[0].cut_out

    # a cut-out that ends while no run is on leaves blue Generate as it is
    app.refslots.revert(0)
    br.cut_go.set()
    app._refs_cut(0)
    assert pump(lambda: not app._ref_busy) and go() == ("Generate", "normal"), go()
    app.root.destroy()
    print("ALL OK (bbox stop gui)")


if __name__ == "__main__":
    main()
