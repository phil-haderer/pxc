"""Manual check (not part of run_all.py): Flux 2 and Flux 3 Refine, Default against the other ready-made prompt (user 22.11.:
"bei flux 2 default gegen neutral vergleichen. flux 3 ebenso. nimm dieselben bilder wie bei minimax"). Four passes in
Refine as the window sends it (start settings, the button of the Refine row picked, seed 1234): Flux 2 Default, Flux 2
Neutral, Flux 3 Default, Flux 3 Restore; on the six photos of MiniMax Refine round 2 (live_minimax_refine.PHOTOS, the
same cuts) = 24 pictures, all four mixed in one blind rating. The round machinery is the one of live_minimax_edit.py.

    python tests\\live_flux_refine_compare.py plan [--photos <folder>] [--passes f2-def f2-neu f3-def f3-res]
    python tests\\live_flux_refine_compare.py run [--photos <folder>] [--passes ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_flux_refine_compare.py rate [folder]      (blind: input left, result right; good / bad, faults 1 to 6)
    python tests\\live_flux_refine_compare.py summary [folder]   (good and fault-free good per pass and photo; ergebnis.md)

Output: data\\flux-refine-compare\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md).
"""
from dataclasses import replace

import live_minimax_refine as lmr       # imports live_minimax_edit, which sets PCCOMFY_HOME before the plugin

from pccomfy import models

lme = lmr.lme
PASSES = {   # pass -> (model, button of the Refine row)
    "f2-def": ("flux2", "Default"),
    "f2-neu": ("flux2", "Neutral"),
    "f3-def": ("flux3", "Default"),
    "f3-res": ("flux3", "Restore"),
}
PASS_NAME = {"f2-def": "Flux 2 Refine Default", "f2-neu": "Flux 2 Refine Neutral",
             "f3-def": "Flux 3 Refine Default", "f3-res": "Flux 3 Refine Restore"}


def prompt_of(p: str) -> str:
    mk, label = PASSES[p]
    return dict((c[0], c[1]) for c in models.BY_KEY[mk].modes["refine"].prompts)[label]


def jobs(passes) -> list:
    """(pass, number, photo, prompt) pass by pass (fewer model loads); the number is the photo's."""
    return [(p, n, ph, prompt_of(p)) for p in passes for n, ph in enumerate(lmr.PHOTOS, 1)]


def window_request(app, p: str, text: str):
    """The Request the window sends: the model with its start settings, Refine, the pass' button of the Refine row."""
    mk, label = PASSES[p]
    app.v_model.set(mk)
    app._factory = True
    try:
        app._on_model()
        app._pick_mode("refine")
    finally:
        app._factory = False
    app.v_fac.set("r:" + label)
    app._on_factor()
    req = app._request()
    req.params = replace(req.params, seed=lme.SEED)
    return req


def check(p: str, req) -> list:
    bad = []
    if req.mode != "refine":
        bad.append(f"mode {req.mode}, wanted refine")
    if req.new_document:
        bad.append("opens a new document")
    return bad


def photo_sources(folder) -> dict:
    """The cuts of MiniMax Refine round 2, from the same cache (data\\minimax-refine\\fotos-r2)."""
    base = lme.BASE
    lme.BASE = lme.lsr.DATA / "minimax-refine"
    try:
        return lmr.photo_sources(folder)
    finally:
        lme.BASE = base


def setup():
    lmr.ROUND = 2
    lmr.setup()
    lme.BASE = lme.lsr.DATA / "flux-refine-compare"
    lme.PASSES = PASSES
    lme.PASS_NAME = PASS_NAME
    lme.SECS = {p: 15 for p in PASSES}
    lme.EDITS = [(n, ph, "") for n, ph in enumerate(lmr.PHOTOS, 1)]
    lme.jobs = jobs
    lme.window_request = window_request
    lme.check = check
    lme.photo_sources = photo_sources
    lme.summarize = lambda key, data: lme_summarize(key, data).replace("# MiniMax Edit Blindtest", "# Flux Refine Default gegen Alternative, Blindtest")


lme_summarize = lme.summarize


def main():
    setup()
    lme.main()


if __name__ == "__main__":
    main()
