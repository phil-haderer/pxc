"""Prompt writer seed (user 17.11., choice A): a seed of its own for the text model that writes the prompt inside a run, so a new
image seed keeps the written prompt. Only the writer of the run (and its reference description in Scribble with reference);
Describe canvas and the slot descriptions are left alone. The row sits in the Advanced settings and is shown only while a
writer that samples runs (not Fibo). Start value 0 (as the workflows' own), -1 = a new one each run; saved like the other
settings. Workflows, bridge and the window with the stubbed Tk.

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


def check_window():
    import shutil
    import test_gui_presets as t
    gui, cfgmod = t.gui, t.cfgmod
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in gui.models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    shown = {"on": False}
    app.f_wseed.grid = lambda *a, **k: shown.__setitem__("on", True)
    app.f_wseed.grid_remove = lambda *a, **k: shown.__setitem__("on", False)

    def pick(model, mode):
        app.v_model.set(model)
        app.v_mode.set(mode)
        app._on_model()

    assert app.v_writer_seed.get() == gui.WRITER_SEED_DEFAULT == 0
    pick("qwen", "sketch")
    assert shown["on"], "Qwen Sketch to image: the writer samples, the row is shown"
    assert app._request().params.writer_seed == 0
    app.v_writer_seed.set(1234)
    assert app._request().params.writer_seed == 1234
    assert app._collect()["writer_seed"] == 1234
    pick("fibo", "sketch")
    assert not shown["on"], "Fibo's writer takes the likeliest words: no row"
    pick("flux3", "inpaint")
    assert not shown["on"], "Flux 3 Fill has no prompt writer"
    pick("flux3", "txt2img")
    app.v_enhance.set(True)
    app._on_workflow()
    assert shown["on"], "Flux 3 Text to image with Enhance my Prompt on"
    app.v_enhance.set(False)
    app._on_workflow()
    assert not shown["on"], "Enhance off: the writer does not run"
    # saved settings and the history put it back; Reset page goes back to the start value
    s = app._collect()
    app.v_writer_seed.set(0)
    app._apply_settings(dict(s, writer_seed=987))
    assert app.v_writer_seed.get() == 987
    app._apply_settings({k: v for k, v in s.items() if k != "writer_seed"})     # an older save without the key keeps the box
    assert app.v_writer_seed.get() == 987
    app._reset_settings()
    assert app.v_writer_seed.get() == 0
    app.v_writer_seed.set(-1)
    assert app._request().params.writer_seed == -1


def main():
    check_workflows()
    check_bridge()
    check_window()
    print("ALL OK (prompt writer seed)")


if __name__ == "__main__":
    main()
