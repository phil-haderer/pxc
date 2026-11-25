# tags: window, workflows
"""The tick in front of each custom LoRA row (user 20.11.): unticked, the row stays grey, its LoRA is not sent, and the
state is saved with the page (a third item False). Hidden Tk window.

    python tests/test_lora_toggle.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-loratoggle-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    tkinter.Tk().destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod, gui  # noqa: E402


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()

    app._set_loras([["a.safetensors", 0.8], ["b.safetensors", 1.0, False]])
    a, b = app.lora_rows
    assert a["on"].get() and not b["on"].get()
    assert str(b["entry"].cget("state")) == "disabled" and str(b["spin"].cget("state")) == "disabled"
    assert str(a["entry"].cget("state")) == "normal"
    assert app._loras() == [["a.safetensors", 0.8]]                       # only the ticked row is sent
    assert app._lora_saved() == [["a.safetensors", 0.8], ["b.safetensors", 1.0, False]]
    assert app._collect()["loras"] == app._lora_saved()                   # saved with the page

    b["on"].set(True)
    app._lora_on_changed(b)
    assert str(b["entry"].cget("state")) == "normal"
    assert app._loras() == [["a.safetensors", 0.8], ["b.safetensors", 1.0]]
    assert app._lora_saved() == app._loras()                              # ticked rows are saved as before (two items)

    a["on"].set(False)
    app._lora_on_changed(a)
    assert app._adv_values()["loras"][0][2] is False                      # the "changed" dot sees the tick
    app.root.destroy()
    print("ALL OK (LoRA row tick)")


if __name__ == "__main__":
    main()
