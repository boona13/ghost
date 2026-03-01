"""Setup provider metadata helpers for dashboard wizard and tooling.

Centralizes provider presentation metadata used by setup APIs and tools so
frontend/backed stay aligned when providers are added.
"""

from __future__ import annotations

from typing import Any

from ghost_providers import get_provider, list_providers


_PROVIDER_UI_META: dict[str, dict[str, Any]] = {
    "openrouter": {
        "icon": "🌐",
        "badge": "Recommended",
        "badgeColor": "purple",
        "keyPlaceholder": "sk-or-v1-...",
    },
    "openai-codex": {
        "icon": "⚡",
        "badge": "Free w/ subscription",
        "badgeColor": "green",
        "authType": "oauth",
    },
    "openai": {
        "icon": "🤖",
        "badge": "Paid",
        "badgeColor": "blue",
        "keyPlaceholder": "sk-...",
    },
    "anthropic": {
        "icon": "🧠",
        "badge": "Paid",
        "badgeColor": "yellow",
        "keyPlaceholder": "sk-ant-...",
    },
    "google": {
        "icon": "💎",
        "badge": "Free tier",
        "badgeColor": "green",
        "keyPlaceholder": "AIza...",
    },
    "xai": {
        "icon": "🚀",
        "badge": "Paid",
        "badgeColor": "blue",
        "keyPlaceholder": "xai-...",
    },
    "deepseek": {
        "icon": "🔍",
        "badge": "Paid",
        "badgeColor": "blue",
        "keyPlaceholder": "sk-...",
    },
    "ollama": {
        "icon": "🦙",
        "badge": "Free / Local",
        "badgeColor": "green",
        "authType": "none",
    },
}


def build_setup_provider_catalog() -> list[dict[str, Any]]:
    """Return provider metadata for setup UI/API consumption."""
    catalog: list[dict[str, Any]] = []
    for prov in list_providers():
        pid = prov.get("id")
        meta = dict(_PROVIDER_UI_META.get(pid, {}))
        provider_obj = get_provider(pid)
        if provider_obj:
            meta.setdefault("authType", provider_obj.auth_type)
            meta.setdefault("desc", provider_obj.description)
        catalog.append({"id": pid, **meta})
    return catalog


def build_setup_provider_tools(_daemon=None):
    """Expose setup provider catalog to tool loop for diagnostics/debugging."""

    def _get_setup_provider_catalog(_: dict[str, Any] | None = None):
        return {"providers": build_setup_provider_catalog()}

    return [{
        "name": "get_setup_provider_catalog",
        "description": "Return setup wizard provider catalog metadata",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "execute": _get_setup_provider_catalog,
    }]
