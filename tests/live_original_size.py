r"""Manual check (not part of run_all.py): the rest of the Original-size test run of 4.11. (docs/tests/original-size-testlauf.md,
parts B, C, E and F; part D, Expand 1 against 2 MP, ran on 5.11. and 12.11.). User 13.11.: "Alles, auch C".

Every case goes through the plugin's real bridge (Bridge.run) against the small PhotoCraft simulator of
tests/test_reference_mode.py, with the Request the window builds from the model's start values (saved pages ignored). Only
what the part is about is changed: "Original size" on (2 MP) or off, "Send reference images in original size" on (2 MP) or
off. "Enhance my Prompt with LLM" is off everywhere, so a writer cannot make the two pictures of a pair differ. One seed.

    B  Text to image, Flux 3, Flux 2, Qwen, MOSS, Fibo; canvas 800x600, 1920x1080, 3456x2234 (15 runs). Checked by
       itself: the size sent (runs.jsonl) is the canvas, rounded down, at most 4 MP; the layer has the canvas size.
    C  Original size per function, Qwen Image 2.1, Flux 3, Flux 2, Fibo; Edit (4 cases, one a 12 MP phone photo), Fill
       (4 cases from the Fill rounds the user approved on 9.11., one a large selection on a 12 MP picture), Remove (4
       cases, one on the 12 MP picture); each with the switch on (2 MP) and off (the model's ~1 MP). A small selection gives the same graph both
       times: run once, counted for both ("bleibt klein"). Checked by itself: on <= 2 MP, off the model's base size
       (~1 MP; Flux 3 1536² = 2.36 MP, so the switch changes nothing there). Then blind pairs.
    E  Fibo Refine: a 3000x2000 picture comes back at its own size (the size sent is the nearest multiple); a picture of
       25 MP or more gives the error message (no GPU needed for that one).
    F  Multi Image Edit, all four models, 2 slots (the cat at 12 MP) and 3 slots (the cat at 4 MP and a robot at 0.5 MP);
       reference images in original size on (2 MP) or off (the model's longest side: 1024 px, Flux 3 1536 px). Checked by
       itself: small ones stay, big ones are capped at 2 MP each. Time and the GPU memory (nvidia-smi, only when ComfyUI
       runs on this PC) are written down. Then blind pairs (Flux 3 Edit is "perfect": compare it with and without the tick).
    I  (user 13.11., "mehr Tests" to back choice 1c: Fill and Remove start with Original size off) large Fill and Remove
       selections (12 to 70 % of the picture) on real phone photos at 12 MP, Qwen, Flux 2, Fibo (Flux 3 has no row since
       1a), on (2 MP) and off. Pictures: prepare-i. Then blind pairs.

    python tests\live_original_size.py prepare --photos "<testpics magnific>\2MP" --big "<folder with big phone photos>"
    python tests\live_original_size.py prepare-i --big "<folder with the big phone photos>"     the pictures of part I
    python tests\live_original_size.py dry [--parts B C E F]          every graph without ComfyUI: counts and the size checks
    python tests\live_original_size.py run [--parts B C E F] [--models ...] [--into <round>]   the real run (resumable)
    python tests\live_original_size.py rate [round]                  blind pairs on/off (C and F): the rating window of the Expand round
    python tests\live_original_size.py summary [round]               sizes, checks, ratings, times, GPU memory (ergebnis.md)

Pictures: the 2 MP test photos (05_, 09_, 10_, 11_, 01_, 07_) and, from --big, the photo nearest to 12 MP (Edit, kept as it
is) and the biggest one (E, the 25 MP error). The 12 MP Fill picture and the 4 / 12 MP reference cats are the 2 MP photos
scaled up (their content is known; sizes are what counts there). Output: <PCCOMFY_HOME>/original-size/eingabe (prepare)
and <PCCOMFY_HOME>/original-size/<time>/ (bilder/<token>.png, records.json, bewertung.json, ergebnis.md). Needs the GPU:
before the run, remind the user not to use ComfyUI or other GPU programs meanwhile."""
import argparse
import copy
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageFilter  # noqa: E402

import live_expand_remote as ler  # noqa: E402  (graph keys, the timed client, the blind rating window)
import live_fill_flux as lff  # noqa: E402  (the selections of the Fill rounds)
import live_style_test as base  # noqa: E402
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator)
from pccomfy import config as cfgmod, inventory, models  # noqa: E402
from pccomfy.bridge import MAX_RESULT_MP, Bridge, BridgeError  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "original-size"
IN = BASE / "eingabe"
SEED = 101
CAP = 2.0                                   # "Original size, up to" and the reference images: the start value 2 MP
PARTS = ("B", "C", "E", "F", "G", "H", "I")
DEFAULT_PARTS = ("B", "C", "E", "F")         # G and H came after the first round (user 13.11.: "3c testen", "4 testen")
C_MODELS = ("qwen", "flux3", "flux2", "fibo")
B_MODELS = ("flux3", "flux2", "qwen", "moss", "fibo")
CANVASES = ((800, 600), (1920, 1080), (3456, 2234))
T2I_PROMPT = "A quiet mountain lake at sunrise, a wooden rowing boat near the shore, pine forest and soft mist over the water."

# (id, picture in eingabe, function, prompt or remove target, selection shape, box as fractions)
CASES_C = [
    ("E1", "05.png", "edit", "Make it a sunny autumn day with orange and yellow leaves on the trees and in the grass.", None, None),
    ("E2", "10.png", "edit", "Add soft morning fog between the trees.", None, None),
    ("E3", "11.png", "edit", "Make it evening with warm golden sunset light and long shadows.", None, None),
    ("E4", "gross-12mp.png", "edit", "Make it evening with warm golden sunset light and long shadows.", None, None),
    ("F1", "09.png", "inpaint", "a cup of coffee", "lasso", (0.14, 0.14, 0.21, 0.24)),            # small: stays small
    ("F2", "05.png", "inpaint", "a brown dog sitting in the grass", "lasso", (0.53, 0.68, 0.71, 0.98)),
    ("F3", "11.png", "inpaint", "a red pickup truck", "rect", (0.62, 0.30, 0.97, 0.58)),
    ("F4", "11-12mp.png", "inpaint", "a red pickup truck", "rect", (0.62, 0.30, 0.97, 0.58)),   # large: capped at 2 MP
    ("R1", "05.png", "remove", "the brown goat", "lasso", (0.71, 0.32, 1.00, 0.92)),
    ("R2", "11.png", "remove", "the orange dump truck", "rect", (0.70, 0.00, 1.00, 0.38)),
    ("R3", "07.png", "remove", "the small robot", "lasso", (0.22, 0.25, 0.42, 0.68)),
    ("R4", "11-12mp.png", "remove", "the orange dump truck", "rect", (0.70, 0.00, 1.00, 0.38)),   # large: capped at 2 MP
]
# (id, main picture, [reference pictures], prompt)
CASES_F = [
    ("M2", "05.png", ["katze-12mp.png"], "Add the cat from the second image, sitting in the grass in front of the boy."),
    ("M3", "05.png", ["katze-4mp.png", "roboter-05mp.png"],
     "Add the cat from the second image, sitting in the grass in front of the boy, and let the boy hold the small robot "
     "from the third image."),
]
CASES_E = [("R6", "refine-3000x2000.png"), ("R25", "refine-gross.png")]
# G (3c): Flux 3 with "Original size, up to" 3 and 4 MP against off (its base 1536² = 2.36 MP; the 2 MP start value changes
# nothing there). Only pictures larger than that: the 12 MP cases of C and two more Edit cases on 12 MP pictures.
G_CAPS = (0.0, 3.0, 4.0)                    # 0 = off
G_CASES = ("E4", "E5", "E6", "F4", "R4")
CASES_C_MORE = [
    ("E5", "11-12mp.png", "edit", "Make it evening with warm golden sunset light and long shadows.", None, None),
    ("E6", "katze-12mp.png", "edit", "Make it a snowy winter day, with snow on the leaves and soft falling snowflakes.", None, None),
]
# H (4): Fibo again, the GPU memory freed before every run (ComfyUI /free): did the two "out of memory" of the first round
# come from Fibo itself or from the models of the runs before? Refine at 6, 4 and 3 MP and Multi Image Edit with 3 slots on.
H_REFINE = (("R6", 6.0), ("R4", 4.0), ("R3", 3.0))
# I: large selections on real 12 MP phone photos (the big phone photos on PC A, passed with --big; prepare-i makes them 12 MP,
# turned upright). (id, picture, function, prompt or remove target, shape, box as fractions of the upright picture)
I_MODELS = ("qwen", "flux2", "fibo")
I_PHOTOS = {"gross-i1.png": "IMG_20241001_155006.jpg", "gross-i2.png": "IMG_20240315_175437.jpg",
            "gross-i3.png": "IMG_20240921_102651.jpg", "gross-i4.png": "IMG_20241123_142913.jpg",
            "gross-i5.png": "IMG_20240522_194039_1.jpg"}
CASES_I = [
    ("FG1", "gross-i1.png", "inpaint", "a large framed painting of a sailing ship on a stormy sea", "rect", (0.00, 0.05, 0.48, 0.70)),
    ("FG2", "gross-i2.png", "inpaint", "a green forested hillside with a few small houses", "rect", (0.00, 0.06, 0.45, 0.50)),
    ("FG3", "gross-i3.png", "inpaint", "a tall waterfall falling over mossy rocks", "rect", (0.30, 0.00, 0.60, 0.55)),
    ("RG1", "gross-i3.png", "remove", "the woman with the backpack", "lasso", (0.11, 0.51, 0.42, 1.00)),
    ("RG2", "gross-i4.png", "remove", "the man in the red jacket and the girl", "lasso", (0.47, 0.27, 1.00, 1.00)),
    ("RG3", "gross-i5.png", "remove", "the wooden frame and the man under it", "rect", (0.00, 0.13, 0.88, 0.92)),
]
FN_LABEL = {"edit": "Edit", "inpaint": "Fill", "remove": "Remove", "multi_edit": "Multi Image Edit", "txt2img": "Text to image",
            "refine": "Refine"}


# ---------- prepare ----------

def scaled(im: Image.Image, mp: float) -> Image.Image:
    f = (mp * 1e6 / (im.width * im.height)) ** 0.5
    return im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)


def cmd_prepare(a):
    photos, big = Path(a.photos), Path(a.big)
    IN.mkdir(parents=True, exist_ok=True)
    pick = {p.name[:2]: p for p in photos.iterdir() if p.suffix.lower() == ".png"}
    for pid in ("01", "05", "07", "09", "10", "11"):
        if pid not in pick:
            sys.exit(f"{photos} has no {pid}_*.png")
        shutil.copyfile(pick[pid], IN / f"{pid}.png")
    phones = []
    for p in sorted(big.iterdir()):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            with Image.open(p) as im:
                phones.append((im.width * im.height / 1e6, p))
    if not phones:
        sys.exit(f"No photos in {big}")
    near12 = min(phones, key=lambda t: abs(t[0] - 12))[1]
    biggest = max(phones)[1]
    meta = {"big_12": near12.name, "big_max": biggest.name}

    def save(im, name, note):
        im.convert("RGB").save(IN / name)
        meta[name] = f"{note}: {im.width}x{im.height} ({im.width * im.height / 1e6:.2f} MP)"
        print(f"{name:22} {meta[name]}")

    from PIL import ImageOps
    with Image.open(near12) as im:
        save(ImageOps.exif_transpose(im), "gross-12mp.png", f"{near12.name} as it is")
    with Image.open(pick["11"]) as im:
        save(scaled(im.convert("RGB"), 12), "11-12mp.png", "11 scaled up to 12 MP")
    with Image.open(pick["01"]) as im:
        im = im.convert("RGB")
        save(scaled(im, 12), "katze-12mp.png", "01 scaled up to 12 MP")
        save(scaled(im, 4), "katze-4mp.png", "01 scaled up to 4 MP")
    with Image.open(pick["07"]) as im:                          # the robot in the hand, cut out a little wider than it is
        im = im.convert("RGB")
        w, h = im.size
        save(scaled(im.crop((round(w * 0.18), round(h * 0.20), round(w * 0.46), round(h * 0.72))), 0.5), "roboter-05mp.png",
             "07 robot crop at 0.5 MP")
    with Image.open(near12) as im:
        save(ImageOps.exif_transpose(im).convert("RGB").resize((3000, 2000), Image.LANCZOS), "refine-3000x2000.png",
             f"{near12.name} at 3000x2000")
    with Image.open(biggest) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width * im.height < 25e6:
            im = scaled(im, 26)
        save(im, "refine-gross.png", f"{biggest.name} (25 MP or more)")
    json.dump(meta, open(IN / "eingabe.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\n-> {IN}")


def cmd_prepare_i(a):
    """Part I: the phone photos turned upright and at 12 MP (a smaller one stays as it is)."""
    from PIL import ImageOps
    big = Path(a.big)
    IN.mkdir(parents=True, exist_ok=True)
    meta = json.loads((IN / "eingabe.json").read_text(encoding="utf-8")) if (IN / "eingabe.json").exists() else {}
    for name, src in I_PHOTOS.items():
        if not (big / src).exists():
            sys.exit(f"{big} has no {src}")
        with Image.open(big / src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width * im.height > 12.5e6:
            im = scaled(im, 12)
        im.save(IN / name)
        meta[name] = f"{src} upright, at most 12 MP: {im.width}x{im.height} ({im.width * im.height / 1e6:.2f} MP)"
        print(f"{name:16} {meta[name]}")
    json.dump(meta, open(IN / "eingabe.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)


# ---------- the cases ----------

def jobs(parts, only_models=None):
    """[(part, model, case id, function, on)]: every run of the round."""
    out = []
    keep = (lambda m: not only_models or m in only_models)
    if "B" in parts:
        out += [("B", m, f"{w}x{h}", "txt2img", None) for m in B_MODELS if keep(m) for (w, h) in CANVASES]
    if "C" in parts:
        out += [("C", m, c[0], c[2], on) for m in C_MODELS if keep(m) for c in CASES_C for on in (True, False)]
    if "E" in parts and keep("fibo"):
        out += [("E", "fibo", c[0], "refine", None) for c in CASES_E]
    if "F" in parts:
        out += [("F", m, c[0], "multi_edit", on) for m in C_MODELS if keep(m) for c in CASES_F for on in (True, False)]
    if "I" in parts:
        out += [("I", m, c[0], c[2], on) for m in I_MODELS if keep(m) for c in CASES_I for on in (True, False)]
    if "G" in parts and keep("flux3"):
        out += [("G", "flux3", cid, case_c(cid)[2], cap) for cid in G_CASES for cap in G_CAPS]
    if "H" in parts and keep("fibo"):
        out += [("H", "fibo", cid, "refine", None) for cid, _mp in H_REFINE] + [("H", "fibo", "M3", "multi_edit", True)]
    return out


def case_c(cid: str):
    return next(c for c in CASES_C + CASES_C_MORE + CASES_I if c[0] == cid)


def refine_picture(cid: str) -> str:
    """H: the Refine picture of this size, made from refine-3000x2000.png when it is not there yet."""
    mp = dict(H_REFINE)[cid]
    name = f"refine-{mp:g}mp.png"
    if not (IN / name).exists():
        im = load("refine-3000x2000.png")
        k = (mp * 1e6 / (im.width * im.height)) ** 0.5
        im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS).save(IN / name)
    return name


_REQS = {}


def window_request(app, model: str, fn: str):
    """The Request the window would send for this model and function with its start values (cached)."""
    if (model, fn) not in _REQS:
        app.v_model.set(model)
        app.v_mode.set(fn)
        app._factory = True
        try:
            app._on_model()
            app._on_mode()
        finally:
            app._factory = False
        app.t_prompt.delete("1.0", "end")
        _REQS[(model, fn)] = app._request()
    return copy.deepcopy(_REQS[(model, fn)])


def load(name: str) -> Image.Image:
    with Image.open(IN / name) as im:
        return im.convert("RGB")


def run_case(comfy, app, part, model, cid, fn, on):
    """One run through Bridge.run. Returns (picture, info): info has the sizes sent (runs.jsonl), the reference images
    uploaded and the pictures ComfyUI gave back."""
    sel = None
    refs = []
    if part == "B":
        w, h = (int(v) for v in cid.split("x"))
        pic, prompt = Image.new("RGB", (w, h), "white"), T2I_PROMPT
    elif part in ("C", "G", "I"):
        c = case_c(cid)
        pic, prompt = load(c[1]), c[3]
        if c[4]:
            sel = lff.selection(pic.size, c[4], c[5])
    elif part == "E" or (part == "H" and fn == "refine"):
        name = next(c for c in CASES_E if c[0] == cid)[1] if part == "E" else refine_picture(cid)
        pic, prompt = load(name), models.BY_KEY[model].modes[fn].prompt_hint   # the text in the field
    else:
        c = next(c for c in CASES_F if c[0] == cid)
        pic, prompt, refs = load(c[1]), c[3], [load(r) for r in c[2]]
    req = window_request(app, model, fn)
    spec = models.BY_KEY[model].modes[fn]
    if fn == "remove":                                      # a model that is told what to remove gets the name, else no text
        req.remove_target = prompt if spec.remove_text else ""
        prompt = prompt if spec.remove_text else ""
    req.enhance = False
    if part in ("C", "I"):
        req.native, req.native_mp = bool(on), CAP
    if part == "G":
        req.native, req.native_mp = bool(on), float(on or CAP)
    if part in ("F", "H") and fn == "multi_edit":
        req.refs, req.ref_native, req.ref_mp = refs, bool(on), CAP
        req.ref_side = models.BY_KEY[model].ref_side
    req.params = replace(req.params, prompt=prompt, seed=SEED)
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="original-size-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], sel))
    sent = []
    up, outimg = comfy.upload_image, comfy.output_images

    def upload(image, name):
        sent.append([name.rsplit("-", 1)[-1].split(".")[0], image.width, image.height])
        return up(image, name)

    got = []

    def output(*k, **kw):
        ims = outimg(*k, **kw)
        got.extend([im.width, im.height] for im in ims)
        return ims

    comfy.upload_image, comfy.output_images = upload, output
    try:
        Bridge(pc, comfy, tmp).run(req)
    finally:
        comfy.upload_image, comfy.output_images = up, outimg
    runs = [json.loads(line) for line in (Path(tmp) / "runs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    sizes = [r["size"] for r in runs if "size" in r]
    shutil.rmtree(tmp, ignore_errors=True)
    return pc.composite(pc.doc), {"canvas": list(pic.size), "gen": sizes[0] if sizes else None, "base_mp": round(req.base_res ** 2 / 1e6, 2), "uploads": sent, "got": got,
                                  "region_mp": None if sel is None else _region_mp(sel, req.context)}


def _region_mp(sel, context):
    from pccomfy import imaging
    bbox = imaging.mask_bbox(sel)
    r = imaging.grow_box(bbox, sel.size, context)
    return round(r.w * r.h / 1e6, 2)


def check(rec: dict) -> str:
    """The size rule of the part, checked on what was really sent: "ok" or what is wrong."""
    if rec.get("error"):
        return "ok (Fehlermeldung wie erwartet)" if rec["case"] == "R25" and "megapixels" in rec["error"] else "FEHLER " + rec["error"]
    g, (cw, ch) = rec.get("gen"), rec["canvas"]
    if rec["case"] == "R25":
        return f"FEHLER: lief, obwohl das Bild {cw * ch / 1e6:.0f} MP hat (Grenze {MAX_RESULT_MP:.0f})"
    if not g:
        return "FEHLER: keine Größe in runs.jsonl"
    gmp = g[0] * g[1] / 1e6
    if rec["part"] == "B":
        if g[0] > cw or g[1] > ch or gmp > 4.0 + 1e-6:
            return f"FEHLER: {g[0]}x{g[1]} größer als Canvas oder 4 MP"
        if cw * ch <= 4e6 and (cw - g[0] >= 64 or ch - g[1] >= 64):
            return f"FEHLER: {g[0]}x{g[1]} deutlich kleiner als der Canvas"
        return "ok"
    if rec["part"] == "G":
        bmp, cap = rec.get("base_mp") or 2.36, float(rec["on"] or 0)
        lim = max(cap, bmp)
        return "ok" if gmp <= lim * 1.03 else f"FEHLER: {gmp:.2f} MP über {lim:.2f} MP"
    if rec["part"] == "H" and rec["fn"] == "multi_edit":
        return "ok"
    if rec["part"] in ("E", "H"):
        return "ok" if abs(g[0] - cw) <= 32 and abs(g[1] - ch) <= 32 else f"FEHLER: {g[0]}x{g[1]} statt etwa {cw}x{ch}"
    if rec["part"] in ("C", "I"):       # never below the model's base size (Flux 3: 1536² = 2.36 MP, so 2 MP changes nothing there)
        bmp = rec.get("base_mp") or 1.05
        if rec["on"]:
            return "ok" if gmp <= max(CAP, bmp) * 1.03 else f"FEHLER: {gmp:.2f} MP über {max(CAP, bmp):.2f} MP"
        return "ok" if gmp <= bmp * 1.06 else f"FEHLER: {gmp:.2f} MP, ohne Haken höchstens die Grundgröße {bmp:.2f} MP"
    # F: the reference images
    side = models.BY_KEY[rec["model"]].ref_side
    refs = [u for u in rec["uploads"] if u[0].startswith("ref")]
    names = next(c[2] for c in CASES_F if c[0] == rec["case"])
    if len(refs) != len(names):
        return f"FEHLER: {len(refs)} Referenzbilder gesendet statt {len(names)}"
    for (_n, w, h), name in zip(refs, names):
        with Image.open(IN / name) as im:
            ow, oh = im.size
        if rec["on"]:
            if w * h > CAP * 1e6 * 1.03:
                return f"FEHLER: {name} mit {w}x{h} über {CAP} MP"
            if ow * oh <= CAP * 1e6 and (abs(w - ow) > 32 or abs(h - oh) > 32):
                return f"FEHLER: {name} hätte seine Größe behalten sollen ({ow}x{oh}), gesendet {w}x{h}"
        elif abs(max(w, h) - min(side, max(ow, oh))) > 32:
            return f"FEHLER: {name} mit {w}x{h}, erwartet die längere Seite {min(side, max(ow, oh))}"
    return "ok"


class VramPeak:
    """The highest GPU memory in use (nvidia-smi, every 0.5 s) while a run lasts; None without nvidia-smi."""

    def __init__(self, on: bool):
        self.on, self.peak, self._stop = on and shutil.which("nvidia-smi") is not None, None, threading.Event()

    def _poll(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                v = max(int(x) for x in out.split())
                self.peak = v if self.peak is None else max(self.peak, v)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            self._stop.wait(0.5)

    def __enter__(self):
        if self.on:
            self._t = threading.Thread(target=self._poll, daemon=True)
            self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        return False


def _rec(part, m, cid, fn, on):
    return {"part": part, "model": m, "case": cid, "fn": fn, "on": on,
            # the fields the rating window of the Expand round reads: a pair is (model, photo, kind), cap 2.0 = on, 1.0 = off
            "photo": cid, "kind": f"{part}-{fn}",
            # G: the caps window ("rate caps": all caps of one case side by side); off counts as Flux 3's base 2.36 MP
            "cap": (float(on) if on else 2.36) if part == "G" else (None if on is None or part == "H" else (2.0 if on else 1.0))}


def cmd_dry(a):
    app = base.make_app("http://127.0.0.1:1")
    rows, t0 = [], time.time()
    for part, m, cid, fn, on in jobs(a.parts, a.models):
        rec = _rec(part, m, cid, fn, on)
        comfy = ler.Recorder()
        try:
            _img, info = run_case(comfy, app, part, m, cid, fn, on)
            rec.update(info, key=ler.graph_key(comfy.graphs[0], comfy.uploads) if comfy.graphs else None)
        except BridgeError as ex:
            rec.update(error=str(ex)[:300], canvas=list(load(next(c[1] for c in CASES_E if c[0] == cid)).size) if part == "E" else None)
        rec["check"] = check(rec)
        rows.append(rec)
    print(f"{len(rows)} cases built in {time.time() - t0:.0f} s\n")
    for r in rows:
        g = f"{r['gen'][0]}x{r['gen'][1]}" if r.get("gen") else "-"
        refs = " ".join(f"{w}x{h}" for n, w, h in r.get("uploads", []) if n.startswith("ref"))
        print(f"{r['part']} {r['model']:6} {r['case']:10} {FN_LABEL[r['fn']]:16} {'' if r['on'] is None else ('an ' if r['on'] else 'aus')} "
              f"gesendet {g:11} {('refs ' + refs) if refs else ''}  {r['check']}")
    keys = {}
    for r in rows:
        if r.get("key"):
            keys.setdefault((r["model"], r["case"], r["fn"]), set()).add(r["key"])
    runs = sum(len(v) for v in keys.values()) + sum(1 for r in rows if not r.get("key"))
    same = sorted(f"{m} {c}" for (m, c, _f), v in keys.items() if len(v) == 1 and any(r["case"] == c and r["on"] is not None for r in rows))
    bad = [r for r in rows if not r["check"].startswith("ok")]
    print(f"\n{len(rows)} cases, {runs} distinct runs on the GPU (on/off equal, run once: {', '.join(same) or 'none'})")
    print(f"size checks: {len(rows) - len(bad)} of {len(rows)} ok" + "".join(f"\n  {r['part']} {r['model']} {r['case']}: {r['check']}" for r in bad))
    BASE.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(BASE / "dry.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    app.root.destroy()
    return rows


def cmd_run(a):
    url = a.url or cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError:
        sys.exit(f"ComfyUI does not answer ({url}).")
    local = host in ("127.0.0.1", "localhost", "::1")
    out = Path(a.into) if a.into else BASE / time.strftime("%Y%m%d-%H%M%S")
    (out / "bilder").mkdir(parents=True, exist_ok=True)
    rfile = out / "records.json"
    records = json.load(open(rfile, encoding="utf-8")) if rfile.exists() else []
    comfy = ler.Timed(url)
    inv = inventory.fetch(comfy, cfgmod.model_map())
    app = base.make_app(url)
    todo = jobs(a.parts, a.models)
    print(f"ComfyUI: {url}\nRound: {out}\n{len(todo)} cases\n", flush=True)
    t_start, done_keys, skipped = time.time(), {r["key"]: r for r in records if r.get("token") and r.get("key")}, set()
    for part, m, cid, fn, on in todo:
        if any(r["part"] == part and r["model"] == m and r["case"] == cid and r["on"] == on for r in records):
            continue
        if inv.tab_status(m).state != "ready":
            if m not in skipped:
                print(f"SKIPPED {m}: its files are not all there", flush=True)
                skipped.add(m)
            continue
        rec = _rec(part, m, cid, fn, on)
        rec_comfy = ler.Recorder()                      # the graph without ComfyUI first: the same graph twice runs once
        key = None
        try:
            run_case(rec_comfy, app, part, m, cid, fn, on)
            key = ler.graph_key(rec_comfy.graphs[0], rec_comfy.uploads) if rec_comfy.graphs else None
        except BridgeError:
            pass
        rec["key"] = key
        if key and key in done_keys:
            old = done_keys[key]
            rec.update({k: old[k] for k in ("token", "canvas", "gen", "base_mp", "uploads", "got", "region_mp") if k in old}, same_as=old["token"])
        else:
            if part == "H":
                free_gpu(url)
            t0 = time.time()
            try:
                with VramPeak(local) as vp:
                    img, info = run_case(comfy, app, part, m, cid, fn, on)
                token = os.urandom(4).hex()
                img.convert("RGB").save(out / "bilder" / f"{token}.png")
                rec.update(info, token=token, seconds=round(time.time() - t0, 1),
                           gen_seconds=round(comfy.t_done - comfy.t_queued, 1), vram_mb=vp.peak)
                if key:
                    done_keys[key] = rec
            except Exception as ex:                    # one broken case must not stop the round
                rec.update(error=f"{type(ex).__name__}: {ex}"[:300], seconds=round(time.time() - t0, 1))
                if part == "E":
                    rec["canvas"] = list(load(next(c[1] for c in CASES_E if c[0] == cid)).size)
                elif part == "H" and fn == "refine":
                    rec["canvas"] = list(load(refine_picture(cid)).size)
        rec["check"] = check(rec) if (rec.get("gen") or rec.get("error")) else "FEHLER: nichts gesendet"
        records.append(rec)
        json.dump(records, open(rfile, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        state = "" if on is None else (" an" if on else " aus")
        note = (f"{rec['gen_seconds']} s" if "gen_seconds" in rec else ("wie ein früherer Lauf" if rec.get("same_as")
                else f"Fehler: {rec.get('error')}"))
        print(f"{part} {m} {cid}{state}: {note}  [{rec['check']}]", flush=True)
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min -> {out}\nNext: python tests\\live_original_size.py rate", flush=True)
    app.root.destroy()


def free_gpu(url: str):
    """ComfyUI's /free: unload every model and free the GPU memory (part H), then a short pause."""
    import urllib.request
    req = urllib.request.Request(url.rstrip("/") + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except OSError as ex:
        print(f"/free failed: {ex}", flush=True)
    time.sleep(5)


def latest(folder):
    if folder:
        return Path(folder)
    runs = sorted(p for p in BASE.iterdir() if (p / "records.json").exists()) if BASE.exists() else []
    if not runs:
        sys.exit(f"No round in {BASE}")
    return runs[-1]


LOOK = {   # what to look at, per function (user 13.11.: the window must say what to rate)
    "edit": "Ist der Auftrag gut umgesetzt? Details in voller Größe: scharf oder verwaschen, erfundene oder verbogene Teile? "
            "Ist der Rest des Bildes gleich geblieben?",
    "inpaint": "Wirkt das neue Objekt in der Auswahl (rot umrandet im Eingabebild) natürlich: Größe, Kanten, Licht, Schärfe?",
    "remove": "Ist das Objekt in der Auswahl (rot umrandet im Eingabebild) sauber weg, ohne Reste? Ist der Hintergrund glaubhaft?",
    "multi_edit": "Ist die Referenz eingesetzt und sieht sie aus wie im Referenzbild (Fell, Augen, Form)? Passt sie ins Bild? "
                  "Details in voller Größe.",
}


def task_picture(out: Path, cid: str) -> Path:
    """The small input picture of the rating window: the photo with the selection outlined in red (Fill, Remove), or the
    main photo with the reference images beside it (Multi Image Edit). Made once per case in <round>/aufgaben."""
    from PIL import ImageDraw
    f = out / "aufgaben" / f"{cid}.png"
    if f.exists():
        return f
    f.parent.mkdir(exist_ok=True)
    c = next((c for c in CASES_C + CASES_C_MORE + CASES_I if c[0] == cid), None)
    if c is not None:
        im = load(c[1])
        im.thumbnail((960, 960))
        if c[4]:
            edge = lff.selection(im.size, c[4], c[5])
            line = edge.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v else 0).filter(ImageFilter.MaxFilter(7))
            ImageDraw.Draw(im).bitmap((0, 0), line, fill=(255, 0, 0))
    else:
        c = next(c for c in CASES_F if c[0] == cid)
        parts = [load(n) for n in [c[1]] + list(c[2])]
        for p in parts:
            p.thumbnail((640, 480))
        im = Image.new("RGB", (sum(p.width for p in parts) + 20 * (len(parts) - 1), max(p.height for p in parts)), (40, 40, 40))
        x = 0
        for p in parts:
            im.paste(p, (x, 0))
            x += p.width + 20
    im.save(f)
    return f


def cmd_rate(a):
    out = latest(a.round)

    def describe(item):
        _p, model, cid, kind = item["id"].split("|")
        fn = kind.split("-", 1)[1]
        c = next((c for c in CASES_C + CASES_C_MORE + CASES_I if c[0] == cid), None) or next(c for c in CASES_F if c[0] == cid)
        what = (f"Entfernen: {c[3]}" if fn == "remove" else f"Prompt: „{c[3]}“")
        if fn == "multi_edit":
            what += "   (Eingabe links, daneben die Referenzbilder 2" + (" und 3)" if len(c[2]) > 1 else ")")
        return (f"{models.BY_KEY[model].label} · {FN_LABEL[fn]} · Fall {cid}\n{what}\nWorauf achten: {LOOK[fn]}\n"
                + ("Frage: Welche Bilder sind gut? Mehrere „Gut“ erlaubt, dann Enter."  if mode == "caps" else
                   "Frage: Welches Bild ist insgesamt besser?") + "  (Klick auf das kleine Bild: Eingabe in voller Größe)"), task_picture(out, cid)

    records = json.load(open(out / "records.json", encoding="utf-8"))
    mode = "caps" if any(r["part"] == "G" for r in records) else "pairs"     # G: three caps of one case side by side
    ler.cmd_rate(argparse.Namespace(mode=mode, round=str(out), title="Original size", describe=describe))


def cmd_summary(a):
    out = latest(a.round)
    records = json.load(open(out / "records.json", encoding="utf-8"))
    bfile = out / "bewertung.json"
    data = json.loads(bfile.read_text(encoding="utf-8")) if bfile.exists() else {}
    who = {r["token"]: r for r in records if r.get("token") and not r.get("same_as")}

    def size(s):
        return f"{s[0]}×{s[1]}" if s else "-"

    lines = [f"# Original size, Teile B, C, E, F: Auswertung ({out.name})", ""]
    for part, title in (("B", "B. Text to image: gesendete Größe"), ("E", "E. Fibo Refine")):
        rs = [r for r in records if r["part"] == part]
        if rs:
            lines += [f"## {title}", "", "| Modell | Fall | Canvas | gesendet | zurück | Zeit s | Prüfung |", "|---|---|---|---|---|---|---|"]
            lines += [f"| {r['model']} | {r['case']} | {size(r.get('canvas'))} | {size(r.get('gen'))} | "
                      f"{size(r['got'][0]) if r.get('got') else '-'} | {r.get('gen_seconds', '-')} | {r['check']} |" for r in rs]
            lines.append("")
    for part, title in (("C", "C. Original size je Funktion (an = 2 MP, aus = etwa 1 MP)"), ("F", "F. Referenzbilder (an = Originalgröße bis 2 MP, aus = längere Seite des Modells)"),
                        ("I", "I. Große Auswahlen auf 12-MP-Handyfotos (an = 2 MP, aus = etwa 1 MP)")):
        rs = [r for r in records if r["part"] == part]
        if not rs:
            continue
        lines += [f"## {title}", "", "| Modell | Fall | Funktion | an: gesendet | aus: gesendet | an: Zeit s | aus: Zeit s | "
                  + ("an: GPU MB | aus: GPU MB | " if part == "F" else "") + "Prüfung |", "|---|---|---|---|---|---|---|" + ("---|---|" if part == "F" else "") + "---|"]
        for m in C_MODELS:
            for cid in dict.fromkeys(r["case"] for r in rs):
                pr = {r["on"]: r for r in rs if r["model"] == m and r["case"] == cid}
                if not pr:
                    continue
                on, off = pr.get(True, {}), pr.get(False, {})
                if part == "F":
                    sent = {k: " ".join(f"{w}×{h}" for n, w, h in v.get("uploads", []) if n.startswith("ref")) or "-" for k, v in (("on", on), ("off", off))}
                else:
                    sent = {"on": size(on.get("gen")), "off": size(off.get("gen"))}
                same = " (gleiches Bild)" if on.get("token") and on.get("token") == off.get("token") else ""
                checks = "; ".join(sorted({v["check"] for v in (on, off) if v}))
                lines.append(f"| {m} | {cid} | {FN_LABEL[on.get('fn') or off.get('fn')]} | {sent['on']} | {sent['off']}{same} | "
                             f"{on.get('gen_seconds', '-')} | {off.get('gen_seconds', '-')} | "
                             + (f"{on.get('vram_mb') or '-'} | {off.get('vram_mb') or '-'} | " if part == "F" else "") + f"{checks} |")
        lines.append("")
    stats = {}
    for iid, v in data.items():
        if not iid.startswith("pair|"):
            continue
        _p, m, _cid, kind = iid.split("|")
        s = stats.setdefault((m, kind), [0, 0, 0, 0, 0])
        s[0] += 1
        b = v["best"]
        if b in ("equal", "none"):
            s[3 if b == "equal" else 4] += 1
        else:
            s[1 if who[v["tokens"][b]]["on"] else 2] += 1
    if stats:
        lines += ["## Blind bewertet: an gegen aus", "", "| Modell | Teil, Funktion | Paare | an besser | aus besser | gleich gut | beide schlecht |",
                  "|---|---|---|---|---|---|---|"]
        for (m, kind), s in sorted(stats.items()):
            lines.append(f"| {m} | {kind} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {s[4]} |")
        tot = [sum(s[i] for s in stats.values()) for i in range(5)]
        lines += [f"| **zusammen** | | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} |", ""]
        bad = {}
        for iid, v in data.items():
            for k in v.get("bad", []):
                r = who[v["tokens"][k]]
                bad.setdefault((r["model"], r["kind"], "an" if r["on"] else "aus"), []).append(r["case"])
        if bad:
            lines += ["Als schlecht angehakt (auch bei „besser“):", ""] + [f"- {m} {k} {o}: {', '.join(sorted(c))}" for (m, k, o), c in sorted(bad.items())] + [""]
        notes = [(iid, v["note"]) for iid, v in sorted(data.items()) if v.get("note")]
        if notes:
            lines += ["Notizen:", ""] + [f"- {iid}: {n}" for iid, n in notes] + [""]
    gs = [r for r in records if r["part"] == "G"]
    if gs:
        good = {}
        for iid, v in data.items():
            if iid.startswith("caps|"):
                for k in v.get("good", []):
                    for r in gs:
                        if r.get("token") == v["tokens"][k] and r["case"] == iid.split("|")[2]:
                            good[(r["case"], r["on"])] = good.get((r["case"], r["on"]), 0) + 1
        lines += ["## G. Flux 3: Grenze aus (Grundgröße 2,36 MP) gegen 3 und 4 MP", "",
                  "| Fall | Funktion | Grenze | gesendet | Zeit s | gut | Prüfung |", "|---|---|---|---|---|---|---|"]
        for r in gs:
            lines.append(f"| {r['case']} | {FN_LABEL[r['fn']]} | {r['on'] or 'aus'} | {size(r.get('gen'))}"
                         + (" (wie aus)" if r.get("same_as") else "") + f" | {r.get('gen_seconds', '-')} | "
                         + f"{'ja' if good.get((r['case'], r['on'])) else ('-' if not data else 'nein')} | {r['check']} |")
        lines.append("")
    hs = [r for r in records if r["part"] == "H"]
    if hs:
        lines += ["## H. Fibo mit geleertem Grafikspeicher", "", "| Fall | Funktion | Bild | gesendet | Zeit s | GPU MB | Prüfung |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f"| {r['case']} | {FN_LABEL[r['fn']]} | {size(r.get('canvas'))} | {size(r.get('gen'))} | {r.get('gen_seconds', '-')} | "
                  f"{r.get('vram_mb') or '-'} | {r['check'].splitlines()[0]} |" for r in hs]
        lines.append("")
    timed = [r for r in records if "gen_seconds" in r and r["on"] is not None and r["part"] in ("C", "F", "I")]
    if timed:
        lines += ["## Generationszeit (Median s)", "", "| Modell | Teil | an | aus |", "|---|---|---|---|"]
        for m in C_MODELS:
            for part in ("C", "F", "I"):
                rs = [r for r in timed if r["model"] == m and r["part"] == part]
                if rs:
                    med = {o: (f"{statistics.median(r['gen_seconds'] for r in rs if r['on'] == o):.0f}" if any(r["on"] == o for r in rs) else "-") for o in (True, False)}
                    lines.append(f"| {m} | {part} | {med[True]} | {med[False]} |")
    bad = [r for r in records if not r["check"].startswith("ok")]
    lines += ["", f"Größen-Prüfung: {len(records) - len(bad)} von {len(records)} ok" + "".join(f"\n- {r['part']} {r['model']} {r['case']}: {r['check']}" for r in bad)]
    text = "\n".join(lines) + "\n"
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--photos", required=True, help="the folder with the 2 MP test photos 01_ ... 11_")
    p.add_argument("--big", required=True, help="a folder with big phone photos (one near 12 MP, one of 25 MP or more if there is)")
    sub.add_parser("prepare-i").add_argument("--big", required=True, help="the folder with the big phone photos of part I")
    for name in ("dry", "run"):
        s = sub.add_parser(name)
        s.add_argument("--parts", nargs="+", default=list(DEFAULT_PARTS), choices=PARTS)
        s.add_argument("--models", nargs="+", choices=sorted(set(B_MODELS) | set(C_MODELS)))
        if name == "run":
            s.add_argument("--into", help="continue this existing round")
            s.add_argument("--url", help="another ComfyUI (default: config.toml)")
    for name in ("rate", "summary"):
        sub.add_parser(name).add_argument("round", nargs="?")
    a = ap.parse_args()
    if a.cmd in ("dry", "run") and not (IN / "eingabe.json").exists():
        sys.exit(f"Run prepare first ({IN} is missing).")
    {"prepare": cmd_prepare, "prepare-i": cmd_prepare_i, "dry": cmd_dry, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
