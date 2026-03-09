"""Artifacts API — list and serve per-message deliverables."""

import mimetypes
from pathlib import Path
from flask import Blueprint, jsonify, send_from_directory, abort

bp = Blueprint("artifacts", __name__)

ARTIFACTS_ROOT = Path.home() / ".ghost" / "artifacts"


@bp.route("/api/chat/artifacts/<message_id>")
def list_artifacts(message_id):
    """List files produced during a chat message."""
    artifacts_dir = ARTIFACTS_ROOT / message_id
    if not artifacts_dir.is_dir():
        return jsonify({"ok": True, "message_id": message_id, "files": []})

    files = []
    for f in sorted(artifacts_dir.iterdir()):
        if not f.is_file():
            continue
        mime, _ = mimetypes.guess_type(f.name)
        files.append({
            "name": f.name,
            "size": f.stat().st_size,
            "type": mime or "application/octet-stream",
            "modified": f.stat().st_mtime,
        })

    return jsonify({"ok": True, "message_id": message_id, "files": files})


@bp.route("/api/chat/artifacts/<message_id>/<path:filename>")
def serve_artifact(message_id, filename):
    """Serve a single artifact file for download or inline preview."""
    artifacts_dir = ARTIFACTS_ROOT / message_id
    if not artifacts_dir.is_dir():
        abort(404)

    file_path = artifacts_dir / filename
    if not file_path.is_file():
        abort(404)

    mime, _ = mimetypes.guess_type(filename)
    is_previewable = mime and (
        mime.startswith("image/")
        or mime.startswith("text/")
        or mime == "application/pdf"
        or mime == "application/json"
    )

    return send_from_directory(
        str(artifacts_dir),
        filename,
        mimetype=mime,
        as_attachment=not is_previewable,
    )
