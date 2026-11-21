"""The page Model Links of the settings window in the real Tk window (hidden), as designed on 19.11.: the narrower window, the
the pages as chips (blue when chosen, no lines) and the menu "⋯" with Reset and Check files (choice K2; the message after a change
with its Undo, which stays without a time limit, 21.11.); the field with the model and its list (choice C, before chips); the head line with
"Show in PxC"; the modes as tiles; one blue download button; and per file the field that shows the file in use (missing:
red frame, linked: blue with the way back) and opens the search window right below itself. Skipped when Tk cannot open a window.

    python tests/test_model_links_design.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-links-")
os.environ["PCCOMFY_HOME"] = TMP
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, inventory, linkpicker, manifest, popmenu, ui_settings  # noqa: E402
import test_detection as td  # noqa: E402

NODES = {n for tab in manifest.TABS.values() for s in tab.modes.values() for n in s.nodes}


def widgets(w):
    out = [w]
    for c in w.winfo_children():
        out += widgets(c)
    return out


def main():
    gui.winlink.available = lambda: False
    # no refresh and no model search against the dead address (linking a file starts one): on Linux their error comes at once
    # and empties the list mid-test (on Windows only after about 2 s, when the test is through; Mint laptop 19.11.)
    gui.App.refresh = lambda self: None
    gui.App._detect_async = lambda self: None
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app._comfy_root = Path("")
    app.root.withdraw()
    app.root.update()
    lists = td.full_lists()
    lists["vae"].remove("qwen_image_vae.safetensors")           # one file missing (Qwen, Krea 2 ...)
    lists["vae"].remove("flux2-vae.safetensors")
    lists["vae"].append("my_vae.safetensors")                    # ... and one stand-in to link
    app._apply_refresh({"_detect": True, "_inv": inventory.Inventory(lists, NODES)})
    app._link_models("flux2-vae.safetensors", "my_vae.safetensors")
    key = next(m.key for m in gui.models.MODELS if app.inv.tab_status(m.key).state != "ready")      # a model with a missing file
    sizes = []      # the size open_settings gives the window (an unmapped test window reports 1x1)
    import tkinter as tk
    real_geo = tk.Toplevel.wm_geometry
    tk.Toplevel.geometry = tk.Toplevel.wm_geometry = lambda w, g=None: (sizes.append(g), real_geo(w, g))[1]
    try:
        app.open_settings(focus=key)
    finally:
        tk.Toplevel.geometry = tk.Toplevel.wm_geometry = real_geo
    win = app._settings_win
    win.update()

    # narrower than before (640 until 19.11.), smallest 440; the size of the old key is not used
    assert ui_settings.SETTINGS_W == 520 and ui_settings.SET_MIN_W == 440
    # always 700 px high, no longer as high as the plugin window (user 20.11.: a short window in Expand hid most models)
    assert ui_settings.SETTINGS_H == 700 and not hasattr(app, "_root_height")
    assert any(g and g.split("+")[0].endswith(f"x{app._px(700)}") for g in sizes), sizes
    # but always inside the work area (review 21.11.): moved up first, then lower; 150 % on Full HD is 1050 px
    fit = ui_settings.fit_height
    assert fit(100, 700, 0, 1040) == (100, 700)
    assert fit(500, 700, 0, 1040) == (340, 700)          # moved up, as high as wanted
    assert fit(200, 1050, 0, 1040) == (0, 1040)          # higher than the area: as high as the area
    assert fit(-50, 700, 0, 1040) == (0, 700)            # never above the area
    assert fit(1200, 700, 1080, 2120, 300) == (1200, 700)    # a second monitor below the first
    assert fit(0, 200, 0, 1040, 300) == (0, 300)         # never below the smallest height
    assert (ui_settings.SET_PAD, ui_settings.SET_IN, ui_settings.SET_ITEM, ui_settings.SET_SECTION) == (16, 4, 12, 20)

    # the head (choice K2): no row of buttons; on top of the page only the message and Undo of a change that can still be taken
    # back: the link made before the window opened keeps them (no time limit, user 21.11.); without one nothing is there
    texts = [str(w.cget("text")) for w in widgets(app.f_set_top) if w.winfo_class() in ("TLabel", "TButton")]
    assert texts == ["Undo", "Linked: flux2-vae.safetensors → my_vae.safetensors."], texts
    app._map_undo.clear()
    app._link_msg = ""
    app._settings_fill()
    win.update()
    texts = [str(w.cget("text")) for w in widgets(app.f_set_top) if w.winfo_class() in ("TLabel", "TButton")]
    assert texts == [], texts
    assert not hasattr(app, "b_check") and not hasattr(app, "b_link_reset") and not hasattr(app, "b_link_default")
    assert app._link_resets() == {"startup": True, "default": True}
    # the pages as two chips like the model chips (user 19.11.): no white lines, no blue line on top; the chosen chip is blue
    nb, chips = app.nb_settings, app.set_tab_chips
    assert not hasattr(app, "sep_set_tabs") and not hasattr(app, "sep_set_under")
    assert [str(c.cget("text")) for c in chips] == ["Model Links", "Other settings"]
    assert all(str(c.cget("style")) == "SetTab.Chip.Toolbutton" for c in chips) and app._set_tab.get() == 0
    # as large as the function buttons of the main window (user 19.11.): their font and their height
    st = gui.ttk.Style()
    assert str(st.lookup("SetTab.Chip.Toolbutton", "font")) == str(st.lookup("Tab.Toolbutton", "font"))
    assert chips[0].master.grid_rowconfigure(0)["minsize"] >= app.b_mode.winfo_reqheight()
    assert not any(isinstance(w, gui.tk.Frame) and str(w.cget("bg")).lower() == gui.ACCENT.lower() for w in win.winfo_children())
    # title, chips and the model field on one line from the left edge
    field, row = app.nb_models.bar, chips[0].master.master
    title = [w for w in app._set_bar.winfo_children() if str(w.winfo_class()) == "TLabel"][0]
    left = int(app._set_left)
    def pad_left(w):                         # pack_info gives a number when both sides are equal, else a pair
        p = w.pack_info()["padx"]
        return int(str(p[0] if isinstance(p, (tuple, list)) else p))
    assert pad_left(row) == left and pad_left(title) == left, (row.pack_info(), title.pack_info())
    # pixels only exist on a shown window: under X11 the window of a hidden main window stays hidden (Linux gate 21.11.)
    if not win.winfo_ismapped():
        app.root.deiconify()
        win.deiconify()
        win.update()
    assert field.winfo_rootx() - win.winfo_rootx() == chips[0].master.winfo_rootx() - win.winfo_rootx(), (field.winfo_rootx(), chips[0].master.winfo_rootx())
    # "⋯" right in the chip row, only on Model Links; its menu: the two resets, Check files (Undo only over the page, 21.11.)
    more = app.b_set_more
    assert str(more.cget("text")) == "⋯" and more.master is row and more.pack_info()["side"] == "right"
    labels = [e[0] if e else "-" for e in app._links_menu_entries()]
    assert labels == ["Reset to startup", "Reset to default models", "-", "Check files"], labels
    chips[1].invoke()                        # a click on the chip shows the page
    win.update()
    assert nb.index(nb.select()) == 1 and not more.winfo_manager()
    nb.select(0)                             # a page chosen in code: the chip follows
    win.update()
    assert app._set_tab.get() == 0 and more.winfo_manager() == "pack"
    # The hidden test window is never drawn, so "⋯" sits at x 0 and the menu would start left of the screen; the clamp to the
    # screen edge then moved it on a PC whose only screen starts at 0 (PC A, 19.11.). Without the clamp only the alignment counts.
    screen = popmenu.PopMenu._screen
    popmenu.PopMenu._screen = lambda self: (-10**6, -10**6, 10**6, 10**6)
    try:
        app._links_menu()
    finally:
        popmenu.PopMenu._screen = screen
    win.update()
    menu = app._set_menu
    assert [e["label"] for e in menu.entries if e["type"] == "command"] == [x for x in labels if x != "-"]
    gx, gy, gw, gh = menu._geo
    assert menu._top is not None and abs(gx + gw - (more.winfo_rootx() + more.winfo_width())) <= 2, (menu._geo, more.winfo_rootx(), more.winfo_width())
    assert abs(gy - (more.winfo_rooty() + more.winfo_height())) <= 2, (menu._geo, more.winfo_rooty(), more.winfo_height())
    menu.unpost()

    # the model field (choice C): one line with the name and the red dot, its list has every page
    tabs = app.nb_models
    assert tabs.field_text == gui.models.BY_KEY[key].label and str(tabs.name.cget("image")), "no name or dot in the field"
    assert tabs.bar.winfo_reqheight() < app._px(40), tabs.bar.winfo_reqheight()
    tabs.open_list()
    win.update()
    assert [e["label"] for e in tabs.menu.entries] == [m.label for m in gui.models.MODELS] + ["Additional"]
    assert all(e["icon"] for e in tabs.menu.entries[:-1] if app.inv.tab_status(next(m.key for m in gui.models.MODELS if m.label == e["label"])).state != "ready")
    tabs.menu.unpost()

    # room between the field and the model's name (user 19.11.)
    assert int(tabs.body.pack_info()["pady"][0]) == gui.spacing.scale(ui_settings.MODEL_GAP), tabs.body.pack_info()
    # the modes name what the main window offers, with its tab names (user 19.11.): Edit canvas, Multi image edit, and the two
    # tabs without a mode of their own, Insert reference (Flux 3) and Scribble with reference
    shown = {k: [lb for _m, lb, st, _t in app._mode_cover(k) if st != "none"] for k in ("flux3", "flux2", "fibo", "minimax")}
    assert "Insert reference" in shown["flux3"] and "Insert reference" not in shown["flux2"]
    assert "Scribble with reference" in shown["flux3"] and "Scribble with reference" in shown["flux2"]
    assert "Scribble with reference" not in shown["fibo"]                      # Fibo: no reference at the scribble
    assert shown["minimax"] == ["Text to image", "Edit canvas", "Multi image edit", "Sketch to image", "Scribble on photo"], shown["minimax"]   # step 8 (21.11.)
    assert ui_settings.MODES_HEAD == "Supported Modes"
    assert "Edit" not in shown["flux3"] and "Multi Image Edit" not in shown["flux3"]

    # the page of that model: head line with "Show in PxC", mode tiles, the blue download button, Required / Optional
    page = app._set_pages[key]["rows"]
    all_w = widgets(page)
    labels = [str(w.cget("text")) for w in all_w if w.winfo_class() == "TLabel"]
    checks = [w for w in all_w if w.winfo_class() == "TCheckbutton"]
    show = next(c for c in checks if str(c.cget("text")) == "Show in PxC")
    assert show.pack_info()["side"] == "left"                   # left, the state chip on the right (user 20.11.)
    chips = [w for w in all_w if w.winfo_class() == "Label" and str(w.cget("text")) in ui_settings.STATE_CHIP.values()]
    assert [str(c.cget("text")) for c in chips] == ["✗ Not ready"] and chips[0].pack_info()["side"] == "right", chips
    assert str(chips[0].cget("bg")) == ui_settings.STATE_CHIP_BG[False] and str(chips[0].cget("fg")).lower() == "#ffffff"
    assert ui_settings.REQUIRED_HEAD in labels, labels
    name = gui.models.BY_KEY[key].label           # the name only in the field above (user 19.11.), no ◀
    assert not any(name in x or "◀" in x for x in labels), labels
    assert ui_settings.MODES_HEAD in labels
    # "Supported Modes" in the font of "Required" (user 19.11.)
    head_st = {str(w.cget("text")): str(w.cget("style")) for w in all_w if w.winfo_class() == "TLabel"}
    assert head_st[ui_settings.MODES_HEAD] == head_st[ui_settings.REQUIRED_HEAD] == "SetSection.TLabel", head_st
    assert "Standard settings need these weights:" not in labels and not any(t.startswith("Covers these modes") for t in labels)
    tiles = [w for w in all_w if hasattr(w, "mode_tiles")]
    assert tiles and tiles[0].mode_tiles, "no mode tiles"
    blue = [w for w in all_w if w.winfo_class() == "TButton" and str(w.cget("style")) == "SetAccent.TButton"]
    assert len(blue) == 1 and str(blue[0].cget("text")).startswith(ui_settings.ALL_FILES_BUTTON + " · "), blue

    # the fields: missing = red frame with "Missing · choose your file"; found = the file's name
    fields = [w for w in all_w if hasattr(w, "field_text")]
    missing = [f for f in fields if f.field_text == ui_settings.FIELD_MISSING]
    assert missing and str(missing[0].cget("highlightbackground")) == gui.NA_RED
    assert any(f.field_text.endswith(".safetensors") for f in fields)

    # the field's name wraps through _settings_wrap (no handler of its own, 19.11.): it has a wraplength once the page is shown
    names = [c for f in fields for c in f.winfo_children() if str(c.cget("text")) == f.field_text]
    assert names and all(int(str(c.cget("wraplength"))) > 0 for c in names), [c.cget("wraplength") for c in names]
    assert not [b for f in fields for b in f.bind("<Configure>").split("\n") if b.strip()], "a field has its own <Configure> handler"

    # only the page on screen is drawn when the window opens (user 19.11., choice A); another one on the first click of its chip
    others = [k for k in app._set_pages if k != key]
    assert all(not app._set_pages[k]["rows"].winfo_children() for k in others), [k for k in others if app._set_pages[k]["rows"].winfo_children()]
    tabs.open_list()
    win.update()
    tabs.menu.invoke(tabs.pages.index(app._set_pages["flux2"]["page"]))      # a click in the list of the field
    tabs.menu.unpost()                      # (a real click closes the list; invoke, like tk.Menu's, does not)
    win.update()
    assert tabs.field_text == gui.models.BY_KEY["flux2"].label

    # a linked file: blue, " · linked", and the arrow back to the expected file
    flux2 = [w for w in widgets(app._set_pages["flux2"]["rows"]) if hasattr(w, "field_text")]
    linked = [f for f in flux2 if f.field_text == "my_vae.safetensors" + ui_settings.FIELD_LINKED]
    assert linked and str(linked[0].cget("highlightbackground")) == gui.ACCENT_TEXT, [f.field_text for f in flux2]
    app._select_model_tab(key)              # back to the first page (drawn once: the same widgets as before)
    assert missing[0].winfo_exists()

    # a click on a field opens the search window right below it
    opened = []
    real = linkpicker.LinkPicker

    kw = {}

    class Rec:
        def __init__(self, root, at, cands=(), pinned=(), hints=None, mapped=None, **k):
            opened.append(at)
            kw.update(k, hints=hints)

        def close(self):
            pass
    linkpicker.LinkPicker = Rec
    try:
        f = missing[0]
        win.update()
        f.event_generate("<Button-1>")
        win.update()
        assert opened and opened[-1] == (f.winfo_rootx(), f.winfo_rooty() + f.winfo_height()), (opened, f.winfo_rootx())
        # dots instead of texts (user 21.11., choice 10A): the file in use green, a copy blue; no "in use" / "same size" text
        kw.clear()
        app._link_entries = lambda e: (["mine.safetensors", "copy.safetensors", "other.safetensors"], ["mine.safetensors"],
                                       {"mine.safetensors": ui_settings.HINT_IN_USE,
                                        "copy.safetensors": ui_settings.HINT_SAME + "x.safetensors",
                                        "other.safetensors": ui_settings.HINT_SIMILAR}, "mine.safetensors", "mine.safetensors")
        app._link_copies = []
        app._choose_for("x.safetensors")
        # a file equal to ANOTHER file PxC knows (another model's) is no replacement: no blue dot (user 21.11.)
        assert kw["strong"] == ["mine.safetensors"] and kw["same"] == [], kw
        assert kw["hints"] == {"other.safetensors": ui_settings.HINT_SIMILAR} and not kw.get("explain"), kw
        app._link_copies = ["copy.safetensors"]          # a renamed copy of the expected file: blue
        app._choose_for("x.safetensors")
        assert kw["same"] == ["copy.safetensors"], kw
        del app._link_entries
    finally:
        linkpicker.LinkPicker = real

    # after a change of a link: its message and Undo on top of the page (K2); Undo stays without a time limit and takes back
    # one change per click until none is left, then the button goes (user 21.11.)
    def top_texts():
        return [str(w.cget("text")) for w in widgets(app.f_set_top) if w.winfo_class() in ("TLabel", "TButton")]
    app._map_undo.clear()
    start = cfgmod.model_map()
    app.v_status.set("")
    app._link_models("qwen_image_vae.safetensors", "flux2-vae.safetensors")
    assert "Linked" not in app.v_status.get(), app.v_status.get()      # only in the settings, not in the status line (user 21.11.)
    first = cfgmod.model_map()
    app._link_models("qwen_image_vae.safetensors", "")
    win.update()
    assert len(app._map_undo) == 2 and cfgmod.model_map() == start
    texts = top_texts()
    assert "Undo" in texts and len(texts) == 2, texts
    assert not hasattr(ui_settings, "LINK_MSG_MS") and not hasattr(app, "_link_msg_job")     # no timer any more
    shown = next(k for k, p in app._set_pages.items() if p["page"] is app.nb_models.select())
    page_rows = app._set_pages[shown]["rows"].winfo_children()
    assert page_rows
    app._link_msg_gone()                     # nothing hides it while something is left to take back
    win.update()
    assert "Undo" in top_texts()
    app._link_undo()
    win.update()
    assert cfgmod.model_map() == first and "Undo" in top_texts()
    app._link_undo()
    win.update()
    assert cfgmod.model_map() == start and app._map_undo == []
    texts = top_texts()
    assert "Undo" not in texts and texts == ["Undone: nothing more to take back."], texts
    app._link_undo()                         # nothing left: no change
    assert cfgmod.model_map() == start
    page_rows = app._set_pages[shown]["rows"].winfo_children()      # (an Undo changes the links: the page is drawn again)
    app._link_msg_gone()
    win.update()
    assert not app.f_set_top.winfo_children() and app._link_msg == ""
    assert all(w.winfo_exists() for w in page_rows), "the page was drawn again"
    app._settings_fill()                     # nothing else changed: no new drawing
    assert all(w.winfo_exists() for w in page_rows)

    # the chain symbol is gone from the file rows
    src = (ROOT / "pccomfy" / "ui_settings.py").read_text(encoding="utf-8")
    assert "Use another file of yours for this one" not in src and "LINKS_INTRO" not in src
    app._settings_close()
    app.root.destroy()
    shutil.rmtree(TMP, ignore_errors=True)
    print("ok model links design")


if __name__ == "__main__":
    main()
