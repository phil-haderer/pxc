"""Manual check (not part of run_all.py): the sentence "No drawing lines left." of the Sketch to image styles (user 18.11.,
docs/plan/testrunden.md point 8). Does it take away the sketch lines and keep the shapes and the layout?

A/B, blind: every style once with its text as it is now (models.SKETCH_NO_LINES at the end) and once without that
sentence (the text before 18.11.), the same sketch, model and seed 1234, through the real plugin path of the style pilot
(live_style_round: the window's request with the start settings of Sketch to image, the bridge with the PhotoCraft
simulator, the real ComfyUI; the prompt writers of Flux 3, Flux 2 and Qwen run as in the plugin, Fibo has none).
Sketches: the three of round 3 (house, hyenas, landscape; data\\sketch-test\\round3-*), the subject typed there.

    python tests\\live_sketch_nolines.py plan [--models ...] [--styles ...] [--sketches ...]
    python tests\\live_sketch_nolines.py run  [--models flux3 flux2 qwen fibo] [--styles "Oil painting" ...] [--sketches house ...]
                                            [--url http://<ip>:8188] [--into <folder>] [--dry] [--free]
    python tests\\live_sketch_nolines.py rate [folder]     (sketch | left | right; 1 left better, 2 same, 3 right better,
                                                          4 both bad; Q/W lines left on left/right, A/S shape lost left/right)
    python tests\\live_sketch_nolines.py summary [folder]  (new against old per model and style; ergebnis.md)

Output: data\\sketch-nolines\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md). ``--dry`` runs the
bridge against a fake ComfyUI (no GPU) and checks that each text reaches the graph. A run resumes in --into.
"""
import argparse
import json
import random
import shutil
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import live_style_round as lsr  # noqa: E402  (sets its own PCCOMFY_HOME first)
from PIL import Image  # noqa: E402

import live_sketch  # noqa: E402
import test_reference_mode as tr  # noqa: E402
from pccomfy import config as cfgmod, inventory, models, styles  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

BASE = lsr.DATA / "sketch-nolines"
SEED = lsr.SEED
MODELS = ("flux3", "flux2", "qwen", "fibo")
# the four styles of the README sketch examples whose text changed, and two from the plan (watercolor, 3D render)
DEFAULT_STYLES = ("Oil painting", "Stock photo (lifestyle)", "Studio portrait", "Pixel art", "Watercolor", "3D render")
SECS = {"flux3": 30, "qwen": 35, "flux2": 45, "fibo": 70}
VARIANTS = ("neu", "alt")          # neu = with "No drawing lines left.", alt = without (the text before 18.11.)
FAULTS = {"q": ("links", "lines"), "w": ("rechts", "lines"), "a": ("links", "shape"), "s": ("rechts", "shape")}
FAULT_NAME = {"lines": "Linien übrig", "shape": "Form/Aufbau verloren"}


def style_texts() -> dict:
    """{name: text} of the Sketch styles that carry the sentence (the others have nothing to compare)."""
    return {s["name"]: s["text"] for g in styles.load().get("sketch", []) for s in g["styles"]
            if s["text"].rstrip().endswith(models.SKETCH_NO_LINES.strip())}


def text_of(style: str, variant: str, subject: str) -> str:
    text = style_texts()[style].replace(models.SKETCH_MARK, subject)
    if variant == "alt":
        text = text.rstrip()[: -len(models.SKETCH_NO_LINES.strip())].rstrip()
    return text


# the README sketch examples (readme-images/examples/sketch-to-image-*.jpg): always in the sample, so the "neu" picture
# can replace the old example (same model, sketch and seed)
README_CELLS = {("qwen", "Oil painting"): "landscape", ("flux3", "Stock photo (lifestyle)"): "hyenas",
                ("flux2", "Studio portrait"): "hyenas", ("flux2", "Pixel art"): "landscape"}


def jobs(a) -> list:
    """(model, style, sketch, variant), model by model (fewer model loads). The sample (default, user 18.11.: at most one
    hour): every model every style once, the sketch taking turns, the README cells fixed; --full: every sketch."""
    known = style_texts()
    bad = [s for s in a.styles if s not in known]
    if bad:
        sys.exit(f"Not a Sketch style with the sentence: {bad}\nKnown: {', '.join(known)}")
    names = list(a.sketches)
    src = dict(zip(names, lsr.sketch_sources(tuple(lsr.SKETCH_NAMES[n] for n in names))))
    out = []
    for m, mk in enumerate(a.models):
        for i, st in enumerate(a.styles):
            if getattr(a, "full", False):
                cells = names
            else:
                fixed = README_CELLS.get((mk, st))
                cells = [fixed if fixed in src else names[(i + m) % len(names)]]
            out += [(mk, st, src[n], v) for n in cells for v in VARIANTS]
    return out


def cmd_plan(a):
    js = jobs(a)
    for mk, st, s, v in js[:4]:
        print(f"   {mk} {st} {s['file']} {v}: {text_of(st, v, s['desc'])!r}")
    secs = sum(SECS.get(mk, 45) for mk, *_ in js)
    print(f"\n{len(js)} pictures ({len(js) // 2} pairs), about {secs / 3600:.1f} h "
          f"({', '.join(f'{mk} {SECS.get(mk, 45)} s' for mk in a.models)} per picture, rough guess)")


def cmd_run(a):
    js = jobs(a)
    out = BASE / ("dry-" + time.strftime("%Y%m%d-%H%M%S")) if a.dry else (
        Path(a.into) if a.into else BASE / time.strftime("%Y%m%d-%H%M%S"))
    for sub in ("bilder", "eingabe", "xch"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    kf = out / "key.json"
    old = json.load(open(kf, encoding="utf-8")) if kf.exists() else {}
    items, pairs = old.get("items", {}), old.get("pairs", [])
    pics, names = {}, {}
    for _, _, s, _ in js:
        if s["file"] not in pics:
            names[s["file"]] = f"{len(names) + 1}.png"
            pics[s["file"]] = Image.open(s["src"]).convert("RGB")
            pics[s["file"]].save(out / "eingabe" / names[s["file"]])

    base = len(pairs)                    # pairs of an earlier run keep their place (ratings go by position)

    def write_key():
        new = sorted(pairs[base:])
        random.Random(1811).shuffle(new)   # blind: the new pairs mixed, not in run order
        pairs[base:] = new
        json.dump({"items": items, "pairs": pairs, "seed": SEED, "sentence": models.SKETCH_NO_LINES.strip()},
                  open(kf, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    url = a.url or cfgmod.load()["comfyui"]["url"]
    if a.dry:
        comfy = tr.FakeComfy()
    else:
        host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
        try:
            socket.create_connection((host, port), timeout=2).close()
        except OSError:
            sys.exit(f"ComfyUI is not running ({url}). Start it first.")
        comfy = ComfyUI(url)
        inv = inventory.fetch(comfy, cfgmod.model_map())
        for mk in a.models:
            if inv.tab_status(mk).state != "ready":
                print(f"WARNING: {mk}: not all its files are there", flush=True)
    app = live_sketch.make_app("http://127.0.0.1:1" if a.dry else url)
    done = {(it["model_key"], it["style"], it["source"], it["variant"]): fid for fid, it in items.items()}
    rnd = random.Random(1811)
    n, failed, t_start, pending = 0, 0, time.time(), {}
    for mk, st, s, v in js:
        n += 1
        k = (mk, st, s["file"], v)
        if k in done:
            fid = done[k]
        else:
            text = text_of(st, v, s["desc"])
            req = lsr.window_request(app, "B", mk, text)
            t0 = time.time()
            try:
                im, res, _ = lsr.run_one(comfy, req, pics[s["file"]], out / "xch")
            except Exception as e:          # one failing run must not stop the round
                failed += 1
                print(f"{n}/{len(js)} {mk} {st} {s['file']} {v}: FAILED {type(e).__name__}: {e}", flush=True)
                continue
            if a.dry:
                ok = lsr._prompt_in(comfy.graphs[-1], text) and (
                    (v == "neu") == (models.SKETCH_NO_LINES.strip() in json.dumps(comfy.graphs[-1], ensure_ascii=False)))
                print(f"{n}/{len(js)} {mk} {st} {s['file']} {v}: {Path(req.workflow or '').name}, "
                      f"text in graph: {'yes' if ok else 'NO'}", flush=True)
                failed += not ok
                continue
            fid = f"{len(items) + 1:04d}"
            im.save(out / "bilder" / f"{fid}.png")
            items[fid] = {"model": models.BY_KEY[mk].label, "model_key": mk, "style": st, "source": s["file"],
                          "input": names[s["file"]], "desc": s["desc"], "variant": v, "text": text,
                          "caption": res.get("vgl", ""), "seed": SEED, "secs": round(time.time() - t0, 1)}
            done[k] = fid
            if a.free:
                lsr.free_memory(comfy)
        pk = (mk, st, s["file"])
        pending.setdefault(pk, []).append(fid)
        if len(pending[pk]) == 2 and not any(set(p) == set(pending[pk]) for p in pairs):
            pair = list(pending[pk])
            rnd.shuffle(pair)                      # which side is new stays hidden
            pairs.append(pair)
        if not a.dry:
            write_key()
    app.root.destroy()
    if a.dry:
        shutil.rmtree(out, ignore_errors=True)    # a dry run leaves no folder behind
    print(f"\n{'DRY RUN' if a.dry else 'DONE'} in {(time.time() - t_start) / 60:.1f} min: "
          f"{len(js) if a.dry else len(items)} pictures, {failed} failed"
          + ("" if a.dry else f", in {out}\nNext: python tests\\live_sketch_nolines.py rate"), flush=True)
    return failed


def latest(folder):
    if folder:
        return Path(folder)
    runs = sorted(p for p in BASE.iterdir() if (p / "key.json").exists() and not p.name.startswith("dry-")) \
        if BASE.exists() else []
    if not runs:
        sys.exit(f"No round in {BASE}")
    return runs[-1]


def cmd_rate(a):
    import tkinter as tk
    from PIL import ImageTk
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    pairs, items = key["pairs"], key["items"]
    fout = out / "bewertung.json"
    data = json.loads(fout.read_text(encoding="utf-8")) if fout.exists() else {}
    root = tk.Tk()
    root.title("Sketch: No drawing lines left – blind vergleichen")
    root.configure(bg="#282828")
    st = {"i": next((k for k in range(len(pairs)) if not data.get(str(k), {}).get("wahl")), 0), "loading": False}
    choice, note = tk.StringVar(), tk.StringVar()
    flags = {f: tk.BooleanVar() for f in FAULTS}
    top = tk.Label(root, bg="#282828", fg="#e6e6e6", font=("Segoe UI", 12, "bold"), wraplength=1800, justify="left")
    top.pack(pady=(8, 4))
    row = tk.Frame(root, bg="#282828")
    row.pack()
    pics = []
    for cap in ("Skizze", "links", "rechts"):
        col = tk.Frame(row, bg="#282828")
        col.pack(side="left", padx=6)
        tk.Label(col, text=cap, bg="#282828", fg="#9a9a9a").pack()
        pics.append(tk.Label(col, bg="#282828"))
        pics[-1].pack()
    kw = dict(bg="#282828", selectcolor="#535353", activebackground="#282828", activeforeground="#ffffff",
              font=("Segoe UI", 11), command=lambda: save())
    side = tk.Frame(root, bg="#282828")
    side.pack(pady=6)
    for k, (label, val) in enumerate((("links besser", "links"), ("gleich gut", "gleich"), ("rechts besser", "rechts"),
                                      ("beide schlecht", "beide schlecht")), 1):
        tk.Radiobutton(side, text=f"{label} ({k})", variable=choice, value=val, fg="#e6e6e6", **kw).pack(side="left", padx=8)
    ff = tk.Frame(root, bg="#282828")
    ff.pack(pady=2)
    for f, (where, what) in FAULTS.items():
        tk.Checkbutton(ff, text=f"{where}: {FAULT_NAME[what]} ({f.upper()})", variable=flags[f], fg="#f0c674", **kw
                       ).pack(side="left", padx=8)
    nf = tk.Frame(root, bg="#282828")
    nf.pack(pady=4)
    tk.Label(nf, text="Notiz:", bg="#282828", fg="#cfcfcf").pack(side="left")
    ent = tk.Entry(nf, textvariable=note, bg="#535353", fg="#ffffff", insertbackground="#ffffff", width=90)
    ent.pack(side="left", padx=6)
    nav = tk.Frame(root, bg="#282828")
    nav.pack(pady=4)
    tk.Button(nav, text="← Zurück", command=lambda: go(-1)).pack(side="left")
    tk.Button(nav, text="Weiter →", command=lambda: go(1)).pack(side="left", padx=8)
    status = tk.Label(nav, bg="#282828", fg="#9a9a9a")
    status.pack(side="left", padx=16)

    def count():
        status.configure(text=f"bewertet: {sum(1 for k in range(len(pairs)) if data.get(str(k), {}).get('wahl'))}/"
                              f"{len(pairs)}  ·  Fehler auch bei „besser“ ankreuzen  ·  {fout}")

    def show():
        i = st["i"]
        left, right = pairs[i]
        it = items[left]
        top.configure(text=f"Paar {i + 1}/{len(pairs)}  ·  Stil: {it['style']}  ·  Skizze: {it['desc']}")
        px = min((root.winfo_screenwidth() - 80) // 3, root.winfo_screenheight() - 300)
        st["photos"] = []
        for lbl, path in zip(pics, (out / "eingabe" / it["input"], out / "bilder" / f"{left}.png",
                                    out / "bilder" / f"{right}.png")):
            im = Image.open(path).convert("RGB")
            im.thumbnail((px, px))
            st["photos"].append(ImageTk.PhotoImage(im))
            lbl.configure(image=st["photos"][-1])
        st["loading"] = True
        rec = data.get(str(i), {})
        choice.set(rec.get("wahl", ""))
        note.set(rec.get("notiz", ""))
        for f, (where, what) in FAULTS.items():
            flags[f].set(what in rec.get("fehler_" + where, []))
        st["loading"] = False
        count()

    def save():
        if st["loading"]:
            return
        i = st["i"]
        rec = {"links": pairs[i][0], "rechts": pairs[i][1], "wahl": choice.get(), "notiz": note.get().strip()}
        for where in ("links", "rechts"):
            rec["fehler_" + where] = [what for f, (w, what) in FAULTS.items() if w == where and flags[f].get()]
        data[str(i)] = rec
        fout.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        count()

    def go(step):
        st["i"] = max(0, min(len(pairs) - 1, st["i"] + step))
        show()

    def key_press(e):
        if root.focus_get() is ent:
            return
        c = (e.char or "").lower()
        if c in ("1", "2", "3", "4"):
            choice.set({"1": "links", "2": "gleich", "3": "rechts", "4": "beide schlecht"}[c])
            save()
            root.after(250, lambda: go(1))
        elif c in FAULTS:
            flags[c].set(not flags[c].get())
            save()
        elif e.keysym in ("Right", "Left"):
            go(1 if e.keysym == "Right" else -1)

    note.trace_add("write", lambda *x: save())
    root.bind("<Key>", key_press)
    root.bind("<Button-1>", lambda e: root.focus_set() if e.widget in pics else None)
    root.state("zoomed")
    show()
    root.mainloop()


def summarize(key: dict, data: dict) -> str:
    """Wins of new against old, and how often each variant kept lines or lost the shape; per model and per style."""
    items = key["items"]
    zero = lambda: {"neu": 0, "alt": 0, "gleich": 0, "beide schlecht": 0, "lines neu": 0, "lines alt": 0,
                    "shape neu": 0, "shape alt": 0, "n": 0}
    total, per = zero(), {}
    for rec in data.values():
        w = rec.get("wahl")
        if not w:
            continue
        it = items[rec["links"]]
        rows = [total, per.setdefault(("Modell", it["model"]), zero()), per.setdefault(("Stil", it["style"]), zero())]
        for r in rows:
            r["n"] += 1
            r[items[rec[w]]["variant"] if w in ("links", "rechts") else w] += 1
            for where in ("links", "rechts"):
                for what in rec.get("fehler_" + where, []):
                    r[f"{what} {items[rec[where]]['variant']}"] += 1
    head = ("| | Paare | neu besser | alt besser | gleich | beide schlecht | Linien übrig neu / alt "
            "| Form verloren neu / alt |\n|---|---|---|---|---|---|---|---|")

    def line(name, r):
        return (f"| {name} | {r['n']} | {r['neu']} | {r['alt']} | {r['gleich']} | {r['beide schlecht']} "
                f"| {r['lines neu']} / {r['lines alt']} | {r['shape neu']} / {r['shape alt']} |")

    rated = total["n"]
    out = [f"# Sketch: „No drawing lines left.“ (A/B, blind)", "",
           f"Bewertet: {rated} von {len(key['pairs'])} Paaren; neu = mit dem Satz, alt = ohne (Text vor dem 18.11.); "
           f"Seed {key.get('seed', SEED)}.", "", head, line("**alle**", total)]
    for kind in ("Modell", "Stil"):
        out += [line(name, r) for (k, name), r in sorted(per.items()) if k == kind]
    notes = [(items[r["links"]], r["notiz"]) for r in data.values() if r.get("notiz")]
    if notes:
        out += ["", "Notizen:"] + [f"- {it['model']}, {it['style']}, {it['desc']}: {n}" for it, n in notes]
    return "\n".join(out) + "\n"


def cmd_summary(a):
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    fout = out / "bewertung.json"
    text = summarize(key, json.loads(fout.read_text(encoding="utf-8")) if fout.exists() else {})
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        s = sub.add_parser(name)
        s.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
        s.add_argument("--styles", nargs="+", default=list(DEFAULT_STYLES))
        s.add_argument("--sketches", nargs="+", choices=list(lsr.SKETCH_NAMES), default=list(lsr.SKETCH_NAMES))
        s.add_argument("--full", action="store_true", help="every sketch per style and model (3x the sample)")
        if name == "run":
            s.add_argument("--url")
            s.add_argument("--into")
            s.add_argument("--dry", action="store_true")
            s.add_argument("--free", action="store_true")
    for name in ("rate", "summary"):
        sub.add_parser(name).add_argument("folder", nargs="?")
    a = p.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
