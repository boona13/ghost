"""Daemon control API — pause/resume, live config reload, restart."""

import os
import signal
import threading
import platform
from datetime import datetime
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import PAUSE_FILE, load_config, save_config, GHOST_HOME, PID_FILE, DEFAULT_CONFIG

bp = Blueprint("daemon", __name__)


def _daemon_running():
    """Check if daemon process is running via PID file."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError, PermissionError):
        return False, None


def _is_autonomy_active():
    """Check if a cron job or evolution is currently running."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon:
        return False
    if daemon.cron and daemon.cron.get_active_count() > 0:
        return True
    if daemon.evolve_engine:
        with daemon.evolve_engine._lock:
            if daemon.evolve_engine._active_evolutions:
                return True
    return False


@bp.route("/api/ghost/status", methods=["GET"])
def get_daemon_status():
    """Return daemon health state — running, paused, uptime, and live stats."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    
    running, pid = _daemon_running()
    paused = PAUSE_FILE.exists()
    
    if daemon:
        running = daemon.running
        pid = os.getpid()
        uptime_secs = int((datetime.now() - daemon.start_time).total_seconds())
        cfg = daemon.cfg
        model = cfg.get("model", DEFAULT_CONFIG["model"])
        if hasattr(daemon, 'engine') and hasattr(daemon.engine, 'fallback_chain'):
            fc = daemon.engine.fallback_chain
            model = f"{fc.active_provider}:{fc.active_model}"
        
        tool_count = len(daemon.tool_registry.names()) if daemon.tool_registry else 0
        skill_count = len(daemon.skill_loader.list_all()) if daemon.skill_loader else 0
        memory_count = daemon.memory_db.count() if daemon.memory_db else 0
        cron_jobs = daemon.cron.list_jobs() if daemon.cron else []
        cron_enabled = sum(1 for j in cron_jobs if j.get("enabled"))
        
        return jsonify({
            "running": running,
            "embedded": True,
            "paused": paused,
            "pid": pid,
            "platform": platform.system(),
            "uptime_seconds": uptime_secs,
            "model": model,
            "features": {
                "tool_loop": cfg.get("enable_tool_loop", True),
                "memory": cfg.get("enable_memory_db", True),
                "skills": cfg.get("enable_skills", True),
                "plugins": cfg.get("enable_plugins", True),
                "browser": cfg.get("enable_browser_tools", True),
                "cron": cfg.get("enable_cron", True),
                "vision": cfg.get("enable_vision", True),
                "tts": cfg.get("enable_tts", True),
                "security_audit": cfg.get("enable_security_audit", True),
                "session_memory": cfg.get("enable_session_memory", True),
            },
            "live": {
                "tools": tool_count,
                "skills": skill_count,
                "memory_entries": memory_count,
                "cron_jobs": len(cron_jobs),
                "cron_enabled": cron_enabled,
            },
        })
    
    # Standalone mode — read from files
    cfg = load_config()
    return jsonify({
        "running": running,
        "embedded": False,
        "paused": paused,
        "pid": pid,
        "platform": platform.system(),
        "model": cfg.get("model", DEFAULT_CONFIG["model"]),
        "features": {
            "tool_loop": cfg.get("enable_tool_loop", True),
            "memory": cfg.get("enable_memory_db", True),
            "skills": cfg.get("enable_skills", True),
            "plugins": cfg.get("enable_plugins", True),
            "browser": cfg.get("enable_browser_tools", True),
            "cron": cfg.get("enable_cron", True),
            "vision": cfg.get("enable_vision", True),
            "tts": cfg.get("enable_tts", True),
            "security_audit": cfg.get("enable_security_audit", True),
            "session_memory": cfg.get("enable_session_memory", True),
        },
    })


@bp.route("/api/ghost/pause", methods=["POST"])
def pause():
    force = request.args.get("force") == "1" or request.json and request.json.get("force")
    if not force and _is_autonomy_active():
        return jsonify({"ok": False, "error": "Cannot pause while autonomy/cron jobs are active. Use ?force=1 to override."}), 409
    PAUSE_FILE.write_text("paused")
    return jsonify({"ok": True, "paused": True})


@bp.route("/api/ghost/resume", methods=["POST"])
def resume():
    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink(missing_ok=True)
    return jsonify({"ok": True, "paused": False})


@bp.route("/api/ghost/reload", methods=["POST"])
def reload_config():
    """Hot-reload config into the running daemon if embedded."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        fresh = load_config()
        daemon.cfg.update(fresh)
        if hasattr(daemon, 'llm'):
            daemon.llm.model = fresh.get("model", daemon.cfg.get("model"))
        if hasattr(daemon, 'engine'):
            daemon.engine.model = fresh.get("model", daemon.cfg.get("model"))
        if daemon.skill_loader:
            daemon.skill_loader.reload()
        return jsonify({"ok": True, "reloaded": True})
    return jsonify({"ok": True, "reloaded": False, "note": "standalone mode"})


@bp.route("/api/ghost/restart", methods=["POST"])
def restart_ghost():
    """Restart the Ghost daemon. Uses supervisor if available, otherwise self-restarts."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()

    EVOLVE_DIR = Path.home() / ".ghost" / "evolve"
    DEPLOY_MARKER = EVOLVE_DIR / "deploy_pending"
    EVOLVE_DIR.mkdir(parents=True, exist_ok=True)

    supervised = daemon and getattr(daemon, "supervised", False)

    if supervised:
        import json, time
        DEPLOY_MARKER.write_text(json.dumps({
            "evolution_id": "manual_restart",
            "restart": True,
            "timestamp": time.time(),
        }))
        return jsonify({"ok": True, "method": "supervisor", "message": "Supervisor will restart Ghost"})

    # Hot-reload config into the running daemon (Docker-safe, no process restart)
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        fresh = load_config()
        daemon.cfg.update(fresh)
        new_model = fresh.get("model", daemon.cfg.get("model"))
        if hasattr(daemon, "llm"):
            daemon.llm.model = new_model
        if hasattr(daemon, "engine"):
            daemon.engine.model = new_model
        new_key = fresh.get("api_key", "")
        if new_key and new_key != "__SETUP_PENDING__":
            daemon.api_key = new_key
            if hasattr(daemon, "llm"):
                daemon.llm.api_key = new_key
            if hasattr(daemon, "engine"):
                daemon.engine.api_key = new_key
        if daemon.skill_loader:
            daemon.skill_loader.reload()
        return jsonify({"ok": True, "method": "hot-reload", "message": "Config reloaded into running daemon"})

    return jsonify({"ok": False, "message": "No daemon running"}), 500


@bp.route("/api/ghost/shutdown", methods=["POST"])
def shutdown_ghost():
    """Shut down the Ghost daemon completely."""
    force = request.args.get("force") == "1" or request.json and request.json.get("force")
    if not force and _is_autonomy_active():
        return jsonify({"ok": False, "error": "Cannot shutdown while autonomy/cron jobs are active. Use ?force=1 to override."}), 409
    from ghost_dashboard import get_daemon
    daemon = get_daemon()

    GHOST_HOME = Path.home() / ".ghost"
    SHUTDOWN_MARKER = GHOST_HOME / "shutdown_requested"

    supervised = daemon and getattr(daemon, "supervised", False)

    SHUTDOWN_MARKER.write_text("shutdown")

    if supervised:
        def _delayed_exit():
            import time as _time
            _time.sleep(2)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=_delayed_exit, daemon=True).start()
        return jsonify({"ok": True, "method": "supervisor", "message": "Ghost and supervisor shutting down..."})

    def _shutdown():
        import time as _time
        _time.sleep(2)
        if daemon:
            daemon.running = False
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"ok": True, "method": "self", "message": "Ghost is shutting down..."})
