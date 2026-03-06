"""Media Gallery API — browse, serve, and manage generated media."""

import logging
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file

log = logging.getLogger(__name__)

bp = Blueprint("media", __name__)

GHOST_HOME = Path.home() / ".ghost"
MEDIA_DIR = GHOST_HOME / "media"


def _get_daemon():
    from ghost_dashboard import get_daemon
    return get_daemon()


@bp.route("/api/media")
def list_media():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"items": [], "stats": {}, "error": "Media store not initialized"})

    media_type = request.args.get("type", "")
    source_node = request.args.get("node", "")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    items = daemon.media_store.list_media(
        media_type=media_type or None,
        source_node=source_node or None,
        limit=min(limit, 200),
        offset=offset,
    )
    stats = daemon.media_store.get_stats()

    return jsonify({"items": items, "stats": stats})


@bp.route("/api/media/<media_id>")
def get_media_info(media_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"error": "Media store not initialized"}), 503

    item = daemon.media_store.get(media_id)
    if not item:
        return jsonify({"error": "Media not found"}), 404
    return jsonify(item)


@bp.route("/api/media/<media_id>/file")
def serve_media_file(media_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"error": "Media store not initialized"}), 503

    item = daemon.media_store.get(media_id)
    if not item:
        return jsonify({"error": "Media not found"}), 404

    file_path = Path(item["path"]).resolve()
    media_root = MEDIA_DIR.resolve()
    if not file_path.is_relative_to(media_root):
        log.warning("Path traversal blocked: %s not under %s", file_path, media_root)
        return jsonify({"error": "Access denied"}), 403
    if not file_path.exists():
        return jsonify({"error": "File not found on disk"}), 404

    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".glb": "model/gltf-binary", ".obj": "model/obj",
    }
    ext = file_path.suffix.lower()
    mime = mime_map.get(ext, "application/octet-stream")

    return send_file(str(file_path), mimetype=mime)


@bp.route("/api/media/<media_id>", methods=["DELETE"])
def delete_media(media_id):
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"error": "Media store not initialized"}), 503

    ok = daemon.media_store.delete(media_id)
    return jsonify({"ok": ok})


@bp.route("/api/media/cleanup", methods=["POST"])
def cleanup_media():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"error": "Media store not initialized"}), 503

    expired = daemon.media_store.cleanup_expired()
    budget = daemon.media_store.enforce_disk_budget()
    return jsonify({"expired_deleted": expired, "budget_deleted": budget})


@bp.route("/api/media/stats")
def media_stats():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "media_store") or not daemon.media_store:
        return jsonify({"error": "Media store not initialized"}), 503

    return jsonify(daemon.media_store.get_stats())
