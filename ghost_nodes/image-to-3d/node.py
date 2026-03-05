"""
Image-to-3D Node — single-image 3D reconstruction using TripoSR.

Model is cached after first load for fast subsequent calls.
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.image_to_3d")

_tsr_model = None
_tsr_device = None


def _ensure_tsr(api):
    """Load and cache the TripoSR model."""
    global _tsr_model, _tsr_device

    model_id = "stabilityai/TripoSR"

    if _tsr_model is not None:
        api.resource_manager.touch(model_id)
        return _tsr_model, _tsr_device

    try:
        from tsr.system import TSR
    except ImportError:
        raise RuntimeError(
            "TripoSR not installed. Run: pip install tsr torch Pillow numpy trimesh"
        )

    device = api.acquire_gpu(model_id, estimated_vram_gb=4.0)
    api.log(f"Loading TripoSR on {device}...")

    _tsr_model = TSR.from_pretrained(
        model_id, config_name="config.yaml", weight_name="model.ckpt",
        token=getattr(api, 'hf_token', None),
    )
    _tsr_model.to(device)
    _tsr_device = device

    api.log("TripoSR ready")
    return _tsr_model, _tsr_device


def register(api):

    def execute_image_to_3d(image_path="", resolution=256,
                             filename="", **_kw):
        if not image_path:
            return json.dumps({"status": "error", "error": "image_path is required"})
        if not Path(image_path).exists():
            return json.dumps({"status": "error", "error": f"File not found: {image_path}"})

        try:
            from PIL import Image
        except ImportError:
            return json.dumps({"status": "error", "error": "Pillow not installed. Run: pip install Pillow"})

        try:
            tsr_model, device = _ensure_tsr(api)

            api.log(f"Generating 3D model from {Path(image_path).name}...")
            t0 = time.time()

            image = Image.open(image_path).convert("RGB")
            scene_codes = tsr_model([image], device=device)
            mesh = tsr_model.extract_mesh(scene_codes, resolution=resolution)[0]

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = filename or f"3d_{ts}.obj"
            out_path = Path(api.data_dir) / fname
            mesh.export(str(out_path))
            mesh_bytes = out_path.read_bytes()
            elapsed = time.time() - t0

            path = api.save_media(
                data=mesh_bytes, filename=fname, media_type="3d",
                metadata={
                    "source": str(image_path), "resolution": resolution,
                    "elapsed_secs": round(elapsed, 2),
                },
            )
            out_path.unlink(missing_ok=True)

            return json.dumps({
                "status": "ok", "path": path,
                "elapsed_secs": round(elapsed, 2),
            })

        except RuntimeError as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})
        except Exception as e:
            log.error("image_to_3d error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "image_to_3d_model",
        "description": (
            "Generate a 3D model from a single image using TripoSR (local). "
            "Creates OBJ mesh files. Best with product shots and objects on clean backgrounds. "
            "Requires: pip install tsr torch Pillow numpy trimesh"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to source image."},
                "resolution": {"type": "integer", "description": "Mesh resolution (default 256)."},
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["image_path"],
        },
        "execute": execute_image_to_3d,
    })
