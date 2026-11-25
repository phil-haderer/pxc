# tags: undo, window
"""Undo and Redo in the Generate row (user 18.11., decision 2a): two squares, blue like Generate with a white icon while they
can be used, grey like the greyed-out Stop otherwise, one of them blue at a time. The order: start = both grey; after a run
Undo blue, Redo grey; after Undo Undo grey, Redo blue; after Redo Undo blue again; a new run: Undo blue. Grey while a run, a
step or a batch is on; a failed step changes nothing; the bridge has to agree (can_undo / can_redo).

    python tests/test_history_buttons.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-hist-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod, gui  # noqa: E402
from pccomfy.bridge import BridgeError  # noqa: E402


def states(app):
    return str(app.b_undo.cget("state")), str(app.b_redo.cget("state"))


def pump(app, until, timeout=5.0):
    """Runs the window until `until()` holds AND the worker thread has ended. A step's thread lives on for a moment after its
    last event, and a click in that moment is ignored (gui_run._history_step); a person never clicks that fast, but the test
    did: red on Tk 9 / Python 3.14 in the install matrix (19.11.)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app._poll()
        app.root.update()
        if until() and not (app.worker and app.worker.is_alive()):
            return True
        time.sleep(0.02)
    return False


def style_checks(app):
    """Square.TButton: ACCENT and the hover blue of Generate, the disabled face of Stop (TButton), icon white / grey."""
    s = gui.ttk.Style(app.root)
    assert str(s.lookup("Square.TButton", "background")).lower() == gui.ACCENT.lower()
    assert str(s.lookup("Square.TButton", "background", ["active"])).lower() == "#5ba3f5"
    assert str(s.lookup("Square.TButton", "background", ["disabled"])).lower() == str(s.lookup("TButton", "background", ["disabled"])).lower()
    assert str(s.lookup("Square.TButton", "background", ["disabled", "active"])).lower() == gui.PANEL.lower()   # no hover while grey
    assert str(s.lookup("Accent.TButton", "background", ["active"])).lower() == "#5ba3f5"                       # the same blue as Generate
    for b in (app.b_undo, app.b_redo):
        assert str(b.cget("style")) == "Square.TButton"
        spec = [str(x) for x in b.cget("image")]
        assert len(spec) == 3 and spec[1] == "disabled" and spec[0] != spec[2], spec       # white icon, grey one when disabled
    cache = app._icon_cache
    white = {str(v) for (k, c, _), v in cache.items() if k in ("undo", "redo") and c == gui.ON_ACCENT}
    grey = {str(v) for (k, c, _), v in cache.items() if k in ("undo", "redo") and c == gui.DISABLED}
    assert {str(app.b_undo.cget("image")[0]), str(app.b_redo.cget("image")[0])} <= white
    assert {str(app.b_undo.cget("image")[2]), str(app.b_redo.cget("image")[2])} <= grey


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    for _ in range(10):
        app.root.update()
    style_checks(app)
    b = app.bridge
    snap = {"undo": False, "redo": False}
    b.can_undo = lambda *a: snap["undo"]
    b.can_redo = lambda: snap["redo"]

    def undo():
        snap["redo"] = True
        return "Undone."

    def redo():
        return "Redone."
    b.undo_last, b.redo_last = undo, redo

    assert states(app) == ("disabled", "disabled"), states(app)          # start: nothing to undo yet

    # grey because nothing is there yet: a click on it stays silent, the tooltip has no lock note (user 25.11.)
    hit = lambda w: type("E", (), {"widget": w, "x": 2, "y": 2})()
    app._status("")
    app._history_grey_click(hit(app.b_undo), "undo")
    assert app.v_status.get() == "" and app.tt_undo.text == gui.HISTORY_UNDO_TIP

    # a run: grey while it is on, Undo blue afterwards
    app._running = True
    app._sync_history_buttons()
    assert states(app) == ("disabled", "disabled")
    # a click on the grey button says why (a grey ttk button calls no command, user 25.11.); the tooltip says it too
    for w, step in ((app.b_undo, "undo"), (app.b_redo, "redo")):
        app._status("")
        app._history_grey_click(hit(w), step)
        assert app.v_status.get() == gui.CUT_NOT_IN_RUN and not getattr(app, "_history_busy", False), app.v_status.get()
    assert app.tt_undo.text == gui.HISTORY_UNDO_TIP + "\n\n" + gui.CUT_NOT_IN_RUN
    assert app.tt_redo.text == gui.HISTORY_REDO_TIP + "\n\n" + gui.CUT_NOT_IN_RUN
    snap["undo"] = True
    app.events.put(("done", "Done."))
    assert pump(app, lambda: not app._running)
    assert states(app) == ("normal", "disabled"), states(app)
    assert app.tt_undo.text == gui.HISTORY_UNDO_TIP          # the lock note goes with the run

    # Undo: grey while it works, then Redo is the blue one
    app.undo_edit()
    assert states(app) == ("disabled", "disabled")
    assert pump(app, lambda: not getattr(app, "_history_busy", False))
    assert app._last_step == "undo" and states(app) == ("disabled", "normal"), states(app)

    # Redo: Undo blue again
    app.redo_edit()
    assert pump(app, lambda: not getattr(app, "_history_busy", False))
    assert app._last_step == "redo" and states(app) == ("normal", "disabled"), states(app)

    # Undo again, then a step that fails: nothing changes ("note-error" leaves the last step)
    app.undo_edit()
    assert pump(app, lambda: not getattr(app, "_history_busy", False))
    assert states(app) == ("disabled", "normal")

    def broken():
        raise BridgeError("PhotoCraft is not answering")
    b.redo_last = broken
    app.redo_edit()
    assert pump(app, lambda: not getattr(app, "_history_busy", False))
    assert app._last_step == "undo" and states(app) == ("disabled", "normal"), states(app)
    b.redo_last = redo

    # the bridge has to agree: no redo left there, Redo stays grey
    snap["redo"] = False
    app._sync_history_buttons()
    assert states(app) == ("disabled", "disabled")
    snap["redo"] = True

    # a new run: Undo is the blue one again
    app._running = True
    app._sync_history_buttons()
    assert states(app) == ("disabled", "disabled")
    app.events.put(("done", "Done."))
    assert pump(app, lambda: not app._running)
    assert app._last_step is None and states(app) == ("normal", "disabled"), states(app)

    # a cancelled run keeps the last step (no new result)
    app.undo_edit()
    assert pump(app, lambda: not getattr(app, "_history_busy", False))
    app._running = True
    app.events.put(("done", "Cancelled."))
    assert pump(app, lambda: not app._running)
    assert app._last_step == "undo" and states(app) == ("disabled", "normal"), states(app)

    # a batch: both grey while it is on, back afterwards
    runner = type("R", (), {"busy": True})()
    app.runner = runner
    app._sync_history_buttons()
    assert states(app) == ("disabled", "disabled")
    runner.busy = False
    app._sync_history_buttons()
    assert states(app) == ("disabled", "normal")
    app.root.destroy()


if __name__ == "__main__":
    main()
    print("ALL OK (history buttons)")
