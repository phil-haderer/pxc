"""Live test (GPU, only on the user's word): "Reference at scribble" (plan B, docs/archiv/plan-edit-sketch-stile.md). A red scribble
on a photo marks where an object goes, a reference picture shows which object. Generated the way Scribble on photo works
(scribble.find, only the crop around it, scribble.put_back with colour match and fading edge), but with the model's
Multi image edit workflow, so the reference goes in as <ref_image_1> / image 2 / <image2>.

Variants (user 15.11.: Flux 3, Flux 2 and Qwen): Flux 3 with and without the scribble's box as <obj_1>, each with and without
BFL's prompt upsampler; Flux 2 and Qwen without box, with and without the upsampler. The upsampler sees only the crop, not the
reference: it gets the object's name, and the sentence "The ... looks exactly like <ref>" is appended to its caption.

    python tests\\live_ref_scribble.py scribbles --photos <folder> --refs <folder>   (draw the scribbles, previews; no GPU)
    python tests\\live_ref_scribble.py run --photos <folder> --refs <folder> [--models flux3 flux2 qwen] [--dry] [--into <dir>]
    python tests\\live_sketch.py rate <folder>       (blind rating, the input shows photo + reference side by side)
    python tests\\live_sketch.py summary <folder>

Output: data\\sketch-test\\ref-scribble-<time>\\ (eingabe\\, bilder\\, roh\\, vorschau\\, key.json). The photo folders are
arguments, never fixed here (the export scan, docs/plan/release.md).
"""
import argparse
import json
import random
import socket
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image, ImageDraw, ImageOps  # noqa: E402

from pccomfy import config as cfgmod, imaging, inventory, models, refslots, scribble, workflows  # noqa: E402
from pccomfy.bridge import Bridge  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402
import live_sketch as ls  # noqa: E402

BASE = ls.BASE
MODELS = ("flux3", "flux2", "qwen")
SEED = 1234
# (photo in --photos, scribble shape, centre x, centre y, width (shares of the photo), style, reference in --refs, object)
PAIRS = [
    ("Screenshot 2025-03-14 091321.png", "dog", 0.30, 0.86, 0.22, "hatch", "Screenshot 2025-04-10 184350.png", "beagle dog"),
    ("signal-2024-11-02-213543_002.jpeg", "dog", 0.30, 0.80, 0.16, "outline", "Screenshot 2025-04-10 184005.png", "golden retriever dog"),
    ("signal-2024-11-02-214028_006.jpeg", "person", 0.69, 0.66, 0.09, "outline", "Screenshot 2025-03-14 091500.png", "hiker"),
    ("signal-2024-11-02-214028_009.jpeg", "person", 0.16, 0.84, 0.13, "outline", "Screenshot 2025-05-25 201643.png", "man"),
    ("signal-2024-11-02-214028_005.jpeg", "car", 0.74, 0.80, 0.20, "fill", "signal-2024-11-02-214028_002.jpeg", "toy rover"),
    ("signal-2024-11-02-214028_006.jpeg", "box", 0.66, 0.86, 0.10, "hatch", "Screenshot 2025-05-13 204208.png", "wicker basket"),
]
TEXT = ("Replace the coloured scribbles{where} with {obj}, realistic and matching the light and perspective of the photo. "
        "Remove every scribble line and keep everything else unchanged.")
SUFFIX = "The {name}{where} looks exactly like {tag}."
VARIANTS = {"flux3": [(False, False), (False, True), (True, False), (True, True)],      # (box, upsampler)
            "flux2": [(False, False), (False, True)], "qwen": [(False, False), (False, True)]}


def variant_name(box: bool, up: bool) -> str:
    return ("mit Box" if box else "ohne Box") + " · " + ("mit Upsampler" if up else "ohne Upsampler")


def load(path: Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def items(a) -> list:
    out = []
    for k, (photo, shape, fx, fy, fw, style, ref, name) in enumerate(PAIRS):
        pic = ls.draw_scribble(load(a.photos / photo), shape, fx, fy, fw, style, seed=100 + k)
        out.append({"k": k, "photo": photo, "ref": ref, "name": name, "pic": pic, "refim": load(a.refs / ref),
                    "input": f"{k + 1:02d} {name}.png"})
    return out


def side_by_side(pic: Image.Image, ref: Image.Image) -> Image.Image:
    """What the rating window shows as the input: the scribbled photo, the reference beside it (same height)."""
    h = pic.height
    r = ref.resize((max(1, round(ref.width * h / ref.height)), h), Image.LANCZOS)
    im = Image.new("RGB", (pic.width + 16 + r.width, h), (40, 40, 40))
    im.paste(pic, (0, 0))
    im.paste(r, (pic.width + 16, 0))
    return im


def cmd_scribbles(a):
    out = BASE / "ref-scribble-kritzel"
    out.mkdir(parents=True, exist_ok=True)
    for s in items(a):
        f = scribble.find(s["pic"])
        im = side_by_side(s["pic"], s["refim"])
        if f is None:
            print(f"  {s['input']}: NO scribble found", flush=True)
        else:
            reg = scribble.region(f, s["pic"].size)
            d = ImageDraw.Draw(im)
            d.rectangle((reg.x, reg.y, reg.x + reg.w - 1, reg.y + reg.h - 1), outline=(255, 220, 0), width=3)
            d.rectangle((f.box.x, f.box.y, f.box.x + f.box.w - 1, f.box.y + f.box.h - 1), outline=(0, 230, 255), width=3)
            print(f"  {s['input']}: {f.how}, box {f.box.w}x{f.box.h}, crop {reg.w}x{reg.h} of {s['pic'].width}x{s['pic'].height}",
                  flush=True)
        im.thumbnail((1400, 700))
        im.save(out / s["input"])
    print(f"Previews (blue = scribble box, yellow = crop): {out}")


def tagged(graph: dict, gen: str, suffix: str) -> None:
    """Every input linked to the upsampler's text gets the caption plus `suffix` (the reference's tag) instead."""
    cat = str(max(int(x) for x in graph if str(x).isdigit()) + 1)
    graph[cat] = {"class_type": "StringConcatenate", "_meta": {"title": "caption + reference"},
                  "inputs": {"string_a": [gen, 0], "string_b": suffix, "delimiter": " "}}
    for k, n in list(graph.items()):
        if k == cat or not isinstance(n, dict):
            continue
        for f, v in n.get("inputs", {}).items():
            if v == [gen, 0] and n.get("class_type") != "PreviewAny":
                n["inputs"][f] = [cat, 0]


BUILT = "Plugin-Weg · eigener Schreiber"


def run_built(a, b, app, comfy, key, out, mk, s, n, total) -> bool:
    """One picture the way the window runs "Scribble with reference" (gebaut 15.11.): the model's Scribble mode request
    with its own prompt writer on, the chip's text with the object typed in, the reference in the one slot; Bridge._graph
    splits the reference sentence off and appends it to what the writer wrote. Put back as Bridge does (put_back, the layer
    mask following the object). Returns False when nothing was made."""
    model = models.BY_KEY[mk]
    req, label = ls.edit_request(app, mk, models.SCRIBBLE_MODE)
    req = replace(req, enhance=True, scribble=True)
    wf = req.workflow
    mult = max(workflows.size_multiple(workflows.load_template(wf)), 1)
    pic = s["pic"]
    found = scribble.find(pic)
    if found is None:
        print(f"   {s['input']}: no scribble found, left out", flush=True)
        return False
    reg = scribble.region(found, pic.size)
    base = imaging.native_base(reg.w, reg.h, req.base_res, req.native_mp) if req.native else req.base_res
    gw, gh = imaging.gen_size(reg.w, reg.h, base, multiple=mult)
    text = models.ref_scribble_text(model.tag_style).replace(models.REF_MARK, "a " + s["name"])
    refim = refslots.prepare_image(s["refim"], mult, model.ref_side)
    p = replace(req.params, prompt=text, seed=SEED, width=gw, height=gh, denoise=1.0)
    if a.dry:
        image_name, ref_name = "dry.png", ["dry-ref.png"]
    else:
        image_name = comfy.upload_image(pic.crop(reg.pil()).resize((gw, gh), Image.LANCZOS), f"pcc-refscr-{mk}-{s['k']}.png")
        ref_name = [comfy.upload_image(refim, f"pcc-refscr-{mk}-{s['k']}-ref.png")]
    graph, out_node = b._graph(req, p, image_name, None, wf, ref_name)
    joined = [nid for nid, nd in graph.items() if isinstance(nd, dict)
              and nd.get("_meta", {}).get("title") == "Written prompt + reference sentence"]
    show = next((nid for nid, nd in graph.items() if isinstance(nd, dict) and "pc:vgl" in nd.get("_meta", {}).get("title", "")),
                None)
    if a.dry:
        print(f"{n}/{total} {label} · {BUILT} · {s['name']}: crop {reg.w}x{reg.h} -> {gw}x{gh}, reference "
              f"{refim.width}x{refim.height}, writer + reference sentence {'yes' if joined else 'NO'}, "
              f"sentence: {graph[joined[0]]['inputs']['string_b'] if joined else '-'}", flush=True)
        return False
    t0 = time.time()
    hist = b._wait(comfy.queue(graph), graph, str(wf), 0, 1, "", lambda *x, **k: None)
    res = comfy.output_images(hist, out_node)[0].convert("RGB").resize((reg.w, reg.h), Image.LANCZOS)
    layer, _m = scribble.put_back(pic, res, found, reg)
    mask = scribble.object_mask(pic, layer, found, reg)
    out_im = Image.composite(layer, pic, mask)
    fid = f"{len(key) + 1:04d}"
    out_im.save(out / "bilder" / f"{fid}.png")
    res.save(out / "roh" / f"{fid}.png")
    rec = {"model": label, "model_key": mk, "file": s["photo"], "ref": s["ref"], "input": s["input"], "kind": "photo",
           "desc": s["name"], "prompt": "Reference at scribble", "variant": BUILT, "way": BUILT, "seed": SEED,
           "box": [found.box.x, found.box.y, found.box.w, found.box.h], "region": [reg.x, reg.y, reg.w, reg.h],
           "text": text, "size": [gw, gh], "ref_size": [refim.width, refim.height], "seconds": round(time.time() - t0)}
    if show:
        rec["caption"] = ls.caption_of(hist, show)
    key[fid] = rec
    print(f"{n}/{total} {label} · {BUILT} · {s['name']}: {rec['seconds']} s", flush=True)
    return True


def cmd_run(a):
    its = items(a)
    out = Path(a.into) if a.into else BASE / f"ref-scribble-{time.strftime('%Y%m%d-%H%M%S')}"
    for sub in ("bilder", "eingabe", "roh"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for s in its:
        side_by_side(s["pic"], s["refim"]).save(out / "eingabe" / s["input"])
    kf = out / "key.json"
    key = json.load(open(kf, encoding="utf-8"))["items"] if kf.exists() else {}

    def write_key():
        order = list(key)
        random.Random(80).shuffle(order)
        json.dump({"items": key, "order": order, "part": "R5", "round": "ref-scribble", "text": TEXT, "suffix": SUFFIX,
                   "system_prompt": ls.EDIT_UPSAMPLER_SYSTEM}, open(kf, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    if a.built:      # the way the plugin runs it since 15.11.: Scribble mode workflow, the model's own prompt writer
        jobs = [(mk, s, None, None) for mk in a.models for s in its]
    else:
        jobs = [(mk, s, box, up) for mk in a.models for (box, up) in VARIANTS[mk] for s in its]
    url = cfgmod.load()["comfyui"]["url"]
    comfy = None
    if not a.dry:
        host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
        try:
            socket.create_connection((host, port), timeout=2).close()
        except OSError:
            sys.exit(f"ComfyUI is not running ({url}). Start it first.")
        comfy = ComfyUI(url)
    b = Bridge(ls._NoPhotoCraft(), comfy, out / "xch")
    app = ls.make_app(url)
    ready = set(a.models)
    if comfy is not None:
        inv = inventory.fetch(comfy, cfgmod.model_map())
        ready = {mk for mk in a.models if inv.tab_status(mk).state == "ready"}
    t_start = time.time()
    for n, (mk, s, box, up) in enumerate(jobs, 1):
        vname = BUILT if box is None else variant_name(box, up)
        if mk not in ready:
            print(f"SKIPPED {mk}: its files are not all there", flush=True)
            continue
        if any(it["model_key"] == mk and it["input"] == s["input"] and it["variant"] == vname for it in key.values()):
            continue
        model = models.BY_KEY[mk]
        if box is None:
            if not run_built(a, b, app, comfy, key, out, mk, s, n, len(jobs)):
                continue
            write_key()
            continue
        req, label = ls.edit_request(app, mk, "multi_edit")
        base_res = model.modes["scribble"].settings.get("base_res", req.base_res)    # the size of Scribble on photo
        req = replace(req, base_res=base_res)
        wf = req.workflow
        mult = max(workflows.size_multiple(workflows.load_template(wf)), 1)
        pic = s["pic"]
        found = scribble.find(pic)
        if found is None:
            print(f"   {s['input']}: no scribble found, left out", flush=True)
            continue
        reg = scribble.region(found, pic.size)
        base = imaging.native_base(reg.w, reg.h, req.base_res, req.native_mp) if req.native else req.base_res
        gw, gh = imaging.gen_size(reg.w, reg.h, base, multiple=mult)
        tag = model.tag_style.format(n=2, i=1)
        where = " in <obj_1>" if box else ""
        text = TEXT.format(where=where, obj="a " + s["name"] if up else tag)
        suffix = SUFFIX.format(name=s["name"], where=where, tag=tag) if up else ""
        layout = ((found.box.x - reg.x, found.box.y - reg.y, found.box.w, found.box.h), (reg.w, reg.h), s["name"]) if box else None
        refim = refslots.prepare_image(s["refim"], mult, model.ref_side)
        p = replace(req.params, prompt=text, seed=SEED, width=gw, height=gh, denoise=1.0)
        if a.dry:
            image_name, ref_name = "dry.png", ["dry-ref.png"]
        else:
            image_name = comfy.upload_image(pic.crop(reg.pil()).resize((gw, gh), Image.LANCZOS), f"pcc-refscr-{mk}-{s['k']}.png")
            ref_name = [comfy.upload_image(refim, f"pcc-refscr-{mk}-{s['k']}-ref.png")]
        graph, out_node = b._graph(req, p, image_name, None, wf, ref_name, force_plain=True, layout=layout)
        show = None
        if up:
            show = ls.upsample_any(graph, text)
            tagged(graph, graph[show]["inputs"]["source"][0], suffix)
        if a.dry:
            refs_in = sum(1 for nd in graph.values() if isinstance(nd, dict) and nd.get("inputs", {}).get("image") == "dry-ref.png")
            print(f"{n}/{len(jobs)} {label} · {vname} · {s['name']}: crop {reg.w}x{reg.h} -> {gw}x{gh}, reference "
                  f"{refim.width}x{refim.height} ({refs_in} node), box {'yes' if layout else 'no'}, prompt: {text}"
                  + (f" + [caption] {suffix}" if up else ""), flush=True)
            continue
        t0 = time.time()
        hist = b._wait(comfy.queue(graph), graph, str(wf), 0, 1, "", lambda *x, **k: None)
        res = comfy.output_images(hist, out_node)[0].convert("RGB")
        layer, mask = scribble.put_back(pic, res, found, reg)
        out_im = Image.composite(layer, pic, mask)
        fid = f"{len(key) + 1:04d}"
        out_im.save(out / "bilder" / f"{fid}.png")
        res.save(out / "roh" / f"{fid}.png")
        rec = {"model": label, "model_key": mk, "file": s["photo"], "ref": s["ref"], "input": s["input"], "kind": "photo",
               "desc": s["name"], "prompt": "Reference at scribble", "variant": vname, "way": vname, "seed": SEED,
               "box": [found.box.x, found.box.y, found.box.w, found.box.h], "region": [reg.x, reg.y, reg.w, reg.h],
               "text": text, "suffix": suffix, "size": [gw, gh], "ref_size": [refim.width, refim.height],
               "seconds": round(time.time() - t0)}
        if show:
            rec["caption"] = ls.caption_of(hist, show)
        key[fid] = rec
        write_key()
        print(f"{n}/{len(jobs)} {label} · {vname} · {s['name']}: {rec['seconds']} s", flush=True)
    write_key()
    app.root.destroy()
    if a.dry:
        print(f"\nDRY RUN: {len(jobs)} pictures would run; inputs in {out / 'eingabe'}")
        return
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min: {len(key)} pictures in {out}\n"
          f"Next: python tests\\live_sketch.py rate \"{out}\"", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scribbles", "run"):
        s = sub.add_parser(name)
        s.add_argument("--photos", type=Path, required=True, help="the folder of the photos that get a scribble")
        s.add_argument("--refs", type=Path, required=True, help="the folder of the reference pictures")
        if name == "run":
            s.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
            s.add_argument("--into", help="a broken round's folder: keep its pictures, make only the missing ones")
            s.add_argument("--dry", action="store_true", help="build every graph, queue nothing")
            s.add_argument("--built", action="store_true",
                           help="the plugin's own way (Scribble mode workflow, the model's prompt writer, the chip's text)")
    a = ap.parse_args()
    {"scribbles": cmd_scribbles, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
