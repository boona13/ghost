"""Usage API — live token/model usage telemetry.

Provides real-time usage state: current model, active call indicator, session token count.
"""

from flask import Blueprint, jsonify
from ghost_usage import get_usage_tracker

bp = Blueprint("usage", __name__, url_prefix="/api/usage")


@bp.route("/live", methods=["GET"])
def live_usage():
    """Return current usage snapshot.
    
    Returns:
        {
            "model": str,           # Current model name
            "provider": str,        # Current provider ID
            "active": bool,         # Whether a call is in progress
            "session_tokens": int,  # Total tokens this session
            "calls_this_session": int,  # Number of successful calls
            "last_call_timestamp": float|null,
            "last_call_tokens": int,
        }
    """
    tracker = get_usage_tracker()
    snapshot = tracker.get_snapshot()
    return jsonify(snapshot.to_dict())


@bp.route("/reset", methods=["POST"])
def reset_session():
    """Reset session-level counters."""
    tracker = get_usage_tracker()
    tracker.reset_session()
    return jsonify({"status": "ok"})
