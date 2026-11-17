"""Save an image to disk: file name patterns, folder, format (stdlib + Pillow only; the window lives in gui_*.py).

A file is never overwritten: the name gets " (2)", " (3)" ... and the file is created exclusively.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import config, hostos

PATTERNS = ("{name}-{function}-{date}-{seed}", "{name}_{date}_{time}", "{name}_{counter}", "{date}_{time}_{seed}")
DEFAULT_PATTERN = PATTERNS[0]
PLACEHOLDERS = ("name", "function", "date", "time", "counter", "seed")
FORMATS = ("png", "jpg", "webp")
DEFAULT_FORMAT = "png"
SAVE_FOLDER_KEY = "save_folder"
SAVE_FORMAT_KEY = "save_format"
SAVE_PATTERN_KEY = "save_pattern"
MAX_STEM = 150
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_TOKEN = re.compile(r"\{([^{}]*)\}")
_SEP = "-_ "
EXAMPLE_NOW = _dt.datetime(2026, 11, 12, 11, 52)


@dataclass
class SaveSettings:
    folder: Path
    fmt: str = DEFAULT_FORMAT
    pattern: str = DEFAULT_PATTERN


def load_settings() -> SaveSettings:
    folder = config.get_setting(SAVE_FOLDER_KEY)
    try:
        path = Path(folder).expanduser() if isinstance(folder, str) and folder.strip() else hostos.downloads_dir()
    except Exception:
        path = hostos.downloads_dir()
    fmt = config.get_setting(SAVE_FORMAT_KEY)
    fmt = fmt.lower() if isinstance(fmt, str) else ""
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in FORMATS:
        fmt = DEFAULT_FORMAT
    pat = config.get_setting(SAVE_PATTERN_KEY)
    if not isinstance(pat, str) or validate_pattern(pat) is not None:
        pat = DEFAULT_PATTERN
    return SaveSettings(path, fmt, pat)


def _clean(text: str) -> str:
    """Characters no system accepts in a file name removed; leading/trailing dots and spaces cut."""
    return _BAD.sub("", text).strip(" .")


def _strip_ext(name: str) -> str:
    base = re.split(r"[\\/]", (name or "").strip())[-1]
    stem, dot, ext = base.rpartition(".")
    if dot and stem and 1 <= len(ext) <= 5 and ext.isalnum():
        return stem
    return base


def _collapse(text: str) -> str:
    """Separators next to each other (left by dropped placeholders) merged; none at the ends."""
    text = re.sub(r"[-_ ]+", lambda m: m.group(0)[0] if len(set(m.group(0))) == 1 else _pick(m.group(0)), text)
    return text.strip(_SEP)


def _pick(run: str) -> str:
    """Of a mixed run of separators the first one that is not a space (a lone space only if all are spaces)."""
    for ch in run:
        if ch in "-_":
            return ch
    return " "


def render_name(pattern, *, name="", function="", seed=None, now=None, counter=1) -> str:
    now = now or _dt.datetime.now()
    pattern = pattern if isinstance(pattern, str) else ""
    values = {
        "name": _clean(_strip_ext(name or "")),
        "function": _clean(str(function or "")),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H%M"),
        "counter": f"{int(counter):03d}",
        "seed": "" if seed is None or str(seed).strip() == "" else _clean(str(seed)),
    }
    out, pos = [], 0
    for m in _TOKEN.finditer(pattern):
        out.append(_BAD.sub("", pattern[pos:m.start()]))
        key = m.group(1).strip().lower()
        out.append(values[key] if key in values else _BAD.sub("", m.group(0)))
        pos = m.end()
    out.append(_BAD.sub("", pattern[pos:]))
    stem = _collapse("".join(out))[:MAX_STEM].strip(" .-_")
    if not stem:
        return "image"
    if stem.split(".")[0].upper() in _RESERVED:
        stem = "_" + stem
    return stem


def validate_pattern(pattern) -> str | None:
    if not isinstance(pattern, str) or not pattern.strip():
        return "The pattern is empty."
    rest = _TOKEN.sub("", pattern)
    if "{" in rest or "}" in rest:
        return "Curly brackets do not match."
    names = [m.group(1).strip().lower() for m in _TOKEN.finditer(pattern)]
    bad = [m.group(1) for m in _TOKEN.finditer(pattern) if m.group(1).strip().lower() not in PLACEHOLDERS]
    if bad:
        return "Unknown placeholder {" + bad[0] + "}. Use " + ", ".join("{" + p + "}" for p in PLACEHOLDERS) + "."
    if not names:
        return "Use at least one placeholder."
    return None


def example_name(pattern, fmt) -> str:
    fmt = fmt if fmt in FORMATS else DEFAULT_FORMAT
    return render_name(pattern, name="beach", function="upscale", seed=83421, now=EXAMPLE_NOW, counter=1) + "." + fmt


def unique_path(folder, stem, ext) -> Path:
    folder = Path(folder)
    ext = ext.lstrip(".")
    p = folder / f"{stem}.{ext}"
    n = 2
    while p.exists():
        p = folder / f"{stem} ({n}).{ext}"
        n += 1
    return p


def next_counter(folder, pattern, **kw) -> int:
    """The smallest counter >= 1 whose rendered name is free in any format. Only matters if the pattern has {counter}."""
    kw.pop("counter", None)
    if "{counter}" not in (pattern or "").lower():
        return 1
    folder = Path(folder)
    n = 1
    while True:
        stem = render_name(pattern, counter=n, **kw)
        if not any((folder / f"{stem}.{e}").exists() for e in (*FORMATS, "jpeg")):
            return n
        n += 1


def _encode(img, fmt: str):
    """(image ready for Pillow's save, save keyword arguments, Pillow format name)."""
    from PIL import Image
    if fmt == "jpg":
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB"), {"quality": 95}, "JPEG"
    if fmt == "webp":
        keep = img.mode in ("RGB", "RGBA")
        return (img if keep else img.convert("RGBA" if ("A" in img.getbands() or "transparency" in img.info) else "RGB")), {"quality": 95}, "WEBP"
    return img, {}, "PNG"


def save_image(img, *, settings=None, name="", function="", seed=None, now=None) -> Path:
    """Write img into the save folder and return the path. Never overwrites an existing file."""
    st = settings or load_settings()
    fmt = st.fmt if st.fmt in FORMATS else DEFAULT_FORMAT
    pattern = st.pattern if validate_pattern(st.pattern) is None else DEFAULT_PATTERN
    folder = Path(st.folder)
    folder.mkdir(parents=True, exist_ok=True)
    data, kw, pil_fmt = _encode(img, fmt)
    base = dict(name=name, function=function, seed=seed, now=now or _dt.datetime.now())
    counter = next_counter(folder, pattern, **base)
    for _ in range(1000):
        path = unique_path(folder, render_name(pattern, counter=counter, **base), fmt)
        try:
            f = open(path, "xb")
        except FileExistsError:
            counter += 1
            continue
        try:
            with f:
                data.save(f, format=pil_fmt, **kw)
        except BaseException:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        return path
    raise OSError("No free file name in " + str(folder))


_FUNCTION_LABELS = {"txt2img": "text2img", "outpaint": "expand", "inpaint": "fill", "remove": "remove", "edit": "edit",
                    "multi_edit": "multi-edit", "sketch": "sketch", "scribble": "scribble", "upscale": "upscale",
                    "refine": "refine", "img2img": "img2img"}


def function_label(mode) -> str:
    mode = str(mode or "")
    return _FUNCTION_LABELS.get(mode) or _clean(mode.replace("_", "-"))


def batch_suffix(mode) -> str:
    return {"upscale": "_upscaled", "refine": "_refined", "edit": "_edited", "multi_edit": "_edited"}.get(str(mode), "_" + function_label(mode))


BATCH_SUFFIXES = ("_upscaled", "_refined", "_edited")


def has_batch_suffix(stem) -> bool:
    """True when a file name's stem already ends with a batch suffix ("beach_upscaled"): a folder batch leaves it out."""
    return str(stem).lower().endswith(BATCH_SUFFIXES)


def _write_exclusive(img, folder: Path, stem: str, fmt: str) -> Path:
    """Write img as <stem>.<fmt> in folder, or <stem> (2).<fmt> ... when taken; the file is created exclusively, so a file
    that appeared meanwhile is never overwritten."""
    data, kw, pil_fmt = _encode(img, fmt)
    folder.mkdir(parents=True, exist_ok=True)
    for _ in range(1000):
        path = unique_path(folder, stem, fmt)
        try:
            f = open(path, "xb")
        except FileExistsError:
            continue
        try:
            with f:
                data.save(f, format=pil_fmt, **kw)
        except BaseException:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        return path
    raise OSError("No free file name in " + str(folder))


def batch_name(stem, mode) -> str:
    """The stem of a batch result: <original stem><suffix> ("beach" + Upscale -> "beach_upscaled")."""
    base = _clean(_strip_ext(str(stem or ""))) or "image"
    return (base + batch_suffix(mode))[:MAX_STEM]


def save_batch_result(img, stem, mode, settings=None) -> Path:
    """A batch result into the save folder (format from the settings) as <original stem><suffix>.<ext>
    ("beach_upscaled.png"); never overwrites ("beach_upscaled (2).png"). Returns the path."""
    st = settings or load_settings()
    fmt = st.fmt if st.fmt in FORMATS else DEFAULT_FORMAT
    return _write_exclusive(img, Path(st.folder), batch_name(stem, mode), fmt)
