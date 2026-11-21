"""The written prompt is kept (user 20.11.): the same request, picture, text model and writer seed send the text the writer
wrote before, so a run of another graph in between (ComfyUI keeps only the last graph's results) does not make it write
again. "Reroll prompt" (a new writer seed) gives a new key.

    python tests/test_written_prompt.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PCCOMFY_HOME", tempfile.mkdtemp(prefix="pccomfy-written-"))
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from pccomfy import comfy, workflows  # noqa: E402

WF = ROOT / "workflows"


def graph(wf, prompt="a horse", seed=1, writer_seed=0, image=None):
    p = workflows.GenParams(prompt=prompt, seed=seed, writer_seed=writer_seed)
    g, _out = workflows.apply_template(workflows.load_template(WF / wf), p, image, None, None, ref_first=False)
    workflows.set_writer_seed(g, writer_seed)
    return g


def main():
    # Text to image (MOSS): the image seed does not change the key, the writer seed and the request do
    k = workflows.writer_key(graph("moss-image-t2i.json"))
    assert k and k == workflows.writer_key(graph("moss-image-t2i.json", seed=99))
    assert k != workflows.writer_key(graph("moss-image-t2i.json", writer_seed=5))       # Reroll prompt
    assert k != workflows.writer_key(graph("moss-image-t2i.json", prompt="a cow"))
    assert k != workflows.writer_key(graph("flux3-klein-t2i.json"))                     # another text model / graph

    # an edit with a picture: the key follows the picture's content, not its upload name
    g = graph("minimax-h3-image-edit.json", image="pccomfy/pcc-x-image.png")
    ka = workflows.writer_key(g, {"pccomfy/pcc-x-image.png": "aaa"})
    kb = workflows.writer_key(g, {"pccomfy/pcc-x-image.png": "bbb"})
    assert ka and kb and ka != kb
    g2 = graph("minimax-h3-image-edit.json", image="pccomfy/pcc-y-image.png")
    assert workflows.writer_key(g2, {"pccomfy/pcc-y-image.png": "aaa"}) == ka

    # the kept text replaces the writer: its readers get the text, the writer chain and its preview are gone
    g = graph("moss-image-t2i.json")
    end = workflows.writer_end(g, workflows.prompt_writers(g)[0])
    used = workflows.use_written(g, "WRITTEN")
    assert end not in used and not workflows.prompt_writers(used)
    assert not any("vgl" in workflows._tags(n) for n in used.values())
    assert used["4"]["inputs"]["text"] == "WRITTEN"
    assert g[end]                                   # the original graph is untouched

    # Reference at scribble: a sentence is appended behind the writer, the preview shows the joined text: nothing kept
    g = graph("moss-image-t2i.json")
    workflows.append_to_writer(g, "with the cup from <ref>")
    assert workflows.writer_key(g) == ""
    # a graph without a writer
    assert workflows.writer_key(workflows.bypass_prompt_writer(graph("moss-image-t2i.json"), "x")) == ""

    # the upload records the picture's hash under the name ComfyUI gives back
    c = comfy.ComfyUI("http://127.0.0.1:1")
    c._request = lambda *a, **k: json.dumps({"name": "pcc-x-image.png", "subfolder": "pccomfy"}).encode()
    name = c.upload_image(Image.new("RGB", (8, 8), "white"), "pcc-x-image.png")
    h1 = c.upload_hashes[name]
    c.upload_image(Image.new("RGB", (8, 8), "black"), "pcc-x-image.png")
    assert name == "pccomfy/pcc-x-image.png" and c.upload_hashes[name] != h1
    print("ALL OK (written prompt kept)")


if __name__ == "__main__":
    main()
