import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request

log = logging.getLogger("ghost.extension.stabilization_mode")

GHOST_HOME = Path.home() / ".ghost"
FEATURES_FILE = GHOST_HOME / "future_features.json"
CRASH_REPORT = GHOST_HOME / "crash_report.json"
CRASH_LOG = GHOST_HOME / "crash_history.json"
HISTORY_FILE = "stabilization_events.json"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        raw = path.read_text(encoding="utf-8")
        loaded = json.loads(raw) if raw.strip() else default
        return loaded
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        log.warning("Failed to read JSON file %s: %s", path, exc)
        return default


def _safe_save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("Failed to write JSON file %s: %s", path, exc)
        raise


def register(api):
    api.register_setting({
        "key": "stabilization_mode",
        "type": "boolean",
        "default": False,
        "label": "Stabilization Mode",
        "description": "Lock down feature intake while core stabilization is active",
    })
    api.register_setting({
        "key": "stabilization_require_p0_approval",
        "type": "boolean",
        "default": True,
        "label": "Require P0 Approval",
        "description": "Keep P0 items in approval_required while stabilization mode is enabled",
    })
    api.register_setting({
        "key": "stabilization_auto_reject_p1_p2",
        "type": "boolean",
        "default": True,
        "label": "Auto-reject P1/P2",
        "description": "Reject new P1/P2 items during stabilization mode",
    })
