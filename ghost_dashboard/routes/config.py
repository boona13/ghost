"""Config API — read/write ~/.ghost/config.json with live daemon reload."""

import logging
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import CONFIG_FILE, load_config, save_config, DEFAULT_CONFIG

bp = Blueprint("config", __name__)


def _notify_daemon():
    """If running embedded, push config changes to the live daemon."""
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if daemon:
            fresh = load_config()
            daemon.cfg.update(fresh)
            new_model = fresh.get("model")
            if new_model and hasattr(daemon, 'llm'):
                daemon.llm.model = new_model
            if new_model and hasattr(daemon, 'engine'):
                daemon.engine.model = new_model
            if new_model and getattr(daemon, 'chat_engine', None):
                daemon.chat_engine.model = new_model
    except Exception:
        log.warning("Failed to reload config in daemon", exc_info=True)


def _mask_key(key):
    """Mask sensitive API keys for display - show first 8 chars + ... + last 4 chars."""
    if not key:
        return ""
    if len(key) > 12:
        return key[:8] + "..." + key[-4:]
    return "***"


@bp.route("/api/config")
def get_config():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    cfg = daemon.cfg if daemon else load_config()
    resp = dict(cfg)
    # Mask sensitive API keys before returning
    if "api_key" in resp and resp["api_key"]:
        resp["api_key"] = _mask_key(resp["api_key"])
    if "firecrawl_api_key" in resp and resp["firecrawl_api_key"]:
        resp["firecrawl_api_key"] = _mask_key(resp["firecrawl_api_key"])
    if daemon and hasattr(daemon, 'engine') and hasattr(daemon.engine, 'fallback_chain'):
        fc = daemon.engine.fallback_chain
        resp["model"] = f"{fc.active_provider}:{fc.active_model}"
    return jsonify({"config": resp, "defaults": DEFAULT_CONFIG})


@bp.route("/api/config", methods=["PUT"])
def update_config():
    data = request.get_json(silent=True) or {}
    cfg = load_config()

    requested_enable = data.get("enable_dangerous_interpreters")
    if requested_enable is True and not cfg.get("enable_dangerous_interpreters", False):
        token = str(data.get("dangerous_interpreters_confirmation", "")).strip()
        if token != "I_UNDERSTAND_THE_RISK":
            return jsonify({
                "ok": False,
                "error": "Enabling dangerous interpreters requires explicit confirmation token",
                "required_confirmation": "I_UNDERSTAND_THE_RISK",
            }), 400
        try:
            from ghost import append_feed
            append_feed({
                "ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                "type": "security",
                "preview": "Dangerous interpreters enabled via config API",
                "result": "enable_dangerous_interpreters set to true with elevated confirmation",
            })
        except Exception:
            pass

    data.pop("dangerous_interpreters_confirmation", None)
    cfg.update(data)
    save_config(cfg)
    _notify_daemon()
    return jsonify({"ok": True, "config": cfg})
