"""
Durable Turn Journal Extension — Checkpoint and resume for long-running tasks.

Captures tool-loop state (goal, completed steps, pending steps, key artifacts,
last successful tool outputs) into JSON snapshots stored under ~/.ghost/journals/.

Tools:
  - journal_checkpoint: Create a checkpoint snapshot
  - journal_list: List checkpoints for a session
  - journal_resume: Load a checkpoint and return resume context
  - journal_export: Export checkpoints (JSON or Markdown)
  - journal_import: Import checkpoints from JSON

Hooks:
  - on_tool_result: Auto-capture lightweight checkpoints after successful tool calls
  - on_generation_interrupt: Capture state when generation is interrupted
  - on_boot: Prune old checkpoints on startup

Security: Secrets/tokens are redacted from captured payloads.
"""

import json
import logging
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ghost.ext.durable_turn_journal")

# Thread-safe file operations
_file_lock = threading.Lock()

# Sensitive field patterns to redact
_SENSITIVE_PATTERNS = [
    re.compile(r'api[_-]?key', re.I),
    re.compile(r'auth[_-]?token', re.I),
    re.compile(r'password', re.I),
    re.compile(r'secret', re.I),
    re.compile(r'private[_-]?key', re.I),
    re.compile(r'access[_-]?token', re.I),
    re.compile(r'bearer\s+\S+', re.I),
]


def _redact_sensitive(data: Any) -> Any:
    """Recursively redact sensitive fields from data structures."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Check if key matches sensitive patterns
            is_sensitive = any(p.search(key) for p in _SENSITIVE_PATTERNS)
            if is_sensitive and isinstance(value, str):
                result[key] = "***REDACTED***"
            else:
                result[key] = _redact_sensitive(value)
        return result
    elif isinstance(data, list):
        return [_redact_sensitive(item) for item in data]
    elif isinstance(data, str):
        # Redact bearer tokens in strings
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.pattern.startswith('bearer'):
                data = pattern.sub('Bearer ***REDACTED***', data)
        return data
    return data


def _atomic_write_json(path: Path, data: Any):
    """Atomically write JSON to a file using temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, str(path))
    except Exception:
        if Path(tmp).exists():
            os.unlink(tmp)
        raise


def _load_json_safe(path: Path, default=None) -> Any:
    """Safely load JSON from a file, returning default on any error."""
    if not path.exists():
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("Failed to load %s: %s", path, exc)
        return default


def _generate_journal_id(session_id: str, timestamp: str) -> str:
    """Generate a unique journal ID from session and timestamp."""
    safe_session = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)[:50]
    safe_ts = re.sub(r'[^0-9]', '', timestamp)[:14]
    return f"{safe_session}_{safe_ts}"


def register(api):
    """Entry point called by ExtensionManager during load."""
    
    # Ensure journals directory exists
    journals_dir = Path.home() / ".ghost" / "journals"
    journals_dir.mkdir(parents=True, exist_ok=True)
    
    # In-memory cache of recent checkpoints (lightweight)
    _recent_checkpoints: dict[str, dict] = {}
    
    def _get_session_path(session_id: str) -> Path:
        """Get the file path for a session's checkpoints."""
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)[:64]
        return journals_dir / f"{safe_id}.jsonl"
    
    def _prune_session_checkpoints(session_id: str):
        """Prune old checkpoints for a session based on retention settings."""
        max_checkpoints = api.get_setting("max_checkpoints_per_session", 50)
        retention_days = api.get_setting("retention_days", 30)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        path = _get_session_path(session_id)
        if not path.exists():
            return
        
        with _file_lock:
            checkpoints = []
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            cp = json.loads(line)
                            # Check retention
                            ts_str = cp.get('timestamp', '')
                            try:
                                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                if ts >= cutoff_date:
                                    checkpoints.append(cp)
                            except ValueError:
                                checkpoints.append(cp)  # Keep if can't parse
                        except json.JSONDecodeError:
                            continue
            except OSError as exc:
                log.warning("Failed to read checkpoints for pruning: %s", exc)
                return
            
            # Keep only the most recent max_checkpoints
            if len(checkpoints) > max_checkpoints:
                checkpoints = checkpoints[-max_checkpoints:]
            
            # Rewrite file
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    for cp in checkpoints:
                        f.write(json.dumps(cp, default=str) + '\n')
            except OSError as exc:
                log.warning("Failed to write pruned checkpoints: %s", exc)

    # ═════════════════════════════════════════════════════════════════
    #  TOOL: journal_checkpoint
    # ═════════════════════════════════════════════════════════════════
    
    def execute_journal_checkpoint(session_id: str = "", label: str = "", 
                                    goal: str = "", completed_steps: list = None,
                                    pending_steps: list = None, artifacts: dict = None,
                                    context: dict = None, **kwargs) -> str:
        """Create a checkpoint snapshot for the current session state."""
        if not session_id:
            return json.dumps({"status": "error", "error": "session_id is required"})
        
        completed_steps = completed_steps or []
        pending_steps = pending_steps or []
        artifacts = artifacts or {}
        context = context or {}
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        journal_id = _generate_journal_id(session_id, timestamp)
        
        checkpoint = {
            "journal_id": journal_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "label": label or f"Checkpoint at {timestamp[:19]}",
            "goal": goal,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "artifacts": _redact_sensitive(artifacts),
            "context": _redact_sensitive(context),
            "version": "1.0",
        }
        
        # Write to session file
        path = _get_session_path(session_id)
        with _file_lock:
            try:
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(checkpoint, default=str) + '\n')
            except OSError as exc:
                log.error("Failed to write checkpoint: %s", exc)
                return json.dumps({"status": "error", "error": f"Failed to write checkpoint: {exc}"})
        
        # Cache recent checkpoint
        _recent_checkpoints[journal_id] = checkpoint
        
        # Prune if needed (async, don't block)
        try:
            _prune_session_checkpoints(session_id)
        except Exception as exc:
            log.warning("Pruning failed (non-critical): %s", exc)
        
        api.memory_save(
            content=f"[Journal] Checkpoint created: {label} for session {session_id}",
            tags="journal,checkpoint,automation",
            memory_type="note"
        )
        
        return json.dumps({
            "status": "ok",
            "journal_id": journal_id,
            "timestamp": timestamp,
            "checkpoint_count": len(_list_checkpoints(session_id)),
        })
    
    api.register_tool({
        "name": "journal_checkpoint",
        "description": (
            "Create a durable checkpoint snapshot for the current session state. "
            "Captures goal, completed steps, pending steps, and artifacts. "
            "Use this to save progress in long-running tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Unique identifier for this session/task",
                },
                "label": {
                    "type": "string",
                    "description": "Human-readable label for this checkpoint",
                },
                "goal": {
                    "type": "string",
                    "description": "Current goal or objective",
                },
                "completed_steps": {
                    "type": "array",
                    "description": "List of completed steps/actions",
                    "items": {"type": "string"},
                },
                "pending_steps": {
                    "type": "array",
                    "description": "List of pending steps/actions",
                    "items": {"type": "string"},
                },
                "artifacts": {
                    "type": "object",
                    "description": "Key artifacts produced so far (files, URLs, etc.)",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context to preserve",
                },
            },
            "required": ["session_id"],
        },
        "execute": execute_journal_checkpoint,
    })
    
    # ═════════════════════════════════════════════════════════════════
    #  TOOL: journal_list
    # ═════════════════════════════════════════════════════════════════
    
    def _list_checkpoints(session_id: str) -> list:
        """Internal: list all checkpoints for a session."""
        path = _get_session_path(session_id)
        if not path.exists():
            return []
        
        checkpoints = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cp = json.loads(line)
                        checkpoints.append(cp)
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            log.warning("Failed to read checkpoints: %s", exc)
        
        return checkpoints
    
    def execute_journal_list(session_id: str = "", limit: int = 20, **kwargs) -> str:
        """List checkpoints for a session, most recent first."""
        if not session_id:
            # List all sessions
            sessions = []
            try:
                for f in journals_dir.glob("*.jsonl"):
                    session_name = f.stem
                    checkpoints = _list_checkpoints(session_name)
                    if checkpoints:
                        sessions.append({
                            "session_id": session_name,
                            "checkpoint_count": len(checkpoints),
                            "last_checkpoint": checkpoints[-1].get("timestamp"),
                            "last_label": checkpoints[-1].get("label"),
                        })
            except OSError as exc:
                log.warning("Failed to list sessions: %s", exc)
            
            sessions.sort(key=lambda x: x.get("last_checkpoint", ""), reverse=True)
            return json.dumps({
                "status": "ok",
                "sessions": sessions[:limit],
            })
        
        checkpoints = _list_checkpoints(session_id)
        # Return most recent first, with summaries
        summary = []
        for cp in reversed(checkpoints[-limit:]):
            summary.append({
                "journal_id": cp.get("journal_id"),
                "timestamp": cp.get("timestamp"),
                "label": cp.get("label"),
                "goal_preview": cp.get("goal", "")[:100] if cp.get("goal") else "",
                "completed_count": len(cp.get("completed_steps", [])),
                "pending_count": len(cp.get("pending_steps", [])),
            })
        
        return json.dumps({
            "status": "ok",
            "session_id": session_id,
            "checkpoints": summary,
            "total_count": len(checkpoints),
        })
    
    api.register_tool({
        "name": "journal_list",
        "description": (
            "List checkpoint journals. Without session_id, lists all sessions. "
            "With session_id, lists checkpoints for that session (most recent first)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to list checkpoints for (omit to list all sessions)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 20,
                },
            },
            "required": [],
        },
        "execute": execute_journal_list,
    })

    # ═════════════════════════════════════════════════════════════════
    #  TOOL: journal_resume
    # ═════════════════════════════════════════════════════════════════
    
    def execute_journal_resume(journal_id: str = "", session_id: str = "", 
                                **kwargs) -> str:
        """Load a checkpoint and return resume context."""
        if not journal_id and not session_id:
            return json.dumps({
                "status": "error", 
                "error": "Either journal_id or session_id is required"
            })
        
        checkpoint = None
        
        # Try to find by journal_id
        if journal_id:
            # Check cache first
            if journal_id in _recent_checkpoints:
                checkpoint = _recent_checkpoints[journal_id]
            else:
                # Search all sessions
                try:
                    for f in journals_dir.glob("*.jsonl"):
                        with open(f, 'r', encoding='utf-8') as file:
                            for line in file:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    cp = json.loads(line)
                                    if cp.get("journal_id") == journal_id:
                                        checkpoint = cp
                                        break
                                except json.JSONDecodeError:
                                    continue
                        if checkpoint:
                            break
                except OSError as exc:
                    log.warning("Failed to search for journal: %s", exc)
        
        # If no journal_id or not found, get latest for session
        if not checkpoint and session_id:
            checkpoints = _list_checkpoints(session_id)
            if checkpoints:
                checkpoint = checkpoints[-1]  # Most recent
        
        if not checkpoint:
            return json.dumps({
                "status": "error",
                "error": f"Checkpoint not found: journal_id={journal_id}, session_id={session_id}",
            })
        
        # Build resume context
        resume_context = {
            "journal_id": checkpoint.get("journal_id"),
            "session_id": checkpoint.get("session_id"),
            "timestamp": checkpoint.get("timestamp"),
            "label": checkpoint.get("label"),
            "goal": checkpoint.get("goal"),
            "completed_steps": checkpoint.get("completed_steps", []),
            "pending_steps": checkpoint.get("pending_steps", []),
            "artifacts": checkpoint.get("artifacts", {}),
            "context": checkpoint.get("context", {}),
        }
        
        # Save to memory that we resumed
        api.memory_save(
            content=f"[Journal] Resumed checkpoint: {checkpoint.get('label')} for session {checkpoint.get('session_id')}",
            tags="journal,resume,automation",
            memory_type="note"
        )
        
        return json.dumps({
            "status": "ok",
            "resume_context": resume_context,
            "message": f"Resumed from checkpoint: {checkpoint.get('label')}",
        })
    
    api.register_tool({
        "name": "journal_resume",
        "description": (
            "Load a checkpoint journal and return resume context. "
            "Provide journal_id for a specific checkpoint, or session_id to get "
            "the latest checkpoint for that session. Returns goal, completed steps, "
            "pending steps, and artifacts needed to resume work."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "journal_id": {
                    "type": "string",
                    "description": "Specific journal checkpoint ID to resume from",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID to resume (gets latest checkpoint)",
                },
            },
            "required": [],
        },
        "execute": execute_journal_resume,
    })
    
    # ═════════════════════════════════════════════════════════════════
    #  TOOL: journal_export
    # ═════════════════════════════════════════════════════════════════
    
    def execute_journal_export(session_id: str = "", format: str = "json", 
                                **kwargs) -> str:
        """Export checkpoints for a session (JSON or Markdown)."""
        if not session_id:
            return json.dumps({"status": "error", "error": "session_id is required"})
        
        checkpoints = _list_checkpoints(session_id)
        if not checkpoints:
            return json.dumps({
                "status": "error",
                "error": f"No checkpoints found for session: {session_id}",
            })
        
        if format.lower() == "markdown":
            # Generate Markdown report
            lines = [
                f"# Journal Export: {session_id}",
                f"\nGenerated: {datetime.utcnow().isoformat()}Z",
                f"Total checkpoints: {len(checkpoints)}\n",
                "---\n",
            ]
            
            for i, cp in enumerate(checkpoints, 1):
                lines.extend([
                    f"\n## Checkpoint {i}: {cp.get('label', 'Untitled')}",
                    f"**ID:** `{cp.get('journal_id')}`",
                    f"**Timestamp:** {cp.get('timestamp')}",
                ])
                
                if cp.get('goal'):
                    lines.extend([f"\n### Goal\n{cp['goal']}"])
                
                completed = cp.get('completed_steps', [])
                if completed:
                    lines.extend(["\n### Completed Steps"])
                    for step in completed:
                        lines.append(f"- {step}")
                
                pending = cp.get('pending_steps', [])
                if pending:
                    lines.extend(["\n### Pending Steps"])
                    for step in pending:
                        lines.append(f"- [ ] {step}")
                
                artifacts = cp.get('artifacts', {})
                if artifacts:
                    lines.extend(["\n### Artifacts"])
                    for key, value in artifacts.items():
                        lines.append(f"- **{key}:** {value}")
                
                lines.append("\n---\n")
            
            content = "\n".join(lines)
            return json.dumps({
                "status": "ok",
                "format": "markdown",
                "session_id": session_id,
                "content": content,
                "checkpoint_count": len(checkpoints),
            })
        
        else:  # JSON format
            export_data = {
                "session_id": session_id,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "checkpoint_count": len(checkpoints),
                "checkpoints": checkpoints,
            }
            return json.dumps({
                "status": "ok",
                "format": "json",
                "session_id": session_id,
                "content": json.dumps(export_data, indent=2, default=str),
                "checkpoint_count": len(checkpoints),
            })
    
    api.register_tool({
        "name": "journal_export",
        "description": (
            "Export all checkpoints for a session as JSON or Markdown. "
            "Useful for sharing progress, documentation, or backup."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to export",
                },
                "format": {
                    "type": "string",
                    "description": "Export format: 'json' or 'markdown'",
                    "enum": ["json", "markdown"],
                    "default": "json",
                },
            },
            "required": ["session_id"],
        },
        "execute": execute_journal_export,
    })
    
    # ═════════════════════════════════════════════════════════════════
    #  TOOL: journal_import
    # ═════════════════════════════════════════════════════════════════
    
    def execute_journal_import(data: str = "", session_id: str = "", 
                                **kwargs) -> str:
        """Import checkpoints from JSON export."""
        if not data:
            return json.dumps({"status": "error", "error": "data is required"})
        
        try:
            import_data = json.loads(data)
        except json.JSONDecodeError as exc:
            return json.dumps({"status": "error", "error": f"Invalid JSON: {exc}"})
        
        # Handle both full export format and simple array
        if isinstance(import_data, dict) and "checkpoints" in import_data:
            checkpoints = import_data["checkpoints"]
            source_session = import_data.get("session_id", "unknown")
        elif isinstance(import_data, list):
            checkpoints = import_data
            source_session = "unknown"
        else:
            return json.dumps({"status": "error", "error": "Invalid import format"})
        
        if not isinstance(checkpoints, list):
            return json.dumps({"status": "error", "error": "Checkpoints must be an array"})
        
        # Use provided session_id or from import
        target_session = session_id or source_session
        
        imported = 0
        path = _get_session_path(target_session)
        
        with _file_lock:
            try:
                with open(path, 'a', encoding='utf-8') as f:
                    for cp in checkpoints:
                        if not isinstance(cp, dict):
                            continue
                        # Update session_id to target
                        cp["session_id"] = target_session
                        # Generate new journal_id to avoid collisions
                        timestamp = datetime.utcnow().isoformat() + "Z"
                        cp["journal_id"] = _generate_journal_id(target_session, timestamp)
                        cp["imported_at"] = timestamp
                        cp["original_journal_id"] = cp.get("journal_id")
                        f.write(json.dumps(cp, default=str) + '\n')
                        imported += 1
            except OSError as exc:
                log.error("Failed to import checkpoints: %s", exc)
                return json.dumps({"status": "error", "error": f"Failed to import: {exc}"})
        
        api.memory_save(
            content=f"[Journal] Imported {imported} checkpoints to session {target_session}",
            tags="journal,import,automation",
            memory_type="note"
        )
        
        return json.dumps({
            "status": "ok",
            "imported_count": imported,
            "session_id": target_session,
        })
    
    api.register_tool({
        "name": "journal_import",
        "description": (
            "Import checkpoints from a JSON export. "
            "Useful for restoring from backup or transferring between systems."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "JSON string containing checkpoints to import",
                },
                "session_id": {
                    "type": "string",
                    "description": "Target session ID (optional, uses source session if omitted)",
                },
            },
            "required": ["data"],
        },
        "execute": execute_journal_import,
    })

    # ═════════════════════════════════════════════════════════════════
    #  HOOKS
    # ═════════════════════════════════════════════════════════════════
    
    def on_tool_result(**kwargs):
        """Auto-capture lightweight checkpoint after successful tool calls."""
        if not api.get_setting("auto_checkpoint_enabled", True):
            return
        
        tool_name = kwargs.get("tool_name", "")
        result = kwargs.get("result", "")
        session_context = kwargs.get("session_context", {})
        
        session_id = session_context.get("session_id", "")
        if not session_id:
            return  # Can't auto-capture without session context
        
        # Only capture for significant tools (not internal/debug)
        significant_tools = [
            "shell_exec", "file_write", "file_read", "web_fetch",
            "web_search", "evolve_apply", "evolve_test", "evolve_submit_pr",
            "browser_navigate", "browser_click", "memory_save",
        ]
        
        if tool_name not in significant_tools:
            return
        
        # Build lightweight checkpoint
        timestamp = datetime.utcnow().isoformat() + "Z"
        journal_id = _generate_journal_id(session_id, timestamp)
        
        # Truncate result for storage
        result_preview = str(result)[:500] if result else ""
        
        checkpoint = {
            "journal_id": journal_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "label": f"Auto: {tool_name} completed",
            "goal": session_context.get("goal", ""),
            "completed_steps": session_context.get("completed_steps", []) + [f"{tool_name}: {result_preview[:100]}..."],
            "pending_steps": session_context.get("pending_steps", []),
            "artifacts": _redact_sensitive(session_context.get("artifacts", {})),
            "context": {
                "auto_captured": True,
                "trigger_tool": tool_name,
                "result_preview": result_preview,
            },
            "version": "1.0",
        }
        
        # Write to session file (fire and forget, don't block)
        path = _get_session_path(session_id)
        try:
            with _file_lock:
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(checkpoint, default=str) + '\n')
            _recent_checkpoints[journal_id] = checkpoint
        except Exception as exc:
            log.debug("Auto-checkpoint failed (non-critical): %s", exc)
    
    api.register_hook("on_tool_result", on_tool_result)
    
    def on_generation_interrupt(**kwargs):
        """Capture state when generation is interrupted."""
        session_context = kwargs.get("session_context", {})
        session_id = session_context.get("session_id", "")
        
        if not session_id:
            return
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        journal_id = _generate_journal_id(session_id, timestamp)
        
        checkpoint = {
            "journal_id": journal_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "label": "Auto: Generation interrupted",
            "goal": session_context.get("goal", ""),
            "completed_steps": session_context.get("completed_steps", []),
            "pending_steps": session_context.get("pending_steps", []),
            "artifacts": _redact_sensitive(session_context.get("artifacts", {})),
            "context": {
                "auto_captured": True,
                "interrupt_reason": kwargs.get("reason", "unknown"),
                "interrupt_data": kwargs.get("data", {}),
            },
            "version": "1.0",
        }
        
        path = _get_session_path(session_id)
        try:
            with _file_lock:
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(checkpoint, default=str) + '\n')
            _recent_checkpoints[journal_id] = checkpoint
            
            api.memory_save(
                content=f"[Journal] Auto-captured interrupt checkpoint for session {session_id}",
                tags="journal,interrupt,automation",
                memory_type="note"
            )
        except Exception as exc:
            log.warning("Interrupt checkpoint failed: %s", exc)
    
    api.register_hook("on_generation_interrupt", on_generation_interrupt)
    
    def on_boot():
        """Prune old checkpoints on startup."""
        log.info("Durable Turn Journal extension booted")
        
        retention_days = api.get_setting("retention_days", 30)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        pruned_sessions = 0
        pruned_checkpoints = 0
        
        try:
            for f in journals_dir.glob("*.jsonl"):
                try:
                    with open(f, 'r', encoding='utf-8') as file:
                        lines = file.readlines()
                    
                    kept = []
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            cp = json.loads(line)
                            ts_str = cp.get('timestamp', '')
                            try:
                                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                if ts >= cutoff_date:
                                    kept.append(line)
                                else:
                                    pruned_checkpoints += 1
                            except ValueError:
                                kept.append(line)  # Keep if can't parse
                        except json.JSONDecodeError:
                            continue
                    
                    if len(kept) < len(lines):
                        with _file_lock:
                            with open(f, 'w', encoding='utf-8') as file:
                                for line in kept:
                                    file.write(line + '\n')
                        pruned_sessions += 1
                
                except OSError as exc:
                    log.warning("Failed to prune %s: %s", f, exc)
        
        except Exception as exc:
            log.warning("Boot pruning failed: %s", exc)
        
        if pruned_sessions > 0:
            log.info("Pruned %d checkpoints from %d sessions", pruned_checkpoints, pruned_sessions)
    
    api.register_hook("on_boot", on_boot)
    
    # ═════════════════════════════════════════════════════════════════
    #  DASHBOARD PAGE
    # ═════════════════════════════════════════════════════════════════
    
    api.register_page({
        "id": "durable_turn_journal",
        "label": "Turn Journal",
        "icon": "journal",
        "section": "automation",
        "js_path": "durable_turn_journal.js",
    })
    
    api.log("Durable Turn Journal extension registered successfully")
