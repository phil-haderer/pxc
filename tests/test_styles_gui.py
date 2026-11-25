# tags: styles, window
"""The Styles button in the real Tk window (hidden): it sits in the middle of the row over the field (Describe Canvas and Save on the left) in every function with a prompt field, and
the menu starts with the submenu Custom prompts (user 11.11.), a separator and a submenu per group (only where the mode has styles), an entry is ADDED to the prompt after a line break in one undo step (Ctrl+Z takes it away),
and the hover box shows the whole text. Skipped when Tk cannot open a window.

    python tests/test_styles_gui.py
"""
import os
import sys
import tempfile
import time
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


def hold_still(app, seconds=1.0):
    """A real window manager (Wayland via XWayland) may still move a window it just showed (title bar, 1 px): update until
    the plugin window stands still for 0.1 s, at most `seconds` (Mint laptop 19.11.)."""
    import time
    end, last, since = time.monotonic() + seconds, None, time.monotonic()
    while time.monotonic() < end:
        app.root.update()
        pos = (app.root.winfo_rootx(), app.root.winfo_rooty())
        if pos != last:
            last, since = pos, time.monotonic()
        elif time.monotonic() - since >= 0.1:
            return
        time.sleep(0.02)


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
    # no Stop button since 20.11. (user): Generate itself turns into "Stop" during a run (test_cancel_all.py)
    assert not hasattr(app, "b_stop") and str(app.b_go.cget("style")) == "Accent.TButton"
    # no blue frame round the prompt field, in focus or with a tip (user 20.11.)
    assert str(app.t_prompt.cget("highlightcolor")) == str(app.t_prompt.cget("highlightbackground")) == "#454545"
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


def empty_click_checks(app):
    """A double or triple click into an empty prompt field selects nothing (Tk selected the empty first line, user 21.11.);
    with text in it a double click still selects the word."""
    t = app.t_prompt
    t.configure(state="normal")
    t.delete("1.0", "end")
    app.root.deiconify()
    app.root.update()

    def clicks(n):              # Tk makes a double / triple click out of quick presses (event_generate refuses "Double")
        for _ in range(n):
            t.event_generate("<ButtonPress-1>", x=8, y=8)
            t.event_generate("<ButtonRelease-1>", x=8, y=8)
        app.root.update()
    for n in (2, 3):
        clicks(n)
        assert not t.tag_ranges("sel") and t.get("1.0", "end-1c") == "", (n, t.tag_ranges("sel"))
        app.root.after(700)     # past the double-click time: the next presses start a new series
    t.insert("1.0", "make it night")
    clicks(2)
    assert t.tag_ranges("sel"), "with text, a double click still selects the word"
    t.tag_remove("sel", "1.0", "end")
    t.delete("1.0", "end")
    app.root.withdraw()


def style_box_checks(app, groups):
    """The window wishes of 21.11. (docs/plan/fenster-wuensche-21-11.md): Custom prompts as a list in the box (2A), no status
    message on a style or a saved prompt, an old plain message goes (3), a style replaces an untouched prompt (4A), the
    right-click menus of a tile and of a saved prompt."""
    from pccomfy import custom_prompts, stylegrid
    t = app.t_prompt
    text = lambda: t.get("1.0", "end").strip()
    first, second = groups[0]["styles"][0]["text"], groups[0]["styles"][1]["text"]
    # (4A) a style replaces a style, a stock text or the text PxC put in; own text gets it as a new line
    t.delete("1.0", "end")
    app._apply_style(first)
    app._apply_style(second)
    assert text() == second
    t.insert("end", " and a red bicycle")
    app._apply_style(first)
    assert text() == second + " and a red bicycle\n" + first
    app._apply_style(second, how="replace")
    assert text() == second
    app._apply_style(first, how="append")
    assert text() == second + "\n" + first
    # (3) no status message; an old plain one goes, an error stays
    app._status("Saved image.")
    app._apply_style(first)
    assert app.v_status.get() == ""
    app._status("Broken", error=True)
    app._apply_style(second)
    assert app.v_status.get() == "Broken"
    app._status("")
    # (2A) Custom prompts: a list in the box, a click = Use, the right-click menu has Use / Append / Edit / Delete
    entries = []
    custom_prompts.add(entries, "Meadow", "Summer meadow at noon", "Flux 3 Klein", "Text to image",
                       context={"model_key": "flux3", "mode": "txt2img", "tab": ""})
    assert custom_prompts.save(entries)
    app._styles_menu()
    app.root.update()
    g = app.style_grid
    g._show_group(stylegrid.CUSTOM)
    app.root.update()
    lines = g.custom_lines()
    assert [str(x.cget("text")) for x in lines] == [custom_prompts.label(entries[0])] and not g.tiles
    assert not g.note_shown()                     # the line about the previews only under the style tiles (user 21.11.)
    g._show_group(0)
    app.root.update()
    assert g.note_shown() and str(g.l_note.cget("text")) == stylegrid.PREVIEW_NOTE and "Qwen Image 2.1" in stylegrid.PREVIEW_NOTE
    g._show_group(stylegrid.CUSTOM)
    app.root.update()
    lines = g.custom_lines()
    assert str(g.chips[0].cget("bg")) == stylegrid.ACCENT
    g._show_tip(lines[0])
    assert g.tip_text == "Summer meadow at noon"
    g._hide_tip()
    t.delete("1.0", "end")
    t.insert("1.0", "own words")
    g._use("Meadow")
    app.root.update()
    assert not g.is_open() and text() == "Summer meadow at noon" and app.v_status.get() == "", (g.is_open(), text(), app.v_status.get())
    app._styles_menu()
    app.root.update()
    assert app.style_grid.group == stylegrid.CUSTOM                 # reopens on Custom prompts
    # a right-click keeps the picker open under its menu (user 21.11.); Escape on the menu gives it back the clicks
    g = app.style_grid
    line = g.custom_lines()[0]
    ev = type("E", (), {"x_root": 300, "y_root": 300})()
    g._menu("custom", line.entry, ev)
    m = app._grid_menu
    assert g.is_open() and g.menu_open
    assert [m.entrycget(i, "label") for i in range(4)] == ["Use", "Append", "Edit", "Delete"]
    assert g._click(type("E", (), {"x_root": -5000, "y_root": -5000})()) is None and g.is_open()    # the menu's clicks, not ours
    m.unpost()
    app.root.update()
    assert g.is_open() and not g.menu_open                          # menu gone, picker still there
    g._menu("custom", line.entry, ev)
    t.delete("1.0", "end")
    app._grid_menu.invoke(0)                                         # Use: the picker closes, the text comes in
    app.root.update()
    assert not g.is_open() and text() == "Summer meadow at noon"
    app._styles_menu()
    app.root.update()
    g = app.style_grid
    g._show_group(0)
    app.root.update()
    g._menu("style", g.tiles[0].style, ev)
    m = app._grid_menu
    assert [m.entrycget(i, "label") for i in range(4)] == ["Append", "Replace", "Copy text", "Save as custom prompt"]
    m.invoke(2)
    app.root.update()
    assert app.root.clipboard_get() == g.tiles[0].style["text"] and g.is_open()      # Copy text keeps the picker
    m.unpost()
    g.close()
    # a click outside closes it (switched off while the tests run: the grab is global, a real click of the user got in)
    app._styles_menu()
    app.root.update()
    g = app.style_grid
    far = type("E", (), {"x_root": -5000, "y_root": -5000})()
    assert g._click(far) == "break" and g.is_open()
    stylegrid.CLOSE_ON_OUTSIDE_CLICK = True
    try:
        assert g._click(far) == "break" and not g.is_open()
    finally:
        stylegrid.CLOSE_ON_OUTSIDE_CLICK = False
    # a function without styles opens the picker straight on Custom prompts
    app.v_mode.set("outpaint")
    app._on_model()
    app.root.update()
    app._styles_menu()
    app.root.update()
    g = app.style_grid
    assert g.is_open() and g.group == stylegrid.CUSTOM and [str(c.cget("text")) for c in g.chips] == ["Custom prompts"]
    g.close()
    custom_prompts.save([])
    g2 = stylegrid.StyleGrid(app.root, [], on_pick=lambda s: None, customs=lambda: [])
    g2.open(app.b_styles)
    app.root.update()
    assert g2.custom_lines() == [] and g2.rows
    g2.close()
    app.v_mode.set("txt2img")
    app._on_model()
    app.root.update()


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
    assert lab == "Edit canvas · " + app._cp_tag()[0] + " – MEADOW", lab      # no square brackets (user 21.11.)
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
    # the start's look at PhotoCraft and ComfyUI (gui_state.refresh, a thread) puts "Can't connect to PhotoCraft" into
    # the status line; under load (the full run, 23.11.) it came only during the style checks that expect an empty line:
    # wait for it, then start from an empty status line. The start sends TWO answers (24.11.): PhotoCraft and ComfyUI
    # (gui_state.refresh) and the file lists (ui_settings._detect_async, "_detect"); waiting for the first only let the
    # other one fill the status line later under load
    seen, real_refresh = set(), app._apply_refresh
    app._apply_refresh = lambda info: (seen.add("detect" if info.get("_detect") else "state"), real_refresh(info))
    end = time.monotonic() + 30
    while seen != {"state", "detect"} and time.monotonic() < end:
        app.root.update()
        time.sleep(0.02)
    del app._apply_refresh
    assert seen == {"state", "detect"}, f"the start's answers did not come: {seen}"
    app._status("")
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

    # the style picker (user 20.11., stylegrid.py): opens UNDER the Styles button, "Custom prompts" and the groups as chips,
    # the styles of the chosen group as square tiles (initials while a style has no picture), the whole text beside the
    # popup while the mouse rests on a tile, a click puts the style in and closes it; it reopens on the group chosen last
    from pccomfy import popmenu, stylegrid
    # where it opens (stylegrid.place): under the button, else above, else beside it (small screens, user 21.11., choice C)
    pl = stylegrid.place
    assert pl(100, 200, 80, 20, 400, 300, (0, 0, 1920, 1040), 2) == (100, 222)          # under the button
    assert pl(1700, 200, 80, 20, 400, 300, (0, 0, 1920, 1040), 2) == (1380, 222)        # right-aligned at the right edge
    assert pl(100, 900, 80, 20, 400, 300, (0, 0, 1920, 1040), 2) == (100, 598)          # above it near the bottom
    assert pl(324, 218, 80, 19, 389, 478, (0, 0, 1366, 712), 2) == (406, 218)           # the Mint laptop: beside it
    assert pl(1200, 218, 80, 19, 389, 478, (0, 0, 1366, 712), 2) == (809, 218)          # beside it on the left
    assert pl(324, 400, 80, 19, 389, 478, (0, 0, 1366, 712), 2) == (406, 234)           # moved up only as far as needed
    assert pl(324, 218, 80, 19, 389, 800, (0, 0, 1366, 712), 2) == (406, 0)             # taller than the screen: from the top
    popmenu.CLOSE_ON_FOCUS_LOSS = stylegrid.CLOSE_ON_FOCUS_LOSS = False
    stylegrid.CLOSE_ON_OUTSIDE_CLICK = False       # a real click of the user during the run must not close it
    app.root.deiconify()
    hold_still(app)
    app._styles_menu()
    app.root.update()
    g = app.style_grid
    assert g.is_open() and top.geometry() is None                     # the old menu does not open
    gx, gy = g.pos
    b = app.b_styles
    assert (gy >= b.winfo_rooty() + b.winfo_height() or gy + g.top.winfo_height() <= b.winfo_rooty()
            or gx >= b.winfo_rootx() + b.winfo_width() or gx + g.top.winfo_width() <= b.winfo_rootx())   # never over the button
    assert [str(c.cget("text")) for c in g.chips] == ["Custom prompts"] + [x["name"] for x in groups]     # no ▸ (21.11., 2A)
    assert [t.style["name"] for t in g.tiles] == [x["name"] for x in groups[0]["styles"]]
    s0 = app._px(stylegrid.TILE)
    assert all(int(t.canvas.cget("width")) == int(t.canvas.cget("height")) == s0 for t in g.tiles)     # square
    assert len({t.winfo_rooty() for t in g.tiles[:stylegrid.COLS]}) == 1 and g.tiles[stylegrid.COLS].winfo_rooty() > g.tiles[0].winfo_rooty()
    # equal columns with a gap of GAP px between the rings, whatever the names (user 21.11., choice 5A)
    assert stylegrid.GAP == 3 and stylegrid.TILE == 88
    xs = [t.canvas.winfo_rootx() for t in g.tiles[:stylegrid.COLS]]
    step = s0 + 2 * app._px(2) + app._px(stylegrid.GAP)
    assert all(abs((xs[k + 1] - xs[k]) - step) <= 1 for k in range(len(xs) - 1)), (xs, step)
    for grp in range(len(groups)):        # no group has a column that a long name widens
        g._show_group(grp)
        app.root.update()
        cols = {}
        for k, t in enumerate(g.tiles):
            cols.setdefault(k % stylegrid.COLS, set()).add(t.canvas.winfo_rootx())
        assert all(len(v) == 1 for v in cols.values()), (groups[grp]["name"], cols)
        assert len({min(v) for v in cols.values()}) == len(cols)
        assert all(t.winfo_width() <= s0 + 2 * app._px(2) + 1 for t in g.tiles), groups[grp]["name"]
    g._show_group(0)
    app.root.update()
    g._show_tip(g.tiles[1])
    assert g.tip_text == groups[0]["styles"][1]["text"]
    g._hide_tip()
    assert g.tip_text == ""
    g._show_group(2)
    app.root.update()
    assert [t.style["name"] for t in g.tiles] == [x["name"] for x in groups[2]["styles"]] and str(g.chips[3].cget("bg")) == stylegrid.ACCENT
    app.t_prompt.delete("1.0", "end")
    g._pick(g.tiles[0].style)
    app.root.update()
    assert not g.is_open() and app.t_prompt.get("1.0", "end").strip() == groups[2]["styles"][0]["text"]
    app._styles_menu()
    app.root.update()
    assert app.style_grid.group == 2                                  # the group chosen last
    app.style_grid.close()
    style_box_checks(app, groups)
    empty_click_checks(app)
    assert stylegrid.initials("Studio & product") == "SP" and stylegrid.initials("Noir") == "N"
    # a picture in style-thumbs/<slug>.png is shown instead of the initials, in every mode (one picture per name)
    import tempfile
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        Image.new("RGB", (300, 200), "red").save(Path(d) / (styles.slug(groups[0]["styles"][0]["name"]) + ".png"))
        saved = styles.THUMBS
        styles.THUMBS = Path(d)
        try:
            app._styles_menu()
            app.root.update()
            app.style_grid._show_group(0)
            tiles = app.style_grid.tiles
            assert tiles[0].has_picture and not tiles[1].has_picture
            app.style_grid.close()
        finally:
            styles.THUMBS = saved
    assert styles.slug("Studio & product") == "studio-product" and styles.thumb_path("No such style") is None
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
