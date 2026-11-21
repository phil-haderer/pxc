"""Hold a picture on the X11 clipboard ourselves (Linux; decision 19.11., choice A).

xclip 0.13 answers EVERY request with its data and calls it the type it was given, so a program that asks for text first
gets a "PNG" labelled as image/png and PhotoCraft (arboard) stops there: "incorrect type received from clipboard". This
small owner offers only TARGETS and image/png and refuses everything else, as ICCCM wants; big pictures go in INCR parts.

It runs as its own process (started by ``clipboard``): ``python x11clip.py`` reads the PNG from stdin, takes the CLIPBOARD,
prints "ready" and serves until another program takes the clipboard. Only libX11 through ctypes, no package imports, so it
starts fast and needs nothing installed (libX11 is there wherever there is an X display, XWayland included).

The decisions (what to answer, how to cut into parts) are plain functions, testable anywhere: ``answer`` and ``chunks``.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import select
import sys
import time

PNG = "image/png"
OFFERED = ("TARGETS", PNG)
CHUNK_MAX = 256 * 1024          # INCR above this (also bounded by the server's request size)
STALL_S = 10.0                  # a part transfer with no answer this long is dropped (the requestor is gone; review 21.11.)
LINGER_S = 10.0                 # after another program took the clipboard: end at the latest this long after


# ---------- the decisions (no X needed) ----------

def answer(target: str, png: bytes):
    """What to put into the requestor's property for `target`: ("ATOM", 32, [names]) for TARGETS, (PNG, 8, bytes) for the
    picture, None to refuse (every other target, the point of this module)."""
    if target == "TARGETS":
        return "ATOM", 32, list(OFFERED)
    if target == PNG:
        return PNG, 8, png
    return None


def chunks(data: bytes, size: int) -> list[bytes]:
    """The INCR parts of `data` (each at most `size` bytes), ending with the empty part that closes the transfer."""
    size = max(1, int(size))
    return [data[i:i + size] for i in range(0, len(data), size)] + [b""]


def stalled(pending: dict, now: float, limit: float = STALL_S) -> list:
    """The part transfers to drop: no answer for ``limit`` seconds (``pending``: key -> (type, parts, last activity))."""
    return [k for k, v in pending.items() if now - v[2] >= limit]


def over(lost_at, pending: dict, now: float, linger: float = LINGER_S) -> bool:
    """Time to end: the clipboard was taken (``lost_at`` is its time, None = still ours) and every transfer is done, or
    ``linger`` seconds have passed since then."""
    return lost_at is not None and (not pending or now - lost_at >= linger)


# ---------- Xlib through ctypes ----------

SelectionClear, SelectionRequest, SelectionNotify, PropertyNotify = 29, 30, 31, 28
PropertyDelete = 1
PropertyChangeMask = 1 << 22
PropModeReplace = 0


class _SelReq(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("owner", ctypes.c_ulong), ("requestor", ctypes.c_ulong), ("selection", ctypes.c_ulong),
                ("target", ctypes.c_ulong), ("property", ctypes.c_ulong), ("time", ctypes.c_ulong)]


class _SelEv(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("requestor", ctypes.c_ulong), ("selection", ctypes.c_ulong), ("target", ctypes.c_ulong),
                ("property", ctypes.c_ulong), ("time", ctypes.c_ulong)]


class _SelClear(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("selection", ctypes.c_ulong), ("time", ctypes.c_ulong)]


class _PropEv(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("atom", ctypes.c_ulong), ("time", ctypes.c_ulong), ("state", ctypes.c_int)]


class _XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("req", _SelReq), ("sel", _SelEv), ("clear", _SelClear), ("prop", _PropEv),
                ("pad", ctypes.c_long * 24)]


def _xlib():
    name = ctypes.util.find_library("X11") or "libX11.so.6"
    x = ctypes.cdll.LoadLibrary(name)
    vp, ul, i = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int
    x.XOpenDisplay.restype = vp
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XInternAtom.restype = ul
    x.XInternAtom.argtypes = [vp, ctypes.c_char_p, i]
    x.XGetAtomName.restype = ctypes.c_void_p
    x.XGetAtomName.argtypes = [vp, ul]
    x.XFree.argtypes = [vp]
    x.XDefaultRootWindow.restype = ul
    x.XDefaultRootWindow.argtypes = [vp]
    x.XCreateSimpleWindow.restype = ul
    x.XCreateSimpleWindow.argtypes = [vp, ul, i, i, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ul, ul]
    x.XSetSelectionOwner.argtypes = [vp, ul, ul, ul]
    x.XGetSelectionOwner.restype = ul
    x.XGetSelectionOwner.argtypes = [vp, ul]
    x.XNextEvent.argtypes = [vp, ctypes.POINTER(_XEvent)]
    x.XChangeProperty.argtypes = [vp, ul, ul, ul, i, i, vp, i]
    x.XSendEvent.argtypes = [vp, ul, i, ctypes.c_long, ctypes.POINTER(_XEvent)]
    x.XSelectInput.argtypes = [vp, ul, ctypes.c_long]
    x.XFlush.argtypes = [vp]
    x.XMaxRequestSize.restype = ctypes.c_long
    x.XMaxRequestSize.argtypes = [vp]
    x.XCloseDisplay.argtypes = [vp]
    x.XPending.restype = i
    x.XPending.argtypes = [vp]
    x.XConnectionNumber.restype = i
    x.XConnectionNumber.argtypes = [vp]
    return x


_ERR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
_ignore_errors = _ERR_HANDLER(lambda d, e: 0)        # a requestor that went away must not end the owner


def serve(png: bytes, ready=lambda: None) -> int:
    """Own the CLIPBOARD with `png` until another program takes it. 0 when it was served, 1 when there was no display or
    the clipboard could not be taken (then `ready` is not called)."""
    try:
        x = _xlib()
    except OSError:
        return 1
    d = x.XOpenDisplay(None)
    if not d:
        return 1
    x.XSetErrorHandler.restype = ctypes.c_void_p
    x.XSetErrorHandler.argtypes = [_ERR_HANDLER]
    x.XSetErrorHandler(_ignore_errors)

    def atom(name: str) -> int:
        return x.XInternAtom(d, name.encode(), 0)

    def name_of(a: int) -> str:
        p = x.XGetAtomName(d, a)
        if not p:
            return ""
        s = ctypes.cast(p, ctypes.c_char_p).value.decode(errors="replace")
        x.XFree(p)
        return s

    clip, incr = atom("CLIPBOARD"), atom("INCR")
    win = x.XCreateSimpleWindow(d, x.XDefaultRootWindow(d), 0, 0, 1, 1, 0, 0, 0)
    x.XSetSelectionOwner(d, clip, win, 0)
    if x.XGetSelectionOwner(d, clip) != win:
        x.XCloseDisplay(d)
        return 1
    x.XFlush(d)
    ready()
    size = max(4096, min(CHUNK_MAX, int(x.XMaxRequestSize(d)) * 4 - 1024))
    pending: dict[tuple[int, int], tuple[int, list[bytes], float]] = {}   # (requestor, property) -> (type, parts left, last activity)

    def put(w, prop, type_atom, fmt, data):
        if fmt == 32:
            arr = (ctypes.c_long * len(data))(*data)
            x.XChangeProperty(d, w, prop, type_atom, 32, PropModeReplace, ctypes.cast(arr, ctypes.c_void_p), len(data))
        else:
            buf = ctypes.create_string_buffer(data, len(data)) if data else ctypes.create_string_buffer(1)
            x.XChangeProperty(d, w, prop, type_atom, 8, PropModeReplace, ctypes.cast(buf, ctypes.c_void_p), len(data))

    lost_at = None
    fd = x.XConnectionNumber(d)
    ev = _XEvent()
    while not over(lost_at, pending, time.monotonic()):
        for key in stalled(pending, time.monotonic()):   # the requestor went away mid-transfer: never wait for it forever
            del pending[key]
            x.XSelectInput(d, key[0], 0)
        if not x.XPending(d):
            try:
                select.select([fd], [], [], 0.5)         # wake up for the time limits even when no event comes
            except (OSError, ValueError):
                time.sleep(0.5)
            continue
        x.XNextEvent(d, ctypes.byref(ev))
        lost = lost_at is not None
        if ev.type == SelectionClear and ev.clear.selection == clip:
            lost_at = lost_at or time.monotonic()        # another program took the clipboard: finish running transfers
        elif ev.type == SelectionRequest:
            r = ev.req
            prop = r.property or r.target               # an obsolete requestor sends no property: use the target
            got = None if lost or r.selection != clip else answer(name_of(r.target), png)
            if got is not None:
                type_name, fmt, data = got
                if fmt == 32:
                    put(r.requestor, prop, atom("ATOM"), 32, [atom(n) for n in data])
                elif len(data) > size:                   # big: announce INCR, send parts as the requestor deletes them
                    x.XSelectInput(d, r.requestor, PropertyChangeMask)
                    pending[(r.requestor, prop)] = (atom(type_name), chunks(data, size), time.monotonic())
                    put(r.requestor, prop, incr, 32, [len(data)])
                else:
                    put(r.requestor, prop, atom(type_name), 8, data)
            reply = _XEvent()
            reply.sel.type = SelectionNotify
            reply.sel.display = d
            reply.sel.requestor, reply.sel.selection, reply.sel.target = r.requestor, r.selection, r.target
            reply.sel.property = prop if got is not None else 0
            reply.sel.time = r.time
            x.XSendEvent(d, r.requestor, 0, 0, ctypes.byref(reply))
        elif ev.type == PropertyNotify and ev.prop.state == PropertyDelete:
            key = (ev.prop.window, ev.prop.atom)
            if key in pending:
                type_atom, parts, _t = pending[key]
                put(key[0], key[1], type_atom, 8, parts.pop(0))
                if parts:
                    pending[key] = (type_atom, parts, time.monotonic())
                else:
                    del pending[key]
                    x.XSelectInput(d, key[0], 0)
        x.XFlush(d)
    x.XCloseDisplay(d)
    return 0


def main() -> int:
    png = sys.stdin.buffer.read()
    if not png:
        return 1

    def ready():
        sys.stdout.write("ready\n")
        sys.stdout.flush()
        sys.stdout.close()
    return serve(png, ready)


if __name__ == "__main__":
    sys.exit(main())
