"""
Virtual Try-On Node — CatVTON garment transfer.

Pipeline (based on CatVTON / pzc163/Comfyui-CatVTON):
  1. Load person image and garment image
  2. Generate clothing mask (auto or user-provided)
  3. Run CatVTON pipeline (SD Inpainting + custom attention)
  4. Output person wearing the new garment

CatVTON (ICLR 2025): lightweight virtual try-on using spatial concatenation.
Only 49.57M trainable parameters, < 8GB VRAM for 1024x768 resolution.
"""

import io
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

log = logging.getLogger("ghost.node.virtual_tryon")

_pipeline = None


def _get_device(api):
    device_info = api.resource_manager.device_info
    if device_info.has_cuda:
        return "cuda"
    if device_info.has_mps:
        return "mps"
    return "cpu"


def _get_dtype(device):
    if device == "cuda":
        return torch.bfloat16
    if device == "mps":
        return torch.float16
    return torch.float32


def _get_tryon_resolution(device):
    """CatVTON concatenates images spatially, doubling memory. Adapt resolution."""
    if device == "cuda":
        return 768, 1024
    return 384, 512


def _generate_clothing_mask(person_image: Image.Image,
                            cloth_type: str = "upper") -> Image.Image:
    """Generate a clothing area mask using rembg segmentation and region heuristics.

    For upper body: mask the torso region (roughly 25%-65% of height).
    For lower body: mask the lower region (roughly 50%-90% of height).
    For overall: mask the full body clothing area (roughly 20%-90% of height).
    """
    from rembg import remove

    person_rgba = remove(person_image, post_process_mask=True)
    alpha = np.array(person_rgba.split()[-1])

    w, h = person_image.size
    mask = np.zeros((h, w), dtype=np.uint8)

    if cloth_type == "upper":
        y_start, y_end = int(h * 0.15), int(h * 0.55)
    elif cloth_type == "lower":
        y_start, y_end = int(h * 0.45), int(h * 0.85)
    else:
        y_start, y_end = int(h * 0.15), int(h * 0.85)

    region = alpha[y_start:y_end, :]
    mask[y_start:y_end, :] = region

    from scipy.ndimage import binary_dilation, binary_fill_holes
    mask_binary = mask > 128
    mask_binary = binary_fill_holes(mask_binary)
    mask_binary = binary_dilation(mask_binary, iterations=5)
    mask = (mask_binary * 255).astype(np.uint8)

    return Image.fromarray(mask).convert("L")


def _load_pipeline(device, dtype):
    """Load the CatVTON pipeline."""
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    node_dir = Path(__file__).parent
    if str(node_dir) not in sys.path:
        sys.path.insert(0, str(node_dir))

    from catvton.pipeline import CatVTONPipeline

    log.info("Loading CatVTON pipeline (SD Inpainting + CatVTON attention)...")
    _pipeline = CatVTONPipeline(
        base_ckpt="runwayml/stable-diffusion-inpainting",
        attn_ckpt="zhengchong/CatVTON",
        attn_ckpt_version="mix",
        weight_dtype=dtype,
        device=device,
        skip_safety_check=True,
        use_tf32=(device == "cuda"),
    )
    log.info("CatVTON pipeline loaded on %s", device)
    return _pipeline


def register(api):
    """Register virtual_tryon tool with Ghost."""

    def execute_virtual_tryon(person_image_path="", garment_image_path="",
                               mask_image_path="", cloth_type="upper",
                               steps=30, guidance_scale=2.5, seed=42,
                               filename="", **_kw):
        if not person_image_path:
            return json.dumps({"status": "error", "error": "person_image_path is required"})
        if not garment_image_path:
            return json.dumps({"status": "error", "error": "garment_image_path is required"})

        try:
            device = _get_device(api)
            dtype = _get_dtype(device)
            api.log(f"Virtual Try-On starting on {device}...")

            person_image = Image.open(person_image_path).convert("RGB")
            garment_image = Image.open(garment_image_path).convert("RGB")

            api.log("Step 1/3: Generating clothing mask...")
            t0 = time.time()
            if mask_image_path:
                mask_image = Image.open(mask_image_path).convert("L")
                mask_image = mask_image.resize(person_image.size, Image.LANCZOS)
            else:
                mask_image = _generate_clothing_mask(person_image, cloth_type)
            api.log(f"Mask ready ({time.time() - t0:.1f}s)")

            api.log("Step 2/3: Loading CatVTON pipeline...")
            t1 = time.time()
            pipe = _load_pipeline(device, dtype)
            api.log(f"Pipeline loaded ({time.time() - t1:.1f}s)")

            api.log(f"Step 3/3: Running try-on ({steps} steps, cfg={guidance_scale})...")
            t2 = time.time()

            generator = None
            if seed >= 0:
                gen_device = device if device == "cuda" else "cpu"
                generator = torch.Generator(device=gen_device).manual_seed(seed)

            vt_width, vt_height = _get_tryon_resolution(device)
            api.log(f"Resolution: {vt_width}x{vt_height}")

            results = pipe(
                image=person_image,
                condition_image=garment_image,
                mask=mask_image,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                height=vt_height,
                width=vt_width,
                generator=generator,
            )
            result_image = results[0]
            elapsed_gen = time.time() - t2
            api.log(f"Try-on complete ({elapsed_gen:.1f}s)")

            buf = io.BytesIO()
            result_image.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = filename or f"tryon_{ts}.png"
            if not fname.endswith(".png"):
                fname += ".png"

            elapsed_total = time.time() - t0
            path = api.save_media(
                data=img_bytes, filename=fname, media_type="image",
                prompt=f"Virtual try-on: {cloth_type} garment",
                params={"tool": "virtual_tryon", "device": device},
                metadata={
                    "cloth_type": cloth_type,
                    "steps": steps,
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    "size": f"{vt_width}x{vt_height}",
                    "device": device,
                    "elapsed_secs": round(elapsed_total, 2),
                    "pipeline": "CatVTON (SD1.5-Inpainting + zhengchong/CatVTON)",
                },
            )

            return json.dumps({
                "status": "ok",
                "path": path,
                "size": f"{vt_width}x{vt_height}",
                "elapsed_secs": round(elapsed_total, 2),
                "pipeline": "CatVTON",
            })

        except Exception as e:
            log.error("virtual_tryon error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "virtual_tryon",
        "description": (
            "Virtual clothing try-on using CatVTON (ICLR 2025). "
            "Takes a person photo and a garment image, and generates a realistic image "
            "of the person wearing the garment. Supports upper body, lower body, and "
            "full-body garments.\n\n"
            "Pipeline: auto-mask generation → CatVTON diffusion (SD Inpainting base) → output.\n"
            "Requires < 8GB VRAM. Models auto-download on first use.\n\n"
            "Best for: fashion e-commerce, clothing visualization, outfit planning."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "person_image_path": {
                    "type": "string",
                    "description": "Path to the person photo (clear full-body or half-body shot).",
                },
                "garment_image_path": {
                    "type": "string",
                    "description": "Path to the garment image (flat-lay or model photo of the clothing item).",
                },
                "mask_image_path": {
                    "type": "string",
                    "description": "Optional: path to a clothing mask image (white = area to replace). Auto-generated if not provided.",
                },
                "cloth_type": {
                    "type": "string",
                    "description": "Type of garment: 'upper' (shirt/jacket), 'lower' (pants/skirt), or 'overall' (dress/jumpsuit). Default: 'upper'.",
                    "enum": ["upper", "lower", "overall"],
                },
                "steps": {
                    "type": "integer",
                    "description": "Diffusion steps (default 30, higher = better quality but slower). CatVTON recommends 42-50.",
                },
                "guidance_scale": {
                    "type": "number",
                    "description": "Classifier-free guidance scale (default 2.5). Higher = more accurate garment transfer.",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility (default 42, -1 for random).",
                },
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["person_image_path", "garment_image_path"],
        },
        "execute": execute_virtual_tryon,
    })
