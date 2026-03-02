"""Webhook Triggers API — create, list, delete, fire, and inspect webhook triggers."""

import json
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

bp = Blueprint("webhooks", __name__)


def _get_handler():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, "webhook_handler") and daemon.webhook_handler:
        return daemon.webhook_handler
    return None


# ── Inbound webhook endpoint (external services POST here) ──────

@bp.route("/api/webhooks/<trigger_id>", methods=["POST"])
def fire_webhook(trigger_id):
    handler = _get_handler()
    if not handler:
        return jsonify({"ok": False, "error": "Webhooks not initialized"}), 503

    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        payload = {}

    raw_body = request.get_data()
    headers = dict(request.headers)

    result = handler.handle(
        trigger_id=trigger_id,
        payload=payload,
        headers=headers,
        raw_body=raw_body,
    )

    status_code = result.pop("status", 200)
    return jsonify(result), status_code


# ── Trigger management (dashboard) ──────────────────────────────

@bp.route("/api/webhooks/triggers", methods=["GET"])
def list_triggers():
    handler = _get_handler()
    if not handler:
        return jsonify({"triggers": [], "error": "Webhooks not initialized"}), 503

    triggers = handler.registry.list_all()
    return jsonify({
        "triggers": [t.to_dict() for t in triggers],
    })


@bp.route("/api/webhooks/triggers", methods=["POST"])
def create_trigger():
    handler = _get_handler()
    if not handler:
        return jsonify({"ok": False, "error": "Webhooks not initialized"}), 503

    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400

    template_id = data.get("template_id", "")
    if template_id:
        trigger = handler.registry.create_from_template(
            template_id,
            name=name,
            cooldown_seconds=data.get("cooldown_seconds", 30),
            hmac_header=data.get("hmac_header", ""),
            hmac_secret=data.get("hmac_secret", ""),
        )
        if not trigger:
            from ghost_webhooks import BUILTIN_TEMPLATES
            available = list(BUILTIN_TEMPLATES.keys())
            return jsonify({
                "ok": False,
                "error": f"Unknown template '{template_id}'",
                "available_templates": available,
            }), 400
    else:
        prompt_template = data.get("prompt_template", "")
        if not prompt_template:
            return jsonify({
                "ok": False,
                "error": "Either prompt_template or template_id is required",
            }), 400
        trigger = handler.registry.create(
            name=name,
            prompt_template=prompt_template,
            event_type=data.get("event_type", "generic"),
            extract_fields=data.get("extract_fields", {}),
            cooldown_seconds=data.get("cooldown_seconds", 30),
            hmac_header=data.get("hmac_header", ""),
            hmac_secret=data.get("hmac_secret", ""),
        )

    return jsonify({"ok": True, "trigger": trigger.to_dict()}), 201


@bp.route("/api/webhooks/triggers/<trigger_id>", methods=["DELETE"])
def delete_trigger(trigger_id):
    handler = _get_handler()
    if not handler:
        return jsonify({"ok": False, "error": "Webhooks not initialized"}), 503

    ok = handler.registry.delete(trigger_id)
    if ok:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Trigger not found"}), 404


@bp.route("/api/webhooks/triggers/<trigger_id>", methods=["PATCH"])
def update_trigger(trigger_id):
    handler = _get_handler()
    if not handler:
        return jsonify({"ok": False, "error": "Webhooks not initialized"}), 503

    data = request.get_json(force=True, silent=True) or {}
    trigger = handler.registry.update(trigger_id, **data)
    if trigger:
        return jsonify({"ok": True, "trigger": trigger.to_dict()})
    return jsonify({"ok": False, "error": "Trigger not found"}), 404


# ── History ──────────────────────────────────────────────────────

@bp.route("/api/webhooks/history", methods=["GET"])
def webhook_history():
    handler = _get_handler()
    if not handler:
        return jsonify({"events": []}), 503

    limit = request.args.get("limit", 50, type=int)
    events = handler.history.recent(limit)
    return jsonify({"events": events})


# ── Built-in templates listing ───────────────────────────────────

@bp.route("/api/webhooks/templates", methods=["GET"])
def list_templates():
    from ghost_webhooks import BUILTIN_TEMPLATES
    templates = {}
    for tid, tmpl in BUILTIN_TEMPLATES.items():
        templates[tid] = {
            "name": tmpl["name"],
            "extract_fields": tmpl["extract_fields"],
            "prompt_template": tmpl["prompt_template"][:200] + "...",
        }
    return jsonify({"templates": templates})
