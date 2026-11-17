"""Manual check (not part of run_all.py): do shorter prompt-writer targets make pictures as good as the long ones?
(docs/plan/promptschreiber.md, V5; user 13.11.)

Qwen 2.1, MOSS and Fibo T2I: every writer runs as the plugin runs it, once with its system prompt as it is ("lang") and
once with only the length passage replaced ("kurz", SHORT below); same idea, same writer seed. Every text then makes one
picture with the model's own workflow (writer bypassed, text sent as it is), same picture seed. A blind page shows per
model and idea the two pictures as "Variante A / B" (text under the picture); the key stays in key.json.

    python tests\\live_writer_short_long.py write [--dry]     texts (GPU, a few minutes)
    python tests\\live_writer_short_long.py render [--dry]    pictures (GPU)
    python tests\\live_writer_short_long.py viewer --serve    blind rating page (gut / mittel / schlecht, fault cross)
    python tests\\live_writer_short_long.py report            words, times, ratings resolved by the key
    --cases qwen,moss,fibo picks models.

Output: data\\writer-short-long\\ (texts.json, pictures\\, key.json, bewertung.json, fehler.json, report.md) and
data\\schreiber-kurz-lang.html. Nothing in the plugin changes.
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

from pccomfy.comfy import ComfyUI  # noqa: E402
from live_llm_tempo import comfy_info  # noqa: E402
from live_writer_compare import picture_graph, run_picture  # noqa: E402
from live_writer_lengths import ends_clean, ideas, json_check, text_graph  # noqa: E402

DATA = ROOT / "data"
OUT = DATA / "writer-short-long"
PICS = OUT / "pictures"
PAGE = "schreiber-kurz-lang.html"
CASES = {"qwen": ("Qwen Image 2.1", "qwen-image-21-t2i.json"), "moss": ("MOSS", "moss-image-t2i.json"),
         "fibo": ("Fibo", "fibo2-t2i.json")}
LABELS = ("lang", "kurz")
WRITER_SEED = 7
PICTURE_SEED = 101
GRADES = ("gut", "mittel", "schlecht")
FAULT = "Wunsch nicht befolgt"

# (old passage, new passage) per model; the old passage must be in the workflow's system prompt word for word
SHORT = {
    "qwen": [(
        "**Size.** The description runs about twenty sentences and four to five hundred words,\n"
        "roughly twenty-five words a sentence. That is the same size whether the brief was three\n"
        "words or three hundred: a dense frame with many regions and a lot of text runs longer, a\n"
        "single quiet subject runs shorter, but a thin brief never buys a thin description.",
        "**Size.** The description runs about eight to ten sentences and 120 to 200 words,\n"
        "roughly twenty words a sentence. That is the same size whether the brief was three\n"
        "words or three hundred: a dense frame with many regions and a lot of text runs longer, a\n"
        "single quiet subject runs shorter, but never more than 200 words. Spend the words on what\n"
        "fills most of the frame and leave small regions out rather than listing them.")],
    "moss": [(
        "- Length: aim for 220 to 320 words for a single-subject scene, 320 to 500 for posters, cards, multi-subject scenes "
        "and text-heavy layouts, and never fewer than 200 words. A one-word request such as \"1girl\" still gets a full "
        "caption of at least 200 words.",
        "- Length: aim for 120 to 200 words for a single-subject scene, up to 250 for posters, cards, multi-subject scenes "
        "and text-heavy layouts, and never more. A one-word request such as \"1girl\" still gets a complete caption of at "
        "least 100 words.")],
    "fibo": [
        ("A concise summary of the imagined image content, 200 words maximum.",
         "A concise summary of the imagined image content, 60 words maximum."),
        ("List a maximum of 5 prominent objects. If the scene implies more than 5,",
         "List a maximum of 3 prominent objects. If the scene implies more than 3,"),
        ("A detailed description of the imagined object, 100 words maximum.",
         "A detailed description of the imagined object, 40 words maximum."),
    ],
}


def graph(case: str, idea: str, label: str) -> tuple[dict, str]:
    g, node, _ = text_graph(CASES[case][1], idea, None)
    w = str(g[node]["inputs"]["source"][0])
    if "sampling_mode.seed" in g[w]["inputs"]:     # Fibo samples greedily: no seed
        g[w]["inputs"]["sampling_mode.seed"] = WRITER_SEED
    if label == "kurz":
        sp = g[str(g[w]["inputs"]["system_prompt"][0])]["inputs"]
        for old, new in SHORT[case]:
            if old not in sp["value"]:
                raise SystemExit(f"{case}: length passage not found in the system prompt (workflow changed?):\n{old[:80]}")
            sp["value"] = sp["value"].replace(old, new, 1)
    return g, node


def picked(a) -> list[str]:
    cases = [x.strip() for x in a.cases.split(",") if x.strip()]
    bad = [x for x in cases if x not in CASES]
    if bad:
        raise SystemExit(f"unknown case {bad}; known: {', '.join(CASES)}")
    return cases


def cmd_write(a):
    cases = picked(a)
    jobs = [(case, i, kind, idea, lab, *graph(case, idea, lab)) for case in cases
            for i, (kind, idea) in enumerate(ideas(False)) for lab in LABELS]
    if a.dry:
        print(f"ok: {len(jobs)} writer graphs; short passages found in {', '.join(cases)}")
        return
    c = ComfyUI()
    info = comfy_info(c)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "texts.json"
    res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"texts": {}}
    res.update({"when": time.strftime("%Y-%m-%d %H:%M"), "comfy": info, "ideas": [x for _, x in ideas(False)]})
    print(f"ComfyUI {info['version']}, {info['gpu']}, start options {' '.join(info['argv'][1:])}")
    for case, i, kind, idea, lab, g, node in jobs:
        t0 = time.time()
        hist = c.wait(c.queue(g))
        text = "\n".join(str(x) for x in ((hist.get("outputs", {}).get(node) or {}).get("text") or [""]))
        row = {"case": case, "idea": i + 1, "kind": kind, "label": lab, "sec": round(time.time() - t0, 1),
               "words": len(text.split()), "ends_clean": ends_clean(text), "json": json_check(case, text), "text": text}
        res["texts"][f"{case}_{i + 1}_{lab}"] = row
        print(f"  {case:5s} {i + 1} {kind:4s} {lab:4s} {row['sec']:6.1f} s  {row['words']:4d} words"
              f"{'' if row['ends_clean'] else '  ENDS MID-SENTENCE'}{'  JSON ' + row['json'] if row['json'] else ''}", flush=True)
        f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {f}")


def load_texts() -> dict:
    f = OUT / "texts.json"
    if not f.exists():
        raise SystemExit(f"no texts yet: {f} (write)")
    return json.loads(f.read_text(encoding="utf-8"))


def cmd_render(a):
    t = load_texts()
    cases = picked(a)
    jobs = [(name, *picture_graph(CASES[row["case"]][1], row["text"], PICTURE_SEED))
            for name, row in t["texts"].items() if row["case"] in cases]
    if a.dry:
        print(f"ok: {len(jobs)} picture graphs build")
        return
    c = ComfyUI()
    info = comfy_info(c)
    PICS.mkdir(parents=True, exist_ok=True)
    print(f"render on ComfyUI {info['version']}, start options {' '.join(info['argv'][1:])}")
    tf = PICS / "times.json"
    times = json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else {}
    for case in cases:      # model by model, so every model loads once
        for name, g, node in [j for j in jobs if t["texts"][j[0]]["case"] == case]:
            img, sec = run_picture(c, g, node)
            img.save(PICS / f"{name}.png")
            times[name] = round(sec, 1)
            print(f"  {name:14s} {sec:6.1f} s", flush=True)
            tf.write_text(json.dumps(times, indent=1), encoding="utf-8")
    print(f"written: {PICS}")


def rel(p: Path) -> str:
    return os.path.relpath(p, DATA).replace("\\", "/")


def build_page(rate: bool) -> Path:
    t = load_texts()["texts"]
    rng = random.Random(13)
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    page, key = [], {}
    for name in [k[:-len("_lang")] for k in t if k.endswith("_lang")]:
        if not all((PICS / f"{name}_{lab}.png").exists() for lab in LABELS):
            continue
        order = list(LABELS)
        rng.shuffle(order)
        row0 = t[f"{name}_lang"]
        title = f"{CASES[row0['case']][0]}, Idee {row0['idea']} ({row0['kind']})"
        key[title] = {"AB"[i]: lab for i, lab in enumerate(order)}
        imgs = []
        for i, lab in enumerate(order):
            p = PICS / f"{name}_{lab}.png"
            th = OUT / "thumbs" / f"{name}_{lab}.jpg"
            if not th.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((120, 90), Image.LANCZOS)
                im.save(th, quality=85)
            row = t[f"{name}_{lab}"]
            imgs.append({"label": f"Variante {'AB'[i]} ({row['words']} Wörter)", "short": f"Variante {'AB'[i]}", "src": rel(p),
                         "thumb": rel(th), "prompt": f"[Idee: {row0_idea(row0)}]  {row['text']}", "id": f"{name}_{lab}"})
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


def row0_idea(row: dict) -> str:
    return [x for _, x in ideas(False)][row["idea"] - 1]


def save_rating(rid: str, wahl: str = "", fehler=None) -> None:
    if "/" in rid or "\\" in rid or ".." in rid or not (PICS / f"{rid}.png").is_file():
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
    t = load_texts()["texts"]

    def load(name):
        f = OUT / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    grades, faults = load("bewertung.json"), load("fehler.json")
    lines = [f"# Prompt-Schreiber lang gegen kurz, Schreiber-Seed {WRITER_SEED}, Bild-Seed {PICTURE_SEED}", "",
             "| Text | Wörter lang / kurz | Zeit lang / kurz (s) | JSON lang / kurz | Bewertung lang | Bewertung kurz |",
             "|---|---|---|---|---|---|"]
    tally = {(c, lab): {g: 0 for g in GRADES} | {"fault": 0, "clean": 0} for c in CASES for lab in LABELS}
    for name in [k[:-len("_lang")] for k in t if k.endswith("_lang")]:
        rl, rk = t[f"{name}_lang"], t.get(f"{name}_kurz")
        if not rk:
            continue
        cells = []
        for lab in LABELS:
            rid = f"{name}_{lab}"
            g = grades.get(rid, "–")
            s = tally[(rl["case"], lab)]
            if g in GRADES:
                s[g] += 1
                s["clean"] += g == "gut" and not faults.get(rid)
            s["fault"] += bool(faults.get(rid))
            cells.append(g + (" ✗" if faults.get(rid) else ""))
        js = f"{rl['json'] or '–'} / {rk['json'] or '–'}"
        lines.append(f"| {name} ({rl['kind']}) | {rl['words']} / {rk['words']} | {rl['sec']:.1f} / {rk['sec']:.1f} | {js} | {cells[0]} | {cells[1]} |")
    lines += ["", "| Modell | Fassung | gut | davon fehlerfrei | mittel | schlecht | " + FAULT + " |", "|---|---|---|---|---|---|---|"]
    for (c, lab), s in tally.items():
        if any(s.values()):
            lines.append(f"| {CASES[c][0]} | {lab} | {s['gut']} | {s['clean']} | {s['mittel']} | {s['schlecht']} | {s['fault']} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {OUT / 'report.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("write", "render", "viewer", "report"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8772)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    {"write": cmd_write, "render": cmd_render, "viewer": cmd_viewer, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
