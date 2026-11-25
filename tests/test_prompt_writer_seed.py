# tags: prompt, workflows
"""Prompt writer seed (user 17.11., choice A): a seed of its own for the text model that writes the prompt inside a run, so a new
image seed keeps the written prompt. Only the writer of the run (and its reference description in Scribble with reference);
Describe canvas and the slot descriptions are left alone. Start value 0 (as the workflows' own), -1 = a new one each run
(bridge). Since 18.11. the window has no seed row: the seed is hidden and "Reroll prompt" draws a new one
(tests/test_prompt_reroll.py). Workflows and bridge here.

    python tests/test_prompt_writer_seed.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp(prefix="pccomfy-wseed-"))
os.environ["PCCOMFY_NO_TIPS"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as tr  # noqa: E402
from pccomfy import bridge, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402

ROOT = tr.ROOT
WF = ROOT / "workflows"


def seeds(graph):
    return [n["inputs"].get("sampling_mode.seed") for n in graph.values()
            if isinstance(n, dict) and n.get("class_type") in workflows.WRITER_CLASSES and n["inputs"].get("sampling_mode") == "on"]


def check_workflows():
    for name in ("qwen-image-21-sketch.json", "flux3-klein-sketch.json", "flux3-klein-t2i.json", "moss-image-t2i.json",
                 "minimax-h3-image-t2i.json", "minimax-h3-image-edit.json"):
        g = workflows.load_template(WF / name)
        assert workflows.writer_samples(g), name
        workflows.set_writer_seed(g, 4321)
        assert seeds(g) and set(seeds(g)) == {4321}, (name, seeds(g))
    for name in ("fibo2-t2i.json", "fibo2-edit.json", "flux3-klein-edit.json"):
        g = workflows.load_template(WF / name)
        before = repr(g)
        assert not workflows.writer_samples(g), name                     # Fibo takes the likeliest words, Flux 3 Edit has none
        workflows.set_writer_seed(g, 4321)
        assert repr(g) == before, name
    # Scribble with reference: the reference description writes with the same seed as the writer
    g, _ = workflows.apply_template(workflows.load_template(WF / "qwen-image-21-sketch.json"),
                                    workflows.GenParams(prompt="a cat"), "img.png", None, "ref.png")
    ref = next(nid for nid, n in g.items() if n.get("class_type") == "LoadImage")
    workflows.describe_reference(g, ref, "cat")
    workflows.set_writer_seed(g, 77)
    assert len(seeds(g)) == 2 and set(seeds(g)) == {77}, seeds(g)


def check_bridge():
    b = object.__new__(bridge.Bridge)
    wf = str(WF / "qwen-image-21-sketch.json")
    for asked, want in ((0, {0}), (555, {555})):
        p = workflows.GenParams(prompt="a house", seed=1, writer_seed=asked)
        g, _ = b._graph(Request(mode="edit", params=p, workflow=wf, enhance=True), p, "img.png", None, wf)
        assert set(seeds(g)) == want, (asked, seeds(g))
    # -1: a new number at the start of the run, written into the params (and so into runs.jsonl)
    p = workflows.GenParams(prompt="a house", seed=-1, writer_seed=-1)
    _req, gp, _tag = b.begin(Request(mode="edit", params=p, workflow=wf, enhance=True))
    assert 0 <= gp.writer_seed < 10**8 and 0 <= gp.seed < 10**8, (gp.seed, gp.writer_seed)
    p = workflows.GenParams(prompt="a house", seed=-1, writer_seed=42)
    _req, gp, _tag = b.begin(Request(mode="edit", params=p, workflow=wf, enhance=True))
    assert gp.writer_seed == 42
    # a new image seed (Remove tries, variants) never changes the writer seed
    import dataclasses
    q = dataclasses.replace(workflows.GenParams(writer_seed=9), seed=123)
    assert q.writer_seed == 9


def main():
    check_workflows()
    check_bridge()
    print("ALL OK (prompt writer seed)")


if __name__ == "__main__":
    main()
