"""Fibo: the GPU memory is freed (ComfyUI /free) before a run only after a model change AND for a large job (user 13.11.,
choice C of 2a; docs/plan/entscheidungen.md, docs/tests/original-size-testlauf.md part H). A stub ComfyUI in Python, no server.

    python tests/test_fibo_free_memory.py
"""
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pccomfy import bridge  # noqa: E402
from pccomfy.bridge import Bridge, Request  # noqa: E402
from pccomfy.comfy import Cancelled  # noqa: E402

WF = ROOT / "workflows"
FIBO_EDIT, FIBO_UP = str(WF / "fibo2-edit.json"), str(WF / "fibo2-upscale.json")
bridge.FREE_PAUSE_S = 0.0           # no waiting in the test


class Stub:
    """Records the calls in order: ("free",) and ("queue", model files)."""

    def __init__(self, fail_free=False):
        self.calls, self.fail_free, self.n = [], fail_free, 0

    def free_memory(self):
        if self.fail_free:
            raise OSError("no /free")
        self.calls.append(("free",))

    def upload_image(self, im, name):
        return name

    def open_events(self):
        return None

    def close_events(self, ws):
        pass

    def queue(self, graph, preview=None):
        self.n += 1
        self.calls.append(("queue", bridge.graph_models(graph)))
        return str(self.n)

    def wait(self, prompt_id, **kw):
        return {}

    def output_images(self, hist, out_node):
        return [Image.new("RGB", (64, 64), "gray")]


def make(stub):
    tmp = tempfile.mkdtemp()
    return Bridge(None, stub, tmp)


def frees(stub):
    return sum(1 for c in stub.calls if c[0] == "free")


def run(b, req, size):
    req, p, tag = b.begin(req)
    return b.process_image(req, p, Image.new("RGB", size, "white"), tag=tag)


def main():
    fails = []

    def check(cond, what):
        print(("ok   " if cond else "FAIL ") + what)
        if not cond:
            fails.append(what)

    # ---- the pieces ----
    check(bridge.frees_memory(FIBO_EDIT) and bridge.frees_memory(FIBO_UP), "Fibo workflows free memory")
    check(not bridge.frees_memory(str(WF / "flux3-klein-upscale.json")) and not bridge.frees_memory(None),
          "other workflows and the built-in graph never")
    g = {"1": {"inputs": {"unet_name": "Fibo\\a.safetensors", "steps": 8}}, "2": {"inputs": {"vae_name": "b.SFT", "x": "c.png"}}}
    check(bridge.graph_models(g) == {"fibo/a.safetensors", "b.sft"}, "graph_models: model files only, folder and case evened")
    big = bridge.big_job
    check(big(Request(mode="refine"), (3000, 2000)), "Refine 6 MP is large")
    check(big(Request(mode="refine"), (2048, 1536)), "Refine 3.1 MP is large")
    check(not big(Request(mode="refine"), (1600, 1200)), "Refine 1.9 MP is not")
    check(big(Request(mode="upscale", scale=2.0), (1024, 1024)), "Upscale to 4.2 MP is large")
    check(not big(Request(mode="upscale", scale=1.5), (1000, 1000)), "Upscale to 2.25 MP is not")
    check(big(Request(mode="edit", full_size=True), (2000, 2000)), "Fibo Refine as Edit, 4 MP, is large")
    check(not big(Request(mode="edit"), (2000, 2000)), "a plain Edit is not")
    im = Image.new("RGB", (32, 32))
    check(big(Request(mode="edit", refs=[im, im]), (1024, 1024)), "Multi Image Edit with 3 slots is large")
    check(not big(Request(mode="edit", refs=[im]), (1024, 1024)), "Multi Image Edit with 2 slots is not")
    check(big(Request(mode="edit", refs=[im], ref_native=True), (1024, 1024)), "references in original size are large")

    # ---- whole runs through process_image ----
    s = Stub()
    b = make(s)
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (1024, 1024))
    check(frees(s) == 0, "small Fibo Refine: no freeing, even as the first run")
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (2400, 1600))
    check(frees(s) == 0, "large Fibo Refine right after Fibo: no freeing (no model change)")

    s = Stub()
    b = make(s)
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (2400, 1600))
    check(frees(s) == 1 and s.calls[0] == ("free",) and s.calls[1][0] == "queue",
          "large Fibo Refine as the first run: freed once, before the job is queued")
    b._last_models = frozenset({"qwen/qwen-image-edit.safetensors"})      # the run before was another model
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (2400, 1600))
    check(frees(s) == 2, "large Fibo Refine after another model: freed")
    b._last_models = frozenset({"qwen/qwen-image-edit.safetensors"})
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (1024, 1024))
    check(frees(s) == 2, "small Fibo Refine after another model: no freeing")
    b._last_models = frozenset({"qwen/qwen-image-edit.safetensors"})
    run(b, Request(mode="edit", workflow=FIBO_EDIT, refs=[im, im], params=_prompt()), (1024, 1024))
    check(frees(s) == 3, "Fibo Multi Image Edit with 3 slots after another model: freed")
    check(b.freed == 3, "Bridge.freed counts it")

    # ---- an old ComfyUI without /free: the run still goes on ----
    s = Stub(fail_free=True)
    b = make(s)
    run(b, Request(mode="refine", workflow=FIBO_UP, scale=1.0), (2400, 1600))
    check(frees(s) == 0 and s.n == 1 and b.freed == 0, "/free fails: the run is queued all the same")

    # ---- Cancel during the pause ----
    s = Stub()
    b = make(s)
    bridge.FREE_PAUSE_S = 5.0
    b._cancel.set()
    try:
        b._free_if_needed(Request(mode="refine"), (2400, 1600), FIBO_UP, {}, lambda *a, **k: None, 0.1)
        check(False, "Cancel during the pause ends the run")
    except Cancelled:
        check(s.n == 0, "Cancel during the pause ends the run")
    bridge.FREE_PAUSE_S = 0.0

    print(f"\n{'FAILED: ' + str(len(fails)) if fails else 'all ok'}")
    return 1 if fails else 0


def _prompt():
    from pccomfy import workflows
    return workflows.GenParams(prompt="put the cat on the sofa")


if __name__ == "__main__":
    sys.exit(main())
