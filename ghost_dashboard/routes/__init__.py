"""Register all API route blueprints."""

from flask import Flask, send_from_directory
from pathlib import Path


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

    for bp in [status_bp, config_bp, models_bp, identity_bp,
               skills_bp, cron_bp, memory_bp, feed_bp, daemon_bp, evolve_bp,
               chat_bp, integrations_bp, autonomy_bp, setup_bp, accounts_bp,
               security_bp, console_bp, channels_bp, future_features_bp,
               voice_bp, canvas_bp, usage_bp, webhooks_bp, projects_bp,
               prs_bp, doctor_bp, mcp_bp, langfuse_bp, browser_use_bp]:
        app.register_blueprint(bp)

    @app.route("/")
    def index():
        from flask import render_template
        return render_template("index.html")
