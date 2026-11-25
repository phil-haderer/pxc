# tags: photocraft, linux
"""The Linux clipboard (pccomfy/clipboard.py, "the Linux part"): choosing a format, file lists, reading and writing through a
fake clipboard program, the backend choice. Runs on any system; no real clipboard is touched.

    python tests/test_clipboard_linux.py
"""
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image  # noqa: E402

from pccomfy import clipboard as cb  # noqa: E402
from pccomfy import x11clip  # noqa: E402


def png_bytes(color=(10, 200, 30), size=(7, 5)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def main():
    # choosing a format: PNG first, then any picture, then copied files
    assert cb.pick_target(["text/plain", "image/png", "image/bmp"]) == ("image", "image/png")
    assert cb.pick_target(["image/bmp", "text/plain"]) == ("image", "image/bmp")
    assert cb.pick_target(["TARGETS", "text/uri-list"]) == ("files", "text/uri-list")
    assert cb.pick_target(["x-special/gnome-copied-files", "text/plain"]) == ("files", "x-special/gnome-copied-files")
    assert cb.pick_target(["text/plain", "UTF8_STRING"]) is None and cb.pick_target([]) is None and cb.pick_target(None) is None

    # file lists: file:// lines only, percent-decoded, no remote hosts, the "copy" line of gnome-copied-files skipped
    text = "copy\nfile:///home/user/My%20Pics/a.png\n# comment\nfile://localhost/tmp/b.jpg\nfile://otherhost/x.png\nhttps://x/y.png\n"
    assert cb.paths_from_uri_list(text) == [Path("/home/user/My Pics/a.png"), Path("/tmp/b.jpg")]
    assert cb.paths_from_uri_list("") == [] and cb.paths_from_uri_list(None) == []

    # the backends (choice A 19.11.): xclip first wherever there is an X display (X11, or XWayland on Wayland, where PxC's
    # window is an X11 client), then wl-clipboard on Wayland; else nothing
    import os
    real = (cb.sys.platform, dict(os.environ), cb.shutil.which)
    try:
        cb.sys.platform = "linux"
        have = {"wl-paste", "wl-copy", "xclip"}
        cb.shutil.which = lambda n: "/usr/bin/" + n if n in have else None
        os.environ["WAYLAND_DISPLAY"], os.environ["DISPLAY"] = "wayland-0", ":0"
        assert cb._linux_backends() == ["xclip", "wl"] and cb._linux_backend() == "xclip" and cb.available()
        del os.environ["DISPLAY"]                           # Wayland without XWayland
        assert cb._linux_backends() == ["wl"]
        os.environ["DISPLAY"] = ":0"
        have.discard("xclip")                               # Wayland, xclip not installed
        assert cb._linux_backends() == ["wl"]
        have.add("xclip")
        del os.environ["WAYLAND_DISPLAY"]                   # X11
        assert cb._linux_backends() == ["xclip"]
        have.discard("xclip")
        assert cb._linux_backends() == [] and cb._linux_backend() is None and not cb.available()
        cb.sys.platform = "win32"
        assert cb._linux_backends() == [] and cb.available()
    finally:
        cb.sys.platform = real[0]
        os.environ.clear()
        os.environ.update(real[1])
        cb.shutil.which = real[2]

    # copying (choice A 19.11.): our own X11 owner first wherever there is an X display, then the readers' order
    real = (cb.sys.platform, dict(os.environ), cb.shutil.which)
    try:
        cb.sys.platform = "linux"
        cb.shutil.which = lambda n: "/usr/bin/" + n
        os.environ["WAYLAND_DISPLAY"], os.environ["DISPLAY"] = "wayland-0", ":0"
        assert cb._linux_write_backends() == ["x11", "xclip", "wl"]
        del os.environ["DISPLAY"]
        assert cb._linux_write_backends() == ["wl"]
        cb.sys.platform = "win32"
        assert cb._linux_write_backends() == []
    finally:
        cb.sys.platform = real[0]
        os.environ.clear()
        os.environ.update(real[1])
        cb.shutil.which = real[2]

    # the owner's answers: only TARGETS and image/png; everything else refused (xclip 0.13 sends the PNG for any request,
    # labelled image/png, and PhotoCraft stops at that); big pictures in INCR parts ending with an empty one
    png = png_bytes()
    assert x11clip.answer("TARGETS", png) == ("ATOM", 32, ["TARGETS", "image/png"])
    assert x11clip.answer("image/png", png) == ("image/png", 8, png)
    for t in ("UTF8_STRING", "text/plain", "STRING", "image/bmp", "MULTIPLE", "TIMESTAMP", ""):
        assert x11clip.answer(t, png) is None, t
    assert x11clip.chunks(b"abcdefg", 3) == [b"abc", b"def", b"g", b""] and x11clip.chunks(b"abc", 3) == [b"abc", b""]
    # time limits (review 21.11.): a requestor that went away mid-transfer is dropped, the helper never waits forever
    pend = {(1, 2): (0, [b"x"], 100.0), (3, 4): (0, [b"y"], 105.0)}
    assert x11clip.stalled(pend, 109.9) == [] and x11clip.stalled(pend, 110.0) == [(1, 2)]
    assert not x11clip.over(None, {}, 999.0)                      # still the owner: serve on
    assert x11clip.over(50.0, {}, 50.0)                           # taken, nothing running: end at once
    assert not x11clip.over(50.0, pend, 59.0) and x11clip.over(50.0, pend, 60.0)    # at most LINGER_S later
    assert x11clip.STALL_S == x11clip.LINGER_S == 10.0
    assert b"".join(x11clip.chunks(bytes(range(256)) * 5, 100)) == bytes(range(256)) * 5
    if not os.environ.get("DISPLAY"):                       # no display (Windows, a bare CI shell): says so, does not hang
        assert x11clip.serve(png) == 1

    # reading and writing through a fake program
    calls = []
    clip = {"types": ["text/plain", "image/png"], "data": {"image/png": png_bytes()}}

    def fake_run(args, data=None):
        calls.append((list(args), data))
        if data is not None:                                    # a write
            clip["written"] = data
            return b""
        if "--list-types" in args or "TARGETS" in args:
            return "\n".join(clip["types"]).encode()
        mime = args[args.index("--type") + 1] if "--type" in args else args[args.index("-t") + 1]
        return clip["data"].get(mime)
    real_run, real_backends, real_wbackends = cb._linux_run, cb._linux_backends, cb._linux_write_backends
    cb._linux_run = fake_run
    try:
        for backend in ("wl", "xclip"):
            cb._linux_backends = cb._linux_write_backends = lambda b=backend: [b]
            calls.clear()
            img = cb.read_image()
            assert img is not None and img.size == (7, 5) and img.getpixel((0, 0)) == (10, 200, 30), backend
            assert calls[0][0][0] == ("wl-paste" if backend == "wl" else "xclip")
            assert "image/png" in calls[1][0]

            assert cb.write_image(Image.new("RGBA", (4, 3), (1, 2, 3, 128))) is True
            assert calls[-1][0][0] == ("wl-copy" if backend == "wl" else "xclip") and "image/png" in calls[-1][0]
            back = Image.open(io.BytesIO(clip["written"]))
            assert back.size == (4, 3) and back.mode == "RGBA" and back.getpixel((0, 0))[3] == 128      # transparency kept

        # copied files: the first picture in the list
        if os.name != "nt":                 # a POSIX path in a file:// URI
            with tempfile.TemporaryDirectory() as tmp:
                pic = Path(tmp) / "pic one.png"
                Image.new("RGB", (3, 2), (5, 6, 7)).save(pic)
                clip["types"] = ["text/uri-list"]
                clip["data"] = {"text/uri-list": (pic.as_uri() + "\r\n").encode()}
                img = cb.read_image()
                assert img is not None and img.size == (3, 2)

        # nothing usable: None, no exception
        clip["types"], clip["data"] = ["text/plain"], {}
        assert cb.read_image() is None
        clip["types"], clip["data"] = ["image/png"], {"image/png": b"not a picture"}
        assert cb.read_image() is None
        cb._linux_run = lambda args, data=None: None            # the program fails
        assert cb.read_image() is None and cb.write_image(Image.new("RGB", (2, 2))) is False

        # xclip fails (Wayland without a working XWayland clipboard): wl-clipboard takes over, both ways (choice A 19.11.)
        cb._linux_backends = cb._linux_write_backends = lambda: ["xclip", "wl"]
        clip["types"], clip["data"] = ["image/png"], {"image/png": png_bytes()}
        tried = []

        def xclip_broken(args, data=None):
            tried.append(args[0])
            return None if args[0] == "xclip" else fake_run(args, data)
        cb._linux_run = xclip_broken
        img = cb.read_image()
        assert img is not None and img.size == (7, 5) and tried[0] == "xclip" and "wl-paste" in tried, tried
        tried.clear()
        assert cb.write_image(Image.new("RGB", (2, 2))) is True and tried == ["xclip", "wl-copy"], tried
        # xclip works: wl-clipboard is not asked
        cb._linux_run = lambda args, data=None: (tried.append(args[0]), fake_run(args, data))[1]
        tried.clear()
        assert cb.read_image() is not None and cb.write_image(Image.new("RGB", (2, 2))) is True
        assert set(tried) == {"xclip"}, tried

        # our own owner first; when it cannot hold the clipboard, xclip takes over
        cb._linux_write_backends = lambda: ["x11", "xclip", "wl"]
        owned = []
        real_own = cb._x11_own
        try:
            cb._x11_own = lambda data: owned.append(data) or True
            tried.clear()
            assert cb.write_image(Image.new("RGB", (2, 2))) is True and len(owned) == 1 and tried == [], tried
            assert Image.open(io.BytesIO(owned[0])).size == (2, 2)
            cb._x11_own = lambda data: False
            assert cb.write_image(Image.new("RGB", (2, 2))) is True and tried == ["xclip"], tried
        finally:
            cb._x11_own = real_own
    finally:
        cb._linux_run, cb._linux_backends, cb._linux_write_backends = real_run, real_backends, real_wbackends

    print("clipboard linux ok")


if __name__ == "__main__":
    main()
