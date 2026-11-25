"""The @ quick search in the prompt field (user 23.11., choice A "Name fürs Modell"): typing @ in a tab with reference
slots (Multi image edit, Insert reference, Scribble with reference) opens a list under the cursor with the reference images
(preview, "image 2", file name) and, as the last row, the picture in PhotoCraft (user 23.11.: "Auch Bild 1"). Typing on
after the @ narrows the list; Enter, Tab or a click puts the name the model understands ("image 2", "<image2>",
"<ref_image_1>" ...) in place of the @ and what was typed after it; Escape, a space with no match or a click elsewhere closes
the list and keeps the text.

The pure part (at_query, entries, matches) needs no Tk and is tested on any system (tests/test_atpick.py); the list
itself (AtPicker) is tested with a real Tk Text in the same file.
"""
from __future__ import annotations

from .refslots import spaced_tag

PICTURE_TITLE = "Your picture in PhotoCraft"
TIP = "Type @ in the prompt to pick a reference image, e.g. “Place the bag from @ on the table.”"   # under the slots (user 23.11.)
MAX_QUERY = 40          # an @ further back than this is not a search any more (an e-mail address, old text)
LEADS = "([{\"'“‘"      # an @ right after one of these starts a search too; after a letter or digit it does not (name@mail)


def at_query(before: str) -> str | None:
    """`before` is the text in front of the cursor. When it ends with an @ and what was typed after it (no space, no line
    break), returns that typed part ("" right after the @); else None. The @ must start a word: an e-mail address does not
    open the list."""
    i = before.rfind("@")
    if i < 0:
        return None
    q = before[i + 1:]
    if len(q) > MAX_QUERY or any(c.isspace() for c in q) or "@" in q:
        return None
    if i > 0 and not (before[i - 1].isspace() or before[i - 1] in LEADS):
        return None
    return q


def entries(slots, picture: bool = True) -> list[dict]:
    """The rows of the list: one per reference image that is sent (image 2, 3 ...), then the picture in PhotoCraft
    (image 1). Each row: tag (what goes into the prompt), title ("image 2"), name (the file name), image (the preview;
    None for the picture in PhotoCraft) and number (1 = the picture). No naming rule (tag_style): no rows."""
    if slots is None or not getattr(slots, "tag_style", ""):
        return []
    rows = [dict(tag=slots.tag(k), title=f"image {k + 2}", name=it.name or "clipboard", image=it.image, number=k + 2)
            for k, it in enumerate(slots.active)]
    if picture:
        rows.append(dict(tag=slots.picture_tag(), title=PICTURE_TITLE, name="image 1", image=None, number=1))
    return rows


def matches(rows: list[dict], query: str) -> list[dict]:
    """The rows that fit what was typed after the @: a number picks that image ("2" = image 2, "1" = the picture), else the
    typed letters are looked for in the title, the tag and the file name (case does not matter)."""
    q = query.strip().lower()
    if not q:
        return list(rows)
    if q.isdigit():
        return [r for r in rows if str(r["number"]) == q]
    flat = q.replace(" ", "")
    return [r for r in rows if any(q in s.lower() or flat in s.lower().replace(" ", "")
                                   for s in (r["title"], r["tag"], r["name"]))]


def replacement(before_at: str, after: str, tag: str) -> str:
    """What replaces the @ and the typed part: the tag with a space in front and behind where needed (refslots.spaced_tag);
    none in front after an opening bracket or quote, where the @ stood."""
    text = spaced_tag(tag, before_at, after)
    return text[1:] if before_at and before_at[-1] in LEADS and text.startswith(" ") else text


class AtPicker:
    """The list under the cursor of a Tk Text. `rows_fn()` returns the rows (`entries`) or [] where the @ means nothing (no
    reference tab): then typing @ opens nothing. `px(n)` scales a size for the display; `monitor(x, y)` gives the work area
    (x0, y0, x1, y1) of the monitor under a point."""

    ROW_PX = 32          # height of a row (before the display scaling); the preview is a square a little smaller
    WIDTH_PX = 260       # width of the list (before the display scaling)
    CLOSE_ON_FOCUS_LOSS = True     # tests switch it off: other test windows take the focus on a busy machine

    def __init__(self, root, text, rows_fn, px=lambda n: n, monitor=None):
        self.root, self.t, self.rows_fn, self.px, self.monitor = root, text, rows_fn, px, monitor
        self.top = None
        self.start = None        # the text index of the @
        self.rows: list = []     # the rows shown
        self.sel = 0
        self._photos: list = []
        self._frames: list = []
        b = text.bind
        b("<Key>", self._on_key, add="+")
        for seq, fn in (("<Up>", lambda e: self._move(-1)), ("<Down>", lambda e: self._move(1)),
                        ("<Return>", lambda e: self._pick_key()), ("<KP_Enter>", lambda e: self._pick_key()),
                        ("<Tab>", lambda e: self._pick_key()), ("<Escape>", lambda e: self._escape())):
            b(seq, fn, add="+")
        b("<FocusOut>", lambda e: self._focus_lost(), add="+")
        b("<ButtonPress-1>", lambda e: self.close(), add="+")

    # ---- state ----
    @property
    def is_open(self) -> bool:
        return self.top is not None

    def _on_key(self, e):
        """Every key in the field: an @ may open the list, anything else changes what it shows. Tk's own Text binding puts the
        character in after this one, so the look happens when Tk is idle."""
        from .gui_common import idle
        if getattr(e, "char", "") == "@" or self.is_open:
            idle(self.t, self.refresh)
        return None

    def refresh(self):
        """Opens, narrows or closes the list after the text in front of the cursor."""
        try:
            before = self.t.get("1.0", "insert")
        except Exception:
            self.close()
            return
        q = at_query(before)
        if q is None:
            self.close()
            return
        start = self.t.index(f"insert-{len(q) + 1}c")
        if self.is_open and start != self.start:
            self.close()
        if not self.is_open and q:      # the list opens only right after typing the @, not when the cursor wanders back to one
            return
        rows = matches(self.rows_fn() or [], q)
        if not rows:
            self.close()
            return
        self.start = start
        self.sel = 0 if self.rows != rows else min(self.sel, len(rows) - 1)
        self._show(rows)

    def close(self):
        top, self.top = self.top, None
        self.start, self.rows, self._frames, self._photos = None, [], [], []
        if top is not None:
            try:
                top.destroy()
            except Exception:
                pass

    def _focus_lost(self):
        if not self.is_open or not self.CLOSE_ON_FOCUS_LOSS:
            return
        from .gui_common import later

        def check():
            try:
                if self.root.focus_get() is not self.t:
                    self.close()
            except Exception:
                self.close()
        later(self.t, 150, check)

    # ---- keys ----
    def _move(self, d: int):
        if not self.is_open:
            return None
        self.sel = (self.sel + d) % len(self.rows)
        self._paint()
        return "break"

    def _pick_key(self):
        if not self.is_open:
            return None
        self.pick(self.sel)
        return "break"

    def _escape(self):
        if not self.is_open:
            return None
        self.close()
        return "break"

    def pick(self, i: int):
        """Row i: its tag replaces the @ and what was typed after it, as one undo step; the cursor goes behind it."""
        if not self.is_open or not 0 <= i < len(self.rows):
            return
        tag, start, t = self.rows[i]["tag"], self.start, self.t
        self.close()
        if not tag:
            return
        text = replacement(t.get("1.0", start), t.get("insert", "end-1c"), tag)
        auto = t.cget("autoseparators")
        t.configure(autoseparators=False)
        try:
            t.edit_separator()
            t.delete(start, "insert")
            t.insert(start, text)
            t.edit_separator()
        finally:
            t.configure(autoseparators=auto)
        t.mark_set("insert", f"{start}+{len(text)}c")
        t.see("insert")
        t.focus_set()

    # ---- drawing ----
    def _show(self, rows: list):
        import tkinter as tk
        from . import hostos
        from .gui_common import PANEL
        from .popmenu import BORDER
        if self.top is None:
            top = self.top = tk.Toplevel(self.root, **hostos.TOP_KW)
            top.withdraw()
            top.wm_overrideredirect(True)
            top.configure(bg=PANEL, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
            self.rows = []
        if rows != self.rows:
            for f in self._frames:
                f.destroy()
            self.rows, self._frames, self._photos = rows, [], []
            for i, r in enumerate(rows):
                self._frames.append(self._row(i, r))
        self._paint()
        self._place()

    def _row(self, i: int, r: dict):
        import tkinter as tk
        from .gui_common import FG, MUTED, PANEL, font
        from .refslots import _b64, thumbnail_png
        h = int(self.px(self.ROW_PX))
        s = h - int(self.px(6))
        f = tk.Frame(self.top, bg=PANEL, height=h, width=int(self.px(self.WIDTH_PX)), cursor="hand2")
        f.pack_propagate(False)
        f.pack(fill="x")
        if r["image"] is not None:
            photo = tk.PhotoImage(data=_b64(thumbnail_png(r["image"], s)))
        else:
            photo = tk.PhotoImage(width=s, height=s)      # the picture in PhotoCraft: an empty grey square in its place
            photo.put("#6b6b6b", to=(0, 0, s, s))
        self._photos.append(photo)
        pic = tk.Label(f, image=photo, bg=PANEL, bd=0, width=s, height=s)
        pic.pack(side="left", padx=(int(self.px(6)), int(self.px(8))))
        title = tk.Label(f, text=r["title"], bg=PANEL, fg=FG, font=font(9), bd=0, anchor="w")
        title.pack(side="left")
        name = tk.Label(f, text=r["name"], bg=PANEL, fg=MUTED, font=font(8), bd=0, anchor="w")
        if r["name"] != "image 1":
            name.pack(side="left", padx=(int(self.px(8)), int(self.px(6))), fill="x", expand=True)
        for w in (f, pic, title, name):
            w.bind("<Enter>", lambda e, i=i: self._hover(i))
            w.bind("<ButtonPress-1>", lambda e, i=i: (self.pick(i), "break")[1])
        f.parts = (title, name)
        return f

    def _hover(self, i: int):
        if self.sel != i:
            self.sel = i
            self._paint()

    def _paint(self):
        from .gui_common import ACCENT, FG, MUTED, ON_ACCENT, PANEL
        for i, f in enumerate(self._frames):
            hot = i == self.sel
            bg = ACCENT if hot else PANEL
            try:
                f.configure(bg=bg)
                for w in f.winfo_children():
                    w.configure(bg=bg)
                title, name = f.parts
                title.configure(fg=ON_ACCENT if hot else FG)
                name.configure(fg=ON_ACCENT if hot else MUTED)
            except Exception:
                pass

    def _place(self):
        """Under the @ (above it when the screen ends below), inside the monitor's work area."""
        top, t = self.top, self.t
        try:
            top.update_idletasks()
            w, h = top.winfo_reqwidth(), top.winfo_reqheight()
            box = t.bbox(self.start) or t.bbox("insert") or (0, 0, 0, int(self.px(16)))
            x = t.winfo_rootx() + box[0]
            y = t.winfo_rooty() + box[1] + box[3] + 2
            x0, y0, x1, y1 = (self.monitor(x, y) if self.monitor else
                              (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
            if y + h > y1:
                y = max(y0, t.winfo_rooty() + box[1] - h - 2)
            x = max(x0, min(x, x1 - w))
            self.pos = (x, y)           # (a hidden test window reports +0+0, so the tests read this)
            top.wm_geometry(f"+{x}+{y}")
            top.deiconify()
            top.wm_attributes("-topmost", True)
            top.lift()
        except Exception:
            pass
