# tags: window
"""The self-drawn popup menu pccomfy/popmenu.py (user 12.11.): tk.Menu-like API, 5 px margin above and below (none left and right), blue hover row with white text,
cascade arrow grey / white, disabled rows, submenu placement (right, flipped left at the screen edge, no overlap), keyboard,
<<MenuSelect>>, grab released on close. Hidden Tk window; mouse and keys are driven through the menu's own handlers.

    python tests/test_popmenu.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
os.environ["PCCOMFY_HOME"] = tempfile.mkdtemp(prefix="pccomfy-popmenu-")
sys.path.insert(0, str(ROOT))

try:
    import tkinter as tk
    _r = tk.Tk()
    _r.destroy()
except Exception as e:
    print(f"SKIPPED (no Tk window: {e})")
    sys.exit(0)

from pccomfy import popmenu  # noqa: E402
from pccomfy.gui_common import ACCENT, DISABLED, MUTED, ON_ACCENT  # noqa: E402
from pccomfy.popmenu import PopMenu  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL:", msg)


def fill(cv, tag):
    return cv.itemcget(f"bg{tag}", "fill")


def main():
    root = tk.Tk()
    root.withdraw()
    root.geometry("1x1+0+0")
    root.update()
    popmenu.CLOSE_ON_FOCUS_LOSS = False      # other test windows steal the focus when the runner works six at a time
    # The popup holds a global grab, so every real mouse move or click anywhere on the screen reaches it: one move while
    # the test waits for the submenu cancels the 150 ms open timer (red on PC B, 24.11.; a stray <Motion> per wait round
    # reproduces it). The test drives _pointer/_click itself, so the bound handlers ignore real events here; that they
    # forward to the chain is checked once at the end.
    real_motion, real_press = PopMenu._on_motion, PopMenu._on_press
    PopMenu._on_motion = lambda self, ev: None
    PopMenu._on_press = lambda self, ev: None
    log = []

    # ---- API ----
    m = PopMenu(root, tearoff=0, bg="#000", fg="#fff", font=("x", 9))
    check(m.index("end") is None and m.index("active") is None, "empty menu: index end/active is None")
    sub = PopMenu(root)
    sub.add_command(label="Sub one", command=lambda: log.append("sub1"))
    sub.add_command(label="Sub two", command=lambda: log.append("sub2"))
    var = tk.StringVar(root, "a")
    chk = tk.BooleanVar(root, False)
    m.add_command(label="First", command=lambda: log.append("first"), accelerator="Ctrl+F")
    m.add_separator()
    m.add_command(label="Off", command=lambda: log.append("off"), state="disabled")
    m.add_cascade(label="More", menu=sub)
    m.add_radiobutton(label="Radio A", value="a", variable=var, command=lambda: log.append("ra"))
    m.add_radiobutton(label="Radio B", value="b", variable=var)
    m.add_checkbutton(label="Check", variable=chk, command=lambda: log.append("chk"))
    check(m.index("end") == 6, "index end")
    check([m.type(i) for i in range(7)] == ["command", "separator", "command", "cascade", "radiobutton", "radiobutton", "checkbutton"], "types")
    check(m.entrycget(0, "label") == "First" and m.entrycget(2, "state") == "disabled" and m.entrycget(0, "state") == "normal", "entrycget")
    check(m.entrycget(3, "menu") is sub, "entrycget menu")
    check(str(m) != str(sub) and str(m) == str(m), "str unique and stable")
    m.invoke(0)
    m.invoke(2)
    check(log == ["first"], "disabled entry is not invoked")
    m.invoke(5)
    check(var.get() == "b", "radiobutton sets its variable")
    m.invoke(6)
    check(chk.get() is True and log[-1] == "chk", "checkbutton toggles")
    m.entryconfigure(2, state="normal")
    m.invoke(2)
    check(log[-1] == "off", "entryconfigure state normal enables")
    m.entryconfigure(2, state="disabled")
    m.delete(0, "end")
    check(m.index("end") is None, "delete(0, end) empties")
    m.add_command(label="x")
    m.add_command(label="y")
    m.delete(0)
    check(m.entrycget(0, "label") == "y", "delete one")
    m.delete(0, "end")

    # ---- look and geometry ----
    for scale in (1.0, 1.75):
        px = lambda n: round(n * scale)  # noqa: E731
        m = PopMenu(root, scale=scale)
        sub = PopMenu(root, scale=scale)
        sub.add_command(label="Sub one")
        sub.add_command(label="Sub two")
        m.add_command(label="Alpha")
        m.add_separator()
        m.add_command(label="Beta", state="disabled")
        m.add_cascade(label="Gamma", menu=sub)
        sels = []
        m.bind("<<MenuSelect>>", lambda e: sels.append(m.index("active")))
        closed = []
        m.bind("<Unmap>", lambda e: closed.append(1))
        check(m.geometry() is None, "geometry None before post")
        m.tk_popup(100, 120)
        root.update()
        x, y, w, h = m.geometry()
        check((x, y) == (100, 120), f"popup at the given point ({x},{y})")
        cv = m._cv
        check(cv.winfo_reqwidth() == m._row_w, "no margin left and right: the hover row is filled edge to edge (12.11.)")
        r0 = cv.coords("bg0")
        check(int(r0[0]) == 0 and int(r0[1]) == px(5) and int(r0[2]) == m._row_w, f"first row spans the whole width, starts 5 px below the top {r0}")
        check(w == cv.winfo_reqwidth() + 2 and h == cv.winfo_reqheight() + 2, "window = canvas + 1 px border")
        last = cv.coords(f"bg3")
        check(int(last[3]) == cv.winfo_reqheight() - px(5), "last row ends 5 px above the bottom")
        sep = cv.coords("sep1")
        check(sep and sep[1] == sep[3] and cv.itemcget("sep1", "fill") == "#454545" and int(sep[0]) == 0
              and int(sep[2]) == m._row_w, "separator full inner width, colour")
        check(m._rows[1][1] - m._rows[1][0] == 2 * px(4) + 1, "separator has 4 px above and below")
        check(fill(cv, 0) == popmenu.PANEL, "idle row on PANEL")
        check(cv.itemcget("arrow3", "fill") in (MUTED, DISABLED), "cascade arrow grey when idle")
        check(cv.itemcget("fg2", "fill") == DISABLED, "disabled text grey")
        check(root.grab_current() is not None and str(root.grab_current()) == str(m._top), "grab on the popup")

        # hover
        cx = x + w // 2
        m._pointer(cx, y + px(1) + m._px(5) + (m._rows[0][0] + m._rows[0][1]) // 2)
        check(m.index("active") == 0 and fill(cv, 0) == ACCENT and cv.itemcget("fg0", "fill") == ON_ACCENT, "hover row: ACCENT bg, white text")
        m._pointer(cx, y + 1 + m._px(5) + (m._rows[2][0] + m._rows[2][1]) // 2)
        check(m.index("active") is None and fill(cv, 2) == popmenu.PANEL, "disabled row: no hover")
        row3 = (cx, y + 1 + m._px(5) + (m._rows[3][0] + m._rows[3][1]) // 2)
        m._pointer(*row3)
        check(cv.itemcget("arrow3", "fill") == ON_ACCENT and fill(cv, 3) == ACCENT, "cascade arrow white on the active row")
        check(sels[:2] == [0, None] and sels[2] == 3, f"<<MenuSelect>> on every change {sels}")
        # submenu after the delay
        until = time.monotonic() + 10          # the delay timer is late on a busy machine (six test windows at a time)
        while sub.geometry() is None and time.monotonic() < until:
            root.update()
            time.sleep(0.01)
        check(sub.geometry() is not None, "submenu opened after hover")
        if sub.geometry() is None:
            break
        sx, sy, sw, sh = sub.geometry()
        check(sx == x + w + px(2), f"submenu 2 px right of the parent ({sx} vs {x + w})")
        check(sy == y + m._rows[3][0], "submenu first row level with the parent row")
        check(not (sx < x + w and sx + sw > x), "no overlap")
        check(str(root.grab_current()) == str(sub._top), "grab moved to the submenu")
        # Escape in the submenu closes only it
        m._key("Escape")
        check(sub.geometry() is None and m.geometry() is not None, "Escape closes only the submenu level")
        check(str(root.grab_current()) == str(m._top), "grab back on the parent")
        m._key("Escape")
        root.update()
        check(m.geometry() is None and root.grab_current() is None, "Escape closes the menu and releases the grab")
        check(closed == [1], "<Unmap> fired once")

        # keyboard: Down skips separator and disabled
        m.tk_popup(100, 120)
        root.update()
        m._key("Down")
        m._key("Down")
        check(m.index("active") == 3, "Down skips separator and disabled")
        m._key("Down")
        check(m.index("active") == 0, "Down wraps")
        m._key("Up")
        check(m.index("active") == 3, "Up wraps and skips")
        m._key("Right")
        check(sub.geometry() is not None and sub.index("active") == 0, "Right opens the cascade with its first row active")
        m._key("Left")
        check(sub.geometry() is None and m.geometry() is not None, "Left closes the submenu")
        # a click outside closes everything
        m._click(x - 50, y - 50) if x - 50 >= 0 else m._click(x + w + 500, y + h + 500)
        check(m.geometry() is None and root.grab_current() is None, "click outside closes the chain and frees the grab")

        # a choice runs after closing
        got = []
        m2 = PopMenu(root, scale=scale)
        m2.add_command(label="Go", command=lambda: got.append(m2.geometry()))
        m2.tk_popup(200, 200)
        root.update()
        gx, gy, gw, gh = m2.geometry()
        m2._click(gx + gw // 2, gy + gh // 2)
        check(m2.geometry() is None, "chain closed at once on a choice")
        root.update()
        check(got == [None], "command ran after the menu was closed")

    # ---- screen edges ----
    sw_, sh_ = root.winfo_vrootwidth(), root.winfo_vrootheight()
    m = PopMenu(root)
    sub = PopMenu(root)
    sub.add_command(label="A long sub entry here")
    m.add_cascade(label="Cascade", menu=sub)
    m.tk_popup(sw_ - 130, sh_ - 20)
    root.update()
    x, y, w, h = m.geometry()
    check(x + w <= sw_ and y + h <= sh_, "popup kept inside the screen (right and bottom)")
    m._click(x + w // 2, y + 1 + m._px(5) + 3)
    sx, sy, sw, sh = sub.geometry()
    check(sx + sw <= x - 0 and sx >= 0, f"submenu flipped to the left ({sx},{sw} vs {x})")
    check(sy + sh <= sh_, "submenu inside the screen at the bottom")
    m.unpost()
    check(root.grab_current() is None and sub.geometry() is None, "unpost closes the chain")

    # ---- anchor beside a widget ----
    btn = tk.Frame(root, width=40, height=20)
    btn.place(x=0, y=0)
    root.update()
    m = PopMenu(root)
    m.add_command(label="One")
    popmenu.place_right_of(m, btn)
    root.update()
    x, y, w, h = m.geometry()
    check(x == btn.winfo_rootx() + btn.winfo_width() + 2 and y == btn.winfo_rooty(), "opens right of its button, top-aligned")
    m.unpost()

    # ---- entry tips (user 12.11.): after TIP_MS on the row, gone on leaving, on keyboard moves and on close; none without `tip` ----
    popmenu.TIP_MS = 0                       # fake timing: the tip shows at the next idle round
    m = PopMenu(root)
    m.add_command(label="Has tip", tip="Hello tip")
    m.add_command(label="No tip")
    m.add_command(label="Off", tip="never", state="disabled")
    check(m.entrycget(0, "tip") == "Hello tip" and m.entrycget(1, "tip") == "", "tip stored in the entry")
    m.tk_popup(50, 50)
    root.update()
    x, y, w, h = m.geometry()
    cx = x + w // 2
    def rowy(i): return y + 1 + m._px(5) + (m._rows[i][0] + m._rows[i][1]) // 2
    def settle():
        for _ in range(3):
            root.update()
    check(m._tip_win is None, "no tip before hovering")
    m._pointer(cx, rowy(0))
    check(m._tip_win is None and m._tip_job is not None, "tip is scheduled, not shown at once (delay)")
    settle()
    check(m._tip_win is not None and m._tip_win.winfo_exists(), "tip shown after the delay")
    lab = [c for c in m._tip_win.winfo_children()][0]
    check(lab.cget("text") == "Hello tip" and lab.cget("background") == "#ffffe0", "tip looks like the app tooltips")
    check(m._tip_win.winfo_rootx() >= x + w or m._tip_win.winfo_rootx() + m._tip_win.winfo_width() <= x, "tip sits beside the popup, not over it")
    check(m.geometry() is not None and m._top.winfo_exists() and root.grab_current() is not None, "menu stays open and keeps the grab")
    m._pointer(cx, rowy(1))
    check(m._tip_win is None and m._tip_job is None, "tip hidden on a row without tip, nothing scheduled")
    settle()
    check(m._tip_win is None, "row without tip shows nothing")
    m._pointer(cx, rowy(2))
    settle()
    check(m._tip_win is None, "disabled row shows nothing")
    m._pointer(cx, rowy(0))
    settle()
    check(m._tip_win is not None, "tip back on the row")
    m._key("Down")
    check(m._tip_win is None, "keyboard move away hides the tip")
    m._key("Up")
    settle()
    check(m._tip_win is not None, "keyboard on the row shows the tip too")
    win = m._tip_win
    m.unpost()
    check(m._tip_win is None and not win.winfo_exists(), "closing the menu closes the tip")
    m.tk_popup(50, 50)
    m._pointer(cx, rowy(0))
    m.unpost()
    settle()
    check(m._tip_win is None and m._tip_job is None, "closing before the delay cancels the tip")
    popmenu.TIP_MS = 450

    # ---- min_width and font_size (the head's lists, user 21.11.): as wide as the chip, entries in the chip's 10 pt ----
    from pccomfy.gui_common import font as _font
    w = PopMenu(root, font_size=10)
    w.add_command(label="Edit")
    w.tk_popup(50, 50)
    narrow = w.geometry()[2]
    w.unpost()
    w.min_width = narrow + 137
    w.tk_popup(50, 50)
    check(w.geometry()[2] == narrow + 137, f"min_width: the popup is exactly that wide ({w.geometry()[2]} != {narrow + 137})")
    from tkinter import font as tkfont
    want = tkfont.Font(root=root, font=_font(10)).actual("size")
    got = tkfont.Font(root=root, font=w._cv.itemcget("fg0", "font")).actual("size")
    check(got == want and w._font.actual("size") == want, f"font_size 10: the row text in font(10) ({got} != {want})")
    w.unpost()
    w.min_width = 5
    w.tk_popup(50, 50)
    check(w.geometry()[2] == narrow, "min_width smaller than the content: the content width stays")
    w.unpost()
    check(PopMenu(root).font_size == 9, "the other menus keep font 9")

    # ---- the bound handlers forward real mouse events to the chain (real ones are ignored above; a generated <Motion>
    # does not reliably reach the handler on Windows, so the handlers get a made-up event with screen coordinates) ----
    PopMenu._on_motion, PopMenu._on_press = real_motion, real_press
    hits = []
    m = PopMenu(root)
    m.add_command(label="Click me", command=lambda: hits.append(1))
    m.tk_popup(60, 60)
    root.update()
    for w in (m._top, m._cv):
        check(w.bind("<Motion>") and w.bind("<Button-1>"), f"<Motion> and <Button-1> bound on {w.winfo_class()}")
    x, y, w, h = m.geometry()
    ev = SimpleNamespace(x_root=x + w // 2, y_root=y + 1 + m._px(5) + (m._rows[0][0] + m._rows[0][1]) // 2)
    m._on_motion(ev)
    check(m.index("active") == 0, "_on_motion moves the active row to the pointer")
    m._on_press(ev)
    root.update()
    check(hits == [1] and m.geometry() is None, "_on_press on the row runs it and closes the menu")
    m.unpost()

    # ---- no dark text on the accent, no hard-coded orange ----
    src = (ROOT / "pccomfy" / "popmenu.py").read_text(encoding="utf-8").lower()
    check("#1b1b1b" not in src, "no #1b1b1b in popmenu.py")
    check("orange" not in src and "#f" not in src.replace("#fff", ""), "no orange colours in popmenu.py")

    root.destroy()
    print("popmenu:", "FAILED " + str(len(fails)) if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
