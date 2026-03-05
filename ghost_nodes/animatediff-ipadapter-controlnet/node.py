"""
animatediff-ipadapter-controlnet -- auto-generated from ComfyUI workflow.
Advanced image-to-video workflow using AnimateDiff + IPAdapter + ControlNet (DWPose, LineArt, Tile). Transforms input images into styled animated videos with upscaling via RIFE.
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.animatediff_ipadapter_controlnet")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(image_path="", filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if image_path: overrides["432.inputs.image"] = image_path

        engine = ComfyUIEngine(
            models_dir=api.models_dir,
            device=api.get_device(0),
            output_dir=None,
            progress_cb=lambda msg: api.log(msg),
        )

        t0 = time.time()
        result = engine.execute_workflow(workflow, overrides=overrides)
        elapsed = time.time() - t0

        saved = result.get("saved_files", [])
        for fpath in saved:
            p = Path(fpath)
            if p.exists():
                api.save_media(
                    data=p.read_bytes(), filename=p.name,
                    media_type="image",
                    metadata={"source_workflow": "animatediff-ipadapter-controlnet", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "animatediff_ipadapter_controlnet",
        "description": "Advanced image-to-video workflow using AnimateDiff + IPAdapter + ControlNet (DWPose, LineArt, Tile). Transforms input images into styled animated videos with upscaling via RIFE. Models: auto-detected. If execution fails with a MISSING MODEL error, use web_search to find the download URL, then comfyui_model_download to fetch it, then retry.",
        "parameters": {
            "type": "object",
            "properties": {"image_path": {"type": "string", "description": "Path to input image (node 432)"}},
            "required": ["image_path"],
        },
        "execute": execute,
    })
