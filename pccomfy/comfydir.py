"""Where ComfyUI's ``models`` folder is (no Tk here), so a download can go straight into it.

Order: the test override ``PCCOMFY_MODELS_DIR``, the folder you chose once (settings), the folder of the ComfyUI process that
waits on the port the plugin talks to (Windows: PowerShell; Linux: /proc), else the window asks. ComfyUI's API names no paths.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
from pathlib import Path

from .hostos import IS_LINUX, IS_WINDOWS

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def models_dir_of(path: str | Path) -> Path | None:
    """The ``models`` folder for a folder the user (or the process) points at: the ComfyUI folder (main.py and models), the
    folder above it (a portable install), or the models folder itself."""
    p = Path(path)
    for cand in (p, p / "models", p / "ComfyUI" / "models"):
        if cand.name.lower() == "models" and cand.is_dir():
            return cand
    return None


def root_from_process(exe: str, cmdline: str, cwd: str = "") -> Path | None:
    """The ComfyUI folder (it holds main.py and models) from a running process: its working folder (Linux passes it), an
    absolute main.py in the command line, else the folders above its Python (a portable install starts
    ``.\\python_embeded\\python.exe ComfyUI\\main.py``)."""
    if cwd:
        for cand in (Path(cwd), Path(cwd) / "ComfyUI"):
            if (cand / "main.py").exists() and (cand / "models").is_dir():
                return cand
    for tok in (cmdline or "").replace('"', " ").split():
        if tok.lower().endswith("main.py") and os.path.isabs(tok) and Path(tok).exists() and (Path(tok).parent / "models").is_dir():
            return Path(tok).parent
    p = Path(exe or "").parent
    for _ in range(5):
        for cand in (p / "ComfyUI", p):
            if (cand / "main.py").exists() and (cand / "models").is_dir():
                return cand
        if p.parent == p:
            break
        p = p.parent
    return None


def listen_inodes(tcp_text: str, port: int) -> set[str]:
    """The socket inodes that listen on ``port`` in the text of /proc/net/tcp (or tcp6); state 0A = LISTEN."""
    found = set()
    for line in tcp_text.splitlines()[1:]:
        f = line.split()
        if len(f) > 9 and f[3] == "0A":
            try:
                if int(f[1].rsplit(":", 1)[1], 16) == port:
                    found.add(f[9])
            except (IndexError, ValueError):
                continue
    return found


def _find_root_linux(port: int, proc: str = "/proc") -> Path | None:
    """Linux: the process that listens on ``port`` (/proc/net/tcp, then the socket in its fds), its working folder and command line."""
    inodes: set[str] = set()
    for name in ("tcp", "tcp6"):
        try:
            with open(os.path.join(proc, "net", name), encoding="ascii", errors="replace") as fh:
                inodes |= listen_inodes(fh.read(), port)
        except OSError:
            continue
    if not inodes:
        return None
    try:
        pids = [e for e in os.listdir(proc) if e.isdigit()]
    except OSError:
        return None
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            links = (os.readlink(os.path.join(fd_dir, fd)) for fd in os.listdir(fd_dir))
            if not any(link.startswith("socket:[") and link[8:-1] in inodes for link in links):
                continue
            base = os.path.join(proc, pid)
            with open(os.path.join(base, "cmdline"), "rb") as fh:
                cmdline = fh.read().replace(b"\0", b" ").decode(errors="replace").strip()
            return root_from_process(os.readlink(os.path.join(base, "exe")), cmdline, os.readlink(os.path.join(base, "cwd")))
        except OSError:
            continue        # a process of someone else, or gone meanwhile
    return None


# Windows (user 17.11.): the port is asked for without "-State Listen": on PC B Windows reported ComfyUI's waiting socket as
# FinWait1 or with no state at all, so the lookup found it in 1 of 6 tries and the window asked for the folder. The waiting socket
# is the one with no remote end (RemotePort 0). Found none: the python processes that run a main.py (pick_process chooses).
_WIN_SCRIPT = ("$c = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Where-Object {{ $_.RemotePort -eq 0 }} | "
               "Select-Object -First 1; "
               "if ($c) {{ $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\"; $how = 'port' }} "
               "else {{ $p = Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object {{ $_.CommandLine -match 'main\\.py' }}; "
               "$how = 'process' }}; "
               "@{{how = $how; items = @($p | Select-Object ExecutablePath, CommandLine)}} | ConvertTo-Json -Compress -Depth 3")


def _port_of(cmdline: str) -> int:
    """The port a ComfyUI command line asks for (``--port N`` or ``--port=N``), else ComfyUI's default 8188."""
    toks = (cmdline or "").replace('"', " ").replace("=", " ").split()
    for i, tok in enumerate(toks[:-1]):
        if tok == "--port":
            try:
                return int(toks[i + 1])
            except ValueError:
                break
    return 8188


def pick_process(answer: dict, port: int) -> Path | None:
    """The ComfyUI folder from the PowerShell answer of find_root: {"how": "port" | "process", "items": [{ExecutablePath, CommandLine}]}.
    "port": the process that holds the port. "process": a python process with main.py whose port (``--port``, default 8188) is ours."""
    items = answer.get("items") or []
    if isinstance(items, dict):         # PowerShell gives one object instead of a list of one
        items = [items]
    for it in items:
        if not isinstance(it, dict):
            continue
        cmd = it.get("CommandLine") or ""
        if answer.get("how") != "port" and _port_of(cmd) != port:
            continue
        root = root_from_process(it.get("ExecutablePath") or "", cmd)
        if root is not None:
            return root
    return None


def find_root(url: str, timeout: float = 10.0) -> Path | None:
    """The ComfyUI folder of the process that waits on the port of ``url`` (only for a local server), or None."""
    parts = urllib.parse.urlsplit(url)
    if (parts.hostname or "") not in LOCAL_HOSTS or not (IS_WINDOWS or IS_LINUX):
        return None
    port = parts.port or 8188
    if IS_LINUX:
        return _find_root_linux(port)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WIN_SCRIPT.format(port=int(port))],
                             capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        answer = json.loads(out) if out else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return pick_process(answer if isinstance(answer, dict) else {}, port)


_EXTRA_KEYS = {"text_encoders": ("text_encoders", "clip"), "diffusion_models": ("diffusion_models", "unet")}      # old and new names of a folder


def extra_model_dirs(models_dir: Path, folder: str) -> list[Path]:
    """The extra folders ComfyUI's ``extra_model_paths.yaml`` (next to the ``models`` folder) names for ``folder`` ("loras", "vae" ...),
    so a file kept outside the models folder can be found on disk. A small reader for the usual shape (sections with ``base_path``
    and ``key: path``, a path may be a ``|`` block of several lines); a missing or odd file gives no folders."""
    keys = set(_EXTRA_KEYS.get(folder, (folder,)))
    try:
        text = (Path(models_dir).parent / "extra_model_paths.yaml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    sections: list[dict[str, list[str]]] = []
    key, key_indent, block = "", 0, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent, body = len(line) - len(line.lstrip()), line.strip()
        if indent == 0:
            sections.append({})
            block = False
        elif not sections:
            continue
        elif block and indent > key_indent:                 # a further line of a "|" block: a path (it may hold a colon, "D:\...")
            sections[-1][key].append(body.strip("\"'"))
        elif ":" in body:
            name, _, value = body.partition(":")
            key, key_indent, value = name.strip(), indent, value.strip().strip("\"'")
            block = value[:1] in ("|", ">")
            sections[-1].setdefault(key, [])
            if value and not block:
                sections[-1][key].append(value)
    out: list[Path] = []
    for items in sections:
        base = (items.get("base_path") or [""])[0]
        for k, values in items.items():
            if k in keys:
                for v in values:
                    q = Path(v)
                    if not q.is_absolute() and base:
                        q = Path(base) / v
                    out.append(q)
    return out

