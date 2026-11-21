"""Manual GPU run (not part of run_all.py): the square preview pictures of the style picker (stylegrid.py), user 20.11.:
one owl, Qwen Image 2.1, first only the five most important styles per group (the choice the user approved on 20.11.,
SELECTION below; docs/plan/entscheidungen.md "Stil-Vorschaubilder").

One picture per style NAME, shared by Text to image, Edit canvas and Sketch to image (user 20.11., "A": the same name has
the same look in every mode, only the sentence around it differs). Every picture is a Text to image picture through the
real plugin path (the window's request with Qwen's start settings, the bridge with the PhotoCraft simulator of
test_reference_mode, the real ComfyUI) on a white canvas:

- a style Text to image has: "<owl>\\n<its text>", as the Styles button adds it;
- a style only Edit canvas or Sketch to image has: its look from tools/styles-looks.json with the owl put in
  ("A watercolor painting of <owl> with soft washes ...").

- ``plan``: every picture with its prompt, and how many are still to make;
- ``run``: the full picture goes to data\\style-thumbs\\full\\<slug>.png, the thumbnail (THUMB_PX square) to
  pccomfy\\assets\\style-thumbs\\<slug>.png, which stylegrid shows in every mode;
- ``view``: one HTML page with every thumbnail by mode and group (file:/// link).

    python tests\\live_style_thumbs.py plan [--mode ...] [--only NAME ...]
    python tests\\live_style_thumbs.py run [--mode txt2img edit sketch] [--all] [--only NAME ...] [--seed N] [--dry] [--redo] [--url ...]
    python tests\\live_style_thumbs.py view

A picture already in full\\ is not made again (resume), unless --redo. ``--only`` limits it to these style names, e.g. a
new seed for a picture that does not fit: ``run --only "Pixel art" --seed 7 --redo``. ``--dry`` runs against a fake
ComfyUI (no GPU) and checks that the text reaches the graph; it writes nothing.
"""
import argparse
import html
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
_HOME = Path(tempfile.mkdtemp(prefix="pccomfy-stylethumbs-"))      # never the plugin's own state.json
if (DATA / "settings.json").exists():
    shutil.copyfile(DATA / "settings.json", _HOME / "settings.json")
os.environ["PCCOMFY_HOME"] = str(_HOME)
os.environ["PCCOMFY_NO_TIPS"] = "1"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image, ImageOps  # noqa: E402

import live_sketch  # noqa: E402
import test_reference_mode as tr  # noqa: E402
from pccomfy import bridge, config as cfgmod, inventory, styles  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

OUT = DATA / "style-thumbs"
LOOKS = ROOT / "tools" / "styles-looks.json"
MODEL = "qwen"
SEED = 1234
SIZE = (1024, 1024)
THUMB_PX = 192                  # the tile is 88 px at 100 % (stylegrid.TILE): sharp up to about 215 % display scaling
SECS = 30                       # rough seconds per picture for the plan

OWL = "a tawny owl perched on a mossy branch, facing the viewer"

# the five most important styles per group (groups of five or fewer: all), approved by the user on 20.11.
SELECTION = {
    "txt2img": {
        "Photo": ["Golden hour travel photo", "Bright summer midday, lifestyle", "Street photo, rainy and muted",
                  "35 mm snapshot, harsh flash", "Motion blur, panning"],
        "Studio & product": ["Bright white minimal, high key", "Studio portrait", "Coloured studio lights, red and blue",
                             "Product photo, colour backdrop", "Stock photo, lifestyle"],
        "Film look": ["Film look, warm dusk", "Film look, cool blue night", "Neon city night, bokeh"],
        "Painting": ["Oil painting, 19th-century realism", "Impressionist painting, sunny", "Watercolor storybook",
                     "Japanese ink wash", "Swirling night-sky painting"],
        "Graphic & poster": ["Flat vector, sunny", "Mid-century travel poster", "Risograph, blue and yellow",
                             "Clear-line comic", "Vintage paper collage"],
        "Anime & comic": ["Modern anime, clean lines", "Retro anime, pastel", "90s anime, VHS grain", "Manga, bold ink"],
        "3D & craft": ["3D clay render", "Claymation, stop-motion", "Low-poly game look", "Voxel diorama, pastel",
                       "Yarn embroidery"],
        "Fantasy & sci-fi": ["Dark fantasy, glowing neon", "Cyberpunk neon, rain",
                             "Solarpunk", "Cosmic glow"],
    },
    "edit": {
        "Photo": ["Realistic photo", "Studio portrait", "Golden hour travel photo", "Vintage black-and-white photo",
                  "Black and white, hard light and shadows"],
        "Painting": ["Oil painting, 19th-century realism", "Impressionist painting, sunny", "Watercolor storybook", "Japanese ink wash"],
        "Anime & comic": ["Animated film", "Modern anime, clean lines", "Retro anime, pastel"],
    },
}
SELECTION["sketch"] = {
    "Photo": SELECTION["edit"]["Photo"],
    "Painting": SELECTION["edit"]["Painting"],
    "Anime & comic": SELECTION["edit"]["Anime & comic"],
    "3D & craft": ["3D clay render", "Claymation, stop-motion", "Voxel diorama, pastel", "Low-poly game look"],
}
MODE_NAME = {"txt2img": "Text to image", "edit": "Edit canvas", "sketch": "Sketch to image"}


def chosen(mode: str, every: bool = False) -> list:
    """[(group, style dict)] of this mode in the picker's order: the SELECTION of a group, a group not named there whole;
    every=True (--all, user 20.11. evening): every style of the mode."""
    out = []
    for g in styles.load().get(mode, []):
        names = None if every else SELECTION[mode].get(g["name"])
        out += [(g["name"], s) for s in g["styles"] if names is None or s["name"] in names]
    return out


def check_selection():
    """Every name in SELECTION is a style of its group (a renamed style must not drop out silently)."""
    data = styles.load()
    for mode, groups in SELECTION.items():
        have = {g["name"]: {s["name"] for s in g["styles"]} for g in data.get(mode, [])}
        for group, names in groups.items():
            missing = [n for n in names if n not in have.get(group, set())]
            if missing or len(names) > 5:      # fewer than five where the user took styles out (20.11.)
                sys.exit(f"SELECTION {mode} / {group}: not in styles.json {missing} or more than five names")


def looks() -> dict:
    """{style name: look} of the Edit canvas and Sketch to image styles (tools/styles-looks.json)."""
    data = json.loads(LOOKS.read_text(encoding="utf-8"))
    return {s["name"]: s["look"] for g in data["groups"] for s in g["styles"]}


def owl_in(look: str) -> str:
    """A look as a Text to image prompt with the owl: "a watercolor painting with soft washes" -> "A watercolor painting
    of <owl>, with soft washes."; the owl goes before the first " with " or ":", else at the end."""
    for cut in (" with ", ":"):
        if cut in look:
            head, tail = look.split(cut, 1)
            text = f"{head} of {OWL}{',' if cut == ' with ' else ''}{cut}{tail}"
            break
    else:
        text = f"{look} of {OWL}"
    return text[0].upper() + text[1:].rstrip(".") + "."


def jobs(modes: list, every: bool = False) -> list:
    """[(style name, prompt)] once per name over these modes, in the picker's order: a name Text to image has gets
    "<owl>\\n<its text>" (as the Styles button adds it), one only Edit canvas or Sketch to image has gets owl_in(look)."""
    t2i = {s["name"]: s["text"] for g in styles.load().get("txt2img", []) for s in g["styles"]}
    look = looks()
    out = {}
    for mode in modes:
        for _, st in chosen(mode, every):
            n = st["name"]
            if n not in out:
                out[n] = OWL + "\n" + t2i[n] if n in t2i else owl_in(look[n])
    return list(out.items())


def window_request(app, text: str, seed: int):
    """The Request the window sends in Text to image with Qwen's start settings (saved pages ignored), no writer."""
    app.v_model.set(MODEL)
    app.v_mode.set("txt2img")
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
    req.params = replace(req.params, seed=seed)
    return req


def run_one(comfy, req, pic: Image.Image, exch: Path) -> Image.Image:
    tr.W, tr.H = pic.size
    pc = tr.FakePC(exch)
    pc.docs.append(tr.Doc("owl.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True, "name": "Background"}]))
    bridge.Bridge(pc, comfy, exch).run(req)
    return tr.FakePC.composite(pc.docs[0]).convert("RGB")


def _text_in(graph: dict, text: str) -> bool:
    words = [w for w in text.replace("\n", " ").split() if len(w) > 4][:6]
    blob = json.dumps(graph, ensure_ascii=False)
    return all(w in blob for w in words)


def connect(a):
    if a.dry:
        return tr.FakeComfy(), "http://127.0.0.1:1"
    url = a.url or cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        sys.exit(f"ComfyUI is not running ({url}). Start it first.")
    comfy = ComfyUI(url)
    if inventory.fetch(comfy, cfgmod.model_map()).tab_status(MODEL).state != "ready":
        print(f"WARNING: {MODEL}: not all its files are there", flush=True)
    return comfy, url


def thumb(im: Image.Image) -> Image.Image:
    return ImageOps.fit(im, (THUMB_PX, THUMB_PX), Image.LANCZOS)


def selected(a) -> list:
    """jobs() of --mode, limited to --only; an --only name that is no chosen style stops the run."""
    rows = jobs(a.mode, a.all)
    if a.only:
        unknown = [n for n in a.only if n not in dict(rows)]
        if unknown:
            sys.exit(f"--only: not a chosen style of {a.mode}: {unknown}")
        rows = [r for r in rows if r[0] in a.only]
    return rows


def full_of(name: str) -> Path:
    return OUT / "full" / f"{styles.slug(name)}.png"


def cmd_plan(a):
    check_selection()
    rows = selected(a)
    for mode in a.mode:
        print(f"{MODE_NAME[mode]}: {len(chosen(mode, a.all))} tiles")
    print()
    for name, prompt in rows:
        done = "  (done)" if full_of(name).exists() else ""
        print(f"{name}{done}: {prompt.replace(chr(10), ' / ')[:170]}")
    todo = sum(not full_of(n).exists() for n, _ in rows)
    print(f"\n{len(rows)} pictures, {todo} still to make, about {todo * SECS / 60:.0f} min")


def cmd_run(a):
    check_selection()
    rows = selected(a)
    comfy, url = connect(a)
    app = live_sketch.make_app(url)
    xch = Path(tempfile.mkdtemp(prefix="pccomfy-thumbs-xch-"))
    blank = Image.new("RGB", SIZE, "white")
    n, bad, t0 = 0, 0, time.time()
    for name, text in rows:
        n += 1
        full = full_of(name)
        if full.exists() and not a.redo and not a.dry:
            continue
        req = window_request(app, text, a.seed)
        t1 = time.time()
        try:
            im = run_one(comfy, req, blank, xch)
        except Exception as e:                # one failing picture must not stop the run
            bad += 1
            print(f"{n}/{len(rows)} {name}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        if a.dry:
            ok = _text_in(comfy.graphs[-1], text)
            bad += not ok
            print(f"{n}/{len(rows)} {name}: {Path(req.workflow or '').name}, text in graph: {'yes' if ok else 'NO'}",
                  flush=True)
            continue
        full.parent.mkdir(parents=True, exist_ok=True)
        im.save(full)
        styles.THUMBS.mkdir(parents=True, exist_ok=True)
        thumb(im).save(styles.THUMBS / full.name, optimize=True)
        print(f"{n}/{len(rows)} {name}: {time.time() - t1:.0f} s (seed {a.seed})", flush=True)
    app.root.destroy()
    print(f"\n{'DRY RUN' if a.dry else 'DONE'} in {(time.time() - t0) / 60:.1f} min: {len(rows)} pictures, {bad} failed",
          flush=True)
    if not a.dry:
        cmd_view(a)
    return bad


def cmd_view(a):
    """One page: per mode and group the thumbnails of EVERY style with their names (a name in several modes shows the
    same picture; a style without a picture shows an empty tile); a click opens the full picture."""
    parts = ["<!doctype html><meta charset='utf-8'><title>Style previews</title><style>"
             "body{background:#282828;color:#e6e6e6;font:14px Segoe UI,sans-serif;margin:16px}"
             "h2{margin:24px 0 4px}h3{margin:12px 0 6px;color:#9a9a9a;font-weight:600}"
             ".row{display:flex;flex-wrap:wrap;gap:10px}.t{width:192px;text-align:center;font-size:12px}"
             ".t img{width:192px;height:192px;display:block;background:#3a3a3a}"
             ".t.new img{outline:3px solid #378ef0;outline-offset:-3px}.t.new b{color:#5ba3f5}</style>"]
    since = None
    if getattr(a, "new_since", None):       # --new-since "2026-11-20 18:00": these pictures get a blue frame and "new"
        since = time.mktime(time.strptime(a.new_since, "%Y-%m-%d %H:%M"))
        n_new = sum(1 for f in (OUT / "full").glob("*.png") if f.stat().st_mtime >= since)
        parts.append(f"<p>Blue frame = new since {html.escape(a.new_since)} ({n_new} pictures)</p>")
    for mode in SELECTION:
        parts.append(f"<h2>{MODE_NAME[mode]}</h2>")
        last = None
        for group, st in chosen(mode, True):
            if group != last:
                parts.append(("</div>" if last else "") + f"<h3>{html.escape(group)}</h3><div class='row'>")
                last = group
            p = styles.thumb_path(st["name"])
            img = f"<a href='{full_of(st['name']).as_uri()}'><img src='{p.as_uri()}'></a>" if p else "<img>"
            full = full_of(st["name"])
            new = since is not None and full.exists() and full.stat().st_mtime >= since
            tag = "<b>new</b> · " if new else ""
            parts.append(f"<div class='t{' new' if new else ''}' title='{html.escape(st['text'], quote=True)}'>{img}"
                         f"{tag}{html.escape(st['name'])}</div>")
        parts.append("</div>")
    page = OUT / "vorschau.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("".join(parts), encoding="utf-8")
    print(f"View: {page.as_uri()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("plan", "run", "view"))
    ap.add_argument("--mode", nargs="+", default=list(SELECTION), choices=list(SELECTION))
    ap.add_argument("--only", nargs="+", metavar="NAME")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--url")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--new-since", metavar="'YYYY-MM-DD HH:MM'", help="view: mark the pictures made since then")
    ap.add_argument("--all", action="store_true", help="every style of the mode, not only SELECTION (user 20.11. evening)")
    a = ap.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "view": cmd_view}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
