r"""Manual check (not part of run_all.py): MOSS Image SFT (our file) against Kromoss (lodestones' fine-tune of MOSS Base), in
Text to image through the plugin's own graph builder (user 20.11. evening: "mach einen moss kromoss vergleich").

Per prompt four pictures, same seed and size (1280 x 1280, the plugin's MOSS size), UltraReal LoRA on as in the window,
no LLM prompt writer:
    A  SFT      the window's start values: DMD2 off, 25 steps, CFG 3
    B  Kromoss  the same values (what the variant runs with DMD2 off, pccomfy/variants.py)
    C  SFT      + DMD2 Turbo LoRA, the plugin's speed values
    D  Kromoss  + DMD2 Turbo LoRA, the variant's values (8 steps, CFG 1, euler/simple; Kromoss card)
The runs go model by model (A, C, then B, D), so each file loads once.

    python tests\live_kromoss_compare.py --dry     builds the graphs, checks ComfyUI's file list; runs nothing
    python tests\live_kromoss_compare.py           the real run (GPU, about 15 minutes; remind the user first)

Output: data/compare-variants/kromoss-<time>/<prompt>_<A|B|C|D>.png, index.html (a click opens 100 %, keys 1-4 switch
A-D at the same spot, arrows previous / next prompt, Escape back), report.md with the times.
"""
import argparse
import html
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pccomfy import bridge, workflows  # noqa: E402
from pccomfy.comfy import ComfyError, ComfyUI  # noqa: E402

SFT = "moss_image_sft_int8_convrot.safetensors"
KRO = "kromoss_int8_convrot.safetensors"
SEED = 1234
SIZE = (1280, 1280)
PROMPTS = (
    ("fox", "A red fox standing in a snowy birch forest at golden hour, breath visible in the cold air, photograph, sharp detail"),
    ("portrait", "Close-up portrait of an elderly fisherman with a weathered face and a knitted cap, soft window light, photograph"),
    ("kitchen", "A sunlit Scandinavian kitchen with oak cabinets, a bowl of lemons on the counter and plants by the window, interior photograph"),
    ("hands", "Two hands of a young woman shaping a clay bowl on a potter's wheel, wet clay, studio light, close-up photograph"),
    ("street", "A rainy street in Tokyo at night, neon signs reflected in puddles, people with umbrellas, 35mm photograph"),
    ("product", "A glass perfume bottle on a white marble table, soft shadows, a sprig of lavender beside it, product photograph"),
)
CONFIGS = (  # tag, file, turbo (DMD2 on), label
    ("A", SFT, False, "SFT · DMD2 off · 25 steps, CFG 3"),
    ("C", SFT, True, "SFT · DMD2 on · plugin speed values"),
    ("B", KRO, False, "Kromoss · DMD2 off · 25 steps, CFG 3"),
    ("D", KRO, True, "Kromoss · DMD2 on · 8 steps, CFG 1, euler/simple"),
)
TAGS = ("A", "B", "C", "D")


def build(unet: str, turbo: bool, prompt: str, loras) -> tuple[dict, str]:
    wf = str(ROOT / "workflows" / "moss-image-t2i.json")
    p = workflows.GenParams(prompt=prompt, seed=SEED, width=SIZE[0], height=SIZE[1])
    req = bridge.Request(mode="txt2img", workflow=wf, params=p, enhance=False, turbo=turbo, stage_on=True, stages_off=["7"],
                         variant="" if unet == SFT else unet)
    graph, out = bridge.Bridge._graph(object(), req, p, None, None, wf)
    for node in graph.values():          # what inventory.apply_names does when the variant is the file in use
        if isinstance(node, dict) and node.get("class_type") == "UNETLoader":
            node["inputs"]["unet_name"] = unet
    if loras is not None:
        graph, missing = workflows.fix_lora_names(graph, loras)
        assert not missing, missing
    return graph, out


def values(graph: dict) -> str:
    ks = graph[workflows.main_sampler(graph)]["inputs"]
    return f"{ks['steps']} steps, CFG {ks['cfg']:g}, {ks['sampler_name']}/{ks['scheduler']}"


def page(rows, labels) -> str:
    data = json.dumps([{"key": k, "prompt": pr} for k, pr in rows])
    leg = " · ".join(f"<b>{t}</b> {html.escape(labels[t])}" for t in TAGS)
    return f"""<!doctype html><meta charset=utf-8><title>MOSS vs Kromoss</title>
<style>body{{font:14px sans-serif;background:#1e1e1e;color:#eee;margin:16px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}
.grid img{{width:100%;cursor:zoom-in}}h2{{margin:26px 0 4px}}#big{{position:fixed;inset:0;background:#000;display:none;overflow:auto}}
#big img{{display:block}}#tag{{position:fixed;top:8px;left:8px;background:#378ef0;color:#fff;padding:4px 10px;font:bold 16px sans-serif}}</style>
<h1>MOSS SFT gegen Kromoss · Text to image · seed {SEED} · {SIZE[0]}×{SIZE[1]}</h1><p>{leg}</p>
<p>Klick auf ein Bild: 100 %. Dort 1 / 2 / 3 / 4 = A / B / C / D an derselben Stelle, ← → voriger / nächster Prompt, Esc zurück.</p>
<div id=rows></div><div id=big><div id=tag></div><img id=bi></div>
<script>
const R={data},T={json.dumps(list(TAGS))};let cur=null,ti=0;
const rows=document.getElementById('rows');
R.forEach((r,i)=>{{const h=document.createElement('h2');h.textContent=r.key;rows.appendChild(h);
const p=document.createElement('p');p.textContent=r.prompt;rows.appendChild(p);const g=document.createElement('div');g.className='grid';
T.forEach((t,j)=>{{const d=document.createElement('div');d.innerHTML='<b>'+t+'</b><br>';const im=new Image();im.src=r.key+'_'+t+'.png';
im.onclick=()=>show(i,j);d.appendChild(im);g.appendChild(d)}});rows.appendChild(g)}});
const big=document.getElementById('big'),bi=document.getElementById('bi'),tag=document.getElementById('tag');
function show(i,j){{cur=i;ti=j;bi.src=R[i].key+'_'+T[j]+'.png';tag.textContent=R[i].key+' · '+T[j];big.style.display='block'}}
document.addEventListener('keydown',e=>{{if(cur===null)return;if(e.key==='Escape'){{big.style.display='none';cur=null;return}}
const n='1234'.indexOf(e.key);if(n>=0){{const x=big.scrollLeft,y=big.scrollTop;show(cur,n);big.scrollLeft=x;big.scrollTop=y}}
if(e.key==='ArrowRight'&&cur<R.length-1)show(cur+1,ti);if(e.key==='ArrowLeft'&&cur>0)show(cur-1,ti)}});
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="build the graphs only, run nothing")
    args = ap.parse_args()
    comfy = ComfyUI()
    known = set(comfy._choices("UNETLoader", "unet_name"))
    loras = comfy._choices("LoraLoaderModelOnly", "lora_name")
    for f in (SFT, KRO):
        if f not in known:
            raise SystemExit(f"{f} is not in ComfyUI's list")
    labels = {}
    for tag, unet, turbo, label in CONFIGS:
        g, _ = build(unet, turbo, PROMPTS[0][1], loras)
        labels[tag] = f"{label} ({values(g)})"
        print(f"{tag}: {labels[tag]}")
    print(f"{len(PROMPTS)} prompts x {len(CONFIGS)} = {len(PROMPTS) * len(CONFIGS)} runs")
    if args.dry:
        return
    out_dir = ROOT / "data" / "compare-variants" / ("kromoss-" + time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page(PROMPTS, labels), encoding="utf-8")
    times = {}
    for tag, unet, turbo, _label in CONFIGS:
        for key, prompt in PROMPTS:
            graph, out = build(unet, turbo, prompt, loras)
            t0 = time.monotonic()
            try:
                hist = comfy.wait(comfy.queue(graph))
            except ComfyError as e:
                print(f"{key} {tag}: failed: {str(e).splitlines()[-1][:300]}")
                continue
            times[(key, tag)] = time.monotonic() - t0
            comfy.output_images(hist, out)[0].save(out_dir / f"{key}_{tag}.png")
            print(f"{key} {tag}: {times[(key, tag)]:.0f} s", flush=True)
    rep = ["# MOSS SFT gegen Kromoss (Text to image)", "", f"Seed {SEED}, {SIZE[0]}x{SIZE[1]}, UltraReal an, kein Prompt-Schreiber.", "",
           *[f"- **{t}**: {labels[t]}" for t in TAGS], "", "| Prompt | A | B | C | D |", "|---|---|---|---|---|",
           *[f"| {k} | " + " | ".join(f"{times[(k, t)]:.0f} s" if (k, t) in times else "–" for t in TAGS) + " |" for k, _p in PROMPTS],
           "", "Zeiten mit Laden (der erste Lauf je Datei lädt das Modell)."]
    (out_dir / "report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print(f"\nResults: {out_dir.as_uri()}/index.html")


if __name__ == "__main__":
    main()
