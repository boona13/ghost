"""Structured Memory API — browse sections, facts, and queue status."""

import logging
import sys
from pathlib import Path
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_structured_memory import (
    get_memory_data,
    get_memory_queue,
    reload_memory_data,
    get_structured_memory_config,
    _save_memory_to_file,
)

bp = Blueprint("structured_memory", __name__)


@bp.route("/api/structured-memory/status")
def sm_status():
    data = get_memory_data()
    queue = get_memory_queue()
    cfg = get_structured_memory_config()

    facts = [f for f in data.get("facts", []) if isinstance(f, dict)]
    categories: dict[str, int] = {}
    for f in facts:
        cat = f.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    def _has_summary(section_group: str, key: str) -> bool:
        group = data.get(section_group)
        if not isinstance(group, dict):
            return False
        entry = group.get(key)
        if not isinstance(entry, dict):
            return False
        return bool(entry.get("summary"))

    return jsonify({
        "lastUpdated": data.get("lastUpdated", ""),
        "facts_count": len(facts),
        "facts_by_category": categories,
        "sections": {
            "workContext": _has_summary("user", "workContext"),
            "personalContext": _has_summary("user", "personalContext"),
            "topOfMind": _has_summary("user", "topOfMind"),
            "recentMonths": _has_summary("history", "recentMonths"),
            "earlierContext": _has_summary("history", "earlierContext"),
            "longTermBackground": _has_summary("history", "longTermBackground"),
        },
        "queue_pending": queue.pending_count,
        "queue_processing": queue.is_processing,
        "enabled": cfg.enabled,
    })


@bp.route("/api/structured-memory/data")
def sm_data():
    data = get_memory_data()
    return jsonify(data)


@bp.route("/api/structured-memory/facts")
def sm_facts():
    data = get_memory_data()
    facts = [f for f in data.get("facts", []) if isinstance(f, dict)]

    category = request.args.get("category")
    if category:
        facts = [f for f in facts if f.get("category") == category]

    sort_by = request.args.get("sort", "confidence")
    reverse = request.args.get("order", "desc") == "desc"

    def _safe_key(f):
        if sort_by == "confidence":
            try:
                return float(f.get("confidence", 0))
            except (TypeError, ValueError):
                return 0.0
        elif sort_by == "date":
            return f.get("createdAt", "")
        return f.get("content", "")

    facts = sorted(facts, key=_safe_key, reverse=reverse)

    return jsonify({"facts": facts, "total": len(facts)})


@bp.route("/api/structured-memory/refresh", methods=["POST"])
def sm_refresh():
    queue = get_memory_queue()
    try:
        queue.flush()
        reload_memory_data()
        return jsonify({"status": "ok", "message": "Memory queue flushed and data reloaded"})
    except Exception as e:
        log.warning("Structured memory refresh failed: %s", e)
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/api/structured-memory/facts/<fact_id>", methods=["DELETE"])
def sm_delete_fact(fact_id):
    data = get_memory_data()
    facts = data.get("facts", [])
    original_len = len(facts)
    data["facts"] = [f for f in facts if not (isinstance(f, dict) and f.get("id") == fact_id)]

    if len(data["facts"]) == original_len:
        return jsonify({"status": "error", "error": "Fact not found"}), 404

    if _save_memory_to_file(data):
        return jsonify({"status": "ok", "message": f"Fact {fact_id} deleted"})
    return jsonify({"status": "error", "error": "Failed to save"}), 500
