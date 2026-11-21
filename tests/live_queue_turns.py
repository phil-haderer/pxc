r"""Manual network check (21.11., decision "Durchsicht 21.11., Lösungen" 1 A): do the participants take turns at ComfyUI?

Runs a real folder batch (Refine with Flux 3 Klein, small grey pictures) through PxC's QueueRunner, without a window and
without PhotoCraft, against a ComfyUI that may run on another PC. Start it on two PCs at about the same time with different
--owner names; the GPU of the ComfyUI PC is used. Afterwards --report reads ComfyUI's /history and prints the order in which
the jobs really ran, with their owner, so taking turns (one of A, one of B, ...) can be seen.

    python tests/live_queue_turns.py --url http://192.168.0.101:8188 --owner "PC A" --n 4
    python tests/live_queue_turns.py --url http://192.168.0.101:8188 --report --since 600

Results go to a temporary folder (printed); nothing is written into the real data/ folder (own PCCOMFY_HOME)."""
import argparse
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="pcc-turns-")
os.environ["PCCOMFY_HOME"] = HOME          # before pccomfy is imported: config.CONFIG_DIR is read once
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from pccomfy import jobqueue as JQ, savefile, workflows  # noqa: E402
from pccomfy.bridge import Bridge, Request  # noqa: E402
from pccomfy.comfy import ComfyUI  # noqa: E402

WF = ROOT / "workflows" / "flux3-klein-refine.json"


class NoPhotoCraft:
    def __getattr__(self, name):
        raise RuntimeError(f"a folder batch used PhotoCraft ({name})")


def run_batch(url: str, owner: str, n: int, size: int) -> int:
    src = Path(HOME) / "in"
    src.mkdir()
    for i in range(n):
        Image.new("RGB", (size, size * 3 // 4), (60 + 40 * i % 180, 90, 140)).save(src / f"{owner[:6]}-{i + 1}.png")
    out = Path(HOME) / "out"
    comfy = ComfyUI(url)
    b = Bridge(NoPhotoCraft(), comfy, HOME)
    got = []
    r = JQ.QueueRunner(b, on_event=lambda k, d: got.append((k, d)), store=JQ.JobStore(Path(HOME) / "q.json", Path(HOME) / "q"),
                       owner=owner)
    req = Request(mode="refine", workflow=str(WF))
    req.params = workflows.GenParams(prompt="", seed=-1)
    t0 = time.time()
    bid = r.start_batch(JQ.BatchSpec(req, JQ.SOURCE_FOLDER, folder=str(src), dry_run=False,
                                     save_settings=savefile.SaveSettings(out, "png", savefile.DEFAULT_PATTERN)))
    print(f"{owner}: batch of {n} sent at {time.strftime('%H:%M:%S')}, client {comfy.client_id[:8]}", flush=True)
    end = time.time() + 1800
    while time.time() < end and not any(k in ("batch-done", "batch-cancelled") for k, _ in got):
        time.sleep(0.5)
    for j in r.jobs(bid):
        print(f"  {j['source'].get('path', '')[-14:]:>14}  {j['status']:<9} prompt {str(j.get('prompt_id'))[:8]}  "
              f"{(j.get('finished') or 0) - (j.get('started') or 0):5.1f} s  {j.get('error', '')[:80]}", flush=True)
    print(f"{owner}: over after {time.time() - t0:.0f} s; results in {out}", flush=True)
    r.stop() if hasattr(r, "stop") else None
    return 0 if all(j["status"] == JQ.DONE for j in r.jobs(bid)) else 1


def report(url: str, since: float) -> int:
    with urllib.request.urlopen(url.rstrip("/") + "/history?max_items=200", timeout=10) as f:
        hist = json.loads(f.read().decode("utf-8"))
    rows = []
    for pid, h in hist.items():
        extra = (h.get("prompt") or [None] * 4)[3] or {}
        start = next((m[1].get("timestamp", 0) / 1000 for m in (h.get("status") or {}).get("messages", [])
                      if m and m[0] == "execution_start"), 0)
        if start and start >= time.time() - since:
            rows.append((start, extra.get(ComfyUI.OWNER_KEY, "?"), extra.get("client_id", "")[:8], pid[:8],
                         (h.get("status") or {}).get("status_str", "")))
    rows.sort()
    for start, owner, client, pid, status in rows:
        print(f"{time.strftime('%H:%M:%S', time.localtime(start))}  {owner:<10} client {client}  prompt {pid}  {status}")
    owners = [r[1] for r in rows]
    runs = sum(1 for a, b in zip(owners, owners[1:]) if a != b)
    print(f"{len(rows)} jobs, {runs} changes of owner")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--owner", default="PC")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--size", type=int, default=768)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--since", type=float, default=900, help="--report: seconds back")
    a = ap.parse_args()
    sys.exit(report(a.url, a.since) if a.report else run_batch(a.url, a.owner, a.n, a.size))


if __name__ == "__main__":
    main()
