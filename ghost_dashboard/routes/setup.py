"""Setup API — first-run wizard + multi-provider configuration."""

import logging
import os, sys
from flask import Blueprint, jsonify, request
from typing import Any, Dict, List
from pathlib import Path

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import GHOST_HOME, CONFIG_FILE, load_config, save_config, DEFAULT_CONFIG

bp = Blueprint("setup", __name__)


def _has_any_provider():
    """Check if any provider has valid credentials."""
    try:
        from ghost_auth_profiles import get_auth_store
        store = get_auth_store()
        return bool(store.get_configured_providers())
    except ImportError:
        pass
    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key and env_key != "__SETUP_PENDING__":
        return True
    cfg = load_config()
    cfg_key = cfg.get("api_key", "").strip()
    return bool(cfg_key and cfg_key != "__SETUP_PENDING__")


@bp.route("/api/setup/status")
def setup_status():
    has_provider = _has_any_provider()
    try:
        from ghost_auth_profiles import get_auth_store
        store = get_auth_store()
        providers = store.summary()
    except Exception:
        providers = []
    return jsonify({
        "needs_setup": not has_provider,
        "has_api_key": has_provider,
        "ghost_home_exists": GHOST_HOME.exists(),
        "config_exists": CONFIG_FILE.exists(),
        "providers": providers,
    })


@bp.route("/api/setup/providers")
def list_providers():
    """List all available providers with their config status."""
    from ghost_providers import list_providers
    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()
    providers = list_providers()
    for p in providers:
        status = store.get_provider_status(p["id"])
        p.update(status)
    return jsonify({"providers": providers})


@bp.route("/api/setup/providers/<provider_id>/configure", methods=["POST"])
def configure_provider(provider_id):
    """Save an API key for a provider."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()

    from ghost_providers import get_provider
    provider = get_provider(provider_id)
    if not provider:
        return jsonify({"ok": False, "error": f"Unknown provider: {provider_id}"}), 400

    if provider.auth_type == "api_key" and not api_key:
        return jsonify({"ok": False, "error": "API key is required"}), 400

    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()

    if provider.auth_type == "none":
        store.set_no_auth(provider_id)
    else:
        store.set_api_key(provider_id, api_key)

    if provider_id == "openrouter":
        cfg = load_config()
        cfg["api_key"] = api_key
        save_config(cfg)
        os.environ["OPENROUTER_API_KEY"] = api_key
        _hot_swap_key(api_key)

    return jsonify({"ok": True})


@bp.route("/api/setup/providers/<provider_id>/test", methods=["POST"])
def test_provider(provider_id):
    """Test connection to a provider."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "")

    if not api_key:
        from ghost_auth_profiles import get_auth_store
        api_key = get_auth_store().get_api_key(provider_id)

    from ghost_providers import test_provider_connection
    result = test_provider_connection(provider_id, api_key)
    return jsonify(result)


@bp.route("/api/setup/providers/<provider_id>/remove", methods=["POST"])
def remove_provider(provider_id):
    """Remove a provider's credentials."""
    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()
    store.remove_profile(f"{provider_id}:default")
    return jsonify({"ok": True})


@bp.route("/api/setup/oauth/codex/start", methods=["POST"])
def start_codex_oauth():
    """Initiate the Codex OAuth PKCE flow."""
    from ghost_oauth import start_codex_oauth as _start
    from ghost_auth_profiles import get_auth_store

    store = get_auth_store()

    def on_complete(tokens):
        store.set_oauth(
            "openai-codex",
            tokens["access_token"],
            tokens.get("refresh_token", ""),
            expires_at=tokens.get("expires_at", 0),
            account_id=tokens.get("account_id", ""),
        )

    result = _start(on_complete=on_complete)
    return jsonify({"ok": True, **result})


@bp.route("/api/setup/oauth/codex/status")
def codex_oauth_status():
    """Check Codex OAuth status."""
    from ghost_oauth import get_codex_oauth_status
    return jsonify(get_codex_oauth_status())


@bp.route("/api/setup/complete", methods=["POST"])
def complete_setup():
    """Complete setup — supports both legacy single-key and multi-provider."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()

    if api_key:
        cfg = load_config()
        cfg["api_key"] = api_key
        if data.get("model"):
            cfg["model"] = data["model"]
        save_config(cfg)
        os.environ["OPENROUTER_API_KEY"] = api_key

        from ghost_auth_profiles import get_auth_store
        get_auth_store().set_api_key("openrouter", api_key)

        _hot_swap_key(api_key)

    return jsonify({"ok": True, "restarting": False})


@bp.route("/api/setup/provider-order", methods=["PUT"])
def set_provider_order():
    """Set the fallback order of providers and rebuild the live chain."""
    data = request.get_json(silent=True) or {}
    order = data.get("order", [])
    if not isinstance(order, list):
        return jsonify({"ok": False, "error": "order must be a list"}), 400

    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()
    store.provider_order = order

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, 'engine'):
        from ghost import load_config, DEFAULT_CONFIG
        cfg = daemon.cfg
        model = cfg.get("model", DEFAULT_CONFIG["model"])
        fallback_models = cfg.get("fallback_models", [])
        new_chain = daemon._build_provider_chain(model, fallback_models)
        daemon.engine.fallback_chain.set_provider_chain(new_chain)
        if getattr(daemon, 'chat_engine', None):
            daemon.chat_engine.fallback_chain.set_provider_chain(list(new_chain))

    return jsonify({"ok": True, "order": order})


def _call_daemon_tool(tool_name: str, args: Dict[str, Any] | None = None):
    """Call a daemon tool and normalize JSON response for setup endpoints."""
    args = args or {}
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if not daemon:
            return {"ok": False, "error": "Daemon is not available"}, 503

        tool = daemon.tool_registry.get(tool_name)
        if not tool:
            return {"ok": False, "error": f"Tool not found: {tool_name}"}, 404

        result = tool["execute"](**args)
        if isinstance(result, dict):
            return result, 200
        return {"ok": True, "result": result}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@bp.route("/api/setup/doctor/status")
def setup_doctor_status():
    # Try daemon first for live state, fallback to direct orchestrator for standalone mode
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        payload, status = _call_daemon_tool("setup_doctor_status", {})
        return jsonify(payload), status
    # Standalone mode: use orchestrator directly
    from ghost_setup_doctor import SetupDoctorOrchestrator
    from ghost import load_config
    cfg = load_config()
    orchestrator = SetupDoctorOrchestrator(config=cfg, daemon_refs={})
    payload = orchestrator.status()
    return jsonify(payload), 200


@bp.route("/api/setup/doctor/run", methods=["POST"])
def setup_doctor_run():
    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    steps_raw = data.get("steps", [])
    steps: List[str] = steps_raw if isinstance(steps_raw, list) else []
    # Try daemon first, fallback to direct orchestrator for standalone mode
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        args = {"dry_run": dry_run, "steps": steps}
        payload, status = _call_daemon_tool("setup_doctor_run", args)
        return jsonify(payload), status
    # Standalone mode: use orchestrator directly
    from ghost_setup_doctor import SetupDoctorOrchestrator, ALLOWED_STEPS
    from ghost import load_config
    cfg = load_config()
    orchestrator = SetupDoctorOrchestrator(config=cfg, daemon_refs={})
    result = orchestrator.run(dry_run=dry_run)
    if steps:
        result["steps"] = {k: v for k, v in result.get("steps", {}).items() if k in set(steps)}
    return jsonify(result), 200


@bp.route("/api/setup/doctor/fix-all", methods=["POST"])
def setup_doctor_fix_all():
    data = request.get_json(silent=True) or {}
    confirm = bool(data.get("confirm", False))
    if not confirm:
        return jsonify({"ok": False, "error": "confirm=true is required"}), 400
    # Try daemon first, fallback to direct orchestrator for standalone mode
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        payload, status = _call_daemon_tool("setup_doctor_fix_all", {"confirm": True})
        return jsonify(payload), status
    # Standalone mode: use orchestrator directly
    from ghost_setup_doctor import SetupDoctorOrchestrator
    from ghost import load_config
    cfg = load_config()
    orchestrator = SetupDoctorOrchestrator(config=cfg, daemon_refs={})
    result = orchestrator.run(dry_run=False)
    return jsonify(result), 200


def _hot_swap_key(api_key):
    """Hot-swap API key into the running daemon."""
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if daemon:
            daemon.api_key = api_key
            daemon.cfg["api_key"] = api_key
            if hasattr(daemon, "llm"):
                daemon.llm.api_key = api_key
            if hasattr(daemon, "engine"):
                daemon.engine.api_key = api_key
            if getattr(daemon, "chat_engine", None):
                daemon.chat_engine.api_key = api_key
    except Exception:
        log.warning("Failed to update daemon API key", exc_info=True)
