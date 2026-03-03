"""Browser-Use API — AI-native browser automation dashboard endpoints."""

import logging
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("browser_use", __name__)

# Import browser-use module
try:
    from ghost_browser_use import (
        browser_use_create_session,
        browser_use_run_task,
        browser_use_get_status,
        browser_use_list_sessions,
        browser_use_close_session,
        browser_use_navigate,
        browser_use_get_html,
        browser_use_screenshot,
        BROWSER_USE_AVAILABLE,
    )
except ImportError:
    log.warning("ghost_browser_use module not available")
    BROWSER_USE_AVAILABLE = False


@bp.route("/api/browser-use/sessions", methods=["GET"])
def list_sessions():
    """List all browser-use sessions."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "browser-use not installed. Run: pip install browser-use",
            "available": False
        }), 503
    
    try:
        result = browser_use_list_sessions()
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to list browser-use sessions")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions", methods=["POST"])
def create_session():
    """Create a new browser-use session."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "browser-use not installed. Run: pip install browser-use",
            "available": False
        }), 503
    
    try:
        data = request.get_json() or {}
        url = data.get("url", "https://google.com")
        session_id = browser_use_create_session(url=url)
        return jsonify({"success": True, "session_id": session_id, "url": url})
    except Exception as exc:
        log.exception("Failed to create browser-use session")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    """Get session status and history."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        result = browser_use_get_status(session_id)
        if not result.get("success"):
            return jsonify(result), 404
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to get browser-use session")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Close and delete a session."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        result = browser_use_close_session(session_id)
        if not result.get("success"):
            return jsonify(result), 404
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to close browser-use session")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>/task", methods=["POST"])
def run_task(session_id):
    """Run an AI-powered task on a session."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        data = request.get_json() or {}
        task = data.get("task")
        if not task:
            return jsonify({"success": False, "error": "task is required"}), 400
        
        result = browser_use_run_task(
            session_id=session_id,
            task=task,
            api_key=data.get("api_key"),
            model=data.get("model", "gpt-4o"),
            headless=data.get("headless", True),
        )
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to run browser-use task")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>/navigate", methods=["POST"])
def navigate(session_id):
    """Navigate to a URL."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        data = request.get_json() or {}
        url = data.get("url")
        if not url:
            return jsonify({"success": False, "error": "url is required"}), 400
        
        result = browser_use_navigate(session_id, url)
        if not result.get("success"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to navigate")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>/html", methods=["GET"])
def get_html(session_id):
    """Get current page HTML."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        max_length = request.args.get("max_length", 50000, type=int)
        result = browser_use_get_html(session_id, max_length=max_length)
        if not result.get("success"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to get HTML")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/sessions/<session_id>/screenshot", methods=["POST"])
def take_screenshot(session_id):
    """Take a screenshot."""
    if not BROWSER_USE_AVAILABLE:
        return jsonify({"success": False, "error": "browser-use not installed"}), 503
    
    try:
        data = request.get_json() or {}
        result = browser_use_screenshot(
            session_id=session_id,
            output_path=data.get("output_path"),
            full_page=data.get("full_page", True),
        )
        if not result.get("success"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as exc:
        log.exception("Failed to take screenshot")
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/browser-use/status", methods=["GET"])
def get_status():
    """Get browser-use availability status."""
    return jsonify({
        "available": BROWSER_USE_AVAILABLE,
        "message": "browser-use is installed" if BROWSER_USE_AVAILABLE else "browser-use not installed. Run: pip install browser-use"
    })
