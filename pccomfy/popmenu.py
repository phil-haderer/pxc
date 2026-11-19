"""A self-drawn popup menu with cascades (user 12.11.): a native Windows menu can neither keep a margin around its items
nor colour the cascade arrow, so every menu of the app is drawn here instead of with tk.Menu.

The class answers the part of the tk.Menu API the app uses (add_command / add_cascade / add_separator / add_radiobutton /
add_checkbutton, delete, index, type, entrycget, entryconfigure, invoke, tk_popup / post, unpost, bind of "<<MenuSelect>>"
and "<Unmap>"), so a call site is ported by changing `tk.Menu(` to `PopMenu(`. `tk_popup(x, y)` does not block.

Look: a Toplevel (overrideredirect, 1 px border), 5 px empty margin inside it, rows with padx 10 / pady 3, the row under the
mouse or the keyboard on ACCENT with ON_ACCENT text, a grey cascade arrow that turns white on the active row, grey disabled
rows without hover, a 1 px separator with 4 px space around it. All sizes are scaled with `scale`.

Behaviour: one active row shared by mouse and keyboard; a submenu opens 150 ms after the mouse rests on a cascade row (at once
on a click, Right or Return), level with its row, 2 px right of the parent (left of it when there is no room). A global grab
sits on the newest popup of the chain, so a click outside closes the whole chain and does not reach the widget below.
Every mouse event is resolved with screen coordinates (x_root / y_root) against all popups of the chain, so it does not matter
which popup Tk delivers it to. A choice closes the chain first and runs its command afterwards (after_idle)."""
from __future__ import annotations

import itertools
import tkinter as tk
from tkinter import font as tkfont

from . import hostos
from .gui_common import ACCENT, DISABLED, FG, MUTED, ON_ACCENT, PANEL, cancel_later, font, idle, later, tip_window

BORDER = "#5c5c5c"
SEP_COLOR = "#454545"
MARGIN = 5          # px of empty space between the border and the rows, above the first and below the last
MARGIN_X = 0        # and left and right of them: the hover row is filled edge to edge (user 12.11., was 5)
PAD_X, PAD_Y = 10, 3
SEP_GAP = 4         # px of space above and below the separator line
SUB_GAP = 2         # px between a popup and its submenu
OPEN_MS = 150       # the mouse rests this long on a cascade row before the submenu opens
CLOSE_ON_FOCUS_LOSS = True   # tests switch it off: other test windows steal the focus on a busy machine
CLOSE_MS = 250      # grace before a submenu closes because the mouse went to another row (diagonal moves)
TIP_MS = 450        # the mouse (or the keyboard) rests this long on a row with a `tip` before its tooltip shows (as Tooltip)
KINDS = ("command", "cascade", "separator", "radiobutton", "checkbutton")
_ids = itertools.count(1)


class _Ev:
    """What a bound callback gets: the widget is the menu."""
    def __init__(self, widget):
        self.widget = widget
        self.x = self.y = self.x_root = self.y_root = 0


class PopMenu:
    def __init__(self, master, scale: float = 1.0, **ignored_tk_menu_kw):
        self.master, self.scale = master, scale
        self._name = f".popmenu{next(_ids)}"
        self.entries: list[dict] = []
        self._binds: dict[str, list] = {}
        self._top = self._cv = None
        self._geo: tuple | None = None
        self._rows: list[tuple[int, int]] = []     # (top, bottom) of every entry inside the canvas
        self._active: int | None = None
        self._parent: PopMenu | None = None
        self._parent_row: int | None = None
        self._child: PopMenu | None = None
        self._chain: list[PopMenu] = []            # on the root menu of a posted chain: every posted popup, root first
        self._open_job = self._close_job = None
        self._grab_retry = 0
        self._font = None
        self._tip_job = None
        self._tip_win = None

    # ---- tk.Menu-like API -------------------------------------------------------------------------------------------
    def __str__(self):
        return self._name

    def winfo_exists(self) -> bool:
        try:
            return bool(self.master.winfo_exists())
        except tk.TclError:
            return False

    def _add(self, kind, **kw):
        e = {"type": kind, "label": "", "command": None, "state": "normal", "menu": None, "value": None, "variable": None,
             "onvalue": True, "offvalue": False, "accelerator": None, "tip": None, "icon": None, "icon_hot": None}
        e.update({k.lstrip("-"): v for k, v in kw.items() if k.lstrip("-") in e})
        if e["state"] not in ("normal", "disabled", "active"):
            e["state"] = "normal"
        self.entries.append(e)

    def add_command(self, **kw): self._add("command", **kw)
    def add_cascade(self, **kw): self._add("cascade", **kw)
    def add_separator(self, **kw): self._add("separator")
    def add_radiobutton(self, **kw): self._add("radiobutton", **kw)
    def add_checkbutton(self, **kw): self._add("checkbutton", **kw)

    def add(self, kind, cnf=None, **kw):
        if kind not in KINDS:
            raise tk.TclError(f"bad menu entry type \"{kind}\"")
        self._add(kind, **{**(cnf or {}), **kw})

    def _idx(self, i) -> int | None:
        n = len(self.entries)
        if i is None or i == "none":
            return None
        if i == "end" or i == "last":
            return n - 1 if n else None
        if i == "active":
            return self._active
        if isinstance(i, str):
            if i.lstrip("-").isdigit():
                i = int(i)
            else:
                for k, e in enumerate(self.entries):
                    if e["label"] == i:
                        return k
                raise tk.TclError(f"bad menu entry index \"{i}\"")
        if i < 0 or i >= n:
            if i == n:
                return n - 1 if n else None
            raise tk.TclError(f"bad menu entry index \"{i}\"")
        return int(i)

    def index(self, i):
        return self._idx(i)

    def _entry(self, i) -> dict:
        k = self._idx(i)
        if k is None:
            raise tk.TclError(f"bad menu entry index \"{i}\"")
        return self.entries[k]

    def type(self, i) -> str:
        return self._entry(i)["type"]

    def entrycget(self, i, option):
        v = self._entry(i).get(str(option).lstrip("-"))
        return "" if v is None else v

    def entryconfigure(self, i, **kw):
        e = self._entry(i)
        for k, v in kw.items():
            k = k.lstrip("-")
            if k in e:
                e[k] = v
        self.redraw()

    entryconfig = entryconfigure

    def delete(self, first, last=None):
        if not self.entries:
            return
        a = self._idx(first)
        b = a if last is None else self._idx(last)
        if a is None or b is None:
            return
        if self._top is not None:
            self.unpost()
        del self.entries[a:b + 1]
        self._active = None

    def invoke(self, i):
        e = self._entry(i)
        if e["state"] == "disabled" or e["type"] == "separator":
            return None
        var = e["variable"]
        if e["type"] == "radiobutton" and var is not None:
            var.set(e["value"])
        elif e["type"] == "checkbutton" and var is not None:
            var.set(e["offvalue"] if var.get() == e["onvalue"] else e["onvalue"])
        cmd = e["command"]
        return cmd() if callable(cmd) else None

    def bind(self, sequence=None, func=None, add=None):
        if sequence is None or func is None:
            return ""
        lst = self._binds.setdefault(sequence, [])
        if add not in ("+", True):
            lst.clear()
        lst.append(func)
        return f"popmenu-{len(lst)}"

    def _fire(self, sequence):
        for f in list(self._binds.get(sequence, [])):
            try:
                f(_Ev(self))
            except tk.TclError:
                pass

    # ---- geometry ---------------------------------------------------------------------------------------------------
    def _px(self, n) -> int:
        return round(n * self.scale)

    def geometry(self):
        """(x, y, width, height) of the shown popup in screen pixels, None while it is not shown."""
        return self._geo if self._top is not None else None

    def _checked(self, e) -> bool:
        var = e["variable"]
        if var is None:
            return False
        try:
            return var.get() == (e["value"] if e["type"] == "radiobutton" else e["onvalue"])
        except tk.TclError:
            return False

    def _measure(self):
        """Row boxes (top, bottom) inside the margin and the widths; fills self._rows and returns (row_w, content_h)."""
        fnt = self._font = tkfont.Font(root=self.master, font=font(9))
        px = self._px
        has_check = any(e["type"] in ("radiobutton", "checkbutton") for e in self.entries)
        has_arrow = any(e["type"] == "cascade" for e in self.entries)
        has_acc = any(e["accelerator"] for e in self.entries)
        self._check_w = px(16) if has_check else 0
        # an entry may carry an "icon" (a PhotoImage kept by the caller): drawn left of the text, in its own column; "icon_hot"
        # (optional, same size) replaces it on the active row, e.g. the white version on the blue hover (user 12.11.)
        icon_w = max([e["icon"].width() for e in self.entries if e["icon"] is not None] or [0])
        self._icon_w = icon_w + px(8) if icon_w else 0
        self._arrow_w = px(16) if has_arrow else 0
        text_w = max([fnt.measure(e["label"]) for e in self.entries if e["type"] != "separator"] or [0])
        acc_w = max([fnt.measure(str(e["accelerator"])) for e in self.entries if e["accelerator"]] or [0])
        self._acc_w = acc_w + (px(16) if acc_w else 0)
        row_w = px(PAD_X) + self._check_w + self._icon_w + text_w + self._acc_w + self._arrow_w + px(PAD_X)
        row_h = fnt.metrics("linespace") + 2 * px(PAD_Y)
        self._rows, y = [], 0
        for e in self.entries:
            h = px(SEP_GAP) * 2 + 1 if e["type"] == "separator" else row_h
            self._rows.append((y, y + h))
            y += h
        return row_w, y

    def row_top(self, i) -> int:
        """Top of entry i inside the popup window (border and margin included)."""
        return 1 + self._px(MARGIN) + self._rows[i][0]

    # ---- drawing ----------------------------------------------------------------------------------------------------
    def _build(self):
        px = self._px
        row_w, content_h = self._measure()
        m, mx = px(MARGIN), px(MARGIN_X)
        self._row_w = row_w
        top = self._top = tk.Toplevel(self.master, **hostos.TOP_KW)
        top.wm_overrideredirect(True)
        top.configure(bg=PANEL, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        cv = self._cv = tk.Canvas(top, bg=PANEL, highlightthickness=0, bd=0, width=row_w + 2 * mx, height=content_h + 2 * m)
        cv.pack()
        for i in range(len(self.entries)):
            self._draw_row(i)
        for w in (top, cv):
            w.bind("<Motion>", self._on_motion)
            w.bind("<Button-1>", self._on_press)
            w.bind("<Key>", self._on_key)
        top.bind("<FocusOut>", lambda e: later(self.master, 200, self._lost_focus))
        self._w, self._h = row_w + 2 * mx + 2, content_h + 2 * m + 2

    def _row_colors(self, i):
        e = self.entries[i]
        disabled = e["state"] == "disabled"
        hot = i == self._active and not disabled
        return (ACCENT if hot else PANEL), (ON_ACCENT if hot else DISABLED if disabled else FG), (ON_ACCENT if hot else DISABLED if disabled else MUTED)

    def _draw_row(self, i):
        cv, px, m, mx = self._cv, self._px, self._px(MARGIN), self._px(MARGIN_X)
        cv.delete(f"r{i}")
        e = self.entries[i]
        y0, y1 = self._rows[i]
        y0 += m
        y1 += m
        x0, x1 = mx, mx + self._row_w
        if e["type"] == "separator":
            yl = (y0 + y1) // 2
            cv.create_line(x0, yl, x1, yl, fill=SEP_COLOR, width=1, tags=(f"r{i}", f"sep{i}"))
            return
        bg, fg, arrow_fg = self._row_colors(i)
        cv.create_rectangle(x0, y0, x1, y1, fill=bg, outline=bg, tags=(f"r{i}", f"bg{i}"))
        mid = (y0 + y1) // 2
        if e["type"] in ("radiobutton", "checkbutton") and self._checked(e):
            cx = x0 + px(PAD_X) + self._check_w // 2 - px(2)
            if e["type"] == "radiobutton":
                r = px(3)
                cv.create_oval(cx - r, mid - r, cx + r, mid + r, fill=fg, outline=fg, tags=(f"r{i}", f"tick{i}"))
            else:
                s = px(4)
                cv.create_line(cx - s, mid, cx - s // 3, mid + s - 1, cx + s, mid - s + 1, fill=fg, width=max(1, px(2)),
                               tags=(f"r{i}", f"tick{i}"))
        icon = e["icon_hot"] if e["icon_hot"] is not None and bg == ACCENT else e["icon"]
        if icon is not None:
            cv.create_image(x0 + px(PAD_X) + self._check_w, mid, image=icon, anchor="w", tags=(f"r{i}", f"icon{i}"))
        cv.create_text(x0 + px(PAD_X) + self._check_w + self._icon_w, mid, text=e["label"], anchor="w", fill=fg, font=font(9),
                       tags=(f"r{i}", f"fg{i}"))
        if e["accelerator"]:
            cv.create_text(x1 - px(PAD_X) - self._arrow_w, mid, text=str(e["accelerator"]), anchor="e", fill=arrow_fg,
                           font=font(9), tags=(f"r{i}", f"acc{i}"))
        if e["type"] == "cascade":
            ax = x1 - px(PAD_X) - px(3)
            h, w = px(4), px(3)
            cv.create_polygon(ax - w, mid - h, ax + w, mid, ax - w, mid + h, fill=arrow_fg, outline=arrow_fg,
                              tags=(f"r{i}", f"arrow{i}"))

    def redraw(self):
        if self._top is None:
            return
        for i in range(len(self.entries)):
            self._draw_row(i)

    # ---- posting ----------------------------------------------------------------------------------------------------
    def _screen(self):
        try:
            r = self.master
            return r.winfo_vrootx(), r.winfo_vrooty(), r.winfo_vrootx() + r.winfo_vrootwidth(), r.winfo_vrooty() + r.winfo_vrootheight()
        except (tk.TclError, TypeError):
            return -10**6, -10**6, 10**6, 10**6

    def _place(self, x, y):
        l, t, r, b = self._screen()
        x = max(l, min(x, r - self._w))
        y = max(t, min(y, b - self._h))
        self._geo = (x, y, self._w, self._h)
        self._top.wm_geometry(f"{self._w}x{self._h}+{x}+{y}")

    def tk_popup(self, x, y, entry="", anchor_w=None, above_w=None, below_w=None):
        """Shows the menu with its top left corner at screen (x, y) and returns at once. With `anchor_w` (a widget) the
        menu opens to the RIGHT of it, top-aligned (left of it when there is no room), x and y are then ignored.
        With `above_w` it opens ABOVE that widget, right-aligned with it (the footer's hamburger), x and y are then ignored.
        With `below_w` it opens BELOW that widget, right-aligned with it (the "⋯" of the settings window, 19.11.)."""
        self.post(x, y, anchor_w=anchor_w, above_w=above_w, below_w=below_w)

    def post(self, x, y, anchor_w=None, above_w=None, below_w=None):
        if self._top is not None or any(m._top is not None for m in self._chain):
            self.unpost()
        if not self.entries:
            return
        self._parent = self._parent_row = None
        self._build()
        if anchor_w is not None:
            ax, ay, aw = anchor_w.winfo_rootx(), anchor_w.winfo_rooty(), anchor_w.winfo_width()
            x, y = ax + aw + self._px(SUB_GAP), ay
            if x + self._w > self._screen()[2]:
                x = ax - self._w - self._px(SUB_GAP)
        elif above_w is not None:
            x = above_w.winfo_rootx() + above_w.winfo_width() - self._w
            y = above_w.winfo_rooty() - self._h - self._px(SUB_GAP)
        elif below_w is not None:
            x = below_w.winfo_rootx() + below_w.winfo_width() - self._w
            y = below_w.winfo_rooty() + below_w.winfo_height()
        self._place(int(x), int(y))
        self._chain = [self]
        self._show_top(self)

    def _show_top(self, menu):
        top = menu._top
        try:
            top.update_idletasks()
            top.deiconify()
            top.lift()
        except tk.TclError:
            pass
        self._set_grab(menu)
        try:
            top.focus_force()
        except tk.TclError:
            pass

    def _set_grab(self, menu):
        """The grab sits on the newest popup. Global where the platform allows it, else local; retried a few times because
        the window has to be viewable first (X11)."""
        for m in self._chain:
            try:
                if m._top is not None and m is not menu:
                    m._top.grab_release()
            except tk.TclError:
                pass
        try:
            menu._top.grab_set_global()
            return
        except tk.TclError:
            pass
        try:
            menu._top.grab_set()
        except tk.TclError:
            if self._grab_retry < 5:
                self._grab_retry += 1
                later(self.master, 30, lambda: self._chain and self._chain[-1] is menu and self._set_grab(menu))

    def _root_menu(self) -> PopMenu:
        m = self
        while m._parent is not None:
            m = m._parent
        return m

    def _open_sub(self, i, keyboard=False):
        e = self.entries[i]
        sub = e["menu"]
        if e["type"] != "cascade" or e["state"] == "disabled" or not isinstance(sub, PopMenu) or not sub.entries:
            return
        if self._geo is None:
            return
        if self._child is sub and sub._top is not None:
            if keyboard:
                sub._set_active(sub._first_enabled())
            return
        self._close_child()
        root = self._root_menu()
        sub._parent, sub._parent_row = self, i
        sub._build()
        x = self._geo[0] + self._w + self._px(SUB_GAP)
        y = self._geo[1] + self._rows[i][0]
        if x + sub._w > self._screen()[2]:
            x = self._geo[0] - sub._w - self._px(SUB_GAP)
        sub._place(x, y)
        self._child = sub
        root._chain.append(sub)
        root._show_top(sub)
        if keyboard:
            sub._set_active(sub._first_enabled())

    def _close_child(self):
        sub = self._child
        if sub is None:
            return
        sub._close_child()
        self._child = None
        root = self._root_menu()
        if sub in root._chain:
            root._chain.remove(sub)
        sub._destroy_top()
        sub._set_active(None, redraw=False)
        sub._parent = sub._parent_row = None
        sub._fire("<Unmap>")
        if root._chain:
            root._show_top(root._chain[-1])

    # ---- entry tooltips: an entry added with `tip="..."` shows it beside the popup after TIP_MS on its row ---------------
    def _tip_hide(self):
        if self._tip_job is not None:
            try:
                cancel_later(self.master, self._tip_job)
            except tk.TclError:
                pass
            self._tip_job = None
        win, self._tip_win = self._tip_win, None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass

    def _tip_schedule(self, i):
        self._tip_hide()
        if i is None or self._top is None or not self.entries[i].get("tip"):
            return
        self._tip_job = later(self.master, TIP_MS, lambda: self._tip_show(i))

    def _tip_show(self, i):
        self._tip_job = None
        if self._top is None or self._active != i or i >= len(self.entries) or not self.entries[i].get("tip") or self._tip_win:
            return
        x, y, w, h = self._geo
        px = self._px
        ty = y + self.row_top(i)
        try:
            win = tip_window(self.master, self.entries[i]["tip"], x + w + px(SUB_GAP), ty)
            win.update_idletasks()
            l, t, r, b = self._screen()
            tw = win.winfo_reqwidth()
            tx = x + w + px(SUB_GAP)
            if tx + tw > r:                                  # no room right of the popup: left of it
                tx = x - px(SUB_GAP) - tw
            win.wm_geometry(f"+{max(l, tx)}+{ty}")
        except tk.TclError:
            return
        self._tip_win = win

    def _destroy_top(self):
        self._tip_hide()
        top, self._top, self._cv, self._geo = self._top, None, None, None
        if top is not None:
            try:
                top.grab_release()
            except tk.TclError:
                pass
            try:
                top.destroy()
            except tk.TclError:
                pass

    def unpost(self):
        """Closes this menu and everything below it; on the root menu the whole chain."""
        if self._parent is not None:
            self._parent._close_child()
            return
        self._cancel_jobs()
        try:
            if self._child is not None:
                self._close_child()
            was = self._top is not None
            self._destroy_top()
        finally:
            for m in self._chain:
                m._destroy_top()
            self._chain = []
            self._child = None
            self._grab_retry = 0
        self._set_active(None, redraw=False)
        if was:
            self._fire("<Unmap>")

    def destroy(self):
        self.unpost()
        self.entries.clear()

    def _cancel_jobs(self):
        for name in ("_open_job", "_close_job"):
            job = getattr(self, name)
            if job:
                try:
                    cancel_later(self.master, job)
                except tk.TclError:
                    pass
                setattr(self, name, None)

    def _lost_focus(self):
        root = self._root_menu()
        if not CLOSE_ON_FOCUS_LOSS or not root._chain or self._top is None:
            return
        try:
            if root.master.focus_displayof() is not None:
                return
        except (tk.TclError, KeyError):
            pass
        root.unpost()

    # ---- active row -------------------------------------------------------------------------------------------------
    def _selectable(self, i) -> bool:
        e = self.entries[i]
        return e["type"] != "separator" and e["state"] != "disabled"

    def _first_enabled(self):
        return next((i for i in range(len(self.entries)) if self._selectable(i)), None)

    def _set_active(self, i, redraw=True):
        if i is not None and not self._selectable(i):
            i = None
        if i == self._active:
            return
        old, self._active = self._active, i
        self._tip_schedule(i)
        if redraw and self._top is not None:
            for k in (old, i):
                if k is not None:
                    self._draw_row(k)
        self._fire("<<MenuSelect>>")

    # ---- mouse and keyboard (resolved with screen coordinates against the whole chain) ------------------------------
    def _hit(self, xr, yr):
        """(menu, row or None) of the topmost popup of the chain under the screen point, or None."""
        for m in reversed(self._root_menu()._chain):
            if m._geo is None:
                continue
            x, y, w, h = m._geo
            if x <= xr < x + w and y <= yr < y + h:
                ry = yr - y - 1 - m._px(MARGIN)
                for i, (a, b) in enumerate(m._rows):
                    if a <= ry < b and m._px(MARGIN_X) + 1 <= xr - x < w - 1 - m._px(MARGIN_X):
                        return m, i
                return m, None
        return None

    def _on_motion(self, ev):
        self._root_menu()._pointer(ev.x_root, ev.y_root)

    def _on_press(self, ev):
        self._root_menu()._click(ev.x_root, ev.y_root)

    def _on_key(self, ev):
        self._root_menu()._key(ev.keysym)

    def _pointer(self, xr, yr):
        """The mouse is at the screen point: moves the active row, opens or closes submenus (after their delays)."""
        root = self._root_menu()
        hit = root._hit(xr, yr)
        if hit is None:
            for m in root._chain:
                if m._child is None:
                    m._set_active(None)
            return
        m, i = hit
        root._cancel_jobs()
        if m._child is not None and m._child._top is not None and i == m._parent_row_of_child():
            return
        # the pointer is in m: popups below m close (after the grace), m's row i is the active one
        if i is not None and m._selectable(i):
            m._set_active(i)
        else:
            m._set_active(None)
        if m._child is not None:
            root._close_job = later(self.master, CLOSE_MS, m._close_child_if_away)
        e = m.entries[i] if i is not None else None
        if e and e["type"] == "cascade" and m._selectable(i):
            root._open_job = later(self.master, OPEN_MS, lambda mm=m, ii=i: mm._open_if_still(ii))

    def _parent_row_of_child(self):
        return self._child._parent_row if self._child is not None else None

    def _close_child_if_away(self):
        if self._child is not None and self._active != self._child._parent_row:
            self._close_child()

    def _open_if_still(self, i):
        if self._top is not None and self._active == i:
            self._open_sub(i)

    def _click(self, xr, yr):
        root = self._root_menu()
        hit = root._hit(xr, yr)
        if hit is None:
            root.unpost()
            return
        m, i = hit
        if i is None or not m._selectable(i):
            return
        root._cancel_jobs()
        m._set_active(i)
        if m.entries[i]["type"] == "cascade":
            m._open_sub(i)
        else:
            m._choose(i)

    def _choose(self, i):
        root = self._root_menu()
        master = self.master
        root.unpost()
        idle(master, lambda: self.invoke(i))

    def _key(self, keysym):
        root = self._root_menu()
        m = root._chain[-1] if root._chain else self
        n = len(m.entries)
        cur = m._active
        if keysym in ("Down", "Up") and n:
            step = 1 if keysym == "Down" else -1
            k = cur if cur is not None else (-1 if step == 1 else 0)
            for _ in range(n):
                k = (k + step) % n
                if m._selectable(k):
                    m._set_active(k)
                    break
        elif keysym in ("Home", "End") and n:
            order = range(n) if keysym == "Home" else range(n - 1, -1, -1)
            m._set_active(next((k for k in order if m._selectable(k)), None))
        elif keysym == "Right":
            if cur is not None and m.entries[cur]["type"] == "cascade":
                m._open_sub(cur, keyboard=True)
        elif keysym in ("Return", "KP_Enter", "space"):
            if cur is not None and m._selectable(cur):
                if m.entries[cur]["type"] == "cascade":
                    m._open_sub(cur, keyboard=True)
                else:
                    m._choose(cur)
        elif keysym in ("Left", "Escape"):
            if m._parent is not None:
                m._parent._close_child()
            elif keysym == "Escape":
                root.unpost()


def place_right_of(menu: PopMenu, widget):
    """Opens `menu` to the right of `widget`, top-aligned with it (left of it when there is no room)."""
    menu.post(0, 0, anchor_w=widget)
