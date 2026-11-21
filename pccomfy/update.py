"""Is a newer PxC out? (docs/plan/update.md, user 19.11.: A1 + A2, H2, B1 first, B3 too). No Tk here.

A1: at the start, at most once a day (`due`), in the background; A2: the button "Check now" in Other settings. Both ask the
GitHub releases of the public repo (`RELEASES_API`) for the latest release; GitHub sees the IP address and the user agent
"PxC/<version>", nothing else. The tick "Check for updates" (Other settings, ticked from the factory) switches A1 off.
B1: the line in Other settings opens the release page; the steps stand under it. B3: a folder from `git clone` of the public
repo is updated with `git pull --ff-only` (`git_update`); never in any other git folder (the private working repo).

A test script never reaches GitHub (`fetch_latest` refuses the real address under testguard); tests start their own server."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__, appinfo, testguard

REPO = "phil-haderer/pxc"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_S = 5
DAY_S = 24 * 3600
START_DELAY_MS = 8000        # the start check waits until the window has settled
ROOT = Path(__file__).resolve().parent.parent

# keys in settings.json (config.get_setting / set_setting)
KEY_OFF = "update_check_off"        # True = the tick "Check for updates" is off (absent = on, the factory setting)
KEY_SKIP = "update_skip"            # the version the user skipped ("Skip this version")
# keys in state.json
KEY_LAST = "update_last_check"      # time.time() of the last automatic check
KEY_FOUND = "update_found"          # the last newer release found: {"version", "url"} (the blue dot survives a restart)

UPDATE_STEPS = {
    "zip": "To update: download the ZIP on the release page, unpack it over this folder, run setup-windows.bat again "
           "(Linux: ./setup-linux.sh) and restart PxC. Your settings stay.",
    "git": "Update now runs git pull in this folder; then restart PxC.",
}


class UpdateError(RuntimeError):
    pass


@dataclass
class Release:
    version: str        # "1.0.7" (the tag without "v")
    url: str            # the release page
    notes: str = ""     # the release text (the CHANGELOG entry)


def fetch_latest(url: str = RELEASES_API, timeout: float = TIMEOUT_S) -> Release:
    """The latest published release (drafts and pre-releases are not returned by GitHub's /releases/latest)."""
    if url == RELEASES_API and testguard.is_test_script() and not os.environ.get("PCCOMFY_ALLOW_UPDATE_CHECK"):
        raise UpdateError("Blocked: a test must not ask GitHub.")
    req = urllib.request.Request(url, headers={"User-Agent": f"PxC/{__version__}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise UpdateError(f"GitHub answered {e.code}.") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise UpdateError("No connection to GitHub.") from None
    except ValueError:
        raise UpdateError("GitHub sent an answer PxC cannot read.") from None
    tag = str(data.get("tag_name") or "") if isinstance(data, dict) else ""
    if not appinfo.parse_version(tag):
        raise UpdateError("GitHub sent no version number.")
    return Release(tag[1:] if tag[:1] in "vV" else tag, str(data.get("html_url") or RELEASES_PAGE), str(data.get("body") or ""))


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = appinfo.parse_version(latest), appinfo.parse_version(current)
    return bool(a and b and a > b)


def is_dev(version: str | None = None) -> bool:
    """The working folder (its version ends in "-dev"; a release export always writes the tag's version): no check at the
    start and no blue dot from a release found earlier (user 21.11.); "Check now" by hand still asks."""
    return str(__version__ if version is None else version).strip().lower().endswith("-dev")


def due(last, now: float | None = None) -> bool:
    """The start check runs when the last one is a day old (or there was none, or the clock went back)."""
    now = time.time() if now is None else now
    try:
        last = float(last)
    except (TypeError, ValueError):
        return True
    return now - last >= DAY_S or now < last


def to_show(found, skipped: str = "", current: str = __version__):
    """The release to announce (dict {"version", "url"}) or None: newer than this one and not skipped."""
    if not isinstance(found, dict) or not is_newer(str(found.get("version", "")), current):
        return None
    if skipped and str(skipped) == str(found.get("version")):
        return None
    return found


# ---------- B3: a folder from git clone ----------

def _git(root: Path, *args, timeout: float = 60) -> subprocess.CompletedProcess:
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}       # CREATE_NO_WINDOW: no console flashes up
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout, **kw)


def install_kind(root: Path = ROOT) -> str:
    """"git" for a clone of the public repo on its main branch with git on PATH, else "zip" (B1: the release page)."""
    if not (root / ".git").exists() or not shutil.which("git"):
        return "zip"
    try:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=10).stdout.strip()
        remote = _git(root, "config", "--get", f"branch.{branch}.remote", timeout=10).stdout.strip()
        url = _git(root, "remote", "get-url", remote, timeout=10).stdout.strip() if remote else ""
    except (OSError, subprocess.SubprocessError):
        return "zip"
    return "git" if branch == "main" and is_public_repo_url(url) else "zip"


def is_public_repo_url(url: str) -> bool:
    """https://github.com/phil-haderer/pxc(.git) or git@github.com:phil-haderer/pxc(.git); not pxc-dev or pxc-test."""
    m = re.match(r"^(?:https?://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?$",
                 str(url or "").strip(), re.I)
    return bool(m) and f"{m.group(1)}/{m.group(2)}".lower() == REPO


def git_update(root: Path = ROOT) -> tuple[bool, str]:
    """git pull --ff-only in a clone of the public repo. Refuses (changes nothing) when files were changed in the folder.
    Returns (ok, text for the window); the text says when the setup must run again (requirements.txt changed)."""
    if install_kind(root) != "git":
        return False, "This folder is not a git clone of PxC; use the release page."
    try:
        dirty = _git(root, "status", "--porcelain", "--untracked-files=no", timeout=20).stdout.strip()
        if dirty:
            return False, "Files in the PxC folder were changed, so git pull was not run. Use the release page instead."
        before = _git(root, "rev-parse", "HEAD", timeout=10).stdout.strip()
        r = _git(root, "pull", "--ff-only", timeout=120)
        if r.returncode != 0:
            return False, "git pull failed: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1][:200]
        after = _git(root, "rev-parse", "HEAD", timeout=10).stdout.strip()
        if before == after:
            return True, "Already up to date."
        changed = _git(root, "diff", "--name-only", before, after, timeout=20).stdout.split()
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"git could not run ({type(e).__name__})."
    setup = "setup-windows.bat" if os.name == "nt" else "./setup-linux.sh"
    if "requirements.txt" in changed:
        return True, f"Updated. Run {setup} again, then restart PxC."
    return True, "Updated. Restart PxC to use the new version."
