"""Scribble on photo (Sketch, docs/sketch-plan.md, decisions of 9.11. evening): find the scribble, cut the crop around it, and
put the result back only there. No Tk, no PhotoCraft: the bridge hands in pictures and gets pictures back.

The settings are the ones the blind test rounds 5 to 7 rated best (docs/tests/sketch-ergebnis.md):
- the scribble is found on its own layer (the top layer, mostly transparent, one colour), else by colour: bright green
  first, then pure red (round 7: on a red neon wall the wall outweighed a green scribble when the larger area won);
  a scribble covers at least MIN_SHARE of the picture (clean photos had red specks of 107 and 314 pixels, the smallest
  real scribble 2410); a thin frame drawn round an area counts with half of that when its box covers at least
  FRAME_BOX of the picture (writer round 10.11.: a 2 px rectangle round a facade had 481 pixels in 1.5 MP);
- only a crop around it is generated: the box (+ 8 %) grown by CONTEXT (40 %; 100 % gave twice the faults);
- the result is shifted to the photo's colours in the ring around the scribble (mean and spread per channel, spread
  held to 0.7 .. 1.4) and comes back opaque over the box, fading to 0 at the crop's sides (as Fill with Qwen and Fibo).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from . import fillmask, imaging

RED = (252, 2, 2)          # as measured on the user's scribbles
GREEN = (0, 255, 0)        # bright pure green (user 9.11.: for photos with much red)
PAD = 0.08                 # the box around the strokes, a little larger
MIN_SHARE = 0.0005         # 0.05 % of the picture (about 1000 pixels at 2 MP)
FRAME_SHARE = 0.5          # a thin frame needs only half of MIN_SHARE ...
FRAME_BOX = 0.01           # ... when the box of its strokes covers at least 1 % of the picture (a speck's box is tiny)
CONTEXT = 0.4              # the crop around the box, as Remove with Flux and Qwen
RING_PAD = 0.20            # the colour match leaves out the box + 20 % (where the new object may reach)
FEATHER_PCT = 10.0         # soft edge in % of the box's shorter side
LAYER_MAX_SHARE = 0.5      # a scribble layer covers at most half of the canvas
LAYER_ONE_COLOUR = 0.9     # ... and at least 90 % of its solid pixels are near its main colour
LAYER_THIN_PX = 0.004      # ... and it is thin: shrunk by 0.4 % of the shorter canvas side (at least 4 px) ...
LAYER_THIN_LEFT = 0.5      # ... at most half of it is left


@dataclass
class Found:
    box: imaging.Box       # the strokes' box, PAD larger, in canvas pixels
    box20: imaging.Box     # the same with RING_PAD (the part the colour match leaves out)
    how: str               # "layer", "green" or "red"


def colour_pixels(a: np.ndarray, colour) -> np.ndarray:
    """Where an RGB array is the scribble's pure colour: its strongest channel above 200 and 140 above both others."""
    c = int(np.argmax(colour))
    o = [i for i in range(3) if i != c]
    return (a[..., c] > 200) & (a[..., c] - a[..., o[0]] > 140) & (a[..., c] - a[..., o[1]] > 140)


def _pad(x0: int, y0: int, x1: int, y1: int, size: tuple[int, int], pad: float) -> imaging.Box:
    W, H = size
    dx, dy = round((x1 - x0) * pad), round((y1 - y0) * pad)
    x0, y0, x1, y1 = max(0, x0 - dx), max(0, y0 - dy), min(W - 1, x1 + dx), min(H - 1, y1 + dy)
    return imaging.Box(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))


def _largest_area(hit: np.ndarray) -> tuple[int, tuple | None]:
    """(pixels, (x0, y0, x1, y1)) of the largest connected area of `hit`; connected on a grid 8 times smaller with the
    lines thickened, so a scribble drawn in several strokes stays one area (as tests/live_sketch.py scribble_box)."""
    if hit.sum() < 1:
        return 0, None
    H, W = hit.shape
    k = 8
    small = Image.fromarray((hit * 255).astype("uint8")).resize((max(1, W // k), max(1, H // k)), Image.BOX)
    grid = np.asarray(small.point(lambda v: 255 if v > 0 else 0).filter(ImageFilter.MaxFilter(7))) > 0
    seen = np.zeros_like(grid, dtype=bool)
    best = (0, None)
    for y0, x0 in zip(*np.nonzero(grid)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < grid.shape[0] and 0 <= xx < grid.shape[1] and grid[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
        cy0, cy1 = min(c[0] for c in comp) * k, (max(c[0] for c in comp) + 1) * k
        cx0, cx1 = min(c[1] for c in comp) * k, (max(c[1] for c in comp) + 1) * k
        part = hit[cy0:cy1, cx0:cx1]
        n = int(part.sum())
        if n > best[0]:
            ys, xs = np.nonzero(part)
            best = (n, (int(xs.min() + cx0), int(ys.min() + cy0), int(xs.max() + cx0), int(ys.max() + cy0)))
    return best


def colour_area(im: Image.Image, colour) -> tuple[int, imaging.Box | None]:
    """(pixels of `colour` in its largest connected area, its box + PAD); (0, None) when there is none."""
    a = np.asarray(im.convert("RGB")).astype(int)
    n, xy = _largest_area(colour_pixels(a, colour))
    return (n, _pad(*xy, im.size, PAD)) if xy else (0, None)


def _found(xy: tuple, size: tuple[int, int], how: str) -> Found:
    return Found(_pad(*xy, size, PAD), _pad(*xy, size, RING_PAD), how)


def find_by_colour(im: Image.Image) -> Found | None:
    """Green first, then red; None when neither has a scribble of at least MIN_SHARE of the picture."""
    a = np.asarray(im.convert("RGB")).astype(int)
    least = MIN_SHARE * im.width * im.height
    for colour, how in ((GREEN, "green"), (RED, "red")):
        n, xy = _largest_area(colour_pixels(a, colour))
        if xy and (n >= least or _thin_frame(n, xy, im.size)):
            return _found(xy, im.size, how)
    return None


def _thin_frame(n: int, xy: tuple, size: tuple[int, int]) -> bool:
    """A thin outline round an area: few pixels (at least FRAME_SHARE of the minimum) but a box of FRAME_BOX or more."""
    area = size[0] * size[1]
    box = (xy[2] - xy[0] + 1) * (xy[3] - xy[1] + 1)
    return n >= FRAME_SHARE * MIN_SHARE * area and box >= FRAME_BOX * area


def is_scribble_layer(layer: Image.Image) -> bool:
    """A layer (RGBA, canvas size) that looks like strokes on an empty layer: at least MIN_SHARE and at most LAYER_MAX_SHARE
    of the canvas visible, its solid pixels nearly all of one colour, and thin (a cut-out person or object on its own layer
    is many colours and solid, a photo layer covers the canvas). A solidly filled blob on its own layer does not count:
    then the colour search decides."""
    rgba = np.asarray(layer.convert("RGBA")).astype(int)
    alpha = rgba[..., 3]
    seen = alpha > 8
    share = seen.mean()
    if not (MIN_SHARE <= share <= LAYER_MAX_SHARE):
        return False
    solid = rgba[..., :3][alpha > 200]
    if len(solid) < 20:
        return False
    main = np.median(solid, axis=0)
    near = np.abs(solid - main).sum(-1) < 90
    if near.mean() < LAYER_ONE_COLOUR:
        return False
    # strokes are thin: shrunk by a few pixels, little of them is left (the user's round 6 scribbles: at most 10 %; a cut-out,
    # even of a plain one-coloured area: at least 81 %)
    r = max(4, round(LAYER_THIN_PX * min(layer.size)))
    m = Image.fromarray((seen * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * r + 1))
    return bool((np.asarray(m) > 0).sum() <= LAYER_THIN_LEFT * seen.sum())


def find_on_layer(layer: Image.Image) -> Found | None:
    """The scribble on its own layer (any colour): the box of its largest connected area (a stray dot elsewhere on the
    layer does not count); None when it is no scribble layer."""
    if not is_scribble_layer(layer):
        return None
    _n, xy = _largest_area(np.asarray(layer.convert("RGBA"))[..., 3] > 8)
    return _found(xy, layer.size, "layer") if xy else None


def find(picture: Image.Image, top_layer: Image.Image | None = None) -> Found | None:
    """The decided order (9d): the top layer when it is a scribble layer, else the colours of the whole picture."""
    if top_layer is not None:
        hit = find_on_layer(top_layer)
        if hit:
            return hit
    return find_by_colour(picture)


def region(found: Found, size: tuple[int, int]) -> imaging.Box:
    """The crop the model gets: the box grown by CONTEXT, inside the canvas."""
    return imaging.grow_box(found.box, size, CONTEXT)


def box_mask(size: tuple[int, int], box: imaging.Box, feather_pct: float = FEATHER_PCT) -> Image.Image:
    """Opaque over `box`, soft outwards by feather_pct of its shorter side (the rectangle grown by the radius, then
    blurred); canvas size. Used for the ring the colour match leaves out."""
    r = imaging.feather_radius(box.w, box.h, feather_pct)
    m = Image.new("L", size, 0)
    m.paste(255, (max(0, box.x - r), max(0, box.y - r), min(size[0], box.x + box.w + r), min(size[1], box.y + box.h + r)))
    return m.filter(ImageFilter.GaussianBlur(r / 2.0)) if r > 0 else m


def fade_mask(size: tuple[int, int], box: imaging.Box, reg: imaging.Box, feather_pct: float = FEATHER_PCT) -> Image.Image:
    """The layer mask: opaque over the box, then a smooth fade that reaches 0 exactly at the crop's sides inside the
    picture (fillmask.crop_fade, as Fill with Qwen and Fibo); canvas size, 0 outside the crop."""
    W, H = size
    m = Image.new("L", (reg.w, reg.h), 0)
    m.paste(255, (box.x - reg.x, box.y - reg.y, box.x - reg.x + box.w, box.y - reg.y + box.h))
    inner = (reg.x > 0, reg.y > 0, reg.x + reg.w < W, reg.y + reg.h < H)
    soft = fillmask.crop_fade(m, imaging.feather_radius(box.w, box.h, feather_pct), inner)
    full = Image.new("L", (W, H), 0)
    full.paste(soft, (reg.x, reg.y))
    return full


def colour_match(result: Image.Image, photo: Image.Image, ring: np.ndarray) -> Image.Image:
    """`result` (same size as `photo`) shifted per channel to the mean and spread of `photo` where `ring` is True; the
    spread change held to 0.7 .. 1.4. Unchanged when the ring is under 100 pixels."""
    r = np.asarray(result.convert("RGB")).astype(float)
    p = np.asarray(photo.convert("RGB")).astype(float)
    if ring.sum() < 100:
        return result.convert("RGB")
    out = r.copy()
    for c in range(3):
        mr, sr = r[..., c][ring].mean(), r[..., c][ring].std() + 1e-6
        mp, sp = p[..., c][ring].mean(), p[..., c][ring].std()
        out[..., c] = (r[..., c] - mr) * min(1.4, max(0.7, sp / sr)) + mp
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8))


def context_ring(size: tuple[int, int], reg: imaging.Box, leave_out: Image.Image) -> np.ndarray:
    """True inside the crop `reg` where `leave_out` is 0: the photo around the scribble the model should have kept."""
    W, H = size
    ring = np.zeros((H, W), bool)
    ring[reg.y:reg.y + reg.h, reg.x:reg.x + reg.w] = True
    return ring & (np.asarray(leave_out) == 0)


CHANGE_LEVEL = 30          # Reference at scribble: a change of the smoothed picture by this much (0..255) counts as the object
CHANGE_BLUR = 0.003        # ... smoothed by 0.3 % of the crop's shorter side (the regenerated ground's grain drops out)
CHANGE_GROW = 0.02         # ... the object's area grown by 2 % and
CHANGE_SOFT = 0.004        # ... the fade from it at most 0.4 % wide plus the room to the crop's sides
CHANGE_MAX = 0.85          # more than this share of the crop changed: the whole crop was redrawn, the fade alone stays


def _areas_touching(hit: np.ndarray, box: tuple[int, int, int, int], k: int = 4) -> np.ndarray:
    """The connected areas of `hit` (on a grid k times smaller) that reach into `box` (x0, y0, x1, y1), full size."""
    H, W = hit.shape
    gw, gh = max(1, W // k), max(1, H // k)
    grid = np.asarray(Image.fromarray((hit * 255).astype("uint8")).resize((gw, gh), Image.BOX)) > 0
    keep = np.zeros_like(grid)
    bx0, by0 = max(0, box[0] // k), max(0, box[1] // k)
    bx1, by1 = min(gw, -(-box[2] // k)), min(gh, -(-box[3] // k))
    stack = [(y, x) for y, x in zip(*np.nonzero(grid[by0:by1, bx0:bx1]))]
    stack = [(y + by0, x + bx0) for y, x in stack]
    for y, x in stack:
        keep[y, x] = True
    while stack:
        y, x = stack.pop()
        for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= yy < gh and 0 <= xx < gw and grid[yy, xx] and not keep[yy, xx]:
                keep[yy, xx] = True
                stack.append((yy, xx))
    return np.asarray(Image.fromarray((keep * 255).astype("uint8")).resize((W, H), Image.NEAREST)) > 0


def _grow_square(a: np.ndarray, size: int) -> np.ndarray:
    """`a` (bool) grown by a size x size square: the same as PIL's MaxFilter(size), but in two passes of shifted maxima
    (MaxFilter(31) took 12 s on a 9 MP crop and 30 s on a 20 MP canvas; the plugin seemed to hang, user 15.11.)."""
    r = size // 2
    out = a.copy()
    for axis in (1, 0):
        src, out = out, out.copy()
        n = src.shape[axis]
        for d in range(1, min(r, n - 1) + 1):
            if axis == 1:
                out[:, d:] |= src[:, :-d]
                out[:, :-d] |= src[:, d:]
            else:
                out[d:, :] |= src[:-d, :]
                out[:-d, :] |= src[d:, :]
    return out


def whole_canvas_fade(hard: Image.Image, radius: int) -> Image.Image:
    """Opaque where `hard` is, fading to 0 over about `radius` px outside it (for a crop that is the whole canvas)."""
    a = np.asarray(hard, dtype=np.float32)
    blur = np.asarray(hard.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32)
    return Image.fromarray(np.maximum(a, np.clip(blur * 2.0, 0, 255)).round().astype(np.uint8))


def object_mask(photo: Image.Image, layer: Image.Image, found: Found, reg: imaging.Box,
                feather_pct: float = FEATHER_PCT) -> Image.Image:
    """Reference at scribble (user 15.11., window test: Flux 3 and Fibo drew the object larger than the scribble, and what
    reached past the box lay in the fade and came out soft): like fade_mask, but opaque over the box AND wherever the result
    changed the photo clearly in an area that reaches into the box (the object and its shadow); the fade starts from that
    shape (fillmask.crop_fade). Falls back to fade_mask when the whole crop changed. `layer` is put_back's layer (canvas
    size); the result is canvas size."""
    a = np.asarray(photo.convert("RGB").crop(reg.pil())).astype(np.int16)
    b = np.asarray(layer.convert("RGB").crop(reg.pil())).astype(np.int16)
    side = min(reg.w, reg.h)
    diff = Image.fromarray(np.abs(a - b).max(axis=2).astype(np.uint8))
    diff = np.asarray(diff.filter(ImageFilter.GaussianBlur(max(1.0, side * CHANGE_BLUR))))
    hit = diff > CHANGE_LEVEL
    W, H = photo.size
    inner = (reg.x > 0, reg.y > 0, reg.x + reg.w < W, reg.y + reg.h < H)
    if not hit.any() or hit.mean() > CHANGE_MAX:
        # the whole canvas went to the model (Fibo): no crop side to fade towards, the usual crop stands in for it
        return fade_mask(photo.size, found.box, reg if any(inner) else region(found, photo.size), feather_pct)
    bx, by = found.box.x - reg.x, found.box.y - reg.y
    obj = _areas_touching(hit, (bx, by, bx + found.box.w, by + found.box.h))
    grow = min(max(3, round(side * CHANGE_GROW)) | 1, 31)
    hard = Image.fromarray((_grow_square(obj, grow) * 255).astype("uint8"))      # as MaxFilter(grow), but fast
    hard.paste(255, (bx, by, bx + found.box.w, by + found.box.h))
    if any(inner):
        soft = fillmask.crop_fade(hard, max(1, round(side * CHANGE_SOFT)), inner)
    else:      # the whole canvas (Fibo, user 15.11.): crop_fade would cover all of it; a soft edge around the object instead
        soft = whole_canvas_fade(hard, max(2, imaging.feather_radius(found.box.w, found.box.h, feather_pct) // 2))
    full = Image.new("L", photo.size, 0)
    full.paste(soft, (reg.x, reg.y))
    return full


def put_back(photo: Image.Image, result: Image.Image, found: Found, reg: imaging.Box) -> tuple[Image.Image, Image.Image]:
    """The new layer (canvas size: the photo with the model's crop pasted at `reg`, colour matched) and its layer mask
    (fade_mask). Where the mask is 0 the layer shows the photo unchanged."""
    size = photo.size
    layer = photo.convert("RGB").copy()
    layer.paste(result.convert("RGB").resize((reg.w, reg.h), Image.LANCZOS), (reg.x, reg.y))
    ring = context_ring(size, reg, box_mask(size, found.box20))
    return colour_match(layer, photo, ring), fade_mask(size, found.box, reg)
