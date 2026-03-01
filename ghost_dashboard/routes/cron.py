"""Cron API — scheduled job management."""

from datetime import datetime
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_cron import CronService, describe_schedule

bp = Blueprint("cron", __name__)

_standalone_cron = None

def _get_cron():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.cron:
        return daemon.cron

    global _standalone_cron
    if _standalone_cron is None:
        _standalone_cron = CronService()
    return _standalone_cron


def _format_job(j):
    state = j.get("state", {})
    next_ms = state.get("nextRunAtMs")
    last_ms = state.get("lastRunAtMs")
    return {
        "id": j["id"],
        "name": j["name"],
        "description": j.get("description", ""),
        "enabled": j.get("enabled", True),
        "deleteAfterRun": j.get("deleteAfterRun", False),
        "schedule": j.get("schedule", {}),
        "schedule_human": describe_schedule(j.get("schedule", {})),
        "payload": j.get("payload", {}),
        "next_run": (
            datetime.fromtimestamp(next_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if next_ms else None
        ),
        "last_run": (
            datetime.fromtimestamp(last_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if last_ms else None
        ),
        "last_status": state.get("lastRunStatus"),
        "last_error": state.get("lastError"),
        "last_duration_ms": state.get("lastDurationMs"),
        "consecutive_errors": state.get("consecutiveErrors", 0),
    }


@bp.route("/api/cron/jobs")
def list_jobs():
    cron = _get_cron()
    jobs = [_format_job(j) for j in cron.list_jobs()]
    return jsonify({"jobs": jobs})


@bp.route("/api/cron/jobs", methods=["POST"])
def create_job():
    data = request.get_json(silent=True) or {}
    cron = _get_cron()

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    stype = data.get("schedule_type", "every")
    if stype == "every":
        secs = data.get("interval_seconds", 300)
        schedule = {"kind": "every", "everyMs": int(secs * 1000)}
    elif stype == "cron":
        expr = data.get("cron_expr", "")
        if not expr:
            return jsonify({"error": "cron_expr required"}), 400
        schedule = {"kind": "cron", "expr": expr}
    elif stype == "at":
        at_val = data.get("run_at", "")
        if not at_val:
            return jsonify({"error": "run_at required"}), 400
        schedule = {"kind": "at", "at": at_val}
    else:
        return jsonify({"error": f"Unknown schedule_type: {stype}"}), 400

    task_type = data.get("task_type", "task")
    task = data.get("task", "")
    if task_type == "task":
        payload = {"type": "task", "prompt": task}
    elif task_type == "notify":
        payload = {"type": "notify", "title": name, "message": task}
    elif task_type == "shell":
        payload = {"type": "shell", "command": task}
    else:
        return jsonify({"error": f"Unknown task_type: {task_type}"}), 400

    job = cron.add_job(
        name=name, schedule=schedule, payload=payload,
        description=data.get("description", ""),
        delete_after_run=data.get("delete_after_run", False),
    )
    return jsonify({"ok": True, "job": _format_job(job)}), 201


@bp.route("/api/cron/jobs/<job_id>", methods=["PUT"])
def update_job(job_id):
    data = request.get_json(silent=True) or {}
    cron = _get_cron()

    if "enabled" in data:
        ok = cron.enable_job(job_id, enabled=data["enabled"])
        if not ok:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"ok": True})

    ok = cron.update_job(job_id, **data)
    if not ok:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"ok": True})


@bp.route("/api/cron/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    cron = _get_cron()
    ok = cron.remove_job(job_id)
    if not ok:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"ok": True})


@bp.route("/api/cron/jobs/<job_id>/run", methods=["POST"])
def run_job(job_id):
    cron = _get_cron()
    ok, msg = cron.run_now(job_id)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "message": msg})


@bp.route("/api/cron/status")
def cron_status():
    cron = _get_cron()
    return jsonify(cron.status())
