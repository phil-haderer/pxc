# tags: window, photocraft, start
"""The window's start (user 22.11.): invisible until the first link has put it in its place (no first picture in the top
left corner and then a jump), shown at the latest after REVEAL_MS; the start log window-start.log (startlog.py).

    python tests/test_window_start.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402

gui, cfgmod = t.gui, t.cfgmod
from pccomfy import startlog, winlink  # noqa: E402


def test_startlog():
    now = {"t": 100.0}
    path = Path(tempfile.mkdtemp()) / "window-start.log"
    lg = startlog.StartLog(path, clock=lambda: now["t"], now=lambda f: "12:00:00")
    lg.state("a")
    lg.state("a")                     # unchanged: not written again
    now["t"] += 1.5
    lg.state("b")
    lg.note("linked")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("=== start") and lines[1:] == ["12:00:00 +0.00s a", "12:00:00 +1.50s b", "12:00:00 +1.50s linked"], lines
    assert lg.active()
    now["t"] += startlog.SECONDS
    assert not lg.active()
    # the file keeps only the last KEEP lines over many starts
    path.write_text("\n".join(f"old {i}" for i in range(startlog.KEEP + 50)) + "\n", encoding="utf-8")
    startlog.StartLog(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == startlog.KEEP and lines[-1].startswith("=== start") and lines[0] == "old 51"
    print("ok start log")


class FakeApi:
    def __init__(self, above):
        self._above = above

    def toplevel(self, root):
        return 10

    def windows(self):
        return [{"hwnd": 20, "visible": True, "owner": 0, "title": "PhotoCraft", "exstyle": 0, "exe": winlink.exe_name(), "area": 9, "pid": 1}]

    def state_of(self, h):
        return True, False

    def foreground(self):
        return 20

    def rect(self, h):
        return (1, 2, 3, 4) if h == 10 else (0, 0, 100, 100)

    def owner_of(self, h):
        return 20

    def above(self, a, b):
        return self._above


def test_window_state():
    winlink.set_control_port(None)
    s = winlink.window_state(None, api=FakeApi(False))
    assert "own rect=(1, 2, 3, 4) visible=True" in s and "own is BELOW it" in s and "linked=True" in s and "focus=PhotoCraft" in s, s
    assert "own is above it" in winlink.window_state(None, api=FakeApi(True))
    print("ok window state")


class ZApi:
    """A z-order list (top first) for lift_above_owner: own window 10, PhotoCraft 20, others 30, 40."""
    def __init__(self, order, topmost=(), refuse=()):
        self.order, self.topmost, self.refuse, self.calls = list(order), set(topmost), set(refuse), []

    def toplevel(self, root):
        return 10

    def owner_of(self, h):
        return 20 if h == 10 else 0

    def windows(self):
        return [{"hwnd": 20, "visible": True, "owner": 0, "title": "PhotoCraft", "exstyle": 0, "exe": winlink.exe_name(), "area": 9, "pid": 1}]

    def state_of(self, h):
        return True, False

    def above(self, a, b):
        return self.order.index(a) < self.order.index(b)

    def window_above(self, h):
        i = self.order.index(h)
        prev = self.order[i - 1] if i else 0
        return prev, prev in self.topmost

    def _move(self, h, pos, how):
        self.calls.append(how)
        if how in self.refuse:
            return
        self.order.remove(h)
        self.order.insert(pos, h)

    def place_below(self, h, above):
        self._move(h, [x for x in self.order if x != h].index(above) + 1, ("below", h, above))

    def bring_to_top(self, h):
        self._move(h, len(self.topmost), ("top", h))


def test_lift_above_owner():
    winlink.set_control_port(None)
    a = ZApi([30, 20, 40, 10])                               # under PhotoCraft: goes right under 30, nothing else moves
    assert winlink.lift_above_owner(None, api=a) == "lifted above PhotoCraft" and a.order == [30, 10, 20, 40], a.order
    assert winlink.lift_above_owner(None, api=a) == "" and len(a.calls) == 1            # above already: nothing done
    a = ZApi([20, 40, 10])                                   # PhotoCraft first: top of the normal windows
    assert winlink.lift_above_owner(None, api=a) == "lifted above PhotoCraft (top)" and a.order == [10, 20, 40]
    a = ZApi([99, 20, 10], topmost={99})                    # never below a topmost window (it would become topmost)
    assert winlink.lift_above_owner(None, api=a) == "lifted above PhotoCraft (top)" and a.order == [99, 10, 20], a.order
    assert ("below", 10, 99) not in a.calls
    a = ZApi([30, 20, 10], refuse={("below", 10, 30), ("top", 10)})                     # both refused: PhotoCraft under it
    assert winlink.lift_above_owner(None, api=a) == "lifted above PhotoCraft (PhotoCraft moved under it)" and a.order == [30, 10, 20]
    a = ZApi([20, 10], refuse={("top", 10), ("below", 20, 10)})
    assert winlink.lift_above_owner(None, api=a) == "lifting above PhotoCraft failed"
    a = ZApi([20, 10])
    a.owner_of = lambda h: 0                                  # not tied: not touched
    assert winlink.lift_above_owner(None, api=a) == "" and not a.calls
    print("ok lift above owner")


def test_hidden_until_placed():
    wl = gui.winlink
    saved = (wl.available, wl.link, wl.owner_present, wl.owner_rect, wl.window_state, wl.lift_above_owner)
    lifts = []
    found = {"v": False}
    try:
        wl.available = lambda: True
        wl.link = lambda root, api=None: found["v"]
        wl.owner_present = lambda api=None: True
        wl.owner_rect = lambda api=None: (0, 0, 1600, 900)
        wl.window_state = lambda root, api=None: "state"
        wl.lift_above_owner = lambda root, api=None: lifts.append(1) or "lifted above PhotoCraft"
        alpha, scheduled = [], []
        orig = gui.tk.Tk

        class Root(orig):
            def attributes(self, *a):
                if a and a[0] == "-alpha" and len(a) == 2:
                    alpha.append(a[1])

            def after(self, ms, fn=None, *a):
                scheduled.append((ms, fn))
                return "job"

        gui.tk.Tk = Root
        try:
            cfgmod.save_state({})
            app = gui.App(cfgmod.load())
        finally:
            gui.tk.Tk = orig
        assert alpha == [0.0] and app._revealed is False, alpha            # invisible from the first moment
        assert any(ms == gui.REVEAL_MS for ms, _ in scheduled)
        log = cfgmod.EXCHANGE_DIR / startlog.LOG_NAME
        assert "hidden until placed=True" in log.read_text(encoding="utf-8")
        app.root.geometry = lambda g=None: "380x700+0+0"
        app.root.winfo_width = lambda: 380
        app._try_link()                                                        # PhotoCraft not there yet: stays hidden
        assert alpha == [0.0]
        found["v"] = True
        app._try_link()                                                        # linked and placed: shown now, once
        assert alpha == [0.0, 1.0] and app._revealed
        app._try_link()
        assert alpha == [0.0, 1.0]
        text = log.read_text(encoding="utf-8")
        assert "linked to PhotoCraft" in text and "moved to 16," in text and "shown (placed at PhotoCraft)" in text, text
        assert len(lifts) == 2 and "lifted above PhotoCraft" in text          # every linked watchdog round checks it
        app._start_log_tick()
        assert text.splitlines()[-1] != "state" and "state" in log.read_text(encoding="utf-8").splitlines()[-1]

        # PhotoCraft never found: shown after REVEAL_MS anyway
        scheduled.clear()
        found["v"] = False
        app._hide_until_placed()
        fn = next(f for ms, f in scheduled if ms == gui.REVEAL_MS)
        fn()
        assert alpha[-1] == 1.0 and app._revealed and "not linked within 3 s" in log.read_text(encoding="utf-8")
        # "stay with PhotoCraft" off: no hiding at all
        alpha.clear()
        app.v_top.set(False)
        app._hide_until_placed()
        assert alpha == [1.0] and app._revealed                              # shown at once
    finally:
        wl.available, wl.link, wl.owner_present, wl.owner_rect, wl.window_state, wl.lift_above_owner = saved
    print("ok hidden until placed")


def main():
    test_startlog()
    test_window_state()
    test_lift_above_owner()
    test_hidden_until_placed()
    print("ok")


if __name__ == "__main__":
    main()
