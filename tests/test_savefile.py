"""Save image core (pccomfy/savefile.py, hostos.downloads_dir): name patterns, sanitizing, never overwriting, formats, settings.
Temp folders only. Run: python tests/test_savefile.py"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="pc_savefile_"))
os.environ["PCCOMFY_HOME"] = str(TMP / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402

from pccomfy import config, gui_common, hostos, savefile as sf  # noqa: E402

NOW = dt.datetime(2026, 11, 12, 11, 52)
R = sf.render_name


def main():
    # every pattern
    kw = dict(name="beach.png", function="upscale", seed=83421, now=NOW, counter=1)
    assert R(sf.PATTERNS[0], **kw) == "beach-upscale-2026-11-12-83421"
    assert R(sf.PATTERNS[1], **kw) == "beach_2026-11-12_1152"
    assert R(sf.PATTERNS[2], **kw) == "beach_001"
    assert R(sf.PATTERNS[3], **kw) == "2026-11-12_1152_83421"
    assert sf.DEFAULT_PATTERN == sf.PATTERNS[0] and all(sf.validate_pattern(p) is None for p in sf.PATTERNS)
    assert sf.example_name(sf.PATTERNS[0], "jpg") == "beach-upscale-2026-11-12-83421.jpg"
    assert sf.example_name(sf.PATTERNS[2], "png") == "beach_001.png"

    # empty placeholders are dropped, separators collapse
    assert R(sf.PATTERNS[0], name="beach", function="fill", seed=None, now=NOW) == "beach-fill-2026-11-12"
    assert R(sf.PATTERNS[0], name="", function="", seed=None, now=NOW) == "2026-11-12"
    assert R(sf.PATTERNS[3], seed=None, now=NOW) == "2026-11-12_1152"
    assert R("{name}-{function}-{seed}", name="a", function="", seed=5) == "a-5"
    assert R("{seed}_{name}", name="", seed=7) == "7"
    assert R("{name} {function} {seed}", name="a", seed=3) == "a 3"
    assert R("{name}", name="") == "image" and R("", name="x") == "image"

    # sanitizing
    s = R("{name}", name='a<b>c:d"e|f?g*h')
    assert s == "abcdefgh", s
    assert R("{name}", name="x\x00y\x1fz\x7f") == "xyz"
    assert R("{name}", name="photo. . ") == "photo"
    assert R("{name}", name="..hidden") == "hidden"
    assert R("{name}", name="C:\\pics\\dir\\cat.jpeg") == "cat"
    assert R("{name}", name="my.photo.v2") == "my.photo"
    for res in ("CON", "nul", "Com1", "LPT9", "aux", "PRN"):
        assert R("{name}", name=res).upper() != res.upper() and R("{name}", name=res).startswith("_"), res
    assert R("{name}", name="con.txt") == "_con"      # extension stripped, still reserved
    assert R("{name}", name="console") == "console"
    # unknown placeholders stay literal (sanitized); broken braces do not crash
    assert R("{name}-{xyz}", name="a") == "a-{xyz}"
    assert R("{name}-{x/y}", name="a") == "a-{xy}"
    for bad in ("{name", "name}", "{{name}}", "}{", "{", "}", "{name}{"):
        assert R(bad, name="a", now=NOW)
    assert len(R("{name}", name="a" * 500)) <= 150

    # validate_pattern
    assert sf.validate_pattern("") and sf.validate_pattern("   ")
    assert sf.validate_pattern("{name") and sf.validate_pattern("{{name}}")
    assert "xyz" in sf.validate_pattern("{name}{xyz}")
    assert sf.validate_pattern("plain")           # no placeholder: every file would collide
    assert sf.validate_pattern(None)
    assert sf.validate_pattern("{Name}_{DATE}") is None

    # unique numbering and never overwriting
    d = TMP / "u"
    d.mkdir()
    assert sf.unique_path(d, "a", "png") == d / "a.png"
    (d / "a.png").write_bytes(b"x")
    assert sf.unique_path(d, "a", ".png") == d / "a (2).png"
    (d / "a (2).png").write_bytes(b"x")
    assert sf.unique_path(d, "a", "png") == d / "a (3).png"
    assert sf.next_counter(d, "{name}_{counter}", name="p") == 1
    (d / "p_001.jpg").write_bytes(b"x")
    (d / "p_002.png").write_bytes(b"x")
    assert sf.next_counter(d, "{name}_{counter}", name="p") == 3
    assert sf.next_counter(d, "{name}_{date}", name="p") == 1

    # save_image: folder created, exclusive create, formats
    out = TMP / "new" / "deep"
    st = sf.SaveSettings(out, "png", sf.PATTERNS[1])
    img = Image.new("RGBA", (6, 4), (255, 0, 0, 0))
    img.putpixel((1, 1), (0, 0, 255, 255))
    p1 = sf.save_image(img, settings=st, name="beach", now=NOW)
    assert p1 == out / "beach_2026-11-12_1152.png" and p1.exists()
    p1.write_bytes(b"precious")
    p2 = sf.save_image(img, settings=st, name="beach", now=NOW)
    assert p2 == out / "beach_2026-11-12_1152 (2).png" and p1.read_bytes() == b"precious"
    # a pre-existing file of another run is untouched, counter pattern skips taken numbers
    stc = sf.SaveSettings(out, "png", sf.PATTERNS[2])
    (out / "beach_001.png").write_bytes(b"old")
    p3 = sf.save_image(img, settings=stc, name="beach")
    assert p3.name == "beach_002.png" and (out / "beach_001.png").read_bytes() == b"old"
    # PNG round trip keeps alpha
    with Image.open(p2) as im:
        assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0 and im.getpixel((1, 1)) == (0, 0, 255, 255)
    # JPG: alpha on white
    stj = sf.SaveSettings(out, "jpg", sf.PATTERNS[1])
    pj = sf.save_image(img, settings=stj, name="j", now=NOW)
    assert pj.suffix == ".jpg"
    with Image.open(pj) as im:
        assert im.mode == "RGB" and min(im.getpixel((0, 0))) >= 235, im.getpixel((0, 0))
    # WebP round trip keeps alpha
    stw = sf.SaveSettings(out, "webp", sf.PATTERNS[1])
    pw = sf.save_image(img, settings=stw, name="w", now=NOW)
    with Image.open(pw) as im:
        assert im.format == "WEBP" and im.convert("RGBA").getpixel((0, 0))[3] == 0 and im.size == (6, 4)
    # RGB / palette input work for every format
    for fmt in sf.FORMATS:
        for src in (Image.new("RGB", (3, 3), (1, 2, 3)), Image.new("L", (3, 3), 9), Image.new("P", (3, 3))):
            sf.save_image(src, settings=sf.SaveSettings(out, fmt, sf.PATTERNS[3]), seed=1, now=NOW)
    # a failed encode leaves no half file
    before = sorted(x.name for x in out.iterdir())

    class Boom:
        mode = "RGB"
        size = (1, 1)

        def convert(self, *_):
            raise RuntimeError("boom")

        def getbands(self):
            return ("R", "G", "B")

        info = {}

        def save(self, *_a, **_k):
            raise RuntimeError("boom")
    try:
        sf.save_image(Boom(), settings=sf.SaveSettings(out, "png", sf.PATTERNS[1]), name="boom", now=NOW)
        raise AssertionError("expected an error")
    except RuntimeError:
        pass
    assert sorted(x.name for x in out.iterdir()) == before

    # settings with fallbacks
    config.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = sf.load_settings()
    assert s.folder == hostos.downloads_dir() and s.fmt == "png" and s.pattern == sf.DEFAULT_PATTERN
    config.set_setting(sf.SAVE_FOLDER_KEY, str(TMP / "mine"))
    config.set_setting(sf.SAVE_FORMAT_KEY, "WEBP")
    config.set_setting(sf.SAVE_PATTERN_KEY, "{name}_{counter}")
    s = sf.load_settings()
    assert s.folder == TMP / "mine" and s.fmt == "webp" and s.pattern == "{name}_{counter}"
    config.set_setting(sf.SAVE_FORMAT_KEY, "bmp")
    config.set_setting(sf.SAVE_PATTERN_KEY, "{bogus}")
    config.set_setting(sf.SAVE_FOLDER_KEY, 12)
    s = sf.load_settings()
    assert s.fmt == "png" and s.pattern == sf.DEFAULT_PATTERN and s.folder == hostos.downloads_dir()

    # function labels / batch suffixes cover every mode of the window
    keys = [k for k, _ in gui_common.MODE_LABELS]
    labels = {k: sf.function_label(k) for k in keys}
    assert labels["txt2img"] == "text2img" and labels["outpaint"] == "expand" and labels["inpaint"] == "fill"
    assert labels["multi_edit"] == "multi-edit" and all(labels.values())
    assert (sf.batch_suffix("upscale"), sf.batch_suffix("refine"), sf.batch_suffix("edit"), sf.batch_suffix("multi_edit")) == \
        ("_upscaled", "_refined", "_edited", "_edited")
    assert sf.batch_suffix("remove") == "_remove" and sf.batch_suffix("inpaint") == "_fill"

    # downloads_dir: absolute on this system, not created
    dd = hostos.downloads_dir()
    assert isinstance(dd, Path) and dd.is_absolute()
    # user-dirs.dirs parser (pure, runs everywhere)
    f = hostos._user_dirs_value
    txt = '# comment\nXDG_DESKTOP_DIR="$HOME/Desktop"\nXDG_DOWNLOAD_DIR="$HOME/Herunterladen"\n'
    assert f(txt, "XDG_DOWNLOAD_DIR", "/home/u") == "/home/u/Herunterladen"
    assert f('XDG_DOWNLOAD_DIR="${HOME}/dl"', "XDG_DOWNLOAD_DIR", "/h") == "/h/dl"
    assert f('XDG_DOWNLOAD_DIR="/data/Downloads"', "XDG_DOWNLOAD_DIR", "/h") == "/data/Downloads"
    assert f("  XDG_DOWNLOAD_DIR='/x y'  ", "XDG_DOWNLOAD_DIR", "/h") == "/x y"
    assert f("XDG_MUSIC_DIR=\"$HOME/m\"", "XDG_DOWNLOAD_DIR", "/h") is None
    assert f("", "XDG_DOWNLOAD_DIR", "/h") is None and f('XDG_DOWNLOAD_DIR=""', "XDG_DOWNLOAD_DIR", "/h") is None
    # Linux branch end to end (env and file), through the real function with the platform flag forced
    saved = (hostos.IS_WINDOWS, dict(os.environ))
    try:
        hostos.IS_WINDOWS = False
        os.environ.pop("XDG_DOWNLOAD_DIR", None)
        cfgd = TMP / "xdgcfg"
        cfgd.mkdir()
        (cfgd / "user-dirs.dirs").write_text('XDG_DOWNLOAD_DIR="$HOME/Dl"\n', encoding="utf-8")
        os.environ["XDG_CONFIG_HOME"] = str(cfgd)
        assert hostos.downloads_dir() == Path.home() / "Dl"
        os.environ["XDG_DOWNLOAD_DIR"] = str(TMP / "envdl")
        assert hostos.downloads_dir() == TMP / "envdl"
        os.environ.pop("XDG_DOWNLOAD_DIR")
        os.environ["XDG_CONFIG_HOME"] = str(TMP / "nothing")
        assert hostos.downloads_dir() == Path.home() / "Downloads"
        assert not (TMP / "nothing").exists()
    finally:
        hostos.IS_WINDOWS = saved[0]
        os.environ.clear()
        os.environ.update(saved[1])
    print("ok")


if __name__ == "__main__":
    try:
        main()
    finally:
        import shutil
        shutil.rmtree(TMP, ignore_errors=True)
