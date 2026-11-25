# tags: models, comfy
"""P4 (user 24.11., choice D): Generate with a missing file reads ComfyUI's lists again only when ComfyUI is not known to be off,
and at most once per PREFLIGHT_REREAD_S; a full reading (_detect_async: Refresh, ComfyUI back, a download) resets the wait.
No window, no server.

    python tests/test_preflight_reread.py
"""
import os
import queue
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp(prefix="pccomfy-pr-"))
sys.path.insert(0, str(ROOT))

from pccomfy import inventory, ui_settings  # noqa: E402

Mixin = ui_settings.SettingsMixin


def main():
    reads = []
    inventory.fetch = lambda comfy, mapping=None: reads.append(1) or "fresh"
    clock = [100.0]
    ui_settings.time = types.SimpleNamespace(monotonic=lambda: clock[0])
    app = types.SimpleNamespace(comfy=object(), PREFLIGHT_REREAD_S=Mixin.PREFLIGHT_REREAD_S)
    reread = lambda: Mixin._reread_inventory(app)        # noqa: E731

    app._comfy_up = False                                 # the dot says off: no question at all
    assert reread() is None and reads == [], reads
    app._comfy_up = None                                  # not known yet: ask
    assert reread() == "fresh" and len(reads) == 1, reads
    app._comfy_up = True
    clock[0] += 3                                         # clicked again within 10 s: the same answer at once, no question
    assert reread() is None and len(reads) == 1, reads
    clock[0] += Mixin.PREFLIGHT_REREAD_S                  # later: ask again
    assert reread() == "fresh" and len(reads) == 2, reads
    clock[0] += 1

    app._comfy_root_start = lambda: None                  # a full reading resets the wait
    app.events = queue.Queue()
    Mixin._detect_async(app)
    app.events.get(timeout=5)
    assert len(reads) == 3, reads
    assert reread() == "fresh" and len(reads) == 4, reads

    def fail(comfy, mapping=None):                        # a failing question also counts: no second try within 10 s
        reads.append(1)
        raise ui_settings.ComfyError("down")
    inventory.fetch = fail
    clock[0] += Mixin.PREFLIGHT_REREAD_S
    assert reread() is None and len(reads) == 5
    clock[0] += 1
    assert reread() is None and len(reads) == 5
    print("ALL OK (preflight re-read)")


if __name__ == "__main__":
    main()
