"""Save image in the window (12.11.): the hamburger menu at the right end of the footer (Save image, Copy canvas; the copy button
is gone from the row), Ctrl+S, the file name taken from PhotoCraft's active document, and the "Save image" section of the settings
(folder, format, file name with a live example). Hidden real Tk window; PhotoCraft is faked, nothing is saved to the disk.

    python tests/test_save_gui.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-save-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    from tkinter import ttk
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import comfy, config as cfgmod, gui, popmenu, savefile, ui_settings  # noqa: E402
from pccomfy.bridge import BridgeError  # noqa: E402
from pccomfy.popmenu import PopMenu  # noqa: E402


class FakePC:
    def __init__(self, name):
        self.name = name

    def session(self):
        return {"active": 1, "documents": [{"name": "other.png"}, {"name": self.name}]}


class FakeBridge:
    def __init__(self, name="beach.jpg", fail=None):
        self.pc, self.fail = FakePC(name), fail

    def cancel(self):
        pass

    def canvas_image(self):
        if self.fail:
            raise self.fail
        return "picture"


def saved_with(app, bridge):
    """Runs Save image against a fake bridge; returns (the keywords savefile got, the event)."""
    got = {}

    def fake_save(img, **kw):
        got.update(kw, img=img)
        return Path("C:/x/beach-file.png")
    real, savefile.save_image = savefile.save_image, fake_save
    gui.savefile.save_image = fake_save
    try:
        app.bridge = bridge
        app.save_image()
        app.worker.join(5)
    finally:
        savefile.save_image = real
    return got, app.events.get_nowait()


def main():
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.root.update_idletasks()

    # ---- the footer: clock, scissors, hamburger (far right); the copy button is gone from the row ----
    assert not hasattr(app, "b_copy_canvas")
    right = [w for w in app.f_foot.pack_slaves() if w.pack_info()["side"] == "right"]
    assert right[:3] == [app.b_menu, app.b_cut, app.b_history], right      # packed first = the far right
    assert app.b_menu.cget("image") and app.b_cut.cget("image") and app.b_history.cget("image")
    assert app.b_menu.cget("command")

    # ---- the menu: Save and Copy first (the batch entries and the queue follow, test_batch_gui.py), each with an icon and
    # a short text; a click runs them ----
    calls = []
    app.save_image = lambda: calls.append("save")
    app.copy_canvas = lambda: calls.append("copy")
    shown = []
    real_popup = PopMenu.tk_popup
    PopMenu.tk_popup = lambda self, *a, **k: shown.append((self, k))
    try:
        app._footer_menu()
    finally:
        PopMenu.tk_popup = real_popup
    menu, kw = shown[0]
    assert kw.get("above_w") is app.b_menu
    assert [e["label"] for e in menu.entries][:2] == ["Save image (Ctrl+S)", "Copy canvas"], menu.entries
    cmds = [e for e in menu.entries if e["type"] != "separator"]      # one line above the two resets of the page (16.11.)
    assert all(e["icon"] is not None for e in cmds) and all(e["type"] == "command" for e in cmds)
    assert all(e["icon_hot"] is not None and e["icon_hot"] is not e["icon"] for e in cmds)   # white on hover (user 12.11.)
    assert menu.entries[0]["tip"] and "save" in menu.entries[0]["tip"].lower(), menu.entries[0]   # Save image has a hover hint (user 12.11.)
    assert all(e["tip"] for e in cmds[-2:]), cmds[-2:]       # the two resets keep the hint of the former "Reset page" button (16.11.)
    assert not any(e["tip"] for e in cmds[1:-2]), menu.entries                                     # the others have none
    menu.entries[0]["command"]()
    menu.entries[1]["command"]()
    assert calls == ["save", "copy"], calls
    del app.save_image, app.copy_canvas

    # a real popup: the icon column is in the row width and the menu sits above the button
    m = PopMenu(app.root)
    plain = PopMenu(app.root)
    plain.add_command(label="Save image (Ctrl+S)")
    icon = app._icon("save", px=gui.SMALL_ICON_PX)[0]
    m.add_command(label="Save image (Ctrl+S)", icon=icon)
    plain._measure()
    m._measure()
    assert m._icon_w > 0 and plain._icon_w == 0 and m._measure()[0] == plain._measure()[0] + m._icon_w
    app.root.deiconify()
    app.root.update()
    m.tk_popup(0, 0, above_w=app.b_menu)
    try:
        x, y, w, h = m.geometry()
        assert y + h <= app.b_menu.winfo_rooty() or y == 0, (y, h)         # (clamped to the screen's top edge when there is no room)
        assert any(m._cv.type(i) == "image" for i in m._cv.find_all())
        # the hover icon: on the active row the white one is drawn, on the others the normal one
        hot = app._icon("save", gui.ON_ACCENT, px=gui.SMALL_ICON_PX)[0]
        m.entries[0]["icon_hot"] = hot
        m._active = 0
        m._draw_row(0)
        assert m._cv.itemcget(m._cv.find_withtag("icon0")[0], "image") == str(hot)
        m._active = None
        m._draw_row(0)
        assert m._cv.itemcget(m._cv.find_withtag("icon0")[0], "image") == str(icon)
    finally:
        m.unpost()
        app.root.withdraw()

    # ---- Ctrl+S: bound on the window, the prompt field has no Ctrl+S of its own ----
    assert app.root.bind("<Control-s>") and app.root.bind("<Control-S>")
    assert not app.t_prompt.bind("<Control-s>") and not app.root.bind_class("Text", "<Control-s>")

    # ---- the file: named after the document; function and seed only for the result of the last run ----
    app._last_result = {"mode": "upscale", "seed": 83421, "doc": "beach.jpg"}
    got, ev = saved_with(app, FakeBridge("beach.jpg"))
    assert got["img"] == "picture" and got["name"] == "beach" and got["seed"] == 83421 and got["function"] == savefile.function_label("upscale")
    assert ev == ("note", "Saved: beach-file.png"), ev
    got, ev = saved_with(app, FakeBridge("holiday.png"))               # another document: nothing of the last run
    assert got["name"] == "holiday" and got["seed"] is None and got["function"] == "", got
    app._last_result = None
    got, ev = saved_with(app, FakeBridge("beach.jpg"))                 # no run yet
    assert got["seed"] is None and got["function"] == "" and got["name"] == "beach"
    got, ev = saved_with(app, FakeBridge(fail=BridgeError("Open a document in PhotoCraft first.")))
    assert ev == ("note-error", "Error: Open a document in PhotoCraft first.") and not got
    real = savefile.save_image
    gui.savefile.save_image = lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied"))
    app.bridge = FakeBridge()
    app.save_image()
    app.worker.join(5)
    gui.savefile.save_image = real
    kind, text = app.events.get_nowait()
    assert kind == "note-error" and "could not be saved" in text and "denied" in text, (kind, text)
    app._status("")
    app.events.put(("lastrun", {"mode": "edit", "seed": 5, "doc": "a.png"}))     # the event loop keeps the last result
    app.root.after = lambda *a, **k: None
    app._poll()
    assert app._last_result == {"mode": "edit", "seed": 5, "doc": "a.png"}

    # ---- the settings section ----
    for key in (savefile.SAVE_FOLDER_KEY, savefile.SAVE_FORMAT_KEY, savefile.SAVE_PATTERN_KEY):
        cfgmod.set_setting(key, None)
    frame = ttk.Frame(app.root)
    app._save_image_row(frame)
    ex = lambda: str(app.lbl_save_example.cget("text"))            # noqa: E731
    assert app.v_save_fmt.get() == "PNG" and app.v_save_pattern.get() == savefile.DEFAULT_PATTERN
    assert ex().startswith("Example: ") and ex().endswith(".png")
    assert app.lbl_save_folder.cget("text") == str(savefile.load_settings().folder)
    assert list(app.cb_save_fmt.cget("values")) == ["PNG", "JPG", "WebP"]
    assert list(app.cb_save_pattern.cget("values")) == list(savefile.PATTERNS) + ["Custom…"]
    assert [b.cget("text") for b in app.b_save_chips] == ["{" + n + "}" for n in savefile.PLACEHOLDERS]
    assert not app.f_save_custom.winfo_manager()

    app.v_save_fmt.set("JPG")                                      # format
    app._save_format_pick()
    assert cfgmod.get_setting(savefile.SAVE_FORMAT_KEY) == "jpg" and ex().endswith(".jpg")
    app.v_save_fmt.set("WebP")
    app._save_format_pick()
    assert cfgmod.get_setting(savefile.SAVE_FORMAT_KEY) == "webp" and ex().endswith(".webp")

    app.v_save_pattern.set(savefile.PATTERNS[1])                   # one of the four patterns
    app._save_pattern_pick()
    assert cfgmod.get_setting(savefile.SAVE_PATTERN_KEY) == savefile.PATTERNS[1]
    assert ex() == "Example: " + savefile.example_name(savefile.PATTERNS[1], "webp")

    app.v_save_pattern.set("Custom…")                              # your own: the field and the placeholder buttons appear
    app._save_pattern_pick()
    assert app.f_save_custom.winfo_manager() == "pack"
    app.v_save_custom.set("{name}_x_{counter}")
    assert cfgmod.get_setting(savefile.SAVE_PATTERN_KEY) == "{name}_x_{counter}"
    assert ex() == "Example: " + savefile.example_name("{name}_x_{counter}", "webp")
    app.v_save_custom.set("{bogus}")                               # invalid: the error replaces the example, nothing is saved
    assert cfgmod.get_setting(savefile.SAVE_PATTERN_KEY) == "{name}_x_{counter}"
    assert not ex().startswith("Example") and ex() == savefile.validate_pattern("{bogus}")
    app.v_save_custom.set("")
    assert not ex().startswith("Example") and cfgmod.get_setting(savefile.SAVE_PATTERN_KEY) == "{name}_x_{counter}"
    app.v_save_custom.set("pic-")                                  # a placeholder button inserts at the cursor
    app.e_save_custom.icursor("end")
    next(b for b in app.b_save_chips if b.cget("text") == "{seed}").invoke()
    assert app.v_save_custom.get() == "pic-{seed}" and cfgmod.get_setting(savefile.SAVE_PATTERN_KEY) == "pic-{seed}"
    assert ex() == "Example: " + savefile.example_name("pic-{seed}", "webp")
    app.v_save_pattern.set(savefile.PATTERNS[0])                   # back to a ready pattern hides the field again
    app._save_pattern_pick()
    assert not app.f_save_custom.winfo_manager()

    from tkinter import filedialog                                 # the folder: Change… and Default
    real_ask = filedialog.askdirectory
    target = tempfile.mkdtemp(prefix="pccomfy-folder-")
    filedialog.askdirectory = lambda **k: target
    try:
        app.b_save_folder.invoke()
    finally:
        filedialog.askdirectory = real_ask
    assert Path(cfgmod.get_setting(savefile.SAVE_FOLDER_KEY)) == Path(target) and Path(str(app.lbl_save_folder.cget("text"))) == Path(target)
    filedialog.askdirectory = lambda **k: ""                       # cancelled: nothing changes
    try:
        app.b_save_folder.invoke()
    finally:
        filedialog.askdirectory = real_ask
    assert Path(cfgmod.get_setting(savefile.SAVE_FOLDER_KEY)) == Path(target)
    app.b_save_default.invoke()
    assert cfgmod.get_setting(savefile.SAVE_FOLDER_KEY) is None
    assert app.lbl_save_folder.cget("text") == str(savefile.load_settings().folder)

    # a saved custom pattern comes back as "Custom…" with its text when the window is built again
    cfgmod.set_setting(savefile.SAVE_PATTERN_KEY, "my-{date}")
    frame2 = ttk.Frame(app.root)
    app._save_image_row(frame2)
    assert app.v_save_pattern.get() == "Custom…" and app.v_save_custom.get() == "my-{date}" and app.f_save_custom.winfo_manager() == "pack"
    assert "_save_image_row" in ui_settings.SettingsMixin._other_settings.__code__.co_names
    app.root.destroy()
    print("ALL OK (Save image: footer menu, Ctrl+S, file name, settings)")


if __name__ == "__main__":
    main()
