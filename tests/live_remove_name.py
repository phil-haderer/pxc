r"""Manual check (not part of run_all.py): Remove with the object named automatically (user 15.11.,
docs/tests/remove-name-testplan.md).

Stage 1 ("names"): the text models name the object inside the selection, with two questions:
    a  the crop Remove sends (Context 40 %) with the selection drawn in as a red outline: "... inside the red outline?"
    b  only the selection's bounding box, no outline: "What is the main object in this picture?"
Each writer of the tested models (manifest.DESCRIBE_WRITERS: Flux 2 and Fibo Qwen3-VL 4B, Flux 3 its prompt upsampler,
Qwen Qwen 3.5 9B w4a8) answers both for every case; no seed, so the likeliest words (as the plugin would do it).
names.html shows each crop with the answers and times; the user rates them right / vague / wrong (in the chat).

Stage 2 ("run"): every case through the plugin's real Remove (Bridge.run against the PhotoCraft simulator of
tests/test_reference_mode.py, the Request the window builds from the model's start values), one try (remove_tries 1, so
only the first sentence counts):
    A   today: no name, bridge.REMOVE_PROMPT
    C   the name from stage 1 (the model's own writer, --question a or b, cleaned: clean_name) in NEW_TARGET_PROMPT
        (user 15.11.: the plugin's REMOVE_TARGET_PROMPT says "anything it holds or stands on", which for a cup or a book
        means the table too)
    C2  (--c2) the same name with REMOVE_TARGET_PROMPT_ALT
    D   (16.11., --pair CD: rated C against D) C plus "Keep every other object that only partly reaches into the red ..."
        (the user saw objects that only partly reach into the selection removed too); with --reuse <round 15.11.> the
        C pictures whose name is unchanged are taken over, only the rest is made
    E   (16.11., --set e, --pair DE) new photos (ECASES) with the user's own words; the model's writer gets them with the
        crop (WRITE_QUESTION, command "write") and writes the instruction for this object only, plus the fixed E_END
        python tests\live_remove_name.py --set e grab-e --images <testpics magnific 3>\2MP   (selections from PhotoCraft)
        python tests\live_remove_name.py --set e preview / names / write / dry --pair DE --full / run --pair DE
    F   (16.11., --set e, --pair FE --reuse <the D/E round>) the user's words as the name in sentence D (user_name, only
        "the" in front), no text model; the E pictures are taken over
Flux 2, Flux 3, Fibo; Qwen only with --qwen (it is "perfect": only for comparison). 6 cases x 2 seeds = 72 pictures.

    python tests\live_remove_name.py open --images "<testpics magnific>\2MP"   (each case as its own document rn-N1 ... rn-N8
                                                    in PhotoCraft; the user draws the selection in each, user 15.11.)
    python tests\live_remove_name.py grab           (reads the selection of every open rn-N* document into masken/N*.png;
                                                    from then on every command uses these masks instead of the boxes)
    python tests\live_remove_name.py preview --images "<testpics magnific>\2MP"   (the selections; no ComfyUI)
    python tests\live_remove_name.py names --images <folder> [--qwen]             (stage 1, a few minutes of GPU)
    python tests\live_remove_name.py dry --images <folder> [--c2] [--qwen] [--pair CD]   (stage 2 without ComfyUI: prompts)
    python tests\live_remove_name.py run --images <folder> [--question a] [--c2] [--qwen] [--pair CD --reuse <round>]
                                                    (stage 2, about 30 min)
    python tests\live_remove_name.py pack [round] --images <folder>   (the round as one zip for the other PC: JPEGs, the task
                                                    pictures with the user's selections, records, names, masks)
    python tests\live_remove_name.py unpack <zip>   (on the other PC; then "rate")
    python tests\live_remove_name.py rate [round]       (blind pairs A / C: which is better, "Schlecht" ticks, a note)
    python tests\live_remove_name.py summary [round]    (tables, also written to ergebnis.md)

Output: <PCCOMFY_HOME>/remove-name/ (vorschau.png, namen/, names.json, names.html) and <PCCOMFY_HOME>/remove-name/<time>/
(bilder/<token>.png, records.json, bewertung.json, ergebnis.md). Needs the GPU: before "names" and "run", remind the user
not to use ComfyUI or other GPU programs meanwhile."""
import argparse
import copy
import html
import json
import re
import os
import socket
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import live_expand_remote as ler  # noqa: E402  (graph keys, the timed client, the blind rating window)
import live_fill_flux as lff  # noqa: E402  (the hand-drawn selections)
import live_style_test as base  # noqa: E402  (the hidden plugin window)
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator)
from pccomfy import bridge, config as cfgmod, imaging, inventory, manifest, models  # noqa: E402
from pccomfy.bridge import Bridge, BridgeError  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "remove-name"
SEEDS = (11, 12)
CONTEXT = 0.4                      # the crop of question a: Remove's Context of Flux and Qwen
MODELS = ("flux2", "flux3", "fibo")

# N2 (the crouching man) and N5 (the person in the checked shirt) left out (user 15.11.: only the six cases whose selection
# he drew in PhotoCraft); the ids stay, so masks and ratings keep their meaning.
# (id, photo, what a person would call it (only shown in the rating), selection shape, box as shares of the photo)
CASES = [
    ("N1", "05_full-shot-kid.png", "the brown goat", "lasso", (0.71, 0.32, 1.00, 0.92)),
    ("N3", "07_man-with-tablet.png", "the small robot in the hand", "lasso", (0.22, 0.25, 0.42, 0.68)),
    ("N4", "09_students-working-study.png", "the coffee cup", "rect", (0.36, 0.20, 0.44, 0.32)),
    ("N6", "11_view-modern-construction.png", "the orange dump truck", "rect", (0.70, 0.00, 1.00, 0.38)),
    ("N7", "08_psychological-therapy-support.png", "the man sitting at the back", "rect", (0.33, 0.36, 0.465, 0.76)),
    ("N8", "04_front-view-boy.png", "the book on the table", "rect", (0.48, 0.68, 1.00, 0.96)),
]
# (16.11.) the set "e" for the test D against E: new photos of the user (testpics magnific 3\2MP), his selections drawn in
# PhotoCraft (grab-e), and his own words for what to remove, exactly as he wrote them (foreground / background only where
# he said it). N1 ... N8 above stay the set "n".
ECASES = [
    ("E06", "06_fiave-italy.png", "tree", "lasso", (0, 0, 1, 1)),
    ("E07", "07_herd-cows-grazing.png", "cows", "lasso", (0, 0, 1, 1)),
    ("E08", "08_high-mountains-hills.png", "bridge", "lasso", (0, 0, 1, 1)),
    ("E09", "09_man-sportswear-running.png", "man and shadow", "lasso", (0, 0, 1, 1)),
    ("E15", "15_student-learns-task.png", "book", "lasso", (0, 0, 1, 1)),
    ("E18", "18_young-people-skateboarding.png", "building in the background", "lasso", (0, 0, 1, 1)),
    ("E01", "01_accident-warehouse-man.png", "helmet behind the hand", "lasso", (0, 0, 1, 1)),
    ("E04", "04_clean-empty-library.png", "shelves in the background", "lasso", (0, 0, 1, 1)),
    ("E05", "05_diverse-university-students.png", "teacher in the background", "lasso", (0, 0, 1, 1)),
]
# E: the user's words go to the model's own writer with the crop Remove sends (red outline); it writes the instruction for
# this object only; the fixed end makes sure the red line goes too (user 16.11.: "Ganzer Satz, fester Schluss")
WRITE_QUESTION = ("The user wants to remove this from the picture: \"{text}\". The object is marked with a red outline. "
                  "Write one or two short English sentences for an image editor that remove exactly this object completely, "
                  "with every part of it and anything it holds, and paint the empty scenery behind it. Describe the object "
                  "precisely (kind, colour, position) so that no other object is confused with it, and name objects nearby "
                  "that must stay. Only the sentences, no explanation.")
E_END = " Also remove the red {shape} itself."
QUESTIONS = {
    "a": "What is the main object inside the red outline? Answer with 2 to 5 English words, like \"the brown goat\". "
         "Only the words, no sentence.",
    "b": "What is the main object in this picture? Answer with 2 to 5 English words, like \"the brown goat\". "
         "Only the words, no sentence.",
}
# the sentence of C (user 15.11.): without "or stands on" of bridge.REMOVE_TARGET_PROMPT
NEW_TARGET_PROMPT = ("Remove {target} inside the red {shape} completely, including every part of it and anything it holds. "
                     "Paint the empty scenery behind it, continuing the surroundings. Also remove the red {shape} itself.")
# the sentence of D (user 15.11.: objects that only partly reach into the selection were removed too): C plus one sentence
NEW_TARGET_PROMPT_D = ("Remove {target} inside the red {shape} completely, including every part of it and anything it holds. "
                       "Paint the empty scenery behind it, continuing the surroundings. Keep every other object that only "
                       "partly reaches into the red {shape} exactly as it is. Also remove the red {shape} itself.")
# F (16.11.): the user's own words as the name in sentence D, no text model (user_name)
SENTENCES = {"C": "NEW_TARGET_PROMPT", "C2": "REMOVE_TARGET_PROMPT_ALT", "D": "NEW_TARGET_PROMPT_D", "F": "NEW_TARGET_PROMPT_D"}
# the rating window of the Expand round pairs the "cap" 1.0 against 2.0: the first variant of --pair is 1.0, the second 2.0
PAIRS = {"AC": ("A", "C"), "CD": ("C", "D"), "DE": ("D", "E"), "FE": ("F", "E")}


def case(cid: str) -> tuple:
    return next(c for c in CASES if c[0] == cid)


def photo(folder: Path, name: str) -> Image.Image:
    with Image.open(folder / name) as im:
        return im.convert("RGB")


def selection(pic: Image.Image, c: tuple) -> Image.Image:
    """The user's own selection from PhotoCraft (masken/<id>.png, "grab") when there is one, else the drawn box / lasso."""
    f = BASE / "masken" / f"{c[0]}.png"
    if f.exists():
        with Image.open(f) as m:
            m = m.convert("L")
        if m.size == pic.size:
            return m.point(lambda v: 255 if v > 127 else 0)
        print(f"{f.name}: size {m.size} is not the photo's {pic.size}; the box is used", flush=True)
    return lff.selection(pic.size, c[3], c[4])


# ---------- the user's own selections (PhotoCraft) ----------

DOC_PREFIX = "rn-"


def photocraft():
    from pccomfy.photocraft import PhotoCraft
    pcc = cfgmod.load()["photocraft"]
    pc = PhotoCraft(pcc["host"], int(pcc["port"]), token_file=pcc["token_file"], headless=bool(pcc["headless"]))
    return pc.connect(), Path(pcc["exchange_dir"])


def cmd_open(a):
    """Every case as its own document, named after the case (rn-N1.png ...), so two cases on one photo get two documents."""
    folder = Path(a.images)
    pc, exchange = photocraft()
    exchange.mkdir(parents=True, exist_ok=True)
    have = [str(d.get("name", "")) for d in pc.session().get("documents", [])]
    for c in CASES:
        name = f"{DOC_PREFIX}{c[0]}.png"
        if any(h.startswith(name[:-4]) for h in have):
            print(f"{name}: already open", flush=True)
            continue
        photo(folder, c[1]).save(exchange / name)
        pc.open(name)
        print(f"{name}: {c[2]}", flush=True)


def cmd_grab(a):
    """Reads the selection of each open rn-N* document (Bridge._export on a throw-away duplicate, as a run does)."""
    pc, exchange = photocraft()
    br = Bridge(pc, None, exchange)
    (BASE / "masken").mkdir(parents=True, exist_ok=True)
    found = set()
    for d in pc.session().get("documents", []):
        name = str(d.get("name", ""))
        cid = name[len(DOC_PREFIX):].split(".")[0]
        if not name.startswith(DOC_PREFIX) or cid not in {c[0] for c in CASES}:
            continue
        idx = d.get("index")
        pc.activate(idx)
        try:
            _src, mask = br._export(idx, f"grab-{cid}", need_mask=True)
        finally:
            br._cleanup()
        share = float((np.asarray(mask) > 127).mean())
        if share == 0 or share > 0.95:
            print(f"{cid}: no selection drawn (or all selected), nothing saved", flush=True)
            continue
        mask.point(lambda v: 255 if v > 127 else 0).save(BASE / "masken" / f"{cid}.png")
        found.add(cid)
        print(f"{cid}: saved, {100 * share:.1f} % of the picture", flush=True)
    missing = [c[0] for c in CASES if c[0] not in found and not (BASE / "masken" / f"{c[0]}.png").exists()]
    print("\nMissing: " + (", ".join(missing) if missing else "none") + f"\nMasks: {BASE / 'masken'}", flush=True)


def cmd_grab_e(a):
    """(set e) The photo and selection of every open PhotoCraft document whose file name is one of ECASES; the photo is
    read from --images, so it must be the same file the document was opened from."""
    pc, exchange = photocraft()
    br = Bridge(pc, None, exchange)
    (BASE / "masken").mkdir(parents=True, exist_ok=True)
    folder = Path(a.images)
    by_photo = {c[1]: c for c in ECASES}
    found = set()
    for d in pc.session().get("documents", []):
        c = by_photo.get(str(d.get("name", "")))
        if not c:
            continue
        idx = d.get("index")
        pc.activate(idx)
        try:
            _src, mask = br._export(idx, f"grab-{c[0]}", need_mask=True)
        finally:
            br._cleanup()
        share = float((np.asarray(mask) > 127).mean())
        if share == 0 or share > 0.95:
            print(f"{c[0]} {c[1]}: no selection drawn (or all selected), nothing saved", flush=True)
            continue
        if mask.size != photo(folder, c[1]).size:
            print(f"{c[0]}: the document has size {mask.size}, the photo in {folder} another; nothing saved", flush=True)
            continue
        mask.point(lambda v: 255 if v > 127 else 0).save(BASE / "masken" / f"{c[0]}.png")
        found.add(c[0])
        print(f"{c[0]} {c[1]}: saved, {100 * share:.1f} % of the picture  [{c[2]}]", flush=True)
    missing = [c[0] for c in ECASES if c[0] not in found]
    print("\nMissing: " + (", ".join(missing) if missing else "none"), flush=True)


def clean_writing(text: str) -> str:
    """(E) The writer's answer as it goes to the image model: one line, no quotes, no talk about the task (sentences that
    start "Here", "Note", "The user", "Only", "Sure"), at most three sentences; braces doubled for str.format."""
    t = " ".join(text.replace("\n", " ").split()).strip().strip("\"'“”")
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    parts = [s for s in parts if not re.match(r"(here|note|the user|only|sure|okay|ok)\b", s, flags=re.I)][:3]
    t = " ".join(parts).strip("\"'“” ")
    if t and t[-1] not in ".!?":
        t += "."
    return t.replace("{", "{{").replace("}", "}}")


def cmd_write(a):
    """(E) The writer of each model writes the instruction for the user's words; writes.json (raw and cleaned)."""
    folder = Path(a.images)
    url = connect(a)
    comfy = ler.Timed(url)
    inv = inventory.fetch(comfy, cfgmod.model_map())
    br = Bridge(T.FakePC(tempfile.mkdtemp(prefix="remove-name-")), comfy, tempfile.mkdtemp(prefix="remove-name-"))
    wfile = BASE / "writes.json"
    data = json.loads(wfile.read_text(encoding="utf-8")) if wfile.exists() else {}
    for f in dict.fromkeys(writers(model_list(a)).values()):
        found = inv.found(f)
        if not found:
            print(f"SKIPPED {f}: ComfyUI does not list it", flush=True)
            continue
        for c in CASES:
            k = f"{f}|{c[0]}"
            if k in data:
                continue
            im = name_inputs(photo(folder, c[1]), c)["a"]
            t0 = time.time()
            try:
                text = br.describe_image(im, question=WRITE_QUESTION.format(text=c[2]), clip=found)
                data[k] = {"writer": f, "case": c[0], "text": c[2], "raw": text, "written": clean_writing(text),
                           "seconds": round(time.time() - t0, 1)}
            except BridgeError as ex:
                data[k] = {"writer": f, "case": c[0], "error": str(ex)[:300], "seconds": round(time.time() - t0, 1)}
            wfile.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"{c[0]} {manifest.DESCRIBE_NAMES.get(f, f)} ({data[k]['seconds']} s): "
                  f"{data[k].get('written') or data[k].get('error')}", flush=True)
    print(f"\nDONE -> {wfile}", flush=True)


def written(model: str, cid: str) -> str:
    wfile = BASE / "writes.json"
    data = json.loads(wfile.read_text(encoding="utf-8")) if wfile.exists() else {}
    v = data.get(f"{writers((model,))[model]}|{cid}", {})
    return clean_writing(v["raw"]) if v.get("raw") else ""


def name_inputs(pic: Image.Image, c: tuple) -> dict:
    """What the text model sees: a = the crop with the red outline (as Remove sends it), b = the selection's box only."""
    sel = selection(pic, c)
    box = imaging.mask_bbox(sel)
    region = imaging.grow_box(box, pic.size, CONTEXT)
    crop, s = pic.crop(region.pil()), sel.crop(region.pil())
    return {"a": imaging.mark_outline(crop, s, bridge.outline_width(*crop.size)), "b": pic.crop(box.pil())}


def outlined(pic: Image.Image, c: tuple, width: int = 7) -> Image.Image:
    """The photo with the selection outlined in red (preview and rating)."""
    im = pic.copy()
    line = selection(pic, c).filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v else 0).filter(ImageFilter.MaxFilter(width))
    ImageDraw.Draw(im).bitmap((0, 0), line, fill=(255, 0, 0))
    return im


def writers(models_: tuple) -> dict:
    """model -> the text model file its Describe uses first (manifest.DESCRIBE_WRITERS)."""
    return {m: manifest.describe_writers(m)[0] for m in models_}


def model_list(a) -> tuple:
    return MODELS + (("qwen",) if getattr(a, "qwen", False) else ())


# ---------- preview ----------

def cmd_preview(a):
    folder = Path(a.images)
    BASE.mkdir(parents=True, exist_ok=True)
    tiles = []
    for c in CASES:
        im = outlined(photo(folder, c[1]), c, 11)
        im.thumbnail((640, 640))
        own = (BASE / "masken" / f"{c[0]}.png").exists()
        tiles.append((f"{c[0]}  {c[2]}  ({'deine Auswahl' if own else 'Auswahl des Skripts'})", im))
    w, h = 640, max(t[1].height for t in tiles) + 26
    sheet = Image.new("RGB", (2 * w, (len(tiles) + 1) // 2 * h), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for k, (label, im) in enumerate(tiles):
        x, y = (k % 2) * w, (k // 2) * h
        sheet.paste(im, (x, y + 24))
        d.text((x + 6, y + 6), label, fill=(255, 255, 255))
    out = BASE / "vorschau.png"
    sheet.save(out)
    print(f"Preview: {out}")


# ---------- stage 1: names ----------

def connect(a) -> str:
    url = a.url or cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=3).close()
    except OSError:
        sys.exit(f"ComfyUI does not answer ({url}).")
    return url


NAME_WORDS = 8          # at most this many words go into the field


def clean_name(text: str) -> str:
    """The answer as it would go into the field (user 15.11., the Flux 3 upsampler kept talking): only up to the first
    full stop or line break, without "inside the red outline", no quotes, "the" in front unless it has an article, a
    capital "The" made small, at most NAME_WORDS words."""
    t = " ".join(text.replace("\n", ". ").split()).strip().strip("\"'“”")
    t = re.split(r"(?<=\w)[.!?;](\s|$)", t, maxsplit=1)[0]
    t = re.sub(r"\s*\b(inside|within|in) the red(-| )?(outlined?|rectangle|frame|area)( area)?\b", "", t, flags=re.I)
    t = t.strip().strip("\"'“”,:").strip()
    # (16.11.) no part of the picture that has to stay: "the miniature robot held in the hand" removed the hand (Flux 3 N3)
    t = re.sub(r"\s+(held|holding|carried|resting|lying|standing|placed)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+(in|on|at|across|under|next to) (the|a|an|his|her|their) (hands?|table|desk|floor|ground|foreground|"
               r"background)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+on (table|desk|floor|ground)$", "", t, flags=re.I)
    if not t:
        return ""
    words = t.split()[:NAME_WORDS]
    if words[0].lower() in ("the", "a", "an"):
        words[0] = words[0].lower()
    else:
        words.insert(0, "the")
    return " ".join(words).rstrip(",.:")


def cmd_names(a):
    folder = Path(a.images)
    url = connect(a)
    comfy = ler.Timed(url)
    inv = inventory.fetch(comfy, cfgmod.model_map())
    br = Bridge(T.FakePC(tempfile.mkdtemp(prefix="remove-name-")), comfy, tempfile.mkdtemp(prefix="remove-name-"))
    (BASE / "namen").mkdir(parents=True, exist_ok=True)
    nfile = BASE / "names.json"
    data = json.loads(nfile.read_text(encoding="utf-8")) if nfile.exists() else {}
    files = dict.fromkeys(writers(model_list(a)).values())
    for f in list(files):
        files[f] = inv.found(f)
        if not files[f]:
            print(f"SKIPPED {f}: ComfyUI does not list it", flush=True)
    print(f"ComfyUI: {url}\n{sum(1 for v in files.values() if v) * len(CASES) * 2} answers\n", flush=True)
    for f, found in files.items():             # one writer after the other, so each is loaded once
        if not found:
            continue
        for c in CASES:
            ins = name_inputs(photo(folder, c[1]), c)
            for q, im in ins.items():
                im.save(BASE / "namen" / f"{c[0]}-{q}.png")
                k = f"{f}|{c[0]}|{q}"
                if k in data:
                    continue
                t0 = time.time()
                try:
                    text = br.describe_image(im, question=QUESTIONS[q], clip=found)
                    data[k] = {"writer": f, "case": c[0], "question": q, "raw": text, "name": clean_name(text),
                               "seconds": round(time.time() - t0, 1)}
                except BridgeError as ex:
                    data[k] = {"writer": f, "case": c[0], "question": q, "error": str(ex)[:300], "seconds": round(time.time() - t0, 1)}
                nfile.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
                print(f"{c[0]} {q} {manifest.DESCRIBE_NAMES.get(f, f)}: {data[k].get('name') or data[k].get('error')}"
                      f"  ({data[k]['seconds']} s)", flush=True)
    write_names_html(data)
    print(f"\nDONE -> {BASE / 'names.html'}", flush=True)


def write_names_html(data: dict):
    """One row per case and question: the picture the text model saw, then each writer's answer and time."""
    fs = list(dict.fromkeys(v["writer"] for v in data.values()))
    head = "".join(f"<th>{html.escape(manifest.DESCRIBE_NAMES.get(f, f))}</th>" for f in fs)
    rows = []
    for c in CASES:
        for q in QUESTIONS:
            cells = []
            for f in fs:
                v = data.get(f"{f}|{c[0]}|{q}", {})
                txt = v.get("name") or ("Fehler: " + v["error"] if "error" in v else "–")
                cells.append(f"<td><b>{html.escape(txt)}</b><br><small>{v.get('seconds', '')} s</small></td>")
            rows.append(f"<tr><td>{c[0]}{q}<br><small>{html.escape(c[2])}</small></td>"
                        f"<td><img src='namen/{c[0]}-{q}.png'></td>{''.join(cells)}</tr>")
    page = ("<!doctype html><meta charset='utf-8'><title>Remove: Namen</title><style>body{background:#222;color:#eee;"
            "font-family:Segoe UI,sans-serif}td,th{border:1px solid #555;padding:6px;vertical-align:top}img{max-width:360px;"
            "max-height:240px}</style><h2>Stufe 1: Erkennt das Textmodell das Motiv?</h2><p>a = Ausschnitt mit roter "
            "Umrandung, b = nur die Auswahl. Je Name: richtig, ungenau oder falsch.</p>"
            f"<table><tr><th>Fall</th><th>Gesehen</th>{head}</tr>{''.join(rows)}</table>")
    (BASE / "names.html").write_text(page, encoding="utf-8")


# ---------- stage 2: pictures ----------

_REQS: dict = {}


def window_request(app, model: str):
    """The Request the window sends for Remove with this model's start values (cached)."""
    if model not in _REQS:
        app.v_model.set(model)
        app.v_mode.set("remove")
        app._factory = True
        try:
            app._on_model()
            app._on_mode()
        finally:
            app._factory = False
        app.t_prompt.delete("1.0", "end")
        _REQS[model] = app._request()
    return copy.deepcopy(_REQS[model])


def auto_name(model: str, cid: str, question: str) -> str:
    """The stage-1 answer of the model's own writer; "" when stage 1 has none (the case then runs without a name)."""
    nfile = BASE / "names.json"
    data = json.loads(nfile.read_text(encoding="utf-8")) if nfile.exists() else {}
    v = data.get(f"{writers((model,))[model]}|{cid}|{question}", {})
    return clean_name(v.get("raw", "")) if v.get("raw") else ""


def user_name(cid: str) -> str:
    """(F) The user's words exactly as he wrote them, only "the" in front when they have no article ("tree" -> "the tree")."""
    t = case(cid)[2].strip()
    return t if t.split()[0].lower() in ("the", "a", "an") else "the " + t


def expected_name(model: str, cid: str, variant: str, question: str) -> str:
    """The name a picture of this variant is made with (A none, E and F the user's words, else the text model's)."""
    if variant == "A":
        return ""
    if variant == "E":
        return case(cid)[2]
    if variant == "F":
        return user_name(cid)
    return auto_name(model, cid, question)


def variants(a) -> tuple:
    return PAIRS[a.pair] + (("C2",) if a.c2 else ())


def cap(a, v: str) -> float:
    """The "cap" field the rating window pairs: the first variant of --pair 1.0, the second 2.0, C2 3.0 (no partner)."""
    return {PAIRS[a.pair][0]: 1.0, PAIRS[a.pair][1]: 2.0}.get(v, 3.0)


def jobs(a) -> list:
    """(model, case, variant, seed); one model after the other, so each is loaded once."""
    return [(m, c[0], v, s) for m in model_list(a) for c in CASES for v in variants(a) for s in SEEDS]


def run_case(comfy, app, folder: Path, model: str, cid: str, variant: str, seed: int, name: str):
    c = case(cid)
    pic = photo(folder, c[1])
    req = window_request(app, model)
    req.remove_target = "" if variant == "A" else name
    req.remove_tries = 1
    req.enhance = False
    req.params = replace(req.params, prompt=req.remove_target, seed=seed)
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="remove-name-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("scene.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], selection(pic, c)))
    keep = bridge.REMOVE_TARGET_PROMPT
    if variant == "E":            # the field holds the user's words; the instruction is the writer's text plus the fixed end
        req.remove_target = c[2]
        req.params = replace(req.params, prompt=c[2])
        bridge.REMOVE_TARGET_PROMPT = (written(model, cid) or "Remove {target} completely.") + E_END
    elif variant != "A":
        s = SENTENCES[variant]
        bridge.REMOVE_TARGET_PROMPT = getattr(bridge, s) if s.startswith("REMOVE_") else globals()[s]
    try:
        Bridge(pc, comfy, tmp).run(req)
    finally:
        bridge.REMOVE_TARGET_PROMPT = keep
    return pc.composite(pc.doc)


def sent_prompt(graph: dict) -> str:
    """The prompt text in the graph (the node titled pc:prompt)."""
    for node in graph.values():
        if str(node.get("_meta", {}).get("title", "")).startswith("pc:"):       # pc:prompt; Fibo: its encoder is pc:size
            for k in ("text", "prompt"):
                v = node.get("inputs", {}).get(k)
                if isinstance(v, str) and len(v) > 20:
                    return v
    return ""


def cmd_dry(a):
    folder = Path(a.images)
    app = base.make_app(a.url or cfgmod.load()["comfyui"]["url"])
    todo = jobs(a)
    for m, cid, v, s in todo:
        if s != SEEDS[0]:
            continue
        rec = ler.Recorder()
        name = expected_name(m, cid, v, a.question) or case(cid)[2]
        run_case(rec, app, folder, m, cid, v, s, name)
        p = sent_prompt(rec.graphs[0]) if rec.graphs else "(no graph)"
        print(f"{m} {cid} {v}: {p if a.full else p[:110]}")
    print(f"\n{len(todo)} pictures in the run" + ("" if (BASE / "names.json").exists() else
          "  (no names.json yet: the dry run used the hand names)"))
    app.root.destroy()


def cmd_run(a):
    folder = Path(a.images)
    url = connect(a)
    if not (BASE / "names.json").exists():
        sys.exit("Stage 1 first: python tests\\live_remove_name.py names --images <folder>")
    out = Path(a.into) if a.into else BASE / time.strftime("%Y%m%d-%H%M%S")
    (out / "bilder").mkdir(parents=True, exist_ok=True)
    rfile = out / "records.json"
    records = json.load(open(rfile, encoding="utf-8")) if rfile.exists() else []
    comfy = ler.Timed(url)
    inv = inventory.fetch(comfy, cfgmod.model_map())
    app = base.make_app(url)
    if a.reuse:                     # (16.11.) the pictures of a variant an earlier round already made (C for the C/D round)
        old_dir = Path(a.reuse)
        for r in json.load(open(old_dir / "records.json", encoding="utf-8")):
            if (r["variant"] in variants(a) and r.get("token") and r["model"] in model_list(a) and r.get("question") == a.question
                    and r.get("name", "") == expected_name(r["model"], r["case"], r["variant"], a.question)
                    and (r["variant"] != "E" or r.get("written") == written(r["model"], r["case"]))
                    and not any(x.get("token") == r["token"] for x in records)):     # a name cleaned differently now: made anew
                img = old_dir / "bilder" / f"{r['token']}.png"
                if img.exists():
                    (out / "bilder" / img.name).write_bytes(img.read_bytes())
                    records.append(dict(r, cap=cap(a, r["variant"]), reused=str(old_dir.name)))
        json.dump(records, open(rfile, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"Reused from {old_dir.name}: {sum(1 for r in records if r.get('reused'))} pictures", flush=True)
    todo = jobs(a)
    print(f"ComfyUI: {url}\nRound: {out}\n{len(todo)} pictures, question {a.question}, pair {'/'.join(PAIRS[a.pair])}\n", flush=True)
    t_start, skipped = time.time(), set()
    for m, cid, v, s in todo:
        if any(r["model"] == m and r["case"] == cid and r["variant"] == v and r["seed"] == s for r in records):
            continue
        if inv.tab_status(m).state != "ready":
            if m not in skipped:
                print(f"SKIPPED {m}: its files are not all there", flush=True)
                skipped.add(m)
            continue
        name = expected_name(m, cid, v, a.question)
        # the fields the rating window of the Expand round reads: a pair is (model, photo, kind), A = cap 1.0, C = 2.0
        rec = {"model": m, "case": cid, "variant": v, "seed": s, "name": name, "question": a.question,
               "photo": f"{cid}-s{s}", "kind": "remove", "cap": cap(a, v)}
        if v == "E":
            rec["written"] = written(m, cid)
        if v != "A" and not name:
            rec["error"] = "no name from stage 1"
        elif v == "E" and not rec["written"]:
            rec["error"] = "no instruction from the writer (command write)"
        else:
            t0 = time.time()
            try:
                img = run_case(comfy, app, folder, m, cid, v, s, name)
                token = os.urandom(4).hex()
                img.convert("RGB").save(out / "bilder" / f"{token}.png")
                rec.update(token=token, seconds=round(time.time() - t0, 1), gen_seconds=round(comfy.t_done - comfy.t_queued, 1))
            except Exception as ex:                    # one broken case must not stop the round
                rec.update(error=f"{type(ex).__name__}: {ex}"[:300], seconds=round(time.time() - t0, 1))
        records.append(rec)
        json.dump(records, open(rfile, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"{m} {cid} {v} seed {s}: " + (f"{rec['gen_seconds']} s" if "gen_seconds" in rec else f"Fehler: {rec['error']}")
              + (f"  [{name}]" if name else ""), flush=True)
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min -> {out}\nNext: python tests\\live_remove_name.py rate", flush=True)
    app.root.destroy()


def latest(folder) -> Path:
    if folder:
        return Path(folder)
    runs = sorted(p for p in BASE.iterdir() if (p / "records.json").exists()) if BASE.exists() else []
    if not runs:
        sys.exit(f"No round in {BASE}")
    return runs[-1]


def task_picture(out: Path, cid: str, folder: Path | None, fresh: bool = False) -> Path | None:
    """The small input picture of the rating window: the photo with the selection outlined in red (made once; fresh=True
    makes it again, "pack" does so)."""
    f = out / "aufgaben" / f"{cid}.png"
    if (f.exists() and not fresh) or folder is None:
        return f if f.exists() else None
    f.parent.mkdir(exist_ok=True)
    c = case(cid)
    im = outlined(photo(folder, c[1]), c, 11)      # at full size: the user's masks have the photo's size
    im.thumbnail((960, 960))
    im.save(f)
    return f


PACK_QUALITY = 93      # JPEG quality of the pictures in the zip (2 MP: about 0.6 MB each instead of 3 MB as PNG)


def cmd_pack(a):
    """A round as one zip for the other PC (user 15.11.: rate on PC B; it goes there as a release asset of the private repo):
    the pictures as JPEG, the task pictures made here with the user's own selections (PC B has no masken/), records.json,
    names.json, names.html and the masks."""
    import zipfile
    out = latest(a.round)
    folder = Path(a.images)
    records = json.load(open(out / "records.json", encoding="utf-8"))
    for cid in dict.fromkeys(r["case"] for r in records):
        task_picture(out, cid, folder, fresh=True)
    zpath = Path(a.zip) if a.zip else BASE / f"remove-name-{out.name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for r in records:
            if r.get("token"):
                with Image.open(out / "bilder" / f"{r['token']}.png") as im:
                    buf = __import__("io").BytesIO()
                    im.convert("RGB").save(buf, "JPEG", quality=PACK_QUALITY)
                z.writestr(f"{out.name}/bilder/{r['token']}.jpg", buf.getvalue())
        for p in sorted((out / "aufgaben").glob("*.png")):
            z.write(p, f"{out.name}/aufgaben/{p.name}")
        for name in ("records.json", "bewertung.json"):
            if (out / name).exists():
                z.write(out / name, f"{out.name}/{name}")
        for p in [BASE / "names.json", BASE / "names.html", *sorted((BASE / "masken").glob("*.png")), *sorted((BASE / "namen").glob("*.png"))]:
            if p.exists():
                z.write(p, str(p.relative_to(BASE)).replace("\\", "/"))
    n = sum(1 for r in records if r.get("token"))
    print(f"{zpath}  ({zpath.stat().st_size / 1e6:.1f} MB, {n} pictures)")


def cmd_unpack(a):
    """The zip of "pack" into <PCCOMFY_HOME>/remove-name/ on this PC; the JPEGs become the PNG names the rating reads."""
    import zipfile
    BASE.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.zip) as z:
        for info in z.infolist():
            target = (BASE / info.filename).resolve()
            if BASE.resolve() not in target.parents:          # no path out of the folder
                sys.exit(f"Refused: {info.filename}")
            if info.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = z.read(info)
            if target.suffix == ".jpg" and target.parent.name == "bilder":
                with Image.open(__import__("io").BytesIO(data)) as im:
                    im.convert("RGB").save(target.with_suffix(".png"))
            elif not target.exists() or target.name != "bewertung.json":     # a rating begun here is kept
                target.write_bytes(data)
    rounds = sorted(p for p in BASE.iterdir() if (p / "records.json").exists())
    print(f"Unpacked into {BASE}\nNext: python tests\\live_remove_name.py rate {rounds[-1] if rounds else ''}")


def cmd_rate(a):
    out = latest(a.round)
    folder = Path(a.images) if a.images else None

    def describe(item):
        _p, model, ph, _kind = item["id"].split("|")
        cid = ph.split("-")[0]
        return (f"{models.BY_KEY[model].label} · Remove · Fall {ph}\nEntfernen: {case(cid)[2]}\nWorauf achten: Ist das Objekt "
                "in der Auswahl (rot umrandet im Eingabebild) ganz weg, ohne Reste? Nichts Neues hineingemalt? Hintergrund "
                "glaubhaft, keine Kante, keine rote Linie, Umgebung gleich?\nFrage: Welches Bild ist insgesamt besser?  "
                "(Klick auf das kleine Bild: Eingabe in voller Größe)"), task_picture(out, cid, folder)

    ler.cmd_rate(argparse.Namespace(mode="pairs", round=str(out), title="Remove mit Namen", describe=describe))


def cmd_summary(a):
    out = latest(a.round)
    records = json.load(open(out / "records.json", encoding="utf-8"))
    bfile = out / "bewertung.json"
    rating = json.loads(bfile.read_text(encoding="utf-8")) if bfile.exists() else {}
    by_tok = {r["token"]: r for r in records if r.get("token")}
    first = next((r["variant"] for r in records if r.get("cap") == 1.0), "A")       # the pair of the round: A/C or C/D
    second = next((r["variant"] for r in records if r.get("cap") == 2.0), "C")
    lines = [f"# Remove mit Namen: Ergebnis ({out.name})", "",
             f"| Modell | Paare | {second} besser | {first} besser | gleich gut | beide schlecht | {first} schlecht | {second} schlecht |",
             "|---|---|---|---|---|---|---|---|"]
    for m in dict.fromkeys(r["model"] for r in records):
        n = c_win = a_win = eq = none = a_bad = c_bad = 0
        for it_id, ent in rating.items():
            if it_id.split("|")[1] != m:
                continue
            n += 1
            var = [by_tok[t]["variant"] if t in by_tok else "?" for t in ent["tokens"]]
            best = ent.get("best")
            if best == "equal":
                eq += 1
            elif best == "none":
                none += 1
            elif isinstance(best, int):
                c_win += var[best] == second
                a_win += var[best] == first
            for k in ent.get("bad", []):
                a_bad += var[k] == first
                c_bad += var[k] == second
        lines.append(f"| {models.BY_KEY[m].label} | {n} | {c_win} | {a_win} | {eq} | {none} | {a_bad} | {c_bad} |")
    names = {(r["model"], r["case"]): r["name"] for r in records if r.get("name")}
    lines += ["", "Namen (Stufe 1, Frage " + str(next((r["question"] for r in records), "?")) + "):", ""]
    lines += [f"- {models.BY_KEY[m].label} {cid}: {n}" for (m, cid), n in sorted(names.items())]
    times = {}
    for r in records:
        if "gen_seconds" in r:
            times.setdefault(r["model"], []).append(r["gen_seconds"])
    lines += ["", "Zeit je Bild (Mittel): " + ", ".join(f"{models.BY_KEY[m].label} {sum(t) / len(t):.1f} s" for m, t in times.items())]
    errs = [r for r in records if r.get("error")]
    if errs:
        lines += ["", f"Fehler: {len(errs)}"] + [f"- {r['model']} {r['case']} {r['variant']} {r['seed']}: {r['error']}" for r in errs]
    text = "\n".join(lines) + "\n"
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    global CASES
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--set", choices=("n", "e"), default="n", help="n: the cases N1 ... N8 (15.11.); e: ECASES (16.11.)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("grab")
    sub.add_parser("grab-e").add_argument("--images", required=True)
    s = sub.add_parser("pack")
    s.add_argument("round", nargs="?")
    s.add_argument("--images", required=True)
    s.add_argument("--zip")
    sub.add_parser("unpack").add_argument("zip")
    sub.add_parser("open").add_argument("--images", required=True)
    for name in ("preview", "names", "write", "dry", "run"):
        s = sub.add_parser(name)
        s.add_argument("--images", required=True)
        s.add_argument("--url")
        s.add_argument("--qwen", action="store_true")
        if name in ("dry", "run"):
            s.add_argument("--question", choices=tuple(QUESTIONS), default="a")
            s.add_argument("--c2", action="store_true")
            s.add_argument("--pair", choices=tuple(PAIRS), default="AC")
        if name == "dry":
            s.add_argument("--full", action="store_true", help="the whole prompt, not the first 110 characters")
        if name == "run":
            s.add_argument("--into")
            s.add_argument("--reuse", help="an earlier round whose pictures of the same variants are taken over")
    for name in ("rate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("round", nargs="?")
        s.add_argument("--images")
    a = p.parse_args()
    if a.set == "e":
        CASES = ECASES
    {"open": cmd_open, "grab": cmd_grab, "grab-e": cmd_grab_e, "write": cmd_write, "pack": cmd_pack, "unpack": cmd_unpack, "preview": cmd_preview, "names": cmd_names, "dry": cmd_dry, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
