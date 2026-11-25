# tags: start, window
""""Save settings" and "Load defaults" at the bottom of the Advanced settings (user 25.11.; before: right-click on a model
chip, "Set current settings as startup settings", user 30.10.). Saved is only what differs from the PxC standard settings
of the page (model and function), never the prompt, the seed, the variants or the page itself; the window stays exactly as
it was. The saved values are the start values of that page; "Load defaults" brings the standard ones and forgets them.
Stubbed Tk.

    python tests/test_saved_page.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
models = gui.models


def main():
    # the config file
    assert cfgmod.saved_page("fibo", "inpaint") == {}
    cfgmod.set_saved_page("fibo", "inpaint", {"steps": 9})
    assert cfgmod.saved_page("fibo", "inpaint") == {"steps": 9} and cfgmod.saved_page("fibo", "edit") == {}
    cfgmod.set_saved_page("fibo", "inpaint", None)
    assert cfgmod.saved_page("fibo", "inpaint") == {} and cfgmod.get_setting("saved_pages") is None

    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    for rb in app.rb_modes.values():
        rb.grid = lambda *a, **k: None
    app.v_model.set("fibo")
    app.v_mode.set("inpaint")
    app._on_model()
    factory = (app.v_feather.get(), app.v_context.get())

    # change things, save: only the changes; prompt, seed and the page are not part of it
    app.v_feather.set(9.5)
    app.v_context.set(0.7)
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red flower")
    app.v_seed.set(77)
    before = app._collect()
    app.save_settings()
    s = cfgmod.saved_page("fibo", "inpaint")
    assert set(s) == {"feather_pct", "context"}, sorted(s)          # nothing else differs from the standard (user 25.11.)
    assert s["feather_pct"] == 9.5 and abs(s["context"] - 0.7) < 1e-9
    assert app._collect() == before, "the window stays as it was"
    assert app.t_prompt.get("1.0", "end").strip() == "a red flower" and app.v_seed.get() == 77
    assert "Saved 2 changed settings" in app.v_status.get(), app.v_status.get()
    # a value set back to the standard one is no longer kept
    app.v_context.set(factory[1])
    app.save_settings()
    assert cfgmod.saved_page("fibo", "inpaint") == {"feather_pct": 9.5}
    app.v_context.set(0.7)
    app.save_settings()
    # nothing changed at all: nothing kept
    app.v_feather.set(factory[0]); app.v_context.set(factory[1])
    app.save_settings()
    assert cfgmod.saved_page("fibo", "inpaint") == {} and "nothing saved" in app.v_status.get()
    app.v_feather.set(9.5); app.v_context.set(0.7)
    app.save_settings()

    # another function and back: the saved settings are the start values of the page
    app.v_mode.set("edit")
    app._apply_model_mode()
    app.v_feather.set(2.0)                  # something else on the other page
    app.v_mode.set("inpaint")
    app._apply_model_mode()
    assert app.v_feather.get() == 9.5 and abs(app.v_context.get() - 0.7) < 1e-9
    # Reset page brings the saved ones back, not the factory ones
    app.v_feather.set(1.0)
    app.reset_settings()
    assert app.v_feather.get() == 9.5
    # "Load defaults" (bottom of the Advanced settings, user 25.11.; was "Reset page to default" in the hamburger menu): the
    # plugin standard settings AND the saved settings of this page are forgotten
    app.v_feather.set(1.0)
    app.reset_settings(factory=True)
    assert app.v_feather.get() == 10.0 and cfgmod.saved_page("fibo", "inpaint") == {}
    assert "standard settings" in app.v_status.get()
    app.reset_settings()                                # a fresh page
    assert app.v_feather.get() == 10.0                  # nothing saved any more: the standard ones
    # it only touches this model and function
    cfgmod.set_saved_page("fibo", "inpaint", {"feather_pct": 9.5})
    cfgmod.set_saved_page("fibo", "edit", {"steps": 7})
    app.v_feather.set(1.0)
    app.reset_settings(factory=True)
    assert app.v_feather.get() == 10.0 and cfgmod.saved_page("fibo", "inpaint") == {} and cfgmod.saved_page("fibo", "edit") == {"steps": 7}
    cfgmod.set_saved_page("fibo", "edit", None)
    # another model's page is not touched
    assert cfgmod.saved_page("qwen", "inpaint") == {}

    print("ALL OK (saved page)")


if __name__ == "__main__":
    main()
