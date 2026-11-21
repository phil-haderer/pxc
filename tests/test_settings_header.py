"""The header of the settings window in the real Tk window (hidden): as high as the plugin's header, the title "Settings"
in the title size (H1: 12 pt, white, thin) at the plugin title's distance from the left edge, and a white line above the
tabs Model Links / Other settings (user 6.11.). Skipped when Tk cannot open a window.

    python tests/test_settings_header.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-sethead-")
os.environ["PCCOMFY_HOME"] = TMP
sys.path.insert(0, str(ROOT))

try:
    import tkinter
    _r = tkinter.Tk()
    _r.destroy()
except Exception as e:                      # no display / no Tk
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import config as cfgmod  # noqa: E402
from pccomfy import gui  # noqa: E402


def main():
    gui.winlink.available = lambda: False
    cfg = cfgmod.load()
    cfg["comfyui"]["url"] = "http://127.0.0.1:1"
    cfg["photocraft"]["port"] = 1
    app = gui.App(cfg)
    app.root.withdraw()
    app.root.update()
    app.open_settings()
    app._settings_win.update()
    bar, title = app._set_bar, [w for w in app._set_bar.winfo_children() if str(w.winfo_class()) == "TLabel"][0]
    # same height as the plugin's header (f_logo is as high as a function button); the windows are not mapped, so ask for the wanted size
    assert bar.winfo_reqheight() == app.f_logo.winfo_reqheight(), (bar.winfo_reqheight(), app.f_logo.winfo_reqheight())
    # the 12 pt title of before, white, not bold (the plugin's "P × C" is 20 % larger since 11.11.; Settings stays as it was)
    assert str(title.cget("text")) == "Settings"
    want = str(gui.ttk.Label(bar, font=gui.font(12)).cget("font"))       # Tk's own spelling of the 12 pt font
    assert str(title.cget("font")) == want, (title.cget("font"), want)
    assert want != str(app.lbl_title[0].cget("font"))
    assert str(title.cget("foreground")) == "#ffffff"
    # no lines and no blue strip (user 19.11.): the header, then the chips of the pages, then the notebook
    nb = app.nb_settings
    row = app.set_tab_chips[0].master.master
    order = app._settings_win.pack_slaves()
    assert order.index(bar) < order.index(row) < order.index(nb), order
    assert not hasattr(app, "sep_set_tabs") and not hasattr(app, "sep_set_under")
    # Escape in the plugin window closes the settings window too (user 20.11.; it no longer stops a run)
    assert app._escape_key() == "break" and app._settings_win is None
    assert app._escape_key() is None, "nothing open: Escape does nothing"
    app.root.destroy()
    shutil.rmtree(TMP, ignore_errors=True)
    print("ok settings header")


if __name__ == "__main__":
    main()
