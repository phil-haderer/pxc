"""Start log of the window (user 22.11.): sometimes the window did not appear until PhotoCraft was minimised and restored.
For the first SECONDS after the start the window writes, only when something changes, where it is, whether it is visible,
tied to PhotoCraft and above it (exchange folder, window-start.log; the last KEEP lines of earlier starts are kept). The next
time it happens, the log shows why. It changes nothing in the window's behaviour."""

from __future__ import annotations

import time
from pathlib import Path

LOG_NAME = "window-start.log"
SECONDS = 30.0          # how long after the start the window's state is written
TICK_MS = 250           # how often the state is looked at in that time
KEEP = 400              # lines kept in the file (several starts)


class StartLog:
    def __init__(self, path: Path, clock=time.monotonic, now=time.strftime):
        self.path, self.clock, self.now = Path(path), clock, now
        self.t0 = clock()
        self._last = None
        self._write(f"=== start {now('%Y-%m-%d %H:%M:%S')}")

    def active(self) -> bool:
        return self.clock() - self.t0 < SECONDS

    def note(self, text: str) -> None:
        """One event (link, placed, shown)."""
        self._write(f"{self.now('%H:%M:%S')} +{self.clock() - self.t0:.2f}s {text}")

    def state(self, text: str) -> None:
        """The window's state: written only when it differs from the last one."""
        if text and text != self._last:
            self._last = text
            self.note(text)

    def _write(self, line: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            old = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
            self.path.write_text("\n".join((old + [line])[-KEEP:]) + "\n", encoding="utf-8")
        except OSError:
            pass            # a log must never stop the window
