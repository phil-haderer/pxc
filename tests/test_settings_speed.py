"""The settings window opens fast: no PowerShell lookup on the Tk thread, no second drawing when nothing changed, the ComfyUI folder and
extra_model_paths.yaml read once per fill, and the text boxes measured only when their width changes (docs/plan/settings-tempo.md 1, 2, 3, 5).

    python tests/test_settings_speed.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_settings_ui as ts  # noqa: E402  (installs the Tk stub)

td, cfgmod = ts.td, ts.cfgmod
from pccomfy import comfydir, inventory, manifest  # noqa: E402


def drain_root(app, limit=5.0):
    """Hand the "comfyroot" event of the lookup thread to the window (what the poll loop does)."""
    end = time.time() + limit
    while time.time() < end:
        try:
            kind, data = app.events.get(timeout=0.2)
        except Exception:
            continue
        if kind == "comfyroot":
            app._comfy_root_done(data)
            return True
    return False


def missing_app():
    """An app whose ComfyUI lists everything but one file per kind plus a stand-in per kind (so the file search has work)."""
    app = ts.make_app()
    lists = td.full_lists()
    for kind in list(lists):
        if lists[kind]:
            lists[kind].pop()
            lists[kind].append(f"sub\\other_{kind}_model_fp8.safetensors")
    app.inv = inventory.Inventory(lists, ts.NODES)
    return app


def test_root_lookup_in_background():
    os.environ.pop("PCCOMFY_MODELS_DIR", None)
    base = Path(tempfile.mkdtemp())
    (base / "ComfyUI" / "models").mkdir(parents=True)
    (base / "ComfyUI" / "main.py").write_text("", encoding="utf-8")
    calls = []
    real = comfydir.find_root
    comfydir.find_root = lambda url, timeout=10.0: calls.append(threading.current_thread()) or (base / "ComfyUI")
    try:
        app = missing_app()
        app._comfy_root = None
        app.events.queue.clear() if hasattr(app.events, "queue") else None
        main = threading.current_thread()
        app.open_settings()                                  # fills the rows: _settings_rows -> _dl_done -> models_dir
        assert app._settings_win is not None
        assert app.models_dir(ask=False) is None             # not known yet: the same as "no folder known"
        assert drain_root(app), "the lookup thread never answered"
        assert calls and all(c is not main for c in calls), "find_root ran on the Tk thread"
        assert len(calls) == 1, calls                        # once, not once per call
        assert app._comfy_root == base / "ComfyUI" and app.models_dir(ask=False) == base / "ComfyUI" / "models"
        # a changed address forgets the folder and looks again in the background; an answer of the old address is dropped
        n = len(calls)
        app._comfy_root_reset()
        assert app._comfy_root is None and app._comfy_root_busy
        app._comfy_root_done((app._comfy_root_seq - 1, "http://old", Path("old")))
        assert app._comfy_root is None
        assert drain_root(app) and len(calls) == n + 1 and calls[-1] is not main
        # a click that needs the folder now (download) may still wait for it
        app._comfy_root = None
        app._comfy_root_busy = False
        assert app.models_dir(ask=True) == base / "ComfyUI" / "models" and calls[-1] is main
        app._settings_close()
    finally:
        comfydir.find_root = real


def test_fill_once():
    os.environ["PCCOMFY_MODELS_DIR"] = tempfile.mkdtemp()
    try:
        app = missing_app()
        now, extra = [], []
        orig_now, orig_extra = app._models_dir_now, comfydir.extra_model_dirs
        app._models_dir_now = lambda ask: now.append(ask) or orig_now(ask)
        comfydir.extra_model_dirs = lambda base, folder: extra.append((str(base), folder)) or orig_extra(base, folder)
        try:
            rows = app._settings_rows()
        finally:
            comfydir.extra_model_dirs = orig_extra
        assert any(r[0] == "file" and r[1]["found"] is None for r in rows)
        assert len(now) == 1, f"models_dir worked out {len(now)} times in one fill"
        assert extra and len(extra) == len(set(extra)), f"extra_model_paths.yaml read twice for one folder: {extra}"
        assert app._fill_ctx is None
        assert app._settings_rows() == rows                  # same rows as before (also with a cold cache)
        # outside a fill nothing is cached: a file that appears is seen
        f = next(g for g in manifest.FILES.values() if g.kind == "vae")
        assert app._disk_file(f, "x.safetensors") is None
        d = Path(os.environ["PCCOMFY_MODELS_DIR"]) / f.folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "x.safetensors").write_text("a", encoding="utf-8")
        assert app._disk_file(f, "x.safetensors") == d / "x.safetensors"
    finally:
        del os.environ["PCCOMFY_MODELS_DIR"]


def test_second_fill_skipped():
    app = ts.make_app()
    app.inv = inventory.Inventory(td.full_lists(), ts.NODES)
    app.open_settings()
    draws = []
    orig = app._settings_draw
    app._settings_draw = lambda rows: draws.append(1) or orig(rows)
    app._set_inventory(app.inv, "")                          # what _detect_async brings back: same lists
    app._settings_fill()
    assert draws == [], "the same rows were drawn again"
    # a change that shows (a file gone) draws once
    lists = td.full_lists()
    lists["vae"].pop()
    app._set_inventory(inventory.Inventory(lists, ts.NODES), "")
    assert draws == [1]
    app._settings_fill()
    assert draws == [1]
    # a download that runs changes the rows: drawn
    name = next(g.name for g in manifest.FILES.values() if g.name not in lists["vae"] and g.kind == "vae")
    app._dl[name] = {"file": None, "target": None, "done": 1, "total": 2, "phase": "loading", "cancel": None}
    app._settings_fill()
    assert draws == [1, 1]
    del app._dl[name]
    # a new window is always drawn, even with the same rows
    app._settings_close()
    app.open_settings()
    draws.clear()
    app._settings_draw = lambda rows: draws.append(1) or orig(rows)
    app._drawn = None
    app._settings_fill()
    assert draws == [1]
    app._settings_close()


class FakeText:
    def __init__(self, lines):
        self.lines, self.h, self.counted = lines, 1, 0

    def count(self, a, b, kind):
        self.counted += 1
        return (self.lines,)

    def cget(self, k):
        return self.h

    def configure(self, **k):
        self.h = k["height"]


def test_fit_text_guard():
    app = ts.make_app()
    t = FakeText(3)
    app._fit_text(t, 400)
    assert t.h == 3 and t.counted == 1
    app._fit_text(t, 400)                    # the Configure caused by its own new height: same width, not measured again
    assert t.counted == 1
    t.lines = 5
    app._fit_text(t, 300)                    # a new width is measured
    assert t.h == 5 and t.counted == 2
    t.lines = 2
    app._fit_text(t)                         # no width given: always measured
    assert t.h == 2 and t.counted == 3


def main():
    test_root_lookup_in_background()
    test_fill_once()
    test_second_fill_skipped()
    test_fit_text_guard()
    print("ok")


if __name__ == "__main__":
    main()
