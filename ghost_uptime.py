"""Uptime monitoring tools for Ghost."""

from __future__ import annotations

import time
from typing import Any, Dict, List


def build_uptime_tools(daemon: Any) -> List[Dict[str, Any]]:
    """Build uptime-related tool definitions.

    Args:
        daemon: GhostDaemon instance exposing _start_time, _msg_count, _tool_count.
    """

    def _execute(_: Dict[str, Any] | None = None) -> Dict[str, Any]:
        start_time = getattr(daemon, "_start_time", None)
        if not isinstance(start_time, (int, float)):
            start_time = time.time()

        msg_count = getattr(daemon, "_msg_count", 0)
        tool_count = getattr(daemon, "_tool_count", 0)

        if not isinstance(msg_count, int):
            msg_count = 0
        if not isinstance(tool_count, int):
            tool_count = 0

        uptime_seconds = max(0.0, time.time() - float(start_time))
        return {
            "uptime_seconds": round(uptime_seconds, 3),
            "messages_processed": max(0, msg_count),
            "tool_calls_made": max(0, tool_count),
        }

    return [
        {
            "name": "uptime_stats",
            "description": "Return current Ghost session uptime in seconds plus message and tool-call counters.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "execute": _execute,
        }
    ]