# tags: expand, window
"""Expand has no "Original size, up to" row (user 13.11.): fixed cap 1 MP, Flux 3 Expand 2 MP; a saved value never counts.
The row stays in the other functions.

    python tests/test_expand_fixed_size.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
from pccomfy import gui_common, models  # noqa: E402


def rec(widget, name):
    calls = []
    setattr(widget, name, lambda *a, **k: calls.append((name, k)))
    return calls


def main():
    assert gui_common.expand_mp("qwen") == 1.0 and gui_common.expand_mp("fibo") == 1.0 and gui_common.expand_mp("flux2") == 1.0
    assert gui_common.expand_mp("flux3") == 2.0 and gui_common.expand_mp("") == 1.0
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names

    def pick(key, mode):
        app.v_model.set(key)
        app.v_mode.set(mode)
        app._on_model()

    hidden = rec(app.f_native, "pack_forget")
    for key in ("qwen", "flux2", "flux3", "fibo"):
        if "outpaint" not in models.BY_KEY[key].modes:
            continue
        hidden.clear()
        pick(key, "outpaint")
        assert hidden, (key, "row must be hidden in Expand")
        want = 2.0 if key == "flux3" else 1.0
        app.v_native_mp.set(4.0)                   # a stale saved value in the variable ...
        app.v_native.set(False)
        req = app._request()
        assert req.native_mp == want and req.native is True, (key, req.native_mp, req.native)
        app._apply_settings({"mode": "outpaint", "native": False, "native_mp": 3.5})     # ... or in My settings / saved state
        req = app._request()
        assert req.native_mp == want and req.native is True, (key, req.native_mp)
        app._save_state(req)
        assert cfgmod.load_state().get("native_mp") == want, key
    for key, mode in (("qwen", "edit"), ("qwen", "inpaint"), ("qwen", "remove"), ("fibo", "edit")):   # the others keep the row (Flux 3 has none since 13.11., 1a)
        hidden.clear()
        pick(key, mode)
        assert not hidden, (key, mode, "row must stay")
        app.v_native_mp.set(3.0)
        assert app._request().native_mp == 3.0, (key, mode)
    for mode in ("edit", "inpaint", "remove"):    # Flux 3: no row and "Original size" never sent (user 13.11., 1a)
        hidden.clear()
        pick("flux3", mode)
        app.v_native.set(True)
        assert hidden and app._request().native is False, ("flux3", mode)
    print("ok")


main()
