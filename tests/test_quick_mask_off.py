# tags: photocraft, mask
"""Quick Mask left on in PhotoCraft (user 24.11.: a red mask flashed at the start of Remove and Fill, the run left a black and
white mask layer in the document and Fill and Remove got a wrong mask): the bridge switches it off before every export and
at the start of a run, but never while this window's own feather preview is shown. A fake PhotoCraft records the commands.

    python tests/test_quick_mask_off.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pccomfy import testguard  # noqa: E402

testguard.isolate_home()
from pccomfy.bridge import Bridge  # noqa: E402
from pccomfy.photocraft import PhotoCraftError  # noqa: E402


class FakePC:
    def __init__(self, quick: bool):
        self.quick = quick
        self.log = []

    def document(self):
        return {"quickMask": self.quick, "layers": [{"id": 1, "visible": True}]}

    def execute(self, command, params=None):
        self.log.append((command, params))
        if command == "select.editInQuickMaskMode":
            self.quick = bool(params and params.get("on"))
        return {}


class Stop(Exception):
    pass


def bridge(pc) -> Bridge:
    b = Bridge.__new__(Bridge)
    b.pc = pc
    b._preview = None
    return b


def main():
    # on: switched off, once
    pc = FakePC(True)
    b = bridge(pc)
    assert b._quick_mask_off() is True
    assert pc.log == [("select.editInQuickMaskMode", {"on": False})] and not pc.quick, pc.log
    assert b._quick_mask_off() is False and len(pc.log) == 1          # off: nothing sent

    # the window's own feather preview shows Quick Mask on purpose: left alone
    pc = FakePC(True)
    b = bridge(pc)
    b._preview = {"doc": "a", "index": 0, "channel": "c", "mask": None}
    assert b._quick_mask_off() is False and pc.log == [] and pc.quick

    # an older PhotoCraft without the field, or an error: nothing sent, no crash
    class Old(FakePC):
        def document(self):
            return {}
    pc = Old(False)
    assert bridge(pc)._quick_mask_off() is False and pc.log == []

    class Broken(FakePC):
        def document(self):
            raise PhotoCraftError("gone")
    assert bridge(Broken(True))._quick_mask_off() is False

    # the export switches it off before the first duplicate is made
    pc = FakePC(True)
    b = bridge(pc)

    def dup(command, params=None, _orig=pc.execute):
        _orig(command, params)
        if command == "image.duplicate":
            raise Stop
    pc.execute = dup
    try:
        b._export(0, "t", need_mask=True)
    except Stop:
        pass
    names = [c for c, _ in pc.log]
    assert names[:2] == ["select.editInQuickMaskMode", "image.duplicate"], names
    messages()
    print("test_quick_mask_off: ok")


def messages():
    """Fenstertest 24.11. ✗ (user: "es startet nicht, das passt, aber die meldung ist falsch"): Quick Mask on and a marquee
    drawn in it; switching Quick Mask off left no selection, and Fill / Remove said "Select the area to fill first". Now its
    own message (choice A), also for Show feather; without Quick Mask the old messages stay."""
    import tempfile

    import numpy as np
    from PIL import Image

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_reference_mode as T
    from pccomfy import workflows
    from pccomfy.bridge import NO_SELECTION, QUICK_MASK_NO_SELECTION, BridgeError, Request

    def req():
        r = Request(mode="inpaint", workflow=str(Path(__file__).resolve().parent.parent / "workflows" / "fibo2-edit.json"),
                    context=0.4, enhance=False)
        r.params = workflows.GenParams(prompt="a red ball", seed=3)
        return r

    def make(quick):
        """quick: None = Quick Mask off and no selection; "empty" = on with nothing painted (a marquee drawn in Quick Mask
        only selects mask pixels, PhotoCraft has no selection after switching it off); "painted" = on with an area."""
        pc, comfy, b = T.make(tempfile.mkdtemp(), with_sel=False)
        b.comfy = comfy
        d = pc.docs[0]
        W, H = d.layers[0]["img"].size
        if quick == "empty":
            d.quick = Image.new("L", (W, H), 0)
        elif quick == "painted":
            q = np.zeros((H, W), np.uint8)
            q[20:60, 20:60] = 255
            d.quick = Image.fromarray(q)
        real = pc.execute

        def execute(command, params=None):
            out = real(command, params)
            if command == "select.editInQuickMaskMode" and d.sel is not None and not np.asarray(d.sel).any():
                d.sel = None            # like PhotoCraft: an empty Quick Mask gives no selection
            return out
        pc.execute = execute
        return pc, b, d

    def error(call) -> str:
        try:
            call()
        except BridgeError as e:
            return str(e)
        raise AssertionError("expected a BridgeError")

    # Fill / Remove: Quick Mask on but empty -> its own message, Quick Mask is off afterwards
    pc, b, d = make("empty")
    assert error(lambda: b.run(req())) == QUICK_MASK_NO_SELECTION
    assert d.quick is None and d.sel is None
    # no Quick Mask, no selection -> the old message
    pc, b, d = make(None)
    assert error(lambda: b.run(req())) == NO_SELECTION
    # Show feather: the same two cases
    pc, b, d = make("empty")
    assert error(lambda: b.show_feather(req())) == QUICK_MASK_NO_SELECTION
    assert d.quick is None and not b.feather_shown
    pc, b, d = make(None)
    assert "Select an area first" in error(lambda: b.show_feather(req()))
    # a painted Quick Mask becomes the selection: the preview shows it (no message)
    pc, b, d = make("painted")
    assert "Hide feather" in b.show_feather(req()) and b.feather_shown
    b.hide_feather()
    assert d.sel is not None and np.asarray(d.sel)[40, 40] == 255


if __name__ == "__main__":
    main()
