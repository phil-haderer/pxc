"""The window without title bar (Windows) has a 1 px frame: blue (ACCENT) while the plugin has the focus, grey otherwise
(user 18.11.). Stubbed Tk.

    python tests/test_focus_frame.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reset_all as ra  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)
from pccomfy import gui  # noqa: E402


def main():
    app = ra.make()
    app._frameless = True                 # as on Windows (Linux has the window manager's frame)
    seen = []
    app.root.configure = lambda **kw: seen.append(kw)
    app.root.focus_get = lambda: app.t_prompt
    app._focus_frame()
    assert seen[-1] == {"highlightbackground": gui.ACCENT, "highlightcolor": gui.ACCENT}, seen
    app.root.focus_get = lambda: None     # another program has the focus
    app._focus_frame()
    assert seen[-1] == {"highlightbackground": gui.WINDOW_BORDER, "highlightcolor": gui.WINDOW_BORDER}, seen

    def unnamed():
        raise KeyError("popdown")         # a combobox list: Tk cannot name it, it still belongs to the plugin
    app.root.focus_get = unnamed
    app._focus_frame()
    assert seen[-1]["highlightbackground"] == gui.ACCENT
    n = len(seen)
    app._frameless = False                # with a title bar: nothing to colour
    app._focus_frame()
    assert len(seen) == n
    src = (Path(gui.__file__).read_text(encoding="utf-8"))
    assert 'self.root.bind("<FocusIn>"' in src and 'self.root.bind("<FocusOut>"' in src
    print("ALL OK (focus frame)")


if __name__ == "__main__":
    main()
