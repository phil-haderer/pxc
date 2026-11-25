# tags: workflows
"""Workflow files are read from disk once and again only when they change; every caller gets its own dict (tempo plan P1, 24.11.).

    python tests/test_workflow_cache.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pccomfy import workflows  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wf.json"
        p.write_text(json.dumps({"1": {"class_type": "A", "inputs": {"x": 1}}}), encoding="utf-8")
        reads = []
        real = Path.read_text

        def counting(self, *a, **k):
            reads.append(self)
            return real(self, *a, **k)

        Path.read_text = counting
        try:
            a = workflows.load_template(p)
            b = workflows.load_template(p)
            c = workflows.read_graph(str(p))
            assert len(reads) == 1, f"read once, not {len(reads)} times"
            assert a == b == c and a is not b and a is not c, "same content, a new dict for every caller"
            a["1"]["inputs"]["x"] = 99
            assert workflows.load_template(p)["1"]["inputs"]["x"] == 1, "changing one copy leaves the cache alone"

            p.write_text(json.dumps({"1": {"class_type": "B", "inputs": {}}, "2": {"class_type": "C", "inputs": {}}}), encoding="utf-8")
            st = p.stat()
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
            assert set(workflows.load_template(p)) == {"1", "2"}, "a changed file is read again"
            assert len(reads) == 2, reads
        finally:
            Path.read_text = real

        p.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000))
        try:
            workflows.load_template(p)
            raise AssertionError("a UI-format save must still be refused")
        except ValueError:
            pass
        try:
            workflows.read_graph(Path(d) / "missing.json")
            raise AssertionError("a missing file must raise OSError")
        except OSError:
            pass

    real_wf = next((ROOT / "workflows").glob("*.json"))
    assert workflows.read_graph(real_wf) == json.loads(real_wf.read_text(encoding="utf-8"))
    print("ok: workflow files are read once and copied for each caller")


if __name__ == "__main__":
    main()
