"""Your prompt text stays when the model changes inside Edit canvas (and Multi image edit, Fill, ...): every pair of models,
also through a model that only has Text to image. Hidden Tk window (stubbed in test_reset_all).

    python tests/test_prompt_keeps_on_model_switch.py
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reset_all as ra  # noqa: E402

from pccomfy import models  # noqa: E402

TEXT = "make it night"


def main():
    app = ra.make()
    text = lambda: app.t_prompt.get("1.0", "end").strip()      # noqa: E731
    keys = [m.key for m in models.MODELS]
    for mode in ("edit", "multi_edit", "inpaint"):
        for a, b in itertools.product([m.key for m in models.MODELS if mode in m.modes], keys):
            ra.go(app, a, mode)
            app.t_prompt.delete("1.0", "end")
            app.t_prompt.insert("1.0", TEXT)
            ra.go(app, b, mode)
            assert text() == TEXT, (mode, a, b, text())
    for seq in itertools.product(keys, repeat=3):            # three clicks in a row, also over a Text-to-image-only model
        ra.go(app, "qwen", "edit")
        app.t_prompt.delete("1.0", "end")
        app.t_prompt.insert("1.0", TEXT)
        for k in seq:
            app.v_model.set(k)
            app._on_model()
            assert text() == TEXT, (seq, k, text())
    # the user's steps 13.11.: Edit canvas, Fibo, a style from the Styles menu, then Flux 3: the style text stays
    # (styles count as stock text for a function change, but not for a model change inside the function)
    styles_edit = app._mode_styles["edit"]
    assert styles_edit
    for name, st in list(styles_edit.items())[:3]:
        for a, b in (("fibo", "flux3"), ("flux3", "fibo"), ("qwen", "flux2"), ("fibo", "qwen")):
            ra.go(app, a, "edit")
            app._apply_style(st, name)
            assert text() == st, (name, a, text())
            ra.go(app, b, "edit")
            assert text() == st, (name, a, b, text())
    print("ALL OK (prompt keeps on model switch)")


if __name__ == "__main__":
    main()
