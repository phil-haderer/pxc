# tags: settings, start
"""settings.json is read from disk once and again only when it changes; save_settings is seen at once (tempo plan P2, 24.11.).

    python tests/test_settings_cache.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy.testguard import isolate_home  # noqa: E402

isolate_home()


def main():
    f = cfgmod.SETTINGS_FILE
    assert "PCCOMFY_HOME" in os.environ and Path(os.environ["PCCOMFY_HOME"]) in f.parents, "never the real data/ folder"
    cfgmod.save_settings({"a": 1})
    reads = []
    real = Path.read_text

    def counting(self, *a, **k):
        reads.append(self)
        return real(self, *a, **k)

    Path.read_text = counting
    try:
        s = cfgmod.load_settings()
        assert s.get("a") == 1, s
        for _ in range(5):
            cfgmod.load_settings()
        assert reads == [], f"what this module wrote needs no new read, got {len(reads)}"
        s["a"] = 99
        assert cfgmod.load_settings()["a"] == 1, "changing the returned dict leaves the cache alone"

        cfgmod.save_settings({"a": 2, "b": [1]})
        assert cfgmod.load_settings() == {"a": 2, "b": [1], "_version": cfgmod.APP_VERSION}, "save is seen at once"

        f.write_text(json.dumps({"from": "outside", "x": 12345}), encoding="utf-8")      # another program (or the user) wrote it
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        assert cfgmod.load_settings() == {"from": "outside", "x": 12345}, "a file changed outside is read again"
        assert len(reads) == 1, reads
    finally:
        Path.read_text = real

    f.write_text("broken", encoding="utf-8")
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000))
    assert cfgmod.load_settings() == {}, "a broken file gives empty settings"
    f.unlink()
    assert cfgmod.load_settings() == {}, "no file gives empty settings"
    print("ok: settings.json is read once and again only when it changes")


if __name__ == "__main__":
    main()
