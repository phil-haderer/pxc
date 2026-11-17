"""Fill Selection for Flux 3 through the layout box (plan B step 4; Fill round 5, 11.11.: crop + "Place" 8 of 8 good, all five
hard cases; the user chose "Place"): no red mark, the selection's bounding box becomes <obj_1> in the crop (the typed text
is the box's description too), the sentence names the box; the result goes back like Insert reference (the box plus
BBOX_MARGIN, soft edge, colours outside matched). Insert reference is a tab of Fill now.

    python tests/test_flux3_fill_box.py
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_fill_flux as lf  # noqa: E402
import test_reference_mode as t  # noqa: E402
from pccomfy import bridge, imaging, manifest, models, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402

WF = str(t.ROOT / "workflows" / "flux3-klein-edit.json")


def run(prompt, fill_box=True, context=0.4):
    tmp = tempfile.mkdtemp()
    pc, _, b = t.make(tmp, with_sel=True)
    b.comfy = t.FakeComfy()
    req = Request(mode="inpaint", workflow=WF, fill_box=fill_box, enhance=False, layer_mask="soft", context=context,
                  feather_pct=10.0, base_res=1536)
    req.params = workflows.GenParams(prompt=prompt, seed=7)
    res = b.run(req)
    return pc, b, res


def test_mode_as_in_the_test_round():
    flux3 = models.BY_KEY["flux3"]
    fill, remove = flux3.modes["inpaint"], flux3.modes["remove"]
    assert fill.fill_box and fill.workflow == remove.workflow == "flux3-klein-edit.json"
    assert remove.settings == lf.settings("flux3")                           # context 40 %, soft mask, Edge feather 10 %, 1536
    assert fill.settings == {**remove.settings, "mask_density": 0}           # Fill only: Mask density 0 % (user 13.11., soft edge)
    assert fill.prompt_tip == models.FILL_TIP
    assert [m.key for m in models.MODELS if any(md.fill_box for md in m.modes.values())] == ["flux3"]
    assert "inpaint" not in manifest.TABS["flux3"].modes                      # no new files


def test_the_wording_is_the_rated_one():
    assert bridge.box_fill_prompt("a red pickup truck.") == lf.BOX_PROMPT.format(verb="Place", text="a red pickup truck")
    assert lf.BOX_APPROACHES["B2"] == ("Place", False)                         # the rated variant: crop, "Place"
    # a leading verb is dropped (the Fill tip's example is "add a red flower")
    for typed in ("add a red flower", "Add a red flower.", "place a red flower", "Put a red flower", "insert  a red flower!"):
        assert bridge.box_fill_text(typed) == "a red flower", typed
    assert bridge.box_fill_text("Address sign on the wall") == "Address sign on the wall"     # only a whole word


def test_run_box_in_the_crop():
    pc, b, res = run("add a red pickup truck")
    graph = b.comfy.graphs[-1]
    bb = next(v for v in graph.values() if v["class_type"] == "CreateBoundingBoxes")
    lay = next(v for v in graph.values() if v["class_type"] == "Flux3LayoutPrompt")
    assert lay["inputs"]["prompt"] == "Place a red pickup truck in <obj_1>. Keep everything else unchanged.", lay["inputs"]["prompt"]
    got = json.loads(bb["inputs"]["bboxes"])[0]
    assert got["metadata"]["desc"] == "a red pickup truck"
    # the canvas is the crop (Context 40 % around the selection, inside the picture), the box the selection in it
    sel = imaging.Box(t.SEL[0], t.SEL[1], t.SEL[2] - t.SEL[0], t.SEL[3] - t.SEL[1])
    region = imaging.grow_box(sel, (t.W, t.H), 0.4)
    assert (bb["inputs"]["width"], bb["inputs"]["height"]) == (region.w, region.h)
    assert (got["x"], got["y"], got["width"], got["height"]) == (sel.x - region.x, sel.y - region.y, sel.w, sel.h), got
    assert (region.w, region.h) != (t.W, t.H)                                  # a crop, not the whole picture
    # no red outline in what the model got
    up = next(im for name, im in b.comfy.uploads.items() if name.endswith("-image.png"))
    a = np.asarray(up.convert("RGB"))
    assert not ((a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 0)).any(), "Flux 3 Fill must not draw the red outline"
    # the result has the soft layer mask, the user's selection comes back
    assert any(l.get("mask") is not None for l in pc.doc.layers) and pc.doc.sel is not None and res["layers"]


def test_the_layer_mask_is_the_box_with_margin():
    sel = imaging.Box(t.SEL[0], t.SEL[1], t.SEL[2] - t.SEL[0], t.SEL[3] - t.SEL[1])
    region = imaging.grow_box(sel, (t.W, t.H), 0.4)
    m = imaging.box_margin_mask(sel, (t.W, t.H), bridge.BBOX_MARGIN, 10.0).crop(region.pil())
    assert m.size == (region.w, region.h)
    a = np.asarray(m)
    assert a[sel.y - region.y + sel.h // 2, sel.x - region.x + sel.w // 2] == 255


def test_other_models_keep_the_red_outline():
    pc, b, res = run("a red pickup truck", fill_box=False)
    graph = b.comfy.graphs[-1]
    assert all(v["class_type"] not in ("CreateBoundingBoxes", "Flux3LayoutPrompt") for v in graph.values())
    text = next(v for v in graph.values() if "pc:prompt" in v.get("_meta", {}).get("title", ""))["inputs"]["text"]
    assert "red rectangle" in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
