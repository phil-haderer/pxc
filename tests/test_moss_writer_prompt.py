"""The MOSS prompt writer's system prompt is short and for English or German requests (user 21.11., 6A; measured with
tests/live_writer_short_long.py --run moss-en, docs/tests/schreiber-laengen-ergebnis.md, section 21.11.): 120 to 200 words
(up to 250 for posters and multi-subject scenes) instead of 220 to 500, no "Chinese" request any more; the rest of the
official text stays.

    python tests/test_moss_writer_prompt.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    g = json.loads((ROOT / "workflows" / "moss-image-t2i.json").read_text(encoding="utf-8"))
    sp = [n["inputs"]["value"] for n in g.values()
          if n.get("_meta", {}).get("title") == "Text (System prompt of the MOSS prompt enhancer)"]
    assert len(sp) == 1, "the MOSS system prompt node is missing or doubled"
    v = sp[0]
    assert "Chinese" not in v, "the MOSS writer expects English or German requests since 21.11."
    assert "usually in English or German" in v and "(German stays German)" in v
    assert "aim for 120 to 200 words for a single-subject scene, up to 250 for posters" in v
    assert "220 to 320" not in v and "never fewer than 200 words" not in v
    # the official rules around it stay (facets, text rules, no edit verbs, the plugin's colour sentence)
    for keep in ("Build the caption from these eight facets", "Text rules:", "Hard rule: the caption always describes",
                 "Colour and light (added by the plugin)"):
        assert keep in v, keep
    print("ok")


if __name__ == "__main__":
    main()
