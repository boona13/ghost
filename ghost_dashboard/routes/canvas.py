"""Canvas API — visual content panel for the agent."""

import sys
from flask import Blueprint, jsonify, request, send_from_directory, abort
from pathlib import Path

bp = Blueprint("canvas", __name__)

CANVAS_ROOT = Path.home() / ".ghost" / "canvas"

_project = str(Path(__file__).resolve().parent.parent.parent)
if _project not in sys.path:
    sys.path.insert(0, _project)


def _get_engine():
    try:
        from ghost_canvas import get_canvas_engine
        return get_canvas_engine()
    except Exception:
        return None


@bp.route("/api/canvas/state")
def canvas_state():
    engine = _get_engine()
    if not engine:
        return jsonify({"visible": False, "version": 0})
    return jsonify(engine.get_state())


@bp.route("/api/canvas/present", methods=["POST"])
def canvas_present():
    engine = _get_engine()
    if not engine:
        return jsonify({"error": "Canvas unavailable"}), 503
    target = (request.json or {}).get("target")
    result = engine.present(target)
    return jsonify(result)


@bp.route("/api/canvas/hide", methods=["POST"])
def canvas_hide():
    engine = _get_engine()
    if not engine:
        return jsonify({"error": "Canvas unavailable"}), 503
    result = engine.hide()
    return jsonify(result)


@bp.route("/api/canvas/navigate", methods=["POST"])
def canvas_navigate():
    engine = _get_engine()
    if not engine:
        return jsonify({"error": "Canvas unavailable"}), 503
    target = (request.json or {}).get("target", "")
    if not target:
        return jsonify({"error": "target required"}), 400
    result = engine.navigate(target)
    return jsonify(result)


@bp.route("/api/canvas/eval", methods=["POST"])
def canvas_eval():
    engine = _get_engine()
    if not engine:
        return jsonify({"error": "Canvas unavailable"}), 503
    code = (request.json or {}).get("code", "")
    if not code:
        return jsonify({"error": "code required"}), 400
    result = engine.eval_js(code)
    return jsonify({"ok": True, "result": result})


@bp.route("/api/canvas/pending_js")
def canvas_pending_js():
    engine = _get_engine()
    if not engine:
        return jsonify({"scripts": []})
    scripts = engine.pop_pending_js()
    return jsonify({"scripts": scripts})


@bp.route("/api/canvas/message", methods=["POST"])
def canvas_message():
    """Receive A2UI messages from canvas content."""
    engine = _get_engine()
    if not engine:
        return jsonify({"error": "Canvas unavailable"}), 503
    data = request.json or {}
    action = data.get("action", "")
    payload = data.get("data", {})
    if not action:
        return jsonify({"error": "action required"}), 400
    engine.receive_message(action, payload)
    return jsonify({"ok": True})


_BRIDGE_SCRIPT = """
<script>
(function(){
  window.ghostCanvas = {
    send: function(action, data) {
      return fetch('/api/canvas/message', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: action, data: data || {}})
      }).then(function(r){ return r.json(); });
    }
  };
})();
</script>
"""


@bp.route("/canvas/content/<path:filepath>")
def canvas_content(filepath):
    """Serve static files from a canvas session directory, injecting JS bridge for HTML."""
    full = (CANVAS_ROOT / filepath).resolve()
    if not str(full).startswith(str(CANVAS_ROOT.resolve())):
        abort(403)
    if not full.is_file():
        abort(404)
    if full.suffix.lower() in ('.html', '.htm'):
        html = full.read_text(encoding="utf-8")
        if '</head>' in html:
            html = html.replace('</head>', _BRIDGE_SCRIPT + '</head>', 1)
        elif '<body' in html:
            html = html.replace('<body', _BRIDGE_SCRIPT + '<body', 1)
        else:
            html = _BRIDGE_SCRIPT + html
        from flask import Response
        return Response(html, mimetype='text/html')
    return send_from_directory(str(full.parent), full.name)
