"""Config payload normalization tools.

Single-responsibility module for building/validating dashboard config payloads.
"""

from __future__ import annotations

from typing import Any, Dict


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def normalize_dangerous_policy_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize dangerous command policy shape for dashboard save operations."""
    source = payload if isinstance(payload, dict) else {}
    policy = source.get("dangerous_command_policy")
    if not isinstance(policy, dict):
        policy = {}

    python_policy = policy.get("python") if isinstance(policy.get("python"), dict) else {}
    pip_policy = policy.get("pip") if isinstance(policy.get("pip"), dict) else {}

    return {
        "python": {
            "allow": _to_bool(python_policy.get("allow"), default=True),
            "require_workspace": _to_bool(python_policy.get("require_workspace"), default=False),
            "deny_flags": _to_str_list(python_policy.get("deny_flags")),
        },
        "pip": {
            "allow": _to_bool(pip_policy.get("allow"), default=True),
            "require_workspace": _to_bool(pip_policy.get("require_workspace"), default=False),
            "allow_subcommands": _to_str_list(pip_policy.get("allow_subcommands")),
        },
    }


def build_config_payload_tools(_cfg: Dict[str, Any] | None = None):
    """Tool builder placeholder for modular wiring consistency in ghost.py."""
    return []
