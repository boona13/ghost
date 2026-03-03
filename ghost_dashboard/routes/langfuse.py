"""Langfuse API — observability and tracing endpoints."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_langfuse import (
    get_langfuse_manager,
    get_recent_traces,
    get_trace_stats,
    test_connection,
)
from ghost import load_config

bp = Blueprint("langfuse", __name__, url_prefix="/api/langfuse")


def _mask_key(key: str) -> str:
    """Mask sensitive API keys for display."""
    if not key:
        return ""
    if len(key) > 12:
        return key[:8] + "..." + key[-4:]
    return "***"


@bp.route("/status")
def get_status():
    """Get Langfuse connection status and configuration."""
    cfg = load_config()
    
    enabled = cfg.get("enable_langfuse", False)
    host = cfg.get("langfuse_host", "https://cloud.langfuse.com")
    public_key = cfg.get("langfuse_public_key", "")
    secret_key = cfg.get("langfuse_secret_key", "")
    
    manager = get_langfuse_manager()
    client = manager.get_client() if manager else None
    
    is_configured = False
    if client and client.enabled:
        is_configured = bool(public_key and secret_key)
    
    return jsonify({
        "enabled": enabled,
        "configured": is_configured,
        "host": host,
        "public_key_masked": _mask_key(public_key),
        "has_credentials": bool(public_key and secret_key),
    })


@bp.route("/traces")
def get_traces():
    """Get recent traces with optional filtering."""
    limit = request.args.get("limit", 50, type=int)
    session_id = request.args.get("session_id", None)
    
    # Cap limit to prevent abuse
    limit = min(max(limit, 1), 100)
    
    traces = get_recent_traces(limit=limit, session_id=session_id)
    
    return jsonify({
        "traces": traces,
        "count": len(traces),
    })


@bp.route("/stats")
def get_stats():
    """Get aggregated trace statistics."""
    hours = request.args.get("hours", 24, type=int)
    
    # Cap hours to prevent abuse
    hours = min(max(hours, 1), 168)  # Max 1 week
    
    stats = get_trace_stats(hours=hours)
    
    return jsonify(stats)


@bp.route("/test", methods=["POST"])
def post_test():
    """Test connection to Langfuse server."""
    cfg = load_config()
    result = test_connection(cfg)
    
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code
