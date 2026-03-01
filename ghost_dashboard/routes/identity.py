"""Identity API — SOUL.md and USER.md management."""

import platform
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import SOUL_FILE, USER_FILE, DEFAULT_SOUL, DEFAULT_USER

bp = Blueprint("identity", __name__)


@bp.route("/api/soul")
def get_soul():
    content = SOUL_FILE.read_text() if SOUL_FILE.exists() else ""
    return jsonify({"content": content, "path": str(SOUL_FILE)})


@bp.route("/api/soul", methods=["PUT"])
def put_soul():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    SOUL_FILE.write_text(content)
    return jsonify({"ok": True, "chars": len(content)})


@bp.route("/api/soul/reset", methods=["POST"])
def reset_soul():
    SOUL_FILE.write_text(DEFAULT_SOUL)
    return jsonify({"ok": True, "content": DEFAULT_SOUL})


@bp.route("/api/user")
def get_user():
    content = USER_FILE.read_text() if USER_FILE.exists() else ""
    return jsonify({"content": content, "path": str(USER_FILE)})


@bp.route("/api/user", methods=["PUT"])
def put_user():
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    USER_FILE.write_text(content)
    return jsonify({"ok": True, "chars": len(content)})


@bp.route("/api/user/reset", methods=["POST"])
def reset_user():
    content = DEFAULT_USER % {"os": platform.system()}
    USER_FILE.write_text(content)
    return jsonify({"ok": True, "content": content})
