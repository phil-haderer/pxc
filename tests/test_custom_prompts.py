"""Custom prompts without Tk (pccomfy/custom_prompts.py; the Prompt-Saver, user 11.11.): add, edit, delete, names without case,
the 100 limit, the 40 character name, the label with model and function, the file in PCCOMFY_HOME, a broken file renamed to
.bad with a note.

    python tests/test_custom_prompts.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp(prefix="pccomfy-customprompts-")
os.environ["PCCOMFY_HOME"] = TMP
sys.path.insert(0, str(ROOT))

from pccomfy import custom_prompts as cp  # noqa: E402


def main():
    assert cp.path() == Path(TMP) / "custom_prompts.json", cp.path()
    assert cp.load() == [] and cp.load_note() == ""          # no file yet

    e = []
    assert cp.add(e, "  Meadow ", "Summer meadow", "Flux 3 Klein", "Text to image") == ""
    assert e == [{"name": "Meadow", "text": "Summer meadow", "model": "Flux 3 Klein", "function": "Text to image",
                  "model_key": "", "mode": "", "tab": ""}]
    assert cp.add(e, "MEADOW", "x") == "exists" and len(e) == 1                 # case-insensitive
    assert cp.add(e, "meadow", "Winter meadow", "Qwen", "Edit canvas", replace=True) == "" and len(e) == 1
    assert e[0]["text"] == "Winter meadow" and e[0]["model"] == "Qwen"
    assert cp.add(e, "", "x") == "name" and cp.add(e, "A", "   ") == "text"
    assert cp.add(e, "n" * 60, "t") == "" and len(e[1]["name"]) == cp.MAX_NAME

    assert cp.edit(e, 1, "Meadow", "t") == "exists"
    assert cp.edit(e, 1, "Moor", "new text") == "" and (e[1]["name"], e[1]["text"], e[1]["model"]) == ("Moor", "new text", "")
    assert cp.edit(e, 1, "meadow", "t", replace=True) == "" and [x["name"] for x in e] == ["meadow"]
    cp.delete(e, 0)
    cp.delete(e, 5)
    assert e == []

    # the keys behind the labels (user 15.11.): kept by add and edit; an older entry gets them from its labels
    ctx = {"model_key": "qwen", "mode": "multi_edit", "tab": "multi"}
    assert cp.add(e, "Bag", "Put <image2> here", "Qwen Image 2.1", "Multi Image Edit", context=ctx) == ""
    assert {k: e[0][k] for k in cp.CONTEXT_KEYS} == ctx
    assert cp.edit(e, 0, "Bag 2", "other") == "" and {k: e[0][k] for k in cp.CONTEXT_KEYS} == ctx
    assert cp.context(e[0], {}, {}) == ctx
    old = {"name": "Old", "text": "t", "model": "Qwen Image 2.1", "function": "Edit canvas"}
    assert cp.context(old, {"Qwen Image 2.1": "qwen"}, {"Edit canvas": "edit"}) == {"model_key": "qwen", "mode": "edit", "tab": ""}
    assert cp.context(old, {}, {}) == {"model_key": "", "mode": "", "tab": ""}
    e.clear()

    assert cp.label({"name": "Summer meadow", "model": "Flux 3 Klein", "function": "Edit canvas"}) == "Edit canvas · Flux 3 Klein – Summer meadow"   # no square brackets (user 21.11.)
    assert cp.label({"name": "Plain", "model": "", "function": ""}) == "Plain"

    full = []
    for i in range(cp.MAX_ENTRIES):
        assert cp.add(full, f"p{i}", "t") == ""
    assert cp.add(full, "one more", "t") == "full" and cp.add(full, "P0", "other", replace=True) == ""

    # the file: written, read back, junk entries dropped
    assert cp.save(full) and len(cp.load()) == cp.MAX_ENTRIES
    cp.path().write_text(json.dumps([{"name": "a", "text": "t"}, {"name": "A", "text": "dup"}, {"name": "", "text": "x"}, 5,
                                     {"name": "ok", "text": "t", "model": "M", "function": "F"}]), encoding="utf-8")
    assert [(x["name"], x["model"]) for x in cp.load()] == [("a", ""), ("ok", "M")]
    cp.path().write_text(json.dumps([{"name": "k", "text": "t", "model_key": "flux3", "mode": "multi_edit", "tab": "bbox"}]), encoding="utf-8")
    assert [(x["model_key"], x["mode"], x["tab"]) for x in cp.load()] == [("flux3", "multi_edit", "bbox")]

    # a broken file: renamed, a note, an empty list; the next broken file replaces the old .bad
    cp.path().write_text("{ not json", encoding="utf-8")
    assert cp.load() == [] and "custom_prompts.json.bad" in cp.load_note()
    assert not cp.path().exists() and (cp.path().parent / "custom_prompts.json.bad").read_text(encoding="utf-8") == "{ not json"
    cp.clear_note()
    assert cp.load_note() == ""
    cp.path().write_text('{"a": 1}', encoding="utf-8")           # valid JSON but not a list: broken too
    assert cp.load() == [] and cp.load_note()
    cp.clear_note()
    print("ALL OK (custom prompts)")


if __name__ == "__main__":
    main()
