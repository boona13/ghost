"""API routes for the Ghost Self-Evolution system."""

import logging
import os
import sys
import threading
from pathlib import Path
from flask import Blueprint, jsonify, request

import ghost_platform

from ghost_dashboard.rate_limiter import rate_limit

log = logging.getLogger(__name__)

bp = Blueprint("evolve", __name__)

_on_evolve_approve = None


def set_evolve_approve_hook(fn):
    """Register a callback fired after the user approves a pending evolution.

    The callback receives no arguments and should:
    1. Check if the Feature Implementer is already running (if yes, the
       in-memory approval will unblock _wait_for_approval — nothing to do).
    2. If NOT running, reset orphaned in_progress features to pending and
       fire the implementer so it picks up the work.
    """
    global _on_evolve_approve
    _on_evolve_approve = fn


def _get_engine():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.evolve_engine:
        return daemon.evolve_engine
    from ghost_evolve import get_engine
    return get_engine()


@bp.route("/api/evolve/history")
def list_history():
    engine = _get_engine()
    history = engine.get_history()
    return jsonify({"history": history})


@bp.route("/api/evolve/pending")
def list_pending():
    engine = _get_engine()
    pending = engine.get_pending()
    return jsonify({"pending": pending})


@bp.route("/api/evolve/approve/<evo_id>", methods=["POST"])
@rate_limit(requests_per_minute=5)
def approve_evolution(evo_id):
    engine = _get_engine()
    ok, msg = engine.approve(evo_id)
    if ok and _on_evolve_approve:
        try:
            _on_evolve_approve()
        except Exception:
            log.warning("Evolve approve hook failed", exc_info=True)
    return jsonify({"ok": ok, "message": msg})


@bp.route("/api/evolve/reject/<evo_id>", methods=["POST"])
@rate_limit(requests_per_minute=5)
def reject_evolution(evo_id):
    engine = _get_engine()
    ok, msg = engine.reject(evo_id)
    return jsonify({"ok": ok, "message": msg})


@bp.route("/api/evolve/rollback/<evo_id>", methods=["POST"])
@rate_limit(requests_per_minute=5)
def rollback_evolution(evo_id):
    engine = _get_engine()
    ok, msg = engine.rollback(evo_id)
    if ok:
        _schedule_restart()
    return jsonify({"ok": ok, "message": msg, "restarting": ok})


def _schedule_restart():
    """Restart Ghost after rollback — supervisor or self-restart."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    supervised = daemon and getattr(daemon, "supervised", False)

    if supervised:
        return

    import subprocess
    project_dir = str(Path(__file__).resolve().parent.parent.parent)
    from ghost import load_config
    cfg = load_config()
    api_key = cfg.get("api_key", "")

    def _spawn_and_exit():
        import time
        time.sleep(1.5)
        cmd = [sys.executable, str(Path(project_dir) / "ghost.py")]
        if api_key:
            cmd += ["--api-key", api_key]
        ghost_platform.popen_detached(cmd, cwd=project_dir)
        time.sleep(1)
        os._exit(0)

    threading.Thread(target=_spawn_and_exit, daemon=True).start()


@bp.route("/api/evolve/diff/<evo_id>")
def get_diff(evo_id):
    engine = _get_engine()
    changes = engine.get_diff(evo_id)
    return jsonify({"evolution_id": evo_id, "changes": changes})


@bp.route("/api/evolve/stats")
def evolve_stats():
    engine = _get_engine()
    history = engine.get_history()
    pending = engine.get_pending()

    from ghost_evolve import BACKUP_DIR
    backups = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)

    deployed = sum(1 for e in history if e.get("status") == "deployed")
    rolled_back = sum(1 for e in history if e.get("status") == "rolled_back")

    return jsonify({
        "total_evolutions": len(history),
        "deployed": deployed,
        "rolled_back": rolled_back,
        "pending_approvals": len(pending),
        "backups": len(backups),
        "latest_backup": str(backups[0]) if backups else None,
    })
