"""Linux (X11): the plugin hangs on PhotoCraft as a transient window, with the menu guard (user 15.11., "A: mit Menü-Schutz").
Pure parts and the window's path with a faked X11 api; the real libX11 calls only where a display exists (the laptop).

    python tests/test_x11link.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402

gui, cfgmod = t.gui, t.cfgmod
from pccomfy import winlink, x11link  # noqa: E402

PC, OURS = 0x4000002, 0x44004B1


class FakeX11:
    """What X11Api offers winlink: one PhotoCraft window (exe /usr/bin/photocraft) and the plugin's wrapper."""

    def __init__(self, present=True):
        self.present = present
        self.owners = {}
        self.shown = []
        self.cur, self.button, self.esc = (500, 20), False, False

    def windows(self, everything=False):
        out = [{"hwnd": OURS, "visible": True, "owner": self.owners.get(OURS, 0), "title": "PxC", "exstyle": 0,
                "exe": "/home/u/pxc/.venv/bin/python3", "area": 380 * 700}]
        if self.present:
            out.append({"hwnd": PC, "visible": True, "owner": 0, "title": "PhotoCraft", "exstyle": 0,
                        "exe": "/usr/bin/photocraft", "area": 1366 * 740})
        return out

    def toplevel(self, root):
        return OURS

    def owner_of(self, w):
        return self.owners.get(w, 0)

    def set_owner(self, w, owner):
        self.owners[w] = owner

    def rect(self, w):
        return (0, 0, 1366, 768) if w == PC else (16, 86, 396, 786)

    def cursor(self):
        return self.cur

    def key_down(self, vk):
        return self.button if vk == x11link.VK_LBUTTON else self.esc if vk == x11link.VK_ESCAPE else False

    def show(self, w, visible):
        self.shown.append(visible)


def test_pure():
    assert x11link.frame_rect(100, 60, 800, 600, [2, 2, 30, 2]) == (98, 30, 902, 662)     # title bar counts, like Windows
    assert x11link.frame_rect(5, 6, 10, 20, None) == (5, 6, 15, 26)
    if os.name == "nt":
        assert not x11link.available() and x11link.api() is None
        assert winlink.exe_name() == "photocraft.exe"
    else:
        assert winlink.exe_name() == "photocraft"
    old = os.environ.pop("PCC_PHOTOCRAFT_EXE", None)
    try:
        os.environ["PCC_PHOTOCRAFT_EXE"] = "PhotoCraft-Beta"
        assert winlink.exe_name() == "photocraft-beta"
    finally:
        os.environ.pop("PCC_PHOTOCRAFT_EXE", None)
        if old is not None:
            os.environ["PCC_PHOTOCRAFT_EXE"] = old


def test_winlink_rules_with_x11():
    saved = winlink.exe_name
    winlink.exe_name = lambda: "photocraft"           # the Linux name, also when this test runs on Windows
    try:
        f = FakeX11()
        assert winlink.link(object(), f) is True and f.owners[OURS] == PC
        assert winlink.owner_present(f) is True and winlink.owner_rect(f) == (0, 0, 1366, 768)
        # a click in PhotoCraft's menu bar hides the plugin, a click below it brings it back
        st = winlink.guard_menus(object(), {}, 1.0, api=f)
        f.button = True
        st = winlink.guard_menus(object(), st, 1.0, api=f)
        assert st["hidden"] and f.shown == [False]
        f.button = False
        st = winlink.guard_menus(object(), st, 1.0, api=f)
        f.cur, f.button = (700, 300), True
        st = winlink.guard_menus(object(), st, 1.0, api=f)
        assert not st["hidden"] and f.shown == [False, True]
        winlink.unlink(object(), f)
        assert f.owners[OURS] == 0
        f2 = FakeX11(present=False)
        assert winlink.link(object(), f2) is False and winlink.owner_present(f2) is False
    finally:
        winlink.exe_name = saved


def test_window_path():
    """Not Windows, X11 there: on top until the link holds, then above PhotoCraft only; the menu guard runs with that api."""
    wl = gui.winlink
    saved = (wl.available, wl.link, wl.unlink, wl.owner_present, wl.guard_menus, wl.owner_rect, x11link.api)
    fake = FakeX11()
    seen = {"link": [], "guard": [], "unlink": []}
    found = {"v": False}
    try:
        wl.available = lambda: False
        x11link.api = lambda: fake
        wl.link = lambda root, api=None: (seen["link"].append(api), found["v"])[1]
        wl.unlink = lambda root, api=None: seen["unlink"].append(api)
        wl.owner_present = lambda api=None: True
        wl.owner_rect = lambda api=None: None
        wl.guard_menus = lambda root, st, ui=1.0, api=None: (seen["guard"].append(api), st)[1]
        app = gui.App(cfgmod.load())
        top = {"v": None}

        def attributes(*a):
            if len(a) == 2:
                top["v"] = a[1]
            return top["v"]
        app.root.attributes = attributes
        scheduled = []
        app.root.after = lambda ms, fn=None, *a: (scheduled.append((ms, fn)), "job")[1]
        app.root.after_cancel = lambda j: None
        app.v_top.set(True)
        app._on_top()
        assert top["v"] is True and scheduled[-1][0] == 300           # on top until PhotoCraft's window is found
        scheduled.pop()[1]()
        assert seen["link"] == [fake] and top["v"] is True            # not found yet: stays on top
        found["v"] = True
        scheduled.pop()[1]()
        assert top["v"] is False                                     # tied to PhotoCraft: no longer above everything
        app._yield_popups()
        assert seen["guard"] == [fake]
        app.v_top.set(False)
        app._on_top()
        assert top["v"] is False and seen["unlink"] == [fake]
        # no X11 (Wayland without XWayland, no libX11): "always on top" as before
        x11link.api = lambda: None
        app.v_top.set(True)
        app._on_top()
        assert top["v"] is True
    finally:
        wl.available, wl.link, wl.unlink, wl.owner_present, wl.guard_menus, wl.owner_rect, x11link.api = saved


def test_real_display():
    """Only with an X display (Linux desktop): the library loads and the root window answers."""
    api = x11link.api()
    if api is None:
        print("  (no X display: real X11 calls skipped)")
        return
    L, T, R, B = api.rect(api.root_win)
    assert R > L and B > T
    assert isinstance(api.windows(), list)
    x, y = api.cursor()
    assert isinstance(x, int) and isinstance(y, int)


def main():
    test_pure()
    test_winlink_rules_with_x11()
    test_window_path()
    test_real_display()
    print("ALL OK (x11link)")


if __name__ == "__main__":
    main()
