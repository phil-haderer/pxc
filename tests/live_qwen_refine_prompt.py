"""Manual check (not part of run_all.py): Qwen Image 2.1 Refine with its Default prompt against the same prompt without
"Image can be illustration or real photo" (user 22.11.: "remove the part ...", then "das testen wir noch mit qwen refine
und upscale"). There is no older Qwen Refine round, so both prompts run here; Upscale reuses the old upscale stages round
(tests/live_upscale_stages.py --part N). Two passes in Refine as the window sends it (start settings, button Default,
the field then holding the pass' text, seed 1234) on the six photos of MiniMax Refine round 2 = 12 pictures, blind.

    python tests\\live_qwen_refine_prompt.py run [--photos <folder>] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_qwen_refine_prompt.py rate [folder]
    python tests\\live_qwen_refine_prompt.py summary [folder]

Output: data\\qwen-refine-prompt\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md).
"""
from dataclasses import replace

import live_flux_refine_compare as lfc   # the photos and the round machinery of the Flux comparison

from pccomfy import models

lme = lfc.lme
OLD = models.QWEN_UPSCALE_DEFAULT
NEW = OLD.replace(" Image can be illustration or real photo, keep", " Keep")
PASSES = {"q-alt": ("qwen", OLD), "q-neu": ("qwen", NEW)}
PASS_NAME = {"q-alt": "Qwen Refine Default (mit Zusatz)", "q-neu": "Qwen Refine ohne „Image can be illustration or real photo“"}


def jobs(passes) -> list:
    return [(p, n, ph, PASSES[p][1]) for p in passes for n, ph in enumerate(lfc.lmr.PHOTOS, 1)]


def window_request(app, p: str, text: str):
    app.v_model.set("qwen")
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
    return req


def main():
    assert NEW != OLD, "the Qwen prompt changed: update OLD/NEW"
    lfc.setup()
    lme.BASE = lme.lsr.DATA / "qwen-refine-prompt"
    lme.PASSES = PASSES
    lme.PASS_NAME = PASS_NAME
    lme.SECS = {p: 20 for p in PASSES}
    lme.jobs = jobs
    lme.window_request = window_request
    lme.summarize = lambda key, data: lfc.lme_summarize(key, data).replace("# MiniMax Edit Blindtest", "# Qwen Refine Prompt-Zusatz, Blindtest")
    lme.main()


if __name__ == "__main__":
    main()
