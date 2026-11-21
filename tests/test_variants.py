"""Known model variants (pccomfy/variants.py, user 20.11.): detection, aliases, the values sent, Qwen Turbo's sigma schedule.

    python tests/test_variants.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp())
sys.path.insert(0, str(ROOT))

from pccomfy import bridge, inventory, manifest, models, variants, workflows  # noqa: E402

WF = ROOT / "workflows"
QWEN, QWEN_T = "qwen_image_2.1_int8_convrot.safetensors", "qwen_image_2.1_turbo_int8_convrot.safetensors"


def sampler(graph):
    return graph[workflows.main_sampler(graph)]


def build(wf, req_kw, mode="txt2img"):
    p = workflows.GenParams(prompt="a fox", seed=5, width=1024, height=1024)
    req = bridge.Request(mode=mode, workflow=str(WF / wf), params=p, enhance=False, **req_kw)
    img, mask = (None, None) if mode == "txt2img" else ("pic.png", "mask.png")
    graph, _ = bridge.Bridge._graph(object(), req, p, img, mask, str(WF / wf))
    return graph


def main():
    # every variant stands in for one of our shipped diffusion model files, and is that file's alias (an untested one would
    # not be; MiniMax w4a8 was one until its test on 21.11., user 4A)
    assert [v.file for v in variants.VARIANTS if not v.alias] == []
    for v in variants.VARIANTS:
        f = manifest.FILES.get(v.base)
        assert f is not None and f.kind == "unet", v.base
        assert (v.file in f.aliases) == v.alias, (v.base, f.aliases)
        assert v.file not in manifest.FILES, v.file          # a variant is no download of its own
        assert any(v.base in variants.unet_names(workflows.load_template(w)) for w in WF.glob("*.json")
                   if isinstance(workflows.load_template(w), dict)), v.base
    assert variants.get("sub\\" + QWEN_T.upper()).file == QWEN_T and variants.get(QWEN) is None and variants.get("") is None

    # detection: ours wins when both are there; the variant when it is alone or linked in Model Links
    tpl = workflows.load_template(WF / "qwen-image-21-t2i.json")
    both = inventory.Inventory({"unet": [QWEN, QWEN_T]})
    assert both.found(QWEN) == QWEN and variants.in_use(tpl, both.found) is None
    alone = inventory.Inventory({"unet": ["Qwen\\" + QWEN_T]})
    assert alone.found(QWEN) == "Qwen\\" + QWEN_T and variants.in_use(tpl, alone.found).file == QWEN_T
    linked = inventory.Inventory({"unet": [QWEN, QWEN_T]}, mapping={QWEN: QWEN_T})
    assert variants.in_use(tpl, linked.found).file == QWEN_T
    assert inventory.Inventory({"unet": []}).found(QWEN) is None
    # the model counts as ready with the variant alone (Qwen's other files there)
    files = {k: [] for k in manifest.KINDS}
    for n in manifest.tab_required("qwen"):
        files[manifest.FILES[n].kind].append(QWEN_T if n == QWEN else n)
    assert inventory.Inventory(files).missing(manifest.tab_required("qwen")) == ()
    # apply_names renames our file to the variant when it is the one ComfyUI lists
    g = workflows.load_template(WF / "qwen-image-21-t2i.json")
    assert alone.apply_names(g) >= 1 and variants.unet_names(g) == ["Qwen\\" + QWEN_T]

    # Qwen Turbo, Text to image: LoRA out even with turbo on, SamplerCustom with the fixed 8-step schedule, euler, CFG 1
    for turbo in (True, False):
        g = build("qwen-image-21-t2i.json", dict(turbo=turbo, variant=QWEN_T))
        assert not any(n.get("class_type") == "LoraLoaderModelOnly" for n in g.values()), turbo
        sc = [n for n in g.values() if n.get("class_type") == "SamplerCustom"]
        assert len(sc) == 1 and sc[0]["inputs"]["cfg"] == 1.0 and sc[0]["inputs"]["noise_seed"] == 5
        sig = g[sc[0]["inputs"]["sigmas"][0]]
        assert sig["class_type"] == "ManualSigmas" and sig["inputs"]["sigmas"] == variants.QWEN_TURBO_SIGMAS
        assert g[sc[0]["inputs"]["sampler"][0]]["inputs"]["sampler_name"] == "euler"
        assert not any(n.get("class_type") == "KSampler" for n in g.values())
        for n in g.values():          # every link points at a node of the graph
            for v in n.get("inputs", {}).values():
                if isinstance(v, list) and len(v) == 2 and isinstance(v[1], int) and isinstance(v[0], str):
                    assert v[0] in g, v
    # Qwen Turbo in Edit / Fill: the same schedule; Refine (denoise below 1): KSampler with 8 steps, euler, simple
    g = build("qwen-image-21-edit.json", dict(turbo=False, variant=QWEN_T), mode="edit")
    assert any(n.get("class_type") == "SamplerCustom" for n in g.values())
    # Qwen Turbo in Expand: no schedule (green hatching in the new part, user 20.11., A), plain 8 steps, euler, simple
    g = build("qwen-image-21-edit.json", dict(turbo=False, variant=QWEN_T), mode="outpaint")
    assert not any(n.get("class_type") == "SamplerCustom" for n in g.values())
    ks = sampler(g)["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, "euler", "simple"), ks
    assert variants.sigmas_for(variants.get(QWEN_T), "outpaint") == "" and variants.sigmas_for(variants.get(QWEN_T), "inpaint")
    assert variants.sigmas_for(None, "edit") == "" and variants.sigmas_for(variants.get(QWEN_T), "refine") == ""
    p = workflows.GenParams(prompt="x", seed=1, denoise=0.4)
    req = bridge.Request(mode="refine", workflow=str(WF / "qwen-image-21-refine.json"), params=p, enhance=False, turbo=False, variant=QWEN_T)
    g, _ = bridge.Bridge._graph(object(), req, p, "pic.png", None, req.workflow)
    ks = sampler(g)
    assert ks["class_type"] == "KSampler" and ks["inputs"]["steps"] == 8 and ks["inputs"]["cfg"] == 1.0
    assert ks["inputs"]["sampler_name"] == "euler" and ks["inputs"]["scheduler"] == "simple" and ks["inputs"]["denoise"] == 0.4
    # the user's own steps win over the schedule (the field is grey, but a request may carry them)
    g = build("qwen-image-21-t2i.json", dict(turbo=False, variant=QWEN_T, sampler_override={"steps": 12}))
    assert sampler(g)["class_type"] == "KSampler" and sampler(g)["inputs"]["steps"] == 12
    # our own file: unchanged (25 steps without the LoRA, 8 with it)
    for turbo, steps in ((True, 8), (False, 25)):
        assert sampler(build("qwen-image-21-t2i.json", dict(turbo=turbo)))["inputs"]["steps"] == steps
    # a variant of another model's file is ignored (the window switched models)
    assert sampler(build("qwen-image-21-t2i.json", dict(turbo=False, variant="fibo2_dev_int8_convrot.safetensors")))["inputs"]["steps"] == 25

    # Fibo Dev: Fibo has no speed LoRA, so the Turbo tick (left off by another model) must not drop the variant's values
    # (20.11.: Fill, Remove, Refine ... ran Fibo Dev with Edit Turbo's 4 steps, CFG 1)
    fibo = "fibo2_dev_int8_convrot.safetensors"
    for wf, mode in (("fibo2-edit.json", "inpaint"), ("fibo2-edit.json", "edit"), ("fibo2-upscale.json", "upscale"), ("fibo2-t2i.json", "txt2img")):
        for turbo in (True, False):
            if mode == "upscale":       # no mask node there
                p = workflows.GenParams(prompt="x", seed=1)
                req = bridge.Request(mode=mode, workflow=str(WF / wf), params=p, enhance=False, turbo=turbo, variant=fibo)
                ks = sampler(bridge.Bridge._graph(object(), req, p, "pic.png", None, req.workflow)[0])["inputs"]
            else:
                ks = sampler(build(wf, dict(turbo=turbo, variant=fibo), mode=mode))["inputs"]
            assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (30, 5.0, "euler", "simple"), (wf, mode, turbo, ks)

    # MOSS Base: with DMD2 8 steps, CFG 1, euler/simple; without it our SFT values (user 20.11.)
    moss = "moss_image_base_int8_convrot.safetensors"
    ks = sampler(build("moss-image-t2i.json", dict(turbo=True, variant=moss)))["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, "euler", "simple"), ks
    off = sampler(build("moss-image-t2i.json", dict(turbo=False, variant=moss)))["inputs"]
    ours = sampler(build("moss-image-t2i.json", dict(turbo=False)))["inputs"]
    assert {k: off[k] for k in ("steps", "cfg", "sampler_name", "scheduler")} == {k: ours[k] for k in ("steps", "cfg", "sampler_name", "scheduler")}
    assert (off["steps"], off["cfg"]) == (25, 3.0)
    # Kromoss (user 20.11.): the same values as MOSS Base, a second alias of our SFT file
    kro = "kromoss_int8_convrot.safetensors"
    ks = sampler(build("moss-image-t2i.json", dict(turbo=True, variant=kro)))["inputs"]
    assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (8, 1.0, "euler", "simple"), ks
    off = sampler(build("moss-image-t2i.json", dict(turbo=False, variant=kro)))["inputs"]
    assert (off["steps"], off["cfg"]) == (25, 3.0)
    assert set(variants.aliases_of("moss_image_sft_int8_convrot.safetensors")) == {moss, kro}

    # Fibo Dev: 30 steps, CFG 5, euler/simple in Text to image and Edit
    for wf, mode in (("fibo2-t2i.json", "txt2img"), ("fibo2-edit.json", "edit")):
        ks = sampler(build(wf, dict(variant="fibo2_dev_int8_convrot.safetensors"), mode=mode))["inputs"]
        assert (ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"]) == (30, 5.0, "euler", "simple"), (wf, ks)
    # a typed CFG still wins
    ks = sampler(build("fibo2-t2i.json", dict(variant="fibo2_dev_int8_convrot.safetensors", sampler_override={"cfg": 4.0})))["inputs"]
    assert ks["cfg"] == 4.0 and ks["steps"] == 30

    # Krea fp8, MiniMax w4a8: the same values as our file
    for wf, name in (("krea2-turbo-t2i.json", "krea2_turbo_fp8.safetensors"), ("minimax-h3-image-t2i.json", "minimax_h3_image_pruned_w4a8.safetensors")):
        a, b = sampler(build(wf, {}))["inputs"], sampler(build(wf, dict(variant=name)))["inputs"]
        assert a == b, (wf, a, b)

    # the values the window shows: the same as the bridge sends
    v = variants.get(QWEN_T)
    assert variants.sampler_values(v, False) == variants.sampler_values(v, True) == {"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}
    assert variants.sampler_values(variants.get(moss), False) == {}
    assert all(m.key for m in models.MODELS)
    print("ALL OK (model variants)")


if __name__ == "__main__":
    main()
