"""Manual check (not part of run_all.py): the MiniMax H3 Image Edit blind test (docs/tests/minimax-edit-testplan.md,
17.11.2026; docs/plan-minimax-h3-image.md step 7, part Edit). Does MiniMax Edit keep up with Flux 3 and Qwen Image 2.1,
and where are its weak spots? 13 edits on 4 photos x 5 passes = 65 pictures, seed 1234, through the real plugin path of
live_style_round.py (the window's request with the start settings of Edit canvas, the bridge with the PhotoCraft
simulator, the real ComfyUI):

- mm4:      MiniMax with its start settings (4 MP, prompt writer on, "Downsize to canvas" on);
- mm4-nopw: the same without the prompt writer (checks the decision of 11.11.: writer on);
- mm8:      MiniMax at 8 MP, writer on (the bench suggested 8 to 16 MP);
- flux3, qwen: Flux 3 Klein Edit and Qwen Image 2.1 with their start settings (the comparison).

    python tests\\live_minimax_edit.py plan [--photos <folder>] [--passes mm4 flux3 ...]
    python tests\\live_minimax_edit.py run [--photos <folder>] [--passes ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_minimax_edit.py rate [folder]      (blind: input left, result right; good / bad, faults 1 to 6)
    python tests\\live_minimax_edit.py summary [folder]   (good and fault-free good per pass, edit, photo; ergebnis.md)

``--dry`` runs the whole bridge against a fake ComfyUI (no GPU) and checks that the text reaches the graph, the size and
the writer of each pass. The result is always the newest document (MiniMax without "Downsize" opens a new one).
Output: data\\minimax-edit\\<time>\\ (eingabe\\, bilder\\, key.json, bewertung.json, ergebnis.md).
"""
import argparse
import json
import random
import shutil
import socket
import sys
import time
from dataclasses import replace
from pathlib import Path

import live_style_round as lsr          # sets its own PCCOMFY_HOME before the plugin is imported
from PIL import Image

from pccomfy import bridge, config as cfgmod, inventory, models
from pccomfy.comfy import ComfyUI
import test_reference_mode as tr

BASE = lsr.DATA / "minimax-edit"
SEED = lsr.SEED
PHOTOS_DIR = r"D:\testpics\testpics1\auswahl"          # only on PC A (memory testbilder-orte)
PHOTOS = {
    "robot": "Screenshot 2025-03-14 093042.png",
    "night": "Screenshot 2025-04-23 214731.png",
    "beach": "Screenshot 2025-05-22 184738.png",
    "ruin": "signal-2024-11-02-214028_007.jpeg",
}
EDITS = [   # (number, photo, prompt) as in the test plan
    (1, "robot", "Replace the rocket in the robot's raised hand with a glowing blue lantern."),
    (2, "robot", "Turn the robot's metal body into polished gold, keep the background unchanged."),
    (3, "robot", 'Add the word "HELIOS" in bold white capital letters at the bottom of the picture.'),
    (4, "night", "Make it a bright snowy winter morning, keep both people and their poses."),
    (5, "night", "Remove the person on the right."),
    (6, "night", "Give the person on the left a burning torch in his hand that lights up both faces."),
    (7, "beach", "Add three surfers carrying surfboards walking along the waterline."),
    (8, "beach", "Make it sunset, the sun low above the sea behind the buildings, warm backlight."),
    (9, "beach", "Add a red lifeguard tower on the sand in the foreground."),
    (10, "beach", "Turn the picture into a watercolor painting."),
    (11, "ruin", "Restore the castle to its original state, with roofs, intact walls and windows."),
    (12, "ruin", "Make it autumn with orange and red leaves on the trees."),
    (13, "ruin", "Add a group of five tourists standing in the courtyard."),
]
# pass -> (model key, changes to the start settings of Edit canvas)
PASSES = {
    "mm4": ("minimax", {}),
    "mm4-nopw": ("minimax", {"enhance": False}),
    "mm8": ("minimax", {"gen_mp": 8}),
    "flux3": ("flux3", {}),
    "qwen": ("qwen", {}),
}
PASS_NAME = {"mm4": "MiniMax 4 MP, Schreiber an", "mm4-nopw": "MiniMax 4 MP, ohne Schreiber",
             "mm8": "MiniMax 8 MP, Schreiber an", "flux3": "Flux 3 Klein Edit", "qwen": "Qwen Image 2.1"}
SECS = {"mm4": 65, "mm4-nopw": 20, "mm8": 90, "flux3": 15, "qwen": 20}   # rough seconds per picture (test plan)

FAULTS = (
    ("1", "task", "Auftrag nicht erfüllt"),
    ("2", "changed", "Rest verändert (Personen, Gesicht, Aufbau)"),
    ("3", "count", "falsche Menge"),
    ("4", "text", "Schrift falsch"),
    ("5", "artifact", "Bildfehler (Hände, Verzerrung)"),
    ("6", "soft", "unscharf oder matschig"),
)
GOOD, BAD = "gut", "schlecht"


def photo_sources(folder) -> dict:
    d = Path(folder or PHOTOS_DIR)
    missing = [f for f in PHOTOS.values() if not (d / f).exists()]
    if missing:
        sys.exit(f"Photos missing in {d}: {missing} (--photos <folder>; the photos are only on PC A)")
    return {k: d / f for k, f in PHOTOS.items()}


def jobs(passes) -> list:
    """(pass, number, photo, prompt) in run order: pass by pass (fewer model loads)."""
    return [(p, n, ph, text) for p in passes for n, ph, text in EDITS]


def cmd_plan(a):
    photo_sources(a.photos)
    js = jobs(a.passes)
    for p in a.passes:
        mk, over = PASSES[p]
        print(f"{p}: {PASS_NAME[p]} ({mk}, {over or 'start settings'}), {len(EDITS)} pictures")
    secs = sum(SECS[p] for p, *_ in js)
    print(f"\n{len(js)} pictures, about {secs / 60:.0f} min (rough guess per picture: "
          + ", ".join(f"{p} {SECS[p]} s" for p in a.passes) + ")")


def window_request(app, p: str, text: str):
    """The Request the window sends in Edit canvas with the model's start settings (saved pages ignored), the pass'
    changes on top, seed 1234."""
    mk, over = PASSES[p]
    app.v_model.set(mk)
    app.v_mode.set("edit")
    app._factory = True
    try:
        app._on_model()
        app._on_mode()
    finally:
        app._factory = False
    if "gen_mp" in over:
        app.v_gen_mp.set(over["gen_mp"])
    if "enhance" in over:
        app.v_enhance.set(over["enhance"])
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", text)
    req = app._request()
    req.params = replace(req.params, seed=SEED)
    return req


def prompt_in(graph, text: str) -> bool:
    """live_style_round._prompt_in on the graph's strings, not its JSON text (there the quotes of "HELIOS" are \\")."""
    strings = []

    def walk(x):
        if isinstance(x, str):
            strings.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(graph)
    blob = "\n".join(strings)
    return all(w in blob for w in [w for w in text.replace("\n", " ").split() if len(w) > 4][:6])


def check(p: str, req) -> list:
    """What a dry run checks besides the text: MiniMax at the pass' size, as a layer, the writer as the pass wants."""
    mk, over = PASSES[p]
    bad = []
    if mk == "minimax":
        want_mp = over.get("gen_mp", models.MINIMAX_EDIT["gen_mp"])
        want_pw = over.get("enhance", models.MINIMAX_EDIT["enhance"])
        if req.gen_mp != want_mp:
            bad.append(f"size {req.gen_mp} MP, wanted {want_mp}")
        if req.new_document:
            bad.append("opens a new document")
        if bool(req.enhance) != want_pw:
            bad.append(f"writer {'on' if req.enhance else 'off'}, wanted {'on' if want_pw else 'off'}")
    return bad


def run_one(comfy, req, pic: Image.Image, exch: Path):
    """One run as the plugin makes it; the result is the newest document (live_t2i_styles.run_one)."""
    tr.W, tr.H = pic.size
    pc = tr.FakePC(exch)
    pc.docs.append(tr.Doc("photo.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True, "name": "Background"}]))
    res = bridge.Bridge(pc, comfy, exch).run(req)
    return tr.FakePC.composite(pc.docs[-1]).convert("RGB"), res


def cmd_run(a):
    srcs = photo_sources(a.photos)
    js = jobs(a.passes)
    out = BASE / ("dry-" + time.strftime("%Y%m%d-%H%M%S")) if a.dry else (
        Path(a.into) if a.into else BASE / time.strftime("%Y%m%d-%H%M%S"))
    for sub in ("bilder", "eingabe", "xch"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    pics = {}
    for k, src in srcs.items():
        pics[k] = Image.open(src).convert("RGB")
        pics[k].save(out / "eingabe" / f"{k}.png")
    kf = out / "key.json"
    old = json.load(open(kf, encoding="utf-8")) if kf.exists() else {}
    key, order = old.get("items", {}), list(old.get("order", []))
    base = len(order)

    def write_key():
        new = sorted(f for f in key if f not in order[:base])     # blind: this run's pictures mixed after the old ones
        random.Random(1711).shuffle(new)
        order[base:] = new
        json.dump({"items": key, "order": order, "seed": SEED, "passes": {p: [PASSES[p][0], PASSES[p][1]] for p in PASSES}},
                  open(kf, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    if a.dry:
        comfy = tr.FakeComfy()
    else:
        url = a.url or cfgmod.load()["comfyui"]["url"]
        host, port = url.split("//")[-1].split(":")[0], int(url.rsplit(":", 1)[-1].strip("/"))
        try:
            socket.create_connection((host, port), timeout=2).close()
        except OSError:
            sys.exit(f"ComfyUI is not running ({url}). Start it first.")
        comfy = ComfyUI(url)
        inv = inventory.fetch(comfy, cfgmod.model_map())
        for mk in sorted({PASSES[p][0] for p in a.passes}):
            if inv.tab_status(mk).state != "ready":
                print(f"WARNING: {mk}: not all its files are there", flush=True)
    app = lsr.live_sketch.make_app("http://127.0.0.1:1" if a.dry else (a.url or cfgmod.load()["comfyui"]["url"]))
    failed, t_start = 0, time.time()
    for i, (p, n, ph, text) in enumerate(js, 1):
        fid = f"{p}-{n:02d}"
        if fid in key:
            continue
        req = window_request(app, p, text)
        t0 = time.time()
        try:
            im, res = run_one(comfy, req, pics[ph], out / "xch")
        except Exception as e:            # one failing run must not stop the round
            failed += 1
            print(f"{i}/{len(js)} {fid} {ph}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        if a.dry:
            bad = ([] if prompt_in(comfy.graphs[-1], text) else ["text not in graph"]) + check(p, req)
            failed += bool(bad)
            print(f"{i}/{len(js)} {fid} {ph}: {Path(req.workflow or '').name}, {req.gen_mp or '-'} MP, "
                  f"writer {'on' if req.enhance else 'off'}, result {im.size[0]}x{im.size[1]}: "
                  + ("ok" if not bad else "PROBLEM: " + "; ".join(bad)), flush=True)
            continue
        im.save(out / "bilder" / f"{fid}.png")
        key[fid] = {"pass": p, "model": models.BY_KEY[PASSES[p][0]].label, "model_key": PASSES[p][0], "edit": n,
                    "photo": ph, "input": f"{ph}.png", "text": text, "caption": res.get("vgl", ""), "seed": SEED,
                    "secs": round(time.time() - t0, 1)}
        write_key()
        print(f"{i}/{len(js)} {fid} {ph}: {key[fid]['secs']} s", flush=True)
        if a.free:
            lsr.free_memory(comfy)
    app.root.destroy()
    if a.dry:
        shutil.rmtree(out, ignore_errors=True)       # a dry run leaves no folder behind
    else:
        write_key()
    print(f"\n{'DRY RUN' if a.dry else 'DONE'} in {(time.time() - t_start) / 60:.1f} min, {len(js)} pictures, {failed} failed"
          + ("" if a.dry else f", in {out}\nNext: python tests\\live_minimax_edit.py rate"), flush=True)
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
    """One result at a time beside its input, the prompt above; the model stays hidden. Keys: G good, S bad, 1 to 6
    faults (also on good), arrows."""
    import tkinter as tk
    from PIL import ImageTk
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    items, order = key["items"], key["order"]
    fout = out / "bewertung.json"
    data = json.loads(fout.read_text(encoding="utf-8")) if fout.exists() else {}
    root = tk.Tk()
    root.title("MiniMax Edit bewerten (blind)")
    root.configure(bg="#282828")
    st = {"i": next((k for k, f in enumerate(order) if not data.get(f, {}).get("wahl")), 0), "loading": False}
    faults = {code: tk.BooleanVar() for _, code, _ in FAULTS}
    choice, note = tk.StringVar(), tk.StringVar()
    top = tk.Label(root, bg="#282828", fg="#e6e6e6", font=("Segoe UI", 12, "bold"), wraplength=1800, justify="left")
    top.pack(pady=(8, 4))
    row = tk.Frame(root, bg="#282828")
    row.pack()
    pics = [tk.Label(row, bg="#282828") for _ in range(2)]
    for lbl in pics:
        lbl.pack(side="left", padx=6)
    side = tk.Frame(root, bg="#282828")
    side.pack(pady=6)
    kw = dict(bg="#282828", selectcolor="#535353", activebackground="#282828", activeforeground="#ffffff",
              font=("Segoe UI", 11), command=lambda: save())
    tk.Radiobutton(side, text="gut (G)", variable=choice, value=GOOD, fg="#7bd389", **kw).pack(side="left", padx=12)
    tk.Radiobutton(side, text="schlecht (S)", variable=choice, value=BAD, fg="#f07b7b", **kw).pack(side="left", padx=12)
    ff = tk.Frame(root, bg="#282828")
    ff.pack(pady=2)
    tk.Label(ff, text="Fehler ankreuzen (Tasten 1–6, auch bei „gut“ möglich):", bg="#282828", fg="#cfcfcf",
             font=("Segoe UI", 10)).grid(row=0, column=0, columnspan=3, sticky="w")
    for k, (digit, code, text) in enumerate(FAULTS):
        tk.Checkbutton(ff, text=f"{digit}  {text}", variable=faults[code], bg="#282828", fg="#f0c674", selectcolor="#535353",
                       activebackground="#282828", activeforeground="#ffffff", font=("Segoe UI", 10),
                       command=lambda: save()).grid(row=1 + k // 3, column=k % 3, sticky="w", padx=8)
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
        status.configure(text=f"bewertet: {sum(1 for f in order if data.get(f, {}).get('wahl'))}/{len(order)}  ·  gespeichert in {fout}")

    def show():
        fid = order[st["i"]]
        it = items[fid]
        top.configure(text=f"Bild {st['i'] + 1}/{len(order)}  ·  Edit {it['edit']}: {it['text']}")
        side_px = min((root.winfo_screenwidth() - 60) // 2, root.winfo_screenheight() - 330)
        st["photos"] = []
        for lbl, path in zip(pics, (out / "eingabe" / it["input"], out / "bilder" / f"{fid}.png")):
            im = Image.open(path).convert("RGB")
            im.thumbnail((side_px, side_px))
            ph = ImageTk.PhotoImage(im)
            st["photos"].append(ph)
            lbl.configure(image=ph)
        st["loading"] = True
        rec = data.get(fid, {})
        choice.set(rec.get("wahl", ""))
        note.set(rec.get("notiz", ""))
        for code, var in faults.items():
            var.set(code in rec.get("fehler", []))
        st["loading"] = False
        count()

    def save():
        if st["loading"]:
            return
        fid = order[st["i"]]
        data[fid] = {"wahl": choice.get(), "notiz": note.get().strip(),
                     "fehler": [code for _, code, _ in FAULTS if faults[code].get()]}
        fout.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        count()

    def go(step):
        st["i"] = max(0, min(len(order) - 1, st["i"] + step))
        show()

    def key_press(e):
        if root.focus_get() is ent:
            return
        if e.char.lower() in ("g", "s"):
            choice.set(GOOD if e.char.lower() == "g" else BAD)
            save()
            root.after(250, lambda: go(1))
        elif e.keysym in ("Right", "Left"):
            go(1 if e.keysym == "Right" else -1)
        elif e.char in {d for d, _, _ in FAULTS}:
            var = faults[next(c for d, c, _ in FAULTS if d == e.char)]
            var.set(not var.get())
            save()

    note.trace_add("write", lambda *x: save())
    root.bind("<Key>", key_press)
    root.bind("<Button-1>", lambda e: root.focus_set() if e.widget in pics else None)
    root.state("zoomed")
    show()
    root.mainloop()


def summarize(key: dict, data: dict) -> str:
    """Good and fault-free good (memory: he often calls a picture with a fault good) per pass, edit and photo, the faults
    per pass and the mean time per pass."""
    items = key["items"]
    rows, faults, secs = {}, {}, {}
    for fid, it in items.items():
        secs.setdefault(it["pass"], []).append(it["secs"])
        rec = data.get(fid, {})
        if not rec.get("wahl"):
            continue
        good = rec["wahl"] == GOOD
        clean = good and not rec.get("fehler")
        for k in (("Durchgang", PASS_NAME.get(it["pass"], it["pass"])), ("Foto", it["photo"]),
                  ("Edit", f"{it['edit']:02d} {it['text'][:60]}"),
                  ("Edit × Durchgang", f"{it['edit']:02d} · {PASS_NAME.get(it['pass'], it['pass'])}")):
            r = rows.setdefault(k, [0, 0, 0])
            r[0] += 1
            r[1] += good
            r[2] += clean
        for f in rec.get("fehler", []):
            faults[(it["pass"], f)] = faults.get((it["pass"], f), 0) + 1
    rated = sum(1 for f in items if data.get(f, {}).get("wahl"))
    lines = [f"# MiniMax Edit Blindtest {key.get('folder', '')}".rstrip(), "",
             f"Bewertet: {rated} von {len(items)} (blind, Seed {SEED})", ""]
    for kind in ("Durchgang", "Foto", "Edit", "Edit × Durchgang"):
        sub = sorted((name, r) for (k, name), r in rows.items() if k == kind)
        if sub:
            lines += [f"## Je {kind}", "", f"| {kind} | bewertet | gut | fehlerfrei gut |", "|---|---|---|---|"]
            lines += [f"| {name} | {r[0]} | {r[1]} | {r[2]} |" for name, r in sub] + [""]
    if faults:
        names = {c: t for _, c, t in FAULTS}
        lines += ["## Fehler je Durchgang (auch bei „gut“)", "", "| Durchgang | Fehler | Anzahl |", "|---|---|---|"]
        lines += [f"| {PASS_NAME.get(p, p)} | {names.get(c, c)} | {n} |" for (p, c), n in sorted(faults.items())] + [""]
    lines += ["## Zeit je Bild", "", "| Durchgang | Bilder | Mittel s |", "|---|---|---|"]
    lines += [f"| {PASS_NAME.get(p, p)} | {len(v)} | {sum(v) / len(v):.0f} |" for p, v in sorted(secs.items())] + [""]
    notes = [(items[f], r["notiz"]) for f, r in data.items() if r.get("notiz") and f in items]
    if notes:
        lines += ["## Notizen", ""] + [f"- {PASS_NAME.get(it['pass'], it['pass'])}, Edit {it['edit']}: {n}" for it, n in notes]
    return "\n".join(lines) + "\n"


def cmd_summary(a):
    out = latest(a.folder)
    key = json.load(open(out / "key.json", encoding="utf-8"))
    key["folder"] = out.name
    data = json.loads((out / "bewertung.json").read_text(encoding="utf-8")) if (out / "bewertung.json").exists() else {}
    text = summarize(key, data)
    (out / "ergebnis.md").write_text(text, encoding="utf-8")
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        r = sub.add_parser(name)
        r.add_argument("--photos", help=f"the folder of the four photos (default {PHOTOS_DIR})")
        r.add_argument("--passes", nargs="+", default=list(PASSES), choices=list(PASSES))
        if name == "run":
            r.add_argument("--into", help="resume in this folder")
            r.add_argument("--dry", action="store_true", help="the whole bridge against a fake ComfyUI, no GPU")
            r.add_argument("--free", action="store_true", help="ask ComfyUI to free memory after every run")
            r.add_argument("--url", help="the ComfyUI address (default: config of PCCOMFY_HOME)")
    for name in ("rate", "summary"):
        s = sub.add_parser(name)
        s.add_argument("folder", nargs="?", help="the round's folder (default: the newest)")
    a = ap.parse_args()
    res = {"plan": cmd_plan, "run": cmd_run, "rate": cmd_rate, "summary": cmd_summary}[a.cmd](a)
    sys.exit(1 if a.cmd == "run" and res else 0)


if __name__ == "__main__":
    main()
