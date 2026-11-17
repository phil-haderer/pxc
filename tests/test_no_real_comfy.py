"""A test script never talks to the ComfyUI of this PC (port 8188): three test runs ended the listening socket of the real ComfyUI
(WinError 64 in asyncio's accept, 3.11.2026). `comfy.real_comfy_blocked` stops it in ComfyUI._request, open_events and
comfyaddr.probe. Nothing here connects anywhere.

    python tests/test_no_real_comfy.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pccomfy import comfy, comfyaddr  # noqa: E402


def main():
    blocked = comfy.real_comfy_blocked
    assert Path(sys.argv[0]).resolve().parent.name == "tests"
    # in a test script: the default port of this PC is blocked, every other port is not
    for host in ("127.0.0.1", "localhost", "::1"):
        assert blocked(host, 8188), host
    assert not blocked("127.0.0.1", 8189) and not blocked("127.0.0.1", 1) and not blocked("192.168.1.20", 8188)
    assert not blocked("example.com", 8188)
    # the requests, the websocket and the address check refuse without opening a socket
    c = comfy.ComfyUI("http://127.0.0.1:8188")
    try:
        c.system_stats()
        raise SystemExit("expected a ComfyError")
    except comfy.ComfyError as e:
        assert "Blocked" in str(e), str(e)
    assert c.open_events() is None
    ok, why = comfyaddr.probe("http://localhost:8188")
    assert not ok and "Blocked" in why, why
    # the opt-out for a deliberate run, and the manual live checks are not blocked
    os.environ["PCCOMFY_ALLOW_REAL_COMFY"] = "1"
    try:
        assert not blocked("127.0.0.1", 8188)
    finally:
        del os.environ["PCCOMFY_ALLOW_REAL_COMFY"]
    # outside a test (14.11.: test code on the call stack counts as a test too, so these run in a process of their own, from a
    # script that is not in a tests/ folder): the plugin itself, a live_*.py check and no script name are never blocked
    probe = ("import sys\nsys.path.insert(0, {root!r})\nfrom pccomfy import comfy\nfrom pathlib import Path\nR = Path({root!r})\n"
             "for argv in ([str(R / 'tests' / 'live_fill_mask.py')], [str(R / 'pccomfy' / '__main__.py')], []):\n"
             "    sys.argv[:] = argv\n    assert not comfy.real_comfy_blocked('127.0.0.1', 8188), argv\nprint('free')\n")
    with tempfile.TemporaryDirectory(prefix="pccomfy-comfy-guard-") as tmp:
        f = Path(tmp) / "probe.py"
        f.write_text(probe.format(root=str(ROOT)), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PCCOMFY_ALLOW_REAL_COMFY"}
        r = subprocess.run([sys.executable, "-B", str(f)], cwd=tmp, capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0 and r.stdout.strip() == "free", (r.stdout, r.stderr)
        # the same helper running a test file through runpy is blocked (the scratchpad helpers of 14.11.)
        t = Path(tmp) / "tests"
        t.mkdir()
        (t / "test_inner.py").write_text(
            f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nfrom pccomfy import comfy\n"
            "print('blocked' if comfy.real_comfy_blocked('127.0.0.1', 8188) else 'free')\n", encoding="utf-8")
        h = Path(tmp) / "helper.py"
        h.write_text(f"import runpy\nrunpy.run_path({str(t / 'test_inner.py')!r}, run_name='__main__')\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "-B", str(h)], cwd=tmp, capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0 and r.stdout.strip() == "blocked", (r.stdout, r.stderr)
    print("ALL OK (tests never touch the real ComfyUI)")


if __name__ == "__main__":
    main()
