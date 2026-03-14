"""Browser-Use API — DEPRECATED.

browser-use has been removed in favor of PinchTab (ghost_browser.py).
These endpoints return 410 Gone to inform any remaining callers.
"""

import logging
from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

bp = Blueprint("browser_use", __name__)

_GONE_MSG = "browser-use has been removed. Browser automation now uses PinchTab via ghost_browser.py."


@bp.route("/api/browser-use/sessions", methods=["GET", "POST"])
@bp.route("/api/browser-use/sessions/<session_id>", methods=["GET", "DELETE"])
@bp.route("/api/browser-use/sessions/<session_id>/task", methods=["POST"])
@bp.route("/api/browser-use/sessions/<session_id>/navigate", methods=["POST"])
@bp.route("/api/browser-use/sessions/<session_id>/html", methods=["GET"])
@bp.route("/api/browser-use/sessions/<session_id>/screenshot", methods=["POST"])
def _gone(**kwargs):
    return jsonify({"success": False, "error": _GONE_MSG}), 410


@bp.route("/api/browser-use/status", methods=["GET"])
def get_status():
    return jsonify({
        "available": False,
        "message": _GONE_MSG,
    })
