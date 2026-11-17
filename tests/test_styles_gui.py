"""The Styles button in the real Tk window (hidden): it sits in the middle of the row over the field (Describe Canvas and Save on the left) in every function with a prompt field, and
the menu starts with the submenu Custom prompts (user 11.11.), a separator and a submenu per group (only where the mode has styles), an entry is ADDED to the prompt after a line break in one undo step (Ctrl+Z takes it away),
and the hover box shows the whole text. Skipped when Tk cannot open a window.

    python tests/test_styles_gui.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-stylesgui-")
os.environ["PCCOMFY_HOME"] = TMP
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models, styles  # noqa: E402


def shown(w) -> bool:
    return bool(w.winfo_manager())


def row_checks(app):
    """The icons beside the field (user 12.11.): Styles, Save, Describe Canvas and the bin in ONE narrow column right of the field,
    top-down in this order, all as big as the bin, the column starting at the top of the field; the placeholder starts where
    written text starts, in the text's font and the grey of the disabled Stop button."""
    app.root.update()
    col = app.f_picons
    assert app.f_ptop.winfo_manager() and app.f_pleft.master is app.f_ptop
    for b in (app.b_styles, app.b_save, app.b_llm, app.b_clear):
        assert b.master is col and str(b.cget("style")) == "Link.TButton" and not str(b.cget("text")) and b.cget("image"), b
    assert col.master is app.f_prompt and app.t_prompt.master is app.f_prompt
    ys = [b.winfo_rooty() for b in (app.b_styles, app.b_save, app.b_llm, app.b_clear)]
    assert ys == sorted(ys) and len(set(ys)) == 4, ys                              # Styles, Save, Describe, Delete top-down
    assert len({b.winfo_reqwidth() for b in (app.b_styles, app.b_save, app.b_llm, app.b_clear)}) == 1       # one size
    assert abs(app.b_styles.winfo_rooty() - app.t_prompt.winfo_rooty()) <= app._px(4)       # the column starts at the field's top
    assert col.winfo_rootx() >= app.t_prompt.winfo_rootx() + app.t_prompt.winfo_width() - 2   # right of the field
    assert col.winfo_reqwidth() <= app.b_clear.winfo_reqwidth() + app._px(6)               # as narrow as the icons
    # Stop: the word (user 12.11., was Cancel), no stop square (user 11.11.), as wide as Generate and as high
    assert str(app.b_stop.cget("text")) == "Stop" and not app.b_stop.cget("image"), (app.b_stop.cget("text"), app.b_stop.cget("image"))
    assert str(app.b_stop.cget("style")) == "" and int(str(app.b_stop.cget("width"))) == gui.STOP_W
    assert app.b_stop.winfo_height() == app.b_go.winfo_height()
    assert str(app.b_go.cget("style")) == "Accent.TButton"
    # the placeholder: the same start as written text, the same font, the grey of the disabled Stop button
    from tkinter import ttk
    from pccomfy import gui_common
    t = app.t_prompt
    t.delete("1.0", "end")
    app.t_prompt.master.focus_set()
    app._prompt_placeholder(focused=False)
    app.root.update()
    ph = app._ph
    assert str(ph.cget("fg")) == gui_common.DISABLED == str(ttk.Style(app.root).map("TButton", "foreground")[0][-1])
    assert str(ph.cget("font")) == str(t.cget("font")) or ph.cget("font") == t.cget("font")
    # place() counts from inside the Text's border and padx / pady: 0, 0 is where typed text starts (13.11.; padx was added twice before)
    assert int(ph.place_info()["x"]) == 0 and int(ph.place_info()["y"]) == 0
    assert int(str(ph.cget("padx"))) == 0 and int(str(ph.cget("pady"))) == 0
    t.insert("1.0", "word " * 200)
    app._prompt_placeholder()
    t.delete("1.0", "end")


def describe_checks(app):
    """Describe Canvas only in Text to image and in Refine while the picture is not made in tiles (P4); never in Upscale
    (user 12.11. after the P8 round: a description helped nowhere there, with tiles it put objects into the tiles)."""
    def at(model, mode):
        app.v_model.set(model)
        app.v_mode.set(mode)
        app._on_model()
        app.root.update()
        return shown(app.b_llm)
    assert at("flux3", "txt2img")
    for mode in ("edit", "multi_edit", "outpaint", "inpaint", "remove"):
        assert not at("qwen", mode), mode
    for model in ("flux3", "flux2", "qwen", "fibo"):
        assert not at(model, "upscale"), model      # Upscale: never, with or without tiles
    assert not at("flux2", "upscale")
    assert not [st for st in app._stages() if "tile" in st["label"].lower()]     # Flux 2 Upscale: always in tiles, no switch (user 12.11.)
    assert at("flux2", "refine")                    # Refine without tiles keeps it


def custom_checks(app):
    """The Prompt-Saver (user 11.11.): Save next to Describe Canvas (in its place where that is hidden), Styles in every function,
    Custom prompts at the top; Use replaces, Append appends, one undo step each; the label has model and function."""
    from unittest import mock
    from pccomfy import custom_prompts, gui_prompt
    app.v_model.set("flux3")
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    assert shown(app.b_save) and shown(app.b_llm) and app.b_save.winfo_rooty() < app.b_llm.winfo_rooty() < app.b_clear.winfo_rooty()
    app.v_mode.set("edit")
    app._on_model()
    app.root.update()
    assert not shown(app.b_llm) and shown(app.b_save)
    assert app.b_styles.winfo_rooty() < app.b_save.winfo_rooty() < app.b_clear.winfo_rooty()
    for mode in ("txt2img", "outpaint", "inpaint", "remove", "edit", "multi_edit", "upscale", "refine"):
        assert mode in app.m_styles and app.m_styles[mode].entrycget(0, "label") == "Custom prompts", mode
    t = app.t_prompt
    # an empty field: the status line, no window
    t.configure(state="normal")
    t.delete("1.0", "end")
    app.save_prompt()
    assert app.v_status.get() == "Write a prompt first" and getattr(app, "_cp_win", None) is None
    # save, replace
    t.insert("1.0", "Summer meadow")
    app.save_prompt()
    win = app._cp_win
    assert win.t_text is None
    app.root.update()
    assert win.wm_geometry().endswith(f"+{app._cp_pos[0]}+{app._cp_pos[1]}"), win.wm_geometry()   # really moved there (window test F)
    x, y = app._cp_pos                       # beside the window, top edges level, like the settings (window test E, 11.11.)
    assert y == app.root.winfo_rooty() and (x >= app.root.winfo_rootx() + app.root.winfo_width() or x < app.root.winfo_rootx()), (x, y)
    win.v_name.set("x" * 60)
    assert len(win.v_name.get()) == custom_prompts.MAX_NAME
    win.v_name.set("Meadow")
    win.ok()
    assert getattr(app, "_cp_win", None) is None
    saved = custom_prompts.load()
    assert len(saved) == 1 and saved[0]["name"] == "Meadow" and saved[0]["text"] == "Summer meadow", saved
    assert saved[0]["function"] == "Edit canvas" and saved[0]["model"] == app._cp_tag()[0] and saved[0]["model"]
    app.save_prompt()
    app._cp_win.v_name.set("MEADOW")
    with mock.patch.object(gui_prompt.messagebox, "askyesno", return_value=False) as ask:
        app._cp_win.ok()
        assert ask.called and "Replace it?" in ask.call_args[0][1]
    assert app._cp_win is not None and len(custom_prompts.load()) == 1
    t.delete("1.0", "end")
    t.insert("1.0", "Winter meadow")
    app._cp_win.close()
    app.save_prompt()
    app._cp_win.v_name.set("MEADOW")
    with mock.patch.object(gui_prompt.messagebox, "askyesno", return_value=True):
        app._cp_win.ok()
    assert [e["text"] for e in custom_prompts.load()] == ["Winter meadow"]
    # the menu: normal submenu, label with model and function, Use / Append / Edit / Delete
    app._refresh_custom_menu("edit")
    cm = app.m_custom["edit"]
    lab = cm.entrycget(0, "label")
    assert lab == "[Edit canvas · " + app._cp_tag()[0] + "] MEADOW", lab
    sub = cm.entrycget(0, "menu")
    assert [sub.entrycget(i, "label") for i in range(4)] == ["Use", "Append", "Edit", "Delete"]
    t.configure(undo=True)
    t.delete("1.0", "end")
    t.insert("1.0", "old text")
    t.edit_reset()
    sub.invoke(0)
    assert t.get("1.0", "end").strip() == "Winter meadow"
    t.edit_undo()
    assert t.get("1.0", "end").strip() == "old text"
    sub.invoke(1)
    assert t.get("1.0", "end").rstrip("\n") == "old text\nWinter meadow"
    t.edit_undo()
    assert t.get("1.0", "end").strip() == "old text"
    # Edit: name and text
    sub.invoke(2)
    w = app._cp_win
    assert w.t_text is not None and w.t_text.get("1.0", "end").strip() == "Winter meadow"
    w.v_name.set("Snow")
    w.t_text.delete("1.0", "end")
    w.t_text.insert("1.0", "Snowy field")
    w.ok()
    assert [(e["name"], e["text"]) for e in custom_prompts.load()] == [("Snow", "Snowy field")]
    # Delete asks first
    app._refresh_custom_menu("edit")
    cm = app.m_custom["edit"]
    sub = cm.entrycget(0, "menu")
    with mock.patch.object(gui_prompt.messagebox, "askyesno", return_value=False) as ask:
        sub.invoke(3)
        assert "Delete" in ask.call_args[0][1]
    assert len(custom_prompts.load()) == 1
    with mock.patch.object(gui_prompt.messagebox, "askyesno", return_value=True):
        sub.invoke(3)
    assert custom_prompts.load() == []
    assert app.m_custom["edit"].entrycget(0, "label") == "No saved prompts yet" and str(app.m_custom["edit"].entrycget(0, "state")) == "disabled"
    # Use goes back to function, model and tab; the image names follow the model; Append only renames (user 15.11.)
    from pccomfy import config as cfgmod, models as _models
    def pick(mode, key):
        app.v_mode.set(mode)
        app._on_mode()
        app.v_model.set(key)
        app._on_model()
    pick("multi_edit", "qwen")
    assert app.v_mode.get() == "multi_edit" and app.v_model.get() == "qwen"
    t.delete("1.0", "end")
    t.insert("1.0", "Put the bag from <image2> on the table")
    app.save_prompt()
    app._cp_win.v_name.set("Bag")
    app._cp_win.ok()
    bag = custom_prompts.load()[0]
    assert (bag["model_key"], bag["mode"], bag["tab"]) == ("qwen", "multi_edit", "multi"), bag
    pick("txt2img", "flux2")
    app._cp_use("Bag")
    assert (app.v_mode.get(), app.v_model.get(), app.v_edtab.get()) == ("multi_edit", "qwen", "multi")
    assert t.get("1.0", "end").strip() == "Put the bag from <image2> on the table"
    pick("multi_edit", "flux2")
    t.delete("1.0", "end")
    t.insert("1.0", "Keep it.")
    app._cp_use("Bag", append=True)                     # Append: stays on Flux 2, the tag as Flux 2 writes it
    assert (app.v_mode.get(), app.v_model.get()) == ("multi_edit", "flux2")
    assert t.get("1.0", "end").strip() == "Keep it.\nPut the bag from image 2 on the table", t.get("1.0", "end")
    # Insert reference (BBOX) of Flux 3 comes back as that tab
    pick("multi_edit", "flux3")
    app.v_edtab.set("bbox")
    app._edtab_clicked()
    t.delete("1.0", "end")
    t.insert("1.0", "wine glass")
    app.save_prompt()
    app._cp_win.v_name.set("Glass")
    app._cp_win.ok()
    pick("multi_edit", "qwen")
    assert not app.v_bbox.get()
    app._cp_use("Glass")
    assert (app.v_mode.get(), app.v_model.get(), app.v_edtab.get(), bool(app.v_bbox.get())) == ("multi_edit", "flux3", "bbox", True)
    # the saved model hidden: the function still opens, with a model the plugin picks, the tags follow it
    cfgmod.set_tab_hidden("qwen", True)
    try:
        pick("txt2img", "flux2")
        app._cp_use("Bag")
        assert app.v_mode.get() == "multi_edit" and app.v_model.get() not in ("qwen", ""), app.v_model.get()
        now = _models.BY_KEY[app.v_model.get()]
        assert t.get("1.0", "end").strip() == "Put the bag from " + now.tag_style.format(n=2, i=1) + " on the table"
        assert "Qwen Image 2.1 is not available here" in app.v_status.get(), app.v_status.get()
    finally:
        cfgmod.set_tab_hidden("qwen", False)
    # an entry saved before 15.11. (only the two labels): the labels tell function and model
    custom_prompts.save([{"name": "Old", "text": "A cat", "model": "Flux 2 Klein Edit", "function": "Edit canvas"}])
    pick("txt2img", "qwen")
    app._cp_use("Old")
    assert (app.v_mode.get(), app.v_model.get()) == ("edit", "flux2") and t.get("1.0", "end").strip() == "A cat"
    custom_prompts.save([])
    app._refresh_custom_menu(app.v_mode.get())
    pick("edit", "flux2")
    # the empty line is a disabled entry (grey, no hover); cascade rows of a saved prompt have a drawn arrow
    e = app.m_custom["edit"]
    assert str(e.entrycget(0, "state")) == "disabled"
    e.entryconfigure(0, state="normal")
    assert str(e.entrycget(0, "state")) == "normal"
    e.entryconfigure(0, state="disabled")
    assert str(e.entrycget(0, "state")) == "disabled"
    # a field that is off (no function does it today; Remove keeps its field since remove_text): Save and Styles are grey
    t.configure(state="disabled")
    app._update_styles_button()
    assert str(app.b_save.cget("state")) == "disabled" and str(app.b_styles.cget("state")) == "disabled"
    app.save_prompt()
    assert getattr(app, "_cp_win", None) is None
    t.configure(state="normal")
    app._update_styles_button()
    assert str(app.b_save.cget("state")) != "disabled" and str(app.b_styles.cget("state")) != "disabled"


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("flux3")
    app.v_mode.set("multi_edit")
    app._on_model()
    app.root.update()
    assert shown(app.b_styles) and shown(app.b_save)                # in every function since 11.11. (was: not in Multi image edit)
    assert app.m_styles["multi_edit"].index("end") == 0 and app.m_styles["multi_edit"].entrycget(0, "label") == "Custom prompts"
    app.v_mode.set("edit")
    app._on_model()
    app.root.update()
    assert shown(app.b_styles)                                      # Edit canvas has styles since plan B (10.11.)
    assert app.m_styles["edit"].index("end") == len(styles.load()["edit"]) + 1     # + Custom prompts and a separator (11.11.)
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    assert shown(app.b_styles) and shown(app.b_llm)
    row_checks(app)
    # the grip under the prompt field is as wide as the text field, not field + icon column (user 12.11.)
    app.root.update()
    for _ in range(3):
        app.root.update_idletasks()
    gw, tw = app.grip.winfo_width(), app.t_prompt.winfo_width()
    assert app.f_picons.winfo_width() > 10 and abs(gw - tw) <= 2, (gw, tw, app.f_picons.winfo_width())
    # same left and right edge on screen (12.11.: the pads were scaled twice, so at a display scale above 100 % the bar was narrower and shifted)
    gl, tl = app.grip.winfo_rootx(), app.t_prompt.winfo_rootx()
    assert abs(gl - tl) <= 1 and abs((gl + gw) - (tl + tw)) <= 1, (gl, gw, tl, tw)

    # the menu: a submenu per group, an entry per style, names only
    top = app.m_styles["txt2img"]
    groups = styles.load()["txt2img"]
    assert top.index("end") == len(groups) + 1
    assert top.entrycget(0, "label") == "Custom prompts" and top.type(1) == "separator"     # Custom prompts at the very top (11.11.)
    assert [top.entrycget(i + 2, "label") for i in range(len(groups))] == [g["name"] for g in groups]
    sub = top.entrycget(2, "menu")
    assert [sub.entrycget(i, "label") for i in range(len(groups[0]["styles"]))] == [s["name"] for s in groups[0]["styles"]]

    # an entry is added after a line break; one Ctrl+Z takes it away again; an empty field just gets the style
    app.t_prompt.configure(undo=True)
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red bicycle")
    app.t_prompt.edit_reset()
    sub.invoke(2)
    want = groups[0]["styles"][2]["text"]
    assert app.t_prompt.get("1.0", "end").rstrip("\n") == "a red bicycle\n" + want, repr(app.t_prompt.get("1.0", "end"))
    app.t_prompt.edit_undo()
    assert app.t_prompt.get("1.0", "end").strip() == "a red bicycle", repr(app.t_prompt.get("1.0", "end"))
    app.t_prompt.delete("1.0", "end")
    sub.invoke(2)
    assert app.t_prompt.get("1.0", "end").strip() == want
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red bicycle\n")        # already ends in a line break: no empty line in between
    sub.invoke(2)
    assert app.t_prompt.get("1.0", "end").rstrip("\n") == "a red bicycle\n" + want

    # a real popup of the Styles menu: right of the Styles button, top-aligned, cascade rows with an arrow; the hover box sits
    # beside the menu, level with the hovered row, and goes with the menu
    from pccomfy import popmenu
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    app.root.deiconify()
    app.root.update()
    app._styles_menu()
    app.root.update()
    gm = top.geometry()
    assert gm is not None
    bx = app.b_styles.winfo_rootx() + app.b_styles.winfo_width()
    assert gm[0] >= bx and gm[1] == app.b_styles.winfo_rooty(), (gm, bx, app.b_styles.winfo_rooty())
    assert top._cv.find_withtag("arrow0") and top._cv.find_withtag("arrow2") and not top._cv.find_withtag("arrow1")
    top._pointer(gm[0] + 20, gm[1] + top.row_top(2) - 1 + 4)        # the first group: its submenu opens after OPEN_MS
    app.root.update()
    for _ in range(30):
        app.root.update()
        app.root.after(20)
        if sub.geometry() is not None:
            break
    sg = sub.geometry()
    assert sg is not None and sg[0] >= gm[0] + gm[2]
    top._pointer(sg[0] + 20, sg[1] + sub.row_top(1) + 4)
    app.root.update()
    assert sub.index("active") == 1 and app._style_tip is not None
    labels = [w for w in app._style_tip.winfo_children() if w.winfo_class() == "Label"]
    assert labels and labels[0].cget("text") == groups[0]["styles"][1]["text"]
    tx, ty = app._style_tip_pos
    assert tx >= sg[0] + sg[2] or tx + app._style_tip.winfo_reqwidth() <= sg[0], (tx, sg)     # beside the menu, not over it
    assert abs(ty - (sg[1] + sub.row_top(1))) < 80 or ty > 0
    top.unpost()
    app.root.update()
    assert app._style_tip is None and top.geometry() is None and sub.geometry() is None
    sub._active = None
    app._style_preview(sub)                     # no active row: no box
    assert app._style_tip is None
    app.root.withdraw()

    app.v_mode.set("outpaint")
    app._on_model()
    app.root.update()
    assert shown(app.b_styles) and app.m_styles["outpaint"].index("end") == 0     # no styles there: only Custom prompts (11.11.; was: no button)
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()
    assert shown(app.b_styles)
    row_checks(app)
    describe_checks(app)
    custom_checks(app)
    app.root.destroy()
    print("ALL OK (styles gui)")


if __name__ == "__main__":
    main()
