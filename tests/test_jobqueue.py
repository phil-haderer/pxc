# tags: queue, comfy
"""The local batch queue (docs/plan/speichern-queue-batch.md, steps 3 and 4; pccomfy/jobqueue.py): persistence, atomic
writes, crash recovery, the retry policy, pause / resume / cancel / reorder, the dry run, the folder scan, output names that
never overwrite, one job at a time at ComfyUI, jobs of others ahead (/queue), the ETA. Against a small fake ComfyUI over
HTTP on a free port (never 8188) and the PhotoCraft simulator of test_reference_mode.py; data in a temp PCCOMFY_HOME.

    python tests/test_jobqueue.py
"""
import io
import dataclasses
import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="pcc-jobqueue-")
os.environ["PCCOMFY_HOME"] = HOME          # before pccomfy is imported: config.CONFIG_DIR is read once

from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from pccomfy import comfy as COMFY, config, jobqueue as JQ, savefile, workflows  # noqa: E402
from pccomfy.bridge import Bridge, BridgeError, Request  # noqa: E402
from pccomfy.comfy import ComfyError, ComfyUI  # noqa: E402
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator)

WF = ROOT / "workflows"
OUT_SIZE = (64, 48)
JQ.RETRY_DELAY_S = 0.0
JQ.OOM_RETRY_DELAY_S = 0.0
JQ.PLACE_GAP_S = 0.0
JQ.QUEUE_POLL_S = 0.1
JQ.GATE_POLL_S = 0.05             # T4 (docs/plan/tempo-und-struktur.md): the plugin's values stay
JQ.SNAPSHOT_POLL_S = 0.05
COMFY.HISTORY_POLL_S = 0.05


# ---------- a fake ComfyUI over HTTP ----------

class Fake:
    def __init__(self):
        self.lock = threading.Lock()
        self.payloads = []            # every POST /prompt body
        self.done = {}                # prompt id -> finished (history answers)
        self.inflight = set()         # queued, not yet reported finished
        self.max_inflight = 0
        self.fail_prompt = []         # codes to answer the next POST /prompt with (500, 400 ...), one per call
        self.hold = threading.Event()  # cleared: jobs stay "running" until it is set
        self.hold.set()
        self.foreign_running, self.foreign_pending = [], []   # [(number, prompt id, client id, owner)]
        self.deletes, self.interrupts = [], []
        self.n = 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    fake: Fake = None

    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode())

    def do_GET(self):
        f = self.fake
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            with f.lock:
                known = pid in f.done or pid in f.inflight
                finished = pid in f.done or (pid in f.inflight and f.hold.is_set())
                if finished:
                    f.inflight.discard(pid)
                    f.done[pid] = True
            if not known:
                self._json({})
            elif not finished:
                self._json({pid: {"status": {"completed": None}, "outputs": {}}})
            else:
                self._json({pid: {"status": {"completed": True, "status_str": "success"},
                                  "outputs": {"out": {"images": [{"filename": f"{pid}.png", "subfolder": "", "type": "output"}]}}}})
        elif self.path.startswith("/view?"):
            buf = io.BytesIO()
            Image.new("RGB", OUT_SIZE, (10, 200, 30)).save(buf, format="PNG")
            self._send(200, buf.getvalue(), "image/png")
        elif self.path == "/queue":
            with f.lock:
                ours = [[100 + i, pid, {}, {"client_id": "me"}, []] for i, pid in enumerate(sorted(f.inflight))]
                run = [[n, pid, {}, {"client_id": c, "pcc_owner": o}, []] for n, pid, c, o in f.foreign_running]
                pend = [[n, pid, {}, {"client_id": c, "pcc_owner": o}, []] for n, pid, c, o in f.foreign_pending]
            self._json({"queue_running": run, "queue_pending": pend + ours})
        elif self.path.startswith("/object_info/"):
            self._json({})
        else:
            self._send(404, b"{}")

    def do_POST(self):
        f = self.fake
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/upload/image":
            name = re.search(rb'name="image"; filename="([^"]+)"', body).group(1).decode()
            self._json({"name": name, "subfolder": "pccomfy", "type": "input"})
        elif self.path == "/prompt":
            with f.lock:
                code = f.fail_prompt.pop(0) if f.fail_prompt else 200
                if code == 200:
                    f.payloads.append(json.loads(body))
                    f.n += 1
                    pid = f"p{f.n}"
                    f.inflight.add(pid)
                    f.max_inflight = max(f.max_inflight, len(f.inflight))
            if code == 400:
                self._json({"error": {"message": "Prompt outputs failed validation"}, "node_errors": {}}, 400)
            elif code != 200:
                self._send(code, b"server trouble", "text/plain")
            else:
                self._json({"prompt_id": pid, "node_errors": {}})
        elif self.path == "/queue":
            with f.lock:
                f.deletes.append(json.loads(body))
                for pid in json.loads(body).get("delete", []):
                    f.inflight.discard(pid)
            self._json({})
        elif self.path == "/interrupt":
            with f.lock:
                f.interrupts.append(json.loads(body) if body else {})
            self._json({})
        else:
            self._json({})


def server():
    fake = Fake()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (Handler,), {"fake": fake}))
    assert srv.server_port != 8188
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()   # shutdown() waits one poll
    return srv, fake


class NoPhotoCraft:
    def __getattr__(self, name):
        raise AssertionError(f"a folder batch used PhotoCraft ({name})")


def wait_until(cond, timeout=30.0, what=""):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out: {what}")


def pictures(folder, names, size=(40, 30)):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        Image.new("RGB", size, (30 * i % 256, 90, 160)).save(folder / n)
    return folder


def refine_request(**kw):
    req = Request(mode="refine", workflow=str(WF / "flux3-klein-refine.json"), **kw)
    req.params = workflows.GenParams(prompt="", seed=-1)
    return req


def runner(url, pc=None, tmp=None, gate=None, events=None):
    tmp = tmp or tempfile.mkdtemp()
    b = Bridge(pc or NoPhotoCraft(), ComfyUI(url), tmp)
    store = JQ.JobStore(Path(tmp) / "queue.json", Path(tmp) / "queue")
    got = []
    r = JQ.QueueRunner(b, on_event=lambda k, d: got.append((k, d)), gate=gate, store=store, owner="phil", events=events)
    return r, got, b


def settings(tmp):
    return savefile.SaveSettings(Path(tmp) / "out", "png", savefile.DEFAULT_PATTERN)


# ---------- pieces without a runner ----------

def test_folder_scan():
    d = Path(tempfile.mkdtemp())
    pictures(d, ["a.png", "B.JPG", "c.jpeg", "d.webp", "e.gif", "g_upscaled.png", "h_Refined.jpg", "k_edited.webp"])
    (d / "f.txt").write_text("x")
    pictures(d / "sub", ["i.png"])
    (d / "dir.png").mkdir()
    got = [f.name for f in JQ.scan_folder(d)]
    assert got == ["a.png", "B.JPG", "c.jpeg", "d.webp"], got
    assert JQ.scan_folder(d / "missing") == []


def test_output_names():
    d = Path(tempfile.mkdtemp())
    st = savefile.SaveSettings(d, "png", savefile.DEFAULT_PATTERN)
    im = Image.new("RGB", (8, 8), "red")
    (d / "beach_upscaled.png").write_bytes(b"keep me")
    p1 = savefile.save_batch_result(im, "beach", "upscale", st)
    p2 = savefile.save_batch_result(im, "beach.jpg", "upscale", st)
    assert p1.name == "beach_upscaled (2).png" and p2.name == "beach_upscaled (3).png", (p1, p2)
    assert (d / "beach_upscaled.png").read_bytes() == b"keep me"
    assert savefile.save_batch_result(im, "x", "refine", st).name == "x_refined.png"
    assert savefile.save_batch_result(im, "x", "edit", savefile.SaveSettings(d, "jpg")).name == "x_edited.jpg"
    assert savefile.has_batch_suffix("a_UPSCALED") and not savefile.has_batch_suffix("upscaled_a")


def test_persistence_and_atomic_write():
    d = Path(tempfile.mkdtemp())
    st = JQ.JobStore(d / "queue.json", d / "queue")
    j = JQ.Job(id="j1", batch_id="b1", mode="upscale", order=3, status=JQ.RUNNING, owner="phil", client_id="c",
               source={"kind": "open", "name": "a.png", "index": 2, "size": [10, 20]}, prompt_id="p9", attempts=2,
               results=["x.png"], eta=12.5, mp=0.4)
    st.jobs.append(j)
    st.batches["b1"] = JQ.Batch(id="b1", mode="upscale", source="open", state=JQ.B_RUNNING, total=1)
    st.save()
    back = JQ.JobStore(d / "queue.json", d / "queue").load()
    assert back.jobs[0].to_dict() == j.to_dict() and back.batches["b1"].to_dict() == st.batches["b1"].to_dict()
    assert sorted(p.name for p in d.iterdir()) == ["queue.json"], list(d.iterdir())       # no temp file left
    # a write that breaks in the middle leaves the old file
    before = (d / "queue.json").read_text(encoding="utf-8")
    real = json.dump
    json.dump = lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    try:
        try:
            JQ.atomic_write_json(d / "queue.json", {"broken": True})
        except OSError:
            pass
    finally:
        json.dump = real
    assert (d / "queue.json").read_text(encoding="utf-8") == before
    assert sorted(p.name for p in d.iterdir()) == ["queue.json"]
    # an unreadable file = an empty queue, no crash
    (d / "queue.json").write_text("{half", encoding="utf-8")
    assert JQ.JobStore(d / "queue.json").load().jobs == []


def test_transient():
    assert JQ.is_transient(ComfyError("x", transient=True)) and not JQ.is_transient(ComfyError("x"))
    assert JQ.is_transient(ConnectionResetError()) and JQ.is_transient(TimeoutError())
    assert not JQ.is_transient(BridgeError("x")) and not JQ.is_transient(ValueError("x"))
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                     # nothing listens there now
    try:
        ComfyUI(f"http://127.0.0.1:{port}").queue({})
    except ComfyError as e:
        assert e.transient, e
    srv, fake = server()
    try:
        c = ComfyUI(f"http://127.0.0.1:{srv.server_port}")
        for code, transient in ((500, True), (503, True), (400, False)):
            fake.fail_prompt = [code]
            try:
                c.queue({"1": {}})
            except ComfyError as e:
                assert e.transient is transient, (code, e)
            else:
                raise AssertionError(code)
    finally:
        srv.shutdown()
        srv.server_close()


def test_eta_math():
    t = JQ.ImageTimings(Path(tempfile.mkdtemp()) / "image-timings.json")
    assert t.estimate("wf", 2.0) is None
    t.record("wf", 1.0, 10.0)
    t.record("wf", 3.0, 30.0)
    assert abs(t.estimate("wf", 2.0) - 20.0) < 1e-9
    for k in range(20):
        t.record("wf", 1.0, 5.0)
    assert len(json.loads(t.path.read_text())["wf"]) == JQ.TIMING_SAMPLES and abs(t.estimate("wf", 4.0) - 20.0) < 1e-9
    assert JQ.format_eta(None) == "" and JQ.format_eta(20) == "<1 min" and JQ.format_eta(240) == "~4 min"
    req = Request(mode="upscale", scale=2.0)
    assert abs(JQ.result_megapixels("upscale", (1000, 500), req) - 2.0) < 1e-9
    assert abs(JQ.result_megapixels("refine", (1000, 500), req) - 0.5) < 1e-9
    assert abs(JQ.result_megapixels("edit", (4000, 3000), Request(mode="edit", base_res=1024)) - 1024 ** 2 / 1e6) < 1e-9
    # batch ETA: waiting jobs' estimates plus what the running one still needs
    r, _, _ = runner("http://127.0.0.1:1")
    now = time.time()
    r.store.batches["b"] = JQ.Batch(id="b", mode="refine", source="folder", state=JQ.B_RUNNING, total=3)
    r.store.jobs += [JQ.Job(id="1", batch_id="b", mode="refine", status=JQ.RUNNING, eta=100.0, started=now - 40, order=1),
                     JQ.Job(id="2", batch_id="b", mode="refine", status=JQ.WAITING, eta=100.0, order=2),
                     JQ.Job(id="3", batch_id="b", mode="refine", status=JQ.DONE, eta=100.0, order=0)]
    eta = r.batch_eta("b")
    assert 159 <= eta <= 161, eta
    assert r.batch_hint("b") == "Batch 2 of 3 · ~3 min", r.batch_hint("b")
    r.store.jobs[1].eta = None          # no timing for it: the batch's own pace (done jobs) or unknown
    assert r.batch_eta("b") is None


def test_jobs_ahead():
    srv, fake = server()
    try:
        c = ComfyUI(f"http://127.0.0.1:{srv.server_port}")
        c.client_id = "me"
        fake.foreign_running = [(1, "f1", "other", "anna")]
        fake.foreign_pending = [(2, "f2", "other", "anna"), (3, "f3", "", "")]
        with fake.lock:
            fake.inflight.add("mine")
        entries = c.queue_entries()
        assert [e["prompt_id"] for e in entries] == ["f1", "f2", "f3", "mine"], entries
        assert entries[0]["running"] and entries[0]["owner"] == "anna" and entries[3]["client_id"] == "me"
        assert entries[0]["kind"] == "generate" and entries[2]["kind"] == "" and entries[0]["batch"] == ""   # "": not from PxC
        assert c.jobs_ahead("mine") == 3 and c.jobs_ahead("f2") == 1 and c.jobs_ahead("gone") == 0 and c.jobs_ahead(None) == 0
        # our own jobs ahead do not count
        fake.foreign_pending = [(2, "mine0", "me", "phil")] + fake.foreign_pending
        assert c.jobs_ahead("mine") == 3
    finally:
        srv.shutdown()
        srv.server_close()


def test_owner_in_extra_data():
    srv, fake = server()
    try:
        c = ComfyUI(f"http://127.0.0.1:{srv.server_port}")
        c.queue({"1": {}})                                     # Generate as always: no extra_data
        c.queue({"1": {}}, preview="taesd")
        seen = []
        with c.job_context(owner="phil", on_queued=lambda pid, g: seen.append(pid)):
            pid = c.queue({"1": {}})
        c.owner = "anna"
        c.queue({"1": {}}, preview="taesd")
        p = fake.payloads
        assert "extra_data" not in p[0] and p[1]["extra_data"] == {"preview_method": "taesd"}
        assert p[2]["extra_data"] == {"pcc_owner": "phil"} and seen == [pid] and c.last_prompt_id == "p4"
        assert p[3]["extra_data"] == {"preview_method": "taesd", "pcc_owner": "anna"}
        # a batch job carries its batch, so other PCs show the pictures of one batch as one group (18.11.)
        with c.job_context(owner="phil", batch="bb"):
            c.queue({"1": {}})
        assert fake.payloads[4]["extra_data"] == {"pcc_owner": "phil", "pcc_batch": "bb"}
        real_json = c._json
        c._json = lambda path, *a, **k: {"queue_running": [], "queue_pending": [
            [7, "q1", {}, {"client_id": "o", "pcc_owner": "ben", "pcc_batch": "bb"}, []]]}
        e = c.queue_entries()[0]
        assert (e["owner"], e["batch"], e["kind"], e["running"]) == ("ben", "bb", "batch", False), e
        assert (e["images"], e["variant"]) == (1, ""), e
        # Generate with variants: the number of pictures, or "variant k of n", goes along for every queue window (18.11.)
        c._json = real_json
        n = len(fake.payloads)
        with c.run_info(images=2):
            c.queue({"1": {}})
        with c.run_info(variant=(1, 3)):
            c.queue({"1": {}})
        with c.run_info(images=1):
            c.queue({"1": {}})
        assert fake.payloads[n]["extra_data"] == {"pcc_owner": "anna", "pcc_images": 2}, fake.payloads[n]
        assert fake.payloads[n + 1]["extra_data"] == {"pcc_owner": "anna", "pcc_variant": "1/3"}
        assert fake.payloads[n + 2]["extra_data"] == {"pcc_owner": "anna"}
        c._json = lambda path, *a, **k: {"queue_running": [], "queue_pending": [
            [8, "q2", {}, {"pcc_owner": "ben", "pcc_images": 2}, []], [9, "q3", {}, {"pcc_owner": "ben", "pcc_variant": "2/2"}, []]]}
        e2, e3 = c.queue_entries()
        assert (e2["images"], e2["variant"], e3["images"], e3["variant"]) == (2, "", 1, "2/2"), (e2, e3)
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- the runner against the fake ComfyUI ----------

def test_folder_batch_dry_run():
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.jpg", "c.webp", "c_refined.png"])
        r, got, b = runner(url, tmp=tmp)
        st = settings(tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=True, save_settings=st))
        wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run result")
        assert len(fake.payloads) == 1 and r.batch(bid)["state"] == JQ.B_CONFIRM and r.busy
        time.sleep(0.4)
        assert len(fake.payloads) == 1, "the rest must wait for confirm()"
        dry = next(d for k, d in got if k == "batch-dry")
        assert dry["job"]["status"] == JQ.DONE and dry["results"][0].endswith("a_refined.png") and dry["image"].size == (40, 30)
        assert r.confirm(bid) and not r.confirm(bid)
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch done")
        assert sorted(p.name for p in (Path(tmp) / "out").iterdir()) == ["a_refined.png", "b_refined.png", "c_refined.png"]
        assert fake.max_inflight == 1, "one job at a time at ComfyUI"
        assert all(p["extra_data"]["pcc_owner"] == "phil" and p["client_id"] == b.comfy.client_id for p in fake.payloads)
        assert all(p["extra_data"]["pcc_batch"] == bid for p in fake.payloads)
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.DONE] * 3 and all(j["prompt_id"] and j["out_node"] == "out" or j["out_node"] for j in jobs)
        assert all(not j["input_png"] for j in jobs) and not list((Path(tmp) / "queue").glob("*.png")), "inputs cleaned up"
        saved = json.loads((Path(tmp) / "queue.json").read_text(encoding="utf-8"))
        assert [j["status"] for j in saved["jobs"]] == [JQ.DONE] * 3
        assert r.batch(bid)["state"] == JQ.B_DONE and not r.busy
        assert (Path(tmp) / "image-timings.json").exists(), "image phase timed"
        kinds = {k for k, _ in got}
        assert {"queue-job", "batch-progress", "batch-step", "batch-dry", "batch-done"} <= kinds, kinds
        prog = [d for k, d in got if k == "batch-progress"]
        assert any(d["progress"]["hint"].startswith("Batch 2 of 3") for d in prog), [d["progress"]["hint"] for d in prog]
        # "Waiting" first, "Collecting" only when _prepare really begins (user 13.11.)
        assert prog[0]["state"] == JQ.B_PREPARING and not prog[0]["collecting"]
        assert any(d["state"] == JQ.B_PREPARING and d["collecting"] for d in prog), "collecting is announced"
    finally:
        srv.shutdown()
        srv.server_close()


def test_dry_run_discard():
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run")
        assert r.discard(bid)
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        assert [j["status"] for j in r.jobs(bid)] == [JQ.DONE, JQ.CANCELLED, JQ.CANCELLED]
        assert r.batch(bid)["state"] == JQ.B_CANCELLED and len(fake.payloads) == 1 and not r.busy
        assert len(list((Path(tmp) / "queue").glob("*.png"))) == 2, "cancelled pictures keep their input for ↻ until the list is cleared"
        assert r.clear_finished((JQ.DONE,)) == 1, "Clear finished: only the done one (user 24.11.)"
        assert [j["status"] for j in r.jobs(bid)] == [JQ.CANCELLED, JQ.CANCELLED]
        assert len(list((Path(tmp) / "queue").glob("*.png"))) == 2
        r.clear_finished()
        assert not list((Path(tmp) / "queue").glob("*.png"))
    finally:
        srv.shutdown()
        srv.server_close()


def test_retry_policy():
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        for codes, status, attempts in (([500, 502], JQ.DONE, 3), ([500, 500, 503], JQ.ERROR, 3), ([400], JQ.ERROR, 1)):
            tmp = tempfile.mkdtemp()
            src = pictures(Path(tmp) / "in", ["a.png"])
            fake.fail_prompt = list(codes)
            r, got, b = runner(url, tmp=tmp)
            bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False,
                                             save_settings=settings(tmp)))
            wait_until(lambda: any(k == "batch-done" for k, _ in got), what=f"batch over {codes}")
            j = r.jobs(bid)[0]
            assert j["status"] == status and j["attempts"] == attempts, (codes, j)
            if status == JQ.ERROR:
                assert any(k == "batch-error" for k, _ in got)
                if codes == [400]:
                    assert "rejected" in j["error"] and j["auto_retries"] == 0
                    assert r.retry(j["id"]), "a failed job can be sent again by hand"
                    wait_until(lambda: r.job(j["id"])["status"] == JQ.DONE, what="manual retry")
                    assert r.job(j["id"])["attempts"] == 2
    finally:
        srv.shutdown()
        srv.server_close()


def test_pause_cancel_reorder():
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png", "d.png"])
        gate = {"open": False}
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp, gate=lambda: gate["open"])
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False,
                                         save_settings=settings(tmp)))
        wait_until(lambda: len(r.jobs(bid)) == 4, what="jobs created")
        assert r.busy and not fake.payloads, "the window's own run holds the batch back (gate)"
        a, bb, c, d = [j["id"] for j in r.jobs(bid)]
        assert r.move(d, -1) and r.move(d, -1) and not r.move(a, -1)
        assert [j["source"]["name"] for j in r.jobs(bid)] == ["a.png", "d.png", "b.png", "c.png"]
        assert r.pause(a) and not r.pause(a) and r.cancel(bb)
        assert r.job(a)["status"] == JQ.PAUSED and r.job(bb)["status"] == JQ.CANCELLED
        gate["open"] = True
        wait_until(lambda: r.job(c)["status"] == JQ.DONE, what="rest of the batch")
        names = [Path(p).stem for j in (d, c) for p in r.job(j)["results"]]
        assert names == ["d_refined", "c_refined"], names
        assert len(fake.payloads) == 2 and r.job(a)["status"] == JQ.PAUSED
        wait_until(lambda: not r.busy, what="idle with a paused job")
        assert r.batch(bid)["state"] == JQ.B_RUNNING, "a paused job keeps the batch open"
        assert r.pause_batch(bid) == 0 and r.resume_batch(bid) == 1
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        assert r.job(a)["status"] == JQ.DONE and r.batch(bid)["state"] == JQ.B_DONE
        # cancelling the running job: only that prompt id at ComfyUI, never a bare /interrupt
        src2 = pictures(Path(tmp) / "in2", ["x.png", "y.png"])
        fake.hold.clear()
        got.clear()
        bid2 = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src2), dry_run=False,
                                          save_settings=settings(tmp)))
        wait_until(lambda: any(j["status"] == JQ.RUNNING and j["prompt_id"] for j in r.jobs(bid2)), what="job at ComfyUI")
        x = r.jobs(bid2)[0]
        assert r.running_job["id"] == x["id"]
        assert r.cancel_batch(bid2)
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch cancelled")
        fake.hold.set()
        assert [j["status"] for j in r.jobs(bid2)] == [JQ.CANCELLED, JQ.CANCELLED]
        assert {"delete": [x["prompt_id"]]} in fake.deletes
        assert fake.interrupts and all(i.get("prompt_id") for i in fake.interrupts), fake.interrupts
        assert r.batch(bid2)["state"] == JQ.B_CANCELLED
    finally:
        fake.hold.set()
        srv.shutdown()
        srv.server_close()


def test_jobs_ahead_events():
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png"])
        fake.foreign_running = [(1, "f1", "other", "anna")]
        fake.hold.clear()
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-ahead" and d["ahead"] == 1 for k, d in got), what="one job of others ahead")
        fake.foreign_running = []
        wait_until(lambda: any(k == "batch-ahead" and d["ahead"] == 0 for k, d in got), what="none ahead any more")
        fake.hold.set()
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="done")
    finally:
        fake.hold.set()
        srv.shutdown()
        srv.server_close()


def two_docs(tmp):
    pc, _, b = T.make(tmp, with_sel=False, layers=1)
    pc.docs.append(T.Doc("second.png", [{"id": 50, "img": Image.new("RGBA", (T.W, T.H), (90, 20, 20, 255)), "visible": True}]))
    pc.active = 0
    return pc


def test_open_images_batch():
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = two_docs(tmp)
        r, got, b = runner(url, pc=pc, tmp=tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_OPEN, dry_run=False, also_save_file=True,
                                         save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="open-images refine")
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.DONE, JQ.DONE] and [j["placed"] for j in jobs] == ["layer", "layer"], jobs
        assert [j["source"]["name"] for j in jobs] == ["scene.png", "second.png"] and jobs[0]["source"]["size"] == [T.W, T.H]
        assert len(pc.docs) == 2 and all(len(d.layers) == 2 for d in pc.docs), [len(d.layers) for d in pc.docs]
        assert sorted(p.name for p in (Path(tmp) / "out").iterdir()) == ["scene_refined.png", "second_refined.png"]
        assert pc.active == 0, "the document in front before the batch is in front again"
        assert any(c == "history.newSnapshot" for c, _ in pc.log), "one undo point per document"
        # Upscale: new documents, no file without the tick
        got.clear()
        req = Request(mode="upscale", workflow=str(WF / "flux3-klein-upscale.json"), scale=2.0)
        req.params = workflows.GenParams(prompt="", seed=5)
        bid = r.start_batch(JQ.BatchSpec(req, JQ.SOURCE_OPEN, dry_run=False, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="open-images upscale")
        jobs = r.jobs(bid)
        assert [j["placed"] for j in jobs] == ["document", "document"] and all(not j["results"] for j in jobs)
        assert len(pc.docs) == 4 and "upscaled" in pc.docs[2].name, [d.name for d in pc.docs]
        # a document changed meanwhile (other size): the result goes to a file and a new document
        got.clear()
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_OPEN, dry_run=True, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run")
        jobs = r.jobs(bid)
        assert len(jobs) == 4
        real_doc = pc.document
        pc.document = lambda: dict(real_doc(), width=999)     # every document now has another size
        try:
            r.confirm(bid)
            wait_until(lambda: any(k == "batch-done" for k, _ in got), what="rest")
        finally:
            pc.document = real_doc
        assert [j["placed"] for j in r.jobs(bid)][1:] == ["file", "file", "file"], r.jobs(bid)
        # bad settings are refused at once
        for bad, text in ((Request(mode="inpaint"), "Refine Image, Upscale and Edit"),
                          (Request(mode="edit", workflow=str(WF / "fibo2-edit.json")), "Type an instruction"),
                          (Request(mode="edit", workflow=str(WF / "fibo2-edit.json"), enhance=False), "Describe the edit")):
            bad.params = workflows.GenParams(prompt="")
            try:
                r.start_batch(JQ.BatchSpec(bad, JQ.SOURCE_OPEN))
            except (ValueError, BridgeError) as e:
                assert text in str(e), e
            else:
                raise AssertionError(text)
    finally:
        srv.shutdown()
        srv.server_close()


def test_upscale_too_large_skipped():
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = Path(tmp) / "in"
        pictures(src, ["big.png"], size=(3000, 2000))
        pictures(src, ["small.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        req = Request(mode="upscale", workflow=str(WF / "flux3-klein-upscale.json"), scale=2.0)
        req.params = workflows.GenParams(prompt="", seed=5)
        bid = r.start_batch(JQ.BatchSpec(req, JQ.SOURCE_FOLDER, folder=str(src), dry_run=True, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        jobs = {j["source"]["name"]: j for j in r.jobs(bid)}
        assert jobs["big.png"]["status"] == JQ.ERROR and jobs["big.png"]["error"].startswith(JQ.SKIPPED)
        assert jobs["small.png"]["status"] == JQ.DONE and len(fake.payloads) == 1
        assert r.batch(bid)["skipped"] and "big.png" in r.batch(bid)["skipped"][0]
        assert not any(k == "batch-dry" for k, _ in got), "nothing left to confirm: no dry-run stop"
        assert Image.open(jobs["small.png"]["results"][0]).size == OUT_SIZE, "Upscale keeps the size it was drawn in"
    finally:
        srv.shutdown()
        srv.server_close()


def test_crash_recovery():
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        tmp = tempfile.mkdtemp()
        pc = two_docs(tmp)
        qdir = Path(tmp) / "queue"
        store = JQ.JobStore(Path(tmp) / "queue.json", qdir)
        with fake.lock:
            fake.done.update({"77": True, "78": True, "79": True})
        old_settings = config.get_setting(savefile.SAVE_FOLDER_KEY)
        config.set_setting(savefile.SAVE_FOLDER_KEY, str(Path(tmp) / "out"))     # a rescued result uses the saved settings

        def job(jid, status, pid="", **kw):
            png = store.write_input(jid, Image.new("RGB", (T.W, T.H), "blue"))
            return JQ.Job(id=jid, batch_id="b", mode=kw.pop("mode", "refine"), status=status, prompt_id=pid,
                          input_png=str(png), out_node="out", **kw)

        store.batches["b"] = JQ.Batch(id="b", mode="refine", source="folder", state=JQ.B_RUNNING, total=6)
        store.jobs = [job("file-ok", JQ.RUNNING, "77", source={"kind": "folder", "path": str(Path(tmp) / "beach.png"), "size": [T.W, T.H]}),
                      job("gone", JQ.RUNNING, "88", source={"kind": "folder", "path": "x.png", "size": [T.W, T.H]}),
                      job("doc-ok", JQ.RUNNING, "78", source={"kind": "open", "name": "second.png", "index": 1, "size": [T.W, T.H]}),
                      job("doc-closed", JQ.RUNNING, "79", source={"kind": "open", "name": "closed.png", "index": 5, "size": [T.W, T.H]}),
                      job("wait", JQ.WAITING), job("held", JQ.PAUSED)]
        (qdir / "stray.png").write_bytes(b"x")
        store.save()
        r, got, b = runner(url, pc=pc, tmp=tmp)
        assert {j["id"]: j["status"] for j in r.jobs()}["file-ok"] == JQ.RUNNING
        r.recover()
        wait_until(lambda: not r.busy, what="recovery")
        st = {j["id"]: j for j in r.jobs()}
        assert st["file-ok"]["status"] == JQ.DONE and Path(st["file-ok"]["results"][0]).name == "beach_refined.png"
        assert st["gone"]["status"] == JQ.ERROR and "no longer knows" in st["gone"]["error"]
        assert st["doc-ok"]["status"] == JQ.DONE and st["doc-ok"]["placed"] == "layer" and len(pc.docs[1].layers) == 2
        assert st["doc-closed"]["status"] == JQ.DONE and st["doc-closed"]["placed"] == "file"
        assert Path(st["doc-closed"]["results"][0]).name == "closed_refined.png" and len(pc.docs) == 3, [d.name for d in pc.docs]
        assert st["wait"]["status"] == JQ.CANCELLED and st["held"]["status"] == JQ.CANCELLED
        assert list(qdir.glob("*.png")) == [], list(qdir.glob("*.png"))
        assert r.batch("b")["state"] == JQ.B_DONE
        assert not r.retry("gone"), "after a restart the settings are gone: no retry"
        saved = json.loads((Path(tmp) / "queue.json").read_text(encoding="utf-8"))
        assert {j["id"]: j["status"] for j in saved["jobs"]}["gone"] == JQ.ERROR
        config.set_setting(savefile.SAVE_FOLDER_KEY, old_settings)
    finally:
        srv.shutdown()
        srv.server_close()


OOM_TEXT = ("Error in node KSampler: Allocation on device 0 would exceed allowed memory. (out of memory) "
            "Currently allocated: 929 MiB")


def _failing(b, texts):
    """bridge.process_image raises ComfyError(texts[i]) on call i while texts last, then works as before."""
    orig, calls = b.process_image, []

    def fake(*a, **kw):
        calls.append(time.monotonic())
        if len(calls) <= len(texts):
            raise ComfyError(texts[len(calls) - 1])
        return orig(*a, **kw)
    b.process_image = fake
    return calls


def test_oom_policy():
    assert JQ.is_oom(OOM_TEXT) and JQ.is_oom("torch.OutOfMemoryError: CUDA") and JQ.is_oom("ALLOCATION ON DEVICE 0")
    assert not JQ.is_oom("Error in node KSampler: shape mismatch") and not JQ.is_oom("")
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        for texts, status, attempts in (([OOM_TEXT], JQ.DONE, 2), ([OOM_TEXT] * 3, JQ.ERROR, 3),
                                        (["Error in node KSampler: shape mismatch"], JQ.ERROR, 1)):
            tmp = tempfile.mkdtemp()
            src = pictures(Path(tmp) / "in", ["a.png"])
            r, got, b = runner(url, tmp=tmp)
            calls = _failing(b, texts)
            bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False,
                                             save_settings=settings(tmp)))
            wait_until(lambda: any(k == "batch-done" for k, _ in got), what=f"batch over {texts[0][:20]}")
            j = r.jobs(bid)[0]
            assert j["status"] == status and j["attempts"] == attempts, (texts, j)
            if status == JQ.ERROR and attempts == 3:
                assert "out of memory" in j["error"] and j["auto_retries"] == JQ.MAX_AUTO_RETRIES
            if attempts == 1:
                assert j["auto_retries"] == 0
            if status == JQ.DONE:
                assert j["auto_retries"] == 1 and j["error"] == ""
    finally:
        srv.shutdown()
        srv.server_close()


def test_oom_retry_text():
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        _failing(b, [OOM_TEXT, OOM_TEXT])
        seen = []
        orig_set = r._set

        def spy(job, **f):
            if f.get("error", "").startswith("Retry"):
                seen.append(f["error"])
            orig_set(job, **f)
        r._set = spy
        r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        assert [x.split(" after:")[0] for x in seen] == ["Retry 1 of 2", "Retry 2 of 2"], seen
        assert OOM_TEXT in seen[0]
    finally:
        srv.shutdown()
        srv.server_close()


def test_gap_after_placing():
    srv, fake = server()
    old = JQ.PLACE_GAP_S
    JQ.PLACE_GAP_S = 0.6
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        placed, sent = [], []
        orig_save, orig_proc = savefile.save_batch_result, b.process_image

        def save(*a, **kw):
            res = orig_save(*a, **kw)
            placed.append(time.monotonic())
            return res

        def proc(*a, **kw):
            sent.append(time.monotonic())
            return orig_proc(*a, **kw)
        savefile.save_batch_result, b.process_image = save, proc
        try:
            r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False, save_settings=settings(tmp)))
            wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        finally:
            savefile.save_batch_result = orig_save
        assert len(sent) == 2 and len(placed) == 2
        assert sent[1] - placed[0] >= 0.55, (sent, placed)
    finally:
        JQ.PLACE_GAP_S = old
        srv.shutdown()
        srv.server_close()


def test_cancel_during_gap():
    srv, fake = server()
    old = JQ.PLACE_GAP_S
    JQ.PLACE_GAP_S = 30.0
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False, save_settings=settings(tmp)))
        wait_until(lambda: [j["status"] for j in r.jobs(bid)][:1] == [JQ.DONE], what="first job done")
        t0 = time.monotonic()
        assert r.cancel_batch(bid)
        wait_until(lambda: not r.busy and not (r._thread and r._thread.is_alive()), timeout=5, what="runner idle")
        assert time.monotonic() - t0 < 3 and len(fake.payloads) == 1
        assert [j["status"] for j in r.jobs(bid)] == [JQ.DONE, JQ.CANCELLED]
    finally:
        JQ.PLACE_GAP_S = old
        srv.shutdown()
        srv.server_close()


def test_second_batch_uses_the_canvas_of_its_start():
    """An open-images batch takes its pictures when it is sent (user 13.11.): a second batch started while the first one runs
    works on what was on screen then, not on the results the first batch places meanwhile (this replaces the "fresh canvas
    before each job" of a396c3a, which did the opposite)."""
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        pc = two_docs(tmp)
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", pc=pc, tmp=tmp)
        before = [d.layers[0]["img"].convert("RGB").getpixel((3, 3)) for d in pc.docs]
        taken = []
        orig = r.store.write_input
        r.store.write_input = lambda jid, im: (taken.append((jid, im.convert("RGB").getpixel((3, 3)))), orig(jid, im))[1]
        fake.hold.clear()
        a = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_OPEN, dry_run=False, save_settings=settings(tmp)))
        wait_until(lambda: any(j["status"] == JQ.RUNNING for j in r.jobs(a)), what="first batch at ComfyUI")
        bb = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_OPEN, dry_run=False, save_settings=settings(tmp)))
        assert r._shots[bb]["done"].wait(10), "the snapshot is taken at once, while the first batch is still at ComfyUI"
        fake.hold.set()
        wait_until(lambda: sum(1 for k, _ in got if k == "batch-done") == 2, what="both batches over")
        assert all(len(d.layers) == 3 for d in pc.docs), "both batches placed a layer in each document"
        second = [px for jid, px in taken if jid in {j["id"] for j in r.jobs(bb)}]
        assert second == before, (second, before, "the second batch must start from the canvas of its send time")
        assert "_fresh_open_picture" not in (ROOT / "pccomfy" / "jobqueue.py").read_text(encoding="utf-8")
    finally:
        srv.shutdown()
        srv.server_close()


def test_resume_confirms_a_waiting_dry_run():
    """Pause all, then resume in a batch that waits for the dry run's confirmation: the pictures stayed unstarted because only
    running batches start pictures (queue window: the ▶ did nothing). Resuming now confirms the dry run."""
    for whole in (True, False):
        srv, fake = server()
        try:
            tmp = tempfile.mkdtemp()
            src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png"])
            r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
            bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=True,
                                             save_settings=settings(tmp)))
            wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run")
            assert r.batch(bid)["state"] == JQ.B_CONFIRM and r.pause_batch(bid) == 2
            wait_until(lambda: not r.busy or r.batch(bid)["state"] == JQ.B_CONFIRM, what="waiting")
            if whole:
                assert r.resume_batch(bid) == 2
            else:
                assert r.resume(r.jobs(bid)[1]["id"])
            assert any(k == "batch-dry-over" and d["batch"] == bid for k, d in got)
            wait_until(lambda: r.job(r.jobs(bid)[1]["id"])["status"] == JQ.DONE, what="resumed picture runs")
            if whole:
                wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
                assert [j["status"] for j in r.jobs(bid)] == [JQ.DONE] * 3
        finally:
            srv.shutdown()
            srv.server_close()


def test_resume_a_dry_run_whose_window_was_closed():
    """X / Escape on the dry-run window only close it (user 13.11.): the batch waits in the queue with unpaused pictures,
    and ▶ on its row (resume_batch) starts the rest."""
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=True,
                                         save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run")
        assert r.batch(bid)["state"] == JQ.B_CONFIRM
        assert r.resume_batch(bid) == 0          # nothing paused, but the dry run is confirmed
        assert any(k == "batch-dry-over" and d["batch"] == bid for k, d in got)
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        assert [j["status"] for j in r.jobs(bid)] == [JQ.DONE] * 3
    finally:
        srv.shutdown()
        srv.server_close()


def test_retry_a_cancelled_picture():
    """↻ on a cancelled picture did nothing: the cancel deleted its input picture, so retry() said no (the window blamed a
    restart). A cancelled picture keeps its input now; retry() queues it again and the batch (cancelled before) runs on."""
    srv, fake = server()
    try:
        tmp = tempfile.mkdtemp()
        src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png"])
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=True, save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-dry" for k, _ in got), what="dry run")
        assert r.pause_batch(bid) == 2                          # a paused row offers resume (the glyph rules are in test_batch_gui)
        jobs = r.jobs(bid)
        assert [j["status"] for j in jobs] == [JQ.DONE, JQ.PAUSED, JQ.PAUSED]
        assert r.cancel(jobs[1]["id"]) and r.cancel_batch(bid)
        wait_until(lambda: r.batch(bid)["state"] == JQ.B_CANCELLED, what="cancelled")
        cj = r.jobs(bid)[1]
        assert cj["status"] == JQ.CANCELLED and cj["input_png"] and Path(cj["input_png"]).exists(), cj
        got.clear()
        assert r.retry(cj["id"]), "a cancelled picture can be sent again"
        wait_until(lambda: r.job(cj["id"])["status"] == JQ.DONE, what="retried picture")
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over again")
        assert r.batch(bid)["state"] == JQ.B_DONE, "the batch is not stuck as cancelled"
        assert not Path(cj["input_png"]).exists(), "done: input removed"
        r.clear_finished()
        assert not list((Path(tmp) / "queue").glob("*.png")), "clearing the list removes the kept inputs of cancelled pictures"
    finally:
        srv.shutdown()
        srv.server_close()


def test_owner_name():
    config.set_setting(JQ.OWNER_SETTING, None)
    assert JQ.owner_name()
    config.set_setting(JQ.OWNER_SETTING, "  Studio PC  ")
    assert JQ.owner_name() == "Studio PC"
    config.set_setting(JQ.OWNER_SETTING, None)
    assert JQ.queue_file() == Path(HOME) / "queue.json" and JQ.queue_dir() == Path(HOME) / "queue"


def test_no_number_and_one_at_a_time_with_others():
    """No priority number at ComfyUI (user 21.11.): it runs the jobs in the order they come in, and PxC has at most one
    picture there, also while other participants have jobs waiting, so the participants take turns picture by picture."""
    srv, fake = server()
    try:
        c = ComfyUI(f"http://127.0.0.1:{srv.server_port}")
        c.queue({"1": {}})
        assert "number" not in fake.payloads[0] and "front" not in fake.payloads[0], fake.payloads[0]
        assert not hasattr(c, "order") and not hasattr(c, "delete_queued")
        assert not hasattr(JQ, "ORDER_STEP") and "preplaced" not in {f.name for f in dataclasses.fields(JQ.Job)}
    finally:
        srv.shutdown()
        srv.server_close()
    srv, fake = server()                   # a fresh ComfyUI: the job above never ends there
    try:
        fake.foreign_pending = [(1.0, "f1", "other", "anna")]
        tmp = tempfile.mkdtemp()
        r, got, b = runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)
        src = pictures(Path(tmp) / "in", ["a.png", "b.png", "c.png"])
        bid = r.start_batch(JQ.BatchSpec(refine_request(), JQ.SOURCE_FOLDER, folder=str(src), dry_run=False,
                                         save_settings=settings(tmp)))
        wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
        assert fake.max_inflight == 1, fake.max_inflight
        assert all("number" not in p for p in fake.payloads) and len(fake.payloads) == 3
        assert [j["status"] for j in r.jobs(bid)] == [JQ.DONE] * 3
    finally:
        srv.shutdown()
        srv.server_close()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t0 = time.monotonic()
        t()
        print(f"ok {t.__name__} ({time.monotonic() - t0:.1f} s)")
    print("ALL OK (jobqueue)")


if __name__ == "__main__":
    main()
