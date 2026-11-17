"""A second PhotoCraft (a PSD opened by a double click, without the control channel): the plugin window sits only on the
PhotoCraft that holds the control port, and Copy canvas, Save image and a run say so when another one is open (user 16.11.,
bug: Ctrl+S saved the picture of the other PhotoCraft; choice 1: link to the right one and warn).

    python tests/test_second_photocraft.py
"""
import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pccomfy import portowner, winlink  # noqa: E402

EXE = "photocraft.exe"


def win(hwnd, pid, area, exe="C:\\Apps\\PhotoCraft\\photocraft.exe", **kw):
    w = {"hwnd": hwnd, "pid": pid, "visible": True, "owner": 0, "title": "PhotoCraft", "exstyle": 0, "exe": exe, "area": area}
    w.update(kw)
    return w


def test_pick_window_prefers_control_pid():
    infos = [win(1, 100, 500), win(2, 200, 900), win(3, 300, 50, exe="C:\\x\\python.exe")]
    assert winlink.pick_window(infos, EXE) == 2                 # no pid: the largest, as before
    assert winlink.pick_window(infos, EXE, 100) == 1            # the PhotoCraft with the control port wins, even when smaller
    assert winlink.pick_window(infos, EXE, 999) == 2            # pid not among the windows (Flatpak): as before
    hidden = [win(1, 100, 500, visible=False), win(2, 200, 900)]
    assert winlink.pick_window(hidden, EXE, 100) == 2           # no plausible window of it: the other one rather than none


def test_other_photocrafts():
    one = [win(1, 100, 500), win(4, 100, 20, owner=1)]          # one program, an owned dialog of it
    assert winlink.other_photocrafts(one, EXE, 100) == 0
    assert winlink.other_photocrafts(one, EXE, None) == 0
    two = one + [win(2, 200, 900)]
    assert winlink.other_photocrafts(two, EXE, 100) == 1
    assert winlink.other_photocrafts(two, EXE, None) == 1        # pid unknown: every program beyond the first
    assert winlink.other_photocrafts(two, EXE, 999) == 1
    assert winlink.other_photocrafts([win(2, 200, 900)], EXE, 100) == 0   # only the other one: no pair, nothing to compare


def test_others_open_with_fake_api():
    class Api:
        def __init__(self, infos):
            self.infos = infos

        def windows(self, everything=False):
            return self.infos
    old = winlink.CONTROL_PORT[0], dict(winlink._PID_CACHE)
    try:
        winlink.set_control_port(None)
        assert winlink.others_open(api=Api([win(1, 100, 500)])) is False
        assert winlink.others_open(api=Api([win(1, 100, 500), win(2, 200, 900)])) is True
    finally:
        winlink.CONTROL_PORT[0] = old[0]
        winlink._PID_CACHE.update(old[1])


def test_listen_inodes_and_pick_listener():
    text = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
            "   0: 0100007F:1EC6 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 4242 1\n"
            "   1: 0100007F:1EC6 0100007F:9C40 01 00000000:00000000 00:00000000 00000000  1000        0 5555 1\n"
            "   2: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 77 1\n")
    assert portowner.listen_inodes(text, 7878) == {"4242"}      # 0x1EC6 = 7878, only the listening line
    assert portowner.listen_inodes(text, 22) == {"77"}
    assert portowner.listen_inodes(text, 9999) == set()
    assert portowner.pick_listener([(80, 4), (7878, 1234)], 7878) == 1234
    assert portowner.pick_listener([(7878, 0)], 7878) is None


def test_listener_pid_finds_this_process():
    """A socket this test opens on a free port (never 8188): the lookup names this process."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    try:
        port = s.getsockname()[1]
        pid = portowner.listener_pid(port)
        if sys.platform == "win32" or os.path.isdir("/proc/net"):
            assert pid == os.getpid(), (pid, os.getpid())
        else:
            assert pid is None
    finally:
        s.close()


def test_hint_and_wiring():
    from pccomfy import gui
    App = gui.App
    assert "Another PhotoCraft is open" in App.OTHER_PC_HINT
    me = object.__new__(App)
    assert App._note_done(me, "Saved: a.png", False) == ("note", "Saved: a.png")
    kind, text = App._note_done(me, "Saved: a.png", True)
    assert kind == "note-error" and text.startswith("Saved: a.png ") and App.OTHER_PC_HINT in text
    root = Path(__file__).resolve().parent.parent / "pccomfy"
    src = (root / "gui.py").read_text(encoding="utf-8")
    assert "winlink.set_control_port(pcc[\"port\"])" in src
    assert src.count("other = self._other_photocraft()") == 2          # Copy canvas and Save image
    run = (root / "gui_run.py").read_text(encoding="utf-8")
    assert "self._other_pc = self._other_photocraft()" in run and "self.OTHER_PC_HINT" in run


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
