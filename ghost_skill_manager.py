"""Managed skill installer and preflight validator for SKILL.md packs."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ghost_skills import SKILLS_USER_DIR


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    field: Optional[str] = None
    fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "fix": self.fix,
        }


class SkillManager:
    """Install/validate/preflight operations for skills."""

    def __init__(self, config_loader, config_saver):
        self._load_config = config_loader
        self._save_config = config_saver
        self.user_dir = SKILLS_USER_DIR
        self.user_dir.mkdir(parents=True, exist_ok=True)

    def enabled(self) -> bool:
        cfg = self._load_config() or {}
        return bool(cfg.get("enable_skill_manager", True))

    def _safe_dir(self, rel_path: str) -> Path:
        p = (self.user_dir / rel_path).resolve()
        root = self.user_dir.resolve()
        if root not in p.parents and p != root:
            raise ValueError("Path traversal denied")
        return p

    def parse_skill_text(self, text: str) -> Dict[str, Any]:
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', text, re.DOTALL)
        if not fm_match:
            return {"frontmatter": {}, "body": text}
        try:
            fm = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        return {"frontmatter": fm, "body": fm_match.group(2)}

    def validate_skill_text(self, text: str) -> Dict[str, Any]:
        parsed = self.parse_skill_text(text)
        fm = parsed["frontmatter"]
        issues: List[ValidationIssue] = []

        if not fm:
            issues.append(ValidationIssue("frontmatter_missing", "error", "Missing or invalid YAML frontmatter", fix="Add --- YAML --- block at top"))
            return self._pack_validation(fm, issues)

        name = fm.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(ValidationIssue("name_required", "error", "Field 'name' is required and must be a non-empty string", field="name"))

        triggers = fm.get("triggers")
        if not isinstance(triggers, list) or not triggers:
            issues.append(ValidationIssue("triggers_required", "error", "Field 'triggers' must be a non-empty list of strings", field="triggers"))
        else:
            bad = [t for t in triggers if not isinstance(t, str) or not t.strip()]
            if bad:
                issues.append(ValidationIssue("triggers_invalid", "error", "All triggers must be non-empty strings", field="triggers"))

        tools = fm.get("tools", [])
        if tools and (not isinstance(tools, list) or any(not isinstance(t, str) for t in tools)):
            issues.append(ValidationIssue("tools_invalid", "error", "Field 'tools' must be a list of strings", field="tools"))

        requires = fm.get("requires", {})
        if requires and not isinstance(requires, dict):
            issues.append(ValidationIssue("requires_invalid", "error", "Field 'requires' must be an object", field="requires"))

        priority = fm.get("priority", 0)
        if not isinstance(priority, (int, float)):
            issues.append(ValidationIssue("priority_type", "warning", "Field 'priority' should be numeric", field="priority", fix="Use an integer like 0, 5, 10"))

        risk = "low"
        if isinstance(tools, list):
            high_risk_tools = {"shell_exec", "browser", "code_run", "sandbox_exec"}
            if any(t in high_risk_tools for t in tools):
                risk = "high"
            elif tools:
                risk = "medium"

        return self._pack_validation(fm, issues, risk=risk)

    def _pack_validation(self, fm: Dict[str, Any], issues: List[ValidationIssue], risk: str = "low") -> Dict[str, Any]:
        severity_rank = {"error": 3, "warning": 2, "info": 1}
        top = "ok"
        if any(i.severity == "error" for i in issues):
            top = "error"
        elif any(i.severity == "warning" for i in issues):
            top = "warning"
        return {
            "ok": top != "error",
            "status": top,
            "risk": risk,
            "frontmatter": fm,
            "issues": [i.to_dict() for i in issues],
        }

    def preflight(self, text: str) -> Dict[str, Any]:
        report = self.validate_skill_text(text)
        fm = report.get("frontmatter", {}) or {}
        requires = fm.get("requires", {}) if isinstance(fm.get("requires", {}), dict) else {}

        bins = requires.get("bins", []) if isinstance(requires.get("bins", []), list) else []
        env = requires.get("env", []) if isinstance(requires.get("env", []), list) else []
        flags = requires.get("config_flags", []) if isinstance(requires.get("config_flags", []), list) else []

        missing_bins = [b for b in bins if not shutil.which(str(b))]
        missing_env = [e for e in env if not os.environ.get(str(e))]

        cfg = self._load_config() or {}
        missing_flags = [f for f in flags if not cfg.get(str(f), False)]

        eligible = report.get("ok", False) and not missing_bins and not missing_env and not missing_flags
        report["preflight"] = {
            "eligible": eligible,
            "requires": {
                "bins": bins,
                "env": env,
                "config_flags": flags,
            },
            "missing": {
                "bins": missing_bins,
                "env": missing_env,
                "config_flags": missing_flags,
            },
        }
        return report

    def install_local(self, relative_name: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
        if not isinstance(relative_name, str) or not relative_name.strip():
            raise ValueError("relative_name is required")
        safe_name = relative_name.strip().strip("/")
        if ".." in safe_name:
            raise ValueError("Invalid relative_name")

        target_dir = self._safe_dir(safe_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"

        if target_file.exists() and not overwrite:
            raise ValueError("Skill already exists; set overwrite=true")

        report = self.preflight(content)
        if not report.get("ok"):
            return {"installed": False, "report": report}

        target_file.write_text(content)
        return {
            "installed": True,
            "path": str(target_file),
            "report": report,
        }


def _disabled_set(load_config):
    cfg = load_config() or {}
    return set(cfg.get("disabled_skills", [])), cfg


def make_skills_preflight(manager: SkillManager):
    def execute(text: str):
        if not manager.enabled():
            return {"error": "Skill manager disabled by config"}
        return manager.preflight(text or "")

    return {
        "name": "skills_preflight",
        "description": "Validate SKILL.md content and run dependency preflight checks.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"]
        },
        "execute": execute,
    }


def make_skills_validate(manager: SkillManager):
    def execute(text: str):
        if not manager.enabled():
            return {"error": "Skill manager disabled by config"}
        return manager.validate_skill_text(text or "")

    return {
        "name": "skills_validate",
        "description": "Validate SKILL.md frontmatter schema and risk level.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"]
        },
        "execute": execute,
    }


def make_skills_install_local(manager: SkillManager):
    def execute(relative_name: str, content: str, overwrite: bool = False):
        if not manager.enabled():
            return {"error": "Skill manager disabled by config"}
        return manager.install_local(relative_name, content, overwrite=bool(overwrite))

    return {
        "name": "skills_install_local",
        "description": "Install a local skill directory with SKILL.md after validation/preflight.",
        "parameters": {
            "type": "object",
            "properties": {
                "relative_name": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"}
            },
            "required": ["relative_name", "content"]
        },
        "execute": execute,
    }


def make_skills_enable(manager: SkillManager):
    def execute(name: str):
        if not manager.enabled():
            return {"error": "Skill manager disabled by config"}
        disabled, cfg = _disabled_set(manager._load_config)
        disabled.discard(name)
        cfg["disabled_skills"] = sorted(disabled)
        manager._save_config(cfg)
        return {"ok": True, "name": name, "enabled": True}

    return {
        "name": "skills_enable",
        "description": "Enable a disabled skill by name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        "execute": execute,
    }


def make_skills_disable(manager: SkillManager):
    def execute(name: str):
        if not manager.enabled():
            return {"error": "Skill manager disabled by config"}
        disabled, cfg = _disabled_set(manager._load_config)
        disabled.add(name)
        cfg["disabled_skills"] = sorted(disabled)
        manager._save_config(cfg)
        return {"ok": True, "name": name, "enabled": False}

    return {
        "name": "skills_disable",
        "description": "Disable a skill by name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        },
        "execute": execute,
    }


def build_skill_manager_tools(config_loader, config_saver):
    manager = SkillManager(config_loader, config_saver)
    return [
        make_skills_preflight(manager),
        make_skills_validate(manager),
        make_skills_install_local(manager),
        make_skills_enable(manager),
        make_skills_disable(manager),
    ]
