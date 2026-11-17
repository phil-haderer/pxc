"""Which process listens on a local TCP port: the PhotoCraft that holds the plugin's control channel (`--control <port>`).

A PhotoCraft opened by a double click on a PSD is a second program without that channel. The plugin window must sit on the
PhotoCraft it talks to, and say so when another one is open (user 16.11., bug: Ctrl+S saved the picture of the other
PhotoCraft). Standard library only: Windows asks iphlpapi (GetExtendedTcpTable), Linux reads /proc. None = cannot tell.
"""
from __future__ import annotations

import os
import socket
import sys

LISTEN_HEX = "0A"                      # /proc/net/tcp: state TCP_LISTEN
TCP_TABLE_OWNER_PID_LISTENER = 3


def listen_inodes(text: str, port: int) -> set[str]:
    """Pure: the socket inodes of /proc/net/tcp (or tcp6) lines that listen on `port`."""
    out = set()
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10 or parts[3] != LISTEN_HEX:
            continue
        try:
            if int(parts[1].rsplit(":", 1)[1], 16) == int(port):
                out.add(parts[9])
        except (ValueError, IndexError):
            continue
    return out


def pick_listener(rows, port: int) -> int | None:
    """Pure: rows of (local port in host order, pid) of listening sockets; the pid that listens on `port`."""
    for p, pid in rows:
        if int(p) == int(port) and pid:
            return int(pid)
    return None


def _linux_pid(port: int, proc: str = "/proc") -> int | None:
    inodes: set[str] = set()
    for name in ("tcp", "tcp6"):
        try:
            with open(os.path.join(proc, "net", name), encoding="ascii", errors="replace") as f:
                inodes |= listen_inodes(f.read(), port)
        except OSError:
            continue
    inodes.discard("0")
    if not inodes:
        return None
    wanted = {f"socket:[{i}]" for i in inodes}
    try:
        pids = [d for d in os.listdir(proc) if d.isdigit()]
    except OSError:
        return None
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue                    # another user's process, or gone
        for fd in fds:
            try:
                if os.readlink(os.path.join(fd_dir, fd)) in wanted:
                    return int(pid)
            except OSError:
                continue
    return None


def _windows_rows() -> list[tuple[int, int]]:
    import ctypes
    from ctypes import wintypes
    fn = ctypes.windll.iphlpapi.GetExtendedTcpTable
    fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    fn.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    fn(None, ctypes.byref(size), False, socket.AF_INET, TCP_TABLE_OWNER_PID_LISTENER, 0)
    for _ in range(3):                  # the table can grow between the two calls
        buf = ctypes.create_string_buffer(size.value + 1024)
        size = wintypes.DWORD(len(buf))
        if fn(buf, ctypes.byref(size), False, socket.AF_INET, TCP_TABLE_OWNER_PID_LISTENER, 0) == 0:
            break
    else:
        return []
    n = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    cells = ctypes.cast(ctypes.addressof(buf) + 4, ctypes.POINTER(wintypes.DWORD))
    rows = []
    for i in range(n):                  # MIB_TCPROW_OWNER_PID: state, local addr, local port, remote addr, remote port, pid
        row = cells[i * 6:(i + 1) * 6]
        rows.append((socket.ntohs(row[2] & 0xFFFF), row[5]))
    return rows


def listener_pid(port: int) -> int | None:
    """The pid of the process that listens on 127.0.0.1:`port` (any local address), None if none or it cannot tell."""
    try:
        if sys.platform == "win32":
            return pick_listener(_windows_rows(), port)
        if os.path.isdir("/proc/net"):
            return _linux_pid(port)
    except Exception:
        return None
    return None
