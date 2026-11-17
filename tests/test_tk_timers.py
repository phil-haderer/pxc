"""Timers of short-lived widgets belong to the Tk root (gui_common.later / idle / cancel_later, 14.11.2026).

Tk keeps a timer of a widget that is destroyed while tkinter deletes the name of its callback; a new callback at the same
memory address gets the same name and the old timer calls it. That closed the new dry-run window at once (test_batch_gui
under load) and called key lambdas without their event (error.log). This test pins the helpers and that pccomfy schedules
no timer on another widget than the root.

    python tests/test_tk_timers.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from pccomfy import gui_common  # noqa: E402

ALLOWED = re.compile(r"^(self\.root|root|_tk_root\(widget\))\.after(_idle|_cancel)?\($")


def source_pin():
    """No `<widget>.after(` / `.after_idle(` / `.after_cancel(` in pccomfy other than on the root; everything else (also
    popmenu.py, whose master can be the settings window) goes through gui_common.later / idle / cancel_later."""
    bad = []
    for f in sorted((ROOT / "pccomfy").glob("*.py")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#")[0]
            if '"""' in line or code.strip().startswith(("'", '"')):
                continue
            for m in re.finditer(r"[\w\.\(\)]*\.after(_idle|_cancel)?\(", code):
                if not ALLOWED.search(m.group(0)):
                    bad.append(f"{f.name}:{n}: {line.strip()}")
    assert not bad, "timers on a widget (use gui_common.later / idle):\n" + "\n".join(bad)


def live():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        print(f"skip live part (no display: {e})")
        return
    root.withdraw()
    try:
        calls = []
        win = tk.Toplevel(root)
        job = gui_common.later(win, 30, calls.append, "late")
        gui_common.idle(win, calls.append, "idle")
        win.destroy()
        for _ in range(20):          # both timers fire after the window is gone: nothing runs, no error
            root.update()
            root.after(10)
        assert calls == [], calls
        assert job.startswith("after#")
        # a living widget gets its call, with the arguments
        w2 = tk.Frame(root)
        gui_common.later(w2, 1, calls.append, "ok")
        gui_common.idle(w2, calls.append, "ok2")
        for _ in range(20):
            root.update()
            root.after(5)
        assert calls == ["ok2", "ok"] or sorted(calls) == ["ok", "ok2"], calls
        # cancel_later stops a timer; a second cancel and a dead job do no harm
        calls.clear()
        j = gui_common.later(w2, 20, calls.append, "never")
        gui_common.cancel_later(w2, j)
        gui_common.cancel_later(w2, j)
        for _ in range(10):
            root.update()
            root.after(10)
        assert calls == [], calls
        # the timers live on the root: destroying the root later finds every name it registered (the "can't delete Tcl
        # command" of error.log at quit came from names that had gone)
        w2.destroy()
    finally:
        root.destroy()


def main():
    source_pin()
    live()
    print("ALL OK (timers of short-lived widgets live on the Tk root)")


if __name__ == "__main__":
    main()
