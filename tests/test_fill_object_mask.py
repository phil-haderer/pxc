# tags: mask, fill, qwen
"""Qwen Fill: the layer mask follows the object (user 21.11., "Mask follows object"). Qwen often drew the object larger
than the selection and the soft layer mask cut it off; scribble.change_mask adds, opaque, what the result clearly changed
in an area that reaches into the selection. Only Qwen's Fill has it; Remove never.

    python tests/test_fill_object_mask.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp(prefix="pccomfy-fom-"))
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from pccomfy import bridge, fillmask, imaging, models, scribble  # noqa: E402


def main():
    # only Qwen Fill follows the object; the Request carries the flag
    assert models.BY_KEY["qwen"].modes["inpaint"].fill_object_mask
    for key, m in models.BY_KEY.items():
        if key != "qwen" and "inpaint" in m.modes:
            assert not m.modes["inpaint"].fill_object_mask, key
    assert bridge.Request.__dataclass_fields__["fill_object"].default is False

    # a 400 x 300 canvas, the crop (100, 50, 200 x 200) inside it, the selection 60 x 60 in its middle
    W, H = 400, 300
    reg = imaging.Box(100, 50, 200, 200)
    sel = imaging.Box(170, 120, 60, 60)
    rng = np.random.default_rng(1)
    photo = Image.fromarray((120 + rng.integers(-6, 7, (reg.h, reg.w, 3))).astype("uint8"))
    sel_mask = Image.new("L", (reg.w, reg.h), 0)
    ImageDraw.Draw(sel_mask).rectangle((70, 70, 129, 129), fill=255)
    base = fillmask.crop_fade(sel_mask, 4, (True, True, True, True))

    # the result: an object twice as large as the selection, the rest as before
    result = photo.copy()
    ImageDraw.Draw(result).ellipse((40, 40, 159, 159), fill=(230, 40, 40))
    lm = scribble.change_mask(photo, result, sel, reg, (W, H), base)
    a, b = np.asarray(lm), np.asarray(base)
    assert lm.size == (reg.w, reg.h)
    assert (a >= b).all()                                   # never less than the old mask
    assert a[100, 50] == 255 and b[100, 50] < 255, (a[100, 50], b[100, 50])     # the object's left part, outside the selection
    assert a[100, 150] == 255 and a[45 + 5, 100] == 255     # right and top parts too
    assert a[5, 5] < 60                                     # the crop's corner still fades out

    # nothing changed: the old mask; a change that does not touch the selection is left out
    assert np.array_equal(np.asarray(scribble.change_mask(photo, photo.copy(), sel, reg, (W, H), base)), b)
    far = photo.copy()
    ImageDraw.Draw(far).rectangle((2, 2, 30, 30), fill=(0, 0, 255))
    assert np.array_equal(np.asarray(scribble.change_mask(photo, far, sel, reg, (W, H), base)), b)
    # the whole crop redrawn: the old mask stays
    allnew = Image.new("RGB", photo.size, (10, 200, 10))
    assert np.array_equal(np.asarray(scribble.change_mask(photo, allnew, sel, reg, (W, H), base)), b)
    print("ALL OK (Qwen Fill mask follows the object)")


if __name__ == "__main__":
    main()
