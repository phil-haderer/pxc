# tags: remove, prompt
"""Remove with a named object (user 16.11., docs/tests/remove-name-ergebnis.md): Flux 3 lets its upsampler write the
instruction for the typed words (E, fixed end), Flux 2 and Fibo put the typed words into sentence D (F); an empty field
lets the model's text model name the object (sentence D). Qwen keeps its old sentences. Flux 3 needs the upsampler.

    python tests/test_remove_named.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_gui_presets as t  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

gui, cfgmod = t.gui, t.cfgmod
from PIL import Image  # noqa: E402

from pccomfy import bridge, manifest, models, workflows  # noqa: E402
from pccomfy.bridge import Request  # noqa: E402

UPS = "qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors"


def test_helpers():
    assert bridge.remove_user_name("tree in the background") == "the tree in the background"
    assert bridge.remove_user_name("The red car.") == "The red car"
    assert bridge.remove_user_name("a dog") == "a dog" and bridge.remove_user_name("  ") == ""
    assert bridge.clean_remove_name("\"The miniature robot held in the hand.\" It is small.") == "the miniature robot"
    assert bridge.clean_remove_name("brown goat inside the red outline") == "the brown goat"
    assert bridge.clean_remove_name("person in the foreground") == "the person"
    assert bridge.clean_remove_name("") == ""
    assert bridge.clean_remove_name("one two three four five six seven eight nine ten") == "the one two three four five six seven eight"
    w = bridge.clean_remove_writing("Here is the instruction:\n\"Remove the yellow helmet behind the hand. Keep the hand\"")
    assert w == "Remove the yellow helmet behind the hand. Keep the hand.", w
    assert bridge.clean_remove_writing("Sure. Only this.") == ""
    sq = Image.new("L", (10, 10), 255)
    assert bridge.remove_named_prompt(sq, "the dog").startswith("Remove the dog inside the red rectangle completely")
    assert "partly reaches into the red rectangle" in bridge.remove_named_prompt(sq, "the dog")
    assert bridge.remove_written_prompt(sq, "Remove the dog.") == "Remove the dog. Also remove the red rectangle itself."


def sent(style, typed, writer="writer.safetensors", answer="", wf="flux3-klein-edit.json"):
    """The prompt a Remove run sends, and the questions the text model was asked."""
    import test_reference_mode as T
    pc, _, b = T.make(tempfile.mkdtemp(), layers=2)
    b.comfy = T.FakeComfy()
    asked = []

    def describe(im, progress=None, question="", workflow=None, clip="", seed=None):
        asked.append((question, clip, im.size))
        progress(0.5, "x")
        return answer

    b._describe = describe
    req = Request(mode="remove", workflow=str(t.ROOT / "workflows" / wf), enhance=False, remove_target=typed,
                  remove_style=style, remove_writer=writer)
    req.params = workflows.GenParams(prompt=typed, seed=7)
    b.run(req)
    graph = b.comfy.graphs[-1]
    text = next(n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode")
    return text, asked


def test_bridge():
    # F: the typed words in sentence D, no text model
    text, asked = sent("F", "tree in the background", wf="flux2-klein-edit.json")
    assert text.startswith("Remove the tree in the background inside the red rectangle") and "partly reaches" in text and not asked
    # E: the writer writes the instruction for the typed words; the fixed end
    text, asked = sent("E", "helmet behind the hand", answer="Remove the yellow helmet behind the man's hand.")
    assert text == "Remove the yellow helmet behind the man's hand. Also remove the red rectangle itself.", text
    assert len(asked) == 1 and "\"helmet behind the hand\"" in asked[0][0] and asked[0][1] == "writer.safetensors"
    # E without a usable answer: the typed words in sentence D
    text, _ = sent("E", "helmet", answer="Sure.")
    assert text.startswith("Remove the helmet inside the red rectangle"), text
    # empty field: the writer names the object (question a), sentence D
    for style in ("E", "F"):
        text, asked = sent(style, "", answer="The brown goat held in the hand.")
        assert text.startswith("Remove the brown goat inside the red rectangle"), (style, text)
        assert asked[0][0] == bridge.REMOVE_NAME_QUESTION
    # empty field, no name or no writer: the old sentence without a name
    assert sent("F", "", answer="")[0].startswith("Erase everything inside the red rectangle")
    text, asked = sent("F", "", writer="")
    assert text.startswith("Erase everything inside the red rectangle") and not asked
    # without a style (Qwen): the old sentences
    assert sent("", "the dog")[0].startswith("Remove the dog that is inside the red rectangle")


def test_models_and_manifest():
    styles = {m.key: m.modes["remove"].remove_style for m in models.MODELS if "remove" in m.modes}
    assert styles == {"flux3": "E", "flux2": "F", "qwen": "", "fibo": "F"}, styles
    # Flux 3: the upsampler is a required file of Remove, so a missing one locks the whole model (user 16.11., choice a)
    assert UPS in manifest.mode_required("flux3", "remove") and not manifest.mode_alone("flux3", "remove")
    assert manifest.describe_writers("flux3")[0] == UPS


def test_window():
    import shutil
    app = gui.App(cfgmod.load())
    wfdir = Path(app.workflows_dir)
    wfdir.mkdir(parents=True, exist_ok=True)
    names = sorted({w for m in models.MODELS for w in m.workflows()})
    for f in names:
        shutil.copy(t.ROOT / "workflows" / f, wfdir / f)
    app.cb_workflow["values"] = [gui.BUILTIN] + names
    app._llm_file = lambda: "found-writer.safetensors"
    for k, style in (("flux3", "E"), ("flux2", "F"), ("fibo", "F"), ("qwen", "")):
        app.v_model.set(k)
        app.v_mode.set("remove")
        app._on_model()
        app.t_prompt.delete("1.0", "end")
        app._prompt_placeholder(focused=False)
        assert app._ph.cget("text") == models.REMOVE_PLACEHOLDER, k      # Qwen too since 17.11. (was "Prompt")
        req = app._request()
        assert req.remove_style == style and req.remove_writer == ("found-writer.safetensors" if style else ""), k
        app.t_prompt.insert("1.0", "the dog")
        assert app._request().remove_target == ("the dog" if style else "") or k == "qwen", k
        app.t_prompt.delete("1.0", "end")
    app.v_model.set("flux3")
    app.v_mode.set("edit")
    app._on_model()
    req = app._request()
    assert req.remove_style == "" and req.remove_writer == ""


def main():
    test_helpers()
    test_bridge()
    test_models_and_manifest()
    test_window()
    print("ok")


if __name__ == "__main__":
    main()
