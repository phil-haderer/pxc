"""The stock text of a function always wins over your own text (user 11.11.; until then your text stayed, user 3.11.):
Upscale, Refine, Scribble on photo and the style of Sketch to image put their text into the field, your text waits aside
and comes back with the next function without a stock text. An edited stock text never pushes your own text out.
Real Tk window (hidden); skipped when Tk cannot open a window.

    python tests/test_stock_prompt_wins.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-spw-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui, models  # noqa: E402


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.cb_workflow["values"] = [gui.BUILTIN] + sorted({w for m in models.MODELS for w in m.workflows()})
    t = app.t_prompt
    text = lambda: t.get("1.0", "end").strip()      # noqa: E731

    def put(s):
        t.delete("1.0", "end")
        t.insert("1.0", s)

    def go(mode):
        app.v_mode.set(mode)
        app._on_mode()
        app.root.update()

    app.v_model.set("flux2")
    app.v_mode.set("edit")
    app._on_model()
    app.root.update()
    up = models.FLUX2.modes["upscale"].prompt_hint
    refine = models.FLUX2.modes["refine"].prompts[0][1]

    # 1. own text -> Refine (ready-made prompts) and Upscale: the stock text wins; back in Edit canvas the own text
    go("edit")
    put("make it night")
    go("refine")
    assert text() == refine, text()
    go("upscale")
    assert text() == up, text()
    go("edit")
    assert text() == "make it night", text()

    # 2. an edited stock text does not push the own text out; leaving for a plain function brings the own text back
    go("upscale")
    put("An old photo of a harbour. " + up)
    go("refine")
    assert text() == refine, text()
    go("inpaint")
    assert text() == "make it night", text()

    # 3. Ctrl+Z (undo) in the field brings the own text back after the stock text came in
    go("upscale")
    assert text() == up, text()
    t.edit_undo()
    assert text() == "make it night", text()
    go("edit")

    # 4. Remove object keeps the field usable (the name of the object, every model since remove_text) but empty (user
    # 21.11.): your text waits aside through Remove and Upscale and comes back later
    put("a red bicycle")
    go("remove")
    assert str(t.cget("state")) == "normal" and text() == "", text()
    go("upscale")
    assert text() == up, text()
    go("edit")
    assert text() == "a red bicycle", text()

    # 5. Scribble on photo: its sentence wins, the own text comes back with Edit canvas
    go("scribble")
    assert text() == models.SKETCH_SCRIBBLE, text()
    go("edit")
    assert text() == "a red bicycle", text()

    # 6. Sketch to image with a style chosen before: the style wins; without one the own text stays
    styles = getattr(app, "_mode_styles", {}).get("sketch", {})
    assert styles, "no Sketch styles loaded"
    name, style = next(iter(styles.items()))
    cfgmod.set_setting(gui.STYLE_KEY + "sketch", name)
    go("sketch")
    assert text() == style, text()
    go("edit")
    assert text() == "a red bicycle", text()
    cfgmod.set_setting(gui.STYLE_KEY + "sketch", "")
    go("sketch")
    assert text() == "a red bicycle", text()
    go("edit")

    # 7. Expand still empties the field and the own text comes back
    go("outpaint")
    assert text() == "", text()
    go("edit")
    assert text() == "a red bicycle", text()

    # 8. Remove with a named object (user 21.11.): picking it always empties the field (the grey "Name what to remove"
    # shows), the object typed there is dropped on the way out, and the own text comes back
    assert models.FLUX2.modes["remove"].remove_text
    go("remove")
    assert text() == "" and str(t.cget("state")) == "normal", text()
    put("car")
    go("edit")
    assert text() == "a red bicycle", text()
    go("remove")
    assert text() == "", text()
    put("car")
    go("upscale")
    assert text() == up, text()
    go("edit")
    assert text() == "a red bicycle", text()
    app.root.destroy()
    print("ALL OK (stock prompt wins over own text)")


if __name__ == "__main__":
    main()
