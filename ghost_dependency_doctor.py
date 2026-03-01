"""Dependency Doctor tools.

Provides lightweight runtime checks for optional Python package imports to
surface actionable remediation commands when environments are missing modules.
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, List


def _check_modules(modules: List[Dict[str, str]]) -> Dict[str, Any]:
    results: List[Dict[str, str]] = []
    missing: List[Dict[str, str]] = []

    for item in modules:
        name = str(item.get("name", "")).strip()
        install_name = str(item.get("install", name)).strip() or name
        if not name:
            continue

        try:
            importlib.import_module(name)
            results.append({"module": name, "status": "ok"})
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            entry = {
                "module": name,
                "status": "missing",
                "error": message,
                "install": f"pip install {install_name}",
            }
            results.append(entry)
            missing.append(entry)

    return {
        "ok": len(missing) == 0,
        "checked": len(results),
        "missing_count": len(missing),
        "results": results,
        "missing": missing,
        "summary": (
            "All checked Python modules are importable."
            if not missing
            else f"Missing {len(missing)} module(s): "
            + ", ".join(m["module"] for m in missing)
        ),
    }


def make_dependency_doctor_check():
    """Tool: check known optional dependencies for importability."""

    def _do(args: Dict[str, Any]):
        raw = args.get("modules") if isinstance(args, dict) else None

        default_modules = [
            {"name": "fastapi", "install": "fastapi"},
            {"name": "tensorflow", "install": "tensorflow"},
        ]

        modules: List[Dict[str, str]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    modules.append({
                        "name": str(item.get("name", "")).strip(),
                        "install": str(item.get("install", item.get("name", ""))).strip(),
                    })
                elif isinstance(item, str):
                    val = item.strip()
                    if val:
                        modules.append({"name": val, "install": val})

        if not modules:
            modules = default_modules

        return _check_modules(modules)

    return {
        "name": "dependency_doctor_check",
        "description": "Check whether key optional Python dependencies are importable and return install commands for missing modules.",
        "parameters": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "description": "Optional modules to check. Items may be strings or {name, install} objects.",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "install": {"type": "string"},
                                },
                                "required": ["name"],
                            },
                        ]
                    },
                }
            },
            "additionalProperties": False,
        },
        "execute": _do,
    }


def build_dependency_doctor_tools(_cfg=None):
    return [make_dependency_doctor_check()]
