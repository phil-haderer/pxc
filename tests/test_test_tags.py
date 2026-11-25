# tags: tools
"""Every test file carries topic tags on its first line ("# tags: window, queue"; user 24.11.: "Tag your tests"), only
tags that tests/run_all.py knows, and `run_all.py --tag` picks by them (CLAUDE.md, "Testing": the targeted run).

    python tests/test_test_tags.py
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_all  # noqa: E402


def main():
    files = sorted(HERE.glob("test_*.py"))
    untagged = [p.name for p in files if not run_all.tags_of(p)]
    assert not untagged, f"first line '# tags: ...' missing in: {', '.join(untagged)}"
    unknown = sorted({f"{p.name}: {t}" for p in files for t in run_all.tags_of(p) if t not in run_all.TAGS})
    assert not unknown, f"tags not in run_all.TAGS: {unknown}"
    unused = [t for t in run_all.TAGS if not any(t in run_all.tags_of(p) for p in files)]
    assert not unused, f"tags no file carries (remove them from run_all.TAGS): {unused}"

    with tempfile.TemporaryDirectory() as d:
        a, b, c = (Path(d) / n for n in ("test_alpha.py", "test_beta.py", "test_gamma.py"))
        a.write_text("# tags: queue, undo\n'''x'''\n", encoding="utf-8")
        b.write_text("# tags: window\n", encoding="utf-8")
        c.write_text("'''no tags'''\n# tags: queue\n", encoding="utf-8")       # only the first line counts
        assert run_all.tags_of(a) == ["queue", "undo"] and run_all.tags_of(c) == []
        names = lambda ps: [p.name for p in ps]                                  # noqa: E731
        assert names(run_all.pick([a, b, c], [], ["undo"])) == ["test_alpha.py"]
        assert names(run_all.pick([a, b, c], ["gamma"], ["window"])) == ["test_beta.py", "test_gamma.py"], "name OR tag"
        assert names(run_all.pick([c, b, a], [], [])) == ["test_alpha.py", "test_beta.py", "test_gamma.py"], "all"
    assert run_all.main(["--tag", "no-such-tag"]) == 2, "an unknown tag stops the run"

    # D (24.11.): every module of pccomfy/ has its tags, so a new module without them fails here at once
    mods = {p.stem for p in (HERE.parent / "pccomfy").glob("*.py")}
    assert not mods - set(run_all.MODULE_TAGS), f"modules without tags in run_all.MODULE_TAGS: {sorted(mods - set(run_all.MODULE_TAGS))}"
    assert not set(run_all.MODULE_TAGS) - mods, f"MODULE_TAGS names gone modules: {sorted(set(run_all.MODULE_TAGS) - mods)}"
    bad = sorted({t for ts in [*run_all.MODULE_TAGS.values(), *run_all.PATH_TAGS.values()] for t in ts} - set(run_all.TAGS))
    assert not bad, f"unknown tags in MODULE_TAGS / PATH_TAGS: {bad}"

    # A (24.11.): --changed picks the importers, the tests naming a tool, and the tags of the changed module
    src = "from pccomfy import (\n    bridge,\n    models as m,\n)\nimport pccomfy.jobqueue as jq\nfrom pccomfy.comfy import X\n"
    assert run_all.imported_modules(src) == {"bridge", "models", "jobqueue", "comfy"}, run_all.imported_modules(src)
    with tempfile.TemporaryDirectory() as d:
        a, b, c, e = (Path(d) / n for n in ("test_q.py", "test_w.py", "test_tool.py", "test_x.py"))
        a.write_text("# tags: queue\n", encoding="utf-8")
        b.write_text("# tags: window\nfrom pccomfy import jobqueue\n", encoding="utf-8")
        c.write_text("# tags: tools\nimport squash_day\n", encoding="utf-8")
        e.write_text("# tags: styles\n", encoding="utf-8")
        fs = [a, b, c, e]
        sel = lambda ch: [p.name for p in run_all.changed_selection(ch, fs)[0]]       # noqa: E731
        assert sel(["pccomfy/jobqueue.py"]) == ["test_q.py", "test_w.py"], "tag of the module + its importer"
        assert sel(["tools/squash_day.py"]) == ["test_tool.py"], "a test that names the tool"
        assert sel(["tests/test_x.py"]) == ["test_x.py"], "a changed test runs itself"
        assert sel(["docs/plan/x.md", "PLAN.md"]) == [], "docs only: no test (CLAUDE.md, user 17.11.)"
        assert sel(["workflows/a.json"]) == [], "workflows/ maps to the tag workflows"
    assert run_all.changed_files("HEAD") is not None and all(not Path(n).name.startswith("todo") for n in run_all.changed_files())
    print(f"ok: {len(files)} test files tagged with {len(run_all.TAGS)} known tags")


if __name__ == "__main__":
    main()
