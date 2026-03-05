"""
Product Studio Node — professional product photography with AI backgrounds.

Pipeline (based on ComfyUI Background-Replacement by meap158):
  1. Remove background with rembg (RMBG-2.0)
  2. Estimate depth map with DPT (Intel/dpt-hybrid-midas)
  3. Generate new background with SDXL Turbo + ControlNet Depth
  4. Alpha-composite product onto generated background

Supports CUDA, MPS (Apple Silicon), and CPU backends.
"""

import io
import json
import logging
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter

log = logging.getLogger("ghost.node.product_studio")

_depth_estimator = None
_feature_extractor = None
_controlnet = None
_pipe = None


def _get_device(api):
    """Pick the best available torch device."""
    device_info = api.resource_manager.device_info
    if device_info.has_cuda:
        return "cuda"
    if device_info.has_mps:
        return "mps"
    return "cpu"


def _get_dtype(device):
    if device == "cpu":
        return torch.float32
    return torch.float16


def _remove_background(image: Image.Image) -> Image.Image:
    """Remove background and return RGBA image with transparent background."""
    from rembg import remove
    return remove(image, post_process_mask=True)


def _get_depth_map(image: Image.Image, device: str) -> Image.Image:
    """Generate depth map using DPT."""
    global _depth_estimator, _feature_extractor
    from transformers import DPTForDepthEstimation, DPTImageProcessor

    if _depth_estimator is None:
        log.info("Loading depth estimator (Intel/dpt-hybrid-midas)...")
        _feature_extractor = DPTImageProcessor.from_pretrained("Intel/dpt-hybrid-midas")
        _depth_estimator = DPTForDepthEstimation.from_pretrained("Intel/dpt-hybrid-midas")
        _depth_estimator.to(device)
        _depth_estimator.eval()

    original_size = image.size
    inputs = _feature_extractor(images=image, return_tensors="pt").pixel_values.to(device)

    with torch.no_grad():
        depth = _depth_estimator(inputs).predicted_depth

    depth = torch.nn.functional.interpolate(
        depth.unsqueeze(1),
        size=original_size[::-1],
        mode="bicubic",
        align_corners=False,
    )
    depth_min = torch.amin(depth, dim=[1, 2, 3], keepdim=True)
    depth_max = torch.amax(depth, dim=[1, 2, 3], keepdim=True)
    depth = (depth - depth_min) / (depth_max - depth_min + 1e-8)

    depth_rgb = torch.cat([depth] * 3, dim=1)
    depth_np = depth_rgb.permute(0, 2, 3, 1).cpu().numpy()[0]
    return Image.fromarray((depth_np * 255).clip(0, 255).astype(np.uint8))


def _mask_depth_map(depth_map: Image.Image, mask: Image.Image,
                    feather_threshold=128, dilation_iterations=1,
                    blur_radius=5) -> Image.Image:
    """Apply feathered mask to depth map so only the product's depth is visible."""
    from scipy.ndimage import binary_dilation

    mask_np = np.array(mask.convert("L"))
    mask_binary = mask_np > feather_threshold
    dilated = binary_dilation(mask_binary, iterations=dilation_iterations)
    dilated_img = Image.fromarray((dilated * 255).astype(np.uint8))
    blurred = dilated_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    blurred_np = np.array(blurred) / 255.0

    depth_np = np.array(depth_map.convert("L")) / 255.0
    masked = depth_np * blurred_np
    masked = (masked * 255).astype(np.uint8)
    return Image.fromarray(masked).convert("RGB")


def _generate_background(depth_image: Image.Image, prompt: str,
                         negative_prompt: str, device: str,
                         width: int, height: int, api) -> Image.Image:
    """Generate background using SDXL Turbo + ControlNet Depth."""
    global _controlnet, _pipe
    from diffusers import (
        StableDiffusionXLControlNetPipeline,
        ControlNetModel,
        AutoencoderKL,
    )

    dtype = _get_dtype(device)

    if _pipe is None:
        log.info("Loading ControlNet depth model...")
        _controlnet = ControlNetModel.from_pretrained(
            "diffusers/controlnet-depth-sdxl-1.0",
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
            use_safetensors=True,
        )
        log.info("Loading SDXL Turbo pipeline...")
        _pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
            "stabilityai/sdxl-turbo",
            controlnet=_controlnet,
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
            use_safetensors=True,
        )
        if device == "cuda":
            try:
                _pipe.enable_model_cpu_offload()
            except Exception:
                _pipe.to(device)
        else:
            _pipe.to(device)
        try:
            _pipe.enable_attention_slicing()
        except Exception:
            pass

    depth_resized = depth_image.resize((width, height), Image.LANCZOS)

    result = _pipe(
        prompt=prompt,
        negative_prompt=negative_prompt or "cartoon, drawing, anime, ugly, blurry, low quality",
        image=depth_resized,
        num_inference_steps=4,
        guidance_scale=0.0,
        controlnet_conditioning_scale=0.65,
        width=width,
        height=height,
    )
    return result.images[0]


def _composite(background: Image.Image, subject_rgba: Image.Image) -> Image.Image:
    """Composite subject over generated background."""
    bg = background.convert("RGBA").resize(subject_rgba.size, Image.LANCZOS)
    return Image.alpha_composite(bg, subject_rgba).convert("RGB")


def register(api):
    """Register product_studio tool with Ghost."""

    def execute_product_studio(image_path="", prompt="", negative_prompt="",
                                width=1024, height=1024, filename="", **_kw):
        if not image_path:
            return json.dumps({"status": "error", "error": "image_path is required"})
        if not prompt:
            prompt = "professional product photography, studio lighting, clean background, commercial photography"

        try:
            device = _get_device(api)
            api.log(f"Product Studio starting on {device}...")

            image = Image.open(image_path).convert("RGB")
            orig_w, orig_h = image.size
            width = (width // 8) * 8
            height = (height // 8) * 8

            api.log("Step 1/4: Removing background...")
            t0 = time.time()
            subject_rgba = _remove_background(image)

            alpha = subject_rgba.split()[-1]
            api.log(f"Background removed ({time.time() - t0:.1f}s)")

            api.log("Step 2/4: Estimating depth map...")
            t1 = time.time()
            depth_map = _get_depth_map(image, device)
            masked_depth = _mask_depth_map(depth_map, alpha)
            api.log(f"Depth map ready ({time.time() - t1:.1f}s)")

            api.log("Step 3/4: Generating AI background...")
            t2 = time.time()
            background = _generate_background(
                masked_depth, prompt, negative_prompt,
                device, width, height, api
            )
            api.log(f"Background generated ({time.time() - t2:.1f}s)")

            api.log("Step 4/4: Compositing...")
            subject_resized = subject_rgba.resize((width, height), Image.LANCZOS)
            result = _composite(background, subject_resized)

            buf = io.BytesIO()
            result.save(buf, format="PNG", quality=95)
            img_bytes = buf.getvalue()

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = filename or f"product_studio_{ts}.png"
            if not fname.endswith(".png"):
                fname += ".png"

            elapsed = time.time() - t0
            path = api.save_media(
                data=img_bytes, filename=fname, media_type="image",
                prompt=prompt,
                params={"tool": "product_studio", "device": device},
                metadata={
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "size": f"{width}x{height}",
                    "original_size": f"{orig_w}x{orig_h}",
                    "device": device,
                    "elapsed_secs": round(elapsed, 2),
                    "pipeline": "rembg + DPT-depth + SDXL-Turbo-ControlNet",
                },
            )

            return json.dumps({
                "status": "ok",
                "path": path,
                "size": f"{width}x{height}",
                "elapsed_secs": round(elapsed, 2),
                "pipeline": "rembg + DPT-depth + SDXL-Turbo-ControlNet",
            })

        except Exception as e:
            log.error("product_studio error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "product_studio",
        "description": (
            "Professional product photography tool. Takes a product image and "
            "generates a professional studio background with depth-aware lighting. "
            "Pipeline: background removal (rembg) → depth estimation (DPT) → "
            "AI background generation (SDXL Turbo + ControlNet Depth) → compositing.\n\n"
            "Best for: e-commerce product photos, catalog images, professional listings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the product image.",
                },
                "prompt": {
                    "type": "string",
                    "description": (
                        "Background description, e.g. 'on a marble countertop with soft studio lighting' "
                        "or 'on a wooden table in a modern kitchen'. Defaults to generic studio."
                    ),
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in the background (default: cartoon, ugly, blurry).",
                },
                "width": {"type": "integer", "description": "Output width (default 1024, multiple of 8)."},
                "height": {"type": "integer", "description": "Output height (default 1024, multiple of 8)."},
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["image_path"],
        },
        "execute": execute_product_studio,
    })
