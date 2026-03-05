"""
Style Transfer Node — apply artistic styles to any image.

Uses VGG19-based neural style transfer. Supports:
- Applying style from any reference image
- Built-in preset styles (configurable)
- Adjustable style/content balance
"""

import json
import logging
import time
import io
from pathlib import Path

log = logging.getLogger("ghost.node.style_transfer")

_vgg = None


def _ensure_vgg(api):
    global _vgg
    if _vgg is not None:
        return _vgg

    import torch
    import torchvision.models as models

    api.log("Loading VGG19 feature extractor...")
    device = api.acquire_gpu("vgg19-style", estimated_vram_gb=0.5)
    _vgg = models.vgg19(weights="IMAGENET1K_V1").features.to(device).eval()
    for p in _vgg.parameters():
        p.requires_grad_(False)
    api.log(f"VGG19 loaded on {device}")
    return _vgg


def _gram_matrix(tensor):
    b, c, h, w = tensor.size()
    features = tensor.view(b * c, h * w)
    G = features @ features.T
    return G / (b * c * h * w)


def _get_features(model, image, layers=None):
    if layers is None:
        layers = {'0': 'conv1_1', '5': 'conv2_1', '10': 'conv3_1',
                  '19': 'conv4_1', '21': 'conv4_2', '28': 'conv5_1'}
    features = {}
    x = image
    for name, layer in model._modules.items():
        x = layer(x)
        if name in layers:
            features[layers[name]] = x
    return features


def register(api):

    def execute_style_transfer(content_image="", style_image="",
                                style_weight=1e6, content_weight=1,
                                steps=300, output_size=512,
                                filename="", **_kw):
        if not content_image:
            return json.dumps({"status": "error", "error": "content_image is required"})
        if not style_image:
            return json.dumps({"status": "error", "error": "style_image is required"})
        if not Path(content_image).exists():
            return json.dumps({"status": "error", "error": f"File not found: {content_image}"})
        if not Path(style_image).exists():
            return json.dumps({"status": "error", "error": f"File not found: {style_image}"})

        try:
            import torch
            import torchvision.transforms as transforms
            from PIL import Image
            import numpy as np

            vgg = _ensure_vgg(api)
            device = next(vgg.parameters()).device

            size = min(int(output_size), 1024)
            transform = transforms.Compose([
                transforms.Resize((size, size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225]),
            ])

            content_img = Image.open(content_image).convert("RGB")
            style_img = Image.open(style_image).convert("RGB")

            content_tensor = transform(content_img).unsqueeze(0).to(device)
            style_tensor = transform(style_img).unsqueeze(0).to(device)

            target = content_tensor.clone().requires_grad_(True)
            optimizer = torch.optim.Adam([target], lr=0.003)

            content_features = _get_features(vgg, content_tensor)
            style_features = _get_features(vgg, style_tensor)

            style_grams = {layer: _gram_matrix(style_features[layer])
                           for layer in style_features}

            style_layers = {'conv1_1': 1.0, 'conv2_1': 0.75, 'conv3_1': 0.2,
                            'conv4_1': 0.2, 'conv5_1': 0.2}

            api.log(f"Applying style transfer ({steps} steps)...")
            t0 = time.time()

            for i in range(1, steps + 1):
                target_features = _get_features(vgg, target)

                content_loss = torch.mean(
                    (target_features['conv4_2'] - content_features['conv4_2']) ** 2
                )

                style_loss = 0
                for layer in style_layers:
                    target_gram = _gram_matrix(target_features[layer])
                    style_gram = style_grams[layer]
                    layer_loss = style_layers[layer] * torch.mean(
                        (target_gram - style_gram) ** 2
                    )
                    style_loss += layer_loss

                total_loss = content_weight * content_loss + style_weight * style_loss
                optimizer.zero_grad()
                total_loss.backward()
                optimizer.step()

                if i % 100 == 0:
                    api.log(f"Step {i}/{steps}, loss: {total_loss.item():.1f}")

            elapsed = time.time() - t0

            result = target.detach().squeeze(0).cpu()
            mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
            result = result * std + mean
            result = result.clamp(0, 1)
            result_img = transforms.ToPILImage()(result)

            buf = io.BytesIO()
            result_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = filename or f"styled_{ts}.png"

            path = api.save_media(
                data=img_bytes, filename=fname, media_type="image",
                prompt=f"Style transfer: {Path(style_image).stem} -> {Path(content_image).stem}",
                params={"steps": steps, "style_weight": style_weight},
                metadata={
                    "content_image": str(content_image),
                    "style_image": str(style_image),
                    "steps": steps, "elapsed_secs": round(elapsed, 2),
                },
            )
            return json.dumps({
                "status": "ok", "path": path,
                "steps": steps,
                "elapsed_secs": round(elapsed, 2),
            })

        except Exception as e:
            log.error("Style transfer error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "style_transfer",
        "description": (
            "Apply the artistic style of one image onto another (local). "
            "Feed a content photo and a style reference (painting, artwork, texture) "
            "to create a stylized masterpiece. Uses neural style transfer with VGG19. "
            "No API key needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content_image": {"type": "string", "description": "Path to the content/photo image."},
                "style_image": {"type": "string", "description": "Path to the style reference image (painting, artwork)."},
                "style_weight": {"type": "number", "description": "How strongly to apply the style (default: 1000000)."},
                "content_weight": {"type": "number", "description": "How much to preserve content (default: 1)."},
                "steps": {"type": "integer", "description": "Optimization steps (more=better, slower). Default: 300."},
                "output_size": {"type": "integer", "description": "Output image size in pixels (default: 512, max: 1024)."},
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["content_image", "style_image"],
        },
        "execute": execute_style_transfer,
    })
