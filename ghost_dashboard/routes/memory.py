"""Memory API — uses live daemon MemoryDB when embedded, else opens its own."""

from flask import Blueprint, jsonify, request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_memory import MemoryDB

bp = Blueprint("memory", __name__)

_standalone_db = None


def _get_db():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.memory_db:
        return daemon.memory_db

    global _standalone_db
    if _standalone_db is None:
        _standalone_db = MemoryDB()
    return _standalone_db


@bp.route("/api/memory/stats")
def memory_stats():
    db = _get_db()
    stats = db.stats()
    return jsonify(stats)


@bp.route("/api/memory/search")
def memory_search():
    db = _get_db()
    q = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 50))
    if not q:
        return jsonify({"results": [], "query": ""})
    results = db.search(q, limit=limit)
    return jsonify({"results": results, "query": q})


@bp.route("/api/memory/recent")
def memory_recent():
    db = _get_db()
    limit = int(request.args.get("limit", 20))
    results = db.recent(limit=limit)
    return jsonify({"results": results})


@bp.route("/api/memory/<int:memory_id>", methods=["DELETE"])
def memory_delete(memory_id):
    db = _get_db()
    try:
        db.delete(memory_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/memory/prune", methods=["POST"])
def memory_prune():
    data = request.get_json(silent=True) or {}
    keep = data.get("keep", 1000)
    db = _get_db()
    db.prune(keep)
    stats = db.stats()
    return jsonify({"ok": True, "stats": stats})
