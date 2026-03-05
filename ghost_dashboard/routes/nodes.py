"""GhostNodes API — node management, GPU status, and pipeline operations."""

import json
import logging
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("nodes", __name__)


def _get_daemon():
    from ghost_dashboard import get_daemon
    return get_daemon()


@bp.route("/api/nodes")
def list_nodes():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"nodes": [], "categories": [], "error": "Node system not initialized"})

    category = request.args.get("category", "")
    nodes = daemon.node_manager.list_nodes(category=category or None)
    categories = {}
    for n in nodes:
        m = n.get("manifest") or {}
        cat = m.get("category", "utility")
        categories.setdefault(cat, 0)
        categories[cat] += 1

    return jsonify({
        "nodes": nodes,
        "total": len(nodes),
        "categories": categories,
        "nodes_dir": str(daemon.node_manager.nodes_dir),
    })


@bp.route("/api/nodes/<name>")
def get_node(name):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    info = daemon.node_manager.get_node(name)
    if not info:
        return jsonify({"error": "Node not found"}), 404
    return jsonify(info.to_dict())


@bp.route("/api/nodes/<name>/enable", methods=["POST"])
def enable_node(name):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    ok = daemon.node_manager.enable_node(name)
    return jsonify({"ok": ok, "message": f"Enabled {name}" if ok else "Node not found"})


@bp.route("/api/nodes/<name>/disable", methods=["POST"])
def disable_node(name):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    ok = daemon.node_manager.disable_node(name)
    return jsonify({"ok": ok, "message": f"Disabled {name}" if ok else "Node not found"})


@bp.route("/api/nodes/install", methods=["POST"])
def install_node():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    data = request.get_json(silent=True) or {}
    source = data.get("source", "")
    if not source:
        return jsonify({"error": "source is required"}), 400

    if source.startswith("http") and "github" in source:
        result = daemon.node_manager.install_from_github(source)
    else:
        result = daemon.node_manager.install_local(source)
    return jsonify(result)


@bp.route("/api/nodes/<name>/uninstall", methods=["POST"])
def uninstall_node(name):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    ok = daemon.node_manager.uninstall_node(name)
    return jsonify({"ok": ok})


@bp.route("/api/gpu/status")
def gpu_status():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "resource_manager") or not daemon.resource_manager:
        return jsonify({"error": "Resource manager not initialized", "device": {"best_device": "unknown"}}), 503

    return jsonify(daemon.resource_manager.get_status())


@bp.route("/api/gpu/unload", methods=["POST"])
def gpu_unload():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "resource_manager") or not daemon.resource_manager:
        return jsonify({"error": "Resource manager not initialized"}), 503

    data = request.get_json(silent=True) or {}
    model_id = data.get("model_id", "")
    if not model_id:
        return jsonify({"error": "model_id required"}), 400

    ok = daemon.resource_manager.release(model_id)
    return jsonify({"ok": ok})


@bp.route("/api/gpu/metrics")
def gpu_metrics():
    """Comprehensive load balancer metrics: per-model stats, eviction scores,
    cache hit rates, queue depth, and load times."""
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "resource_manager") or not daemon.resource_manager:
        return jsonify({"error": "Resource manager not initialized"}), 503

    rm = daemon.resource_manager
    if hasattr(rm, "get_metrics"):
        return jsonify(rm.get_metrics())
    return jsonify(rm.get_status())


@bp.route("/api/gpu/queue")
def gpu_queue():
    """Current model load queue — models waiting for the load gate."""
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "resource_manager") or not daemon.resource_manager:
        return jsonify({"error": "Resource manager not initialized"}), 503

    rm = daemon.resource_manager
    if hasattr(rm, "get_queue"):
        return jsonify({"queue": rm.get_queue(), "currently_loading": rm._gate_holder})
    return jsonify({"queue": [], "currently_loading": None})


@bp.route("/api/pipelines")
def list_pipelines():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"pipelines": [], "error": "Pipeline engine not initialized"})

    limit = request.args.get("limit", 20, type=int)
    pipelines = daemon.pipeline_engine.list_pipelines(limit=limit)
    return jsonify({"pipelines": pipelines, "total": len(pipelines)})


@bp.route("/api/pipelines/<pipeline_id>")
def get_pipeline(pipeline_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"error": "Pipeline engine not initialized"}), 503

    pipeline = daemon.pipeline_engine.get(pipeline_id)
    if not pipeline:
        return jsonify({"error": "Pipeline not found"}), 404
    return jsonify(pipeline.to_dict())


@bp.route("/api/pipelines", methods=["POST"])
def create_pipeline():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"error": "Pipeline engine not initialized"}), 503

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    steps = data.get("steps", [])
    description = data.get("description", "")
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not steps or not isinstance(steps, list):
        return jsonify({"error": "steps must be a non-empty array"}), 400

    for i, s in enumerate(steps):
        if "tool_name" not in s:
            return jsonify({"error": f"Step {i} missing tool_name"}), 400

    try:
        pipeline = daemon.pipeline_engine.create(name, steps, description=description)
        return jsonify({"ok": True, "pipeline": pipeline.to_dict()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/pipelines/<pipeline_id>/run", methods=["POST"])
def run_pipeline(pipeline_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"error": "Pipeline engine not initialized"}), 503

    data = request.get_json(silent=True) or {}
    async_mode = data.get("async", False)

    try:
        if async_mode:
            daemon.pipeline_engine.execute_async(pipeline_id)
            return jsonify({"ok": True, "message": f"Pipeline {pipeline_id} started in background"})
        pipeline = daemon.pipeline_engine.execute(pipeline_id)
        return jsonify({"ok": True, "pipeline": pipeline.to_dict()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@bp.route("/api/pipelines/<pipeline_id>/cancel", methods=["POST"])
def cancel_pipeline(pipeline_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"error": "Pipeline engine not initialized"}), 503

    ok = daemon.pipeline_engine.cancel(pipeline_id)
    return jsonify({"ok": ok})


@bp.route("/api/pipelines/<pipeline_id>", methods=["DELETE"])
def delete_pipeline(pipeline_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "pipeline_engine") or not daemon.pipeline_engine:
        return jsonify({"error": "Pipeline engine not initialized"}), 503

    ok = daemon.pipeline_engine.delete(pipeline_id)
    return jsonify({"ok": ok})


# ── ComfyUI Workflow Endpoints ──────────────────────────────────────

@bp.route("/api/comfyui/analyze", methods=["POST"])
def comfyui_analyze():
    """Analyze a ComfyUI workflow JSON (upload or path)."""
    try:
        from ghost_comfyui_engine import analyze_workflow

        data = request.get_json(silent=True) or {}
        workflow_path = data.get("workflow_path", "")
        workflow_json = data.get("workflow")

        if workflow_json:
            analysis = analyze_workflow(workflow_json)
            return jsonify({"ok": True, "analysis": analysis})

        if workflow_path:
            from pathlib import Path
            p = Path(workflow_path)
            if not p.exists():
                return jsonify({"ok": False, "error": f"File not found: {workflow_path}"}), 404
            import json as json_mod
            workflow_json = json_mod.loads(p.read_text())
            analysis = analyze_workflow(workflow_json)
            return jsonify({"ok": True, "analysis": analysis})

        return jsonify({"ok": False, "error": "Provide workflow (JSON body) or workflow_path"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 400


@bp.route("/api/comfyui/import", methods=["POST"])
def comfyui_import():
    """Import a ComfyUI workflow as a Ghost node."""
    try:
        from ghost_comfyui_engine import generate_ghost_node

        data = request.get_json(silent=True) or {}
        workflow = data.get("workflow")
        node_name = data.get("node_name", "").strip()
        description = data.get("description", "")

        if not workflow:
            return jsonify({"ok": False, "error": "workflow JSON is required"}), 400
        if not node_name:
            return jsonify({"ok": False, "error": "node_name is required"}), 400

        result = generate_ghost_node(
            workflow=workflow,
            name=node_name,
            description=description,
        )

        if result.get("status") == "error":
            return jsonify({"ok": False, "error": result["error"]}), 400

        daemon = _get_daemon()
        if daemon and hasattr(daemon, "node_manager") and daemon.node_manager:
            daemon.node_manager.discover_all()
            if node_name in daemon.node_manager.nodes:
                daemon.node_manager._load_node(node_name)

        return jsonify({"ok": True, "result": result})
    except Exception as e:
        log.error("ComfyUI import error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)[:500]}), 500


@bp.route("/api/comfyui/upload", methods=["POST"])
def comfyui_upload():
    """Upload a workflow JSON file for analysis."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename or not f.filename.endswith(".json"):
        return jsonify({"ok": False, "error": "File must be a .json file"}), 400

    try:
        content = f.read().decode("utf-8")
        workflow = json.loads(content)
        from ghost_comfyui_engine import analyze_workflow
        analysis = analyze_workflow(workflow)
        return jsonify({"ok": True, "workflow": workflow, "analysis": analysis})
    except json.JSONDecodeError as e:
        return jsonify({"ok": False, "error": f"Invalid JSON: {e}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 500


@bp.route("/api/nodes/hf-test", methods=["POST"])
def test_hf_token():
    """Validate a HuggingFace token by calling the whoami API."""
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "No token provided"})
    try:
        from huggingface_hub import HfApi
        hf = HfApi(token=token)
        info = hf.whoami()
        username = info.get("name", "unknown")
        return jsonify({
            "ok": True,
            "message": f"Authenticated as: {username}",
            "username": username,
        })
    except ImportError:
        return jsonify({"ok": False, "error": "huggingface-hub not installed"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]})


# ── HuggingFace OAuth Device Code Flow ─────────────────────────────

import urllib.request
import urllib.parse

_HF_DEVICE_URL = "https://huggingface.co/oauth/device"
_HF_TOKEN_URL = "https://huggingface.co/oauth/token"


@bp.route("/api/nodes/hf-device-start", methods=["POST"])
def hf_device_start():
    """Initiate HuggingFace OAuth device code flow."""
    data = request.get_json(silent=True) or {}
    client_id = data.get("client_id", "").strip()
    if not client_id:
        daemon = _get_daemon()
        if daemon:
            client_id = daemon.cfg.get("hf_oauth_client_id", "")
    if not client_id:
        return jsonify({
            "ok": False,
            "error": "No OAuth client_id configured. Create a public OAuth app at huggingface.co/settings/applications/new first.",
        })
    try:
        body = urllib.parse.urlencode({
            "client_id": client_id,
            "scope": "openid profile read-repos",
        }).encode()
        req = urllib.request.Request(
            _HF_DEVICE_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
        return jsonify({
            "ok": True,
            "device_code": result["device_code"],
            "user_code": result["user_code"],
            "verification_uri": result.get("verification_uri", "https://huggingface.co/device"),
            "expires_in": result.get("expires_in", 900),
            "interval": result.get("interval", 5),
        })
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.readable() else str(e)
        log.warning("HF device start failed: %s %s", e.code, error_body[:200])
        return jsonify({"ok": False, "error": f"HuggingFace returned {e.code}: {error_body[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]})


@bp.route("/api/nodes/hf-device-poll", methods=["POST"])
def hf_device_poll():
    """Poll HuggingFace for device code authorization result."""
    data = request.get_json(silent=True) or {}
    device_code = data.get("device_code", "").strip()
    client_id = data.get("client_id", "").strip()
    if not client_id:
        daemon = _get_daemon()
        if daemon:
            client_id = daemon.cfg.get("hf_oauth_client_id", "")
    if not device_code or not client_id:
        return jsonify({"ok": False, "error": "Missing device_code or client_id"})
    try:
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": client_id,
        }).encode()
        req = urllib.request.Request(
            _HF_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        access_token = result.get("access_token")
        if not access_token:
            return jsonify({"ok": False, "status": "pending", "error": result.get("error", "unknown")})

        from huggingface_hub import HfApi
        hf = HfApi(token=access_token)
        info = hf.whoami()
        username = info.get("name", "unknown")

        from ghost import load_config, save_config
        cfg = load_config()
        cfg["hf_token"] = access_token
        save_config(cfg)

        try:
            from huggingface_hub import login
            login(token=access_token, add_to_git_credential=False)
        except Exception:
            pass

        daemon = _get_daemon()
        if daemon:
            daemon.cfg["hf_token"] = access_token

        return jsonify({
            "ok": True,
            "status": "authorized",
            "username": username,
            "message": f"Logged in as: {username}",
        })

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode()
            err_json = json.loads(error_body)
            hf_error = err_json.get("error", "")
            if hf_error in ("authorization_pending", "slow_down"):
                return jsonify({"ok": False, "status": "pending", "error": hf_error})
        except Exception:
            pass
        return jsonify({"ok": False, "status": "error", "error": f"HTTP {e.code}: {error_body[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "status": "error", "error": str(e)[:200]})
