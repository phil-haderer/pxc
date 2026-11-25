# tags: queue, undo
""""Undo AI edit" after a batch over the open documents (pccomfy/jobqueue.py, Bridge.batch_snapshot): the active document
decides. One that got a batch result goes back to its state before the batch, the others stay; a Generate after the batch
still takes back only that run; Upscale batches open new documents and take no snapshot (like a normal Upscale run);
folder batches touch no document. Against the fake ComfyUI of test_jobqueue.py (a free port, never 8188) and the
PhotoCraft simulator of test_reference_mode.py with real history snapshots added.

    python tests/test_batch_undo.py
"""
import copy
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import test_jobqueue as Q  # noqa: E402  (sets PCCOMFY_HOME first, then imports pccomfy)
from PIL import Image  # noqa: E402
from pccomfy import jobqueue as JQ, workflows  # noqa: E402
from pccomfy.bridge import Bridge, BridgeError, Request  # noqa: E402
import test_reference_mode as T  # noqa: E402

WF = ROOT / "workflows"


class HistoryPC(T.FakePC):
    """The simulator with PhotoCraft's history snapshots: a snapshot belongs to the document it was taken in and holds
    its layers; selecting it brings them back (only in that document, which must be the active one)."""

    def __init__(self, exchange):
        super().__init__(exchange)
        self.snaps, self.sid = {}, 0

    def execute(self, cmd, params=None):
        if cmd == "history.newSnapshot":
            self.sid += 1
            self.snaps[self.sid] = (self.doc, copy.deepcopy(self.doc.layers))
            self.log.append((cmd, params))
            return {"id": self.sid}
        if cmd == "history.selectSnapshot":
            doc, layers = self.snaps[params["snapshot"]]
            assert doc is self.doc, "a snapshot is selected in its own document"
            doc.layers = copy.deepcopy(layers)
            self.log.append((cmd, params))
            return {}
        if cmd == "history.deleteSnapshot":
            self.snaps.pop(params["snapshot"], None)
            self.log.append((cmd, params))
            return {}
        return super().execute(cmd, params)


NAMES = ["scene.png", "second.png", "third.png"]


def three_docs(tmp):
    pc = HistoryPC(tmp)
    for i, n in enumerate(NAMES):
        pc.docs.append(T.Doc(n, [{"id": 10 + i, "img": Image.new("RGBA", (T.W, T.H), (40 * i, 90, 160, 255)), "visible": True}]))
    pc.active = 0
    return pc


def layers(pc):
    return {d.name: len(d.layers) for d in pc.docs}


def activate(pc, name):
    pc.active = next(i for i, d in enumerate(pc.docs) if d.name == name)


def batch(r, got, req, tmp, source=JQ.SOURCE_OPEN, **kw):
    got.clear()
    bid = r.start_batch(JQ.BatchSpec(req, source, dry_run=False, save_settings=Q.settings(tmp), **kw))
    Q.wait_until(lambda: any(k == "batch-done" for k, _ in got), what="batch over")
    return r.jobs(bid)


def test_no_batch_no_photocraft_call():
    """Without a batch, Undo looks only at the run snapshot (exactly as before: no question to PhotoCraft)."""
    b = Bridge(Q.NoPhotoCraft(), None, tempfile.mkdtemp())
    assert b._undo_target() is None and not b.can_undo() and not b.can_undo("a.png") and not b.can_redo()
    assert b.batch_undo_docs() == []
    try:
        b.undo_last()
    except (BridgeError, AssertionError) as e:
        assert "Nothing to undo" in str(e) or "PhotoCraft" in str(e), e
    else:
        raise AssertionError


def test_open_images_batch_undo():
    srv, fake = Q.server()
    try:
        tmp = tempfile.mkdtemp()
        pc = three_docs(tmp)
        r, got, b = Q.runner(f"http://127.0.0.1:{srv.server_port}", pc=pc, tmp=tmp)
        jobs = batch(r, got, Q.refine_request(), tmp)
        assert [j["placed"] for j in jobs] == ["layer"] * 3, jobs
        assert layers(pc) == dict.fromkeys(NAMES, 2)
        assert b.batch_undo_docs() == sorted(NAMES) and all(b.can_undo(n) for n in NAMES)
        assert not b.can_undo("other.png") and b._snap is None
        assert sum(c == "history.newSnapshot" for c, _ in pc.log) == 3, "one undo point per document and batch"

        # a Generate after the batch, in "scene.png": its own snapshot
        activate(pc, "scene.png")
        b.run(Q.refine_request())
        assert layers(pc) == {"scene.png": 3, "second.png": 2, "third.png": 2}
        assert b._snap and b._snap["doc"] == "scene.png"

        # Undo in "second.png": only that document goes back to before the batch
        activate(pc, "second.png")
        msg = b.undo_last()
        assert "before the batch" in msg and "second.png" in msg, msg
        assert layers(pc) == {"scene.png": 3, "second.png": 1, "third.png": 2}
        assert pc.docs[pc.active].name == "second.png"
        # Redo brings the batch result back, Undo again takes it back
        assert b.can_redo()
        b.redo_last()
        assert layers(pc)["second.png"] == 2
        b.undo_last()
        assert layers(pc)["second.png"] == 1

        # Undo in "scene.png": the run came after the batch, so only the run goes (the batch result stays)
        activate(pc, "scene.png")
        msg = b.undo_last()
        assert "before the last AI edit" in msg, msg
        assert layers(pc) == {"scene.png": 2, "second.png": 1, "third.png": 2}
        b.undo_last()                       # one step back, as before: the same snapshot again
        assert layers(pc)["scene.png"] == 2

        # Undo in "third.png": its batch result goes, the others stay
        activate(pc, "third.png")
        b.undo_last()
        assert layers(pc) == {"scene.png": 2, "second.png": 1, "third.png": 1}

        # a second batch: the older batch snapshot of each document is replaced (only the latest is kept)
        before = set(pc.snaps)
        batch(r, got, Q.refine_request(), tmp)
        assert layers(pc) == {"scene.png": 3, "second.png": 2, "third.png": 2}
        assert not ({s["id"] for s in b._batch_snaps.values()} & before), "new snapshots for the new batch"
        activate(pc, "scene.png")           # now the batch is newer than the run in this document
        msg = b.undo_last()
        assert "before the batch" in msg and layers(pc)["scene.png"] == 2, (msg, layers(pc))

        # Upscale batch: new documents, no snapshot (like a normal Upscale run); Undo in a new document = the run's
        n_snap = sum(c == "history.newSnapshot" for c, _ in pc.log)
        snaps = dict(b._batch_snaps)
        req = Request(mode="upscale", workflow=str(WF / "flux3-klein-upscale.json"), scale=2.0)
        req.params = workflows.GenParams(prompt="", seed=5)
        jobs = batch(r, got, req, tmp)
        assert [j["placed"] for j in jobs] == ["document"] * 3, jobs
        assert len(pc.docs) == 6 and sum(c == "history.newSnapshot" for c, _ in pc.log) == n_snap
        assert b._batch_snaps == snaps and b.can_undo(pc.docs[-1].name)   # the run snapshot still counts
        pc.active = 5
        msg = b.undo_last()                  # falls back to the last run, in its own document (as before)
        assert "before the last AI edit" in msg and pc.docs[pc.active].name == "scene.png", msg
    finally:
        srv.shutdown()
        srv.server_close()


def test_folder_batch_no_undo():
    srv, fake = Q.server()
    try:
        tmp = tempfile.mkdtemp()
        src = Q.pictures(Path(tmp) / "in", ["a.png", "b.png"])
        r, got, b = Q.runner(f"http://127.0.0.1:{srv.server_port}", tmp=tmp)   # NoPhotoCraft: any use fails
        jobs = batch(r, got, Q.refine_request(), tmp, source=JQ.SOURCE_FOLDER, folder=str(src))
        assert [j["placed"] for j in jobs] == ["file", "file"], jobs
        assert b.batch_undo_docs() == [] and not b.can_undo()
    finally:
        srv.shutdown()
        srv.server_close()


def main():
    for t in (test_no_batch_no_photocraft_call, test_open_images_batch_undo, test_folder_batch_no_undo):
        t()
        print(f"ok {t.__name__}")
    print("ALL OK (batch undo)")


if __name__ == "__main__":
    main()
