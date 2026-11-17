"""The ComfyUI dot stays green over short stalls (a big model loading, user 11.11.): red only after 3 failed probes in a row,
a success resets the count, and during a run the poll never turns it red. Run against the stubbed Tk of test_gui_presets.

    python tests/test_comfy_dot_grace.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_settings_ui as ts  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

OK, BAD = "ConnOk.TLabel", "ConnBad.TLabel"


def green(app):
    return app.v_conn.get() == "ComfyUI connected" and app.lbl_dot.cget("style") == OK


def main():
    app = ts.make_app()
    app.refresh = lambda: None
    url = app.comfy.url
    app._comfy_read = True
    app._comfy_alive(url, True)
    assert green(app)
    # two misses keep it green, the third turns it red
    app._comfy_alive(url, False)
    app._comfy_alive(url, False)
    assert green(app)
    app._comfy_alive(url, False)
    assert app.v_conn.get() == "ComfyUI not connected" and app.lbl_dot.cget("style") == BAD
    # a success resets the count: two misses, a success, two misses stay green
    app._comfy_read = True
    app._comfy_alive(url, True)
    app._apply_refresh({"comfy": True})
    assert green(app)
    app._comfy_alive(url, False)
    app._comfy_alive(url, False)
    app._comfy_alive(url, True)
    app._comfy_alive(url, False)
    app._comfy_alive(url, False)
    assert green(app)
    # an active run: never red from the poll
    app._running = True
    for _ in range(10):
        app._comfy_alive(url, False)
    assert green(app)
    app._running = False
    app._comfy_alive(url, False)                      # the run is over and the misses go on: red at once
    assert app.lbl_dot.cget("style") == BAD
    # before any success (not up) a miss shows red at once, as before
    app2 = ts.make_app()
    app2._comfy_up = False
    app2._comfy_alive(app2.comfy.url, False)
    assert app2.lbl_dot.cget("style") == BAD
    # no connection at all (ComfyUI closed): red at once, but never during a run
    app3 = ts.make_app()
    app3.refresh = lambda: None
    app3._comfy_read = True
    app3._comfy_alive(app3.comfy.url, True)
    assert green(app3)
    app3._running = True
    app3._comfy_alive(app3.comfy.url, False, True)
    assert green(app3)
    app3._running = False
    app3._comfy_alive(app3.comfy.url, False, True)
    assert app3.lbl_dot.cget("style") == BAD and app3.v_conn.get() == "ComfyUI not connected"
    # a timeout (busy loading) keeps the tolerance
    app3._comfy_read = True
    app3._comfy_alive(app3.comfy.url, True)
    app3._apply_refresh({"comfy": True})
    app3._comfy_alive(app3.comfy.url, False, False)
    assert green(app3)
    # the watcher passes the refusal on: probe_ex is asked, the answer goes into the events (no real port 8188)
    from pccomfy import comfyaddr
    import queue
    import os
    seen = []
    old, env = comfyaddr.probe_ex, os.environ.pop("PCCOMFY_NO_WATCH", None)
    comfyaddr.probe_ex = lambda url, timeout=3.0: (seen.append(timeout), (False, "Not reachable", True))[1]
    try:
        app3._watching = False
        app3.events = queue.Queue()
        app3.root.after = lambda *a, **k: None
        app3._watch_comfy()
        got = app3.events.get(timeout=3)
    finally:
        comfyaddr.probe_ex = old
        if env is not None:
            os.environ["PCCOMFY_NO_WATCH"] = env
    assert got == ("alive", (app3.comfy.url, False, True)) and seen == [2.0], (got, seen)
    # probe_ex tells "no connection" from the rest on a real closed local port (not 8188), and fast
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    import time
    t0 = time.time()
    ok, _m, refused = comfyaddr.probe_ex(f"http://127.0.0.1:{port}", 2.0)       # the real timeout of the watcher
    assert not ok and refused and time.time() - t0 < 1.2, time.time() - t0      # Windows needs 2 s to refuse; the short connect makes it < 1 s
    from pccomfy import icons
    im = icons.error_badge(16)
    assert im.size == (16, 16) and im.getpixel((8, 8))[3] == 255 and im.getpixel((0, 0))[3] == 0   # a circle: the corner is clear
    print("ok")


if __name__ == "__main__":
    main()
