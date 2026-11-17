"""Manual check (not part of run_all.py): do pictures stay the same with ComfyUI's start option --use-ck-attention
(Comfy Kitchen attention)? Follow-up of tests/live_llm_tempo.py (user 13.11.: "Erst Bilder prüfen").

Text to image of every model with its own workflow (prompt writer off, typed prompt, the model's start settings), the same
prompts and seeds in both passes; time per picture.

    python tests\\live_ck_images.py run          one pass on the running ComfyUI; label (normal / ck) from its start options
    python tests\\live_ck_images.py compare      differences (PSNR), sheets A | B | difference, and the A/B page data\\ck-bilder.html
    add --dry to `run` to only build the graphs and check every file is known to ComfyUI.
    --cases flux3,flux2,qwen,moss,fibo picks models.

Output: data\\ck-images\\<label>\\ (pictures, times.json), data\\ck-images\\report.md, data\\ck-bilder.html. Nothing in the plugin changes.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

from pccomfy.comfy import ComfyUI  # noqa: E402
from live_flux2_file_compare import psnr, sheet  # noqa: E402
from live_llm_tempo import comfy_info  # noqa: E402
from live_writer_compare import picture_graph, run_picture  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "ck-images"
CASES = {"flux3": ("Flux 3", "flux3-klein-t2i.json"), "flux2": ("Flux 2", "flux2-klein-t2i.json"),
         "qwen": ("Qwen Image 2.1", "qwen-image-21-t2i.json"), "moss": ("MOSS", "moss-image-t2i.json"),
         "fibo": ("Fibo", "fibo2-t2i.json")}
PROMPTS = [
    "A close-up portrait of an old fisherman with a weathered face and a grey wool cap, soft window light, "
    "a small sign on the wall behind him reads \"HARBOUR 1952\"",
    "A cosy reading corner with a green velvet armchair, a tall bookshelf, a sleeping tabby cat and warm evening sunlight",
]
SEED = 101


def missing_files(c: ComfyUI, graph: dict) -> list[str]:
    """Values of loader inputs that ComfyUI's lists do not hold (model files absent on this PC)."""
    miss = []
    for node in graph.values():
        ct = node.get("class_type", "")
        if "Loader" not in ct:
            continue
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, str) and v.endswith((".safetensors", ".gguf", ".pth", ".ckpt", ".pt")):
                try:
                    have = c._choices(ct, k)
                except Exception:
                    continue
                if have and v not in have:
                    miss.append(f"{ct}.{k}: {v}")
    return miss


def build(case: str) -> list[tuple[str, dict, str]]:
    wf = CASES[case][1]
    return [(f"{case}_{i + 1}", *picture_graph(wf, p, SEED)) for i, p in enumerate(PROMPTS)]


def cmd_run(a):
    c = ComfyUI()
    cases = [x.strip() for x in a.cases.split(",") if x.strip()]
    built, skip = {}, {}
    for case in cases:
        if case not in CASES:
            raise SystemExit(f"unknown case {case!r}; known: {', '.join(CASES)}")
        b = build(case)
        miss = sorted({m for _, g, _ in b for m in missing_files(c, g)})
        if miss:
            skip[case] = miss
        else:
            built[case] = b
    for case, miss in skip.items():
        print(f"skip {case}: files missing on this PC: {'; '.join(miss)}")
    if a.dry:
        print("ok: graphs build; runnable:", ", ".join(f"{k} ({len(v)})" for k, v in built.items()) or "none")
        return
    info = comfy_info(c)
    label = "ck" if "--use-ck-attention" in info["argv"] else "normal"
    out = OUT / label
    out.mkdir(parents=True, exist_ok=True)
    print(f"pass '{label}': ComfyUI {info['version']}, {info['gpu']}, start options {' '.join(info['argv'][1:])}")
    res = {"label": label, "when": time.strftime("%Y-%m-%d %H:%M"), "comfy": info, "skipped": skip, "pictures": {}}
    for case, items in built.items():
        for k, (name, g, node) in enumerate(items):
            img, sec = run_picture(c, g, node)
            img.save(out / f"{name}.png")
            res["pictures"][name] = {"sec": round(sec, 1), "first": k == 0, "size": list(img.size)}
            print(f"  {name:8s} {sec:6.1f} s{'  (with model load)' if k == 0 else ''}")
            (out / "times.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {out}")


def rel(p: Path) -> str:
    return os.path.relpath(p, DATA).replace("\\", "/")


def cmd_compare(a):
    t = {k: json.loads((OUT / k / "times.json").read_text(encoding="utf-8")) for k in ("normal", "ck") if (OUT / k / "times.json").exists()}
    if len(t) < 2:
        raise SystemExit("need both passes: data\\ck-images\\normal and ck")
    (OUT / "sheets").mkdir(exist_ok=True)
    (OUT / "thumbs").mkdir(exist_ok=True)
    lines = [f"# Bilder mit und ohne `--use-ck-attention`, ComfyUI {t['normal']['comfy']['version']}, {t['normal']['comfy']['gpu']}", "",
             f"Seed {SEED}, Prompt-Schreiber aus. Zeit beim ersten Bild je Modell mit Laden.", "",
             "| Bild | ohne (s) | mit CK (s) | mittlere Abweichung (0–255) | PSNR (dB) |", "|---|---|---|---|---|"]
    page = []
    for name, rn in t["normal"]["pictures"].items():
        rk = t["ck"]["pictures"].get(name)
        if not rk:
            continue
        pa, pb = OUT / "normal" / f"{name}.png", OUT / "ck" / f"{name}.png"
        ia, ib = Image.open(pa).convert("RGB"), Image.open(pb).convert("RGB")
        mad, db = psnr(ia, ib) if ia.size == ib.size else (float("nan"), float("nan"))
        if ia.size == ib.size:
            sheet(ia, ib).save(OUT / "sheets" / f"{name}.jpg", quality=90)
        lines.append(f"| {name} | {rn['sec']:.1f} | {rk['sec']:.1f} | {mad:.1f} | {db:.1f} |")
        imgs = []
        for lab, p, im in (("ohne CK", pa, ia), ("mit CK", pb, ib)):
            th = OUT / "thumbs" / f"{name}_{'ck' if lab == 'mit CK' else 'normal'}.jpg"
            s = im.copy()
            s.thumbnail((120, 90), Image.LANCZOS)
            s.save(th, quality=85)
            imgs.append({"label": f"{lab} ({im.width}x{im.height})", "short": lab, "src": rel(p), "thumb": rel(th),
                         "prompt": PROMPTS[int(name.rsplit('_', 1)[1]) - 1], "id": f"{name}-{lab}"})
        page.append({"title": f"{CASES[name.rsplit('_', 1)[0]][0]}, Bild {name.rsplit('_', 1)[1]}", "images": imgs})
    lines += ["", "PSNR über etwa 35 dB: kaum sichtbar; unter etwa 20 dB: ein anderes Bild (gleiches Motiv, andere Details)."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    html = (ROOT / "tools" / "ab_viewer_template.html").read_text(encoding="utf-8").replace("__SETS__", json.dumps(page, ensure_ascii=False))
    (DATA / "ck-bilder.html").write_text(html, encoding="utf-8")
    print("\n".join(lines[4:-2]))
    print(f"written: {OUT / 'report.md'} and {DATA / 'ck-bilder.html'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "compare"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    cmd_run(a) if a.cmd == "run" else cmd_compare(a)


if __name__ == "__main__":
    main()
