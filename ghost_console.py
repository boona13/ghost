"""
Ghost Console — Real-time event bus for observability.

Streams every Ghost event (tool calls, cron fires, chat, growth,
errors, lifecycle) to the dashboard terminal console via SSE.

Replaces the old ghost_process_manager.py which was never triggered.
"""

import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime

from ghost_security_audit import sanitize_diagnostic_text

RING_BUFFER_SIZE = 500
MAX_DETAIL_LEN = 500
MAX_RESULT_LEN = 300
SENSITIVE_CATEGORIES = {"security", "security_patrol", "security_audit", "audit", "error"}


class ConsoleEventBus:
    """Thread-safe event bus with ring buffer and SSE subscriber notification."""

    def __init__(self, maxlen: int = RING_BUFFER_SIZE):
        self._buffer: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._subscribers: dict[str, threading.Event] = {}
        self._sub_lock = threading.Lock()
        self._seq = 0

    def emit(self, level: str, category: str, title: str,
             detail: str = "", result: str = "", duration_ms: int = None,
             safety_mask: bool = False):
        safe_detail = detail or ""
        safe_result = result or ""
        normalized_category = (category or "").lower()
        if safety_mask or normalized_category in SENSITIVE_CATEGORIES:
            safe_detail = sanitize_diagnostic_text(safe_detail, max_chars=MAX_DETAIL_LEN)
            safe_result = sanitize_diagnostic_text(safe_result, max_chars=MAX_RESULT_LEN)

        evt = {
            "id": f"evt_{uuid.uuid4().hex[:8]}",
            "seq": self._next_seq(),
            "ts": datetime.now().isoformat(),
            "level": level,
            "category": category,
            "title": title,
            "detail": safe_detail[:MAX_DETAIL_LEN],
        }
        if safe_result:
            evt["result"] = safe_result[:MAX_RESULT_LEN]
        if duration_ms is not None:
            evt["duration_ms"] = duration_ms

        with self._lock:
            self._buffer.append(evt)

        self._notify_subscribers()

    def history(self, limit: int = 200, after_seq: int = None) -> list[dict]:
        with self._lock:
            items = list(self._buffer)
        if after_seq is not None:
            items = [e for e in items if e.get("seq", 0) > after_seq]
        return items[-limit:]

    def clear(self):
        with self._lock:
            self._buffer.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def subscribe(self) -> tuple[str, threading.Event]:
        sub_id = f"sub_{uuid.uuid4().hex[:6]}"
        event = threading.Event()
        with self._sub_lock:
            self._subscribers[sub_id] = event
        return sub_id, event

    def unsubscribe(self, sub_id: str):
        with self._sub_lock:
            evt = self._subscribers.pop(sub_id, None)
            if evt:
                evt.set()

    def _notify_subscribers(self):
        with self._sub_lock:
            for evt in self._subscribers.values():
                evt.set()

    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq


console_bus = ConsoleEventBus()


def build_console_tools(cfg=None):
    """LLM-callable tool to write to the console."""

    def console_log(message, level="info", category="system"):
        console_bus.emit(
            level=level,
            category=category,
            title="agent_log",
            detail=message,
        )
        return f"Logged to console: {message[:100]}"

    return [
        {
            "name": "console_log",
            "description": (
                "Write a message to the real-time Ghost console. "
                "Use this to log progress, status updates, or debugging info "
                "that will appear in the dashboard terminal view."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to log to the console",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["info", "warn", "error", "success", "debug"],
                        "description": "Log level (default: info)",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["tool_call", "cron", "chat", "channel",
                                 "growth", "system", "error"],
                        "description": "Event category (default: system)",
                    },
                },
                "required": ["message"],
            },
            "execute": console_log,
        },
    ]
