"""Audit Log API — query and view security audit logs."""

import logging
from flask import Blueprint, jsonify, request

from ghost_dashboard.rate_limiter import rate_limit

import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_audit_log import get_audit_log, AuditAction

bp = Blueprint("audit", __name__)


@bp.route("/api/audit")
@rate_limit(requests_per_minute=60)
def list_audit_entries():
    """Query audit log entries with optional filters."""
    audit = get_audit_log()
    
    # Parse query parameters
    action = request.args.get("action", "")
    resource_type = request.args.get("resource_type", "")
    resource_id = request.args.get("resource_id", "")
    success_param = request.args.get("success", "")
    since = request.args.get("since", "")
    until = request.args.get("until", "")
    
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        limit = 100
        offset = 0
    
    # Convert success to boolean if provided
    success = None
    if success_param.lower() == "true":
        success = True
    elif success_param.lower() == "false":
        success = False
    
    entries = audit.query(
        action=action or None,
        resource_type=resource_type or None,
        resource_id=resource_id or None,
        success=success,
        since=since or None,
        until=until or None,
        limit=limit,
        offset=offset,
    )
    
    return jsonify({
        "entries": entries,
        "count": len(entries),
        "filters": {
            "action": action or None,
            "resource_type": resource_type or None,
            "resource_id": resource_id or None,
            "success": success,
            "since": since or None,
            "until": until or None,
        },
    })


@bp.route("/api/audit/stats")
@rate_limit(requests_per_minute=60)
def get_audit_stats():
    """Get audit log statistics."""
    audit = get_audit_log()
    stats = audit.get_stats()
    return jsonify(stats)


@bp.route("/api/audit/actions")
@rate_limit(requests_per_minute=60)
def list_audit_actions():
    """List all available audit action types."""
    actions = [
        {"value": a.value, "category": a.value.split(".")[0]}
        for a in AuditAction
    ]
    return jsonify({"actions": actions})


@bp.route("/api/audit/export", methods=["POST"])
@rate_limit(requests_per_minute=5)
def export_audit_log():
    """Export audit log entries as JSON."""
    data = request.get_json(silent=True) or {}
    
    since = data.get("since", "")
    until = data.get("until", "")
    
    audit = get_audit_log()
    entries = audit.query(
        since=since or None,
        until=until or None,
        limit=10000,  # Export up to 10k entries
    )
    
    return jsonify({
        "exported_at": audit._get_timestamp(),
        "count": len(entries),
        "entries": entries,
    })
