"""Goals API — persistent multi-step user goals with autonomous execution."""

import logging
import threading
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


def _get_daemon():
    try:
        from ghost_dashboard import get_daemon
        return get_daemon()
    except Exception:
        return None


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
    recurrence = (data.get("recurrence") or "").strip() or None
    delivery = (data.get("delivery") or "").strip()
    context = data.get("context", {})
    if delivery:
        context["delivery"] = delivery
    goal = store.add(
        title=title,
        goal_text=goal_text,
        recurrence=recurrence,
        context=context,
    )
    if delivery and goal.get("id"):
        store._update(goal["id"], {"delivery": delivery})
        goal["delivery"] = delivery
    if goal.get("_error"):
        return jsonify({"ok": False, "error": goal["_error"]}), 400
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


@bp.route("/<goal_id>/delete", methods=["POST", "DELETE"])
def delete_goal(goal_id):
    store = _get_store()
    ok = store.delete_goal(goal_id)
    if not ok:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    return jsonify({"ok": True})


@bp.route("/<goal_id>/delivery", methods=["POST"])
def set_delivery(goal_id):
    data = request.get_json() or {}
    delivery = data.get("delivery", "").strip()
    store = _get_store()
    goal = store.get(goal_id)
    if not goal:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    updated = store._update(goal_id, {"delivery": delivery})
    if not updated:
        return jsonify({"ok": False, "error": "Update failed"}), 500
    return jsonify({"ok": True, "delivery": delivery})


@bp.route("/<goal_id>/run", methods=["POST"])
def run_goal_now(goal_id):
    """Trigger immediate execution of a specific goal."""
    store = _get_store()
    goal = store.get(goal_id)
    if not goal:
        return jsonify({"ok": False, "error": "Goal not found"}), 404
    if goal.get("status") not in ("pending_plan", "active"):
        return jsonify({"ok": False, "error": f"Goal is {goal.get('status')} — cannot run"}), 400

    daemon = _get_daemon()
    if not daemon or not getattr(daemon, "tool_registry", None):
        return jsonify({"ok": False, "error": "Ghost daemon not ready — try again in a moment"}), 503

    def _run_in_background():
        try:
            from ghost_goal_executor import GoalExecutorEngine, deliver_goal_results
            # Reload goal from store to avoid stale data
            fresh_goal = store.get(goal_id)
            if not fresh_goal:
                log.warning("Goal [%s] disappeared before run-now could execute", goal_id)
                return
            executor = GoalExecutorEngine(
                cfg=daemon.cfg,
                tool_registry=daemon.tool_registry,
                auth_store=getattr(daemon, "auth_store", None),
                provider_chain=getattr(daemon, "provider_chain", None),
            )
            result = executor._process_goal(fresh_goal)
            if result.get("completed"):
                deliver_goal_results([result], daemon)
        except Exception as exc:
            log.error("Goal run-now failed for [%s]: %s", goal_id, exc, exc_info=True)

    t = threading.Thread(target=_run_in_background, daemon=True, name=f"goal-run-{goal_id}")
    t.start()
    return jsonify({"ok": True, "message": f"Goal execution started in background for [{goal_id}]"})
