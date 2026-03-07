"""
GHOST Persistent Memory

SQLite + FTS5 memory database. Every analysis is stored and searchable.
The LLM can search past context and save important notes.
Survives across daemon restarts.
"""

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from hashlib import md5
from typing import Optional


GHOST_HOME = Path.home() / ".ghost"
MEMORY_DB_PATH = GHOST_HOME / "memory.db"


class MemoryDB:
    """Persistent memory store backed by SQLite with FTS5 full-text search."""

    def __init__(self, db_path=None):
        self.db_path = str(db_path or MEMORY_DB_PATH)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'analysis',
                source_hash TEXT,
                content TEXT NOT NULL,
                source_preview TEXT,
                tags TEXT DEFAULT '',
                skill TEXT DEFAULT '',
                tools_used TEXT DEFAULT '',
                tokens_used INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp);
            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_hash ON memories(source_hash);
        """)

        try:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(content, tags, source_preview, content='memories', content_rowid='id');
            """)
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tags, source_preview)
                    VALUES (new.id, new.content, new.tags, new.source_preview);
                END;
            """)
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, source_preview)
                    VALUES ('delete', old.id, old.content, old.tags, old.source_preview);
                END;
            """)
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags, source_preview)
                    VALUES ('delete', old.id, old.content, old.tags, old.source_preview);
                    INSERT INTO memories_fts(rowid, content, tags, source_preview)
                    VALUES (new.id, new.content, new.tags, new.source_preview);
                END;
            """)
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("ALTER TABLE memories ADD COLUMN citations TEXT DEFAULT ''")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

        self.conn.commit()

    def save(self, content, type="analysis", source_preview="", tags="",
             skill="", tools_used="", tokens_used=0, source_hash=None,
             citations=""):
        """Save a memory entry.

        Args:
            citations: Optional JSON string of citation locations.
                Format: [{"file": "ghost_loop.py", "line": 42, "snippet": "class Foo:"}]
                Citations enable JIT verification on retrieval.
        """
        if not source_hash:
            source_hash = md5(content.encode(errors="replace")).hexdigest()

        c = self.conn.cursor()
        c.execute("""
            INSERT INTO memories (timestamp, type, source_hash, content, source_preview, tags, skill, tools_used, tokens_used, citations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            type,
            source_hash,
            content[:10000],
            source_preview[:500],
            tags,
            skill,
            tools_used,
            tokens_used,
            citations[:5000] if citations else "",
        ))
        self.conn.commit()
        return c.lastrowid

    def expire_old_memories(self, max_age_days: int = 28):
        """Remove memories older than max_age_days (Copilot uses 28-day expiration).

        Returns the number of expired memories removed.
        """
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM memories WHERE timestamp < ?", (cutoff,))
        count = c.fetchone()[0]
        if count > 0:
            c.execute("DELETE FROM memories WHERE timestamp < ?", (cutoff,))
            self.conn.commit()
        return count

    def verify_citations(self, citations_json):
        """Verify that citation locations still contain the expected code.

        Returns (all_valid: bool, status_note: str).
        Implements the JIT verification pattern from GitHub Copilot's
        agentic memory system — verify before trusting.
        """
        if not citations_json:
            return True, ""
        try:
            citations = json.loads(citations_json)
        except (json.JSONDecodeError, TypeError):
            return True, ""
        if not citations:
            return True, ""

        project_dir = Path(__file__).resolve().parent
        stale = []
        for cite in citations:
            fpath = project_dir / cite.get("file", "")
            if not fpath.exists():
                stale.append(f"{cite.get('file', '?')} (not found)")
                continue
            try:
                lines = fpath.read_text(encoding="utf-8").split("\n")
                line_idx = cite.get("line", 0) - 1
                snippet = cite.get("snippet", "").strip()
                if not snippet:
                    continue
                if 0 <= line_idx < len(lines):
                    if snippet in lines[line_idx]:
                        continue
                    window = lines[max(0, line_idx - 2):min(len(lines), line_idx + 3)]
                    if any(snippet in l for l in window):
                        continue
                    stale.append(f"{cite['file']}:{cite['line']} (changed)")
                else:
                    stale.append(f"{cite['file']}:{cite['line']} (out of range)")
            except Exception:
                stale.append(f"{cite.get('file', '?')} (read error)")

        if stale:
            return False, f" [STALE: {'; '.join(stale[:3])}]"
        return True, " [VERIFIED]"

    @staticmethod
    def _sanitize_fts_query(query):
        """Turn a natural-language query into a safe FTS5 expression.

        Uses ghost_query_expansion for multi-language keyword extraction
        with stemming variants. Falls back to basic stopword removal if
        the expansion module is unavailable.
        """
        try:
            from ghost_query_expansion import expand_query_for_fts
            result = expand_query_for_fts(query)
            if result["expanded"]:
                return result["expanded"]
        except ImportError:
            pass

        import re
        stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "do", "does", "did", "have", "has", "had", "i", "me", "my",
            "you", "your", "we", "our", "they", "their", "it", "its",
            "this", "that", "what", "which", "who", "whom", "how",
            "when", "where", "why", "can", "could", "will", "would",
            "shall", "should", "may", "might", "of", "in", "on", "at",
            "to", "for", "with", "by", "from", "about", "and", "or",
            "not", "no", "but", "if", "so", "as", "up", "out", "just",
            "also", "than", "then", "too", "very", "don", "t", "s",
            "re", "ve", "ll", "d", "m",
        }
        text = re.sub(r"[^\w\s]", " ", query)
        words = [w for w in text.lower().split() if w not in stopwords and len(w) > 1]
        if not words:
            words = text.lower().split()[:3]
        return " OR ".join(words)

    def search(self, query, limit=10, type_filter=None):
        """Full-text search across memories. Returns list of dicts."""
        c = self.conn.cursor()
        fts_query = self._sanitize_fts_query(query)
        if not fts_query.strip():
            return self._fallback_search(query, limit, type_filter)
        try:
            if type_filter:
                c.execute("""
                    SELECT m.id, m.timestamp, m.type, m.content, m.source_preview,
                           m.tags, m.skill, m.tools_used, m.citations,
                           rank
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                    AND m.type = ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, type_filter, limit))
            else:
                c.execute("""
                    SELECT m.id, m.timestamp, m.type, m.content, m.source_preview,
                           m.tags, m.skill, m.tools_used, m.citations,
                           rank
                    FROM memories_fts f
                    JOIN memories m ON m.id = f.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, limit))
            results = [dict(row) for row in c.fetchall()]
            if results:
                return results
            return self._fallback_search(query, limit, type_filter)
        except sqlite3.OperationalError:
            return self._fallback_search(query, limit, type_filter)

    def _fallback_search(self, query, limit, type_filter=None):
        """Fallback LIKE search when FTS5 fails or returns nothing."""
        import re
        c = self.conn.cursor()
        text = re.sub(r"[^\w\s]", " ", query)
        words = [w for w in text.split() if len(w) > 1]
        if not words:
            return []
        conditions = " OR ".join(
            ["(content LIKE ? OR tags LIKE ? OR source_preview LIKE ?)"] * len(words)
        )
        params = []
        for w in words:
            pat = f"%{w}%"
            params.extend([pat, pat, pat])

        if type_filter:
            conditions = f"({conditions}) AND type = ?"
            params.append(type_filter)

        c.execute(f"""
            SELECT id, timestamp, type, content, source_preview, tags, skill, tools_used, citations
            FROM memories
            WHERE {conditions}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params + [limit])
        return [dict(row) for row in c.fetchall()]

    def get_recent(self, limit=20, type_filter=None, verify=False):
        """Get the most recent memories, optionally verifying citations."""
        c = self.conn.cursor()
        if type_filter:
            c.execute("""
                SELECT id, timestamp, type, content, source_preview, tags, skill, tools_used, citations
                FROM memories WHERE type = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (type_filter, limit))
        else:
            c.execute("""
                SELECT id, timestamp, type, content, source_preview, tags, skill, tools_used, citations
                FROM memories ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
        rows = [dict(row) for row in c.fetchall()]
        if verify:
            for row in rows:
                _, note = self.verify_citations(row.get("citations", ""))
                row["_citation_status"] = note
        return rows

    def get_by_id(self, memory_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def recent(self, limit=20):
        """Return the most recent memory entries."""
        c = self.conn.cursor()
        c.execute("SELECT * FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(row) for row in c.fetchall()]

    def delete(self, memory_id):
        """Delete a single memory entry by ID."""
        c = self.conn.cursor()
        c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.conn.commit()
        return c.rowcount > 0

    def count(self, type_filter=None):
        c = self.conn.cursor()
        if type_filter:
            c.execute("SELECT COUNT(*) FROM memories WHERE type = ?", (type_filter,))
        else:
            c.execute("SELECT COUNT(*) FROM memories")
        row = c.fetchone()
        return row[0] if row else 0

    def has_source(self, source_hash):
        """Check if we already have an analysis for this source content."""
        c = self.conn.cursor()
        c.execute("SELECT id FROM memories WHERE source_hash = ? LIMIT 1", (source_hash,))
        return c.fetchone() is not None

    def stats(self):
        """Return memory statistics."""
        c = self.conn.cursor()
        c.execute("SELECT type, COUNT(*) as cnt FROM memories GROUP BY type ORDER BY cnt DESC")
        type_counts = {row["type"]: row["cnt"] for row in c.fetchall()}
        c.execute("SELECT COUNT(*) FROM memories")
        total = c.fetchone()[0]
        c.execute("SELECT SUM(tokens_used) FROM memories")
        total_tokens = c.fetchone()[0] or 0
        return {
            "total": total,
            "by_type": type_counts,
            "total_tokens": total_tokens,
        }

    def prune(self, max_entries=5000):
        """Remove oldest entries if we exceed the limit."""
        try:
            count = self.count()
            if count <= max_entries:
                return 0
            to_delete = count - max_entries
            c = self.conn.cursor()
            c.execute("""
                DELETE FROM memories WHERE id IN (
                    SELECT id FROM memories ORDER BY timestamp ASC LIMIT ?
                )
            """, (to_delete,))
            self.conn.commit()
            return to_delete
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            return 0

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
#  MEMORY TOOLS (for the tool registry)
# ═════════════════════════════════════════════════════════════════════

def make_memory_search(memory_db):
    """Create memory_search tool that uses the memory DB."""
    def execute(query, limit=5, type_filter=None):
        results = memory_db.search(query, limit=limit, type_filter=type_filter)
        if not results:
            return "No memories found matching that query."
        parts = []
        has_stale = False
        for r in results:
            ts = r["timestamp"][:19].replace("T", " ")
            citations_raw = r.get("citations", "")
            valid, verify_note = memory_db.verify_citations(citations_raw)
            if not valid:
                has_stale = True
            parts.append(
                f"[{ts}] ({r['type']}) {r['content'][:300]}{verify_note}"
            )
        result = "\n---\n".join(parts)
        if has_stale:
            result += (
                "\n\n⚠ STALE MEMORIES DETECTED: Some memories have citations that no "
                "longer match the current codebase. If you use information from a "
                "[STALE] memory, verify it first. Consider saving a corrected version "
                "with memory_save (include updated citations)."
            )
        return result

    return {
        "name": "memory_search",
        "description": (
            "Search Ghost's memory for past analyses, notes, and context. "
            "Results with code citations are verified in real-time: [VERIFIED] "
            "means the cited code still matches, [STALE] means the code has changed "
            "since the memory was saved — treat stale memories with caution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (keywords or natural language)"},
                "limit": {"type": "integer", "description": "Max results to return", "default": 5},
                "type_filter": {"type": "string", "description": "Filter by type (analysis, note, error, code, etc.)", "default": None},
            },
            "required": ["query"],
        },
        "execute": execute,
    }


def make_memory_save(memory_db):
    """Create memory_save tool that writes to the memory DB."""
    def execute(content, tags="", type="note", citations=""):
        memory_db.save(
            content=content,
            type=type,
            tags=tags,
            source_preview=content[:100],
            citations=citations,
        )
        cite_info = ""
        if citations:
            try:
                n = len(json.loads(citations))
                cite_info = f", {n} citation(s)"
            except Exception:
                pass
        return f"OK: saved to memory ({len(content)} chars, tags: {tags or 'none'}{cite_info})"

    return {
        "name": "memory_save",
        "description": (
            "Save important information to Ghost's persistent memory for future reference. "
            "Optionally include citations — references to specific code locations "
            "(file, line, snippet) that support the fact. Cited memories are "
            "automatically verified on retrieval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Information to remember"},
                "tags": {"type": "string", "description": "Comma-separated tags for organization", "default": ""},
                "type": {"type": "string", "description": "Type of memory (note, insight, preference, etc.)", "default": "note"},
                "citations": {
                    "type": "string",
                    "description": (
                        "Optional JSON array of code location citations. "
                        "Format: [{\"file\": \"ghost_loop.py\", \"line\": 42, \"snippet\": \"class Foo:\"}]. "
                        "Citations are verified when the memory is retrieved."
                    ),
                    "default": "",
                },
            },
            "required": ["content"],
        },
        "execute": execute,
    }
