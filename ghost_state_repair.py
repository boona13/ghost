"""
GHOST State File Repair

Validates and repairs Ghost's critical state files (config, databases, logs).
Inspired by OpenClaw's session-transcript-repair.ts and session-file-repair.ts.
"""

import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("ghost.state_repair")

GHOST_HOME = Path.home() / ".ghost"
BACKUP_DIR = GHOST_HOME / "state_backups"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, dest)
    return dest


def repair_config(config_path: Path = None) -> dict:
    """Validate and repair config.json. Returns repair report."""
    config_path = config_path or (GHOST_HOME / "config.json")
    report = {"file": str(config_path), "status": "ok", "repairs": []}

    if not config_path.exists():
        report["status"] = "missing"
        report["repairs"].append("Config file does not exist — Ghost will use defaults")
        return report

    try:
        raw = config_path.read_text()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Config root must be a JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        report["status"] = "corrupted"
        bak = _backup(config_path)
        report["repairs"].append(f"Backed up corrupted config to {bak}")
        config_path.write_text("{}")
        report["repairs"].append("Reset config to empty object — Ghost will use defaults")
        return report

    required_keys = {"model": "google/gemini-2.0-flash-001"}
    for key, default in required_keys.items():
        if key not in data or not data[key]:
            data[key] = default
            report["repairs"].append(f"Restored missing key '{key}' = '{default}'")

    if report["repairs"]:
        _backup(config_path)
        config_path.write_text(json.dumps(data, indent=2))
        report["status"] = "repaired"

    return report


def repair_sqlite_db(db_path: Path, label: str = "database") -> dict:
    """Validate and repair a SQLite database. Returns repair report."""
    report = {"file": str(db_path), "label": label, "status": "ok", "repairs": []}

    if not db_path.exists():
        report["status"] = "missing"
        report["repairs"].append(f"{label} does not exist — will be recreated on next use")
        return report

    try:
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            report["status"] = "corrupted"
            bak = _backup(db_path)
            report["repairs"].append(f"Integrity check failed: {result[0]}")
            report["repairs"].append(f"Backed up corrupted DB to {bak}")
            try:
                conn.execute("REINDEX")
                conn.commit()
                re_check = conn.execute("PRAGMA integrity_check").fetchone()
                if re_check[0] == "ok":
                    report["status"] = "repaired"
                    report["repairs"].append("REINDEX fixed the database")
                else:
                    db_path.unlink()
                    report["repairs"].append("Database was unrecoverable — deleted for recreation")
            except Exception:
                db_path.unlink()
                report["repairs"].append("REINDEX failed — deleted database for recreation")
        else:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        conn.close()
    except sqlite3.DatabaseError as e:
        report["status"] = "corrupted"
        bak = _backup(db_path)
        report["repairs"].append(f"Cannot open database: {e}")
        report["repairs"].append(f"Backed up corrupted file to {bak}")
        db_path.unlink(missing_ok=True)
        report["repairs"].append("Deleted corrupted file for recreation")
    except Exception as e:
        report["status"] = "error"
        report["repairs"].append(f"Unexpected error: {e}")

    return report


def repair_jsonl(jsonl_path: Path, label: str = "log") -> dict:
    """Validate and repair a JSONL file by dropping malformed lines."""
    report = {"file": str(jsonl_path), "label": label, "status": "ok", "repairs": []}

    if not jsonl_path.exists():
        report["status"] = "missing"
        return report

    try:
        raw_lines = jsonl_path.read_text().splitlines()
    except Exception as e:
        report["status"] = "unreadable"
        report["repairs"].append(f"Cannot read file: {e}")
        return report

    valid_lines = []
    dropped = 0
    for i, line in enumerate(raw_lines):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
            valid_lines.append(line)
        except json.JSONDecodeError:
            dropped += 1

    if dropped > 0:
        _backup(jsonl_path)
        jsonl_path.write_text("\n".join(valid_lines) + "\n" if valid_lines else "")
        report["status"] = "repaired"
        report["repairs"].append(f"Dropped {dropped} malformed line(s) out of {len(raw_lines)}")

    return report


def run_full_repair() -> list[dict]:
    """Run repair on all Ghost state files. Returns list of repair reports."""
    reports = []

    reports.append(repair_config())

    for db_name, label in [
        ("memory.db", "Memory database"),
        ("x_tracker.db", "X tracker database"),
    ]:
        reports.append(repair_sqlite_db(GHOST_HOME / db_name, label))

    debug_log = GHOST_HOME / "debug" / "tool_loop_debug.jsonl"
    if debug_log.exists():
        reports.append(repair_jsonl(debug_log, "Debug log"))

    evolve_history = GHOST_HOME / "evolve" / "history.jsonl"
    if evolve_history.exists():
        reports.append(repair_jsonl(evolve_history, "Evolution history"))

    issues = [r for r in reports if r["status"] not in ("ok", "missing")]
    if issues:
        log.warning("State repair found %d issue(s):", len(issues))
        for r in issues:
            log.warning("  %s: %s — %s", r.get("label", r["file"]), r["status"],
                        "; ".join(r["repairs"]))
    else:
        log.info("State repair: all files healthy")

    return reports


def build_state_repair_tools() -> list[dict]:
    """Build repair tools for the Ghost tool registry."""

    def repair_state_exec(**_extra):
        reports = run_full_repair()
        issues = [r for r in reports if r["status"] not in ("ok", "missing")]
        if not issues:
            return "All Ghost state files are healthy. No repairs needed."
        lines = [f"Repaired {len(issues)} issue(s):"]
        for r in issues:
            lines.append(f"  {r.get('label', r['file'])}: {r['status']}")
            for repair in r["repairs"]:
                lines.append(f"    → {repair}")
        return "\n".join(lines)

    return [
        {
            "name": "repair_state",
            "description": (
                "Validate and repair Ghost's state files (config, databases, logs). "
                "Checks integrity of SQLite databases, fixes corrupted JSON files, "
                "drops malformed JSONL lines. Creates backups before any repair."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "execute": repair_state_exec,
        }
    ]
