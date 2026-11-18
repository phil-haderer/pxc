"""tools/save_ratings.py copies the small text files of every rated round from data\\ to docs\\tests\\runs\\ (user 18.11.),
leaves pictures and exchange folders out, copies only new or changed files and never deletes."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import save_ratings as sr  # noqa: E402


def _tree(base: Path):
    src, dst = base / "data", base / "runs"
    r = src / "sketch-test" / "round9"
    (r / "bilder").mkdir(parents=True)
    (r / "bewertung.json").write_text('{"0": {"wahl": "gut"}}', encoding="utf-8")
    (r / "key.json").write_text("{}", encoding="utf-8")
    (r / "ergebnis.md").write_text("# x", encoding="utf-8")
    (r / "bilder" / "0001.png").write_bytes(b"png")
    (r / "big.json").write_bytes(b" " * (sr.MAX_BYTES + 1))
    (src / "exchange").mkdir()
    (src / "exchange" / "bewertung.json").write_text("{}", encoding="utf-8")       # not a round
    (src / "unrated" / "x").mkdir(parents=True)
    (src / "unrated" / "key.json").write_text("{}", encoding="utf-8")               # no rating: not copied
    return src, dst


def test_copies_only_the_small_text_files_of_rated_rounds():
    with tempfile.TemporaryDirectory() as t:
        src, dst = _tree(Path(t))
        assert sr.rounds(src) == [src / "sketch-test" / "round9"]
        todo = sr.plan(src, dst)
        names = sorted(f.name for f, _ in todo)
        assert names == ["bewertung.json", "ergebnis.md", "key.json"], names
        assert all(tgt == dst / "sketch-test" / "round9" / f.name for f, tgt in todo)


def test_only_new_or_changed_files_and_nothing_deleted():
    with tempfile.TemporaryDirectory() as t:
        src, dst = _tree(Path(t))
        for f, tgt in sr.plan(src, dst):
            tgt.parent.mkdir(parents=True, exist_ok=True)
            tgt.write_bytes(f.read_bytes())
        (dst / "sketch-test" / "old-round").mkdir()
        (dst / "sketch-test" / "old-round" / "bewertung.json").write_text("{}", encoding="utf-8")
        assert sr.plan(src, dst) == []
        (src / "sketch-test" / "round9" / "bewertung.json").write_text('{"0": {"wahl": "schlecht"}}', encoding="utf-8")
        assert [f.name for f, _ in sr.plan(src, dst)] == ["bewertung.json"]
        assert (dst / "sketch-test" / "old-round" / "bewertung.json").exists()


def test_targets_stay_private():
    assert sr.DST == ROOT / "docs" / "tests" / "runs"      # docs\ never goes into a release (tools/export_release.py)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
