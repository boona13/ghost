"""
GHOST X/Twitter Interaction Tracker

SQLite-backed tracker that logs every interaction Ghost performs on X
(likes, retweets, follows, comments, posts) to prevent duplicate actions.

Storage: ~/.ghost/x_tracker.db
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

GHOST_HOME = Path.home() / ".ghost"
DB_PATH = GHOST_HOME / "x_tracker.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,          -- like, retweet, follow, comment, post, quote_retweet
    target_type TEXT NOT NULL,          -- tweet, user
    target_id   TEXT NOT NULL,          -- tweet URL/ID or username
    content     TEXT DEFAULT '',        -- comment text, post text, etc.
    timestamp   REAL NOT NULL,          -- epoch seconds
    session_id  TEXT DEFAULT '',        -- cron job id or 'manual'
    metadata    TEXT DEFAULT '{}'       -- extra context as JSON
);
CREATE INDEX IF NOT EXISTS idx_action_target ON interactions(action, target_id);
CREATE INDEX IF NOT EXISTS idx_target_id ON interactions(target_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON interactions(timestamp);
"""


class XTracker:
    """Thread-safe X interaction tracker backed by SQLite."""

    def __init__(self, db_path=None):
        self._db_path = Path(db_path) if db_path else DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_schema(self):
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    @staticmethod
    def _normalize_target(target_id: str) -> str:
        """Normalize tweet URLs and usernames for consistent matching."""
        t = target_id.strip()
        if t.startswith("@"):
            t = t[1:]
        if "x.com/" in t or "twitter.com/" in t:
            t = t.split("?")[0].rstrip("/")
        return t.lower()

    def log(self, action: str, target_type: str, target_id: str,
            content: str = "", session_id: str = "", metadata: dict = None) -> dict:
        target_norm = self._normalize_target(target_id)
        now = time.time()
        meta_json = json.dumps(metadata or {})

        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO interactions (action, target_type, target_id, content, timestamp, session_id, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (action.lower(), target_type.lower(), target_norm, content, now, session_id, meta_json),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "action": action.lower(),
            "target_id": target_norm,
            "timestamp": datetime.fromtimestamp(now).isoformat(),
        }

    def check(self, action: str, target_id: str, hours: int = 0) -> dict:
        """Check if an action was already performed on a target.
        
        hours=0 means check all time. hours>0 means only check within that window.
        """
        target_norm = self._normalize_target(target_id)
        conn = self._conn()

        if hours > 0:
            cutoff = time.time() - (hours * 3600)
            row = conn.execute(
                "SELECT id, action, target_id, content, timestamp FROM interactions "
                "WHERE action = ? AND target_id = ? AND timestamp > ? ORDER BY timestamp DESC LIMIT 1",
                (action.lower(), target_norm, cutoff),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, action, target_id, content, timestamp FROM interactions "
                "WHERE action = ? AND target_id = ? ORDER BY timestamp DESC LIMIT 1",
                (action.lower(), target_norm),
            ).fetchone()

        if row:
            return {
                "already_done": True,
                "action": row["action"],
                "target_id": row["target_id"],
                "when": datetime.fromtimestamp(row["timestamp"]).isoformat(),
                "content": row["content"],
            }
        return {"already_done": False}

    def check_any(self, target_id: str) -> list:
        """Check all actions performed on a target."""
        target_norm = self._normalize_target(target_id)
        conn = self._conn()
        rows = conn.execute(
            "SELECT action, target_id, content, timestamp FROM interactions "
            "WHERE target_id = ? ORDER BY timestamp DESC",
            (target_norm,),
        ).fetchall()
        return [
            {
                "action": r["action"],
                "target_id": r["target_id"],
                "when": datetime.fromtimestamp(r["timestamp"]).isoformat(),
                "content": r["content"],
            }
            for r in rows
        ]

    def history(self, action: str = None, limit: int = 50,
                hours: int = 24) -> list:
        conn = self._conn()
        cutoff = time.time() - (hours * 3600)

        if action:
            rows = conn.execute(
                "SELECT action, target_type, target_id, content, timestamp, session_id "
                "FROM interactions WHERE action = ? AND timestamp > ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (action.lower(), cutoff, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT action, target_type, target_id, content, timestamp, session_id "
                "FROM interactions WHERE timestamp > ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()

        return [
            {
                "action": r["action"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "content": r["content"][:100],
                "when": datetime.fromtimestamp(r["timestamp"]).isoformat(),
                "session": r["session_id"],
            }
            for r in rows
        ]

    def stats(self, hours: int = 24) -> dict:
        conn = self._conn()
        cutoff = time.time() - (hours * 3600)
        rows = conn.execute(
            "SELECT action, COUNT(*) as cnt FROM interactions "
            "WHERE timestamp > ? GROUP BY action ORDER BY cnt DESC",
            (cutoff,),
        ).fetchall()

        total = 0
        by_action = {}
        for r in rows:
            by_action[r["action"]] = r["cnt"]
            total += r["cnt"]

        all_time = conn.execute(
            "SELECT COUNT(*) as cnt FROM interactions"
        ).fetchone()["cnt"]

        unique_tweets = conn.execute(
            "SELECT COUNT(DISTINCT target_id) as cnt FROM interactions "
            "WHERE target_type = 'tweet' AND timestamp > ?",
            (cutoff,),
        ).fetchone()["cnt"]

        unique_users = conn.execute(
            "SELECT COUNT(DISTINCT target_id) as cnt FROM interactions "
            "WHERE target_type = 'user' AND timestamp > ?",
            (cutoff,),
        ).fetchone()["cnt"]

        return {
            "period": f"last {hours}h",
            "total_actions": total,
            "all_time_total": all_time,
            "by_action": by_action,
            "unique_tweets_interacted": unique_tweets,
            "unique_users_interacted": unique_users,
        }


_tracker_instance = None
_tracker_lock = threading.Lock()


def get_tracker() -> XTracker:
    global _tracker_instance
    if _tracker_instance is None:
        with _tracker_lock:
            if _tracker_instance is None:
                _tracker_instance = XTracker()
    return _tracker_instance


# ═════════════════════════════════════════════════════════════════════
#  TOOL BUILDERS
# ═════════════════════════════════════════════════════════════════════

def build_x_tracker_tools() -> list[dict]:
    """Build tool defs for Ghost's tool registry."""

    def x_log_action_exec(action: str, target_type: str, target_id: str,
                          content: str = "", session_id: str = "",
                          metadata: dict = None):
        tracker = get_tracker()

        dupe = tracker.check(action, target_id)
        if dupe["already_done"]:
            return (
                f"WARNING: You already performed '{action}' on {target_id} "
                f"at {dupe['when']}. Logging again anyway, but this may be a duplicate. "
                f"Use x_check_action first next time."
            )

        result = tracker.log(
            action=action, target_type=target_type,
            target_id=target_id, content=content,
            session_id=session_id, metadata=metadata,
        )
        return f"Logged: {action} on {target_id} (id: {result['id']})"

    def x_check_action_exec(action: str, target_id: str, hours: int = 0):
        tracker = get_tracker()

        if action == "any":
            results = tracker.check_any(target_id)
            if not results:
                return f"No interactions found for {target_id}. Safe to proceed."
            lines = [f"Found {len(results)} interaction(s) for {target_id}:"]
            for r in results:
                lines.append(f"  - {r['action']} at {r['when']}")
            return "\n".join(lines)

        result = tracker.check(action, target_id, hours=hours)
        if result["already_done"]:
            return (
                f"ALREADY DONE: '{action}' was performed on {target_id} "
                f"at {result['when']}. SKIP this action to avoid duplicates."
            )
        scope = f" (within last {hours}h)" if hours > 0 else ""
        return f"NOT done: '{action}' has not been performed on {target_id}{scope}. Safe to proceed."

    def x_action_history_exec(action: str = None, limit: int = 50,
                              hours: int = 24):
        tracker = get_tracker()
        results = tracker.history(action=action, limit=limit, hours=hours)
        if not results:
            scope = f" for '{action}'" if action else ""
            return f"No interactions found{scope} in the last {hours}h."

        lines = [f"X interaction history (last {hours}h, showing {len(results)}):"]
        for r in results:
            content_snip = f' — "{r["content"]}"' if r["content"] else ""
            lines.append(f"  [{r['when'][:16]}] {r['action']} → {r['target_id']}{content_snip}")
        return "\n".join(lines)

    def x_action_stats_exec(hours: int = 24):
        tracker = get_tracker()
        stats = tracker.stats(hours=hours)

        lines = [
            f"X Engagement Stats ({stats['period']}):",
            f"  Total actions: {stats['total_actions']}  (all-time: {stats['all_time_total']})",
        ]
        if stats["by_action"]:
            lines.append("  Breakdown:")
            for action, count in stats["by_action"].items():
                lines.append(f"    {action}: {count}")
        lines.append(f"  Unique tweets: {stats['unique_tweets_interacted']}")
        lines.append(f"  Unique users: {stats['unique_users_interacted']}")
        return "\n".join(lines)

    return [
        {
            "name": "x_log_action",
            "description": (
                "Log an X/Twitter interaction you just performed. MUST be called after every "
                "like, retweet, follow, comment, or post to prevent duplicates. "
                "Warns if the action was already logged for the same target."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["like", "retweet", "follow", "comment", "post", "quote_retweet"],
                        "description": "The action performed",
                    },
                    "target_type": {
                        "type": "string",
                        "enum": ["tweet", "user"],
                        "description": "Whether the target is a tweet or a user profile",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "The tweet URL (e.g. https://x.com/user/status/123) or username (e.g. @username)",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text of your comment/post (if applicable)",
                        "default": "",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Cron job ID or 'manual' to identify the session",
                        "default": "",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional extra context (e.g. tweet author, topic)",
                    },
                },
                "required": ["action", "target_type", "target_id"],
            },
            "execute": x_log_action_exec,
        },
        {
            "name": "x_check_action",
            "description": (
                "Check if you already performed an action on a specific tweet or user. "
                "MUST be called BEFORE every like, retweet, follow, or comment to avoid duplicates. "
                "Use action='any' to check all interaction types at once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["like", "retweet", "follow", "comment", "post", "quote_retweet", "any"],
                        "description": "The action to check, or 'any' to check all actions",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "The tweet URL or username to check",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Only check within the last N hours (0 = all time)",
                        "default": 0,
                    },
                },
                "required": ["action", "target_id"],
            },
            "execute": x_check_action_exec,
        },
        {
            "name": "x_action_history",
            "description": (
                "View recent X interaction history. Use to review what you've already "
                "done in a session before deciding next actions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["like", "retweet", "follow", "comment", "post", "quote_retweet"],
                        "description": "Filter by action type (omit for all)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return",
                        "default": 50,
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Look back this many hours",
                        "default": 24,
                    },
                },
            },
            "execute": x_action_history_exec,
        },
        {
            "name": "x_action_stats",
            "description": (
                "Get engagement statistics for X interactions. Shows counts by action type, "
                "unique tweets/users interacted with. Use to track growth progress."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Stats for the last N hours",
                        "default": 24,
                    },
                },
            },
            "execute": x_action_stats_exec,
        },
    ]
