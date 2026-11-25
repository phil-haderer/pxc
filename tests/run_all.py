"""Runs every tests/test_*.py in its own Python process and prints one line per file and a summary.
Run: python tests/run_all.py            (all files)
     python tests/run_all.py bars round  (only files whose name contains one of the words)
     python tests/run_all.py -j 4        (four files at a time; the files use their own temp folders and ports)
     python tests/run_all.py --tag queue,undo   (files with one of these tags on their first line; mixes with name words)
     python tests/run_all.py --tags      (lists the tags and how many files carry each)
     python tests/run_all.py -j 6 --changed   (the tests of what is not committed yet: importers, tags of the modules)
     python tests/run_all.py -j 6 --changed-day   (the same for everything since next)
PCCOMFY_SLOW_TESTS=1 also runs the slow parts (test_scribble on the real round 6 photos, the full matrix of
test_fill_mask_variants); without it they are skipped or sampled. Only test_*.py files are collected
(tests/selfcheck_*.py and tests/live_*.py are run by hand).
Exit code 0 = all green. The tests use a stubbed Tk and a fake PhotoCraft: the real window and real generations are not covered."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


# Skipped on GitHub's machines only (GITHUB_ACTIONS=true, the install matrix; user 24.11.: "auf CI überspringen"): they
# check sizes to the pixel, which are 1 px off with the fonts there (or no font loads at all), not an install problem.
# Locally they run as always. Details: docs/plan/kleinkram.md.
CI_SKIP = {
    "test_head_chips.py": "chip width 1 px wider with the Fedora/Arch fonts",
    "test_cancel_all.py": "queue row buttons 2 px wider with the Fedora/Arch fonts",
    "test_ui_tweaks_16_11.py": "progress bar exactly half the button height, odd heights there",
    "test_atpick.py": "the Arch container cannot allocate a font",
}


def ci_skipped(files: list[Path], env=os.environ) -> tuple[list[Path], list[str]]:
    """The files to run and the names skipped because the run is on GitHub (see CI_SKIP)."""
    if env.get("GITHUB_ACTIONS") != "true":
        return files, []
    return [p for p in files if p.name not in CI_SKIP], [p.name for p in files if p.name in CI_SKIP]


def child_env(home: str) -> dict:
    """Environment of one test process. PCCOMFY_HOME always points at a throw-away folder: pccomfy.config reads it at import
    time, so a test that imports pccomfy before it sets its own would otherwise use (and could overwrite) the real data/ folder.
    A test that sets its own PCCOMFY_HOME simply overrides this one."""
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PCCOMFY_NO_TIPS": "1", "PCCOMFY_NO_WATCH": "1", "PCCOMFY_NO_UPDATE_CHECK": "1", "PCCOMFY_HOME": home}


def run_one(p: Path) -> tuple[Path, bool, str, float]:
    t0 = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="pccomfy-test-home-") as home:
            # UTF-8 both ways: on Windows the console code page cannot hold the tests' "·" and "→"
            r = subprocess.run([sys.executable, "-B", str(p)], cwd=ROOT, capture_output=True, text=True, timeout=300,
                               encoding="utf-8", errors="replace", env=child_env(home))
        ok, out = r.returncode == 0, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        ok, out = False, "timeout after 300 s"
    return p, ok, out, time.monotonic() - t0


TIMES_FILE = Path(tempfile.gettempdir()) / "pccomfy-test-times.json"     # outside the repo and data/ (tempo plan T1, 24.11.)


def load_times(path: Path = TIMES_FILE) -> dict[str, float]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_times(new: dict[str, float], path: Path = TIMES_FILE) -> None:
    try:
        path.write_text(json.dumps({**load_times(path), **new}, indent=0, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def start_order(files: list[Path], times: dict[str, float]) -> list[Path]:
    """The slowest files of the last run start first, so the long ones do not start at the end and make the whole run wait
    (tempo plan T1, 24.11.). A file without a time (new) counts as slow. Same files, only another order."""
    return sorted(files, key=lambda p: (-times.get(p.name, float("inf")), p.name))


TAGS = {       # the topic tags of the first line "# tags: a, b" of every test file (user 24.11.: "Tag your tests")
    "window": "the Tk window: layout, look, fonts, scale, menus, head",
    "settings": "the gear window: Model Links, Other settings, downloads, settings.json",
    "start": "start values, factory and own startup settings",
    "queue": "runs one after another: job queue, batch, Generate queue, Cancel, progress, history",
    "undo": "Undo / Redo and history snapshots",
    "comfy": "the ComfyUI client: address, dot, connections, websocket, live preview, its folder",
    "photocraft": "the PhotoCraft link: commands, layers, clipboard, window linking, Quick Mask",
    "models": "manifest, models.json, inventory, variants, optional files, downloads",
    "workflows": "the ComfyUI graphs in workflows/ and how the bridge fills them",
    "prompt": "the prompt field, the prompt writer, custom prompts",
    "styles": "styles.json, the style picker and the styles overview",
    "mask": "selection, layer masks, feather, mask density, BBOX",
    "save": "Save image",
    "t2i": "Text to image", "edit": "Edit canvas", "multiedit": "Multi image edit and reference slots",
    "fill": "Fill selection", "expand": "Expand", "remove": "Remove", "upscale": "Upscale", "refine": "Refine",
    "sketch": "Sketch to image and the Scribble tabs",
    "qwen": "Qwen Image 2.1", "flux2": "Flux 2", "flux3": "Flux 3", "fibo": "Fibo", "moss": "MOSS", "minimax": "MiniMax H3",
    "linux": "the Linux side",
    "release": "README, setup scripts, install matrix, export, app name, update check",
    "tools": "tools/ scripts, the test runner and the test guards",
}


MODULE_TAGS = {   # every module of pccomfy/ and the tags of the tests that cover it (--changed; test_test_tags checks it, 24.11.)
    "__init__": ["tools"], "__main__": ["release", "photocraft"], "appinfo": ["release"], "appname": ["release"],
    "atpick": ["prompt", "multiedit"], "bridge": ["workflows", "photocraft", "queue"], "bridge_tools": ["mask", "multiedit", "prompt"],
    "clipboard": ["photocraft"], "comfy": ["comfy", "queue"], "comfyaddr": ["comfy"], "comfydir": ["comfy", "linux"],
    "config": ["start", "settings"], "custom_prompts": ["prompt"], "downloads": ["models"], "fillmask": ["mask", "fill"],
    "fonts": ["window"], "gui": ["window"], "gui_batch": ["queue"], "gui_common": ["window"], "gui_lora": ["window", "workflows"],
    "gui_modes": ["window", "start"], "gui_prompt": ["prompt", "styles"], "gui_queuewin": ["queue"], "gui_run": ["queue", "undo"],
    "gui_state": ["window", "comfy"], "gui_theme": ["window"], "gui_tips": ["window"], "history": ["queue", "undo"],
    "hostos": ["linux", "save"], "icons": ["window"], "imaging": ["mask", "photocraft"], "inventory": ["models", "settings"],
    "jobqueue": ["queue"], "launcher": ["release", "photocraft"], "linkpicker": ["settings"], "listpopup": ["settings", "window"],
    "manifest": ["models"], "models": ["models", "start"], "namematch": ["settings"], "photocraft": ["photocraft"],
    "popmenu": ["window"], "portowner": ["photocraft"], "refslots": ["multiedit"], "savefile": ["save"], "scribble": ["sketch"],
    "spacing": ["window"], "startlog": ["window"], "sthead": ["settings"], "stylegrid": ["styles"], "styles": ["styles"],
    "testguard": ["tools"], "tips": ["window"], "ui_downloads": ["settings", "models"], "ui_other_settings": ["settings", "comfy"],
    "ui_settings": ["settings"], "ui_settings_data": ["settings", "models"], "ui_update": ["release"], "uiscale": ["window", "linux"],
    "update": ["release"], "variants": ["models"], "winlink": ["photocraft"], "workflows": ["workflows"],
    "x11clip": ["photocraft", "linux"], "x11link": ["photocraft", "linux"],
}
PATH_TAGS = {"workflows/": ["workflows"], ".github/": ["release"], "setup-": ["release"], "README": ["release"],
             "pccomfy/models.json": ["models"], "pccomfy/styles": ["styles"], "tests/run_all.py": ["tools"]}


def changed_files(base: str = "HEAD") -> list[str]:
    """Files changed since `base` (HEAD: what is not committed yet; next: the whole day branch), staged, unstaged and new
    (git-ignored ones and the personal todo*.md left out)."""
    def git(*a: str) -> list[str]:
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return [line.strip() for line in r.stdout.splitlines() if line.strip()] if r.returncode == 0 else []
    fork = (git("merge-base", base, "HEAD") or ["HEAD"])[0]
    names = git("diff", "--name-only", fork) + git("ls-files", "--others", "--exclude-standard")
    return sorted({n for n in names if not Path(n).name.lower().startswith("todo")})


def imported_modules(text: str) -> set[str]:
    """pccomfy modules a test names: `pccomfy.x`, `from pccomfy import a, b as c` (also in brackets over several lines)."""
    mods = set(re.findall(r"pccomfy\.(\w+)", text))
    for in_brackets, one_line in re.findall(r"from pccomfy import (?:\(([^)]*)\)|([^\n#]*))", text):
        group = re.sub(r"#[^\n]*", "", in_brackets or one_line)
        mods |= {part.split()[0] for part in group.replace("\n", " ").split(",") if part.split()}
    return mods


def changed_selection(changed: list[str], files: list[Path]) -> tuple[list[Path], list[str]]:
    """The tests of a change (choice A, 24.11.): changed test files, tests that import a changed module, tests that name
    a changed tool or data file, and every test with a tag of the changed modules. Returns (files, tags used)."""
    tags: set[str] = set()
    hit: set[Path] = set()
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in files}
    for name in changed:
        path = Path(name)
        for prefix, ts in PATH_TAGS.items():
            if name.startswith(prefix):
                tags |= set(ts)
        if name.startswith("tests/") and path.name.startswith("test_"):
            hit |= {p for p in files if p.name == path.name}
        elif name.startswith("pccomfy/") and path.suffix == ".py":
            tags |= set(MODULE_TAGS.get(path.stem, []))
            hit |= {p for p, t in texts.items() if path.stem in imported_modules(t)}
        elif name.startswith(("tools/", "tests/", "pccomfy/")):
            hit |= {p for p, t in texts.items() if re.search(rf"\b{re.escape(path.stem)}\b", t)}
    hit |= {p for p in files if tags & set(tags_of(p))}
    return sorted(hit), sorted(tags)


def tags_of(p: Path) -> list[str]:
    """The tags on the first line of a test file ("# tags: window, queue"); [] when the line is missing."""
    try:
        with p.open(encoding="utf-8") as f:
            line = f.readline()
    except OSError:
        return []
    if not line.startswith("# tags:"):
        return []
    return [t.strip() for t in line[len("# tags:"):].split(",") if t.strip()]


def pick(files: list[Path], words: list[str], tags: list[str]) -> list[Path]:
    """Files whose name contains one of the words OR that carry one of the tags; everything when neither is given."""
    if not words and not tags:
        return sorted(files)
    return sorted(p for p in files if any(w in p.name for w in words) or set(tags) & set(tags_of(p)))


def main(args: list[str]) -> int:
    jobs = 1
    if "-j" in args:
        i = args.index("-j")
        jobs = max(1, int(args[i + 1]))
        del args[i:i + 2]
    if "--tags" in args:
        all_files = list(HERE.glob("test_*.py"))
        for t, what in TAGS.items():
            print(f"{t:<11} {sum(t in tags_of(p) for p in all_files):3} files  {what}")
        return 0
    tags: list[str] = []
    while "--tag" in args:
        i = args.index("--tag")
        tags += [t.strip() for t in args[i + 1].split(",") if t.strip()]
        del args[i:i + 2]
    unknown = [t for t in tags if t not in TAGS]
    if unknown:
        print("Unknown tag:", ", ".join(unknown), "(python tests/run_all.py --tags lists them)")
        return 2
    if "--changed" in args or "--changed-day" in args:
        since = "next" if "--changed-day" in args else "HEAD"
        args = [a for a in args if a not in ("--changed", "--changed-day")]
        changed = changed_files(since)
        all_files = list(HERE.glob("test_*.py"))
        files, used = changed_selection(changed, all_files)
        if args or tags:                                        # name words and --tag add to the selection
            files = sorted(set(files) | set(pick(all_files, args, tags)))
        print(f"changed since {since}: {len(changed)} files, tags {', '.join(used) or '-'} -> {len(files)} test files")
        if not files:
            print(f"No code changed since {since}: nothing to test.")
            return 0
    else:
        files = pick(list(HERE.glob("test_*.py")), args, tags)
    if not files:
        print("No test file matches:", " ".join(args + tags))
        return 2
    files, skipped = ci_skipped(files)
    for name in skipped:
        print(f"skip {name:<34} on GitHub: {CI_SKIP[name]}")
    failed = []
    secs_of: dict[str, float] = {}
    t_all = time.monotonic()
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {p: pool.submit(run_one, p) for p in start_order(files, load_times())}
        for p in files:                                         # results are printed in file order
            _p, ok, out, secs = futures[p].result()
            secs_of[p.name] = round(secs, 1)
            print(f"{'ok  ' if ok else 'FAIL'} {p.name:<34} {secs:5.1f} s")
            if not ok:
                failed.append(p.name)
                print("     " + "\n     ".join(out.strip().splitlines()[-12:]))
    save_times(secs_of)
    print(f"\n{len(files) - len(failed)} of {len(files)} test files green in {time.monotonic() - t_all:.0f} s"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
