"""Manual GPU run (not part of run_all.py): the GPU probe of A+ (user 20.11., docs/plan/entscheidungen.md "Edit/Sketch-Stile
heißen wie in Text to image, A+"). The Edit canvas and Sketch to image styles whose sentence changed with their new name
run once on the owl photo (Edit canvas) and once on the owl sketch (Sketch to image) of data\\style-thumbs\\eingabe\\,
with Qwen Image 2.1 through the real plugin path (live_style_thumbs: the window's request with Qwen's start settings, the
bridge with the PhotoCraft simulator, the real ComfyUI).

    python tests\\live_style_probe.py run [--seed N] [--url ...]
    python tests\\live_style_probe.py view

Output: data\\style-thumbs\\probe-a-plus\\<mode>-<slug>.png and vergleich.html (input left, the styles beside it, at 100 %
on a click). Seed 13667396: with the owl photo Qwen Edit gave a broken picture at seed 1234 (20.11.).
"""
import argparse
import html
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_style_thumbs as lt  # noqa: E402  (sets its own PCCOMFY_HOME first)
from PIL import Image  # noqa: E402

import live_sketch  # noqa: E402
from pccomfy import models, styles  # noqa: E402

CHANGED = ["Product photo, glass on white", "Oil painting, 19th-century realism", "Impressionist painting, sunny",
           "Black and white, hard light and shadows", "Cyanotype blue print, glowing", "Claymation, stop-motion",
           "Voxel diorama, pastel"]
INPUT = {"edit": "owl-photo.png", "sketch": "owl-sketch.png"}
OUT = lt.OUT / "probe-a-plus"
SEED = 13667396


def jobs() -> list:
    """[(mode, name, text)] of the changed styles in each mode that has them."""
    out = []
    for mode in ("edit", "sketch"):
        have = {s["name"]: s["text"] for g in styles.load().get(mode, []) for s in g["styles"]}
        missing = [n for n in CHANGED if n not in have and not (mode == "edit" and n in ("Claymation, stop-motion",
                                                                                         "Voxel diorama, pastel"))]
        if missing:
            sys.exit(f"{mode}: not in styles.json: {missing}")
        out += [(mode, n, have[n].replace(models.SKETCH_MARK, lt.OWL)) for n in CHANGED if n in have]
    return out


def request(app, mode: str, text: str, seed: int):
    app.v_model.set(lt.MODEL)
    app.v_mode.set(mode)
    app._factory = True
    try:
        app._on_model()
        app._on_mode()
    finally:
        app._factory = False
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", text)
    req = app._request()
    req.enhance = False
    req.params = lt.replace(req.params, seed=seed)
    return req


def cmd_run(a):
    comfy, url = lt.connect(a)
    app = live_sketch.make_app(url)
    xch = Path(tempfile.mkdtemp(prefix="pccomfy-probe-xch-"))
    OUT.mkdir(parents=True, exist_ok=True)
    rows, bad, t0 = jobs(), 0, time.time()
    for k, (mode, name, text) in enumerate(rows, 1):
        pic = Image.open(lt.OUT / "eingabe" / INPUT[mode]).convert("RGB")
        t1 = time.time()
        try:
            im = lt.run_one(comfy, request(app, mode, text, a.seed), pic, xch)
        except Exception as e:                # one failing picture must not stop the run
            bad += 1
            print(f"{k}/{len(rows)} {mode} {name}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        im.save(OUT / f"{mode}-{styles.slug(name)}.png")
        print(f"{k}/{len(rows)} {mode} {name}: {time.time() - t1:.0f} s", flush=True)
    app.root.destroy()
    print(f"\nDONE in {(time.time() - t0) / 60:.1f} min: {len(rows)} pictures, {bad} failed", flush=True)
    cmd_view(a)
    return bad


def cmd_view(a):
    parts = ["<!doctype html><meta charset='utf-8'><title>A+ probe</title><style>"
             "body{background:#282828;color:#e6e6e6;font:14px Segoe UI,sans-serif;margin:16px}h2{margin:20px 0 6px}"
             ".row{display:flex;flex-wrap:wrap;gap:10px}.t{width:320px;font-size:12px}"
             ".t img{width:320px;display:block;background:#3a3a3a}.in{outline:2px solid #378ef0}</style>"]
    for mode, label in (("edit", "Edit canvas (owl photo)"), ("sketch", "Sketch to image (owl sketch)")):
        src = lt.OUT / "eingabe" / INPUT[mode]
        parts.append(f"<h2>{label}</h2><div class='row'><div class='t'><a href='{src.as_uri()}'>"
                     f"<img class='in' src='{src.as_uri()}'></a>Input</div>")
        for m, name, text in jobs():
            p = OUT / f"{m}-{styles.slug(name)}.png"
            if m == mode and p.exists():
                parts.append(f"<div class='t' title='{html.escape(text, quote=True)}'><a href='{p.as_uri()}'>"
                             f"<img src='{p.as_uri()}'></a>{html.escape(name)}</div>")
        parts.append("</div>")
    page = OUT / "vergleich.html"
    page.write_text("".join(parts), encoding="utf-8")
    print(f"View: {page.as_uri()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "view"))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--url")
    ap.add_argument("--dry", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    return {"run": cmd_run, "view": cmd_view}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
