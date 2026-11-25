"""Manual check (not part of run_all.py): Refine on real old colour photos (user 22.11.: "mach noch einen testlauf durch,
nimm neue fotos, suche im internet nach passenden fotos. nimm nur farbfotos von menschen oder menschengruppen"; the
phone photos of the earlier rounds were only slightly soft). Six DOCUMERICA slides of the 1970s (US EPA, public domain,
original TIFF scans of the US National Archives): faded colours, grain, soft focus. A 1:1 cut of about 2 MP around the
faces (BOXES), cut once into data\\qwen-restore-lora\\fotos-r2\\; seed 1234, blind. His choice 22.11. "Qwen 4 + Flux 2":

    q-def     Qwen Refine, Default prompt, no LoRA (as the window today)
    q-b       Qwen Refine, prompt B, no LoRA (refine round 3: 5 of 6)
    q-r10     Qwen Refine + ausboss' Restore LoRA 1.0, Default prompt (LoRA round: 5 of 6)
    q-r05     the same with the LoRA at 0.5 (LoRA round: 5 of 6)
    f2-def    Flux 2 Refine Default (as the window)
    f3-def    Flux 3 Refine Default (as the window, with its Restore LoRA since 22.11.)
    f2-neu    Flux 2 Refine Neutral (added 22.11. into the same run: --passes f2-neu --into <run folder>)

6 x 6 = 36 pictures, about 14 min on PC A.

    python tests\\live_refine_old_photos.py run [--photos <folder of the TIFFs>] [--passes ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_refine_old_photos.py rate [folder]
    python tests\\live_refine_old_photos.py summary [folder]

The TIFFs (about 88 MB, not in the repo): https://catalog.archives.gov/medialz/stillpix/412-da/<file of PHOTOS>, saved as
<key>.tif in data\\qwen-restore-lora\\fotos-r2\\orig\\ (or --photos <folder>).
Output: data\\qwen-restore-lora\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md, wf\\).
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

from PIL import Image

import live_flux_refine_compare as lfc
import live_qwen_restore_lora as lql
import live_refine_round3 as lr3

from pccomfy import models

lme = lfc.lme
PHOTOS = {   # key -> (NARA file, box (left, top, right, bottom) of about 2 MP around the faces)
    "ranch": ("412-DA-12409_14-0589M.TIF", (150, 150, 1850, 1330)),             # ranch family at table, Leakey TX
    "teens": ("412-DA-12446_14-0626M.TIF", (300, 150, 2000, 1330)),             # teenage girls, Leakey TX
    "church-youth": ("412-DA-10127_12-2185M.TIF", (300, 100, 2028, 1252)),      # young people after a church meeting
    "church-family": ("412-DA-13781_15-0661M.TIF", (1000, 0, 2728, 1152)),      # family with a baby, Chicago
    "fisher-family": ("412-DA-01712_05-2253M.TIF", (150, 1000, 1650, 2350)),    # fisherman's family, Bayou Gauche
    "woman-hat": ("412-DA-13699_15-0579M.TIF", (411, 300, 2139, 1452)),         # woman with a pink hat, Chicago
}
PASSES = {   # pass -> (model key, LoRA strength or None, prompt or None = the window's Default)
    "q-def": ("qwen", None, None),
    "q-b": ("qwen", None, lql.QWEN_B),
    "q-r10": ("qwen", 1.0, None),
    "q-r05": ("qwen", 0.5, None),
    "f2-def": ("flux2", None, None),
    "f3-def": ("flux3", None, None),
    "f2-neu": ("flux2", None, models.RELIGHT_NEUTRAL),   # user 22.11. "Ja, so": does Neutral keep the colours? (--passes f2-neu)
    "q-f2": ("qwen", None, models.FLUX2_DEFAULT),
    "q-dk": ("qwen", None, lr3.QWEN_DK),
    "f3-res": ("flux3", None, models.FLUX3_RESTORE),   # user 24.11. "alle refines genau einen modus": Restore with its LoRA   # user 24.11.: Default and Keep colors combined (--passes q-dk --into)   # user 24.11.: can Qwen be made Flux-2-like? (--passes q-f2 --into)
}
PASS_NAME = {"q-def": "Qwen Refine Default", "q-b": "Qwen Refine Prompt B", "q-r10": "Qwen + Restore-LoRA 1.0",
             "q-r05": "Qwen + Restore-LoRA 0.5", "f2-def": "Flux 2 Refine Default",
             "f3-def": "Flux 3 Refine Default (mit Restore-LoRA)", "f2-neu": "Flux 2 Refine Neutral",
             "q-f2": "Qwen Refine, Flux-2-Default-Prompt", "q-dk": "Qwen Refine, Default + Keep colors",
             "f3-res": "Flux 3 Refine Restore (mit Restore-LoRA)"}


def prompt_of(p: str) -> str:
    mk, _lora, text = PASSES[p]
    return text or models.BY_KEY[mk].modes["refine"].prompt_hint


def jobs(passes) -> list:
    return [(p, n, ph, prompt_of(p)) for p in passes for n, ph in enumerate(PHOTOS, 1)]


def window_request(app, p: str, text: str):
    """The window's Refine of the pass' model with the Default button, then the pass' prompt; the Qwen LoRA passes get the
    copy of the workflow with the LoRA (live_qwen_restore_lora)."""
    mk, lora, _text = PASSES[p]
    app.v_model.set(mk)
    app._factory = True
    try:
        app._on_model()
        app._pick_mode("refine")
    finally:
        app._factory = False
    app.v_fac.set("r:Default")
    app._on_factor()
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", text)
    req = app._request()
    req.params = replace(req.params, seed=lme.SEED)
    if lora is not None:
        req.workflow = lql.lora_workflow(lora)
    return req


def check(p: str, req) -> list:
    bad = lfc.check(p, req)
    mk, lora, _text = PASSES[p]
    if lora is not None:
        g = json.loads(Path(req.workflow).read_text(encoding="utf-8"))
        if g.get("20", {}).get("inputs", {}).get("strength_model") != lora:
            bad.append("LoRA strength")
    elif mk == "qwen" and "restore" in Path(req.workflow or "").name:
        bad.append("LoRA where none belongs")
    if mk == "flux3" and req.turbo is not True:
        bad.append("Flux 3 Refine without its Restore LoRA")
    return bad


def photo_sources(folder) -> dict:
    """Cut the boxes out of the TIFFs once into data/qwen-restore-lora/fotos-r2/ and return those."""
    cache = lme.BASE / "fotos-r2"
    d = Path(folder) if folder else cache / "orig"
    missing = [str(d / f"{k}.tif") for k in PHOTOS if not (d / f"{k}.tif").exists()]
    if missing:
        sys.exit(f"Photos missing: {missing} (download them, see the top of this file, or --photos <folder>)")
    out = {}
    for k, (_f, box) in PHOTOS.items():
        out[k] = cache / f"{k}.png"
        if not out[k].exists():
            Image.open(d / f"{k}.tif").convert("RGB").crop(box).save(out[k])
    return out


def main():
    lfc.setup()
    lme.BASE = lme.lsr.DATA / "qwen-restore-lora"
    lql.lme.BASE = lme.BASE
    lme.PASSES = PASSES
    lme.PASS_NAME = PASS_NAME
    lme.SECS = {p: 26 if PASSES[p][0] == "qwen" else 20 for p in PASSES}
    lme.EDITS = [(n, ph, "") for n, ph in enumerate(PHOTOS, 1)]
    lme.jobs = jobs
    lme.window_request = window_request
    lme.check = check
    lme.photo_sources = photo_sources
    lme.summarize = lambda key, data: lfc.lme_summarize(key, data).replace("# MiniMax Edit Blindtest", "# Refine auf alten Farbfotos, Blindtest")
    lme.main()


if __name__ == "__main__":
    main()
