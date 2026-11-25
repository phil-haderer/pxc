"""The jobs of the Bridge beside a run (moved out of bridge.py unchanged, tempo plan S3, 24.11.): the feather preview in
Quick Mask mode, the cut-out of the background (reference slots and the scissors in the footer) and the descriptions by the
text model (LLM button, Describe, the slot tools). Bridge inherits them from BridgeToolsMixin.

The names of bridge.py these methods use are imported at the end of this file: bridge.py imports this module just before its
class Bridge, so the class must already stand here when that happens (the methods look the names up only when they run)."""
from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path

from PIL import Image

from . import imaging, models, refslots, workflows
from .comfy import ComfyUI
from .photocraft import PhotoCraft, PhotoCraftError


class BridgeToolsMixin:
    # ---------- feather preview ----------

    @property
    def feather_shown(self) -> bool:
        return self._preview is not None

    def show_feather(self, req: Request) -> str:
        """Feather preview: the layer mask the next run would give its result (the same computation), shown in PhotoCraft
        in Quick Mask mode: red where the picture stays, the soft edge as a gradient. The user's selection is saved in a
        channel first and comes back with hide_feather (also at the start of the next run). Called again while it is
        shown (the slider moved), it only computes the mask anew: no second export."""
        pc = self.pc.connect()
        if req.mode == "remove":
            req = dataclasses.replace(req, mode="inpaint", remove=True)
        sess = pc.session()
        orig = sess.get("active")
        if orig is None:
            raise BridgeError("Open a document in PhotoCraft first.")
        name = sess["documents"][orig]["name"]
        if self._preview and (self._preview["doc"], self._preview.get("index")) != (name, orig):
            self.hide_feather()      # another document is active now (two may share a name): end the old preview
        tag = uuid.uuid4().hex[:8]
        try:
            if self._preview:
                mask = self._preview["mask"]
                pc.execute("select.editInQuickMaskMode", {"on": False})
            else:
                quick = self._quick_mask_off()      # the user's own Quick Mask: off first, else the check sees no selection
                if not pc.document().get("hasSelection"):
                    raise BridgeError(QUICK_MASK_NO_SELECTION if quick else
                                      "Select an area first: the preview shows the soft edge the result gets there.")
                _, mask = self._export(orig, tag, need_mask=True)
                if imaging.mask_bbox(mask) is None:
                    raise BridgeError("The selection is empty.")
                channel = f"pccomfy-preview-{tag}"
                pc.execute("select.saveSelection", {"name": channel})
                self._preview = {"doc": name, "index": orig, "channel": channel, "mask": mask}
            W, H = mask.size
            bbox = imaging.mask_bbox(mask)
            region = imaging.grow_box(bbox, (W, H), req.context) if req.mode in ("inpaint", "outpaint") else bbox
            wf_paths = workflows.resolve(req.workflow) if req.workflow else [None]
            lm_mode = effective_layer_mask(req.layer_mask, req.mode, is_editor(wf_paths), True)
            if req.bbox and req.mode == "edit":      # BBOX: the result is the whole canvas, the box (grown) is where it counts
                region = imaging.Box(0, 0, W, H)
                if lm_mode == "soft":
                    shown = imaging.box_margin_mask(bbox, (W, H), BBOX_MARGIN, req.feather_pct, outside=True)
                elif lm_mode == "selection":
                    shown = mask
                else:
                    shown = Image.new("L", (W, H), 255)
            elif lm_mode == "soft" and req.fill_box and req.mode == "inpaint":    # Flux 3 Fill: the box plus a margin
                shown = imaging.box_margin_mask(bbox, (W, H), BBOX_MARGIN, req.feather_pct).crop(region.pil())
            elif lm_mode == "soft":
                shown = soft_layer_mask(req, wf_paths, mask, region, bbox)
            elif lm_mode == "selection":
                shown = mask.crop(region.pil())
            else:   # no layer mask: the result covers its whole rectangle
                shown = Image.new("L", (region.w, region.h), 255)
            helper_im = Image.new("RGBA", shown.size, (255, 255, 255, 0))
            helper_im.putalpha(shown.convert("L"))
            active = pc.document().get("activeLayer")
            helper = self._place_png(orig, helper_im, region, tag, "feather")
            try:
                pc.execute("select.loadSelection", {"channel": "transparency", "layer": helper})
            finally:
                self._try("layer.delete", {"layer": helper})
                if active is not None:
                    self._try("layer.select", {"layer": active})
            pc.execute("select.editInQuickMaskMode", {"on": True})
        except Exception:
            if self._preview:   # never leave the user with a changed selection
                try:
                    self.hide_feather()
                except (BridgeError, PhotoCraftError):
                    pass
            raise
        finally:
            self._cleanup()
        what = {"soft": "Soft edge", "selection": "Hard edge (layer mask: hard)", "none": "No layer mask: the whole rectangle"}
        return f"{what.get(lm_mode, 'Edge')} shown in red in PhotoCraft. Hide feather or Generate brings your selection back."

    def hide_feather(self) -> str:
        """End the feather preview: Quick Mask off, the user's selection back from its channel, the channel deleted. The
        document that is active stays active."""
        prev, self._preview = self._preview, None
        if not prev:
            return ""
        pc = self.pc.connect()
        sess = pc.session()
        current = sess.get("active")
        # the document by its place first, then by name; several open documents may share a name ("Untitled-1"):
        # the one that really holds the saved selection is it (live finding 28.10.: the first one was taken, the run
        # broke off and the saved selection stayed behind as a channel)
        same = [d["index"] for d in sess.get("documents", []) if d["name"] == prev["doc"]]
        order = ([prev["index"]] if prev.get("index") in same else []) + [i for i in same if i != prev.get("index")]
        doc = None
        for i in order:
            if i != current:
                pc.activate(i)
            try:
                names = [c.get("name") for c in pc.document().get("channels", {}).get("alpha", []) if isinstance(c, dict)]
            except (PhotoCraftError, AttributeError, TypeError):
                names = []
            if prev["channel"] in names:
                doc = i
                break
            if i != current:
                pc.activate(current)
        if doc is None:
            return "Feather preview ended (its document was closed)."
        try:
            self._try("select.editInQuickMaskMode", {"on": False})
            try:
                pc.execute("select.loadSelection", {"channel": prev["channel"]})
            except PhotoCraftError as e:
                raise BridgeError(f"Could not bring your selection back (channel {prev['channel']}): {e}") from None
            self._try("channel.delete", {"channel": prev["channel"]})
        finally:
            if current is not None and doc != current:
                pc.activate(current)
        return "Feather preview off: your selection is back."

    # ---------- cut-out (reference slots) ----------

    def remove_background(self, im: Image.Image, progress: Progress | None = None, workflow: str | Path | None = None,
                          crop: bool = True, model: str = "birefnet") -> Image.Image:
        """The picture with its background cut away (RGBA), made by ComfyUI's own background-removal nodes (birefnet-remove-bg.json,
        model `birefnet.safetensors`, or rmbg2-remove-bg.json with `rmbg-2.0.safetensors`, both in models/background_removal;
        `model` is a key of workflows.CUTOUT_MODELS, an explicit `workflow` wins). Used by the reference slots: it needs no PhotoCraft.
        The edge colours are cleaned (imaging.defringe: no bright rim from the old background, 6.11.).
        `crop`: the result ends at the subject (slots); the footer's Remove background keeps the full size (crop=False)."""
        progress = progress or (lambda f, m, **kw: None)
        self._cancel.clear()
        wf = Path(workflow) if workflow else workflows.cutout_model(model)[3]
        tpl = workflows.load_template(wf)
        name = self.comfy.upload_image(im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im, f"pcc-{uuid.uuid4().hex[:8]}-cut.png")
        graph, out_node = workflows.apply_template(tpl, workflows.GenParams(), name, None)
        progress(0.1, "Cutting out the background")
        hist = self._queue_wait(graph, wf, progress)
        out = self.comfy.output_images(hist, out_node)[0]
        progress(1.0, "Background removed")
        out = imaging.defringe(out.convert("RGBA"))
        return imaging.crop_to_alpha(out) if crop else out      # the picture ends at the subject's outermost pixels (user 1.11.)

    def remove_background_layer(self, progress: Progress | None = None, models: tuple = ("birefnet",)) -> dict:
        """The scissors in the hamburger menu (user 5.11.): a copy of the visible picture of the active document as a new layer
        on top (full canvas size) whose editable layer mask hides the background (user 17.11.: the cut-out's alpha is the mask,
        made like Fill's soft mask; before it was a transparent RGBA layer). The user's selection is kept (_keep_selection).
        The layers below stay as they are; one snapshot makes Undo possible like after a run. `models`: keys of
        workflows.CUTOUT_MODELS; with several ("Both", 6.11.) one layer per model, the first lowest, each named
        "Background removed (<model>)", all under the one snapshot."""
        progress = progress or (lambda f, m, **kw: None)
        models = tuple(models)
        if not models:
            raise BridgeError("No cut-out model chosen.")
        for key in models:
            workflows.cutout_model(key)       # an unknown key fails before anything is sent
        try:
            pc = self.pc.connect()
            sess = pc.session()
            orig = sess.get("active")
            if orig is None:
                raise BridgeError("Open a document in PhotoCraft first.")
            tag = uuid.uuid4().hex[:8]
            progress(0.02, "Reading the picture", phase="prepare")
            img, _ = self._export(orig, tag, need_mask=False)
            n = len(models)
            cuts = []
            for i, key in enumerate(models):
                _, label, _, _ = workflows.cutout_model(key)

                def part(f, m, i=i, **kw):      # one bar over all models: model i of n
                    progress(min(0.9, (i + f) / n * 0.9), m, **kw)
                cut = self.remove_background(img, part, crop=False, model=key)
                if cut.size != img.size:
                    raise BridgeError(f"The cut-out has another size than the picture ({cut.size} against {img.size}).")
                cuts.append((label, cut))
            progress(0.95, "Placing the layer" if n == 1 else "Placing the layers", phase="place")
            self._snapshot(sess["documents"][orig]["name"])
            above = None        # a group on top would take the copy into itself (see _run): out of it, above it
            try:
                top = pc.document()["layers"][0]
                self._try("layer.select", {"layer": top["id"]})
                above = top["id"] if top.get("kind") == "Group" else None
            except (KeyError, IndexError, TypeError, PhotoCraftError):
                pass
            layers = []
            with self._keep_selection(tag, on=True):     # the mask is made through a selection: the user's comes back afterwards
                for i, (label, cut) in enumerate(cuts):
                    # the layer is the picture as read (no defringe: the mask hides the old background, user 17.11.), the mask its alpha
                    layers.append(self._import(orig, img, imaging.Box(0, 0, img.width, img.height), "soft",
                                               f"Background removed ({label})", tag, i, first=(i == 0),
                                               layer_mask=cut.getchannel("A"),
                                               above=(layers[-1] if layers and above is not None else above)))   # each one above the one before
            progress(1.0, "Background removed", phase="place")
            return {"layer": layers[-1], "layers": layers, "size": list(img.size)}
        except PhotoCraftError as e:
            raise BridgeError(str(e)) from None
        finally:
            self._cleanup()

    def describe_image(self, im: Image.Image, progress: Progress | None = None, question: str = "",
                       workflow: str | Path | None = None, clip: str = "", seed: int | None = None) -> str:
        """What the picture shows, in a sentence or two, written by the text model of describe-image.json (Qwen 3.5 9B reads
        the picture itself; checked live). `question` replaces the workflow's own request. Used by the reference slots.
        Without a seed the model takes its likeliest words (the same picture gives the same text); with one it samples,
        so another seed gives another description."""
        self._cancel.clear()
        return self._describe(im, progress, question, workflow, clip, seed)

    def _describe(self, im: Image.Image, progress: Progress | None = None, question: str = "",
                  workflow: str | Path | None = None, clip: str = "", seed: int | None = None) -> str:
        """describe_image without resetting Cancel (also used inside a run: Remove names the object first)."""
        progress = progress or (lambda f, m, **kw: None)
        wf = Path(workflow) if workflow else workflows.DESCRIBE_WORKFLOW
        tpl = workflows.load_template(wf)
        small = refslots.prepare_image(im, 32, 768)   # a description needs no more pixels (and ~1 s less)
        name = self.comfy.upload_image(small, f"pcc-{uuid.uuid4().hex[:8]}-describe.png")
        graph, _ = workflows.apply_template(tpl, workflows.GenParams(prompt=question.strip(), clip=clip), name, None)
        if seed is not None:
            workflows.text_sampling(graph, seed)
        progress(0.1, "Describing the picture")
        hist = self._queue_wait(graph, wf, progress)
        text = " ".join(self._vgl_text(graph, hist).split())
        if not text:
            raise BridgeError("The text model returned no description.")
        progress(1.0, "Described")
        return text

    def describe_canvas(self, clip: str = "", progress: Progress | None = None) -> str:
        """The "LLM" button: what the active document shows (all visible layers as one picture), in a sentence or two, written
        by the text model file `clip` (empty: the workflow's own)."""
        pc = self.pc.connect()
        orig = pc.session().get("active")
        if orig is None:
            raise BridgeError("Open a document in PhotoCraft first.")
        tag = uuid.uuid4().hex[:8]
        try:
            src, _ = self._export(orig, f"{tag}-describe", need_mask=False)
            return self.describe_image(imaging.to_rgb(src), progress, clip=clip)
        except PhotoCraftError as e:
            raise BridgeError(str(e)) from None
        finally:
            self._cleanup()

    def describe_scene(self, progress: Progress | None = None) -> str:
        """Krea 2 / MOSS Expand (Describe button): the surroundings of the active picture without its main subject, as the
        prompt (SCENE_QUESTION). Only the original is described, not the empty margin: where content_box finds it, else
        where the last Expand of this document put it (its result fills the margin)."""
        pc = self.pc.connect()
        orig = pc.session().get("active")
        if orig is None:
            raise BridgeError("Open a document in PhotoCraft first.")
        tag = uuid.uuid4().hex[:8]
        try:
            src, _ = self._export(orig, f"{tag}-describe", need_mask=False)
            keep = imaging.content_box(src)
            last = self._last_expand
            if keep is None and last and tuple(last["size"]) == src.size:
                keep = last["keep"]
            im = src.crop(keep.pil()) if keep is not None else src
            return self.describe_image(imaging.to_rgb(im), progress, question=SCENE_QUESTION)
        except PhotoCraftError as e:
            raise BridgeError(str(e)) from None
        finally:
            self._cleanup()


from .bridge import (BBOX_MARGIN, QUICK_MASK_NO_SELECTION, SCENE_QUESTION, BridgeError, Progress, Request,  # noqa: E402  (see the module text)
                     effective_layer_mask, is_editor, soft_layer_mask)
