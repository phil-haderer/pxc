r"""Manual check (not part of run_all.py): P8, a description of the picture in front of the Upscale prompt, with and
without tiles (user 12.11.; docs/archiv/plan-vorschlaege-10-11.md P8, docs/archiv/tests/p8-upscale-prompt-testplan.md). GPU: remind
the user first, start only on his word.

With tiles every tile gets the whole prompt: "a runner on the road" may put a runner into every tile. Does a description
help without tiles and harm with them? 4 photos (testpics magnific 3\2MP, shrunk to 1 MP), seed 1234, the default prompt
and start values of the plugin, the graphs built the way the plugin builds them (Bridge._graph with its stages):

    flux2  2x    tiles (always since 12.11., no stage; "notiles" is gone)  x  ohne / mit description   = 2 per photo
    fibo   1.5x  us (start: 4x UltraSharp first) / tiles  x  ohne / mit          = 4 per photo
    flux3  2x    tiles (always)                     x  ohne / mit               = 2 per photo

Fibo at 1.5x: at 2x (4 MP from 1 MP) it tiles by itself above 3 MP, "without tiles" does not exist there. The description
is made once per photo like the LLM button (Bridge.describe_image, Qwen 3.5 9B int8, no seed: the same picture gives the
same text) and goes in front of the default prompt with a line break (gui_prompt.put_in_front). One text for all models.

    python tests\live_upscale_prompt.py run --images "<testpics magnific 3>\2MP" [--url http://<ip>:8188] [--dry]
    python tests\live_upscale_prompt.py viewer --serve   (blind A/B page: gut / mittel / schlecht, keys G M S, and the
                                                          fault "Objekt doppelt / erfunden", key X; saved per run)
    python tests\live_upscale_prompt.py summary

Output: data\upscale-prompt\<time>\<photo>\<model>_<factor>x_<variant>_<ohne|mit>.png, beschreibungen.json, report.md.
"""
import argparse
import json
import os
import random
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

import live_upscale_stages as stages  # noqa: E402
from pccomfy import config as cfgmod, models, workflows  # noqa: E402
from pccomfy.bridge import Bridge, Request  # noqa: E402

DATA = cfgmod.CONFIG_DIR
BASE = DATA / "upscale-prompt"
SEED = 1234
SOURCE_MP = 1.0
DESCRIBER = "qwen3.5_9b_int8_convrot.safetensors"      # the describe writer every model falls back to (manifest)
PHOTOS = ["09_man-sportswear-running", "15_student-learns-task", "07_herd-cows-grazing", "14_smiling-woman-prepares"]
# model: (factor, {variant: (stage_on, stages_off)}); the start variant first
RUNS = {
    "flux2": (2.0, {"tiles": (True, [])}),            # always tiles since 12.11.: there is no stage to switch off
    "fibo": (1.5, {"us": (True, ["102"]), "tiles": (False, [])}),
    "flux3": (2.0, {"tiles": (False, [])}),           # SeedVR2 off, 4x UltraSharp on (the start values); always tiles
}
DESC = ("ohne", "mit")
PAGE = "vergleich-upscale-prompt.html"
PORT = 8767
GRADES = ("gut", "mittel", "schlecht")
FAULT = "Objekt doppelt / erfunden"


def jobs() -> list:
    """(photo, model, factor, variant, desc); one model after the other, so each is loaded once."""
    return [(ph, m, f, v, d) for m, (f, vs) in RUNS.items() for v in vs for ph in PHOTOS for d in DESC]


def mode(model: str) -> models.Mode:
    return models.BY_KEY[model].modes["upscale"]


def request(model: str, variant: str) -> Request:
    st, factor = mode(model).settings, RUNS[model][0]
    stage_on, off = RUNS[model][1][variant]
    return Request(mode="upscale", workflow=str(ROOT / "workflows" / mode(model).workflow), enhance=st.get("enhance", True),
                   turbo=st.get("turbo", True), scale=factor, context=0.0, stage_on=stage_on, stages_off=list(off),
                   detail=st.get("detail", 1.0))


def prompt(model: str, desc: str) -> str:
    """The default prompt; with a description in front of it and a line break, as the LLM button puts it."""
    base = mode(model).prompt_hint
    return (desc.strip() + "\n" + base) if desc else base


def graph_of(b: Bridge, model: str, variant: str, image_name: str, size: tuple, text: str):
    req = request(model, variant)
    mp = size[0] * size[1] * req.scale * req.scale / 1e6
    req = Bridge._auto_stages(req, req.workflow, mp)
    p = workflows.GenParams(prompt=text, seed=SEED, width=size[0], height=size[1])
    p.extra["megapixels"] = mp
    graph, out = b._graph(req, p, image_name, None, req.workflow)
    return graph, out, req


def tiled(graph: dict) -> bool:
    return any(n.get("class_type") == "SplitImageToTileList" for n in graph.values())


def comfy_at(url: str):
    url = url or cfgmod.load()["comfyui"]["url"]
    host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        sys.exit(f"ComfyUI is not running ({url}). Start it first.")
    from pccomfy.comfy import ComfyUI
    return ComfyUI(url)


class _NoPhotoCraft:
    pass


def cmd_run(a):
    folder = Path(a.images)
    missing = [n for n in PHOTOS if not (folder / f"{n}.png").exists()]
    if missing:
        sys.exit(f"Missing in {folder}: {', '.join(missing)}")
    todo = jobs()
    if a.dry:
        b = Bridge(_NoPhotoCraft(), None, BASE / "xch")
        for _, m, f, v, d in todo:
            g, _, req = graph_of(b, m, v, "x.png", (1224, 816), prompt(m, "A test description." if d == "mit" else ""))
            bad = stages.links_ok(g)
            if bad:
                sys.exit(f"{m} {v}: broken links {bad}")
            want = v not in ("us", "notiles")
            if want != _tiles_active(g):
                sys.exit(f"{m} {v}: tiles {'missing' if want else 'still on'}")
        print(f"ok: {len(todo)} graphs built, links point at nodes, tiles on and off as planned")
        return
    comfy = comfy_at(a.url)
    b = Bridge(_NoPhotoCraft(), comfy, BASE / "xch")
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    b._real_lora_names = lambda tpl: workflows.fix_lora_names(tpl, loras)[0]
    root = Path(a.out) if a.out else BASE / time.strftime("%Y%m%d-%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    descs_file = root / "beschreibungen.json"
    descs = json.loads(descs_file.read_text(encoding="utf-8")) if descs_file.exists() else {}
    sources = {}
    for ph in PHOTOS:
        d = root / ph
        d.mkdir(exist_ok=True)
        im = stages.shrink(Image.open(folder / f"{ph}.png").convert("RGB"), SOURCE_MP)
        im.save(d / "source.png")
        sources[ph] = (comfy.upload_image(im, f"pccomfy-p8-{ph}.png"), im)
        if ph not in descs:
            t0 = time.time()
            descs[ph] = b.describe_image(im, clip=DESCRIBER)
            descs_file.write_text(json.dumps(descs, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"described {ph} in {time.time() - t0:.0f} s: {descs[ph]}", flush=True)
    rows = ["| photo | model | factor | variant | description | size | time (s) |", "|---|---|---|---|---|---|---|"]
    t_start = time.time()
    for n, (ph, m, f, v, d) in enumerate(todo, 1):
        dest = root / ph / f"{m}_{f}x_{v}_{d}.png"
        if dest.exists():
            continue
        name, im = sources[ph]
        g, out, req = graph_of(b, m, v, name, im.size, prompt(m, descs[ph] if d == "mit" else ""))
        t0 = time.time()
        try:
            res = stages.run_one(comfy, g, out).convert("RGB")
        except Exception as e:      # noqa: BLE001 - one failed run is noted, the round goes on
            rows.append(f"| {ph} | {m} | {f}x | {v} | {d} | FAILED: {str(e)[:60].replace('|', '/')} | {time.time() - t0:.0f} |")
            print(rows[-1], flush=True)
            if isinstance(e, OSError):
                sys.exit("ComfyUI not reachable: stopping (run again with --out to skip the finished ones)")
            continue
        if req.detail < 0.999:      # as the bridge does for Upscale: mixed with the plainly scaled original (Flux 3: 0.7)
            res = Image.blend(im.resize(res.size, Image.LANCZOS), res, max(0.0, req.detail))
        res.save(dest)
        rows.append(f"| {ph} | {m} | {f}x | {v} | {d} | {res.width}x{res.height} | {time.time() - t0:.0f} |")
        left = (time.time() - t_start) / n * (len(todo) - n)
        print(f"{n}/{len(todo)} {m} {f}x {v} {d} {ph}: {time.time() - t0:.0f} s (about {left / 60:.0f} min left)", flush=True)
    (root / "report.md").write_text("\n".join([f"# P8 Upscale-Prompt {root.name}", "", "Beschreibungen:", ""]
                                              + [f"- {ph}: {t}" for ph, t in descs.items()] + ["", *rows, ""]), encoding="utf-8")
    print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min: {root}\nNext: python tests\\live_upscale_prompt.py viewer --serve", flush=True)


def _tiles_active(g: dict) -> bool:
    """The graph really makes tiles: a SplitImageToTileList whose output reaches the sampler side (a bypassed stage is
    cut out of the graph by workflows.bypass_stage, so its split node is gone)."""
    return any(n.get("class_type") == "SplitImageToTileList" for n in g.values())


def latest(folder):
    if folder:
        return Path(folder)
    runs = sorted(p for p in BASE.iterdir() if (p / "report.md").exists()) if BASE.exists() else []
    if not runs:
        sys.exit(f"No finished run in {BASE}")
    return runs[-1]


def viewer_sets(run: Path, rng: random.Random) -> tuple[list, dict]:
    """One set per photo and model: the source, Lanczos and the variants (tiles x description) under blind letters."""
    sets, key = [], {}
    for photo_dir in sorted(p for p in run.iterdir() if (p / "source.png").exists()):
        src = photo_dir / "source.png"
        groups = {}
        for f in sorted(photo_dir.glob("*_*x_*_*.png")):
            m, fac, rest = f.stem.split("_", 2)
            groups.setdefault((m, fac), []).append((rest, f))
        for (m, fac), items in sorted(groups.items()):
            rng.shuffle(items)
            letters = "ABCD"
            title = f"{photo_dir.name[3:]}, {m}, {fac}"
            key[title] = {letters[i]: v for i, (v, _) in enumerate(items)}
            size = Image.open(items[0][1]).size
            lz = photo_dir / f"lanczos_{m}_{fac}.png"
            if not lz.exists():
                Image.open(src).convert("RGB").resize(size, Image.LANCZOS).save(lz)
            imgs = [("Original 1 MP", src, ""), (f"Lanczos {fac} (no AI)", lz, "")]
            imgs += [(f"Variante {letters[i]}", f, f"{photo_dir.name}/{f.stem}") for i, (_, f) in enumerate(items)]
            sets.append({"title": title, "images": imgs})
    return sets, key


def build_page(run: Path, rate: bool) -> Path:
    sets, key = viewer_sets(run, random.Random(8))
    out = DATA / "vergleich-upscale-prompt"
    (out / "thumbs").mkdir(parents=True, exist_ok=True)

    def rel(p: Path) -> str:
        return os.path.relpath(p, DATA).replace("\\", "/")

    page = []
    for s in sets:
        imgs = []
        for label, path, rid in s["images"]:
            th = out / "thumbs" / (rel(path).replace("/", "_").replace(".png", ".jpg"))
            if not th.exists():
                im = Image.open(path).convert("RGB")
                im.thumbnail((120, 90), Image.LANCZOS)
                im.save(th, quality=85)
            w, h = Image.open(path).size
            imgs.append({"label": f"{label} ({w}x{h})", "short": label, "src": rel(path), "thumb": rel(th), "prompt": "(blind)", "id": rid})
        page.append({"title": s["title"], "images": imgs})
    (run / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    html = (ROOT / "tools" / "ab_viewer_template.html").read_text(encoding="utf-8").replace("__SETS__", json.dumps(page, ensure_ascii=False))
    if rate:
        conf = json.dumps({"url": "/rate", "ratings_url": "/ratings", "fault": FAULT, "faults_url": "/faults"}, ensure_ascii=False)
        html = html.replace("<script>\nconst SETS", f"<script>window.RATE_CONF = {conf};</script>\n<script>\nconst SETS", 1)
    target = DATA / PAGE
    target.write_text(html, encoding="utf-8")
    print(f"ok: {len(page)} sets in {target}; the key is in {run / 'key.json'}")
    return target


def _check_id(run: Path, rid: str):
    photo, _, stem = str(rid).partition("/")
    if not photo or "/" in stem or ".." in rid or not (run / photo / f"{stem}.png").is_file() or stem.startswith(("source", "lanczos")):
        raise ValueError("unknown picture")


def save_rating(run: Path, rid: str, wahl: str = "", fehler=None) -> None:
    """A grade into bewertung.json, or the fault on / off into fehler.json (also on good pictures)."""
    _check_id(run, rid)
    if fehler is not None:
        f = run / "fehler.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if fehler:
            data[rid] = True
        else:
            data.pop(rid, None)
    else:
        if wahl not in GRADES:
            raise ValueError("unknown rating")
        f = run / "bewertung.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        data[rid] = wahl
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def cmd_viewer(a):
    run = latest(a.folder)
    target = build_page(run, a.serve)
    if not a.serve:
        return
    import functools
    import http.server
    import webbrowser
    allowed = (PAGE, "vergleich-upscale-prompt/", os.path.relpath(run, DATA).replace("\\", "/") + "/")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0].lstrip("/")
            if path in ("ratings", "faults"):
                f = run / ("bewertung.json" if path == "ratings" else "fehler.json")
                self._send(200, f.read_bytes() if f.exists() else b"{}")
            elif path.startswith(allowed) and ".." not in path:
                super().do_GET()
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/rate":
                self.send_error(404)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 2000:
                    raise ValueError("request too large")
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                save_rating(run, body.get("id", ""), body.get("wahl", ""), body.get("fehler"))
            except (ValueError, AttributeError) as e:
                self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, b'{"ok": true}')

        def log_message(self, fmt, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Handler, directory=str(DATA)))
    url = f"http://127.0.0.1:{a.port}/{target.name}"
    print(f"Rating page: {url}  (saved into {run}; Ctrl+C or closing this window ends it)", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def summarize(run: Path) -> str:
    """Per model and variant: ohne against mit description, gut / mittel / schlecht and the fault; then per photo."""
    def load(name):
        f = run / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    grades, faults = load("bewertung.json"), load("fehler.json")
    rows: dict = {}
    for rid, wahl in grades.items():
        photo, _, stem = rid.partition("/")
        m, fac, v, d = stem.split("_", 3)
        r = rows.setdefault((m, fac, v, d), {"gut": [], "mittel": [], "schlecht": [], "fault": []})
        r[wahl].append(photo[3:])
        if faults.get(rid):
            r["fault"].append(photo[3:])
    lines = [f"# P8 Upscale-Prompt {run.name}", "", f"Bewertet: {len(grades)} von {len(jobs())} Bildern (blind).", "",
             f"| Modell | Faktor | Kacheln | Beschreibung | gut | mittel | schlecht | {FAULT} | gut bei |", "|---|---|---|---|---|---|---|---|---|"]
    order = list(RUNS)
    for k in sorted(rows, key=lambda k: (order.index(k[0]), k[2], DESC.index(k[3]))):
        r = rows[k]
        lines.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {len(r['gut'])} | {len(r['mittel'])} | {len(r['schlecht'])} | "
                     f"{len(r['fault'])} | {', '.join(r['gut'])} |")
    descs = load("beschreibungen.json")
    if descs:
        lines += ["", "Beschreibungen:", ""] + [f"- {ph}: {t}" for ph, t in descs.items()]
    return "\n".join(lines) + "\n"


def cmd_summary(a):
    run = latest(a.folder)
    text = summarize(run)
    (run / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--images", required=True, help="the folder with the 2 MP photos (testpics magnific 3\\2MP)")
    r.add_argument("--url", default="", help="the ComfyUI address (default: config.toml), e.g. http://<ip of PC C>:8188")
    r.add_argument("--dry", action="store_true", help="only build the graphs and check links and tiles")
    r.add_argument("--out", help="an earlier run folder to continue (finished files are skipped)")
    v = sub.add_parser("viewer")
    v.add_argument("folder", nargs="?")
    v.add_argument("--serve", action="store_true", help="the page with rating buttons and the fault, saved per run")
    v.add_argument("--port", type=int, default=PORT)
    v.add_argument("--no-open", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("folder", nargs="?")
    a = ap.parse_args()
    {"run": cmd_run, "viewer": cmd_viewer, "summary": cmd_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
