"""Responses API capability config + validation helpers.

Deny-by-default advanced OpenAI Responses features.
"""

from __future__ import annotations

from typing import Any

DEFAULT_RESPONSES_CAPABILITIES: dict[str, bool] = {
    "enable_responses_skills": False,
    "enable_hosted_shell": False,
    "enable_container_networking": False,
}


def normalize_responses_capabilities(raw: Any) -> dict[str, bool]:
    """Normalize and strictly validate responses capability toggles."""
    if raw is None:
        return dict(DEFAULT_RESPONSES_CAPABILITIES)
    if not isinstance(raw, dict):
        raise ValueError("responses_capabilities must be an object")

    out = dict(DEFAULT_RESPONSES_CAPABILITIES)
    for key in out:
        val = raw.get(key, out[key])
        if not isinstance(val, bool):
            raise ValueError(f"{key} must be a boolean")
        out[key] = val

    # Security guardrail: networking requires hosted shell explicitly enabled.
    if out["enable_container_networking"] and not out["enable_hosted_shell"]:
        raise ValueError("enable_container_networking requires enable_hosted_shell=true")

    return out


def get_responses_capabilities(cfg: dict[str, Any]) -> dict[str, bool]:
    """Read capabilities from config with safe fallback."""
    try:
        return normalize_responses_capabilities(cfg.get("responses_capabilities"))
    except Exception:
        return dict(DEFAULT_RESPONSES_CAPABILITIES)


def get_responses_capabilities_scope() -> str:
    """Contract helper for dashboard/routes: capabilities are global, not provider-local."""
    return "global"
