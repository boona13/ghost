import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)
_file_lock = threading.Lock()


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, out))


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Failed writing JSON %s: %s", path, exc)
        if Path(tmp).exists():
            try:
                os.unlink(tmp)
            except OSError as cleanup_exc:
                logger.warning("Failed cleaning temp file %s: %s", tmp, cleanup_exc)
        raise


def _rules_path(api) -> Path:
    return Path(api.data_dir) / "ruleset.json"


def _history_path(api) -> Path:
    return Path(api.data_dir) / "history.json"


def _default_rules() -> dict[str, Any]:
    return {
        "version": 1,
        "checks": [
            {"id": "todo_markers", "regex": r"\b(TODO|FIXME|HACK)\b", "severity": "warning"},
            {"id": "bare_except", "regex": r"except\s*:\s*$", "severity": "error"},
            {"id": "silent_pass", "regex": r"except\s+[^\n]+:\s*\n\s*pass\b", "severity": "error"},
        ],
    }


def _load_rules(api) -> dict[str, Any]:
    path = _rules_path(api)
    with _file_lock:
        if not path.exists():
            rules = _default_rules()
            _atomic_write_json(path, rules)
            return rules
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed reading ruleset %s: %s", path, exc)
            return _default_rules()
    if isinstance(data, dict) and isinstance(data.get("checks"), list):
        return data
    return _default_rules()


def _save_rules(api, rules: dict[str, Any]) -> None:
    path = _rules_path(api)
    with _file_lock:
        _atomic_write_json(path, rules)


def _load_history(api, limit: int) -> list[dict[str, Any]]:
    path = _history_path(api)
    with _file_lock:
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
            loaded = json.loads(raw) if raw.strip() else []
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed reading history %s: %s", path, exc)
            return []
    if not isinstance(loaded, list):
        return []
    return loaded[-limit:]


def _append_history(api, entry: dict[str, Any], max_entries: int) -> None:
    path = _history_path(api)
    with _file_lock:
        rows: list[dict[str, Any]] = []
        if path.exists():
            try:
                raw = path.read_text(encoding="utf-8")
                loaded = json.loads(raw) if raw.strip() else []
                if isinstance(loaded, list):
                    rows = loaded[-max_entries:]
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                logger.warning("Failed parsing history %s: %s", path, exc)
                rows = []
        rows.append(entry)
        rows = rows[-max_entries:]
        _atomic_write_json(path, rows)


def _validate_checks(checks: Any) -> list[dict[str, str]]:
    if not isinstance(checks, list):
        return []
    out: list[dict[str, str]] = []
    for item in checks:
        if not isinstance(item, dict):
            continue
        cid = _coerce_text(item.get("id")).strip()
        pattern = _coerce_text(item.get("regex")).strip()
        severity = _coerce_text(item.get("severity"), "warning").strip().lower()
        if not cid or not pattern:
            continue
        if severity not in {"info", "warning", "error"}:
            severity = "warning"
        try:
            re.compile(pattern)
        except re.error as exc:
            logger.warning("Invalid regex for rule %s: %s", cid, exc)
            continue
        out.append({"id": cid, "regex": pattern, "severity": severity})
    return out


def _github_fetch_pr_files(owner: str, repo: str, number: int, token: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    return []


def _annotate(files: list[dict[str, Any]], checks: list[dict[str, str]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for file_entry in files:
        filename = _coerce_text(file_entry.get("filename")).strip()
        patch = _coerce_text(file_entry.get("patch"))
        if not filename or not patch:
            continue
        lines = patch.splitlines()
        for idx, line in enumerate(lines, start=1):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            content = line[1:]
            for rule in checks:
                if re.search(rule["regex"], content):
                    findings.append(
                        {
                            "file": filename,
                            "line_in_patch": idx,
                            "severity": rule["severity"],
                            "rule_id": rule["id"],
                            "excerpt": content[:300],
                        }
                    )
    return findings


def register(api):
    # Create Flask blueprint for dashboard API routes
    bp = Blueprint("pr_review_annotator", __name__, url_prefix="/extensions/pr_review_annotator")

    @bp.route("/ruleset", methods=["GET"])
    def _route_ruleset_get():
        try:
            rules = _load_rules(api)
            return jsonify({"status": "ok", "ruleset": rules})
        except Exception as exc:
            logger.warning("Failed to load ruleset: %s", exc)
            return jsonify({"status": "error", "error": "failed to load ruleset"}), 500

    api.register_route(bp)

    def pr_review_ruleset_get(**kwargs):
        _ = kwargs
        rules = _load_rules(api)
        return json.dumps({"status": "ok", "ruleset": rules}, ensure_ascii=False)

    def pr_review_ruleset_set(checks=None, **kwargs):
        incoming = checks if checks is not None else kwargs.get("checks")
        parsed = _validate_checks(incoming)
        if not parsed:
            return json.dumps({"status": "error", "error": "no valid checks provided"})
        ruleset = {"version": 1, "checks": parsed}
        _save_rules(api, ruleset)
        return json.dumps({"status": "ok", "saved": len(parsed)}, ensure_ascii=False)

    def review_github_pr(
        owner: str = "",
        repo: str = "",
        pr_number: int = 0,
        mode: str = "",
        include_info: bool = False,
        github_token: str = "",
        max_findings: int = 200,
        **kwargs,
    ):
        owner_s = _coerce_text(owner).strip()
        repo_s = _coerce_text(repo).strip()
        if not owner_s or not repo_s:
            return json.dumps({"status": "error", "error": "owner and repo are required"})

        try:
            pr_num = int(pr_number)
        except (TypeError, ValueError):
            return json.dumps({"status": "error", "error": "pr_number must be an integer"})
        if pr_num <= 0:
            return json.dumps({"status": "error", "error": "pr_number must be > 0"})

        review_mode = _coerce_text(mode).strip().lower() or _coerce_text(
            api.get_setting("pr_review_default_mode", "dry_run")
        ).strip().lower()
        if review_mode not in {"dry_run", "report"}:
            review_mode = "dry_run"

        token = _coerce_text(github_token).strip() or _coerce_text(kwargs.get("token")).strip()
        if not token:
            token = _coerce_text(os.getenv("GITHUB_TOKEN")).strip()

        rules = _load_rules(api)
        checks = _validate_checks(rules.get("checks"))
        if not checks:
            checks = _default_rules()["checks"]

        try:
            files = _github_fetch_pr_files(owner_s, repo_s, pr_num, token)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            logger.warning("GitHub PR fetch failed [%s]: %s", status_code, exc)
            return json.dumps({"status": "error", "error": f"github http error: {status_code}"})
        except requests.RequestException as exc:
            logger.warning("GitHub request failed: %s", exc)
            return json.dumps({"status": "error", "error": "github request failed"})

        include_info_b = _bool(include_info, default=False)
        findings = _annotate(files, checks)
        if not include_info_b:
            findings = [f for f in findings if f.get("severity") != "info"]

        limit = _safe_int(max_findings, 200, 1, 1000)
        findings = findings[:limit]

        report = {
            "status": "ok",
            "mode": review_mode,
            "repo": f"{owner_s}/{repo_s}",
            "pr_number": pr_num,
            "total_files": len(files),
            "total_findings": len(findings),
            "findings": findings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        hist_limit = _safe_int(api.get_setting("pr_review_history_limit", 100), 100, 10, 1000)
        _append_history(
            api,
            {
                "repo": report["repo"],
                "pr_number": pr_num,
                "total_files": report["total_files"],
                "total_findings": report["total_findings"],
                "generated_at": report["generated_at"],
            },
            hist_limit,
        )
        return json.dumps(report, ensure_ascii=False)

    def pr_review_history(limit: int = 25, **kwargs):
        _ = kwargs
        max_limit = _safe_int(limit, 25, 1, 200)
        rows = _load_history(api, max_limit)
        return json.dumps({"status": "ok", "entries": rows[-max_limit:]}, ensure_ascii=False)

    api.register_tool(
        {
            "name": "pr_review_ruleset_get",
            "description": "Get the active PR review regex ruleset.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "execute": pr_review_ruleset_get,
        }
    )

    api.register_tool(
        {
            "name": "pr_review_ruleset_set",
            "description": "Replace PR review regex ruleset checks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "checks": {
                        "type": "array",
                        "description": "List of checks with id, regex, and severity",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "regex": {"type": "string"},
                                "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                            },
                            "required": ["id", "regex"],
                        },
                    }
                },
                "required": ["checks"],
            },
            "execute": pr_review_ruleset_set,
        }
    )

    api.register_tool(
        {
            "name": "review_github_pr",
            "description": "Fetch PR files from GitHub and annotate likely issues via regex checks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub org/user"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "pr_number": {"type": "integer", "description": "Pull request number"},
                    "mode": {"type": "string", "enum": ["dry_run", "report"], "default": "dry_run"},
                    "include_info": {"type": "boolean", "default": False},
                    "github_token": {"type": "string", "description": "Optional GitHub token override"},
                    "max_findings": {"type": "integer", "default": 200},
                },
                "required": ["owner", "repo", "pr_number"],
            },
            "execute": review_github_pr,
        }
    )

    api.register_tool(
        {
            "name": "pr_review_history",
            "description": "Read recent PR review report summaries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 25},
                },
            },
            "execute": pr_review_history,
        }
    )

    api.register_page(
        {
            "id": "pr_review_annotator",
            "label": "PR Review",
            "icon": "git-pull-request",
            "section": "automation",
            "js_path": "pr_review_annotator.js",
        }
    )
