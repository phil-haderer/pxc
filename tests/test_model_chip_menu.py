# tags: window, start, models
"""Right-click menu on the model chip (L3, user 29.10.; since 20.11. one model chip with a list): save the settings and
"Hide this model". A hidden model leaves the list, the others keep their order; hiding the chosen model chooses another one;
a function whose models are all hidden is greyed out.

    python tests/test_model_chip_menu.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
models = gui.models


class Menu:
    def __init__(self):
        self.items = []

    def delete(self, *a):
        self.items = []

    def add_checkbutton(self, **k):
        self.items.append(("check", k))

    def add_command(self, **k):
        self.items.append(("command", k))

    def add_separator(self):
        self.items.append(("sep", {}))

    def tk_popup(self, *a):
        pass

    def grab_release(self):
        pass


class Ev:
    x_root = y_root = 10


def chips(app):
    """The models in the model chip's list, in their order; a hidden one is not there."""
    return [key for key, item in app.rb_tabs.items() if item.shown]


def main():
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.m_chip = Menu()
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    app._update_mode_radios()
    assert len(chips(app)) == len(models.MODELS), chips(app)

    # the menu: save settings (chosen model only), hide (the favourite was removed 12.11.)
    app._chip_menu("fibo", Ev())
    assert [(kind, it.get("label")) for kind, it in app.m_chip.items] == [        # Fibo is not the chosen model: no "Set current settings ..." (user 1.11.)
        ("command", "Hide this model")]
    app._chip_menu(app.v_model.get(), Ev())                # the chosen model offers it
    assert [(k, it.get("label")) for k, it in app.m_chip.items][1:] == [
        ("command", "Reset to PxC standard settings (for this mode and model)"), ("sep", None), ("command", "Hide this model")]
    assert app.m_chip.items[0] == ("command", app.m_chip.items[0][1]) and app.m_chip.items[0][1]["label"] == "Set current settings as startup settings (for this mode and model)"   # renamed 12.11.

    # the function opens with the model last used for it (no favourite any more)
    app._mode_model["inpaint"] = "qwen"
    assert app._model_for_mode("inpaint") == "qwen"
    cfgmod.set_setting("favorites", {"inpaint": "fibo"})   # an old favourites key in settings.json is ignored
    assert app._model_for_mode("inpaint") == "qwen"
    cfgmod.set_setting("favorites", None)

    # hide a model that is not chosen: it leaves the list, the others keep their order
    app._set_model_hidden("flux2", True)
    assert cfgmod.hidden_tabs() == {"flux2"} and "flux2" not in chips(app)
    assert chips(app) == [m.key for m in models.MODELS if m.key != "flux2"]
    assert app.v_model.get() == "qwen"

    # hide the chosen model: another one that can fill is chosen, the function stays (Flux 3 hidden too: it can fill
    # since 11.11. and would come first)
    app._set_model_hidden("flux3", True)
    app._set_model_hidden("qwen", True)
    assert app.v_model.get() == "fibo" and app.v_mode.get() == "inpaint", (app.v_model.get(), app.v_mode.get())
    assert app._model_for_mode("inpaint") == "fibo"

    # every model that can fill hidden: Fill is greyed out, the chosen model goes to one still shown
    app._set_model_hidden("fibo", True)
    left = [m for m in models.MODELS if m.key not in cfgmod.hidden_tabs()]
    if not any("inpaint" in m.modes for m in left):
        assert app.rb_modes["inpaint"].cget("state") == "disabled"
        assert app._model_for_mode("inpaint") == ""
    assert app.v_model.get() in {m.key for m in left}

    # shown again (the gear window): back in its place, the function too
    for k in ("flux3", "flux2", "qwen", "fibo"):
        app._set_model_hidden(k, False)
    assert cfgmod.hidden_tabs() == set() and len(chips(app)) == len(models.MODELS)
    assert app.rb_modes["inpaint"].cget("state") == "normal"

    # the gear window, tab "Models": one tick per model, all ticked after installing; unticking hides, ticking shows
    app.open_settings()
    assert list(app._shown_vars) == [m.key for m in models.MODELS] and all(v.get() for v in app._shown_vars.values())
    app._shown_vars["krea2"].set(False)
    app._set_model_hidden("krea2", not app._shown_vars["krea2"].get())     # what the tick's command does
    assert cfgmod.hidden_tabs() == {"krea2"} and "krea2" not in chips(app)
    app._set_model_hidden("moss", True)                   # the right-click menu: the gear window follows
    assert app._shown_vars["moss"].get() is False
    app._shown_vars["krea2"].set(True)
    app._set_model_hidden("krea2", False)
    app._set_model_hidden("moss", False)
    assert cfgmod.hidden_tabs() == set() and all(v.get() for v in app._shown_vars.values())
    app._settings_close()

    # every model hidden: none is chosen
    for m in models.MODELS:
        app._set_model_hidden(m.key, True)
    assert app.v_model.get() == "" and chips(app) == []
    for m in models.MODELS:
        app._set_model_hidden(m.key, False)
    print("test_model_chip_menu: ok")


if __name__ == "__main__":
    main()
