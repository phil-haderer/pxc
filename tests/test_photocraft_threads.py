# tags: photocraft
"""Two threads that ask PhotoCraft at the same moment each get their own reply at once (window test 23.11. evening: Text to
image with x2 started 18 to 30 s late; the run asked for the document name while the queue took the canvas size on the same
socket, one thread read the other's reply away and waited until something else came). PhotoCraft.call holds one lock per
request. A fake control channel on a free local port answers every request after a short delay; nothing else is contacted.

    python tests/test_photocraft_threads.py
"""
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pccomfy.photocraft import PhotoCraft  # noqa: E402

DELAY = 0.15        # PhotoCraft's answer time: both requests are on the wire before the first reply comes


def serve(listener: socket.socket, stop: threading.Event) -> None:
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = listener.accept()
        except socket.timeout:
            continue
        except OSError:         # the listener was closed at the end
            return
        threading.Thread(target=handle, args=(conn, stop), daemon=True).start()


def handle(conn: socket.socket, stop: threading.Event) -> None:
    buf = b""
    conn.settimeout(0.2)
    with conn:
        while not stop.is_set():
            try:
                chunk = conn.recv(1 << 16)
            except socket.timeout:
                continue
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            lines = []
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                lines.append(json.loads(line))
            if lines:
                time.sleep(DELAY)
            out = b""
            for req in lines:      # all replies of one read in one write: the old code lost one of them in its buffer
                result = {"method": req["method"], "who": (req.get("params") or {}).get("who")}
                out += (json.dumps({"id": req["id"], "ok": True, "result": result}) + "\n").encode()
            if out:
                conn.sendall(out)


def main():
    stop = threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = threading.Thread(target=serve, args=(listener, stop), daemon=True)
    server.start()
    with tempfile.TemporaryDirectory() as tmp:
        token = Path(tmp) / "token"
        token.write_text("t")
        pc = PhotoCraft("127.0.0.1", port, token_file=token, timeout=5.0)
        pc.connect()
        try:
            results, errors = {}, []
            start = threading.Barrier(4)

            def ask(who):
                try:
                    start.wait()
                    results[who] = pc.call("doc.info", {"who": who})
                except Exception as e:      # a lost reply ends in "No reply from PhotoCraft" after the timeout
                    errors.append(f"{who}: {type(e).__name__}: {e}")

            threads = [threading.Thread(target=ask, args=(w,)) for w in ("run", "queue", "tk", "other")]
            t0 = time.monotonic()
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
            took = time.monotonic() - t0
            assert not errors, errors
            assert sorted(results) == ["other", "queue", "run", "tk"], results
            for who, res in results.items():
                assert res == {"method": "doc.info", "who": who}, (who, res)       # each its own reply
            assert took < 4 * DELAY + 2.0, f"four requests took {took:.1f} s"
            # the lock is re-entrant: a call inside a call of the same thread (as _modal_message does) does not hang
            with pc._lock():
                assert pc.call("doc.info", {"who": "inner"})["who"] == "inner"
        finally:
            pc.close()
            stop.set()
            server.join(2)
            listener.close()
    print("photocraft threads: ok")


if __name__ == "__main__":
    main()
