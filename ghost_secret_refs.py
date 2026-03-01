"""
Secret reference helpers for secure credential indirection.

Provides:
- secret-key detection for config sanitization
- ${AUTH_PROFILE:provider.field} reference resolution
- migration helper for legacy plaintext config keys into auth profile store
"""

from __future__ import annotations

import re
from typing import Any

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password)", re.IGNORECASE)
_SECRET_REF_RE = re.compile(r"^\$\{AUTH_PROFILE:([a-zA-Z0-9_.:-]+)\}$")


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(str(key or "")))


def redact_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-3:]}"


def sanitize_config_for_output(cfg: dict) -> dict:
    out = {}
    for k, v in (cfg or {}).items():
        if is_secret_key(k):
            out[k] = redact_value(v)
        else:
            out[k] = v
    return out


def resolve_secret_ref(value: str, auth_store) -> str:
    if not isinstance(value, str):
        return ""
    m = _SECRET_REF_RE.match(value.strip())
    if not m:
        return value
    ref = m.group(1)
    # format: provider.field (default profile)
    if "." not in ref:
        return ""
    provider, field = ref.split(".", 1)
    profile = auth_store.get_provider_profile(provider)
    if not profile:
        return ""
    return str(profile.get(field, "") or "")


def migrate_config_secrets(cfg: dict, auth_store) -> tuple[dict, bool]:
    """Move plaintext config secrets into auth profile refs.

    Current migration scope intentionally narrow/safe:
    - cfg['api_key'] -> openrouter default profile key + reference
    """
    changed = False
    new_cfg = dict(cfg or {})

    raw_api = new_cfg.get("api_key", "")
    if isinstance(raw_api, str) and raw_api and not raw_api.startswith("${AUTH_PROFILE:"):
        auth_store.set_api_key("openrouter", raw_api, name="default")
        new_cfg["api_key"] = "${AUTH_PROFILE:openrouter.key}"
        changed = True

    return new_cfg, changed
