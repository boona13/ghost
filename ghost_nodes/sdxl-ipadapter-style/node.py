"""
sdxl-ipadapter-style -- auto-generated from ComfyUI workflow.
SDXL IPAdapter style composition - apply style and composition from reference images to generate new images
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.sdxl_ipadapter_style")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(image_12="", image_16="", filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if image_12: overrides["12.inputs.image"] = image_12
        if image_16: overrides["16.inputs.image"] = image_16

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
                    metadata={"source_workflow": "sdxl-ipadapter-style", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "sdxl_ipadapter_style",
        "description": "SDXL IPAdapter style composition - apply style and composition from reference images to generate new images. Models: auto-detected. If execution fails with a MISSING MODEL error, use web_search to find the download URL, then comfyui_model_download to fetch it, then retry.",
        "parameters": {
            "type": "object",
            "properties": {"image_12": {"type": "string", "description": "Path to input image (node 12)"}, "image_16": {"type": "string", "description": "Path to input image (node 16)"}},
            "required": ["image_12", "image_16"],
        },
        "execute": execute,
    })
