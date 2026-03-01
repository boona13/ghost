"""
Ghost Session Memory — Auto-save conversation summaries to persistent memory.

Registers on_shutdown and on_session_end hooks to capture session context.
Generates LLM-summarized markdown files with descriptive slugs.
Saves to ~/.ghost/memory/sessions/YYYY-MM-DD-{slug}.md for searchable recall.
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ghost.session_memory")

GHOST_HOME = Path.home() / ".ghost"
SESSION_MEMORY_DIR = GHOST_HOME / "memory" / "sessions"
SESSION_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

MAX_MESSAGES_TO_SUMMARIZE = 15
MAX_ENTRIES_TO_CAPTURE = 30


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len] or "session"


def _extract_session_content(feed_entries: list) -> str:
    """Extract recent session entries into a readable conversation log."""
    lines = []
    for entry in feed_entries[:MAX_ENTRIES_TO_CAPTURE]:
        etype = entry.get("type", "unknown")
        source = entry.get("source", "")[:200]
        result = entry.get("result", "")[:300]
        tools = entry.get("tools_used", [])
        skill = entry.get("skill", "")

        if etype == "ask":
            lines.append(f"User: {source}")
            if tools:
                lines.append(f"  [Used tools: {', '.join(tools)}]")
            lines.append(f"Ghost: {result}")
        elif etype == "cron":
            lines.append(f"[Cron] {source[:100]}")
            lines.append(f"  Result: {result[:200]}")
        elif etype in ("error", "code", "url", "long_text"):
            lines.append(f"[{etype}] {source[:100]}")
            lines.append(f"  Analysis: {result[:200]}")

        if skill:
            lines.append(f"  [Skill: {skill}]")
        lines.append("")

    return "\n".join(lines)


def _generate_summary_and_slug(content: str, engine=None) -> tuple[str, str]:
    """Generate a summary and slug using the LLM, or fall back to timestamp."""
    if engine:
        try:
            prompt = (
                "Summarize this conversation session in 2-3 sentences. "
                "Then provide a 3-5 word slug (lowercase, hyphens) that captures the main topic.\n"
                "Format your response EXACTLY as:\n"
                "SUMMARY: <your summary>\n"
                "SLUG: <your-slug>\n\n"
                f"Conversation:\n{content[:3000]}"
            )
            result = engine.single_shot(
                system_prompt="You generate concise session summaries. Be specific about what was discussed.",
                user_message=prompt,
                temperature=0.2,
                max_tokens=200,
            )
            if result:
                summary = ""
                slug = ""
                for line in result.split("\n"):
                    line = line.strip()
                    if line.upper().startswith("SUMMARY:"):
                        summary = line[8:].strip()
                    elif line.upper().startswith("SLUG:"):
                        slug = _slugify(line[5:].strip())
                if summary and slug:
                    return summary, slug
                if summary:
                    return summary, _slugify(summary[:50])
        except Exception as e:
            log.debug("LLM summary generation failed: %s", e)

    ts = datetime.now().strftime("%H%M")
    return "Session auto-saved on shutdown.", f"session-{ts}"


def save_session(feed_entries: list, engine=None, memory_db=None,
                 hybrid_memory=None) -> str | None:
    """Save the current session to a markdown file and optionally to memory DB.

    Returns the file path if saved, None if nothing to save.
    """
    if not feed_entries:
        return None

    recent = [e for e in feed_entries if e.get("type") in
              ("ask", "cron", "error", "code", "url", "long_text", "image")]
    if not recent:
        return None

    content = _extract_session_content(recent)
    if not content.strip():
        return None

    summary, slug = _generate_summary_and_slug(content, engine)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{slug}.md"
    filepath = SESSION_MEMORY_DIR / filename

    counter = 1
    while filepath.exists():
        filepath = SESSION_MEMORY_DIR / f"{date_str}-{slug}-{counter}.md"
        counter += 1

    session_md = (
        f"# Session: {date_str} — {slug}\n\n"
        f"**Summary:** {summary}\n\n"
        f"**Timestamp:** {datetime.now().isoformat()}\n"
        f"**Entries:** {len(recent)}\n"
        f"**Tools used:** {', '.join(set(t for e in recent for t in e.get('tools_used', []))) or 'none'}\n\n"
        f"---\n\n"
        f"## Conversation Log\n\n"
        f"{content}\n"
    )

    filepath.write_text(session_md)
    log.info("Session saved to %s", filepath)

    if memory_db:
        try:
            memory_db.save(
                content=f"Session summary ({date_str}): {summary}",
                type="session",
                source_preview=f"session:{slug}",
                tags="session,auto-save",
            )
        except Exception as e:
            log.debug("Failed to save session to memory DB: %s", e)

    if hybrid_memory:
        try:
            from ghost_hybrid_memory import get_manager
            mgr = get_manager()
            mgr.index_file(str(filepath), source="session")
        except Exception as e:
            log.debug("Failed to index session in hybrid memory: %s", e)

    return str(filepath)


def register_session_hooks(hook_runner, daemon):
    """Register session memory hooks with the hook runner.

    Called during daemon initialization to wire up auto-save.
    """

    def _on_shutdown():
        try:
            from ghost import read_feed
            feed = read_feed()
            if feed:
                save_session(
                    feed_entries=feed,
                    engine=daemon.engine,
                    memory_db=daemon.memory_db,
                )
        except Exception as e:
            log.debug("Session memory save on shutdown failed: %s", e)

    def _on_session_end(entries):
        try:
            if entries:
                save_session(
                    feed_entries=entries,
                    engine=daemon.engine,
                    memory_db=daemon.memory_db,
                )
        except Exception as e:
            log.debug("Session memory save on session_end failed: %s", e)

    hook_runner.register("on_shutdown", _on_shutdown, priority=10, plugin_id="session_memory")
    hook_runner.register("on_session_end", _on_session_end, priority=10, plugin_id="session_memory")
    log.info("Session memory hooks registered")
