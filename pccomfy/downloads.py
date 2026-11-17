"""Downloads of model files (standard library only; no Tk here).

``download`` writes to ``<target>.part`` and renames it only after the size and the SHA-256 of the manifest match. A stopped or
interrupted download goes on where it ended (HTTP Range); a cancel keeps the ``.part`` file for that. A Hugging Face token is
sent only to huggingface.co and dropped when a redirect leaves the host (the files come from a CDN).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

CHUNK = 1 << 20
SPACE_MARGIN = 100 * 1_000_000          # bytes that stay free besides the file itself
TOKEN_HOSTS = ("huggingface.co",)


class DownloadError(Exception):
    """The message is meant for the status line."""


class Cancelled(DownloadError):
    """The user stopped the download; the ``.part`` file stays for a later resume."""


def target_for(models_dir: str | Path, f) -> Path:
    """Where a manifest file goes: ``<models>/<folder>/<name>``, a LoRA's sub-folder included."""
    base = Path(models_dir).resolve()
    path = (base / f.folder / f.name.replace("\\", "/")).resolve()
    if base not in path.parents:
        raise DownloadError(f"Refusing a target outside the models folder: {f.name}")
    return path


def free_space(path: str | Path) -> int:
    """Free bytes on the drive of ``path`` (it need not exist yet)."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


def _host_ok(url: str, hosts: tuple) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Follows redirects, but the token goes only to the hosts that may have it."""

    def __init__(self, hosts: tuple):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _host_ok(newurl, self.hosts):
            for h in ("Authorization", "authorization"):
                new.headers.pop(h, None)
                new.unredirected_hdrs.pop(h, None)
        return new


def _sha256(path: Path, progress: Callable | None, cancel: Callable | None) -> str:
    h, done, total = hashlib.sha256(), 0, path.stat().st_size
    with open(path, "rb") as fh:
        while True:
            if cancel is not None and cancel():
                raise Cancelled("Cancelled.")
            block = fh.read(CHUNK)
            if not block:
                return h.hexdigest()
            h.update(block)
            done += len(block)
            if progress is not None:
                progress(done, total, "verifying")


CHECK_STATES = ("ok", "damaged", "missing", "unknown")      # the result of a file in "Check files" (user 17.11.)


def check_files(entries: list, progress: Callable[[int, int, str], None] | None = None,
                cancel: Callable[[], bool] | None = None) -> list[dict]:
    """"Check files" of the settings window (user 17.11.): each entry is {"name", "path" (Path or None = not on the disk),
    "sha256" (of models.json, "" = none known), "size" (0 = unknown), "note" (why no checksum applies, optional)}.
    Returns one dict per entry with "state" (CHECK_STATES) and "text". A file whose size already differs is damaged without
    hashing it; a file without a known checksum is not read at all. ``progress(done, total, name)`` counts bytes over all files
    to hash; ``cancel()`` returning True stops it (Cancelled). Reads only: no file is ever changed or deleted here."""
    todo = []
    for e in entries:
        p = e.get("path")
        try:
            todo.append((e, p.stat().st_size if (p is not None and e.get("sha256")) else 0))
        except OSError:
            todo.append((e, 0))
    total = sum(n for _e, n in todo if not (_e.get("size") and n != _e["size"]))
    done, out = 0, []
    for e, n in todo:
        name, p, want = e["name"], e.get("path"), (e.get("sha256") or "").lower()
        if e.get("note") and not want:         # the user's own file (linked): ComfyUI has it, its checksum is not known
            out.append({"name": name, "path": p, "state": "unknown", "text": e["note"]})
            continue
        if p is None or not Path(p).is_file():
            out.append({"name": name, "path": p, "state": "missing", "text": "missing"})
            continue
        if not want:
            out.append({"name": name, "path": p, "state": "unknown",
                        "text": e.get("note") or "no checksum known, not checked"})
            continue
        if e.get("size") and n != e["size"]:
            out.append({"name": name, "path": p, "state": "damaged",
                        "text": f"damaged: {n:,} bytes instead of {e['size']:,}".replace(",", ".")})
            continue
        base = done

        def step(d, _t, _phase, base=base, name=name):
            if progress is not None:
                progress(base + d, total, name)
        got = _sha256(Path(p), step, cancel).lower()
        done = base + n
        out.append({"name": name, "path": p, "state": "ok" if got == want else "damaged",
                    "text": "ok" if got == want else "damaged: the checksum does not match"})
    return out


def _http_message(e: urllib.error.HTTPError) -> str:
    if e.code in (401, 403):
        return "The server wants a login or a licence you have not accepted yet (HTTP %d)." % e.code
    if e.code == 404:
        return "The file is not at this address any more (HTTP 404)."
    return "The server answered HTTP %d." % e.code


def download(url: str, dest: str | Path, size: int = 0, sha256: str = "", token: str = "",
             progress: Callable[[int, int, str], None] | None = None, cancel: Callable[[], bool] | None = None,
             token_hosts: tuple = TOKEN_HOSTS, timeout: float = 30.0) -> Path:
    """Fetch ``url`` to ``dest``. ``progress(done, total, phase)`` with phase "downloading" or "verifying" (total 0 = unknown);
    ``cancel()`` returning True stops it (Cancelled). Returns ``dest``; a file that is already there is left alone."""
    dest = Path(dest)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if size and have > size:
        part.unlink()
        have = 0
    need = max(size - have, 0)
    if need + SPACE_MARGIN > free_space(dest.parent):
        raise DownloadError(f"Not enough free space: {need / 1e9:.1f} GB needed on this drive, "
                            f"{free_space(dest.parent) / 1e9:.1f} GB free.")
    headers = {"User-Agent": "photocraft-comfyui-bridge"}
    if token and _host_ok(url, token_hosts):
        headers["Authorization"] = "Bearer " + token
    if have:
        headers["Range"] = f"bytes={have}-"
    opener = urllib.request.build_opener(_Redirects(token_hosts))
    try:
        resp = opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have and (not size or have == size):      # the part file is already complete
            resp = None
        else:
            if e.code == 416:
                part.unlink(missing_ok=True)
            raise DownloadError(_http_message(e)) from e
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise DownloadError("The secure connection could not be verified (certificate of "
                                f"{urllib.parse.urlsplit(url).hostname}). Open the page in your browser instead.") from e
        raise DownloadError("No connection to the server: " + str(reason)) from e
    if resp is not None:
        with resp:
            resume = resp.status == 206 and have > 0
            if not resume:
                have = 0                          # the server sent the whole file again
            length = int(resp.headers.get("Content-Length") or 0)
            total = have + length if length else size
            if not resume and length and length + SPACE_MARGIN > free_space(dest.parent):
                raise DownloadError(f"Not enough free space: {length / 1e9:.1f} GB needed on this drive.")
            done = have
            try:
                with open(part, "ab" if resume else "wb") as fh:
                    while True:
                        if cancel is not None and cancel():
                            raise Cancelled("Cancelled. The part that is loaded stays for a later resume.")
                        block = resp.read(CHUNK)
                        if not block:
                            break
                        fh.write(block)
                        done += len(block)
                        if progress is not None:
                            progress(done, total, "downloading")
            except (urllib.error.URLError, OSError, ConnectionError) as e:
                raise DownloadError("The connection broke off; start again to go on where it stopped.") from e
    got = part.stat().st_size
    if size and got != size:
        if got > size:
            part.unlink()
        raise DownloadError(f"Incomplete: {got} of {size} bytes; start again to go on where it stopped.")
    if sha256 and _sha256(part, progress, cancel).lower() != sha256.lower():
        part.unlink()
        raise DownloadError("The checksum does not match: the file was damaged and is deleted. Start again.")
    os.replace(part, dest)
    return dest
