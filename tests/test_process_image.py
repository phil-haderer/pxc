"""The middle part of a run without PhotoCraft (docs/plan/speichern-queue-batch.md, step 2): Bridge.process_image takes a
picture and a ComfyUI, nothing else. Refine, Upscale and Edit against a small fake ComfyUI over HTTP on a free port (never
8188); the graphs it sends are the ones a run from PhotoCraft sends for the same picture. And the split of Bridge._run did
not change what a run sends: graph and upload fingerprints of representative runs, taken from the code before the split.

    python tests/test_process_image.py
    python tests/test_process_image.py --update     # after an intended change of the graphs: new fingerprints
"""
import hashlib
import io
import itertools
import json
import re
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from pccomfy import bridge, workflows  # noqa: E402
from pccomfy.bridge import Bridge, BridgeError, Processed, Request  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402
import test_reference_mode as T  # noqa: E402  (the PhotoCraft simulator and the in-process fake ComfyUI)

WF = ROOT / "workflows"
OUT_SIZE = (96, 64)


# ---------- a fake ComfyUI over HTTP ----------

class Fake:
    def __init__(self):
        self.uploads, self.graphs, self.lock = {}, [], threading.Lock()

    @staticmethod
    def out_image(n):
        return Image.new("RGB", OUT_SIZE, (20 * n % 256, 120, 200))


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
            self._json({pid: {"status": {"completed": True, "status_str": "success"},
                              "outputs": {"out": {"images": [{"filename": f"{pid}.png", "subfolder": "", "type": "output"}]}}}})
        elif self.path.startswith("/view?"):
            n = int(re.search(r"filename=(\d+)\.png", self.path).group(1))
            buf = io.BytesIO()
            f.out_image(n).save(buf, format="PNG")
            self._send(200, buf.getvalue(), "image/png")
        elif self.path.startswith("/object_info/"):
            self._json({})                 # no LoRA list: the names stay as they are
        else:
            self._send(404, b"{}")         # also /ws: no websocket, the client polls /history

    def do_POST(self):
        f = self.fake
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/upload/image":
            name = re.search(rb'name="image"; filename="([^"]+)"', body).group(1).decode()
            png = body[body.index(b"\x89PNG"):]
            with f.lock:
                f.uploads[name] = Image.open(io.BytesIO(png)).convert("RGB")
            self._json({"name": name, "subfolder": "pccomfy", "type": "input"})
        elif self.path == "/prompt":
            with f.lock:
                f.graphs.append(json.loads(body)["prompt"])
                pid = str(len(f.graphs))
            self._json({"prompt_id": pid, "node_errors": {}})
        else:
            self._json({})


def server():
    fake = Fake()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (Handler,), {"fake": fake}))
    assert srv.server_port != 8188
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, fake


def same(a, b):
    return a.size == b.size and np.array_equal(np.asarray(a.convert("RGB")), np.asarray(b.convert("RGB")))


class NoPhotoCraft:
    """Any use of PhotoCraft fails the test."""
    def __getattr__(self, name):
        raise AssertionError(f"process_image used PhotoCraft ({name})")


def fixed_uuid():
    ctr = itertools.count()
    return lambda: uuid.UUID(int=next(ctr))


# ---------- process_image without PhotoCraft ----------

def standalone_checks():
    srv, fake = server()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        picture = T.FakePC.composite(T.make(tempfile.mkdtemp(), with_sel=False)[0].docs[0])     # the simulator's 200x120 scene
        cases = [
            ("refine", dict(workflow=str(WF / "flux3-klein-refine.json")), "", 1.0),
            ("refine", dict(workflow=str(WF / "flux3-klein-refine.json"), detail=0.6), "sharp", 0.6),
            ("upscale", dict(workflow=str(WF / "flux3-klein-upscale.json"), scale=2.0), "a young woman", 1.0),
            ("edit", dict(workflow=str(WF / "fibo2-edit.json"), enhance=False), "make it night", 1.0),
            ("edit", dict(workflow=str(WF / "qwen-image-21-edit.json"), enhance=False), "snow", 1.0),
        ]
        for mode, kw, prompt, detail in cases:
            for via in ("standalone", "run"):
                fake.uploads.clear()
                fake.graphs.clear()
                uuid_before = uuid.uuid4
                uuid.uuid4 = fixed_uuid()          # the same tag (file names in the graph) for both ways
                try:
                    tmp = tempfile.mkdtemp()
                    req = Request(mode=mode, **kw)
                    req.params = workflows.GenParams(prompt=prompt, seed=7)
                    if via == "standalone":
                        b = Bridge(NoPhotoCraft(), ComfyUI(url), tmp)
                        req, p, tag = b.begin(req)
                        msgs = []
                        out = b.process_image(req, p, picture.copy(), tag=tag, progress=lambda f, m, **k: msgs.append(m))
                        assert isinstance(out, Processed) and len(out.results) == 1, out
                        ims = out.results[0][1]
                        assert len(ims) == 1
                        if detail < 1:     # the Detail mix with the plainly scaled picture is part of the middle part
                            mix = Image.blend(picture.convert("RGB").resize(OUT_SIZE, Image.LANCZOS), Fake.out_image(1), detail)
                            assert same(ims[0], mix)
                        else:
                            assert same(ims[0], Fake.out_image(1)), mode
                        assert out.job.region.__dict__ == {"x": 0, "y": 0, "w": 200, "h": 120} and out.job.src is not None
                        assert msgs[0].startswith("Sending to ComfyUI") and any(m.startswith("Queued in ComfyUI") for m in msgs), msgs
                        assert (Path(tmp) / "last-graph.json").exists() and (Path(tmp) / "runs.jsonl").exists()
                        up = fake.uploads[f"pcc-{tag}-image.png"]
                        if mode in bridge.SCALE_MODES:    # at its own size, unchanged
                            assert same(up, picture), up.size
                        if mode == "upscale":
                            mp = [n["inputs"]["megapixels"] for n in fake.graphs[0].values()
                                  if n.get("_meta", {}).get("title", "").startswith("pc:upscale")][0]
                            assert abs(mp - 200 * 120 * 4 / 1e6) < 1e-9
                        alone = (json.loads(json.dumps(fake.graphs)), {k: np.asarray(v).tobytes() for k, v in fake.uploads.items()})
                    else:              # the same request through a whole run from (simulated) PhotoCraft
                        pc, _, b = T.make(tmp, with_sel=False)
                        b.comfy = ComfyUI(url)
                        res = b.run(req)
                        assert res["seed"] == 7
                        ran = (json.loads(json.dumps(fake.graphs)), {k: np.asarray(v).tobytes() for k, v in fake.uploads.items()})
                finally:
                    uuid.uuid4 = uuid_before
            assert alone == ran, f"{mode} {kw}: process_image sends something else than a run"

        # what needs PhotoCraft says so; a Fill without a selection stops as in a run
        b = Bridge(NoPhotoCraft(), ComfyUI(url), tempfile.mkdtemp())
        for mode, kw, text in (("outpaint", {}, "PhotoCraft only"), ("edit", {"scribble": True}, "PhotoCraft only"),
                               ("inpaint", {}, "Select the area")):
            req = Request(mode=mode, workflow=str(WF / "flux2-klein-sketch.json"), **kw)
            req.params = workflows.GenParams(prompt="x", seed=1)
            req, p, tag = b.begin(req)
            try:
                b.process_image(req, p, picture)
            except BridgeError as e:
                assert text in str(e), (mode, str(e))
            else:
                raise AssertionError(f"{mode}: expected an error")
        # a Fill with a mask works without PhotoCraft too (Qwen: the red mark in the crop)
        mask = Image.new("L", picture.size, 0)
        mask.paste(255, T.SEL)
        req = Request(mode="inpaint", workflow=str(WF / "qwen-image-21-edit.json"), enhance=False)
        req.params = workflows.GenParams(prompt="a red flower", seed=3)
        req, p, tag = b.begin(req)
        fake.graphs.clear()
        out = b.process_image(req, p, picture, mask=mask, tag=tag)
        assert out.job.fill and out.job.marked and out.job.bbox is not None and len(fake.graphs) == 1
    finally:
        srv.shutdown()
        srv.server_close()


# ---------- the split did not change what a run sends ----------

def W(name):
    return str(WF / name)


RUNS = {   # name: (mode, selection, layers, request, params, setup)
    "refine-flux3": ("refine", False, 3, dict(workflow=W("flux3-klein-refine.json")), dict(prompt="", seed=7), None),
    "refine-qwen-variants": ("refine", False, 2, dict(workflow=W("qwen-image-21-refine.json"), variants=2, detail=0.5), dict(prompt="", seed=11), None),
    "upscale-flux3": ("upscale", True, 3, dict(workflow=W("flux3-klein-upscale.json"), scale=2.0), dict(prompt="a woman", seed=7), None),
    "upscale-fibo-tiles": ("upscale", False, 3, dict(workflow=W("fibo2-upscale.json"), scale=8.0, stages_off=["102"]), dict(prompt="p", seed=7), None),
    "edit-fibo": ("edit", True, 3, dict(workflow=W("fibo2-edit.json")), dict(prompt="make it night", seed=7, denoise=0.6), None),
    "edit-flux3-bbox": ("edit", True, 3, dict(workflow=W("flux3-klein-edit.json"), bbox=True, enhance=False, layer_mask="soft"), dict(prompt="a cat", seed=4), None),
    "edit-flux2-refs": ("edit", False, 3, dict(workflow=W("flux2-klein-edit.json"), refs=[Image.new("RGB", (300, 200), "red")]), dict(prompt="put image 2 in", seed=9), None),
    "edit-minimax": ("edit", False, 3, dict(workflow=W("minimax-h3-image-edit.json"), gen_mp=1.0, enhance=False), dict(prompt="night", seed=7), None),
    "fill-qwen": ("inpaint", True, 3, dict(workflow=W("qwen-image-21-edit.json"), enhance=False), dict(prompt="add a red flower", seed=5), None),
    "fill-flux3-box": ("inpaint", True, 3, dict(workflow=W("flux3-klein-edit.json"), fill_box=True, enhance=False), dict(prompt="a red flower", seed=5), None),
    "inpaint-moss-seam": ("inpaint", True, 3, dict(workflow=W("moss-image-inpaint.json"), seam=True), dict(prompt="a red ball", seed=5), None),
    "inpaint-builtin": ("inpaint", True, 3, dict(workflow=None), dict(prompt="a red ball", seed=5, checkpoint="sd.safetensors"), None),
    "remove-fibo-tries": ("remove", True, 3, dict(workflow=W("fibo2-edit.json"), enhance=False, remove_tries=3), dict(prompt="", seed=5), None),
    "outpaint-flux3": ("outpaint", False, 2, dict(workflow=W("flux3-klein-outpaint.json"), overlap=8, context=1.0), dict(prompt="a stone wall", seed=5), "margin"),
    "txt2img-qwen": ("txt2img", False, 3, dict(workflow=W("qwen-image-21-t2i.json")), dict(prompt="a castle", seed=5), None),
    "txt2img-minimax-doc": ("txt2img", False, 3, dict(workflow=W("minimax-h3-image-t2i.json"), gen_mp=2.0, new_document=True), dict(prompt="a castle", seed=5), None),
}

# fingerprints of graphs and uploads, taken from the code before the split of _run (12.11.); "inputs" = the workflow files
# and workflows.py they were taken with: when those change, the comparison is skipped (the graphs may differ on purpose)
FINGERPRINTS = {
    "inputs": "bd6ecc16a554f800",
    "refine-flux3": "dd324483f4e033911d1b",
    "refine-qwen-variants": "4b6a0eadd04494fb486f",
    "upscale-flux3": "2bc77392f809f62ab61e",
    "upscale-fibo-tiles": "e0fd3c6162cd0161baef",
    "edit-fibo": "0e75fecb67f7a4f39823",
    "edit-flux3-bbox": "0985303574705dc25001",
    "edit-flux2-refs": "e884e721f80ab6a7aef3",
    "edit-minimax": "628ce9b49c2f59d8779d",
    "fill-qwen": "d5cbd7db701edb0420dd",
    "fill-flux3-box": "135ae1ec7747349312de",
    "inpaint-moss-seam": "2b091b4ed0ef7cc76c8c",
    "inpaint-builtin": "13e86a8f9868ba194343",
    "remove-fibo-tries": "409951eeb12b49561a4c",
    "outpaint-flux3": "38ced522df77de066272",
    "txt2img-qwen": "8254493c550c84b9a9d4",
    "txt2img-minimax-doc": "cb0ba27704a2df4ff08f"
}


def inputs_key():
    h = hashlib.sha256()
    for f in sorted({v[3]["workflow"] for v in RUNS.values() if v[3]["workflow"]}) + [str(ROOT / "pccomfy" / "workflows.py")]:
        h.update(Path(f).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def fingerprint(name):
    mode, with_sel, layers, rk, pk, setup = RUNS[name]
    uuid_before = uuid.uuid4
    uuid.uuid4 = fixed_uuid()
    try:
        tmp = tempfile.mkdtemp()
        pc, _, b = T.make(tmp, with_sel=with_sel, layers=layers)
        b.comfy = T.FakeComfy()
        if setup == "margin":
            pc.docs[0].layers[0]["img"].paste((255, 255, 255, 255), (T.W - 16, 0, T.W, T.H))
        req = Request(mode=mode, **rk)
        req.params = workflows.GenParams(**pk)
        b.run(req)
    finally:
        uuid.uuid4 = uuid_before
    h = hashlib.sha256(json.dumps(b.comfy.graphs, sort_keys=True).encode())
    for k in sorted(b.comfy.uploads):
        im = b.comfy.uploads[k]
        h.update(k.encode() + im.mode.encode() + repr(im.size).encode() + im.tobytes())
    return h.hexdigest()[:20]


def fingerprint_checks(update=False):
    got = {name: fingerprint(name) for name in RUNS}
    if update:
        me = Path(__file__)
        text = me.read_text(encoding="utf-8")
        new = "FINGERPRINTS = " + json.dumps({"inputs": inputs_key(), **got}, indent=4) + "\n"
        me.write_text(re.sub(r"FINGERPRINTS = \{.*?\}\n",lambda m: new, text, count=1, flags=re.S), encoding="utf-8")
        print("fingerprints written")
        return
    assert FINGERPRINTS, "no fingerprints yet: run with --update"
    if FINGERPRINTS.get("inputs") != inputs_key():
        print("SKIP fingerprints: the workflow files or workflows.py changed since they were taken")
        return
    bad = [n for n in RUNS if got[n] != FINGERPRINTS.get(n)]
    assert not bad, f"a run sends other graphs or uploads than before: {bad}"


def main():
    if "--update" in sys.argv:
        fingerprint_checks(update=True)
        return
    fingerprint_checks()
    standalone_checks()
    print("ALL OK (process_image)")


if __name__ == "__main__":
    main()
