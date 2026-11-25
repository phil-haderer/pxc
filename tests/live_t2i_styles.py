"""Manual check (not part of run_all.py): Text to image examples with the built-in styles (user 17.11.2026: "with every
model 3 pictures with our style prompts, an interesting subject with some details before the prompt"), for the README.

Seven models x 3 (subject, style) pairs, every style only once. The text is what the Styles button makes: the subject,
a line break, the style's text from pccomfy/assets/styles.json (mode txt2img). Through the real plugin path of
live_style_round.py (the window's request with the start settings of Text to image, the bridge with the PhotoCraft
simulator, the real ComfyUI), seed 1234, an empty white canvas of CANVAS.

    python tests\\live_t2i_styles.py plan
    python tests\\live_t2i_styles.py run [--models flux3 qwen ...] [--into <folder>] [--dry] [--free] [--url http://<ip>:8188]
    python tests\\live_t2i_styles.py run --anime [--into <folder>]   (Anime, golden sky with the text of styles.json; 17.11., 18.11.)
    python tests\\live_t2i_styles.py run --redo [--models flux2 fibo] [--url ...]   (the 3 README pictures whose style text changed; 18.11.)
    python tests\\live_t2i_styles.py view [folder]      (data\\t2i-styles\\<time>\\ansicht.html; a click shows 100 %)

Output: data\\t2i-styles\\<time>\\bilder\\<model>-<n>.png and key.json (resumes in --into).
"""
import argparse
import json
import shutil
import socket
import sys
import time
from pathlib import Path

from live_progress import Left         # what is left of the round
import live_style_round as lsr          # sets its own PCCOMFY_HOME before the plugin is imported
from PIL import Image

from pccomfy import config as cfgmod, inventory, models, styles
from pccomfy.comfy import ComfyUI
import test_reference_mode as tr

BASE = lsr.DATA / "t2i-styles"
CANVAS = (1536, 1024)                   # 3:2 landscape, the shape of the README pairs
SEED = lsr.SEED

# model key -> [(style name in styles.json, subject)], every style once over all models
PLAN = {
    "flux3": [("Street photo, rainy and muted", "an elderly flower seller under a striped awning in a narrow cobbled street, "
               "buckets of tulips and peonies, a bicycle leaning against the wall"),
              ("Tilt-shift, miniature look", "a busy harbour with colourful fishing boats, stacked containers, a red crane "
               "and tiny people on the quay"),
              ("Watercolor storybook", "a fox in a knitted scarf reading a map by lantern light in a snowy forest, a small "
               "backpack beside him")],
    "flux2": [("Food photography", "a stack of fluffy pancakes with blueberries, maple syrup dripping down the side, powdered "
               "sugar and a cup of coffee in the background"),
              ("Linocut print", "a grey heron standing in reeds at a misty lake, a wooden rowing boat and distant pine trees"),
              ("Claymation, stop-motion", "a tiny astronaut planting a flower on a small rocky planet, a little rover and a "
               "waving green alien beside him")],
    "qwen": [("Mid-century travel poster", "a cable car above an alpine village with a turquoise lake, the word \"ALPENSEE\" "
              "in large letters at the top"),
             ("Product photo, colour backdrop", "an open vintage brass pocket watch with an engraved lid, its chain curled "
              "beside it"),
             ("Anime, golden sky", "a small railway station on a hill, a red train arriving, sunflowers along the "
              "platform")],
    "moss": [("Studio portrait", "an old fisherman with a weathered face, a grey knitted cap and a wooden pipe"),
             ("Impressionist painting, sunny", "a café terrace by the sea with white tablecloths, a waiter carrying a tray "
              "and sailboats in the bay"),
             ("Neon city night, bokeh", "a ramen stall in a narrow alley, steam rising from the pots, a cook in a white "
              "headband")],
    "krea2": [("Dark fantasy, glowing neon", "a lone knight with a glowing sword at the gate of a ruined castle, ravens "
              "circling above the towers"),
             ("Japanese ink wash", "two cranes flying over misty mountains, a small temple on a cliff"),
             ("3D clay render", "a cosy treehouse with a rope ladder, paper lanterns and a cat sleeping on the balcony")],
    "fibo": [("Golden hour travel photo", "a hot air balloon festival over rolling vineyards, dozens of colourful balloons "
              "and an old stone farmhouse"),
             ("Vintage paper collage", "a whale swimming through the clouds above a small town, little birds around it"),
             ("Low-poly game look", "a desert oasis with palm trees, a camel caravan and an old caravanserai")],
    "minimax": [("Business headshot", "a woman in her thirties with short black hair and round glasses, a navy blazer"),
                ("Cyberpunk neon, rain", "a delivery robot crossing a crowded market street, holographic signs and "
                 "people with umbrellas"),
                ("Oil painting, 19th-century realism", "a blacksmith at his anvil, sparks flying, tools hanging on the "
                 "wall behind him")],
}
SECS = {"flux3": 30, "flux2": 45, "qwen": 30, "moss": 60, "krea2": 30, "fibo": 70, "minimax": 120}   # rough guess


# --anime (user 17.11.): Qwen drew "Anime background, golden sky" as a photo-like sunset; the Krea text says "anime" once and
# then only light words. The new text for every model, two subjects (the railway station of the first run and a second one)
# 18.11. (user): "background" out of name and text, "Anime, golden sky"; the text comes from styles.json
ANIME_STYLE = "Anime, golden sky"
ANIME_SUBJECTS = ("a small railway station on a hill, a red train arriving, sunflowers along the platform",
                  "a girl on a bicycle riding along a coastal road, a lighthouse and the sea below")


# --redo (user 18.11.): the README pictures whose style text changed (docs/archiv/stil-vorschlag-18-11.md) again, with the same
# model, subject, seed and canvas as in the run of 17.11.; only the style text is new
REDO = [("flux2", 2), ("fibo", 3), ("minimax", 2)]     # Linocut print, Low-poly, Cyberpunk (the Oil painting blacksmith is out, 18.11.)


def style_texts() -> dict:
    return {s["name"]: s["text"] for g in styles.load()["txt2img"] for s in g["styles"]}


def jobs(models_wanted, anime=False, redo=False) -> list:
    st = style_texts()
    out = []
    if anime:
        return [(mk, f"anime{n}", ANIME_STYLE + " (new text)", subj, subj + "\n" + st[ANIME_STYLE])
                for mk in models_wanted for n, subj in enumerate(ANIME_SUBJECTS, 1)]
    for mk in models_wanted:
        for n, (style, subject) in enumerate(PLAN[mk], 1):
            if redo and (mk, n) not in REDO:
                continue
            if style not in st:
                sys.exit(f"style not in styles.json: {style}")
            out.append((mk, n, style, subject, subject + "\n" + st[style]))
    return out


def cmd_plan(a):
    js = jobs(a.models, a.anime, a.redo)
    for mk, n, style, subject, _ in js:
        print(f"{models.BY_KEY[mk].label:22} {n}  {style:34} {subject}")
    secs = sum(SECS.get(mk, 60) for mk, *_ in js)
    print(f"\n{len(js)} pictures, about {secs / 60:.0f} min (rough guess), canvas {CANVAS[0]}x{CANVAS[1]}")


def run_one(comfy, req, pic, exch):
    """live_style_round.run_one, but the result is the newest document: MiniMax opens its Text to image result as a new
    document (no "Downsize to canvas", user 10.11.), so the first document stays the white canvas (17.11.: 3 white pictures)."""
    tr.W, tr.H = pic.size
    pc = tr.FakePC(exch)
    pc.docs.append(tr.Doc("photo.png", [{"id": 1, "img": pic.convert("RGBA"), "visible": True, "name": "Background"}]))
    res = lsr.bridge.Bridge(pc, comfy, exch).run(req)
    return tr.FakePC.composite(pc.docs[-1]).convert("RGB"), res


def cmd_run(a):
    js = jobs(a.models, a.anime, a.redo)
    out = BASE / ("dry-" + time.strftime("%Y%m%d-%H%M%S")) if a.dry else (
        Path(a.into) if a.into else BASE / time.strftime("%Y%m%d-%H%M%S"))
    for sub in ("bilder", "xch"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    kf = out / "key.json"
    key = json.load(open(kf, encoding="utf-8"))["items"] if kf.exists() else {}
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
        for mk in a.models:
            if inv.tab_status(mk).state != "ready":
                print(f"WARNING: {mk}: not all its files are there", flush=True)
    app = lsr.live_sketch.make_app("http://127.0.0.1:1" if a.dry else (a.url or cfgmod.load()["comfyui"]["url"]))
    blank = Image.new("RGB", CANVAS, "white")
    failed, t_start = 0, time.time()
    left = Left(len(js))
    for i, (mk, n, style, subject, text) in enumerate(js, 1):
        fid = f"{mk}-{n}"
        if fid in key:
            continue
        req = lsr.window_request(app, "C", mk, text)
        t0 = time.time()
        try:
            im, res = run_one(comfy, req, blank, out / "xch")
        except Exception as e:            # one failing run must not stop the round
            failed += 1
            print(f"{i}/{len(js)} {fid} {style}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        if a.dry:
            ok = lsr._prompt_in(comfy.graphs[-1], text)
            failed += not ok
            print(f"{i}/{len(js)} {fid}: {Path(req.workflow or '').name}, text in graph: {'yes' if ok else 'NO'}", flush=True)
            continue
        im.save(out / "bilder" / f"{fid}.png")
        key[fid] = {"model": models.BY_KEY[mk].label, "model_key": mk, "style": style, "subject": subject, "text": text,
                    "seed": SEED, "secs": round(time.time() - t0, 1)}
        json.dump({"items": key, "canvas": CANVAS}, open(kf, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"{i}/{len(js)} {fid} {style}: {key[fid]['secs']} s" + left(i), flush=True)
        if a.free:
            lsr.free_memory(comfy)
    app.root.destroy()
    if a.dry:
        shutil.rmtree(out, ignore_errors=True)
    print(f"\n{'DRY RUN' if a.dry else 'DONE'} in {(time.time() - t_start) / 60:.1f} min, {failed} failed"
          + ("" if a.dry else f", in {out}"), flush=True)
    return failed


VIEW = """<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Text to image mit Stilen</title><style>
body{margin:0;background:#1b1b1d;color:#e6e6e6;font:15px/1.4 "Segoe UI",sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:16px}
h2{font-size:18px;margin:26px 0 8px}
.row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
figure{margin:0}
figure img{width:100%;display:block;cursor:zoom-in;border-radius:4px}
figcaption{font-size:13px;color:#aaa;margin-top:4px}
figcaption b{color:#e6e6e6}
#full{position:fixed;inset:0;background:#000;overflow:auto;display:none;cursor:zoom-out}
#full img{display:block;margin:auto}
.pick{font:inherit;font-size:13px;margin-top:6px;border:1px solid #555;background:transparent;color:#e6e6e6;border-radius:6px;padding:3px 10px;cursor:pointer}
figure.on img{outline:4px solid #378ef0;outline-offset:-4px}
figure.on .pick{background:#378ef0;border-color:#378ef0;color:#fff}
.bar{position:sticky;top:0;background:#1b1b1d;padding:8px 0;border-bottom:1px solid #444;display:flex;gap:10px;align-items:center;z-index:2}
.bar button{font:inherit;border:1px solid #555;background:#2a2a2d;color:#e6e6e6;border-radius:6px;padding:4px 12px;cursor:pointer}
</style></head><body><div class="wrap"><h1>Text to image mit eingebauten Stilen</h1>
<p>Seed 1234, Startwerte, Leinwand __CANVAS__. Klick aufs Bild: 100 %, nochmal Klick oder Esc: zurück.
„Wählen“ merkt sich der Browser; „Auswahl speichern“ legt <code>t2i-auswahl.json</code> in den Download-Ordner.</p>
<div class="bar"><span id="count">0 gewählt</span><button id="save">Auswahl speichern</button><button id="copy">Auswahl kopieren</button></div>
__BODY__</div>
<div id="full"><img></div><script>
const f=document.getElementById("full"),fi=f.querySelector("img");
document.querySelectorAll("figure img").forEach(i=>i.onclick=()=>{fi.src=i.src;f.style.display="block"});
f.onclick=()=>f.style.display="none";document.onkeydown=e=>{if(e.key==="Escape")f.style.display="none"};
const KEY="t2i-auswahl:__RUN__";let picked=[];try{picked=JSON.parse(localStorage.getItem(KEY)||"[]")}catch(e){}
const figs=[...document.querySelectorAll("figure[data-id]")];
const show=()=>{figs.forEach(g=>{const on=picked.includes(g.dataset.id);g.classList.toggle("on",on);g.querySelector(".pick").textContent=on?"✓ Gewählt":"Wählen"});
 document.getElementById("count").textContent=picked.length+" gewählt";try{localStorage.setItem(KEY,JSON.stringify(picked))}catch(e){}};
figs.forEach(g=>g.querySelector(".pick").onclick=()=>{const id=g.dataset.id;picked=picked.includes(id)?picked.filter(x=>x!==id):[...picked,id];show()});
const out=()=>JSON.stringify({run:"__RUN__",picked},null,1);
document.getElementById("save").onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([out()],{type:"application/json"}));a.download="t2i-auswahl.json";a.click()};
document.getElementById("copy").onclick=()=>navigator.clipboard.writeText(out());
show();
</script></body></html>"""


def cmd_view(a):
    import html
    folder = Path(a.folder) if a.folder else max(p for p in BASE.iterdir() if (p / "key.json").exists())
    data = json.load(open(folder / "key.json", encoding="utf-8"))
    body = []
    for mk in PLAN:
        items = [(fid, it) for fid, it in data["items"].items() if it["model_key"] == mk]
        if not items:
            continue
        body.append(f"<h2>{html.escape(items[0][1]['model'])}</h2><div class=\"row\">")
        for fid, it in sorted(items):
            body.append(f'<figure data-id="{fid}"><img src="bilder/{fid}.png" loading="lazy"><figcaption><b>{html.escape(it["style"])}</b>'
                        f' · {it["secs"]} s<br>{html.escape(it["subject"])}</figcaption><button class="pick">Wählen</button></figure>')
        body.append("</div>")
    out = folder.resolve() / "ansicht.html"
    out.write_text(VIEW.replace("__CANVAS__", "x".join(map(str, data.get("canvas", CANVAS)))).replace("__BODY__", "".join(body)).replace("__RUN__", folder.resolve().name),
                   encoding="utf-8")
    print("file:///" + str(out).replace("\\", "/"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("view")
    v.add_argument("folder", nargs="?")
    for name in ("plan", "run"):
        r = sub.add_parser(name)
        r.add_argument("--models", nargs="+", default=list(PLAN), choices=list(PLAN))
        r.add_argument("--anime", action="store_true", help="Anime, golden sky (text of styles.json), two subjects")
        r.add_argument("--redo", action="store_true", help="only the README pictures whose style text changed (18.11.)")
        if name == "run":
            r.add_argument("--into")
            r.add_argument("--dry", action="store_true", help="the whole bridge against a fake ComfyUI, no GPU")
            r.add_argument("--free", action="store_true", help="ask ComfyUI to free memory after every run")
            r.add_argument("--url")
    a = ap.parse_args()
    if a.cmd == "view":
        return cmd_view(a)
    sys.exit(cmd_plan(a) if a.cmd == "plan" else (1 if cmd_run(a) else 0))


if __name__ == "__main__":
    main()
