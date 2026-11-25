# tags: queue, comfy, window
"""Closing PxC during a run (user 25.11.: "comfyui rechnet weiter wenn ein lauf läuft, und ich photocraft und pxc
währenddessen schließe"; choice "Ask when closing PxC"): closing by hand asks Yes (stop) / No (let ComfyUI finish) /
Cancel (stay open); PhotoCraft gone closes without a question and stops the window's runs. The stop reaches ComfyUI at
once by the prompt id (the worker thread dies with the process), queued Generate clicks are cancelled, a batch of the
⋯ menu at ComfyUI goes on.

    python tests/test_close_during_run.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def bridge_checks():
    from pccomfy import bridge as bridgemod
    calls = []
    b = bridgemod.Bridge.__new__(bridgemod.Bridge)
    import threading
    b._cancel, b._cancel_all = threading.Event(), threading.Event()
    b.comfy = SimpleNamespace(interrupt=lambda pid=None: calls.append(pid))
    b.running_prompt = None
    assert b.stop_at_comfy() is False and calls == []            # nothing at ComfyUI: no bare /interrupt
    assert b._cancel.is_set() and b._cancel_all.is_set()        # the variants that would follow stop too
    b.running_prompt = "p1"
    assert b.stop_at_comfy() is True and calls == ["p1"]        # by its prompt id

    # _wait keeps the prompt id while it waits and drops it afterwards
    seen = []
    b._wait_inner = lambda pid, *a, **k: seen.append(b.running_prompt) or "res"
    assert b._wait("p2", {}, "", 0, 1, "", None) == "res" and seen == ["p2"] and b.running_prompt is None


class Worker:
    def __init__(self, alive):
        self.alive = alive

    def is_alive(self):
        return self.alive


def gui_checks():
    import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)
    gui = t.gui
    if not hasattr(gui.messagebox, "askyesnocancel"):          # the Tk stub has no such dialog; _dialog is replaced below
        gui.messagebox.askyesnocancel = lambda **k: None
    app = gui.App(t.cfgmod.load())
    stopped, destroyed, asked, cancelled = [], [], [], []
    app.bridge.stop_at_comfy = lambda: stopped.append(1) or True
    app.bridge.cancel = lambda: None
    app.root.destroy = lambda: destroyed.append(1)
    answer = {"v": None}

    def dialog(fn, **kw):
        asked.append(kw.get("message"))
        return answer["v"]
    app._dialog = dialog
    app._batch_shutdown = lambda: False

    def reset():
        app._closing = False
        stopped.clear(), destroyed.clear(), asked.clear(), cancelled.clear()

    # no run: closes at once, no question, nothing stopped
    app.worker = None
    app._quit()
    assert destroyed and not asked and not stopped
    # a run of the window: Cancel keeps PxC open
    reset()
    app.worker = Worker(True)
    answer["v"] = None
    app._quit()
    assert asked == [gui.CLOSE_RUN_ASK] and not destroyed and not stopped and not app._closing
    # Yes: stopped at ComfyUI, then closed
    reset()
    answer["v"] = True
    app._quit()
    assert stopped and destroyed
    # No: ComfyUI finishes it, PxC closes
    reset()
    answer["v"] = False
    app._quit()
    assert asked and destroyed and not stopped
    # PhotoCraft is gone: no question, stopped
    reset()
    app._quit(ask=False)
    assert not asked and stopped and destroyed

    # queued Generate clicks (×n, Add to queue) of this window: asked too; Yes cancels them; a ⋯ batch at ComfyUI goes on
    from pccomfy import jobqueue
    batches = {"g1": {"id": "g1", "state": "running", "kind": jobqueue.K_GENERATE},
               "m1": {"id": "m1", "state": "running", "kind": jobqueue.K_BATCH}}
    runner = SimpleNamespace(batches=lambda: list(batches.values()), batch=lambda bid: batches.get(bid),
                             cancel_batch=lambda bid: cancelled.append(bid) or True, running_job={"batch_id": "g1"},
                             shutdown=lambda *a: None, jobs=lambda *a: [])
    app.runner = runner
    app._batch_mine = {"g1", "m1"}
    reset()
    app.worker = None
    answer["v"] = True
    app._quit()
    assert asked and cancelled == ["g1"] and stopped and destroyed, (asked, cancelled, stopped)
    # only the ⋯ batch is at ComfyUI: closing does not ask and does not stop it (its result is picked up later)
    batches["g1"]["state"] = "done"
    runner.running_job = {"batch_id": "m1"}
    reset()
    app._quit()
    assert not asked and not stopped and not cancelled and destroyed
    reset()
    app._quit(ask=False)                    # PhotoCraft gone: still no stop for the ⋯ batch
    assert not stopped and not cancelled and destroyed


def main():
    bridge_checks()
    gui_checks()
    print("test_close_during_run: ok")


if __name__ == "__main__":
    main()
