# tags: prompt
"""Reroll prompt (user 18.11., choice A): the "Prompt writer seed" row is gone from the Advanced settings; the writer seed is
hidden (start value 0, sent with every run, saved with My settings and the history, Reset = 0). A button "Reroll prompt" right
of "Enhance my Prompt with LLM" draws a new one: the next run writes a new prompt, after that it stays the same again. The
button is there only in the Enhance row, only while Enhance is ticked, only for a writer that samples (not Fibo),
wherever the Enhance row is (MiniMax too). Sketch to image / Scribble (user 25.11., "Nur Reroll-Knopf zeigen"): the writer
always runs there, so the row shows "Reroll prompt" without the Enhance tick (Flux 3, Flux 2, Qwen; not Fibo or MiniMax,
not with a written prompt from the history). The window with the stubbed Tk.

    python tests/test_prompt_reroll.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp(prefix="pccomfy-reroll-"))
os.environ["PCCOMFY_NO_TIPS"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    gui, cfgmod = t.gui, t.cfgmod
    src = (ROOT / "pccomfy" / "gui.py").read_text(encoding="utf-8")
    assert 'text="Prompt writer seed' not in src and "f_wseed" not in src, "no seed row in the Advanced settings any more"
    assert "self.b_reroll = ttk.Button(self.f_enh," in src, "the button sits in the Enhance row"
    app = gui.App(cfgmod.load())
    assert not hasattr(app, "f_wseed") and not hasattr(app, "w_writer_seed")
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in gui.models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    shown = {"on": False}
    app.b_reroll.pack = lambda *a, **k: shown.__setitem__("on", True)
    app.b_reroll.pack_forget = lambda *a, **k: shown.__setitem__("on", False)
    app.b_reroll.winfo_manager = lambda: "pack" if shown["on"] else ""

    def pick(model, mode, enhance=True):
        app.v_model.set(model)
        app.v_mode.set(mode)
        app._on_model()
        app.v_enhance.set(enhance)
        app._on_workflow()
        return shown["on"]

    assert app.v_writer_seed.get() == gui.WRITER_SEED_DEFAULT == 0
    assert pick("flux3", "txt2img", True), "Flux 3 Text to image with Enhance on: the button is there"
    assert not pick("flux3", "txt2img", False), "Enhance off: no button"
    app.v_enhance.set(True)                       # the tick alone (its trace) shows it again
    assert shown["on"]
    assert pick("qwen", "txt2img", True), "Qwen Text to image"
    tick = {"on": True}
    app.cb_enhance.pack = lambda *a, **k: tick.__setitem__("on", True)
    app.cb_enhance.pack_forget = lambda *a, **k: tick.__setitem__("on", False)
    app.cb_enhance.winfo_manager = lambda: "pack" if tick["on"] else ""
    for model in ("qwen", "flux3", "flux2"):
        for mode in ("sketch", "scribble"):
            assert pick(model, mode, False), f"{model} {mode}: Reroll prompt, also with Enhance off (the writer always runs)"
            assert not tick["on"] and app._writer_only(), f"{model} {mode}: no Enhance tick"
    assert not pick("fibo", "sketch", True) and not pick("minimax", "sketch", True), "no writer that samples: no button"
    pick("qwen", "sketch", True)
    app._written_for = "qwen"                     # a written prompt from the history runs without the writer: no button
    app._update_prompt_hint()
    assert not shown["on"] and not app._writer_only()
    app._written_for = ""
    app._update_prompt_hint()
    assert shown["on"]
    assert pick("qwen", "txt2img", True) and tick["on"], "back to Text to image: the tick is there again"
    pick("qwen", "sketch", True)
    app.v_writer_seed.set(0)
    app.reroll_prompt()
    assert app._request().params.writer_seed == app.v_writer_seed.get() != 0, "Sketch: the next run uses the new writer seed"
    app.v_writer_seed.set(0)
    assert not pick("flux3", "inpaint", True), "Fill: no prompt writer, no row"
    assert pick("minimax", "txt2img", True), "MiniMax Text to image with Enhance on: the button is there"
    assert pick("minimax", "edit", True), "MiniMax Edit with Enhance on"
    assert not pick("minimax", "edit", False), "MiniMax Edit starts with Enhance off: no button"
    assert not pick("fibo", "txt2img", True), "Fibo's writer takes the likeliest words: a new seed changes nothing"
    # the Enhance tooltip names Reroll prompt only where the button can appear (review 18.11.)
    assert gui.ENHANCE_REROLL_TIP not in app.tt_enhance.text, "Fibo: no button, no sentence"
    pick("flux3", "txt2img", True)
    assert app.tt_enhance.text == ("Rewrites your prompt with the Flux 3 prompt upsampler (Qwen 3.5 9B). "
                                   "Takes longer, most on smaller GPUs.\n" + gui.ENHANCE_REROLL_TIP), app.tt_enhance.text
    pick("flux2", "txt2img", True)       # a 4B writer: "a little longer" (user 18.11., choice C)
    assert app.tt_enhance.text == "Rewrites your prompt with Qwen3-VL 4B. Takes a little longer.\n" + gui.ENHANCE_REROLL_TIP
    pick("fibo", "edit", True)           # no Reroll line, no "it looks at your pictures"
    assert app.tt_enhance.text == "Rewrites your prompt with Qwen3-VL 4B. Takes a little longer.", app.tt_enhance.text

    # a click: a new seed (another number, in the seed range), sent with the next run, a word in the status line
    pick("flux3", "txt2img", True)
    assert app._request().params.writer_seed == 0
    seen = set()
    for _ in range(20):
        before = app.v_writer_seed.get()
        app.reroll_prompt()
        after = app.v_writer_seed.get()
        assert after != before and 0 <= after < 10**gui.SEED_DIGITS, (before, after)
        seen.add(after)
    assert len(seen) > 1
    assert app._request().params.writer_seed == after, "the next run uses the new seed (and keeps it)"
    assert app._request().params.writer_seed == after
    assert "new prompt" in app.v_status.get().lower(), app.v_status.get()

    # saved with My settings and the history, put back; an old -1 (the field of 17.11.) counts as 0; Reset = 0
    s = app._collect()
    assert s["writer_seed"] == after
    app.v_writer_seed.set(0)
    app._apply_settings(s)
    assert app.v_writer_seed.get() == after
    app._apply_settings({k: v for k, v in s.items() if k != "writer_seed"})      # an older save without the key keeps it
    assert app.v_writer_seed.get() == after
    app._apply_settings(dict(s, writer_seed=-1))
    assert app.v_writer_seed.get() == 0
    app.v_writer_seed.set(777)
    app._reset_settings()
    assert app.v_writer_seed.get() == 0
    print("ALL OK (prompt reroll)")


if __name__ == "__main__":
    main()
