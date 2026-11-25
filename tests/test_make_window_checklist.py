# tags: tools
"""tools/make_window_checklist.py (HTML checklist of the open window tests, test round 16a part C, user 21.11.): every
bullet of docs/plan/fenstertest.md and of part C2 of docs/plan/testrunde-16a.md becomes one item, ids stay the same when
the page is rebuilt, titles and groups come out as planned, and HTML in the plan text is escaped. tools/ and docs/ are
private: the check skips where they are missing.

    python tests/test_make_window_checklist.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

SAMPLE = """Intro line, not an item.

- **Remove leert das Feld (21.11., PC A, `feat/x`):** Remove wählen: Feld leer. GPU-Test offen.
- **Durchsicht 21.11. (PC A):** Linux (Mint-Laptop): Copy canvas.
- **Queue-Fenster (19.11., PC B):** an Spaltenköpfen ziehen, bei 150 %.
**Neu am 12.11. (PC B, Menüs)**
- **Stop** statt Cancel (schmaler), <b>roh</b>.
- Leere Statuszeile über der Fußzeile fällt weg; bei einer Meldung wird das Fenster höher.
- My settings mit Steps (Fehler vom 4.11. behoben). Mehr Text.
"""


def main():
    if not (ROOT / "tools" / "make_window_checklist.py").exists() or not (ROOT / "docs" / "plan" / "fenstertest.md").exists():
        print("skip: tools/ or docs/ missing (release export)")
        return
    import make_window_checklist as mw

    groups = mw.parse(SAMPLE, "ab16")
    assert [g["title"] for g in groups] == ["Neu am 21.11.", "Neu am 19.11.", "Neu am 12.11. (PC B, Menüs)"], groups
    items = [it for g in groups for it in g["items"]]
    assert [it["short"] for it in items] == [
        "Remove leert das Feld", "Durchsicht 21.11.", "Queue-Fenster", "Stop",
        "Leere Statuszeile über der Fußzeile fällt weg",
        "My settings mit Steps (Fehler vom 4.11. behoben)."], [it["short"] for it in items]
    assert items[0]["meta"] == "21.11., PC A, feat/x" and items[0]["body"].startswith("Remove wählen")
    assert items[3]["body"].startswith("**Stop** statt Cancel"), "a bold lead without colon keeps the whole sentence"
    assert items[0]["tags"] == ["GPU"] and items[1]["tags"] == ["Linux"] and items[2]["tags"] == ["150 %"]
    assert len({it["id"] for it in items}) == len(items)
    assert [it["id"] for it in mw.parse(SAMPLE, "ab16")[0]["items"]] == [it["id"] for it in groups[0]["items"]], \
        "ids must not change between two builds"
    assert mw.parse(SAMPLE, "c2")[0]["items"][0]["id"] != items[0]["id"], "the two parts have their own ids"
    page = mw.render([{"name": "T", "file": "f.md", "key": "ab16", "groups": groups}], "21.11.2026 20:00")
    assert "&lt;b&gt;roh&lt;/b&gt;" in page and "<b>roh</b>" not in page, "HTML in the plan text must be escaped"
    assert "21.11., PC A, feat/x" in page and page.count('class="item"') == len(items)
    assert "@@" not in page

    # one checkbox per sub-point (user 22.11.): sentences, not at dates, abbreviations or inside parentheses
    subs = mw.subpoints("Feld leer, grau „Name“; z. B. „car“ tippen. Fehler vom 4.11. behoben (Wahl A; B). "
                        "Passt es bei 150 %? Ja.")
    assert subs == ["Feld leer, grau „Name“", "z. B. „car“ tippen.",
                    "Fehler vom 4.11. behoben (Wahl A; B).", "Passt es bei 150 %? Ja."], subs
    assert [sp["text"] for sp in items[0]["subs"]] == ["Remove wählen: Feld leer.", "GPU-Test offen."]
    assert page.count('class="chk" data-k=') == sum(len(it["subs"]) for it in items)
    assert items[0]["subs"][0]["k"] == mw.parse(SAMPLE, "ab16")[0]["items"][0]["subs"][0]["k"], "stable keys"

    # checks as indented bullets (user 23.11.: "fasse schritte die zu einem test gehören zusammen"): steps → expected,
    # "braucht:" names what the test needs; ✓ / ✗ and a note field per check ("unter jedem punkt ein notizfeld")
    nested = mw.parse("- **Neu (23.11., PC A):** Kurz vorweg.\n"
                      "  - braucht: GPU-Lauf, Flux 3\n"
                      "  - Wähle X und drücke Y. Dann Z. → Es startet kein Lauf; die Zeile sagt „A“.\n"
                      "  - Nur ein Satz ohne Pfeil.\n"
                      "- **Alt (22.11.):** Satz eins ist hier. Satz zwei ist hier.\n"
                      "Ein Absatz dazwischen.\n"
                      "  - eingerückt nach dem Absatz: ein eigener Punkt wie bisher\n", "ab16")
    its = [it for g in nested for it in g["items"]]
    assert [it["short"] for it in its] == ["Neu", "Alt", "eingerückt nach dem Absatz: ein eigener Punkt wie bisher"], its
    assert not its[1]["checks"], "a paragraph ends the point: nothing after it is one of its checks"
    new, old = its[:2]
    nested = [{"title": "T", "note": "", "items": [new, old]}]
    assert new["needs"] == ["GPU-Lauf", "Flux 3"] and new["intro"] == "Kurz vorweg." and "GPU" in new["tags"]
    assert [(s["step"], s["exp"]) for s in new["subs"]] == [
        ("Wähle X und drücke Y. Dann Z.", "Es startet kein Lauf; die Zeile sagt „A“."), ("Nur ein Satz ohne Pfeil.", "")]
    assert [s["text"] for s in old["subs"]] == ["Satz eins ist hier.", "Satz zwei ist hier."] and not old["checks"]
    page2 = mw.render([{"name": "T", "file": "f.md", "key": "ab16", "groups": nested}], "x")
    assert page2.count('class="chk"') == 4 and page2.count('class="cb yes"') == 4 and page2.count('class="cb no"') == 4
    assert page2.count('class="cnote hidden"') == 4, "a note field under every check"
    assert '<span class="exp">→ Es startet kein Lauf; die Zeile sagt „A“.</span>' in page2
    assert 'braucht: GPU-Lauf, Flux 3' in page2 and '<p class="ibody">Kurz vorweg.</p>' in page2
    assert 'id="badsec"' in page2 and 'id="reload"' in page2
    # the real file is written that way (rule in CLAUDE.md, 23.11.): every point has its "braucht:" line and checks
    real = [it for g in mw.parse(mw.FENSTERTEST.read_text(encoding="utf-8"), "ab16") for it in g["items"]]
    assert real and all(it["needs"] and it["checks"] for it in real), [it["short"] for it in real if not it["checks"]]

    # the real plan files: one item per bullet, all ids unique, the page is written where --out says; one sample point with
    # two checks is added to a copy, so the check marks below do not depend on what is open today (25.11.: one check each)
    copy = Path(tempfile.mkdtemp(prefix="pccomfy-fenster-")) / "fenstertest.md"
    copy.write_text(mw.FENSTERTEST.read_text(encoding="utf-8").rstrip("\n") + "\n- **Probe mit zwei Prüfungen (Test):**\n"
                    "  - braucht: nichts\n  - Eins klicken. → A.\n  - Zwei klicken. → B.\n", encoding="utf-8")
    mw.FENSTERTEST = copy
    parts = mw.collect()
    fenster = mw.FENSTERTEST.read_text(encoding="utf-8")
    c2 = mw.section(mw.TESTRUNDE.read_text(encoding="utf-8"), "C2")
    want = sum(1 for ln in fenster.splitlines() if ln.startswith("- ")) + \
        sum(1 for ln in c2.splitlines() if ln.startswith("- "))         # indented bullets are checks, not points
    got = [it for p in parts for g in p["groups"] for it in g["items"]]
    assert len(got) == want, (len(got), want)
    assert len({it["id"] for it in got}) == len(got)
    assert all(it["short"] for it in got)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "sub" / "c.html"
        mw.main(["--out", str(out)])
        html = out.read_text(encoding="utf-8")
        assert len(re.findall(r'class="item"', html)) == want
        assert "<script>window.PXC_STATE =" not in html, "the file page keeps its marks in the browser"

        # --serve (user 22.11.): the marks go into a state file that is committed and travels to the other PC
        import threading
        import urllib.error
        import urllib.request
        state = Path(d) / "stand.json"
        srv = mw.make_server(0, state)      # port 0: a free port, never ComfyUI's 8188
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{port}"
            page = urllib.request.urlopen(base + "/").read().decode("utf-8")
            assert "<script>window.PXC_STATE =" in page and page.count('class="item"') == want
            first = next(it for it in got if len(it["subs"]) >= 2)     # a point with two checks (the list changes)
            body = {"items": {first["id"]: {"st": "bad", "note": "</script> Rand", "subs": {first["subs"][0]["k"]: True}},
                              "gone-item": {"st": "ok"}}}
            req = urllib.request.Request(base + "/state", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Origin": base})
            assert urllib.request.urlopen(req).status == 204
            saved = json.loads(state.read_text(encoding="utf-8"))
            assert list(saved["items"]) == [first["id"]], "marks of points no longer in the lists are dropped"
            assert saved["items"][first["id"]]["st"] == "bad" and saved["updated"]
            assert saved["items"][first["id"]]["subs"] == {first["subs"][0]["k"]: "ok"}, "true of old files = ✓"
            # ✗ and a note per check (user 23.11.)
            k0, k1 = first["subs"][0]["k"], first["subs"][1]["k"]
            body = {"items": {first["id"]: {"st": "bad", "note": "", "subs": {k0: "ok", k1: "bad", "x": False},
                                            "snotes": {k1: "Statuszeile leer", k0: "  "}}}}
            req = urllib.request.Request(base + "/state", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Origin": base})
            assert urllib.request.urlopen(req).status == 204
            got1 = json.loads(state.read_text(encoding="utf-8"))["items"][first["id"]]
            assert got1["subs"] == dict(sorted({k0: "ok", k1: "bad"}.items())) and got1["snotes"] == {k1: "Statuszeile leer"}, got1
            page = urllib.request.urlopen(base + "/").read().decode("utf-8")
            assert '"snotes": {"' + k1 + '": "Statuszeile leer"}' in page
            # the page knows the version of the plan files and asks for it to offer a reload
            ver = urllib.request.urlopen(base + "/version").read().decode("ascii")
            assert ver == mw.source_version() and f'window.PXC_VERSION = "{ver}"' in page
            # the server must stay usable after a bad POST with a broken item
            body = {"items": {first["id"]: {"st": "bad", "note": "</script> Rand", "subs": {k0: True}}}}
            req = urllib.request.Request(base + "/state", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Origin": base})
            assert urllib.request.urlopen(req).status == 204
            page = urllib.request.urlopen(base + "/").read().decode("utf-8")
            assert "<\\/script> Rand" in page and "</script> Rand" not in page, "a note cannot end the script"
            evil = urllib.request.Request(base + "/state", data=b'{"items": {}}', method="POST",
                                          headers={"Content-Type": "application/json", "Origin": "https://evil.example"})
            try:
                urllib.request.urlopen(evil)
                raise AssertionError("a POST from another web page must be refused")
            except urllib.error.HTTPError as e:
                assert e.code == 403
            assert json.loads(state.read_text(encoding="utf-8"))["items"], "the refused POST changed nothing"
        finally:
            srv.shutdown()
            srv.server_close()
    print("ok")


if __name__ == "__main__":
    main()
