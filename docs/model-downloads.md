# Model downloads (direct links)

The same lists as in the README section "Model downloads", written by `tools/update_readme_downloads.py` from the
plugin's own file list (do not edit by hand). The plugin's gear window shows the same files with a download button.

Put each file into the named folder inside your ComfyUI folder (for example `ComfyUI/models/diffusion_models`; a folder
like `loras/Flux 3` is a sub-folder you create), then restart ComfyUI. You only need the files of the models you want.
"Optional" files switch extra features on; without them the model still works. Files marked "needs a free Hugging Face
login" answer with an error until you log in and accept the licence on the model page. Each model has its own licence
on its page; the plugin ships no model.

**Custom nodes.** [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) is needed for Flux 2 and some Upscale
cases (see the notes under each model). Install it from the ComfyUI Manager or the link, then restart ComfyUI.

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
