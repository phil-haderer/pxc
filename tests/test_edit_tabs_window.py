"""The tabs under Edit (Edit canvas / Multi image edit / Insert reference; Sketch to image / Scribble on photo, plan B 10.11.)
and the chosen model chip in the real
window (user 10.11.): no tab text is cut (the chosen one is bold), every row uses the full width, and a chosen chip is blue
to its edge (no dark ring inside the blue border). Real Tk window (hidden); skipped when Tk cannot open a window.

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
    bold = tkfont.Font(root=app.root, font=font(9, bold=True))
    plain = tkfont.Font(root=app.root, font=font(9))
    rows = app._edtab_layout
    assert rows and rows[0], (model, rows)
    full = app.f_edtabs.winfo_width()
    for r, row in enumerate(rows):
        frame = app.f_edtab_rows[r]
        assert frame.winfo_width() == full, (model, r, frame.winfo_width(), full)      # every row the full width
        right = 0
        for k in row:
            rb = app.rb_edtabs[k]
            label = dict(app.EDIT_TABS)[k]
            need = rb.winfo_reqwidth() - plain.measure(label) + bold.measure(label)
            assert rb.winfo_width() >= need, (model, k, rb.winfo_width(), need)      # the bold text fits: nothing cut
            right = max(right, rb.winfo_x() + rb.winfo_width())
        assert full - right <= 2 * 4, (model, r, full, right)                         # the last tab reaches the right edge
    # (the long "Scribble with reference", 15.11., may take a row of its own, the full width)
    widths = [app.rb_edtabs[k].winfo_width() for k in sum(rows, []) if not (k == "refscribble" and len(rows[-1]) == 1)]
    assert max(widths) - min(widths) <= 1, (model, widths)          # all tabs the same width (window test 11.11.)
    if "sketch" in models.BY_KEY[model].modes:      # MiniMax has Edit and Multi image edit only (step 4): one row of two
        # plan B: the edit tabs in the first row, the sketch tabs after them in their own row(s); since 15.11. three of them
        # (Fibo without Scribble with reference, user 15.11.)
        want = ["sketch", "scribble"] + (["refscribble"] if models.offers_ref_scribble(models.BY_KEY[model]) else [])
        assert rows[0] == ["edit", "multi"] and sum(rows[1:], []) == want, (model, rows)
    return rows


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
        for opt in ("lightcolor", "darkcolor", "bordercolor"):
            line = st.lookup("Accent.TButton", opt)
            assert line and line != gui.ACCENT and st.lookup(name, opt, ["selected"]) == line, (name, opt, line)
    assert st.lookup("Accent.TButton", "lightcolor") == gui.PANEL        # the dark ring of Generate
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
    assert all(sum(seen[k], []) == ["edit", "multi", "sketch", "scribble", "refscribble"] for k in ("flux3", "flux2", "qwen")), seen
    assert sum(seen["fibo"], []) == ["edit", "multi", "sketch", "scribble"], seen     # no tab with reference (user 15.11.)
    # under Fill (Flux 3 only): Fill selection and Insert reference in one row, the full width, the same width
    app.v_model.set("flux3")
    app.v_mode.set("inpaint")
    app._on_model()
    app.root.update()
    assert app._edtab_layout == [["fill", "bbox"]], app._edtab_layout
    fw = [app.rb_edtabs[k].winfo_width() for k in ("fill", "bbox")]
    assert abs(fw[0] - fw[1]) <= 1 and app.v_fn.get() == "inpaint", fw
    assert seen["minimax"] == [["edit", "multi"]], seen

    # the looks swapped (user 10.11.): the tabs filled grey like the small switches, the Sketch templates outlined like the
    # model chips; and every row of buttons starts at the same left edge as the model chips
    assert all(str(rb["style"]) == "Small.Toolbutton" for rb in app.rb_edtabs.values())
    app.v_model.set("flux3")
    app.v_mode.set("edit")
    app._on_model()
    app.v_edtab.set("scribble")
    app._edtab_clicked()
    app.root.geometry("+-4000+-4000")      # shown off-screen: a withdrawn window is never laid out (its canvas body sits 1 px off)
    app.root.deiconify()
    app.root.update()
    left =app.rb_tabs[models.MODELS[0].key].winfo_rootx()
    firsts = {"function": app.rb_modes["edit"], "tab": app.rb_edtabs["edit"]}
    assert not app.f_sketch.winfo_manager()      # the two scribble chips are tabs since 15.11. (user): no chip row
    for name, w in firsts.items():
        assert w.winfo_manager() and w.winfo_rootx() == left, (name, w.winfo_rootx(), left)
    app.root.destroy()
    print("ALL OK (Edit tabs and chip fill in the real window)")


if __name__ == "__main__":
    main()
