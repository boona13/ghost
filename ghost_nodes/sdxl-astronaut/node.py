"""
sdxl-astronaut -- auto-generated from ComfyUI workflow.
SDXL txt2img workflow: generate cinematic photos of astronauts on Mars
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.sdxl_astronaut")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(prompt="", prompt_2="", seed=None, steps=None, cfg=None, denoise=None, filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if prompt: overrides["6.inputs.text"] = prompt
        if prompt_2: overrides["7.inputs.text"] = prompt_2
        if seed is not None: overrides["3.inputs.seed"] = seed
        if steps is not None: overrides["3.inputs.steps"] = steps
        if cfg is not None: overrides["3.inputs.cfg"] = cfg
        if denoise is not None: overrides["3.inputs.denoise"] = denoise

        engine = ComfyUIEngine(
            models_dir=api.models_dir,
            device=api.get_device(4.0),
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
                    metadata={"source_workflow": "sdxl-astronaut", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "sdxl_astronaut",
        "description": "SDXL txt2img workflow: generate cinematic photos of astronauts on Mars Models: sd_xl_base_1.0.safetensors.",
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "Text prompt (default: cinematic photo of an astronaut riding a horse on )"}, "prompt_2": {"type": "string", "description": "Text prompt (default: ugly, blurry, low quality, distorted, cartoon, dra)"}, "seed": {"type": "number", "description": "seed (default: 156680208700286)"}, "steps": {"type": "number", "description": "steps (default: 25)"}, "cfg": {"type": "number", "description": "cfg (default: 7)"}, "denoise": {"type": "number", "description": "denoise (default: 1)"}},
            "required": [],
        },
        "execute": execute,
    })
