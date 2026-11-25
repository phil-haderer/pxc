# tags: prompt, queue, sketch, comfy
"""The written prompt is kept when a run is stopped after the writer was done (user 25.11., "Text auch beim Stopp merken"):
on 24.11. Sketch ×3 wrote three times because variants 1 and 2 were stopped after their writer had finished, and the text was
only kept for a run that went through. comfy.wait passes every node's output on (on_output); the bridge keeps the text of
the pc:vgl preview from it. A fake ComfyUI and PhotoCraft; no GPU.

    python tests/test_written_on_stop.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-wstop-")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as T  # noqa: E402
from pccomfy import comfy, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402
from pccomfy.comfy import Cancelled  # noqa: E402

SKETCH = ROOT / "workflows" / "qwen-image-21-sketch.json"
WRITTEN = "A photo of waves at dusk."


class StopAfterWriter(T.FakeComfy):
    """Every upload has the same content (as the picture of variant 1 is sent again); the runs in `stop` are stopped right
    after the writer's preview reported its text, like ✕ / Stop run in the window."""
    def __init__(self, bridge, stop):
        super().__init__()
        self.bridge, self.stop, self.n, self.wrote = bridge, set(stop), 0, []
        self.upload_hashes = {}

    def upload_image(self, image, name):
        self.upload_hashes[name] = "same-picture"
        return super().upload_image(image, name)

    def wait(self, pid, on_progress=None, cancelled=None, timeout=0, on_preview=None, on_output=None):
        k, self.n = self.n, self.n + 1
        g = self.graphs[-1]
        vgl = [nid for nid, n in g.items() if "vgl" in workflows._tags(n)]
        self.wrote.append(bool(workflows.prompt_writers(g)))
        if vgl and on_output is not None:
            on_output(vgl[0], {"text": [WRITTEN]})
        if k in self.stop:
            self.bridge.cancel()
            assert cancelled()
            raise Cancelled()
        return {"outputs": {vgl[0]: {"text": [WRITTEN]}} if vgl else {}}


def run(stop, variants=3):
    pc, _, b = T.make(tempfile.mkdtemp(), with_sel=False)
    b.comfy = StopAfterWriter(b, stop)
    req = Request(mode="edit", workflow=str(SKETCH), enhance=True, variants=variants, one_by_one=True)
    req.params = workflows.GenParams(prompt="Turn this sketch of waves into a realistic photo", seed=7)
    try:
        res = b.run(req)
    except Cancelled:
        res = None
    return b, res


def bridge_tests():
    # the waves case of 24.11.: variants 1 and 2 stopped after writing; only variant 1 writes, 2 and 3 take its text
    b, res = run({0, 1})
    assert b.comfy.wrote == [True, False, False], b.comfy.wrote
    assert res and len(res["layers"]) == 1
    # every variant goes through: the same (the writer runs once)
    b, _ = run(set())
    assert b.comfy.wrote == [True, False, False], b.comfy.wrote
    # a single run stopped after writing: the next Generate with the same picture and request does not write again
    b, res = run({0}, variants=1)
    assert res is None and b.comfy.wrote == [True]
    b.reset_cancel_all()
    req = Request(mode="edit", workflow=str(SKETCH), enhance=True)
    req.params = workflows.GenParams(prompt="Turn this sketch of waves into a realistic photo", seed=8)
    b.comfy.stop = set()
    b.run(req)
    assert b.comfy.wrote == [True, False], b.comfy.wrote
    assert b.comfy.graphs[-1] and WRITTEN in json.dumps(b.comfy.graphs[-1])


class FakeWS:
    def __init__(self, msgs):
        self.msgs = list(msgs)

    def recv(self):
        return self.msgs.pop(0)


def wait_tests():
    """comfy.wait hands the output of a finished node to on_output (from the websocket's "executed" message)."""
    c = comfy.ComfyUI("http://127.0.0.1:1")
    c.history = lambda pid: {"status": {"completed": True}, "outputs": {}}
    c._log = lambda *a, **k: None
    ws = FakeWS([json.dumps({"type": "executed", "data": {"prompt_id": "p", "node": "404", "output": {"text": ["hi"]}}}),
                 json.dumps({"type": "executed", "data": {"prompt_id": "other", "node": "9", "output": {"text": ["no"]}}}),
                 json.dumps({"type": "execution_success", "data": {"prompt_id": "p"}})])
    got = []
    c.wait("p", ws=ws, on_output=lambda node, out: got.append((node, out)))
    assert got == [("404", {"text": ["hi"]})], got
    # without on_output the message is simply passed over
    ws = FakeWS([json.dumps({"type": "executed", "data": {"prompt_id": "p", "node": "404", "output": {"text": ["hi"]}}}),
                 json.dumps({"type": "execution_success", "data": {"prompt_id": "p"}})])
    c.wait("p", ws=ws)


def main():
    wait_tests()
    bridge_tests()
    print("ALL OK (written prompt kept on stop)")


if __name__ == "__main__":
    main()
