"""Console API — real-time event stream for the dashboard terminal."""

import json
import time
import sys
from pathlib import Path
from flask import Blueprint, Response, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from ghost_console import console_bus

bp = Blueprint("console", __name__)


@bp.route("/api/console/history")
def console_history():
    limit = request.args.get("limit", 200, type=int)
    after_seq = request.args.get("after_seq", None, type=int)
    events = console_bus.history(limit=limit, after_seq=after_seq)
    return jsonify({"events": events, "total": console_bus.count})


@bp.route("/api/console/stream")
def console_stream():
    """SSE endpoint — streams console events in real time."""
    def generate():
        sub_id, wake = console_bus.subscribe()
        try:
            last_seq = 0
            burst = console_bus.history(limit=100)
            if burst:
                for evt in burst:
                    yield f"data: {json.dumps(evt)}\n\n"
                last_seq = burst[-1].get("seq", 0)

            while True:
                wake.wait(timeout=15)
                wake.clear()

                new = console_bus.history(limit=50, after_seq=last_seq)
                for evt in new:
                    yield f"data: {json.dumps(evt)}\n\n"
                    last_seq = evt.get("seq", 0)

                if not new:
                    yield f": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            console_bus.unsubscribe(sub_id)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/console/clear", methods=["POST"])
def console_clear():
    console_bus.clear()
    return jsonify({"ok": True})


@bp.route("/api/processes")
def list_processes_compat():
    """Compatibility shim for old process manager endpoints."""
    return jsonify({"processes": []})
