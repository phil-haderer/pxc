# tags: styles, tools
"""docs/stile-uebersicht.md is current (user 21.11.: every style job works from this overview): it equals what
tools/styles_overview.py writes from pccomfy/assets/styles.json and tools/styles-tests.json, every name in the test log is
a style of the picker, and a renamed style stops the tool. tools/ and docs/ are private: the check skips where they are missing.

    python tests/test_styles_overview.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def main():
    if not (ROOT / "tools" / "styles_overview.py").exists() or not (ROOT / "docs" / "stile-uebersicht.md").exists():
        print("skip: tools/ or docs/ missing (release export)")
        return
    import styles_overview as so
    want = so.build()
    have = so.OUT.read_text(encoding="utf-8")
    assert have == want, "docs/stile-uebersicht.md is behind: run python tools/styles_overview.py"
    # a name the picker lacks stops the tool
    try:
        so.tested([{"id": "X", "mode": "edit", "styles": ["No such style"]}], {"edit": ["Pixel art"]})
    except ValueError as e:
        assert "No such style" in str(e)
    else:
        raise AssertionError("an unknown style name must stop the tool")
    # the old name of a round is shown, '*' covers the whole mode
    got = so.tested([{"id": "R", "mode": "edit", "styles": [{"name": "Pixel art", "als": "Pixels"}]},
                     {"id": "V", "mode": "edit", "styles": ["*"]}], {"edit": ["Pixel art", "Linocut print"]})
    assert got == {("edit", "Pixel art"): ["R (als Pixels)", "V"], ("edit", "Linocut print"): ["V"]}, got
    assert "| Edit canvas | 34 |" in want and "**Offen in Edit canvas" in want
    print("ok")


if __name__ == "__main__":
    main()
