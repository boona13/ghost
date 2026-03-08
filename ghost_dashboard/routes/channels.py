"""Channels API — multi-channel messaging configuration, status, and testing."""

import json
import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_channels import (
    load_channels_config, save_channels_config,
    _sanitize_config, INBOUND_LOG_FILE,
)

bp = Blueprint("channels", __name__)


def _get_router():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.channel_router:
        return daemon.channel_router
    return None


def _get_registry():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.channel_registry:
        return daemon.channel_registry
    return None


@bp.route("/api/channels")
def list_channels():
    registry = _get_registry()
    if not registry:
        return jsonify({"channels": [], "error": "Channels not initialized"}), 503

    channels_cfg = load_channels_config()
    configured = set(registry.list_configured())
    result = []
    for meta in registry.list_all():
        prov = registry.get(meta.id)
        health = {}
        if prov:
            try:
                health = prov.health_check()
            except Exception:
                health = {"status": "error"}
        entry = {
            "id": meta.id,
            "label": meta.label,
            "emoji": meta.emoji,
            "configured": meta.id in configured,
            "status": health.get("status", "unknown"),
            "supports_inbound": meta.supports_inbound,
            "supports_media": meta.supports_media,
            "supports_threads": meta.supports_threads,
            "supports_groups": meta.supports_groups,
            "supports_edit": meta.supports_edit,
            "supports_unsend": meta.supports_unsend,
            "supports_polls": meta.supports_polls,
            "supports_streaming": meta.supports_streaming,
            "supports_directory": meta.supports_directory,
            "supports_gateway": meta.supports_gateway,
            "text_chunk_limit": meta.text_chunk_limit,
            "delivery_mode": meta.delivery_mode.value,
            "docs_url": meta.docs_url,
            "enabled": channels_cfg.get(meta.id, {}).get("enabled", False),
        }
        result.append(entry)

    router = _get_router()
    preferred = router.get_preferred_channel() if router else None

    return jsonify({
        "channels": result,
        "preferred": preferred,
        "configured_count": len(configured),
        "total_count": len(result),
    })


@bp.route("/api/channels/<channel_id>/status")
def channel_status(channel_id):
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404
    try:
        health = prov.health_check()
    except Exception as e:
        health = {"status": "error", "last_error": str(e)}
    return jsonify({"channel": channel_id, **health})


@bp.route("/api/channels/<channel_id>/schema")
def channel_schema(channel_id):
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404
    schema = prov.get_config_schema()
    current = load_channels_config().get(channel_id, {})
    return jsonify({
        "channel": channel_id,
        "schema": schema,
        "current": _sanitize_config(current),
    })


@bp.route("/api/channels/<channel_id>/configure", methods=["POST"])
def configure_channel(channel_id):
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No config data provided"}), 400

    data["enabled"] = True
    ok = prov.configure(data)

    all_cfg = load_channels_config()
    all_cfg[channel_id] = data
    save_channels_config(all_cfg)

    return jsonify({
        "ok": ok,
        "channel": channel_id,
        "config": _sanitize_config(data),
        "message": "Configured successfully" if ok else "Saved but configure() returned False",
    })


@bp.route("/api/channels/<channel_id>/enable", methods=["POST"])
def enable_channel(channel_id):
    all_cfg = load_channels_config()
    section = all_cfg.get(channel_id, {})
    section["enabled"] = True
    all_cfg[channel_id] = section
    save_channels_config(all_cfg)

    registry = _get_registry()
    if registry:
        prov = registry.get(channel_id)
        if prov:
            prov.configure(section)

    return jsonify({"ok": True, "channel": channel_id, "enabled": True})


@bp.route("/api/channels/<channel_id>/disable", methods=["POST"])
def disable_channel(channel_id):
    all_cfg = load_channels_config()
    section = all_cfg.get(channel_id, {})
    section["enabled"] = False
    all_cfg[channel_id] = section
    save_channels_config(all_cfg)

    registry = _get_registry()
    if registry:
        prov = registry.get(channel_id)
        if prov:
            try:
                prov.stop_inbound()
            except Exception:
                log.warning("Failed to stop inbound provider", exc_info=True)
            if hasattr(prov, "_configured"):
                prov._configured = False

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, "inbound_dispatcher") and daemon.inbound_dispatcher:
        dispatcher = daemon.inbound_dispatcher
        if hasattr(dispatcher, "_active") and channel_id in dispatcher._active:
            dispatcher._active.remove(channel_id)

    return jsonify({"ok": True, "channel": channel_id, "enabled": False})


@bp.route("/api/channels/<channel_id>/test", methods=["POST"])
def test_channel(channel_id):
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    data = request.get_json(force=True) or {}
    message = data.get("message", "Hello from Ghost! This is a test message.")
    to = data.get("to", "")

    result = prov.send_text(to=to, text=message, title="Ghost Test")
    return jsonify({
        "ok": result.ok,
        "channel": channel_id,
        "message_id": result.message_id,
        "error": result.error,
    })


@bp.route("/api/channels/send", methods=["POST"])
def send_message():
    router = _get_router()
    if not router:
        return jsonify({"error": "Channel router not initialized"}), 503

    data = request.get_json(force=True) or {}
    text = data.get("message", data.get("text", ""))
    if not text:
        return jsonify({"error": "No message text provided"}), 400

    channel = data.get("channel", None)
    to = data.get("to", None)
    priority = data.get("priority", "normal")

    result = router.send(text, channel=channel, to=to, priority=priority)
    return jsonify({
        "ok": result.ok,
        "channel": result.channel_id,
        "message_id": result.message_id,
        "error": result.error,
    })


@bp.route("/api/channels/preferred", methods=["POST"])
def set_preferred():
    data = request.get_json(force=True) or {}
    channel_id = data.get("channel", "")
    if not channel_id:
        return jsonify({"error": "No channel specified"}), 400

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        daemon.cfg["preferred_channel"] = channel_id
        if daemon.channel_router:
            daemon.channel_router.config["preferred_channel"] = channel_id
        from ghost import save_config
        save_config(daemon.cfg)
    return jsonify({"ok": True, "preferred": channel_id})


@bp.route("/api/channels/inbound/log")
def inbound_log():
    limit = int(request.args.get("limit", 50))
    entries = []
    if INBOUND_LOG_FILE.exists():
        try:
            entries = json.loads(INBOUND_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Failed to load inbound log entries", exc_info=True)
    return jsonify({"entries": entries[:limit]})


@bp.route("/api/channels/webhook/inbound", methods=["POST"])
def webhook_inbound():
    """Generic webhook inbound endpoint for the Webhook channel provider."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Not initialized"}), 503
    prov = registry.get("webhook")
    if not prov:
        return jsonify({"error": "Webhook provider not loaded"}), 404

    data = request.get_json(force=True) or {}
    headers = dict(request.headers)
    ok = prov.handle_inbound_request(data, headers)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Rejected"}), 403


@bp.route("/api/channels/whatsapp/webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    """WhatsApp Business API webhook (verification + events)."""
    registry = _get_registry()
    if not registry:
        return "", 503
    prov = registry.get("whatsapp")
    if not prov:
        return "", 404

    if request.method == "GET":
        challenge = prov.handle_webhook_verify(request.args.to_dict())
        if challenge:
            return challenge, 200
        return "Forbidden", 403

    data = request.get_json(force=True) or {}
    prov.handle_webhook_event(data)
    return "", 200


@bp.route("/api/channels/whatsapp/qr/start", methods=["POST"])
def whatsapp_qr_start():
    """Start WhatsApp Web QR code linking process."""
    registry = _get_registry()
    if not registry:
        return jsonify({"ok": False, "error": "Channels not initialized"}), 503
    prov = registry.get("whatsapp")
    if not prov:
        return jsonify({"ok": False, "error": "WhatsApp provider not loaded"}), 404
    if not hasattr(prov, "start_qr_link"):
        return jsonify({"ok": False, "error": "Provider does not support QR linking"}), 400

    data = request.get_json(force=True) or {}
    if data.get("mode"):
        all_cfg = load_channels_config()
        wa_cfg = all_cfg.get("whatsapp", {})
        wa_cfg["mode"] = data["mode"]
        wa_cfg["enabled"] = True
        all_cfg["whatsapp"] = wa_cfg
        save_channels_config(all_cfg)
        prov.configure(wa_cfg)

    result = prov.start_qr_link()
    return jsonify(result)


@bp.route("/api/channels/whatsapp/qr/status")
def whatsapp_qr_status():
    """Poll the current WhatsApp Web linking/connection status."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get("whatsapp")
    if not prov:
        return jsonify({"error": "WhatsApp provider not loaded"}), 404
    if not hasattr(prov, "get_link_status"):
        return jsonify({"error": "Provider does not support QR linking"}), 400

    result = prov.get_link_status()
    return jsonify(result)


@bp.route("/api/channels/whatsapp/logout", methods=["POST"])
def whatsapp_logout():
    """Logout from WhatsApp Web and clear session."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get("whatsapp")
    if not prov:
        return jsonify({"error": "WhatsApp provider not loaded"}), 404
    if not hasattr(prov, "logout_web"):
        return jsonify({"error": "Provider does not support web logout"}), 400

    result = prov.logout_web()
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
#  Telegram Setup Wizard
# ═══════════════════════════════════════════════════════════════

@bp.route("/api/channels/telegram/detect-chat", methods=["POST"])
def telegram_detect_chat():
    """Poll Telegram getUpdates to auto-detect the user's chat ID."""
    registry = _get_registry()
    if not registry:
        return jsonify({"ok": False, "error": "Channels not initialized"}), 503
    prov = registry.get("telegram")
    if not prov:
        return jsonify({"ok": False, "error": "Telegram provider not loaded"}), 404

    data = request.get_json(force=True) or {}
    bot_token = data.get("bot_token") or prov.bot_token
    if not bot_token:
        return jsonify({"ok": False, "error": "No bot token configured"}), 400

    import requests as http_requests
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        resp = http_requests.get(
            url, params={"limit": 10, "allowed_updates": ["message"]}, timeout=10
        )
        body = resp.json()
        if not body.get("ok"):
            return jsonify({"ok": False, "error": body.get("description", "API error")})

        for update in reversed(body.get("result", [])):
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            if chat_id:
                chat_id_str = str(chat_id)
                sender = msg.get("from", {})
                sender_name = (
                    (sender.get("first_name", "") + " " + sender.get("last_name", "")).strip()
                    or sender.get("username", "")
                )

                all_cfg = load_channels_config()
                tg_cfg = all_cfg.get("telegram", {})
                tg_cfg["default_chat_id"] = chat_id_str
                all_cfg["telegram"] = tg_cfg
                save_channels_config(all_cfg)

                if hasattr(prov, "default_chat_id"):
                    prov.default_chat_id = chat_id_str

                sender_id_str = str(sender.get("id", ""))
                added_to_allowlist = False
                if sender_id_str:
                    try:
                        from ghost import load_config, save_config
                        ghost_cfg = load_config()
                        allowed = ghost_cfg.get("channel_allowed_senders", [])
                        if sender_id_str not in allowed:
                            allowed.append(sender_id_str)
                            ghost_cfg["channel_allowed_senders"] = allowed
                            save_config(ghost_cfg)
                            added_to_allowlist = True

                            from ghost_dashboard import get_daemon
                            daemon = get_daemon()
                            if daemon:
                                daemon.cfg["channel_allowed_senders"] = allowed
                    except Exception as exc:
                        log.warning("Failed to auto-add sender to allowlist: %s", exc)

                return jsonify({
                    "ok": True,
                    "chat_id": chat_id_str,
                    "sender_id": sender_id_str,
                    "sender_name": sender_name,
                    "chat_type": chat.get("type", "private"),
                    "added_to_allowlist": added_to_allowlist,
                })

        return jsonify({"ok": False, "error": "no_messages"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


@bp.route("/api/channels/telegram/bot-info", methods=["POST"])
def telegram_bot_info():
    """Validate a bot token and return bot info."""
    data = request.get_json(force=True) or {}
    bot_token = data.get("bot_token", "")
    if not bot_token:
        return jsonify({"ok": False, "error": "No bot token provided"}), 400

    import requests as http_requests
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        resp = http_requests.get(url, timeout=10)
        body = resp.json()
        if body.get("ok"):
            bot = body["result"]
            return jsonify({
                "ok": True,
                "username": bot.get("username", ""),
                "first_name": bot.get("first_name", ""),
                "bot_id": bot.get("id", ""),
            })
        return jsonify({"ok": False, "error": body.get("description", "Invalid token")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)})


# ═══════════════════════════════════════════════════════════════
#  Phase 2 Endpoints
# ═══════════════════════════════════════════════════════════════

@bp.route("/api/channels/queue/stats")
def queue_stats():
    """Delivery queue statistics."""
    router = _get_router()
    if not router:
        return jsonify({"error": "Router not initialized"}), 503
    return jsonify(router.queue_stats())


@bp.route("/api/channels/queue/pending")
def queue_pending():
    """List pending deliveries in the queue."""
    try:
        from ghost_channels.queue import load_pending
        entries = load_pending()
        return jsonify({
            "pending": [{"id": e.id, "channel": e.channel, "to": e.to,
                         "text": e.text[:200], "retry_count": e.retry_count,
                         "enqueued_at": e.enqueued_at, "last_error": e.last_error}
                        for e in entries],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/channels/queue/failed")
def queue_failed():
    """List failed deliveries."""
    try:
        from ghost_channels.queue import load_failed
        entries = load_failed()
        return jsonify({
            "failed": [{"id": e.id, "channel": e.channel, "to": e.to,
                         "text": e.text[:200], "retry_count": e.retry_count,
                         "enqueued_at": e.enqueued_at, "last_error": e.last_error}
                        for e in entries],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/channels/<channel_id>/health")
def channel_health(channel_id):
    """Enhanced health check (probe + audit + issues)."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    result = {"channel": channel_id}
    try:
        from ghost_channels.health import HealthMixin
        if isinstance(prov, HealthMixin):
            result["probe"] = prov.probe().to_dict()
            result["audit"] = prov.audit().to_dict()
            result["issues"] = [i.to_dict() for i in prov.collect_issues()]
            result["snapshot"] = prov.build_snapshot().to_dict()
        else:
            result["health"] = prov.health_check()
    except ImportError:
        result["health"] = prov.health_check()
    except Exception as e:
        result["error"] = str(e)
    return jsonify(result)


@bp.route("/api/channels/health/all")
def all_channel_health():
    """Health summary for all channels."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    results = {}
    for cid in registry.list_configured():
        prov = registry.get(cid)
        if not prov:
            continue
        try:
            from ghost_channels.health import HealthMixin
            if isinstance(prov, HealthMixin):
                probe = prov.probe()
                results[cid] = {"ok": probe.ok, "latency_ms": probe.latency_ms,
                                "error": probe.error}
            else:
                h = prov.health_check()
                results[cid] = {"ok": h.get("configured", False),
                                "status": h.get("status", "unknown")}
        except Exception as e:
            results[cid] = {"ok": False, "error": str(e)}
    return jsonify({"channels": results})


@bp.route("/api/channels/<channel_id>/security")
def channel_security(channel_id):
    """Security status for a channel."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    try:
        from ghost_channels.security import SecurityMixin
        if isinstance(prov, SecurityMixin):
            ch_cfg = load_channels_config().get(channel_id, {})
            return jsonify({
                "channel": channel_id,
                "dm_policy": prov.resolve_dm_policy(ch_cfg).value,
                "allowlist_count": len(prov.get_allowlist(ch_cfg)),
                "blocklist_count": len(prov.get_blocklist(ch_cfg)),
                "warnings": prov.collect_security_warnings(ch_cfg),
            })
        return jsonify({"channel": channel_id, "security": "not supported"})
    except ImportError:
        return jsonify({"channel": channel_id, "security": "module not available"})


@bp.route("/api/channels/security/log")
def security_log():
    """Recent security events."""
    try:
        from ghost_channels.security import load_security_log
        limit = int(request.args.get("limit", 50))
        return jsonify({"events": load_security_log(limit)})
    except ImportError:
        return jsonify({"events": []})


@bp.route("/api/channels/security/allowlist")
def get_allowlist():
    """Return global channel security settings: dm_policy, allowed/blocked senders."""
    from ghost import load_config
    cfg = load_config()
    return jsonify({
        "channel_dm_policy": cfg.get("channel_dm_policy", "open"),
        "channel_allowed_senders": cfg.get("channel_allowed_senders", []),
        "channel_inbound_enabled": cfg.get("channel_inbound_enabled", True),
    })


@bp.route("/api/channels/security/allowlist", methods=["PUT"])
def update_allowlist():
    """Update global channel security allowlist and dm_policy."""
    from ghost import load_config, save_config
    data = request.get_json(silent=True) or {}
    cfg = load_config()

    if "channel_dm_policy" in data:
        policy = data["channel_dm_policy"]
        if policy not in ("open", "allowlist", "block", "blocklist"):
            return jsonify({"ok": False, "error": "Invalid dm_policy"}), 400
        cfg["channel_dm_policy"] = policy

    if "channel_allowed_senders" in data:
        senders = data["channel_allowed_senders"]
        if not isinstance(senders, list):
            return jsonify({"ok": False, "error": "channel_allowed_senders must be a list"}), 400
        cfg["channel_allowed_senders"] = [str(s).strip() for s in senders if str(s).strip()]

    if "channel_inbound_enabled" in data:
        cfg["channel_inbound_enabled"] = bool(data["channel_inbound_enabled"])

    save_config(cfg)

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        daemon.cfg.update(cfg)

    return jsonify({
        "ok": True,
        "channel_dm_policy": cfg["channel_dm_policy"],
        "channel_allowed_senders": cfg.get("channel_allowed_senders", []),
        "channel_inbound_enabled": cfg.get("channel_inbound_enabled", True),
    })


@bp.route("/api/channels/<channel_id>/onboard")
def onboard_steps(channel_id):
    """Get onboarding wizard steps for a channel."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    try:
        from ghost_channels.onboard import OnboardingMixin
        if isinstance(prov, OnboardingMixin):
            steps = prov.get_setup_steps()
            status = prov.get_setup_status()
            return jsonify({
                "channel": channel_id,
                "steps": [s.to_dict() for s in steps],
                "status": status,
            })
        return jsonify({"channel": channel_id, "onboard": "not supported"})
    except ImportError:
        return jsonify({"channel": channel_id, "onboard": "module not available"})


@bp.route("/api/channels/<channel_id>/onboard/validate", methods=["POST"])
def onboard_validate(channel_id):
    """Validate a single onboarding step."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    data = request.get_json(force=True) or {}
    step_id = data.get("step_id", "")
    value = data.get("value", "")

    try:
        from ghost_channels.onboard import OnboardingMixin
        if isinstance(prov, OnboardingMixin):
            result = prov.validate_step(step_id, value)
            return jsonify({"ok": result.ok, "message": result.message,
                            "warning": result.warning})
        return jsonify({"error": "Onboarding not supported"}), 400
    except ImportError:
        return jsonify({"error": "Onboarding module not available"}), 500


@bp.route("/api/channels/<channel_id>/onboard/complete", methods=["POST"])
def onboard_complete(channel_id):
    """Complete onboarding with collected config."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    config = request.get_json(force=True) or {}

    try:
        from ghost_channels.onboard import OnboardingMixin
        if isinstance(prov, OnboardingMixin):
            result = prov.complete_setup(config)
            if result.ok:
                all_cfg = load_channels_config()
                all_cfg[channel_id] = result.config
                save_channels_config(all_cfg)
            return jsonify({
                "ok": result.ok, "message": result.message,
                "test_sent": result.test_sent,
            })
        return jsonify({"error": "Onboarding not supported"}), 400
    except ImportError:
        return jsonify({"error": "Onboarding module not available"}), 500


@bp.route("/api/channels/<channel_id>/gateway")
def gateway_status(channel_id):
    """Gateway connection status."""
    registry = _get_registry()
    if not registry:
        return jsonify({"error": "Channels not initialized"}), 503
    prov = registry.get(channel_id)
    if not prov:
        return jsonify({"error": f"Unknown channel: {channel_id}"}), 404

    try:
        from ghost_channels.gateway import GatewayMixin
        if isinstance(prov, GatewayMixin):
            status = prov.gateway_status()
            return jsonify({"channel": channel_id, **status.to_dict()})
        return jsonify({"channel": channel_id, "gateway": "not a gateway channel"})
    except ImportError:
        return jsonify({"channel": channel_id, "gateway": "module not available"})
