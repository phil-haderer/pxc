"""Custom prompts (the Prompt-Saver, docs/prompt-saver-konzept.md): texts of the prompt field kept under a name. One list for
every function and model; each entry also remembers the model and function it was saved for: shown in the menu, and "Use" goes back to them (model,
function and tab, user 15.11.). No Tk.

The file is data/custom_prompts.json (PCCOMFY_HOME respected, on Linux the folder of the other user data): a list of
{"name", "text", "model", "function", "model_key", "mode", "tab"} (the last three since 15.11.: the keys behind
the two labels and the tab under Edit or Fill; older entries have none). A file that cannot be read is renamed to custom_prompts.json.bad, never lost."""
from __future__ import annotations

import json
from pathlib import Path

from . import config as cfgmod

MAX_ENTRIES = 100
MAX_NAME = 40
EMPTY_LABEL = "No saved prompts yet"
CONTEXT_KEYS = ("model_key", "mode", "tab")    # what "Use" switches back to (user 15.11.)
_LOAD_NOTE = ""         # set by load() when it had to rename a broken file ("" = all fine)


def path() -> Path:
    return cfgmod.CONFIG_DIR / "custom_prompts.json"


def load_note() -> str:
    """The message of the last load() that found a broken file, else ""; the window shows it in the status line once."""
    return _LOAD_NOTE


def clear_note() -> None:
    global _LOAD_NOTE
    _LOAD_NOTE = ""


def _clean(entry) -> dict | None:
    if not isinstance(entry, dict):
        return None
    name, text = entry.get("name"), entry.get("text")
    if not isinstance(name, str) or not isinstance(text, str) or not name.strip():
        return None
    out = {"name": name.strip()[:MAX_NAME], "text": text,
           "model": str(entry.get("model") or ""), "function": str(entry.get("function") or "")}
    for k in CONTEXT_KEYS:
        out[k] = str(entry.get(k) or "")
    return out


def load() -> list[dict]:
    """The saved prompts. A missing file is an empty list; a broken one is renamed to .bad and the note is set."""
    global _LOAD_NOTE
    p = path()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("not a list")
    except ValueError:
        bad = p.with_name(p.name + ".bad")
        try:
            if bad.exists():
                bad.unlink()
            p.replace(bad)
            _LOAD_NOTE = f"{p.name} was damaged and is kept as {bad.name}; your saved prompts start empty."
        except OSError:
            _LOAD_NOTE = f"{p.name} is damaged and could not be moved aside; your saved prompts start empty."
        return []
    out: list[dict] = []
    for e in data:
        c = _clean(e)
        if c and find(out, c["name"]) < 0:
            out.append(c)
    return out[:MAX_ENTRIES]


def save(entries: list[dict]) -> bool:
    """Writes the list; False when the folder is not writable."""
    p = path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(entries[:MAX_ENTRIES], indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def same_name(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def find(entries: list[dict], name: str) -> int:
    """Index of the entry with this name (case-insensitive), -1 for none."""
    for i, e in enumerate(entries):
        if same_name(e["name"], name):
            return i
    return -1


def add(entries: list[dict], name: str, text: str, model: str = "", function: str = "", replace: bool = False,
        context: dict | None = None) -> str:
    """Adds an entry in place; `context` holds the keys of CONTEXT_KEYS (model_key, mode, tab). Returns "" when done, "name" (empty name), "text" (empty text), "exists" (name taken and
    replace is False) or "full" (100 entries)."""
    name = name.strip()[:MAX_NAME].strip()
    if not name:
        return "name"
    if not text.strip():
        return "text"
    i = find(entries, name)
    if i >= 0:
        if not replace:
            return "exists"
        entries[i] = _entry(name, text, model, function, context)
        return ""
    if len(entries) >= MAX_ENTRIES:
        return "full"
    entries.append(_entry(name, text, model, function, context))
    return ""


def _entry(name: str, text: str, model: str, function: str, context: dict | None) -> dict:
    e = {"name": name, "text": text, "model": model, "function": function}
    for k in CONTEXT_KEYS:
        e[k] = str((context or {}).get(k) or "")
    return e


def edit(entries: list[dict], index: int, name: str, text: str, replace: bool = False) -> str:
    """Changes entry `index` (name and text; model and function stay). Same return values as add(); another entry that
    already has the new name makes it "exists" unless replace is True (that other entry is then removed)."""
    name = name.strip()[:MAX_NAME].strip()
    if not name:
        return "name"
    if not text.strip():
        return "text"
    other = find(entries, name)
    if other >= 0 and other != index:
        if not replace:
            return "exists"
        entries[index].update(name=name, text=text)
        del entries[other]
        return ""
    entries[index].update(name=name, text=text)
    return ""


def delete(entries: list[dict], index: int) -> None:
    if 0 <= index < len(entries):
        del entries[index]


def label(entry: dict) -> str:
    """The menu label, function first, then model, then the name: "[Edit canvas · Flux 3 Klein] Summer meadow" (user 12.11.; the tag
    is left out when nothing was remembered)."""
    tag = " · ".join(x for x in (entry.get("function", ""), entry.get("model", "")) if x)
    return f"[{tag}] {entry['name']}" if tag else entry["name"]


def context(entry: dict, model_labels: dict, mode_labels: dict) -> dict:
    """{"model_key", "mode", "tab"} of an entry; an older one (saved before 15.11.) gets them from its two labels, as far as they
    tell (`model_labels`: label -> model key, `mode_labels`: function label -> mode; "" where a label tells nothing)."""
    out = {k: entry.get(k, "") or "" for k in CONTEXT_KEYS}
    if not out["model_key"]:
        out["model_key"] = model_labels.get(entry.get("model", ""), "")
    if not out["mode"]:
        out["mode"] = mode_labels.get(entry.get("function", ""), "")
    return out
