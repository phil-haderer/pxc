# tags: release, window
"""The update check (docs/plan/update.md, user 19.11.: A1 + A2, H2, B1, B3). Never asks GitHub: a small server of its own.

    python tests/test_update_check.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-update-")
os.environ["PCCOMFY_HOME"] = TMP
os.environ["PCCOMFY_NO_UPDATE_CHECK"] = "1"       # no start check by itself; the test calls the check
sys.path.insert(0, str(ROOT))

from pccomfy import update  # noqa: E402

ANSWER = {"status": 200, "body": {}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ANSWER["agent"] = self.headers.get("User-Agent")
        body = ANSWER["body"]
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(ANSWER["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/releases/latest"


def check_pure():
    assert update.is_newer("1.0.7", "1.0.6") and update.is_newer("v2.0", "1.9.9")
    assert not update.is_newer("1.0.6", "1.0.6") and not update.is_newer("1.0.5", "1.0.6") and not update.is_newer("x", "1.0")
    assert update.is_dev("1.0.6-dev") and update.is_dev("1.0.8-DEV ") and not update.is_dev("1.0.7") and not update.is_dev("0.21-test")
    now = 1_000_000.0
    assert update.due(None, now) and update.due("x", now) and update.due(now - update.DAY_S, now)
    assert not update.due(now - 3600, now) and update.due(now + 60, now)          # the clock went back: check
    assert update.to_show({"version": "99.0", "url": "u"}) == {"version": "99.0", "url": "u"}
    assert update.to_show({"version": "99.0"}, skipped="99.0") is None
    assert update.to_show({"version": "0.1"}) is None and update.to_show(None) is None
    for url in ("https://github.com/phil-haderer/pxc", "https://github.com/phil-haderer/pxc.git",
                "git@github.com:phil-haderer/pxc.git", "https://github.com/Phil-Haderer/PxC/"):
        assert update.is_public_repo_url(url), url
    for url in ("https://github.com/phil-haderer/pxc-dev.git", "https://github.com/phil-haderer/pxc-test",
                "https://example.com/phil-haderer/pxc", "", "C:/repos/pxc"):
        assert not update.is_public_repo_url(url), url
    # the working repo (remote private = pxc-dev, branch next) is never updated with git pull. A release folder can be a
    # clone of pxc on main, where "git" is right (install matrix of pxc, red since 1.0.5): there only check_git_pull's
    # own clones count. CLAUDE.md is never exported, so it marks the working repo; a folder without .git is a ZIP.
    if (ROOT / "CLAUDE.md").exists() or not (ROOT / ".git").exists():
        assert update.install_kind(ROOT) == "zip"
    assert set(update.UPDATE_STEPS) == {"zip", "git"}


def check_fetch(url):
    ANSWER.update(status=200, body={"tag_name": "v1.2.3", "html_url": "https://example.invalid/r", "body": "news"})
    r = update.fetch_latest(url)
    assert (r.version, r.url, r.notes) == ("1.2.3", "https://example.invalid/r", "news"), r
    assert ANSWER["agent"] == f"PxC/{update.__version__}", ANSWER["agent"]      # nothing but the version
    for status, body, want in ((404, {"message": "Not Found"}, "404"), (200, b"{nope", "cannot read"), (200, {"tag_name": ""}, "no version")):
        ANSWER.update(status=status, body=body)
        try:
            update.fetch_latest(url)
            raise AssertionError(f"no error for {status} {body!r}")
        except update.UpdateError as e:
            assert want in str(e), e
    try:
        update.fetch_latest("http://127.0.0.1:1/x", timeout=2)
        raise AssertionError("no error without a server")
    except update.UpdateError as e:
        assert "No connection" in str(e)
    try:                                                     # a test never asks the real GitHub
        update.fetch_latest()
        raise AssertionError("the real GitHub was asked")
    except update.UpdateError as e:
        assert "Blocked" in str(e)


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def check_git_pull():
    if not shutil.which("git"):
        print("SKIPPED git part (no git)")
        return
    base = Path(tempfile.mkdtemp(prefix="pccomfy-upd-git-"))
    origin, work, clone = base / "origin.git", base / "work", base / "clone"
    git(base, "init", "--bare", "-b", "main", str(origin))
    git(base, "clone", str(origin), str(work))
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git(work, "config", k, v)
    (work / "a.txt").write_text("1\n")
    (work / "requirements.txt").write_text("pillow\n")
    git(work, "add", "a.txt", "requirements.txt")
    git(work, "commit", "-m", "one")
    git(work, "push", "origin", "HEAD:main")
    git(base, "clone", "-b", "main", str(origin), str(clone))
    real = update.is_public_repo_url
    update.is_public_repo_url = lambda u: True          # the local origin stands in for github.com/phil-haderer/pxc
    try:
        assert update.install_kind(clone) == "git"
        assert update.git_update(clone) == (True, "Already up to date.")
        (work / "a.txt").write_text("2\n")
        git(work, "commit", "-am", "two")
        git(work, "push", "origin", "HEAD:main")
        ok, text = update.git_update(clone)
        assert ok and "Restart PxC" in text and (clone / "a.txt").read_text().strip() == "2", text
        (work / "requirements.txt").write_text("pillow\nnumpy\n")
        git(work, "commit", "-am", "three")
        git(work, "push", "origin", "HEAD:main")
        ok, text = update.git_update(clone)
        assert ok and "again" in text, text                              # a new package: run the setup again
        (clone / "a.txt").write_text("changed by hand\n")                # a changed file: nothing is pulled
        (work / "a.txt").write_text("4\n")
        git(work, "commit", "-am", "four")
        git(work, "push", "origin", "HEAD:main")
        ok, text = update.git_update(clone)
        assert not ok and "changed" in text and (clone / "a.txt").read_text() == "changed by hand\n", text
        git(clone, "checkout", "-b", "other")                            # not on main: the release page
        assert update.install_kind(clone) == "zip"
    finally:
        update.is_public_repo_url = real
        shutil.rmtree(base, ignore_errors=True)


def check_window(url):
    try:
        import tkinter
        _r = tkinter.Tk()
        _r.destroy()
    except Exception as e:
        print(f"SKIPPED window part (no Tk window: {e})")
        return
    from pccomfy import config as cfgmod
    from pccomfy import gui
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app._update_url = url

    def run_check():
        app._update_check(manual=True)
        end = time.time() + 10
        while app._update_busy and time.time() < end:
            app.root.update()
            time.sleep(0.05)
        assert not app._update_busy, "no answer"

    try:
        assert not app.lbl_update_dot.winfo_manager()                     # nothing known: no dot
        app.open_settings()
        app._settings_win.update()
        assert app.cb_update_check.cget("text") == "Check for updates" and app.v_update_check.get()   # ticked from the factory
        assert not app.f_update_note.winfo_manager()
        ANSWER.update(status=200, body={"tag_name": "v99.0.0", "html_url": "https://example.invalid/r99", "body": ""})
        run_check()
        assert app._update_found == {"version": "99.0.0", "url": "https://example.invalid/r99"}
        assert app.lbl_update_dot.winfo_manager() == "place"              # H2: the blue dot on the gear
        assert app.f_update_note.winfo_manager() == "pack"
        assert app.f_update_note.master.pack_slaves()[0] is app.f_update_note      # at the very top of Other settings
        assert str(app.b_update_news.cget("text")) == "What's new" and str(app.b_update_skip.cget("text")) == "Skip this version"
        # the steps for this folder: B1 "unpack it over this folder" in the working repo (zip, pinned in check_pure), git
        # pull in a clone of pxc on main (install matrix of pxc)
        assert str(app.lbl_update_steps.cget("text")) == update.UPDATE_STEPS[update.install_kind()]
        assert cfgmod.load_state()[update.KEY_FOUND]["version"] == "99.0.0"      # the dot survives a restart
        app._update_skip()
        assert cfgmod.get_setting(update.KEY_SKIP) == "99.0.0" and not app.lbl_update_dot.winfo_manager()
        assert not app.f_update_note.winfo_manager()
        run_check()                                                         # asked by hand: the skipped one shows again
        assert app._update_found and cfgmod.get_setting(update.KEY_SKIP) is None
        ANSWER.update(body={"tag_name": "v0.0.1", "html_url": "x", "body": ""})
        run_check()
        assert app._update_found is None and "is the latest version" in str(app.lbl_update_status.cget("text"))
        assert not app.lbl_update_dot.winfo_manager()
        ANSWER.update(status=500, body={})
        run_check()
        assert "500" in str(app.lbl_update_status.cget("text"))
        app.cb_update_check.invoke()                                        # untick: the start check is off
        assert cfgmod.get_setting(update.KEY_OFF) is True
        app.state[update.KEY_LAST] = 0
        app._update_check_auto()
        assert not app._update_busy
        app.cb_update_check.invoke()
        assert cfgmod.get_setting(update.KEY_OFF) is None
        app.state[update.KEY_LAST] = time.time()                            # checked today: no second check
        app._update_check_auto()
        assert not app._update_busy
        real_version = update.__version__
        try:                                                                # the working folder (user 21.11.): no start check
            update.__version__ = "1.0.6-dev"
            app.state[update.KEY_LAST] = 0
            app._update_check_auto()
            assert not app._update_busy
        finally:
            update.__version__ = real_version
        app._settings_close()
    finally:
        app.root.destroy()


def main():
    srv, url = serve()
    try:
        check_pure()
        check_fetch(url)
        check_git_pull()
        check_window(url)
    finally:
        srv.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)
    print("ok update check")


if __name__ == "__main__":
    main()
