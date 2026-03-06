import json
import re
from datetime import datetime, timezone
from typing import Any


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, out))


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _normalize_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _extract_bullets(text: str, limit: int) -> list[str]:
    lines = _normalize_lines(text)
    bullets: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^[-*•\d\.)\s]+", "", line).strip()
        if not cleaned:
            continue
        if cleaned in bullets:
            continue
        bullets.append(cleaned)
        if len(bullets) >= limit:
            break

    if bullets:
        return bullets

    if not text.strip():
        return []

    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    out = []
    for chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


def _build_digest(record: dict[str, Any], max_points: int) -> dict[str, Any]:
    thread_text = _coerce_text(record.get("thread_text"))
    title = _coerce_text(record.get("title")) or "Thread Digest"
    channel = _coerce_text(record.get("channel")) or "unknown"
    thread_id = _coerce_text(record.get("thread_id")) or ""

    bullets = _extract_bullets(thread_text, max_points)
    if not bullets and thread_text:
        bullets = [thread_text[:220].strip()]

    return {
        "title": title,
        "channel": channel,
        "thread_id": thread_id,
        "bullets": bullets,
        "summary": " | ".join(bullets[:3])[:500],
    }


def _history_read(api) -> list[dict[str, Any]]:
    raw = api.read_data("digest_history.json")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _history_write(api, rows: list[dict[str, Any]]):
    api.write_data("digest_history.json", json.dumps(rows, ensure_ascii=False, indent=2))


def register(api):
    max_input_chars = _safe_int(api.get_setting("max_input_chars", 12000), 12000, 500, 200000)
    default_max_points = _safe_int(api.get_setting("default_max_points", 5), 5, 1, 20)
    history_limit = _safe_int(api.get_setting("history_limit", 200), 200, 10, 1000)

    def channel_thread_context(channel: str = "", thread_id: str = "", text: str = "", **kwargs):
        channel_s = _coerce_text(channel).strip() or _coerce_text(kwargs.get("source")).strip()
        thread_id_s = _coerce_text(thread_id).strip() or _coerce_text(kwargs.get("conversation_id")).strip()
        thread_text = _coerce_text(text)
        if not thread_text:
            thread_text = _coerce_text(kwargs.get("thread_text"))

        if not thread_text.strip():
            return json.dumps({"status": "error", "error": "thread text is required"})

        if len(thread_text) > max_input_chars:
            thread_text = thread_text[:max_input_chars]

        payload = {
            "status": "ok",
            "channel": channel_s or "unknown",
            "thread_id": thread_id_s,
            "thread_text": thread_text,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def semantic_memory_save(content: str = "", tags: str = "", memory_type: str = "thread_digest", **kwargs):
        daemon = api.get_daemon_ref()
        text = _coerce_text(content).strip()
        if not text:
            text = _coerce_text(kwargs.get("summary")).strip()
        if not text:
            return json.dumps({"status": "error", "error": "content is required"})

        safe_tags = _coerce_text(tags).strip()
        safe_type = _coerce_text(memory_type).strip() or "thread_digest"

        try:
            if daemon and getattr(daemon, "memory", None):
                daemon.memory.save(text, tags=safe_tags, type=safe_type)
            else:
                return json.dumps({"status": "error", "error": "memory service unavailable"})
        except Exception as e:
            return json.dumps({"status": "error", "error": f"memory save failed: {e}"})

        return json.dumps({"status": "ok", "saved": True, "type": safe_type}, ensure_ascii=False)

    def digest_recent_thread_to_memory(
        thread_text: str = "",
        channel: str = "",
        thread_id: str = "",
        title: str = "",
        max_points: int = 0,
        save_memory: bool = True,
        postback: bool = False,
        postback_target: str = "",
        tags: str = "",
        **kwargs,
    ):
        text = _coerce_text(thread_text)
        if not text:
            text = _coerce_text(kwargs.get("text"))
        if not text.strip():
            return json.dumps({"status": "error", "error": "thread_text is required"})

        max_pts = _safe_int(max_points, default_max_points, 1, 20)
        if len(text) > max_input_chars:
            text = text[:max_input_chars]

        digest = _build_digest(
            {
                "thread_text": text,
                "title": _coerce_text(title),
                "channel": _coerce_text(channel),
                "thread_id": _coerce_text(thread_id),
            },
            max_pts,
        )

        saved = False
        if bool(save_memory):
            mem_text = (
                f"[{digest['channel']}] {digest['title']}"
                + (f" (thread {digest['thread_id']})" if digest.get("thread_id") else "")
                + "\n- "
                + "\n- ".join(digest["bullets"])
            )
            mem_tags = _coerce_text(tags).strip() or f"thread,digest,{digest['channel']}"
            save_result = json.loads(semantic_memory_save(mem_text, mem_tags, memory_type="thread_digest"))
            saved = save_result.get("status") == "ok"

        history = _history_read(api)
        row = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "channel": digest["channel"],
            "thread_id": digest.get("thread_id", ""),
            "title": digest["title"],
            "bullets": digest["bullets"],
            "summary": digest["summary"],
            "saved": saved,
            "postback": bool(postback),
            "postback_target": _coerce_text(postback_target).strip(),
        }
        history.insert(0, row)
        if len(history) > history_limit:
            history = history[:history_limit]
        _history_write(api, history)

        postback_result = None
        if bool(postback):
            postback_result = {
                "status": "skipped",
                "reason": "postback transport not configured in this extension",
                "target": _coerce_text(postback_target).strip(),
            }

        return json.dumps(
            {
                "status": "ok",
                "digest": digest,
                "saved": saved,
                "postback": postback_result,
            },
            ensure_ascii=False,
        )

    def digest_history_list(limit: int = 25, **_kwargs):
        safe_limit = _safe_int(limit, 25, 1, 200)
        rows = _history_read(api)
        return json.dumps({"status": "ok", "items": rows[:safe_limit]}, ensure_ascii=False)

    api.register_tool({
        "name": "channel_thread_context",
        "description": "Normalize raw channel thread payload into digestable context.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "thread_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
        "execute": channel_thread_context,
    })

    api.register_tool({
        "name": "semantic_memory_save",
        "description": "Save concise digest content into semantic memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "tags": {"type": "string"},
                "memory_type": {"type": "string"},
            },
            "required": ["content"],
        },
        "execute": semantic_memory_save,
    })

    api.register_tool({
        "name": "digest_recent_thread_to_memory",
        "description": "Digest a thread into bullet memory points and optionally save.",
        "parameters": {
            "type": "object",
            "properties": {
                "thread_text": {"type": "string"},
                "channel": {"type": "string"},
                "thread_id": {"type": "string"},
                "title": {"type": "string"},
                "max_points": {"type": "integer"},
                "save_memory": {"type": "boolean"},
                "postback": {"type": "boolean"},
                "postback_target": {"type": "string"},
                "tags": {"type": "string"},
            },
            "required": ["thread_text"],
        },
        "execute": digest_recent_thread_to_memory,
    })

    api.register_tool({
        "name": "digest_history_list",
        "description": "List recent thread digest history entries.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
        },
        "execute": digest_history_list,
    })

    api.register_page({
        "id": "thread_memory_digest",
        "label": "Thread Digest",
        "icon": "layers",
        "section": "extensions",
        "js_path": "thread_memory_digest.js",
    })

    def on_boot():
        api.log("thread_memory_digest extension loaded")

    api.register_hook("on_boot", on_boot)
