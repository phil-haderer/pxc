"""Manual check (not part of run_all.py): Fibo Text to image, our Edit Turbo file against Fibo 2.0 Dev, blind (user 20.11.).

Bria writes that Edit Turbo is meant for editing and Fibo 2.0 Dev for text to image (docs/tests/modellvarianten-ergebnis.md).
This round runs every prompt and seed once with our file (fibo2_edit_turbo_int8_convrot, 6 steps, CFG 1, the start
settings of Fibo Text to image) and once with fibo2_dev_int8_convrot as PxC runs it as a variant (pccomfy/variants.py:
30 steps, CFG 5, euler, simple; user 20.11.: 30 instead of the card's 50). Everything else is the plugin's start
settings (LLM writer off, 1216 px as in the LLM round of 30.10.). The user rates each pair blind (left / right in random
order) with the rating window of tests/live_fibo_llm.py; the time per picture is kept in key.json.

Six prompts of docs/tests/testprompts.md (user 20.11.: "6 prompts"): text, counting, position, face, motion, layout.

    python tests\\live_fibo_t2i_dev.py run [--seeds 2] [--size 1216] [--dry]
    python tests\\live_fibo_t2i_dev.py rate          (the newest round; or give its folder)
    python tests\\live_fibo_t2i_dev.py summary       (wins Turbo / Dev and the times, also written to ergebnis.md)

``--dry`` builds and checks all graphs (model file, steps, CFG, sampler, LLM off) without ComfyUI.
Output: data\\fibo-t2i-dev\\<time>\\ (bilder\\, key.json, bewertung.json, ergebnis.md).
Needs ComfyUI with both Fibo files; nothing in the plugin changes.
"""
import argparse
import json
import random
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_fibo_llm as lfl  # noqa: E402  (sets sys.path for pccomfy)

from pccomfy import config as cfgmod, variants, workflows  # noqa: E402
from pccomfy.bridge import Bridge, Request  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "fibo-t2i-dev"
WF = lfl.WF
TURBO = "fibo2_edit_turbo_int8_convrot.safetensors"
DEV = "fibo2_dev_int8_convrot.safetensors"
PROMPTS = [1, 40, 55, 73, 90, 180]
EXPECT = {False: (TURBO, 6, 1.0), True: (DEV, 30, 5.0)}       # (file, steps, CFG) of each side


def label(it: dict) -> str:
    return "Dev" if it["dev"] else "Edit Turbo"


# the rating window and the summary of the LLM round, with this round's folder, names and title
lfl.BASE, lfl.label = BASE, label
lfl.TITLE = "Fibo Text to image: Edit Turbo gegen Dev blind vergleichen"
lfl.HEADING = "Fibo Text to image, Edit Turbo gegen Dev:"


def prompts() -> dict[int, str]:
    old = lfl.PROMPTS
    lfl.PROMPTS = PROMPTS
    try:
        return lfl.prompts()
    finally:
        lfl.PROMPTS = old


def build(b, prompt: str, seed: int, size: int, dev: bool):
    """The graph the plugin sends for Fibo Text to image (start settings), with the Dev file as PxC runs a variant."""
    req = Request(mode="txt2img", workflow=str(WF), enhance=False, variant=DEV if dev else "")
    p = workflows.GenParams(prompt=prompt, seed=seed, width=size, height=size)
    graph, out = Bridge._graph(b, req, p, None, None, str(WF), force_plain=True)
    if dev:                     # what inventory.apply_names does when the user links the Dev file (Model Links)
        for node in graph.values():
            if isinstance(node, dict) and node.get("class_type") == "UNETLoader":
                node["inputs"]["unet_name"] = DEV
    ks = graph[workflows.main_sampler(graph)]["inputs"]
    unets = variants.unet_names(graph)
    want = EXPECT[dev]
    assert (unets, ks["steps"], float(ks["cfg"]), ks["sampler_name"], ks["scheduler"]) == ([want[0]], want[1], want[2], "euler", "simple"), \
        (unets, ks["steps"], ks["cfg"], ks["sampler_name"], ks["scheduler"])
    assert not workflows.prompt_writers(graph) or all(
        n.get("mode") == 4 for nid, n in graph.items() if nid in workflows.prompt_writers(graph)), "LLM writer must be off"
    return graph, out


def cmd_run(a):
    seeds = [101, 202, 303, 404][: max(1, a.seeds)]
    ps = prompts()
    if a.dry:
        b = Bridge.__new__(Bridge)
        for num, prompt in ps.items():
            for seed in seeds:
                for dev in (False, True):
                    build(b, prompt, seed, a.size, dev)
        print(f"dry: {len(ps)} prompts x {len(seeds)} seeds x 2 = {len(ps) * len(seeds) * 2} graphs ok "
              f"(Turbo 6 steps CFG 1, Dev 30 steps CFG 5, LLM off, {a.size} px)")
        return
    url = cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        sys.exit(f"ComfyUI is not running ({url}). Start it first.")
    out = BASE / time.strftime("%Y%m%d-%H%M%S")
    (out / "bilder").mkdir(parents=True)
    b = Bridge(lfl._NoPhotoCraft(), ComfyUI(url), out / "xch")
    known = set(b.comfy._choices("UNETLoader", "unet_name"))
    missing = [f for f in (TURBO, DEV) if f not in known]
    if missing:
        sys.exit(f"Not in ComfyUI's list: {', '.join(missing)}")
    key, pairs, n, t_start = {}, [], 0, time.time()
    total = len(ps) * len(seeds) * 2
    for num, prompt in ps.items():
        for seed in seeds:
            pair = []
            for dev in (False, True):
                n += 1
                t0 = time.time()
                graph, out_node = build(b, prompt, seed, a.size, dev)
                hist = b._wait(b.comfy.queue(graph), graph, str(WF), 0, 1, "", lambda *x, **k: None)
                im = b.comfy.output_images(hist, out_node)[0].convert("RGB")
                fid = f"{len(key) + 1:04d}"
                im.save(out / "bilder" / f"{fid}.png")
                secs = round(time.time() - t0, 1)
                key[fid] = {"prompt_nr": num, "seed": seed, "dev": dev, "sekunden": secs}
                pair.append(fid)
                print(f"{n}/{total} prompt {num} seed {seed} {label(key[fid])}: {secs:.0f} s", flush=True)
            pairs.append(pair)
    rnd = random.Random(7)
    rnd.shuffle(pairs)
    for pair in pairs:
        rnd.shuffle(pair)                # which one is Dev is hidden
    json.dump({"pairs": pairs, "items": key, "prompts": ps, "size": a.size},
              open(out / "key.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min: {len(key)} pictures in {out}\n"
          f"Next: python tests\\live_fibo_t2i_dev.py rate", flush=True)


def cmd_summary(a):
    lfl.cmd_summary(a)
    out = lfl.latest(a.folder)
    items = json.load(open(out / "key.json", encoding="utf-8"))["items"].values()
    lines = ["", "Zeit je Bild (mit Laden, Mittel):", ""]
    for dev in (False, True):
        t = [it["sekunden"] for it in items if it["dev"] == dev and "sekunden" in it]
        if t:
            lines.append(f"- {label({'dev': dev})}: {sum(t) / len(t):.0f} s ({len(t)} Bilder)")
    text = "\n".join(lines) + "\n"
    with open(out / "ergebnis.md", "a", encoding="utf-8") as f:
        f.write(text)
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seeds", type=int, default=2, help="seeds per prompt (1 to 4)")
    r.add_argument("--size", type=int, default=1216, help="width and height in px")
    r.add_argument("--dry", action="store_true", help="build and check the graphs only, no ComfyUI")
    for name in ("rate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("folder", nargs="?", help="the round's folder (default: the newest)")
    a = ap.parse_args()
    {"run": cmd_run, "rate": lfl.cmd_rate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
