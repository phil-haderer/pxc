"""Known variants of the main diffusion models: other files of the same model that PxC runs with their own settings
(user 20.11., docs/plan/entscheidungen.md "Modellvarianten"; values and sources: docs/tests/modellvarianten-ergebnis.md).

Rules:
- When our int8 ConvRot file and a variant both lie in ComfyUI's folder, PxC takes ours. The variant runs when the user
  picks it in Model Links, or when it is the only file there (its name is an alias of ours, see manifest.FILES); an
  untested variant (``alias=False``; none at the moment) only when it is picked.
- The variant's values stand visibly in the window's fields (Steps, CFG, Sampler, Scheduler). A variant with the speed
  LoRA built in (Qwen 2.1 Turbo) switches the window's LoRA off and greys it out.
- A fixed sigma schedule (Qwen Turbo, the official ComfyUI template) replaces the sampler's own steps only at full denoise;
  Refine and Upscale (denoise below 1) run the same file with 8 steps, euler, simple. Modes in ``plain_modes`` also run
  with 8 steps, euler, simple (Qwen Turbo in Expand: the schedule gave green hatching in the new part, user 20.11., A).

Plain data and small graph helpers, so the tests run without ComfyUI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

QWEN_TURBO_SIGMAS = "1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0"   # image_qwen_image_2_1_turbo_t2i.json


@dataclass(frozen=True)
class Variant:
    file: str                       # the variant's file name (as Comfy-Org publishes it)
    base: str                       # our file it can stand in for (manifest name)
    label: str                      # short name for tooltips and the run log
    values: dict = field(default_factory=dict)      # sampler values with the speed LoRA on (or without a LoRA switch)
    values_no_lora: dict = field(default_factory=dict)   # with the LoRA switched off (empty = the workflow's own pc_no_lora values)
    lora_off: bool = False          # the speed LoRA is built into the file: the window's LoRA is off and greyed out
    sigmas: str = ""                # a fixed sigma schedule (ManualSigmas) at full denoise; "" = the sampler's own scheduler
    tip: str = ""                   # tooltip of the greyed-out LoRA box / Steps field
    plain_modes: tuple = ()         # modes that skip the sigma schedule and run the plain values (steps, sampler, scheduler)
    alias: bool = True              # counts as our file when ours is missing; False = only when linked in Model Links (untested)


VARIANTS: tuple[Variant, ...] = (
    Variant("qwen_image_2.1_turbo_int8_convrot.safetensors", "qwen_image_2.1_int8_convrot.safetensors", "Qwen Image 2.1 Turbo",
            values={"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}, lora_off=True, sigmas=QWEN_TURBO_SIGMAS,
            plain_modes=("outpaint",), tip="Turbo is built into this file"),
    Variant("moss_image_base_int8_convrot.safetensors", "moss_image_sft_int8_convrot.safetensors", "MOSS Image Base",
            values={"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}),   # with DMD2; without: our SFT values (user 20.11.)
    # Kromoss (lodestones/Kromoss): a full fine-tune of MOSS Image Base, same layout, text encoder and VAE (user 20.11.);
    # its card: 8 steps, CFG 1, euler/simple with the 8-step DMD2 LoRA; without it our SFT values, as MOSS Base
    Variant("kromoss_int8_convrot.safetensors", "moss_image_sft_int8_convrot.safetensors", "Kromoss",
            values={"steps": 8, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}),
    Variant("fibo2_dev_int8_convrot.safetensors", "fibo2_edit_turbo_int8_convrot.safetensors", "Fibo 2.0 Dev",
            values={"steps": 30, "cfg": 5.0, "sampler": "euler", "scheduler": "simple"}),  # card: 50 steps; user 20.11.: 30
    Variant("krea2_turbo_fp8.safetensors", "krea2_turbo_int8_convrot.safetensors", "Krea 2 Turbo fp8"),
    # tested 21.11. on PC A (Text to image and Edit, same pictures and speed as ours): unlocks MiniMax again (user 21.11., 4A)
    Variant("minimax_h3_image_pruned_w4a8.safetensors", "minimax_h3_image_pruned_int8_convrot.safetensors", "MiniMax H3 Image w4a8"),
)


def _bare(name: str) -> str:
    """File name without folder, case and separator tolerant (as inventory.norm, then the last part)."""
    return str(name or "").replace("\\", "/").strip().lower().rpartition("/")[2]


BY_FILE = {_bare(v.file): v for v in VARIANTS}


def aliases_of(base: str) -> tuple:
    """The variant file names that count as ``base`` when ``base`` itself is missing (manifest adds them as aliases); an
    untested one (``alias`` False) only runs when it is linked in Model Links."""
    return tuple(v.file for v in VARIANTS if v.base == base and v.alias)


def get(name: str) -> Variant | None:
    """The variant a file name ComfyUI lists belongs to (any sub-folder), None for our own file or an unknown one."""
    return BY_FILE.get(_bare(name)) if name else None


def unet_names(graph: dict) -> list[str]:
    """The diffusion model files a workflow loads (UNETLoader)."""
    return [n["inputs"]["unet_name"] for n in graph.values() if isinstance(n, dict) and n.get("class_type") == "UNETLoader"
            and isinstance(n.get("inputs", {}).get("unet_name"), str)]


def in_use(graph: dict, found) -> Variant | None:
    """The variant this workflow will really run with: ``found(name)`` gives the file ComfyUI lists for one of our files
    (Inventory.found: the user's link, our file, or an alias); None = our own file (or nothing known)."""
    for name in unet_names(graph):
        try:
            real = found(name)
        except Exception:
            real = None
        v = get(real) if real else None
        if v is not None and v.base == name:
            return v
    return None


def sigmas_for(v: Variant | None, mode: str) -> str:
    """The fixed sigma schedule this variant runs in ``mode`` ("" = the sampler's own steps and scheduler)."""
    if v is None or not v.sigmas or mode in ("upscale", "refine") or mode in v.plain_modes:
        return ""
    return v.sigmas


def sampler_values(v: Variant, lora_on: bool) -> dict:
    """The values the variant runs with (an empty dict = the workflow's own)."""
    if v.lora_off or lora_on:
        return dict(v.values)
    return dict(v.values_no_lora)


def use_manual_sigmas(graph: dict, nid: str, sigmas: str, sampler: str = "euler") -> bool:
    """Turn the KSampler ``nid`` into SamplerCustom with a fixed sigma schedule (ManualSigmas) and KSamplerSelect, keeping
    its model, conditioning, latent, seed and CFG. Only at full denoise; returns False (graph unchanged) otherwise."""
    node = graph.get(nid)
    if not isinstance(node, dict) or node.get("class_type") != "KSampler":
        return False
    ks = node.get("inputs", {})
    try:
        if abs(float(ks.get("denoise", 1.0)) - 1.0) > 1e-6:
            return False
    except (TypeError, ValueError):
        return False
    sel, sig = f"{nid}_pcv_sel", f"{nid}_pcv_sig"
    graph[sel] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": ks.get("sampler_name") or sampler},
                  "_meta": {"title": "Variant sampler"}}
    graph[sig] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}, "_meta": {"title": "Variant sigma schedule"}}
    graph[nid] = {"class_type": "SamplerCustom", "_meta": json.loads(json.dumps(node.get("_meta", {}))), "inputs": {
        "model": ks["model"], "add_noise": True, "noise_seed": ks.get("seed", 0), "cfg": ks.get("cfg", 1.0),
        "positive": ks["positive"], "negative": ks["negative"], "sampler": [sel, 0], "sigmas": [sig, 0],
        "latent_image": ks["latent_image"]}}
    return True
