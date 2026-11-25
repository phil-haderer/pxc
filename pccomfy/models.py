"""The models the window offers as tabs, and what each of them can do.

A tab is a model; below it only the modes that work well with it are enabled. Each mode names the workflow that runs it and
the settings it starts with (the same keys a preset saves). What a model can do comes from live tests; see the project
notes ("plugin-erfahrungen"): add a mode here once it has been tried.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PLACEHOLDER = "<DESCRIBE THE IMAGE>"


@dataclass(frozen=True)
class Mode:
    workflow: str
    settings: dict = field(default_factory=dict)
    prompt_hint: str = ""           # what an empty prompt field starts with in this mode
    prompts: tuple = ()             # (label, text, tip): ready-made prompts, shown as radio buttons next to "Prompt"
    prompt_tip: str = ""            # an orange hint under the prompt field in this mode (the field gets an orange frame)
    run_as: str = ""                # the mode the bridge runs when it is another one (Fibo "Refine" runs as a whole-image edit)
    remove_text: bool = False       # Remove Selection: the field stays usable and takes an optional name of the object ("the dog")
    remove_style: str = ""          # Remove with a named object (user 16.11.): "E" = the writer writes the instruction (Flux 3),
                                    # "F" = the typed words in sentence D (Flux 2, Fibo); empty field = the writer names it (bridge)
    describe: bool = False          # Expand with Krea 2 / MOSS: a prompt is required, the Describe button under the field writes one
    steps_tip: str = ""             # the tooltip of the Steps field in this mode ("" = none)
    max_scale: float = 0.0          # Upscale: the largest factor this model is offered for (0 = all four; the others are greyed out)
    stage_row: bool = False         # Upscale: its stages sit in one row between "Upscale factor" and "Refine" (grey while Refine is on)
    fill_box: bool = False          # Fill (Flux 3): the selection is the layout box <obj_1> in the crop, no red mark (bridge.BOX_FILL_PROMPT; Fill round 5)
    ref_scribble: bool = True       # Scribble on photo: the tab "Scribble with reference" is offered (with a tag_style);
                                    # Fibo off (user 15.11.: it does not take poses over)
    scribble_object_mask: bool = False   # Scribble on photo: the layer mask follows the drawn object (scribble.object_mask)
                                    # instead of fading out from the scribble's box; MiniMax (user 21.11.: it draws larger, soft edges)
    fill_object_mask: bool = False  # Fill: the layer mask also covers what the model clearly changed in an area that reaches
                                    # into the selection (scribble.change_mask); Qwen (user 21.11.: it drew larger, the mask cut it off)


@dataclass(frozen=True)
class Model:
    key: str
    label: str
    modes: dict                     # mode key -> Mode (a mode that is not here is greyed out)
    max_refs: int = 0               # Multi Image Edit: how many reference-image slots this model takes (0 = none)
    tag_style: str = ""             # Multi Image Edit: how this model names an image in the prompt; {n} counts from 1 (the picture
                                    # is image 1, the first reference image 2), {i} from 0 ("" = no names)
    requires: tuple = ()            # model detection: the model files this tab needs (file names, as ComfyUI lists them); () = not set yet
    ref_side: int = 1024            # Multi Image Edit: the longest side of a reference image sent to the model (user 4.11.; Flux 3 as its picture)
    bbox: bool = False              # Multi Image Edit: the BBOX switch (the selection becomes <obj_1>, see bridge.BBOX_SENTENCE); Flux 3 only
    seam: str = "off"               # seam correction in Fill / Remove / Expand: "on" always (one corrected layer), "off" never
                                    # (user 29.10.: Fibo on, the others off; the A/B checkbox was removed 1.11., Qwen fixed off)
    preview: str = "taesd"          # live preview method sent with each prompt: "taesd" (the model's TAE file in vae_approx, else
                                    # ComfyUI's latent2rgb colours) or "latent2rgb" (never loads a TAE file)

    def workflows(self) -> list[str]:
        out = []
        for m in self.modes.values():
            if m.workflow not in out:
                out.append(m.workflow)
        return out


_SOFT = {"layer_mask": "soft", "mask_grow": 8, "mask_blur": 8}

# Refine / Upscale (Flux 2 and 3 Klein): the field holds the WHOLE prompt and starts with what the workflow sends by default;
# describing the picture in front of it helps. Flux 2 also offers relight prompts (live tested).
FLUX2_DEFAULT = "A sharp, natural photograph of the same scene: clean detail and texture, true-to-life colors, soft natural light. Keep the composition and colors exactly as they are."
FLUX2_DEFAULT_PREV = "A sharp, natural photograph of the same scene: clean detail and texture, true-to-life colors, soft natural light. Keep the composition, and colors exactly as they are."
FLUX2_DEFAULT_OLD = "A sharp, natural photograph of the same scene: clean detail and texture, true-to-life colors, soft natural light. Keep the composition, people, faces and colors exactly as they are."
# Fibo Upscale (provisional, 6.11.): FLUX2_DEFAULT ("true-to-life colors, soft natural light") coloured an old sepia photo in the first trial;
# this text names no colour or light, only sharpness (docs/tests/fibo-upscale-ergebnis.md; more prompts follow in the next test round)
FIBO_UPSCALE_DEFAULT = "A sharp, high-resolution version of the same photograph: clean detail and texture. Keep the composition, the subjects, the colors and the light exactly as they are."
FLUX3_DEFAULT = "Restore the photo: remove blur, noise and compression artifacts and recover sharp, natural detail, keeping the same composition and colors."
RELIGHT_NEUTRAL = "A crystal-clear, high-fidelity photograph of the subject captured under perfectly neutral, even lighting. The scene utilizes soft global illumination to eliminate harsh shadows and high contrast, resulting in a balanced, flat-field exposure. The white balance is calibrated to 5500K (daylight neutral), ensuring absolutely accurate, true-to-life colors with no warm or cool color casts. Photographed with a Sony A7R V using a 55mm f/8 lens for maximum sharpness from edge to edge and zero distortion. The aesthetic is objective, documentary-style, and ultra-realistic. 8k resolution, clean ISO 100, raw output. Remove watermarks and checkerboard patterns."
# RELIGHT_STUDIO: out of the Flux 2 Refine choice since 22.11. (user: "ja nur bei flux 2 entfernen"); kept in STOCK_PROMPTS
RELIGHT_STUDIO = "Transform the image into a professionally lit studio portrait with soft, diffused lighting. Remove harsh sunlight, strong contrast, and directional shadows."
# Refine Image has ONE prompt per model since 24.11. (user: "alle refines genau einen modus ... keine schalter mehr"; comparison
# data/vergleich-refine-raster.html): Qwen Keep colors, Flux 2 Neutral, Flux 3 Restore (with its LoRA), Fibo and MiniMax FLUX2_DEFAULT
FLUX3_RESTORE = "Restore this old photo: remove scratches, white lines, dust, folds and stains, and bring back sharp facial detail. Keep the people, their faces, their expressions, their poses and the framing exactly unchanged."   # after Pixaroma's "Restore and Colorize" (wording agreed with the user 1.11.)
# Qwen Image 2.1 Upscale and Refine (workflow qwen212KUpscale_v10): the generic prompt of the workflow is the standard setting (user 2.11.: perfect)
QWEN_UPSCALE_DEFAULT = "Enhance this image to high resolution while preserving the original composition, lighting, and atmosphere. Image can be illustration or real photo, keep the original input style."
# Qwen Refine "Keep colors" (prompt B of refine round 3, user 22.11. "Default + Keep colors"): phone photos 5 of 6, old slides
# 4 of 6 keeping 90 % of their colour cast, where Default keeps 80 % (docs/tests/refine-alte-fotos-ergebnis.md)
QWEN_KEEP_COLORS = "A sharper, cleaner version of the same image: clean detail and texture, the same style, composition, colors and light."
FIBO_REFINE = "relight the scene to natural lighting"   # Fibo Refine's old prompt (now FLUX2_DEFAULT, user 28.10.); kept as a stock text
FILL_TIP = "Draw a selection and prompt e.g. “add a red flower”."   # wording from the user (3.11.; "Always hide the layers ..." dropped 17.11.)
QWEN_SMALL = "Small selections don't work well with Qwen."   # user 30.10.: small fills came out shifted (helikopter.psd)
REMOVE_NAME_TIP = "Name what to remove (e.g. “car”)."
REMOVE_PLACEHOLDER = "Name what to remove"   # grey in the empty field, Remove with remove_style (user 16.11.: the longer one was cut off)
REMOVE_AGAIN = "If the first try doesn't work, try removing it a second time."   # idea of the user (28.10.), for all models since 3.11.
REMOVE_TIP = REMOVE_NAME_TIP + " " + REMOVE_AGAIN    # Qwen; Flux 3, Flux 2 and Fibo only REMOVE_AGAIN (the placeholder names it, user 16.11.)
# Multi image edit has no tip under the prompt since 23.11. (user): the @ tip under the slots replaced it (atpick.TIP)
EDIT_TIP = "Example: “Make the person smile.”"   # the same for every model (user 3.11.; wording 21.11.)
# Krea 2 / MOSS Expand (wording chosen by the user 29.10.; A/B test docs/tests/krea-moss-expand-ab.md)
EXPAND_DESCRIBE_TIP = ("This model needs a prompt: describe the surroundings only (place, light, style), not the main subject. "
                       "Describe writes one for you.")
# Upscale has no tip under the prompt since 12.11. (user, after the P8 round): the old advice "Add a short description of
# your image in front of the default prompt" helped nowhere, and with tiles it put objects into tiles
# (docs/tests/p8-upscale-prompt-ergebnis.md: all 7 "object doubled or made up" came with a description)
REFINE_TIP = "Refine Image keeps the size and redraws fine detail."   # Refine, every model (user 3.11.; description advice dropped 12.11.)
T2I_TIP = "A new image is added to the canvas."   # user 3.11.
FLUX3_DEFAULT_OLD = "Restore the photo: remove blur, noise and compression artifacts and recover sharp, natural detail, keeping the same composition, people and colors."
# Sketch (docs/archiv/sketch-plan.md; tab "Sketch" under Edit): the whole prompt stands in the field and can be edited (user 10.11.); the
# user replaces SKETCH_MARK with what the sketch shows. Left in, the bridge turns it into the generic sentence
# (bridge.sketch_text). The wordings are the ones of the blind test rounds 1 to 7 (docs/tests/sketch-ergebnis.md): Photo,
# the animated-film look without "expressive faces" (round 3b) and Scribble on photo (rounds 5 to 7).
SKETCH_MARK = "SUBJECT"     # was "<WHAT IT SHOWS>" until 21.11. (user: "replace ... to SUBJECT", everywhere)
OLD_SKETCH_MARKS = ("<WHAT IT SHOWS>",)   # still read in saved prompts and pages (bridge.sketch_text, the style swap)
SKETCH_PHOTO = ("Turn this sketch of " + SKETCH_MARK + " into a realistic photograph. Keep the composition, the shapes and the "
                "proportions of the drawing exactly. Natural light, real materials, no drawing lines left.")
SKETCH_ILLUSTRATION = ("Turn this sketch of " + SKETCH_MARK + " into a still from a classic hand-drawn animated film: clean "
                       "outlines, soft cel shading, warm colours. Keep the composition and the shapes of the drawing.")
SKETCH_SCRIBBLE = ("Replace the coloured scribbles with " + SKETCH_MARK + ", realistic and matching the light and perspective of "
                   "the photo. Remove every scribble line and keep everything else unchanged.")
SCRIBBLE_LABEL = "Scribble on photo"     # the template that finds the scribble and changes only the place around it (scribble.py)
SKETCH_PROMPTS = (
    ("Photo", SKETCH_PHOTO, "The whole sketch becomes a realistic photograph."),
    ("Illustration", SKETCH_ILLUSTRATION, "The whole sketch becomes a hand-drawn animated-film picture."),
    (SCRIBBLE_LABEL, SKETCH_SCRIBBLE, "Scribbles on a photo become real objects; only the place around them changes."),
)
SCRIBBLE_MODE = "scribble"      # the window mode of the tab Scribble on photo (plan B, 10.11.: its own tab under Edit)
# The two chips of the tab (user 15.11., after the round docs/tests/ref-scribble-ergebnis.md): "Text at scribble" (the text says
# what goes there) and "Reference at scribble" (the picture in the one reference slot goes there). The reference chip's text
# carries {tag}, the model's name of the reference (Model.tag_style, n=2 / i=1; ref_scribble_text); the user types the object
# where REF_MARK stands, left in the run stops with REF_MARK_LEFT. The sentence with the tag goes past the prompt writer and is
# appended to what it wrote (bridge.ref_scribble_split); "It" there becomes "The <typed object>", as in the round.
TEXT_SCRIBBLE_LABEL = "Scribble on photo"      # tab names since the window test of 15.11. (user)
REF_SCRIBBLE_LABEL = "Scribble with reference"
REF_MARK = SKETCH_MARK     # "SUBJECT" like Scribble on photo (user 22.11.); was "<WHAT IS IN THE REFERENCE>" until then
OLD_REF_MARKS = ("<WHAT IS IN THE REFERENCE>",)   # still read in saved prompts (bridge.begin, the stop before a run)
REF_SCRIBBLE = ("Replace the coloured scribbles with " + REF_MARK + ", realistic and matching the light and perspective of the "
                "photo. Remove every scribble line and keep everything else unchanged. It fills the scribbled area and looks like {tag}.")     # the user's sentence (window test 15.11.: Flux 3 and
# Flux 2 "very good" with it and a pose in the object, "the man sitting on a rock")
REF_SCRIBBLE_TIP = ("Put the reference picture into the slot. Replace " + REF_MARK + " with what it shows: “a beagle dog”.")
REF_MARK_LEFT = "Replace " + REF_MARK + " with what the reference picture shows, e.g. “a beagle dog”."
NO_REF_SCRIBBLE = "Scribble with reference needs a reference picture: drop, paste or add one in the slot."
SCRIBBLE_PROMPTS = (
    (TEXT_SCRIBBLE_LABEL, SKETCH_SCRIBBLE, "Scribbles on a photo become what you describe; only the place around them changes."),
    (REF_SCRIBBLE_LABEL, REF_SCRIBBLE, "Scribbles on a photo become the object of the reference picture in the slot; only the "
                                       "place around them changes."),
)


def offers_ref_scribble(m) -> bool:
    """The tab Scribble with reference: a model with reference slots, a tag and Scribble on photo, not Fibo (15.11.)."""
    spec = m.modes.get("scribble") if m is not None else None
    return bool(spec is not None and spec.ref_scribble and m.tag_style and m.max_refs > 0)


def ref_scribble_text(tag_style: str) -> str:
    """The text of the chip Reference at scribble for a model with this naming rule: the reference is image 2."""
    return REF_SCRIBBLE.replace("{tag}", tag_style.format(n=2, i=1) if tag_style else "the reference picture")
# Sketch to image: its styles come from Styles (styles.json, mode "sketch"); the two tested ones keep the template texts word
# for word (Realistic photo = SKETCH_PHOTO, Animated film = SKETCH_ILLUSTRATION). An empty field shows this in grey and does not run.
# The frame sentences of the styles of Edit canvas and Sketch to image ({look} = a style's look, tools/styles-looks.json; the
# same frames as the style pilot, tests/live_style_round.py; tools/build_style_looks.py writes the texts into styles.json).
EDIT_FRAME = "Transform this image into {look}. Keep the composition, the subjects and their positions."
SKETCH_FRAME = "Turn this sketch of " + SKETCH_MARK + " into {look}. Keep the composition and the shapes of the drawing."
SKETCH_NO_LINES = " No drawing lines left."     # after the frame of every Sketch style whose look wants no lines (user 18.11.)
SKETCH_PLACEHOLDER = "Choose a style under Style prompts"
NO_STYLE = "Choose a style under Style prompts, or type a prompt."
SKETCH_TIP = ("Replace " + SKETCH_MARK + " with what your sketch shows and include its surroundings: "
              "“a dog in an empty street”.")     # shorter example (user 25.11.)
WRITTEN_TIP = "Loaded the written prompt: it runs as it is, without the prompt writer. Choose a style or a template to start fresh."   # Sketch after the history (user 10.11.)
SCRIBBLE_TIP = "Scribble in bright red or green and replace " + SKETCH_MARK + " with what goes there."   # shorter (user 21.11.)
NO_SCRIBBLE = "No scribble found. Scribble in bright red or green, or on its own layer."
# The system prompt of Flux 2's Sketch writer (qwen3vl 4B, node 402 of flux2-klein-sketch.json): an edit instruction, not a
# caption; the sketch part is neutral so Illustration stays an illustration (writer round on PC A, 10.11.: Photo and
# Illustration 7/7; docs/tests/sketch-schreiber-ergebnis.md). Flux 3 and Qwen keep BFL's upsampler.
SKETCH_WRITER_SYSTEM = (
    "You write the edit instruction for an image editing model. You get a picture and a short request. Write ONE clear "
    "English instruction that starts with a verb. If the picture carries rough coloured scribble lines: say where they "
    "are (which part of the picture, what they lie on) and what replaces them exactly there; name the new object with "
    "its look, material, colour, size and pose, matching the light, perspective and style of the photo; the scribble "
    "lines must be gone and everything else stays unchanged. If the picture is a sketch or drawing: say to turn it into "
    "the finished picture in the look the request asks for (a realistic photograph, a still from an animated film or "
    "another style) and name each element of the drawing with its colour, material and place, keeping the composition, "
    "shapes and proportions exactly, with no sketch lines left unless the look has outlines. Output only the instruction "
    "as one block of prose, 60 to 150 words, with no lists, Markdown or explanations.")
# Qwen's Sketch writer (qwen3.5 9B w4a8, node 402 of qwen-image-21-sketch.json; user 16.11. evening, after writer round 3,
# docs/tests/sketch-schreiber-w4a8-ergebnis.md): the upsampler's way of working as rules, temperature 0.3. Scribble on photo
# writes without thinking (V1), Sketch to image with thinking and max_length 8192 (V3); the same text for both.
QWEN_SKETCH_WRITER_HEAD = (
    "You write the edit instruction for an image editing model. You get a picture and a short request. Look at the "
    "whole picture closely before you write. Write ONE English instruction of 150 to 210 words. "
    "If the picture is a sketch or drawing: begin with \"Create a\" and the look the request asks for (for example a "
    "realistic photograph or a still from an animated film), then say to preserve the exact composition, viewpoint, "
    "shapes and proportions of the drawing. Then go through the drawing part by part (left, centre, right, foreground, "
    "background) and for every drawn element say where it is, its shape and size, and the real material, colour and "
    "texture it becomes, keeping its exact silhouette and place. Colours come from the request or the drawing; where "
    "neither gives one, choose a natural one. The result is in full colour unless the request asks otherwise. End with: "
    "no drawing lines left, unless the look has outlines. "
    "If the picture is a photo with rough coloured scribble lines: begin with \"Replace the\", the colour of the "
    "scribbles, what they lie on and what they become. For each scribbled area say where it is in the picture, how many "
    "objects it marks and the exact look of each (shape, size, material, colour, pose), fitted to the outline of the "
    "scribble. Then say to match the light, perspective, colours and grain of the photo, to remove every scribble line "
    "and to keep everything else unchanged. "
    "Name only what the picture shows or the request asks for: no extra objects, people, animals, brands or text. Do "
    "not use general phrases such as \"ensure\", \"seamlessly\", \"lifelike\" or \"stunning\".")
QWEN_SKETCH_WRITER_TAIL = " Output only the instruction as one block of prose, with no lists, Markdown or explanations."
QWEN_SKETCH_WRITER_SYSTEM = QWEN_SKETCH_WRITER_HEAD + QWEN_SKETCH_WRITER_TAIL
SKETCH_MODE = "sketch"      # the window mode of the tab; it runs as a whole-image edit
SCRIBBLE_PREFIX = "Replace the coloured scribbles"


EDIT_TABS_VERSION = 2       # saved with every run and page since plan B (10.11.): Scribble on photo has its own tab


def legacy_sketch_mode(mode: str, prompt: str, version=None) -> str:
    """Before plan B (10.11.) Scribble on photo was a template of the tab Sketch: a run or page saved before (no
    ``edit_tabs`` version) in mode "sketch" whose prompt is the scribble sentence belongs to the tab Scribble on photo now."""
    old = version is None and mode == SKETCH_MODE and str(prompt).lstrip().startswith(SCRIBBLE_PREFIX)
    return SCRIBBLE_MODE if old else mode
STOCK_PROMPTS = {QWEN_KEEP_COLORS, FIBO_UPSCALE_DEFAULT, FLUX2_DEFAULT_PREV, FLUX2_DEFAULT_OLD, FLUX3_DEFAULT_OLD, PLACEHOLDER, FLUX2_DEFAULT, FLUX3_DEFAULT, FLUX3_RESTORE, QWEN_UPSCALE_DEFAULT, RELIGHT_NEUTRAL, RELIGHT_STUDIO, FIBO_REFINE,
                 SKETCH_PHOTO, SKETCH_ILLUSTRATION, SKETCH_SCRIBBLE}   # texts the window may replace when the mode changes
# the same templates with the mark used until 21.11. (a page or run saved before): still stock texts
STOCK_PROMPTS |= {s.replace(SKETCH_MARK, old) for s in (SKETCH_PHOTO, SKETCH_ILLUSTRATION, SKETCH_SCRIBBLE) for old in OLD_SKETCH_MARKS}

# The tooltips of the function buttons: one general text per function, the same for every model (user 28.10.); what
# holds for one model only goes into its tip under the prompt (Mode.prompt_tip). No ranking in it (user 3.11.).
# The tooltips of the tabs under Edit (refslots.py); the function buttons and the model chips have none (user 11.11.)
FUNCTION_TIPS = {
    "inpaint": "Fills your selection with what you describe (“a red flower”). Only the selected place changes.",
    "edit": "Changes the whole picture from your text (\"make it night\"). A selection is ignored.",
    "multi_edit": ("Edit the picture with reference images in the slots below (drop, paste or add files). "
                   "Name them in the text by their tags. The whole picture changes; a selection is ignored."),
    "sketch": "Turns a sketch on the canvas into a picture in the style you choose under Style prompts. A selection is ignored.",
    "scribble": "Turns coloured scribbles on a photo into real objects; only the place around them changes. A selection is ignored.",
}

QWEN = Model(
    "qwen", "Qwen Image 2.1",
    {
        "txt2img": Mode("qwen-image-21-t2i.json", dict(native=True, base_res=1024, turbo=False, layer_mask="none", enhance=False), prompt_tip=T2I_TIP),   # LLM off like the others (user 30.10.)
        "edit": Mode("qwen-image-21-edit.json", dict(base_res=1024, turbo=False, layer_mask="none"), prompt_tip=EDIT_TIP),
        "multi_edit": Mode("qwen-image-21-edit.json", dict(base_res=1024, turbo=False, layer_mask="none"), run_as="edit"),
        "sketch": Mode("qwen-image-21-sketch.json", dict(base_res=1024, turbo=False, layer_mask="none", enhance=True), prompt_tip=SKETCH_TIP, run_as="edit"),   # Sketch to image: a style from Styles (plan B, 10.11.)
        "scribble": Mode("qwen-image-21-sketch.json", dict(base_res=1024, turbo=False, layer_mask="none", enhance=True), SKETCH_SCRIBBLE, SCRIBBLE_PROMPTS, SCRIBBLE_TIP, run_as="edit"),   # its own tab (plan B)
        # soft: opaque over the selection, fading out to the crop's side (Bridge: soft_layer_mask; Fill mask test round 30.10.)
        "inpaint": Mode("qwen-image-21-edit.json", dict(_SOFT, base_res=1024, context=0.4, turbo=False, feather_pct=4.0), prompt_tip=FILL_TIP + " " + QWEN_SMALL,
                        fill_object_mask=True),   # the mask follows the object (user 21.11., "Mask follows object")
        "outpaint": Mode("qwen-image-21-edit.json", dict(base_res=1024, context=0.4, turbo=False, layer_mask="soft")),   # soft mask: only the new area (+ overlap) is returned, the original stays untouched (user 4.11.); Context 40 %
        "remove": Mode("qwen-image-21-edit.json", dict(_SOFT, base_res=1024, context=0.4, turbo=False, feather_pct=10.0), prompt_tip=REMOVE_TIP, remove_text=True),
        # native 2K upscale: no upscaler node and no LoRA, 25 steps; the result is about the scale factor times the picture, up to 16 MP
        "upscale": Mode("qwen-image-21-upscale.json", dict(scale=1.5, turbo=False, context=0.0), QWEN_UPSCALE_DEFAULT),
        # the upscale graph at the size of the canvas (factor 1), with the Turbo LoRA as a switch (own file so Upscale stays
        # as it is)
        "refine": Mode("qwen-image-21-refine.json", dict(turbo=False, context=0.0), QWEN_KEEP_COLORS, prompt_tip=REFINE_TIP),
    },
    requires=(
        "qwen_image_2.1_int8_convrot.safetensors",
        "qwen_image_2.1_vae_bf16.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=8, tag_style="<image{n}>")

FLUX2 = Model(
    "flux2", "Flux 2 Klein Edit",
    {
        "txt2img": Mode("flux2-klein-t2i.json", dict(native=True, base_res=1024, layer_mask="none", enhance=False), prompt_tip=T2I_TIP),
        "edit": Mode("flux2-klein-edit.json", dict(base_res=1024, layer_mask="none"), prompt_tip=EDIT_TIP),
        "multi_edit": Mode("flux2-klein-edit.json", dict(base_res=1024, layer_mask="none"), run_as="edit"),
        "sketch": Mode("flux2-klein-sketch.json", dict(base_res=1024, layer_mask="none", enhance=True), prompt_tip=SKETCH_TIP, run_as="edit"),   # Sketch to image: a style from Styles (plan B, 10.11.)
        "scribble": Mode("flux2-klein-sketch.json", dict(base_res=1024, layer_mask="none", enhance=True), SKETCH_SCRIBBLE, SCRIBBLE_PROMPTS, SCRIBBLE_TIP, run_as="edit"),   # its own tab (plan B)
        # Fill (user 10.11.): the way its Remove runs, the edit graph with the red outline and the start values of Remove,
        # the wording bridge.FILL_PROMPT_NATURAL (Flux Fill round 2: 8 of 8 good; docs/tests/fill-flux-ergebnis.md)
        "inpaint": Mode("flux2-klein-edit.json", dict(_SOFT, base_res=1024, context=0.4, feather_pct=10.0), prompt_tip=FILL_TIP),
        "remove": Mode("flux2-klein-edit.json", dict(_SOFT, base_res=1024, context=0.4, feather_pct=10.0), prompt_tip=REMOVE_AGAIN, remove_text=True, remove_style="F"),
        "outpaint": Mode("flux2-klein-edit.json", dict(base_res=1024, layer_mask="soft")),   # soft mask: only the new area is returned (user 4.11.)
        # Upscale always in tiles, no switch (user 12.11.; upscale stage round 9.11.: 2 of 3 good with tiles, 0 of 3 without;
        # needs KJNodes, manifest ModeSpec.nodes); Refine keeps the graph without tiles as its own file, unchanged
        "upscale": Mode("flux2-klein-upscale.json", dict(scale=1.5, turbo=True, context=0.0), FLUX2_DEFAULT),
        "refine": Mode("flux2-klein-refine.json", dict(turbo=True, context=0.0), RELIGHT_NEUTRAL, prompt_tip=REFINE_TIP),
    },
    requires=(
        "flux-2-klein-9b_int8_convrot.safetensors",
        "qwen_3_8b_fp8mixed.safetensors",
        "flux2-vae.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=3, tag_style="image {n}", seam="off")

FLUX3 = Model(
    "flux3", "Flux 3 Klein Edit",
    {
        "txt2img": Mode("flux3-klein-t2i.json", dict(native=True, base_res=1536, layer_mask="none", enhance=False), prompt_tip=T2I_TIP),
        "edit": Mode("flux3-klein-edit.json", dict(base_res=1536, layer_mask="none"), prompt_tip=EDIT_TIP),
        "multi_edit": Mode("flux3-klein-edit.json", dict(base_res=1536, layer_mask="none"), run_as="edit"),
        "sketch": Mode("flux3-klein-sketch.json", dict(base_res=1536, layer_mask="none", enhance=True), prompt_tip=SKETCH_TIP, run_as="edit"),   # Sketch to image: a style from Styles (plan B, 10.11.)
        "scribble": Mode("flux3-klein-sketch.json", dict(base_res=1536, layer_mask="none", enhance=True), SKETCH_SCRIBBLE, SCRIBBLE_PROMPTS, SCRIBBLE_TIP, run_as="edit"),   # its own tab (plan B)
        # Fill through the layout box (plan B step 4; Fill round 5, 11.11.: 16 of 16 good in the crop, "Place", user's choice):
        # the start values of its Remove, the selection's box becomes <obj_1>; no new files
        "inpaint": Mode("flux3-klein-edit.json", dict(_SOFT, base_res=1536, context=0.4, feather_pct=10.0, mask_density=0), prompt_tip=FILL_TIP, fill_box=True),
        "remove": Mode("flux3-klein-edit.json", dict(_SOFT, base_res=1536, context=0.4, feather_pct=10.0), prompt_tip=REMOVE_AGAIN, remove_text=True, remove_style="E"),
        # Expand: its own graph with ausboss' outpaint LoRA (29.10., after Pixaroma's "14. Flux 3 Klein - Outpaint"; without
        # it Flux 3 slid or zoomed the picture instead of filling the margin): grey margin, ~1 megapixel, Context 1.0 (confirmed 4.11.)
        "outpaint": Mode("flux3-klein-outpaint.json", dict(base_res=1024, context=1.0, layer_mask="soft")),   # Context 100 % fits (user 4.11. evening); soft mask: only the new area is returned
        "upscale": Mode("flux3-klein-upscale.json", dict(scale=1.5, turbo=True, stage_on=False, stage2_on=True, context=0.0, detail=0.7), FLUX3_DEFAULT),
        # Refine with the Restore LoRA of Upscale (0.5, the switch "Restore LoRA", on; user 22.11.: round 3, 4 of 6 against 0)
        "refine": Mode("flux3-klein-refine.json", dict(turbo=True, context=0.0), FLUX3_RESTORE, prompt_tip=REFINE_TIP),
    },
    requires=(
        "flux3-image-klein-int8-convrot.safetensors",
        "qwen3vl_4b_int8_convrot.safetensors",
        "flux2-vae.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=3, tag_style="<ref_image_{i}>", seam="off", bbox=True, ref_side=1536)   # with BBOX ticked only one (refslots.BBOX_MAX_REFS)

# MOSS: the DMD2 speed LoRA (8 steps, CFG 1.5) is the model's own LoRA; the Lenovo UltraReal LoRA and the skip-layer
# guidance (SLG) are switches that start on (best result in the live tests); the LLM prompt enhancer starts off.
_MOSS = dict(turbo=True, stage_on=True, stage2_on=False, stage3_on=False)     # the stages of moss-image-t2i.json: UltraReal (on), skip-layer guidance (off)
MOSS_STEPS_TIP = "Turn up the steps to 35 for best results."     # wording of the user (29.10.), 35 after the CFG test
_MOSS_INPAINT = {"turbo": False, "stage_on": True, "stage2_on": False, "base_res": 1216, "layer_mask": "soft", "mask_grow": 8, "mask_blur": 16,
                 "context": 1.0}      # 0.4 gave the model too little surroundings (user test 1.11.: Fill did not fit the picture)
MOSS = Model(
    "moss", "MOSS Image",
    {
        # Text to image starts without DMD2 and without SLG, no LLM: the user's live test 29.10. (with DMD2 or SLG the photos
        # looked artificial, with the LLM prompt too). Without DMD2 the workflow runs 25 steps at CFG 3.0 (35 was the blind-test winner, 25 is the default since 2.11.) (pc_no_lora; blind
        # test docs/tests/moss-cfg.md)
        "txt2img": Mode("moss-image-t2i.json", {**_MOSS, "turbo": False, "native": True, "base_res": 1280,
                                                "layer_mask": "none", "enhance": False},
                        prompt_tip=T2I_TIP, steps_tip=MOSS_STEPS_TIP),
    },
    requires=(
        "moss_image_sft_int8_convrot.safetensors",
        "qwen3.5_9b_w4a8_gptq.safetensors",
        "flux2-vae_small.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=3, tag_style="image {n}", seam="off")

# Krea-2 Turbo: a fast distilled text-to-image model (8 steps, CFG 1). Text to image has the model's own prompt enhancer
# (starts off, like the other models').
KREA2 = Model(
    "krea2", "Krea 2 Turbo",
    {
        "txt2img": Mode("krea2-turbo-t2i.json", dict(native=True, base_res=1024, layer_mask="none", enhance=False), prompt_tip=T2I_TIP),
    },
    requires=(
        "krea2_turbo_int8_convrot.safetensors",
        "qwen3vl_4b_int8_convrot.safetensors",
        "qwen_image_vae.safetensors",
    ))   # the model files this tab needs (details per mode: manifest.py)

# Expand with Krea 2 and MOSS was switched off (user 29.10.; MOSS came back 1.11. with the Inpainting v10 recipe, see MOSS above): in a blind test with the user's own pictures
# (docs/tests/expand-seam-testrunde.md) only 2 of 64 Krea 2 and 10 of 64 MOSS results were good, also with a description
# of the surroundings, a wider overlap, the seam correction or a second run over the border. The modes are kept here,
# with the Describe button they used, so they can come back when a better recipe exists (idea: Krea 2 AnyPaint LoRA).
PARKED_EXPAND = {
    "krea2": Mode("krea2-turbo-inpaint.json", dict(base_res=1024, layer_mask="soft"),
                  prompt_tip=EXPAND_DESCRIBE_TIP, describe=True),
    "moss": Mode("moss-image-inpaint.json", _MOSS_INPAINT, prompt_tip=EXPAND_DESCRIBE_TIP, describe=True),   # Inpainting v10 with the plugin's cut-out
}
# their graph files stay in the workflows folder but are not offered in the Workflow list: picked there they counted as a
# workflow of your own ("Image -> image" appeared, user 29.10.)
PARKED_WORKFLOWS = {m.workflow for m in PARKED_EXPAND.values()}   # (moss-image-inpaint-v10.json deleted 10.11.; in git history)

FIBO = Model(
    "fibo", "Fibo 2.0 Edit Turbo",
    {
        "txt2img": Mode("fibo2-t2i.json", dict(native=True, base_res=1224, layer_mask="none", enhance=False), prompt_tip=T2I_TIP),
        "edit": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="none", enhance=False), prompt_tip=EDIT_TIP),
        "multi_edit": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="none", enhance=False), run_as="edit"),
        "sketch": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="none", enhance=False), prompt_tip=SKETCH_TIP, run_as="edit"),   # no writer (sketch round 2: best without)   # Sketch to image: a style from Styles (plan B, 10.11.)
        "scribble": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="none", enhance=False), SKETCH_SCRIBBLE, SCRIBBLE_PROMPTS, SCRIBBLE_TIP, run_as="edit", ref_scribble=False),   # its own tab (plan B)
        "refine": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="none", enhance=False), FLUX2_DEFAULT, run_as="edit",
                       prompt_tip=REFINE_TIP),   # no Sharpen any more (user 17.11.; was 10 % since 31.10.)
        # Upscale (6.11.): Fibo draws the picture anew at the larger size (the user's Fibo2_turbo_edit_2K-ROPE workflow); 8 steps; up to
        # 3x since 10.11. (upscale stage round: 3x 4 of 4 good, 4x 2 of 4 with made-up writing once, so 4x stays grey; docs/tests/upscale-stufen-ergebnis.md)
        # Prompt C (the Qwen upscale text) is the standard since 7.11. (rounds 3 and 4: truest to the original); the stage "4x UltraSharp first"
        # starts on (best at 1.5x and 2x), "Tiles" is a second stage that excludes it; above 3 MP the result is made in tiles by itself (auto_on_above_mp)
        "upscale": Mode("fibo2-upscale.json", dict(scale=1.5, layer_mask="none", enhance=False, context=0.0), QWEN_UPSCALE_DEFAULT, max_scale=3.0,
                        stage_row=True),   # the stages in one row of the Upscale / Refine box (8.11.; Fibo first, the others after test round 2.3/1)
        "inpaint": Mode("fibo2-edit.json", dict(base_res=1024, context=0.1, layer_mask="soft", feather_pct=10.0, enhance=False), prompt_tip=FILL_TIP),   # Context 0.1 chosen by the user 1.11. (was 0.4 from the test round 28.10.); Edge feather 10 % stays
        "outpaint": Mode("fibo2-edit.json", dict(base_res=1024, context=1.0, layer_mask="soft", enhance=False)),   # Context 100 %: with 40 % Fibo saw mostly the white margin and drew bars (user 4.11.); soft mask: only the new area is returned
        "remove": Mode("fibo2-edit.json", dict(base_res=1024, layer_mask="soft", feather_pct=10.0, enhance=False), prompt_tip=REMOVE_AGAIN, remove_text=True, remove_style="F"),
    },
    requires=(
        "fibo2_edit_turbo_int8_convrot.safetensors",
        "qwen3vl_4b_int8_convrot.safetensors",
        "flux2-vae.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=2, tag_style="<image_{n}>", seam="on")

# MiniMax H3 Image (PLAN 2.0b, docs/plan-minimax-h3-image.md; Release 1): distilled, 6 steps, CFG 1, no negative prompt; it
# works on about 4 to 20 MP. Text to image draws the area of the size row (gen_mp) in the canvas' aspect ratio; without the
# tick "Downsize to canvas" the result opens as a new document in that size (user 10.11.), with it it becomes a layer scaled
# down to the canvas (the official min_generation_area rule). The prompt writer (Qwen 3.5 9B with the official task prompt)
# starts off everywhere: Edit / Multi image edit had it on from 11.11. ("remove the trees" came back unchanged without it), the
# blind test of 17.11. (docs/tests/minimax-edit-ergebnis.md) put it off: 4 MP without the writer 11 of 13 good in 24 s, with it 10
# of 13 in 77 s (user 17.11.). 4 MP is the start (8 MP with the writer 12 of 13, but 108 s).
GEN_MP_STEPS = (4, 8, 12, 16, 20)       # the size row of MiniMax (user 10.11.)
MINIMAX_STEPS_TIP = "MiniMax H3 Image is made for 6 steps at CFG 1."
MINIMAX_DESCRIBE_TIP = "Tick \"Enhance my Prompt with LLM\" – MiniMax H3 Image likes a long prompt."   # also in tips.py (user 18.11., choice C; shorter, user 21.11.)
MINIMAX_T2I_TIP = MINIMAX_DESCRIBE_TIP   # the "Downsize to canvas" sentence went (too long, user 13.11.); it stays in DOWNSIZE_TIP
MINIMAX_EDIT = dict(gen_mp=4, downsize=True, layer_mask="none", enhance=False)    # Edit / Multi image edit: 4 MP, "Downsize to canvas" on, the writer off (user 17.11.)
MINIMAX = Model(
    "minimax", "MiniMax H3 Image",
    {
        "txt2img": Mode("minimax-h3-image-t2i.json", dict(native=True, gen_mp=4, downsize=False, layer_mask="none", enhance=False),
                        prompt_tip=MINIMAX_T2I_TIP, steps_tip=MINIMAX_STEPS_TIP),
        # Edit and Multi image edit (step 4, user 11.11.): the size row as in Text to image, "Downsize to canvas" starts ON (a
        # layer in the canvas like every edit model; off = a new document in the chosen size)
        "edit": Mode("minimax-h3-image-edit.json", MINIMAX_EDIT, prompt_tip=EDIT_TIP, steps_tip=MINIMAX_STEPS_TIP),
        "multi_edit": Mode("minimax-h3-image-edit.json", MINIMAX_EDIT, steps_tip=MINIMAX_STEPS_TIP, run_as="edit"),
        # Sketch to image and Scribble on photo (step 8, user 21.11.: "Ja, ohne Schreiber"; docs/tests/minimax-sketch-ergebnis.md:
        # without the writer 25 of 26 good at 27 s, like Flux 3): the Edit graph and its start values. Scribble with
        # reference is not offered yet (not probed with MiniMax)
        "sketch": Mode("minimax-h3-image-edit.json", MINIMAX_EDIT, prompt_tip=SKETCH_TIP, steps_tip=MINIMAX_STEPS_TIP, run_as="edit"),
        "scribble": Mode("minimax-h3-image-edit.json", MINIMAX_EDIT, SKETCH_SCRIBBLE, SCRIBBLE_PROMPTS, SCRIBBLE_TIP,
                         steps_tip=MINIMAX_STEPS_TIP, run_as="edit", ref_scribble=False,
                         scribble_object_mask=True),   # the mask follows the object (user 21.11., "Mask follows object")
        # Refine (user 22.11. "Ja, mit Default"): the Edit graph and its start values with the Flux 2 Default text, as Fibo
        # Refine (MiniMax refine round 2: 5 of 6, docs/tests/minimax-refine-ergebnis.md); one button, no own files
        "refine": Mode("minimax-h3-image-edit.json", MINIMAX_EDIT, FLUX2_DEFAULT, run_as="edit", prompt_tip=REFINE_TIP,
                       steps_tip=MINIMAX_STEPS_TIP),
    },
    requires=(
        "minimax_h3_image_pruned_int8_convrot.safetensors",
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "minimax_h3_image_vae_fp16.safetensors",
    ),   # the model files this tab needs (details per mode: manifest.py)
    max_refs=6, tag_style="<Picture {n}>", ref_side=2048,   # references at 2048 px (probe 14.11.: 1024 put the jacket on the child too)
    # live preview without the TAE file (11.11.): an older 2D taeh3.safetensors in vae_approx is not recognised by ComfyUI 0.45,
    # its preview then stops KSampler ("'NoneType' object has no attribute 'show_progress_bar'"); latent2rgb never loads it
    preview="latent2rgb")   # <Picture 1> is the picture, the references follow (<Picture 2> ...)

MODELS = [FLUX3, FLUX2, QWEN, FIBO, KREA2, MOSS, MINIMAX]      # the order of the tabs
# the list of the model chip and the model field of the gear window, the same order in both (user 22.11.: "minimax, moss,
# krea 2, qwen, flux 3, flux 2, fibo"; 21.11. only MiniMax first); MODELS keeps the old order for the replacement choice
PICK_ORDER = [MINIMAX, MOSS, KREA2, QWEN, FLUX3, FLUX2, FIBO]
assert sorted(m.key for m in PICK_ORDER) == sorted(m.key for m in MODELS), "PICK_ORDER must hold every model once"
BY_KEY = {m.key: m for m in MODELS}
# the unedited text of Reference at scribble is a stock text in every naming rule (a model change replaces it like the others)
STOCK_PROMPTS.update(ref_scribble_text(m.tag_style) for m in MODELS if m.tag_style)

SHORT = {"flux3": "Flux 3", "flux2": "Flux 2", "qwen": "Qwen Image 2.1", "fibo": "Fibo", "krea2": "Krea 2", "moss": "MOSS",
         "minimax": "MiniMax"}


def model_for_workflow(name: str) -> Model | None:
    """The model a workflow file belongs to (None for a workflow of your own)."""
    return next((m for m in MODELS if name in m.workflows()), None)
