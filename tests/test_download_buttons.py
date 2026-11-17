"""The download symbols of the settings window and the ComfyUI folder finder, against the stubbed Tk (no network, no GPU).

    python tests/test_download_buttons.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_settings_ui as ts  # noqa: E402  (installs the Tk stub)

t, td = ts.t, ts.td
from pccomfy import comfydir, downloads, inventory, manifest, ui_downloads  # noqa: E402

gui = t.gui
NODES = ts.NODES
SMALL = "taef2_decoder.pth"                       # Hugging Face, not gated
GATED = "flux3-image-klein-int8-convrot.safetensors"
ULTRA = "Flux 2" + chr(92) + "ultra_real_v4.safetensors"          # a Civitai LoRA: its page opens instead
UPS = "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors"      # gated at Hugging Face: its page opens instead


def drain(app, until=lambda: False, limit=200):
    """Take the "download" events the worker sent and hand them to the window, until ``until()`` or no more come."""
    for _ in range(limit):
        if until():
            return
        try:
            kind, data = app.events.get(timeout=5)
        except Exception:
            return
        if kind == "download":
            app._download_event(data)


def root_lookup_checks(base, root):
    """The ComfyUI folder (user 17.11.): Windows reported ComfyUI's waiting port without the state Listen, the lookup found nothing and
    the window asked for the folder. Now: the process that holds the port, else a python process with main.py on our port; a click
    looks up again after "none found"; ComfyUI not running: a short note, no folder window."""
    exe = str(base / "python_embeded" / "python.exe")
    portable = r".\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build"
    assert comfydir._port_of(portable) == 8188 and comfydir._port_of("python main.py --port 8190") == 8190
    assert comfydir._port_of('python main.py --listen --port=8191') == 8191
    one = {"ExecutablePath": exe, "CommandLine": portable}
    assert comfydir.pick_process({"how": "port", "items": one}, 8188) == root                 # one object, not a list
    assert comfydir.pick_process({"how": "port", "items": [one]}, 9000) == root                # the port's own process: any port
    assert comfydir.pick_process({"how": "process", "items": [one]}, 8188) == root
    assert comfydir.pick_process({"how": "process", "items": [one]}, 8190) is None              # another ComfyUI's port
    other = {"ExecutablePath": r"C:\nowhere\python.exe", "CommandLine": "python main.py --port 8190"}
    assert comfydir.pick_process({"how": "process", "items": [other, one]}, 8188) == root
    assert comfydir.pick_process({}, 8188) is None and comfydir.pick_process({"how": "port", "items": [None]}, 8188) is None
    assert "Listen" not in comfydir._WIN_SCRIPT and "RemotePort -eq 0" in comfydir._WIN_SCRIPT

    app = ts.make_app()
    app.comfy.url = "http://127.0.0.1:8188"
    asked, calls = [], []
    app._ask_models_dir = lambda ask, remote: asked.append(remote) if ask else None      # the real one asks only on a click
    real = ui_downloads.comfydir.find_root
    try:
        # the start found nothing; the click looks up again and finds it
        app._comfy_root = Path("")
        ui_downloads.comfydir.find_root = lambda url, **k: calls.append(url) or root
        assert app.models_dir() == root / "models" and calls and asked == []
        # a window being drawn does not wait for the lookup
        app._comfy_root, calls[:] = Path(""), []
        assert app.models_dir(ask=False) is None and calls == []
        # ComfyUI not running (the dot is red): a short note, no folder window
        ui_downloads.comfydir.find_root = lambda url, **k: None
        app._comfy_up = False
        got = app.models_dir()
        assert got is None and asked == [], (got, asked, app._comfy_root)
        assert app.v_status.get() == ui_downloads.COMFY_NOT_RUNNING
        # running, but its folder cannot be found: the window asks as before
        app._comfy_up = True
        app.models_dir()
        assert asked == [False]
    finally:
        ui_downloads.comfydir.find_root = real
        app._comfy_root = Path("")


def main():
    # ---- the ComfyUI folder finder
    base = Path(tempfile.mkdtemp())
    root = base / "ComfyUI"
    (root / "models").mkdir(parents=True)
    (root / "main.py").write_text("", encoding="utf-8")
    (base / "python_embeded").mkdir()
    assert comfydir.models_dir_of(root) == root / "models" and comfydir.models_dir_of(root / "models") == root / "models"
    assert comfydir.models_dir_of(base) == root / "models" and comfydir.models_dir_of(base / "nothing") is None
    assert comfydir.root_from_process(str(base / "python_embeded" / "python.exe"), r".\python_embeded\python.exe  ComfyUI\main.py") == root
    assert comfydir.root_from_process(r"C:\Python\python.exe", f'python "{root / "main.py"}" --port 8188') == root
    assert comfydir.root_from_process(r"C:\nowhere\python.exe", "python x.py") is None
    assert comfydir.find_root("http://example.org:8188") is None                   # only a local server is looked up

    root_lookup_checks(base, root)

    # ---- the "ComfyUI without models" test start loads into a sandbox folder of the test user, never into ComfyUI's
    os.environ["PCCOMFY_SIMULATE_NO_MODELS"] = "1"
    try:
        sand = ts.make_app().models_dir(ask=False)
        assert sand == ts.cfgmod.CONFIG_DIR / "test-downloads" and sand.is_dir()
    finally:
        del os.environ["PCCOMFY_SIMULATE_NO_MODELS"]

    # ---- the buttons
    mdir = Path(tempfile.mkdtemp()).resolve()        # the long form: a temp path can hold a short name like FDK-DE~1, the download target is resolved
    os.environ["PCCOMFY_MODELS_DIR"] = str(mdir)
    app = ts.make_app()
    lists = td.full_lists()
    lists["preview"] = []
    lists["vae"].remove("flux2-vae_small.safetensors")
    lists["unet"].remove("moss_image_sft_int8_convrot.safetensors")
    lists["lora"].remove(ULTRA)
    lists["clip"].remove(UPS)
    lists["vae"].remove("flux2-vae.safetensors")
    app._apply_refresh({"_detect": True, "_inv": inventory.Inventory(lists, NODES)})
    app.open_settings()
    files = {d["name"]: d for d in ts.file_rows(app)}
    assert files[SMALL]["dl"] is None and files[SMALL]["browser"] is False and files[GATED]["browser"] is True
    heads = {r[1]: r[5] for r in app._settings_rows() if r[0] == "model"}
    assert heads["moss"]["count"] == 2 and heads["moss"]["size"] and heads["krea2"] is None      # the all-missing symbol: two or more

    fake_gate = threading.Event()
    log = []

    def fake_download(url, dest, size=0, sha256="", progress=None, cancel=None, **kw):
        log.append(Path(dest).name)
        progress(10, size or 100, "downloading")
        fake_gate.wait(10)
        if cancel is not None and cancel():
            raise downloads.Cancelled("Cancelled.")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"x")
        progress(size or 100, size or 100, "verifying")
        return Path(dest)

    real, ui_downloads.downloads.download = ui_downloads.downloads.download, fake_download
    opened = []
    ui_downloads.webbrowser.open = lambda u: opened.append(u)
    try:
        # a refused OK starts nothing
        t.mb.askokcancel = lambda *a, **k: False
        app.download_file(SMALL)
        assert app._dl == {} and log == []
        t.mb.askokcancel = lambda *a, **k: True

        # a gated file opens its page; nothing is loaded
        app.download_file(GATED)
        assert opened == [manifest.FILES[GATED].url] and app._dl == {}

        # one file: starts at once, shown as loading, the target is the sub-folder of its kind
        app.download_file(SMALL)
        assert list(app._dl) == [SMALL] and app._dl[SMALL]["target"] == mdir / "vae_approx" / SMALL
        drain(app, until=lambda: app._dl[SMALL]["done"] > 0)
        info = app._dl_info(SMALL)
        assert info["state"] == "loading" and info["done"] == 10
        assert [d for d in ts.file_rows(app) if d["name"] == SMALL][0]["dl"]["state"] == "loading"
        fake_gate.set()
        drain(app, until=lambda: SMALL not in app._dl)
        assert (mdir / "vae_approx" / SMALL).read_bytes() == b"x" and SMALL in app._dl_restart
        assert "restart ComfyUI" in app.v_status.get()
        assert [d for d in ts.file_rows(app) if d["name"] == SMALL][0]["restart"] is True
        app.download_file(SMALL)                                                    # it is there now: nothing again
        assert app._dl == {} and "already in" in app.v_status.get()

        # all missing of a model: every file loads at the same time; one can be stopped while the other goes on
        fake_gate.clear()
        log.clear()
        missing = [f.name for f, found, _lv in next(r for r in app.inv.rows() if r["key"] == "moss")["files"]
                   if found is None and f.url and not ui_downloads.browser_only(f)]
        assert len(missing) >= 2, missing
        app.download_missing("moss")
        assert set(app._dl) == set(missing)
        drain(app, until=lambda: all(app._dl[n]["done"] > 0 for n in missing))
        assert sorted(log) == sorted(missing) and all(app._dl_info(n)["state"] == "loading" for n in missing)
        app.download_cancel(missing[0])
        fake_gate.set()
        drain(app, until=lambda: not app._dl)
        assert app._dl == {} and not (mdir / "vae" / missing[0]).exists()
        done = [n for n in missing if any(mdir.rglob(Path(n.replace("\\", "/")).name))]
        assert len(done) == len(missing) - 1 and missing[0] not in done, (done, missing)
        # "all missing" does not forget the files that need a website: they are named in the OK window and open in the browser
        rows = {d["name"]: d for d in ts.file_rows(app)}
        assert rows[ULTRA]["browser"] and rows[ULTRA]["hint"].startswith("The disk symbol opens civitai.com") and "civitai.com" in rows[ULTRA]["hint"]
        assert "models" + chr(92) + "loras" + chr(92) + "Flux 2" in rows[ULTRA]["hint"] and "licence" in rows[UPS]["hint"]
        head = next(r for r in app._settings_rows() if r[0] == "model" and r[1] == "flux2")
        assert head[5]["count"] == 1 and head[5]["site"] == 1      # the whole package, optional files too (user 3.11.): the same files the download below opens; Flux 2's Sketch writes with qwen3vl 4B since 10.11. (no gated upsampler)
        asked = []
        t.mb.askokcancel = lambda title, msg, **k: asked.append(msg) or True
        opened.clear()
        fake_gate.set()
        app.download_missing("flux2")
        assert opened == [manifest.FILES[ULTRA].url], opened
        assert "open in your browser" in asked[0] and ULTRA in asked[0] and "flux2-vae.safetensors" in asked[0]
        drain(app, until=lambda: not app._dl)
        assert (mdir / "vae" / "flux2-vae.safetensors").exists()

        # the tabs: rows split per model, the functions each model covers
        top, per, extra = app._settings_sections(app._settings_rows())
        assert [r[0] for r in top] == ["links", "intro"] and set(per) == {m.key for m in ts.models.MODELS}
        assert per["krea2"][0][0] == "model" and per["krea2"][1][0] == "enable" and per["krea2"][2][0] == "sep" and per["krea2"][3][0] == "modes"
        assert extra[0][0] == "head" and all(r[0] in ("head", "file", "stop") for r in extra)
        cover = {m: st for m, _l, st, _tip in app._mode_cover("krea2")}
        assert cover["txt2img"] == "ready" and cover["inpaint"] == "none" and "img2img" not in cover
        qc = {m: st for m, _l, st, _t in app._mode_cover("qwen")}
        assert {st for m, st in qc.items() if m not in ("sketch", "scribble")} <= {"ready", "none"} and "ready" in qc.values()
        assert qc["sketch"] == qc["scribble"] == "ready"        # no upsampler in this ComfyUI: Qwen writes with its own w4a8 since 16.11. evening
        app._settings_close()
        app.open_settings(focus="moss")
        assert app._settings_focus == "moss" and set(app._set_pages) == {m.key for m in ts.models.MODELS} | {"additional"}
        check_button(app, mdir)
    finally:
        ui_downloads.downloads.download = real
        del os.environ["PCCOMFY_MODELS_DIR"]
    app._settings_close()
    print("ok")


def drain_check(app, until, limit=400):
    for _ in range(limit):
        if until():
            return
        try:
            kind, data = app.events.get(timeout=5)
        except Exception:
            return
        if kind == "filecheck":
            app._check_event(data)


def check_button(app, mdir):
    """"Check files" (user 17.11.): runs in a thread, reads the files on the disk against models.json, never deletes one."""
    import dataclasses
    import hashlib
    small = manifest.FILES[SMALL]
    target = mdir / "vae_approx" / SMALL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"y" * small.size)                     # the right size, the wrong content: damaged
    assert app.b_check.cget("text") == "Check files"
    app.check_files()
    assert app._check is not None and app.b_check.cget("text") == "Stop checking"
    drain_check(app, until=lambda: app._check is None)
    res = {r["name"]: r for r in app._check_result}
    assert set(res) == set(manifest.FILES), "every file of models.json is listed"
    assert res[SMALL]["state"] == "damaged" and target.exists() and target.stat().st_size == small.size      # not deleted
    assert res["flux2-vae.safetensors"]["state"] == "damaged"       # the fake download above wrote one byte: the size is wrong
    assert res["moss_image_sft_int8_convrot.safetensors"]["state"] == "missing"
    assert "damaged" in app.l_check.cget("text") and "missing" in app.l_check.cget("text") and app.b_check.cget("text") == "Check files"
    report = app.check_report(app._check_result)
    assert report.startswith(app.CHECK_DAMAGED_HINT) and "Delete it yourself" in report and str(target) in report
    assert report.index("damaged: " + SMALL) < report.index("missing: moss_image_sft_int8_convrot.safetensors")
    # the right content: ok
    real = manifest.FILES[SMALL]
    manifest.FILES[SMALL] = dataclasses.replace(real, sha256=hashlib.sha256(b"y" * small.size).hexdigest())
    try:
        app.check_files()
        drain_check(app, until=lambda: app._check is None)
        assert {r["name"]: r["state"] for r in app._check_result}[SMALL] == "ok"
    finally:
        manifest.FILES[SMALL] = real
    # a file ComfyUI lists under another name (linked with the chain symbol): not read, said so
    entries = {e["name"]: e for e in app._check_entries(mdir)}
    inv_real = app.inv
    lists = {k: list(v) for k, v in inv_real.lists.items()}
    lists["vae"] = [n for n in lists["vae"] if n != "flux2-vae_small.safetensors"] + ["my_own_vae.safetensors"]
    app.inv = inventory.Inventory(lists, NODES, {"flux2-vae_small.safetensors": "my_own_vae.safetensors"})
    try:
        e = {e["name"]: e for e in app._check_entries(mdir)}["flux2-vae_small.safetensors"]
        assert e["sha256"] == "" and "my_own_vae.safetensors" in e["note"] and "no checksum known" in e["note"]
    finally:
        app.inv = inv_real
    assert entries[SMALL]["path"] == target
    # Stop: a slow read is stopped by a second click
    gate = threading.Event()
    real_check = ui_downloads.downloads.check_files

    def slow(entries, progress=None, cancel=None):
        progress(1, 10, SMALL)
        gate.wait(5)
        if cancel():
            raise downloads.Cancelled("Cancelled.")
        return []
    ui_downloads.downloads.check_files = slow
    try:
        app.check_files()
        drain_check(app, until=lambda: "%" in app.l_check.cget("text"))
        assert app.l_check.cget("text").startswith("10 %") and SMALL in app.l_check.cget("text")
        app.check_files()                     # the second click stops it
        gate.set()
        drain_check(app, until=lambda: app._check is None)
        assert app.l_check.cget("text") == "Check stopped." and app.b_check.cget("text") == "Check files"
    finally:
        ui_downloads.downloads.check_files = real_check


if __name__ == "__main__":
    main()
