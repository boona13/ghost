from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


ALLOWED_STEPS = {"preflight_scan", "plan", "apply_safe_fixes", "recheck", "summary"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "none"}


class SetupDoctorOrchestrator:
    """High-level setup doctor workflow built on top of GhostDoctor."""

    def __init__(self, config: Dict[str, Any], daemon_refs: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.daemon_refs = daemon_refs or {}

    def run(self, dry_run: bool = True) -> Dict[str, Any]:
        preflight = self._run_doctor()
        plan = self._build_plan(preflight)

        applied = []
        if not dry_run and plan.get("fixable_count", 0) > 0:
            applied = self._apply_safe_fixes(preflight)

        recheck = self._run_doctor()
        summary = self._build_summary(preflight, recheck, plan, applied, dry_run)

        return {
            "ok": True,
            "timestamp": self._now(),
            "dry_run": bool(dry_run),
            "steps": {
                "preflight_scan": preflight,
                "plan": plan,
                "apply_safe_fixes": {"applied": applied, "attempted": not dry_run},
                "recheck": recheck,
                "summary": summary,
            },
            "status": self._normalize_status(recheck),
        }

    def status(self) -> Dict[str, Any]:
        report = self._run_doctor()
        return {
            "ok": True,
            "timestamp": self._now(),
            "status": self._normalize_status(report),
        }

    def _run_doctor(self) -> Dict[str, Any]:
        from ghost_doctor import GhostDoctor

        doctor = GhostDoctor(self.config, daemon_refs=self.daemon_refs)
        return doctor.run()

    def _apply_safe_fixes(self, preflight: Dict[str, Any]) -> List[Dict[str, Any]]:
        from ghost_doctor import GhostDoctor

        fixable = [
            c.get("id") for c in preflight.get("checks", [])
            if c.get("status") != "ok" and c.get("fix_available")
        ]
        if not fixable:
            return []

        doctor = GhostDoctor(self.config, daemon_refs=self.daemon_refs)
        result = doctor.fix(check_ids=fixable, dry_run=False)
        return result.get("fixes", []) if isinstance(result, dict) else []

    def _build_plan(self, report: Dict[str, Any]) -> Dict[str, Any]:
        issues = [c for c in report.get("checks", []) if c.get("status") != "ok"]
        fixable = [c for c in issues if c.get("fix_available")]
        non_fixable = [c for c in issues if not c.get("fix_available")]

        return {
            "issue_count": len(issues),
            "fixable_count": len(fixable),
            "manual_count": len(non_fixable),
            "fixes": [
                {
                    "check_id": c.get("id"),
                    "severity": c.get("severity", "low"),
                    "summary": c.get("summary", ""),
                }
                for c in fixable
            ],
            "manual_actions": [
                {
                    "check_id": c.get("id"),
                    "severity": c.get("severity", "low"),
                    "summary": c.get("summary", ""),
                }
                for c in non_fixable
            ],
        }

    def _build_summary(
        self,
        preflight: Dict[str, Any],
        recheck: Dict[str, Any],
        plan: Dict[str, Any],
        applied: List[Dict[str, Any]],
        dry_run: bool,
    ) -> Dict[str, Any]:
        before = self._normalize_status(preflight)
        after = self._normalize_status(recheck)

        return {
            "mode": "dry_run" if dry_run else "apply",
            "issues_before": before.get("issue_count", 0),
            "issues_after": after.get("issue_count", 0),
            "fixable_before": plan.get("fixable_count", 0),
            "applied_count": len([f for f in applied if f.get("status") == "applied"]),
            "failed_count": len([f for f in applied if f.get("status") == "failed"]),
            "highest_severity_before": before.get("highest_severity", "none"),
            "highest_severity_after": after.get("highest_severity", "none"),
        }

    def _normalize_status(self, report: Dict[str, Any]) -> Dict[str, Any]:
        checks = report.get("checks", []) if isinstance(report, dict) else []
        buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        fixable = 0
        manual = 0

        for check in checks:
            if check.get("status") == "ok":
                continue
            sev = str(check.get("severity", "low")).lower()
            if sev not in ALLOWED_SEVERITIES:
                sev = "low"
            if sev in buckets:
                buckets[sev] += 1
            if check.get("fix_available"):
                fixable += 1
            else:
                manual += 1

        issue_count = sum(buckets.values())
        highest = "none"
        for sev in ("critical", "high", "medium", "low"):
            if buckets[sev] > 0:
                highest = sev
                break

        return {
            "issue_count": issue_count,
            "highest_severity": highest,
            "severity_buckets": buckets,
            "fixable_count": fixable,
            "manual_count": manual,
            "has_blockers": highest in {"critical", "high"},
        }

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat() + "Z"


def _build_orchestrator(config: Dict[str, Any], daemon_refs: Dict[str, Any]) -> SetupDoctorOrchestrator:
    return SetupDoctorOrchestrator(config=config, daemon_refs=daemon_refs)


def make_setup_doctor_status(config: Dict[str, Any], daemon_refs: Dict[str, Any]) -> Dict[str, Any]:
    def execute() -> Dict[str, Any]:
        orchestrator = _build_orchestrator(config, daemon_refs)
        return orchestrator.status()

    return {
        "name": "setup_doctor_status",
        "description": "Get normalized setup doctor status with severity and blockers.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "execute": execute,
    }


def make_setup_doctor_run(config: Dict[str, Any], daemon_refs: Dict[str, Any]) -> Dict[str, Any]:
    def execute(dry_run: bool = True, steps: Optional[List[str]] = None) -> Dict[str, Any]:
        if not isinstance(dry_run, bool):
            return {"ok": False, "error": "dry_run must be boolean"}
        if steps is not None:
            if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
                return {"ok": False, "error": "steps must be a list of strings"}
            invalid = [s for s in steps if s not in ALLOWED_STEPS]
            if invalid:
                return {"ok": False, "error": f"Invalid steps: {', '.join(invalid)}"}

        orchestrator = _build_orchestrator(config, daemon_refs)
        result = orchestrator.run(dry_run=dry_run)

        if steps:
            result["steps"] = {k: v for k, v in result.get("steps", {}).items() if k in set(steps)}
        return result

    return {
        "name": "setup_doctor_run",
        "description": "Run setup doctor orchestration (preflight, plan, optional safe fixes, recheck).",
        "parameters": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": True},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional subset of steps to return",
                },
            },
            "required": [],
        },
        "execute": execute,
    }


def make_setup_doctor_fix_all(config: Dict[str, Any], daemon_refs: Dict[str, Any]) -> Dict[str, Any]:
    def execute(confirm: bool = False) -> Dict[str, Any]:
        if confirm is not True:
            return {"ok": False, "error": "confirm=true is required to apply fixes"}
        orchestrator = _build_orchestrator(config, daemon_refs)
        return orchestrator.run(dry_run=False)

    return {
        "name": "setup_doctor_fix_all",
        "description": "Apply all safe auto-fixes from setup doctor and recheck.",
        "parameters": {
            "type": "object",
            "properties": {
                "confirm": {"type": "boolean", "description": "Must be true to apply fixes"}
            },
            "required": ["confirm"],
        },
        "execute": execute,
    }


def build_setup_doctor_tools(config: Dict[str, Any], daemon_refs: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        make_setup_doctor_status(config, daemon_refs),
        make_setup_doctor_run(config, daemon_refs),
        make_setup_doctor_fix_all(config, daemon_refs),
    ]
