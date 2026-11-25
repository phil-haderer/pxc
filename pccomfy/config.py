"""Configuration: ~/.config/pccomfy/config.toml (every field optional)."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

from . import __version__ as APP_VERSION
from .hostos import IS_WINDOWS
from .testguard import dead_port_fails_fast, isolate_home

if sys.version_info >= (3, 11):
    import tomllib
else:      # Ubuntu 22.04 and Mint 21 ship Python 3.10: tomli is the same reader (setup-linux.sh installs it)
    import tomli as tomllib

_ROOT = Path(__file__).resolve().parent.parent


def _config_dir() -> Path:
    """PCCOMFY_HOME wins (a test script started by hand gets a throw-away one: testguard.isolate_home). On Windows everything
    lives in <bridge folder>\\data (portable, like PhotoCraft)."""
    isolate_home()
    dead_port_fails_fast()
    env = os.environ.get("PCCOMFY_HOME")
    if env:
        return Path(env).expanduser()
    if IS_WINDOWS:
        return _ROOT / "data"
    return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "pccomfy"


CONFIG_DIR = _config_dir()
# The workflows shipped next to the code, on every system (the Linux default used to be ~/.config/pccomfy/workflows, which
# nobody filled: no workflow was found). Your own ones: workflows_dir in config.toml.
WORKFLOWS_DIR = _ROOT / "workflows"
EXCHANGE_DIR = CONFIG_DIR / "exchange" if IS_WINDOWS else Path("~/.cache/pccomfy/exchange").expanduser()     # a "~" left in it made a folder "~" in the working directory (Linux VM 4.11.)
CONFIG_FILE = CONFIG_DIR / "config.toml"
STATE_FILE = CONFIG_DIR / "state.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"     # what the settings overlay and the tab menu save (model map, favourites ...)
HISTORY_FILE = CONFIG_DIR / "history.json"       # the last 20 runs (the clock in the header, history.py)


def effective_workflows_dir(configured) -> tuple[Path, str]:
    """(folder, note). A folder from config.toml that has none of the plugin's own workflows (an old config.toml with the former
    Linux default ~/.config/pccomfy/workflows, or a folder that is gone) would leave every model without its workflow, and the
    window fell back to the built-in SD1.5 graph (tester 7.11.). Then the shipped folder is used and the note says why."""
    p = Path(configured).expanduser()
    try:
        if p.resolve() == WORKFLOWS_DIR.resolve():
            return p, ""
        shipped = {f.name for f in WORKFLOWS_DIR.glob("*.json")}
        have = {f.name for f in p.glob("*.json")} if p.is_dir() else set()
    except OSError:
        return p, ""
    if shipped and not (shipped & have):
        return WORKFLOWS_DIR, (f"The workflows folder in config.toml ({p}) has none of PxC's workflows, so PxC's own "
                               f"folder is used. Remove workflows_dir from {CONFIG_FILE} to hide this note.")
    return p, ""

DEFAULTS = {
    "photocraft": {
        "host": "127.0.0.1",
        "port": 7878,
        "token_file": str(CONFIG_DIR / "photocraft.token"),
        "exchange_dir": str(EXCHANGE_DIR),
        "headless": False,
    },
    "comfyui": {
        "url": "http://127.0.0.1:8188",
        "workflows_dir": str(WORKFLOWS_DIR),
    },
    "defaults": {
        "checkpoint": "",
        "negative": "",
        "steps": 25,
        "cfg": 6.0,
        "sampler": "dpmpp_2m",
        "scheduler": "karras",
        "denoise": 0.6,
        "base_res": 1024,
        "context": 0.4,
        "mask_grow": 8,
        "mask_blur": 8,
        "overlap": 48,
        "variants": 1,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None = None) -> dict:
    p = Path(path).expanduser() if path else CONFIG_FILE
    cfg = DEFAULTS
    if p.exists():
        with open(p, "rb") as f:
            cfg = _merge(DEFAULTS, tomllib.load(f))
    return cfg


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_WRITE_ERROR = ""       # the last failed write of a config file ("<file>: <reason>"), "" while all went well


def write_error() -> str:
    """The last failed write of state.json / settings.json (read-only folder, full disk, ...), else ""; shown at the start and in the report."""
    return _WRITE_ERROR


def _write_json(path: Path, data: dict) -> bool:
    """Writes a config file with the plugin's version in it ("_version"); a failure is remembered, not raised."""
    global _WRITE_ERROR
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({**data, "_version": APP_VERSION}, indent=2, ensure_ascii=False)
        _JSON_CACHE.pop(str(path), None)
        path.write_text(text, encoding="utf-8")
        _remember(path, text)
        _WRITE_ERROR = ""
        return True
    except OSError as e:
        _WRITE_ERROR = f"{path} ({e.strerror or type(e).__name__})"
        return False


def save_state(state: dict) -> None:
    _write_json(STATE_FILE, state)


# ---------- settings of the settings overlay (data/settings.json, separate from the window state) ----------

_JSON_CACHE: dict[str, tuple[int, int, str]] = {}      # path -> (mtime_ns, size, text) of a config file


def _remember(path: Path, text: str) -> None:
    try:
        st = path.stat()
        _JSON_CACHE[str(path)] = (st.st_mtime_ns, st.st_size, text)
    except OSError:
        _JSON_CACHE.pop(str(path), None)


def _read_cached(path: Path) -> str:
    """The text of a config file, read from disk only when its time or size changed or this module wrote it (tempo plan P2,
    24.11.: settings.json was read 74 times for ten function switches). Raises OSError like read_text."""
    st = path.stat()
    hit = _JSON_CACHE.get(str(path))
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    text = path.read_text(encoding="utf-8")
    _JSON_CACHE[str(path)] = (st.st_mtime_ns, st.st_size, text)
    return text


def load_settings() -> dict:
    try:
        d = json.loads(_read_cached(SETTINGS_FILE))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    _write_json(SETTINGS_FILE, settings)


def check_version() -> str:
    """At the start: compares the version the config files were last written by with the running one (appinfo.version_change),
    stamps the running one in and returns the sentence for the status line ("" when there is nothing to say). A folder that
    cannot be written says so here (it would otherwise lose every setting without a word)."""
    from . import appinfo
    s = load_settings()
    had = SETTINGS_FILE.exists() or STATE_FILE.exists()
    _kind, text = appinfo.version_change(s.get("_version"), APP_VERSION, had)
    if s.get("_version") != APP_VERSION:
        if not _write_json(SETTINGS_FILE, {k: v for k, v in s.items() if k != "_version"}):
            text = f"{text} Settings could not be saved: {_WRITE_ERROR}.".strip()
    return text


def get_setting(key: str, default=None):
    return load_settings().get(key, default)


def set_setting(key: str, value) -> None:
    s = load_settings()
    if value is None:
        s.pop(key, None)
    else:
        s[key] = value
    save_settings(s)


def model_map() -> dict:
    """The user's own file links: the file name the plugin expects -> the file name ComfyUI lists for it."""
    m = get_setting("model_map", {})
    return {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}


def set_model_link(expected: str, local: str | None) -> None:
    """Link ``expected`` to ``local``; an empty ``local`` removes the link."""
    m = model_map()
    if local:
        m[expected] = local
    else:
        m.pop(expected, None)
    set_setting("model_map", m or None)


def set_model_map(m: dict) -> None:
    """Replace all links at once (Undo / Reset in the settings window)."""
    set_setting("model_map", dict(m) or None)


# Hidden tabs: the right-click menu (lane L3) reads and writes them only through these. (The model favourite was removed
# 12.11. by the user; an old "favorites" key in settings.json is simply ignored.)


# Saved page settings: "Save settings" at the bottom of the Advanced settings (user 25.11.; before: the right-click menu on a model chip).

def saved_page(model: str, mode: str) -> dict:
    """The settings the user saved for this model and function ({} = none); they replace the starting settings."""
    s = get_setting("saved_pages", {})
    page = s.get(f"{model}|{mode}") if isinstance(s, dict) else None
    return dict(page) if isinstance(page, dict) else {}


def set_saved_page(model: str, mode: str, settings: dict | None) -> None:
    s = get_setting("saved_pages", {})
    s = dict(s) if isinstance(s, dict) else {}
    if settings:
        s[f"{model}|{mode}"] = settings
    else:
        s.pop(f"{model}|{mode}", None)
    set_setting("saved_pages", s or None)


def hidden_tabs() -> set:
    h = get_setting("hidden_tabs", [])
    return {str(x) for x in h} if isinstance(h, list) else set()


def set_tab_hidden(tab: str, hidden: bool) -> None:
    h = hidden_tabs()
    (h.add if hidden else h.discard)(tab)
    set_setting("hidden_tabs", sorted(h) or None)
