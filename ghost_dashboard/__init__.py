"""
Ghost Dashboard — Flask web app for controlling Ghost.

Can run standalone:     run_dashboard(port=3333)
Or embedded in daemon:  start_with_daemon(daemon, port=3333)
"""

import os, webbrowser, threading, logging, socket
from werkzeug.serving import make_server
from flask import Flask
from pathlib import Path


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

    @app.after_request
    def add_no_cache(response):
        if "text/javascript" in response.content_type or "text/css" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    return app


def start_with_daemon(daemon, port=3333, open_browser=False):
    """Start dashboard as a background thread inside the Ghost daemon."""
    global _daemon_ref, _server_ref
    _daemon_ref = daemon

    app = create_app()

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)

    bind_host = os.environ.get("GHOST_BIND_HOST", "127.0.0.1")

    # Find an available port using pre-check to avoid werkzeug's sys.exit(1)
    candidate_ports = [port] + list(range(port + 1, port + 11))
    actual_port = None
    for p in candidate_ports:
        if _is_port_available(bind_host, p):
            actual_port = p
            break
        elif p == port:
            print(f"  ⚠ Dashboard port {p} is in use, trying fallback ports...")
    
    if actual_port is None:
        print(f"  ⚠ Dashboard: could not find open port near {port}")
        return None
    
    try:
        _server_ref = make_server(bind_host, actual_port, app, threaded=True)
        if actual_port != port:
            print(f"  ℹ Dashboard fallback to available port {actual_port}")
    except OSError as e:
        print(f"  ⚠ Dashboard bind failed on {bind_host}:{actual_port}: {e}")
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

    # Find an available port using pre-check to avoid werkzeug's sys.exit(1)
    candidate_ports = [port] + list(range(port + 1, port + 11))
    actual_port = None
    for p in candidate_ports:
        if _is_port_available(bind_host, p):
            actual_port = p
            break
        elif p == port:
            print(f"\n  ⚠ Dashboard port {p} is in use, trying fallback ports...")
    
    if actual_port is None:
        print(f"\n  ⚠ Ghost Dashboard: could not find open port near {port}\n")
        return
    
    try:
        server = make_server(bind_host, actual_port, app, threaded=True)
        if actual_port != port:
            print(f"  ℹ Dashboard fallback to available port {actual_port}")
    except OSError as e:
        print(f"\n  ⚠ Dashboard bind failed on {bind_host}:{actual_port}: {e}\n")
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
        except Exception:
            pass
