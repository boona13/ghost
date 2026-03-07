"""GhostNodes API — node management, GPU status, pipeline operations, and tool execution."""

import json
import logging
import threading
import time
from flask import Blueprint, jsonify, request, send_file
from ghost_dashboard.rate_limiter import rate_limit

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
@rate_limit(requests_per_minute=10)
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


@bp.route("/api/nodes/browse")
def browse_files():
    """Browse directories and files for the file picker.
    Restricted to user home directory and below."""
    from pathlib import Path

    req_path = request.args.get("path", "")
    exts = request.args.get("ext", "")
    ext_set = set(e.strip().lower() for e in exts.split(",") if e.strip()) if exts else None

    if not req_path:
        home = str(Path.home())
        req_path = home

    target = Path(req_path).resolve()
    home_root = Path.home().resolve()

    if not target.is_relative_to(home_root):
        return jsonify({"error": "Access denied"}), 403

    if not target.exists():
        return jsonify({"error": "Path not found"}), 404

    if target.is_file():
        return jsonify({"path": str(target), "is_file": True})

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff"}
    _AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}
    _VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}

    def _file_kind(suffix):
        s = suffix.lower()
        if s in _IMAGE_EXTS:
            return "image"
        if s in _AUDIO_EXTS:
            return "audio"
        if s in _VIDEO_EXTS:
            return "video"
        return "other"

    dirs = []
    files = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif entry.is_file():
                if ext_set and entry.suffix.lower().lstrip(".") not in ext_set:
                    continue
                files.append({
                    "name": entry.name,
                    "path": str(entry),
                    "size": entry.stat().st_size,
                    "kind": _file_kind(entry.suffix),
                })
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

    daemon = _get_daemon()
    media_dir = ""
    if daemon and hasattr(daemon, "media_store") and daemon.media_store:
        from ghost_media_store import MEDIA_DIR
        media_dir = str(MEDIA_DIR / "images")

    return jsonify({
        "current": str(target),
        "parent": str(target.parent) if target != home_root else None,
        "dirs": dirs,
        "files": files,
        "media_dir": media_dir,
    })


_SETTINGS_FILE = None


def _settings_path():
    global _SETTINGS_FILE
    if _SETTINGS_FILE is None:
        from pathlib import Path
        p = Path.home() / ".ghost" / "node_settings.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE = p
    return _SETTINGS_FILE


def _load_all_settings():
    p = _settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_all_settings(data):
    _settings_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


@bp.route("/api/nodes/settings/<node_name>/<tool_name>")
def get_tool_settings(node_name, tool_name):
    """Load saved user settings for a specific node+tool."""
    all_s = _load_all_settings()
    key = f"{node_name}/{tool_name}"
    return jsonify({"settings": all_s.get(key, {}), "key": key})


@bp.route("/api/nodes/settings/<node_name>/<tool_name>", methods=["POST"])
def save_tool_settings(node_name, tool_name):
    """Save user settings for a specific node+tool."""
    data = request.get_json(silent=True) or {}
    settings = data.get("settings", {})
    all_s = _load_all_settings()
    key = f"{node_name}/{tool_name}"
    all_s[key] = settings
    _save_all_settings(all_s)
    return jsonify({"ok": True, "key": key})


@bp.route("/api/nodes/<name>/tools")
def get_node_tools(name):
    """Return full tool definitions (name, description, parameters) for a node."""
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    info = daemon.node_manager.get_node(name)
    if not info:
        return jsonify({"error": "Node not found"}), 404
    if not info.loaded or not info.tools:
        return jsonify({"tools": [], "node": name})

    registry = getattr(daemon, "tool_registry", None)
    if not registry:
        return jsonify({"tools": [], "node": name})

    tools = []
    for tool_name in info.tools:
        tool_def = registry.get(tool_name)
        if tool_def:
            tools.append({
                "name": tool_def.get("name", tool_name),
                "description": tool_def.get("description", ""),
                "parameters": tool_def.get("parameters", {"type": "object", "properties": {}}),
            })
    return jsonify({"tools": tools, "node": name})


_run_jobs = {}
_run_lock = threading.Lock()
_JOB_TTL = 600


def _cleanup_stale_jobs():
    now = time.time()
    with _run_lock:
        stale = [jid for jid, j in _run_jobs.items()
                 if j.get("finished_at") and now - j["finished_at"] > _JOB_TTL]
        for jid in stale:
            _run_jobs.pop(jid, None)


@bp.route("/api/nodes/<name>/run", methods=["POST"])
def run_node_tool(name):
    """Start async execution of a node's tool. Returns a job_id for polling."""
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "node_manager") or not daemon.node_manager:
        return jsonify({"error": "Node system not initialized"}), 503

    info = daemon.node_manager.get_node(name)
    if not info:
        return jsonify({"error": "Node not found"}), 404
    if not info.loaded:
        return jsonify({"error": f"Node '{name}' is not loaded"}), 400

    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool", "")
    args = data.get("args", {})

    if not tool_name:
        return jsonify({"error": "tool name is required"}), 400
    if tool_name not in (info.tools or []):
        return jsonify({"error": f"Tool '{tool_name}' not found in node '{name}'"}), 404

    registry = getattr(daemon, "tool_registry", None)
    if not registry:
        return jsonify({"error": "Tool registry not available"}), 503

    tool_def = registry.get(tool_name)
    if not tool_def or not callable(tool_def.get("execute")):
        return jsonify({"error": f"Tool '{tool_name}' not executable"}), 500

    tool_params = (tool_def.get("parameters") or {}).get("properties", {})

    saved = _load_all_settings().get(f"{name}/{tool_name}", {})
    for param_key in tool_params:
        if param_key not in args and param_key in saved:
            args[param_key] = saved[param_key]

    import uuid as _uuid
    job_id = _uuid.uuid4().hex[:12]
    job = {
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "node": name,
        "tool": tool_name,
        "message": "Starting...",
        "result": None,
        "error": None,
    }
    with _run_lock:
        _run_jobs[job_id] = job

    _cleanup_stale_jobs()

    def _execute():
        try:
            job["message"] = "Loading model..."
            raw = tool_def["execute"](**args)
            if isinstance(raw, str):
                try:
                    result = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    result = {"status": "ok", "raw": raw}
            elif isinstance(raw, dict):
                result = raw
            else:
                result = {"status": "ok", "raw": str(raw)}
            job["status"] = "complete"
            job["result"] = result
            job["message"] = "Done"
        except Exception as e:
            log.error("Tool execution error (%s/%s): %s", name, tool_name, e, exc_info=True)
            job["status"] = "error"
            job["error"] = str(e)[:500]
            job["message"] = "Failed"
        finally:
            job["finished_at"] = time.time()

    t = threading.Thread(target=_execute, daemon=True)
    t.start()

    return jsonify({"ok": True, "job_id": job_id})


@bp.route("/api/nodes/run-status/<job_id>")
def run_status(job_id):
    """Poll job status. Returns status, elapsed time, message, and result when done."""
    with _run_lock:
        job = _run_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    now = time.time()
    elapsed = round(now - job["started_at"], 1)

    resp = {
        "status": job["status"],
        "elapsed": elapsed,
        "message": job.get("message", ""),
        "node": job.get("node", ""),
        "tool": job.get("tool", ""),
    }

    if job["status"] == "running":
        if elapsed < 3:
            resp["message"] = "Starting..."
        elif elapsed < 10:
            resp["message"] = "Loading model..."
        elif elapsed < 30:
            resp["message"] = "Processing..."
        elif elapsed < 60:
            resp["message"] = "Generating output..."
        else:
            resp["message"] = "Still working... (large models take time)"

    elif job["status"] == "complete":
        resp["result"] = job["result"]
        total = round(job["finished_at"] - job["started_at"], 1)
        resp["elapsed"] = total

    elif job["status"] == "error":
        resp["error"] = job.get("error", "Unknown error")

    return jsonify(resp)


@bp.route("/api/nodes/upload-file", methods=["POST"])
def upload_file():
    """Accept a file upload, save to media staging, return the server path."""
    from pathlib import Path
    from ghost_media_store import MEDIA_DIR
    import uuid as _uuid

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    safe_name = f"{_uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
    upload_dir = MEDIA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    f.save(str(dest))

    return jsonify({"ok": True, "path": str(dest), "name": f.filename})


@bp.route("/api/nodes/serve-file")
def serve_result_file():
    """Serve a result file (image/audio/video) by absolute path.
    Only allows files inside the Ghost media directory."""
    daemon = _get_daemon()
    file_path = request.args.get("path", "")
    if not file_path:
        return jsonify({"error": "path required"}), 400

    from pathlib import Path
    fp = Path(file_path).resolve()

    allowed_roots = [Path.home().resolve()]
    try:
        from ghost_media_store import MEDIA_DIR
        allowed_roots.append(MEDIA_DIR.resolve())
    except ImportError:
        pass

    if not any(fp.is_relative_to(root) for root in allowed_roots):
        return jsonify({"error": "Access denied"}), 403

    if not fp.exists() or not fp.is_file():
        return jsonify({"error": "File not found"}), 404

    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4",
        ".webm": "video/webm", ".ogg": "audio/ogg", ".flac": "audio/flac",
        ".m4a": "audio/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
        ".bmp": "image/bmp", ".tiff": "image/tiff",
        ".obj": "model/obj", ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json", ".stl": "model/stl",
    }
    mime = mime_map.get(fp.suffix.lower(), "application/octet-stream")
    try:
        return send_file(str(fp), mimetype=mime)
    except Exception as e:
        log.error("serve-file error for %s: %s", fp, e)
        return jsonify({"error": "Failed to serve file"}), 500


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
            result = json.loads(resp.read().decode("utf-8"))
        return jsonify({
            "ok": True,
            "device_code": result["device_code"],
            "user_code": result["user_code"],
            "verification_uri": result.get("verification_uri", "https://huggingface.co/device"),
            "expires_in": result.get("expires_in", 900),
            "interval": result.get("interval", 5),
        })
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.readable() else str(e)
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
            result = json.loads(resp.read().decode("utf-8"))

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
            error_body = e.read().decode("utf-8")
            err_json = json.loads(error_body)
            hf_error = err_json.get("error", "")
            if hf_error in ("authorization_pending", "slow_down"):
                return jsonify({"ok": False, "status": "pending", "error": hf_error})
        except Exception:
            pass
        return jsonify({"ok": False, "status": "error", "error": f"HTTP {e.code}: {error_body[:200]}"})
    except Exception as e:
        return jsonify({"ok": False, "status": "error", "error": str(e)[:200]})
