"""Shared detection of "a test script started by hand" (`python tests/<name>.py`), used by the two guards that keep a test
away from the user's real things: comfy.real_comfy_blocked (port 8188) and config (the real data/ folder, see isolate_home).
Imports nothing heavy, so config.py can use it. The real app never runs a script from a folder called tests."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


_seen_test_code = False      # once test code was seen on the stack, the whole process counts as a test (worker threads too)


def _is_test_file(name) -> bool:
    try:
        p = Path(name).resolve()
    except (OSError, ValueError, TypeError):
        return False
    return p.parent.name == "tests" and p.suffix == ".py" and not p.name.startswith("live_")


def is_test_script() -> bool:
    """True when the main script lives in a folder named `tests` and is not a manual `live_*.py` check, or when code from such
    a file is on the call stack: a helper script elsewhere that runs a test (runpy, import) is a test too. On 14.11.2026 two
    helper scripts in the scratchpad ran tests/test_batch_gui.py through runpy; argv[0] was not in tests/, so they used the
    real data/ folder and overwrote settings.json and state.json. Once seen, it stays True for the process."""
    global _seen_test_code
    if _seen_test_code:
        return True
    try:
        main = sys.argv[0]
    except IndexError:
        main = ""
    if _is_test_file(main):
        _seen_test_code = True
        return True
    if Path(main).name.startswith("live_"):       # a manual live check started directly: its helpers in tests/ are not tests
        return False
    f = sys._getframe(1)
    while f is not None:
        if _is_test_file(f.f_code.co_filename):
            _seen_test_code = True
            return True
        f = f.f_back
    return False


def isolate_home() -> None:
    """Called by config before its paths are computed. A test script without PCCOMFY_HOME gets a fresh throw-away folder
    (so a hand run never reads or overwrites the real data/: settings, state, queue). Not for live_*.py (they read the real
    config.toml on purpose, e.g. the ComfyUI address), not for the normal app start; PCCOMFY_ALLOW_REAL_HOME=1 lifts it.
    The runner (tests/run_all.py) already sets its own folder, which wins."""
    if os.environ.get("PCCOMFY_HOME") or os.environ.get("PCCOMFY_ALLOW_REAL_HOME") or not is_test_script():
        return
    os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-test-home-")
