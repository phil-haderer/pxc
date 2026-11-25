# tags: queue, undo
"""Generate while a run is on (docs/plan/generate-queue.md, step 1: Refine, Upscale, Edit; step 2: Text to image (canvas
size only); decisions 22.11.; since 23.11. evening (choice D) only these four and only behind the same function, Multi
Edit, Sketch and Scribble never queue): the queue's
kind "generate" (jobqueue: the picture of the document in front taken at the click, ×n = n jobs with their own seeds and run
numbers, results as layers without a history snapshot, the "batch-placed" event, Stop batch for queued clicks), the
bridge's layer step (Bridge.set_result_visible: hide, show, already, gone, closed) and the window's Undo / Redo stacks
(result layers hidden and shown again, the snapshot of a run as before, the order of both, what may run while the queue
works). Against the fake ComfyUI of test_jobqueue.py (a free port, never 8188) and the PhotoCraft simulator of
test_reference_mode.py; the window part with a hidden real Tk window and faked bridge and runner.

    python tests/test_generate_queue.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_jobqueue as Q  # noqa: E402  (sets PCCOMFY_HOME before pccomfy is imported)

from PIL import Image  # noqa: E402

from pccomfy import history as runhistory, jobqueue as JQ, workflows  # noqa: E402
from pccomfy.bridge import Bridge, BridgeError, Request  # noqa: E402
import test_reference_mode as T  # noqa: E402

RED = (200, 30, 30, 255)


def gen_spec(req, copies=1, label="Refine · Flux 3"):
    return JQ.BatchSpec(request=req, source=JQ.SOURCE_ACTIVE, dry_run=False, kind=JQ.K_GENERATE, copies=copies,
                        label=label, model="Flux 3")


def refine(seed=-1, run_no=0):
    req = Q.refine_request()
    req.params.seed = seed
    if run_no:
        req.preset, req.run_no, req.group_name = "Flux 3 Klein Refine", run_no, f"Refine {run_no}"
    return req


# ---------- the queue ----------

def test_queued_generate_layers_and_seeds():
    srv, fake = Q.server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = Q.two_docs(tmp)
        pc.active = 1                                   # "second.png" is in front when Generate is clicked
        gate = {"open": False}                          # the window's own run is on: no job starts yet
        r, got, b = Q.runner(url, pc=pc, tmp=tmp, gate=lambda: gate["open"])
        b.last_vgl = "the run that is on wrote this"
        bid = r.start_batch(gen_spec(refine(seed=5, run_no=7), copies=2))
        assert b.last_vgl == "the run that is on wrote this", "queuing must not clear what the run that is on keeps"
        Q.wait_until(lambda: len(r.jobs(bid)) == 2, what="the two jobs of ×2")
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.WAITING, JQ.WAITING]
        assert [j["source"]["kind"] for j in jobs] == [JQ.SOURCE_ACTIVE] * 2 and jobs[0]["source"]["name"] == "second.png"
        # the picture is the one of the click: a change afterwards does not reach the job
        with Image.open(jobs[0]["input_png"]) as im:
            before = im.convert("RGB").getpixel((5, 5))
        pc.docs[1].layers[0]["img"] = Image.new("RGBA", (T.W, T.H), (0, 255, 0, 255))
        assert [j["seed"] for j in jobs] == [5, (5 + 7919) % 2**31], "each copy its own seed, as with variants"
        assert [(j["run_no"], j["group"]) for j in jobs] == [(7, "Refine 7"), (8, "Refine 8")]
        assert r.batch(bid)["kind"] == JQ.K_GENERATE and r.batch(bid)["label"] == "Refine · Flux 3" and not r.batch(bid)["dry_run"]
        assert r.busy and r.only_generate
        snaps = sum(1 for c, _ in pc.log if c == "history.newSnapshot")
        gate["open"] = True
        r._kick()
        Q.wait_until(lambda: any(k == "batch-done" for k, _ in got), what="the queued Generate")
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.DONE, JQ.DONE] and [j["placed"] for j in jobs] == ["layer", "layer"], jobs
        assert sum(1 for c, _ in pc.log if c == "history.newSnapshot") == snaps, "a queued Generate takes no snapshot"
        assert not b.batch_undo_docs()
        placed = [d for k, d in got if k == "batch-placed"]
        assert [d["doc"] for d in placed] == ["second.png", "second.png"] and [d["name"] for d in placed] == \
            ["Flux 3 Klein Refine #7", "Flux 3 Klein Refine #8"], placed
        ids = {l["id"] for l in pc.docs[1].layers}
        assert all(d["layer"] in ids for d in placed) and len(pc.docs[1].layers) == 3
        assert all(d["batch"] == bid for d in placed)
        # every payload counts as Generate in the queue windows (no pcc_batch), with the seeds of the jobs
        for pl in fake.payloads:
            assert "pcc_batch" not in (pl.get("extra_data") or {}), pl.get("extra_data")
        assert before == (90, 20, 20)
        assert not r.busy
        # Upscale: a new document, no layer event
        got.clear()
        req = Request(mode="upscale", workflow=str(Q.WF / "flux3-klein-upscale.json"), scale=2.0)
        req.params = workflows.GenParams(prompt="", seed=3)
        r.start_batch(gen_spec(req))
        Q.wait_until(lambda: any(k == "batch-done" for k, _ in got), what="queued upscale")
        assert not [d for k, d in got if k == "batch-placed"] and len(pc.docs) == 3
        # Fill, Remove, Expand can't wait in the queue; a batch source is refused for it
        for bad in ("inpaint", "outpaint", "remove"):
            x = Request(mode=bad)
            x.params = workflows.GenParams(prompt="a cat")
            try:
                r.start_batch(gen_spec(x))
            except ValueError as e:
                assert "can wait in the queue" in str(e), e
            else:
                raise AssertionError(bad)
        try:
            r.start_batch(JQ.BatchSpec(refine(), JQ.SOURCE_OPEN, kind=JQ.K_GENERATE))
        except ValueError:
            pass
        else:
            raise AssertionError("a queued Generate takes the document in front only")
    finally:
        srv.shutdown()
        srv.server_close()


def test_queued_text_to_image():
    """Step 2: Text to image takes only the canvas size at the click (no export, nothing stored) and comes back as layers
    without a snapshot."""
    srv, fake = Q.server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = Q.two_docs(tmp)
        pc.active = 1
        gate = {"open": False}
        r, got, b = Q.runner(url, pc=pc, tmp=tmp, gate=lambda: gate["open"])
        exports = []
        real_export = b._export
        b._export = lambda *a, **kw: exports.append(a) or real_export(*a, **kw)
        t2i = Request(mode="txt2img", workflow=str(Q.WF / "flux3-klein-t2i.json"))
        t2i.params = workflows.GenParams(prompt="a lighthouse at dusk", seed=11)
        t2i.preset, t2i.run_no, t2i.group_name = "Flux 3 Klein Text", 2, "Text 2"
        bid = r.start_batch(gen_spec(t2i, copies=2, label="Text · Flux 3"))
        Q.wait_until(lambda: len(r.jobs(bid)) == 2, what="the two Text to image jobs")
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.WAITING] * 2, jobs
        assert all(j["input_png"] == "" for j in jobs), "Text to image stores no picture"
        assert jobs[0]["source"]["size"] == [T.W, T.H] and jobs[0]["source"]["name"] == "second.png"
        assert jobs[0]["mp"] > 0, "the time estimate needs the result's size"
        assert not exports, "Text to image exports nothing from PhotoCraft"
        assert [j["seed"] for j in jobs] == [11, (11 + 7919) % 2**31]
        assert r.open_modes() == {"txt2img"}, "Generate may only queue Text to image behind it (choice D)"
        snaps = sum(1 for c, _ in pc.log if c == "history.newSnapshot")
        gate["open"] = True
        r._kick()
        Q.wait_until(lambda: r.batch(bid)["state"] == JQ.B_DONE, what="Text to image")
        assert r.open_modes() == set()
        for j in r.jobs(bid):
            assert j["status"] == JQ.DONE and j["placed"] == "layer", j
        assert sum(1 for c, _ in pc.log if c == "history.newSnapshot") == snaps, "no snapshot"
        placed = [d for k, d in got if k == "batch-placed"]
        assert [d["batch"] for d in placed] == [bid, bid], placed
        assert [d["name"] for d in placed][:2] == ["Flux 3 Klein Text #2", "Flux 3 Klein Text #3"]
        assert len(pc.docs[1].layers) == 3
        prompts = [str(pl) for pl in fake.payloads]
        assert sum("a lighthouse at dusk" in x for x in prompts) == 2
        # a failed Text to image job can be sent again (it needs no stored picture)
        jid = r.jobs(bid)[0]["id"]
        with r._lock:
            r._set(r._job(jid), status=JQ.ERROR, error="ComfyUI was gone")
        assert r.retry(jid)
    finally:
        srv.shutdown()
        srv.server_close()


def test_only_four_functions_queue():
    """User 23.11. evening (choice D): Multi Edit (reference images), Sketch, Scribble (a scribble) and Insert reference
    (BBOX) never wait in the queue; start_batch refuses them before anything is collected."""
    tmp = tempfile.mkdtemp()
    pc = Q.two_docs(tmp)
    r, got, b = Q.runner("http://127.0.0.1:9", pc=pc, tmp=tmp, gate=lambda: False)
    edit = str(Q.WF / "flux3-klein-edit.json")
    for kw in ({"refs": [Image.new("RGB", (8, 8))]}, {"scribble": True}, {"bbox": True}):
        req = Request(mode="edit", workflow=edit, **kw)
        req.params = workflows.GenParams(prompt="a red car", seed=1)
        try:
            r.start_batch(gen_spec(req, label="Edit · Flux 3"))
        except ValueError as e:
            assert "can wait in the queue" in str(e), e
        else:
            raise AssertionError(f"queued: {kw}")
    assert not r.batches() and r.open_modes() == set()
    assert JQ.copy_request(Request(mode="edit", scribble=True, scribble_object=True)).scribble is False


def test_variants_take_the_run_picture():
    """×n of a direct run (window test 23.11. evening: a pause before both started): the queued variants wait for the
    picture the run exports and take it, no second export from PhotoCraft; without it (the run failed first) they
    export their own."""
    import threading
    srv, fake = Q.server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = Q.two_docs(tmp)
        pc.active = 1
        r, got, b = Q.runner(url, pc=pc, tmp=tmp, gate=lambda: False)
        exports = []
        real_export = b._export
        b._export = lambda *a, **kw: exports.append(a) or real_export(*a, **kw)
        shared = {"done": threading.Event(), "pic": None, "index": None, "name": ""}
        spec = gen_spec(refine(), copies=2)
        spec.shared = shared
        bid = r.start_batch(spec)
        time.sleep(0.6)
        assert not r.jobs(bid) and not exports, "the variants wait for the run's picture"
        shared.update(pic=Image.new("RGB", (T.W, T.H), (1, 2, 3)), index=1, name="second.png")
        shared["done"].set()
        Q.wait_until(lambda: len(r.jobs(bid)) == 2, what="the two variants")
        assert not exports, "no second export"
        j = r.jobs(bid)[0]
        assert j["source"]["name"] == "second.png" and j["source"]["size"] == [T.W, T.H], j["source"]
        with Image.open(j["input_png"]) as im:
            assert im.convert("RGB").getpixel((1, 1)) == (1, 2, 3)
        shared2 = {"done": threading.Event(), "pic": None, "index": None, "name": ""}
        shared2["done"].set()
        spec2 = gen_spec(refine(), copies=1)
        spec2.shared = shared2
        bid2 = r.start_batch(spec2)
        Q.wait_until(lambda: len(r.jobs(bid2)) == 1, what="the variant without the run's picture")
        assert exports, "it exported its own"
        r.cancel_batch(bid)
        r.cancel_batch(bid2)
    finally:
        srv.shutdown()
        srv.server_close()


def test_cancel_one_generate_leaves_the_others():
    srv, fake = Q.server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = Q.two_docs(tmp)
        r, got, b = Q.runner(url, pc=pc, tmp=tmp, gate=lambda: False)
        folder = Q.pictures(Path(tmp) / "in", ["a.png", "b.png"])
        batch = r.start_batch(JQ.BatchSpec(refine(), JQ.SOURCE_FOLDER, folder=str(folder), dry_run=False,
                                           save_settings=Q.settings(tmp)))
        gen = r.start_batch(gen_spec(refine(), copies=3))
        gen2 = r.start_batch(gen_spec(refine(), copies=2))
        Q.wait_until(lambda: len(r.jobs(gen)) == 3 and len(r.jobs(gen2)) == 2 and len(r.jobs(batch)) == 2,
                     what="all prepared")
        assert not r.only_generate, "a batch of the ⋯ menu is on"
        assert r.cancel_batch(gen)              # Stop batch: one batch only (user 23.11. evening)
        assert [j["status"] for j in r.jobs(gen)] == [JQ.CANCELLED] * 3
        assert [j["status"] for j in r.jobs(gen2)] == [JQ.WAITING] * 2
        assert [j["status"] for j in r.jobs(batch)] == [JQ.WAITING] * 2
        r.cancel_batch(gen2)
        r.cancel_batch(batch)
    finally:
        srv.shutdown()
        srv.server_close()


def test_no_document():
    tmp = tempfile.mkdtemp()
    pc, _, _b = T.make(tmp, with_sel=False, layers=1)
    pc.active = None
    pc.session = lambda: {"active": None, "documents": []}
    r, got, b = Q.runner("http://127.0.0.1:1", pc=pc, tmp=tmp, gate=lambda: False)
    bid = r.start_batch(gen_spec(refine()))
    Q.wait_until(lambda: any(k == "batch-done" for k, _ in got), what="the job without a document ends")
    j = r.jobs(bid)[0]
    assert j["status"] == JQ.ERROR and "Open a document" in j["error"], j


# ---------- the bridge's layer step ----------

def test_set_result_visible():
    tmp = tempfile.mkdtemp()
    pc, _, b = T.make(tmp, with_sel=False, layers=3)
    entry = {"doc": "scene.png", "layer": 3, "name": "Flux 3 #1"}
    assert b.set_result_visible(entry, False) == "ok" and pc.docs[0].layers[2]["visible"] is False
    assert b.set_result_visible(entry, False) == "already"
    assert b.set_result_visible(entry, True) == "ok" and pc.docs[0].layers[2]["visible"] is True   # (hideLayers toggles here)
    assert b.set_result_visible(dict(entry, layer=99), False) == "gone"
    assert b.set_result_visible(dict(entry, doc="closed.png"), False) == "closed"
    # a layer inside a group counts too
    pc.docs[0].layers[1] = {"id": 40, "name": "Group", "visible": True, "members": [pc.docs[0].layers[1]]}
    assert b.set_result_visible({"doc": "scene.png", "layer": 40}, False) == "ok"
    assert b.set_result_visible({"doc": "scene.png", "layer": 2}, False) in ("ok", "already")
    # PhotoCraft that does neither: an error, not a silent "ok"
    real = pc.execute
    pc.execute = lambda cmd, params=None: {} if cmd.startswith("layer.") and "Layers" in cmd else real(cmd, params)
    try:
        b.set_result_visible(entry, False)
    except BridgeError as e:
        assert "did not hide" in str(e)
    else:
        raise AssertionError("no error")
    finally:
        pc.execute = real
    assert Bridge._layer_states([{"id": 1, "visible": False, "children": [{"id": 2, "visible": True}]}]) == {1: False, 2: True}
    # a direct Scribble on photo: Undo shows its (hidden) scribble layer again, Redo hides it
    pc2, _, b2 = T.make(tempfile.mkdtemp(), with_sel=False, layers=3)
    pc2.docs[0].layers[1]["visible"] = False
    entry = {"doc": "scene.png", "layer": 3, "name": "Flux 2 #1", "scribble": 2}
    assert b2.set_result_visible(entry, False) == "ok"
    assert pc2.docs[0].layers[1]["visible"] is True and pc2.docs[0].layers[2]["visible"] is False
    assert b2.set_result_visible(entry, True) == "ok"
    assert pc2.docs[0].layers[1]["visible"] is False and pc2.docs[0].layers[2]["visible"] is True


# ---------- the window: Undo / Redo stacks ----------

def window_tests():
    try:
        import tkinter
        tkinter.Tk().destroy()
    except Exception as e:
        print(f"(window part skipped: no Tk window: {e})")
        return
    from pccomfy import config as cfgmod, gui
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    before_app = set(threading.enumerate())
    app = gui.App(cfg)
    app.root.withdraw()
    # the first refresh (a thread, started by root.after(200) in App) reports the missing PhotoCraft into the status line;
    # it came late and overwrote the Undo texts below: red on every GitHub machine (24.11.), because waiting for running
    # "(work)" threads stopped at once when the 200 ms timer had not started the thread yet. Wait for both of its answers
    # itself: the connections (with the error text) and ui_settings' reading of the installed files ("_detect").
    refreshed = set()
    real_apply = app._apply_refresh
    app._apply_refresh = lambda info: (refreshed.add("detect" if info.get("_detect") else "conn"), real_apply(info))[1]
    end = time.monotonic() + 20.0
    while time.monotonic() < end and not (refreshed == {"conn", "detect"} and not any(
            th.is_alive() and th.name.endswith("(work)") for th in set(threading.enumerate()) - before_app)):
        app._poll()
        app.root.update()
        time.sleep(0.02)
    assert refreshed == {"conn", "detect"}, f"the first refresh did not answer: {refreshed}"
    app._poll()

    def pump(until, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app._poll()
            app.root.update()
            if until() and not (app.worker and app.worker.is_alive()):
                return True
            time.sleep(0.02)
        return False

    def states():
        return str(app.b_undo.cget("state")), str(app.b_redo.cget("state"))

    b = app.bridge
    snap = {"undo": True, "redo": False}
    calls = []
    b.can_undo = lambda *a: snap["undo"]
    b.can_redo = lambda: snap["redo"]
    answers = {}
    b.set_result_visible = lambda e, vis: calls.append((e["layer"], vis)) or answers.get(e["layer"], "ok")
    b.undo_last = lambda: calls.append("undo-snap") or "Back to the state before the last AI edit."
    b.redo_last = lambda: calls.append("redo-snap") or "Redone."

    class Runner:
        busy, only_generate, running_job = False, True, None

        def jobs(self, *a):
            return []

        def batches(self):
            return []

        def open_modes(self):
            return set(open_modes)

        def batch(self, bid):
            return {"id": bid, "kind": JQ.K_GENERATE, "model": "Qwen Image 2.1", "label": "Refine · Qwen Image 2.1"}

        def recover(self):                  # App's start timer (1.5 s) calls it; on a slow machine after the swap
            pass
    open_modes = set()
    real_runner, app.runner = app.runner, Runner()
    app._batch_mine = {"g1"}

    # which functions may wait in the queue (user 23.11. evening, choice D): Refine, Upscale, Edit, Text to image, and
    # only behind the same function; Multi Edit, Sketch, Scribble, Fill, Remove, Expand never
    mode0 = app.v_mode.get()
    app._run_mode = lambda: {"multi_edit": "edit", "sketch": "edit", "scribble": "edit"}.get(app.v_mode.get(), app.v_mode.get())
    app._bbox_on = lambda: False
    for mode, ok in (("txt2img", True), ("multi_edit", False), ("refine", True), ("upscale", True), ("edit", True),
                     ("sketch", False), ("scribble", False), ("inpaint", False), ("remove", False), ("outpaint", False)):
        app.v_mode.set(mode)
        assert (app._queue_refusal() == "") == ok, (mode, app._queue_refusal())
    app.v_mode.set("sketch")
    assert app._queue_refusal() == gui.QUEUE_LOCKED.format(fn="Sketch to image")
    app.v_mode.set("img2img")
    assert app._queue_refusal() == gui.QUEUE_LOCKED.format(fn="Image → Image")
    # the same function only: Text to image runs (direct), Text to image may wait (any model), Edit may not
    real_running = getattr(app, "_running", False)
    app._running, app._run_wmode = True, "txt2img"
    app.v_mode.set("txt2img")
    assert app._queue_refusal() == ""
    app.v_mode.set("edit")
    assert app._queue_refusal() == gui.QUEUE_OTHER_FN.format(run="Text to Image"), app._queue_refusal()
    app._run_wmode = "multi_edit"           # a direct Multi Edit run: Edit may not wait behind it either
    assert app._queue_refusal() == gui.QUEUE_OTHER_FN.format(run="Multi image edit")
    app._running = real_running
    open_modes.add("refine")                # a batch or queued click of Refine waits
    assert app._queue_refusal() == gui.QUEUE_OTHER_FN.format(run="Refine Image")
    app.v_mode.set("refine")
    assert app._queue_refusal() == ""
    open_modes.clear()
    app.v_mode.set("multi_edit")
    app._bbox_on = lambda: True
    assert app._queue_refusal() == gui.QUEUE_NO_BBOX
    del app._run_mode, app._bbox_on
    app.v_mode.set(mode0)

    # a run of the window, then a queued result: Undo hides the layer first, then goes back to the snapshot
    app._undo_new_run("refine")
    app._batch_event("batch-placed", {"job": "j1", "batch": "g1", "doc": "pic.png", "layer": 11, "name": "Qwen #3"})
    app._batch_event("batch-placed", {"job": "x", "batch": "someone-else", "doc": "pic.png", "layer": 12, "name": "?"})
    assert [e["kind"] for e in app._undo_stack] == ["snap", "layers"] and app._undo_stack[1]["layer"] == 11
    assert "scribble" not in app._undo_stack[1]
    app._batch_event("batch-placed", {"job": "j0", "batch": "g1", "doc": "pic.png", "layer": 13, "name": "S", "scribble": 5})
    assert app._undo_stack.pop()["scribble"] == 5, "Scribble on photo: Undo shows its scribble layer again"
    app._sync_history_buttons()
    assert states() == ("normal", "disabled")
    app.undo_edit()
    assert pump(lambda: calls == [(11, False)])
    assert pump(lambda: app.v_status.get() == "Undo: “Qwen #3” is hidden."), app.v_status.get()
    assert states() == ("normal", "normal"), "more steps back and the hidden layer to bring back (choice B)"
    snap["redo"] = True
    app.undo_edit()
    assert pump(lambda: calls[-1] == "undo-snap")
    assert app._undo_stack == [] and [e["kind"] for e in app._redo_stack] == ["layers", "snap"]
    assert states() == ("disabled", "normal")
    app.redo_edit()
    assert pump(lambda: calls[-1] == "redo-snap")
    app.redo_edit()
    assert pump(lambda: calls[-1] == (11, True))
    assert pump(lambda: app.v_status.get() == "Redo: “Qwen #3” is visible again."), app.v_status.get()  # set after the call
    assert [e["kind"] for e in app._undo_stack] == ["snap", "layers"] and app._redo_stack == []
    assert states() == ("normal", "disabled")

    # while queued Generate clicks run: both grey, a click (or key) does nothing and says why (user 24.11.: "am besten
    # sperren wir redo/undo während eines laufs komplett"; until then a layer step could go)
    app.runner.busy = True
    app._sync_history_buttons()
    assert states() == ("disabled", "disabled")
    n = len(calls)
    app.undo_edit()
    app.redo_edit()
    assert len(calls) == n and app.v_status.get() == gui.CUT_NOT_IN_RUN, app.v_status.get()
    app.runner.only_generate = False              # a batch of the ⋯ menu: both grey too
    app._sync_history_buttons()
    assert states() == ("disabled", "disabled")
    app.runner.busy, app.runner.only_generate = False, True
    app._running = True                           # a direct run of the window: the same
    app._sync_history_buttons()
    assert states() == ("disabled", "disabled")
    app.undo_edit()
    assert len(calls) == n
    app._running = False
    app._sync_history_buttons()
    assert states() == ("normal", "disabled")
    app.undo_edit()
    assert pump(lambda: calls[-1] == (11, False))
    assert states() == ("normal", "normal")
    # an Upscale run that ends leaves Undo and Redo as they were (user 24.11.: "upscale sollte aus redo/undo ausgenommen
    # werden"): no snapshot step, the steps of before and the redo stay, the blue one too
    u0, r0, last0 = [dict(e) for e in app._undo_stack], [dict(e) for e in app._redo_stack], app._last_step
    app._running, app._run_req_mode, app._run_placed = True, "upscale", None
    app.events.put(("done", "Done · seed 1 · 1 document · 3 s"))
    app._poll()
    assert not app._running and app._undo_stack == u0 and app._redo_stack == r0 and app._last_step == last0, (
        app._undo_stack, app._redo_stack, app._last_step)
    assert states() == ("normal", "normal")
    app._run_req_mode = ""

    # a result layer deleted by hand: Undo says so and drops it; one hidden by hand: nothing changed
    app._undo_stack[:] = [{"kind": "layers", "doc": "pic.png", "layer": 21, "name": "Flux #1"},
                          {"kind": "layers", "doc": "pic.png", "layer": 22, "name": "Flux #2"}]
    app._redo_stack[:] = []
    answers.update({22: "gone", 21: "already"})
    app.undo_edit()
    assert pump(lambda: calls[-1] == (22, False))
    assert pump(lambda: "is no longer in “pic.png” (deleted or merged)" in app.v_status.get()), app.v_status.get()
    assert app._status_error
    assert [e["layer"] for e in app._undo_stack] == [21] and app._redo_stack == []
    app.undo_edit()
    assert pump(lambda: calls[-1] == (21, False))
    assert pump(lambda: app.v_status.get() == "“Flux #1” was hidden already: nothing changed."), app.v_status.get()
    assert app._undo_stack == []

    # a new queued result after a snapshot Undo ends the snapshot's redo (it would drop the new layer)
    app._undo_new_run("edit")
    snap["redo"] = True
    app.undo_edit()
    assert pump(lambda: calls[-1] == "undo-snap")
    assert app._last_step == "undo"
    app._batch_event("batch-placed", {"job": "j2", "batch": "g1", "doc": "pic.png", "layer": 31, "name": "Qwen #4"})
    assert app._redo_stack == [] and app._last_step == "stale"
    app._sync_history_buttons()
    assert states() == ("normal", "disabled")
    app.undo_edit()
    assert pump(lambda: calls[-1] == (31, False))
    assert states() == ("disabled", "normal"), "the snapshot was taken back already: no second step back to it"
    # a direct run of a function that can wait in the queue: Undo hides its result layer, no snapshot step (user 23.11.:
    # Undo deleted the layers)
    app._undo_stack[:] = []
    app._undo_new_run("edit", {"doc": "pic.png", "layer": 41, "name": "Flux #2", "scribble": 7})
    assert app._undo_stack == [{"kind": "layers", "doc": "pic.png", "layer": 41, "name": "Flux #2", "scribble": 7}], app._undo_stack
    app.undo_edit()
    assert pump(lambda: calls[-1] == (41, False)) and app._redo_stack and app._redo_stack[-1]["layer"] == 41
    # Fill and Remove hide their layer too (user 23.11. late: Undo after Remove deleted it); Expand keeps the snapshot
    app._undo_new_run("inpaint", {"doc": "pic.png", "layer": 42, "name": "Qwen #3"})
    assert app._undo_stack[-1] == {"kind": "layers", "doc": "pic.png", "layer": 42, "name": "Qwen #3"} and app._redo_stack == []
    app._undo_new_run("remove", {"doc": "pic.png", "layer": 43, "name": "Qwen #4"})
    assert app._undo_stack[-1]["layer"] == 43 and len(app._undo_stack) == 2, app._undo_stack
    app._undo_new_run("outpaint", {"doc": "pic.png", "layer": 44, "name": "Qwen #5"})
    assert app._undo_stack[-1] == {"kind": "snap"}, "Expand changes the canvas: the snapshot step"
    app._undo_stack[:] = []
    app._undo_new_run("txt2img", {"doc": "pic.png", "layer": None})
    assert app._undo_stack == [{"kind": "snap"}], "no layer reported: the snapshot as before"
    # Upscale takes no snapshot: only the redo chain ends
    app._undo_stack[:] = [{"kind": "snap"}]
    app._undo_new_run("upscale")
    assert app._undo_stack == [] and app._redo_stack == []

    # the bar names the queued job's model; its history entry carries the prompt its writer wrote
    app._batch_event("queue-job", {"id": "j9", "batch_id": "g1", "status": JQ.RUNNING, "source": {}})
    assert app._queue_label == "Qwen Image 2.1" and "Qwen Image 2.1 is generating" == app._generating_word()
    app._queued_hist = {"g1": runhistory.entry("Refine 3", "Qwen Image 2.1", {"prompt": "old"}, llm="")}
    before = len(runhistory.load(gui.cfgmod.HISTORY_FILE))
    done = {"id": "j9", "batch_id": "g1", "status": JQ.DONE, "group": "Refine 4", "written": "a written prompt", "source": {}}
    app._batch_event("queue-job", done)
    app._batch_event("queue-job", done)          # once per job
    runs = runhistory.load(gui.cfgmod.HISTORY_FILE)
    assert len(runs) == before + 1 and runs[0]["title"] == "Refine 4" and runs[0]["llm"] == "a written prompt", runs[0]
    # its end on the bar and in the status line
    app._batch_event("batch-done", {"id": "g1", "kind": JQ.K_GENERATE, "label": "Refine · Qwen Image 2.1", "state": "done",
                                    "total": 1, "progress": {"total": 1, "counts": {"done": 1}}})
    assert app.v_pl.get() == "Done" and app.v_pl_rest.get() == " · Refine · Qwen Image 2.1", (app.v_pl.get(), app.v_pl_rest.get())

    # ×n of a direct Generate (user 23.11., choice A): the first picture runs now, the other n - 1 wait in the queue as jobs
    # of their own (each with its ✕); the queue waits for the run (gate); Fill keeps one run with n pictures
    specs, ran = [], []
    app.runner.start_batch = lambda spec: specs.append((spec, app._direct_pending)) or "g7"
    b.run = lambda rq, progress=None: ran.append(rq.variants) or {"layers": [], "seed": 5}
    app._running, app.worker = False, None
    app._active_doc_name = lambda: "pic.png"           # no PhotoCraft here
    app.cb_workflow["values"] = [gui.BUILTIN] + sorted({w for m in gui.models.MODELS for w in m.workflows()})
    app.v_model.set("flux3")
    app.v_mode.set("edit")
    app._on_model()
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red car")
    app.v_variants.set(3)
    before_run = set(threading.enumerate())
    app.generate()
    assert pump(lambda: bool(ran)), (ran, app.v_status.get(), specs, app._something_runs())
    assert ran == [1], ran
    assert len(specs) == 1 and specs[0][0].copies == 2 and specs[0][0].kind == JQ.K_GENERATE, specs
    assert specs[0][1], "the queue waits until the direct run has started"
    assert not app._direct_pending
    assert app._run_rest_bid == "g7", "Stop batch ends the variants of this run with it (user 23.11. evening)"
    # the queue window counts this run as 1/3 and its two queued pictures as 2/3, 3/3 (window test 23.11. late)
    assert app._rest_of.get("g7") == 3 and app._run_fn.endswith(" · 1/3"), (app._rest_of, app._run_fn)
    shared = specs[0][0].shared         # the variants take the run's picture; this run (faked) exported none
    assert shared is not None and shared["done"].is_set() and shared["pic"] is None and b.on_taken is None
    assert app.v_status.get() in ("", gui.VARIANTS_QUEUED.format(n=2)) or "Done" in app.v_pl.get()
    assert gui.VARIANTS_QUEUED.format(n=1) == "The first picture runs now; 1 more in the queue."
    specs.clear(); ran.clear()
    app._queue_refusal = lambda: "can't wait"         # Fill, Remove, Expand: one run with all n pictures, as before
    req = app._request()
    assert req.variants == 3 and app._variants_rest(req) == 0
    del app._queue_refusal
    req = app._request()
    assert app._variants_rest(req) == 2
    req.variants = 1
    assert app._variants_rest(req) == 0
    app.v_variants.set(1)

    # the status line during a run (window test 23.11.: "Insert reference can't wait in the queue" was gone at once): the
    # first progress clears what was there before, once; a message written meanwhile stays; a step text of its own goes
    def tick(msg="", phase="image"):
        app.events.put(("progress", (0.3, msg, phase, 0.3, 2.0)))
        app._poll()
    # the threads of the run above may still write into the status line (PhotoCraft is not there): let them end first
    end = time.monotonic() + 5.0
    while time.monotonic() < end and any(th.is_alive() for th in set(threading.enumerate()) - before_run):
        app._poll()
        app.root.update()
        time.sleep(0.02)
    app._poll()
    app._status("Done (seed 4)")
    app._status_stale = True                # as at the start of a run
    tick()
    assert app.v_status.get() == "", app.v_status.get()
    app._status(gui.QUEUE_NO_BBOX)
    for _ in range(3):
        tick()
    assert app.v_status.get() == gui.QUEUE_NO_BBOX, app.v_status.get()
    tick("Comparison 2/3: context 64", "prepare")
    assert app.v_status.get().startswith("Comparison 2/3")
    tick()
    assert app.v_status.get() == ""
    app.runner = real_runner
    app.root.destroy()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t0 = time.monotonic()
        t()
        print(f"ok {t.__name__} ({time.monotonic() - t0:.1f} s)")
    window_tests()
    print("ok window part")
    print("ALL OK (generate queue)")


if __name__ == "__main__":
    main()
