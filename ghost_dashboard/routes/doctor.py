"""Doctor API — health checks and auto-fixes for Ghost."""

from flask import Blueprint, jsonify, request
from typing import Any, Dict, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import load_config

bp = Blueprint("doctor", __name__)


def _get_daemon():
    """Get the embedded daemon instance if available."""
    try:
        from ghost_dashboard import get_daemon
        return get_daemon()
    except (ImportError, AttributeError, RuntimeError) as e:
        import logging
        logging.getLogger(__name__).debug(f"Daemon not available in doctor routes: {e}")
        return None


def _call_doctor_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Call a doctor tool via daemon or fallback to direct invocation."""
    daemon = _get_daemon()
    
    if daemon and hasattr(daemon, 'tool_registry') and daemon.tool_registry:
        tool = daemon.tool_registry.get(tool_name)
        if tool and callable(tool.get("execute")):
            try:
                result = tool["execute"](**args)
                if isinstance(result, dict):
                    return {"ok": True, **result}
                return {"ok": True, "result": result}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    
    # Fallback: direct invocation using GhostDoctor
    try:
        from ghost_doctor import GhostDoctor
        cfg = load_config()
        daemon_refs = {}
        if daemon:
            daemon_refs = {
                "cron": getattr(daemon, 'cron', None),
                "memory": getattr(daemon, 'memory', None),
                "skills": getattr(daemon, 'skills', None),
                "identity": getattr(daemon, 'identity', None),
            }
        doctor = GhostDoctor(config=cfg, daemon_refs=daemon_refs)
        
        if tool_name == "doctor_run":
            result = doctor.run()
            return {"ok": True, **result}
        elif tool_name == "doctor_fix":
            check_ids = args.get("check_ids", [])
            dry_run = args.get("dry_run", True)
            result = doctor.fix(check_ids=check_ids, dry_run=dry_run)
            return {"ok": True, **result}
        else:
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"ok": False, "error": f"Direct invocation failed: {str(e)}"}


@bp.route("/api/doctor/run", methods=["POST"])
def doctor_run():
    """Run structured Ghost health checks and return findings.
    
    POST /api/doctor/run
    
    Returns:
        {
            "ok": true,
            "timestamp": "2026-03-01T21:30:00Z",
            "summary": {"ok": 5, "warn": 1, "fail": 0},
            "checks": [...]
        }
    """
    result = _call_doctor_tool("doctor_run", {})
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


@bp.route("/api/doctor/fix", methods=["POST"])
def doctor_fix():
    """Apply safe doctor auto-fixes, optionally in dry-run mode.
    
    POST /api/doctor/fix
    Body: {
        "check_ids": ["providers.credentials", "cron.service"],  // optional
        "dry_run": true  // default: true
    }
    
    Returns:
        {
            "ok": true,
            "timestamp": "2026-03-01T21:30:00Z",
            "dry_run": true,
            "fixes": [...],
            "post_check": {...}
        }
    """
    data = request.get_json(silent=True) or {}
    
    # Validate check_ids if provided
    check_ids = data.get("check_ids")
    if check_ids is not None:
        if not isinstance(check_ids, list):
            return jsonify({"ok": False, "error": "check_ids must be a list"}), 400
        if len(check_ids) > 100:
            return jsonify({"ok": False, "error": "check_ids exceeds maximum of 100 items"}), 400
        for item in check_ids:
            if not isinstance(item, str):
                return jsonify({"ok": False, "error": "check_ids must contain only strings"}), 400
            if len(item) > 128:
                return jsonify({"ok": False, "error": f"check_id exceeds 128 chars: {item[:20]}..."}), 400
            if not all(c.isalnum() or c in '.-_' for c in item):
                return jsonify({"ok": False, "error": f"check_id contains invalid characters: {item}"}), 400
    
    dry_run = bool(data.get("dry_run", True))
    
    args = {
        "check_ids": check_ids or [],
        "dry_run": dry_run,
    }
    
    result = _call_doctor_tool("doctor_fix", args)
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code
