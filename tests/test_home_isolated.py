# tags: tools
"""pccomfy.config reads PCCOMFY_HOME once, at import. A test that imports pccomfy before setting its own PCCOMFY_HOME would use
the real data/ folder (settings, state, queue) and could read or overwrite it. The runner therefore gives every test process a
throw-away PCCOMFY_HOME (run_all.child_env); this test pins that, and that a test's own value still wins. Nothing here talks to
ComfyUI.

    python tests/test_home_isolated.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import run_all  # noqa: E402

PROBE = "from pccomfy import config; print(config.CONFIG_DIR)"


def run_py(args: list, cwd, env: dict) -> subprocess.CompletedProcess:
    """Start Python and read its output as UTF-8 both ways. The runner passes PYTHONIOENCODING=utf-8 on, so the child prints
    UTF-8; read with the Windows code page, a folder like "Plugin Ordner Jörg Ä" (install matrix) came back as "JÃ¶rg Ã„"."""
    return subprocess.run([sys.executable, "-B", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          env={**env, "PYTHONIOENCODING": "utf-8"}, timeout=60)


def config_dir(env: dict) -> Path:
    r = run_py(["-c", PROBE], ROOT, env)
    assert r.returncode == 0, r.stderr
    return Path(r.stdout.strip()).resolve()


def main():
    base = {k: v for k, v in os.environ.items() if k != "PCCOMFY_HOME"}
    with tempfile.TemporaryDirectory(prefix="pccomfy-home-check-") as home:
        env = run_all.child_env(home)
        assert env["PCCOMFY_HOME"] == home
        # a plain import, nothing else set: the plugin uses the throw-away folder, never <repo>/data
        got = config_dir({**base, **env})
        assert got == Path(home).resolve(), got
        assert (ROOT / "data").resolve() not in got.parents and got != (ROOT / "data").resolve()
        # a test that sets its own folder after the runner did wins
        with tempfile.TemporaryDirectory(prefix="pccomfy-home-own-") as own:
            assert config_dir({**base, **env, "PCCOMFY_HOME": own}) == Path(own).resolve()
    # the runner really starts its children with it: run_one on this very file sees a home that is not the real data folder
    src = (HERE / "run_all.py").read_text(encoding="utf-8")
    assert "env=child_env(home)" in src, "run_one must start every test with child_env(home)"
    hand_run_guard(base)
    print("ok: every test process gets its own PCCOMFY_HOME")


def run_script(folder_name: str, script_name: str, env: dict) -> Path:
    """Run a tiny script from <tmp>/<folder_name>/<script_name> (the guard looks at the folder name of the main script)."""
    with tempfile.TemporaryDirectory(prefix="pccomfy-guard-script-") as tmp:
        d = Path(tmp) / folder_name
        d.mkdir()
        f = d / script_name
        f.write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n{PROBE}\n", encoding="utf-8")
        r = run_py([str(f)], tmp, env)
        assert r.returncode == 0, r.stderr
        return Path(r.stdout.strip()).resolve()


def hand_run_guard(base: dict):
    """pccomfy.testguard: a script in a tests/ folder started by hand (no PCCOMFY_HOME) gets a throw-away home."""
    # a script outside tests/ (the real app) is not touched: the normal folder (only computed, nothing is created there)
    real = run_script("tools", "probe.py", base)
    if sys.platform == "win32":
        assert real == (ROOT / "data").resolve(), real
    got = run_script("tests", "test_probe.py", base)
    assert got != real and real not in got.parents, got
    assert got.name.startswith("pccomfy-test-home-"), got
    # a manual live_*.py check keeps the normal folder (it reads the real config.toml on purpose; only the path is computed here)
    assert run_script("tests", "live_probe.py", base) == real
    # opt-out
    assert run_script("tests", "test_probe.py", {**base, "PCCOMFY_ALLOW_REAL_HOME": "1"}) == real
    # a helper outside tests/ that runs a test file through runpy is a test too (14.11.: two scratchpad helpers did that and
    # overwrote the real settings.json and state.json); a live_*.py run that way keeps the normal folder
    with tempfile.TemporaryDirectory(prefix="pccomfy-guard-runpy-") as tmp:
        t = Path(tmp) / "tests"
        t.mkdir()
        (t / "test_inner.py").write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n{PROBE}\n", encoding="utf-8")
        (t / "live_inner.py").write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n{PROBE}\n", encoding="utf-8")
        for inner, isolated in (("test_inner.py", True), ("live_inner.py", False)):
            helper = Path(tmp) / f"helper_{inner}"
            helper.write_text(f"import runpy\nrunpy.run_path({str(t / inner)!r}, run_name='__main__')\n", encoding="utf-8")
            r = run_py([str(helper)], tmp, base)
            assert r.returncode == 0, r.stderr
            got = Path(r.stdout.strip()).resolve()
            if isolated:
                assert got != real and got.name.startswith("pccomfy-test-home-"), got
            else:
                assert got == real, got
    # an own PCCOMFY_HOME wins
    with tempfile.TemporaryDirectory(prefix="pccomfy-home-own2-") as own:
        assert run_script("tests", "test_probe.py", {**base, "PCCOMFY_HOME": own}) == Path(own).resolve()
    print("ok: hand-run guard")


if __name__ == "__main__":
    main()
