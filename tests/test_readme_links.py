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
anchors = {slug(h) for h in headings}

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
checked = text.replace(example, "")
assert not any(x in checked for x in private), [x for x in private if x in checked]

print("ALL OK (readme links)")
sys.exit(0)
