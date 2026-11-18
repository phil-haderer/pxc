# Security policy

## Supported versions

Only the newest release of PxC gets fixes. Please update before you report a problem.

## Reporting a vulnerability

Please report security problems **privately** through GitHub: the repository's **Security** tab ▸ **Report a
vulnerability**. Do not open a public issue for them.

## What PxC connects to

PxC runs on your own computer. It connects to:

- **ComfyUI** at the address set in the gear window (by default `http://127.0.0.1:8188`),
- **PhotoCraft** through its local control channel, protected by a token, with file access limited to PxC's exchange
  folder,
- **Hugging Face** and the other download sources in the model list, only when you start a download.
