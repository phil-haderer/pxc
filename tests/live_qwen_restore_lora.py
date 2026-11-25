"""Manual check (not part of run_all.py): Qwen Image 2.1 Refine with ausboss' Restore LoRA (user 22.11.: "get this lora for
qwen and test it in a run", huggingface.co/ausboss/Qwen-Image-2.1-Restore-LoRA, file qwen-image-2.1-restore.safetensors,
step 1500, in the LoRA folder under qwen\\). Its card: strength 1.0 for a small or compressed picture in focus, 0.5 for a
blurry one; its own request "Restore the photo: ...". The LoRA sits after the Turbo LoRA of qwen-image-21-refine.json
(title not pc:lora, so the Turbo switch does not touch it). On the six photos of MiniMax Refine round 2, seed 1234, blind:

    q-r10     LoRA 1.0, Qwen's Default prompt
    q-r05     LoRA 0.5, Qwen's Default prompt
    q-r10p    LoRA 1.0, the card's request

3 x 6 = 18 pictures; compare: Qwen Refine without the LoRA 3 of 6 (docs/tests/qwen-prompt-kurz-ergebnis.md).

    python tests\\live_qwen_restore_lora.py run [--photos <folder>] [--passes ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_qwen_restore_lora.py rate [folder]
    python tests\\live_qwen_restore_lora.py summary [folder]

Output: data\\qwen-restore-lora\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md, wf\\).
"""
import json
from dataclasses import replace

import live_flux_refine_compare as lfc   # the photos and the round machinery of the Flux comparison

from pccomfy import models

lme = lfc.lme
LORA = "qwen\\qwen-image-2.1-restore.safetensors"
QWEN_B = ("A sharper, cleaner version of the same image: clean detail and texture, the same style, composition, colors "
          "and light.")
CARD = ("Restore the photo: remove blur, noise and compression artifacts and recover sharp, natural detail, keeping the "
        "same composition, people and colors.")
PASSES = {   # pass -> (model key, LoRA strength, prompt or None = Qwen's Default); live_minimax_edit reads [0] as the model
    "q-r10": ("qwen", 1.0, None),
    "q-r05": ("qwen", 0.5, None),
    "q-r10p": ("qwen", 1.0, CARD),
    "q-r10b": ("qwen", 1.0, QWEN_B),   # user 22.11.: also with prompt B of refine round 3 (5 of 6 there)
}
PASS_NAME = {"q-r10": "Qwen Refine + Restore-LoRA 1.0", "q-r05": "Qwen Refine + Restore-LoRA 0.5",
             "q-r10p": "Qwen Refine + Restore-LoRA 1.0, Prompt der Modellkarte",
             "q-r10b": "Qwen Refine + Restore-LoRA 1.0, Prompt B"}


def lora_workflow(strength: float) -> str:
    g = json.loads((lme.lsr.ROOT / "workflows" / "qwen-image-21-refine.json").read_text(encoding="utf-8"))
    sampler = next(k for k, v in g.items() if isinstance(v, dict) and v.get("_meta", {}).get("title", "").startswith("pc:sampler"))
    g["20"] = {"class_type": "LoraLoaderModelOnly", "_meta": {"title": "Restore LoRA (test)"},
               "inputs": {"lora_name": LORA, "strength_model": strength, "model": g[sampler]["inputs"]["model"]}}
    g[sampler]["inputs"]["model"] = ["20", 0]
    out = lme.BASE / "wf" / f"qwen-image-21-refine-restore-{int(strength * 100)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
    return str(out)


def jobs(passes) -> list:
    return [(p, n, ph, PASSES[p][2] or models.QWEN_UPSCALE_DEFAULT) for p in passes for n, ph in enumerate(lfc.lmr.PHOTOS, 1)]


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
    req.workflow = lora_workflow(PASSES[p][1])
    return req


def check(p: str, req) -> list:
    bad = [] if req.mode == "refine" else [f"mode {req.mode}"]
    g = json.loads(open(req.workflow, encoding="utf-8").read())
    if g.get("20", {}).get("inputs", {}).get("strength_model") != PASSES[p][1]:
        bad.append("LoRA strength")
    return bad


def main():
    lfc.setup()
    lme.BASE = lme.lsr.DATA / "qwen-restore-lora"
    lme.PASSES = PASSES
    lme.PASS_NAME = PASS_NAME
    lme.SECS = {p: 25 for p in PASSES}
    lme.jobs = jobs
    lme.window_request = window_request
    lme.check = check
    lme.summarize = lambda key, data: lfc.lme_summarize(key, data).replace("# MiniMax Edit Blindtest", "# Qwen Refine mit Restore-LoRA, Blindtest")
    lme.main()


if __name__ == "__main__":
    main()
