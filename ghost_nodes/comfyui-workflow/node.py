"""
ComfyUI Workflow Node — run, analyze, and import ComfyUI community workflows.

Three tools:
  comfyui_run     — execute a workflow JSON file directly
  comfyui_analyze — inspect a workflow (models, inputs, node types)
  comfyui_import  — convert a workflow into a standalone Ghost node
"""

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("ghost.node.comfyui_workflow")


def register(api):

    # ── Tool 1: Run a workflow ─────────────────────────────────────

    def execute_run(workflow_path="", overrides="", device="auto",
                    filename="", **_kw):
        if not workflow_path:
            return json.dumps({"status": "error",
                               "error": "workflow_path is required"})

        wf_path = Path(workflow_path)
        if not wf_path.exists():
            return json.dumps({"status": "error",
                               "error": f"File not found: {workflow_path}"})

        try:
            workflow = json.loads(wf_path.read_text())
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error",
                               "error": f"Invalid JSON: {e}"})

        override_dict = {}
        if overrides:
            try:
                override_dict = json.loads(overrides) if isinstance(overrides, str) else overrides
            except json.JSONDecodeError:
                return json.dumps({"status": "error",
                                   "error": "overrides must be valid JSON"})

        try:
            from ghost_comfyui_engine import ComfyUIEngine

            engine = ComfyUIEngine(
                models_dir=api.models_dir,
                device=device,
                progress_cb=lambda msg: api.log(msg),
            )

            api.log(f"Running ComfyUI workflow: {wf_path.name}")
            t0 = time.time()
            result = engine.execute_workflow(workflow, overrides=override_dict)
            elapsed = time.time() - t0

            saved = result.get("saved_files", [])
            for fpath in saved:
                p = Path(fpath)
                if p.exists():
                    api.save_media(
                        data=p.read_bytes(),
                        filename=filename or p.name,
                        media_type="image",
                        metadata={
                            "source_workflow": wf_path.name,
                            "mode": result.get("mode", "unknown"),
                            "elapsed": round(elapsed, 2),
                        },
                    )

            return json.dumps({
                "status": "ok",
                "files": saved,
                "mode": result.get("mode"),
                "elapsed_secs": round(elapsed, 2),
            })

        except Exception as e:
            log.error("Workflow execution error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "comfyui_run",
        "description": (
            "Execute a ComfyUI workflow JSON file natively. "
            "Supports any community workflow — custom nodes are auto-installed. "
            "For simple workflows (txt2img, img2img, inpaint) runs via diffusers; "
            "complex workflows fall back to ComfyUI node packages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_path": {
                    "type": "string",
                    "description": "Path to a ComfyUI workflow .json file.",
                },
                "overrides": {
                    "type": "string",
                    "description": (
                        'JSON dict of input overrides. Format: '
                        '{"node_id.inputs.key": value}. '
                        'E.g. {"6.inputs.text": "a cat"} to override a prompt.'
                    ),
                },
                "device": {
                    "type": "string",
                    "description": "Device: auto, cpu, cuda, or mps. Default: auto.",
                },
            },
            "required": ["workflow_path"],
        },
        "execute": execute_run,
    })

    # ── Tool 2: Analyze a workflow ─────────────────────────────────

    def execute_analyze(workflow_path="", **_kw):
        if not workflow_path:
            return json.dumps({"status": "error",
                               "error": "workflow_path is required"})

        wf_path = Path(workflow_path)
        if not wf_path.exists():
            return json.dumps({"status": "error",
                               "error": f"File not found: {workflow_path}"})

        try:
            workflow = json.loads(wf_path.read_text())
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error",
                               "error": f"Invalid JSON: {e}"})

        try:
            from ghost_comfyui_engine import analyze_workflow
            analysis = analyze_workflow(workflow)
            return json.dumps({"status": "ok", "analysis": analysis}, default=str)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "comfyui_analyze",
        "description": (
            "Analyze a ComfyUI workflow JSON file without executing it. "
            "Reports: required models, node types (and which need ComfyUI), "
            "input parameters, output nodes, and whether it can run natively."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_path": {
                    "type": "string",
                    "description": "Path to a ComfyUI workflow .json file.",
                },
            },
            "required": ["workflow_path"],
        },
        "execute": execute_analyze,
    })

    # ── Tool 3: Import workflow as a Ghost node ────────────────────

    def execute_import(workflow_path="", node_name="", description="",
                       **_kw):
        if not workflow_path:
            return json.dumps({"status": "error",
                               "error": "workflow_path is required"})
        if not node_name:
            return json.dumps({"status": "error",
                               "error": "node_name is required"})

        wf_path = Path(workflow_path)
        if not wf_path.exists():
            return json.dumps({"status": "error",
                               "error": f"File not found: {workflow_path}"})

        try:
            workflow = json.loads(wf_path.read_text())
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error",
                               "error": f"Invalid JSON: {e}"})

        try:
            from ghost_comfyui_engine import generate_ghost_node

            result = generate_ghost_node(
                workflow=workflow,
                name=node_name,
                description=description,
            )
            return json.dumps(result, default=str)
        except Exception as e:
            log.error("Workflow import error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "comfyui_import",
        "description": (
            "Convert a ComfyUI workflow JSON into a standalone Ghost node. "
            "Creates a new node directory with NODE.yaml, node.py, and the "
            "bundled workflow. The generated node has proper input parameters "
            "(images, prompts, seed, etc.) auto-extracted from the workflow. "
            "After import, enable the new node to use it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_path": {
                    "type": "string",
                    "description": "Path to a ComfyUI workflow .json file.",
                },
                "node_name": {
                    "type": "string",
                    "description": "Name for the new Ghost node (e.g. 'my-virtual-tryon').",
                },
                "description": {
                    "type": "string",
                    "description": "What this workflow does.",
                },
            },
            "required": ["workflow_path", "node_name"],
        },
        "execute": execute_import,
    })
