# tags: photocraft
"""PhotoCraft in a modal state (user 17.11., choice A): while the Crop tool extends or crops the canvas, PhotoCraft refuses
document commands with "command is unavailable while a modal dialog is open" although no dialog shows. The plugin turns
that into a clear message: CROP_PENDING when ui.inspect says tool "Crop", else MODAL_OPEN. Other errors stay as they were."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pccomfy import photocraft as P  # noqa: E402

REFUSAL = "engine.execute: command is unavailable while a modal dialog is open"


class Fake(P.PhotoCraft):
    def __init__(self, tool="Crop", inspect_fails=False, error=REFUSAL):
        super().__init__()
        self.tool, self.inspect_fails, self.error, self.calls = tool, inspect_fails, error, []

    def call(self, method, params=None):
        self.calls.append(method)
        if method == "ui.inspect":
            if self.inspect_fails:
                raise P.PhotoCraftError("ui.inspect: gone")
            return {"tool": self.tool, "dialogs": []}
        raise P.PhotoCraftError(self.error)


def message(pc):
    try:
        pc.document()
    except P.PhotoCraftError as e:
        return str(e)
    raise AssertionError("no error")


# the Crop tool waits for Enter: the clear message, not PhotoCraft's text
assert message(Fake("Crop")) == P.CROP_PENDING
assert "Enter" in P.CROP_PENDING and "Esc" in P.CROP_PENDING and "Generate" in P.CROP_PENDING
assert message(Fake("crop")) == P.CROP_PENDING
# another tool (a real dialog), or ui.inspect fails too: the general message
assert message(Fake("Brush")) == P.MODAL_OPEN
assert message(Fake(inspect_fails=True)) == P.MODAL_OPEN
# every other refusal keeps its command name and PhotoCraft's text, and ui.inspect is not asked
pc = Fake(error="engine.execute: no document")
assert message(pc) == "document.inspect: engine.execute: no document" and "ui.inspect" not in pc.calls

print("ALL OK (photocraft modal)")
