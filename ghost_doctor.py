from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class GhostDoctor:
    """Structured health checks with optional safe auto-fixes."""

    def __init__(self, config: Dict[str, Any], daemon_refs: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.daemon_refs = daemon_refs or {}
        self._fix_handlers: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def run(self) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = [
            self._check_provider_credentials(),
            self._check_cron_service(),
            self._check_browser_runtime(),
            self._check_sandbox_docker(),
            self._check_state_integrity_ready(),
            self._check_channel_security(),
        ]
        summary = self._summarize(checks)
        return {
            "ok": True,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": summary,
            "checks": checks,
        }

    def fix(self, check_ids: Optional[List[str]] = None, dry_run: bool = True) -> Dict[str, Any]:
        report = self.run()
        selected = set(check_ids or [])
        fixes: List[Dict[str, Any]] = []

        for check in report.get("checks", []):
            check_id = check.get("id")
            if check.get("status") == "ok" or not check.get("fix_available"):
                continue
            if selected and check_id not in selected:
                continue

            fix_id = check.get("fix_id")
            if not fix_id or fix_id not in self._fix_handlers:
                fixes.append({
                    "check_id": check_id,
                    "status": "skipped",
                    "message": "No registered fix handler",
                })
                continue

            if dry_run:
                fixes.append({
                    "check_id": check_id,
                    "status": "planned",
                    "message": f"Would run {fix_id}",
                })
                continue

            try:
                result = self._fix_handlers[fix_id]()
                fixes.append({
                    "check_id": check_id,
                    "status": "applied",
                    "result": result,
                })
            except Exception as exc:
                fixes.append({
                    "check_id": check_id,
                    "status": "failed",
                    "message": str(exc),
                })

        return {
            "ok": True,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "dry_run": bool(dry_run),
            "fixes": fixes,
            "post_check": self.run(),
        }

    def _check_provider_credentials(self) -> Dict[str, Any]:
        providers = self.config.get("providers", {}) if isinstance(self.config, dict) else {}
        enabled = [name for name, meta in providers.items() if isinstance(meta, dict) and meta.get("enabled")]
        missing = []
        for name in enabled:
            meta = providers.get(name) or {}
            has_key = bool(meta.get("api_key") or meta.get("key_env"))
            if not has_key and name != "ollama":
                missing.append(name)

        status = "ok" if not missing else "warn"
        self._fix_handlers["provider_defaults"] = self._fix_provider_defaults
        return {
            "id": "providers.credentials",
            "status": status,
            "severity": "medium" if missing else "none",
            "summary": "Provider credential presence",
            "details": {"enabled": enabled, "missing": missing},
            "fix_available": bool(missing),
            "fix_id": "provider_defaults" if missing else None,
        }

    def _check_cron_service(self) -> Dict[str, Any]:
        cron = self.daemon_refs.get("cron")
        running = bool(getattr(cron, "running", False)) if cron else False
        self._fix_handlers["cron_start"] = self._fix_cron_start
        return {
            "id": "cron.service",
            "status": "ok" if running else "warn",
            "severity": "high" if not running else "none",
            "summary": "Cron service running",
            "details": {"running": running},
            "fix_available": not running,
            "fix_id": "cron_start" if not running else None,
        }

    def _check_browser_runtime(self) -> Dict[str, Any]:
        browser_enabled = bool(self.config.get("enable_browser", True))
        self._fix_handlers["browser_enable"] = self._fix_browser_enable
        return {
            "id": "browser.runtime",
            "status": "ok" if browser_enabled else "warn",
            "severity": "low" if not browser_enabled else "none",
            "summary": "Browser automation toggle",
            "details": {"enable_browser": browser_enabled},
            "fix_available": not browser_enabled,
            "fix_id": "browser_enable" if not browser_enabled else None,
        }

    def _check_sandbox_docker(self) -> Dict[str, Any]:
        try:
            from ghost_sandbox import docker_available
            available = bool(docker_available())
        except Exception:
            available = False

        return {
            "id": "sandbox.docker",
            "status": "ok" if available else "warn",
            "severity": "medium" if not available else "none",
            "summary": "Docker availability for sandbox",
            "details": {"docker_available": available},
            "fix_available": False,
            "fix_id": None,
        }

    def _check_state_integrity_ready(self) -> Dict[str, Any]:
        home = Path.home() / ".ghost"
        required = [home / "config.json", home / "memory.db"]
        missing = [str(p) for p in required if not p.exists()]
        self._fix_handlers["create_missing_state"] = self._fix_create_missing_state
        return {
            "id": "state.files",
            "status": "ok" if not missing else "warn",
            "severity": "high" if missing else "none",
            "summary": "Critical state files present",
            "details": {"missing": missing},
            "fix_available": bool(missing),
            "fix_id": "create_missing_state" if missing else None,
        }

    def _fix_provider_defaults(self) -> Dict[str, Any]:
        return {"message": "Provider credential gaps require user key configuration"}

    def _fix_cron_start(self) -> Dict[str, Any]:
        cron = self.daemon_refs.get("cron")
        if not cron:
            return {"started": False, "reason": "cron ref unavailable"}
        if getattr(cron, "running", False):
            return {"started": False, "reason": "already running"}
        starter = getattr(cron, "start", None)
        if callable(starter):
            starter()
            return {"started": True}
        return {"started": False, "reason": "start method unavailable"}

    def _fix_browser_enable(self) -> Dict[str, Any]:
        self.config["enable_browser"] = True
        return {"enable_browser": True}

    def _check_channel_security(self) -> Dict[str, Any]:
        inbound_enabled = self.config.get("channel_inbound_enabled", False)
        dm_policy = self.config.get("channel_dm_policy", "open")
        allowed_senders = self.config.get("channel_allowed_senders", [])
        
        # Only check if channels are actually enabled
        if not inbound_enabled:
            return {
                "id": "channel.security",
                "status": "ok",
                "severity": "none",
                "summary": "Channel security (inbound disabled)",
                "details": {"inbound_enabled": False},
                "fix_available": False,
                "fix_id": None,
            }
        
        insecure_config = (dm_policy == "open" and not allowed_senders)
        self._fix_handlers["channel_security_lockdown"] = self._fix_channel_security_lockdown
        
        return {
            "id": "channel.security",
            "status": "warn" if insecure_config else "ok",
            "severity": "high" if insecure_config else "none",
            "summary": "Channel DM policy security",
            "details": {
                "inbound_enabled": True,
                "dm_policy": dm_policy,
                "allowed_senders_count": len(allowed_senders),
            },
            "fix_available": insecure_config,
            "fix_id": "channel_security_lockdown" if insecure_config else None,
        }
    
    def _fix_channel_security_lockdown(self) -> Dict[str, Any]:
        """Safe fix: Change from 'open' to 'allowlist' mode when no senders configured."""
        from ghost import load_config, save_config
        cfg = load_config()
        cfg["channel_dm_policy"] = "allowlist"
        save_config(cfg)
        return {"channel_dm_policy": "allowlist", "note": "Set to allowlist mode. Add trusted senders to channel_allowed_senders."}

    def _fix_create_missing_state(self) -> Dict[str, Any]:
        home = Path.home() / ".ghost"
        home.mkdir(parents=True, exist_ok=True)
        cfg = home / "config.json"
        mem = home / "memory.db"
        created: List[str] = []
        if not cfg.exists():
            cfg.write_text("{}", encoding="utf-8")
            created.append(str(cfg))
        if not mem.exists():
            mem.touch()
            created.append(str(mem))
        return {"created": created}

    @staticmethod
    def _summarize(checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts = {"ok": 0, "warn": 0, "fail": 0}
        for c in checks:
            status = c.get("status", "warn")
            counts[status] = counts.get(status, 0) + 1
        return counts


def build_doctor_tools(config: Dict[str, Any], daemon_refs: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    doctor = GhostDoctor(config=config, daemon_refs=daemon_refs)

    def _validate_check_ids(raw: Any) -> List[str]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            if isinstance(item, str) and 0 < len(item) <= 120:
                out.append(item)
        return out

    def _doctor_run(_=None) -> Dict[str, Any]:
        return doctor.run()

    def _doctor_fix(args: Dict[str, Any]) -> Dict[str, Any]:
        args = args or {}
        check_ids = _validate_check_ids(args.get("check_ids"))
        dry_run = bool(args.get("dry_run", True))
        return doctor.fix(check_ids=check_ids, dry_run=dry_run)

    return [
        {
            "name": "doctor_run",
            "description": "Run structured Ghost health checks and return findings.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "execute": _doctor_run,
        },
        {
            "name": "doctor_fix",
            "description": "Apply safe doctor auto-fixes, optionally in dry-run mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subset of check IDs to fix",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, plan fixes without applying",
                        "default": True,
                    },
                },
                "additionalProperties": False,
            },
            "execute": _doctor_fix,
        },
    ]