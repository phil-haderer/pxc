"""The visible app name lives only in pccomfy/appname.py (PLAN.md point 20): no other module holds it as a string literal,
and the places that show it take it from there.

    python tests/test_appname.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pccomfy import appname, launcher  # noqa: E402


def test_values_unchanged():
    assert appname.APP_NAME == "PxC" and appname.WINDOW_TITLE == "PxC"
    assert appname.HEADER_TITLE == ("P", "×", "C")
    assert launcher.NAME == appname.APP_NAME


def test_no_other_literal():
    names = {appname.APP_NAME, appname.WINDOW_TITLE}
    for f in sorted((ROOT / "pccomfy").glob("*.py")):
        if f.name == "appname.py":
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value in names:
                # a module docstring or a docstring is an Expr; only count real uses
                raise AssertionError(f"{f.name}:{node.lineno} holds the app name as a literal")


def test_header_title():
    """The header shows HEADER_TITLE: the names white and thin, the sign light blue (as the prompt tip) and bold, all at 12 pt (user 3.11.)."""
    sys.path.insert(0, str(ROOT / "tests"))
    import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)
    from pccomfy.gui_common import ACCENT_TEXT, HEADER_GAP, HEADER_PT, font, sign_font
    app = t.gui.App(t.cfgmod.load())
    assert tuple(w["text"] for w in app.lbl_title) == appname.HEADER_TITLE
    assert [w["foreground"] for w in app.lbl_title] == ["#ffffff", ACCENT_TEXT, "#ffffff"]
    assert [w["font"] for w in app.lbl_title] == [font(HEADER_PT), sign_font(), font(HEADER_PT)]   # 20 % over 12 pt (user 11.11.)
    assert "bold" in sign_font()                    # the "×" is bold (user 12.11.)
    assert HEADER_PT == 12 * 1.2 and HEADER_GAP == 3     # gaps 20 % smaller again (4 -> 3, user 12.11.)
    from pccomfy.gui_theme import HEADER_H, ICON_PX
    assert HEADER_H == round((ICON_PX + 12) * 0.85) == 27   # the header 85 % as high as before (32 px)


if __name__ == "__main__":
    test_values_unchanged()
    test_no_other_literal()
    test_header_title()
    print("ok")
