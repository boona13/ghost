"""
virtual-tryon-v2 -- auto-generated from ComfyUI workflow.
Virtual clothing try-on using CatVTON. Upload a person photo and garment photo to see realistic results. Auto-downloads CatVTON models from HuggingFace.
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.virtual_tryon_v2")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(image_11="", image_10="", filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if image_11: overrides["11.inputs.image"] = image_11
        if image_10: overrides["10.inputs.image"] = image_10

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
                    metadata={"source_workflow": "virtual-tryon-v2", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "virtual_tryon_v2",
        "description": "Virtual clothing try-on using CatVTON. Upload a person photo and garment photo to see realistic results. Auto-downloads CatVTON models from HuggingFace. Models: auto-detected.",
        "parameters": {
            "type": "object",
            "properties": {"image_11": {"type": "string", "description": "Path to input image (node 11)"}, "image_10": {"type": "string", "description": "Path to input image (node 10)"}},
            "required": ["image_11", "image_10"],
        },
        "execute": execute,
    })
