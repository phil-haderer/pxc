# tags: queue, sketch, multiedit
"""×n one picture after the other for Sketch, Scribble and Multi Edit (user 24.11., choice A "nacheinander"): a batch of n
needed the VRAM of n pictures at once. The window marks these functions with Request.one_by_one; the bridge then runs n
single runs (batch 1, each its own seed) like Refine and groups the layers. A fake PhotoCraft; no ComfyUI. That
variant 2 and later take the scribble of variant 1 needs the real window (docs/plan/fenstertest.md).

    python tests/test_variants_one_by_one.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pccomfy import testguard  # noqa: E402

testguard.isolate_home()
import threading  # noqa: E402

from pccomfy import bridge as B  # noqa: E402
from pccomfy.workflows import GenParams  # noqa: E402


class FakePC:
    def connect(self):
        return self

    def session(self):
        return {"active": 0, "documents": [{"index": 0, "name": "pic.png"}]}


def make() -> B.Bridge:
    b = B.Bridge.__new__(B.Bridge)
    b.pc = FakePC()
    b._cancel, b._cancel_all = threading.Event(), threading.Event()
    b._seq_src = b._variant_no = b._scribble_layer = None
    b.seq_rows, b._seq_written = [], ""
    b._tmp, b.keep_files = [], False
    b.last_vgl = ""
    b.calls, b.groups, b.hidden = [], [], []
    b._group = lambda layers, name: b.groups.append((list(layers), name)) or 99
    b._try = lambda cmd, params=None: b.hidden.append((cmd, params))
    b._activate_doc = lambda name: None

    def run_one(req, p, tag, progress, seq=None):
        b.calls.append((req.variants, p.batch, p.seed, seq))
        return {"layers": [10 + (seq[0] if seq else 0)], "seed": p.seed}
    b._run = run_one
    return b


def req(**kw) -> B.Request:
    return B.Request(mode="edit", params=GenParams(prompt="a red car", seed=100), variants=3, **kw)


def main():
    b = make()
    out = b.run(req(one_by_one=True))
    assert [c[:2] for c in b.calls] == [(1, 1)] * 3, b.calls          # three single runs, batch 1 each
    assert [c[3] for c in b.calls] == [(0, 3), (1, 3), (2, 3)]
    seeds = [c[2] for c in b.calls]
    assert seeds[0] == 100 and len(set(seeds)) == 3, seeds             # each its own seed, the first the one shown
    assert out["seed"] == 100 and out["layers"] == [12, 11, 10] and out["group"] == 99, out
    assert b.groups == [([12, 11, 10], "AI edit variants")], b.groups
    assert ("layer.hideLayers", {"layer": 10}) in b.hidden and ("layer.hideLayers", {"layer": 11}) in b.hidden

    assert [r["status"] for r in b.seq_rows] == ["done"] * 3 and all(r["t0"] and r["t1"] for r in b.seq_rows), b.seq_rows

    # ✕ on a waiting variant in the queue window (user 24.11. evening, choice C): only that one is left out
    b = make()
    seen = []

    def run_skip(req, p, tag, progress, seq=None):
        seen.append(([r["status"] for r in b.seq_rows], b._seq_written))
        if seq[0] == 0:
            assert b.skip_variant(2) and not b.skip_variant(1), "variant 1 runs: no skip (its ✕ is Stop run)"
            b.last_vgl = "WRITTEN ONCE"              # what variant 1's writer wrote
        return {"layers": [10 + seq[0]], "seed": p.seed}
    b._run = run_skip
    out = b.run(req(one_by_one=True))
    assert len(seen) == 2 and seen[1] == (["done", "cancelled", "running"], "WRITTEN ONCE"), seen   # variant 3 takes the text
    assert out["layers"] == [12, 10] and b._seq_written == "", out
    assert [r["status"] for r in b.seq_rows] == ["done", "cancelled", "done"]
    src = (Path(__file__).resolve().parent.parent / "pccomfy" / "bridge.py").read_text(encoding="utf-8")
    assert "if kept is None and wkey and (getattr(self, \"_variant_no\", None) or (1, 1))[0] > 1 and getattr(self, \"_seq_written\", \"\"):" in src

    # Stop batch while variant 1 runs: the waiting ones read Cancelled
    b = make()

    def run_all(req, p, tag, progress, seq=None):
        b._cancel_all.set()
        raise B.Cancelled()
    b._run = run_all
    try:
        b.run(req(one_by_one=True))
        raise AssertionError("no Cancelled")
    except B.Cancelled:
        pass
    assert [r["status"] for r in b.seq_rows] == ["cancelled"] * 3, b.seq_rows

    b = make()                                       # without the mark (Edit, Fill ...): one run with the batch as before
    b.run(req())
    assert b.calls == [(3, 3, 100, None)], b.calls

    b = make()                                       # ×1 with the mark: a plain run
    b.run(B.Request(mode="edit", params=GenParams(prompt="x", seed=5), variants=1, one_by_one=True))
    assert b.calls == [(1, 1, 5, None)], b.calls

    # the window sets the mark for exactly these three functions
    src = (Path(__file__).resolve().parent.parent / "pccomfy" / "gui_run.py").read_text(encoding="utf-8")
    assert 'req.one_by_one = self.v_mode.get() in ("sketch", "scribble", "multi_edit")' in src

    print("test_variants_one_by_one: ok")


if __name__ == "__main__":
    main()
