"""Manual check (not part of run_all.py): which text model writes the Sketch prompt (user 10.11.). Today Flux 3, Flux 2 and
Qwen Image 2.1 expand the prompt with BFL's upsampler (qwen3.5 9B, 6.7 GB, gated). Tested against it, through the real
plugin path (the bridge with the PhotoCraft simulator of test_reference_mode and the real ComfyUI, the built Sketch
workflows; only the CLIPLoader of the upsampler, node 401, gets another file):

- Flux 3: its own encoder qwen3vl_4b (no extra download);
- Flux 2: qwen3vl_4b (its own encoder qwen_3_8b reads only text, it cannot see the scribble);
- Qwen Image 2.1: its own encoder qwen3vl_8b, and qwen3vl_4b (the 8 GB candidate).

Pictures from older rounds on this PC: the seven sketches of round 3 (Photo) and the six photos with red scribbles of
round 2 A (Scribble on photo, crop path of the build), the subject as there; seed 1234; BFL runs again in the same path,
so every pair differs only in the writer. Fibo has no writer in Sketch and is left out.

    python tests\\live_sketch_writers.py plan                  (what would run; no ComfyUI)
    python tests\\live_sketch_writers.py run [--dry] [--into <folder>] [--only flux3 ...] [--pictures N] [--free]
                                               [--sketch-template photo|illustration] [--part a b c d e]
                                                              (resumes in --into; key.json after every picture)

Parts of the round on PC A (docs/archiv/sketch-schreiber-plan.md, step 2; --part replaces --only and --sketch-template):
a Qwen 4B (the rest), b Qwen 4B + instruction v2, c Flux 2 4B + instruction v2 with Illustration, d Flux 2 BFL with
Illustration, e Flux 2 4B + instruction v2 with Photo (c to e on the seven sketches only).

Qwen 9B w4a8 against the upsampler (user 16.11., docs/archiv/tests/sketch-schreiber-w4a8-testplan.md): ``--part f g h``,
f Qwen BFL upsampler, g Qwen 9B w4a8 (only the file of node 401 swapped, loader type and system prompt as built),
h Qwen 9B w4a8 + instruction v2; Photo for the sketches, Scribble on photo for the photos (3 x 13 = 39 runs).

Round 2 of w4a8 (user 16.11. evening, fewer model dependencies): ``--part i j k`` with three new system prompts, all at
temperature 0.3: i the upsampler's way of working as rules (v3), j v3 with two example answers, k v3 with thinking on.
Rated against the upsampler of round 1, which is not run again:

    python tests\\live_sketch_writers.py compare --into <new folder> --ref data\\sketch-test\\writers-w4a8-20261116

Round 3 (new pictures, 16.11. evening): sketches in data\\sketch-test\\runde3\\sketch, photos with red scribbles drawn in
PhotoCraft and saved by ``grab`` (every open document) into runde3\\photo, subjects in runde3\\motive.json; then
``plan --set runde3 --part f i l`` and ``run --set runde3 --part f i l --free --into <folder>`` (upsampler, V1, V3 with
max_length 8192), ``compare --into <folder> --ref <folder>`` (the upsampler of the same folder).

Output: data\\sketch-test\\writers-<time>\\ (eingabe\\, bilder\\, key.json with the written prompt and the time of each run).
Rate with ``python tests\\live_sketch.py rate <folder>`` (blind, good / bad with faults).
"""
import argparse
import json
import os
import shutil
import random
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# a data folder of its own (a copy of settings.json for the address and the linked files): the window built here must not
# write the plugin's state.json (last model, pages) while the user works with the plugin
_HOME = Path(tempfile.mkdtemp(prefix="pccomfy-writers-"))
if (DATA / "settings.json").exists():
    shutil.copyfile(DATA / "settings.json", _HOME / "settings.json")
os.environ["PCCOMFY_HOME"] = str(_HOME)
os.environ["PCCOMFY_NO_TIPS"] = "1"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

import live_sketch  # noqa: E402
import test_reference_mode as tr  # noqa: E402
from pccomfy import bridge, config as cfgmod, inventory, models  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

BASE = DATA / "sketch-test"
SEED = 1234
UPS = "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors"
VL4, VL8 = "qwen3vl_4b_int8_convrot.safetensors", "qwen3vl_8b_int8_convrot.safetensors"
W4A8 = "qwen3.5_9b_w4a8_gptq.safetensors"   # Qwen's own text model (Enhance my Prompt with LLM, Describe), 16.11.
# model -> the writers to compare; the first is today's
IN4 = "qwen3vl 4B instruction"
IN4V2 = "qwen3vl 4B instruction v2"      # the neutral sketch part (user 10.11.: Illustration must not become a photo)
Q9 = "qwen3.5 9B w4a8"
Q9IN = "qwen3.5 9B w4a8 instruction"
WRITERS = {"flux3": ("BFL upsampler", "qwen3vl 4B", IN4),
           "flux2": ("BFL upsampler", "qwen3vl 4B", IN4),
           "qwen": ("BFL upsampler", "qwen3vl 8B", "qwen3vl 4B", IN4)}
WRITER_FILE = {"BFL upsampler": UPS, "qwen3vl 4B": VL4, "qwen3vl 8B": VL8, IN4: VL4, IN4V2: VL4, Q9: W4A8, Q9IN: W4A8}
# writers of the same family as the upsampler (qwen3.5 9B): only the file changes, the loader keeps the workflow's type
SAME_TYPE = {Q9, Q9IN}
# User 10.11. evening: does 4B catch up with another system prompt? The workflows' prompt (node 402) asks for a caption of
# the whole finished picture; BFL's upsampler writes an edit instruction anyway, 4B follows the prompt word for word.
# This one asks 4B for the instruction itself.
_INSTR_HEAD = (
    "You write the edit instruction for an image editing model. You get a picture and a short request. Write ONE clear "
    "English instruction that starts with a verb. If the picture carries rough coloured scribble lines: say where they "
    "are (which part of the picture, what they lie on) and what replaces them exactly there; name the new object with "
    "its look, material, colour, size and pose, matching the light, perspective and style of the photo; the scribble "
    "lines must be gone and everything else stays unchanged. ")
_INSTR_TAIL = (" Output only the instruction as one block of prose, 60 to 150 words, with no lists, Markdown or "
               "explanations.")
# v1: rated on PC B (10.11.), the sketch part fixed to a photograph; kept for those pictures
INSTRUCTION_SYSTEM_V1 = _INSTR_HEAD + (
    "If the picture is a sketch or drawing: say to turn it into a realistic photograph and name each element of the "
    "drawing with its real material, colour and place, keeping the composition, shapes and proportions exactly, with no "
    "drawing lines left.") + _INSTR_TAIL
# v2 (user 10.11.): the sketch part neutral, the look comes from the request; the scribble part word for word as v1.
# Built into Flux 2's Sketch workflow since 10.11.: it lives in pccomfy/models.py now (one place)
INSTRUCTION_SYSTEM = models.SKETCH_WRITER_SYSTEM
# Round 2 of w4a8 (user 16.11. evening: fewer model dependencies, can a better prompt close the gap to the upsampler?).
# The upsampler goes through the picture part by part (place, shape, size, material), invents nothing and writes no
# filler; w4a8 with v2 invented details (an oak, claws, brand names) and wrote generic sentences. V1 asks for the
# upsampler's way of working, V2 adds two example answers, V3 is V1 with thinking on; all three at temperature 0.3.
Q9V1 = "qwen3.5 9B w4a8 v3"
Q9V2 = "qwen3.5 9B w4a8 v3 examples"
Q9V3 = "qwen3.5 9B w4a8 v3 thinking"
_V3_HEAD = models.QWEN_SKETCH_WRITER_HEAD     # built into Qwen's Sketch workflow since 16.11.: one place
_V3_TAIL = models.QWEN_SKETCH_WRITER_TAIL
_V3_EXAMPLES = (
    " Two examples of the form (other pictures; never copy their content). "
    "Example for a pencil sketch of a lighthouse on a cliff, request \"a realistic photograph\": Create a realistic "
    "photograph of the lighthouse on the cliff shown in the drawing, preserving the exact composition, viewpoint, shapes "
    "and proportions. On the right third, keep the tall slender lighthouse tower with its exact silhouette, rendered as "
    "white-painted masonry with one broad red band below the gallery, a black iron railing and a glass lantern room "
    "with a brass dome. At its foot on the right, keep the small keeper's house with a pitched slate roof and two square "
    "windows. In the centre and on the left, render the drawn cliff as rough grey granite with tufts of yellow-green "
    "grass along its edge, dropping steeply into the sea at the lower left, where the drawn wave lines become dark "
    "blue-green water breaking into white foam on the rocks. In the background, keep the low horizon line and render "
    "the empty upper half as a pale blue sky with thin high clouds. Soft afternoon light from the left, real materials, "
    "full colour, no drawing lines left. "
    "Example for a park photo with a red scribble on the lawn, request \"a bench\": Replace the red scribble on the lawn "
    "in the lower centre of the photo with one wooden park bench, fitted to the outline of the scribble: a long seat of "
    "three weathered brown slats, a backrest of two slats, and dark green cast-iron legs and armrests, turned slightly "
    "towards the viewer as the long side of the scribble runs. Its size matches the people on the path behind it, and "
    "it casts a soft shadow onto the grass to the right like the trees nearby. Match the warm evening light, the shallow "
    "perspective, the muted greens and the fine grain of the photo, remove every scribble line, and keep everything "
    "else in the picture unchanged.")
SYSTEM_V3 = _V3_HEAD + _V3_TAIL
SYSTEM_V3_EXAMPLES = _V3_HEAD + _V3_EXAMPLES + _V3_TAIL
SYSTEM_OF = {IN4: INSTRUCTION_SYSTEM_V1, IN4V2: INSTRUCTION_SYSTEM, Q9IN: INSTRUCTION_SYSTEM,
             Q9V1: SYSTEM_V3, Q9V2: SYSTEM_V3_EXAMPLES, Q9V3: SYSTEM_V3}
# writer -> inputs of the TextGenerate node (403) set for it
# Round 3 (16.11. evening): V3 wrote an empty prompt twice (the thinking used up max_length 4096); repaired with 8192
Q9V3B = "qwen3.5 9B w4a8 v3 thinking 8k"
GEN_OF = {Q9V1: {"sampling_mode.temperature": 0.3},
          Q9V2: {"sampling_mode.temperature": 0.3},
          Q9V3: {"sampling_mode.temperature": 0.3, "thinking": True},
          Q9V3B: {"sampling_mode.temperature": 0.3, "thinking": True, "max_length": 8192}}
SYSTEM_OF[Q9V3B] = SYSTEM_V3
# the built combination (16.11. evening): the workflow file as it is (w4a8, V1, 0.3, thinking only in Sketch to image,
# empty-prompt fallback); writer_workflow leaves it untouched
Q9BUILT = "qwen built-in"
WRITER_FILE[Q9BUILT] = W4A8
WRITER_FILE.update({Q9V1: W4A8, Q9V2: W4A8, Q9V3: W4A8, Q9V3B: W4A8})
SAME_TYPE |= {Q9V1, Q9V2, Q9V3, Q9V3B}

# the sketch templates by name (photos with scribbles always get "Scribble on photo")
TEMPLATES = {"photo": "Photo", "illustration": "Illustration"}
TEMPLATE_TEXT = {"Photo": models.SKETCH_PHOTO, "Illustration": models.SKETCH_ILLUSTRATION,
                 "Scribble on photo": models.SKETCH_SCRIBBLE}
# docs/archiv/sketch-schreiber-plan.md, step 2: part -> (model, writer, sketch template, kinds of picture)
PARTS = {"a": ("qwen", "qwen3vl 4B", "Photo", ("sketch", "photo")),
         "b": ("qwen", IN4V2, "Photo", ("sketch", "photo")),
         "c": ("flux2", IN4V2, "Illustration", ("sketch",)),
         "d": ("flux2", "BFL upsampler", "Illustration", ("sketch",)),
         "e": ("flux2", IN4V2, "Photo", ("sketch",)),
         # w4a8 against the upsampler at Qwen (16.11.), all 13 pictures each
         "f": ("qwen", "BFL upsampler", "Photo", ("sketch", "photo")),
         "g": ("qwen", Q9, "Photo", ("sketch", "photo")),
         "h": ("qwen", Q9IN, "Photo", ("sketch", "photo")),
         # round 2 of w4a8 (16.11. evening): three new prompts, rated against f of the first round (compare --ref)
         "i": ("qwen", Q9V1, "Photo", ("sketch", "photo")),
         "j": ("qwen", Q9V2, "Photo", ("sketch", "photo")),
         "k": ("qwen", Q9V3, "Photo", ("sketch", "photo")),
         # round 3 (new pictures, --set runde3): upsampler, V1 and the repaired V3
         "l": ("qwen", Q9V3B, "Photo", ("sketch", "photo")),
         # GPU probe of the built combination (16.11. evening): Qwen's Sketch workflow exactly as the plugin sends it
         "m": ("qwen", Q9BUILT, "Photo", ("sketch", "photo"))}

# --set runde3: the user's own pictures in data\sketch-test\runde3\ (sketch\ and photo\, the photos with red scribbles
# grabbed from PhotoCraft by `grab`); the subject per file in motive.json ({"cat.jpg": "a cat", ...}), else the file name
SETS = ("alt", "runde3")
SET3 = BASE / "runde3"
_EXT = (".png", ".jpg", ".jpeg", ".webp")


def sources_set3():
    mf = SET3 / "motive.json"
    motive = json.load(open(mf, encoding="utf-8")) if mf.exists() else {}
    items = []
    for kind in ("sketch", "photo"):
        for p in sorted((SET3 / kind).glob("*"), key=lambda p: p.name.lower()):
            if p.suffix.lower() in _EXT:
                items.append({"src": p, "file": p.name, "desc": motive.get(p.name, p.stem).strip(), "kind": kind,
                              "round": "runde3", "named": p.name in motive})
    if not items:
        sys.exit(f"No pictures in {SET3}\\sketch or {SET3}\\photo")
    for k, s in enumerate(items, 1):
        s["input"] = f"{k}.png"
    return items


def sources(which: str = "alt"):
    """The pictures: round 3's sketches and round 2 A's scribbled photos, with the subject typed there."""
    if which == "runde3":
        return sources_set3()
    items = []
    for pattern, kind in (("round3-2*", "sketch"), ("round2-A-2*", "photo")):
        runs = sorted(p for p in BASE.glob(pattern) if (p / "key.json").exists())
        if not runs:
            sys.exit(f"No folder {pattern} in {BASE}")
        key = json.load(open(runs[-1] / "key.json", encoding="utf-8"))["items"]
        seen = set()
        for it in key.values():
            if it["kind"] != kind or it["input"] in seen:
                continue
            seen.add(it["input"])
            src = next(runs[-1].joinpath("eingabe").glob(Path(it["input"]).stem + ".*"))     # round 2 A keeps .jpg
            items.append({"src": src, "file": it["file"], "desc": it["desc"].strip(),
                          "kind": kind, "round": runs[-1].name})
    for k, s in enumerate(items, 1):
        s["input"] = f"{k}.png"
    return items


def template_of(s: dict, sketch_template: str) -> str:
    """The template the picture runs with: a photo with scribbles always "Scribble on photo", a sketch the chosen one."""
    return "Scribble on photo" if s["kind"] == "photo" else sketch_template


def text_of(s: dict, template: str) -> str:
    return TEMPLATE_TEXT[template].replace(models.SKETCH_MARK, s["desc"])


def job_list(a) -> list:
    """(model, writer, sketch template, kinds) in run order: the parts, or every writer of --only with one template."""
    if a.part:
        return [PARTS[p] for p in a.part]
    return [(mk, w, TEMPLATES[a.sketch_template], ("sketch", "photo")) for mk in a.only for w in WRITERS[mk]]


def writer_workflow(mk: str, writer: str, folder: Path) -> Path:
    """The model's Sketch workflow with another file in the upsampler's loader (type stable_diffusion, as the other
    qwen3vl writers of the plugin, e.g. fibo2-edit.json)."""
    name = models.BY_KEY[mk].modes["sketch"].workflow
    g = json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8"))
    if mk == "qwen" and writer != Q9BUILT:
        # Qwen's workflow writes with w4a8 since 16.11. evening: the rounds start from the graph as it was (upsampler,
        # its prompt, temperature 0.7, no thinking, no empty-prompt fallback) and change only what the writer names
        g["401"]["inputs"].update(clip_name=UPS, type="flux3")
        g["402"]["inputs"]["value"] = live_sketch.EDIT_UPSAMPLER_SYSTEM
        g["403"]["inputs"]["sampling_mode.temperature"] = 0.7
        for k in ("pc_empty_fallback", "pc_sketch_inputs"):
            g["403"]["_meta"].pop(k, None)
    if writer not in ("BFL upsampler", Q9BUILT):
        g["401"]["inputs"]["clip_name"] = WRITER_FILE[writer]
        if writer not in SAME_TYPE:
            g["401"]["inputs"]["type"] = "stable_diffusion"
    if writer in SYSTEM_OF:
        g["402"]["inputs"]["value"] = SYSTEM_OF[writer]
    for k, v in GEN_OF.get(writer, {}).items():
        assert k in g["403"]["inputs"], (name, k)      # a renamed input must not be skipped silently
        g["403"]["inputs"][k] = v
    out = folder / f"{Path(name).stem}--{writer.replace(' ', '_')}.json"
    out.write_text(json.dumps(g, indent=1), encoding="utf-8")
    return out


def cmd_plan(a):
    items = sources(a.set)
    jobs = job_list(a)
    for s in items:
        note = "" if s.get("named", True) else "   (no subject in motive.json: file name)"
        if s["kind"] == "photo":
            from pccomfy import scribble
            if scribble.find(Image.open(s["src"]).convert("RGB")) is None:
                note += "   NO SCRIBBLE FOUND"
        print(f"{s['input']:>6} {s['kind']:<6} {s['file']:<45} \"{s['desc']}\"{note}")
    runs = sum(1 for _, _, _, kinds in jobs for s in items if s["kind"] in kinds)
    print(f"\n{len(items)} pictures, {len(jobs)} model-writer-template sets = {runs} runs: "
          + ", ".join(f"{mk} {w} ({tpl})" for mk, w, tpl, _ in jobs))


def window_request(app, mk: str, s: dict, template: str):
    """The Request the window sends for Sketch with this model's start settings (saved pages ignored), the template of the
    picture's kind and its text in the field, seed 1234."""
    from dataclasses import replace
    scribble = template == "Scribble on photo"
    app.v_model.set(mk)
    # Scribble on photo is a tab (window mode) of its own since plan B (10.11.); its chip without reference is the first
    app.v_mode.set(models.SCRIBBLE_MODE if scribble else "sketch")
    app._factory = True
    try:
        app._on_model()
        app._on_mode()
    finally:
        app._factory = False
    app._sketch_pick(models.SCRIBBLE_PROMPTS[0][0] if scribble else template)
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", text_of(s, template))
    req = app._request()
    assert req.enhance and req.scribble == (s["kind"] == "photo"), (mk, s["input"], req.enhance, req.scribble)
    req.params = replace(req.params, seed=SEED)
    return req


def run_one(comfy, req, pic: Image.Image, exch: Path):
    """One run as the plugin makes it: a document with the picture as its only layer, the bridge, the composite."""
    tr.W, tr.H = pic.size                 # the simulator's document size
    pc = tr.FakePC(exch)
    pc.docs.append(tr.Doc("photo.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True, "name": "Background"}]))
    b = bridge.Bridge(pc, comfy, exch)
    res = b.run(req)
    return tr.FakePC.composite(pc.docs[0]).convert("RGB"), res


def free_memory(comfy) -> None:
    """ComfyUI's /free: unload every model and free RAM and VRAM before the next run (a failure only gets a line)."""
    try:
        comfy._json("/free", {"unload_models": True, "free_memory": True})
    except Exception as e:
        print(f"   (free memory failed: {type(e).__name__}: {e})", flush=True)


def cmd_grab(a):
    """Every open PhotoCraft document (the user's photos with red scribbles) as it is visible, through the plugin's own
    export (Bridge._export on a throw-away duplicate), into data\\sketch-test\\runde3\\photo\\<document name>.png. A file
    that is there already is kept; no scribble found gets a line."""
    from pccomfy import scribble
    from pccomfy.photocraft import PhotoCraft
    pcc = cfgmod.load()["photocraft"]
    pc = PhotoCraft(pcc["host"], int(pcc["port"]), token_file=pcc["token_file"], headless=bool(pcc["headless"])).connect()
    br = bridge.Bridge(pc, None, Path(pcc["exchange_dir"]))
    out = SET3 / "photo"
    out.mkdir(parents=True, exist_ok=True)
    for d in pc.session().get("documents", []):
        name = str(d.get("name", ""))
        if not name or name.startswith("pccomfy-"):
            continue
        dst = out / f"{Path(name).stem}.png"
        if dst.exists():
            print(f"{name}: kept ({dst.name} is there)", flush=True)
            continue
        idx = d.get("index")
        pc.activate(idx)
        try:
            src, _ = br._export(idx, f"grab-{len(list(out.iterdir()))}", need_mask=False)
        finally:
            br._cleanup()
        src.convert("RGB").save(dst)
        found = scribble.find(src.convert("RGB"))
        print(f"{name}: saved {dst.name} {src.size[0]}x{src.size[1]}" + ("" if found else "   NO SCRIBBLE FOUND"), flush=True)
    print(f"\nPhotos: {out}\nSubjects: {SET3 / 'motive.json'}", flush=True)


def cmd_run(a):
    items = sources(a.set)
    if a.files:
        items = [s for s in items if s["file"] in a.files]
        missing = set(a.files) - {s["file"] for s in items}
        if missing:
            sys.exit("Not in the set: " + ", ".join(sorted(missing)))
    items = items[: a.pictures or None]
    out = Path(a.into) if a.into else BASE / f"writers-{time.strftime('%Y%m%d-%H%M%S')}"
    for sub in ("bilder", "eingabe", "wf", "xch"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    pics = {}
    for s in items:
        im = Image.open(s["src"]).convert("RGB")
        im.save(out / "eingabe" / s["input"])
        pics[s["input"]] = im
    kf = out / "key.json"
    old = json.load(open(kf, encoding="utf-8")) if kf.exists() else {}
    key = old.get("items", {})
    rated_order = list(old.get("order", []))       # a resumed round keeps the order the user already rated in

    def write_key():
        new = [f for f in key if f not in rated_order]
        random.Random(1011).shuffle(new)            # blind: models and writers mixed; new pictures after the old ones
        extra = {k: v for k, v in old.items() if k not in ("items", "order", "writers", "seed", "prompts", "parts",
                                                           "system_prompt_instruction", "system_prompt_instruction_v2",
                                                           "system_prompt_v3", "system_prompt_v3_examples", "generate")}
        json.dump({"items": key, "order": rated_order + new, "writers": WRITERS, "seed": SEED, "prompts": TEMPLATE_TEXT,
                   "parts": {p: list(v) for p, v in PARTS.items()},
                   "system_prompt_instruction": INSTRUCTION_SYSTEM_V1, "system_prompt_instruction_v2": INSTRUCTION_SYSTEM,
                   "system_prompt_v3": SYSTEM_V3, "system_prompt_v3_examples": SYSTEM_V3_EXAMPLES, "generate": GEN_OF,
                   **extra},       # keeps "part": "R5" set for rating
            open(kf, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    url = "http://127.0.0.1:1" if a.dry else cfgmod.load()["comfyui"]["url"]
    if not a.dry:
        host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
        try:
            socket.create_connection((host, port), timeout=2).close()
        except OSError:
            sys.exit(f"ComfyUI is not running ({url}). Start it first.")
    comfy = ComfyUI(url)
    if not a.dry:
        inv = inventory.fetch(comfy, cfgmod.model_map())
        have = set(inv.lists.get("clip", [])) if hasattr(inv, "lists") else None
        for f in sorted({WRITER_FILE[w] for _, w, _, _ in job_list(a)}):
            if have is not None and not any(Path(h).name == f for h in have):
                print(f"WARNING: {f} not in ComfyUI's text encoder list", flush=True)
    app = live_sketch.make_app(url)
    jobs = job_list(a)
    total = sum(1 for _, _, _, kinds in jobs for s in items if s["kind"] in kinds)
    n, t_start = 0, time.time()
    for mk, writer, sketch_tpl, kinds in jobs:
        wf = writer_workflow(mk, writer, out / "wf")
        for s in items:
            if s["kind"] not in kinds:
                continue
            n += 1
            tpl = template_of(s, sketch_tpl)
            if any(r["model_key"] == mk and r["writer"] == writer and r["input"] == s["input"]
                   and r.get("prompt") == tpl for r in key.values()):
                continue
            req = window_request(app, mk, s, tpl)
            req.workflow = str(wf)
            if a.dry:
                print(f"{n}/{total} {mk} {writer} {s['input']} {s['kind']} {tpl}: {Path(wf).name}", flush=True)
                continue
            t0 = time.time()
            try:
                im, res = run_one(comfy, req, pics[s["input"]], out / "xch")
            except Exception as e:            # one failing writer (e.g. a loader type) must not stop the round
                print(f"{n}/{total} {mk} {writer} {tpl} {s['input']}: FAILED {type(e).__name__}: {e}", flush=True)
                continue
            fid = f"{len(key) + 1:04d}"
            im.save(out / "bilder" / f"{fid}.png")
            key[fid] = {"model": models.BY_KEY[mk].label, "model_key": mk, "writer": writer, "variant": writer,
                        "file": s["file"], "input": s["input"], "kind": s["kind"], "desc": s["desc"],
                        "prompt": tpl, "seed": SEED, "text": text_of(s, tpl), "caption": res.get("vgl", ""), "secs": round(time.time() - t0, 1),
                        "scribble": res.get("scribble", ""), "region": res.get("region"), "size": res.get("size")}
            write_key()
            print(f"{n}/{total} {mk} {writer} {s['input']} {s['kind']} {tpl}: {key[fid]['secs']:.0f} s, "
                  f"{len(key[fid]['caption'].split())} words", flush=True)
            if a.free:
                free_memory(comfy)
    if not a.dry:                             # a dry run leaves key.json as it is (it travels through git)
        write_key()
    print(f"\n{'DRY RUN' if a.dry else 'DONE'} in {(time.time() - t_start) / 60:.1f} min: {len(key)} pictures in {out}\n"
          f"Next: python tests\\live_sketch.py rate \"{out}\"", flush=True)


_CMP_CSS = (
    "body{font:14px system-ui,sans-serif;margin:16px;background:#1b1b1b;color:#eee}"
    ".row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px} img{width:100%;display:block}"
    "figure{margin:0} figcaption{font-weight:600;margin:4px 0} h3{font-size:15px;margin:24px 0 6px}"
    "h2.part{margin-top:40px;padding-top:12px;border-top:2px solid #378ef0} a{color:#378ef0}"
    "button{margin:6px 6px 0 0;padding:6px 16px;font:inherit;border:1px solid #555;background:#2a2a2a;color:#eee;"
    "border-radius:4px;cursor:pointer} button.on{background:#378ef0;border-color:#378ef0;color:#fff}"
    "button.ok{padding:4px 10px} #res{width:100%;height:110px;margin-top:8px;font:13px monospace;background:#111;"
    "color:#eee} #bar{position:sticky;top:0;background:#1b1b1b;padding:8px 0;z-index:1}")
_CMP_JS = """
const KEY = "%s"; let st = {};
try { st = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const num = k => parseInt(k.slice(1)) * 1000 + parseInt(k.split(":")[1]);
function show() {
  document.querySelectorAll("button[data-k]").forEach(b => b.classList.toggle("on", st[b.dataset.k] === b.dataset.v));
  document.querySelectorAll("button[data-ok]").forEach(b => b.classList.toggle("on", !!st["ok " + b.dataset.ok]));
  const pairs = Object.keys(st).filter(k => !k.startsWith("ok ")).sort((a, b) => num(a) - num(b));
  const oks = Object.keys(st).filter(k => k.startsWith("ok ") && st[k]).map(k => k.slice(3))
      .sort((a, b) => num(a) - num(b) || a.localeCompare(b));
  const all = document.querySelectorAll("button.eq").length;
  document.getElementById("res").value = `Blindvergleich (${pairs.length} von ${all}): ` +
      pairs.map(k => k + ":" + st[k]).join(" ") + "\\nFehlerfrei gut: " + oks.join(" ");
}
document.addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.k) st[b.dataset.k] = st[b.dataset.k] === b.dataset.v ? undefined : b.dataset.v;
  if (b.dataset.ok) st["ok " + b.dataset.ok] = !st["ok " + b.dataset.ok];
  Object.keys(st).forEach(k => { if (!st[k]) delete st[k]; });
  try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {}
  show();
});
show();
"""


def cmd_compare(a):
    """Blind pairs of every writer of --into against the reference writer of --ref (the same pictures and seed): one part
    per writer, sides at random, buttons "besser" / "gleich" and "fehlerfrei gut" under each picture (the rule counts
    fault-free good pictures, docs/archiv/tests/sketch-schreiber-w4a8-testplan.md). Writes blindvergleich.html and the
    resolution aufloesung.json into --into; the reference pictures are copied there (bilder/ref-*.png)."""
    import html
    out, ref = Path(a.into), Path(a.ref)
    new = json.load(open(out / "key.json", encoding="utf-8"))["items"]
    old = json.load(open(ref / "key.json", encoding="utf-8"))["items"]
    refs = {it["input"]: fid for fid, it in old.items() if it["writer"] == a.ref_writer}
    writers = list(dict.fromkeys(w for _, w, _, _ in PARTS.values()
                                 if w != a.ref_writer and any(it["writer"] == w for it in new.values())))
    rnd = random.Random(1611)
    res, body = {}, []
    for p, w in enumerate(writers, 1):
        items = sorted(((fid, it) for fid, it in new.items() if it["writer"] == w),
                       key=lambda x: int(Path(x[1]["input"]).stem))
        body.append(f'<h2 class="part">Teil {p} ({len(items)} Bilder)</h2>')
        for fid, it in items:
            inp = it["input"]
            if inp not in refs:
                sys.exit(f"{inp}: no picture of {a.ref_writer} in {ref}")
            rf = f"ref-{refs[inp]}.png"
            shutil.copyfile(ref / "bilder" / f"{refs[inp]}.png", out / "bilder" / rf)
            sides = [(a.ref_writer, f"bilder/{rf}"), (w, f"bilder/{fid}.png")]
            rnd.shuffle(sides)
            k = f"P{p}:{Path(inp).stem}"
            res[f"P{p}:{inp}"] = {"A": sides[0][0], "B": sides[1][0]}
            figs = [f'<figure><figcaption>Eingabe</figcaption><a href="eingabe/{inp}" target="_blank">'
                    f'<img src="eingabe/{inp}"></a><button class="eq" data-k="{k}" data-v="=">gleich</button></figure>']
            for side, (_, src) in zip("AB", sides):
                figs.append(f'<figure><figcaption>{side}</figcaption><a href="{src}" target="_blank"><img src="{src}"></a>'
                            f'<button data-k="{k}" data-v="{side}">besser</button>'
                            f'<button class="ok" data-ok="{k}:{side}">fehlerfrei gut</button></figure>')
            body.append(f'<section><h3>{k} &middot; {it["kind"]} &middot; &bdquo;{html.escape(it["desc"])}&ldquo;</h3>'
                        f'<div class="row">{"".join(figs)}</div></section>')
    n = len(res)
    page = (f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Blindvergleich</title>'
            f'<style>{_CMP_CSS}</style></head><body><h1>Blindvergleich ({n} Paare in {len(writers)} Teilen)</h1>'
            f'<p>Je Bild: Eingabe, A, B (Seiten zufällig). Klick auf ein Bild öffnet es in 100 %. Je Paar „besser“ oder '
            f'„gleich“, dazu „fehlerfrei gut“ unter jedem Bild ohne Fehler. Die Auflösung steht in '
            f'<code>aufloesung.json</code>; erst nach deiner Bewertung öffnen.</p>'
            f'<div id="bar"><textarea id="res" readonly></textarea></div>{"".join(body)}'
            f'<script>{_CMP_JS % ("blind-" + out.name)}</script></body></html>')
    (out / "blindvergleich.html").write_text(page, encoding="utf-8")
    (out / "aufloesung.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{n} pairs, {len(writers)} parts: {', '.join(writers)}\n{(out / 'blindvergleich.html').resolve().as_uri()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "run", "compare", "grab"))
    ap.add_argument("--set", default="alt", choices=SETS,
                    help="the pictures: alt (rounds 3 and 2 A) or runde3 (data\\sketch-test\\runde3, 16.11.)")
    ap.add_argument("--ref", help="compare: the folder with the reference writer's pictures (same pictures and seed)")
    ap.add_argument("--ref-writer", default="BFL upsampler")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--into")
    ap.add_argument("--pictures", type=int, default=0, help="only the first N pictures (a quick check)")
    ap.add_argument("--files", nargs="+", help="only these pictures of the set (file names, e.g. cat.jpg boat.png)")
    ap.add_argument("--free", action="store_true",
                    help="ask ComfyUI to unload the models and free memory after every run (10.11.: Qwen with 8B, 4B and "
                         "the upsampler filled RAM and page file, ComfyUI stopped taking connections)")
    ap.add_argument("--only", nargs="+", default=list(WRITERS), choices=list(WRITERS))
    ap.add_argument("--sketch-template", default="photo", choices=list(TEMPLATES),
                    help="the template of the sketches (photos with scribbles always run with Scribble on photo)")
    ap.add_argument("--part", nargs="+", choices=list(PARTS),
                    help="parts of the round on PC A (docs/archiv/sketch-schreiber-plan.md); replaces --only and --sketch-template")
    a = ap.parse_args()
    if a.cmd == "compare" and not (a.into and a.ref):
        ap.error("compare needs --into and --ref")
    {"plan": cmd_plan, "run": cmd_run, "compare": cmd_compare, "grab": cmd_grab}[a.cmd](a)


if __name__ == "__main__":
    main()
