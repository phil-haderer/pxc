"""The tabs under Edit (Edit canvas / Multi image edit; Sketch to image / Scribble on photo / Scribble with reference, plan B
10.11.) in the real window: since 20.11. (user) one list chip in the look of the function chip, with its arrow, the full
width, a little higher than the tabs were and lower than the function chip; and a chosen chip is blue to its edge (no
dark ring inside the blue border). Real Tk window (hidden); skipped when Tk cannot open a window.

    python tests/test_edit_tabs_window.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-edtabs-")
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

import tkinter.font as tkfont  # noqa: E402

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models  # noqa: E402
from pccomfy.gui_common import font  # noqa: E402


def check_tabs(app, model):
    app.v_model.set(model)
    app.v_mode.set("edit")
    app._on_model()
    app.root.update()
    shown = list(app._edtab_shown)
    assert shown, (model, shown)
    chip = app.b_edtab
    assert chip.winfo_manager() == "pack" and str(chip.cget("style")) == "Pick.TButton"
    full = app.f_edtabs.winfo_width()
    assert full - chip.winfo_width() <= 2 * 2 * gui.EDTAB_PADX + 1, (model, full, chip.winfo_width())     # the full width
    # right under the function and model chips, above the prompt; the reference slots stay under the prompt (user 20.11.)
    order = app.f_body.pack_slaves()
    assert order.index(app.f_edtabs) < order.index(app.f_prompt), model
    if app.f_refs.winfo_manager():
        assert order.index(app.f_refs) > order.index(app.f_prompt), model
    # the gap above the list (to the chips) and below it (to the prompt box) as wide as the gap between the chips (user 21.11.)
    app.root.update()
    across = app.b_model.winfo_rootx() - (app.b_mode.winfo_rootx() + app.b_mode.winfo_width())
    above = chip.winfo_rooty() - (app.b_mode.winfo_rooty() + app.b_mode.winfo_height())
    below = app.f_prompt.winfo_rooty() - (chip.winfo_rooty() + chip.winfo_height())
    assert above == below == across, (model, above, below, across)
    label = dict(app.EDIT_TABS)[app.v_edtab.get()]
    text = str(chip.cget("text"))
    assert text.startswith(label) and text.endswith(gui.PICK_ARROW), (model, text)      # the chosen tab and the arrow
    # a little higher than the tabs were (Small.Toolbutton), lower than the function chip with its symbol
    assert app.rb_edtabs["edit"].winfo_reqheight() < chip.winfo_reqheight() < app.b_mode.winfo_height(), \
        (model, app.rb_edtabs["edit"].winfo_reqheight(), chip.winfo_reqheight(), app.b_mode.winfo_height())
    if "sketch" in models.BY_KEY[model].modes:      # MiniMax since 21.11. too (step 8), without Scribble with reference
        want = ["sketch", "scribble"] + (["refscribble"] if models.offers_ref_scribble(models.BY_KEY[model]) else [])
        assert shown == ["edit", "multi"] + want, (model, shown)
    # the list: one entry per tab, greyed out where the tab is
    app._edtab_menu()
    assert app.m_edtab.index("end") == len(shown) - 1, (model, app.m_edtab.index("end"))
    assert [str(app.m_edtab.entrycget(i, "state")) == "disabled" for i in range(len(shown))] == \
        [str(app.rb_edtabs[k].cget("state")) == "disabled" for k in shown]
    app.m_edtab.unpost()
    return shown


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names

    # the chosen chip and the chosen function button: blue with Generate's light black outline (window test 11.11.): the
    # same border colours and relief as Generate (its outer line and the dark ring inside), only while chosen
    st = gui.ttk.Style(app.root)
    for name in ("Chip.Toolbutton", "Tab.Toolbutton"):
        assert st.lookup(name, "background", ["selected"]) == gui.ACCENT, name
        assert str(st.lookup(name, "relief", ["selected"])) == str(st.lookup("Accent.TButton", "relief")) == "raised", name
        for opt in ("lightcolor", "darkcolor", "bordercolor"):      # no outline on a blue button since 21.11. (user)
            assert st.lookup(name, opt, ["selected"]) == st.lookup("Accent.TButton", opt) == gui.ACCENT, (name, opt)
    # not chosen: a function button keeps its border in its own fill (no outline, as before), a chip its grey outline
    for opt in ("lightcolor", "darkcolor", "bordercolor"):
        assert st.lookup("Tab.Toolbutton", opt, ["!selected"]) == gui.PANEL, opt
        assert st.lookup("Tab.Toolbutton", opt, ["active"]) == "#5f5f5f", opt
    assert st.lookup("Chip.Toolbutton", "bordercolor", ["!selected"]) == gui.BG      # the grid lines are drawn by the backdrop frames (12.11.)
    assert str(st.lookup("Chip.Toolbutton", "relief", ["!selected"])) == "solid"
    # the border adds clam's 2 px a side, taken off the padding: a function button has its former size (padding 4 5, no border)
    pad = [int(float(v)) for v in re.findall(r"[\d.]+", str(st.lookup("Tab.Toolbutton", "padding")))]
    from pccomfy import spacing
    assert str(st.lookup("Tab.Toolbutton", "borderwidth")) == "1" and pad == [spacing.scale(4) - 2, spacing.scale(5) - 2], pad
    assert str(st.lookup("Set.Tab.Toolbutton", "borderwidth")) == "0"       # the settings window's model buttons: unchanged

    seen = {}
    for m in models.MODELS:
        if "multi_edit" in m.modes or "sketch" in m.modes:
            seen[m.key] = check_tabs(app, m.key)
    # Insert reference is a tab of Fill since 11.11. (plan B step 4): Flux 3 has the same 2 + 2 under Edit as the others
    assert all(seen[k] == ["edit", "multi", "sketch", "scribble", "refscribble"] for k in ("flux3", "flux2", "qwen")), seen
    assert seen["fibo"] == ["edit", "multi", "sketch", "scribble"], seen     # no tab with reference (user 15.11.)
    # under Fill (Flux 3 only): Fill selection and Insert reference in the same list
    app.v_model.set("flux3")
    app.v_mode.set("inpaint")
    app._on_model()
    app.root.update()
    assert app._edtab_shown == ["fill", "bbox"] and app.v_fn.get() == "inpaint", app._edtab_shown
    assert str(app.b_edtab.cget("text")).startswith("Fill selection")
    app.v_edtab.set("bbox")             # a pick in the list: what a click on the tab did
    app._edtab_clicked()
    assert app.v_mode.get() == "multi_edit" and app.v_bbox.get() and str(app.b_edtab.cget("text")).startswith("Insert reference")
    assert seen["minimax"] == ["edit", "multi", "sketch", "scribble"], seen     # step 8 (21.11.), no tab with reference yet

    # the list chip starts at the same left edge as the function chip
    app.v_model.set("flux3")
    app.v_mode.set("edit")
    app._on_model()
    app.v_edtab.set("scribble")
    app._edtab_clicked()
    app.root.geometry("+-4000+-4000")      # shown off-screen: a withdrawn window is never laid out (its canvas body sits 1 px off)
    app.root.deiconify()
    app.root.update()
    left = app.b_mode.winfo_rootx()          # the function chip (20.11.; was the first model chip)
    firsts = {"function": app.b_mode, "tab": app.b_edtab}
    assert not app.f_sketch.winfo_manager()      # the two scribble chips are tabs since 15.11. (user): no chip row
    for name, w in firsts.items():
        assert w.winfo_manager() and abs(w.winfo_rootx() - left) <= 1, (name, w.winfo_rootx(), left)
    app.root.destroy()
    print("ALL OK (Edit tab list and chip fill in the real window)")


if __name__ == "__main__":
    main()
