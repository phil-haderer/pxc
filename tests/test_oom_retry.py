# tags: comfy, queue
"""One new try after ComfyUI ran out of GPU memory (user 25.11., "alles"): on 25.11. Fibo Sketch ×3 failed four times in
variant 2 with "Allocation on device 0 would exceed allowed memory. (out of memory)". The bridge calls ComfyUI's /free, waits
and sends the same graph once more; a second OOM, another error or a failed /free end the run as before. A fake ComfyUI and
PhotoCraft; no GPU.

    python tests/test_oom_retry.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-oom-")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reference_mode as T  # noqa: E402
from pccomfy import bridge as B, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402
from pccomfy.comfy import ComfyError  # noqa: E402

B.FREE_PAUSE_S = 0.0
OOM = "ComfyUI reported an error: Allocation on device 0 would exceed allowed memory. (out of memory)"


class FailingComfy(T.FakeComfy):
    """wait() raises the errors in `errors` one after the other, then finishes normally."""
    def __init__(self, errors, free_ok=True):
        super().__init__()
        self.errors, self.free_ok, self.freed = list(errors), free_ok, 0

    def free_memory(self):
        if not self.free_ok:
            raise ComfyError("no /free")
        self.freed += 1

    def wait(self, pid, on_progress=None, cancelled=None, timeout=0, on_preview=None):
        if self.errors:
            raise ComfyError(self.errors.pop(0))
        return super().wait(pid, on_progress, cancelled, timeout, on_preview)


def run(errors, free_ok=True, variants=1):
    pc, _, b = T.make(tempfile.mkdtemp(), with_sel=False)
    b.comfy = FailingComfy(errors, free_ok)
    msgs = []
    req = Request(mode="edit", workflow=str(ROOT / "workflows" / "fibo2-edit.json"), enhance=False, variants=variants,
                  one_by_one=variants > 1)
    req.params = workflows.GenParams(prompt="Turn this sketch of a dog into a realistic photograph", seed=7)
    try:
        res, err = b.run(req, progress=lambda f, m="", **kw: msgs.append(m)), None
    except ComfyError as e:
        res, err = None, e
    return b, res, err, msgs


def main():
    assert B.is_oom(ComfyError(OOM)) and B.is_oom(RuntimeError("torch.OutOfMemoryError: CUDA"))
    assert not B.is_oom(ComfyError("Error in node KSampler: value not in list"))

    b, res, err, msgs = run([OOM])                           # one OOM: /free, then the same graph again
    assert res and err is None and b.comfy.freed == 1 and len(b.comfy.graphs) == 2, (err, b.comfy.freed)
    assert b.comfy.graphs[0] == b.comfy.graphs[1] and B.OOM_RETRY in msgs and b.oom_retries == 1
    b, res, err, _ = run([OOM, OOM])                         # a second OOM ends the run
    assert res is None and B.is_oom(err) and b.comfy.freed == 1 and len(b.comfy.graphs) == 2
    b, res, err, _ = run(["Error in node X: broken"])         # another error: no new try
    assert res is None and "broken" in str(err) and b.comfy.freed == 0 and len(b.comfy.graphs) == 1
    b, res, err, _ = run([OOM], free_ok=False)                # /free fails: the OOM is the error shown
    assert res is None and B.is_oom(err) and len(b.comfy.graphs) == 1
    b, res, err, _ = run([OOM], variants=3)                   # ×3 one by one: the OOM'd variant is tried again, all three come
    assert res and err is None and len(res["layers"]) == 3 and b.comfy.freed == 1 and len(b.comfy.graphs) == 4
    print("ALL OK (one new try after an OOM)")


if __name__ == "__main__":
    main()
