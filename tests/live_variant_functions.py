r"""Manual check (not part of run_all.py): the model variants in the functions besides Text to image and Edit canvas
(user 20.11.: "die übrigen Funktionen testen wir kurz und bündig"; docs/plan/testrunden.md, "Modellvarianten in den übrigen
Funktionen"; values: pccomfy/variants.py).

Short round: each variant (Qwen Image 2.1 Turbo, Fibo 2.0 Dev) once per function (Fill, Expand, Remove, Sketch, Refine,
Upscale), one picture each, through the plugin's real bridge (Bridge.run) against the PhotoCraft simulator of
tests/test_reference_mode.py, with the Request the window builds from the model's start values plus the variant (as the
window sends it when the variant is the file in use). No A/B: our own files are known good in these functions; the
question is only whether the variant runs and gives a usable picture. LLM prompt writer off, one seed.

    python tests\live_variant_functions.py --dry      builds every graph against a fake ComfyUI and checks the variant values
    python tests\live_variant_functions.py            the real run (GPU; remind the user first)
    python tests\live_variant_functions.py --only qwen

Output: data/compare-variants/functions-<time>/ (<model>-<function>_in.png / _out.png, index.html input | result).
"""
import argparse
import copy
import html
import sys
import tempfile
import shutil
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import live_fill_flux as lff  # noqa: E402  (selection shapes)
import live_style_test as base  # noqa: E402  (make_app)
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator and FakeComfy)
from pccomfy import config as cfgmod, variants, workflows  # noqa: E402
from pccomfy.bridge import Bridge  # noqa: E402

PHOTOS = Path(r"C:\programs\testpics magnific\2MP")
SKETCH = ROOT / "data" / "sketch-test" / "round3-20261109-094900" / "eingabe" / "1.png"
SEED = 2011
VARIANT = {"qwen": "qwen_image_2.1_turbo_int8_convrot.safetensors", "fibo": "fibo2_dev_int8_convrot.safetensors"}
# function: (picture, prompt or remove target, selection shape, box as fractions)
CASES = {
    "inpaint": ("05_full-shot-kid.png", "a brown dog sitting in the grass", "lasso", (0.53, 0.68, 0.71, 0.98)),
    "outpaint": ("10_trees-growing-forest.png", "", None, None),
    # a whole object inside the selection (case R2 of live_original_size.py; 20.11.: a box through the family gave nothing to judge)
    "remove": ("11_view-modern-construction.png", "the orange dump truck", "rect", (0.70, 0.00, 1.00, 0.38)),
    "sketch": (None, "a cozy wooden cabin by a lake, photograph", None, None),
    "refine": ("11_view-modern-construction.png", None, None, None),
    "upscale": ("01_emotional-pet-having.png", None, None, None),
}
LABEL = {"inpaint": "Fill", "outpaint": "Expand", "remove": "Remove", "sketch": "Sketch", "refine": "Refine", "upscale": "Upscale"}
GROW = 0.25          # Expand: the canvas is made this much wider on the right (transparent margin)


def picture(fn: str) -> Image.Image:
    name = CASES[fn][0]
    src = SKETCH if fn == "sketch" else PHOTOS / name
    with Image.open(src) as im:
        im = im.convert("RGB")
    if fn == "upscale":              # Upscale 2x of a 2 MP photo would give 8 MP: start from about 0.5 MP
        im.thumbnail((1000, 1000))
    if fn == "outpaint":
        c = Image.new("RGBA", (im.width + round(im.width * GROW), im.height), (0, 0, 0, 0))
        c.paste(im.convert("RGBA"), (0, 0))
        return c
    return im


def request(app, model: str, fn: str):
    app.v_model.set(model)
    app.v_mode.set(fn)
    app._factory = True
    try:
        app._on_model()
        app._on_mode()
    finally:
        app._factory = False
    app.t_prompt.delete("1.0", "end")
    req = copy.deepcopy(app._request())
    req.variant = VARIANT[model]      # what the window sends when the variant is the file in use (gui_run: self._variant())
    req.sampler_override = {}         # the fields show the variant's values, so nothing differs from them
    req.enhance = False
    prompt = CASES[fn][1]
    if fn == "remove":
        req.remove_target = prompt
    if prompt is None:                # Refine / Upscale: the text the field starts with
        prompt = app._model().modes[fn].prompt_hint
    req.params = replace(req.params, prompt=prompt or "", seed=SEED)
    return req


def run_one(comfy, req, fn: str, pic: Image.Image):
    T.W, T.H = pic.size
    sel = lff.selection(pic.size, CASES[fn][2], CASES[fn][3]) if CASES[fn][2] else None
    tmp = tempfile.mkdtemp(prefix="variant-fn-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], sel))
    v = variants.get(req.variant)
    queue = comfy.queue
    if v is None:                        # our own file: nothing to rename
        return _run_plain(comfy, req, pic)

    def to_variant(graph, *k, **kw):     # what Model Links (or the variant alone in the folder) does: load the variant file
        for n in graph.values():
            if isinstance(n, dict) and n.get("class_type") == "UNETLoader" and n["inputs"].get("unet_name") == v.base:
                n["inputs"]["unet_name"] = v.file
        return queue(graph, *k, **kw)

    comfy.queue = to_variant
    try:
        Bridge(pc, comfy, tmp).run(req)
        # Upscale opens its result as a new document; the simulator shows it at the canvas size, keeps the file in .raw
        return getattr(pc.doc, "raw", None) or pc.composite(pc.doc)
    finally:
        comfy.queue = queue
        shutil.rmtree(tmp, ignore_errors=True)


def check_graph(model: str, fn: str, graph: dict):
    """The variant file is loaded, and its values stand in the main sampler (Qwen at full denoise: the sigma plan)."""
    assert VARIANT[model] in variants.unet_names(graph), variants.unet_names(graph)
    custom = [n for n in graph.values() if isinstance(n, dict) and n.get("class_type") == "SamplerCustom"]
    if custom:
        return "Sigma-Plan (8 Steps), CFG %g" % custom[0]["inputs"]["cfg"]
    ks = graph[workflows.main_sampler(graph)]["inputs"]
    return f"{ks.get('steps')} steps, CFG {ks.get('cfg')}, {ks.get('sampler_name')}/{ks.get('scheduler')}, denoise {ks.get('denoise', 1)}"


def page(out: Path, rows) -> str:
    cells = []
    for r in rows:
        img = (f'<img src="{r["key"]}_in.png"><img src="{r["key"]}_out.png">' if r.get("ok") else "")
        cells.append(f'<section><h2>{html.escape(r["title"])}</h2><p>{html.escape(r["info"])}</p><div>{img}</div></section>')
    return ("<!doctype html><meta charset=utf-8><title>Varianten je Funktion</title><style>body{font:14px sans-serif;"
            "background:#1e1e1e;color:#ddd;margin:16px}div{display:flex;gap:8px}img{max-width:49%;height:auto}"
            "h2{font-size:16px;margin:24px 0 4px}</style><h1>Modellvarianten je Funktion (links Eingabe, rechts Ergebnis)</h1>"
            + "".join(cells))


# --probe-expand (20.11.: the Qwen Turbo Expand of the forest was very bad, green hatching in the new part): which setting
# is to blame? (tag, variant file or "", turbo LoRA on, sampler_override)
EXPAND_PROBE = (
    ("1-turbo-sigmaplan", VARIANT["qwen"], False, {}),                                   # as PxC runs it now
    ("2-turbo-8-simple", VARIANT["qwen"], False, {"steps": 8, "sampler": "euler", "scheduler": "simple"}),
    ("3-turbo-16-simple", VARIANT["qwen"], False, {"steps": 16, "sampler": "euler", "scheduler": "simple"}),
    ("4-ours-turbo-lora", "", True, {}),                                                 # our file with its Turbo LoRA (8 steps)
    ("5-ours-standard", "", False, {}),                                                  # our file as Expand starts (25 steps)
)


def probe_expand(args):
    url = cfgmod.load()["comfyui"]["url"]
    app = base.make_app("http://127.0.0.1:1" if args.dry else url)
    out = ROOT / "data" / "compare-variants" / ("expand-probe-" + time.strftime("%Y%m%d-%H%M%S"))
    pic = picture("outpaint")
    rows = []
    if not args.dry:
        out.mkdir(parents=True, exist_ok=True)
        from live_expand_remote import Timed
        comfy = Timed(url)
        pic.convert("RGBA").save(out / "expand_in.png")
    for tag, var, lora, over in EXPAND_PROBE:
        req = request(app, "qwen", "outpaint")
        req.variant, req.turbo, req.sampler_override = var, lora, dict(over)
        fake = T.FakeComfy()
        run_one(fake, copy.deepcopy(req), "outpaint", pic)
        g = fake.graphs[0]
        unet = variants.unet_names(g)
        custom = [n for n in g.values() if isinstance(n, dict) and n.get("class_type") == "SamplerCustom"]
        ks = g[workflows.main_sampler(g)]["inputs"] if not custom else {}
        lo = any(isinstance(n, dict) and n.get("class_type") == "LoraLoaderModelOnly" for n in g.values())
        vals = ("Sigma-Plan 8, CFG %g" % custom[0]["inputs"]["cfg"]) if custom else f"{ks['steps']} steps, CFG {ks['cfg']}, {ks['sampler_name']}/{ks['scheduler']}"
        print(f"{tag}: {unet} LoRA {'an' if lo else 'aus'}, {vals}", flush=True)
        if args.dry:
            continue
        t0 = time.time()
        res = run_one(comfy, req, "outpaint", pic) if var else _run_plain(comfy, req, pic)
        res.save(out / f"{tag}.png")
        rows.append(f'<section><h2>{html.escape(tag)}</h2><p>{html.escape(vals)}, LoRA {"an" if lo else "aus"}, {time.time() - t0:.0f} s</p><img src="{tag}.png"></section>')
        (out / "index.html").write_text("<!doctype html><meta charset=utf-8><title>Qwen Expand Probe</title><style>body{font:14px sans-serif;"
                                        "background:#1e1e1e;color:#ddd;margin:16px}img{max-width:100%}</style>" + "".join(rows), encoding="utf-8")
    if not args.dry:
        print(f"Results: {(out / 'index.html').as_uri()}")
    app.root.destroy()


def _run_plain(comfy, req, pic):
    """Our own file: no variant, so nothing to rename."""
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="variant-fn-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], None))
    try:
        Bridge(pc, comfy, tmp).run(req)
        return pc.composite(pc.doc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="qwen,fibo")
    ap.add_argument("--fn", default=",".join(CASES), help="functions: " + ",".join(CASES))
    ap.add_argument("--probe-expand", action="store_true", help="Qwen Expand: Turbo file with three settings, our file with and without LoRA")
    args = ap.parse_args()
    if args.probe_expand:
        return probe_expand(args)
    models_ = [m for m in args.only.split(",") if m in VARIANT]
    url = cfgmod.load()["comfyui"]["url"]
    app = base.make_app("http://127.0.0.1:1" if args.dry else url)
    out = ROOT / "data" / "compare-variants" / ("functions-" + time.strftime("%Y%m%d-%H%M%S"))
    if not args.dry:
        out.mkdir(parents=True, exist_ok=True)
        from live_expand_remote import Timed
        comfy = Timed(url)
    rows = []
    for m in models_:
        for fn in [f for f in args.fn.split(",") if f in CASES]:
            title = f"{m} | {LABEL[fn]} | {VARIANT[m]}"
            pic = picture(fn)
            req = request(app, m, fn)
            fake = T.FakeComfy()
            run_one(fake, copy.deepcopy(req), fn, pic)
            vals = check_graph(m, fn, fake.graphs[0])
            if m == "fibo":
                assert vals.startswith("30 steps, CFG 5"), vals
            print(f"{title}: {vals}", flush=True)
            if args.dry:
                continue
            key = f"{m}-{fn}"
            t0 = time.time()
            try:
                res = run_one(comfy, req, fn, pic)
            except Exception as e:      # noqa: BLE001  one failed function must not stop the round
                msg = str(e).splitlines()[-1][:300] if str(e) else type(e).__name__
                print(f"  failed: {msg}", flush=True)
                rows.append(dict(key=key, title=title, info=f"FEHLER: {msg}", ok=False))
                continue
            secs = time.time() - t0
            pic.convert("RGBA").save(out / f"{key}_in.png")
            res.save(out / f"{key}_out.png")
            print(f"  done in {secs:.0f} s, {res.width}x{res.height}", flush=True)
            rows.append(dict(key=key, title=title, info=f"{vals}; {secs:.0f} s mit Laden; Ergebnis {res.width}x{res.height}", ok=True))
            (out / "index.html").write_text(page(out, rows), encoding="utf-8")
    if not args.dry:
        print(f"Results: {(out / 'index.html').as_uri()}")
    app.root.destroy()


if __name__ == "__main__":
    main()
