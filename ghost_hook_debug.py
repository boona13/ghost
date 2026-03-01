"""Hook debug event store + tools.

Provides redacted hook event introspection with a bounded JSONL store and
safe replay support for debugging plugin hook chains.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


GHOST_HOME = Path.home() / ".ghost"
HOOK_DEBUG_FILE = GHOST_HOME / "hook_debug_events.jsonl"
SENSITIVE_KEYS = {
    "password", "token", "secret", "api_key", "authorization", "cookie", "set-cookie",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: Any, limit: int = 180) -> str:
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _redact(obj: Any, depth: int = 0) -> Any:
    if depth > 3:
        return "[truncated]"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in SENSITIVE_KEYS:
                out[k] = "[redacted]"
            else:
                out[k] = _redact(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_redact(v, depth + 1) for v in obj[:20]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return _safe_str(obj)


@dataclass
class HookDebugStore:
    path: Path = HOOK_DEBUG_FILE
    max_events: int = 2000

    def __post_init__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _read_all(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        try:
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
        except Exception:
            return []
        return events

    def _write_all(self, events: List[Dict[str, Any]]) -> None:
        data = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
        if data:
            data += "\n"
        self.path.write_text(data)

    def _append(self, event: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._rotate_if_needed()

    def _rotate_if_needed(self) -> None:
        events = self._read_all()
        if len(events) <= self.max_events:
            return
        self._write_all(events[-self.max_events:])

    def record_event(
        self,
        *,
        phase: str,
        hook_name: str,
        plugin_id: str,
        status: str,
        correlation_id: Optional[str],
        duration_ms: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        event_id = f"he_{uuid.uuid4().hex[:16]}"
        event = {
            "id": event_id,
            "ts": _utc_now(),
            "phase": phase,
            "hook_name": hook_name,
            "plugin_id": plugin_id,
            "status": status,
            "correlation_id": correlation_id,
            "duration_ms": duration_ms,
            "payload": _redact(payload or {}),
            "error": _safe_str(error, 300) if error else None,
        }
        self._append(event)
        return event_id

    def list_events(self, limit: int = 100, hook_name: str = "", status: str = "") -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        events = self._read_all()
        if hook_name:
            events = [e for e in events if e.get("hook_name") == hook_name]
        if status:
            events = [e for e in events if e.get("status") == status]
        return list(reversed(events[-limit:]))

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        if not event_id.startswith("he_"):
            return None
        for e in self._read_all():
            if e.get("id") == event_id:
                return e
        return None

    def stats(self) -> Dict[str, Any]:
        events = self._read_all()
        total = len(events)
        failures = sum(1 for e in events if e.get("status") == "error")
        avg_ms = 0.0
        durations = [float(e["duration_ms"]) for e in events if isinstance(e.get("duration_ms"), (int, float))]
        if durations:
            avg_ms = round(sum(durations) / len(durations), 2)
        return {
            "total": total,
            "failures": failures,
            "success": total - failures,
            "avg_duration_ms": avg_ms,
            "path": str(self.path),
        }


_STORE: Optional[HookDebugStore] = None


def get_hook_debug_store() -> HookDebugStore:
    global _STORE
    if _STORE is None:
        _STORE = HookDebugStore()
    return _STORE


def build_hook_debug_tools(hook_runner=None):
    store = get_hook_debug_store()

    def _enabled() -> bool:
        if hook_runner is None:
            return True
        cfg = getattr(hook_runner, "_config", {}) or {}
        return bool(cfg.get("enable_hook_debug", False))

    def list_execute(limit: int = 50, hook_name: str = "", status: str = ""):
        if not _enabled():
            return {"ok": False, "error": "Hook debug disabled (enable_hook_debug=false)"}
        limit = max(1, min(int(limit), 500))
        hook_name = str(hook_name).strip()
        status = str(status).strip()
        return {"ok": True, "events": store.list_events(limit=limit, hook_name=hook_name, status=status)}

    def stats_execute():
        if not _enabled():
            return {"ok": False, "error": "Hook debug disabled (enable_hook_debug=false)"}
        return {"ok": True, "stats": store.stats()}

    def replay_execute(event_id: str = "", confirm: bool = False):
        if not _enabled():
            return {"ok": False, "error": "Hook debug disabled (enable_hook_debug=false)"}
        event_id = str(event_id).strip()
        if not event_id:
            return {"ok": False, "error": "event_id is required"}
        event = store.get_event(event_id)
        if not event:
            return {"ok": False, "error": f"event not found: {event_id}"}
        if confirm is not True:
            return {"ok": False, "error": "Set confirm=true to run replay", "event": event}
        if hook_runner is None:
            return {"ok": False, "error": "hook runner unavailable"}
        hook_name = event.get("hook_name")
        payload = event.get("payload") or {}
        start = time.perf_counter()
        try:
            replay_result = hook_runner.run(hook_name, payload)
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            store.record_event(
                phase="replay",
                hook_name=hook_name,
                plugin_id="replay",
                status="ok",
                correlation_id=event.get("correlation_id"),
                duration_ms=elapsed,
                payload={"source_event_id": event_id},
            )
            return {"ok": True, "replayed": event_id, "duration_ms": elapsed, "result": _redact(replay_result)}
        except Exception as e:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            store.record_event(
                phase="replay",
                hook_name=hook_name,
                plugin_id="replay",
                status="error",
                correlation_id=event.get("correlation_id"),
                duration_ms=elapsed,
                payload={"source_event_id": event_id},
                error=str(e),
            )
            return {"ok": False, "error": str(e)}

    return [
        {
            "name": "hook_debug_list",
            "description": "List recent hook debug events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    "hook_name": {"type": "string"},
                    "status": {"type": "string", "enum": ["", "ok", "error"]},
                },
                "required": [],
            },
            "execute": list_execute,
        },
        {
            "name": "hook_debug_stats",
            "description": "Get hook debug aggregate statistics.",
            "parameters": {"type": "object", "properties": {}, "required": []},
            "execute": stats_execute,
        },
        {
            "name": "hook_debug_replay",
            "description": "Replay a recorded hook event in debug mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["event_id"],
            },
            "execute": replay_execute,
        },
    ]
