"""Manual check (not part of run_all.py): how long do the prompt writers write, and do they hit their limit?
(docs/plan/promptschreiber.md, V1; user 13.11.)

Every writer runs as the plugin runs it: the model's own workflow, the idea filled in by `apply_template`, then only the
text model and what feeds it (no picture is made). Per writer 3 short and 3 detailed ideas (edit writers get edit
instructions on one picture). Measured: words, characters, tokens (exact with --tokenizer, else words x 1.3), seconds,
"at the limit" (tokens near `max_length` or the text ends mid-sentence), and for the JSON writers whether the JSON is what
the next node reads: Fibo as ComfyUI's fibo2 encoder reads it (whole text a JSON object; Edit also `edit_instruction`),
MiniMax as `JsonExtractString` reads it (`expanded_caption` found).

    python tests\\live_writer_lengths.py write [--dry]   texts on the running ComfyUI (GPU, a few minutes)
    python tests\\live_writer_lengths.py report [--tokenizer <folder with vocab.json and merges.txt>]
    --cases flux3,flux2,qwen,moss,fibo,fibo_edit,minimax,minimax_edit picks writers; --image <file in ComfyUI's input>.

Exact tokens: run `report` with ComfyUI's own Python (it has `tokenizers`) and --tokenizer
<ComfyUI>\\comfy\\text_encoders\\qwen35_tokenizer (exact for the Qwen 3.5 writers, close for Qwen3-VL). MiniMax: the thinking counts
towards max_length but is not in the measured text.
Output: data\\writer-lengths\\texts.json and report.md. Nothing in the plugin changes.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pccomfy import workflows  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402
from live_llm_tempo import comfy_info  # noqa: E402

WF = ROOT / "workflows"
OUT = ROOT / "data" / "writer-lengths"
SEED = 7
# name: (label, workflow, edit?, words asked for by the system prompt)
CASES = {
    "flux3": ("Flux 3 T2I", "flux3-klein-t2i.json", False, "60–150"),
    "flux2": ("Flux 2 T2I", "flux2-klein-t2i.json", False, "60–150"),
    "qwen": ("Qwen 2.1 T2I", "qwen-image-21-t2i.json", False, "400–500"),
    "moss": ("MOSS T2I", "moss-image-t2i.json", False, "220–500"),
    "fibo": ("Fibo T2I (VGL)", "fibo2-t2i.json", False, "JSON"),
    "fibo_edit": ("Fibo Edit (VGL)", "fibo2-edit.json", True, "JSON"),
    "minimax": ("MiniMax T2I", "minimax-h3-image-t2i.json", False, "offiziell"),
    "minimax_edit": ("MiniMax Edit", "minimax-h3-image-edit.json", True, "offiziell"),
}
SHORT_T2I = ["a red fox in the snow", "rainy neon street at night", "a cup of coffee on a wooden table"]
SHORT_EDIT = ["make it night", "add snow", "turn it into a watercolor painting"]
LONG_EDIT = [
    "Change the season to late autumn: the trees get orange and red leaves, some leaves lie on the ground, the light becomes "
    "a low warm afternoon sun from the left, and the people keep their faces, poses and clothes exactly as they are",
    "Replace the background with a busy Paris street cafe in the evening, string lights above the tables, a waiter in the "
    "distance, shallow depth of field so the background is soft, keep the people sharp and unchanged",
    "Restyle the whole picture as a 1970s film photo: faded warm colors, visible film grain, slight vignette, a light leak "
    "in the top right corner, but keep the composition and every person exactly in place",
]
DEFAULT_IMAGE = "couple.jpg"


def long_t2i() -> list[str]:
    """The first idea of three Extreme groups of docs/tests/testprompts.md (detailed, many parts)."""
    lines = (ROOT / "docs" / "tests" / "testprompts.md").read_text(encoding="utf-8").splitlines()
    out, extreme, got = [], False, False
    for ln in lines:
        if ln.startswith("###"):
            extreme, got = ln.rstrip().endswith("Extreme"), False
        elif extreme and not got and re.match(r"\d+\. ", ln):
            out.append(re.sub(r"^\d+\. ", "", ln).strip())
            got = True
    return [out[0], out[len(out) // 2], out[-1]]


def ideas(edit: bool) -> list[tuple[str, str]]:
    short, long_ = (SHORT_EDIT, LONG_EDIT) if edit else (SHORT_T2I, long_t2i())
    return [("kurz", x) for x in short] + [("lang", x) for x in long_]


def writer_node(g: dict) -> str:
    """The TextGenerate node that writes (MiniMax: behind the StringReplace that is its pc:prompt)."""
    ids = [k for k, n in g.items() if n.get("class_type", "").startswith("TextGenerate")]
    if len(ids) != 1:
        raise SystemExit(f"expected one TextGenerate node, found {ids}")
    return ids[0]


def text_graph(wf: str, idea: str, image: str | None) -> tuple[dict, str, int]:
    """The workflow filled as the plugin fills it, cut down to the writer; returns (graph, output node, max_length)."""
    tpl = workflows.load_template(WF / wf)
    g, _ = workflows.apply_template(tpl, workflows.GenParams(prompt=idea, seed=SEED), image, None)
    w = writer_node(g)
    keep = workflows._upstream(g, w) | {w}
    g = {k: v for k, v in g.items() if k in keep}
    if "sampling_mode.seed" in g[w]["inputs"]:
        g[w]["inputs"]["sampling_mode.seed"] = SEED
    g["900"] = {"class_type": "PreviewAny", "inputs": {"source": [w, 0]}, "_meta": {"title": "out"}}
    return g, "900", int(g[w]["inputs"]["max_length"])


def json_check(case: str, text: str) -> str:
    """What the next node makes of the text (ComfyUI 0.45.0: comfy/text_encoders/fibo2.py, nodes_string.JsonExtractString)."""
    if case.startswith("fibo"):
        try:
            d = json.loads(text)
        except ValueError:
            return "kaputt (geht als Text)"
        if not isinstance(d, dict):
            return "kaputt (kein Objekt)"
        if case == "fibo_edit" and not d.get("edit_instruction"):
            return "ok, aber ohne edit_instruction"
        return "ok"
    if case.startswith("minimax"):
        dec = json.JSONDecoder()
        for m in re.finditer(r"\{", text):
            try:
                d, _ = dec.raw_decode(text, m.start())
            except ValueError:
                continue
            return "ok" if isinstance(d, dict) and d.get("expanded_caption") else "ohne expanded_caption"
        return "kaputt (kein JSON)"
    return ""


def ends_clean(text: str) -> bool:
    t = text.rstrip().rstrip("`").rstrip()
    return bool(t) and t[-1] in '.!?"\'”)}]。！？'


def picked(a) -> list[str]:
    cases = [x.strip() for x in a.cases.split(",") if x.strip()]
    bad = [x for x in cases if x not in CASES]
    if bad:
        raise SystemExit(f"unknown case {bad}; known: {', '.join(CASES)}")
    return cases


def cmd_write(a):
    c = ComfyUI()
    cases = picked(a)
    built = {}
    for case in cases:
        _, wf, edit, _ = CASES[case]
        built[case] = [(kind, idea, *text_graph(wf, idea, a.image if edit else None)) for kind, idea in ideas(edit)]
    clips = sorted({n["inputs"]["clip_name"] for v in built.values() for _, _, g, _, _ in v for n in g.values()
                    if n.get("class_type") == "CLIPLoader"})
    miss = [f for f in clips if f not in c._choices("CLIPLoader", "clip_name")]
    if any(CASES[x][2] for x in cases) and a.image not in c._choices("LoadImage", "image"):
        miss.append(f"{a.image} (input picture)")
    if miss:
        raise SystemExit("ComfyUI does not list: " + ", ".join(miss))
    if a.dry:
        for case, v in built.items():
            print(f"ok: {case:13s} {len(v)} graphs, {len(v[0][2])} nodes, max_length {v[0][4]}")
        print("text models:", ", ".join(clips))
        return
    info = comfy_info(c)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "texts.json"
    res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    res.update({"when": time.strftime("%Y-%m-%d %H:%M"), "comfy": info, "seed": SEED, "image": a.image})
    res.setdefault("texts", {})
    print(f"ComfyUI {info['version']}, {info['gpu']}, start options {' '.join(info['argv'][1:])}")
    for case in cases:
        for i, (kind, idea, g, node, max_len) in enumerate(built[case]):
            t0 = time.time()
            hist = c.wait(c.queue(g))
            text = "\n".join(str(x) for x in ((hist.get("outputs", {}).get(node) or {}).get("text") or [""]))
            sec = time.time() - t0
            row = {"case": case, "kind": kind, "idea": idea, "sec": round(sec, 1), "max_length": max_len,
                   "words": len(text.split()), "chars": len(text), "ends_clean": ends_clean(text),
                   "json": json_check(case, text), "text": text}
            res["texts"][f"{case}_{i + 1}"] = row
            print(f"  {case:13s} {kind:4s} {i + 1}  {sec:6.1f} s  {row['words']:4d} words"
                  f"{'' if row['ends_clean'] else '  ENDS MID-SENTENCE'}{'  JSON ' + row['json'] if row['json'] else ''}"
                  f"{'  (with model load)' if i == 0 else ''}", flush=True)
            f.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {f}")


def counter(folder: str | None):
    if not folder:
        return None, "geschätzt (Wörter x 1,3)"
    from tokenizers import Tokenizer, models, pre_tokenizers, decoders  # ComfyUI's own Python has it
    p = Path(folder)
    tok = Tokenizer(models.BPE.from_file(str(p / "vocab.json"), str(p / "merges.txt")))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=True)
    tok.decoder = decoders.ByteLevel()
    return (lambda s: len(tok.encode(s).ids)), f"gezählt ({p.name})"


def cmd_report(a):
    f = OUT / "texts.json"
    if not f.exists():
        raise SystemExit(f"no texts yet: {f} (write)")
    res = json.loads(f.read_text(encoding="utf-8"))
    count, how = counter(a.tokenizer)
    lines = [f"# Länge der Prompt-Schreiber, ComfyUI {res['comfy']['version']}, {res['comfy']['gpu']}", "",
             f"{res['when']}, Seed {res['seed']}, Edit-Bild {res['image']}; Token {how}; "
             "„am Limit“ = Token ab 95 % von max_length oder Text endet mitten im Satz.", "",
             "| Schreiber | Vorgabe | max_length | kurz: Wörter | lang: Wörter | Token max | Zeit s | am Limit | JSON |",
             "|---|---|---|---|---|---|---|---|---|"]
    by = {}
    for row in res["texts"].values():
        by.setdefault(row["case"], []).append(row)
    for case, rows in by.items():
        for r in rows:
            r["tokens"] = count(r["text"]) if count else round(r["words"] * 1.3)
        w = {k: [r["words"] for r in rows if r["kind"] == k] for k in ("kurz", "lang")}
        limit = sum(r["tokens"] >= 0.95 * r["max_length"] or not r["ends_clean"] for r in rows)
        js = [r["json"] for r in rows if r["json"]]
        jcell = (f"{js.count('ok')} von {len(js)} ok" + ("; " + "; ".join(sorted({x for x in js if x != 'ok'})) if js.count('ok') < len(js) else "")) if js else "–"
        span = lambda v: f"{min(v)}–{max(v)}" if v else "–"  # noqa: E731
        lines.append(f"| {CASES[case][0]} | {CASES[case][3]} | {rows[0]['max_length']} | {span(w['kurz'])} | {span(w['lang'])} | "
                     f"{max(r['tokens'] for r in rows)} | {span([round(r['sec']) for r in rows])} | {limit} von {len(rows)} | {jcell} |")
    lines += ["", "Zeit: die erste Zeile je Schreiber enthält das Laden des Textmodells."]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"written: {OUT / 'report.md'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("write", "report"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--tokenizer")
    a = ap.parse_args()
    {"write": cmd_write, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
