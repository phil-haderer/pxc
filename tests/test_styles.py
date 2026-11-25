# tags: styles, prompt
"""The Styles button beside the prompt (user 1.11.): styles.json (style prompts of the Krea 2 Style Explorer, MIT; for Text to image
84 with descriptive names in 13 groups since plan B step 3, 10.11.; before 186 in 9 groups; + 7 own studio and stock styles), the loader (a broken file means no styles), the palette icon, the button (only in a mode that has styles), a click on an entry is ADDED to the prompt after a line break (Text to image; Edit canvas and Sketch to image set the whole sentence, 47 styles from tools/styles-looks.json), and the whole text of every entry is kept for the hover box.
Stubbed Tk.

    python tests/test_styles.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_reset_all as ra  # noqa: E402  (installs the Tk stub and a temporary PCCOMFY_HOME)

from pccomfy import gui_common, icons, styles  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def data_checks():
    from pccomfy import models
    got = styles.load()
    assert list(got) == ["txt2img", "edit", "sketch"], list(got)    # Edit canvas and Sketch to image since plan B (10.11.)
    look_checks(got)
    sk = {s["name"]: s["text"] for g in got["sketch"] for s in g["styles"]}
    # a new style keeps what was typed for <WHAT IT SHOWS> (decision 8)
    mark = models.SKETCH_MARK
    filled = models.SKETCH_PHOTO.replace(mark, "a red barn")
    assert styles.subject_of(filled, sk.values(), mark) == "a red barn"
    assert styles.subject_of(models.SKETCH_PHOTO, sk.values(), mark) == mark
    assert styles.subject_of("make it night", sk.values(), mark) is None
    assert styles.fill(models.SKETCH_ILLUSTRATION, "a red barn", mark) == models.SKETCH_ILLUSTRATION.replace(mark, "a red barn")
    assert styles.fill(models.SKETCH_ILLUSTRATION, None, mark) == models.SKETCH_ILLUSTRATION
    groups = got["txt2img"]
    assert len(groups) == 13 and sum(len(g["styles"]) for g in groups) == 73 + 7 + 3  # renamed and thinned (plan B step 3, 10.11.; 4 merged 18.11.; 7 taken out 20.11.) + own + the 3 from Edit (21.11.)
    # the own texts (tools/styles-own.json, user 10.11.) are there word for word; since 21.11. Text to image follows Edit's
    # order (tools/build_styles.py follow_edit), so an own style Edit also has stands where Edit has it, the others at the end
    # of their group (tools/ is private since 17.11.: the release export leaves it out, so the check runs only where it is)
    edit_names = {s["name"] for g in got["edit"] for s in g["styles"]}
    own_file = ROOT / "tools" / "styles-own.json"
    own_styles = []
    if own_file.exists():
        own = json.loads(own_file.read_text(encoding="utf-8"))["groups"]
        own_styles = [(g["name"], s["name"], s["text"]) for g in own for s in g["styles"]]
        assert len(own_styles) == 7 + 3 and ("Studio & product", "Studio portrait") in [o[:2] for o in own_styles]   # + 3 from Edit (21.11.)
        t2i_text_of = {s["name"]: s["text"] for g in groups for s in g["styles"]}
        assert all(t2i_text_of.get(n) == t for _g, n, t in own_styles), "own texts word for word"
        for gname in dict.fromkeys(o[0] for o in own_styles):
            mine = [o for o in own_styles if o[0] == gname and o[1] not in edit_names]
            grp = next(g for g in groups if g["name"] == gname)
            assert not mine or [(gname, s["name"], s["text"]) for s in grp["styles"][-len(mine):]] == mine, gname
    else:
        print("  (tools/ not here: own styles not compared)")
    # Text to image in Edit's order (user 21.11., "Edit groups, rest after"): Edit's groups first and in Edit's order, each
    # starting with Edit's styles in Edit's order; the groups Edit lacks come after
    edit_groups = [g["name"] for g in got["edit"]]
    assert [g["name"] for g in groups][:len(edit_groups)] == edit_groups, [g["name"] for g in groups]
    for eg, tg in zip(got["edit"], groups):
        want = [s["name"] for s in eg["styles"]]
        assert [s["name"] for s in tg["styles"]][:len(want)] == want, eg["name"]
    names = [s["name"] for g in groups for s in g["styles"]]
    assert len(set(names)) == len(names), "short names must be unique"
    # 18.11. (docs/archiv/stil-vorschlag-18-11.md): merged styles are gone, renamed ones carry the new name, no scene words left
    assert not {"Dark romantic landscape, oil", "Gothic fantasy, fiery red", "Soft clouds, white minimal",
                "Stop-motion, felt and clay", "Cyberpunk city, neon rain", "8-bit pixel art"} & set(names)
    assert {"Claymation, stop-motion", "Cyberpunk neon, rain", "Solarpunk", "Cosmic glow", "Pixel art"} <= set(names)
    t2i_text = " ".join(s["text"] for g in groups for s in g["styles"]).lower()
    assert not any(w in t2i_text for w in ("megacity", "megastructures", "skeletal", "pastoral scene", "silhouette in window",
                                           "nocturnal city lighting", "turquoise water"))
    assert "voxel" not in next(s["text"] for g in groups for s in g["styles"] if s["name"] == "Low-poly game look")
    assert all(s["text"].strip() and s["name"].strip() for g in groups for s in g["styles"])
    assert all(len(g["styles"]) <= 25 for g in groups)       # a menu that fits the screen
    assert all(len(n) <= 40 for n in names), max(names, key=len)   # descriptive, but short enough for the menu
    assert (ROOT / "pccomfy" / "assets" / "LICENSE-krea-style-explorer.txt").read_text(encoding="utf-8").startswith("Style texts")
    # the texts are the source's, character for character (the source lives in data/, not in the repo: only checked where it is)
    src = ROOT / "data" / "styles" / "krea_moodboards.json"
    sel = ROOT / "data" / "styles" / "auswahl-2026-11-10.json"
    if src.exists() and sel.exists():
        texts = {e["index"]: e["styleKeywords"] for e in json.loads(src.read_text(encoding="utf-8"))}
        sys.path.insert(0, str(ROOT / "tools"))
        from build_styles import final          # rewritten, renamed and merged styles (17.11., 18.11.)
        # name and text only: since 21.11. the order and the group follow Edit (follow_edit, checked above)
        want = sorted(f for g in json.loads(sel.read_text(encoding="utf-8"))["groups"] for s in g["styles"]
                      if (f := final(s["name"], texts[s["index"]])))
        own_names = {o[1] for o in own_styles}
        have = sorted((s["name"], s["text"]) for g in groups for s in g["styles"] if s["name"] not in own_names)
        assert have == want
    else:
        print("  (source files not in data/styles: texts not compared)")


def look_checks(got):
    """Edit canvas and Sketch to image (plan B, 10.11.): styles.json is what tools/build_style_looks.py makes of
    tools/styles-looks.json; 11 tested styles of the pilot + 36 chosen by the user (10.11.), 3D only in Sketch to image."""
    from pccomfy import models
    if not (ROOT / "tools" / "build_style_looks.py").exists():     # tools/ is private since 17.11. (release export)
        print("  (tools/ not here: style looks not compared with their source)")
        return
    sys.path.insert(0, str(ROOT / "tools"))
    import build_style_looks
    built = build_style_looks.build()
    data = json.loads((ROOT / "pccomfy" / "assets" / "styles.json").read_text(encoding="utf-8"))["modes"]
    assert {k: data[k] for k in ("edit", "sketch")} == built, "styles.json is behind tools/styles-looks.json: run tools/build_style_looks.py"
    src = json.loads((ROOT / "tools" / "styles-looks.json").read_text(encoding="utf-8"))["groups"]
    all_src = [s for g in src for s in g["styles"]]
    assert len(all_src) == 38 and sum(1 for s in all_src if s.get("tested")) == 6     # A+ of 20.11.: 3 merged, 2 new sentences
    ed = {s["name"]: s["text"] for g in got["edit"] for s in g["styles"]}
    sk = {s["name"]: s["text"] for g in got["sketch"] for s in g["styles"]}
    assert len(ed) == 34 and len(sk) == 38, (len(ed), len(sk))     # 5 taken out by the user 20.11., 4 merged (A+, 20.11.)
    three_d = {s["name"] for g in src if g["name"] == "3D & craft" for s in g["styles"]}
    assert len(three_d) == 4 and not three_d & set(ed) and three_d <= set(sk)      # 3D render 0/6 on photos (pilot); 2 merged 20.11.
    assert "Pencil gesture sketch" in ed and "Pencil gesture sketch" in sk     # took over Pencil drawing in Sketch (A+, 20.11.)
    # A+ (user 20.11.): a style of Edit canvas / Sketch to image whose look Text to image has too carries its name there
    t2i = {s["name"] for g in got["txt2img"] for s in g["styles"]}
    own = set(ed) | set(sk)
    # every style of Edit canvas is in Text to image too, with the same picture (user 21.11.; the last three of 20.11. came in
    # with their own Text to image words in tools/styles-own.json); Sketch has none of its own either
    assert own - t2i == set(), sorted(own - t2i)
    assert all(styles.thumb_path(n) is not None for n in set(ed) & t2i)
    # the tested sentences stay word for word; every other text is look in its frame
    assert sk["Realistic photo"] == models.SKETCH_PHOTO and sk["Animated film"] == models.SKETCH_ILLUSTRATION
    mark = models.SKETCH_MARK
    assert all(t.count(mark) == 1 for t in sk.values()) and all(mark not in t for t in ed.values())
    for s in all_src:
        if "edit" in s["tabs"]:
            assert ed[s["name"]] == models.EDIT_FRAME.format(look=s["look"])
        if "sketch" in s["tabs"] and "fixed" not in s:
            no_lines = "" if s.get("lines") else models.SKETCH_NO_LINES      # user 18.11.: no sketch lines left
            assert sk[s["name"]] == models.SKETCH_FRAME.format(look=s["look"]) + no_lines
    # 18.11.: the sentence on 31 styles (Realistic photo has it in its own words), never on the 14 line styles
    clean = {n for n, t in sk.items() if t.lower().endswith("no drawing lines left.")}
    lined = {s["name"] for s in all_src if s.get("lines")}
    assert len(clean) == 27 and len(lined) == 11 and not clean & lined and "Modern anime, clean lines" in lined and "Gouache, flat and earthy" in clean
    # the same frames and looks as the style pilot (tests/live_style_round.py)
    pilot = (ROOT / "tests" / "live_style_round.py").read_text(encoding="utf-8")
    assert 'EDIT_FRAME = "' + models.EDIT_FRAME + '"' in pilot
    assert 'SKETCH_FRAME = "' + models.SKETCH_FRAME.replace(mark, "{subject}") + '"' in pilot
    assert all(len(g["styles"]) <= 25 for m in ("edit", "sketch") for g in got[m])
    assert all(len(n) <= 40 for n in list(ed) + list(sk))


def loader_checks():
    d = Path(tempfile.mkdtemp())

    def write(obj, name="s.json"):
        p = d / name
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        return p
    assert styles.load(d / "missing.json") == {}
    assert styles.load(write("{not json")) == {}
    assert styles.load(write({"modes": []})) == {}
    assert styles.load(write({"x": 1})) == {}
    ok = styles.load(write({"modes": {
        "txt2img": {"groups": [{"name": "A", "styles": [{"name": "one", "text": "t1"}, {"name": "", "text": "x"}, {"name": "bad"}, 5]},
                               {"name": "empty", "styles": []}, {"name": " ", "styles": [{"name": "n", "text": "t"}]}]},
        "edit": {"groups": [{"name": "B", "styles": [{"name": "two", "text": "t2"}]}]},
        "broken": 7}}))
    assert ok == {"txt2img": [{"name": "A", "styles": [{"name": "one", "text": "t1"}]}],
                  "edit": [{"name": "B", "styles": [{"name": "two", "text": "t2"}]}]}, ok


def icon_checks():
    assert "palette" in icons.SHAPES
    im = icons.render("palette", "#ffffff", 40)
    assert im.size == (40, 40) and im.getchannel("A").getextrema()[1] == 255


def gui_checks():
    app = ra.make()
    assert set(app.m_styles) == {k for k, _l in gui_common.MODE_LABELS} | {"txt2img", "edit", "sketch"} and len(app._style_texts) == 73 + 7 + 3 + 34 + 38
    assert not str(app.b_styles.cget("text")) and app.b_styles.cget("image")      # an icon in the column right of the field (12.11.)
    # the button: only in Text to image, Edit canvas and Sketch to image
    ra.go(app, "flux3", "txt2img")
    app._on_mode_ui()
    assert app._styles_shown
    ra.go(app, "flux3", "multi_edit")
    app._on_mode_ui()
    assert app._styles_shown                        # every function has the button since 11.11. (Custom prompts); was: not in Multi image edit
    ra.go(app, "flux3", "edit")
    app._on_mode_ui()
    assert app._styles_shown
    ra.go(app, "flux3", "txt2img")
    app._on_mode_ui()
    assert app._styles_shown
    # an entry is added after a line break (an empty field just gets the style; one undo step in a real Tk)
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "a red bicycle")
    first = styles.load()["txt2img"][0]["styles"][0]["text"]
    app._apply_style(first)
    assert app.t_prompt.get("1.0", "end").strip() == "a red bicycle\n" + first
    assert app.v_status.get() == ""                 # no status message on a style (user 21.11., choice 3)
    # a field that is switched off is left alone
    app.t_prompt.configure(state="disabled")
    app._apply_style("other")
    app.t_prompt.configure(state="normal")
    assert app.t_prompt.get("1.0", "end").strip() == "a red bicycle\n" + first
    # the hover box: the whole text of an entry by (menu, number); nothing for a group entry or "none"
    key, text = next(iter(app._style_texts.items()))
    menu = type("M", (), {"__str__": lambda s: key[0]})()
    assert app._style_text_at(menu, key[1]) == text and text in {t for g in styles.load()["txt2img"] for t in [s["text"] for s in g["styles"]]}
    assert app._style_text_at(menu, "none") == "" and app._style_text_at(menu, None) == "" and app._style_text_at(menu, 999) == ""
    sketch_checks(app)
    edit_checks(app)


def edit_checks(app):
    """Edit canvas (plan B, 10.11.): Styles sets the whole sentence and is remembered, but opening the tab leaves the field as
    it was (user 10.11.), and an empty field still runs as before (no style message)."""
    from pccomfy import config as cfgmod, models
    text = lambda: app.t_prompt.get("1.0", "end").strip()
    st = {s["name"]: s["text"] for g in styles.load()["edit"] for s in g["styles"]}
    ra.go(app, "flux2", "edit")
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", "make it winter")
    app._apply_style(st["Watercolor storybook"], "Watercolor storybook")
    assert text() == st["Watercolor storybook"] and cfgmod.get_setting("style_edit") == "Watercolor storybook"
    app._apply_style(st["Gouache, flat and earthy"], "Gouache, flat and earthy")
    assert text() == st["Gouache, flat and earthy"]
    ra.go(app, "flux2", "txt2img")
    app.t_prompt.delete("1.0", "end")
    ra.go(app, "flux2", "edit")
    assert text() == ""                                         # not filled on opening
    app._prompt_placeholder()
    assert app._ph.cget("text") == "Prompt"
    app.v_status.set("")
    app.generate()
    assert app.v_status.get() != models.NO_STYLE
    cfgmod.set_setting("style_edit", "")


def sketch_checks(app):
    """Sketch to image (plan B, 10.11.): Styles sets the whole sentence, keeps what was typed for <WHAT IT SHOWS>, and is
    remembered; without a style the field stays empty and a run stops with a message."""
    from pccomfy import config as cfgmod, models
    mark = models.SKETCH_MARK
    cfgmod.set_setting("style_sketch", "")
    text = lambda: app.t_prompt.get("1.0", "end").strip()
    ra.go(app, "flux2", "sketch")
    assert text().startswith("a red bicycle")                  # your own text stays when the tab opens
    app.t_prompt.delete("1.0", "end")
    ra.go(app, "flux2", "txt2img")
    ra.go(app, "flux2", "sketch")
    app._on_mode_ui()
    assert app._styles_shown
    assert text() == ""                                         # no style chosen yet: empty, the grey placeholder
    app._prompt_placeholder()
    assert app._ph.cget("text") == models.SKETCH_PLACEHOLDER
    app.generate()
    assert app.v_status.get() == models.NO_STYLE                # no run without a style or text (decision 7)
    app._apply_style(models.SKETCH_PHOTO, "Realistic photo")
    assert text() == models.SKETCH_PHOTO and cfgmod.get_setting("style_sketch") == "Realistic photo"
    app.t_prompt.delete("1.0", "end")
    app.t_prompt.insert("1.0", models.SKETCH_PHOTO.replace(mark, "a red barn"))
    app._apply_style(models.SKETCH_ILLUSTRATION, "Animated film")          # the subject goes along (decision 8)
    assert text() == models.SKETCH_ILLUSTRATION.replace(mark, "a red barn")
    # the style chosen last comes back when the tab opens with an empty field (decision 7)
    ra.go(app, "flux2", "txt2img")
    app.t_prompt.delete("1.0", "end")
    ra.go(app, "flux2", "sketch")
    assert text() == models.SKETCH_ILLUSTRATION
    app._prompt_placeholder()
    assert app._ph.cget("text") == models.SKETCH_PLACEHOLDER        # the word follows the tab ("Prompt" elsewhere)
    ra.go(app, "flux2", "txt2img")
    app._prompt_placeholder()
    assert app._ph.cget("text") == "Prompt"
    cfgmod.set_setting("style_sketch", "")


def main():
    data_checks()
    loader_checks()
    icon_checks()
    gui_checks()
    print("ALL OK (styles)")


if __name__ == "__main__":
    main()
