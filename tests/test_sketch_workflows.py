# tags: sketch, workflows
"""The Sketch workflows (docs/archiv/sketch-plan.md, "Bauplan nach Runde 2", step 1 of the build, 9.11.): each is the model's
Edit workflow plus BFL's prompt upsampler, as the test rounds 2 to 7 ran it (tests/live_sketch.py, upsample_any), without
reference slots. The Edit workflows themselves stay as they are (the user calls Flux 3 and Qwen Edit "perfect").
Since 10.11. (writer round on PC A, option B) Flux 2 writes with qwen3vl 4B and an instruction prompt instead."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from pccomfy import bridge, models, workflows  # noqa: E402
try:
    import live_sketch as ls  # noqa: E402
except ImportError:          # tests/live_sketch.py stays in the private repo (it names the user's picture folders)
    if __name__ == "__main__":
        print("skipped: tests/live_sketch.py is only in the private working repo")
        sys.exit(0)
    raise

WF = ROOT / "workflows"
PAIRS = {"flux3-klein-sketch.json": "flux3-klein-edit.json", "flux2-klein-sketch.json": "flux2-klein-edit.json",
         "qwen-image-21-sketch.json": "qwen-image-21-edit.json"}
OWN = {"401", "402", "403", "404", "405"}       # the writer's nodes
VL4 = "qwen3vl_4b_int8_convrot.safetensors"
W4 = "qwen3.5_9b_w4a8_gptq.safetensors"


def _writer(name):
    """(file, loader type, system prompt) of the writer in this Sketch workflow."""
    if name.startswith("flux2"):
        return VL4, "stable_diffusion", models.SKETCH_WRITER_SYSTEM
    if name.startswith("qwen"):           # its own w4a8 with prompt V1 since 16.11. evening (writer round 3)
        return W4, "flux3", models.QWEN_SKETCH_WRITER_SYSTEM
    return ls.UPSAMPLER_FILE, "flux3", ls.EDIT_UPSAMPLER_SYSTEM


def _prompt_nodes(g):
    return [k for k, n in g.items() if "pc:prompt" in n.get("_meta", {}).get("title", "").lower()]


def test_the_upsampler_writes_the_prompt_and_sees_the_picture():
    for name in PAIRS:
        g = workflows.load_template(WF / name)
        assert _prompt_nodes(g) == ["403"], name
        gen = g["403"]
        assert gen["class_type"] == "TextGenerate"
        img = next(k for k, n in g.items() if "pc:image" in n.get("_meta", {}).get("title", "").lower())
        assert gen["inputs"]["image"] == [img, 0], name
        f, typ, system = _writer(name)
        loader = g[gen["inputs"]["clip"][0]]["inputs"]
        assert loader["clip_name"] == f and loader["type"] == typ, (name, loader)
        assert g[gen["inputs"]["system_prompt"][0]]["inputs"]["value"] == system, name
        assert "vgl" in g["404"]["_meta"]["title"]
        assert workflows.ref_slot_count(g) == 1, name       # one slot for Reference at scribble (15.11.)


def test_everything_else_is_the_edit_workflow():
    """Apart from the upsampler and the text input of the encoder, the graph is the Edit workflow with its reference slots
    from 2 on dropped: same model files, sampler, steps and size handling, and slot 1 wired as in Edit (Reference at
    scribble, 15.11.)."""
    for name, edit in PAIRS.items():
        g = workflows.load_template(WF / name)
        e = workflows.load_template(WF / edit)
        workflows.drop_ref_slot(e, 2)
        assert set(g) - OWN == set(e), name
        for k in e:
            a, b = json.loads(json.dumps(g[k])), json.loads(json.dumps(e[k]))
            if k in _prompt_nodes(e):       # the encoder: its text now comes from the upsampler
                for n in (a, b):
                    n["_meta"] = {}
                    n["inputs"].pop("text", None)
                    n["inputs"].pop("prompt", None)
            assert a == b, (name, k)


def test_llm_off_sends_the_typed_text():
    """The LLM switch off (bypass_prompt_writer): no text model runs and the encoder gets the typed text; Qwen keeps
    "<image1>" in front, as its Edit workflow does."""
    text = "Replace the coloured scribbles with a rabbit."
    for name in PAIRS:
        g = workflows.bypass_prompt_writer(workflows.load_template(WF / name), text)
        assert not any(n["class_type"] == "TextGenerate" for n in g.values()), name
        # the upsampler's loader may stay (as in Text to image), but nothing uses it: ComfyUI runs only what an output needs
        loaders = {k for k, n in g.items() if n["inputs"].get("clip_name") == _writer(name)[0] and k in OWN}
        assert not any(isinstance(v, list) and v and v[0] in loaders for n in g.values() for v in n["inputs"].values()), name
        graph, _out = workflows.apply_template(g, workflows.GenParams(prompt=text), "pic.png", None)
        if name.startswith("qwen"):
            cat = graph["405"]["inputs"]
            assert cat["string_a"] == "<image1>" and cat["string_b"] == text
            assert graph["8"]["inputs"]["prompt"] == ["405", 0]
        else:
            enc = next(n for n in graph.values() if n["class_type"] == "CLIPTextEncode")
            assert enc["inputs"]["text"] == text, name


def test_llm_on_gives_the_request_to_the_upsampler():
    text = "Replace the coloured scribbles with a rabbit."
    for name in PAIRS:
        graph, out = workflows.apply_template(workflows.load_template(WF / name), workflows.GenParams(prompt=text),
                                              "pic.png", None)
        assert graph["403"]["inputs"]["prompt"] == text, name      # no "<image1>" for the upsampler itself
        assert out is not None



def _run_strings(graph, nid):
    """What a chain of StringConcatenate / RegexReplace nodes outputs, with the writer's text given (as ComfyUI runs them)."""
    import re
    n = graph[nid]
    if "text" in n:
        return n["text"]
    inp = {k: (_run_strings(graph, v[0]) if isinstance(v, list) else v) for k, v in n["inputs"].items()}
    if n["class_type"] == "StringConcatenate":
        return inp["delimiter"].join((inp["string_a"], inp["string_b"]))
    assert n["class_type"] == "RegexReplace"
    flags = (re.I if inp["case_insensitive"] else 0) | (re.M if inp["multiline"] else 0) | (re.S if inp["dotall"] else 0)
    return re.sub(inp["regex_pattern"], inp["replace"], inp["string"], count=inp["count"], flags=flags)


def test_qwen_writer_settings_and_empty_fallback():
    """Qwen's Sketch writer (user 16.11. evening): w4a8, prompt V1, temperature 0.3; Scribble on photo without thinking,
    Sketch to image with thinking and max_length 8192; nothing written = the typed request goes to the image model."""
    text = "Replace the coloured scribbles with a rabbit."
    g = workflows.load_template(WF / "qwen-image-21-sketch.json")
    gen = g["403"]["inputs"]
    assert gen["sampling_mode.temperature"] == 0.3 and gen["thinking"] is False and gen["max_length"] == 4096
    graph, _out = workflows.apply_template(g, workflows.GenParams(prompt=text), "pic.png", None)
    workflows.add_empty_fallback(graph)
    end = workflows.writer_end(graph, "403")
    assert end != "403" and graph["405"]["inputs"]["string_b"] == [end, 0] and graph["404"]["inputs"]["source"] == [end, 0]
    for written, sent in (("", text), ("  \n ", text), ("A rabbit sits there.", "A rabbit sits there."),
                          ("Line one.\nLine two.", "Line one.\nLine two.")):
        graph["403"]["text"] = written
        assert _run_strings(graph, end) == sent, (written, _run_strings(graph, end))
    del graph["403"]["text"]
    assert {graph[k]["class_type"] for k in workflows.writer_chain(graph)} >= {"TextGenerate", "StringConcatenate", "RegexReplace"}
    assert end in bridge.prompt_phase_nodes(graph)
    workflows.set_sketch_inputs(graph)
    assert graph["403"]["inputs"]["thinking"] is True and graph["403"]["inputs"]["max_length"] == 8192
    # the other Sketch workflows have neither
    for name in ("flux3-klein-sketch.json", "flux2-klein-sketch.json"):
        g2, _ = workflows.apply_template(workflows.load_template(WF / name), workflows.GenParams(prompt=text), "pic.png", None)
        before = json.dumps(g2, sort_keys=True)
        workflows.set_sketch_inputs(workflows.add_empty_fallback(g2))
        assert json.dumps(g2, sort_keys=True) == before, name
    # the LLM switch off: no fallback nodes, the typed text as before
    off = workflows.bypass_prompt_writer(workflows.load_template(WF / "qwen-image-21-sketch.json"), text)
    graph, _ = workflows.apply_template(off, workflows.GenParams(prompt=text), "pic.png", None)
    assert workflows.add_empty_fallback(graph) and not any(n["class_type"] == "RegexReplace" for n in graph.values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
