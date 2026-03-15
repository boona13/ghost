from __future__ import annotations

import time
from datetime import UTC, datetime


def _to_int(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def register(api):
    def execute(**kwargs):
        cfg = api._config if isinstance(api._config, dict) else {}

        now_ts = time.time()
        now = datetime.now(UTC)

        start_ts = cfg.get("daemon_start_time")
        uptime_seconds = None
        if isinstance(start_ts, (int, float)):
            uptime_seconds = max(0, int(now_ts - float(start_ts)))
        else:
            daemon_started_at = cfg.get("daemon_started_at")
            if isinstance(daemon_started_at, str):
                try:
                    started = datetime.fromisoformat(daemon_started_at.replace("Z", "+00:00"))
                    uptime_seconds = max(0, int((now - started.astimezone(UTC)).total_seconds()))
                except ValueError:
                    uptime_seconds = None

        tool_calls = _to_int(cfg.get("session_tool_calls"))
        if tool_calls is None:
            tool_calls = _to_int(cfg.get("tool_count"))

        cron_completed = _to_int(cfg.get("cron_completed_jobs"))
        if cron_completed is None:
            cron_completed = _to_int(cfg.get("cron_completed"))

        data = {
            "uptime_seconds": uptime_seconds,
            "session_tool_calls": tool_calls,
            "completed_cron_jobs": cron_completed,
            "unavailable": {
                "uptime_seconds": uptime_seconds is None,
                "session_tool_calls": tool_calls is None,
                "completed_cron_jobs": cron_completed is None,
            },
        }
        summary = (
            f"Uptime: {uptime_seconds if uptime_seconds is not None else 'unavailable'}s | "
            f"Session tool calls: {tool_calls if tool_calls is not None else 'unavailable'} | "
            f"Completed cron jobs: {cron_completed if cron_completed is not None else 'unavailable'}"
        )
        return {"ok": True, "summary": summary, "data": data}

    api.register_tool(
        {
            "name": "uptime_report",
            "description": "Return daemon uptime, current session tool calls, and completed cron jobs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "execute": execute,
        }
    )
