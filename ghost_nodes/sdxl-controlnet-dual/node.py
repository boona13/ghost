"""
sdxl-controlnet-dual -- auto-generated from ComfyUI workflow.
SDXL dual ControlNet workflow - depth + canny edge detection for image-guided generation
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.sdxl_controlnet_dual")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(image_7="", image_33="", filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if image_7: overrides["7.inputs.image"] = image_7
        if image_33: overrides["33.inputs.image"] = image_33

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
                    metadata={"source_workflow": "sdxl-controlnet-dual", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "sdxl_controlnet_dual",
        "description": "SDXL dual ControlNet workflow - depth + canny edge detection for image-guided generation. Models: auto-detected. If execution fails with a MISSING MODEL error, use web_search to find the download URL, then comfyui_model_download to fetch it, then retry.",
        "parameters": {
            "type": "object",
            "properties": {"image_7": {"type": "string", "description": "Path to input image (node 7)"}, "image_33": {"type": "string", "description": "Path to input image (node 33)"}},
            "required": ["image_7", "image_33"],
        },
        "execute": execute,
    })
