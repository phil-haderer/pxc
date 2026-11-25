# tags: sketch
"""Sketch (docs/archiv/sketch-plan.md, build steps 3 and 4, 10.11.): the mode `sketch` of the four edit models, its templates in the
prompt field, the lock of only the tab Sketch without the upsampler, and "Scribble on photo" in the bridge (find the scribble,
generate only a crop, put it back with a fading layer mask, hide the scribble layer). Bridge against the PhotoCraft simulator
of test_reference_mode, window with the stubbed Tk.

    python tests/test_sketch_mode.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# a data folder of its own before pccomfy is imported: the window part saves the chosen style (settings.json), which must
# never land in the plugin's real data folder (it did once, 10.11.)
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-sketch-")
os.environ["PCCOMFY_NO_TIPS"] = "1"

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as tr  # noqa: E402
from pccomfy import bridge, manifest, models, scribble, workflows  # noqa: E402
from pccomfy.bridge import BridgeError, Request  # noqa: E402

ROOT = tr.ROOT
W, H = tr.W, tr.H
UPS = "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors"
W4 = "qwen3.5_9b_w4a8_gptq.safetensors"      # Qwen's Sketch writer since 16.11. evening (no upsampler)
VL4 = "qwen3vl_4b_int8_convrot.safetensors"        # Flux 2's Sketch writer (10.11.)


def photo():
    """A photo-like picture: smooth colours and a little noise (no pure red or green)."""
    rng = np.random.default_rng(3)
    y, x = np.mgrid[0:H, 0:W]
    a = np.stack([90 + x * 0.3, 110 + y * 0.4, 140 + 0 * x], -1) + rng.normal(0, 6, (H, W, 3))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def strokes(colour, box=(120, 30, 170, 80), width=2):
    """Thin scribble strokes on an empty layer."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = box
    for k in range(5):
        d.line([(x0, y0 + k * (y1 - y0) // 4), (x1, y1 - k * (y1 - y0) // 4)], fill=colour + (255,), width=width)
    return im


def doc(layers):
    tmp = tempfile.mkdtemp()
    pc = tr.FakePC(tmp)
    pc.docs.append(tr.Doc("photo.png", [{"id": i + 1, "img": im, "visible": True, "name": f"L{i + 1}"} for i, im in enumerate(layers)]))
    b = bridge.Bridge(pc, tr.FakeComfy(), tmp)
    return pc, b


def run(pc, b, prompt, wf="flux2-klein-sketch.json", scribble_on=True, enhance=True):
    req = Request(mode="edit", workflow=str(ROOT / "workflows" / wf), enhance=enhance, layer_mask="none", scribble=scribble_on)
    req.params = workflows.GenParams(prompt=prompt, seed=7)
    return b.run(req)


def sent_prompt(b):
    g = b.comfy.graphs[-1]
    for n in g.values():
        if "pc:prompt" in n.get("_meta", {}).get("title", ""):
            return n["inputs"].get("prompt") or n["inputs"].get("text") or ""
    return ""


def test_models_and_texts():
    for key in ("flux3", "flux2", "qwen", "fibo"):
        spec = models.BY_KEY[key].modes["sketch"]
        # Sketch to image (plan B, 10.11.): no templates, the style comes from Styles; an empty field starts empty
        assert spec.run_as == "edit" and spec.prompts == () and spec.prompt_hint == "" and spec.prompt_tip == models.SKETCH_TIP
        assert spec.settings["enhance"] is (key != "fibo"), key          # the writer always, Fibo without one
        assert spec.workflow == {"flux3": "flux3-klein-sketch.json", "flux2": "flux2-klein-sketch.json",
                                 "qwen": "qwen-image-21-sketch.json", "fibo": "fibo2-edit.json"}[key]
        sc = models.BY_KEY[key].modes["scribble"]            # Scribble on photo: its own tab, the same workflow and values
        assert (sc.workflow, sc.settings, sc.run_as) == (spec.workflow, spec.settings, "edit")
        assert sc.prompts == models.SCRIBBLE_PROMPTS and sc.prompt_hint == models.SKETCH_SCRIBBLE and sc.prompt_tip == models.SCRIBBLE_TIP
    for key in ("krea2", "moss"):
        assert "sketch" not in models.BY_KEY[key].modes and "scribble" not in models.BY_KEY[key].modes
    assert [lb for lb, _t, _tip in models.SCRIBBLE_PROMPTS] == ["Scribble on photo", "Scribble with reference"]    # 15.11.
    # old saved runs and states: Scribble on photo was a template of Sketch
    assert models.legacy_sketch_mode("sketch", models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "a dog")) == "scribble"
    assert models.legacy_sketch_mode("sketch", models.SKETCH_PHOTO) == "sketch"
    assert models.legacy_sketch_mode("edit", models.SKETCH_SCRIBBLE) == "edit"
    assert models.legacy_sketch_mode("sketch", models.SKETCH_SCRIBBLE, models.EDIT_TABS_VERSION) == "sketch"    # saved since plan B
    assert [lb for lb, _t, _tip in models.SKETCH_PROMPTS] == ["Photo", "Illustration", "Scribble on photo"]
    for _lb, text, _tip in models.SKETCH_PROMPTS:
        assert models.SKETCH_MARK in text and text in models.STOCK_PROMPTS
    # the wordings of the test rounds (tests/live_sketch.py); without "expressive faces" (round 3b)
    assert "expressive faces" not in models.SKETCH_ILLUSTRATION and "cel shading" in models.SKETCH_ILLUSTRATION
    # the marker: replaced = the sentence as typed; left in = the generic sentence of the test rounds
    assert bridge.sketch_text(models.SKETCH_PHOTO.replace(models.SKETCH_MARK, "a house")).startswith("Turn this sketch of a house into")
    assert bridge.sketch_text(models.SKETCH_PHOTO).startswith("Turn this sketch into a realistic photograph.")
    assert bridge.sketch_text(models.SKETCH_SCRIBBLE).startswith("Replace the coloured scribbles with what they show, realistic")
    assert models.SKETCH_MARK not in bridge.sketch_text("A " + models.SKETCH_MARK + " here")
    assert bridge.sketch_text("make it night") == "make it night"
    # 21.11. (user): the mark is SUBJECT everywhere; a prompt saved with the old <WHAT IT SHOWS> still works and is a stock text
    assert models.SKETCH_MARK == "SUBJECT" and "<WHAT IT SHOWS>" in models.OLD_SKETCH_MARKS
    old_scribble = models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "<WHAT IT SHOWS>")
    assert bridge.sketch_text(old_scribble) == bridge.sketch_text(models.SKETCH_SCRIBBLE)
    assert old_scribble in models.STOCK_PROMPTS
    assert models.SCRIBBLE_TIP == "Scribble in bright red or green and replace SUBJECT with what goes there."
    assert models.SKETCH_TIP == "Replace SUBJECT with what your sketch shows and include its surroundings: “a dog in an empty street”."   # user 25.11.


def test_manifest_lock_only_the_tab():
    assert manifest.mode_alone("flux3", "sketch") and UPS in manifest.mode_extra("flux3", "sketch")
    assert manifest.mode_alone("qwen", "sketch") and W4 in manifest.mode_extra("qwen", "sketch")
    assert UPS not in manifest.mode_extra("qwen", "sketch") + manifest.mode_extra("qwen", "scribble")
    for key in ("flux3", "flux2", "qwen", "fibo"):          # Scribble on photo needs what Sketch needs (plan B)
        assert manifest.mode_extra(key, "scribble") == manifest.mode_extra(key, "sketch"), key
    # Flux 2 writes with qwen3vl 4B since 10.11. (option B): no upsampler, the 4B file locks only its tab
    assert manifest.mode_alone("flux2", "sketch") and manifest.mode_extra("flux2", "sketch") == (VL4,)
    assert not manifest.mode_alone("fibo", "sketch") and manifest.mode_extra("fibo", "sketch") == ()
    assert not manifest.mode_alone("flux3", "upscale")
    import test_settings_ui as su
    from pccomfy import inventory
    nodes = su.NODES | {n["class_type"] for f in (ROOT / "workflows").glob("*.json") for n in json.loads(f.read_text(encoding="utf-8")).values()}
    inv = inventory.Inventory(su.lists_without(clip=UPS), nodes)
    assert inv.mode_status("qwen", "sketch").state == "ready"            # Qwen writes with its own w4a8 (16.11. evening)
    assert not any(f.name == UPS for f, _fd, _lv in next(r for r in inv.rows() if r["key"] == "qwen")["files"])
    now4 = inventory.Inventory(su.lists_without(clip=W4), nodes)
    assert now4.mode_status("qwen", "sketch").state == now4.mode_status("qwen", "scribble").state == "missing"
    assert now4.tab_status("qwen").state == "ready", now4.tab_status("qwen")     # the model stays offered (user 9.11.)
    row = next(r for r in now4.rows() if r["key"] == "qwen")
    assert [lv for f, _fd, lv in row["files"] if f.name == W4] == ["optional"]   # listed with the additional features
    # Flux 3: since 16.11. its Remove needs the upsampler (user, choice a), so the whole model is locked without it
    assert inv.tab_status("flux3").state == "missing" and UPS in [f.name for f in inv.tab_status("flux3").missing]
    assert inv.mode_status("fibo", "sketch").state == "ready"
    assert inv.mode_status("flux2", "sketch").state == "ready"           # needs no upsampler any more
    assert not any(f.name == UPS for f, _fd, _lv in next(r for r in inv.rows() if r["key"] == "flux2")["files"])
    no4b = inventory.Inventory(su.lists_without(clip=VL4), nodes)
    assert no4b.mode_status("flux2", "sketch").state == "missing" and no4b.tab_status("flux2").state == "ready"
    full = inventory.Inventory(su.td.full_lists(), nodes)
    assert all(full.mode_status(k, "sketch").state == "ready" for k in ("flux3", "flux2", "qwen", "fibo"))


def test_scribble_on_its_own_layer():
    pc, b = doc([photo(), strokes((40, 90, 230))])          # blue: only the layer finds it, the colour search does not
    res = run(pc, b, models.SKETCH_SCRIBBLE)
    assert res["scribble"] == "layer"
    r = res["region"]
    assert (r["w"], r["h"]) != (W, H) and r["x"] > 60, r       # only the crop around the scribble was generated
    assert "what they show" in sent_prompt(b) and models.SKETCH_MARK not in sent_prompt(b)
    d = pc.docs[0]
    top = d.layers[-1]
    assert top["name"].startswith("AI edit") and top.get("mask") is not None
    m = np.asarray(top["mask"])
    assert m[:, : max(0, r["x"] - 1)].max() == 0 and m[60, 145] == 255       # nothing outside the crop, opaque over the scribble
    scribble_layer = next(l for l in d.layers if l.get("name") == "L2")
    assert scribble_layer["visible"] is False                                # hidden after the run (user 9.11.)
    assert next(l for l in d.layers if l.get("name") == "L1")["visible"]
    assert len(pc.docs) == 1                                                 # the throw-away duplicates are closed


def test_minimax_scribble_object_mask():
    """MiniMax Scribble on photo (user 21.11., "Mask follows object"): it draws larger than the scribble, so the layer mask
    follows the object (scribble.object_mask) instead of fading out from the scribble's box; the other models keep the fade."""
    flags = {m.key: m.modes["scribble"].scribble_object_mask for m in models.MODELS if "scribble" in m.modes}
    assert flags.pop("minimax") is True and not any(flags.values()), flags
    from pccomfy import scribble as scr
    calls, real = [], scr.object_mask
    scr.object_mask = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        for on in (False, True):
            base = photo()
            base.alpha_composite(strokes((252, 2, 2), box=(20, 20, 70, 70), width=3))
            pc, b = doc([base])
            req = Request(mode="edit", workflow=str(ROOT / "workflows" / "minimax-h3-image-edit.json"), enhance=False,
                          layer_mask="none", scribble=True, scribble_object=on, gen_mp=4)
            req.params = workflows.GenParams(prompt=models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "a car"), seed=7)
            b.run(req)
            assert pc.docs[0].layers[-1].get("mask") is not None
            assert len(calls) == (1 if on else 0), (on, calls)
    finally:
        scr.object_mask = real

def test_scribble_by_colour():
    base = photo()
    base.alpha_composite(strokes((252, 2, 2), box=(20, 20, 70, 70), width=3))
    pc, b = doc([base])
    res = run(pc, b, models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "a red vintage car"))
    assert res["scribble"] == "red" and res["region"]["x"] < 40
    assert "a red vintage car" in sent_prompt(b)
    # green wins over red (decided 9.11.)
    base = photo()
    base.alpha_composite(strokes((252, 2, 2), box=(20, 20, 70, 70), width=3))
    base.alpha_composite(strokes((0, 255, 0), box=(130, 40, 180, 90), width=3))
    pc, b = doc([base])
    res = run(pc, b, models.SKETCH_SCRIBBLE)
    assert res["scribble"] == "green" and res["region"]["x"] > 80


def test_no_scribble_no_run():
    pc, b = doc([photo()])
    try:
        run(pc, b, models.SKETCH_SCRIBBLE)
    except BridgeError as e:
        assert str(e) == models.NO_SCRIBBLE
    else:
        raise AssertionError("ran without a scribble")
    assert b.comfy.graphs == [] and len(pc.docs[0].layers) == 1
    # a filled shape on its own layer is no scribble layer (rule "thin strokes", user 9.11.)
    blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    blob.paste((40, 90, 230, 255), (100, 20, 170, 90))
    pc, b = doc([photo(), blob])
    try:
        run(pc, b, models.SKETCH_SCRIBBLE)
        raise AssertionError("a filled blob counted as a scribble")
    except BridgeError as e:
        assert str(e) == models.NO_SCRIBBLE


def test_whole_sketch():
    pc, b = doc([photo()])
    res = run(pc, b, models.SKETCH_PHOTO, scribble_on=False)
    assert res["scribble"] == "" and (res["region"]["w"], res["region"]["h"]) == (W, H)
    assert sent_prompt(b).startswith("Turn this sketch into")
    top = pc.docs[0].layers[-1]
    assert top.get("mask") is None and len(pc.docs[0].layers) == 2           # a new layer on top, no layer mask
    # Fibo without a writer: the text goes in as it is
    pc, b = doc([photo()])
    run(pc, b, models.SKETCH_PHOTO.replace(models.SKETCH_MARK, "a barn"), wf="fibo2-edit.json", scribble_on=False, enhance=False)
    assert "a barn" in json.dumps(b.comfy.graphs[-1])


def test_window():
    import shutil
    import test_gui_presets as t
    gui, cfgmod = t.gui, t.cfgmod
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in gui.models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names

    def pick(model, mode):
        app.v_model.set(model)
        app.v_mode.set(mode)
        app._on_model()

    def tab(key):
        app.v_edtab.set(key)
        app._edtab_clicked()

    def prompt():
        return app.t_prompt.get("1.0", "end").strip()

    def where(key):         # the place in the list of the Edit tabs (a list since 20.11.); None when not offered
        return app._edtab_shown.index(key) if key in app._edtab_shown else None

    pick("flux3", "edit")
    app._edtabs_ensure()
    app._edtabs_update()
    # plan B (10.11.): the edit tabs first, then Sketch to image and Scribble on photo; Insert reference is a tab of Fill
    # since 11.11. (step 4)
    assert [where(k) for k in ("edit", "multi", "sketch", "scribble")] == [0, 1, 2, 3]
    assert where("bbox") is None and where("fill") is None
    app.t_prompt.delete("1.0", "end")
    tab("sketch")
    assert app.v_mode.get() == "sketch" and app.v_fn.get() == "edit"
    assert prompt() == "", repr(prompt()[:80])                       # no style chosen yet: empty with the grey placeholder
    assert app._hint_text == models.SKETCH_TIP
    assert not app._llm_row_wanted()                                               # no LLM row: the writer always runs
    app._apply_style(models.SKETCH_PHOTO, "Realistic photo")
    req = app._request()
    assert req.mode == "edit" and req.enhance and not req.scribble and req.workflow.endswith("flux3-klein-sketch.json")
    tab("scribble")
    assert app.v_mode.get() == "scribble" and app.v_fn.get() == "edit"
    assert prompt() == models.SKETCH_SCRIBBLE and app.v_sketch.get() == "Scribble on photo" and app._hint_text == models.SCRIBBLE_TIP
    req = app._request()
    assert req.scribble and req.enhance and req.mode == "edit" and req.workflow.endswith("flux3-klein-sketch.json")
    tab("sketch")                                                    # the style chosen last comes back
    assert prompt() == models.SKETCH_PHOTO and not app._request().scribble
    # Flux 2 (no Insert reference): 2 + 2
    pick("flux2", "sketch")
    assert app.v_mode.get() == "sketch" and app.v_edtab.get() == "sketch"
    assert [where(k) for k in ("edit", "multi", "sketch", "scribble")] == [0, 1, 2, 3] and where("bbox") is None
    # Fibo: no writer, so no LLM enhancement
    pick("fibo", "sketch")
    req = app._request()
    assert not req.enhance and req.workflow.endswith("fibo2-edit.json")
    # a model without Sketch: back to Edit canvas
    pick("krea2", "txt2img")
    pick("flux3", "sketch")
    pick("moss", "txt2img")
    assert app.v_mode.get() == "txt2img"
    # an edited text stays when the tab changes
    pick("qwen", "scribble")
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "Replace the coloured scribbles with a dog")
    pick("qwen", "edit")
    assert prompt() == "Replace the coloured scribbles with a dog"
    # an old saved Sketch run with the scribble sentence loads into the tab Scribble on photo
    from pccomfy import history as runhistory
    before = {k: v for k, v in app._collect().items() if k != "edit_tabs"}       # saved before plan B: no version
    old = runhistory.entry("Sketch 3", "Qwen Image 2.1", {**before, "mode": "sketch",
                                                           "prompt": models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "a dog")})
    app.load_history(old)
    assert app.v_mode.get() == "scribble" and app._request().scribble
    # a Sketch run from the history (way A, user 10.11.): the written prompt runs as it is, without the upsampler
    from pccomfy import history as runhistory
    pick("flux2", "sketch")
    assert app._request().enhance
    written = "A realistic photograph of a red barn in a green summer meadow, soft morning light."
    e = runhistory.entry("Sketch", "Flux 2 Klein Edit", app._collect(), llm=written)
    pick("qwen", "edit")
    app.load_history(e)
    assert app.v_model.get() == "flux2" and app.v_mode.get() == "sketch" and prompt() == written
    assert not app._request().enhance and app._hint_text == models.WRITTEN_TIP
    app.t_prompt.insert("end", " A dog.")                     # an edited written prompt still runs as it is
    assert not app._request().enhance
    app._history_begin(app._request())                        # the run keeps it as written: it loads back the same way
    assert app._hist_run["llm"].endswith("A dog.")
    app._apply_style(models.SKETCH_PHOTO, "Realistic photo")  # a style: the writer again
    assert app._request().enhance and app._hint_text == models.SKETCH_TIP
    app.load_history(e)
    pick("flux3", "sketch")                                   # another model: the upsampler again
    assert app._request().enhance
    app.load_history(e)
    app.v_edtab.set("edit")                                   # another tab
    app._edtab_clicked()
    app.v_edtab.set("sketch")
    app._edtab_clicked()
    assert app._request().enhance
    e_plain = runhistory.entry("Sketch", "Flux 2 Klein Edit", e["settings"])      # a run without a written prompt
    app.load_history(e_plain)
    assert app._request().enhance
    # the tab Sketch is greyed out without the upsampler, the model stays offered (user 9.11.)
    import test_settings_ui as su
    from pccomfy import inventory
    nodes = su.NODES | {n["class_type"] for f in (ROOT / "workflows").glob("*.json") for n in json.loads(f.read_text(encoding="utf-8")).values()}
    app._apply_refresh({"_detect": True, "_inv": inventory.Inventory(su.lists_without(clip=W4), nodes)})
    pick("qwen", "edit")                    # Qwen's writer is its w4a8 since 16.11. evening (Flux 3: the upsampler)
    app._edtabs_update()
    for k in ("sketch", "scribble"):       # both tabs of the writer (plan B)
        assert str(app.rb_edtabs[k].cget("state")) == "disabled" and W4 in app.tt_edtabs[k].text, k
        assert type(app.tt_edtabs[k]).__name__ == "Tooltip", k     # shown (user 11.11.), not a switched-off chip tooltip
    pick("flux2", "edit")                   # Flux 2 writes with qwen3vl 4B (10.11.): no upsampler needed
    app._edtabs_update()
    assert str(app.rb_edtabs["sketch"].cget("state")) == str(app.rb_edtabs["scribble"].cget("state")) == "normal"
    pick("fibo", "edit")
    app._edtabs_update()
    assert str(app.rb_edtabs["sketch"].cget("state")) == "normal"


def main():
    test_window()           # first: importing test_settings_ui swaps the stub's Text for one that reads back empty
    test_models_and_texts()
    test_manifest_lock_only_the_tab()
    test_scribble_on_its_own_layer()
    test_scribble_by_colour()
    test_minimax_scribble_object_mask()
    test_no_scribble_no_run()
    test_whole_sketch()
    print("ALL OK (sketch mode)")


if __name__ == "__main__":
    main()
