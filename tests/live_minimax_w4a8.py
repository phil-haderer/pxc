r"""Manual check (not part of run_all.py): MiniMax H3 Image with the w4a8 UNet against our int8 ConvRot file, through the
plugin's real bridge (user 21.11., "4A"; docs/plan/entscheidungen.md: w4a8 unlocks MiniMax only after this test).

Text to image (three prompts) and Edit (three photos), each once with our file (A) and once with w4a8 (B): the Request
the window builds from MiniMax's start values (4 MP, lcm, the prompt writer off in both since 17.11.), same seed, the PhotoCraft
simulator of tests/test_reference_mode.py. B is what PxC sends when w4a8 is the file in use (Model Links): the variant
in the Request and the UNet file renamed in the graph.

    python tests\live_minimax_w4a8.py --dry      builds every graph against a fake ComfyUI, checks the UNet files; runs nothing
    python tests\live_minimax_w4a8.py            the real run (GPU, 12 pictures; remind the user first)
    python tests\live_minimax_w4a8.py --only t2i (or edit)

Output: data/compare-variants/minimax-w4a8-<time>/ (<case>_A.png / _B.png, times in report.md, A/B page index.html with
100 %, A/B and toggle from tools/ab_viewer_template.html). Nothing in the plugin changes.
"""
import argparse
import copy
import json
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import live_style_test as base  # noqa: E402  (make_app)
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator and FakeComfy)
from pccomfy import config as cfgmod, variants  # noqa: E402
from pccomfy.bridge import Bridge  # noqa: E402

PHOTOS = Path(r"C:\programs\testpics magnific\2MP")
SEED = 2111
OURS = "minimax_h3_image_pruned_int8_convrot.safetensors"
W4A8 = "minimax_h3_image_pruned_w4a8.safetensors"
# key: (mode, photo or None, prompt)
CASES = {
    "t2i-1": ("txt2img", None, "A watchmaker's workshop at dusk, an old man at the bench with a loupe, brass gears and "
                               "tools spread out, warm desk lamp, photograph"),
    "t2i-2": ("txt2img", None, "Poster for a jazz night: the words \"BLUE NOTE FRIDAY\" in big white letters, a saxophone "
                               "player in silhouette against a deep blue background"),
    "t2i-3": ("txt2img", None, "A red fox in a snowy birch forest at golden hour, breath visible in the cold air"),
    "edit-1": ("edit", "01_emotional-pet-having.png", "make it night, the room lit only by a warm lamp"),
    "edit-2": ("edit", "06_happy-family-park.png", "turn it into a watercolor painting"),
    "edit-3": ("edit", "11_view-modern-construction.png", "remove the orange dump truck"),
}
TITLE = {"txt2img": "Text to image", "edit": "Edit"}


def picture(case: str) -> Image.Image:
    photo = CASES[case][1]
    if photo is None:                    # Text to image: an empty canvas, as when nothing is open in PhotoCraft
        return Image.new("RGB", (1024, 1024), (255, 255, 255))
    with Image.open(PHOTOS / photo) as im:
        return im.convert("RGB")


def request(app, case: str, variant: str):
    mode = CASES[case][0]
    app.v_model.set("minimax")
    app.v_mode.set(mode)
    app._factory = True
    try:
        app._on_model()
        app._on_mode()
    finally:
        app._factory = False
    app.t_prompt.delete("1.0", "end")
    req = copy.deepcopy(app._request())
    req.variant = variant                # "" = our file; the w4a8 name = what the window sends when it is in use
    req.sampler_override = {}
    req.params = replace(req.params, prompt=CASES[case][2], seed=SEED)
    return req


def run_one(comfy, req, pic: Image.Image) -> Image.Image:
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="minimax-w4a8-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], None))
    queue = comfy.queue

    def to_w4a8(graph, *k, **kw):        # what Model Links does: load the w4a8 file instead of ours
        for n in graph.values():
            if isinstance(n, dict) and n.get("class_type") == "UNETLoader" and n["inputs"].get("unet_name") == OURS:
                n["inputs"]["unet_name"] = W4A8
        return queue(graph, *k, **kw)

    if req.variant:
        comfy.queue = to_w4a8
    try:
        Bridge(pc, comfy, tmp).run(req)
        return getattr(pc.doc, "raw", None) or pc.composite(pc.doc)
    finally:
        comfy.queue = queue
        shutil.rmtree(tmp, ignore_errors=True)


def describe(graph: dict) -> str:
    unet = variants.unet_names(graph)
    ks = [n["inputs"] for n in graph.values() if isinstance(n, dict) and n.get("class_type") == "KSampler"]
    writer = any(isinstance(n, dict) and str(n.get("class_type", "")).startswith("TextGenerate") for n in graph.values())
    k = ks[0] if ks else {}
    return (f"{', '.join(unet)}; {k.get('steps')} steps, CFG {k.get('cfg')}, {k.get('sampler_name')}/{k.get('scheduler')}; "
            f"Schreiber {'an' if writer else 'aus'}")


def page(out: Path, rows: list[dict]) -> None:
    sets = []
    for r in rows:
        imgs = []
        for lab in ("A", "B"):
            if not (out / f"{r['case']}_{lab}.png").exists():
                continue
            th = out / "thumbs" / f"{r['case']}_{lab}.jpg"
            if not th.exists():
                th.parent.mkdir(exist_ok=True)
                im = Image.open(out / f"{r['case']}_{lab}.png").convert("RGB")
                im.thumbnail((120, 90), Image.LANCZOS)
                im.save(th, quality=85)
            name = "int8 ConvRot (unsere)" if lab == "A" else "w4a8"
            imgs.append({"label": f"{lab}: {name}, {r['sec_' + lab]:.0f} s", "short": f"{lab} {name}",
                         "src": f"{r['case']}_{lab}.png", "thumb": f"thumbs/{r['case']}_{lab}.jpg",
                         "prompt": r["prompt"], "id": f"{r['case']}_{lab}"})
        if imgs:
            sets.append({"title": r["title"], "images": imgs})
    tpl = (ROOT / "tools" / "ab_viewer_template.html").read_text(encoding="utf-8")
    html = tpl.replace("<title>Fibo Upscale A/B</title>", "<title>MiniMax w4a8 A/B</title>").replace(
        "__SETS__", json.dumps(sets, ensure_ascii=False))
    (out / "index.html").write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="", help="t2i or edit")
    args = ap.parse_args()
    cases = [c for c in CASES if not args.only or c.startswith(args.only)]
    url = cfgmod.load()["comfyui"]["url"]
    app = base.make_app("http://127.0.0.1:1" if args.dry else url)
    out = ROOT / "data" / "compare-variants" / ("minimax-w4a8-" + time.strftime("%Y%m%d-%H%M%S"))
    assert variants.get(W4A8) is not None and variants.get(W4A8).base == OURS, "w4a8 is no longer a known variant"
    for case in cases:                   # every graph against the fake ComfyUI first: the right file, both runs alike
        info = {}
        for lab, var in (("A", ""), ("B", W4A8)):
            fake = T.FakeComfy()
            run_one(fake, request(app, case, var), picture(case))
            g = fake.graphs[-1]
            want = OURS if lab == "A" else W4A8
            assert want in variants.unet_names(g), (case, lab, variants.unet_names(g))
            info[lab] = describe(g)
        print(f"{case}: A {info['A']} | B {info['B']}", flush=True)
    if args.dry:
        print(f"ok: {len(cases) * 2} graphs build, A loads {OURS}, B loads {W4A8}")
        app.root.destroy()
        return
    out.mkdir(parents=True, exist_ok=True)
    from live_expand_remote import Timed
    comfy = Timed(url)
    rows = []
    for lab, var in (("A", ""), ("B", W4A8)):     # file by file, so every UNet loads once
        for case in cases:
            row = next((r for r in rows if r["case"] == case), None)
            if row is None:
                mode, photo, prompt = CASES[case]
                row = {"case": case, "title": f"{TITLE[mode]}: {photo or prompt[:40]}", "prompt": prompt}
                rows.append(row)
            pic = picture(case)
            t0 = time.time()
            try:
                res = run_one(comfy, request(app, case, var), pic)
            except Exception as e:      # noqa: BLE001  one failed picture must not stop the round
                msg = str(e).splitlines()[-1][:300] if str(e) else type(e).__name__
                print(f"  {case} {lab} failed: {msg}", flush=True)
                row[f"sec_{lab}"], row[f"err_{lab}"] = 0.0, msg
                continue
            row[f"sec_{lab}"] = time.time() - t0
            res.save(out / f"{case}_{lab}.png")
            print(f"  {case} {lab}: {row[f'sec_{lab}']:.0f} s, {res.width}x{res.height}", flush=True)
            page(out, rows)
    lines = ["# MiniMax w4a8 gegen int8 ConvRot", "", f"Seed {SEED}, Startwerte des Fensters.", "",
             "| Fall | A int8 (s) | B w4a8 (s) | Fehler |", "|---|---|---|---|"]
    for r in rows:
        err = "; ".join(f"{lab}: {r[f'err_{lab}']}" for lab in "AB" if r.get(f"err_{lab}")) or "–"
        lines.append(f"| {r['title']} | {r.get('sec_A', 0):.0f} | {r.get('sec_B', 0):.0f} | {err} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"Results: {(out / 'index.html').as_uri()}")
    app.root.destroy()


if __name__ == "__main__":
    main()
