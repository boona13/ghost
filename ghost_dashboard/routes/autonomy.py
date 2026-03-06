"""Autonomy API — action items, growth log, and growth routine management."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_autonomy import (
    ActionItemStore, GrowthLogger, GROWTH_ROUTINES,
    DEFAULT_GROWTH_SCHEDULES, GROWTH_JOB_PREFIX,
    reschedule_growth_cron,
)

bp = Blueprint("autonomy", __name__)

_action_store = ActionItemStore()
_growth_logger = GrowthLogger()


@bp.route("/api/autonomy/actions")
def get_actions():
    show_all = request.args.get("all", "false") == "true"
    items = _action_store.get_all() if show_all else _action_store.get_pending()
    return jsonify({"items": items, "pending_count": _action_store.count_pending()})


@bp.route("/api/autonomy/actions/<item_id>/resolve", methods=["POST"])
def resolve_action(item_id):
    ok = _action_store.resolve(item_id)
    return jsonify({"ok": ok})


@bp.route("/api/autonomy/actions/<item_id>/dismiss", methods=["POST"])
def dismiss_action(item_id):
    ok = _action_store.dismiss(item_id)
    return jsonify({"ok": ok})


@bp.route("/api/autonomy/growth-log")
def get_growth_log():
    limit = int(request.args.get("limit", 50))
    entries = _growth_logger.get_recent(limit)
    return jsonify({"entries": entries})


@bp.route("/api/autonomy/status")
def get_status():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()

    routines_status = []
    for routine in GROWTH_ROUTINES:
        job_name = f"{GROWTH_JOB_PREFIX}{routine['id']}"
        status = {"id": routine["id"], "name": routine["name"],
                  "description": routine["description"]}

        if daemon and daemon.cron:
            for job in daemon.cron.store.get_all():
                if job["name"] == job_name:
                    status["enabled"] = job.get("enabled", True)
                    status["schedule"] = job.get("schedule", {}).get("expr", "")
                    status["last_run"] = job.get("state", {}).get("lastRunAtMs")
                    status["last_status"] = job.get("state", {}).get("lastRunStatus")
                    status["next_run"] = job.get("state", {}).get("nextRunAtMs")
                    break

        routines_status.append(status)

    crash_report = None
    crash_file = Path.home() / ".ghost" / "crash_report.json"
    if crash_file.exists():
        try:
            import json
            crash_report = json.loads(crash_file.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Failed to load crash report", exc_info=True)

    return jsonify({
        "routines": routines_status,
        "pending_actions": _action_store.count_pending(),
        "growth_log_count": len(_growth_logger.get_recent(1000)),
        "crash_report": crash_report,
    })


@bp.route("/api/autonomy/reschedule", methods=["POST"])
def reschedule():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon or not daemon.cron:
        return jsonify({"ok": False, "error": "Daemon or cron not available"}), 503

    reschedule_growth_cron(daemon.cron, daemon.cfg)
    return jsonify({"ok": True, "message": "Growth schedules updated"})
