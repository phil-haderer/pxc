r"""Manual check (not part of run_all.py): MiniMax H3 Image Sketch to image and Scribble on photo, step 8 of
docs/plan-minimax-h3-image.md (user 21.11.: "Sketch/Scribble testen"; test plan docs/tests/minimax-sketch-testplan.md).

MiniMax runs both through its Edit graph (run_as="edit", like Flux 3, Flux 2 and Qwen); the two Modes are added to
models.MINIMAX for this run only, nothing in the plugin changes. Three writers:
    a  the official MiniMax writer of the Edit graph, unchanged
    b  our Sketch writer (models.QWEN_SKETCH_WRITER_SYSTEM, qwen3.5 9B w4a8 as in Qwen's Sketch graph: temperature 0.3,
       thinking for Sketch to image, none for Scribble on photo), patched into the graph before it is queued
    c  no writer
Flux 3 is not run again (user 21.11.: "rechne hier die flux 3 bilder nicht neu"): its pictures of the same cases, seed
1234, with today's build settings, are copied from the earlier sketch rounds into the blind rating:
    Sketch to image, Animated film (no faces): the 7 sketches of round 3 b (data\sketch-test\round3b-*), the originals
    from live_sketch.R3_IMAGES; Photo: the same 7 sketches, MiniMax only (round 3's Flux 3 pictures are on PC B;
    its ratings are in docs\tests\runs\sketch-test\round3-20261109-094900).
    Scribble on photo: the 12 photos of round 6 (red scribbles, the way built: crop, colour match, edge fades), their
    Flux 3 pictures of the way "cfade".
Scribble with reference (user 21.11.: "Erst Probe machen", --only refscr): the 6 cases of the probe of 15.11.
    (data\sketch-test\ref-scribble-kritzel, the references from --testpics\testpics1), MiniMax without a writer (the start
    value) and the chip's text with the object typed in; Flux 3's pictures of the way built (no box, with the upsampler)
    from data\sketch-test\ref-scribble-20261115-*. 6 MiniMax pictures.
The texts are the ones Flux 3 got. 26 cases x 3 = 78 MiniMax pictures and 19 Flux 3 pictures to rate; the user chose
only a and c (21.11.), 52 pictures (--variants abc for all three).

    python tests\live_minimax_sketch.py plan
    python tests\live_minimax_sketch.py run --dry          (every graph against the fake ComfyUI; no GPU)
    python tests\live_minimax_sketch.py run [--only sketch|scribble] [--variants ac|abc] [--url http://<ip>:8188]
    python tests\live_minimax_sketch.py run --only refscr --testpics <D:\testpics> [--dry]
    python tests\live_minimax_sketch.py rate [folder]       (blind: input left, result right; G / S, faults 1 to 6)
    python tests\live_minimax_sketch.py summary [folder]    (good and fault-free good per variant; ergebnis.md)

Output: data\minimax-sketch\<time>\ (eingabe\, bilder\, key.json, bewertung.json, index.html, ergebnis.md).
Needs the GPU: before the run, remind the user not to use ComfyUI meanwhile.
"""
import argparse
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
from PIL import Image  # noqa: E402

from live_progress import Left  # noqa: E402  (what is left of the round)
import live_minimax_fill_multi as lfm  # noqa: E402  (window_request, page, rate)
import live_style_test as base  # noqa: E402  (make_app)
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator and FakeComfy)
from pccomfy import models  # noqa: E402
from pccomfy import config as cfgmod  # noqa: E402
from pccomfy.bridge import Bridge  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "minimax-sketch"
OLD = cfgmod.CONFIG_DIR / "sketch-test"
SEED = 1234
WF = "minimax-h3-image-edit.json"
_EDIT = dict(models.MINIMAX_EDIT, enhance=True)          # 4 MP, "Downsize to canvas" on; the writer on (a, b), off for c
TEST_MODES = {
    "sketch": models.Mode(WF, dict(_EDIT), prompt_tip=models.SKETCH_TIP, run_as="edit"),
    "scribble": models.Mode(WF, dict(_EDIT), models.SKETCH_SCRIBBLE, models.SCRIBBLE_PROMPTS, models.SCRIBBLE_TIP,
                            run_as="edit"),
}
VARIANTS = ("a", "b", "c")
NAME = {"a": "MiniMax, offizieller Schreiber", "b": "MiniMax, unser Sketch-Schreiber", "c": "MiniMax, ohne Schreiber",
        "flux3": "Flux 3 Klein (frühere Runde)"}
FAULTS = (
    ("1", "task", "Auftrag nicht erfüllt (Objekt / Motiv falsch)"),
    ("2", "changed", "Rest verändert (Komposition, Foto)"),
    ("3", "seam", "Rand oder Naht sichtbar"),
    ("4", "lines", "bleibt Skizze / Linien übrig"),
    ("5", "artifact", "Bildfehler (Hände, Gesichter, Verzerrung)"),
    ("6", "style", "Stil falsch"),
)


# ---------- the cases ----------

def _key(folder: Path) -> dict:
    return json.load(open(folder / "key.json", encoding="utf-8"))["items"]


def _one(pattern: str) -> Path:
    found = sorted(OLD.glob(pattern))
    if not found:
        sys.exit(f"Not found: {OLD / pattern} (the earlier sketch rounds are on PC A)")
    return found[-1]


def cases() -> list[dict]:
    """{id, kind (sketch / scribble), style, text, desc, source (the picture MiniMax gets), shown (the input of the rating),
    flux (Flux 3's picture or None)}."""
    subjects = {v: k for k, v in __import__("live_sketch").R3_SUBJECTS.items()}       # desc -> file stem
    photo_texts = {it["desc"]: it["text"] for it in _key(_one("round3-2*")).values()
                   if it["model"].startswith("Flux 3") and it["prompt"] == "Photo"}
    out, n = [], 0
    for folder in (_one("round3b-2*"), _one("round3b-figuren-*")):
        for fid, it in _key(folder).items():
            if not it["model"].startswith("Flux 3"):
                continue
            n += 1
            src = __import__("live_sketch").R3_IMAGES / f"{subjects[it['desc']]}.jpg"
            shown = folder / "eingabe" / it["input"]
            out.append(dict(id=f"S{n}f", kind="sketch", style="Animated film", text=it["text"], desc=it["desc"],
                            source=src, shown=shown, flux=folder / "bilder" / f"{fid}.png"))
            out.append(dict(id=f"S{n}p", kind="sketch", style="Photo", text=photo_texts[it["desc"]], desc=it["desc"],
                            source=src, shown=shown, flux=None))
    r6 = _one("round6-2*")
    for fid, it in sorted(_key(r6).items(), key=lambda x: int(x[1]["input"].split(".")[0])):
        if it["model"].startswith("Flux 3") and it.get("way") == "cfade":
            pic = r6 / "eingabe" / it["input"]
            out.append(dict(id=f"K{int(it['input'].split('.')[0]):02d}", kind="scribble", style="Scribble on photo",
                            text=it["text"], desc=it["desc"], source=pic, shown=pic, flux=r6 / "bilder" / f"{fid}.png"))
    if R["testpics"]:
        out += ref_cases()
    return out


R = {"testpics": ""}            # set from the command line (the reference pictures of Scribble with reference)


def ref_cases() -> list[dict]:
    """Scribble with reference: the probe of 15.11., the scribbled photos and Flux 3's pictures of the way built (no box,
    with the upsampler)."""
    folder = _one("ref-scribble-20261115-0*")
    out = []
    for fid, it in sorted(_key(folder).items()):
        v = it.get("variant", "")
        if not it["model"].startswith("Flux 3") or not ("ohne Box" in v and "mit Upsampler" in v):
            continue
        n = int(it["input"][:2])
        text = models.REF_SCRIBBLE.replace(models.REF_MARK, "a " + it["desc"]).replace(
            "{tag}", models.MINIMAX.tag_style.format(n=2, i=1))
        out.append(dict(id=f"R{n}", kind="refscr", style="Scribble with reference", text=text, desc=it["desc"],
                        source=OLD / "ref-scribble-kritzel" / it["input"], shown=folder / "eingabe" / it["input"],
                        ref=Path(R["testpics"]) / "testpics1" / it["ref"], flux=folder / "bilder" / f"{fid}.png"))
    if len(out) != 6:
        sys.exit(f"Scribble with reference: {len(out)} of 6 Flux 3 pictures found in {folder}")
    return out


def jobs(only: str, variants: str = "ac", ids: str = "") -> list[tuple]:
    """(variant, case); every MiniMax picture, the writer that loads least first (user 21.11.: "nur A und C")."""
    cs = [c for c in cases() if only in ("", c["kind"]) and (not ids or c["id"] in ids.split(","))]
    return [(v, c) for v in ("c", "a", "b") if v in variants for c in cs if c["kind"] != "refscr" or v != "b"]


def describe(c: dict) -> str:
    return f"{c['style']} {c['id']}: {c['text']}"


# ---------- the plugin path ----------

def patch_b(graph: dict, kind: str) -> None:
    """b: the writer of Qwen's Sketch graph (node 403 of qwen-image-21-sketch.json) in place of the official one; its plain
    prose goes straight to MiniMax (no JSON caption)."""
    if "15" not in graph:
        raise RuntimeError("b: the writer node 15 is not in the graph (writer off?)")
    graph["17"]["inputs"]["value"] = models.QWEN_SKETCH_WRITER_SYSTEM
    graph["20"]["inputs"]["value"] = "{input text}"           # the request alone, no task prompt around it
    graph["15"] = {"class_type": "TextGenerate", "_meta": {"title": "Sketch writer (test b)"}, "inputs": {
        "clip": ["16", 0], "system_prompt": ["17", 0], "prompt": ["19", 0],
        "max_length": 8192 if kind == "sketch" else 4096, "sampling_mode": "on", "sampling_mode.temperature": 0.3,
        "sampling_mode.top_k": 64, "sampling_mode.top_p": 0.95, "sampling_mode.min_p": 0.05,
        "sampling_mode.repetition_penalty": 1.0, "sampling_mode.seed": 0, "sampling_mode.presence_penalty": 0.0,
        "thinking": kind == "sketch", "use_default_template": True, "mtp": "auto", "image": ["30", 0]}}
    graph["5"]["inputs"]["prompt"] = ["15", 0]
    graph.pop("26", None)
    if "18" in graph:
        graph["18"]["inputs"]["source"] = ["15", 0]


class Patched:
    """The ComfyUI client with b's writer patched into every graph before it is queued."""
    def __init__(self, inner, kind: str):
        self._inner, self._kind = inner, kind

    def queue(self, graph, preview=None):
        patch_b(graph, self._kind)
        return self._inner.queue(graph, preview)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def run_one(comfy, app, variant: str, c: dict) -> Image.Image:
    with Image.open(c["source"]) as im:
        pic = im.convert("RGB")
    req = lfm.window_request(app, "minimax", "scribble" if c["kind"] == "refscr" else c["kind"])
    if c["kind"] == "refscr":
        with Image.open(c["ref"]) as im:
            req.refs = [im.convert("RGB")]
    req.enhance = variant != "c"
    req.params = replace(req.params, prompt=c["text"], seed=SEED)
    T.W, T.H = pic.size
    tmp = tempfile.mkdtemp(prefix="minimax-sketch-")
    pc = T.FakePC(tmp)
    pc.docs.append(T.Doc("sketch.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True}], None))
    try:
        Bridge(pc, Patched(comfy, c["kind"]) if variant == "b" else comfy, tmp).run(req)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    doc = pc.docs[-1]
    return getattr(doc, "raw", None) or pc.composite(doc)


def check_dry(app, js) -> None:
    """Every job against the fake ComfyUI: MiniMax, the scribble found, the writer as the variant wants it."""
    for variant, c in js:
        fake = T.FakeComfy()
        run_one(fake, app, variant, c)
        g = fake.graphs[-1]
        unets = [n["inputs"].get("unet_name", "") for n in g.values() if isinstance(n, dict) and n.get("class_type") == "UNETLoader"]
        writer = g.get("15", {}).get("class_type", "-")
        info = f"{variant} {c['id']}: {', '.join(unets)[:50]}; writer {writer}"
        assert any("minimax" in u for u in unets), info
        assert writer == {"a": "TextGenerateV2", "b": "TextGenerate", "c": "-"}[variant], info
        prompt = g["5"]["inputs"]["prompt"]
        if variant == "c":
            assert isinstance(prompt, str) and c["text"][:40] in prompt, (info, prompt)
        else:
            if isinstance(prompt, list) and g[prompt[0]].get("_meta", {}).get("title") == "Written prompt + reference sentence":
                info += f"; + {g[prompt[0]]['inputs']['string_b'][-60:]!r}"     # Scribble with reference: the sentence past the writer
                prompt = g[prompt[0]]["inputs"]["string_a"]
            assert prompt == (["15", 0] if variant == "b" else ["26", 0]), (info, prompt)
            assert c["text"][:40] in json.dumps(g, ensure_ascii=False), info
        main = next((v for k, v in fake.uploads.items() if k.endswith("-image.png")), None)
        info += f"; sent {main.size if main else '-'}"
        if c["kind"] == "refscr":       # the reference in slot 2, named <Picture 2> in the text MiniMax gets
            refs = [v.size for k, v in fake.uploads.items() if "-ref" in k]
            assert len(refs) == 1 and g["5"]["inputs"].get("images.image_2") == ["31", 0], (info, refs)
            text = g["5"]["inputs"]["prompt"]
            if isinstance(text, list):          # the writer on: the sentence with the tag is appended after it
                text = g[text[0]]["inputs"]["string_b"]
            assert "<Picture 2>" in text, (info, text)
            info += f"; ref {refs[0]}; text {text[-90:]!r}"
        print(info, flush=True)
    print(f"ok: {len(js)} graphs build")


# ---------- commands ----------

def cmd_plan(a):
    js = jobs(a.only, a.variants, a.cases)
    for v, c in js:
        print(f"{NAME[v]:<34} {describe(c)[:110]}")
    flux = [c for c in cases() if c["flux"] and a.only in ("", c["kind"])]
    print(f"{len(js)} MiniMax pictures, {len(flux)} Flux 3 pictures copied")


def cmd_run(a):
    models.MINIMAX.modes.update(TEST_MODES)          # for this run only
    if a.only == "refscr":
        if not R["testpics"] or not Path(R["testpics"]).is_dir():
            sys.exit(f"--testpics <folder> is missing or not there: {R['testpics']}")
        models.MINIMAX.modes["scribble"] = replace(models.MINIMAX.modes["scribble"], ref_scribble=True)
    _use_here()
    url = a.url or cfgmod.load()["comfyui"]["url"]
    app = base.make_app("http://127.0.0.1:1" if a.dry else url)
    js = jobs(a.only, a.variants, a.cases)
    try:
        check_dry(app, js)
        if a.dry:
            return
        out = BASE / time.strftime("%Y%m%d-%H%M%S")
        for sub in ("bilder", "eingabe"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        key = {}

        def write_key():
            order = list(key)
            random.Random(2111).shuffle(order)
            json.dump({"items": key, "order": order, "names": NAME}, open(out / "key.json", "w", encoding="utf-8"),
                      indent=1, ensure_ascii=False)
            lfm.page(out, key)

        def note(fid, variant, c, secs):
            if not (out / "eingabe" / f"{c['id']}.jpg").exists():
                with Image.open(c["shown"]) as im:
                    im.convert("RGB").save(out / "eingabe" / f"{c['id']}.jpg", quality=92)
            key[fid] = {"variant": variant, "case": c["id"], "kind": c["kind"], "style": c["style"], "seed": SEED,
                        "text": describe(c), "input": f"{c['id']}.jpg", "secs": secs}

        for c in cases():
            if c["flux"] and a.only in ("", c["kind"]) and (not a.cases or c["id"] in a.cases.split(",")):
                shutil.copy(c["flux"], out / "bilder" / f"{c['id']}_flux3.png")
                note(f"{c['id']}_flux3", "flux3", c, 0)
        write_key()
        from live_expand_remote import Timed
        comfy = Timed(url)
        left = Left(len(js))
        for i, (variant, c) in enumerate(js, 1):
            fid = f"{c['id']}_{variant}"
            t0 = time.time()
            try:
                res = run_one(comfy, app, variant, c)
            except Exception as e:      # noqa: BLE001  one failed picture must not stop the round
                msg = str(e).splitlines()[-1][:300] if str(e) else type(e).__name__
                print(f"{i}/{len(js)} {fid} failed: {msg}", flush=True)
                continue
            secs = round(time.time() - t0)
            res.save(out / "bilder" / f"{fid}.png")
            note(fid, variant, c, secs)
            write_key()
            print(f"{i}/{len(js)} {fid}: {secs} s" + left(i), flush=True)
        print(f"Results: {(out / 'index.html').as_uri()}")
    finally:
        app.root.destroy()


def _use_here():
    """rate and page of live_minimax_fill_multi with this round's folder, names and faults."""
    lfm.BASE, lfm.NAME, lfm.FAULTS = BASE, NAME, FAULTS


def cmd_rate(a):
    _use_here()
    lfm.cmd_rate(a)


def summarize(key: dict, data: dict) -> str:
    items = key["items"]
    rows, faults, secs = {}, {}, {}
    for fid, it in items.items():
        if it["variant"] != "flux3":
            secs.setdefault((it["kind"], it["variant"]), []).append(it["secs"])
        rec = data.get(fid, {})
        if not rec.get("wahl"):
            continue
        good = rec["wahl"] == lfm.GOOD
        clean = good and not rec.get("fehler")
        for k in (("Variante", f"{it['style']} · {NAME[it['variant']]}"), ("Fall", f"{it['case']} · {NAME[it['variant']]}")):
            r = rows.setdefault(k, [0, 0, 0])
            r[0] += 1
            r[1] += good
            r[2] += clean
        for f in rec.get("fehler", []):
            faults[(it["style"], it["variant"], f)] = faults.get((it["style"], it["variant"], f), 0) + 1
    rated = sum(1 for f in items if data.get(f, {}).get("wahl"))
    lines = [f"# MiniMax Sketch to image und Scribble on photo {key.get('folder', '')}".rstrip(), "",
             f"Bewertet: {rated} von {len(items)} (blind, Seed {SEED}; Flux 3 aus den Sketch-Runden 3 b und 6)", ""]
    for kind in ("Variante", "Fall"):
        sub = sorted((name, r) for (k, name), r in rows.items() if k == kind)
        if sub:
            lines += [f"## Je {kind}", "", f"| {kind} | bewertet | gut | fehlerfrei gut |", "|---|---|---|---|"]
            lines += [f"| {name} | {r[0]} | {r[1]} | {r[2]} |" for name, r in sub] + [""]
    if faults:
        names = {c: t for _, c, t in FAULTS}
        lines += ["## Fehler je Variante (auch bei „gut“)", "", "| Stil | Variante | Fehler | Anzahl |", "|---|---|---|---|"]
        lines += [f"| {s} | {NAME[v]} | {names.get(c, c)} | {n} |" for (s, v, c), n in sorted(faults.items())] + [""]
    lines += ["## Zeit je Bild (MiniMax)", "", "| Teil | Variante | Bilder | Mittel s |", "|---|---|---|---|"]
    lines += [f"| {k} | {NAME[v]} | {len(s)} | {sum(s) / len(s):.0f} |" for (k, v), s in sorted(secs.items())] + [""]
    notes = [(items[f], r["notiz"]) for f, r in data.items() if r.get("notiz") and f in items]
    if notes:
        lines += ["## Notizen", ""] + [f"- {NAME[it['variant']]}, {it['case']}: {n}" for it, n in notes]
    return "\n".join(lines) + "\n"


def cmd_summary(a):
    _use_here()
    out = lfm.latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    key["folder"] = out.name
    data = json.loads((out / "bewertung.json").read_text(encoding="utf-8")) if (out / "bewertung.json").exists() else {}
    text = summarize(key, data)
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "run", "rate", "summary"))
    ap.add_argument("folder", nargs="?", default="")
    ap.add_argument("--only", default="", choices=("", "sketch", "scribble", "refscr"))
    ap.add_argument("--testpics", default="", help="Scribble with reference: the folder D:\testpics (testpics1)")
    ap.add_argument("--url", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default="", help="only these cases, e.g. R1,R3 (user 21.11.: R1 and R3 with the writer)")
    ap.add_argument("--variants", default="ac", help="which writers: a, b, c (default ac, user 21.11.)")
    a = ap.parse_args()
    R["testpics"] = a.testpics if a.only == "refscr" else ""
    {"plan": cmd_plan, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
