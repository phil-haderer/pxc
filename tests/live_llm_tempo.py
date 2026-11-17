"""Manual check (not part of run_all.py): how fast do the prompt writers and Describe run on ComfyUI 0.45,
with and without the start option --use-ck-attention (Comfy Kitchen attention)? (testrunden.md Kurzliste 7, user 13.11.: on PC B)

Only the text steps run (no pictures). Every case: one warm-up run (model load, not counted), then the measured runs.
The same prompts and seeds in both passes, so equal texts mean the time ratio is the speed-up.

    python tests\\live_llm_tempo.py run          one pass on the running ComfyUI; the label (normal / ck) comes from its start options
    python tests\\live_llm_tempo.py compare      report from the two passes: data\\llm-tempo\\report.md
    add --dry to `run` to only build the graphs and check the files are known to ComfyUI.
    --cases flux3,qwen,flux2,fibo,describe picks cases; --n 3 the number of measured runs per case.

Output: data\\llm-tempo\\<label>.json (texts, seconds, ComfyUI version, start options) and report.md. Nothing in the plugin changes.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from pccomfy.comfy import ComfyUI  # noqa: E402
from live_writer_compare import describe_graph, known, prompts, run_text, writer_graph  # noqa: E402

OUT = ROOT / "data" / "llm-tempo"
DESCRIBE_IMAGES = ["Cat.jpeg", "Architecture.png", "DancerInWhite.png"]
# case: (label, workflow, text model file, CLIP type); W4A8 is what the ComfyUI speed-up names, int8 ConvRot is the control
CASES = {
    "flux3": ("Flux 3 Enhance (Prompt Upsampler 9B W4A8)", "flux3-klein-t2i.json",
              "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors", "flux3"),
    "qwen": ("Qwen Image 2.1 Enhance (Qwen3.5 9B W4A8 GPTQ)", "qwen-image-21-t2i.json",
             "qwen3.5_9b_w4a8_gptq.safetensors", "moss_image"),
    "flux2": ("Flux 2 Enhance (Qwen3-VL 4B int8 ConvRot)", "flux2-klein-t2i.json",
              "qwen3vl_4b_int8_convrot.safetensors", "stable_diffusion"),
    "fibo": ("Fibo Enhance (Qwen3-VL 4B int8 ConvRot)", "fibo2-t2i.json",
             "qwen3vl_4b_int8_convrot.safetensors", "stable_diffusion"),
    "describe": ("Describe (Qwen3.5 9B int8 ConvRot)", "describe-image.json",
                 "qwen3.5_9b_int8_convrot.safetensors", "stable_diffusion"),
}


def graphs(case: str, n: int) -> list[tuple[str, dict, str]]:
    """[(name, graph, output node)]: the first one is the warm-up (different input, so ComfyUI's cache never answers a measured one)."""
    _, wf, clip, ctype = CASES[case]
    if case == "describe":
        out = []
        for i, img in enumerate([DESCRIBE_IMAGES[0]] + DESCRIBE_IMAGES[:n]):
            g, node = describe_graph(clip, img)
            if i == 0:
                g["3"]["inputs"]["max_length"] = 199        # warm-up: another input than the measured run of the same picture
            out.append(("warm-up" if i == 0 else img, g, node))
        return out
    ps = prompts(n + 1)
    out = []
    for i, p in enumerate([ps[-1]] + ps[:n]):
        g, node = writer_graph(wf, clip, ctype, p, seed=3 if i == 0 else 7)
        out.append(("warm-up" if i == 0 else f"prompt {i}", g, node))
    return out


def comfy_info(c: ComfyUI) -> dict:
    import urllib.request
    with urllib.request.urlopen(c.url + "/system_stats", timeout=10) as r:
        s = json.load(r)
    sysd = s.get("system", {})
    dev = (s.get("devices") or [{}])[0]
    return {"version": sysd.get("comfyui_version"), "argv": sysd.get("argv", []), "gpu": dev.get("name"),
            "vram_mb": int(dev.get("vram_total", 0)) // 2 ** 20}


def cmd_run(a):
    c = ComfyUI()
    cases = [x.strip() for x in a.cases.split(",") if x.strip()]
    for case in cases:
        if case not in CASES:
            raise SystemExit(f"unknown case {case!r}; known: {', '.join(CASES)}")
    known(c, *sorted({CASES[x][2] for x in cases}))
    built = {case: graphs(case, a.n) for case in cases}
    if a.dry:
        print("ok: files known to ComfyUI, graphs build:", ", ".join(f"{k} ({len(v)})" for k, v in built.items()))
        return
    info = comfy_info(c)
    label = "ck" if "--use-ck-attention" in info["argv"] else "normal"
    print(f"pass '{label}': ComfyUI {info['version']}, {info['gpu']}, start options {' '.join(info['argv'][1:])}")
    res = {"label": label, "when": time.strftime("%Y-%m-%d %H:%M"), "comfy": info, "cases": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    for case in cases:
        rows = []
        for name, g, node in built[case]:
            text, sec = run_text(c, g, node)
            rows.append({"name": name, "sec": round(sec, 2), "words": len(text.split()), "chars": len(text), "text": text})
            print(f"  {case:9s} {name:16s} {sec:7.1f} s  {len(text.split()):5d} words")
        res["cases"][case] = rows
        (OUT / f"{label}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {OUT / (label + '.json')}")


def cmd_compare(a):
    p = {k: json.loads((OUT / f"{k}.json").read_text(encoding="utf-8")) for k in ("normal", "ck") if (OUT / f"{k}.json").exists()}
    if len(p) < 2:
        raise SystemExit("need both passes: data\\llm-tempo\\normal.json and ck.json")
    n, k = p["normal"], p["ck"]
    lines = [f"# LLM-Tempo, ComfyUI {n['comfy']['version']}, {n['comfy']['gpu']} ({n['comfy']['vram_mb']} MB)", "",
             f"Ohne Startoption: {n['when']}; mit `--use-ck-attention`: {k['when']}. Ohne Aufwärmlauf (Modell laden).", "",
             "| Fall | Lauf | ohne (s) | mit CK (s) | Faktor | Wörter ohne / mit | Text gleich |", "|---|---|---|---|---|---|---|"]
    summary = []
    for case, rows in n["cases"].items():
        krows = {r["name"]: r for r in k["cases"].get(case, [])}
        tn = tk = 0.0
        for r in rows:
            if r["name"] == "warm-up" or r["name"] not in krows:
                continue
            q = krows[r["name"]]
            tn, tk = tn + r["sec"], tk + q["sec"]
            lines.append(f"| {CASES[case][0]} | {r['name']} | {r['sec']:.1f} | {q['sec']:.1f} | {r['sec'] / max(q['sec'], 0.01):.2f} | "
                         f"{r['words']} / {q['words']} | {'ja' if r['text'] == q['text'] else 'nein'} |")
        if tk:
            summary.append(f"- {CASES[case][0]}: {tn:.1f} s ohne, {tk:.1f} s mit CK, Faktor {tn / tk:.2f}")
    lines += ["", "## Summe je Fall", ""] + summary + ["", "Faktor über 1 = mit `--use-ck-attention` schneller."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"written: {OUT / 'report.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "compare"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    cmd_run(a) if a.cmd == "run" else cmd_compare(a)


if __name__ == "__main__":
    main()
