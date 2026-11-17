"""Tie the PxC window to PhotoCraft's main window under Linux with X11 (user 15.11., "A: mit Menü-Schutz").

The X11 counterpart of the Windows owned window (winlink.py): PxC becomes a *transient* window of PhotoCraft (WM_TRANSIENT_FOR).
The window manager then minimizes and restores it with PhotoCraft and keeps it above PhotoCraft only, not above every other
program (window test on Linux Mint 15.11.: with "always on top" it did not minimize and covered PhotoCraft's menus).

`X11Api` offers the same calls as `winlink.Win32Api` that `winlink.link`, `unlink`, `owner_present`, `owner_rect` and
`guard_menus` use, so the Windows rules (menu guard, first place under the menu bar) run unchanged with it. It talks to
libX11 through ctypes: no new dependency (every X11 desktop has the library). Wayland without XWayland, or no libX11:
`api()` returns None and the window keeps "always on top" as before. Windows never loads this module's library.
"""
from __future__ import annotations

import os
import sys

BUTTON1_MASK = 1 << 8
XK_ESCAPE = 0xFF1B
VK_LBUTTON, VK_ESCAPE = 0x01, 0x1B        # the Windows key codes winlink.guard_menus asks for


def available() -> bool:
    """Linux (or another X11 system) with an X display; never Windows."""
    return os.name != "nt" and sys.platform != "darwin" and bool(os.environ.get("DISPLAY"))


def frame_rect(x: int, y: int, w: int, h: int, extents) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of a window with its frame (_NET_FRAME_EXTENTS left, right, top, bottom), like Windows'
    GetWindowRect, which includes the title bar: winlink.MENU_BAND counts from the top of the title bar."""
    el, er, et, eb = (list(extents or ()) + [0, 0, 0, 0])[:4]
    return x - el, y - et, x + w + er, y + h + eb


class X11Api:
    """The part of winlink.Win32Api that winlink's link and menu rules need, on X11. Window ids are X window ids."""

    def __init__(self):
        import ctypes
        import ctypes.util
        self.c = ctypes
        path = ctypes.util.find_library("X11") or "libX11.so.6"
        x = ctypes.CDLL(path)
        self.x = x
        vp, ul, c_int, c_uint = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_uint
        x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = vp, [ctypes.c_char_p]
        x.XDefaultRootWindow.restype, x.XDefaultRootWindow.argtypes = ul, [vp]
        x.XInternAtom.restype, x.XInternAtom.argtypes = ul, [vp, ctypes.c_char_p, c_int]
        x.XGetWindowProperty.restype = c_int
        x.XGetWindowProperty.argtypes = [vp, ul, ul, ctypes.c_long, ctypes.c_long, c_int, ul, ctypes.POINTER(ul),
                                         ctypes.POINTER(c_int), ctypes.POINTER(ul), ctypes.POINTER(ul), ctypes.POINTER(vp)]
        x.XFree.argtypes = [vp]
        x.XSetTransientForHint.argtypes = [vp, ul, ul]
        x.XDeleteProperty.argtypes = [vp, ul, ul]
        x.XFlush.argtypes = [vp]
        x.XQueryPointer.restype = c_int
        x.XQueryPointer.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(ul), ctypes.POINTER(c_int), ctypes.POINTER(c_int),
                                    ctypes.POINTER(c_int), ctypes.POINTER(c_int), ctypes.POINTER(c_uint)]
        x.XQueryKeymap.argtypes = [vp, ctypes.c_char_p]
        x.XKeysymToKeycode.restype, x.XKeysymToKeycode.argtypes = ctypes.c_ubyte, [vp, ul]
        x.XTranslateCoordinates.restype = c_int
        x.XTranslateCoordinates.argtypes = [vp, ul, ul, c_int, c_int, ctypes.POINTER(c_int), ctypes.POINTER(c_int), ctypes.POINTER(ul)]
        x.XGetGeometry.restype = c_int
        x.XGetGeometry.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(c_int), ctypes.POINTER(c_int), ctypes.POINTER(c_uint),
                                   ctypes.POINTER(c_uint), ctypes.POINTER(c_uint), ctypes.POINTER(c_uint)]
        x.XQueryTree.restype = c_int
        x.XQueryTree.argtypes = [vp, ul, ctypes.POINTER(ul), ctypes.POINTER(ul), ctypes.POINTER(vp), ctypes.POINTER(c_uint)]
        x.XSetErrorHandler.restype, x.XSetErrorHandler.argtypes = vp, [vp]
        self.d = x.XOpenDisplay(None)
        if not self.d:
            raise OSError("no X display")
        # A window that vanished between two calls must not end the program (Xlib's default handler exits). The handler is
        # one per process: errors of our own connection are ignored, every other one goes on to the handler before (Tk's).
        proto = ctypes.CFUNCTYPE(c_int, vp, vp)
        mine = self.d
        before: list = [None]

        def on_error(dpy, event):
            if dpy == mine or not before[0]:
                return 0
            return before[0](dpy, event)
        self._on_error = proto(on_error)
        prev = x.XSetErrorHandler(self._on_error)
        before[0] = proto(prev) if prev else None
        self.root_win = x.XDefaultRootWindow(self.d)
        self._atoms: dict[str, int] = {}
        self._tk_root = None

    def atom(self, name: str) -> int:
        if name not in self._atoms:
            self._atoms[name] = int(self.x.XInternAtom(self.d, name.encode(), 0))
        return self._atoms[name]

    def prop(self, win: int, name: str, fmt_long: bool = True) -> list[int] | bytes | None:
        """A window property: a list of numbers (32-bit formats: WINDOW, CARDINAL, ATOM) or the bytes of a string; None if absent."""
        c = self.c
        typ, fmt, n, after, data = c.c_ulong(), c.c_int(), c.c_ulong(), c.c_ulong(), c.c_void_p()
        ok = self.x.XGetWindowProperty(self.d, win, self.atom(name), 0, 4096, 0, 0, c.byref(typ), c.byref(fmt), c.byref(n),
                                       c.byref(after), c.byref(data))
        if ok != 0 or not data.value:
            return None
        try:
            if fmt.value == 32:          # Xlib hands 32-bit items over as C longs
                return list(c.cast(data, c.POINTER(c.c_ulong))[:n.value])
            if fmt.value == 8:
                return c.string_at(data, n.value)
            return None
        finally:
            self.x.XFree(data)

    def _pid(self, win: int) -> int:
        pid = self.prop(win, "_NET_WM_PID")
        return int(pid[0]) if isinstance(pid, list) and pid else 0

    def _exe(self, win: int) -> str:
        pid = self._pid(win)
        if not pid:
            return ""
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return ""

    def _title(self, win: int) -> str:
        t = self.prop(win, "_NET_WM_NAME") or self.prop(win, "WM_NAME")
        return t.decode("utf-8", "replace") if isinstance(t, bytes) else ""

    def windows(self, everything: bool = False) -> list[dict]:
        """The windows the window manager manages (_NET_CLIENT_LIST), as winlink.pick_window expects them."""
        out = []
        for w in self.prop(self.root_win, "_NET_CLIENT_LIST") or []:
            try:
                r = self.rect(w)
                owner = self.owner_of(w)
                out.append({"hwnd": int(w), "visible": True, "owner": owner, "title": self._title(w) or "?", "exstyle": 0,
                            "exe": self._exe(w), "pid": self._pid(w), "rect": r, "class": "", "iconic": False,
                            "area": max(0, r[2] - r[0]) * max(0, r[3] - r[1])})
            except Exception:
                pass
        return out

    def toplevel(self, root) -> int:
        """The window the window manager manages for the Tk root: Tk's wrapper, the X parent of the root's inner window; 0
        while Tk has not made it yet (the parent is then the screen's root window). Not `wm frame`: that names the window
        manager's decoration frame around it (laptop 15.11.: the link went onto Muffin's frame, which it ignores). Stays
        the same while the window is hidden for a menu."""
        self._tk_root = root
        root.update_idletasks()
        try:
            parent = self.parent_of(int(root.winfo_id()))
        except Exception:
            return 0
        return 0 if parent in (0, self.root_win) else parent

    def parent_of(self, win: int) -> int:
        c = self.c
        r, parent, kids, n = c.c_ulong(), c.c_ulong(), c.c_void_p(), c.c_uint()
        if not self.x.XQueryTree(self.d, win, c.byref(r), c.byref(parent), c.byref(kids), c.byref(n)):
            return 0
        if kids.value:
            self.x.XFree(kids)
        return int(parent.value)

    def owner_of(self, win: int) -> int:
        t = self.prop(win, "WM_TRANSIENT_FOR")
        return int(t[0]) if isinstance(t, list) and t else 0

    def set_owner(self, win: int, owner: int) -> None:
        if owner:
            self.x.XSetTransientForHint(self.d, win, owner)
        else:
            self.x.XDeleteProperty(self.d, win, self.atom("WM_TRANSIENT_FOR"))
        self.x.XFlush(self.d)

    def cursor(self) -> tuple[int, int]:
        x, y = self._pointer()[:2]
        return x, y

    def _pointer(self) -> tuple[int, int, int]:
        c = self.c
        r, ch = c.c_ulong(), c.c_ulong()
        rx, ry, wx, wy, mask = c.c_int(), c.c_int(), c.c_int(), c.c_int(), c.c_uint()
        self.x.XQueryPointer(self.d, self.root_win, c.byref(r), c.byref(ch), c.byref(rx), c.byref(ry), c.byref(wx), c.byref(wy),
                             c.byref(mask))
        return rx.value, ry.value, mask.value

    def key_down(self, vk: int) -> bool:
        """The two keys winlink.guard_menus asks for: the left mouse button and Escape."""
        if vk == VK_LBUTTON:
            return bool(self._pointer()[2] & BUTTON1_MASK)
        if vk == VK_ESCAPE:
            code = int(self.x.XKeysymToKeycode(self.d, XK_ESCAPE))
            keys = self.c.create_string_buffer(32)
            self.x.XQueryKeymap(self.d, keys)
            return bool(code) and bool(keys.raw[code // 8] & (1 << (code % 8)))
        return False

    def rect(self, win: int) -> tuple[int, int, int, int]:
        c = self.c
        r, gx, gy, w, h, bw, depth = c.c_ulong(), c.c_int(), c.c_int(), c.c_uint(), c.c_uint(), c.c_uint(), c.c_uint()
        self.x.XGetGeometry(self.d, win, c.byref(r), c.byref(gx), c.byref(gy), c.byref(w), c.byref(h), c.byref(bw), c.byref(depth))
        ax, ay, child = c.c_int(), c.c_int(), c.c_ulong()
        self.x.XTranslateCoordinates(self.d, win, self.root_win, 0, 0, c.byref(ax), c.byref(ay), c.byref(child))
        return frame_rect(ax.value, ay.value, w.value, h.value, self.prop(win, "_NET_FRAME_EXTENTS"))

    def monitor_at(self, x: int, y: int) -> int:
        L, T, R, B = self.rect(self.root_win)
        return 1 if L <= x < R and T <= y < B else 0

    def show(self, win: int, visible: bool) -> None:
        """Hide for an open PhotoCraft menu / show again: through Tk (withdraw / deiconify), which keeps its own state right."""
        root = self._tk_root
        if root is None:
            return
        if visible:
            root.deiconify()
        else:
            root.withdraw()


_API: list = []


def api():
    """The one X11Api of this process, or None (not X11, no libX11, no display). Tried once."""
    if not _API:
        made = None
        if available():
            try:
                made = X11Api()
            except Exception:
                made = None
        _API.append(made)
    return _API[0]
