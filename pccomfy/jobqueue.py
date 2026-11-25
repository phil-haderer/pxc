"""The local job queue that serves Batch (docs/plan/speichern-queue-batch.md, steps 3 and 4; decisions of 12.11.).

Variant A: the queue lives on this PC only (``data/queue.json`` plus the input pictures as PNG in ``data/queue/``), ComfyUI
stays as it is, and at most ONE job of this plugin is at ComfyUI at a time (one runner thread that waits for each job), so
several PCs on one ComfyUI take turns. Batch uses the queue, and Generate clicked while a run is on (kind K_GENERATE,
docs/plan/generate-queue.md: Refine, Upscale, Edit and Text to image, only the function that runs (user 23.11., choice D);
the picture of the document in front is taken at the click, for Text to image only its size); a
Generate with nothing on runs directly, not through it. The runner does not start a job while the window's own worker
runs (``gate``).

One job per picture. A job runs ``Bridge.begin`` + ``Bridge.process_image`` on its own copy of the batch's
``bridge.Request`` (one result per picture, no variants), then delivers the result:
  * folder batch: a file in the save folder, ``<stem><suffix>.<ext>`` (savefile.save_batch_result), never overwritten;
  * open-images batch: like Generate (Refine / Edit as a new layer in that document, Upscale as a new document), only
    while the document is still open with the same name and size, otherwise as a file plus a new document; with
    ``also_save_file`` the file is written as well.

The GUI talks to ``QueueRunner`` only. The runner reports through ``events`` (a ``queue.Queue`` of ``(kind, data)`` tuples,
the window's own ``self.events``) and/or ``on_event(kind, data)``; every kind starts with "queue-" or "batch-":

  ("queue-job",      job dict)          a job was added or changed (status, prompt id, result, error ...)
  ("batch-progress", batch dict)        a batch changed; batch dict["progress"] = {"index", "total", "eta", "hint"}
  ("batch-step",     (fraction, message, phase, phase_fraction, elapsed))   the bar of the job that runs (as "progress")
  ("batch-ahead",    {"job", "batch", "ahead"})   jobs of OTHER clients ComfyUI has before ours ("N jobs of others ahead")
  ("batch-dry",      {"batch", "job", "results", "placed", "image", "error"})   the dry run's first result is ready;
                                                  the batch waits in state "confirm" for confirm() or discard()
  ("batch-dry-over", {"batch"})         resume() / resume_batch() confirmed the waiting dry run: its dialog can go
  ("batch-done",     batch dict)        the batch is over (state "done" or "cancelled")
  ("batch-error",    {"batch", "job", "message"})   a job failed for good, or a step of the runner itself failed
  ("batch-placed",   {"job", "batch", "doc", "layer", "name"})   a queued Generate put its result layer (or group) into
                                                  the document: the window's Undo can hide it

Job dicts and batch dicts are plain copies (``Job.to_dict``, ``Batch.to_dict``), safe to read in the Tk thread.
"""
from __future__ import annotations

import dataclasses
import getpass
import itertools
import json
import os
import queue as _queue
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

from . import config, imaging, savefile, workflows
from .comfy import Cancelled, ComfyError

# ---------- statuses, constants, settings ----------

WAITING, RUNNING, PAUSED, DONE, ERROR, CANCELLED = "waiting", "running", "paused", "done", "error", "cancelled"
STATUSES = (WAITING, RUNNING, PAUSED, DONE, ERROR, CANCELLED)
ACTIVE = (WAITING, RUNNING, PAUSED)              # a job in one of these is not over yet
FINISHED = (DONE, ERROR, CANCELLED)

# batch states: "preparing" (the pictures are being collected), "running", "confirm" (dry run: the first result is
# there, waiting for confirm() / discard()), "done", "cancelled"
B_PREPARING, B_RUNNING, B_CONFIRM, B_DONE, B_CANCELLED = "preparing", "running", "confirm", "done", "cancelled"

BATCH_MODES = ("refine", "upscale", "edit")      # Fill, Remove, Expand need a selection: no batch (plan step 4)
SOURCE_OPEN, SOURCE_FOLDER = "open", "folder"
SOURCE_ACTIVE = "active"      # a queued Generate (docs/plan/generate-queue.md): the document in front when it was clicked
K_BATCH, K_GENERATE = "batch", "generate"       # Batch.kind: a batch of the ⋯ menu, or Generate clicked while a run is on
QUEUE_MODES = ("refine", "upscale", "edit", "txt2img")   # the run modes a Generate can queue (user 23.11., choice D;
                                                         # Multi Edit, Sketch, Scribble run as "edit" but never queue)
NO_PICTURE_MODES = ("txt2img",)   # a queued Generate that takes only the canvas size, no picture (nothing stored)
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MAX_AUTO_RETRIES = 2          # network / server errors and GPU out-of-memory (is_oom) only; never another graph error
OOM_RETRY_DELAY_S = 5.0       # after a GPU out-of-memory error: wait this long times the retry's number (VRAM must be free)
PLACE_GAP_S = 2.0             # after a result was handed over (layer / new document / file) the next job waits this long
OOM_MARKS = ("out of memory", "outofmemory", "allocation on device")   # lower case, in ComfyUI's node error text
RETRY_DELAY_S = 3.0           # an automatic retry waits this long times the retry's number (ComfyUI may be starting up)
QUEUE_POLL_S = 2.0            # GET /queue while our job is at ComfyUI (decisions 12.11.: "etwa alle 2 s")
GATE_POLL_S = 0.3             # while the gate is shut (the window runs a job itself) the runner looks again this often
SNAPSHOT_POLL_S = 0.2         # how often a wait for the pictures of a batch looks at Stop (tests make both shorter)
KEEP_FINISHED = 200           # finished jobs kept in queue.json (the queue window's list)
TIMING_SAMPLES = 8            # image-timings.json: the last N (megapixels, seconds) per workflow

OWNER_SETTING = "owner_name"  # settings.json: the name other PCs see on our jobs (default: the login name)
SKIPPED = "Skipped: "         # the start of the error text of a picture the batch leaves out (too large for Upscale)


def owner_name() -> str:
    """The owner's name sent with every job (batch and Generate, 18.11.): the setting ``owner_name``, else the login name, else the PC's name."""
    name = config.get_setting(OWNER_SETTING)
    if isinstance(name, str) and name.strip():
        return name.strip()[:64]
    try:
        return getpass.getuser() or socket.gethostname()
    except Exception:
        return socket.gethostname() or "user"


def queue_file() -> Path:
    """data/queue.json (Windows) or ~/.config/pccomfy/queue.json: the list of jobs and batches."""
    return config.CONFIG_DIR / "queue.json"


def queue_dir() -> Path:
    """data/queue/: the input picture of every job as <job id>.png."""
    return config.CONFIG_DIR / "queue"


def atomic_write_json(path: Path, data) -> None:
    """Write JSON through a temporary file in the same folder and os.replace: a crash leaves the old file or the new one,
    never half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        for attempt in range(5):        # Windows: a reader holding the file for a moment makes os.replace fail briefly
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def is_transient(exc: BaseException) -> bool:
    """A network or server error worth sending the job again (automatically at most MAX_AUTO_RETRIES times): no
    connection, connection reset, timeout, HTTP 5xx. A graph or validation error (ComfyUI refused the job, a node failed)
    and our own errors (BridgeError) are not."""
    if isinstance(exc, ComfyError):
        return bool(getattr(exc, "transient", False))
    return isinstance(exc, (ConnectionError, TimeoutError, socket.timeout))


def is_oom(message: str) -> bool:
    """A ComfyUI node error caused by a full GPU memory (text of the execution_error / history message). The job often
    works after a short pause: ComfyUI unloads its models after such an error."""
    low = str(message).lower()
    return any(m in low for m in OOM_MARKS)


def scan_folder(folder) -> list[Path]:
    """The pictures of a folder batch: only that folder (no subfolders), files ending in .png .jpg .jpeg .webp (any case),
    without the ones whose stem already ends with a batch suffix (_upscaled, _refined, _edited); sorted by name."""
    folder = Path(folder)
    out = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    for f in entries:
        try:
            if not f.is_file():
                continue
        except OSError:
            continue
        if f.suffix.lower() in IMAGE_EXTS and not savefile.has_batch_suffix(f.stem):
            out.append(f)
    return sorted(out, key=lambda f: f.name.casefold())


def copy_request(req):
    """A request of its own for one picture: begin() and process_image() change it (prompt, seed, denoise, sizes in
    req.params, stages), so every job gets a copy; the lists and dicts inside are copied too. Batch = one result per
    picture: variants 1, no BBOX, no scribble."""
    p = req.params
    params = dataclasses.replace(p, extra=dict(p.extra))
    return dataclasses.replace(req, params=params, variants=1, bbox=False, scribble=False, fill_box=False,
                               scribble_object=False,
                               stages_off=list(req.stages_off), stage_strengths=dict(req.stage_strengths),
                               sampler_override=dict(req.sampler_override), loras=list(req.loras), refs=list(req.refs))


def result_megapixels(mode: str, size, req) -> float:
    """The megapixels a job's result has (what its time grows with): Upscale size x factor², Refine the picture,
    Edit the area the model draws (MiniMax: gen_mp; else at most base_res²)."""
    w, h = (int(v) for v in size)
    mp = w * h / 1e6
    if mode == "upscale":
        return mp * float(req.scale) ** 2
    if mode == "txt2img":       # the canvas size, at most native_mp (MiniMax: gen_mp), like Bridge._plan
        if float(getattr(req, "gen_mp", 0) or 0) > 0:
            return float(req.gen_mp)
        cap = float(getattr(req, "native_mp", 0) or 0)
        return min(mp, cap) if cap > 0 else mp
    if mode == "edit":
        if float(getattr(req, "gen_mp", 0) or 0) > 0:
            return float(req.gen_mp)
        if getattr(req, "full_size", False):
            return mp
        return min(mp, float(req.base_res) ** 2 / 1e6)
    return mp


def format_eta(seconds) -> str:
    """"~4 min", "<1 min"; "" without an estimate."""
    if seconds is None:
        return ""
    s = max(0.0, float(seconds))
    return "<1 min" if s < 60 else f"~{round(s / 60)} min"


# ---------- jobs and batches ----------

def qlog(bridge, event: str, **fields) -> None:
    """A time mark of the queue in comfy-net.log (window test 23.11. evening: ×2 with Text to image showed nothing in the
    queue and started late; measured, not guessed). s = seconds within the minute, to 1/100. Never raises."""
    try:
        bridge.comfy._log(event, s=f"{time.time() % 60:05.2f}", **fields)
    except Exception:
        pass


@dataclass
class Job:
    """One picture of a batch. Times are seconds since the epoch (time.time()), 0 = not yet."""
    id: str
    batch_id: str
    mode: str                                  # "refine", "upscale", "edit" or "txt2img" (a queued Generate)
    order: int = 0                             # place in the queue (smaller first), shared by all batches
    status: str = WAITING
    owner: str = ""                            # the owner's name (setting owner_name) ...
    client_id: str = ""                        # ... and this plugin's ComfyUI client id
    workflow: str = ""                         # the workflow's stem ("flux3-klein-upscale"), "builtin" without one
    source: dict = field(default_factory=dict)  # {"kind": "open", "name", "index", "size": [w, h]} or {"kind": "folder", "path", "size"}
    input_png: str = ""                        # data/queue/<id>.png ("" once it is cleaned up)
    prompt_id: str = ""                        # ComfyUI's id of the job while / after it ran there
    out_node: str = ""                         # the graph's output node (pc:output), to pick the result up after a restart
    attempts: int = 0                          # how often it was sent (manual retries included)
    auto_retries: int = 0                      # automatic retries used (at most MAX_AUTO_RETRIES)
    error: str = ""
    results: list = field(default_factory=list)   # file paths written for it
    placed: str = ""                           # "layer", "document" or "file": where the result went
    created: float = 0.0
    started: float = 0.0
    finished: float = 0.0
    eta: float | None = None                   # estimated seconds at ComfyUI (image phase), None = no estimate yet
    mp: float = 0.0                            # megapixels of the result (ETA)
    detail: float = 1.0                        # the request's Detail mix (a result picked up after a restart gets it too)
    also_save: bool = False                    # open-images batch: write the file too
    seed: int | None = None
    run_no: int = 0                            # queued Generate: the run number of this job (layer "<model> #<n>") ...
    group: str = ""                            # ... and its group name ("Refine 7")
    written: str = ""                          # the prompt the text model wrote for it ("" without one)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["source"] = dict(self.source)
        d["results"] = list(self.results)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        names = {f.name for f in dataclasses.fields(cls)}
        job = cls(**{k: v for k, v in d.items() if k in names})
        if job.status not in STATUSES:
            job.status = ERROR
        return job


@dataclass
class Batch:
    id: str
    mode: str
    source: str                                # SOURCE_OPEN or SOURCE_FOLDER
    folder: str = ""
    state: str = B_PREPARING
    collecting: bool = False                   # _prepare has begun; before that a preparing batch only waits (user 13.11.)
    total: int = 0                             # pictures in it (skipped ones included)
    dry_run: bool = True
    dry_pending: bool = True                   # the dry run's first result has not come yet
    also_save: bool = False
    workflow: str = ""
    owner: str = ""
    skipped: list = field(default_factory=list)   # "<name>: <why>" of pictures left out
    stopped: bool = False                      # cancelled by the user (cancel_batch / discard): ends as "cancelled"
    kind: str = K_BATCH                        # K_GENERATE: Generate clicked while a run was on (no dry run, no undo point)
    label: str = ""                            # "Refine · Qwen Image 2.1": the queue window's Function and the bar's model
    model: str = ""                            # the model's label ("Qwen Image 2.1")
    created: float = 0.0
    finished: float = 0.0

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["skipped"] = list(self.skipped)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Batch":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class BatchSpec:
    """What the batch dialog hands to QueueRunner.start_batch.
    request: the window's bridge.Request (RunMixin._request()), mode "refine", "upscale" or "edit"; it is copied.
    source: SOURCE_OPEN (all pictures open in PhotoCraft) or SOURCE_FOLDER (``folder``; ``files`` = an explicit list
    instead of scanning it). dry_run: the first picture alone, then wait for confirm(). also_save_file: open-images batch
    writes the file as well. save_settings: a savefile.SaveSettings (None = the saved settings at delivery time)."""
    request: object
    source: str = SOURCE_FOLDER
    folder: str | None = None
    files: list | None = None
    dry_run: bool = True
    also_save_file: bool = False
    save_settings: object = None
    kind: str = K_BATCH           # K_GENERATE with source SOURCE_ACTIVE: a queued Generate (copies = its ×n)
    shared: dict | None = None    # the variants of a direct run: {"done": Event, "pic", "index", "name"} filled by that run
                                  # when it has exported its picture; the snapshot waits for it instead of exporting again
    copies: int = 1
    label: str = ""
    model: str = ""


class JobStore:
    """queue.json plus the input PNGs. Not thread-safe by itself: QueueRunner holds its lock around it."""

    def __init__(self, path: Path | None = None, folder: Path | None = None):
        self.path = Path(path) if path else queue_file()
        self.folder = Path(folder) if folder else queue_dir()
        self.jobs: list[Job] = []
        self.batches: dict[str, Batch] = {}

    def load(self) -> "JobStore":
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        self.jobs = [Job.from_dict(j) for j in d.get("jobs", []) if isinstance(j, dict) and j.get("id")]
        self.batches = {b["id"]: Batch.from_dict(b) for b in d.get("batches", []) if isinstance(b, dict) and b.get("id")}
        return self

    def save(self) -> None:
        self.prune()
        try:
            atomic_write_json(self.path, {"version": 1, "jobs": [j.to_dict() for j in self.jobs],
                                          "batches": [b.to_dict() for b in self.batches.values()]})
        except OSError:
            pass

    def prune(self) -> None:
        """Keep every job that is not over and the newest KEEP_FINISHED finished ones; batches without jobs go."""
        done = [j for j in self.jobs if j.status in FINISHED]
        if len(done) > KEEP_FINISHED:
            drop = {j.id for j in sorted(done, key=lambda j: j.finished or j.created)[: len(done) - KEEP_FINISHED]}
            self.jobs = [j for j in self.jobs if j.id not in drop]
        live = {j.batch_id for j in self.jobs}
        self.batches = {k: b for k, b in self.batches.items() if k in live or b.state in (B_PREPARING, B_RUNNING, B_CONFIRM)}

    def png_path(self, job_id: str) -> Path:
        return self.folder / f"{job_id}.png"

    def write_input(self, job_id: str, im: Image.Image) -> Path:
        """The job's input picture as data/queue/<id>.png (written through a temporary file)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.png_path(job_id)
        tmp = path.with_name(path.name + ".tmp")
        im.save(tmp, format="PNG")
        os.replace(tmp, path)
        return path

    def drop_input(self, job: Job) -> None:
        if job.input_png:
            try:
                Path(job.input_png).unlink()
            except OSError:
                pass
            job.input_png = ""

    def orphan_pngs(self) -> list[Path]:
        keep = {Path(j.input_png).name for j in self.jobs if j.input_png}
        try:
            return [f for f in self.folder.glob("*.png") if f.name not in keep]
        except OSError:
            return []


class ImageTimings:
    """exchange/image-timings.json (next to timings.json, which holds the text-model phase): seconds of the image phase per
    workflow stem and megapixels, the last TIMING_SAMPLES runs; estimate() = their seconds per megapixel x megapixels."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def record(self, workflow: str, mp: float, seconds: float) -> None:
        if not workflow or mp <= 0 or seconds <= 0:
            return
        with self._lock:
            d = self._load()
            rows = [r for r in d.get(workflow, []) if isinstance(r, list) and len(r) == 2][-(TIMING_SAMPLES - 1):]
            rows.append([round(float(mp), 3), round(float(seconds), 1)])
            d[workflow] = rows
            try:
                atomic_write_json(self.path, d)
            except OSError:
                pass

    def estimate(self, workflow: str, mp: float) -> float | None:
        rows = self._load().get(workflow) or []
        try:
            total_mp = sum(float(r[0]) for r in rows)
            total_s = sum(float(r[1]) for r in rows)
        except (TypeError, ValueError, IndexError):
            return None
        if total_mp <= 0 or total_s <= 0 or mp <= 0:
            return None
        return total_s / total_mp * float(mp)


# ---------- the runner ----------

class QueueRunner:
    """The batch queue of one window. All public methods are safe to call from the Tk thread; they only change the list
    (under a lock), save queue.json and wake the runner thread, never wait for ComfyUI or PhotoCraft.

    bridge: the window's Bridge (its ComfyUI and PhotoCraft). events: the window's queue.Queue (see the module text for
    the tuples); on_event(kind, data): the same as a callback. gate(): False while the window's own worker runs (Generate,
    Describe ...): no batch job starts then. store / timings / owner: for tests (default: data/queue.json, the bridge's
    exchange/image-timings.json, owner_name())."""

    def __init__(self, bridge, events: "_queue.Queue | None" = None, on_event: Callable[[str, object], None] | None = None,
                 gate: Callable[[], bool] | None = None, store: JobStore | None = None, timings: ImageTimings | None = None,
                 owner: str | None = None):
        self.bridge = bridge
        self.events = events
        self.on_event = on_event
        self.gate = gate
        self.store = (store or JobStore()).load()
        self.timings = timings or ImageTimings(Path(bridge.exchange) / "image-timings.json")
        self.owner = owner or owner_name()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._tasks: deque = deque()              # prepare / recover steps, run in the runner thread before any job
        self._requests: dict[str, object] = {}    # batch id -> its bridge.Request (only in memory: lost on a restart)
        self._settings: dict[str, object] = {}    # batch id -> savefile.SaveSettings or None
        self._snapshots: set = set()              # (batch id, document name): one undo point per document and batch
        # one at a time talks to PhotoCraft's documents: the snapshot, a result's placing, and the window's own run (bridge.pc_lock)
        self._pc_lock = getattr(bridge, "pc_lock", None) or threading.RLock()
        self._shots: dict[str, dict] = {}         # batch id -> {"done": Event, "items": [...], "error": str}: the canvases at send time
        self._shared: dict[str, dict] = {}        # batch id -> BatchSpec.shared (the picture of the direct run it belongs to)
        self._current: Job | None = None
        self._cancel_running = False
        self._stop = threading.Event()
        self._ids = itertools.count(1)

    # ----- reading -----

    @property
    def busy(self) -> bool:
        """True while a batch is on: a job runs or waits, pictures are being collected, results of a restart are being
        picked up, or a dry run waits for confirmation. The window keeps Generate locked while it is True. Paused jobs
        alone do not count."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            if any(j.status in (WAITING, RUNNING) for j in self.store.jobs):
                return True
            return any(b.state in (B_PREPARING, B_CONFIRM) for b in self.store.batches.values())

    def open_modes(self) -> set:
        """The run modes of the batches and queued Generate clicks that are not over (a job waits or runs, or the batch
        collects its pictures or waits for its dry run): Generate may only queue the same function (user 23.11., choice D)."""
        with self._lock:
            modes = {j.mode for j in self.store.jobs if j.status in (WAITING, RUNNING)}
            modes |= {b.mode for b in self.store.batches.values() if b.state in (B_PREPARING, B_CONFIRM)}
            return modes

    @property
    def only_generate(self) -> bool:
        """No batch of the ⋯ menu is on (what is on, if anything, are queued Generate clicks): Undo and Redo of a result
        layer may run meanwhile (hiding a layer is safe, docs/plan/generate-queue.md)."""
        with self._lock:
            return not any(b.kind != K_GENERATE and b.state in (B_PREPARING, B_RUNNING, B_CONFIRM)
                           for b in self.store.batches.values())

    @property
    def pc_lock(self):
        """The lock around every talk with PhotoCraft's documents (shared with the bridge's own runs)."""
        return self._pc_lock

    @property
    def running_job(self) -> dict | None:
        """The job at ComfyUI now (a dict), or None."""
        with self._lock:
            return self._current.to_dict() if self._current is not None else None

    def jobs(self, batch_id: str | None = None) -> list[dict]:
        """All jobs (or those of one batch) in queue order, as dicts."""
        with self._lock:
            return [j.to_dict() for j in self._ordered() if batch_id is None or j.batch_id == batch_id]

    def job(self, job_id: str) -> dict | None:
        with self._lock:
            j = self._job(job_id)
            return j.to_dict() if j else None

    def batches(self) -> list[dict]:
        with self._lock:
            return [self._batch_dict(b) for b in sorted(self.store.batches.values(), key=lambda b: b.created)]

    def batch(self, batch_id: str) -> dict | None:
        with self._lock:
            b = self.store.batches.get(batch_id)
            return self._batch_dict(b) if b else None

    def job_eta(self, job_id: str) -> float | None:
        """Seconds the job still needs at ComfyUI (a running one: its estimate minus the time it has run), None = unknown."""
        with self._lock:
            j = self._job(job_id)
            return self._remaining(j) if j else None

    def batch_eta(self, batch_id: str) -> float | None:
        """Seconds until the batch is through (waiting jobs + what the running one still needs); None = unknown."""
        with self._lock:
            jobs = [j for j in self.store.jobs if j.batch_id == batch_id and j.status in (WAITING, RUNNING)]
            if not jobs:
                return 0.0
            total = 0.0
            for j in jobs:
                r = self._remaining(j)
                if r is None:
                    return None
                total += r
            return total

    def batch_hint(self, batch_id: str) -> str:
        """The line for the bar: "Batch 3 of 12 · ~4 min" ("" for an unknown batch)."""
        b = self.batch(batch_id)
        return b["progress"]["hint"] if b else ""

    # ----- starting a batch -----

    def start_batch(self, spec: BatchSpec) -> str:
        """Check the settings (raises bridge.BridgeError / ValueError at once when they cannot work), create the batch and
        let the runner thread collect the pictures (the open documents through PhotoCraft, or the folder's files) and run
        them. Returns the batch id. The pictures appear as "queue-job" events."""
        from .bridge import Bridge
        req = spec.request
        gen = spec.kind == K_GENERATE
        if gen and (req.mode not in QUEUE_MODES or req.refs or req.scribble or req.bbox):
            # user 23.11. evening (choice D): Multi Edit, Sketch, Scribble, Insert reference never wait in the queue
            raise ValueError(f"Only Refine Image, Upscale, Edit and Text to Image can wait in the queue, not {req.mode}.")
        if not gen and req.mode not in BATCH_MODES:
            raise ValueError(f"Batch works with Refine Image, Upscale and Edit, not with {req.mode}.")
        if spec.source not in ((SOURCE_ACTIVE,) if gen else (SOURCE_OPEN, SOURCE_FOLDER)):
            raise ValueError(f"Unknown batch source {spec.source!r}.")
        if spec.source == SOURCE_FOLDER and not spec.files:
            if not spec.folder or not Path(spec.folder).is_dir():
                raise ValueError("Choose a folder with pictures.")
        qlog(self.bridge, "q_start_batch", mode=req.mode, copies=spec.copies)
        test = copy_request(req)
        # the checks of a run (workflow, Upscale factor ...), no network; begin() also clears what the bridge keeps of the
        # run that may be on meanwhile (a queued Generate): put that back
        kept = (getattr(self.bridge, "last_vgl", ""), getattr(self.bridge, "_scribble_layer", None))
        try:
            test, p, _tag = self.bridge.begin(test)
        finally:
            self.bridge.last_vgl, self.bridge._scribble_layer = kept
        wfs = workflows.resolve(test.workflow) if test.workflow else [None]
        Bridge._check_mode(test, p, wfs)                  # Edit: an instruction editor and a prompt
        bid = uuid.uuid4().hex[:10]
        with self._lock:
            b = Batch(id=bid, mode=req.mode, source=spec.source, folder=str(spec.folder or ""),
                      dry_run=bool(spec.dry_run) and not gen, dry_pending=bool(spec.dry_run) and not gen,
                      also_save=bool(spec.also_save_file) and not gen, owner=self.owner, workflow=self._wf_stem(req),
                      kind=K_GENERATE if gen else K_BATCH, label=str(spec.label or ""), model=str(spec.model or ""),
                      created=time.time())
            self.store.batches[bid] = b
            self._requests[bid] = copy_request(req)
            self._settings[bid] = spec.save_settings
            if spec.shared is not None:
                self._shared[bid] = spec.shared
            self.store.save()
            if spec.source in (SOURCE_OPEN, SOURCE_ACTIVE):
                self._snapshot_open(b)
            self._tasks.append(lambda: self._prepare(bid, spec))
            self._emit("batch-progress", self._batch_dict(b))
            self._kick()
        qlog(self.bridge, "q_batch_added", batch=bid)
        return bid

    # ----- controls (own jobs only) -----

    def confirm(self, batch_id: str) -> bool:
        """Dry run ok: the rest of the batch runs. False when the batch does not wait for confirmation."""
        with self._lock:
            b = self.store.batches.get(batch_id)
            if b is None or b.state != B_CONFIRM:
                return False
            b.state = B_RUNNING
            self._changed_batch(b)
            self._kick()
            return True

    def discard(self, batch_id: str) -> bool:
        """Dry run not ok: the rest of the batch is cancelled (the first result stays where it went)."""
        return self.cancel_batch(batch_id)

    def pause(self, job_id: str) -> bool:
        """A waiting job is held back (status paused). A running job cannot be paused (cancel it instead)."""
        with self._lock:
            j = self._job(job_id)
            if j is None or j.status != WAITING:
                return False
            self._set(j, status=PAUSED)
            return True

    def resume(self, job_id: str) -> bool:
        with self._lock:
            j = self._job(job_id)
            if j is None or j.status != PAUSED:
                return False
            self._confirm_on_resume(j.batch_id)
            self._set(j, status=WAITING)
            self._kick()
            return True

    def _confirm_on_resume(self, batch_id: str) -> None:
        """A picture is resumed in a batch that waits for the dry run's confirmation: nothing would start (_next_job only takes
        pictures of running batches), so "resume" did nothing. Resuming says "go on": it confirms the dry run (call with
        the lock held; "batch-dry-over" closes the window's dry-run dialog)."""
        b = self.store.batches.get(batch_id)
        if b is not None and b.state == B_CONFIRM:
            b.state = B_RUNNING
            self._emit("batch-dry-over", {"batch": batch_id})

    def pause_batch(self, batch_id: str) -> int:
        """Every waiting job of the batch paused (the running one finishes). Returns how many."""
        with self._lock:
            jobs = [j for j in self.store.jobs if j.batch_id == batch_id and j.status == WAITING]
            for j in jobs:
                self._set(j, status=PAUSED)
            return len(jobs)

    def resume_batch(self, batch_id: str) -> int:
        with self._lock:
            jobs = [j for j in self.store.jobs if j.batch_id == batch_id and j.status == PAUSED]
            b = self.store.batches.get(batch_id)
            waits = b is not None and b.state == B_CONFIRM
            self._confirm_on_resume(batch_id)      # also without paused pictures: ▶ on a batch whose dry-run window was closed (user 13.11.)
            if waits:
                self._changed_batch(b)
            for j in jobs:
                self._set(j, status=WAITING)
            self._kick()
            return len(jobs)

    def cancel(self, job_id: str) -> bool:
        """Cancel a job. A running one is stopped at ComfyUI with its own prompt id only (never a bare /interrupt)."""
        with self._lock:
            j = self._job(job_id)
            if j is None or j.status not in ACTIVE:
                return False
            if j.status == RUNNING:
                self._cancel_running = True
                self.bridge.cancel()         # Bridge._wait -> ComfyUI.interrupt(prompt_id)
                return True
            self._set(j, status=CANCELLED, finished=time.time())
            self._check_batch(j.batch_id)
            return True

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel every job of the batch that is not over (the running one at ComfyUI by its prompt id)."""
        with self._lock:
            b = self.store.batches.get(batch_id)
            if b is None or b.state in (B_DONE, B_CANCELLED):
                return False
            b.stopped = True
            if b.state == B_PREPARING:
                b.state = B_CANCELLED       # _prepare stops at the next picture
            elif b.state == B_CONFIRM:
                b.state = B_RUNNING         # so _check_batch can end it
            for j in [j for j in self.store.jobs if j.batch_id == batch_id and j.status in ACTIVE]:
                if j.status == RUNNING:
                    self._cancel_running = True
                    self.bridge.cancel()
                else:
                    self._set(j, status=CANCELLED, finished=time.time())
            self._check_batch(batch_id, force=True)
            return True

    def move(self, job_id: str, delta: int) -> bool:
        """Move a waiting or paused job up (delta < 0) or down (delta > 0) among the waiting and paused jobs."""
        with self._lock:
            j = self._job(job_id)
            if j is None or j.status not in (WAITING, PAUSED) or not delta:
                return False
            line = [x for x in self._ordered() if x.status in (WAITING, PAUSED)]
            i = line.index(j)
            k = max(0, min(len(line) - 1, i + (1 if delta > 0 else -1) * abs(int(delta))))
            if k == i:
                return False
            orders = [x.order for x in line]
            line.insert(k, line.pop(i))
            for x, o in zip(line, orders):
                x.order = o
            self.store.save()
            for x in line:
                self._emit("queue-job", x.to_dict())
            return True

    def retry(self, job_id: str) -> bool:
        """Send a failed (or cancelled) job again. Needs its input picture and the batch's settings, which only live
        until the plugin is closed: after a restart a failed job cannot be retried (False)."""
        with self._lock:
            j = self._job(job_id)
            if j is None or j.status not in (ERROR, CANCELLED) or j.error.startswith(SKIPPED):
                return False
            needs_pic = j.mode not in NO_PICTURE_MODES
            if j.batch_id not in self._requests or (needs_pic and (not j.input_png or not Path(j.input_png).exists())):
                return False
            b = self.store.batches.get(j.batch_id)
            if b is not None and b.state in (B_DONE, B_CANCELLED):
                b.state, b.finished, b.stopped = B_RUNNING, 0.0, False
            self._set(j, status=WAITING, error="", prompt_id="", auto_retries=0, finished=0.0, order=self._next_order())
            if b is not None:
                self._changed_batch(b)
            self._kick()
            return True

    def clear_finished(self, statuses: tuple = FINISHED) -> int:
        """Remove finished jobs (and their input pictures) from the list; `statuses` (DONE,) only the done ones ("Clear
        finished" since 24.11.; "Clear all" takes every finished one). Returns how many."""
        statuses = tuple(s for s in statuses if s in FINISHED)
        with self._lock:
            gone = [j for j in self.store.jobs if j.status in statuses]
            for j in gone:
                self.store.drop_input(j)
            ids = {j.id for j in gone}
            self.store.jobs = [j for j in self.store.jobs if j.id not in ids]
            self.store.save()
            return len(gone)

    def recover(self) -> None:
        """At the start of the plugin ("nur Ergebnisse retten", 12.11.): a job that was at ComfyUI when the plugin ended is
        asked for at /history (or waited for while ComfyUI still runs it) and its result delivered; a job ComfyUI no longer
        knows is an error. Every waiting or paused job is discarded (cancelled) and the input pictures are cleaned up.
        Runs in the runner thread; the outcome comes as events."""
        with self._lock:
            self._tasks.appendleft(self._recover)
            self._kick()

    def shutdown(self, timeout: float = 0.0) -> None:
        """The window closes: the runner stops after the current step. A job at ComfyUI keeps its prompt id in queue.json,
        so recover() at the next start picks its result up."""
        self._stop.set()
        t = self._thread
        if t is not None and timeout > 0:
            t.join(timeout)

    # ----- internals: bookkeeping -----

    def _emit(self, kind: str, data) -> None:
        if self.events is not None:
            try:
                self.events.put((kind, data))
            except Exception:
                pass
        if self.on_event is not None:
            try:
                self.on_event(kind, data)
            except Exception:
                pass

    def _ordered(self) -> list[Job]:
        return sorted(self.store.jobs, key=lambda j: (j.order, j.created))

    def _job(self, job_id: str) -> Job | None:
        return next((j for j in self.store.jobs if j.id == job_id), None)

    def _next_order(self) -> int:
        return max((j.order for j in self.store.jobs), default=0) + 1

    @staticmethod
    def _wf_stem(req) -> str:
        return Path(req.workflow).stem if req.workflow else "builtin"

    def _set(self, job: Job, **fields) -> None:
        for k, v in fields.items():
            setattr(job, k, v)
        self.store.save()
        self._emit("queue-job", job.to_dict())
        b = self.store.batches.get(job.batch_id)
        if b is not None:
            self._emit("batch-progress", self._batch_dict(b))

    def _changed_batch(self, b: Batch) -> None:
        self.store.save()
        self._emit("batch-progress", self._batch_dict(b))

    def _remaining(self, j: Job) -> float | None:
        est = j.eta
        if est is None:
            est = self._batch_rate_estimate(j)
        if est is None:
            return None
        if j.status == RUNNING and j.started:
            return max(0.0, est - (time.time() - j.started))
        return est

    def _batch_rate_estimate(self, j: Job) -> float | None:
        """Without a timing of the workflow yet: the seconds per megapixel of the jobs of the same batch that are done."""
        done = [x for x in self.store.jobs if x.batch_id == j.batch_id and x.status == DONE and x.started and x.finished and x.mp > 0]
        if not done or j.mp <= 0:
            return None
        rate = sum(x.finished - x.started for x in done) / sum(x.mp for x in done)
        return rate * j.mp

    def _batch_dict(self, b: Batch) -> dict:
        d = b.to_dict()
        jobs = [j for j in self.store.jobs if j.batch_id == b.id]
        total = len(jobs) or b.total
        over = sum(1 for j in jobs if j.status in FINISHED)
        running = any(j.status == RUNNING for j in jobs)
        index = min(total, over + (1 if running else 0)) if total else 0
        eta = None
        if b.state in (B_RUNNING, B_CONFIRM, B_PREPARING):
            act = [j for j in jobs if j.status in (WAITING, RUNNING)]
            eta = 0.0 if not act else None
            if act:
                vals = [self._remaining(j) for j in act]
                eta = None if any(v is None for v in vals) else sum(vals)
        if b.kind == K_GENERATE:        # a queued Generate: its ×n, nothing for a single picture
            hint = (f"Queued {max(index, 1)} of {total}" + (f" · {format_eta(eta)}" if eta else "")) if total > 1 else ""
        else:
            hint = f"Batch {max(index, 1) if total else 0} of {total}" + (f" · {format_eta(eta)}" if eta else "")
        d["progress"] = {"index": index, "total": total, "eta": eta, "hint": hint,
                         "counts": {s: sum(1 for j in jobs if j.status == s) for s in STATUSES}}
        return d

    def _check_batch(self, batch_id: str, force: bool = False) -> None:
        """A batch whose jobs are all over (none waiting, running or paused) ends: state done (cancelled when nothing was
        done and something was cancelled), the input pictures of done and cancelled jobs are deleted, "batch-done" goes out."""
        b = self.store.batches.get(batch_id)
        if b is None or b.state == B_PREPARING or (b.state == B_CONFIRM and not force):
            return
        if b.state in (B_DONE, B_CANCELLED) and b.finished:
            return                          # ended already (a retry() opens it again)
        jobs = [j for j in self.store.jobs if j.batch_id == batch_id]
        if any(j.status in ACTIVE for j in jobs):
            self._changed_batch(b)
            return
        if b.stopped:
            b.state = B_CANCELLED
        elif b.state not in (B_DONE, B_CANCELLED):
            done = any(j.status == DONE for j in jobs)
            b.state = B_DONE if done or not any(j.status == CANCELLED for j in jobs) else B_CANCELLED
        b.finished = b.finished or time.time()
        for j in jobs:
            if j.status == DONE:            # a cancelled picture keeps its input: ↻ can send it again (clear_finished drops it)
                self.store.drop_input(j)
        self.store.save()
        self._emit("batch-progress", self._batch_dict(b))
        self._emit("batch-done", self._batch_dict(b))

    # ----- internals: the thread -----

    def _kick(self) -> None:
        """Start the runner thread when it is not running (call with the lock held)."""
        if self._stop.is_set():
            return
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="pcc-batch", daemon=True)
            self._thread.start()

    def _next_job(self) -> Job | None:
        for j in self._ordered():
            if j.status != WAITING:
                continue
            b = self.store.batches.get(j.batch_id)
            if b is not None and b.state != B_RUNNING:
                continue
            return j
        return None

    def _loop(self) -> None:
        me = threading.current_thread()
        while not self._stop.is_set():
            task = None
            with self._lock:
                if self._tasks:
                    task = self._tasks.popleft()
            if task is not None:
                try:
                    task()
                except Exception as e:      # a step of the runner itself: report it, go on
                    self._emit("batch-error", {"batch": "", "job": "", "message": f"{type(e).__name__}: {e}"})
                continue
            if self.gate is not None and not self.gate():
                if not getattr(self, "_gate_logged", False):
                    self._gate_logged = True
                    qlog(self.bridge, "q_gate_wait")
                with self._lock:
                    if self._next_job() is None and not self._tasks:
                        if self._thread is me:
                            self._thread = None
                        return
                time.sleep(GATE_POLL_S)
                continue
            if getattr(self, "_gate_logged", False):
                self._gate_logged = False
                qlog(self.bridge, "q_gate_open")
            with self._lock:
                job = self._next_job()
                if job is None:
                    if self._tasks:
                        continue
                    if self._thread is me:
                        self._thread = None
                    return
                job.status, job.started, job.finished, job.error = RUNNING, time.time(), 0.0, ""
                job.attempts += 1
                self._current, self._cancel_running = job, False
                getattr(self.bridge, "_cancel").clear()     # a cancel of the job before this one does not count
                self.store.save()
                self._emit("queue-job", job.to_dict())
                b = self.store.batches.get(job.batch_id)
                if b is not None:
                    self._emit("batch-progress", self._batch_dict(b))
            qlog(self.bridge, "q_job_start", job=job.id)
            try:
                self._execute(job)
            finally:
                with self._lock:
                    self._current = None
            if job.status == DONE:
                self._place_gap()
        with self._lock:
            if self._thread is me:
                self._thread = None

    def _place_gap(self) -> None:
        """_execute has returned, so the result is already placed (layer added, document opened or file saved). PhotoCraft
        may still hold VRAM for a moment: the next job goes out PLACE_GAP_S later. Short slices: Stop, Pause and Cancel
        (no next job waits any more) end the wait at once."""
        end = time.monotonic() + PLACE_GAP_S
        while not self._stop.is_set() and time.monotonic() < end:
            with self._lock:
                if self._next_job() is None:
                    return
            self._stop.wait(min(0.1, max(0.0, end - time.monotonic())))

    # ----- internals: collecting the pictures -----

    def _prepare(self, batch_id: str, spec: BatchSpec) -> None:
        with self._lock:
            b = self.store.batches.get(batch_id)
            req = self._requests.get(batch_id)
        if b is None or req is None:
            return
        qlog(self.bridge, "q_prepare_begin", batch=batch_id)
        with self._lock:                # "Collecting" from here on; until now the batch waited for the job before it
            b.collecting = True
            self._emit("batch-progress", self._batch_dict(b))
        items = []        # (source dict, picture or None, error)
        if spec.source == SOURCE_FOLDER:
            files = [Path(f) for f in spec.files] if spec.files else scan_folder(spec.folder)
            for f in files:
                try:
                    with Image.open(f) as im:
                        im = ImageOps.exif_transpose(im)
                        im.load()
                        pic = im.convert("RGBA" if ("A" in im.getbands() or "transparency" in im.info) else "RGB")
                    items.append(({"kind": SOURCE_FOLDER, "path": str(f), "name": f.name, "size": list(pic.size)}, pic, ""))
                except Exception as e:
                    items.append(({"kind": SOURCE_FOLDER, "path": str(f), "name": f.name, "size": [0, 0]}, None,
                                  f"Cannot read the picture ({type(e).__name__})."))
                with self._lock:
                    if b.state == B_CANCELLED:
                        break
        else:
            items = self._snapshot_items(b)
            if b.kind == K_GENERATE:        # ×n of a queued Generate: n jobs on the same picture (decision 22.11.)
                items = items[:1] * max(1, int(spec.copies or 1))
        with self._lock:
            if b.state == B_CANCELLED:
                if not b.finished:
                    self._check_batch(batch_id, force=True)
                return
            from .bridge import MAX_SCALE_MP
            order = self._next_order()
            base_seed = getattr(req.params, "seed", None)
            group = str(getattr(req, "group_name", "") or "")
            run0 = int(getattr(req, "run_no", 0) or 0)
            if run0 and group.endswith(f" {run0}"):
                group = group[: -len(f" {run0}")]
            blank = req.mode in NO_PICTURE_MODES          # Text to image: the canvas size only, nothing stored
            for k, (src, pic, err) in enumerate(items):
                jid = f"{time.strftime('%Y%m%d%H%M%S')}-{next(self._ids):03d}-{uuid.uuid4().hex[:6]}"
                size = src.get("size") or [0, 0]
                mp = result_megapixels(req.mode, size, req) if (pic is not None or (blank and not err)) else 0.0
                job = Job(id=jid, batch_id=batch_id, mode=req.mode, order=order, owner=self.owner,
                          client_id=getattr(self.bridge.comfy, "client_id", ""), workflow=b.workflow, source=src,
                          created=time.time(), mp=round(mp, 3), detail=float(getattr(req, "detail", 1.0)),
                          also_save=b.also_save)
                if b.kind == K_GENERATE:
                    if base_seed is not None and int(base_seed) >= 0:      # a fixed seed: each copy its own, as with variants
                        job.seed = (int(base_seed) + 7919 * k) % (2**31)
                    if run0:
                        job.run_no = run0 + k
                        job.group = f"{group} {run0 + k}" if group else ""
                order += 1
                too_big = req.mode in ("upscale", "refine") and mp > MAX_SCALE_MP + 1e-9
                if err or (pic is None and not blank):
                    job.status, job.error, job.finished = ERROR, err or "No picture.", time.time()
                elif too_big:
                    w, h = size
                    job.status, job.finished = ERROR, time.time()
                    job.error = (f"{SKIPPED}the result would be {mp:.1f} megapixels ({w}×{h}); the limit is {MAX_SCALE_MP:.0f}.")
                else:
                    try:
                        if pic is not None:
                            job.input_png = str(self.store.write_input(jid, pic))
                    except OSError as e:
                        job.status, job.error, job.finished = ERROR, f"Cannot store the picture: {e}", time.time()
                    job.eta = self.timings.estimate(job.workflow, mp)
                if job.status == ERROR:
                    b.skipped.append(f"{src.get('name', '?')}: {job.error}")
                self.store.jobs.append(job)
                self._emit("queue-job", job.to_dict())
            b.total = len(items)
            b.state = B_RUNNING
            qlog(self.bridge, "q_jobs_listed", batch=batch_id, jobs=len(items))
            self.store.save()
            self._emit("batch-progress", self._batch_dict(b))
            if not items:
                self._emit("batch-error", {"batch": batch_id, "job": "", "message": "No pictures found for the batch."})
            self._check_batch(batch_id)

    def _snapshot_open(self, b: Batch) -> None:
        """Open-images batch: the canvases are taken at once, when the batch is sent (user 13.11.: a second batch must work on
        what was on screen then, not on the results of the batch that runs before it). A thread of its own does it, so the
        Tk thread never waits for PhotoCraft; _prepare picks the pictures up when it is the batch's turn (call with the lock held)."""
        shot = self._shots[b.id] = {"done": threading.Event(), "items": [], "error": ""}
        shared = self._shared.pop(b.id, None)

        def work():
            qlog(self.bridge, "q_snapshot_begin", batch=b.id)
            try:
                if shared is not None:      # ×n of a direct run (window test 23.11. evening: a pause before both started)
                    while not shared["done"].wait(SNAPSHOT_POLL_S):
                        if self._stop.is_set():
                            return
                    pic = shared.get("pic")
                    if pic is not None:
                        shot["items"] = [({"kind": SOURCE_ACTIVE, "name": str(shared.get("name") or ""),
                                           "index": shared.get("index"), "size": list(pic.size)}, pic, "")]
                        return
                with self._pc_lock:
                    if b.source == SOURCE_ACTIVE:
                        shot["items"] = self._collect_active(b.mode)
                    else:
                        shot["items"] = self._collect_open(b)
            except Exception as e:
                shot["error"] = f"{type(e).__name__}: {e}"
            finally:
                qlog(self.bridge, "q_snapshot_end", batch=b.id, error=bool(shot["error"]))
                shot["done"].set()
        threading.Thread(target=work, name="pcc-snapshot", daemon=True).start()

    def _snapshot_items(self, b: Batch) -> list:
        """The pictures _snapshot_open took (waits for it); a failure of the snapshot is raised here like the old collecting."""
        shot = self._shots.pop(b.id, None)
        if shot is None:                 # no snapshot (a batch of an older kind): collect now
            with self._pc_lock:
                return self._collect_open(b)
        while not shot["done"].wait(SNAPSHOT_POLL_S):
            if self._stop.is_set():
                return []
        if shot["error"]:
            raise RuntimeError(shot["error"])
        return shot["items"]

    def _collect_active(self, mode: str = "") -> list:
        """A queued Generate: the document in front, exported like a run does (what is visible, flattened). The temporary
        files stay until the next run ends (Bridge.run cleans up): a run that is on may still need its own. Text to image
        takes only the canvas size (no picture: None with no error)."""
        try:
            pc = self.bridge.pc.connect()
            sess = pc.session()
            idx = sess.get("active")
            if idx is None:
                return [({"kind": SOURCE_ACTIVE, "name": "", "index": None, "size": [0, 0]}, None,
                         "Open a document in PhotoCraft first.")]
            name = next((str(d.get("name") or "") for d in sess.get("documents") or [] if d.get("index") == idx), "")
            if mode in NO_PICTURE_MODES:
                info = pc.document()
                size = [int(info.get("width") or 0), int(info.get("height") or 0)]
                if not all(size):
                    raise RuntimeError("PhotoCraft did not tell the size of the document.")
                return [({"kind": SOURCE_ACTIVE, "name": name, "index": idx, "size": size}, None, "")]
            tag = uuid.uuid4().hex[:8]
            pic, _ = self.bridge._export(idx, tag, need_mask=False)
            pic.load()
            src = {"kind": SOURCE_ACTIVE, "name": name, "index": idx, "size": list(pic.size)}
            return [(src, pic.copy(), "")]
        except Exception as e:
            return [({"kind": SOURCE_ACTIVE, "name": "", "index": None, "size": [0, 0]}, None,
                     f"Could not take the picture from PhotoCraft: {e}")]

    def _collect_open(self, b: Batch) -> list:
        """Every document open in PhotoCraft: brought to the front one after the other and exported like a run does (what
        is visible, flattened); the document the user had in front is active again afterwards."""
        pc = self.bridge.pc.connect()
        sess = pc.session()
        docs = list(sess.get("documents") or [])
        before = sess.get("active")
        before_name = next((d.get("name") for d in docs if d.get("index") == before), None)
        items = []
        try:
            for d in docs:
                with self._lock:
                    if b.state == B_CANCELLED:
                        break
                idx, name = d.get("index"), str(d.get("name") or "")
                try:
                    pc.activate(idx)
                    info = pc.document()
                    size = [int(info.get("width") or d.get("width") or 0), int(info.get("height") or d.get("height") or 0)]
                    pic, _ = self.bridge._export(idx, uuid.uuid4().hex[:8], need_mask=False)
                    pic.load()
                    if list(pic.size) != size and all(size):
                        size = list(pic.size)
                    items.append(({"kind": SOURCE_OPEN, "name": name, "index": idx, "size": list(pic.size)}, pic.copy(), ""))
                except Exception as e:
                    items.append(({"kind": SOURCE_OPEN, "name": name, "index": idx, "size": [0, 0]}, None,
                                  f"Could not take the picture from PhotoCraft: {e}"))
        finally:
            self.bridge._cleanup()
            if before_name is not None:
                self._activate_by_name(before_name)
        return items

    # ----- internals: one job -----

    def _execute(self, job: Job) -> None:
        with self._lock:
            req0 = self._requests.get(job.batch_id)
            b = self.store.batches.get(job.batch_id)
        if req0 is None:
            self._fail(job, "The settings of this batch are gone (PxC was restarted).", transient=False)
            return
        try:
            if job.mode in NO_PICTURE_MODES and not job.input_png:     # Text to image: only the canvas size counts
                pic = Image.new("RGB", tuple(int(v) for v in job.source.get("size") or (0, 0)), "white")
            else:
                with Image.open(job.input_png) as im:
                    im.load()
                    pic = im.copy()
        except (OSError, ValueError) as e:
            self._fail(job, f"The stored picture is gone: {e}", transient=False)
            return
        comfy = self.bridge.comfy
        # seconds: the job at ComfyUI (from queued to fetched), the part it only waited behind others' jobs, the text-model
        # phase (timings.json has that one): what is left is the image phase (image-timings.json)
        marks = {"prompt": 0.0, "pending": 0.0, "queued": 0.0, "fetched": 0.0}
        watch_stop = threading.Event()

        def on_queued(pid, graph):
            out_node = next((k for k, n in graph.items() if isinstance(n, dict)
                             and str(n.get("_meta", {}).get("title", "")).startswith("pc:output")), "")
            marks["queued"] = time.monotonic()
            with self._lock:
                job.prompt_id, job.out_node = str(pid), str(out_node)
                self.store.save()
                self._emit("queue-job", job.to_dict())
            threading.Thread(target=self._watch, args=(job, str(pid), watch_stop, marks), daemon=True,
                             name="pcc-batch-watch").start()

        def progress(f, msg, phase="", phase_fraction=-1.0, elapsed=0.0, **kw):
            if phase == "prompt" and elapsed:
                marks["prompt"] = max(marks["prompt"], float(elapsed))
            self._emit("batch-step", (f, msg, phase, phase_fraction, elapsed))

        gen = b is not None and b.kind == K_GENERATE
        try:
            req = copy_request(req0)
            if gen:
                if job.seed is not None:
                    req.params.seed = int(job.seed)
                if job.run_no:
                    req.run_no, req.group_name = job.run_no, job.group or req.group_name
            req, p, tag = self.bridge.begin(req)
            job.seed = p.seed
            # a queued Generate counts as Generate in every queue window, a batch as "Batch"
            with comfy.job_context(owner=self.owner, on_queued=on_queued, batch=None if gen else job.batch_id):
                out = self.bridge.process_image(req, p, pic, tag=tag, progress=progress)
            job.written = str(getattr(self.bridge, "last_vgl", "") or "")
            marks["fetched"] = time.monotonic()
            watch_stop.set()
            with self._lock:
                cancelled = self._cancel_running
            if cancelled:
                raise Cancelled()
            placed, paths, shown = self._deliver(job, b, req, p, out, tag, progress, pic.size)
            secs = (marks["fetched"] - marks["queued"] - marks["pending"] - marks["prompt"]) if marks["queued"] else 0.0
            if secs > 0 and job.mp > 0:
                self.timings.record(job.workflow, job.mp, secs)
            with self._lock:
                self._set(job, status=DONE, finished=time.time(), placed=placed, results=list(paths), error="")
                self.store.drop_input(job)
                self._refresh_etas(job.workflow)
                self._after_job(job, shown)
        except Cancelled:
            watch_stop.set()
            with self._lock:
                self._set(job, status=CANCELLED, finished=time.time())
                self._after_job(job, None)
        except Exception as e:
            watch_stop.set()
            with self._lock:
                cancelled = self._cancel_running
            if cancelled:
                with self._lock:
                    self._set(job, status=CANCELLED, finished=time.time())
                    self._after_job(job, None)
            else:
                msg = str(e) or type(e).__name__
                self._fail(job, msg, transient=is_transient(e), oom=is_oom(msg))
        finally:
            watch_stop.set()
            try:
                self.bridge._cleanup()
            except Exception:
                pass

    def _fail(self, job: Job, message: str, transient: bool, oom: bool = False) -> None:
        with self._lock:
            if (transient or oom) and job.auto_retries < MAX_AUTO_RETRIES:
                pid = job.prompt_id
                if pid:      # the job may still sit at ComfyUI: take exactly this one out before it is sent again
                    try:
                        self.bridge.comfy.interrupt(pid)
                    except Exception:
                        pass
                self._set(job, status=WAITING, auto_retries=job.auto_retries + 1, prompt_id="", started=0.0,
                          error=f"Retry {job.auto_retries + 1} of {MAX_AUTO_RETRIES} after: {message}")
                delay = (OOM_RETRY_DELAY_S if oom and not transient else RETRY_DELAY_S) * job.auto_retries
            else:
                self._set(job, status=ERROR, finished=time.time(), error=message)
                self._emit("batch-error", {"batch": job.batch_id, "job": job.id, "message": message})
                self._after_job(job, None)
                return
        self._stop.wait(delay)          # outside the lock: the window can still pause or cancel meanwhile

    def _after_job(self, job: Job, shown) -> None:
        """A job is over (call with the lock held): the dry run's first result is announced, the batch may end."""
        b = self.store.batches.get(job.batch_id)
        if b is None:
            return
        if b.dry_pending and b.state == B_RUNNING and job.status in (DONE, ERROR):
            b.dry_pending = False
            if any(j.status in (WAITING, PAUSED) for j in self.store.jobs if j.batch_id == b.id):
                b.state = B_CONFIRM
                self.store.save()
                self._emit("batch-progress", self._batch_dict(b))
                self._emit("batch-dry", {"batch": b.id, "job": job.to_dict(), "results": list(job.results),
                                         "placed": job.placed, "image": shown, "error": job.error})
                return
        self._check_batch(b.id)

    def _refresh_etas(self, workflow: str) -> None:
        for j in self.store.jobs:
            if j.workflow == workflow and j.status in (WAITING, PAUSED):
                j.eta = self.timings.estimate(workflow, j.mp)

    def _watch(self, job: Job, pid: str, stop: threading.Event, marks: dict) -> None:
        """While our job is at ComfyUI: GET /queue about every QUEUE_POLL_S, "batch-ahead" when the number of other
        clients' jobs before ours changes; the time our job only waited there is kept out of the image timing."""
        last = None
        t = time.monotonic()
        while not stop.wait(QUEUE_POLL_S if last is not None else 0.2):
            try:
                entries = self.bridge.comfy.queue_entries()
            except Exception:
                continue
            now = time.monotonic()
            if any(e["prompt_id"] == pid and not e["running"] for e in entries):
                marks["pending"] += now - t
            t = now
            ahead = self.bridge.comfy.jobs_ahead(pid, entries)
            if ahead != last:
                last = ahead
                self._emit("batch-ahead", {"job": job.id, "batch": job.batch_id, "ahead": ahead})

    # ----- internals: delivering a result -----

    @staticmethod
    def _file_image(req, im: Image.Image, src_size) -> Image.Image:
        """The result as the file gets it: Upscale (and MiniMax at full size) as drawn; Refine and Edit in the picture's
        own size, like the layer Generate places."""
        if req.mode == "upscale" or (getattr(req, "gen_mp", 0) > 0 and getattr(req, "new_document", False)):
            return im.convert("RGB")
        out = im.convert("RGB")
        if tuple(out.size) != tuple(src_size):
            out = out.resize(tuple(src_size), Image.LANCZOS)
        return out

    def _deliver(self, job: Job, b: Batch | None, req, p, out, tag: str, progress, src_size) -> tuple[str, list, Image.Image]:
        """Returns (placed, file paths, the picture as the file gets it)."""
        im = out.results[0][1][0]
        shown = self._file_image(req, im, src_size)
        settings = self._settings.get(job.batch_id)
        paths = []
        if job.source.get("kind") == SOURCE_FOLDER:
            paths.append(str(savefile.save_batch_result(shown, Path(job.source.get("path", "image")).stem, job.mode, settings)))
            return "file", paths, shown
        placed, saved = self._place_in_document(job, req, p, out, tag, progress, shown, settings)
        if saved:
            paths.append(saved)
            return placed, paths, shown
        if job.also_save:
            paths.append(str(savefile.save_batch_result(shown, Path(job.source.get("name", "image")).stem, job.mode, settings)))
        return placed, paths, shown

    def _find_open(self, name: str, index, size) -> int | None:
        """The index of the open document with this name (the same index first) and the same size, else None."""
        pc = self.bridge.pc.connect()
        docs = pc.session().get("documents") or []
        cands = sorted((d for d in docs if d.get("name") == name), key=lambda d: d.get("index") != index)
        for d in cands:
            w, h = d.get("width"), d.get("height")
            if w is None or h is None:
                pc.activate(d["index"])
                info = pc.document()
                w, h = info.get("width"), info.get("height")
            if [int(w or 0), int(h or 0)] == [int(v) for v in size]:
                return d["index"]
        return None

    def _activate_by_name(self, name: str) -> None:
        try:
            pc = self.bridge.pc.connect()
            for d in pc.session().get("documents") or []:
                if d.get("name") == name:
                    pc.activate(d["index"])
                    return
        except Exception:
            pass

    def _active_name(self) -> str | None:
        try:
            s = self.bridge.pc.connect().session()
            return next((d.get("name") for d in s.get("documents") or [] if d.get("index") == s.get("active")), None)
        except Exception:
            return None

    def _place_in_document(self, job: Job, req, p, out, tag, progress, shown, settings) -> tuple[str, str]:
        """Open-images batch, like Generate: Upscale opens a new document; Refine / Edit go as a layer into the document
        when it is still open with the same name and size (one history snapshot per document and batch first), else the
        result is saved as a file and opened as a new document. Returns (placed, path of the file written or "")."""
        with self._pc_lock:             # not while a snapshot of a batch just sent walks through the documents
            return self._place_locked(job, req, p, out, tag, progress, shown, settings)

    def _place_locked(self, job: Job, req, p, out, tag, progress, shown, settings) -> tuple[str, str]:
        name, index, size = job.source.get("name", ""), job.source.get("index"), job.source.get("size") or [0, 0]
        before = self._active_name()
        try:
            new_doc = req.mode == "upscale" or (getattr(req, "gen_mp", 0) > 0 and getattr(req, "new_document", False))
            idx = self._find_open(name, index, size)
            if new_doc:
                self.bridge._place(req, p, out, idx if idx is not None else 0, name, tag, progress)
                return "document", ""
            if idx is None:
                path = savefile.save_batch_result(shown, Path(name or "image").stem, job.mode, settings)
                self._open_file(shown, path.stem)
                return "file", str(path)
            self.bridge.pc.connect().activate(idx)
            b = self.store.batches.get(job.batch_id)
            if b is not None and b.kind == K_GENERATE:
                # a queued Generate takes no history snapshot: the window's Undo hides its layer (docs/plan/generate-queue.md)
                kept = getattr(self.bridge, "_scribble_layer", None)
                self.bridge._scribble_layer = None          # the scribble layer of a direct run is not this job's
                try:
                    res = self.bridge._place(req, p, out, idx, name, tag, progress) or {}
                finally:
                    self.bridge._scribble_layer = kept
                layers = list(res.get("layers") or [])
                top = res.get("group") or (layers[0] if layers else None)
                if top is not None:
                    ev = {"job": job.id, "batch": job.batch_id, "doc": name, "layer": top,
                          "name": f"{req.preset} #{req.run_no}" if req.preset else ""}
                    self._emit("batch-placed", ev)
                return "layer", ""
            self._undo_point(job, name)
            self.bridge._place(req, p, out, idx, name, tag, progress)
            return "layer", ""
        finally:
            if before and before != name:
                self._activate_by_name(before)

    def _undo_point(self, job: Job, name: str) -> None:
        """Before the first result of a batch goes into an open document (it is the active one now): one history snapshot
        for the whole batch in this document, kept in the bridge so "Undo AI edit" on this document goes back to it
        (Bridge.batch_snapshot). Upscale and results opened as new documents take none, like a normal Upscale run."""
        if (job.batch_id, name) not in self._snapshots:
            self._snapshots.add((job.batch_id, name))
            self.bridge.batch_snapshot(name)

    def _open_file(self, im: Image.Image, stem: str) -> None:
        """Open a picture in PhotoCraft as a new document (through the exchange folder, the only place PhotoCraft reads)."""
        fname = f"{stem}.png"
        full = Path(self.bridge.exchange) / fname
        im.convert("RGB").save(full)
        self.bridge._tmp.append(full)
        self.bridge.pc.connect().open(fname)

    # ----- internals: after a restart -----

    def _recover(self) -> None:
        with self._lock:
            jobs = list(self.store.jobs)
            rescue = [j for j in jobs if j.status == RUNNING]
            for j in jobs:
                if j.status in (WAITING, PAUSED):
                    j.status, j.finished, j.error = CANCELLED, time.time(), "Discarded after a restart."
                    self.store.drop_input(j)
                    self._emit("queue-job", j.to_dict())
            self.store.save()
        for j in rescue:
            try:
                self._rescue(j)
            except Exception as e:
                with self._lock:
                    self._set(j, status=ERROR, finished=time.time(), error=f"Result could not be picked up: {e}")
        with self._lock:
            for j in self.store.jobs:
                if j.status in FINISHED:
                    self.store.drop_input(j)
            for f in self.store.orphan_pngs():
                try:
                    f.unlink()
                except OSError:
                    pass
            for b in list(self.store.batches.values()):
                if b.state in (B_PREPARING, B_RUNNING, B_CONFIRM):
                    b.state = B_DONE if any(j.status == DONE for j in self.store.jobs if j.batch_id == b.id) else B_CANCELLED
                    b.finished = time.time()
                    self._emit("batch-done", self._batch_dict(b))
            self.store.save()

    def _rescue(self, job: Job) -> None:
        """One job that was at ComfyUI when the plugin ended."""
        comfy = self.bridge.comfy
        if not job.prompt_id:
            with self._lock:
                self._set(job, status=ERROR, finished=time.time(), error="Stopped before it reached ComfyUI (restart).")
            return
        entries = comfy.queue_entries()
        if any(e["prompt_id"] == job.prompt_id for e in entries):
            hist = comfy.wait(job.prompt_id)            # still there: wait for it
        else:
            hist = comfy.history(job.prompt_id)
        if not hist:
            with self._lock:
                self._set(job, status=ERROR, finished=time.time(),
                          error="ComfyUI no longer knows this job (was it restarted?).")
            return
        status = hist.get("status") or {}
        if status.get("status_str") == "error":
            raise ComfyError("ComfyUI reported an error for this job.")
        im = comfy.output_images(hist, job.out_node or None)[0].convert("RGB")
        src = None
        if job.input_png and Path(job.input_png).exists():
            with Image.open(job.input_png) as f:
                f.load()
                src = imaging.to_rgb(f.copy())
        if src is not None and job.mode in ("upscale", "refine", "edit") and job.detail < 0.999:
            im = Image.blend(src.resize(im.size, Image.LANCZOS), im, max(0.0, job.detail))
        size = job.source.get("size") or list(im.size)
        if job.mode != "upscale" and tuple(im.size) != tuple(size) and all(size):
            im = im.resize(tuple(size), Image.LANCZOS)
        paths, placed = [], "file"
        if job.source.get("kind") == SOURCE_FOLDER:
            paths.append(str(savefile.save_batch_result(im, Path(job.source.get("path", "image")).stem, job.mode)))
        else:
            name = job.source.get("name", "")
            stem = Path(name or "image").stem
            idx = None if job.mode == "upscale" else self._find_open(name, job.source.get("index"), size)
            if job.mode == "upscale":
                self._open_file(im, f"{stem} upscaled {im.size[0]}x{im.size[1]}")
                placed = "document"
            elif idx is not None:
                self.bridge.pc.connect().activate(idx)
                self._undo_point(job, name)
                tag = uuid.uuid4().hex[:8]
                layer = self.bridge._place_png(idx, im, imaging.Box(0, 0, im.size[0], im.size[1]), tag, "rescued")
                self.bridge._try("layer.renameLayer", {"layer": layer, "name": f"AI {job.mode} (batch): {stem}"})
                placed = "layer"
            else:
                path = savefile.save_batch_result(im, stem, job.mode)
                paths.append(str(path))
                self._open_file(im, path.stem)
            if job.also_save and placed != "file":
                paths.append(str(savefile.save_batch_result(im, stem, job.mode)))
            self.bridge._cleanup()
        with self._lock:
            self._set(job, status=DONE, finished=time.time(), placed=placed, results=paths, error="")
            self.store.drop_input(job)
