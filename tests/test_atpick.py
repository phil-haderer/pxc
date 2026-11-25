# tags: prompt, multiedit
"""The @ quick search in the prompt (user 23.11., atpick.py): which text opens it, which rows it offers and filters, what a
pick writes (the name the model understands) - the pure part on any system, the list itself with a real Tk Text.

    python tests/test_atpick.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402

from pccomfy import atpick, refslots  # noqa: E402
from pccomfy.atpick import at_query, entries, matches, replacement  # noqa: E402


def slots(style="<image{n}>", n=2, max_refs=3):
    rs = refslots.RefSlots(max_refs=max_refs, tag_style=style)
    for k, name in enumerate(("bag.png", "Table Lamp.jpg", "dog.png")[:n]):
        rs.add(Image.new("RGB", (40, 30), (k * 60, 80, 120)), name)
    return rs


def pure():
    # the @ must start a word; what follows it is the search, until a space
    assert at_query("Place the bag from @") == "" and at_query("@") == "" and at_query("from @ba") == "ba"
    assert at_query("(@2") == "2" and at_query("“@") == "" and at_query("line\n@x") == "x"
    assert at_query("mail me at name@mail") is None          # an e-mail address opens nothing
    assert at_query("from @bag on") is None and at_query("no at sign") is None and at_query("from @a@") is None
    assert at_query("@" + "x" * (atpick.MAX_QUERY + 1)) is None
    # the rows: every reference that is sent, then the picture in PhotoCraft (user 23.11.: "Auch Bild 1")
    rs = slots()
    rows = entries(rs)
    assert [r["tag"] for r in rows] == ["<image2>", "<image3>", "<image1>"]
    assert [r["title"] for r in rows] == ["image 2", "image 3", atpick.PICTURE_TITLE]
    assert rows[0]["name"] == "bag.png" and rows[0]["image"] is not None and rows[-1]["image"] is None
    assert [r["tag"] for r in entries(slots("image {n}"))] == ["image 2", "image 3", "image 1"]          # Flux 2, MiniMax-like
    assert [r["tag"] for r in entries(slots("<ref_image_{i}>"))] == ["<ref_image_1>", "<ref_image_2>", "<ref_image_0>"]   # Flux 3
    assert entries(slots(max_refs=1, n=1))[0]["tag"] == "<image2>" and len(entries(slots(max_refs=1, n=1))) == 2
    rs.max_refs = 1                         # an image beyond the model's slots is kept but not sent: not in the list
    assert [r["number"] for r in entries(rs)] == [2, 1]
    assert entries(slots(n=0)) == [dict(tag="<image1>", title=atpick.PICTURE_TITLE, name="image 1", image=None, number=1)]
    assert entries(refslots.RefSlots(max_refs=3, tag_style="")) == [] and entries(None) == []
    # filtering: a number picks that image, letters look in title, tag and file name
    rows = entries(slots())
    assert matches(rows, "") == rows
    assert [r["number"] for r in matches(rows, "2")] == [2] and [r["number"] for r in matches(rows, "1")] == [1]
    assert [r["number"] for r in matches(rows, "BA")] == [2]
    assert [r["number"] for r in matches(rows, "lamp")] == [3] and [r["number"] for r in matches(rows, "tablel")] == [3]
    assert [r["number"] for r in matches(rows, "image3")] == [3] and [r["number"] for r in matches(rows, "photocraft")] == [1]
    assert matches(rows, "zebra") == [] and matches(rows, "9") == []
    # what replaces the @: spaces where needed (refslots.spaced_tag)
    assert replacement("from ", " on the table.", "image 2") == "image 2"
    assert replacement("from ", "", "<image2>") == "<image2> "
    assert replacement("(", ").", "<image2>") == "<image2>"
    # the tip under the slots, word for word (user 23.11.)
    assert atpick.TIP == "Type @ in the prompt to pick a reference image, e.g. “Place the bag from @ on the table.”"


def with_tk():
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception as e:   # no tkinter or no display (cloud VM)
        print("SKIP Tk part:", e)
        return
    try:
        atpick.AtPicker.CLOSE_ON_FOCUS_LOSS = False
        root.geometry("+40+40")
        t = tk.Text(root, width=50, height=5, undo=True)
        t.pack()
        root.update()
        rs = slots()
        on = {"refs": True}
        p = atpick.AtPicker(root, t, lambda: entries(rs) if on["refs"] else [])

        def typed(s):
            t.insert("insert", s)
            p.refresh()

        typed("Place the bag from @")
        assert p.is_open and [r["number"] for r in p.rows] == [2, 3, 1] and p.sel == 0
        assert len(p._frames) == 3
        typed("la")                                     # narrows to the lamp
        assert p.is_open and [r["number"] for r in p.rows] == [3]
        assert p._pick_key() == "break" and not p.is_open
        t.insert("insert", "on the table.")            # the name ends with a space, so typing goes on
        assert t.get("1.0", "end-1c") == "Place the bag from <image3> on the table.", t.get("1.0", "end-1c")
        t.edit_undo()                                   # Ctrl+Z: one step back to the @ and what was typed
        t.edit_undo()
        assert "<image3>" not in t.get("1.0", "end-1c"), t.get("1.0", "end-1c")
        # the arrow keys move the choice, Enter takes it; the cursor ends behind the name
        t.delete("1.0", "end")
        typed("@")
        assert p._move(1) == "break" and p._move(1) == "break" and p.sel == 2
        p._pick_key()
        assert t.get("1.0", "end-1c") == "<image1> " and t.index("insert") == "1.9", (t.get("1.0", "end-1c"), t.index("insert"))
        # Escape closes and keeps the text; keys do nothing special while the list is closed
        t.delete("1.0", "end")
        typed("x @")
        assert p._escape() == "break" and not p.is_open and t.get("1.0", "end-1c") == "x @"
        assert p._pick_key() is None and p._move(1) is None and p._escape() is None
        # moving back onto an old @ does not open it again; a space or no match closes it
        typed("b")
        assert not p.is_open
        t.delete("1.0", "end")
        typed("@ba")
        assert not p.is_open
        t.delete("1.0", "end")
        typed("@")
        typed(" ")
        assert not p.is_open
        typed("@zz")
        assert not p.is_open
        # an e-mail address and a tab without reference slots open nothing
        t.delete("1.0", "end")
        typed("name@")
        assert not p.is_open
        on["refs"] = False
        typed(" @")
        assert not p.is_open
        on["refs"] = True
        # a click on a row picks it
        t.delete("1.0", "end")
        typed("use @")
        p.pick(1)
        assert t.get("1.0", "end-1c") == "use <image3> " and not p.is_open
        print("Tk part OK")
    finally:
        root.destroy()


def main():
    pure()
    with_tk()
    print("ALL OK (atpick)")


if __name__ == "__main__":
    main()
