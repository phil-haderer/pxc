"""Manual check (not part of run_all.py): MiniMax H3 Image with the Refine prompts of the other models (user 22.11.: "lets
check minimax against refine prompts from the other models, this should work too"; docs/tests/minimax-refine-testplan.md).
MiniMax has no Refine of its own; it runs here as Edit canvas with its start settings (4 MP, "Downsize to canvas" on, so
the result has the size of the photo, no prompt writer), the whole field holding one Refine prompt. 7 prompts x 6 photos
of poor quality = 42 pictures, seed 1234, no comparison pass (his choice). Round 2 (default, 22.11.): six 1:1 cuts of own
phone photos (PHOTOS); round 1 (--round 1 --photos2 <folder>): the compressed Signal pictures and two clean photos. The round machinery (window request, bridge
with the PhotoCraft simulator, blind rating, summary) is the one of live_minimax_edit.py.

    python tests\\live_minimax_refine.py plan [--round 1|2] [--photos <folder>] [--photos2 <folder>]
    python tests\\live_minimax_refine.py run [--round 1|2] [--photos <folder>] [--photos2 <folder>] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_minimax_refine.py rate [folder]      (blind: input left, result right; good / bad, faults 1 to 6)
    python tests\\live_minimax_refine.py summary [folder]   (good and fault-free good per prompt and photo; ergebnis.md)

Output: data\\minimax-refine\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md).
"""
import sys
from pathlib import Path

import live_minimax_edit as lme         # sets PCCOMFY_HOME (live_style_round) before the plugin is imported

from PIL import Image, ImageOps

from pccomfy import models

PHOTOS_DIR = r"D:\testpics"                   # round 2 (default): own phone photos, only on PC A
PHOTOS2_DIR = ""     # round 1 --photos2: the folder "testpics magnific\2MP" (both PCs; no path here because of the export scan)
# Round 2 (user 22.11.: round 1 was bad, the photos unsuited, scratches in 5, 16, 22, 32, 33): a 1:1 cut of about 2 MP
# out of the full-size phone photo keeps the real phone faults (waxy skin, smeared noise in lamp light, soft edges);
# shrunk to 2 MP the same photos are almost clean. Box (left, top, right, bottom) after the EXIF turn; None = whole photo.
PHOTOS = {   # key -> (sub-folder of PHOTOS_DIR, file, box)
    "selfie": ("testpics3", "IMG_20240419_155701.jpg", (1512, 2128, 2712, 3728)),   # mirror selfie in a shop, waxy skin
    "dinner": ("testpics3", "IMG_20240918_191128.jpg", (1504, 825, 3104, 2025)),    # dinner in lamp light, smeared
    "dj": ("testpics3", "IMG_20240509_221644.jpg", (2441, 1565, 3641, 3165)),       # dim room, noise
    "oldphoto": ("testpics3", "signal-2024-02-13-16-52-31-089-2.jpg", None),       # a paper photo photographed: restore
    "lake": ("testpics1", "IMG_3388.jpg", None),                                    # soft, over-saturated
    "backlight": ("testpics3", "IMG_20241123_142913.jpg", (755, 1029, 2355, 2229)), # selfie outside against the light
}
PHOTOS_R1 = {   # round 1 (22.11., run 20261122-162725): key -> (folder 1 or 2, file); --round 1
    "jpeg8": (1, "signal-2024-11-02-214028_008.jpeg"),     # the most compressed one (167 KB at 1600x1200)
    "jpeg9": (1, "signal-2024-11-02-214028_009.jpeg"),     # upright
    "jpeg5": (1, "signal-2024-11-02-214028_005.jpeg"),
    "small": (1, "Screenshot 2025-03-14 091321.png"),        # 567x675: small and soft
    "father": (2, "03_father-with-little.png"),
    "family": (2, "06_happy-family-park.png"),
}
ROUND = 2
PROMPTS = [   # (number, name, text): every Refine prompt of the other models, the Fibo Upscale one too
    (1, "Flux 2 Default", models.FLUX2_DEFAULT),
    (2, "Flux 2 Neutral", models.RELIGHT_NEUTRAL),
    (3, "Flux 2 Studio portrait", models.RELIGHT_STUDIO),
    (4, "Flux 3 Default", models.FLUX3_DEFAULT),
    (5, "Flux 3 Restore", models.FLUX3_RESTORE),
    (6, "Qwen Default", models.QWEN_UPSCALE_DEFAULT),
    (7, "Fibo Default", models.FIBO_UPSCALE_DEFAULT),
]
FAULTS = (
    ("1", "task", "nicht besser als vorher (nicht schärfer, nicht repariert)"),
    ("2", "changed", "Rest verändert (Personen, Gesicht, Aufbau)"),
    ("3", "color", "Farbe oder Licht ungewollt anders"),
    ("4", "plastic", "glatt, wachsig, Plastikhaut"),
    ("5", "artifact", "Bildfehler (Hände, Verzerrung, Muster)"),
    ("6", "soft", "unscharf oder matschig"),
)


def photo_sources_r1(folder, folder2=None) -> dict:
    if not (folder2 or PHOTOS2_DIR):
        sys.exit(r"--photos2 <folder of testpics magnific\2MP> is needed (the two photos with people)")
    dirs = {1: Path(folder or PHOTOS_DIR + r"\testpics2"), 2: Path(folder2 or PHOTOS2_DIR)}
    srcs = {k: dirs[d] / f for k, (d, f) in PHOTOS_R1.items()}
    missing = [str(p) for p in srcs.values() if not p.exists()]
    if missing:
        sys.exit(f"Photos missing: {missing} (--photos / --photos2 <folder>; folder 1 is only on PC A)")
    return srcs


def photo_sources(folder, folder2=None) -> dict:
    """Round 2: cut the boxes out of the phone photos once into data/minimax-refine/fotos-r2/ and return those."""
    if ROUND == 1:
        return photo_sources_r1(folder, folder2)
    d = Path(folder or PHOTOS_DIR)
    missing = [str(d / sub / f) for sub, f, _b in PHOTOS.values() if not (d / sub / f).exists()]
    if missing:
        sys.exit(f"Photos missing: {missing} (--photos <folder with testpics1 and testpics3>; only on PC A)")
    cache = lme.BASE / "fotos-r2"
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for k, (sub, f, box) in PHOTOS.items():
        out[k] = cache / f"{k}.png"
        if not out[k].exists():
            im = ImageOps.exif_transpose(Image.open(d / sub / f)).convert("RGB")
            (im.crop(box) if box else im).save(out[k])
    return out


def setup(a=None):
    """live_minimax_edit with this round's photos, prompts, one pass and its own folder."""
    lme.BASE = lme.lsr.DATA / "minimax-refine"
    lme.PHOTOS_DIR = PHOTOS_DIR
    # one number per picture (the file name pass-NN must be unique): prompt by prompt, photo by photo
    photos = PHOTOS_R1 if ROUND == 1 else PHOTOS
    lme.EDITS = [(i, ph, text) for i, (ph, text) in enumerate(((ph, t) for _n, _name, t in PROMPTS for ph in photos), 1)]
    lme.PASSES = {"mm4": ("minimax", {})}
    lme.PASS_NAME = {"mm4": "MiniMax 4 MP, Downsize to canvas, ohne Schreiber"}
    lme.SECS = {"mm4": 25}
    lme.FAULTS = FAULTS
    folder2 = getattr(a, "photos2", None)
    lme.photo_sources = lambda folder: photo_sources(folder, folder2)


_summarize = lme.summarize


def summarize(key: dict, data: dict) -> str:
    """live_minimax_edit's summary and one table per Refine prompt (good, fault-free good, the faults)."""
    names = {text: f"{n} {name}" for n, name, text in PROMPTS}
    rows = {}
    for fid, it in key["items"].items():
        rec = data.get(fid, {})
        if not rec.get("wahl"):
            continue
        r = rows.setdefault(names.get(it["text"], it["text"][:40]), [0, 0, 0, {}])
        r[0] += 1
        r[1] += rec["wahl"] == lme.GOOD
        r[2] += rec["wahl"] == lme.GOOD and not rec.get("fehler")
        for f in rec.get("fehler", []):
            r[3][f] = r[3].get(f, 0) + 1
    text = _summarize(key, data).replace("# MiniMax Edit Blindtest", "# MiniMax Refine-Prompts Blindtest")
    if not rows:
        return text
    fn = {c: t for _, c, t in FAULTS}
    lines = ["## Je Prompt", "", "| Prompt | bewertet | gut | fehlerfrei gut | Fehler |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {r[0]} | {r[1]} | {r[2]} | " + ", ".join(f"{fn.get(c, c)} {n}" for c, n in sorted(r[3].items())) + " |"
              for k, r in sorted(rows.items())]
    nl = chr(10)
    return text.replace(nl + "## Je Durchgang", nl + nl.join(lines) + nl + nl + "## Je Durchgang", 1)


def main():
    global ROUND
    i = next((k for k, v in enumerate(sys.argv) if v == "--round"), None)
    if i is not None and i + 1 < len(sys.argv):
        ROUND = int(sys.argv[i + 1])
        del sys.argv[i:i + 2]
    setup()
    lme.summarize = summarize
    if len(sys.argv) > 1 and sys.argv[1] in ("plan", "run"):
        i = next((k for k, v in enumerate(sys.argv) if v == "--photos2"), None)
        if i is not None and i + 1 < len(sys.argv):
            folder2 = sys.argv[i + 1]
            del sys.argv[i:i + 2]
            lme.photo_sources = lambda folder: photo_sources(folder, folder2)
    lme.main()


if __name__ == "__main__":
    main()
