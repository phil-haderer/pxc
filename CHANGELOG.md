# Changelog

All notable changes to PxC. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers follow [Semantic Versioning](https://semver.org/). The text of each GitHub release is the same as its
entry here.

## [Unreleased]

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

[Unreleased]: ../../compare/v1.0.5...HEAD
[1.0.5]: ../../compare/v1.0.4...v1.0.5
[1.0.4]: ../../compare/v1.0.3...v1.0.4
[1.0.3]: ../../compare/v1.0.2...v1.0.3
[1.0.2]: ../../compare/v1.0.1...v1.0.2
[1.0.1]: ../../compare/v1.0.0...v1.0.1
[1.0.0]: ../../releases/tag/v1.0.0
