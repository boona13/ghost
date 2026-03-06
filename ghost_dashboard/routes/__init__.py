"""Register all API route blueprints."""

import logging
from flask import Flask, send_from_directory, jsonify
from pathlib import Path

log = logging.getLogger(__name__)


def register_routes(app: Flask):
    from .status import bp as status_bp
    from .config import bp as config_bp
    from .models import bp as models_bp
    from .identity import bp as identity_bp
    from .skills import bp as skills_bp
    from .cron import bp as cron_bp
    from .memory import bp as memory_bp
    from .feed import bp as feed_bp
    from .daemon import bp as daemon_bp
    from .evolve import bp as evolve_bp
    from .chat import bp as chat_bp
    from .integrations import bp as integrations_bp
    from .autonomy import bp as autonomy_bp
    from .setup import bp as setup_bp
    from .accounts import bp as accounts_bp
    from .security import bp as security_bp
    from .console import bp as console_bp
    from .channels import bp as channels_bp
    from .future_features import bp as future_features_bp
    from .voice import bp as voice_bp
    from .canvas import bp as canvas_bp
    from .usage import bp as usage_bp
    from .webhooks import bp as webhooks_bp
    from .projects import bp as projects_bp
    from .prs import bp as prs_bp
    from .doctor import bp as doctor_bp
    from .mcp import bp as mcp_bp
    from .langfuse import bp as langfuse_bp
    from .browser_use import bp as browser_use_bp
    from .pairing import bp as pairing_bp
    from .nodes import bp as nodes_bp
    from .media import bp as media_bp
    from .extensions import bp as extensions_bp
    from .audit import bp as audit_bp

    for bp in [status_bp, config_bp, models_bp, identity_bp,
               skills_bp, cron_bp, memory_bp, feed_bp, daemon_bp, evolve_bp,
               chat_bp, integrations_bp, autonomy_bp, setup_bp, accounts_bp,
               security_bp, console_bp, channels_bp, future_features_bp,
               voice_bp, canvas_bp, usage_bp, webhooks_bp, projects_bp,
               prs_bp, doctor_bp, mcp_bp, langfuse_bp, browser_use_bp,
               pairing_bp, nodes_bp, media_bp, extensions_bp, audit_bp]:
        app.register_blueprint(bp)

    _register_extension_routes(app)
    _register_extension_static(app)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")


def _register_extension_routes(app: Flask):
    """Register Flask blueprints from loaded extensions."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon or not hasattr(daemon, "extension_manager") or not daemon.extension_manager:
        return
    for bp in daemon.extension_manager.get_all_routes():
        try:
            app.register_blueprint(bp)
        except Exception as e:
            log.warning("Failed to register extension blueprint: %s", e)


def _register_extension_static(app: Flask):
    """Serve static files from extensions at /extensions/<name>/static/..."""
    import re as _re

    @app.route("/extensions/<name>/static/<path:filename>")
    def extension_static(name, filename):
        if not _re.match(r"^[a-zA-Z0-9_-]+$", name):
            return jsonify({"error": "Invalid extension name"}), 400
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if not daemon or not hasattr(daemon, "extension_manager") or not daemon.extension_manager:
            return jsonify({"error": "Extension system not initialized"}), 503
        ext_dir = daemon.extension_manager.get_extension_dir(name)
        if not ext_dir:
            return jsonify({"error": "Extension not found"}), 404
        static_dir = ext_dir / "static"
        if not static_dir.is_dir():
            return jsonify({"error": "No static files"}), 404
        return send_from_directory(str(static_dir), filename)
