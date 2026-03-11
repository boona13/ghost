"""
Ghost Dashboard — Flask web app for controlling Ghost.

Can run standalone:     run_dashboard(port=3333)
Or embedded in daemon:  start_with_daemon(daemon, port=3333)
"""

import os, webbrowser, threading, logging, socket, secrets
from werkzeug.serving import make_server
from flask import Flask, request, jsonify
from pathlib import Path

# CSRF protection (optional - gracefully degrades if not installed)
try:
    from flask_wtf.csrf import CSRFProtect, generate_csrf
    _csrf_available = True
except ImportError:
    _csrf_available = False
    CSRFProtect = None
    generate_csrf = None


def _is_port_available(host: str, port: int) -> bool:
    """Check if a port is available by attempting to bind a test socket.
    
    This prevents calling make_server on an in-use port, which would trigger
    werkzeug's internal sys.exit(1) call (see BaseWSGIServer.__init__).
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False

DASHBOARD_DIR = Path(__file__).resolve().parent

_daemon_ref = None
_server_ref = None


def get_daemon():
    """Return the live GhostDaemon instance (or None if running standalone)."""
    return _daemon_ref


def create_app():
    app = Flask(
        __name__,
        template_folder=str(DASHBOARD_DIR / "templates"),
        static_folder=str(DASHBOARD_DIR / "static"),
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    from .routes import register_routes
    register_routes(app)

    # Initialize CSRF protection (if available)
    if _csrf_available:
        app.config["SECRET_KEY"] = os.environ.get("GHOST_SECRET_KEY", secrets.token_hex(32))
        app.config["WTF_CSRF_TIME_LIMIT"] = 3600  # 1 hour token validity
        csrf = CSRFProtect(app)
        # Exempt webhook endpoints that use Bearer token auth (all paths under /api/webhooks/)
        csrf.exempt("/api/webhooks/")
        # Exempt CSRF token endpoint itself
        csrf.exempt("/api/csrf-token")
    else:
        logging.getLogger("ghost_dashboard").warning(
            "CSRF protection not available - install flask-wtf: pip install flask-wtf"
        )

    # Context processor to provide csrf_token() in templates (fallback when flask-wtf not installed)
    @app.context_processor
    def inject_csrf_token():
        if _csrf_available and generate_csrf:
            return dict(csrf_token=generate_csrf)
        return dict(csrf_token=lambda: "")


    @app.after_request
    def add_no_cache(response):
        if "text/javascript" in response.content_type or "text/css" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.route("/api/csrf-token", methods=["GET"])
    def get_csrf_token():
        """Return a fresh CSRF token for the frontend."""
        if _csrf_available and generate_csrf:
            token = generate_csrf()
            return jsonify({"csrf_token": token})
        return jsonify({"csrf_token": ""})

    return app


def start_with_daemon(daemon, port=3333, open_browser=False):
    """Start dashboard as a background thread inside the Ghost daemon."""
    global _daemon_ref, _server_ref
    _daemon_ref = daemon

    app = create_app()

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)

    bind_host = os.environ.get("GHOST_BIND_HOST", "127.0.0.1")

    if not _is_port_available(bind_host, port):
        print(f"  ⚠ Dashboard port {port} is already in use — refusing to start a second instance.")
        print(f"    Run ./stop.sh first, or let ./start.sh handle cleanup automatically.")
        return None

    try:
        _server_ref = make_server(bind_host, port, app, threaded=True)
    except OSError as e:
        print(f"  ⚠ Dashboard bind failed on {bind_host}:{port}: {e}")
        return None

    t = threading.Thread(target=_server_ref.serve_forever, daemon=True, name="ghost-dashboard")
    t.start()

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    return port


def stop_dashboard():
    """Shut down the background dashboard server."""
    global _server_ref, _daemon_ref
    if _server_ref:
        _server_ref.shutdown()
        _server_ref = None
    _daemon_ref = None


def run_dashboard(port=3333, open_browser=True):
    """Run dashboard as standalone (blocking). For `python ghost.py dashboard`.

    Uses resilient port binding (same strategy as start_with_daemon) so a busy
    default port does not crash the process with exit code 1.
    """
    app = create_app()

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)

    bind_host = os.environ.get("GHOST_BIND_HOST", "127.0.0.1")

    if not _is_port_available(bind_host, port):
        print(f"\n  ⚠ Dashboard port {port} is already in use.")
        print(f"    Another Ghost instance may be running. Use ./stop.sh first.\n")
        return

    try:
        server = make_server(bind_host, port, app, threaded=True)
    except OSError as e:
        print(f"\n  ⚠ Dashboard bind failed on {bind_host}:{port}: {e}\n")
        return

    url = f"http://localhost:{port}"
    print(f"\n  👻 Ghost Dashboard → {url}\n")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
        except (OSError, RuntimeError) as exc:
            logging.getLogger("ghost_dashboard").warning("Server shutdown error: %s", exc)
