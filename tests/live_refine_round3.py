"""Manual check (not part of run_all.py): Refine round 3, Flux 3 and Qwen (user 22.11.: "Flux 3 und Qwen", after Flux 3 Refine
scored 0 of 6 with Default and 2 with Restore, Qwen 3 of 6; docs/tests/refine-runde3-testplan.md). Flux 3 Refine hardly
changes the photo; Flux 3 Upscale (the user's "perfect") has a Restore LoRA (0.5), SeedVR2 and tiles, Flux 3 Refine none of it.
On the six photos of MiniMax Refine round 2, seed 1234, blind:

    f3-lora    Flux 3 Refine + the Restore LoRA of Flux 3 Upscale (0.5), Default prompt
    f3-f2p     Flux 3 Refine, the Flux 2 Default prompt (it describes the goal instead of "remove blur ...")
    f3-both    both
    f3-up1     Flux 3 Upscale at factor 1.0 (its whole chain: SeedVR2, tiles, Restore LoRA, Color Match), Default prompt
    q-b        Qwen Refine, the prompt "A sharper, cleaner version of the same image: ..." (proposal B)

5 x 6 = 30 pictures. Variants the window cannot make (the LoRA, factor 1) are set on the request here only.

    python tests\\live_refine_round3.py run [--photos <folder>] [--passes ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_refine_round3.py rate [folder]
    python tests\\live_refine_round3.py summary [folder]

Output: data\\refine-round3\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md, wf\\ the changed workflow).
"""
import json
from dataclasses import replace

import live_flux_refine_compare as lfc   # the photos and the round machinery of the Flux comparison

from pccomfy import models

lme = lfc.lme
QWEN_B = ("A sharper, cleaner version of the same image: clean detail and texture, the same style, composition, colors "
          "and light.")
QWEN_DK = ("Enhance this image to high resolution while preserving the original composition, lighting, and atmosphere: a sharper, cleaner "
          "version with clean detail and texture, the same style, colors and light. Image can be illustration or real photo, keep the "
          "original input style.")   # Qwen Default + Keep colors in one (user 24.11. "defkeep")
PASSES = {   # pass -> (model, function, prompt or None = the function's own, Restore LoRA, factor)
    "f3-lora": ("flux3", "refine", None, True, None),
    "f3-f2p": ("flux3", "refine", models.FLUX2_DEFAULT, False, None),
    "f3-both": ("flux3", "refine", models.FLUX2_DEFAULT, True, None),
    "f3-up1": ("flux3", "upscale", None, False, 1.0),
    "q-b": ("qwen", "refine", QWEN_B, False, None),
    "q-f2": ("qwen", "refine", models.FLUX2_DEFAULT, False, None),   # user 24.11.: can Qwen be made Flux-2-like? (--passes q-f2 --into)
    "q-dk": ("qwen", "refine", QWEN_DK, False, None),   # user 24.11.: Default and Keep colors combined (--passes q-dk --into)
    # user 24.11. "alle refines genau einen modus": Flux 3 Restore as the window runs it today (its Restore LoRA switch on)
    "f3-res-l": ("flux3", "refine", models.FLUX3_RESTORE, False, None),
}
PASS_NAME = {"f3-lora": "Flux 3 Refine + Restore-LoRA", "f3-f2p": "Flux 3 Refine, Flux-2-Default-Prompt",
             "f3-both": "Flux 3 Refine + Restore-LoRA + Flux-2-Prompt", "f3-up1": "Flux 3 Upscale 1x",
             "q-b": "Qwen Refine, Prompt B", "q-f2": "Qwen Refine, Flux-2-Default-Prompt",
             "q-dk": "Qwen Refine, Default + Keep colors", "f3-res-l": "Flux 3 Refine Restore (mit Restore-LoRA)"}


def lora_workflow() -> str:
    """flux3-klein-refine.json with the Restore LoRA node of flux3-klein-upscale.json between the model and the sampler; its
    title is not pc:lora, so the Turbo switch (off for Flux 3 Refine) does not bypass it."""
    root = lme.lsr.ROOT
    g = json.loads((root / "workflows" / "flux3-klein-refine.json").read_text(encoding="utf-8"))
    up = json.loads((root / "workflows" / "flux3-klein-upscale.json").read_text(encoding="utf-8"))
    node = dict(up["9"], inputs=dict(up["9"]["inputs"], model=["8", 0]))
    node["_meta"] = {"title": "Restore LoRA (round 3 test)"}
    g["9"] = node
    g["163"]["inputs"]["model"] = ["9", 0]
    out = lme.BASE / "wf" / "flux3-klein-refine-restore-lora.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
    return str(out)


def prompt_of(p: str) -> str:
    mk, fn, text, _lora, _fac = PASSES[p]
    return text or models.BY_KEY[mk].modes[fn].prompt_hint


def jobs(passes) -> list:
    return [(p, n, ph, prompt_of(p)) for p in passes for n, ph in enumerate(lfc.lmr.PHOTOS, 1)]


def window_request(app, p: str, text: str):
    """The window's request for the model and function (start settings), the pass' prompt in the field, then what the
    window cannot do: the LoRA workflow or factor 1."""
    mk, fn, own, lora, fac = PASSES[p]
    app.v_model.set(mk)
    app._factory = True
    try:
        app._on_model()
        app._pick_mode(fn)
    finally:
        app._factory = False
    if fn == "refine":
        app.v_fac.set("r:Default")
        app._on_factor()
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", text)
    req = app._request()
    req.params = replace(req.params, seed=lme.SEED)
    if lora:
        req.workflow = lora_workflow()
    if fac is not None:
        req.scale = fac
    return req


def check(p: str, req) -> list:
    mk, fn, _own, lora, fac = PASSES[p]
    bad = []
    if req.mode != fn:
        bad.append(f"mode {req.mode}, wanted {fn}")
    if lora and "restore-lora" not in str(req.workflow):
        bad.append("no LoRA workflow")
    if fac is not None and float(req.scale) != fac:
        bad.append(f"factor {req.scale}")
    if p == "f3-res-l" and req.turbo is not True:
        bad.append("Flux 3 Refine without its Restore LoRA")
    return bad


def main():
    lfc.setup()
    lme.BASE = lme.lsr.DATA / "refine-round3"
    lme.PASSES = PASSES
    lme.PASS_NAME = PASS_NAME
    lme.SECS = {p: 20 for p in PASSES}
    lme.jobs = jobs
    lme.window_request = window_request
    lme.check = check
    lme.summarize = lambda key, data: lfc.lme_summarize(key, data).replace("# MiniMax Edit Blindtest", "# Refine Runde 3 (Flux 3, Qwen), Blindtest")
    lme.main()


if __name__ == "__main__":
    main()
