"""Goals API — persistent multi-step user goals with autonomous execution."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_goals import GoalStore

bp = Blueprint("goals", __name__, url_prefix="/api/goals")
_store = GoalStore()


def _get_store():
    return _store


@bp.route("/list")
def list_goals():
    status = request.args.get("status", "")
    store = _get_store()
    goals = store.list_goals(status=status or None)
    return jsonify({"ok": True, "goals": goals, "count": len(goals)})


@bp.route("/stats")
def stats():
    store = _get_store()
    all_goals = store.list_goals()
    counts = {}
    for g in all_goals:
        s = g.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1
    return jsonify({
        "ok": True,
        "total": len(all_goals),
        "active": counts.get("active", 0),
        "pending_plan": counts.get("pending_plan", 0),
        "paused": counts.get("paused", 0),
        "completed": counts.get("completed", 0),
        "abandoned": counts.get("abandoned", 0),
    })


@bp.route("/<goal_id>")
def get_goal(goal_id):
    store = _get_store()
    goal = store.get(goal_id)
    if not goal:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    return jsonify({"ok": True, "goal": goal})


@bp.route("/add", methods=["POST"])
def add_goal():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    goal_text = data.get("goal_text", "").strip()
    if not title or not goal_text:
        return jsonify({"ok": False, "error": "title and goal_text are required"}), 400
    store = _get_store()
    goal = store.add(
        title=title,
        goal_text=goal_text,
        recurrence=data.get("recurrence", ""),
        context=data.get("context", {}),
    )
    return jsonify({"ok": True, "goal": goal})


@bp.route("/<goal_id>/pause", methods=["POST"])
def pause_goal(goal_id):
    store = _get_store()
    ok = store.pause_goal(goal_id)
    if not ok:
        return jsonify({"ok": False, "error": "Goal not found or cannot be paused"}), 400
    return jsonify({"ok": True})


@bp.route("/<goal_id>/resume", methods=["POST"])
def resume_goal(goal_id):
    store = _get_store()
    ok = store.resume_goal(goal_id)
    if not ok:
        return jsonify({"ok": False, "error": "Goal not found or cannot be resumed"}), 400
    return jsonify({"ok": True})


@bp.route("/<goal_id>/abandon", methods=["POST"])
def abandon_goal(goal_id):
    store = _get_store()
    ok = store.abandon_goal(goal_id)
    if not ok:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    return jsonify({"ok": True})


@bp.route("/<goal_id>/delete", methods=["POST"])
def delete_goal(goal_id):
    store = _get_store()
    goals = store._load()
    before = len(goals)
    goals = [g for g in goals if g["id"] != goal_id]
    if len(goals) == before:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    store._save(goals)
    return jsonify({"ok": True})
