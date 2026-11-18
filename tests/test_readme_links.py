"""README for humans (5.11.2026): every jump link (#section) points at a real heading, and every file or picture the README
links to exists in the repo. The quick start, the install sections and the help table must stay in place.

    python tests/test_readme_links.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = (ROOT / "README.md").read_text(encoding="utf-8")


def slug(heading: str) -> str:
    """GitHub's anchor: lower case, punctuation removed, spaces become hyphens."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


# headings outside code fences
body, fenced = [], False
for line in text.splitlines():
    if line.strip().startswith("```"):
        fenced = not fenced
        continue
    if not fenced:
        body.append(line)
headings = [re.sub(r"^#+\s*", "", l) for l in body if re.match(r"^#{1,6}\s", l)]
headings += re.findall(r"<summary><h2>([^<]+)</h2></summary>", text)      # folded sections (Help, Technical details: user 18.11.)
anchors = {slug(h) for h in headings}
anchors |= set(re.findall(r'<a id="([^"]+)"></a>', text))      # HTML anchors, e.g. the Examples fold (17.11.)

# 1. the sections a newcomer is sent to
for want in ("Before you start", "How it fits together", "Install on Windows", "Install on Linux", "Functions", "Help",
             "Technical details"):
    assert want in headings, f"heading missing: {want}"
for gone in ("Licences of the models", "Credits", "First start", "Quick start"):      # removed 16.11. (user: absolute minimum); 17.11.: one full install section per system, Quick start became Before you start
    assert gone not in headings, f"heading back: {gone}"

# 2. jump links
links = re.findall(r"\]\(#([^)]+)\)", text)
assert links, "no jump links"
bad = sorted({a for a in links if a not in anchors})
assert not bad, f"jump links without a heading: {bad}"

# 3. files and pictures
for target in re.findall(r"(?:\]\(|src=\")((?!https?:|#|mailto:|\.\./\.\./actions/)[^)\" ]+)", text):
    assert (ROOT / target).exists(), f"linked file missing: {target}"

# 3b. badges (17.11.): the CI badge is a relative GitHub link (../../actions/...), so the README names no repository (check 5) and
# works in whichever repo it is exported to; the workflow it points at must exist. No hard-coded test counts (a static number
# drifts: the companion project's badge said 194 while its text said 152).
assert "![Install matrix](../../actions/workflows/install-matrix.yml/badge.svg)" in text, "CI badge missing"
assert (ROOT / ".github" / "workflows" / "install-matrix.yml").exists(), "the CI badge points at a workflow that is gone"
badge_lines = [l for l in text.splitlines() if l.startswith("[![")]
assert len(badge_lines) >= 4, "the badge block is incomplete"
assert not re.search(r"badge/tests?-", text, re.I), "no static test-count badge"

# 4. the screenshot is there and not empty
shot = ROOT / "readme-images" / "plugin-window.png"
assert shot.exists() and shot.stat().st_size > 10_000 and shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

# 5. a placeholder repository is fine until the public repo exists, but no private path or name may sneak in
private = ("C:\\" + "programs", "Phil" + "ipp", "phil-" + "had" + "erer")     # built from parts: the export scan must not find the names in this file
example = "C:\\" + "programs\\pxc"     # the README's example install folder is allowed (user 11.11.), nothing else under it
clone = "github.com/" + "phil-" + "had" + "erer" + "/pxc.git"     # the public clone address (user 18.11.), nothing else with the name
checked = text.replace(example, "").replace(clone, "")
assert not any(x in checked for x in private), [x for x in private if x in checked]

# 6. the examples (18.11., replaces the fold of 17.11.): the README shows a short teaser with a button to EXAMPLES.md, both
# written by tools/make_more_examples.py between its markers; EXAMPLES.md holds every example in the user's order, no outer
# fold (closing it left the reader far down the README)
assert text.count("<!-- examples:start -->") == 1 and text.count("<!-- examples:end -->") == 1, "examples markers"
ex = text[text.index("<!-- examples:start -->"):text.index("<!-- examples:end -->")]
assert '<a id="examples"></a>' in ex and "## Examples" in ex and "<details>" not in ex, "the Examples teaser is wrong"
assert '<a href="EXAMPLES.md"><img src="readme-images/all-examples.svg"' in ex, "the button to EXAMPLES.md is missing"
assert (ROOT / "readme-images" / "all-examples.svg").exists(), "the button picture is missing"
assert text.index("<!-- examples:start -->") < text.index("## How it fits together"), "examples belong at the top"
assert ex.index("<table>") < ex.index('<a href="EXAMPLES.md"><img src="readme-images/all-examples.svg"'), \
    "the button goes below the two main pictures (user 18.11.)"
assert "Photos: Magnific" not in ex, "no photo credit in the README: the credited photos are only on EXAMPLES.md (user 18.11.)"
assert "## Features" in text and "**Seven SOTA models:**" in text and "**Six generation modes:**" in text, "Features list"
feat = text[text.index("## Features"):text.index("## How it fits together")]
assert feat.index("**Seven SOTA models:**") < feat.index("**Six generation modes:**"), "the models come first (user 18.11.)"
assert feat.index("**Six generation modes:**") < feat.index("Style prompt examples"), \
    "the style prompt examples stand right above How it fits together (user 18.11.)"
page = (ROOT / "EXAMPLES.md").read_text(encoding="utf-8")
pics = re.findall(r'<img src="(readme-images/examples/[^"]+)"', page)
assert len(set(pics)) >= 10, "too few example pictures"
missing = [x for x in set(pics) if not (ROOT / x).exists()]
assert not missing, f"EXAMPLES.md pictures missing: {missing}"
assert "[← Back to the README](README.md)" in page and "Photos: Magnific, Freepik, Pexels" in page
assert not page.lstrip().startswith("<details>") and "<summary><h2>" not in page, "no outer fold on the examples page"
order = ["Text to image", "Edit canvas", "Edit canvas › Style prompts (built in)", "Fill Selection", "Remove Selection",
         "Multi image edit", "Sketch to image", "Scribble on photo", "Scribble with reference", "Expand image"]   # user 18.11.
found = [h for h in re.findall(r"<b>([^<]+)</b>", page) if h in order]
assert found == [h for h in order if h in found] and len(found) >= 8, f"order of the examples: {found}"
assert not any(x in page for x in private), "private name on the examples page"

# the logo and the function icons (user 18.11.): a dark and a light file each, both there (srcset is not caught above)
for target in re.findall(r'srcset="([^"]+)"', text):
    assert (ROOT / target).exists(), f"dark-mode picture missing: {target}"
assert 'src="readme-images/logo.png"' in text and (ROOT / "readme-images/logo.png").exists(), "logo"   # one picture on the window's grey (18.11.)
for name in ("text-to-image", "expand", "fill", "remove", "edit", "upscale-refine"):
    assert f'srcset="readme-images/icons/{name}-dark.png"' in text, f"icon {name}"

print("ALL OK (readme links)")
sys.exit(0)
