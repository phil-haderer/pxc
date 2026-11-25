# tags: refine, flux3, workflows
"""Flux 3 Refine (after Pixaroma's "Restore and Colorize"): standard nodes only, size of the picture, prompt switch,
the Restore LoRA (user 22.11.).

    python tests/test_flux3_refine.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as T  # noqa: E402
from pccomfy import models, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402

WF = ROOT / "workflows" / "flux3-klein-refine.json"


def main():
    g = json.loads(WF.read_text(encoding="utf-8"))
    assert not any("AUSBOSS" in n["class_type"] or "Pixaroma" in n["class_type"] for n in g.values())   # standard nodes only
    assert all(str(v[0]) in g for n in g.values() for v in n["inputs"].values() if isinstance(v, list))
    assert workflows.has_upscale_slot(g)                                         # sets the size
    # the Restore LoRA of Upscale (user 22.11.: refine round 3, 4 of 6 against 0): same file and strength, a pc:lora switch, on
    up = json.loads((ROOT / "workflows" / "flux3-klein-upscale.json").read_text(encoding="utf-8"))
    assert g["9"]["inputs"]["lora_name"] == up["9"]["inputs"]["lora_name"] and workflows.lora_strength(g) == 0.5
    assert g["9"]["_meta"]["pc_lora_label"] == "Restore LoRA" and g["163"]["inputs"]["model"] == ["9", 0]
    assert models.FLUX3.modes["refine"].settings["turbo"] is True
    from pccomfy import inventory, manifest
    lora = "Flux 3\\flux-3-image-klein-restore.safetensors"
    assert lora in manifest.mode_required("flux3", "refine") and lora in inventory.default_switch_files("flux3", "refine")
    off = workflows.bypass_lora(workflows.load_template(WF))                     # the switch off: straight to the model
    assert "9" not in off and off["163"]["inputs"]["model"] == ["8", 0], off["163"]["inputs"]["model"]
    assert g["163"]["inputs"]["steps"] == 16 and g["163"]["inputs"]["cfg"] == 1 and g["161"]["inputs"]["resolution"] == "keep resolution"

    m = models.FLUX3.modes["refine"]
    assert m.workflow == WF.name and m.prompts == () and m.prompt_hint == models.FLUX3_RESTORE   # one prompt since 24.11. (user)
    assert models.FLUX3_RESTORE in models.STOCK_PROMPTS and models.FLUX3_DEFAULT in models.STOCK_PROMPTS

    for typed, want in (("", models.FLUX3_RESTORE), (models.FLUX3_DEFAULT, models.FLUX3_DEFAULT)):
        pc, _, b = T.make(tempfile.mkdtemp(), with_sel=False)
        b.comfy = T.FakeComfy()
        req = Request(mode="refine", workflow=str(WF), preset="X", run_no=1, scale=1.0)
        req.params = workflows.GenParams(prompt=typed, seed=5)
        b.run(req)
        out = b.comfy.graphs[0]
        assert out["159"]["inputs"]["text"] == want
        mp = out["3"]["inputs"]["megapixels"]                      # the picture's own size, not a fixed 1 MP
        assert abs(mp - T.W * T.H / 1e6) < 0.01, mp
    # a selection is ignored: the whole picture goes in (1.11., user: Refine only without a selection)
    pc, _, b = T.make(tempfile.mkdtemp(), with_sel=True)
    b.comfy = T.FakeComfy()
    req = Request(mode="refine", workflow=str(WF), preset="X", run_no=1, scale=1.0)
    req.params = workflows.GenParams(prompt="", seed=5)
    res = b.run(req)
    assert res["region"] == {"x": 0, "y": 0, "w": T.W, "h": T.H}, res["region"]
    print("ALL OK (flux3 refine)")


if __name__ == "__main__":
    main()
