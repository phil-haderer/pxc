# tags: release
"""The setup scripts carry the app name in ONE variable (APP_NAME) that equals pccomfy.appname.APP_NAME, never name
the old app ("PhotoCraft AI", "photocraft-ai.*") except in the lines that remove the old entries, and remove exactly
three old entries: the Windows desktop shortcut, the Windows autostart value and the Linux menu entry.

    python tests/test_setup_appname.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pccomfy import appname  # noqa: E402

OLD_LNK = "PhotoCraft AI.lnk"
OLD_RUN = "PhotoCraft ComfyUI bridge"
OLD_DESKTOP = "photocraft-ai.desktop"
BAD = ("PhotoCraft AI", "photocraft-ai.")


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def main():
    bat = read("setup-windows.bat")
    sh = read("setup-linux.sh")
    fails = []

    m_bat = re.search(r'^set "APP_NAME=(.*)"\s*$', bat, re.M)
    m_sh = re.search(r'^APP_NAME="(.*)"\s*$', sh, re.M)
    if not m_bat or m_bat.group(1) != appname.APP_NAME:
        fails.append(f"setup-windows.bat: APP_NAME is {m_bat and m_bat.group(1)!r}, expected {appname.APP_NAME!r}")
    if not m_sh or m_sh.group(1) != appname.APP_NAME:
        fails.append(f"setup-linux.sh: APP_NAME is {m_sh and m_sh.group(1)!r}, expected {appname.APP_NAME!r}")

    # the old names may stand only in the three lines that define the old entries to remove
    for name, text, marker in (("setup-windows.bat", bat, 'set "OLD_'), ("setup-linux.sh", sh, "OLD_DESKTOP=")):
        for n, line in enumerate(text.splitlines(), 1):
            if any(b in line for b in BAD) and not line.startswith(marker):
                fails.append(f"{name}:{n}: still names the old app: {line.strip()}")
            if "bridge" in line and not line.startswith(marker):
                fails.append(f"{name}:{n}: still says bridge: {line.strip()}")

    # exactly these three old entries are named
    for text, name, want in ((bat, "setup-windows.bat", f'set "OLD_LNK={OLD_LNK}"'),
                             (bat, "setup-windows.bat", f'set "OLD_RUN={OLD_RUN}"'),
                             (sh, "setup-linux.sh", f'OLD_DESKTOP="{OLD_DESKTOP}"')):
        if want not in text.splitlines():
            fails.append(f"{name}: missing line {want}")
    if len(re.findall(r'^set "OLD_\w+=', bat, re.M)) != 2:
        fails.append("setup-windows.bat: expected exactly two OLD_ variables")
    if len(re.findall(r"^OLD_\w+=", sh, re.M)) != 1:
        fails.append("setup-linux.sh: expected exactly one OLD_ variable")
    # the removal code uses the variables (and deletes nothing else)
    if "$env:OLD_LNK" not in bat or '/v "%OLD_RUN%"' not in bat:
        fails.append("setup-windows.bat: removal does not use OLD_LNK / OLD_RUN")
    # the autostart is gone (user 16.11.): where it was installed, its Run value and its four variables go too
    if '/v "%APP_NAME%"' not in bat or bat.count('reg delete "HKCU\\Environment" /v %%V') != 1:
        fails.append("setup-windows.bat: does not remove the autostart value %APP_NAME% and its variables")
    if "$OLD_DESKTOP" not in sh:
        fails.append("setup-linux.sh: removal does not use OLD_DESKTOP")

    # the starters in the texts are the new ones
    if "./pxc.sh" not in sh:
        fails.append("setup-linux.sh: does not mention ./pxc.sh")

    if fails:
        print("FAIL")
        for f in fails:
            print("  " + f)
        return 1
    print("test_setup_appname: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
