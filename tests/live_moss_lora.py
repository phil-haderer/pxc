"""Manual check (not part of run_all.py): the new MOSS speed LoRA from lodestones/Kromoss blind (user 14.11., choice 2).

`opd-priming-8-steps-dmd-lora_cfg-ramp-neg_12000.safetensors` (lodestones/Kromoss/experimental) was distilled for the
OPD-priming Kromoss checkpoint; Kromoss has the same architecture as MOSS-Image-SFT, so it loads on our MOSS, but
nobody says how it looks there. Four variants on the same prompts and seeds, everything else as the plugin's start
settings for MOSS Text to image (no LLM, UltraReal and SLG off, like tests/live_moss_cfg.py):

    N8   new LoRA, 8 steps, CFG 1, euler / simple (the README's setup)
    N4   new LoRA, 4 steps, CFG 1, euler / simple ("ramp-neg" is the only kind that also works at 4 steps)
    D8   old Moss\\lora_dmd2.safetensors, 8 steps, CFG 1.5, the workflow's sa_solver / sgm_uniform
    B25  no LoRA, 25 steps, CFG 3.0 (the plugin's start values)

Rated blind in three pairings: N8 vs B25 (can the fast one replace the start values?), N8 vs D8 (better than the old
LoRA?), N4 vs N8 (is 4 steps enough?). The rating window is the one of live_moss_cfg.py.

    python tests\\live_moss_lora.py run [--prompts 5] [--seeds 2] [--size 1280]
    python tests\\live_moss_lora.py run --extra --into latest   (two interiors and a landscape, same round)
    python tests\\live_moss_lora.py rate          (the newest round; or give its folder)
    python tests\\live_moss_lora.py summary       (wins per pairing, also written to ergebnis.md)

Output: data\\moss-lora-test\\<time>\\ (pictures, key.json, bewertung.json, ergebnis.md). ComfyUI must have been
restarted after the LoRA was put into loras\\Moss; nothing in the plugin changes.
"""
import argparse
import json
import random
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import live_moss_cfg as cfgtest  # noqa: E402
from pccomfy import config as cfgmod, workflows  # noqa: E402
from pccomfy.bridge import Bridge, Request  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

BASE = cfgmod.CONFIG_DIR / "moss-lora-test"
WF = cfgtest.WF
SLG = cfgtest.SLG
LORA_NODE = "6"      # pc:lora of moss-image-t2i.json (the DMD2 loader)
NEW_LORA = "Moss\\opd-priming-8-steps-dmd-lora_cfg-ramp-neg_12000.safetensors"
OLD_LORA = "Moss\\lora_dmd2.safetensors"
# name -> (LoRA file or None, steps, cfg, sampler, scheduler); None for sampler/scheduler keeps the workflow's
VARIANTS = {
    "N8": (NEW_LORA, 8, 1.0, "euler", "simple"),
    "N4": (NEW_LORA, 4, 1.0, "euler", "simple"),
    "D8": (OLD_LORA, 8, 1.5, None, None),
    "B25": (None, 25, 3.0, None, None),
}
PAIRINGS = (("N8", "B25"), ("N8", "D8"), ("N4", "N8"))
# extra round (user 14.11.): very detailed interior photographs and a landscape with interesting features
EXTRA_PROMPTS = {
    "I1": ("Photograph of a cluttered watchmaker's workshop in an old town house, late afternoon window light from the "
           "left. A worn wooden workbench covered with brass gears, tiny screwdrivers, tweezers, a loupe and three open "
           "pocket watches under a green-shaded desk lamp; behind it shelves of small labeled drawers and a wall of "
           "pendulum clocks showing different times. Dust hangs in the light beam, the parquet floor is scuffed, a "
           "grey cat sleeps on a stool. 35 mm lens at eye level, natural colours, fine detail on metal and wood."),
    "I2": ("Photograph of a rustic farmhouse kitchen in the morning. Copper pots hang from a dark wooden beam; on the "
           "large oak table lie flour, a half-kneaded dough, brown eggs in a ceramic bowl, fresh herbs and a bread "
           "knife. A cast-iron stove with a steaming kettle, a wall of hand-painted blue and white tiles, a window "
           "with condensation and a view of a misty garden, and a small chalkboard with the handwritten words "
           "\"Milch, Eier, Butter\". Wide 24 mm shot, soft daylight, realistic textures."),
    "L1": ("Photograph of a high alpine valley at sunrise. A turquoise glacial lake in the foreground with smooth "
           "boulders and a wooden rowing boat pulled onto the shore, a small white stone chapel on a green ridge, a "
           "thin waterfall dropping from a cliff on the right, cows with bells grazing in the middle distance, and "
           "layered peaks with fresh snow and wisps of low cloud behind. Landscape photograph, crisp detail from "
           "front to back, natural colours."),
}
LABELS = {"N8": "neu 8 Schritte", "N4": "neu 4 Schritte", "D8": "altes DMD2 8 Schritte", "B25": "ohne LoRA 25 Schritte"}


def render(b, name, prompt, seed, size):
    lora, steps, cfg, sampler, scheduler = VARIANTS[name]
    over = {"steps": steps, "cfg": cfg}
    if sampler:
        over |= {"sampler": sampler, "scheduler": scheduler}
    req = Request(mode="txt2img", workflow=str(WF), enhance=False, turbo=lora is not None, stage_on=False,
                  stages_off=[SLG], sampler_override=over)
    p = workflows.GenParams(prompt=prompt, seed=seed, width=size, height=size)
    graph, out_node = b._graph(req, p, None, None, str(WF))
    if lora:
        node = graph.get(LORA_NODE)
        if not node or node.get("class_type") != "LoraLoaderModelOnly":
            sys.exit(f"Node {LORA_NODE} is not the LoRA loader any more; fix LORA_NODE.")
        node["inputs"]["lora_name"] = lora
    elif LORA_NODE in graph:
        sys.exit("The speed LoRA is still in the graph with turbo off.")
    hist = b._wait(b.comfy.queue(graph), graph, str(WF), 0, 1, "", lambda *x, **k: None)
    return b.comfy.output_images(hist, out_node)[0].convert("RGB")


def cmd_run(a):
    url = cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        sys.exit(f"ComfyUI is not running ({url}). Start it first.")
    comfy = ComfyUI(url)
    names = comfy.loras()
    if NEW_LORA not in names and NEW_LORA.replace("\\", "/") not in names:
        sys.exit(f"ComfyUI does not list {NEW_LORA}. Restart ComfyUI after the download.")
    if a.into:                      # add the extra prompts to an existing round (user 14.11.)
        cfgtest.BASE = BASE
        out = cfgtest.latest(None) if a.into == "latest" else Path(a.into)
        old = json.load(open(out / "key.json", encoding="utf-8"))
    else:
        out = BASE / time.strftime("%Y%m%d-%H%M%S")
        (out / "bilder").mkdir(parents=True)
        old = {"pairs": [], "items": {}, "prompts": {}}
    b = Bridge(cfgtest._NoPhotoCraft(), comfy, out / "xch")
    seeds = [101, 202, 303, 404][: max(1, a.seeds)]
    if a.extra:
        ps = dict(EXTRA_PROMPTS)
    else:
        ps = cfgtest.prompts()
        keep = list(ps)[:: max(1, len(ps) // max(1, a.prompts))][: a.prompts]   # evenly spread (user 14.11.: 5 of 10)
        ps = {k: ps[k] for k in keep}
    items, pairs, n, t_start = dict(old["items"]), [], 0, time.time()
    total = len(ps) * len(seeds) * len(VARIANTS)
    for num, prompt in ps.items():
        for seed in seeds:
            fids = {}
            for name in VARIANTS:
                n += 1
                t0 = time.time()
                im = render(b, name, prompt, seed, a.size)
                fid = f"{len(items) + 1:04d}"
                im.save(out / "bilder" / f"{fid}.png")
                lora, steps, cfg, *_ = VARIANTS[name]
                items[fid] = {"prompt_nr": num, "seed": seed, "variant": name, "steps": steps, "cfg": cfg, "model": ""}
                fids[name] = fid
                print(f"{n}/{total} prompt {num} seed {seed} {name}: {time.time() - t0:.0f} s", flush=True)
            pairs += [[fids[x], fids[y]] for x, y in PAIRINGS]
    rnd = random.Random(14 + len(old["pairs"]))
    for pair in pairs:
        rnd.shuffle(pair)                # which variant is left is hidden
    fb = out / "bewertung.json"
    rated = fb.exists() and any(r.get("wahl") for r in json.loads(fb.read_text(encoding="utf-8")).values())
    if rated:            # ratings are stored by pair index: keep the old order, the new pairs go to the end
        rnd.shuffle(pairs)
        pairs = old["pairs"] + pairs
    else:                # nothing rated yet: mix the new pairs in with the old ones
        pairs = old["pairs"] + pairs
        rnd.shuffle(pairs)
    json.dump({"title": "MOSS: Speed-LoRA blind vergleichen", "pairs": pairs, "items": items,
               "prompts": {**old["prompts"], **{str(k): v for k, v in ps.items()}}, "size": a.size},
              open(out / "key.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min: {len(items)} pictures, {len(pairs)} pairs in {out}\n"
          f"Next: python tests\\live_moss_lora.py rate", flush=True)


def cmd_rate(a):
    cfgtest.BASE = BASE          # the rating window of live_moss_cfg.py, on this test's rounds
    cfgtest.cmd_rate(a)


def cmd_summary(a):
    cfgtest.BASE = BASE
    out = cfgtest.latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    fout = out / "bewertung.json"
    data = json.loads(fout.read_text(encoding="utf-8")) if fout.exists() else {}
    items = key["items"]
    res = {pg: {pg[0]: 0, pg[1]: 0, "gleich": 0, "beide schlecht": 0} for pg in PAIRINGS}
    notes = []
    for rec in data.values():
        w = rec.get("wahl")
        if not w:
            continue
        l, r = items[rec["links"]]["variant"], items[rec["rechts"]]["variant"]
        pg = next(p for p in PAIRINGS if set(p) == {l, r})
        if w in ("links", "rechts"):
            res[pg][l if w == "links" else r] += 1
        else:
            res[pg][w] += 1
        if rec.get("notiz"):
            notes.append(f"- Prompt {items[rec['links']]['prompt_nr']} ({LABELS[l]} / {LABELS[r]}, Wahl {w}): {rec['notiz']}")
    rated = sum(1 for r in data.values() if r.get("wahl"))
    lines = [f"# MOSS Speed-LoRA-Testrunde {out.name}", "",
             f"Bewertet: {rated} von {len(key['pairs'])} Paaren ({key.get('size', '?')} px, ohne SLG, ohne LLM, "
             "UltraReal aus)", "", "| Paarung | A besser | B besser | gleich gut | beide schlecht |", "|---|---|---|---|---|"]
    for (x, y), c in res.items():
        lines.append(f"| A = {LABELS[x]}, B = {LABELS[y]} | {c[x]} | {c[y]} | {c['gleich']} | {c['beide schlecht']} |")
    if notes:
        lines += ["", "Notizen:"] + notes
    text = "\n".join(lines) + "\n"
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--prompts", type=int, default=5, help="how many of the ten prompts (evenly spread; user 14.11.: 5)")
    r.add_argument("--seeds", type=int, default=2, help="seeds per prompt (1 to 4)")
    r.add_argument("--extra", action="store_true", help="the extra prompts (EXTRA_PROMPTS: two interiors, a landscape)")
    r.add_argument("--into", help="add to this round's folder instead of a new one ('latest' = the newest)")
    r.add_argument("--size", type=int, default=1280, help="width and height in px (the plugin's base res. for MOSS)")
    for name in ("rate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("folder", nargs="?", help="the round's folder (default: the newest)")
    a = ap.parse_args()
    {"run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
