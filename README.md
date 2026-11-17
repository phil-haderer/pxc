<div align="center">

# PxC

*PhotoCraft x ComfyUI*

[![Install matrix](../../actions/workflows/install-matrix.yml/badge.svg)](../../actions/workflows/install-matrix.yml)
[![License: MIT or Apache-2.0](https://img.shields.io/badge/license-MIT%20%7C%20Apache--2.0-blue)](#license)
[![Platform: Windows and Linux](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)](#install-on-windows)
[![Python 3.11 or newer, on Linux 3.10 or newer](https://img.shields.io/badge/python-3.11%2B%20%C2%B7%20Linux%203.10%2B-blue)](#install-on-windows)

**Photoshop-style generative AI for PhotoCraft, running on your own PC.**
Pick a function, type a prompt, press Generate: the result arrives as a new layer in your document.

<img src="readme-images/plugin-window.png" alt="The plugin window: six functions, seven models, prompt box and Generate button" width="330">

Tested: Windows 11 · PhotoCraft 0.23.1 · ComfyUI version: 0.45.0 

[Quick start](#quick-start) · [Install on Windows](#install-on-windows) · [Install on Linux](#install-on-linux) · [First start](#first-start) · [Model downloads](#model-downloads) · [Functions](#functions) · [Help](#help) · [Technical details](#technical-details)

</div>

---

- **Six function buttons:** Text to image, Expand, Fill, Remove, Edit and Upscale / Refine. Edit has tabs: Edit canvas, Multi image edit, Sketch to image, Scribble on photo and Scribble with reference; not every model offers every tab.
- **Seven models:** Flux 3 Klein, Flux 2 Klein, Qwen Image 2.1, Fibo 2.0 Edit Turbo, Krea 2 Turbo, MOSS Image and MiniMax H3 Image.
- **Your own prompts:** the Save button right of the prompt keeps a prompt under a name; use or append it later under Style prompts > Custom prompts. Use also brings back the function, model and tab it was saved with, and image tags such as `<image2>` are rewritten for the model you are on.
- **Local:** the models run in ComfyUI on your own graphics card.

> Unofficial community project, not affiliated with PhotoCraft, ArtCraft or Storyteller. PhotoCraft is in early alpha
> and so is this plugin.

## Quick start

**What you need first** (all free):

- **[PhotoCraft](https://github.com/storytold/photocraft/releases)**: the image editor where you work. The plugin adds AI functions to it.
- **[ComfyUI](https://github.com/comfyanonymous/ComfyUI#installing)**: runs the AI models; leave it running while you work. Flux 2 and Upscale (Flux 3, Fibo) also need the add-on [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) ([ComfyUI Easy Install](https://github.com/Tavris1/ComfyUI-Easy-Install) includes it).
- **[Python](https://www.python.org/downloads/windows/) 3.11 or newer**. No Python yet? On Windows the setup offers to install it for you.
- **About 11 to 19 GB of free disk space per model you want to use, MiniMax about 45 GB** (the models are large files; one model is enough to start).

**Windows**

1. Click **Code ▸ Download ZIP** (green button at the top of this page) and unpack it to a folder you keep, for example `C:\programs\pxc`.
2. Double-click **`setup-windows.bat`**. It sets everything up and puts **PxC** on your desktop.
3. Start ComfyUI, close PhotoCraft if it is open, then double-click **PxC** on your desktop. PhotoCraft opens and the plugin window appears next to it.
4. In the plugin window click the gear ▸ pick a model tab (for example **Qwen Image 2.1**, which needs no login) ▸ **Download all model files**, then restart ComfyUI. (You can also download the files by hand: see [Model downloads](#model-downloads).)
5. Pick a function and a model, type a prompt and press **Generate** (Ctrl+Enter).

**Linux** (Debian/Ubuntu; other distributions: [Install on Linux](#install-on-linux))

```bash
sudo apt install python3 python3-tk python3-venv
git clone <this repository> && cd <this repository>
./setup-linux.sh
```

Then do steps 3 to 5 above, starting **PxC** from your application menu.

## How it fits together

```
PhotoCraft  <-->  this plugin (a small window)  <-->  ComfyUI (your graphics card)
```

- **PhotoCraft** is the image editor where you work and where the results land as layers.
- **ComfyUI** runs the AI models on your graphics card.
- **This plugin** sits between them: it sends your picture or selection to ComfyUI and puts the result back as a layer.

You need Windows 10/11 or Linux, an NVIDIA graphics card (more VRAM means faster runs), Python 3.11+ (Linux: 3.10+), ComfyUI and PhotoCraft 0.20.2 or newer (tested with PhotoCraft 0.23.1, and ComfyUI 0.45.0). MiniMax H3 Image needs a newer ComfyUI that has the nodes `MiniMaxH3ImageConditioning` and `TextGenerateV2`; it does not fit into 16 GB VRAM on its own, so ComfyUI offloads it to system RAM and you need plenty of RAM for it.

## Install on Windows

1. **Download**: click **Code ▸ Download ZIP** at the top of this page and unpack it to a folder you keep (not Downloads). Using git is fine too, see [Technical details](#technical-details).
2. **Set up**: double-click **`setup-windows.bat`**. It shows its four steps as it goes: Python, a private Python environment, the packages, and the desktop shortcut **PxC**. It finds `photocraft.exe` itself and asks once if it can't. (`setup-windows.bat /check` only looks and changes nothing.)
3. **Start**: start ComfyUI, close PhotoCraft if it is open, double-click **PxC** on your desktop. PhotoCraft opens, and a few seconds later the plugin window appears.

No Python yet? The setup offers to install Python 3.13 (the official one from python.org, for your Windows user only, no admin rights) with one key press. Without winget, or if you say no, it opens the download page: install Python 3.13 there with the default options ("tcl/tk" stays ticked) and run `setup-windows.bat` again.
Then go on with [First start](#first-start).

## Install on Linux

X11 and Wayland. Under X11 the window is tied to PhotoCraft as on Windows: it minimises with PhotoCraft and stays above it, but not above other programs. Under Wayland it is a normal window that stays on top. Either way it closes with PhotoCraft.

1. **System packages** (Python 3.10+ with tkinter and venv):

   ```bash
   # Debian/Ubuntu
   sudo apt install python3 python3-tk python3-venv
   # Fedora
   sudo dnf install python3 python3-tkinter
   # Arch
   sudo pacman -S python tk
   # optional, to paste pictures from the clipboard: wl-clipboard (Wayland) or xclip (X11)
   sudo apt install wl-clipboard xclip
   # only if setup-linux.sh says libXcursor is missing (needed to drag pictures onto the reference slots)
   sudo apt install libxcursor1      # Fedora: libXcursor, Arch: libxcursor
   ```

2. **Get the plugin**: download the ZIP and unpack it, or `git clone <this repository>`.
3. **Set up**: run `./setup-linux.sh` in the plugin folder. It makes a private Python environment, installs the packages and adds **PxC** to your application menu (an old PhotoCraft AI menu entry is removed once). It never installs system packages itself; if something is missing it prints the command for your distribution. (`./setup-linux.sh --check` only looks and changes nothing.)
4. **Start**: start ComfyUI, close PhotoCraft if it is open, then start **PxC** from the menu (or run `./pxc.sh`). PhotoCraft is found in `PATH`, `/opt`, `~/Applications`, `~/.local/bin` or as a Flatpak. If it is somewhere else: `PHOTOCRAFT=/path/to/photocraft ./pxc.sh`.

Then go on with [First start](#first-start). Window too small or too big? Gear window ▸ **Other settings** ▸ **Interface scale**.

## First start

1. **Get the models.** A *model* is the AI itself, one big file (or a few) that ComfyUI loads. Open the plugin's settings window (gear symbol at the top right) and pick a model tab. The button **Download all model files** loads everything that model needs; it shows the total size first (about 11 to 19 GB, MiniMax about 45 GB, so it can take a while). Good first choices:
   - **Qwen Image 2.1** or **Fibo 2.0**: no login needed.
   - **Flux 3 Klein**: needs a free Hugging Face account once (the button opens the page; log in and accept the licence there).
2. **Restart ComfyUI.** It reads its model folders only when it starts, so new files appear after a restart.
3. **Generate.** Pick a function and a model, type a prompt (a short description of what you want, in English) and press **Generate** (Ctrl+Enter). Each model starts with its tested settings; the Advanced settings below the prompt change them. The status line at the bottom tells you what is happening.

Prefer to download by hand, or want to see every file and its size? Open [Model downloads](#model-downloads).

## Model downloads

Everything below is for people who want to download the files themselves; the plugin's **Download all model files** button does the same. Click a model to open its list. Put each file into the named folder inside your ComfyUI folder (for example `ComfyUI/models/diffusion_models`; a folder like `loras/Flux 3` is a sub-folder you create), then restart ComfyUI. You only need the files of the models you want. "Optional" files switch extra features on; without them the model still works.

**Custom nodes.** A custom node pack is a small add-on for ComfyUI. Only two are ever mentioned: KJNodes is needed for Flux 2 and for some Upscale cases, GGUF is optional:
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes): its *Color Match* node is used by **Upscale with Flux 3**, by the **tiles** of **Upscale with Flux 2** (always on, no switch) and by the **tiles** option of **Upscale with Fibo**. Without it Flux 2 is locked (Upscale with Flux 2 needs it) and Upscale with Flux 3 and the Fibo tiles cannot start; the line at the bottom of the plugin names the pack.
- [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF): only if you want to use smaller GGUF model files (gear window, chain symbol). Not needed otherwise.

Install a pack from the ComfyUI Manager (search for its name) or from its link, then restart ComfyUI.

<!-- model-downloads:start -->

<details>
<summary><b>Flux 3 Klein</b>: about 18.2 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `flux3-image-klein-int8-convrot.safetensors` | all functions | `models/diffusion_models` | 5.8 GB | [Hugging Face: black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy/resolve/main/diffusion_models/flux3-image-klein-int8-convrot.safetensors) (needs a free Hugging Face login and acceptance of the licence) |
| `qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors` | Remove, Enhance my Prompt with LLM, Describe Canvas, Describe Multi Image Slot, Sketch to image, Scribble on photo | `models/text_encoders` | 6.7 GB | [Hugging Face: black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy/resolve/main/text_encoders/qwen3.5_9b_flux3_prompt_upsampler_w4a8.safetensors) (needs a free Hugging Face login and acceptance of the licence) |
| `qwen3vl_4b_int8_convrot.safetensors` | all functions | `models/text_encoders` | 4.9 GB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) |
| `flux2-vae.safetensors` | all functions | `models/vae` | 336 MB | [Hugging Face: Comfy-Org/Flux-2-Dev](https://huggingface.co/Comfy-Org/Flux-2-Dev/resolve/main/split_files/vae/flux2-vae.safetensors) |
| `flux-3-image-klein-outpaint.safetensors` | Expand | `models/loras/Flux 3` | 161 MB | [Hugging Face: ausboss/FLUX-3-Image-Klein-Outpaint-LoRA](https://huggingface.co/ausboss/FLUX-3-Image-Klein-Outpaint-LoRA/resolve/main/flux-3-image-klein-outpaint.safetensors) |
| `flux-3-image-klein-restore.safetensors` | Upscale | `models/loras/Flux 3` | 161 MB | [Hugging Face: ausboss/FLUX-3-Image-Klein-Restore-LoRA](https://huggingface.co/ausboss/FLUX-3-Image-Klein-Restore-LoRA/resolve/main/flux-3-image-klein-restore.safetensors) |
| `4x-UltraSharpV2.safetensors` | Upscale | `models/upscale_models` | 140 MB | [Hugging Face: Kim2091/UltraSharpV2](https://huggingface.co/Kim2091/UltraSharpV2/resolve/main/4x-UltraSharpV2.safetensors) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `seedvr2_3b_int8_convrot.safetensors` | SeedVR2 pre-cleaning in Upscale | `models/diffusion_models` | 3.5 GB | [Hugging Face: Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_3b_int8_convrot.safetensors) |
| `seedvr2_ema_vae_fp16.safetensors` | SeedVR2 pre-cleaning in Upscale | `models/vae` | 501 MB | [Hugging Face: Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors) |
| `taef2_decoder.pth` | live preview | `models/vae_approx` | 3 MB | [GitHub: madebyollin/taesd](https://raw.githubusercontent.com/madebyollin/taesd/main/taef2_decoder.pth) |

**Custom node:** Upscale also needs the custom node pack [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) (Color Match). Install it from the ComfyUI Manager or the link, then restart ComfyUI.

</details>

<details>
<summary><b>Flux 2 Klein</b>: about 18.6 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `flux-2-klein-9b_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 9.4 GB | [Hugging Face: obsxrver/ComfyUI-Native-INT8_ConvRot](https://huggingface.co/obsxrver/ComfyUI-Native-INT8_ConvRot/resolve/main/diffusion_models/flux-2-klein-9b_int8_convrot.safetensors) |
| `qwen_3_8b_fp8mixed.safetensors` | all functions | `models/text_encoders` | 8.7 GB | [Hugging Face: Comfy-Org/Flux-2-Klein-9B](https://huggingface.co/Comfy-Org/Flux-2-Klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors) |
| `flux2-vae.safetensors` | all functions | `models/vae` | 336 MB | [Hugging Face: Comfy-Org/Flux-2-Dev](https://huggingface.co/Comfy-Org/Flux-2-Dev/resolve/main/split_files/vae/flux2-vae.safetensors) |
| `ultra_real_v4.safetensors` | Upscale, Refine | `models/loras/Flux 2` | 166 MB | [Civitai](https://civitai.com/api/download/models/2846977) (Civitai may ask you to log in) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `qwen3vl_4b_int8_convrot.safetensors` | Enhance my Prompt with LLM, Describe Canvas, Describe Multi Image Slot, Sketch to image, Scribble on photo | `models/text_encoders` | 4.9 GB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) |
| `taef2_decoder.pth` | live preview | `models/vae_approx` | 3 MB | [GitHub: madebyollin/taesd](https://raw.githubusercontent.com/madebyollin/taesd/main/taef2_decoder.pth) |

**Custom node:** Upscale (always in tiles) also needs the custom node pack [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) (Color Match). Install it from the ComfyUI Manager or the link, then restart ComfyUI. Without it Flux 2 is locked.

</details>

<details>
<summary><b>Qwen Image 2.1</b>: about 17.3 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `qwen_image_2.1_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 7.3 GB | [Hugging Face: Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors) |
| `qwen3vl_8b_int8_convrot.safetensors` | all functions | `models/text_encoders` | 9.4 GB | [Hugging Face: Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors) |
| `qwen_image_2.1_vae_bf16.safetensors` | all functions | `models/vae` | 676 MB | [Hugging Face: Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `qwen3.5_9b_w4a8_gptq.safetensors` | Enhance my Prompt with LLM, Describe Canvas, Describe Multi Image Slot, Sketch to image, Scribble on photo | `models/text_encoders` | 7.3 GB | [Hugging Face: Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors) |
| `qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors` | Turbo LoRA | `models/loras/qwen` | 913 MB | [Hugging Face: Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/loras/qwen_image_2.1_turbo_lora_avg_rank_178_bf16.safetensors) |
| `taeqi2_1_decoder.pth` | live preview | `models/vae_approx` | 15 MB | [GitHub: madebyollin/taesd](https://raw.githubusercontent.com/madebyollin/taesd/main/taeqi2_1_decoder.pth) |

</details>

<details>
<summary><b>Fibo 2.0</b>: about 13.7 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `fibo2_edit_turbo_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 8.4 GB | [Hugging Face: Comfy-Org/Fibo-2.0](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/diffusion_models/fibo2_edit_turbo_int8_convrot.safetensors) |
| `qwen3vl_4b_int8_convrot.safetensors` | all functions | `models/text_encoders` | 4.9 GB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) |
| `flux2-vae.safetensors` | all functions | `models/vae` | 336 MB | [Hugging Face: Comfy-Org/Flux-2-Dev](https://huggingface.co/Comfy-Org/Flux-2-Dev/resolve/main/split_files/vae/flux2-vae.safetensors) |
| `4x-UltraSharpV2.safetensors` | Upscale | `models/upscale_models` | 140 MB | [Hugging Face: Kim2091/UltraSharpV2](https://huggingface.co/Kim2091/UltraSharpV2/resolve/main/4x-UltraSharpV2.safetensors) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `taef2_decoder.pth` | live preview | `models/vae_approx` | 3 MB | [GitHub: madebyollin/taesd](https://raw.githubusercontent.com/madebyollin/taesd/main/taef2_decoder.pth) |

**Custom node:** The tiles option of Upscale also needs the custom node pack [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) (Color Match). Install it from the ComfyUI Manager or the link, then restart ComfyUI.

</details>

<details>
<summary><b>Krea 2 Turbo</b>: about 18.6 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `krea2_turbo_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 13.5 GB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_int8_convrot.safetensors) |
| `qwen3vl_4b_int8_convrot.safetensors` | all functions | `models/text_encoders` | 4.9 GB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) |
| `qwen_image_vae.safetensors` | all functions | `models/vae` | 254 MB | [Hugging Face: Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `lighttaew2_1.safetensors` | live preview | `models/vae_approx` | 45 MB | [Hugging Face: lightx2v/Autoencoders](https://huggingface.co/lightx2v/Autoencoders/resolve/main/lighttaew2_1.safetensors) |

</details>

<details>
<summary><b>MOSS Image</b>: about 13.1 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `moss_image_sft_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 5.4 GB | [Hugging Face: Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/diffusion_models/moss_image_sft_int8_convrot.safetensors) |
| `qwen3.5_9b_w4a8_gptq.safetensors` | all functions | `models/text_encoders` | 7.3 GB | [Hugging Face: Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors) |
| `flux2-vae_small.safetensors` | all functions | `models/vae` | 250 MB | [Hugging Face: Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/vae/flux2-vae_small.safetensors) |
| `lenovo_moss.safetensors` | Text to image | `models/loras/Moss` | 65 MB | [Hugging Face: Danrisi/lenovo_moss](https://huggingface.co/Danrisi/lenovo_moss/resolve/main/lenovo_moss.safetensors) |

Optional (the model works without them, the named feature is greyed out):

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `lora_dmd2.safetensors` | Turbo LoRA | `models/loras/Moss` | 1.2 GB | [Hugging Face: lodestones/MOSS-Image-Base-8-steps-dmd](https://huggingface.co/lodestones/MOSS-Image-Base-8-steps-dmd/resolve/main/lora_dmd2.safetensors) |
| `taef2_decoder.pth` | live preview | `models/vae_approx` | 3 MB | [GitHub: madebyollin/taesd](https://raw.githubusercontent.com/madebyollin/taesd/main/taef2_decoder.pth) |

</details>

<details>
<summary><b>MiniMax H3 Image</b>: about 45.2 GB needed</summary>

| File | Needed for | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `minimax_h3_image_pruned_int8_convrot.safetensors` | all functions | `models/diffusion_models` | 21.0 GB | [Hugging Face: Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors) |
| `qwen3.5_9b_w4a8_gptq.safetensors` | all functions | `models/text_encoders` | 7.3 GB | [Hugging Face: Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors) |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | all functions | `models/text_encoders` | 15.7 GB | [Hugging Face: Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |
| `minimax_h3_image_vae_fp16.safetensors` | all functions | `models/vae` | 1.2 GB | [Hugging Face: Comfy-Org/MiniMax-H3-Image](https://huggingface.co/Comfy-Org/MiniMax-H3-Image/resolve/main/vae/minimax_h3_image_vae_fp16.safetensors) |

</details>

<details>
<summary><b>Remove background</b> (scissors button, optional)</summary>

| File | Feature | Goes into ComfyUI's | Size | Download |
|---|---|---|---|---|
| `birefnet.safetensors` | Cut out, remove background | `models/background_removal` | 444 MB | [Hugging Face: Comfy-Org/BiRefNet](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors) |
| `rmbg-2.0.safetensors` | Remove background (second model) | `models/background_removal` | 885 MB | [Hugging Face: chflame163/ComfyUI_LayerStyle](https://huggingface.co/chflame163/ComfyUI_LayerStyle/resolve/main/ComfyUI/models/BiRefNet/RMBG-2.0/model.safetensors) |

RMBG-2.0 is a community copy of the official file, which needs a Hugging Face login ([official page](https://huggingface.co/briaai/RMBG-2.0)).

</details>

<!-- model-downloads:end -->

## Functions

You pick a **function** at the top, type a prompt and press **Generate**. The plugin sends the picture (or the selection)
to ComfyUI and puts the result back into PhotoCraft as a new layer in a group, with a soft layer mask where that makes sense.

| Function | What it does |
|---|---|
| **Text to image** | A new picture from text only, as a new layer. MiniMax H3 Image draws 4 to 20 MP and opens the picture as a new document in that size; tick "Downsize to canvas" to get a layer in your canvas instead. With MiniMax, Edit and Multi image edit (up to 6 reference images) use the same MP buttons and tick; there the tick starts on (a layer in your canvas), off opens a new document in full size. |
| **Expand image** | Extend the canvas with the Crop tool, fill the new area white; the plugin paints it. |
| **Fill Selection** | Select an area, type what should appear there. With Flux 3 the tab Insert reference beside it puts one reference image into your rectangle selection. |
| **Remove Selection** | Select an object, with a little margin around it, and name it in the prompt field ("car"); it is removed and the background filled in. With Flux 3, Flux 2 and Fibo you can leave the field empty: the model then names the subject itself. |
| **Edit** › Edit canvas | Changes the whole picture from your text ("make it night"). **Style prompts** turns the picture into a style (painting, comic, film look …): it sets the whole sentence in the prompt. |
| **Edit** › Multi image edit | Edits the picture with reference images (drop or paste images into the slots). A click on the tag on a slot puts it where your cursor is in the prompt, or at the end. |
| **Edit** › Sketch to image | Turns a sketch on the canvas into a picture in the style you choose under **Style prompts** (photo, film look, painting, comic, 3D and more). The style's whole text stands in the prompt: replace `<WHAT IT SHOWS>`; the style you chose last comes back next time. Flux 3 needs the Flux 3 prompt upsampler for it, Qwen needs Qwen 3.5 9B w4a8 GPTQ, Flux 2 needs Qwen3-VL 4B; without it only this tab is greyed out. |
| **Edit** › Scribble on photo | Turns scribbles on a photo into real objects: scribble in bright red or green, or on a layer of its own; only that place changes. Replace `<WHAT IT SHOWS>` in the prompt with what goes there. Needs the same files as Sketch to image. |
| **Edit** › Scribble with reference | Like Scribble on photo, but the scribbled place becomes the object of the reference picture in the slot. Replace `<WHAT IS IN THE REFERENCE>` with what it shows ("a beagle dog"). |
| **Upscale / Refine** | Pick a factor (1.5x to 4x) in the row "Upscale factor": the whole picture is enlarged into a new document, up to 16 MP. Or pick a button in the row "Refine" (Default; with Flux 2 also Neutral and Studio portrait; with Flux 3 also Restore): the picture is cleaned up at the same size, as a new layer. A selection is ignored. |

<details>
<summary>Which model offers which function</summary>

| | Flux 3 | Flux 2 | Qwen Image 2.1 | Fibo | Krea 2 | MOSS | MiniMax |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Fill Selection | ✓ | ✓ | ✓ | ✓ | | | |
| Fill › Insert reference | ✓ | | | | | | |
| Remove Selection | ✓ | ✓ | ✓ | ✓ | | | |
| Expand image | ✓ | ✓ | ✓ | ✓ | | | |
| Edit › Edit canvas | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| Edit › Multi image edit | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| Upscale (new file) | ✓ | ✓ | ✓ | ✓ (up to 3x) | | | |
| Refine (same size) | ✓ | ✓ | ✓ | ✓ | | | |
| Edit › Sketch to image | ✓ | ✓ | ✓ | ✓ | | | |
| Edit › Scribble on photo | ✓ | ✓ | ✓ | ✓ | | | |
| Edit › Scribble with reference | ✓ | ✓ | ✓ | | | | |
| Text to image | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

</details>

More in the window: **variants** (several results as layers in one group), prompt history (the clock at the bottom right, "Last runs"), Style prompts, Enhance my Prompt with LLM, live preview. **Check files** (gear window ▸ Model Links) compares the model files on your disk with their checksums; a damaged file is named, never deleted. The **scissors** at the bottom right (**Remove background**) opens a small menu: **BiRefNet**, **RMBG-2.0** or **Both** (two layers, RMBG-2.0 on top). A copy of the visible picture is added as a new layer with a layer mask that hides the background; the mask stays editable (paint on it to fix an edge, or apply it in PhotoCraft). It needs the optional `birefnet.safetensors` and/or `rmbg-2.0.safetensors` (gear window ▸ Model Links ▸ Additional); RMBG-2.0 is by Bria AI, and its download symbol in the settings window uses a community mirror because the official file needs a Hugging Face login. To get it by hand: log in at [huggingface.co/briaai/RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0), accept the terms, download `model.safetensors`, rename it to `rmbg-2.0.safetensors` and put it into ComfyUI's `models/background_removal` folder (restart ComfyUI). Advanced settings: **edge feather, context size, mask density (PhotoCraft 0.17+), custom LoRAs, prompt writer seed.**

## Help

| You see | What to do |
|---|---|
| The dot next to **ComfyUI** (bottom left) is red, or "ComfyUI not connected" | Start ComfyUI. If it runs on another address or port: gear ▸ **Other settings** ▸ **ComfyUI address**, then Refresh. |
| "PhotoCraft not found" when you start | Windows: run `.venv\Scripts\python.exe -m pccomfy shortcut --photocraft "C:\path\to\photocraft.exe"` in the plugin folder (type `powershell` into Explorer's address bar). Linux: `PHOTOCRAFT=/path/to/photocraft ./pxc.sh`. |
| "PhotoCraft did not open the control port" | Another PhotoCraft is already running: close all of them and start through the shortcut or menu entry. Or another program uses port 7878. |
| "No control-channel token" or "rejected the token" | PhotoCraft was started without the plugin's start options. Close it and start through the shortcut or menu entry. Flatpak: see [Technical details](#technical-details). |
| "You need to download …" | Open the gear window and download the missing file, then restart ComfyUI (it reads its model folders only at start). |
| A Flux 3 download is refused | Log in to Hugging Face and accept the licence on the model page first. |
| On Linux nothing appears | Run `./pxc.sh` in a terminal; the message tells you what is missing. |
| **Enhance my Prompt with LLM** is slow, especially with 8 GB of VRAM | Start ComfyUI with the option `--use-ck-attention` (Comfy Kitchen attention): add it at the end of the line with `main.py` in your ComfyUI start file (`.bat`), or run `python main.py --use-ck-attention`. In our tests on 8 GB the prompt writers ran 2 to 5 times faster, Qwen Image 2.1 pictures about 25 % faster, with the same quality of prompts and pictures (tested with ComfyUI 0.45). On 16 GB the prompt writers are fast without it. |

**Update.** Download the new ZIP and unpack it over the old folder, or run `git pull` in the plugin folder if you used `git clone`; then run the setup script again and restart the plugin. Your settings, including "Set current settings as startup settings" (right-click on a model), stay in `data\` (Linux: `~/.config/pccomfy/`) and are not touched.

**Report a problem.** Open an issue on this repository's **Issues** page and tell us:
- what you did, what you expected and what happened (the status line at the bottom of the window is useful);
- the **report** of the plugin: gear window ▸ **Other settings** ▸ **Copy report**, then paste it into the issue. It lists the plugin version, Python, your settings and what ComfyUI and PhotoCraft answered; it contains no prompts and no access tokens.

If we ask for more: the last lines of `data\exchange\runs.jsonl` (Linux: `~/.cache/pccomfy/exchange/runs.jsonl`) have one line per run, and `last-graph.json` in the same folder is the exact request sent to ComfyUI. Both can contain your prompts, so look through them before you post.

## Technical details

**Install with git.**

```bash
git clone <this repository>
cd <this repository>
```

**Windows, by hand** (what `setup-windows.bat` does):

```bat
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
:: desktop shortcut (optional)
.venv\Scripts\python.exe -m pccomfy shortcut --photocraft "C:\path\to\photocraft.exe"
:: start without the shortcut (ComfyUI running, PhotoCraft closed)
.venv\Scripts\python.exe pxc.pyw --photocraft "C:\path\to\photocraft.exe"
```

If `setup-windows.bat` said it uses Python directly, use the path in `data\python.txt` instead of `.venv\Scripts\python.exe`.
The shortcut starts PhotoCraft with a control channel for the plugin (local only, protected by a token, file access limited to `data\exchange`) and then the plugin, without a console window.

**Linux, by hand** (what `setup-linux.sh` does):

```bash
# create the venv with the system Python: a Python from uv or pyenv brings a Tk that does not draw the Inter font
/usr/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./pxc.sh
# menu entry (optional)
.venv/bin/python -m pccomfy shortcut --photocraft /path/to/photocraft
```

Settings and the PhotoCraft token live in `~/.config/pccomfy/`. A different ComfyUI address or port goes into `~/.config/pccomfy/config.toml` (see `config.example.toml`). `.venv/bin/python -m pccomfy scale` shows how the plugin detected the display scale.

**PhotoCraft as a Flatpak.** It is found by itself; to name it: `PHOTOCRAFT=flatpak:ai.storyteller.photocraft ./pxc.sh`. The Flatpak sandbox sees only Pictures and Documents, so the plugin opens `~/.config/pccomfy` and `~/.cache/pccomfy` for the Flatpak run; that lets PhotoCraft write its token file there.

**Custom nodes.** Flux 3 Upscale, the tiles of Flux 2 Upscale (always on) and the tiles of Fibo Upscale use the *Color Match* node of [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes). Install the pack from the ComfyUI Manager or the link, then restart ComfyUI. Without it Flux 2 is locked and Upscale with Flux 3 and the Fibo tiles cannot run (the line at the bottom of the plugin names the pack); everything else uses ComfyUI's own nodes. GGUF files (link them with the chain symbol in the gear window) need [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).

**Model files.** All files with sizes, folders and links are listed under [Model downloads](#model-downloads). The gear window lists the same files with a download button; the plugin enables a model when it finds all the files for its standard settings. To keep the memory use low, release 1 uses int8 ConvRot files for most models; the exceptions are the text encoders of MiniMax (nvfp4) and Flux 2 (fp8mixed) and the prompt writers (w4a8). Some files are gated: log in to Hugging Face and accept the licence on the model page first. Flux 3 is one of them.

**Known limitations.**
- Developed and tested on Windows 11 with an NVIDIA card. On Linux it was run on Ubuntu 24.04 (Wayland) and Linux Mint (X11); other distributions are not tested yet.
- During a run, PhotoCraft briefly opens a temporary document. Please don't switch documents or change the selection while a run is going.
- A run consists of several PhotoCraft steps (history entries).
- CMYK, Lab and 16-bit documents go through 8-bit RGB.

## License

Dual-licensed under [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE), at your option. The models are not part of this
repository and have their own licences (on each model's page).
