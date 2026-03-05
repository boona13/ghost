"""
lcm-lora-fast -- auto-generated from ComfyUI workflow.
Fast LCM LoRA txt2img community workflow from thinkyhead gist
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.lcm_lora_fast")

WORKFLOW_PATH = Path(__file__).parent / "workflow.json"


def register(api):

    def execute(prompt="", seed=None, steps=None, cfg=None, denoise=None, filename="", **_kw):
        from ghost_comfyui_engine import ComfyUIEngine
        workflow = json.loads(WORKFLOW_PATH.read_text())
        overrides = {}
        if prompt: overrides["4.inputs.text"] = prompt
        if seed is not None: overrides["1.inputs.seed"] = seed
        if steps is not None: overrides["1.inputs.steps"] = steps
        if cfg is not None: overrides["1.inputs.cfg"] = cfg
        if denoise is not None: overrides["1.inputs.denoise"] = denoise

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
                    metadata={"source_workflow": "lcm-lora-fast", "elapsed": round(elapsed, 2)},
                )

        return json.dumps({
            "status": "ok", "files": saved,
            "mode": result.get("mode", "unknown"),
            "elapsed_secs": round(elapsed, 2),
        })

    api.register_tool({
        "name": "lcm_lora_fast",
        "description": "Fast LCM LoRA txt2img community workflow from thinkyhead gist Models: deliberate_v2.safetensors, lcm-lora-sdv1-5.safetensors.",
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string", "description": "Text prompt (default: Prompt)"}, "seed": {"type": "number", "description": "seed (default: 0)"}, "steps": {"type": "number", "description": "steps (default: 8)"}, "cfg": {"type": "number", "description": "cfg (default: 1.2)"}, "denoise": {"type": "number", "description": "denoise (default: 1)"}},
            "required": [],
        },
        "execute": execute,
    })
