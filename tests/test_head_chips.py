# tags: window
"""The head has two chips with a list since 20.11. (user): the function chip on the left (symbol, name, arrow), the model chip
right beside it; grey like the former function buttons, each as wide as its longest entry, so neither changes its width.
The function list has the order of the former buttons, the model list the order of the former chips; a model that cannot do
the chosen function is greyed out in its place, a hidden one is not listed, one with missing files is red. A right-click on
the model chip opens the settings menu of the chosen model. Both chips fit at the narrow window width MIN_W.
Replaces tests/test_chip_grid.py (the chip grid went). Real Tk window (hidden); skipped when Tk cannot open a window.

    python tests/test_head_chips.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-headchips-")
os.environ["PCCOMFY_HOME"] = TMP
os.environ["PCCOMFY_NO_TIPS"] = "1"
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models, popmenu  # noqa: E402


class Ev:
    x_root = y_root = 10


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    app.root.update()

    # the two chips: in one row, the function chip left, the model chip right of it; the old buttons and chips are gone
    assert app.b_mode.grid_info()["column"] == 0 and app.b_model.grid_info()["column"] == 1
    assert str(app.b_mode["style"]) == str(app.b_model["style"]) == "Pick.TButton"
    assert not hasattr(app, "f_models") and not hasattr(app, "chip_lines")
    st = gui.ttk.Style()
    assert st.lookup("Pick.TButton", "background") == gui.PANEL and st.lookup("Pick.TButton", "foreground") == gui.FG   # grey (user 20.11.)
    assert app.b_mode["text"].startswith("Fill Selection") and app.b_mode["text"].endswith(gui.PICK_ARROW)
    assert app.b_model["text"].startswith("Qwen") and app.b_model["text"].endswith(gui.PICK_ARROW)
    assert str(app.b_mode["image"])                                   # the function's symbol

    # fixed widths: whatever is chosen, the chips keep their width (the arrow at the same place)
    widths = set()
    for key in app._mode_order:
        app._pick_mode(key)
        app.root.update_idletasks()
        widths.add(app.b_mode.winfo_reqwidth())
    assert len(widths) <= 1 or max(widths) - min(widths) <= 2, widths
    mw = set()
    for m in models.MODELS:
        app.v_model.set(m.key)
        app._on_model()
        app.root.update_idletasks()
        mw.add(app.b_model.winfo_reqwidth())
    assert max(mw) - min(mw) <= 2, mw
    # both fit at the narrow window width (the window's side gaps of 10 px each); since 20.11. they share it in two equal
    # halves, so each one's longest entry must fit in half of it
    half = (app._px(gui.MIN_W) - 2 * app._px(10) - app._px(gui.PICK_GAP) - 1) // 2
    for b, labels in ((app.b_mode, ["Remove Selection", "Fill Selection", "Upscale", "Refine Image"]), (app.b_model, [m.label for m in models.MODELS])):
        frame = b.winfo_reqwidth() - app._pick_measure(str(b["text"]))       # padding, border, symbol
        need = frame + max(app._pick_measure(t) for t in labels) + app._pick_measure(gui.PICK_ARROW)
        assert need <= half, (str(b), need, half)
    app.root.update()
    assert abs(app.b_mode.winfo_width() - app.b_model.winfo_width()) <= 2, (app.b_mode.winfo_width(), app.b_model.winfo_width())
    assert abs(app.b_mode.winfo_height() - app.b_model.winfo_height()) <= 1     # as high as the function chip (user 20.11.)

    # the function list: the order of the former buttons, Edit for its tabs, Refine below Edit, then Upscale (two functions
    # again, user 22.11.), the dot on the chosen one
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    app.v_model.set("qwen")
    app._on_model()
    app._pick_mode("inpaint")
    app._mode_menu()
    labels = [e["label"] for e in app.m_mode.entries]
    assert labels == ["Text to Image", "Expand Image", "Fill Selection", "Remove Selection", "Edit", "Refine Image", "Upscale"], labels
    assert all(e["icon"] is not None for e in app.m_mode.entries)
    assert app.v_pick_mode.get() == "inpaint"
    app.m_mode.unpost()
    app.m_mode.invoke(labels.index("Edit"))                         # a choice does what a click on the button did
    app.root.update()
    assert app.v_mode.get() == "edit" and app.b_mode["text"].startswith("Edit")
    app.v_mode.set("multi_edit")                                      # a tab of Edit: the chip still says Edit
    app._show_picks()
    assert app.b_mode["text"].startswith("Edit")
    app._pick_mode("refine")
    assert app.v_mode.get() == "refine" and app.b_mode["text"].startswith("Refine")
    assert str(app._function_icon("refine")[0]) in str(app.b_mode["image"])       # its own symbol
    app._pick_mode("upscale")
    assert app.v_mode.get() == "upscale" and app.b_mode["text"].startswith("Upscale")
    assert str(app._function_icon("upscale")[0]) in str(app.b_mode["image"])

    # the model list: every model in the order of the chips, greyed out when it cannot do the function, the chosen one dotted
    app._pick_mode("inpaint")
    app._model_menu()
    ent = app.m_model.entries
    assert [e["label"] for e in ent] == [m.label for m in models.PICK_ORDER] and ent[0]["value"] == "minimax"   # MiniMax first (21.11.)
    # grey but clickable (user 20.11., A): every entry can be clicked, the ones that cannot fill are drawn grey
    assert all(e["state"] == "normal" for e in ent)
    assert [e["label"] for e in ent if e["fg"] != gui.DISABLED] == [m.label for m in models.PICK_ORDER if "inpaint" in m.modes]
    assert all(e["variable"] is app.v_model for e in ent)
    app.m_model.unpost()
    k = next(i for i, e in enumerate(ent) if e["fg"] != gui.DISABLED and e["value"] != app.v_model.get())
    app.m_model.invoke(k)
    app.root.update()
    assert app.v_model.get() == ent[k]["value"] and app.b_model["text"].startswith(ent[k]["label"])

    # missing files: red in the list (as the red chip was); greyed out wins over red
    app.rb_tabs["flux3"].missing = True
    app._model_menu()
    e = next(x for x in app.m_model.entries if x["value"] == "flux3")
    assert e["fg"] == gui.NA_RED
    i = app.m_model.entries.index(e)
    app.m_model._active = None
    assert app.m_model._row_colors(i)[1] == gui.NA_RED
    app.m_model.unpost()
    app.rb_tabs["flux3"].missing = False

    # a hidden model is not listed; every model hidden: the chip is greyed out
    app._set_model_hidden("flux2", True)
    app._model_menu()
    assert "Flux 2" not in [x["label"] for x in app.m_model.entries if x["value"] == "flux2"] and all(
        x["value"] != "flux2" for x in app.m_model.entries)
    app.m_model.unpost()
    app._set_model_hidden("flux2", False)
    for m in models.MODELS:
        app._set_model_hidden(m.key, True)
    assert str(app.b_model["state"]) == "disabled" and app.b_model["text"].startswith(gui.MODEL_PICK_EMPTY)
    for m in models.MODELS:
        app._set_model_hidden(m.key, False)
    assert str(app.b_model["state"]) == "normal"

    # right-click on the model chip: the menu of the chosen model (save settings, standard settings, hide)
    app.v_model.set("qwen")
    app._on_model()
    app.b_model.event_generate("<Button-3>", x=2, y=2)
    app.root.update()
    labels = [e["label"] for e in app.m_chip.entries if e["type"] != "separator"]
    assert labels[-1] == "Hide this model" and labels[0].startswith("Set current settings"), labels
    app.m_chip.unpost()

    # the gap to the prompt box (user 22.11.): without the Edit list (Fill, Refine, Text to image) from the chips to the box
    # as wide as from the Edit list to the box with it, and that is the gap between the two chips
    app.root.deiconify()
    app.v_model.set("flux3")
    app._on_model()

    def gap(mode):
        app._pick_mode(mode)
        app.root.update()
        above = app.f_edtabs if app.f_edtabs.winfo_manager() else app.f_tabs     # Flux 3 Fill has its tabs too
        return app.f_prompt.winfo_rooty() - (above.winfo_rooty() + above.winfo_height())

    with_list = gap("edit")
    assert app.f_edtabs.winfo_manager()
    chips = app.b_model.winfo_rootx() - (app.b_mode.winfo_rootx() + app.b_mode.winfo_width())
    assert abs(with_list - chips) <= 1, (with_list, chips)
    for mode in ("inpaint", "refine", "txt2img", "upscale"):
        assert abs(gap(mode) - with_list) <= 1, (mode, gap(mode), with_list)
    app.root.destroy()
    print("ALL OK (head chips)")


if __name__ == "__main__":
    main()
