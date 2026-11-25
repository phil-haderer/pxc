# tags: queue, window
"""Batch and the queue in the window (12.11., docs/plan/speichern-queue-batch.md steps 3-4; gui_batch.py): the three new entries
of the footer menu, the batch dialog (refuses other functions and BBOX, counts a folder, its checkboxes, Start hands the
runner the request Generate would send), the dry-run dialog, the queue window and its buttons, "At ComfyUI", Generate locked
while a batch is on, the hint at the bar, the "jobs of others ahead" poll of Generate, the owner name setting. Hidden real
Tk window; the runner, PhotoCraft and ComfyUI are faked (no server, nothing goes to the network).

    python tests/test_batch_gui.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-batch-gui-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    from tkinter import ttk
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from PIL import Image  # noqa: E402

from pccomfy import config as cfgmod, gui, gui_batch, gui_queuewin, jobqueue, models, popmenu, ui_settings  # noqa: E402
from pccomfy.bridge import BridgeError  # noqa: E402
from pccomfy.popmenu import PopMenu  # noqa: E402


class FakeComfy:
    client_id = "me"
    owner = None

    def __init__(self):
        self.last_prompt_id = None
        self.entries = []
        self.reads = 0
        self.fail = False

    def queue_entries(self):
        self.reads += 1
        if self.fail:
            raise jobqueue.ComfyError("no connection")
        return [dict(e) for e in self.entries]

    def jobs_ahead(self, pid, entries=None):
        n = 0
        for e in entries if entries is not None else self.entries:
            if e["prompt_id"] == pid:
                return n
            if e["client_id"] != self.client_id:
                n += 1
        return 0


class FakePC:
    def __init__(self, n=3):
        self.n = n

    def session(self):
        return {"active": 0, "documents": [{"name": f"pic{i}.png", "index": i} for i in range(self.n)]}


class FakeBridge:
    feather_shown = False

    def __init__(self):
        self.comfy, self.pc, self.cancels = FakeComfy(), FakePC(), 0

    def cancel(self):
        self.cancels += 1


def job(jid, status, bid="b1", name=None, **kw):
    d = {"id": jid, "batch_id": bid, "mode": "upscale", "status": status, "source": {"kind": "folder", "name": name or f"{jid}.png"},
         "error": "", "results": [], "placed": "", "eta": 120.0, "started": 0.0, "finished": 0.0}
    d.update(kw)
    return d


class FakeRunner:
    def __init__(self):
        self.calls, self.busy, self.fail, self.owner, self.running_job = [], False, None, "tester", None
        self.hint = "Batch 3 of 12 · ~4 min"
        self._jobs = [job("j1", "done", started=1.0, finished=43.0), job("j2", "running", started=time.time()), job("j3", "waiting"),
                      job("j4", "paused"), job("j5", "error", error="ComfyUI said no"),
                      job("j6", "error", error=jobqueue.SKIPPED + "too large")]
        self._batches = [{"id": "b1", "mode": "upscale", "source": "folder", "folder": "C:/pics/holiday", "state": "running",
                          "skipped": ["j6.png: too large"], "progress": {"hint": self.hint, "total": 6, "counts": {}}}]

    def _rec(self, *a):
        self.calls.append(a)
        return True

    def start_batch(self, spec):
        self.calls.append(("start", spec))
        if self.fail:
            raise self.fail
        return "b1"

    def confirm(self, b): return self._rec("confirm", b)
    def discard(self, b): return self._rec("discard", b)
    def pause(self, j): return self._rec("pause", j)
    def resume(self, j): return self._rec("resume", j)
    def cancel(self, j): return self._rec("cancel", j)
    def move(self, j, d): return self._rec("move", j, d)
    def retry(self, j): return self._rec("retry", j) and False         # after a restart: the settings are gone
    def pause_batch(self, b): return self._rec("pause_batch", b)
    def resume_batch(self, b): return self._rec("resume_batch", b)
    def cancel_batch(self, b): return self._rec("cancel_batch", b)
    def clear_finished(self, statuses=("done", "error", "cancelled")): return self._rec("clear", tuple(statuses))
    def shutdown(self, timeout=0.0): return self._rec("shutdown")
    def recover(self): return self._rec("recover")

    def jobs(self, batch_id=None):
        return [dict(j) for j in self._jobs if batch_id is None or j["batch_id"] == batch_id]

    def batches(self):
        return [dict(b) for b in self._batches]

    def job_eta(self, jid):
        return 90.0

    def batch_hint(self, bid):
        return self.hint if bid == "b1" else ""


def pump(app, until=lambda: True, timeout=5.0):
    """Runs the window's event loop step (_poll) until `until()` is true."""
    end = time.monotonic() + timeout
    while True:
        app._poll()
        if until() or time.monotonic() > end:
            return until()
        time.sleep(0.02)


def main():
    popmenu.CLOSE_ON_FOCUS_LOSS = False
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.root.after = (lambda real: (lambda ms, fn=None, *a: real(ms, fn, *a) if ms != 100 else "poll"))(app.root.after)  # _poll is pumped by hand

    # ---- the runner of the window; Generate does not send the owner's name ----
    assert isinstance(app.runner, jobqueue.QueueRunner) and app.runner.bridge is app.bridge and app.runner.events is app.events
    assert app.runner.gate() is True
    app.worker = threading.Thread(target=lambda: time.sleep(0.3))
    app.worker.start()
    assert app.runner.gate() is False              # no batch job starts while the window's own worker runs
    app.worker.join()
    # Generate sends the owner's name too (decision 18.11., replaces 12.11.): the queue window of every PC shows who sent it
    assert app.comfy is app.bridge.comfy and app.comfy.owner == app.runner.owner == jobqueue.owner_name()

    real_runner = app.runner
    app.runner = runner = FakeRunner()
    app.bridge = bridge = FakeBridge()
    # a fresh data folder: the workflow list holds only the built-in graph until ComfyUI answers, so a model could not take
    # its workflow and the window would drop it (as test_model_tabs.py and test_round5.py, the list is filled by hand)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    assert all((Path(app.workflows_dir) / f).is_file() for f in names)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app.v_model.set("qwen")
    app.v_mode.set("inpaint")
    app._on_model()
    app._pick_mode("refine")               # Refine is its own function again (22.11.)
    assert app.v_mode.get() == "refine" and app.v_model.get() == "qwen", app.v_model.get()

    # ---- the footer menu: Save, Copy, then the two batch sources and the queue, each with an icon and a white hover icon ----
    calls = []
    app.open_batch = lambda src: calls.append(("batch", src))
    app.open_queue = lambda: calls.append("queue")
    shown = []
    real_popup = PopMenu.tk_popup
    PopMenu.tk_popup = lambda self, *a, **k: shown.append(self)
    try:
        app._footer_menu()
    finally:
        PopMenu.tk_popup = real_popup
    menu = shown[0]
    # the two resets of the page come under a line (user 16.11.); "History" took the place of "Open queue", the queue has
    # its own symbol in the footer (user 24.11. evening)
    assert [e["label"] for e in menu.entries] == ["Save image (Ctrl+S)", "Copy canvas", "Batch: open images", "Batch: folder…",
                                                  "History", "", "Reset page to my saved settings", "Reset page to default"]
    assert menu.entries[5]["type"] == "separator"
    cmds = [e for e in menu.entries if e["type"] != "separator"]
    assert all(e["icon"] is not None and e["icon_hot"] is not None and e["icon_hot"] is not e["icon"] for e in cmds)
    assert len({str(e["icon"]) for e in cmds}) == 7
    assert all(e["state"] == "normal" for e in cmds)
    app.reset_settings = lambda factory=False: calls.append(("reset", factory))
    real_hist, app._history_menu = app._history_menu, lambda: calls.append("history")
    for e in cmds[2:]:
        e["command"]()
    app._history_menu = real_hist
    assert calls == [("batch", "open"), ("batch", "folder"), "history", ("reset", False), ("reset", True)], calls
    # the queue symbol in the footer opens the queue window, a second click closes it
    calls.clear()
    app.b_queue.invoke()
    assert calls == ["queue"], calls
    del app.open_batch, app.open_queue, app.reset_settings
    # no model linked (the footer is hidden): the two resets are grey
    app._foot_hidden, shown[:] = True, []
    PopMenu.tk_popup = lambda self, *a, **k: shown.append(self)
    try:
        app._footer_menu()
    finally:
        PopMenu.tk_popup = real_popup
        app._foot_hidden = False
    assert [e["state"] for e in shown[0].entries[-2:]] == ["disabled", "disabled"]
    for k in ("images", "folder", "list"):
        assert k in gui.icons.SHAPES

    # ---- the dialog refuses functions without batch, and BBOX ----
    app.v_mode.set("inpaint")
    app.open_batch("open")
    assert app.lbl_batch_msg.cget("text") == gui_batch.BATCH_ONLY and app.b_batch_start is None
    assert app.b_batch_cancel.cget("text") == "Close"
    # the window is called "Batch mode"; the red "!" of the status line stands in front of the function (user 13.11.)
    assert app._batch_dlg.title() == "Batch mode"
    assert not [c for c in app._batch_dlg.winfo_children() if c.winfo_class() == "Frame" and str(c.cget("bg")).lower() == gui.ACCENT.lower()], \
        "the batch window has no blue line on top (user 22.11.: everywhere)"
    assert app.lbl_batch_warn is not None and app.lbl_batch_warn.winfo_manager() == "pack"
    head = app.lbl_batch_fn.master
    assert head.pack_slaves() == [app.lbl_batch_warn, app.lbl_batch_fn]
    # Escape closes it: the window takes the keyboard focus when it opens (it has no title bar)
    assert app._batch_dlg.bind("<Escape>")
    import inspect
    assert "focus_force" in inspect.getsource(gui_batch.BatchMixin._raise_small)
    app.b_batch_cancel.invoke()
    assert app._batch_dlg is None
    app.v_mode.set("multi_edit")
    app._bbox_on = lambda: True
    app.open_batch("open")
    assert app.lbl_batch_msg.cget("text") == gui_batch.BATCH_NO_BBOX and app.b_batch_start is None, (app.lbl_batch_msg.cget("text"), app._run_mode(), app.v_model.get())
    del app._bbox_on
    app._batch_close()
    app.v_mode.set("refine")
    app.open_batch("open")
    assert app.lbl_batch_msg is None and app.lbl_batch_fn.cget("text").startswith("Refine Image · ")
    assert app.lbl_batch_warn is None                  # Refine can run as a batch: no "!"
    # the open window follows a change of function (user 13.11.): Fill can't, the "!" and the reason come; back to Refine
    app.v_batch_dry.set(True)
    app.v_mode.set("inpaint")
    for _ in range(3):
        app.root.update()
    assert app.lbl_batch_warn is not None and app.lbl_batch_msg is not None
    assert app.lbl_batch_msg.cget("text") == gui_batch.BATCH_ONLY and app.b_batch_start is None
    app.v_mode.set("refine")
    for _ in range(3):
        app.root.update()
    assert app.b_batch_start is not None and app.lbl_batch_warn is None
    assert app.lbl_batch_fn.cget("text").startswith("Refine Image · ") and app._alive(app._batch_dlg)
    app.v_batch_dry.set(False)
    # Start and Cancel centred, Start on the left (user 13.11.)
    row = app.b_batch_start.master
    assert row.pack_slaves() == [app.b_batch_start, app.b_batch_cancel] and row.pack_info()["anchor"] == "center"

    # ---- open images: the number of open documents, the checkboxes and their defaults ----
    assert pump(app, lambda: app.lbl_batch_src.cget("text") == "Open images: 3 in PhotoCraft"), app.lbl_batch_src.cget("text")
    assert app.v_batch_dry.get() is False and app.v_batch_save.get() is False       # dry run off at the start (user 13.11.)
    assert app.cb_batch_dry.cget("text") == "Dry run on the first picture"
    assert app.cb_batch_save.cget("text") == "Also save to the save folder"
    assert app.lbl_batch_out.cget("text") == "Results appear as a new layer in each open picture (Upscale: as a new document)."
    app.v_batch_save.set(True)
    app.v_batch_dry.set(True)
    app.b_batch_start.invoke()
    kind, spec = runner.calls[-1]
    assert kind == "start" and isinstance(spec, jobqueue.BatchSpec)
    assert spec.source == "open" and spec.folder is None and spec.dry_run is True and spec.also_save_file is True
    req = spec.request
    assert req.mode == "refine" and req.workflow == app._request().workflow and req.preset == app._layer_prefix()
    assert req.run_no >= 1 and req.group_name == f"Refine {req.run_no}" and app.state["runs"][req.preset] == req.run_no
    assert app._batch_dlg is None and app.v_status.get() == "Batch started." and "b1" in app._batch_mine
    assert app._alive(app._queue_win)                  # the queue opens with the batch (user 13.11.)
    app._queue_close()

    # ---- folder: Choose folder…, "N pictures, M skipped", Start; an error of the runner stays in the dialog ----
    folder = Path(tempfile.mkdtemp(prefix="pccomfy-batch-folder-"))
    for n in ("a.png", "b.JPG", "c_upscaled.png", "notes.txt"):
        (folder / n).write_bytes(b"x")
    (folder / "sub").mkdir()
    app.open_batch("folder")
    assert app.cb_batch_save is None and app.v_batch_dry.get() is False
    assert str(app.b_batch_start.cget("state")) == "disabled"
    from tkinter import filedialog
    real_ask = filedialog.askdirectory
    filedialog.askdirectory = lambda **k: str(folder)
    try:
        app.b_batch_folder.invoke()
    finally:
        filedialog.askdirectory = real_ask
    assert app.lbl_batch_count.cget("text") == "2 pictures, 2 skipped", app.lbl_batch_count.cget("text")
    assert str(app.b_batch_start.cget("state")) == "normal"
    runner.fail = ValueError("Choose a folder with pictures.")
    app.b_batch_start.invoke()
    assert app.lbl_batch_err.cget("text") == "Choose a folder with pictures." and app._batch_dlg is not None
    runner.fail = BridgeError("Upscale needs a factor.")
    app.b_batch_start.invoke()
    assert app.lbl_batch_err.cget("text") == "Upscale needs a factor."
    runner.fail = None
    app.b_batch_start.invoke()
    spec = runner.calls[-1][1]
    assert spec.source == "folder" and Path(spec.folder) == folder and spec.dry_run is False and spec.also_save_file is False
    assert app._batch_dlg is None
    app._queue_close()
    empty = tempfile.mkdtemp(prefix="pccomfy-batch-empty-")
    app.open_batch("folder")
    app._batch_set_folder(empty)
    assert app.lbl_batch_count.cget("text") == "0 pictures, 0 skipped" and str(app.b_batch_start.cget("state")) == "disabled"
    app._batch_close()

    # ---- the dry run: the picture and Start remaining N / Cancel batch; an error: only Close (it cancels the batch) ----
    pic = Image.new("RGB", (1600, 800), "red")
    app._batch_event("batch-dry", {"batch": "b1", "job": {}, "results": [], "placed": "layer", "image": pic, "error": ""})
    assert app.b_dry_start.cget("text") == "Start remaining 2" and app.b_dry_cancel.cget("text") == "Cancel batch"
    assert app.b_dry_start.master.pack_slaves() == [app.b_dry_start, app.b_dry_cancel]
    assert app._dry_photo.width() <= app._px(gui_batch.THUMB_PX) and app._dry_photo.height() <= app._px(gui_batch.THUMB_PX)
    assert app.lbl_dry.cget("text") == "Added as a new layer. Is the result ok?"
    app.b_dry_start.invoke()
    assert runner.calls[-1] == ("confirm", "b1") and app._dry_dlg is None
    app._batch_event("batch-dry", {"batch": "b1", "job": {}, "results": [], "placed": "file", "image": pic, "error": ""})
    app.b_dry_cancel.invoke()
    assert runner.calls[-1] == ("discard", "b1") and app._dry_dlg is None
    # X / Escape of the waiting dry run only close the window: no discard, the batch keeps waiting in the queue (user 13.11.)
    app._batch_event("batch-dry", {"batch": "b1", "job": {}, "results": [], "placed": "layer", "image": pic, "error": ""})
    n = len(runner.calls)
    _no_line = [c for c in app._dry_dlg.winfo_children() if c.winfo_class() == "Frame" and str(c.cget("bg")).lower() == gui.ACCENT.lower()]
    assert not _no_line, "the dry run has no blue line on top (user 22.11.: everywhere)"
    _x = [w for w in app._dry_dlg.winfo_children()[0].winfo_children() if str(w.cget("text")) == "✕"][0]   # the head bar comes first (no blue line above it)
    _x.invoke()
    assert app._dry_dlg is None and all(c[0] != "discard" for c in runner.calls[n:]), runner.calls[n:]
    app._batch_event("batch-dry", {"batch": "b1", "job": {}, "results": [], "placed": "", "image": None, "error": "Out of memory"})
    assert app.b_dry_start is None and app.b_dry_cancel is None and app.b_dry_close.cget("text") == "Close"
    assert "Out of memory" in app.lbl_dry.cget("text")
    app.b_dry_close.invoke()
    assert runner.calls[-1] == ("discard", "b1") and app._dry_dlg is None
    # one picture only: no jobs remain; only Close, no question; Close ends the window without cancelling
    saved_jobs, runner._jobs = runner._jobs, [job("j1", "done", started=1.0, finished=43.0)]
    n = len(runner.calls)
    app._batch_event("batch-dry", {"batch": "b1", "job": {}, "results": [], "placed": "layer", "image": pic, "error": ""})
    assert app.b_dry_start is None and app.b_dry_cancel is None and app.b_dry_close.cget("text") == "Close"
    assert app.lbl_dry.cget("text") == "Added as a new layer."
    app.b_dry_close.invoke()
    assert app._dry_dlg is None and len(runner.calls) == n
    runner._jobs = saved_jobs

    # ---- the queue window: every run of the network in one list with "#" and "Sent by" (user 18.11.), batch groups,
    # buttons per status, ComfyUI's queue read in a thread, the participants below ----
    runner._jobs[1]["prompt_id"] = "z"             # j2 is our picture at ComfyUI: place 3, still waiting there
    bridge.comfy.entries = [
        {"prompt_id": "x", "number": 1, "client_id": "other", "owner": "Anna", "kind": "generate", "batch": "", "running": True, "images": 2},
        {"prompt_id": "y", "number": 2, "client_id": "other2", "owner": "", "kind": "", "batch": "", "running": False},
        {"prompt_id": "z", "number": 3, "client_id": "me", "owner": "tester", "kind": "batch", "batch": "b1", "running": False},
        {"prompt_id": "w1", "number": 4, "client_id": "ben", "owner": "Ben", "kind": "batch", "batch": "bb", "running": False},
        {"prompt_id": "w2", "number": 5, "client_id": "ben", "owner": "Ben", "kind": "batch", "batch": "bb", "running": False},
        {"prompt_id": "g", "number": 6, "client_id": "me", "owner": "tester", "kind": "generate", "batch": "", "running": False,
         "variant": "1/2"}]
    app.open_queue()
    win = app._queue_win
    tv = app.tv_queue
    accent = lambda w: [c for c in w.winfo_children() if c.winfo_class() == "Frame" and str(c.cget("bg")).lower() == gui.ACCENT.lower()]   # noqa: E731
    assert not accent(win), "the queue window has no blue line on top (user 22.11.)"
    # flat (user 19.11.): "#" first, "Sent by" second, no folding; what is through stands on top
    # what a run is on the left, how far it is on the right, Status last before the symbols (user 23.11., choice A);
    # "Document" instead of "Picture" (user 23.11.)
    # Progress and Status are one column (user 23.11.): no "prog" any more
    assert tuple(tv.cget("columns"))[:6] == ("idx", "fn", "pic", "who", "time", "status") and "tree" not in str(tv.cget("show"))
    assert "prog" not in tuple(tv.cget("columns"))
    assert tv.heading("pic", "text") == "Document"
    assert tv.heading("status", "text") == "Status" and int(tv.column("status", "width")) == app._q_status_w()
    # Status and the symbols are one block of a fixed width (user 24.11. evening): wide enough for the bar at 100 % and
    # "Cancelled", not dragged, saved or squeezed
    import tkinter.font as tkfont
    body = tkfont.Font(root=app.root, font=gui.font(9))
    assert app._q_status_w() >= max(body.measure(x) for x in ("▰▰▰▰▰ 100 %", "Cancelled")) + app._px(8)
    assert tv.get_children("") == ("j:j1", "j:j5", "j:j6", "j:j2", "j:j3", "j:j4"), tv.get_children("")      # before ComfyUI was read: own only
    assert pump(app, lambda: app._q_entries is not None)
    top = tv.get_children("")
    assert top == ("j:j1", "j:j5", "j:j6", "c:x", "c:y", "j:j2", "c:w1", "c:w2", "c:g", "j:j3", "j:j4"), top   # as they run
    old_order = ("idx", "who", "pic", "status", "fn", "time")
    val = lambda iid: tuple(tv.set(iid, c) for c in old_order)   # noqa: E731   (#, Sent by, Document, Status, Function, Time)
    # another's run that runs keeps "Running" (no bar: ComfyUI sends it only to the one who queued it; its time is in Time)
    assert val("c:x") == ("1", "Anna", "Generate · 2 variants", "Running", "", "0 s"), val("c:x")
    assert val("c:y") == ("2", "unknown", "ComfyUI", "Waiting", "", "starts in <1 min"), val("c:y")   # not from PxC
    assert tv.item("c:x", "tags") == ("other",) and tv.item("j:j2", "tags") in ("", ())
    # a batch picture: its batch in Function (user 19.11.); sent, ComfyUI keeps it waiting; when it starts, from the runs ahead
    # (others' runs count with the average of ours: 42 s)
    assert val("j:j2") == ("3", "tester (you)", "j2.png", "Waiting", "Upscale · batch 2/6", "starts in ~1 min"), val("j:j2")
    assert val("j:j3") == ("~7", "tester (you)", "j3.png", "Waiting", "Upscale · batch 3/6", "starts in ~5 min"), val("j:j3")
    assert val("j:j4")[0] == "" and val("j:j4")[5] == "" and val("j:j1")[3:] == ("Done", "Upscale · batch 1/6", "42 s")
    assert val("j:j6")[3] == "Skipped"
    assert val("c:w1") == ("4", "Ben", "Batch", "Waiting", "", "starts in ~3 min"), val("c:w1")
    assert val("c:g")[:4] == ("6", "tester (you)", "Generate · variant 1 of 2", "Waiting")
    n_text = len(app.Q_TEXT_COLS)
    assert all(v == "" for i in ("c:x", "c:w1", "c:g") for v in tv.item(i, "values")[n_text:])   # nothing to click there
    # no "Participants" list any more (user 24.11.: "Sent by" names who sent each run); connected: no grey line
    assert not hasattr(app, "tv_comfy") and app.lbl_q_conn.winfo_manager() == ""
    app._queue_comfy_show([])                      # nothing at ComfyUI: your pictures waiting in PxC count on from ~1
    assert val("j:j2")[:3] == ("~1", "tester (you)", "j2.png") and val("j:j2")[3].endswith(" %") and val("j:j3")[0] == "~2"
    assert val("j:j3")[5] == "starts in ~2 min", val("j:j3")      # the running one still needs 90 s
    # our own picture that runs: the window's bar as a text bar in Status (user 19.11.; one column since 23.11.)
    app._bar_value = 0.0
    app._queue_fill()
    assert val("j:j2")[3] == "▱▱▱▱▱ 0 %" and val("j:j3")[3] == "Waiting", val("j:j2")
    app._bar_value = 0.6
    app._queue_fill()
    assert val("j:j2")[3] == "▰▰▰▱▱ 60 %", val("j:j2")
    assert gui_queuewin.progress_text(1.0) == "▰▰▰▰▰ 100 %" and gui_queuewin.progress_text(None) == "▱▱▱▱▱ 0 %"
    # our own Generate that runs: its bar too; another's that runs: its time (no pre-placed pictures since 21.11.)
    saved_entries, app._running = app._q_entries, True
    app._run_fn = "Edit · Flux 3"                  # window test 23.11.: the run's function stays in Function
    app._run_doc = "photo.png"                     # ... and Document is the document it was started in (user 23.11.)
    app._q_seen = {"o1": time.time() - 42}
    app._queue_comfy_show([
        {"prompt_id": "g1", "number": 1, "client_id": "me", "owner": "tester", "kind": "generate", "batch": "", "running": True},
        {"prompt_id": "o1", "number": 2, "client_id": "other", "owner": "Anna", "kind": "generate", "batch": "", "running": True}])
    assert val("c:g1")[3] == "▰▰▰▱▱ 60 %" and val("c:o1")[3] == "Running", (val("c:g1"), val("c:o1"))
    assert val("c:o1")[5] == gui_queuewin.duration_text(42), val("c:o1")          # another's run: its time since the start
    assert val("c:g1")[4] == "Edit · Flux 3" and val("c:o1")[4] == "", (val("c:g1"), val("c:o1"))   # not another's run
    assert val("c:g1")[2] == "photo.png" and val("c:o1")[2] != "photo.png", (val("c:g1"), val("c:o1"))
    # ✕ on our own direct run stops it like "Stop run"; another's run has none (window test 24.11.: "der erste lauf kann
    # in der queue nicht abgebrochen werden")
    assert app.tv_queue.set("c:g1", "x") == "✕" and app._row_actions("c:g1") == {"x": "cancel"}, app.tv_queue.set("c:g1", "x")
    assert app.tv_queue.set("c:o1", "x") == "" and app._row_actions("c:o1") == {}
    stopped = []
    app.stop = lambda: stopped.append(1)
    app._queue_do("cancel", "c:o1")
    assert stopped == [], "never another's run"
    app._queue_do("cancel", "c:g1")
    assert stopped == [1], stopped
    del app.stop
    # the run ends cancelled: it stays as "Cancelled" with its whole time until "Clear finished" (user 23.11.)
    app._run_t0 = time.time() - 65
    app._queue_note_own_done("Cancelled.")
    app._queue_fill()
    assert val("o:1")[:5] == ("", "tester (you)", "photo.png", "Cancelled", "Edit · Flux 3"), val("o:1")
    assert val("o:1")[5] == gui_queuewin.duration_text(65), val("o:1")
    # ComfyUI's queue as last read still lists the stopped run: it shows once, as Cancelled (window test 23.11. evening)
    assert not app.tv_queue.exists("c:g1") and app.tv_queue.exists("c:o1"), app.tv_queue.get_children("")
    app._queue_note_own_done("Done.")            # no second row without a new run
    assert len(app._q_own_done) == 1
    app._run_t0 = time.time() - 3
    app._queue_note_own_done("Done · seed 5 · 1 layer · 3 s")
    assert [d["status"] for d in app._q_own_done] == ["Cancelled", "Done"]
    # ↻ on the row of a cancelled direct run (window test 23.11. late: after "Stop batch" only the queued picture had it):
    # it sends the same settings with the same picture of the same document as a new job; a done run has no ↻
    app._queue_fill()
    assert tv.set("o:1", "x") == "" and tv.set("o:2", "x") == "", "rows without kept settings: no ↻"
    from types import SimpleNamespace
    from PIL import Image as _Img
    kept_pic = _Img.new("RGB", (8, 6), "blue")
    app._run_retry = {"req": SimpleNamespace(preset="", mode="edit", run_no=0, group_name=""), "label": "Edit · Flux 3",
                      "model": "Flux 3", "pic": kept_pic, "index": 4, "name": "photo.png", "capture": object()}
    app._run_t0 = time.time() - 9
    app._queue_note_own_done("Cancelled.")
    assert getattr(app, "_run_retry", None) is None and "capture" not in app._q_own_done[-1]["retry"]
    app._queue_fill()
    assert tv.set("o:3", "x") == "↻" and app._row_actions("o:3") == {"x": "retry"}, tv.set("o:3", "x")
    before = len(app.runner.calls)
    app._queue_do("retry", "o:3")
    spec = app.runner.calls[before][1]
    assert app.runner.calls[before][0] == "start" and spec.copies == 1 and spec.kind == gui_batch.jobqueue.K_GENERATE
    assert spec.source == gui_batch.jobqueue.SOURCE_ACTIVE and spec.label == "Edit · Flux 3" and spec.model == "Flux 3"
    assert spec.shared["done"].is_set() and spec.shared["index"] == 4 and spec.shared["name"] == "photo.png"
    assert spec.shared["pic"].size == (8, 6) and spec.request is not app._q_own_done[-1].get("req")
    assert app._q_own_done[-1]["retry"] is None and tv.set("o:3", "x") == "", "↻ once: the new job has its own row"
    app._queue_do("retry", "o:3")
    assert len(app.runner.calls) == before + 1
    # a run that ends well keeps no ↻
    app._run_retry = {"req": SimpleNamespace(preset="", mode="edit"), "label": "x", "model": "", "pic": None}
    app._run_t0 = time.time() - 2
    app._queue_note_own_done("Done · seed 1 · 1 layer · 2 s")
    assert app._q_own_done[-1]["retry"] is None
    del app._q_own_done[2:]
    # finished rows keep their place (user 23.11. late): Edit ×3, the direct run (started at 100) runs, its 2/3 was
    # cancelled, 3/3 waits; another's run came later. 2/3 stays between 1/3 and 3/3, a Done from before stays first
    far = float("inf")
    app._q_batches = {"g9": {"id": "g9", "created": 100.5}}
    rows9 = [[1, "c:p1", (), (), (), ("entry", {"prompt_id": "p1", "client_id": "me"})],
             [-far, "j:v2", (), (), (), ("job", {"batch_id": "g9", "order": 1})],
             [2, "j:v3", (), (), (), ("job", {"batch_id": "g9", "order": 2})],
             [3, "c:z", (), (), (), ("entry", {"prompt_id": "z", "client_id": "other"})],
             [-far, "o:7", (), (), (), ("own", {"t0": 50.0})]]
    t0_was, seen_was = getattr(app, "_run_t0", None), getattr(app, "_q_seen", {})
    app._run_t0, app._q_seen = 100.0, {"z": 200.0}
    assert [r[1] for r in app._queue_order(rows9, [], "me")] == ["o:7", "c:p1", "j:v2", "j:v3", "c:z"]
    app._run_t0, app._q_seen = t0_was, seen_was
    # ×3 of a direct run: the run is 1/3, its queued pictures 2/3 and 3/3 (window test 23.11. late: they read 1/2, 2/2);
    # a queued Generate ×2 of its own counts 1/2, 2/2
    saved_jobs, saved_batches = runner._jobs, runner._batches
    runner._jobs = [job("v1", "waiting", bid="g3", mode="edit"), job("v2", "waiting", bid="g3", mode="edit"),
                    job("w1", "waiting", bid="g4", mode="edit"), job("w2", "waiting", bid="g4", mode="edit")]
    runner._batches = [{"id": "g3", "kind": jobqueue.K_GENERATE, "label": "Edit · Flux 3", "mode": "edit", "state": "running"},
                       {"id": "g4", "kind": jobqueue.K_GENERATE, "label": "Edit · Flux 3", "mode": "edit", "state": "running"}]
    app._rest_of = {"g3": 3}
    app._queue_fill()
    assert [tv.set(i, "fn") for i in ("j:v1", "j:v2", "j:w1", "j:w2")] == [
        "Edit · Flux 3 · 2/3", "Edit · Flux 3 · 3/3", "Edit · Flux 3 · 1/2", "Edit · Flux 3 · 2/2"]
    runner._jobs, runner._batches = saved_jobs, saved_batches
    app._rest_of = {}
    # the Status word in colour (user 23.11. evening): Done green, Cancelled and Error red, nothing else coloured; only
    # the rows in sight get a word (the list in this test is short), and the words follow a scroll
    app._queue_fill()

    def marks():
        for _ in range(3):
            app.root.update()
        app._queue_marks()
        shown = [(str(m.cget("text")), str(m.cget("fg"))) for m in app._q_marks if m.winfo_manager()]
        want = [(tv.set(i, "status"), gui_queuewin.Q_STATUS_COLORS[tv.set(i, "status")]) for i in tv.get_children("")
                if tv.set(i, "status") in gui_queuewin.Q_STATUS_COLORS and tv.bbox(i, "status")]
        assert shown == want, (shown, want)
        return shown
    seen = set()
    for iid in ("j:j1", "o:1", "j:j5", "o:2"):
        tv.see(iid)
        seen |= set(marks())
    tv.see("o:1")                          # finished rows stand where they came, not on top (23.11. late)
    marks()
    if tv.bbox("o:1"):
        assert {("Cancelled", gui.ERROR), ("Error", gui.ERROR), ("Done", gui.DONE_GREEN)} <= seen, seen
        app.root.update()
        lab = next(m for m in app._q_marks if m.winfo_manager())
        iid = tv.identify_row(lab.winfo_y() + 2)
        lab._q_press(type("E", (), {"x": 3, "y": 3, "x_root": 0, "y_root": 0})())
        app._queue_release(type("E", (), {"x": 3, "y": 3, "x_root": 0, "y_root": 0})())
        app.root.update()
        assert tv.selection() == (iid,), (tv.selection(), iid)        # a click on the word selects its row
        tv.see(iid)
        app.root.update()
        app._queue_marks()                  # (<<TreeviewSelect>> calls it; a hidden list gets no virtual events)
        y = tv.bbox(iid, "status")[1]
        on = [m for m in app._q_marks if m.winfo_manager() and int(m.place_info()["y"]) == y]
        assert on and str(on[0].cget("bg")) == gui.ACCENT, "the selected row: the word on the blue of the selection"
        tv.selection_remove(iid)
    else:
        print("(status colours: list not on screen, checked without boxes)")
    app._q_own_done = []
    app._running = False
    # ×n one after the other (Sketch, Scribble, Multi Edit; user 24.11. evening, choice C): a row per variant at once, the
    # running one with its own part of the bar, ✕ on a waiting one skips only it, ✕ on the running one is Stop run
    from pccomfy.bridge import Bridge
    bridge.skip_variant = lambda k: Bridge.skip_variant(bridge, k)
    t = time.time()
    bridge.seq_rows = [{"status": "running", "t0": t - 5, "t1": None}, {"status": "waiting", "t0": None, "t1": None},
                       {"status": "waiting", "t0": None, "t1": None}]
    app._running, app._run_seq, app._run_fn, app._run_doc, app._run_t0 = True, 3, "Sketch to image · Qwen", "s.png", t - 5
    app._bar_value = 0.2                           # 0.2 × 3 = 0.6 of variant 1
    app._queue_comfy_show([
        {"prompt_id": "s1", "number": 1, "client_id": "me", "owner": "tester", "kind": "generate", "batch": "", "running": True,
         "variant": "1/3"}])
    seq_iids = [i for i in app.tv_queue.get_children("") if i.startswith(("s:", "c:s1"))]
    assert seq_iids == ["s:1", "s:2", "s:3"], app.tv_queue.get_children("")      # the entry at ComfyUI is row 1 itself
    assert val("s:1")[:5] == ("1", "tester (you)", "s.png", "▰▰▰▱▱ 60 %", "Sketch to image · Qwen · 1/3"), val("s:1")
    assert val("s:2")[3:5] == ("Waiting", "Sketch to image · Qwen · 2/3") and val("s:3")[4].endswith("3/3"), val("s:2")
    assert all(app.tv_queue.set(i, "x") == "✕" for i in seq_iids)
    stopped = []
    app.stop = lambda: stopped.append(1)
    app._queue_do("cancel", "s:2")                 # skips variant 2 only
    assert stopped == [] and [r["status"] for r in bridge.seq_rows] == ["running", "cancelled", "waiting"]
    assert val("s:2")[3] == "Cancelled" and app.tv_queue.set("s:2", "x") == "", val("s:2")
    app._queue_do("cancel", "s:1")                 # the running one: Stop run
    assert stopped == [1] and bridge.seq_rows[0]["status"] == "running"
    del app.stop
    # the rows stay one block 1/3, 2/3, 3/3 where the variant at ComfyUI stands, a stopped or skipped one keeps its place
    # (window test 24.11. late evening: "ein teillauf wandert bei klick auf x plötzlich nach oben")
    saved_seq = [dict(r) for r in bridge.seq_rows]
    bridge.seq_rows[0].update(status="cancelled", t1=t - 3)
    bridge.seq_rows[2].update(status="running", t0=t - 3)
    app._queue_comfy_show([
        {"prompt_id": "o9", "number": 1, "client_id": "other", "owner": "Anna", "kind": "generate", "batch": "", "running": True},
        {"prompt_id": "s3", "number": 2, "client_id": "me", "owner": "tester", "kind": "generate", "batch": "", "running": False,
         "variant": "3/3"}])
    order = [i for i in app.tv_queue.get_children("") if i.startswith(("s:", "c:o9"))]
    assert order == ["c:o9", "s:1", "s:2", "s:3"], order
    assert val("s:1")[3] == val("s:2")[3] == "Cancelled" and val("s:3")[0] == "2", (val("s:1"), val("s:3"))
    app._queue_comfy_show([])                      # between two variants (nothing of ours at ComfyUI): the block stays
    order = [i for i in app.tv_queue.get_children("") if i.startswith("s:")]
    assert order == ["s:1", "s:2", "s:3"], order
    for r, old in zip(bridge.seq_rows, saved_seq):
        r.clear()
        r.update(old)
    app._q_foreign_done = [d for d in app._q_foreign_done if d["prompt_id"] != "o9"]
    # the run ends: every variant keeps its row with its outcome
    bridge.seq_rows[0].update(status="cancelled", t1=t - 2)
    bridge.seq_rows[2].update(status="done", t0=t - 2, t1=t)
    app._running = False
    app._queue_note_own_done("Done · seed 1 · 1 layer · 5 s")
    app._queue_fill()
    own = [i for i in app.tv_queue.get_children("") if i.startswith("o:")]
    assert [val(i)[3:5] for i in own] == [("Cancelled", "Sketch to image · Qwen · 1/3"), ("Cancelled", "Sketch to image · Qwen · 2/3"),
                                          ("Done", "Sketch to image · Qwen · 3/3")], [val(i) for i in own]
    assert val(own[2])[5] == gui_queuewin.duration_text(2) and app._run_seq == 0, val(own[2])
    assert all(d["retry"] is None for d in app._q_own_done)
    del bridge.skip_variant
    bridge.seq_rows = []
    app._q_own_done = []
    # which direct runs keep their settings for ↻: only one picture of a function that can wait in the queue
    mode_was = app.v_mode.get()
    one = SimpleNamespace(variants=1, mode="edit")
    app.v_mode.set("inpaint")
    assert app._retry_keep(one, [one]) is None, "Fill never waits in the queue: no ↻"
    app.v_mode.set("edit")
    k = app._retry_keep(one, [one])
    assert k is not None and k["req"] is not one and k["pic"] is None and k["label"], k
    assert app._retry_keep(one, [one, one]) is None, "a comparison series: no ↻"
    app.v_mode.set(mode_was)
    assert app._q_movable(app._q_jobs["j3"]) and app._q_movable(app._q_jobs["j4"])
    app._bar_value = 0.0
    app._queue_comfy_show(saved_entries)
    runner._jobs[1].pop("prompt_id")
    # Paket 3 (user 19.11., choice A): a run of another that PxC saw running stays as "Done" with the time since PxC saw it
    # start, read-only, on top with the finished ones; not our own Generate (g1), not one only seen waiting (y), nothing
    # noted when ComfyUI could not be read
    assert [d["prompt_id"] for d in app._q_foreign_done] == ["x", "o1"], app._q_foreign_done
    assert val("d:x")[1:4] == ("Anna", "Generate · 2 variants", "Done"), val("d:x")
    assert val("d:o1") == ("", "Anna", gui_queuewin.generate_label({}), "Done", "", "42 s"), val("d:o1")
    assert tv.item("d:o1", "tags") == ("other",) and all(v == "" for v in tv.item("d:o1", "values")[len(app.Q_TEXT_COLS):])
    top = tv.get_children("")
    # finished rows keep their place by when they came (user 23.11. late, replaces "through: on top"): o1 started 42 s
    # ago, x later; the jobs of the test were queued before both (time 0)
    assert top.index("j:j4") < top.index("d:o1") < top.index("d:x"), top
    app._queue_comfy_show(None)
    app._queue_comfy_show([])                      # after a failed read nothing is said about what ended
    app._queue_note_foreign_done([{"prompt_id": "b9", "client_id": "ben", "owner": "Ben", "kind": "batch", "running": True}], [])
    assert [d["prompt_id"] for d in app._q_foreign_done] == ["x", "o1", "b9"] and app._foreign_what(app._q_foreign_done[2]) == "Batch"
    app._q_foreign_done.pop()
    app._queue_note_foreign_done([], [{"prompt_id": "x", "running": True}])     # back at ComfyUI: not through after all
    assert [d["prompt_id"] for d in app._q_foreign_done] == ["o1"], app._q_foreign_done
    app._queue_comfy_show(saved_entries)
    state = lambda: {k: str(b.cget("state")) == "normal" for k, b in app.q_buttons.items()}   # noqa: E731
    # Pause all / Resume all act on every queued picture without a selection; no Cancel batch under the list (user 25.11.)
    assert set(app.q_buttons) == {"pause_all", "resume_all", "clear", "clear_all"}, set(app.q_buttons)
    tv.selection_set(())
    app.root.update()
    app._queue_buttons()
    assert state()["pause_all"] and state()["resume_all"], state()           # j3 waits, j4 is paused
    n = len(runner.calls)
    app._queue_do("pause_all")
    assert runner.calls[n:] == [("pause_batch", "b1")], runner.calls[n:]
    n = len(runner.calls)
    app._queue_do("resume_all")
    assert runner.calls[n:] == [("resume_batch", "b1")], runner.calls[n:]
    # what a row can do sits in the row (user 13.11.): ⏸ / ▶ and ✕ in the last two columns; ↻ stands where ✕ was (25.11.)
    assert app.Q_ACT_COLS == ("pr", "x")
    acts = lambda iid: tv.item(iid, "values")[len(app.Q_TEXT_COLS):]          # noqa: E731
    assert acts("j:j3") == ("⏸", "✕"), acts("j:j3")                 # waiting: pause, cancel
    assert acts("j:j4") == ("▶", "✕"), acts("j:j4")                 # paused: resume, cancel
    assert acts("j:j2") == ("", "✕"), acts("j:j2")                  # running: cancel only
    assert acts("j:j1") == ("", ""), acts("j:j1")                   # done: nothing
    assert acts("j:j5") == ("", "↻"), acts("j:j5")                  # failed: retry, in the column of ✕
    assert acts("j:j6") == ("", ""), acts("j:j6")                   # skipped: no retry
    app.tv_queue.selection_set("j:j5")
    n = len(runner.calls)
    app._queue_key_act("x")                                          # Delete on a failed row: never a retry
    assert runner.calls[n:] == [], runner.calls[n:]
    for iid, col, want in (("j:j3", "pr", ("pause", "j3")), ("j:j3", "x", ("cancel", "j3")), ("j:j4", "pr", ("resume", "j4")),
                           ("j:j5", "x", ("retry", "j5"))):
        app._queue_do(app._row_actions(iid)[col], iid)
        assert runner.calls[-1] == want, (iid, col, runner.calls[-1])
    # ⏸ keeps the row where it is, ▶ too (bug 23.11.: a paused picture went to the end of the list and the next one slid
    # under the mouse, so it looked as if another row was paused)
    runner._jobs.insert(3, job("j7", "waiting"))
    app._queue_fill()
    before = tv.get_children("")
    assert before.index("j:j3") < before.index("j:j7") < before.index("j:j4"), before

    def set_status(jid, st):
        next(j for j in runner._jobs if j["id"] == jid)["status"] = st
    real_pause, real_resume = runner.pause, runner.resume
    runner.pause = lambda j: (set_status(j, "paused"), runner._rec("pause", j))[1]
    runner.resume = lambda j: (set_status(j, "waiting"), runner._rec("resume", j))[1]
    app._queue_do(app._row_actions("j:j3")["pr"], "j:j3")
    assert runner.calls[-1] == ("pause", "j3") and tv.get_children("") == before, tv.get_children("")
    assert acts("j:j3")[0] == "▶" and val("j:j3")[0] == "" and val("j:j7")[0].startswith("~"), (val("j:j3"), val("j:j7"))
    app._queue_do(app._row_actions("j:j3")["pr"], "j:j3")
    assert runner.calls[-1] == ("resume", "j3") and tv.get_children("") == before and acts("j:j3")[0] == "⏸"
    runner.pause, runner.resume = real_pause, real_resume
    runner._jobs.pop(3)
    app._queue_fill()
    # keys (user 19.11.): Delete = ✕, Space = pause / resume of the selected row; nothing where the row offers nothing
    tv.selection_set("j:j3")
    assert app._queue_key_act("x") == "break" and runner.calls[-1] == ("cancel", "j3")
    app._queue_key_act("pr")
    assert runner.calls[-1] == ("pause", "j3")
    tv.selection_set("j:j4")
    app._queue_key_act("pr")
    assert runner.calls[-1] == ("resume", "j4")
    n = len(runner.calls)
    tv.selection_set("j:j1")                       # a done picture: nothing
    app._queue_key_act("x")
    assert len(runner.calls) == n
    assert tv.bind("<KeyPress-Delete>") and tv.bind("<KeyPress-space>")
    # a click on a symbol: the real cell under the mouse (the windows must be on screen for that)
    app.root.deiconify()
    win.deiconify()
    for _ in range(3):
        app.root.update()
    x, y, w, h = tv.bbox("j:j3", "x")
    ev = type("E", (), {"x": x + w // 2, "y": y + h // 2})()
    assert app._queue_cell(ev) == ("j:j3", "x")
    assert app._queue_press(ev) == "break" and runner.calls[-1] == ("cancel", "j3")
    x, y, w, h = tv.bbox("j:j1", "x")                             # a done row: its ✕ column is empty, nothing happens
    n = len(runner.calls)
    assert app._queue_press(type("E", (), {"x": x + w // 2, "y": y + h // 2})()) is None and len(runner.calls) == n
    # drag and drop instead of Up / Down: j4 dragged above j3 moves it one place up
    x, y, w, h = tv.bbox("j:j4", "pic")
    app._queue_press(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert app._q_drag and app._q_drag["iid"] == "j:j4"
    x, y, w, h = tv.bbox("j:j3", "pic")
    app._queue_motion(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert tv.index("j:j4") < tv.index("j:j3")
    app._queue_fill()                                             # a runner event while dragging: no redraw under the mouse
    assert tv.index("j:j4") < tv.index("j:j3")
    app._queue_release(None)
    assert runner.calls[-1] == ("move", "j4", -1), runner.calls[-1]
    assert app._q_drag is None
    x, y, w, h = tv.bbox("j:j2", "pic")                            # the running picture cannot be dragged
    app._queue_press(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert app._q_drag is None

    # the columns always fill the list (user 13.11.): a column set very wide gives the room back, the symbols stay
    cols = tuple(tv.cget("columns"))
    F = gui_queuewin.Q_FILLER

    def widths():
        return {c: int(tv.column(c, "width")) for c in cols}

    def fills():
        return abs(sum(widths().values()) - (tv.winfo_width() - gui_queuewin.Q_TREE_INSET)) <= 1
    want0 = dict(app._q_want)
    assert "status" not in want0, want0
    app._q_want["time"] = app._px(900)
    app._queue_fit_cols()
    assert sum(widths().values()) <= tv.winfo_width() - gui_queuewin.Q_TREE_INSET + 1, (widths(), tv.winfo_width())
    assert widths()[F] >= app._px(gui_queuewin.Q_PICTURE_MIN)
    assert all(widths()[c] == app._px(24) for c in app.Q_ACT_COLS)
    app._q_want.update(want0)
    app._queue_fit_cols()
    assert fills() and widths()["time"] == want0["time"] and widths()["status"] == app._q_status_w(), widths()   # no gap, the set width is back
    before = widths()
    for _ in range(3):
        app.root.update()
    assert widths() == before, (before, widths())        # Tk leaves them as they are: nothing squeezed, nothing jumps
    # a heading line dragged (user 19.11.: the columns jumped): PxC drags it, the column gets exactly the width set, the
    # neighbour on the right gives way, nothing jumps on release
    w0 = widths()
    edge = sum(w0[c] for c in ("idx", "fn", "pic", "who"))
    assert app._queue_sep_col(edge + 2) == "who" and app._queue_sep_col(edge - 2) == "who"
    app._q_coldrag = {"col": "who", "x": edge, "w": w0}
    assert app._queue_motion(type("E", (), {"x": edge + 20, "y": 5})()) == "break"     # Tk's own column drag stays out
    w1 = widths()
    assert w1["who"] == w0["who"] + 20 and w1["time"] == w0["time"] - 20, (w0, w1)
    assert all(w1[c] == w0[c] for c in ("idx", "fn", "pic", "status")), (w0, w1)
    app._queue_release(None)
    assert widths() == w1 and app._q_coldrag is None, "release changes nothing"
    # far to the right: the neighbours give way down to their minimum, then the line stops
    app._q_coldrag = {"col": "who", "x": edge, "w": widths()}
    app._queue_motion(type("E", (), {"x": edge + 2000, "y": 5})())
    app._queue_release(None)
    w2 = widths()
    assert w2["time"] == app._q_min("time") and w2["status"] == app._q_status_w() and fills(), w2
    assert all(w2[c] == app._px(24) for c in app.Q_ACT_COLS)
    # narrower again: the neighbour on the right takes the room
    edge = sum(w2[c] for c in ("idx", "fn", "pic", "who"))
    app._q_coldrag = {"col": "who", "x": edge, "w": w2}
    app._queue_motion(type("E", (), {"x": edge - 30, "y": 5})())
    app._queue_release(None)
    w3 = widths()
    assert w3["who"] == w2["who"] - 30 and w3["time"] == w2["time"] + 30 and w3[F] == w2[F], (w2, w3)
    # "Function" wider: Document, its neighbour, gives the room
    edge = sum(w3[c] for c in ("idx", "fn"))
    app._q_coldrag = {"col": "fn", "x": edge, "w": w3}
    app._queue_motion(type("E", (), {"x": edge + 10, "y": 5})())
    app._queue_release(None)
    w3b = widths()
    assert w3b["fn"] == w3["fn"] + 10 and w3b[F] == w3[F] - 10 and fills(), (w3, w3b)
    # "Time" has the fixed Status on its right (24.11. evening): Document gives the room; Status's own edge is no line to drag
    edge = sum(w3b[c] for c in app.Q_TEXT_COLS[:-1])
    assert app._queue_sep_col(edge) == "time"
    app._q_coldrag = {"col": "time", "x": edge, "w": w3b}
    app._queue_motion(type("E", (), {"x": edge + 15, "y": 5})())
    app._queue_release(None)
    w4 = widths()
    assert w4["time"] == w3b["time"] + 15 and w4[F] == w3b[F] - 15 and w4["status"] == w3b["status"] and fills(), (w3b, w4)
    assert app._queue_sep_col(sum(w4[c] for c in app.Q_TEXT_COLS)) is None, "Status keeps its width"
    assert app._queue_col_at(sum(w4[c] for c in app.Q_TEXT_COLS) - 5) is None, "no autofit on Status"
    # the edge of a symbol column is no line to drag
    assert app._queue_sep_col(sum(w4.values()) - app._px(24)) is None
    # the widths set are kept for the next start, in px before the scaling (user 19.11.)
    sc = app._q_scale()
    assert app.state["queue_cols"] == {c: round(w4[c] / sc) for c in app.Q_TEXT_COLS if c not in (F, "status")}, app.state["queue_cols"]
    # light lines between the columns, in the heading and in the rows (user 19.11.)
    app.root.update()
    placed = [ln for pair in app._q_lines for ln in pair if ln.winfo_manager() == "place"]
    # none between the symbols (user 19.11.) and none after Status, the last text column (window test 23.11. evening)
    assert len(placed) == 2 * (len(app.Q_TEXT_COLS) - 1), len(placed)
    hl, bl = app._q_lines[0]
    assert int(hl.place_info()["x"]) == w4["idx"] - 1 and hl.cget("bg") == gui_queuewin.Q_GRID_HEAD
    assert bl.cget("bg") == gui_queuewin.Q_GRID_BODY and int(bl.place_info()["y"]) == int(hl.place_info()["height"]) > 4
    # a double-click on a heading: the column as wide as its longest text (user 19.11.)
    tv.set("j:j1", "fn", "Upscale · batch 12/60 x")
    import tkinter.font as tkfont
    need = tkfont.Font(root=app.root, font=gui.font(9)).measure(tv.set("j:j1", "fn")) + app._px(14)
    x_fn = widths()["idx"] + 5
    hy = app._queue_head_h() // 2
    if tv.identify_region(x_fn, hy) == "heading":
        assert app._queue_double(type("E", (), {"x": x_fn, "y": hy})()) == "break"
    else:
        app._queue_autofit("fn")
    assert widths()["fn"] == need and fills(), (widths()["fn"], need)
    assert app._queue_double(type("E", (), {"x": x_fn, "y": tv.bbox("j:j3", "fn")[1] + 3})()) is None   # a row: no autofit
    # right-click on a heading: Reset column widths (user 19.11.)
    app._queue_reset_cols()
    assert {c: widths()[c] for c in app.Q_TEXT_COLS if c not in (F, "status")} == {
        c: app._px(v) for c, v in gui_queuewin.Q_COL_DEFAULT.items() if c not in (F, "status")}
    assert "queue_cols" not in app.state and fills()
    # widths saved before 24.11. evening: a saved Status (or Progress) width is no longer used
    app.state["queue_cols"] = {"status": 80, "prog": 90, "time": 100}
    assert app._q_saved_cols() == {"time": app._px(100)}, app._q_saved_cols()
    del app.state["queue_cols"]
    if tv.identify_region(x_fn, hy) == "heading":
        assert app._queue_head_menu(type("E", (), {"x": x_fn, "y": hy, "x_root": 10, "y_root": 10})()) == "break"
        assert [e.get("label") for e in app._q_menu.entries] == ["Reset column widths"]
        app._q_menu.unpost() if hasattr(app._q_menu, "unpost") else None
    # the window narrower: the text columns give way; wider again: they get the widths set back
    set_w = {c: widths()[c] for c in app.Q_TEXT_COLS if c != F}
    win_w = app._queue_win.winfo_width()
    app._queue_win.geometry(f"{app._px(360)}x{app._queue_win.winfo_height()}")
    for _ in range(3):
        app.root.update()
    app._queue_fit_cols()
    assert widths()[F] == app._px(gui_queuewin.Q_PICTURE_MIN) and widths()["time"] < set_w["time"], widths()
    app._queue_win.geometry(f"{win_w}x{app._queue_win.winfo_height()}")
    for _ in range(3):
        app.root.update()
    app._queue_fit_cols()
    assert {c: widths()[c] for c in app.Q_TEXT_COLS if c != F} == set_w and fills(), (widths(), set_w)
    # the separator of a symbol column can't be dragged
    app.root.update()
    x, y, w, h = tv.bbox("j:j3", "pr")
    hy = 5                                          # in the heading row
    sep = type("E", (), {"x": x + w - 1, "y": hy})()
    if tv.identify_region(sep.x, sep.y) == "separator":
        assert app._queue_press(sep) == "break"
    # the heading of the lower list (user 13.11.)
    heads = [wd for wd in app.tv_queue.master.winfo_children() if wd.winfo_class() == "TLabel"]
    assert not any(str(wd.cget("text")) == "Participants" for wd in heads), "the Participants list is gone (user 24.11.)"
    # Q opens the queue, but not while typing in a field
    app._queue_close()
    app.t_prompt.focus_force()
    app.root.update()
    assert app._queue_key() is None and app._queue_win is None
    app.root.focus_force()
    app.root.update()
    assert app._queue_key() == "break" and app._alive(app._queue_win)
    assert app._queue_key() == "break" and app._queue_win is None, "Q again closes it (toggle, user 13.11.)"
    assert app._queue_key() == "break" and app._alive(app._queue_win)
    app.root.update()                              # the window's own raise (after_idle) first, it takes the focus
    app.t_prompt.focus_force()
    app.root.update()
    assert app._queue_key() is None and app._alive(app._queue_win), "typing a q into the prompt does not toggle the queue"
    assert app.root.bind("<Escape>") and app.root.bind("<KeyPress-q>") and app._queue_win.bind("<KeyPress-q>")
    assert app._escape_key() == "break" and app._queue_win is None, "Escape closes the queue instead of stopping a run"
    # Escape never stops a run (user 20.11.): with no queue and no settings window open it does nothing
    stopped = []
    app.stop, app.stop_all = (lambda: stopped.append("stop")), (lambda: stopped.append("all"))
    assert app._escape_key() is None and not stopped, "Escape must not stop a run"
    del app.stop, app.stop_all
    # Q many times in a row (user 13.11.: after a few rounds Q did nothing): the queue takes the focus when it opens, and
    # closing it gives the focus back to the plugin window, never into a field (here the prompt had it before)
    app.t_prompt.focus_force()
    app.root.update()
    app.open_queue()                               # from the menu, while the prompt has the focus
    app.root.update()
    for i in range(8):
        was_open = app._alive(app._queue_win)
        if was_open:
            app._queue_win.focus_force()
            app.root.update()
        assert app._queue_key() == "break", f"Q round {i + 1}"
        app.root.update()
        if was_open:
            f = app.root.focus_get()
            assert f is not None and f.winfo_toplevel() is app.root, f"round {i + 1}: the focus is back in the plugin ({f})"
            assert f.winfo_class() not in ("Text", "Entry", "TEntry"), f"round {i + 1}: not in a field, a Q is no letter there"
        else:
            assert app._alive(app._queue_win), f"round {i + 1}: Q opens the queue again"
    app._queue_close()
    app.open_queue()
    assert app._alive(app._queue_win)
    win = app._queue_win
    tv = app.tv_queue
    for _ in range(3):
        app.root.update()

    def pick(iid):
        tv.selection_set(iid)
        app._queue_buttons()
    pick("j:j3")                                   # Pause all / Resume all: every batch, whatever row is selected (25.11.)
    s = state()
    assert s["pause_all"] and s["resume_all"] and s["clear"], s
    for key in ("pause_all", "resume_all"):
        pick("j:j3")
        app.q_buttons[key].invoke()
        assert runner.calls[-1] == (key.replace("_all", "_batch"), "b1"), (key, runner.calls[-1])
    pick("j:j6")                                   # skipped: the reason under the list
    assert "too large" in app.lbl_q_detail.cget("text")
    pick("j:j5")                                   # failed: retry refused after a restart: said so
    assert app.lbl_q_detail.cget("text") == "ComfyUI said no"
    app._queue_do("retry", "j:j5")
    assert runner.calls[-1] == ("retry", "j5") and app.lbl_q_detail.cget("text").startswith("Can't retry")
    # resizable: the grip in the corner, the list and "At ComfyUI" in a pane with a line to drag (user 13.11.)
    assert app.lbl_q_grip.winfo_manager() == "place" and not hasattr(app, "pw_queue")      # one list, the whole height
    # the queue moves with the plugin (user 13.11.)
    app.root.update()
    qx, qy = win.winfo_x(), win.winfo_y()
    rx, ry = app.root.winfo_x(), app.root.winfo_y()
    app.root.geometry(f"+{rx + 40}+{ry + 20}")
    app.root.update()
    app._queue_follow()
    app.root.update()
    assert (win.winfo_x() - qx, win.winfo_y() - qy) == (app.root.winfo_x() - rx, app.root.winfo_y() - ry), (win.winfo_x(), qx)
    app.root.withdraw()
    # "Clear finished" takes only Done; "Clear all" Cancelled and Error too (user 24.11.)
    app._q_own_done = [{"id": 91, "doc": "a.png", "fn": "Edit", "status": "Done", "took": "", "pids": [], "t0": 1.0},
                       {"id": 92, "doc": "a.png", "fn": "Edit", "status": "Cancelled", "took": "", "pids": [], "t0": 2.0}]
    app.q_buttons["clear"].invoke()
    assert runner.calls[-1] == ("clear", (jobqueue.DONE,)), runner.calls[-1]
    assert [d["id"] for d in app._q_own_done] == [92], "a cancelled own run stays on Clear finished"
    assert str(app.q_buttons["clear_all"].cget("state")) == "normal"
    app.q_buttons["clear_all"].invoke()
    assert runner.calls[-1] == ("clear", jobqueue.FINISHED) and app._q_own_done == [], runner.calls[-1]
    # "Clear finished" removes the finished runs of others too (user 19.11.); with only those, it can be pressed
    assert app._q_foreign_done == [] and not any(i.startswith("d:") for i in tv.get_children("")), tv.get_children("")
    app._q_foreign_done = [{"prompt_id": "q", "owner": "Ben", "kind": "batch", "started": None, "finished": 1.0}]
    saved_jobs, runner._jobs = runner._jobs, []
    app._queue_fill()
    assert tuple(tv.set("d:q", c) for c in ("idx", "who", "pic", "status", "fn", "time")) == ("", "Ben", "Batch", "Done", "", "") and str(app.q_buttons["clear"].cget("state")) == "normal"
    app.q_buttons["clear"].invoke()
    assert app._q_foreign_done == [] and str(app.q_buttons["clear"].cget("state")) == "disabled"
    runner._jobs = saved_jobs
    app.open_queue()                               # a second time: the same window, in front
    assert app._queue_win is win
    reads = bridge.comfy.reads
    app._queue_close()
    assert app._queue_win is None and app._q_tick is None
    time.sleep(0.1)
    app._queue_comfy_tick()                        # closed: no more reading of ComfyUI
    time.sleep(0.1)
    assert bridge.comfy.reads == reads
    bridge.comfy.fail = True
    app.open_queue()
    # no ComfyUI (user 19.11.): alone (address on this PC) the hint asks whether it runs, in a network where to set it
    assert pump(app, lambda: str(app.lbl_q_conn.cget("text")) == gui_queuewin.Q_NOT_CONNECTED_LOCAL and bool(app.lbl_q_conn.winfo_manager()))
    assert gui_queuewin.Q_NOT_CONNECTED_LOCAL == "ComfyUI not connected. Is ComfyUI running?"
    app._queue_close()
    bridge.comfy.url = "http://192.168.1.20:8188"
    app.open_queue()
    assert pump(app, lambda: str(app.lbl_q_conn.cget("text")) == gui_queuewin.Q_NOT_CONNECTED_NET)
    assert gui_queuewin.Q_NOT_CONNECTED_NET == "ComfyUI not connected. Set its host address in: Settings › Other settings."
    del bridge.comfy.url
    app._queue_close()
    bridge.comfy.fail = False

    # ---- Generate (and Save, Copy) locked while a batch is on: Generate is the grey "Stop run" with "Stop batch" (20.11.);
    # since 22.11. a function that can wait in the queue makes it "Add to queue"; since 23.11. Fill, Remove, Expand show
    # the same row with a grey "Add to queue" and ×n (user 23.11., choice A) ----
    mode_before = app.v_mode.get()
    app.v_mode.set("inpaint")
    runner.calls.clear()
    runner.busy = True
    app._batch_sync()
    assert str(app.b_go.cget("text")) == gui.ADD_QUEUE_TEXT and app.b_stop_all.winfo_manager() == "grid"
    assert str(app.b_go.cget("state")) == "disabled" and str(app.w_variants.cget("state")) == "disabled"
    assert app.b_stop_run.winfo_manager() == "grid"
    app._batch_sync()                              # the periodic sync keeps it grey
    assert str(app.b_go.cget("state")) == "disabled"
    # Undo and Redo are grey with Generate (a step back would take a batch layer); a finished Copy or Save (event "note")
    # does not bring them back while the batch is on
    assert str(app.b_undo.cget("state")) == "disabled" and str(app.b_redo.cget("state")) == "disabled"
    app.events.put(("note", "Copied."))
    app._poll()
    assert str(app.b_undo.cget("state")) == "disabled" and str(app.b_redo.cget("state")) == "disabled"
    undo_calls = []
    bridge.undo_last = bridge.redo_last = lambda: undo_calls.append(1) or "undone"
    app.worker = None
    app._status("")
    app.undo_edit()                                # Ctrl+Z on the button's way: refused, says why
    app.redo_edit()
    assert app.worker is None and undo_calls == [] and app.v_status.get() == gui_batch.BATCH_BUSY
    # a click on the grey button: a grey ttk button calls no command, the click binding says why (user 25.11.)
    app.root.update()
    assert app.b_undo.bind("<ButtonRelease-1>") and app.b_redo.bind("<ButtonRelease-1>")
    for b, step in ((app.b_undo, "undo"), (app.b_redo, "redo")):
        app._status("")
        app._history_grey_click(type("E", (), {"widget": b, "x": 2, "y": 2})(), step)
        assert app.worker is None and undo_calls == [] and app.v_status.get() == gui_batch.BATCH_BUSY, app.v_status.get()
        app._status("")
        app._history_grey_click(type("E", (), {"widget": b, "x": -5, "y": 2})(), step)     # released outside: nothing
        assert app.v_status.get() == ""
    assert app.tt_undo.text.endswith(gui.CUT_NOT_IN_RUN) and app.tt_redo.text.endswith(gui.CUT_NOT_IN_RUN)
    del bridge.undo_last, bridge.redo_last
    app._status("")
    app.generate()                                 # Fill can't wait in the queue: it says why (user 22.11.)
    assert app.worker is None and app.v_status.get() == gui.QUEUE_LOCKED.format(fn="Fill Selection"), app.v_status.get()
    assert not [c for c in runner.calls if c[0] == "start"]
    app._status("")
    app.save_image()
    assert app.worker is None and app.v_status.get() == gui_batch.BATCH_BUSY
    # Refine during the batch: "Add to queue" (blue), ×n, "Stop run", "Stop batch" (Variant 1); a click queues it
    app.v_mode.set(mode_before)
    for _ in range(3):
        app.root.update()
    assert str(app.b_go.cget("text")) == gui.ADD_QUEUE_TEXT and str(app.b_go.cget("style")) == "Accent.TButton"
    assert str(app.b_go.cget("state")) == "normal" and app.w_variants.winfo_manager() == "grid"
    assert str(app.w_variants.cget("state")) == "normal"
    assert app.b_stop_run.winfo_manager() == "grid" and app.b_stop_all.winfo_manager() == "grid"
    app._batch_sync()                              # the periodic sync keeps it usable
    assert str(app.b_go.cget("state")) == "normal" and str(app.w_variants.cget("state")) == "normal"
    app._stop_armed -= gui.STOP_GUARD_S
    app.v_variants.set(2)
    app._status("")
    app.generate()
    starts = [c for c in runner.calls if c[0] == "start"]
    assert len(starts) == 1, runner.calls
    spec = starts[0][1]
    assert spec.kind == jobqueue.K_GENERATE and spec.source == jobqueue.SOURCE_ACTIVE and spec.copies == 2
    assert spec.request.mode == "refine" and spec.label == "Refine Image · " + app._model().label and not spec.dry_run
    assert spec.request.group_name == f"Refine {spec.request.run_no}"
    assert app.state["runs"][spec.request.preset] == spec.request.run_no + 1     # two run numbers, one per job
    assert app.v_status.get().startswith("Added to the queue: Refine Image · "), app.v_status.get()
    app.v_variants.set(1)
    runner.calls.clear()
    runner.busy = False
    bridge.can_undo = lambda *a: True               # a run before the batch left something to undo
    app._last_step = None
    app._batch_sync()
    assert str(app.b_go.cget("state")) == "normal" and str(app.b_go.cget("text")) == "Generate"
    assert not app.b_stop_all.winfo_manager()
    # back after the batch, by their own rule (decision 2a, 18.11.): Undo blue, Redo grey until an Undo
    assert str(app.b_undo.cget("state")) == "normal" and str(app.b_redo.cget("state")) == "disabled", (app._stacks(), app._last_step, getattr(app, "_history_busy", None), app._running, app._batch_busy())
    del bridge.can_undo

    # ---- the hint at the bar: "Batch 3 of 12 · ~4 min", " · N jobs of others ahead" ----
    app._batch_event("queue-job", job("j2", "running"))
    assert app._batch_shown == "b1"
    app._batch_event("batch-step", (0.3, "", "image", -1.0, 12.0))
    assert app.v_pl.get().endswith(" · Batch 3 of 12 · ~4 min"), app.v_pl.get()
    app._batch_event("batch-ahead", {"job": "j2", "batch": "b1", "ahead": 2})
    assert app.v_pl.get().endswith(" · Batch 3 of 12 · ~4 min · 2 jobs of others ahead"), app.v_pl.get()
    app._batch_event("batch-ahead", {"job": "j2", "batch": "b1", "ahead": 0})
    assert app.v_pl.get().endswith("~4 min"), app.v_pl.get()
    done = {"id": "b1", "state": "done", "total": 3, "progress": {"total": 3, "counts": {"done": 2, "error": 1}}}
    app._batch_event("batch-done", done)
    assert app._batch_shown is None and app.v_pl.get() == "Done" and app.v_pl_rest.get() == " · batch: 2 of 3 done · 1 failed"
    app._batch_event("batch-done", dict(done, id="someone-else"))      # a batch of an earlier start: the bar stays
    assert app.v_pl_rest.get() == " · batch: 2 of 3 done · 1 failed"

    # ---- Generate: "N jobs of others ahead" while the job waits; the poll ends with the run ----
    gui_batch.AHEAD_POLL_S = 0.03
    comfy = bridge.comfy
    comfy.last_prompt_id = "old"
    comfy.entries = [{"prompt_id": "x", "client_id": "other", "owner": "", "running": True},
                     {"prompt_id": "p1", "client_id": "me", "owner": "", "running": False}]
    go = threading.Event()
    app.worker = threading.Thread(target=go.wait, daemon=True)
    app.worker.start()
    app._running, app._pl_args = True, None
    app._ahead_start()
    r0 = comfy.reads
    time.sleep(0.15)
    assert comfy.reads == r0                       # the old prompt id (of an earlier run): nothing is asked
    comfy.last_prompt_id = "p1"
    assert pump(app, lambda: app._ahead_n == 1)
    app._set_progress(0.4, "", "image", -1.0, 5.0)
    assert app.v_pl.get().endswith(" · 1 job of others ahead"), app.v_pl.get()
    comfy.entries[1]["running"] = True             # our job runs now: 0, and no more asking for it
    assert pump(app, lambda: app._ahead_n == 0)
    assert not app.v_pl.get().endswith("ahead"), app.v_pl.get()
    r1 = comfy.reads
    time.sleep(0.2)
    assert comfy.reads == r1
    go.set()                                       # the run ends: the poll thread ends
    app.worker.join(2)
    app._ahead_thread.join(2)
    assert not app._ahead_thread.is_alive()
    app._running = False
    comfy.last_prompt_id = "p2"                    # the "done" event of a run stops it too
    go2 = threading.Event()
    app.worker = threading.Thread(target=go2.wait, daemon=True)
    app.worker.start()
    app._ahead_start()
    t = app._ahead_thread
    app.events.put(("done", "Cancelled."))
    app._poll()
    t.join(2)
    assert not t.is_alive()
    go2.set()
    src = (ROOT / "pccomfy" / "gui_run.py").read_text(encoding="utf-8")
    assert "self._ahead_start()" in src and "self._ahead_stop()" in src

    # ---- results rescued after a restart: a short note ----
    runner._jobs = [job("r1", "running")]
    app._batch_recover()
    assert pump(app, lambda: ("recover",) in runner.calls)
    app._batch_event("queue-job", job("r1", "done"))
    assert app.v_status.get() == "Picked up 1 batch result that finished while PxC was closed.", app.v_status.get()

    # ---- the setting "Name in the queue" ----
    cfgmod.set_setting(jobqueue.OWNER_SETTING, None)
    frame = ttk.Frame(app.root)
    app._owner_name_row(frame)
    assert app.v_owner_name.get() == "" and app.lbl_owner_name.cget("text") == f"Empty: {jobqueue.owner_name()}"
    app.v_owner_name.set("Studio PC")
    assert cfgmod.get_setting(jobqueue.OWNER_SETTING) == "Studio PC" and runner.owner == "Studio PC"
    assert app.lbl_owner_name.cget("text") == ""
    app.v_owner_name.set("  ")
    assert cfgmod.get_setting(jobqueue.OWNER_SETTING) is None and runner.owner == jobqueue.owner_name()
    assert "_owner_name_row" in ui_settings.SettingsMixin._other_settings.__code__.co_names
    # order of "Other settings" (sections since 20.11.): the update line and the answer of Check now on top, Connection
    # (address, queue name), Save image, Appearance (scale, tips), Maintenance, one line between two sections; "Check for
    # updates" sits in the chip row (user 20.11.)
    import inspect
    src = inspect.getsource(ui_settings.SettingsMixin._other_settings)
    seq = [ln.strip().split("#")[0].strip() for ln in src.splitlines() if ln.strip().startswith("self._") and "(parent" in ln]
    assert seq == ["self._update_note_row(parent)", "self._update_status_row(parent)",
                   'self._other_head(parent, "Connection", first=True)', "self._comfy_address_row(parent)",
                   "self._owner_name_row(parent)", "self._other_sep(parent)", "self._save_image_row(parent)",
                   "self._other_sep(parent)", 'self._other_head(parent, "Appearance")', "self._ui_scale_row(parent)",
                   "self._tips_setting_row(parent, pady=(10, 0))", "self._other_sep(parent)",
                   'self._other_head(parent, "Maintenance")', "self._maintenance_row(parent)"], seq
    assert not any("_update_check_row" in c for c in seq) and [m[0] for m in ui_settings.SettingsMixin.MAINTENANCE][-1] == "Copy report"

    # ---- closing the window stops the runner; a batch job at ComfyUI is not cancelled ----
    runner.running_job = {"id": "j2"}
    app.worker = None
    assert app._batch_shutdown() is True and runner.calls[-1] == ("shutdown",)
    runner.running_job = None
    assert app._batch_shutdown() is False
    real_runner.shutdown()
    app.root.destroy()
    # a preparing batch waits until it really collects (user 13.11.)
    assert gui_queuewin.batch_state_text({"state": jobqueue.B_PREPARING}) == "Waiting"
    assert gui_queuewin.batch_state_text({"state": jobqueue.B_PREPARING, "collecting": True}) == "Collecting"
    assert gui_queuewin.batch_state_text({"state": jobqueue.B_RUNNING, "collecting": True}) == "Running"
    assert '"batch-dry-over"' in (ROOT / "pccomfy" / "gui_batch.py").read_text(encoding="utf-8"), "resume closes the dry-run window"
    # after Pause all the picture rows and the batch row offer ▶ (never ↻, which is for failed or cancelled pictures)
    st = lambda s_: {"status": s_}   # noqa: E731
    A = gui_queuewin.QueueWinMixin
    assert A._job_actions(st("paused")) == {"pr": "resume", "x": "cancel"}
    assert A._job_actions(dict(st("cancelled"), error="")) == {"x": "retry"}, "a cancelled picture: ↻ (its input is kept now)"
    brow = {"state": jobqueue.B_RUNNING}
    assert A._batch_actions(brow, [st("running"), st("paused"), st("paused")]) == {"pr": "resume_batch", "x": "cancel_batch"}
    assert A._batch_actions({"state": jobqueue.B_CONFIRM}, [st("done"), st("paused")])["pr"] == "resume_batch"
    assert A._batch_actions({"state": jobqueue.B_CONFIRM}, [st("done"), st("waiting")])["pr"] == "resume_batch"   # dry-run window closed
    # all its pictures are there but none has begun (the batch before it runs): "Waiting", not "Running" (user 13.11.)
    run = lambda **c: {"state": jobqueue.B_RUNNING, "collecting": True, "progress": {"counts": c}}   # noqa: E731
    assert gui_queuewin.batch_state_text(run(waiting=3)) == "Waiting"
    assert gui_queuewin.batch_state_text(run(waiting=2, running=1)) == "Running"
    assert gui_queuewin.batch_state_text(run(waiting=2, done=1)) == "Running", "between two pictures"
    assert gui_queuewin.batch_state_text(run(paused=3)) == "Running", "paused after it began is not waiting"
    assert gui_queuewin.batch_state_text({"state": jobqueue.B_DONE}) == "Done"
    print("ALL OK (Batch: menu, dialog, dry run, queue window, lock, hints, owner name)")


if __name__ == "__main__":
    main()
