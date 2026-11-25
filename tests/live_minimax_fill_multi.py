r"""Manual check (not part of run_all.py): MiniMax H3 Image Fill/Remove (A) and Multi image edit (B), user 21.11.
"erstmal A und B" (docs/tests/minimax-fill-multi-testplan.md; idea from the Pixaroma workflows EP43).

A  Fill and Remove through our MiniMax Edit graph, the way Qwen runs them (a crop around the selection, a soft layer mask
   back, the writer off). The two Modes are added to models.MINIMAX for this run only; nothing in the plugin changes.
     a1  today's way: Context 40 %, the red outline, FILL_PROMPT_LARGE / REMOVE_TARGET_PROMPT with the name
     a2  the Pixaroma way: Context 10 %, no outline, a sentence about <Picture 1> ending in "Keep ... exactly as it is"
     qwen, flux3  Qwen Image 2.1 and Flux 3 Klein Fill / Remove with their start values (the yardstick)
   Fill: the 8 cases of Fill round 1 (live_fill_flux.CASES); Remove: the 6 cases with the user's own selections
   (live_remove_name.CASES, data/remove-name/masken), the name from his words. Seed 11. 14 x 4 = 56 pictures.
B  Multi image edit, the three pairs of the reference probe of 14.11. (picture 1 from testpics magnific\2MP, the reference
   from the big portraits), the writer off, seed 1234:
     b1  today: 4 MP, references at 2048 px
     b2  4 MP, references in original size (ref_native; --ref-mp caps it, 0 = no cap)
     b3  8 MP, references in original size
   each with a short and a long (Pixaroma pattern) prompt: 3 x 3 x 2 = 18 pictures.

    python tests\live_minimax_fill_multi.py plan
    python tests\live_minimax_fill_multi.py run --dry --photos <testpics magnific\2MP> --refs <portraits>   (no GPU)
    python tests\live_minimax_fill_multi.py run --photos ... --refs ... [--only a|b] [--url http://<ip>:8188]
    python tests\live_minimax_fill_multi.py rate [folder]       (blind: input left, result right; G / S, faults 1 to 6)
    python tests\live_minimax_fill_multi.py summary [folder]    (good and fault-free good per variant; ergebnis.md)

Round 2 (user 21.11., "1C und 2C mit neuen Bildern"; plan section "Runde 2"): 10 Fill + 10 Remove cases on new photos from
D:\testpics (a1, qwen, flux3) and 8 new Multi pairs (b1, b2, short prompts), two seeds: 120 + 32 pictures.
    python tests\live_minimax_fill_multi.py open2 --testpics <D:\testpics>   (each case as a PhotoCraft document at 2 MP,
                                                                           named after what to mark: mm2-F01_Ballon-im-Himmel)
    python tests\live_minimax_fill_multi.py grab2                             (reads the selections; names the missing)
    python tests\live_minimax_fill_multi.py run --round 2 --testpics <D:\testpics> [--dry] [--only a|b]

Output: data\minimax-fill-multi\<time>\ (eingabe\, bilder\, key.json, bewertung.json, index.html, ergebnis.md).
Needs the GPU: before the run, remind the user not to use ComfyUI meanwhile.
"""
import argparse
import copy
import dataclasses
import json
import random
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageFilter  # noqa: E402

from live_progress import Left  # noqa: E402  (what is left of the round)
import live_fill_flux as lff  # noqa: E402  (CASES of Fill round 1, selection)
import live_remove_name as lrn  # noqa: E402  (CASES with the user's selections)
import live_style_test as base  # noqa: E402  (make_app)
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator and FakeComfy)
from pccomfy import bridge, models  # noqa: E402
from pccomfy import config as cfgmod  # noqa: E402
from pccomfy.bridge import Bridge  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "minimax-fill-multi"
SEED_A, SEED_B = 11, 1234
WF = "minimax-h3-image-edit.json"
_SOFT = dict(layer_mask="soft", mask_grow=8, mask_blur=8)
# the Modes MiniMax gets for this run only (like Qwen's: the Edit graph, a soft mask back; base 1536 px, MiniMax wants >= 2 MP)
TEST_MODES = {
    "inpaint": models.Mode(WF, dict(_SOFT, base_res=1536, context=0.4, feather_pct=10.0, enhance=False)),
    "remove": models.Mode(WF, dict(_SOFT, base_res=1536, context=0.4, feather_pct=10.0, enhance=False), remove_text=True),
}
A2_CONTEXT = 0.1
A2_FILL = ("Add {text} in <Picture 1>, filling most of the picture and blended naturally into the scene, with matching "
           "light, shadows and perspective. Keep everything else exactly as it is.")
A2_REMOVE = ("Remove {target} from <Picture 1>, so that the background continues in its place, unbroken and natural. "
             "Keep everything else exactly as it is.")
A_VARIANTS = ("a1", "a2", "qwen", "flux3")
A_MODEL = {"a1": "minimax", "a2": "minimax", "qwen": "qwen", "flux3": "flux3"}
NAME = {"a1": "MiniMax rot (heute, 40 %)", "a2": "MiniMax Pixaroma (10 %, ohne Rot)", "qwen": "Qwen Image 2.1",
        "flux3": "Flux 3 Klein", "b1": "B1 4 MP, Ref 2048", "b2": "B2 4 MP, Ref Original", "b3": "B3 8 MP, Ref Original"}
B_VARIANTS = {"b1": dict(gen_mp=4, ref_native=False), "b2": dict(gen_mp=4, ref_native=True), "b3": dict(gen_mp=8, ref_native=True)}
# (tag, picture 1, reference, short prompt, long prompt in the Pixaroma pattern: who takes what from where, how it sits,
# its details, pose and framing, then what to keep)
PAIRS = [
    ("pullover", "07_man-with-tablet.png", "albert-dera-ILip77SbmOE-unsplash.jpg",
     "The man in <Picture 1> wears the sweater from <Picture 2>.",
     "The man in <Picture 1> now wears the dark grey knitted sweater from <Picture 2> instead of his plain grey sweater. "
     "It fits him loosely, with a wide shawl collar folded around his neck and a row of dark buttons down the front; the "
     "sleeves reach his wrists. Keep his pose with both hands holding the tablet, the small robot, the workshop behind him "
     "and the light exactly as they are. Keep his face, his hair and his beard exactly as they are."),
    ("jeansjacke", "03_father-with-little.png", "toa-heftiba-O3ymvT7Wf9U-unsplash.jpg",
     "The father in <Picture 1> wears the denim jacket from <Picture 2>.",
     "The father in <Picture 1> now wears the light blue denim jacket from <Picture 2>, open at the front, over a grey hoodie "
     "instead of his white T-shirt. The jacket has a pointed collar, metal buttons and two chest pockets with flaps; the grey "
     "hood lies on his shoulders. Keep his pose and the way he holds the child. Keep the child, the child's clothes, the "
     "brick wall and the warm light exactly as they are."),
    ("gesicht", "05_full-shot-kid.png", "vicky-hladynets-C8Ta0gwPbQg-unsplash.jpg",
     "The kneeling man in <Picture 1> has the face of the man in <Picture 2>.",
     "The kneeling man in <Picture 1> now has the face of the man in <Picture 2>: his ginger beard, his short hair and his "
     "black glasses, at the right size for his body and turned the same way as the head in <Picture 1>. Keep his kneeling "
     "pose, his clothes and his hands exactly as they are. Keep the child, the goats, the meadow and the light exactly as "
     "they are."),
]
# ---- round 2 (user 21.11.: "1C und 2C mit neuen Bildern"): new photos from D:\testpics (--testpics), the selections drawn
# by the user in PhotoCraft (open2 / grab2), two seeds, only a1 / qwen / flux3 and b1 / b2, short prompts
FOLDERS = {"t1": "testpics1", "t4": "testpics4", "p": "testpics5 persons"}
R2_DIR = BASE / "r2"
R2_SEEDS = (11, 12)
R2_MP = 2.0                      # the photos go in at about 2 MP, like the earlier rounds (never scaled up)
# (id, kind, (folder, file), what to mark (document name, German, ASCII), the text: Fill = the object, Remove = the name)
R2_A = [
    ("F01", "inpaint", ("t4", "pexels_1868676.jpeg"), "Ballon-im-Himmel", "a hot air balloon"),
    ("F02", "inpaint", ("t4", "pexels_2999008.jpeg"), "Fahrrad-an-der-Hauswand", "a bicycle leaning against the wall"),
    ("F03", "inpaint", ("t4", "pexels_352091.jpeg"), "Gleitschirm-im-Himmel", "a paraglider in the sky"),
    ("F04", "inpaint", ("t4", "pexels_68427.jpeg"), "Radfahrer-auf-der-Strasse", "a cyclist riding on the road"),
    ("F05", "inpaint", ("t4", "pexels_9241.jpg"), "Tankwagen-neben-dem-Jet", "a fuel truck parked on the tarmac"),
    ("F06", "inpaint", ("t4", "pexels_2067431.jpeg"), "Katze-auf-der-Theke", "a cat sitting on the counter"),
    ("F07", "inpaint", ("t1", "signal-2024-11-02-214028_006.jpeg"), "Lagerfeuer-vor-dem-Zelt", "a small campfire burning in the grass"),
    ("F08", "inpaint", ("t1", "signal-2024-11-02-213543_004.jpeg"), "Holzbank-auf-dem-Rasen", "a wooden garden bench on the lawn"),
    ("F09", "inpaint", ("t1", "Screenshot 2025-05-22 184738.png"), "Sonnenschirm-im-Sand", "a red beach umbrella stuck in the sand"),
    ("F10", "inpaint", ("t1", "signal-2024-11-02-214028_015.jpeg"), "Schwan-auf-dem-Wasser", "a white swan swimming on the water"),
    ("R01", "remove", ("t4", "pexels_3184394.jpeg"), "Frau-ganz-rechts", "the woman on the far right"),
    ("R02", "remove", ("t4", "pexels_68427.jpeg"), "Bus", "the bus"),
    ("R03", "remove", ("t4", "pexels_352091.jpeg"), "rote-Pistenraupe", "the red snow groomer"),
    ("R04", "remove", ("t1", "signal-2024-11-02-213543_004.jpeg"), "Person-rechts", "the person standing on the right"),
    ("R05", "remove", ("t1", "signal-2024-11-02-214028_006.jpeg"), "gelbes-Auto", "the yellow car"),
    ("R06", "remove", ("t1", "Screenshot 2025-03-14 091321.png"), "Mann-mit-Hund", "the man and the dog"),
    ("R07", "remove", ("t1", "signal-2024-11-02-214028_013.jpeg"), "Dose", "the green can"),
    ("R08", "remove", ("t1", "signal-2024-11-02-214028_009.jpeg"), "Mann-auf-der-Kugel", "the man standing on the golden ball"),
    ("R09", "remove", ("t1", "Screenshot 2025-03-14 091310.png"), "Baum-auf-dem-Felsen", "the tree on the rock"),
    ("R10", "remove", ("t1", "signal-2024-11-02-214028_011.jpeg"), "Ruestung-in-der-Mitte", "the suit of armour in the middle"),
]
# (tag, picture 1, references, short prompt)
R2_PAIRS = [
    ("sakko", ("t1", "Screenshot 2025-05-25 201650.png"), [("p", "linkedin-sales-solutions-pAtA8xe_iVM-unsplash.jpg")],
     "The man in <Picture 1> wears the dark blazer and white shirt from <Picture 2>."),
    ("bluse", ("t1", "Screenshot 2025-05-25 201646.png"), [("p", "stefan-stefancik-QXevDflbl8A-unsplash.jpg")],
     "The woman in <Picture 1> wears the striped blouse from <Picture 2>."),
    ("muetze", ("t1", "Screenshot 2025-05-25 201643.png"), [("p", "philip-martin-5aGUyCW_PJw-unsplash.jpg")],
     "The man in <Picture 1> wears the orange beanie and the black turtleneck sweater from <Picture 2>."),
    ("pulli-rot", ("t4", "pexels_2058662.jpeg"), [("p", "h-ng-ph-m-nX8P-y9uVac-unsplash.jpg")],
     "The man in <Picture 1> wears the red knitted sweater from <Picture 2> instead of the white hoodie."),
    ("gesicht", ("t4", "pexels_1300402.jpeg"), [("p", "craig-mckay-jmURdhtm7Ng-unsplash.jpg")],
     "The man in <Picture 1> has the face, the bald head and the long beard of the man in <Picture 2>."),
    ("hund", ("t1", "Screenshot 2025-05-13 204144.png"), [("t1", "Screenshot 2025-04-10 184005.png")],
     "The man in <Picture 1> walks the golden retriever from <Picture 2> on a leash beside him."),
    ("korb", ("t4", "pexels_2067431.jpeg"), [("t1", "Screenshot 2025-05-13 204208.png")],
     "The wicker basket from <Picture 2>, filled with fresh bread, stands on the counter in <Picture 1>."),
    ("strand", ("t1", "Screenshot 2025-05-22 184738.png"),
     [("p", "toa-heftiba-O3ymvT7Wf9U-unsplash.jpg"), ("t1", "Screenshot 2025-04-10 184350.png")],
     "The woman from <Picture 2> walks along the beach in <Picture 1> with the beagle from <Picture 3> running beside her."),
]
R = {"round": 1, "testpics": None}           # set from the command line
FAULTS = (
    ("1", "task", "Auftrag nicht erfüllt (Objekt fehlt / nicht ganz weg)"),
    ("2", "changed", "Rest verändert"),
    ("3", "seam", "Rand oder Naht sichtbar"),
    ("4", "red", "rote Linie / Rahmen übrig"),
    ("5", "artifact", "Bildfehler (Hände, Verzerrung)"),
    ("6", "wrong", "falsch übernommen (Größe, Ort, Referenz)"),
)
GOOD, BAD = "gut", "schlecht"


# ---------- the cases ----------

def a_cases() -> list[dict]:
    if R["round"] == 2:
        return [{"id": c[0], "kind": c[1], "src": c[2], "task": c[3], "text": c[4], "file": R2_DIR / "fotos" / f"{c[0]}.png",
                 "maskfile": R2_DIR / "masken" / f"{c[0]}.png"} for c in R2_A]
    out = [{"id": f"F{i + 1}", "kind": "inpaint", "photo": c[0], "text": c[1], "shape": c[2], "box": c[3:7]}
           for i, c in enumerate(lff.CASES)]
    out += [{"id": c[0], "kind": "remove", "photo": c[1], "text": c[2], "shape": c[3], "box": c[4], "case": c}
            for c in lrn.CASES]
    return out


def jobs(only: str) -> list[tuple]:
    """(variant, case id, seed); model after model, so each loads once (MiniMax first, its B too)."""
    js = []
    if R["round"] == 2:
        if only in ("", "a"):
            js += [("a1", c["id"], s) for c in a_cases() for s in R2_SEEDS]
        if only in ("", "b"):
            js += [(v, p[0], s) for v in ("b1", "b2") for p in R2_PAIRS for s in R2_SEEDS]
        if only in ("", "a"):
            js += [(v, c["id"], s) for v in ("qwen", "flux3") for c in a_cases() for s in R2_SEEDS]
        return js
    if only in ("", "a"):
        js += [(v, c["id"], SEED_A) for v in ("a1", "a2") for c in a_cases()]
    if only in ("", "b"):
        js += [(v, f"{p[0]}-{s}", SEED_B) for v in B_VARIANTS for p in PAIRS for s in ("kurz", "lang")]
    if only in ("", "a"):
        js += [(v, c["id"], SEED_A) for v in ("qwen", "flux3") for c in a_cases()]
    return js


def fid_of(variant: str, cid: str, seed: int) -> str:
    return f"{cid}_{variant}" + (f"_s{seed}" if R["round"] == 2 else "")


def photo(folder: Path, name: str) -> Image.Image:
    with Image.open(folder / name) as im:
        return im.convert("RGB")


def source(ref: tuple) -> Image.Image:
    """(folder key, file) under --testpics, as it is."""
    return photo(Path(R["testpics"]) / FOLDERS[ref[0]], ref[1])


def at_2mp(im: Image.Image) -> Image.Image:
    k = min(1.0, (R2_MP * 1e6 / (im.width * im.height)) ** 0.5)
    return im if k >= 1.0 else im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)


def a_selection(pic: Image.Image, c: dict) -> Image.Image:
    if "maskfile" in c:
        with Image.open(c["maskfile"]) as m:
            return m.convert("L").point(lambda v: 255 if v > 127 else 0)
    return lrn.selection(pic, c["case"]) if c["kind"] == "remove" else lff.selection(pic.size, c["shape"], c["box"])


def outlined(pic: Image.Image, sel: Image.Image) -> Image.Image:
    """The input for the rating: the photo with the selection's edge in red."""
    edge = sel.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(7))
    out = pic.copy()
    out.paste((255, 40, 40), mask=edge)
    return out


def side_by_side(*ims: Image.Image, h: int = 1200) -> Image.Image:
    rs = [im.resize((round(im.width * h / im.height), h), Image.LANCZOS) for im in ims]
    out = Image.new("RGB", (sum(r.width for r in rs) + 16 * (len(rs) - 1), h), (40, 40, 40))
    x = 0
    for r in rs:
        out.paste(r, (x, 0))
        x += r.width + 16
    return out


# ---------- the plugin path ----------

_REQS: dict = {}


def window_request(app, model: str, mode: str):
    """The Request the window sends for this mode with the model's start values (cached)."""
    if (model, mode) not in _REQS:
        app.v_model.set(model)
        app.v_mode.set(mode)
        app._factory = True
        try:
            app._on_model()
            app._on_mode()
        finally:
            app._factory = False
        app.t_prompt.delete("1.0", "end")
        _REQS[(model, mode)] = app._request()
    return copy.deepcopy(_REQS[(model, mode)])


class NoMark(Bridge):
    """a2: the crop goes to the model without the red outline (Pixaroma: only the cut-out area is <Picture 1>)."""
    def _plan(self, *a, **k):
        req, job = super()._plan(*a, **k)
        return req, dataclasses.replace(job, marked=False)


def run_a(comfy, app, folder: Path, variant: str, c: dict, seed: int) -> tuple[Image.Image, Image.Image]:
    if "file" in c:
        with Image.open(c["file"]) as im:
            pic = im.convert("RGB")
    else:
        pic = photo(folder, c["photo"])
    sel = a_selection(pic, c)
    req = window_request(app, A_MODEL[variant], c["kind"])
    req.enhance = False if variant in ("a1", "a2") else req.enhance
    if c["kind"] == "remove":
        req.remove_target = c["text"]
        req.remove_tries = 1
    req.params = replace(req.params, prompt=c["text"], seed=seed)
    if variant == "a2":
        req.context = A2_CONTEXT
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="minimax-fill-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], sel))
    keep = bridge.fill_prompt, bridge.remove_prompt
    if variant == "a1":
        bridge.fill_prompt = lambda text, mask, workflow=None: bridge.FILL_PROMPT_LARGE.format(text=text.strip().rstrip("."), shape=bridge._shape(mask))
    elif variant == "a2":
        bridge.fill_prompt = lambda text, mask, workflow=None: A2_FILL.format(text=text.strip().rstrip("."))
        bridge.remove_prompt = lambda mask, attempt=0, target="": A2_REMOVE.format(target=target or "the object")
    try:
        (NoMark if variant == "a2" else Bridge)(pc, comfy, tmp).run(req)
    finally:
        bridge.fill_prompt, bridge.remove_prompt = keep
        shutil.rmtree(tmp, ignore_errors=True)
    return pc.composite(pc.doc), outlined(pic, sel)


def pair(cid: str) -> tuple:
    if R["round"] == 2:
        p = next(p for p in R2_PAIRS if p[0] == cid)
        return p, p[3]
    tag, which = cid.rsplit("-", 1)
    p = next(p for p in PAIRS if p[0] == tag)
    return p, (p[3] if which == "kurz" else p[4])


def run_b(comfy, app, photos: Path, refs: Path, variant: str, cid: str, ref_mp: float, seed: int) -> tuple[Image.Image, Image.Image]:
    p, prompt = pair(cid)
    if R["round"] == 2:
        pic, rlist = at_2mp(source(p[1])), [source(r) for r in p[2]]
    else:
        pic, rlist = photo(photos, p[1]), [photo(refs, p[2])]
    req = window_request(app, "minimax", "multi_edit")
    v = B_VARIANTS[variant]
    req.gen_mp = v["gen_mp"]
    req.ref_native = v["ref_native"]
    biggest = max(r.width * r.height for r in rlist) / 1e6
    req.ref_mp = ref_mp if ref_mp > 0 else biggest + 1     # 0 = no cap: the references as they are
    req.enhance = False
    req.refs = rlist
    req.params = replace(req.params, prompt=prompt, seed=seed)
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="minimax-multi-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], None))
    try:
        Bridge(pc, comfy, tmp).run(req)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    doc = pc.docs[-1]
    return (getattr(doc, "raw", None) or pc.composite(doc)), side_by_side(pic, *rlist)


def run_job(comfy, app, a, variant: str, cid: str, seed: int):
    if variant.startswith("b"):
        return run_b(comfy, app, Path(a.photos or "."), Path(a.refs or "."), variant, cid, a.ref_mp, seed)
    return run_a(comfy, app, Path(a.photos or "."), variant, next(c for c in a_cases() if c["id"] == cid), seed)


def is_pair(cid: str) -> bool:
    return any(p[0] == cid for p in R2_PAIRS) if R["round"] == 2 else "-" in cid


def describe(cid: str) -> str:
    if is_pair(cid):
        p, prompt = pair(cid)
        return f"{p[0]}: {prompt}" if R["round"] == 2 else f"{p[0]} ({cid.rsplit('-', 1)[1]}): {prompt}"
    c = next(c for c in a_cases() if c["id"] == cid)
    where = c["task"] if "task" in c else c["photo"][:2]
    return f"{'Fill' if c['kind'] == 'inpaint' else 'Remove'} {cid} {where}: {c['text']}"


# ---------- commands ----------

def cmd_plan(a):
    js = jobs(a.only)
    for v, cid, s in js:
        print(f"{NAME[v]:<36} s{s} {describe(cid)[:110]}")
    print(f"{len(js)} pictures")


R2_PREFIX = "mm2-"


def cmd_open2(a):
    """Round 2: every Fill/Remove case as its own PhotoCraft document at about 2 MP; the name says what to mark
    (mm2-F01_Ballon-im-Himmel.png). The same picture is saved as the round's photo (r2/fotos), so the selection fits it."""
    pc, exchange = lrn.photocraft()
    exchange.mkdir(parents=True, exist_ok=True)
    (R2_DIR / "fotos").mkdir(parents=True, exist_ok=True)
    have = [str(d.get("name", "")) for d in pc.session().get("documents", [])]
    for c in a_cases():
        name = f"{R2_PREFIX}{c['id']}_{c['task']}.png"
        if any(h.startswith(f"{R2_PREFIX}{c['id']}_") for h in have):
            print(f"{name}: already open", flush=True)
            continue
        pic = at_2mp(source(c["src"]))
        pic.save(c["file"])
        pic.save(exchange / name)
        pc.open(name)
        print(f"{name}: {pic.width}x{pic.height}", flush=True)


def cmd_grab2(a):
    """Round 2: reads the selection of every open mm2-* document into r2/masken (as a run reads it)."""
    import numpy as np
    pc, exchange = lrn.photocraft()
    br = Bridge(pc, None, exchange)
    (R2_DIR / "masken").mkdir(parents=True, exist_ok=True)
    ids = {c["id"]: c for c in a_cases()}
    for d in pc.session().get("documents", []):
        name = str(d.get("name", ""))
        cid = name[len(R2_PREFIX):].split("_")[0]
        if not name.startswith(R2_PREFIX) or cid not in ids:
            continue
        idx = d.get("index")
        pc.activate(idx)
        try:
            _src, mask = br._export(idx, f"grab-{cid}", need_mask=True)
        except Exception as e:      # noqa: BLE001  PhotoCraft says "no selection": report it, go on with the others
            print(f"{cid}: no selection ({str(e)[-60:]}), nothing saved  [{ids[cid]['task']}]", flush=True)
            continue
        finally:
            br._cleanup()
        share = float((np.asarray(mask) > 127).mean())
        if share == 0 or share > 0.95:
            print(f"{cid}: no selection drawn (or all selected), nothing saved  [{ids[cid]['task']}]", flush=True)
            continue
        with Image.open(ids[cid]["file"]) as im:
            if mask.size != im.size:
                print(f"{cid}: the document has size {mask.size}, the photo {im.size}; nothing saved", flush=True)
                continue
        mask.point(lambda v: 255 if v > 127 else 0).save(ids[cid]["maskfile"])
        print(f"{cid}: saved, {100 * share:.1f} % of the picture  [{ids[cid]['task']}]", flush=True)
    missing = [c for c in ids if not ids[c]["maskfile"].exists()]
    print("\nMissing: " + (", ".join(missing) if missing else "none"), flush=True)


def sent(graph: dict) -> str:
    """The text the model gets: MiniMax's conditioning prompt when it is a plain string (writer off), else the field of the
    node titled pc:prompt."""
    texts = []
    for n in graph.values():
        if not isinstance(n, dict):
            continue
        ins = n.get("inputs", {})
        for k in ("prompt", "text", "value", "replace", "string"):
            if isinstance(ins.get(k), str) and len(ins[k]) > 10 and "{input text}" not in ins[k]:
                texts.append(ins[k])
    return max(texts, key=lambda t: ("<Picture" in t or "red" in t or "Remove" in t or "Add" in t, -len(t)), default="")


def red_share(im: Image.Image) -> float:
    a = __import__("numpy").asarray(im.convert("RGB").resize((256, 256), Image.NEAREST)).astype(int)
    return float(((a[..., 0] > 220) & (a[..., 1] < 40) & (a[..., 2] < 40)).mean())


def check_dry(app, a) -> None:
    """Every job against the fake ComfyUI: the right model, the text in the graph, the red outline only in a1, the
    reference size of B."""
    for variant, cid, seed in jobs(a.only):
        fake = T.FakeComfy()
        run_job(fake, app, a, variant, cid, seed)
        g = fake.graphs[-1]
        unets = [n["inputs"].get("unet_name", "") for n in g.values() if isinstance(n, dict) and n.get("class_type") == "UNETLoader"]
        text = sent(g)
        imgs = {k: v for k, v in fake.uploads.items()}
        main = next((v for k, v in imgs.items() if k.endswith("-image.png")), None)
        refs = [v.size for k, v in imgs.items() if "-ref" in k]
        info = f"{variant} {cid} s{seed}: {', '.join(unets)[:60]}; crop {main.size if main else '-'}"
        if variant in ("a1", "a2"):
            assert any("minimax" in u for u in unets), info
            red = red_share(main)
            assert (red > 0.001) == (variant == "a1"), (info, red)
            assert ("red " in text) == (variant == "a1") and ("exactly as it is" in text) == (variant == "a2"), (info, text[:200])
            info += f"; rot {red:.3f}"
        if variant.startswith("b"):
            assert any("minimax" in u for u in unets) and refs, info
            if variant == "b1":
                assert all(max(r) <= 2048 for r in refs), (info, refs)
            elif a.ref_mp <= 0:
                assert len(refs) == len(pair(cid)[0][2]) if R["round"] == 2 else True, (info, refs)
            info += f"; ref {refs}"
        print(info + f"; Text: {text[:150]!r}", flush=True)
    print(f"ok: {len(jobs(a.only))} graphs build")


def cmd_run(a):
    need = (("--testpics", a.testpics),) if R["round"] == 2 else (("--photos", a.photos), ("--refs", a.refs))
    for what, d in need:
        if not d or not Path(d).is_dir():
            sys.exit(f"{what} <folder> is missing or not there: {d}")
    if R["round"] == 2 and a.only != "b":
        missing = [c["id"] for c in a_cases() if not c["maskfile"].exists()]
        if missing:
            sys.exit(f"Round 2: no selection yet for {', '.join(missing)} (open2, draw in PhotoCraft, grab2)")
    models.MINIMAX.modes.update(TEST_MODES)          # for this run only
    url = a.url or cfgmod.load()["comfyui"]["url"]
    app = base.make_app("http://127.0.0.1:1" if a.dry else url)
    try:
        check_dry(app, a)
        if a.dry:
            return
        out = BASE / (("r2-" if R["round"] == 2 else "") + time.strftime("%Y%m%d-%H%M%S"))
        for sub in ("bilder", "eingabe"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        from live_expand_remote import Timed
        comfy = Timed(url)
        key, js = {}, jobs(a.only)
        left = Left(len(js))
        for i, (variant, cid, seed) in enumerate(js, 1):
            fid = fid_of(variant, cid, seed)
            t0 = time.time()
            try:
                res, inp = run_job(comfy, app, a, variant, cid, seed)
            except Exception as e:      # noqa: BLE001  one failed picture must not stop the round
                msg = str(e).splitlines()[-1][:300] if str(e) else type(e).__name__
                print(f"{i}/{len(js)} {fid} failed: {msg}", flush=True)
                continue
            secs = round(time.time() - t0)
            res.save(out / "bilder" / f"{fid}.png")
            if not (out / "eingabe" / f"{cid}.jpg").exists():
                inp.save(out / "eingabe" / f"{cid}.jpg", quality=92)
            key[fid] = {"variant": variant, "case": cid, "seed": seed, "text": describe(cid), "input": f"{cid}.jpg", "secs": secs}
            order = list(key)
            random.Random(2111).shuffle(order)
            json.dump({"items": key, "order": order, "names": NAME}, open(out / "key.json", "w", encoding="utf-8"),
                      indent=1, ensure_ascii=False)
            page(out, key)
            print(f"{i}/{len(js)} {fid}: {secs} s" + left(i), flush=True)
        print(f"Results: {(out / 'index.html').as_uri()}")
    finally:
        app.root.destroy()


def page(out: Path, key: dict) -> None:
    sets = {}
    for fid, it in key.items():
        th = out / "thumbs" / f"{fid}.jpg"
        if not th.exists():
            th.parent.mkdir(exist_ok=True)
            im = Image.open(out / "bilder" / f"{fid}.png").convert("RGB")
            im.thumbnail((120, 90), Image.LANCZOS)
            im.save(th, quality=85)
        s = sets.setdefault(it["case"], {"title": it["text"][:90], "images": [
            {"label": "Eingabe", "short": "Eingabe", "src": f"eingabe/{it['input']}", "thumb": f"eingabe/{it['input']}",
             "prompt": it["text"]}]})
        s["images"].append({"label": f"{NAME[it['variant']]}, {it['secs']} s", "short": NAME[it["variant"]].split(" (")[0],
                            "src": f"bilder/{fid}.png", "thumb": f"thumbs/{fid}.jpg", "prompt": it["text"], "id": fid})
    tpl = (ROOT / "tools" / "ab_viewer_template.html").read_text(encoding="utf-8")
    html = tpl.replace("<title>Fibo Upscale A/B</title>", "<title>MiniMax Fill und Multi A/B</title>").replace(
        "__SETS__", json.dumps(list(sets.values()), ensure_ascii=False))
    (out / "index.html").write_text(html, encoding="utf-8")


def latest(folder):
    if folder:
        return Path(folder)
    runs = sorted(p for p in BASE.iterdir() if (p / "key.json").exists()) if BASE.exists() else []
    if not runs:
        sys.exit(f"No round in {BASE}")
    return runs[-1]


def cmd_rate(a):
    """One result at a time beside its input, the task above; the variant stays hidden. Keys: G good, S bad, 1 to 6
    faults (also on good), arrows."""
    import tkinter as tk
    from PIL import ImageTk
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    items, order = key["items"], key["order"]
    fout = out / "bewertung.json"
    data = json.loads(fout.read_text(encoding="utf-8")) if fout.exists() else {}
    root = tk.Tk()
    root.title("MiniMax Fill / Multi bewerten (blind)")
    root.configure(bg="#282828")
    st = {"i": next((k for k, f in enumerate(order) if not data.get(f, {}).get("wahl")), 0), "loading": False}
    faults = {code: tk.BooleanVar() for _, code, _ in FAULTS}
    choice, note = tk.StringVar(), tk.StringVar()
    top = tk.Label(root, bg="#282828", fg="#e6e6e6", font=("Segoe UI", 12, "bold"), wraplength=1800, justify="left")
    top.pack(pady=(8, 4))
    row = tk.Frame(root, bg="#282828")
    row.pack()
    pics = [tk.Label(row, bg="#282828") for _ in range(2)]
    for lbl in pics:
        lbl.pack(side="left", padx=6)
    side = tk.Frame(root, bg="#282828")
    side.pack(pady=6)
    kw = dict(bg="#282828", selectcolor="#535353", activebackground="#282828", activeforeground="#ffffff",
              font=("Segoe UI", 11), command=lambda: save())
    tk.Radiobutton(side, text="gut (G)", variable=choice, value=GOOD, fg="#7bd389", **kw).pack(side="left", padx=12)
    tk.Radiobutton(side, text="schlecht (S)", variable=choice, value=BAD, fg="#f07b7b", **kw).pack(side="left", padx=12)
    ff = tk.Frame(root, bg="#282828")
    ff.pack(pady=2)
    tk.Label(ff, text="Fehler ankreuzen (Tasten 1–6, auch bei „gut“ möglich):", bg="#282828", fg="#cfcfcf",
             font=("Segoe UI", 10)).grid(row=0, column=0, columnspan=3, sticky="w")
    for k, (digit, code, text) in enumerate(FAULTS):
        tk.Checkbutton(ff, text=f"{digit}  {text}", variable=faults[code], bg="#282828", fg="#f0c674", selectcolor="#535353",
                       activebackground="#282828", activeforeground="#ffffff", font=("Segoe UI", 10),
                       command=lambda: save()).grid(row=1 + k // 3, column=k % 3, sticky="w", padx=8)
    nf = tk.Frame(root, bg="#282828")
    nf.pack(pady=4)
    tk.Label(nf, text="Notiz:", bg="#282828", fg="#cfcfcf").pack(side="left")
    ent = tk.Entry(nf, textvariable=note, bg="#535353", fg="#ffffff", insertbackground="#ffffff", width=90)
    ent.pack(side="left", padx=6)
    nav = tk.Frame(root, bg="#282828")
    nav.pack(pady=4)
    tk.Button(nav, text="← Zurück", command=lambda: go(-1)).pack(side="left")
    tk.Button(nav, text="Weiter →", command=lambda: go(1)).pack(side="left", padx=8)
    status = tk.Label(nav, bg="#282828", fg="#9a9a9a")
    status.pack(side="left", padx=16)

    def count():
        status.configure(text=f"bewertet: {sum(1 for f in order if data.get(f, {}).get('wahl'))}/{len(order)}  ·  gespeichert in {fout}")

    def show():
        fid = order[st["i"]]
        it = items[fid]
        top.configure(text=f"Bild {st['i'] + 1}/{len(order)}  ·  {it['text']}")
        side_px = min((root.winfo_screenwidth() - 60) // 2, root.winfo_screenheight() - 330)
        st["photos"] = []
        for lbl, path in zip(pics, (out / "eingabe" / it["input"], out / "bilder" / f"{fid}.png")):
            im = Image.open(path).convert("RGB")
            im.thumbnail((side_px, side_px))
            ph = ImageTk.PhotoImage(im)
            st["photos"].append(ph)
            lbl.configure(image=ph)
        st["loading"] = True
        rec = data.get(fid, {})
        choice.set(rec.get("wahl", ""))
        note.set(rec.get("notiz", ""))
        for code, var in faults.items():
            var.set(code in rec.get("fehler", []))
        st["loading"] = False
        count()

    def save():
        if st["loading"]:
            return
        fid = order[st["i"]]
        data[fid] = {"wahl": choice.get(), "notiz": note.get().strip(),
                     "fehler": [code for _, code, _ in FAULTS if faults[code].get()]}
        fout.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        count()

    def go(step):
        st["i"] = max(0, min(len(order) - 1, st["i"] + step))
        show()

    def key_press(e):
        if root.focus_get() is ent:
            return
        if e.char.lower() in ("g", "s"):
            choice.set(GOOD if e.char.lower() == "g" else BAD)
            save()
            root.after(250, lambda: go(1))
        elif e.keysym in ("Right", "Left"):
            go(1 if e.keysym == "Right" else -1)
        elif e.char in {d for d, _, _ in FAULTS}:
            var = faults[next(c for d, c, _ in FAULTS if d == e.char)]
            var.set(not var.get())
            save()

    note.trace_add("write", lambda *x: save())
    root.bind("<Key>", key_press)
    root.bind("<Button-1>", lambda e: root.focus_set() if e.widget in pics else None)
    root.state("zoomed")
    show()
    root.mainloop()


def summarize(key: dict, data: dict) -> str:
    """Good and fault-free good per variant (Fill, Remove, Multi apart), per case, the faults and the mean time."""
    items = key["items"]
    rows, faults, secs = {}, {}, {}
    part = lambda it: "Multi" if it["variant"].startswith("b") else ("Fill" if it["case"].startswith("F") else "Remove")  # noqa: E731
    for fid, it in items.items():
        secs.setdefault((part(it), it["variant"]), []).append(it["secs"])
        rec = data.get(fid, {})
        if not rec.get("wahl"):
            continue
        good = rec["wahl"] == GOOD
        clean = good and not rec.get("fehler")
        for k in (("Variante", f"{part(it)} · {NAME[it['variant']]}"), ("Fall", f"{it['case']} · {NAME[it['variant']]}")):
            r = rows.setdefault(k, [0, 0, 0])
            r[0] += 1
            r[1] += good
            r[2] += clean
        for f in rec.get("fehler", []):
            faults[(part(it), it["variant"], f)] = faults.get((part(it), it["variant"], f), 0) + 1
    rated = sum(1 for f in items if data.get(f, {}).get("wahl"))
    lines = [f"# MiniMax Fill/Remove und Multi image edit {key.get('folder', '')}".rstrip(), "",
             f"Bewertet: {rated} von {len(items)} (blind, Seeds A {SEED_A}, B {SEED_B})", ""]
    for kind in ("Variante", "Fall"):
        sub = sorted((name, r) for (k, name), r in rows.items() if k == kind)
        if sub:
            lines += [f"## Je {kind}", "", f"| {kind} | bewertet | gut | fehlerfrei gut |", "|---|---|---|---|"]
            lines += [f"| {name} | {r[0]} | {r[1]} | {r[2]} |" for name, r in sub] + [""]
    if faults:
        names = {c: t for _, c, t in FAULTS}
        lines += ["## Fehler je Variante (auch bei „gut“)", "", "| Teil | Variante | Fehler | Anzahl |", "|---|---|---|---|"]
        lines += [f"| {p} | {NAME[v]} | {names.get(c, c)} | {n} |" for (p, v, c), n in sorted(faults.items())] + [""]
    lines += ["## Zeit je Bild", "", "| Teil | Variante | Bilder | Mittel s |", "|---|---|---|---|"]
    lines += [f"| {p} | {NAME[v]} | {len(s)} | {sum(s) / len(s):.0f} |" for (p, v), s in sorted(secs.items())] + [""]
    notes = [(items[f], r["notiz"]) for f, r in data.items() if r.get("notiz") and f in items]
    if notes:
        lines += ["## Notizen", ""] + [f"- {NAME[it['variant']]}, {it['case']}: {n}" for it, n in notes]
    return "\n".join(lines) + "\n"


def cmd_summary(a):
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    key["folder"] = out.name
    data = json.loads((out / "bewertung.json").read_text(encoding="utf-8")) if (out / "bewertung.json").exists() else {}
    text = summarize(key, data)
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "run", "rate", "summary", "open2", "grab2"))
    ap.add_argument("folder", nargs="?", default="")
    ap.add_argument("--photos", default="")
    ap.add_argument("--refs", default="")
    ap.add_argument("--only", default="", choices=("", "a", "b"))
    ap.add_argument("--ref-mp", type=float, default=0.0, help="B2/B3: cap of the references in megapixels (0 = none)")
    ap.add_argument("--url", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--round", type=int, default=1, choices=(1, 2))
    ap.add_argument("--testpics", default="", help="round 2: the folder D:\testpics (testpics1, testpics4, testpics5 persons)")
    a = ap.parse_args()
    R["round"] = 2 if a.cmd in ("open2", "grab2") else a.round
    R["testpics"] = a.testpics
    {"plan": cmd_plan, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary, "open2": cmd_open2,
     "grab2": cmd_grab2}[a.cmd](a)


if __name__ == "__main__":
    main()
