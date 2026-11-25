# tags: tools
"""The "N left, about M min" part of the progress line of the GPU rounds (tests/live_progress.py, user 22.11.).

    python tests/test_live_progress.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_progress import Left  # noqa: E402


def main():
    now = [0.0]
    left = Left(24, clock=lambda: now[0])
    now[0] = 26
    assert left(1) == " - 23 left, about 10 min", left(1)    # 23 x 26 s
    now[0] = 52 * 10                                           # skipped pictures (already done) do not count
    left = Left(10, clock=lambda: now[0])
    now[0] = 52 * 10 + 30
    assert left(9) == " - 1 left, about <1 min"
    assert left(10) == " - last one"
    # every run loop of the rounds prints it
    for name in ("live_minimax_edit", "live_minimax_fill_multi", "live_minimax_sketch", "live_t2i_styles"):
        text = (ROOT / "tests" / f"{name}.py").read_text(encoding="utf-8")
        assert "Left(len(js))" in text and "+ left(i)" in text, name
    print("ALL OK (live progress)")


if __name__ == "__main__":
    main()
