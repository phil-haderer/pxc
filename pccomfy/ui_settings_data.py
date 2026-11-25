"""The "Models" page of the settings window as plain data (no Tk; moved out of ui_settings.py unchanged, tempo plan S2,
24.11.): the rows of each model (links, mode tiles, Required / Optional files, "Used by several models"), and the hints of
the chain list ("Probably right", "Similar name", "same size and header as", "incomplete?"). SettingsMixin inherits
SettingsDataMixin; ui_settings.py draws the rows.

The names of ui_settings.py these methods use are imported at the end of this file: ui_settings.py imports this module just
before its class SettingsMixin, so the class must already stand here then (the methods look the names up only when they run)."""
from __future__ import annotations

import difflib
from pathlib import Path

from . import comfydir, inventory, manifest, namematch, sthead
from .gui_common import *  # noqa: F401,F403
from .gui_common import __all__ as _ALL  # noqa: F401
from .ui_downloads import browser_only, site_hint, size_text


class SettingsDataMixin:
    # ---------- the overlay: content as plain data (tested without Tk) ----------

    def _settings_rows(self) -> list[tuple]:
        """The "Models" tab as rows (kind, data), drawn by _settings_draw; no Tk here. Kinds (user 19.11.): "links" (the top row:
        Undo and Reset; no count, choice A), "error" (text, detail), "model" (key, label, state, focus, can be shown), "modes" (key, cover),
        "download" (key, what is missing), "file" (a dict, see below), "gguf" (url), "node" (class, pack, url), "head" (text),
        "stop" (file names). A file row: expected name, path with its folder ("/vae/flux2-vae.safetensors"), kind, found (your
        file's name or None), linked, level (required / optional), size text, download url, found on disk (a path or "")."""
        self._fill_ctx = {"extra": {}, "disk": {}, "cands": {}}      # models folder, yaml, disk files, candidates: once per fill
        try:
            return self._settings_rows_now()
        finally:
            self._fill_ctx = None

    def _settings_rows_now(self) -> list[tuple]:
        rows: list[tuple] = []
        links = cfgmod.model_map()
        if self._fill_ctx is not None:
            self._fill_ctx["links"] = links
        # the top row: how many files are linked, with Undo and Reset (user 19.11.: no intro text and no list; a linked file is
        # blue in its own field)
        rows.append(("links", len(links)))      # no "N files linked" (user 19.11., choice A: it read as wrong; a linked file is blue)
        if self.inv is None:
            rows.append(("error", "ComfyUI could not be read.", (self._inv_error or "Not connected yet.")
                         + "\nStart ComfyUI, then click the refresh arrow (⟳) at the bottom of PxC."))
            rows += [("model", m.key, m.label, "", False, True) for m in models.PICK_ORDER]      # only "Show in PxC" (no mark, no state)
        else:
            for row in self.inv.rows():
                miss = [f for f, found, lv in row["files"] if found is None and f.url and not self._dl_done(f)]      # every file of the package (user 3.11.)
                direct = [f for f in miss if not browser_only(f)]
                # the head: mark, name, state and "Show in PxC" in one line (user 19.11.); the last value: can it be shown
                rows.append(("model", row["key"], row["label"], row["status"].state, row["key"] == self._settings_focus,
                             row["status"].state != "missing"))
                rows.append(("modes", row["key"], self._mode_cover(row["key"])))      # small tiles (user 19.11.)
                if miss:      # the one blue button of the page (user 19.11.)
                    rows.append(("download", row["key"], {"count": len(direct), "site": len(miss) - len(direct),
                                                          "size": size_text(sum(f.size for f in direct))}))
                needed = [x for x in row["files"] if x[2] == "required"]
                extra = [x for x in row["files"] if x[2] != "required"]
                rows.append(("head", REQUIRED_HEAD))
                last_unet = max((i for i, x in enumerate(needed) if x[0].kind == "unet"), default=-1)
                for i, (f, found, level) in enumerate(needed):
                    rows.append(("file", self._file_data(f, found, level)))
                    if i == last_unet and row["key"] in manifest.GGUF_PAGES:      # under the main model's weights (user 5.11.)
                        rows.append(("gguf", manifest.GGUF_PAGES[row["key"]]))
                for c in row["status"].nodes:
                    pack = manifest.node_pack(c)
                    rows.append(("node", c, pack[0] if pack else "", pack[1] if pack else ""))
                if extra:       # the files of the extra features, apart from the ones the standard settings need (user 2.11.)
                    rows.append(("head", OPTIONAL_HEAD))
                    for f, found, level in extra:      # what each file is for, in brackets after it (user 16.11.)
                        rows.append(("file", {**self._file_data(f, found, level), "feature": manifest.feature_use(row["key"], f.name)}))
                rows.append(("stop", [f.name for f, _fd, _lv in row["files"]]))
            rows.append(("head", ADDITIONAL_HEAD))
            add_names = []
            for f, found, use, keys in self.inv.additional_rows():
                add_names.append(f.name)
                rows.append(("file", {**self._file_data(f, found, "optional"),
                                      "use": manifest.ADDITIONAL_USE.get(f.name) or f"{use}: " + ", ".join(models.SHORT[k] for k in keys)}))
            rows.append(("stop", add_names))
        return rows

    def _mode_cover(self, key: str) -> list[tuple]:
        """The functions a model covers: (mode key, label, state, tooltip); state ready / missing (a file or node is missing) /
        none (the model does not offer it). Named as in the main window (user 19.11.): the tab "Edit canvas" for the whole-picture
        edit, and the two tabs that are no mode of their own: "Insert reference" (Flux 3, under Fill; runs as Multi image edit)
        and "Scribble with reference" (runs as Scribble on photo)."""
        m = models.BY_KEY[key]
        names = {"edit": "Edit canvas", "multi_edit": "Multi image edit"}      # the tab names under the prompt
        extra = {"inpaint": ("bbox", "Insert reference", "multi_edit", bool(m.bbox)),
                 "scribble": ("refscribble", models.REF_SCRIBBLE_LABEL, "scribble", "scribble" in m.modes and models.offers_ref_scribble(m))}
        out = []

        def add(mode, label, status_of, offered):
            if not offered:
                out.append((mode, label, "none", "This model does not offer this function."))
                return
            st = self.inv.mode_status(key, status_of) if self.inv is not None else None
            if st is None or st.state == "ready":
                out.append((mode, label, "ready", "Ready."))
            else:
                need = [f.name for f in st.missing] + list(st.nodes)
                out.append((mode, label, "missing", "Missing: " + ", ".join(need[:3]) + (" ..." if len(need) > 3 else "")))

        for mode, label in MODE_LABELS:           # noqa: F405
            if mode == "img2img":
                continue
            add(mode, names.get(mode, label), mode, mode in m.modes)
            if mode in extra:
                add(*extra[mode])
        return out

    def _file_data(self, f, found, level) -> dict:
        """One file row: expected name, path, found (your file's name or None), level, size, url, note, the download state
        (see DownloadMixin._dl_info), "restart" (loaded, ComfyUI does not list it yet) and "browser" (its page opens instead)."""
        probable = self._probable_file(f) if found is None else ""
        ctx = getattr(self, "_fill_ctx", None)
        links = ctx["links"] if (ctx and "links" in ctx) else cfgmod.model_map()
        return {"name": f.name, "path": file_path(f), "found": found, "level": level, "size": f.size_text, "url": f.url,
                "kind": manifest.KIND_LABEL.get(f.kind, f.kind), "linked": f.name in links,      # the field of the file (user 19.11.)
                "dl": self._dl_info(f.name),        # no note of models.json under a file (user 16.11. evening; before: no licence, 2.11.)
                "restart": found is None and f.name in self._dl_restart, "browser": browser_only(f) if f.url else False,
                "hint": site_hint(f) if (found is None and f.url and browser_only(f)) else "",
                "other": found is not None and self._is_other_file(f, found),
                "probable": probable,
                "similar": self._similar_file(f) if (found is None and not probable) else ""}

    def _probable_file(self, f) -> str:
        """A file ComfyUI lists under another name that is the missing ``f`` (same size, complete safetensors header), or "".
        Needs the models folder (not asked for here) and, for a file that was just renamed, a ComfyUI restart."""
        base = self.models_dir(ask=False) if f.size else None
        if base is None:
            return ""
        same = []
        for n in self._link_candidates(f.name):
            p = self._disk_file(f, n)
            if p is not None and p.stat().st_size == f.size:
                same.append(n)
        hints = self._link_hints(f.name, same)
        return next((n for n in same if hints.get(n) == HINT_SAME + f.name), "")

    def _similar_file(self, f) -> str:
        """A file ComfyUI lists whose NAME is like the missing ``f`` (same model in another precision or spelling: namematch.py), or "".
        Files the plugin itself knows (another entry of models.json) are no stand-ins. A hint only; a renamed copy found by size
        and header (``_probable_file``) is named first and wins (the caller asks only when there is none)."""
        known = [g.name for g in manifest.FILES.values() if g.name != f.name]
        return namematch.suggest(f.name, self._link_candidates(f.name), known)

    @staticmethod
    def _is_other_file(f, found: str) -> bool:
        """Show "your file: ..." when ComfyUI's file is not the expected one by name, folder included (user 7.11.: a tester's file in
        ``flux/`` was found but looked missing; before, a main diffusion model in another folder was left out). Only case and the
        kind of slash do not count."""
        return inventory.norm(found) != inventory.norm(f.name)

    def _link_candidates(self, expected: str) -> list[str]:
        """The files ComfyUI lists for the kind of ``expected`` that can stand in for it (itself left out), the ones with a
        name most like it first. ComfyUI's own list: it knows its folders, the default one, the extra ones and links."""
        f = manifest.FILES.get(expected)
        if f is None or self.inv is None:
            return []
        ctx = getattr(self, "_fill_ctx", None)
        if ctx is not None and expected in ctx["cands"]:
            return list(ctx["cands"][expected])
        avail = list(self.inv.lists.get(f.kind, []))
        own = inventory.resolve(f.name, avail, None, f.aliases)
        base = lambda n: n.replace("\\", "/").rpartition("/")[2].lower()      # noqa: E731
        out = sorted((n for n in avail if n != own),
                     key=lambda n: -difflib.SequenceMatcher(None, base(n), base(f.name)).ratio())
        if ctx is not None:
            ctx["cands"][expected] = out
        return list(out)

    def _disk_file(self, f, name: str):
        """The path on disk of ``name`` (as ComfyUI lists it) for the kind of ``f``: in ComfyUI's models folder or in one of the extra
        folders of its extra_model_paths.yaml; None when it is in none of them."""
        base = self.models_dir(ask=False)
        if base is None:
            return None
        ctx = getattr(self, "_fill_ctx", None)
        if ctx is not None and (f.folder, name) in ctx["disk"]:
            return ctx["disk"][f.folder, name]
        if ctx is not None:
            if f.folder not in ctx["extra"]:          # extra_model_paths.yaml: read once per folder and fill
                ctx["extra"][f.folder] = comfydir.extra_model_dirs(base, f.folder)
            dirs = [Path(base) / f.folder, *ctx["extra"][f.folder]]
        else:
            dirs = [Path(base) / f.folder, *comfydir.extra_model_dirs(base, f.folder)]
        rel, found = name.replace("\\", "/"), None
        for d in dirs:
            try:
                if (d / rel).is_file():
                    found = d / rel
                    break
            except OSError:
                continue
        if ctx is not None:
            ctx["disk"][f.folder, name] = found
        return found

    def _link_hints(self, expected: str, cands: list[str]) -> dict[str, str]:
        """For the files of the chain list: "same size and header as <file>" when the file's size and its safetensors header match a file of
        the manifest (a renamed copy; for the expected file itself it names <expected>), "incomplete? ..." when the header promises
        more bytes than the file has. Files in the extra folders of extra_model_paths.yaml count too."""
        f = manifest.FILES.get(expected)
        base = self.models_dir(ask=False) if f is not None else None
        if base is None:
            return {}
        by_size = {g.size: g.name for g in manifest.FILES.values() if g.kind == f.kind and g.size}
        out: dict[str, str] = {}
        for n in cands:
            p = self._disk_file(f, n)
            if p is None:
                continue
            size = p.stat().st_size
            head = sthead.read_header(p)
            if head is None:
                continue
            if not sthead.is_complete(p):
                out[n] = HINT_INCOMPLETE
            elif size in by_size:
                out[n] = HINT_SAME + by_size[size]
        return out

    @staticmethod
    def _menu_hints(expected: str, hints: dict[str, str]) -> dict[str, str]:
        """The hints shown in the chain list: "same size and header as <file>" only for a file that equals ANOTHER file of the manifest
        than the expected one (a warning against mixing them up); a copy of the expected file is already named under the missing
        file ("This is probably the right file"). "incomplete?" always stays (user 6.11.)."""
        return {n: h for n, h in hints.items() if h != HINT_SAME + expected}


from .ui_settings import (ADDITIONAL_HEAD, HINT_INCOMPLETE, HINT_SAME, OPTIONAL_HEAD, REQUIRED_HEAD,  # noqa: E402
                          file_path)
