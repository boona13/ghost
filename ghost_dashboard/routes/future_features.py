"""Future Features API — backlog management for autonomous feature implementation."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_future_features import FutureFeaturesStore, FeatureChangelog, FEATURE_STATUSES, FEATURE_SOURCES

bp = Blueprint("future_features", __name__, url_prefix="/api/future-features")
store = FutureFeaturesStore()
changelog = FeatureChangelog()

# Set by GhostDaemon to trigger the queue processor when state changes.
_on_queue_trigger = None
# Direct fire: bypass queue guard (for explicit user "Start" clicks).
_on_force_fire = None

def set_queue_trigger(fn):
    """Register a callback for queue state changes (approve, complete, fail)."""
    global _on_queue_trigger
    _on_queue_trigger = fn

def set_force_fire(fn):
    """Register a callback to fire the implementer directly (no guard check)."""
    global _on_force_fire
    _on_force_fire = fn

def _notify_queue():
    """Safely invoke the queue trigger callback."""
    if _on_queue_trigger:
        try:
            _on_queue_trigger()
        except Exception:
            log.warning("_notify_queue callback failed", exc_info=True)

def _force_fire_implementer():
    """Fire the implementer directly, bypassing the queue guard."""
    if _on_force_fire:
        try:
            _on_force_fire()
        except Exception:
            log.warning("_force_fire_implementer callback failed", exc_info=True)


@bp.route("/list")
def list_features():
    """List features with optional status filter."""
    status = request.args.get("status", "")
    limit = request.args.get("limit", 50, type=int)
    
    if status:
        items = store.get_all(status_filter=status)[:limit]
    else:
        items = store.get_all()[:limit]
    
    return jsonify({"ok": True, "features": items})


@bp.route("/pending")
def pending_features():
    """Get pending/approval_required features sorted by priority."""
    limit = request.args.get("limit", 20, type=int)
    items = store.get_pending(limit)
    return jsonify({"ok": True, "features": items})


@bp.route("/stats")
def feature_stats():
    """Get feature statistics."""
    stats = store.get_stats()
    return jsonify({"ok": True, "stats": stats})


@bp.route("/counts")
def feature_counts():
    """Get counts by status."""
    counts = store.count_by_status()
    return jsonify({"ok": True, "counts": counts})


@bp.route("/<feature_id>")
def get_feature(feature_id):
    """Get a single feature by ID."""
    item = store.get_by_id(feature_id)
    if not item:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    return jsonify({"ok": True, "feature": item})


@bp.route("/add", methods=["POST"])
def add_feature():
    """Add a new feature to the backlog."""
    data = request.get_json() or {}
    
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    
    if not title or not description:
        return jsonify({"ok": False, "error": "Title and description required"}), 400
    
    feature = store.add(
        title=title,
        description=description,
        priority=data.get("priority", "P2"),
        source=data.get("source", "user"),
        source_detail=data.get("source_detail", ""),
        estimated_effort=data.get("estimated_effort", "medium"),
        auto_implement=data.get("auto_implement", True),
        tags=data.get("tags", []),
        affected_files=data.get("affected_files", ""),
        proposed_approach=data.get("proposed_approach", ""),
        category=data.get("category", "feature"),
    )

    is_duplicate = feature.get("_warning")
    if not is_duplicate and feature.get("status") == "pending":
        _notify_queue()

    # Strip internal flags before returning to client
    clean = {k: v for k, v in feature.items() if not k.startswith("_")}
    return jsonify({"ok": True, "feature": clean, "duplicate": bool(is_duplicate)})


@bp.route("/<feature_id>/approve", methods=["POST"])
def approve_feature(feature_id):
    """Approve a feature for implementation."""
    ok = store.approve(feature_id)
    if not ok:
        return jsonify({"ok": False, "error": "Feature not found or already approved"}), 400
    _notify_queue()
    return jsonify({"ok": True})


@bp.route("/<feature_id>/start", methods=["POST"])
def start_feature(feature_id):
    """Mark a feature as in progress and fire the implementer."""
    ok, error = store.mark_in_progress(feature_id)
    if not ok:
        return jsonify({"ok": False, "error": error or "Feature not found"}), 409
    _force_fire_implementer()
    return jsonify({"ok": True})


@bp.route("/<feature_id>/complete", methods=["POST"])
def complete_feature(feature_id):
    """Mark a feature as completed."""
    data = request.get_json() or {}
    summary = data.get("summary", "")
    
    item = store.get_by_id(feature_id)
    if not item:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    
    store.mark_implemented(feature_id, summary)
    changelog.add(item, summary)
    _notify_queue()
    
    return jsonify({"ok": True})


@bp.route("/<feature_id>/fail", methods=["POST"])
def fail_feature(feature_id):
    """Mark a feature as failed."""
    data = request.get_json() or {}
    error = data.get("error", "")
    
    ok = store.mark_failed(feature_id, error)
    if not ok:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    _notify_queue()
    
    return jsonify({"ok": True})


@bp.route("/<feature_id>/reject", methods=["POST"])
def reject_feature(feature_id):
    """Reject a feature."""
    data = request.get_json() or {}
    reason = data.get("reason", "")
    
    ok = store.reject(feature_id, reason)
    if not ok:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    
    return jsonify({"ok": True})


@bp.route("/<feature_id>/retry", methods=["POST"])
def retry_feature(feature_id):
    """Reset a failed/deferred feature back to pending and fire the implementer.

    Follows the same queue discipline as the Start button: resets to pending,
    then marks in_progress (which rejects if another feature is already running),
    then fires the implementer directly.
    """
    item = store.get_by_id(feature_id)
    if not item:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    if item.get("status") not in ("failed", "deferred"):
        return jsonify({"ok": False, "error": "Only failed or deferred features can be retried"}), 400
    store._update_status(feature_id, "pending", "Retried by user")
    ok, error = store.mark_in_progress(feature_id)
    if not ok:
        return jsonify({"ok": False, "error": error or "Cannot start feature"}), 409
    _force_fire_implementer()
    return jsonify({"ok": True})


@bp.route("/<feature_id>/update", methods=["POST"])
def update_feature(feature_id):
    """Update feature priority or status."""
    data = request.get_json() or {}
    
    items = store._load()
    for item in items:
        if item["id"] == feature_id:
            if "priority" in data:
                from ghost_future_features import PRIORITY_LEVELS
                item["priority"] = data["priority"].upper()
                item["priority_score"] = PRIORITY_LEVELS.get(item["priority"], 50)
            if "status" in data:
                item["status"] = data["status"]
            item["updated_at"] = __import__("datetime").datetime.now().isoformat()
            store._save(items)
            return jsonify({"ok": True, "feature": item})
    
    return jsonify({"ok": False, "error": "Feature not found"}), 404


@bp.route("/<feature_id>/delete", methods=["POST"])
def delete_feature(feature_id):
    """Permanently delete a feature."""
    ok = store.delete(feature_id)
    if not ok:
        return jsonify({"ok": False, "error": "Feature not found"}), 404
    return jsonify({"ok": True})


@bp.route("/changelog")
def get_changelog():
    """Get recent completed features."""
    limit = request.args.get("limit", 50, type=int)
    entries = changelog.get_recent(limit)
    return jsonify({"ok": True, "changelog": entries})


@bp.route("/metadata")
def get_metadata():
    """Get metadata for forms (statuses, priorities, sources)."""
    from ghost_future_features import PRIORITY_LEVELS, STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_IMPLEMENTED, STATUS_COMPLETED, STATUS_FAILED, STATUS_REJECTED, STATUS_DEFERRED
    
    statuses = [
        {"value": STATUS_PENDING, "label": "Pending", "emoji": "⏳"},
        {"value": STATUS_APPROVAL_REQUIRED, "label": "Approval Required", "emoji": "🛑"},
        {"value": STATUS_IN_PROGRESS, "label": "In Progress", "emoji": "🔄"},
        {"value": STATUS_IMPLEMENTED, "label": "Completed", "emoji": "✅"},
        {"value": STATUS_COMPLETED, "label": "Completed", "emoji": "✅"},
        {"value": STATUS_FAILED, "label": "Failed", "emoji": "⚠️"},
        {"value": STATUS_REJECTED, "label": "Rejected", "emoji": "❌"},
        {"value": STATUS_DEFERRED, "label": "Deferred", "emoji": "📋"},
    ]
    
    priorities = [
        {"value": "P0", "label": "P0 - Critical (needs approval)", "score": 100},
        {"value": "P1", "label": "P1 - High (auto-implement)", "score": 75},
        {"value": "P2", "label": "P2 - Medium (auto when idle)", "score": 50},
        {"value": "P3", "label": "P3 - Low (manual only)", "score": 25},
    ]
    
    sources = [
        {"value": "tech_scout", "label": "Tech Scout"},
        {"value": "competitive_intel", "label": "Competitive Intel"},
        {"value": "user_request", "label": "User Request"},
        {"value": "user", "label": "User"},
        {"value": "action_item", "label": "Action Item"},
        {"value": "bug_hunter", "label": "Bug Hunter"},
        {"value": "manual", "label": "Manual"},
        {"value": "other", "label": "Other"},
    ]
    
    efforts = [
        {"value": "small", "label": "Small"},
        {"value": "medium", "label": "Medium"},
        {"value": "large", "label": "Large"},
    ]
    
    return jsonify({
        "ok": True,
        "statuses": statuses,
        "priorities": priorities,
        "sources": sources,
        "efforts": efforts,
    })
