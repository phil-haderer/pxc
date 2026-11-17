"""Which system the plugin runs on: the one place every platform branch asks (PLAN.md 18c).

The Windows branches are the code that always ran; a Linux branch is added next to it, never in its place.
``tests/test_platform_pins.py`` pins what each system gets.
"""
from __future__ import annotations

import os
import sys

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")

# Tk window arguments. Windows gets none (the code that always ran). Elsewhere the window manager needs a WM_CLASS: Tk sets
# none that is usable and WSLg's Weston drops the window without it ("does not have appId").
ROOT_KW = {} if IS_WINDOWS else {"className": "pccomfy"}
TOP_KW = {} if IS_WINDOWS else {"class_": "Pccomfy"}
# The bottom-right resize grip: X11 has no "size_nw_se".
GRIP_CURSOR = "size_nw_se" if IS_WINDOWS else "bottom_right_corner"


def _user_dirs_value(text: str, key: str, home: str) -> str | None:
    """The value of ``key="..."`` in the text of an XDG user-dirs.dirs file ("$HOME" expanded), or None."""
    found = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(key + "="):
            continue
        val = line.split("=", 1)[1].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        val = val.replace("${HOME}", home).replace("$HOME", home)
        if val:
            found = val                    # the last assignment wins, like in a shell
    return found


def _windows_downloads() -> str | None:
    """The Downloads folder from the shell (SHGetKnownFolderPath), also when the user moved it. None if the call fails."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        guid = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7D))
        shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ptr = ctypes.c_void_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr))
        try:
            if hr == 0 and ptr.value:
                return ctypes.wstring_at(ptr.value) or None
        finally:
            if ptr.value:
                ole32.CoTaskMemFree(ptr)
    except Exception:
        pass
    return None


def downloads_dir():
    """The user's Downloads folder (a pathlib.Path; never created here)."""
    from pathlib import Path
    home = Path.home()
    if IS_WINDOWS:
        p = _windows_downloads()
        return Path(p) if p else home / "Downloads"
    env = os.environ.get("XDG_DOWNLOAD_DIR")
    if env:
        return Path(env).expanduser()
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")) / "user-dirs.dirs"
    try:
        val = _user_dirs_value(cfg.read_text(encoding="utf-8", errors="replace"), "XDG_DOWNLOAD_DIR", str(home))
    except OSError:
        val = None
    return Path(val) if val else home / "Downloads"
