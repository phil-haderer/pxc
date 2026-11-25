# Changelog

All notable changes to PxC. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers follow [Semantic Versioning](https://semver.org/). The text of each GitHub release is the same as its
entry here.

## [Unreleased]

## [1.1.0] - 2026-11-25

### Added
- **Generate while a run is on:** for Text to Image, Edit, Refine Image and Upscale, Generate becomes **Add to queue**
  for the same function (any model): the picture in front and the settings are taken at the click, the result comes as
  a new layer. Variants ×n become n queue jobs; the first picture runs at once.
- **Queue window:** a row per variant with its number (1/3, 2/3 …), the progress in the Status column, coloured status
  words, columns ordered from what a run is to how far it is, finished rows stay at their place. ✕ stops a waiting or
  running picture, ↻ in the same column runs a stopped or failed one again, ⏸ sits right next to ✕. **Pause all** and
  **Resume all** act on every queued picture; **Clear finished** and **Clear all** clean up.
- **Refine Image** has its own function again (next to Upscale) with one tested prompt per model (Qwen Image 2.1: keep
  the colours, Flux 2: neutral light, Flux 3: restore old photos with its Restore LoRA; Fibo and MiniMax use the
  Flux 2 text). MiniMax H3 Image can refine too.
- **Reroll prompt in Sketch to image and Scribble** (Flux 3, Flux 2, Qwen): the text model writes a new prompt on the
  next run.
- Pick reference images with **@** in the prompt (Multi image edit).
- When ComfyUI runs out of GPU memory, PxC frees it and tries the run once more.
- A thin blue progress line in the head while the window is minimised.

### Changed
- The functions are named the same everywhere, as in the function list: **Text to Image**, **Expand Image**,
  **Fill Selection**, **Remove Selection**, **Edit**, **Refine Image**, **Upscale** (queue, messages, tips, Advanced
  settings, README).
- Undo and Redo are locked during a run (a click on the grey button says why) and leave Upscale out.
- The footer: the queue at the outside, the run history in the **⋯** menu.
- A stopped run keeps the prompt its text model already wrote, so the next run does not write a new one.
- Shorter Sketch to image tip; the README shows the window next to PhotoCraft and a sharper logo.

### Fixed
- The window no longer jumps from the top-left corner at the start and stays above PhotoCraft.
- Undo hides the result layer after Remove, Fill and a direct run.
- Quick Mask in PhotoCraft is switched off before a run takes the picture; only one thread talks to PhotoCraft at a time.
- Cut out is greyed out while a run or a queue job is on.
- Stop batch ends only the batch that runs; queued variants take the picture of their own run.
- No "tile 2" in the status line of functions without tiles.

## [1.0.8] - 2026-11-21

### Added
- **MiniMax H3 Image: Sketch to image and Scribble on photo.** MiniMax is also first in the model list.
- **Style picker:** Styles opens a box of square preview pictures, grouped by chips; Custom prompts are listed in the
  same box (click = use, right-click = use, append, edit or delete). A style replaces a prompt you have not touched.
  Text to image also offers the Edit canvas styles, in the same order.
- **Model variants:** known variants of a model file (for example Kromoss for MOSS Image) are recognised and run with
  their own settings.
- Each custom LoRA row has its own on/off tick.
- **Advanced settings** are grouped; a dot marks every value you changed from the start value.
- Model Links: a coloured chip shows the state of each model; the file list marks the file in use and real
  replacements with dots, with a legend. Undo has no time limit, one step per click.
- The queue window keeps finished runs of other PCs as "Done".

### Changed
- **Generate turns into Stop** while a run is on (with a short guard against double clicks); the Edit tabs are a
  list right under the head chips, and functions and models are two list chips in the head, as wide as their lists.
- PCs sharing one ComfyUI take turns picture by picture.
- Remove: picking it always empties the prompt field; your text comes back when you leave Remove.
- Qwen Image Fill: the layer mask follows the object, so an object drawn larger than the selection is no longer cut
  off. MiniMax Scribble on photo does the same.
- Sketch prompts use SUBJECT as the placeholder; new, shorter tips under the prompt for Edit canvas, Multi image edit
  and Scribble on photo.
- The MOSS prompt writer writes short English prompts.
- Styles renamed alike across modes; eight styles removed; no "Ready" line; no outlines on the blue buttons and the
  progress bar.

### Fixed
- The settings window stays inside the screen's work area and always opens at full height.
- Escape closes the queue or settings window but never stops a run; Stop during a batch ends only that batch.
- Linux: copied pictures stay on the X11 clipboard (with time limits), the batch window keeps its bottom edge.
- Qwen Turbo in Expand runs without the sigma schedule.

## [1.0.7] - 2026-11-19

### Added
- **Update check:** once a day at the start PxC asks GitHub whether a newer version is out (GitHub sees your IP
  address and the PxC version, nothing else). A newer version shows as a blue dot on the gear and a line at the top of
  Gear ▸ Other settings with **What's new** (the release page) and **Skip this version**. **Check now** asks at once;
  untick **Check for updates** to stop it. If you installed with `git clone`, **Update now** runs `git pull` for you.

### Changed
- **Model Links redesigned:** a narrower settings window; you pick the model in a field, and every file has its own
  field that opens the search right below it (instead of the chain icon). One blue button **Download missing files**
  shows the size. Undo, Reset and Check files moved into the menu **⋯**. The pages Model Links and Other settings are
  chips like the function buttons, and **Supported Modes** sits above the mode tiles.

## [1.0.6] - 2026-11-19

### Added
- **Queue window for the whole network:** it lists every run at ComfyUI, your own and those of other PCs, in the
  order they run, with the columns #, Sent by, Picture, Status, Progress, Function and Time. Generate tells every queue
  window how many variants it makes.
- **Progress column:** a text bar for your own running run, the time since start for a run of another PC.
- Orders of different PCs on one ComfyUI run one after the other. When others have jobs waiting, PxC places your next
  batch picture early ("Sent"); Pause and ✕ take it back out.
- Queue window comforts: a double-click on a heading fits the column to its longest text, a right-click on a heading
  resets the widths, widths and window size stay after a restart, Time shows "starts in ~3 min", Delete cancels and
  Space pauses or resumes the selected row, and a clear hint when ComfyUI is not connected.

### Changed
- The Generate row fills the full width: Generate and the variants piece are as wide as the tab "Edit canvas".
- Undo and Redo are square buttons; the one you can use is blue.

### Removed
- The short LICENSE file again: GitHub showed the licence as "Other" with it. The licence stays MIT or Apache-2.0
  (LICENSE-MIT, LICENSE-APACHE).

### Fixed
- Queue columns no longer jump when you drag a column border.
- The queue window opens on Linux (it stopped with a cursor error).

## [1.0.5] - 2026-11-18

### Added
- **Reroll prompt:** a button next to Enhance my Prompt with LLM has the text model write a new prompt.
- The window frame turns blue while PxC has the focus.
- Issue forms, CONTRIBUTING, SECURITY, a CHANGELOG and a LICENSE file that names the MIT or Apache-2.0 choice.

### Changed
- Sketch to image: styles that are not line styles end with "No drawing lines left.", so no sketch lines stay in the
  picture.
- Text to image style prompts cleaned up and merged; the anime golden-sky style has no background any more.
- The window and the report say "PxC" instead of "plugin".
- The last row of model chips is centred; the last-seed icon is smaller.
- Shorter and corrected tooltips (Enhance my Prompt with LLM, the MiniMax Text to image tip and others).
- README: a personal note, a new feature list and a square logo.

### Fixed
- A test of cancelling Describe Canvas failed now and then on Windows.

## [1.0.4] - 2026-11-17

### Changed
- MiniMax H3 Image: Edit and Multi image edit now start at 4 MP with the prompt writer off (a blind test showed no
  gain from it at 4 MP, at about 50 s extra per picture). The Qwen 3.5 9B writer is optional for MiniMax, the download
  drops to about 38 GB.
- README: an Examples section with before/after pictures for every function, Text to image with built-in styles, and
  new window screenshots.

### Removed
- `check-windows.bat` (a developer diagnosis tool).

## [1.0.3] - 2026-11-17

### Changed
- README rebuilt: "Before you start" lists the requirements, then one complete install guide each for Windows and
  Linux; every step is written only once.
- Shorter texts in Functions and More in the window; disk space corrected to 13 to 19 GB per model.

## [1.0.2] - 2026-11-17

### Fixed
- An own function icon file is closed right after reading (Windows test failure in 1.0.1).

### Changed
- README shorter and clearer; the model download tables show the ComfyUI folder below each file name.

## [1.0.1] - 2026-11-17

### Changed
- README: shorter quick start (ComfyUI and the KJNodes add-on in one point, no graphics card line, no tab details).

### Fixed
- Two tests now pass on the CI machines of the install matrix (Linux program name, slow refused connection on Windows).

## [1.0.0] - 2026-11-17

First release of **PxC**: generative AI for PhotoCraft with local models through ComfyUI. Results arrive as new layers
in your document.

### Added
- Six functions: Text to image, Expand, Fill, Remove, Edit (with Sketch to image and Scribble tabs) and
  Upscale / Refine; plus Remove background.
- Seven models: Flux 3 Klein, Flux 2 Klein, Qwen Image 2.1, Fibo 2.0 Edit Turbo, Krea 2 Turbo, MOSS Image and
  MiniMax H3 Image.
- Windows 10/11 and Linux, an NVIDIA graphics card, PhotoCraft 0.20.2 or newer.
- One custom node pack: ComfyUI-KJNodes.

[Unreleased]: ../../compare/v1.0.8...HEAD
[1.0.8]: ../../compare/v1.0.7...v1.0.8
[1.0.7]: ../../compare/v1.0.6...v1.0.7
[1.0.6]: ../../compare/v1.0.5...v1.0.6
[1.0.5]: ../../compare/v1.0.4...v1.0.5
[1.0.4]: ../../compare/v1.0.3...v1.0.4
[1.0.3]: ../../compare/v1.0.2...v1.0.3
[1.0.2]: ../../compare/v1.0.1...v1.0.2
[1.0.1]: ../../compare/v1.0.0...v1.0.1
[1.0.0]: ../../releases/tag/v1.0.0
