"""Subagents API — browse subagent types and execution history."""

import logging
import sys
from pathlib import Path
from flask import Blueprint, jsonify

log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_subagent_config import (
    BUILTIN_SUBAGENTS,
    list_background_tasks,
    SubagentStatus,
)

bp = Blueprint("subagents", __name__)


@bp.route("/api/subagents/types")
def subagent_types():
    types = []
    for name, cfg in BUILTIN_SUBAGENTS.items():
        types.append({
            "name": cfg.name,
            "description": cfg.description,
            "system_prompt": cfg.system_prompt,
            "tools": cfg.tools,
            "disallowed_tools": cfg.disallowed_tools,
            "model": cfg.model,
            "max_steps": cfg.max_steps,
            "timeout_seconds": cfg.timeout_seconds,
            "max_result_chars": cfg.max_result_chars,
        })
    return jsonify({"types": types})


@bp.route("/api/subagents/history")
def subagent_history():
    tasks = list_background_tasks()
    history = []
    for r in tasks:
        history.append({
            "task_id": r.task_id,
            "trace_id": r.trace_id,
            "subagent_type": r.subagent_type,
            "status": r.status.value if isinstance(r.status, SubagentStatus) else str(r.status),
            "result_preview": (r.result or "")[:200] if r.result else None,
            "error": r.error,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_ms": r.duration_ms,
            "steps_used": r.steps_used,
            "tokens_used": r.tokens_used,
        })
    history.sort(key=lambda h: h.get("started_at") or "", reverse=True)
    return jsonify({"history": history, "total": len(history)})
