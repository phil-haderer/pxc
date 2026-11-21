"""The style picker under the Styles button (user 20.11., docs/plan/entscheidungen.md): a popup with the groups as chips on
top ("Custom prompts" first: the saved prompts as a list in the box, user 21.11., choice 2A) and the styles of the chosen group
as square thumbnails, four to a row in equal columns, the name under each (gaps of about 3 px, user 21.11., choice 5A). The mouse on
a thumbnail or a saved prompt shows the whole text beside the popup; a click puts it in (the window's _apply_style / Use) and closes
the popup; a right-click keeps it open (user 21.11.) and hands the item to on_menu (the window opens Append / Replace / Copy text / Save as custom
prompt for a style, Use / Append / Edit / Delete for a saved prompt; user 21.11., choices 2A and 4A). A style without a picture yet
shows its initials on a grey square. A function without styles opens straight on Custom prompts.

Closing: Escape, a click outside (a grab sits on the popup, as with the menus of popmenu.py), or the window losing the focus.
The pictures come from styles.thumb_path (pccomfy/assets/style-thumbs/<name>.png, one per name
for every mode)."""
from __future__ import annotations

import tkinter as tk

from .gui_common import ACCENT, BG, FG, MUTED, ON_ACCENT, PANEL, cancel_later, font, later, tip_window

COLS = 4
TILE = 88             # px of a thumbnail at 100 % (was 84 with GAP 8: the box keeps its width, user 21.11., choice 5A)
GAP = 3
CUSTOM = -1           # the "group" number of Custom prompts
PAD = 10
BORDER = "#5c5c5c"
EMPTY = "#3a3a3a"     # the square of a style without a picture
CLOSE_ON_FOCUS_LOSS = True     # tests switch it off: other test windows steal the focus on a busy machine
PREVIEW_NOTE = "All previews were made with Qwen Image 2.1; other models may give different results."   # under the tiles (user 21.11.)
CLOSE_ON_OUTSIDE_CLICK = True  # tests switch it off: the grab is global, so a real click of the user during a test closed it
TIP_MS = 350


def initials(name: str) -> str:
    words = [w for w in name.replace("&", " ").replace("-", " ").split() if w[:1].isalnum()]
    return "".join(w[0].upper() for w in words[:2]) or "?"


def place(bx: int, by: int, bw: int, bh: int, w: int, h: int, area, gap: int) -> tuple[int, int]:
    """Where the picker opens for a button at (bx, by) of size bw x bh: under it, left-aligned (right-aligned when there is
    no room on the right); above it when there is no room below; beside it when neither fits (small screens, user 21.11.,
    choice C: the button stays free), at the button's height and moved up only as far as the screen needs."""
    x0, y0, x1, y1 = area
    x = bx if bx + w <= x1 else max(x0, bx + bw - w)
    if by + bh + gap + h <= y1:
        return x, by + bh + gap
    if by - gap - h >= y0:
        return x, by - gap - h
    x = bx + bw + gap if bx + bw + gap + w <= x1 else max(x0, bx - gap - w)
    return x, max(y0, min(by, y1 - h))


class StyleGrid:
    def __init__(self, master, groups: list[dict], on_pick, on_custom=None, thumb=None, scale: float = 1.0, group: int = 0,
                 on_group=None, monitor=None, customs=None, on_menu=None, empty_label: str = "No saved prompts yet"):
        """groups: [{"name", "styles": [{"name", "text"}]}]; on_pick(style); on_custom(name): Use of a saved prompt; thumb(name)
        -> a path or None; on_group(i): remember the chosen group (CUSTOM for Custom prompts); monitor(x, y) -> (x0, y0, x1, y1)
        of the screen there; customs() -> the saved prompts [{"name", "text", "label"}]; on_menu(kind, item, x, y): a right-click
        on a style ("style") or a saved prompt ("custom") at screen (x, y); the popup stays open under that menu, the window calls
        menu_closed() when its menu is gone and close() before an entry changes the prompt (user 21.11.)."""
        self.master, self.groups, self.on_pick, self.on_custom = master, groups, on_pick, on_custom
        self.thumb, self.scale, self.on_group, self.monitor = thumb, scale, on_group, monitor
        self.customs, self.on_menu, self.empty_label = customs, on_menu, empty_label
        self.group = group if 0 <= group < len(groups) else (CUSTOM if group == CUSTOM or not groups else 0)
        self.top = None
        self.menu_open = False                # a right-click menu is open over the popup (it stays open, user 21.11.)
        self.chips: list[tk.Label] = []       # [Custom prompts, group 1, group 2, ...]
        self.tiles: list[tk.Frame] = []       # the tiles of the chosen group (each has .style and .canvas)
        self.rows: list = []                  # [the frame of the saved prompts] while Custom prompts is chosen
        self._imgs: list = []                 # the PhotoImages in use (Tk drops a picture nobody holds)
        self._tip = self._tip_job = None
        self.tip_text = ""                    # the text of the box beside the popup ("" = none), for the tests

    def _px(self, v) -> int:
        return max(1, round(v * self.scale))

    # ---- open and close ----

    def open(self, below_w):
        """Opens under `below_w`, left-aligned with it (right-aligned when there is no room on the right)."""
        self.close()
        top = self.top = tk.Toplevel(self.master, bg=BORDER)
        top.withdraw()
        top.wm_overrideredirect(True)
        self.body = tk.Frame(top, bg=BG, padx=self._px(PAD), pady=self._px(PAD))
        self.body.pack(padx=1, pady=1)
        self.f_chips = tk.Frame(self.body, bg=BG, width=self._width())
        self.f_chips.pack(fill="x")
        self.f_tiles = tk.Frame(self.body, bg=BG)
        self.f_tiles.pack(fill="x", pady=(self._px(GAP), 0))
        # one grey line under the tiles: the previews were made with one model (user 21.11.); not under Custom prompts
        self.l_note = tk.Label(self.body, text=PREVIEW_NOTE, bg=BG, fg=MUTED, font=font(8), anchor="w", justify="left",
                               wraplength=self._width(), padx=0, bd=0)
        self._make_chips()
        self._show_group(self.group)
        top.bind("<Escape>", lambda e: self.close())
        top.bind("<ButtonPress>", self._click, add="+")
        top.bind("<FocusOut>", self._focus_out, add="+")
        top.update_idletasks()
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        bx, by, bw, bh = below_w.winfo_rootx(), below_w.winfo_rooty(), below_w.winfo_width(), below_w.winfo_height()
        area = self.monitor(bx, by + bh) if self.monitor else (0, 0, top.winfo_screenwidth(), top.winfo_screenheight())
        x, y = place(bx, by, bw, bh, w, h, area, self._px(2))
        top.wm_geometry(f"+{x}+{y}")
        self.pos = (x, y)
        top.deiconify()
        top.lift()
        try:
            top.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        self._grab()
        try:
            top.focus_force()
        except tk.TclError:
            pass

    def _grab(self, tries: int = 5):
        top = self.top
        if top is None:
            return
        try:
            top.grab_set_global()
            return
        except tk.TclError:
            pass
        try:
            top.grab_set()
        except tk.TclError:
            if tries:
                later(self.master, 30, lambda: self._grab(tries - 1))

    def menu_closed(self):
        """The right-click menu is gone: the popup takes the clicks and the keyboard again."""
        self.menu_open = False
        if self.top is not None:
            self._grab()
            try:
                self.top.focus_force()
            except tk.TclError:
                pass

    def is_open(self) -> bool:
        return self.top is not None

    def close(self):
        self.menu_open = False
        self._hide_tip()
        top, self.top = self.top, None
        if top is not None:
            try:
                top.grab_release()
                top.destroy()
            except tk.TclError:
                pass
        self.chips, self.tiles, self.rows, self._imgs = [], [], [], []

    def _click(self, e):
        """A click outside the popup (the grab sends it here) closes it and goes no further."""
        top = self.top
        if top is None or self.menu_open:
            return None
        x, y = top.winfo_rootx(), top.winfo_rooty()
        if not (x <= e.x_root < x + top.winfo_width() and y <= e.y_root < y + top.winfo_height()):
            if CLOSE_ON_OUTSIDE_CLICK:
                self.close()
            return "break"
        return None

    def _focus_out(self, e=None):
        if not CLOSE_ON_FOCUS_LOSS:
            return

        def check():
            if self.menu_open:          # the right-click menu has the focus, the popup stays
                return
            try:
                if self.top is not None and self.top.focus_get() is None:
                    self.close()
            except (tk.TclError, KeyError):
                self.close()
        later(self.master, 120, check)

    # ---- the parts ----

    def _width(self) -> int:
        """The width of a row of tiles, their highlight rings included."""
        return COLS * (self._px(TILE) + 2 * self._px(2)) + (COLS - 1) * self._px(GAP)

    def _chip(self, text: str, on: bool, command) -> tk.Label:
        c = tk.Label(self.f_chips, text=text, bg=ACCENT if on else PANEL, fg=ON_ACCENT if on else FG,
                     font=font(9, bold=on), padx=self._px(8), pady=self._px(2), cursor="hand2", bd=0)
        c.bind("<Button-1>", lambda e: (command(), "break")[1])
        if not on:
            c.bind("<Enter>", lambda e: c.configure(fg=ACCENT), add="+")
            c.bind("<Leave>", lambda e: c.configure(fg=FG), add="+")
        return c

    def _make_chips(self):
        for c in self.chips:
            c.destroy()
        self.chips = [self._chip("Custom prompts", self.group == CUSTOM, lambda: self._show_group(CUSTOM))]
        for i, g in enumerate(self.groups):
            self.chips.append(self._chip(g["name"], i == self.group, lambda i=i: self._show_group(i)))
        width, gap = self._width(), self._px(4)
        x = y = line_h = 0
        for c in self.chips:
            w, h = c.winfo_reqwidth(), c.winfo_reqheight()
            if x and x + w > width:
                x, y, line_h = 0, y + line_h + gap, 0
            c.place(x=x, y=y)
            x, line_h = x + w + gap, max(line_h, h)
        self.f_chips.configure(width=width, height=y + line_h)

    def _show_group(self, i: int):
        self._hide_tip()
        if i != CUSTOM and not 0 <= i < len(self.groups):
            return
        changed = i != self.group
        self.group = i
        if changed:
            self._make_chips()
            if self.on_group:
                self.on_group(i)
        for t in self.tiles + self.rows:
            t.destroy()
        self.tiles, self.rows, self._imgs = [], [], []
        self._show_note(i != CUSTOM)
        if i == CUSTOM:
            self._show_customs()
            return
        s, gap = self._px(TILE), self._px(GAP)
        ring = 2 * self._px(2)
        for c in range(2 * COLS - 1):   # equal tile columns (even), fixed gap columns between them: a long name no longer
            self.f_tiles.columnconfigure(c, uniform="tile" if c % 2 == 0 else "", minsize=s + ring if c % 2 == 0 else gap)
        for k, style in enumerate(self.groups[i]["styles"]):      # widens its column (user 21.11., choice 5A)
            f = tk.Frame(self.f_tiles, bg=BG)
            f.grid(row=k // COLS, column=2 * (k % COLS), sticky="n", pady=(0 if k < COLS else gap, 0))
            cv = tk.Canvas(f, width=s, height=s, bg=EMPTY, highlightthickness=self._px(2), highlightbackground=BG,
                           highlightcolor=BG, bd=0, cursor="hand2")
            cv.pack()
            img = self._picture(style["name"], s)
            mid = int(cv.cget("highlightthickness")) + s // 2        # canvas coordinates start outside the highlight ring
            if img is not None:
                self._imgs.append(img)
                cv.create_image(mid, mid, image=img)
            else:
                cv.create_text(mid, mid, text=initials(style["name"]), fill=MUTED, font=font(14, bold=True))
            lbl = tk.Label(f, text=style["name"], bg=BG, fg=FG, font=font(8), wraplength=s + ring, justify="center", padx=0, bd=0,
                           cursor="hand2")
            lbl.pack(pady=(self._px(2), 0))
            f.style, f.canvas, f.has_picture = style, cv, img is not None
            for w in (f, cv, lbl):
                w.bind("<Button-1>", lambda e, st=style: (self._pick(st), "break")[1])
                w.bind("<Button-3>", lambda e, st=style: (self._menu("style", st, e), "break")[1])
                w.bind("<Enter>", lambda e, t=f: self._hover(t), add="+")
                w.bind("<Leave>", lambda e, t=f: self._unhover(t), add="+")
            self.tiles.append(f)

    def _show_note(self, on: bool):
        note = getattr(self, "l_note", None)
        if note is None:
            return
        if on and not note.winfo_manager():
            note.pack(fill="x", pady=(self._px(GAP), 0))
        elif not on and note.winfo_manager():
            note.pack_forget()

    def note_shown(self) -> bool:
        """The line about the previews is under the tiles (for the tests)."""
        note = getattr(self, "l_note", None)
        return bool(note is not None and note.winfo_manager())

    def _picture(self, name: str, s: int):
        path = self.thumb(name) if self.thumb else None
        if not path:
            return None
        try:
            from PIL import Image, ImageOps, ImageTk
            with Image.open(path) as im:
                return ImageTk.PhotoImage(ImageOps.fit(im.convert("RGB"), (s, s), Image.LANCZOS), master=self.top)
        except Exception:
            return None

    def _show_customs(self):
        """Custom prompts: one line per saved prompt (its label, cut at the box width), the whole text beside the popup while the
        mouse rests on it; no prompts: one grey line."""
        for c in range(2 * COLS - 1):
            self.f_tiles.columnconfigure(c, uniform="", minsize=0)
        entries = self.customs() if self.customs else []
        width = self._width()
        holder = tk.Frame(self.f_tiles, bg=BG, width=width, height=1)
        holder.grid(row=0, column=0, columnspan=2 * COLS - 1, sticky="we")
        holder.lines = []
        self.rows = [holder]
        if not entries:
            tk.Label(holder, text=self.empty_label, bg=BG, fg=MUTED, font=font(9), anchor="w", padx=self._px(4),
                     width=1).pack(fill="x")
        for e in entries:
            lbl = tk.Label(holder, text=e.get("label", e["name"]), bg=BG, fg=FG, font=font(9), anchor="w", cursor="hand2",
                           padx=self._px(4), pady=self._px(2), width=1)
            lbl.pack(fill="x")
            lbl.entry, lbl.style, lbl.canvas = e, {"name": e["name"], "text": e["text"]}, None
            lbl.bind("<Button-1>", lambda ev, n=e["name"]: (self._use(n), "break")[1])
            lbl.bind("<Button-3>", lambda ev, en=e: (self._menu("custom", en, ev), "break")[1])
            lbl.bind("<Enter>", lambda ev, t=lbl: self._hover(t), add="+")
            lbl.bind("<Leave>", lambda ev, t=lbl: self._unhover(t), add="+")
            holder.lines.append(lbl)
        holder.update_idletasks()
        holder.configure(width=width, height=max(1, sum(w.winfo_reqheight() for w in holder.winfo_children())))
        holder.pack_propagate(False)

    def custom_lines(self) -> list:
        """The lines of the saved prompts while Custom prompts is shown (for the tests)."""
        return list(self.rows[0].lines) if self.group == CUSTOM and self.rows else []

    def _use(self, name: str):
        self.close()
        if self.on_custom:
            self.on_custom(name)

    def _menu(self, kind: str, item: dict, e):
        """A right-click: the popup stays open (user 21.11.), the menu of the window takes the grab until it is gone."""
        if not self.on_menu or self.top is None:
            return
        self._hide_tip()
        self.menu_open = True
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.on_menu(kind, item, e.x_root, e.y_root)

    def _pick(self, style: dict):
        self.close()
        self.on_pick(style)

    # ---- the style text beside the popup ----

    def _hover(self, tile):
        if tile.canvas is None:
            tile.configure(fg=ACCENT)
        else:
            tile.canvas.configure(highlightbackground=ACCENT, highlightcolor=ACCENT)
        cancel_later(self.master, self._tip_job)
        self._tip_job = later(self.master, TIP_MS, lambda: self._show_tip(tile))

    def _unhover(self, tile):
        try:
            if tile.canvas is None:
                tile.configure(fg=FG)
            else:
                tile.canvas.configure(highlightbackground=BG, highlightcolor=BG)
        except tk.TclError:
            pass
        self._hide_tip()

    def _show_tip(self, tile):
        self._tip_job = None
        top = self.top
        if top is None:
            return
        self._hide_tip()
        try:
            gx, gw = top.winfo_rootx(), top.winfo_width()
            y = tile.winfo_rooty()
            tip = tip_window(self.master, tile.style["text"], gx + gw + self._px(4), y)
            tip.update_idletasks()
            x0, y0, x1, y1 = self.monitor(gx, y) if self.monitor else (0, 0, tip.winfo_screenwidth(), tip.winfo_screenheight())
            x = gx + gw + self._px(4)
            if x + tip.winfo_reqwidth() > x1:
                x = max(x0, gx - tip.winfo_reqwidth() - self._px(4))
            tip.wm_geometry(f"+{x}+{max(y0, min(y, y1 - tip.winfo_reqheight()))}")
            tip.wm_attributes("-topmost", True)
            tip.lift()
        except tk.TclError:
            return
        self._tip, self.tip_text = tip, tile.style["text"]

    def _hide_tip(self):
        cancel_later(self.master, self._tip_job)
        self._tip_job = None
        tip, self._tip, self.tip_text = self._tip, None, ""
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass
