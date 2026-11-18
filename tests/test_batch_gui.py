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

from pccomfy import config as cfgmod, gui, gui_batch, jobqueue, models, popmenu, ui_settings  # noqa: E402
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
    def clear_finished(self): return self._rec("clear")
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
    assert app.comfy.owner is None and app.bridge.comfy.owner is None
    for name in ("gui.py", "gui_run.py", "gui_batch.py"):
        assert ".owner =" not in (ROOT / "pccomfy" / name).read_text(encoding="utf-8").replace("runner.owner =", ""), name

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
    app.v_fn.set("scale")
    app._on_scale_fn()                     # Refine
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
    # "Queue" became "Open queue", the two resets of the page come under a line (user 16.11.)
    assert [e["label"] for e in menu.entries] == ["Save image (Ctrl+S)", "Copy canvas", "Batch: open images", "Batch: folder…",
                                                  "Open queue", "", "Reset page to my saved settings", "Reset page to default"]
    assert menu.entries[5]["type"] == "separator"
    cmds = [e for e in menu.entries if e["type"] != "separator"]
    assert all(e["icon"] is not None and e["icon_hot"] is not None and e["icon_hot"] is not e["icon"] for e in cmds)
    assert len({str(e["icon"]) for e in cmds}) == 7
    assert all(e["state"] == "normal" for e in cmds)
    app.reset_settings = lambda factory=False: calls.append(("reset", factory))
    for e in cmds[2:]:
        e["command"]()
    assert calls == [("batch", "open"), ("batch", "folder"), "queue", ("reset", False), ("reset", True)], calls
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
    assert app.lbl_batch_msg is None and app.lbl_batch_fn.cget("text").startswith("Refine · ")
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
    assert app.lbl_batch_fn.cget("text").startswith("Refine · ") and app._alive(app._batch_dlg)
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
    _x = [w for w in app._dry_dlg.winfo_children()[1].winfo_children() if str(w.cget("text")) == "✕"][0]
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

    # ---- the queue window: rows per batch, buttons per status, "At ComfyUI" read in a thread ----
    bridge.comfy.entries = [{"prompt_id": "x", "number": 1, "client_id": "other", "owner": "Anna", "running": True},
                            {"prompt_id": "y", "number": 2, "client_id": "other2", "owner": "", "running": False},
                            {"prompt_id": "z", "number": 3, "client_id": "me", "owner": "tester", "running": False}]
    app.open_queue()
    win = app._queue_win
    tv = app.tv_queue
    assert tv.get_children("") == ("b:b1",) and len(tv.get_children("b:b1")) == 6
    assert tv.item("b:b1", "values")[0] == "Running" and tv.item("b:b1", "values")[2] == runner.hint
    assert tv.item("j:j1", "values")[0] == "Done" and tv.item("j:j1", "values")[2] == gui.duration_text(42.0)
    assert tv.item("j:j3", "values")[2] == "~2 min" and tv.item("j:j6", "values")[0] == "Skipped"
    assert tv.item("j:j2", "text") == "j2.png" and tv.item("j:j2", "values")[1] == "Upscale"
    assert pump(app, lambda: len(app.tv_comfy.get_children()) == 3)
    rows = [(app.tv_comfy.item(i, "text"), app.tv_comfy.item(i, "values")[0]) for i in app.tv_comfy.get_children()]
    assert rows == [("Anna", "running"), ("unknown", "waiting"), ("tester (you)", "waiting")], rows
    state = lambda: {k: str(b.cget("state")) == "normal" for k, b in app.q_buttons.items()}   # noqa: E731
    assert set(app.q_buttons) == {"pause_batch", "resume_batch", "cancel_batch", "clear"}, set(app.q_buttons)
    # what a row can do sits in the row (user 13.11.): ⏸ / ▶, ↻, ✕ in the last three columns
    acts = lambda iid: tv.item(iid, "values")[3:]          # noqa: E731
    assert acts("j:j3") == ("⏸", "", "✕"), acts("j:j3")             # waiting: pause, cancel
    assert acts("j:j4") == ("▶", "", "✕"), acts("j:j4")             # paused: resume, cancel
    assert acts("j:j2") == ("", "", "✕"), acts("j:j2")              # running: cancel only
    assert acts("j:j1") == ("", "", ""), acts("j:j1")               # done: nothing
    assert acts("j:j5") == ("", "↻", ""), acts("j:j5")              # failed: retry
    assert acts("j:j6") == ("", "", ""), acts("j:j6")               # skipped: no retry
    assert acts("b:b1") == ("⏸", "", "✕"), acts("b:b1")             # the batch: pause all, cancel the batch
    for iid, col, want in (("j:j3", "pr", ("pause", "j3")), ("j:j3", "x", ("cancel", "j3")), ("j:j4", "pr", ("resume", "j4")),
                           ("j:j5", "retry", ("retry", "j5")), ("b:b1", "pr", ("pause_batch", "b1")),
                           ("b:b1", "x", ("cancel_batch", "b1"))):
        app._queue_do(app._row_actions(iid)[col], iid)
        assert runner.calls[-1] == want, (iid, col, runner.calls[-1])
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
    x, y, w, h = tv.bbox("j:j4", "#0")
    app._queue_press(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert app._q_drag and app._q_drag["iid"] == "j:j4"
    x, y, w, h = tv.bbox("j:j3", "#0")
    app._queue_motion(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert tv.index("j:j4") < tv.index("j:j3")
    app._queue_fill()                                             # a runner event while dragging: no redraw under the mouse
    assert tv.index("j:j4") < tv.index("j:j3")
    app._queue_release(None)
    assert runner.calls[-1] == ("move", "j4", -1), runner.calls[-1]
    assert app._q_drag is None
    x, y, w, h = tv.bbox("j:j2", "#0")                            # the running picture cannot be dragged
    app._queue_press(type("E", (), {"x": x + 5, "y": y + h // 2})())
    assert app._q_drag is None

    # the columns always fill the list (user 13.11.): a column made very wide gives the room back, the symbols stay
    tv.column("status", width=app._px(900))
    app._queue_fit_cols()
    cols = ("#0",) + tuple(tv.cget("columns"))
    total = sum(int(tv.column(c, "width")) for c in cols)
    assert total <= tv.winfo_width() - 2 + 1, (total, tv.winfo_width())
    assert int(tv.column("#0", "width")) >= app._px(gui_batch.Q_PICTURE_MIN)
    assert all(int(tv.column(c, "width")) == app._px(24) for c in app.Q_ACT_COLS)
    tv.column("status", width=app._px(80))
    app._queue_fit_cols()
    total = sum(int(tv.column(c, "width")) for c in cols)
    assert abs(total - (tv.winfo_width() - 2)) <= 1, (total, tv.winfo_width())    # no gap: Picture takes the rest
    # the separator of a symbol column can't be dragged
    app.root.update()
    x, y, w, h = tv.bbox("j:j3", "pr")
    hy = 5                                          # in the heading row
    sep = type("E", (), {"x": x + w - 1, "y": hy})()
    if tv.identify_region(sep.x, sep.y) == "separator":
        assert app._queue_press(sep) == "break"
    # the heading of the lower list (user 13.11.)
    heads = [wd for wd in app.tv_comfy.master.winfo_children() if wd.winfo_class() == "TLabel"]
    assert heads and heads[0].cget("text") == "All jobs at ComfyUI now"
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
    pick("j:j3")                                   # the buttons under the list act on the row's batch
    s = state()
    assert s["pause_batch"] and s["resume_batch"] and s["cancel_batch"] and s["clear"], s
    for key in ("pause_batch", "resume_batch", "cancel_batch"):
        pick("j:j3")
        app.q_buttons[key].invoke()
        assert runner.calls[-1] == (key, "b1"), (key, runner.calls[-1])
    pick("j:j6")                                   # skipped: the reason under the list
    assert "too large" in app.lbl_q_detail.cget("text")
    pick("j:j5")                                   # failed: retry refused after a restart: said so
    assert app.lbl_q_detail.cget("text") == "ComfyUI said no"
    app._queue_do("retry", "j:j5")
    assert runner.calls[-1] == ("retry", "j5") and app.lbl_q_detail.cget("text").startswith("Can't retry")
    # resizable: the grip in the corner, the list and "At ComfyUI" in a pane with a line to drag (user 13.11.)
    assert app.lbl_q_grip.winfo_manager() == "place" and str(app.pw_queue.cget("orient")) == "vertical"
    assert len(app.pw_queue.panes()) == 2
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
    app.q_buttons["clear"].invoke()
    assert runner.calls[-1] == ("clear",)
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
    assert pump(app, lambda: app.tv_comfy.item(app.tv_comfy.get_children()[0], "text") == "ComfyUI not reachable.")
    app._queue_close()
    bridge.comfy.fail = False

    # ---- Generate (and Save, Copy) locked while a batch is on ----
    runner.busy = True
    app._batch_sync()
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
    del bridge.undo_last, bridge.redo_last
    app._status("")
    app.generate()
    assert app.worker is None and app.v_status.get() == gui_batch.BATCH_BUSY
    app._status("")
    app.save_image()
    assert app.worker is None and app.v_status.get() == gui_batch.BATCH_BUSY
    runner.busy = False
    app._batch_sync()
    assert str(app.b_go.cget("state")) == "normal"
    assert str(app.b_undo.cget("state")) == "normal" and str(app.b_redo.cget("state")) == "normal"

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
    # order of "Other settings" (13.11.): Save image between two lines, the queue name right below, Interface scale,
    # and the tips tick at the very bottom (user 13.11.)
    import inspect
    src = inspect.getsource(ui_settings.SettingsMixin._other_settings)
    seq = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("self._") and "(parent)" in ln]
    assert [c.split("#")[0].strip() for c in seq] == ["self._comfy_address_row(parent)", "self._other_sep(parent)",
                                                  "self._save_image_row(parent)", "self._other_sep(parent)", "self._owner_name_row(parent)",
                                                  "self._ui_scale_row(parent)", "self._tips_setting_row(parent)"], seq
    assert src.index("Copy report") < src.index("_ui_scale_row")

    # ---- closing the window stops the runner; a batch job at ComfyUI is not cancelled ----
    runner.running_job = {"id": "j2"}
    app.worker = None
    assert app._batch_shutdown() is True and runner.calls[-1] == ("shutdown",)
    runner.running_job = None
    assert app._batch_shutdown() is False
    real_runner.shutdown()
    app.root.destroy()
    # a preparing batch waits until it really collects (user 13.11.)
    assert gui_batch.batch_state_text({"state": jobqueue.B_PREPARING}) == "Waiting"
    assert gui_batch.batch_state_text({"state": jobqueue.B_PREPARING, "collecting": True}) == "Collecting"
    assert gui_batch.batch_state_text({"state": jobqueue.B_RUNNING, "collecting": True}) == "Running"
    assert '"batch-dry-over"' in (ROOT / "pccomfy" / "gui_batch.py").read_text(encoding="utf-8"), "resume closes the dry-run window"
    # after Pause all the picture rows and the batch row offer ▶ (never ↻, which is for failed or cancelled pictures)
    st = lambda s_: {"status": s_}   # noqa: E731
    A = gui_batch.BatchMixin
    assert A._job_actions(st("paused")) == {"pr": "resume", "x": "cancel"}
    assert A._job_actions(dict(st("cancelled"), error="")) == {"retry": "retry"}, "a cancelled picture: ↻ (its input is kept now)"
    brow = {"state": jobqueue.B_RUNNING}
    assert A._batch_actions(brow, [st("running"), st("paused"), st("paused")]) == {"pr": "resume_batch", "x": "cancel_batch"}
    assert A._batch_actions({"state": jobqueue.B_CONFIRM}, [st("done"), st("paused")])["pr"] == "resume_batch"
    assert A._batch_actions({"state": jobqueue.B_CONFIRM}, [st("done"), st("waiting")])["pr"] == "resume_batch"   # dry-run window closed
    # all its pictures are there but none has begun (the batch before it runs): "Waiting", not "Running" (user 13.11.)
    run = lambda **c: {"state": jobqueue.B_RUNNING, "collecting": True, "progress": {"counts": c}}   # noqa: E731
    assert gui_batch.batch_state_text(run(waiting=3)) == "Waiting"
    assert gui_batch.batch_state_text(run(waiting=2, running=1)) == "Running"
    assert gui_batch.batch_state_text(run(waiting=2, done=1)) == "Running", "between two pictures"
    assert gui_batch.batch_state_text(run(paused=3)) == "Running", "paused after it began is not waiting"
    assert gui_batch.batch_state_text({"state": jobqueue.B_DONE}) == "Done"
    print("ALL OK (Batch: menu, dialog, dry run, queue window, lock, hints, owner name)")


if __name__ == "__main__":
    main()
