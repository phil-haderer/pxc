# tags: tools
"""tests/run_all.py starts the slowest files of the last run first; new files count as slow (tempo plan T1, 24.11.).

    python tests/test_run_all_order.py
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_all  # noqa: E402


def main():
    files = [Path(n) for n in ("test_a.py", "test_b.py", "test_c.py", "test_new.py")]
    order = [p.name for p in run_all.start_order(files, {"test_a.py": 1.0, "test_b.py": 50.0, "test_c.py": 5.0})]
    assert order == ["test_new.py", "test_b.py", "test_c.py", "test_a.py"], order
    assert sorted(order) == sorted(p.name for p in files), "same files, only another order"
    assert [p.name for p in run_all.start_order(files, {})] == sorted(p.name for p in files), "no times: file order"

    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "times.json"
        assert run_all.load_times(f) == {}, "no file: no times"
        run_all.save_times({"test_a.py": 2.0}, f)
        run_all.save_times({"test_b.py": 3.0}, f)          # a filtered run keeps the times of the other files
        assert run_all.load_times(f) == {"test_a.py": 2.0, "test_b.py": 3.0}
        f.write_text("not json", encoding="utf-8")
        assert run_all.load_times(f) == {}, "a broken file is ignored"

    assert Path(tempfile.gettempdir()) in run_all.TIMES_FILE.parents, "the times file stays outside the repo and data/"

    # on GitHub (install matrix) the pixel-exact window tests are skipped, locally never (user 24.11.)
    some = [Path("test_head_chips.py"), Path("test_bars.py"), Path("test_atpick.py")]
    assert run_all.ci_skipped(some, {}) == (some, []), "locally nothing is skipped"
    assert run_all.ci_skipped(some, {"GITHUB_ACTIONS": "false"}) == (some, [])
    assert run_all.ci_skipped(some, {"GITHUB_ACTIONS": "true"}) == ([Path("test_bars.py")], ["test_head_chips.py", "test_atpick.py"])
    for name in run_all.CI_SKIP:
        assert (HERE / name).is_file(), f"CI_SKIP names a missing file: {name}"
    assert len(run_all.CI_SKIP) == 4, "a new entry needs his OK (the matrix then checks less)"
    print("ok: run_all starts the slowest files first, skips the pixel tests on GitHub only")


if __name__ == "__main__":
    main()
