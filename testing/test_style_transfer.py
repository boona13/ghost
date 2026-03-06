"""Test style transfer with aggressive settings to get real Starry Night style."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONTENT = ROOT / "testing" / "person.jpg"
STYLE = ROOT / "testing" / "Starry-Night.jpg"


def main():
    import torch
    from PIL import Image
    from transformers import CLIPVisionModelWithProjection
    from diffusers import StableDiffusionXLImg2ImgPipeline

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32
    print(f"Device: {device}")

    print("Loading SDXL + IP-Adapter Plus (ViT-H)...")
    t0 = time.time()

    image_encoder = CLIPVisionModelWithProjection.from_pretrained(
        "h94/IP-Adapter",
        subfolder="models/image_encoder",
        torch_dtype=dtype,
    )

    pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        image_encoder=image_encoder,
        torch_dtype=dtype,
    )

    pipe.load_ip_adapter(
        "h94/IP-Adapter",
        subfolder="sdxl_models",
        weight_name="ip-adapter-plus_sdxl_vit-h.safetensors",
    )
    pipe.to(device)
    print(f"Loaded in {time.time() - t0:.1f}s")

    content_img = Image.open(CONTENT).convert("RGB")
    style_img = Image.open(STYLE).convert("RGB")

    w, h = content_img.size
    max_dim = 768
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        w, h = int(w * ratio), int(h * ratio)
    w = (w // 8) * 8
    h = (h // 8) * 8
    content_img = content_img.resize((w, h), Image.LANCZOS)
    print(f"Content: {w}x{h}, Style: Starry Night")

    tests = [
        {
            "name": "A_strong_flat",
            "scale": 1.0,
            "strength": 0.7,
            "prompt": "a person in the style of van gogh starry night, swirling brushstrokes, oil painting, vibrant blue and yellow",
            "steps": 40,
        },
        {
            "name": "B_instantstyle_strong",
            "scale": {"up": {"block_0": [0.0, 1.0, 0.0]}},
            "strength": 0.7,
            "prompt": "a person in the style of van gogh starry night, swirling brushstrokes, oil painting, vibrant blue and yellow",
            "steps": 40,
        },
        {
            "name": "C_style_layout_strong",
            "scale": {"down": {"block_2": [0.0, 1.0]}, "up": {"block_0": [0.0, 1.0, 0.0]}},
            "strength": 0.75,
            "prompt": "a person in the style of van gogh starry night, swirling brushstrokes, oil painting, vibrant blue and yellow",
            "steps": 40,
        },
        {
            "name": "D_max_style",
            "scale": 1.2,
            "strength": 0.8,
            "prompt": "van gogh starry night style portrait, thick impasto brushstrokes, swirling sky, vibrant blue yellow",
            "steps": 50,
        },
    ]

    for t in tests:
        print(f"\n--- {t['name']} (strength={t['strength']}, steps={t['steps']}) ---")
        pipe.set_ip_adapter_scale(t["scale"])

        gen = torch.Generator(device="cpu").manual_seed(42)
        t0 = time.time()
        result = pipe(
            prompt=t["prompt"],
            image=content_img,
            ip_adapter_image=style_img,
            strength=t["strength"],
            num_inference_steps=t["steps"],
            guidance_scale=7.5,
            negative_prompt="photo, realistic, lowres, bad anatomy, worst quality, blurry",
            generator=gen,
        )
        elapsed = time.time() - t0

        out = ROOT / "testing" / f"styled_{t['name']}.png"
        result.images[0].save(out, format="PNG")
        print(f"Done in {elapsed:.1f}s -> {out.name}")

    print("\nAll tests complete!")


if __name__ == "__main__":
    main()
