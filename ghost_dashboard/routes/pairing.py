"""Device Pairing API — remote device auth with short-code approval flow."""

import sys
from pathlib import Path
from flask import Blueprint, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_device_auth import get_pairing_store

bp = Blueprint("pairing", __name__)


def _get_store():
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        cfg = daemon.cfg if daemon else {}
    except Exception:
        cfg = {}
    return get_pairing_store(cfg)


@bp.route("/api/pairing/request", methods=["POST"])
def pairing_request():
    """Create a pairing request (called by the remote device, no auth required)."""
    data = request.get_json(silent=True) or {}
    device_name = data.get("device_name", "").strip()
    device_type = data.get("device_type", "unknown").strip()

    if not device_name:
        return jsonify({"error": "device_name is required"}), 400

    try:
        result = _get_store().request_pairing(device_name, device_type)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 429


@bp.route("/api/pairing/pending", methods=["GET"])
def pairing_pending():
    """List pending pairing requests (dashboard view)."""
    pending = _get_store().list_pending()
    return jsonify({"pending": pending, "count": len(pending)})


@bp.route("/api/pairing/<request_id>/approve", methods=["POST"])
def pairing_approve(request_id):
    """Approve a pairing request. Returns the token ONCE."""
    data = request.get_json(silent=True) or {}
    scopes = data.get("scopes")

    try:
        result = _get_store().approve(request_id, scopes=scopes)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/api/pairing/<request_id>/reject", methods=["POST"])
def pairing_reject(request_id):
    """Reject a pairing request."""
    try:
        result = _get_store().reject(request_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/api/pairing/poll", methods=["POST"])
def pairing_poll():
    """Poll pairing status (called by the device waiting for approval)."""
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id", "")
    if not request_id:
        return jsonify({"error": "request_id is required"}), 400
    result = _get_store().poll(request_id)
    return jsonify(result)


@bp.route("/api/pairing/devices", methods=["GET"])
def pairing_devices():
    """List all paired devices."""
    devices = _get_store().list_paired()
    return jsonify({"devices": devices, "count": len(devices)})


@bp.route("/api/pairing/devices/<device_id>", methods=["DELETE"])
def pairing_revoke(device_id):
    """Revoke a paired device."""
    try:
        result = _get_store().revoke(device_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/api/pairing/devices/<device_id>/rotate", methods=["POST"])
def pairing_rotate(device_id):
    """Rotate a device's auth token."""
    try:
        result = _get_store().rotate_token(device_id)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@bp.route("/api/pairing/verify", methods=["POST"])
def pairing_verify():
    """Verify a device auth token."""
    data = request.get_json(silent=True) or {}
    token = data.get("token", "")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return jsonify({"error": "token required"}), 400

    result = _get_store().verify_token(token)
    if result:
        return jsonify({"valid": True, **result})
    return jsonify({"valid": False}), 401
