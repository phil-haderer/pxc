# tags: prompt, models
"""Your prompt text stays when the model changes inside Edit canvas (and Multi image edit, Fill, ...): every pair of models,
also through a model that only has Text to image. Hidden Tk window (stubbed in test_reset_all).

    python tests/test_prompt_keeps_on_model_switch.py
"""
import itertools
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reset_all as ra  # noqa: E402

from pccomfy import models  # noqa: E402

TEXT = "make it night"
SLOW = os.environ.get("PCCOMFY_SLOW_TESTS") == "1"


def triples(keys: list[str]) -> list[tuple[str, ...]]:
    """Every three-click order with PCCOMFY_SLOW_TESTS=1 (343, about 25 s); otherwise every order whose middle click is a
    Text-to-image-only model (the case this part is about) and a seventh of the others that changes daily (tempo plan T5,
    24.11., like A3 of test_start_factory)."""
    every = list(itertools.product(keys, repeat=3))
    if SLOW:
        return every
    t2i_only = {m.key for m in models.MODELS if set(m.modes) == {"txt2img"}}
    day = int(os.environ.get("PCCOMFY_START_SAMPLE_DAY") or date.today().toordinal())
    return [s for i, s in enumerate(every) if s[1] in t2i_only or i % 7 == day % 7]


def main():
    app = ra.make()
    text = lambda: app.t_prompt.get("1.0", "end").strip()      # noqa: E731
    keys = [m.key for m in models.MODELS]
    for mode in ("edit", "multi_edit", "inpaint"):
        for a, b in itertools.product([m.key for m in models.MODELS if mode in m.modes], keys):
            ra.go(app, a, mode)
            app._away_prompt = ""        # the text before Multi image edit waits aside and would come back when it is left (24.11.)
            app.t_prompt.delete("1.0", "end")
            app.t_prompt.insert("1.0", TEXT)
            ra.go(app, b, mode)
            if mode == "multi_edit" and app.v_mode.get() != "multi_edit":
                # the new model has no Multi image edit: the window leaves it, and its text waits aside (user 23.11.)
                assert text() == "" and app._sketch_away.get("multi_edit") == TEXT, (a, b, text())
                app._sketch_away.pop("multi_edit", None)
                continue
            assert text() == TEXT, (mode, a, b, text())
    for seq in triples(keys):                                # three clicks in a row, also over a Text-to-image-only model
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
    # the Multi text waiting aside follows a model change too: it comes back with the new model's image names (23.11.)
    ra.go(app, "qwen", "multi_edit")
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "put the bag from <image2> on <image1>")
    ra.go(app, "qwen", "edit")
    assert text() == "" and app._sketch_away.get("multi_edit") == "put the bag from <image2> on <image1>"
    ra.go(app, "flux2", "edit")
    assert app._sketch_away.get("multi_edit") == "put the bag from image 2 on image 1", app._sketch_away
    ra.go(app, "flux2", "multi_edit")
    assert text() == "put the bag from image 2 on image 1", text()
    assert any(set(m.modes) == {"txt2img"} for m in models.MODELS), "no Text-to-image-only model: the sample lost its point"
    print("ALL OK (prompt keeps on model switch;", f"{len(triples(keys))} of {len(keys) ** 3} three-click orders"
          + ("" if SLOW else ", all with PCCOMFY_SLOW_TESTS=1") + ")")


if __name__ == "__main__":
    main()
