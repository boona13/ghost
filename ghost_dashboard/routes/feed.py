"""Feed API — activity feed."""

import json
from flask import Blueprint, jsonify

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import FEED_FILE

bp = Blueprint("feed", __name__)


@bp.route("/api/feed")
def get_feed():
    if not FEED_FILE.exists():
        return jsonify({"entries": []})
    try:
        entries = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        return jsonify({"entries": entries})
    except Exception:
        return jsonify({"entries": []})
