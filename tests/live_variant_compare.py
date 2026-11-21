"""Manual check (not part of run_all.py): do other variants of the main diffusion models run in PxC's own workflows, and how
does one Text to image result compare with the int8 ConvRot file PxC ships with? (user 20.11., docs/plan/entscheidungen.md)

For each model: the plugin's own Text to image workflow, once with our file (A) and once with the variant (B), same prompt,
seed and size, no LLM prompt writer. Where a variant needs other settings (a turbo merge without the Turbo LoRA, a non-turbo
model with more steps) the case says so and the report names it. Output:
    data/compare-variants/<time>/<model>_A.png / _B.png / _sheet.png (A | B | difference x4), report.md, index.html

    python tests\\live_variant_compare.py             needs ComfyUI running; uses the GPU (two runs per model)
    python tests\\live_variant_compare.py --dry       builds the graphs, checks which files ComfyUI lists; runs nothing
    python tests\\live_variant_compare.py --only qwen,moss
    python tests\\live_variant_compare.py --moss-nolora [--dry]   MOSS Base against SFT, DMD2 LoRA off, the plugin's own path

A model whose file A is not in ComfyUI's list runs B alone (the report says so). Nothing in the plugin changes.
"""
import argparse
import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

from live_flux2_file_compare import psnr, sheet  # noqa: E402
from pccomfy import workflows  # noqa: E402
from pccomfy.comfy import ComfyError, ComfyUI  # noqa: E402

PROMPT = ("A red fox standing in a snowy birch forest at golden hour, breath visible in the cold air, "
          "photograph, sharp detail")
SEED = 1234
SIZE = (1024, 1024)

# key: (label, workflow, our file A, variant B, changes for B: {"lora_off": True, "steps": n, "cfg": x}, note)
CASES = {
    "qwen": ("Qwen Image 2.1", "qwen-image-21-t2i.json", "qwen_image_2.1_int8_convrot.safetensors",
             "qwen_image_2.1_turbo_int8_convrot.safetensors", {"lora_off": True},
             "B has the Turbo LoRA merged in, so its Turbo LoRA is switched off (strength 0); 8 steps as A."),
    "moss": ("MOSS Image", "moss-image-t2i.json", "moss_image_sft_int8_convrot.safetensors",
             "moss_image_base_int8_convrot.safetensors", {}, "Same graph and LoRAs (dmd2, lenovo), only the file differs."),
    "fibo": ("Fibo 2.0", "fibo2-t2i.json", "fibo2_edit_turbo_int8_convrot.safetensors",
             "fibo2_dev_int8_convrot.safetensors", {"steps": 30, "cfg": 5.0},
             "B is the non-turbo Dev model: 30 steps, CFG 5 (A: 6 steps, CFG 1)."),
    "krea": ("Krea 2 Turbo", "krea2-turbo-t2i.json", "krea2_turbo_int8_convrot.safetensors",
             "krea2_turbo_fp8.safetensors", {}, "Same graph; fp8 instead of int8 ConvRot."),
    "minimax": ("MiniMax H3 Image", "minimax-h3-image-t2i.json", "minimax_h3_image_pruned_int8_convrot.safetensors",
                "minimax_h3_image_pruned_w4a8.safetensors", {}, "Same graph; w4a8 instead of int8 ConvRot."),
}

QWEN_TURBO_SIGMAS = "1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0"
# --probe (user 20.11.: a probe round before building the variants in): B = the variant with the values of the first run,
# C = the values of the model card / the official ComfyUI template
PROBE = {
    "qwen": ({"lora_off": True, "sigmas": QWEN_TURBO_SIGMAS, "cfg": 1.0, "sampler": "euler"},
             "C: the official Turbo template: fixed 8-step sigma schedule (ManualSigmas), euler, CFG 1, Turbo LoRA off "
             "(Qwen/Qwen-Image-2.1-Turbo, image_qwen_image_2_1_turbo_t2i.json); B: 8 steps, euler, simple."),
    "moss": ({"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"},
             "C: lora_dmd2 card (lodestones/MOSS-Image-Base-8-steps-dmd): Euler, CFG 1, 4-8 steps on Base; B: our SFT values "
             "(8 steps, CFG 1.5, sa_solver, sgm_uniform)."),
    "fibo": ({"steps": 50, "cfg": 5.0, "sampler": "euler", "scheduler": "simple"},
             "C: briaai/Fibo-2.0-dev card and image_fibo2_edit_dev_pe.json: 50 steps, CFG 5, euler, simple; B: 30 steps, CFG 5."),
}


def build(case: str, unet: str, variant: bool, loras=None, probe: dict | None = None) -> tuple[dict, str]:
    _label, wf, file_a, file_b, change, _note = CASES[case]
    tpl = workflows.bypass_prompt_writer(workflows.load_template(ROOT / "workflows" / wf), PROMPT)
    swapped = 0
    for node in tpl.values():
        if not isinstance(node, dict):
            continue
        inp = node.get("inputs", {})
        if node.get("class_type") == "UNETLoader" and inp.get("unet_name") in (file_a, file_b):
            inp["unet_name"] = unet
            swapped += 1
        if variant and change.get("lora_off") and node.get("class_type") == "LoraLoaderModelOnly":
            inp["strength_model"] = 0
        if variant and node.get("class_type") == "KSampler":
            for k in ("steps", "cfg"):
                if k in change:
                    inp[k] = change[k]
            for k, name in (("steps", "steps"), ("cfg", "cfg"), ("sampler", "sampler_name"), ("scheduler", "scheduler")):
                if probe and k in probe:
                    inp[name] = probe[k]
    assert swapped == 1, f"{wf}: expected one UNETLoader with {file_a}, found {swapped}"
    p = workflows.GenParams(prompt=PROMPT, seed=SEED, width=SIZE[0], height=SIZE[1])
    graph, out = workflows.apply_template(tpl, p, None, None)
    if probe and probe.get("sigmas"):          # the KSampler becomes SamplerCustom with a fixed sigma schedule
        nid = workflows.main_sampler(graph)
        ks = graph[nid]["inputs"]
        graph["pc_probe_sel"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": probe.get("sampler", "euler")}}
        graph["pc_probe_sig"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": probe["sigmas"]}}
        graph[nid] = {"class_type": "SamplerCustom", "_meta": graph[nid].get("_meta", {}), "inputs": {
            "model": ks["model"], "add_noise": True, "noise_seed": ks["seed"], "cfg": probe.get("cfg", ks["cfg"]),
            "positive": ks["positive"], "negative": ks["negative"], "sampler": ["pc_probe_sel", 0],
            "sigmas": ["pc_probe_sig", 0], "latent_image": ks["latent_image"]}}
    if loras is not None:              # the names ComfyUI lists ("qwen\x" may lie directly in loras/), as the plugin does
        graph, missing = workflows.fix_lora_names(graph, loras)
        assert not missing, f"{case}: LoRA files not in ComfyUI's list: {missing}"
    return graph, out


def page(out_dir: Path, rows: list[dict], tags=("A", "B")) -> str:
    """A small local page: per model A and B side by side at 100 %, a click on a picture swaps A/B."""
    parts = ["<!doctype html><meta charset=utf-8><title>Variants</title><style>body{font:14px sans-serif;background:#222;"
             "color:#eee;margin:16px}img{max-width:100%;cursor:pointer}.pair{display:flex;gap:8px}.pair div{flex:1}"
             "h2{margin-top:28px}</style><h1>Model variants: Text to image, same prompt and seed</h1>",
             f"<p>{html.escape(PROMPT)} · seed {SEED} · {SIZE[0]}×{SIZE[1]}. Click a picture to swap A and B.</p>"]
    for r in rows:
        parts.append(f"<h2>{html.escape(r['label'])}</h2><p>A = {html.escape(r['a'])} · B = {html.escape(r['b'])}<br>"
                     f"{html.escape(r['note'])}<br>{html.escape(r['result'])}</p><div class=pair>")
        for tag in tags:
            f = f"{r['key']}_{tag}.png"
            if (out_dir / f).exists():
                other = f"{r['key']}_{tags[1] if tag == tags[0] else tags[0]}.png"
                parts.append(f"<div><b>{tag}</b><br><img src='{f}' data-o='{other}' "
                             "onclick=\"var s=this.getAttribute('src');this.src=this.dataset.o;this.dataset.o=s\"></div>")
        parts.append("</div>")
    return "\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="build the graphs only, run nothing")
    ap.add_argument("--only", default="", help="comma-separated keys: " + ",".join(CASES))
    ap.add_argument("--probe", action="store_true", help="B (first-run values) against C (model card values): " + ",".join(PROBE))
    ap.add_argument("--edit", action="store_true", help="Edit canvas, Qwen and Fibo: our file against the variant")
    ap.add_argument("--images", default="", help="--edit: folder with the test photos")
    ap.add_argument("--pick", default="", help="--edit: comma-separated file name starts (e.g. 01_,06_)")
    ap.add_argument("--moss-nolora", action="store_true", help="MOSS Text to image, DMD2 off: SFT (A) against Base (B), 3 prompts")
    args = ap.parse_args()
    if args.moss_nolora:
        return moss_nolora_round(args)
    if args.edit:
        return edit_round(args)
    if args.probe:
        return probe_round(args)
    keys = [k for k in args.only.split(",") if k] or list(CASES)
    comfy = ComfyUI()
    known = set(comfy._choices("UNETLoader", "unet_name"))
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    plan = []
    for k in keys:
        label, _wf, a, b, _c, _n = CASES[k]
        build(k, b, True, loras)
        if b not in known:
            print(f"{label}: variant {b} is not in ComfyUI's list (restart ComfyUI after copying it) - skipped")
            continue
        plan.append((k, a in known))
        print(f"{label}: B ok" + ("" if a in known else f"; our file {a} missing, B runs alone"))
    if args.dry:
        print(f"ok: {sum(2 if has_a else 1 for _k, has_a in plan)} runs planned")
        return
    out_dir = ROOT / "data" / "compare-variants" / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, has_a in plan:
        label, _wf, a, b, _c, note = CASES[k]
        times = {}
        for tag, unet, variant in (("A", a, False), ("B", b, True)):
            if tag == "A" and not has_a:
                continue
            graph, out = build(k, unet, variant, loras)
            t0 = time.monotonic()
            try:
                hist = comfy.wait(comfy.queue(graph))
            except ComfyError as e:           # e.g. a text encoder of that model is not on this PC: note it, go on
                times["error"] = str(e).splitlines()[-1][:300]
                print(f"{label} {tag}: failed: {times['error']}")
                break
            times[tag] = time.monotonic() - t0
            comfy.output_images(hist, out)[0].save(out_dir / f"{k}_{tag}.png")
            print(f"{label} {tag}: {times[tag]:.1f} s (includes loading the model)")
        if "error" in times:
            result = f"not run: {times['error']}"
        elif has_a:
            ia, ib = Image.open(out_dir / f"{k}_A.png"), Image.open(out_dir / f"{k}_B.png")
            mae, db = psnr(ia, ib if ib.size == ia.size else ib.resize(ia.size))
            sheet(ia, ib if ib.size == ia.size else ib.resize(ia.size)).save(out_dir / f"{k}_sheet.png")
            result = f"time A {times['A']:.0f} s, B {times['B']:.0f} s (each includes loading); mean diff {mae:.1f}, PSNR {db:.1f} dB"
        else:
            result = f"B only ({times['B']:.0f} s with loading): our file A is not on this PC"
        rows.append(dict(key=k, label=label, a=a, b=b, note=note, result=result))
    report = ["# Model variants: Text to image against our int8 ConvRot files", "",
              f"Prompt: {PROMPT}", f"Seed {SEED}, {SIZE[0]}x{SIZE[1]}, no LLM prompt writer.", "",
              "| model | A (ours) | B (variant) | note | result |", "|---|---|---|---|---|",
              *[f"| {r['label']} | `{r['a']}` | `{r['b']}` | {r['note']} | {r['result']} |" for r in rows], "",
              "PSNR says only how close B is to A, not which is better: judge the pictures by eye (index.html)."]
    (out_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (out_dir / "index.html").write_text(page(out_dir, rows), encoding="utf-8")
    (out_dir / "cases.json").write_text(json.dumps({k: CASES[k][:5] for k in keys}, indent=1), encoding="utf-8")
    print("\n".join(report))
    print(f"\nResults: {out_dir.as_uri()}/index.html")


def probe_round(args):
    """B: the variant with the values of the first run; C: the same file with the values of its model card / template."""
    keys = [k for k in args.only.split(",") if k] or list(PROBE)
    comfy = ComfyUI()
    known = set(comfy._choices("UNETLoader", "unet_name"))
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    keys = [k for k in keys if CASES[k][3] in known]
    for k in keys:
        build(k, CASES[k][3], True, loras)
        build(k, CASES[k][3], True, loras, PROBE[k][0])
    print(f"probe: {', '.join(keys)} ({2 * len(keys)} runs)")
    if args.dry:
        return
    out_dir = ROOT / "data" / "compare-variants" / ("probe-" + time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for k in keys:
        label, _wf, _a, b, _c, _note = CASES[k]
        times = {}
        for tag, probe in (("B", None), ("C", PROBE[k][0])):
            graph, out = build(k, b, True, loras, probe)
            t0 = time.monotonic()
            try:
                hist = comfy.wait(comfy.queue(graph))
            except ComfyError as e:
                times["error"] = str(e).splitlines()[-1][:300]
                print(f"{label} {tag}: failed: {times['error']}")
                break
            times[tag] = time.monotonic() - t0
            comfy.output_images(hist, out)[0].save(out_dir / f"{k}_{tag}.png")
            print(f"{label} {tag}: {times[tag]:.1f} s")
        result = (f"not run: {times['error']}" if "error" in times
                  else f"time B {times['B']:.0f} s, C {times['C']:.0f} s (B includes loading the model)")
        rows.append(dict(key=k, label=label, a="B (first run)", b="C (model card) - " + b, note=PROBE[k][1], result=result))
    (out_dir / "index.html").write_text(page(out_dir, rows, ("B", "C")), encoding="utf-8")
    print("\n".join(f"{r['label']}: {r['result']}" for r in rows))
    print(f"\nResults: {out_dir.as_uri()}/index.html")


# --edit (user 20.11.: "ein testlauf mit einem canvas edit bei qwen und fibo"): Edit canvas as the window starts it, our file
# (A) against the variant with its chosen values (B; docs/plan/entscheidungen.md 20.11.: model card values, Fibo 30 steps)
EDIT_PROMPT = "Make it winter, with snow on the ground and snow falling"
EDIT = {
    "qwen": ("qwen-image-21-edit.json", "Turbo LoRA off as the tab starts (25 steps)",
             {"lora_off": True, "sigmas": QWEN_TURBO_SIGMAS, "cfg": 1.0, "sampler": "euler"},
             "Turbo int8, LoRA off, official fixed 8-step sigma schedule, CFG 1, euler"),
    "fibo": ("fibo2-edit.json", "Edit Turbo, 4 steps, CFG 1 (the workflow's values)",
             {"steps": 30, "cfg": 5.0, "sampler": "euler", "scheduler": "simple"},
             "Dev int8, 30 steps, CFG 5, euler/simple"),
}


def build_edit(case: str, variant: bool, image_name: str, size, loras) -> tuple[dict, str]:
    wf, _da, probe, _db = EDIT[case]
    _label, _wf, file_a, file_b, _c, _n = CASES[case]
    tpl = workflows.bypass_prompt_writer(workflows.load_template(ROOT / "workflows" / wf), EDIT_PROMPT)
    tpl = workflows.bypass_lora(tpl)                 # Qwen Edit starts with the Turbo LoRA off; Fibo has none
    swapped = 0
    for node in tpl.values():
        if isinstance(node, dict) and node.get("class_type") == "UNETLoader" and node["inputs"].get("unet_name") in (file_a, file_b):
            node["inputs"]["unet_name"] = file_b if variant else file_a
            swapped += 1
        if variant and isinstance(node, dict) and node.get("class_type") == "KSampler":
            for k, name in (("steps", "steps"), ("cfg", "cfg"), ("sampler", "sampler_name"), ("scheduler", "scheduler")):
                if k in probe:
                    node["inputs"][name] = probe[k]
    assert swapped == 1, f"{wf}: expected one UNETLoader with {file_a}, found {swapped}"
    p = workflows.GenParams(prompt=EDIT_PROMPT, seed=SEED, width=size[0], height=size[1])
    graph, out = workflows.apply_template(tpl, p, image_name, None)
    if variant and probe.get("sigmas"):
        nid = workflows.main_sampler(graph)
        ks = graph[nid]["inputs"]
        graph["pc_probe_sel"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": probe.get("sampler", "euler")}}
        graph["pc_probe_sig"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": probe["sigmas"]}}
        graph[nid] = {"class_type": "SamplerCustom", "_meta": graph[nid].get("_meta", {}), "inputs": {
            "model": ks["model"], "add_noise": True, "noise_seed": ks["seed"], "cfg": probe.get("cfg", ks["cfg"]),
            "positive": ks["positive"], "negative": ks["negative"], "sampler": ["pc_probe_sel", 0],
            "sigmas": ["pc_probe_sig", 0], "latent_image": ks["latent_image"]}}
    if loras is not None:
        graph, missing = workflows.fix_lora_names(graph, loras)
        assert not missing, missing
    return graph, out


def edit_round(args):
    if not args.images:
        raise SystemExit("--edit needs --images <folder> and --pick <name,name> (e.g. the 2MP test photos)")
    folder = Path(args.images)
    picks = [n for n in args.pick.split(",") if n] if args.pick else []
    files = [f for f in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")) if not picks or any(f.name.startswith(n) for n in picks)]
    comfy = ComfyUI()
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    out_dir = ROOT / "data" / "compare-variants" / ("edit-" + time.strftime("%Y%m%d-%H%M%S"))
    jobs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        k = (1024 * 1024 / (im.width * im.height)) ** 0.5          # about 1 MP, a multiple of 16, as Edit canvas sends it
        size = (max(16, round(im.width * k / 16) * 16), max(16, round(im.height * k / 16) * 16))
        jobs.append((f.stem, im.resize(size, Image.LANCZOS), size))
    for case in EDIT:
        for variant in (False, True):
            build_edit(case, variant, "x.png", jobs[0][2], loras)
    print(f"edit: {len(jobs)} pictures x {len(EDIT)} models x 2 = {len(jobs) * len(EDIT) * 2} runs")
    if args.dry:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for stem, im, size in jobs:
        im.save(out_dir / f"{stem}_source.png")
        name = comfy.upload_image(im, f"pccomfy-variant-{stem}.png")
        for case in EDIT:
            times = {}
            for tag, variant in (("A", False), ("B", True)):
                graph, out = build_edit(case, variant, name, size, loras)
                t0 = time.monotonic()
                try:
                    hist = comfy.wait(comfy.queue(graph))
                except ComfyError as e:
                    times["error"] = str(e).splitlines()[-1][:300]
                    print(f"{case} {stem} {tag}: failed: {times['error']}")
                    break
                times[tag] = time.monotonic() - t0
                comfy.output_images(hist, out)[0].save(out_dir / f"{case}-{stem}_{tag}.png")
                print(f"{case} {stem} {tag}: {times[tag]:.1f} s")
            wf, da, _p, db = EDIT[case]
            rows.append(dict(key=f"{case}-{stem}", label=f"{CASES[case][0]} · {stem}", a=f"{CASES[case][2]} ({da})",
                             b=f"{CASES[case][3]} ({db})", note=f"Edit canvas, prompt: {EDIT_PROMPT}",
                             result=times.get("error") or f"time A {times['A']:.0f} s, B {times['B']:.0f} s"))
    (out_dir / "index.html").write_text(page(out_dir, rows), encoding="utf-8")
    print(f"\nResults: {out_dir.as_uri()}/index.html")


# --moss-nolora (user 20.11.: MOSS Base without the DMD2 LoRA runs with our SFT values, "aber einen testlauf damit machen"):
# the graph comes from the plugin's own path (bridge._graph with Request.variant), MOSS Text to image as the tab starts it:
# DMD2 off (25 steps, CFG 3), UltraReal LoRA on, SLG off, no prompt writer, 1280 x 1280.
MOSS_PROMPTS = (
    ("fox", PROMPT),
    ("portrait", "Close-up portrait of an elderly fisherman with a weathered face and a knitted cap, soft window light, photograph"),
    ("kitchen", "A sunlit Scandinavian kitchen with oak cabinets, a bowl of lemons on the counter and plants by the window, interior photograph"),
)
MOSS_SIZE = (1280, 1280)


def build_moss(unet_variant: str, prompt: str, loras) -> tuple[dict, str]:
    from pccomfy import bridge
    wf = str(ROOT / "workflows" / "moss-image-t2i.json")
    p = workflows.GenParams(prompt=prompt, seed=SEED, width=MOSS_SIZE[0], height=MOSS_SIZE[1])
    req = bridge.Request(mode="txt2img", workflow=wf, params=p, enhance=False, turbo=False, stage_on=True, stages_off=["7"],
                         variant=unet_variant)
    graph, out = bridge.Bridge._graph(object(), req, p, None, None, wf)
    if unet_variant:                    # what inventory.apply_names does when ComfyUI lists only the variant
        for node in graph.values():
            if isinstance(node, dict) and node.get("class_type") == "UNETLoader":
                node["inputs"]["unet_name"] = unet_variant
    if loras is not None:
        graph, missing = workflows.fix_lora_names(graph, loras)
        assert not missing, missing
    return graph, out


def moss_nolora_round(args):
    a, b = CASES["moss"][2], CASES["moss"][3]
    comfy = ComfyUI()
    known = set(comfy._choices("UNETLoader", "unet_name"))
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    for f in (a, b):
        if f not in known:
            raise SystemExit(f"{f} is not in ComfyUI's list")
    for _k, prompt in MOSS_PROMPTS:
        for v in ("", b):
            g, _ = build_moss(v, prompt, loras)
            ks = g[workflows.main_sampler(g)]["inputs"]
            assert (ks["steps"], ks["cfg"]) == (25, 3.0), ks
            assert not any("DMD2" in str(n.get("_meta", {}).get("title", "")) for n in g.values() if isinstance(n, dict))
            assert [n["inputs"]["unet_name"] for n in g.values() if isinstance(n, dict) and n.get("class_type") == "UNETLoader"] == [v or a]
    print(f"moss-nolora: {len(MOSS_PROMPTS)} prompts x 2 = {2 * len(MOSS_PROMPTS)} runs (25 steps, CFG 3, DMD2 off, {MOSS_SIZE[0]}x{MOSS_SIZE[1]})")
    if args.dry:
        return
    out_dir = ROOT / "data" / "compare-variants" / ("moss-nolora-" + time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, prompt in MOSS_PROMPTS:
        times = {}
        for tag, v in (("A", ""), ("B", b)):
            graph, out = build_moss(v, prompt, loras)
            t0 = time.monotonic()
            try:
                hist = comfy.wait(comfy.queue(graph))
            except ComfyError as e:
                times["error"] = str(e).splitlines()[-1][:300]
                print(f"moss {k} {tag}: failed: {times['error']}")
                break
            times[tag] = time.monotonic() - t0
            comfy.output_images(hist, out)[0].save(out_dir / f"moss-{k}_{tag}.png")
        rows.append(dict(key=f"moss-{k}", label=f"MOSS Image · {k}", a=f"{a} (SFT)", b=f"{b} (Base)",
                         note=f"DMD2 off, 25 steps, CFG 3, UltraReal on, seed {SEED}. Prompt: {prompt}",
                         result=times.get("error") or f"time A {times['A']:.0f} s, B {times['B']:.0f} s (with loading)"))
    (out_dir / "index.html").write_text(page(out_dir, rows), encoding="utf-8")
    print(f"Results: {out_dir.as_uri()}/index.html")


if __name__ == "__main__":
    main()
