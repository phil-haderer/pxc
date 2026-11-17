"""Manual check (not part of run_all.py): are the prompts the writers write with ComfyUI's start option --use-ck-attention
(Comfy Kitchen attention) as good as without it? (user 13.11.: the speed-up is known, the quality of the written prompts is not)

Every writer gets the same ideas and the same writer seed in both passes; its own system prompt and text model. Then every
written prompt makes one picture with the model's own text-to-image workflow (writer bypassed, the written text sent as it
is, as the plugin does), the same picture seed for all. A blind page shows per model and idea the two results as
"Variante A / B" (text under the picture); the key stays in key.json.

    python tests\\live_ck_writer_quality.py write     texts on the running ComfyUI; label (normal / ck) from its start options
    python tests\\live_ck_writer_quality.py render    pictures of both text sets on the running ComfyUI (one state for all)
    python tests\\live_ck_writer_quality.py viewer --serve    blind rating page (gut / mittel / schlecht, fault cross)
    python tests\\live_ck_writer_quality.py report    words, times, Fibo JSON check, and the ratings resolved by the key
    add --dry to `write` / `render` to only build the graphs and check every file is known to ComfyUI.
    --cases flux3,flux2,qwen,moss,fibo picks models; --n 4 the number of ideas.

Output: data\\ck-writer\\<label>\\texts.json, data\\ck-writer\\pictures\\, key.json, bewertung.json, fehler.json,
report.md and data\\ck-schreiber.html. Nothing in the plugin changes.
"""
import argparse
import functools
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from PIL import Image  # noqa: E402

from pccomfy import workflows  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402
from live_llm_tempo import comfy_info  # noqa: E402
from live_writer_compare import WF, known, picture_graph, prompts, run_picture, run_text, writer_graph  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "ck-writer"
PICS = OUT / "pictures"
PAGE = "ck-schreiber.html"
CASES = {"flux3": ("Flux 3", "flux3-klein-t2i.json"), "flux2": ("Flux 2", "flux2-klein-t2i.json"),
         "qwen": ("Qwen Image 2.1", "qwen-image-21-t2i.json"), "moss": ("MOSS", "moss-image-t2i.json"),
         "fibo": ("Fibo", "fibo2-t2i.json")}
LABELS = ("normal", "ck")
WRITER_SEED = 7
PICTURE_SEED = 101
GRADES = ("gut", "mittel", "schlecht")
FAULT = "Wunsch nicht befolgt"


def own_writer(wf: str) -> tuple[str, str]:
    """The text model file and loader type of the workflow's own prompt writer (as the plugin runs it)."""
    t = workflows.load_template(WF / wf)
    w = str(workflows.prompt_writers(t)[0])
    loader = t[str(t[w]["inputs"]["clip"][0])]["inputs"]
    return loader["clip_name"], loader["type"]


def fibo_json_ok(text: str) -> bool:
    """Fibo's encoder reads the prompt as a JSON object; anything else goes in as plain text (comfy/text_encoders/fibo2.py)."""
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def picked(a) -> list[str]:
    cases = [x.strip() for x in a.cases.split(",") if x.strip()]
    for case in cases:
        if case not in CASES:
            raise SystemExit(f"unknown case {case!r}; known: {', '.join(CASES)}")
    return cases


def cmd_write(a):
    c = ComfyUI()
    cases, ideas = picked(a), prompts(a.n)
    known(c, *sorted({own_writer(CASES[x][1])[0] for x in cases}))
    built = {case: [writer_graph(CASES[case][1], *own_writer(CASES[case][1]), p, seed=WRITER_SEED) for p in ideas] for case in cases}
    if a.dry:
        print("ok: writer files known to ComfyUI;", ", ".join(f"{k} ({len(v)})" for k, v in built.items()))
        print("ideas:", *[f"  {i + 1}. {p}" for i, p in enumerate(ideas)], sep="\n")
        return
    info = comfy_info(c)
    label = "ck" if "--use-ck-attention" in info["argv"] else "normal"
    out = OUT / label
    out.mkdir(parents=True, exist_ok=True)
    print(f"write '{label}': ComfyUI {info['version']}, {info['gpu']}, start options {' '.join(info['argv'][1:])}")
    res = {"label": label, "when": time.strftime("%Y-%m-%d %H:%M"), "comfy": info, "ideas": ideas, "texts": {}}
    for case in cases:
        for i, (g, node) in enumerate(built[case]):
            text, sec = run_text(c, g, node)
            row = {"idea": i + 1, "sec": round(sec, 1), "words": len(text.split()), "text": text}
            if case == "fibo":
                row["json_ok"] = fibo_json_ok(text)
            res["texts"][f"{case}_{i + 1}"] = row
            print(f"  {case:6s} idea {i + 1}  {sec:6.1f} s  {row['words']:4d} words{'  (with model load)' if i == 0 else ''}")
            (out / "texts.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {out / 'texts.json'}")


def load_texts() -> dict:
    t = {k: json.loads((OUT / k / "texts.json").read_text(encoding="utf-8")) for k in LABELS if (OUT / k / "texts.json").exists()}
    if len(t) < 2:
        raise SystemExit("need both text passes: data\\ck-writer\\normal and ck (write)")
    return t


def cmd_render(a):
    c = ComfyUI()
    t = load_texts()
    cases = picked(a)
    jobs = [(lab, name, row["text"]) for lab in LABELS for name, row in t[lab]["texts"].items() if name.rsplit("_", 1)[0] in cases]
    graphs = [(lab, name, *picture_graph(CASES[name.rsplit("_", 1)[0]][1], text, PICTURE_SEED)) for lab, name, text in jobs]
    if a.dry:
        print(f"ok: {len(graphs)} picture graphs build")
        return
    info = comfy_info(c)
    PICS.mkdir(parents=True, exist_ok=True)
    print(f"render on ComfyUI {info['version']}, start options {' '.join(info['argv'][1:])}")
    times = {"render_argv": info["argv"], "when": time.strftime("%Y-%m-%d %H:%M"), "sec": {}}
    # model by model, so every model loads once
    for case in cases:
        for lab, name, g, node in [x for x in graphs if x[1].rsplit("_", 1)[0] == case]:
            img, sec = run_picture(c, g, node)
            img.save(PICS / f"{name}_{lab}.png")
            times["sec"][f"{name}_{lab}"] = round(sec, 1)
            print(f"  {name:8s} {lab:6s} {sec:6.1f} s")
            (PICS / "times.json").write_text(json.dumps(times, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {PICS}")


def rel(p: Path) -> str:
    return os.path.relpath(p, DATA).replace("\\", "/")


def build_page(rate: bool) -> Path:
    t = load_texts()
    rng = random.Random(13)
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    page, key = [], {}
    for name in t["normal"]["texts"]:
        if not all((PICS / f"{name}_{lab}.png").exists() for lab in LABELS):
            continue
        if t["normal"]["texts"][name]["text"] == t["ck"]["texts"].get(name, {}).get("text"):
            continue        # the same text gives the same picture: nothing to rate (report.md names these)
        order = list(LABELS)
        rng.shuffle(order)
        case, idea = name.rsplit("_", 1)
        title = f"{CASES[case][0]}, Idee {idea}"
        key[title] = {"AB"[i]: lab for i, lab in enumerate(order)}
        imgs = []
        for i, lab in enumerate(order):
            p = PICS / f"{name}_{lab}.png"
            th = OUT / "thumbs" / f"{name}_{lab}.jpg"
            if not th.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((120, 90), Image.LANCZOS)
                im.save(th, quality=85)
            row = t[lab]["texts"][name]
            imgs.append({"label": f"Variante {'AB'[i]} ({row['words']} Wörter)", "short": f"Variante {'AB'[i]}", "src": rel(p),
                         "thumb": rel(th), "prompt": f"[Idee: {t[lab]['ideas'][int(idea) - 1]}]  {row['text']}", "id": f"{name}_{lab}"})
        page.append({"title": title, "images": imgs})
    (OUT / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    html = (ROOT / "tools" / "ab_viewer_template.html").read_text(encoding="utf-8").replace("__SETS__", json.dumps(page, ensure_ascii=False))
    if rate:
        conf = json.dumps({"url": "/rate", "ratings_url": "/ratings", "fault": FAULT, "faults_url": "/faults"}, ensure_ascii=False)
        html = html.replace("<script>\nconst SETS", f"<script>window.RATE_CONF = {conf};</script>\n<script>\nconst SETS", 1)
    target = DATA / PAGE
    target.write_text(html, encoding="utf-8")
    print(f"ok: {len(page)} sets in {target}; the key is in {OUT / 'key.json'}")
    return target


def save_rating(rid: str, wahl: str = "", fehler=None) -> None:
    case, _, rest = str(rid).partition("_")
    if case not in CASES or "/" in rid or ".." in rid or not (PICS / f"{rid}.png").is_file():
        raise ValueError("unknown picture")
    if fehler is not None:
        f = OUT / "fehler.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if fehler:
            data[rid] = True
        else:
            data.pop(rid, None)
    else:
        if wahl not in GRADES:
            raise ValueError("unknown rating")
        f = OUT / "bewertung.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        data[rid] = wahl
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def cmd_viewer(a):
    target = build_page(a.serve)
    if not a.serve:
        return
    import http.server
    import webbrowser
    allowed = (PAGE, rel(OUT) + "/")

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
                f = OUT / ("bewertung.json" if path == "ratings" else "fehler.json")
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
                save_rating(body.get("id", ""), body.get("wahl", ""), body.get("fehler"))
            except (ValueError, AttributeError) as e:
                self._send(400, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, b'{"ok": true}')

        def log_message(self, fmt, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), functools.partial(Handler, directory=str(DATA)))
    url = f"http://127.0.0.1:{a.port}/{target.name}"
    print(f"Rating page: {url}  (saved into {OUT}; Ctrl+C or closing this window ends it)", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def cmd_report(a):
    t = load_texts()

    def load(name):
        f = OUT / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    grades, faults = load("bewertung.json"), load("fehler.json")
    n, k = t["normal"], t["ck"]
    lines = [f"# Prompt-Schreiber mit und ohne `--use-ck-attention`, ComfyUI {n['comfy']['version']}, {n['comfy']['gpu']}", "",
             f"Schreiber-Seed {WRITER_SEED}, Bild-Seed {PICTURE_SEED}; Texte ohne: {n['when']}, mit CK: {k['when']}.", "",
             "| Text | Zeit ohne / mit CK (s) | Wörter ohne / mit | Bewertung ohne | Bewertung mit CK |", "|---|---|---|---|---|"]
    tally = {lab: {g: 0 for g in GRADES} | {"fault": 0, "clean": 0} for lab in LABELS}
    for name, rn in n["texts"].items():
        rk = k["texts"].get(name)
        if not rk:
            continue
        cells = []
        for lab in LABELS:
            rid = f"{name}_{lab}"
            g = grades.get(rid, "–")
            if g in GRADES:
                tally[lab][g] += 1
                tally[lab]["clean"] += g == "gut" and not faults.get(rid)
            tally[lab]["fault"] += bool(faults.get(rid))
            cells.append(g + (" ✗" if faults.get(rid) else ""))
        js = f" (JSON {'ok' if rn.get('json_ok') else 'kaputt'} / {'ok' if rk.get('json_ok') else 'kaputt'})" if "json_ok" in rn else ""
        js += " (Text gleich)" if rn["text"] == rk["text"] else ""
        lines.append(f"| {name}{js} | {rn['sec']:.1f} / {rk['sec']:.1f} | {rn['words']} / {rk['words']} | {cells[0]} | {cells[1]} |")
    lines += ["", "| | gut | davon fehlerfrei | mittel | schlecht | " + FAULT + " |", "|---|---|---|---|---|---|"]
    for lab, name in (("normal", "ohne CK"), ("ck", "mit CK")):
        s = tally[lab]
        lines.append(f"| {name} | {s['gut']} | {s['clean']} | {s['mittel']} | {s['schlecht']} | {s['fault']} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {OUT / 'report.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("write", "render", "viewer", "report"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8771)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    {"write": cmd_write, "render": cmd_render, "viewer": cmd_viewer, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
