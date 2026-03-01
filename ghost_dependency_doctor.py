"""Dependency Doctor tools.

Provides lightweight runtime checks for optional Python package imports to
surface actionable remediation commands when environments are missing modules.
Also provides auto-install capability for missing dependencies.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
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


def make_dependency_doctor_install():
    """Tool: install missing Python dependencies via pip."""

    def _do(args: Dict[str, Any]):
        modules = args.get("modules") if isinstance(args, dict) else None
        auto_install = args.get("auto_install", False) if isinstance(args, dict) else False

        default_modules = [
            {"name": "fastapi", "install": "fastapi"},
            {"name": "tensorflow", "install": "tensorflow"},
        ]

        modules_to_check: List[Dict[str, str]] = []
        if isinstance(modules, list):
            for item in modules:
                if isinstance(item, dict):
                    modules_to_check.append({
                        "name": str(item.get("name", "")).strip(),
                        "install": str(item.get("install", item.get("name", ""))).strip(),
                    })
                elif isinstance(item, str):
                    val = item.strip()
                    if val:
                        modules_to_check.append({"name": val, "install": val})

        if not modules_to_check:
            modules_to_check = default_modules

        # Check which modules are missing
        check_result = _check_modules(modules_to_check)
        missing = check_result.get("missing", [])

        if not missing:
            return "All requested modules are already installed."

        if not auto_install:
            # Just return the install commands without installing
            commands = [m["install"] for m in missing]
            return {
                "status": "missing",
                "message": f"Found {len(missing)} missing module(s). Set auto_install=true to install.",
                "missing": [m["module"] for m in missing],
                "install_commands": commands,
            }

        # Actually install missing modules
        installed = []
        failed = []

        for item in missing:
            module_name = item["module"]
            install_cmd = item.get("install", f"pip install {module_name}")
            # Extract package name from install command
            pkg_name = install_cmd.replace("pip install ", "").strip()

            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg_name],
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout for large packages like tensorflow
                )
                if result.returncode == 0:
                    # Verify the import works now
                    try:
                        importlib.import_module(module_name)
                        installed.append(module_name)
                    except Exception as import_exc:
                        failed.append({
                            "module": module_name,
                            "error": f"Installed but import failed: {import_exc}",
                        })
                else:
                    failed.append({
                        "module": module_name,
                        "error": result.stderr or "Installation failed",
                    })
            except Exception as exc:
                failed.append({
                    "module": module_name,
                    "error": f"Installation error: {exc}",
                })

        if installed and not failed:
            return {
                "status": "success",
                "message": f"Successfully installed {len(installed)} module(s): {', '.join(installed)}",
                "installed": installed,
            }
        elif installed and failed:
            return {
                "status": "partial",
                "message": f"Installed {len(installed)} module(s), {len(failed)} failed",
                "installed": installed,
                "failed": failed,
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to install {len(failed)} module(s)",
                "failed": failed,
            }

    return {
        "name": "dependency_doctor_install",
        "description": "Check and optionally install missing Python dependencies. When auto_install=true, actually runs pip install for missing modules (e.g., tensorflow).",
        "parameters": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "description": "Optional modules to check/install. Items may be strings or {name, install} objects.",
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
                },
                "auto_install": {
                    "type": "boolean",
                    "description": "If true, actually install missing packages via pip. If false, just return install commands.",
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
        "execute": _do,
    }


def build_dependency_doctor_tools(_cfg=None):
    return [make_dependency_doctor_check(), make_dependency_doctor_install()]
