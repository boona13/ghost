"""Accounts API — list and delete saved credentials."""

import json
from pathlib import Path
from flask import Blueprint, jsonify, request

bp = Blueprint("accounts", __name__)

CREDENTIALS_FILE = Path.home() / ".ghost" / "credentials.json"


def _load():
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save(creds):
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))


@bp.route("/api/accounts")
def list_accounts():
    creds = _load()
    safe = []
    for i, c in enumerate(creds):
        safe.append({
            "index": i,
            "service": c.get("service", ""),
            "username": c.get("username", ""),
            "email": c.get("email", ""),
            "created_at": c.get("created_at", ""),
            "notes": c.get("notes", ""),
        })
    return jsonify({"accounts": safe, "total": len(safe)})


@bp.route("/api/accounts/<int:index>", methods=["DELETE"])
def delete_account(index):
    creds = _load()
    if index < 0 or index >= len(creds):
        return jsonify({"ok": False, "error": "Invalid index"}), 404
    removed = creds.pop(index)
    _save(creds)
    label = removed.get("email") or removed.get("username") or removed.get("service")
    return jsonify({"ok": True, "deleted": label})
