"""Reference at scribble (user 15.11., docs/plan/entscheidungen.md): the second chip of the tab Scribble on photo. The text with
the placeholder and the model's tag, the one reference slot of the three sketch workflows (Fibo: fibo2-edit.json), the sentence
with the tag past the prompt writer (StringConcatenate behind it, "It" -> "The <object>"), the stops (placeholder left, no
picture) and the window (chips, slot, tip). Bridge against the PhotoCraft simulator of test_reference_mode, window with the
stubbed Tk.

    python tests/test_ref_scribble.py
"""
import dataclasses
import os
import sys
import tempfile
from pathlib import Path

os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-refscribble-")
os.environ["PCCOMFY_NO_TIPS"] = "1"

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sketch_mode as ts  # noqa: E402
from pccomfy import bridge, models, refslots, workflows  # noqa: E402
from pccomfy.bridge import BridgeError, Request  # noqa: E402

ROOT = ts.ROOT
WF = {"flux3": "flux3-klein-sketch.json", "flux2": "flux2-klein-sketch.json", "qwen": "qwen-image-21-sketch.json",
      "fibo": "fibo2-edit.json"}


def typed(key, obj="a beagle dog"):
    return models.ref_scribble_text(models.BY_KEY[key].tag_style).replace(models.REF_MARK, obj)


def test_texts():
    assert [lb for lb, _t, _tip in models.SCRIBBLE_PROMPTS] == ["Scribble on photo", "Scribble with reference"]
    tags = {k: models.BY_KEY[k].tag_style.format(n=2, i=1) for k in WF}
    assert tags == {"flux3": "<ref_image_1>", "flux2": "image 2", "qwen": "<image2>", "fibo": "<image_2>"}
    for k, tag in tags.items():
        t = models.ref_scribble_text(models.BY_KEY[k].tag_style)
        assert t.endswith("It fills the scribbled area and looks like " + tag + ".") and models.REF_MARK in t and "{tag}" not in t
        assert t in models.STOCK_PROMPTS
        assert models.BY_KEY[k].modes["scribble"].prompts == models.SCRIBBLE_PROMPTS
    assert models.REF_MARK != models.SKETCH_MARK


def test_mentions_reference():
    for s in ("It looks exactly like <ref_image_1>.", "like image 2.", "like <image2>", "<image_2> here", "<Picture 2>"):
        assert refslots.mentions_reference(s), s
    for s in ("<ref_image_0> is the photo", "image 1", "<image1> the picture", "no tag", "myimage 2"):
        assert not refslots.mentions_reference(s), s


def test_split():
    req, suf = bridge.ref_scribble_split(typed("flux3"))
    assert req == models.SKETCH_SCRIBBLE.replace(models.SKETCH_MARK, "a beagle dog")
    assert suf == "The beagle dog fills the scribbled area and looks like <ref_image_1>."            # the user's sentence (15.11.)
    req, suf = bridge.ref_scribble_split(typed("qwen", "an old wicker basket"))
    assert suf == "The old wicker basket fills the scribbled area and looks like <image2>." and "<image2>" not in req
    # the object not found (the text rewritten): "It" stays
    req, suf = bridge.ref_scribble_split("Put a dog there. It looks exactly like image 2.")
    assert (req, suf) == ("Put a dog there.", "It looks exactly like image 2.")
    # the tag inside the request (window test 15.11.): the request stays with the writer, without the tag
    req, suf = bridge.ref_scribble_split("Replace the coloured scribbles with the book from <ref_image_1>, realistic. "
                                         "Remove every scribble line. It looks exactly like <ref_image_1>.")
    assert req == "Replace the coloured scribbles with the book, realistic. Remove every scribble line."
    assert suf == "The book looks exactly like <ref_image_1>."
    req, suf = bridge.ref_scribble_split("Replace the coloured scribbles with the book from image 2, realistic.")
    assert (req, suf) == ("Replace the coloured scribbles with the book, realistic.", "The book looks exactly like image 2.")
    req, suf = bridge.ref_scribble_split("Replace the coloured scribbles with <image2>, realistic.")
    assert (req, suf) == ("Replace the coloured scribbles with the object, realistic.", "The object looks exactly like <image2>.")
    # no tag: nothing goes past the writer
    assert bridge.ref_scribble_split("Replace the scribbles with a dog.") == ("Replace the scribbles with a dog.", "")


def test_workflows_one_slot():
    for k, wf in WF.items():
        tpl = workflows.load_template(ROOT / "workflows" / wf)
        assert workflows.ref_slot_count(tpl) >= 1, wf
        g, _out = workflows.apply_template(tpl, workflows.GenParams(prompt="x"), "pic.png", None, None, ref_first=False)
        assert not any("pc:ref" in n.get("_meta", {}).get("title", "") for n in g.values()), wf     # no reference: as before
        assert "example.png" not in str([n["inputs"].get("image") for n in g.values() if n.get("class_type") == "LoadImage"]
                                        ).replace("'pic.png'", ""), wf


def _graph(key, prompt, enhance=True):
    b = bridge.Bridge(None, ts.tr.FakeComfy(), tempfile.mkdtemp())
    req = Request(mode="edit", workflow=str(ROOT / "workflows" / WF[key]), enhance=enhance, layer_mask="none", scribble=True)
    p = workflows.GenParams(prompt=prompt, seed=1)
    g, _out = b._graph(req, p, "pic.png", None, req.workflow, ["ref.png"])
    return g


def _ref_wired(g):
    ids = [nid for nid, n in g.items() if n.get("class_type") == "LoadImage" and n["inputs"].get("image") == "ref.png"]
    assert len(ids) == 1
    return any(isinstance(v, list) and str(v[0]) == ids[0] for n in g.values() for v in n.get("inputs", {}).values())


def test_bridge_graph_writer_on():
    for key in ("flux3", "flux2", "qwen"):
        g = _graph(key, typed(key))
        assert _ref_wired(g), key
        cat = [nid for nid, n in g.items() if n.get("_meta", {}).get("title") == "Written prompt + reference sentence"]
        assert len(cat) == 1, key
        c = g[cat[0]]
        tag = models.BY_KEY[key].tag_style.format(n=2, i=1)
        assert c["inputs"]["string_b"] == f"The beagle dog fills the scribbled area and looks like {tag}." and c["inputs"]["string_a"] == [workflows.writer_end(g, "403"), 0]
        users = [nid for nid, n in g.items() for v in n.get("inputs", {}).values() if v == [cat[0], 0]]
        end = workflows.writer_end(g, "403")
        assert users and not any(v == [end, 0] for nid, n in g.items() if nid != cat[0] for v in n.get("inputs", {}).values()), key
        vgl = next(n for n in g.values() if "pc:vgl" in n.get("_meta", {}).get("title", ""))
        assert vgl["inputs"]["source"] == [cat[0], 0]          # the history holds what was really sent
        # the writer gets a description of the reference by the same text model (user 15.11., "A: Referenz beschreiben")
        gen = [nid for nid, n in g.items() if n.get("_meta", {}).get("title") == "Reference description (text model)"]
        assert len(gen) == 1, key
        d = g[gen[0]]["inputs"]
        ref_id = next(nid for nid, n in g.items() if n.get("class_type") == "LoadImage" and n["inputs"].get("image") == "ref.png")
        assert d["image"] == [ref_id, 0] and d["clip"] == g["403"]["inputs"]["clip"] and d["prompt"] == "Describe the beagle dog in this picture."
        assert g[d["system_prompt"][0]]["inputs"]["value"] == workflows.REF_DESCRIBE_SYSTEM
        cat2 = g["403"]["inputs"]["prompt"]
        c2 = g[cat2[0]]["inputs"]
        assert c2["string_b"] == [gen[0], 0] and "a beagle dog" in c2["string_a"] and tag not in c2["string_a"]
        assert c2["delimiter"] == " The beagle dog in the reference picture looks like this: "
        assert gen[0] in bridge.prompt_phase_nodes(g)
    # Qwen: its picture tag stays in front
    g = _graph("qwen", typed("qwen"))
    assert g["405"]["inputs"]["string_a"] == "<image1>"


def test_bridge_graph_writer_off():
    for key in ("flux3", "fibo"):
        g = _graph(key, typed(key), enhance=False)
        assert _ref_wired(g), key
        assert not any(n.get("class_type") == "StringConcatenate" and "reference" in n.get("_meta", {}).get("title", "")
                       for n in g.values())
        tag = models.BY_KEY[key].tag_style.format(n=2, i=1)
        texts = [v for n in g.values() for v in n.get("inputs", {}).values() if isinstance(v, str) and tag in v]
        assert texts and all("The beagle dog fills the scribbled area and looks like " + tag in t for t in texts), (key, texts)


def test_stops():
    pc, b = ts.doc([ts.photo(), ts.strokes((40, 90, 230))])
    req = Request(mode="edit", workflow=str(ROOT / "workflows" / WF["flux3"]), enhance=True, layer_mask="none", scribble=True,
                  refs=[Image.new("RGB", (64, 64), "red")])
    req.params = workflows.GenParams(prompt=models.ref_scribble_text(models.FLUX3.tag_style), seed=7)
    try:
        b.begin(req)
        raise AssertionError("ran with the placeholder")
    except BridgeError as e:
        assert str(e) == models.REF_MARK_LEFT
    # a full run through the simulator: the reference goes along, only the crop is generated
    req.params = workflows.GenParams(prompt=typed("flux3"), seed=7)
    res = b.run(req)
    assert res["scribble"] == "layer"
    g = b.comfy.graphs[-1]
    assert any(n.get("_meta", {}).get("title") == "Written prompt + reference sentence" for n in g.values())


def test_size_sentence():
    # window test 15.11.: Flux 3 and Fibo drew the object larger than the scribble; the text says how large it is
    t = typed("flux3", "a travel bag")
    assert "It fills the scribbled area and looks like <ref_image_1>." in t
    req, suf = bridge.ref_scribble_split(t)
    assert "It " not in req and "<ref_image_1>" not in req
    assert suf == "The travel bag fills the scribbled area and looks like <ref_image_1>."


def test_object_mask():
    """The layer mask follows the object: opaque where it reaches past the scribble's box, 0 at the crop's sides."""
    import numpy as np
    from pccomfy import imaging, scribble
    rng = np.random.default_rng(1)
    W, H = 600, 400
    photo = Image.fromarray(rng.integers(100, 140, (H, W, 3), dtype=np.uint8))
    box = imaging.Box(250, 150, 100, 80)
    found = scribble.Found(box, imaging.Box(230, 134, 140, 112), "red")
    reg = scribble.region(found, (W, H))
    fade = scribble.fade_mask((W, H), box, reg)
    # the model's crop: the ground with a new grain, and a dark object reaching 30 px left of the box
    crop = np.asarray(photo.crop(reg.pil())).copy()
    crop = np.clip(crop.astype(int) + rng.integers(-12, 13, crop.shape), 0, 255).astype(np.uint8)
    ox, oy = box.x - reg.x, box.y - reg.y
    crop[oy + 10:oy + 70, ox - 30:ox + 90] = (30, 25, 20)
    layer, _m = scribble.put_back(photo, Image.fromarray(crop), found, reg)
    m = np.asarray(scribble.object_mask(photo, layer, found, reg))
    f = np.asarray(fade)
    y = box.y + 40
    assert m[y, box.x - 25] == 255 and f[y, box.x - 25] < 255          # the part past the box stays opaque
    assert (m[box.y:box.y + box.h, box.x:box.x + box.w] == 255).all()    # the box as before
    assert m[reg.y, reg.x + reg.w // 2] == 0 and m[reg.y + reg.h // 2, reg.x] == 0     # still 0 at the crop's sides
    assert m[box.y + box.h + 30, box.x + box.w + 30] <= f[box.y + box.h + 30, box.x + box.w + 30] + 1   # the ground: the fade
    # nothing changed, or the whole crop redrawn: the fade mask
    same, _m = scribble.put_back(photo, photo.crop(reg.pil()), found, reg)
    assert (np.asarray(scribble.object_mask(photo, same, found, reg)) == f).all()
    other, _m = scribble.put_back(photo, Image.new("RGB", (reg.w, reg.h), (250, 250, 250)), found, reg)
    assert (np.asarray(scribble.object_mask(photo, other, found, reg)) == f).all()


def test_fibo_no_ref_scribble():
    """Fibo has no tab Scribble with reference (user 15.11.: it does not take poses over); the two-step code of
    probe A2 is gone. Flux 3, Flux 2 and Qwen keep the tab, Fibo keeps Scribble on photo."""
    fibo = models.BY_KEY["fibo"]
    assert "scribble" in fibo.modes and not models.offers_ref_scribble(fibo)
    others = [m for m in models.MODELS if "scribble" in m.modes and m.key != "fibo" and m.tag_style and m.max_refs > 0]
    assert others and all(models.offers_ref_scribble(m) for m in others)
    for gone in ("ref_scribble_step2_prompt", "ref_step2_box", "REF_STEP2_PROMPT", "REF_STEP2_CONTEXT"):
        assert not hasattr(bridge, gone), gone
    assert not hasattr(bridge.Bridge, "_ref_scribble_step2")
    assert "scribble_two_step" not in {f.name for f in dataclasses.fields(Request)}


def test_object_mask_whole_canvas():
    """A crop that is the whole canvas: the layer mask follows the object with a soft edge instead of covering all of it."""
    import numpy as np
    from pccomfy import imaging, scribble
    W, H = 600, 400
    rng = np.random.default_rng(2)
    photo = Image.fromarray(rng.integers(100, 140, (H, W, 3), dtype=np.uint8))
    box = imaging.Box(250, 150, 100, 80)
    found = scribble.Found(box, imaging.Box(230, 134, 140, 112), "red")
    reg = imaging.Box(0, 0, W, H)
    res = np.clip(np.asarray(photo).astype(int) + rng.integers(-12, 13, (H, W, 3)), 0, 255).astype(np.uint8)
    res[box.y + 10:box.y + 70, box.x - 30:box.x + 90] = (30, 25, 20)
    layer, _m = scribble.put_back(photo, Image.fromarray(res), found, reg)
    m = np.asarray(scribble.object_mask(photo, layer, found, reg))
    assert (m[box.y:box.y + box.h, box.x:box.x + box.w] == 255).all() and m[box.y + 40, box.x - 25] == 255
    assert m[5, 5] == 0 and m[H - 5, W - 5] == 0 and (m > 127).mean() < 0.2
    other, _m = scribble.put_back(photo, Image.new("RGB", (W, H), (250, 250, 250)), found, reg)
    f = np.asarray(scribble.fade_mask((W, H), box, scribble.region(found, (W, H))))
    assert (np.asarray(scribble.object_mask(photo, other, found, reg)) == f).all()


def test_grow_square_as_maxfilter():
    """object_mask grows the object by a square as PIL's MaxFilter did, only fast (MaxFilter(31) took 30 s on 20 MP)."""
    import numpy as np
    from PIL import ImageFilter
    from pccomfy import scribble
    rng = np.random.default_rng(3)
    for size in (3, 7, 31):
        a = rng.random((120, 170)) > 0.995
        a[0, 0] = a[-1, -1] = True
        want = np.asarray(Image.fromarray((a * 255).astype("uint8")).filter(ImageFilter.MaxFilter(size))) > 0
        assert (scribble._grow_square(a, size) == want).all(), size


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

    def prompt():
        return app.t_prompt.get("1.0", "end").strip()

    said = []
    app._status = lambda text, error=False, **k: said.append(text)
    app.v_model.set("flux3")
    app.v_mode.set("edit")
    app._on_model()
    app._edtabs_ensure()
    app.v_edtab.set("scribble")
    app._edtab_clicked()
    assert app.v_sketch.get() == models.TEXT_SCRIBBLE_LABEL and not app._refs_wanted()
    # the two scribble functions are tabs since 15.11. (user): no chip row
    assert app._edtab_layout[-1] == ["sketch", "scribble", "refscribble"] or "refscribble" in sum(app._edtab_layout, [])
    assert str(app.rb_edtabs["scribble"].cget("text")) == "Scribble on photo"
    assert str(app.rb_edtabs["refscribble"].cget("text")) == "Scribble with reference"
    assert not app.f_sketch.winfo_manager()
    app.v_edtab.set("refscribble")
    app._edtab_clicked()
    assert app.v_edtab.get() == "refscribble" and app.v_mode.get() == "scribble"
    assert prompt() == models.ref_scribble_text("<ref_image_{i}>") and app._hint_text == models.REF_SCRIBBLE_TIP
    assert app._ref_scribble() and app._refs_wanted() and app.refslots.max_refs == 1
    # the placeholder left: no run
    app.generate()
    assert said[-1] == models.REF_MARK_LEFT
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", typed("flux3"))
    app.generate()
    assert said[-1] == models.NO_REF_SCRIBBLE
    app.refslots.add(Image.new("RGB", (64, 64), "red"))
    app.refslots.add(Image.new("RGB", (64, 64), "blue")) if app.refslots.free else None
    req = app._request()
    assert req.scribble and req.mode == "edit" and len(req.refs) == 1 and not req.bbox and req.ref_side == models.FLUX3.ref_side
    # a model change keeps the tab; the unedited text gets the new model's tag
    app._sketch_pick(models.REF_SCRIBBLE_LABEL)
    app.v_model.set("qwen")
    app._on_model()
    assert app.v_mode.get() == "scribble" and app.v_sketch.get() == models.REF_SCRIBBLE_LABEL and app.v_edtab.get() == "refscribble"
    assert prompt() == models.ref_scribble_text("<image{n}>"), prompt()
    # the tab Scribble on photo: no slot, its text
    app.v_edtab.set("scribble")
    app._edtab_clicked()
    assert app.v_edtab.get() == "scribble"
    assert prompt() == models.SKETCH_SCRIBBLE and not app._refs_wanted() and app._request().refs == []
    assert app._hint_text == models.SCRIBBLE_TIP
    # another tab
    app.v_edtab.set("refscribble")
    app._edtab_clicked()
    app.v_edtab.set("multi")
    app._edtab_clicked()
    assert app.v_mode.get() == "multi_edit" and app.refslots.max_refs == models.QWEN.max_refs
    app.root.destroy()


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("ALL OK (Scribble with reference)")


if __name__ == "__main__":
    main()
