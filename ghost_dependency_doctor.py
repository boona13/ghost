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


def _check_modules(modules: List[Dict[str, Any]]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    for item in modules:
        name = str(item.get("name", "")).strip()
        install_name = str(item.get("install", name)).strip() or name
        optional_heavy = bool(item.get("optional_heavy", False))
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
                "optional_heavy": optional_heavy,
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
            {"name": "tensorflow", "install": "tensorflow", "optional_heavy": True},
        ]

        modules: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    modules.append({
                        "name": str(item.get("name", "")).strip(),
                        "install": str(item.get("install", item.get("name", ""))).strip(),
                        "optional_heavy": bool(item.get("optional_heavy", False)),
                    })
                elif isinstance(item, str):
                    val = item.strip()
                    if val:
                        modules.append({"name": val, "install": val, "optional_heavy": False})

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

        modules_to_check: List[Dict[str, Any]] = []
        if isinstance(modules, list):
            for item in modules:
                if isinstance(item, dict):
                    modules_to_check.append({
                        "name": str(item.get("name", "")).strip(),
                        "install": str(item.get("install", item.get("name", ""))).strip(),
                        "optional_heavy": bool(item.get("optional_heavy", False)),
                    })
                elif isinstance(item, str):
                    val = item.strip()
                    if val:
                        modules_to_check.append({"name": val, "install": val, "optional_heavy": False})

        if not modules_to_check:
            return {
                "status": "error",
                "message": "No modules specified. Provide a modules list to check/install.",
            }

        # Check which modules are missing
        check_result = _check_modules(modules_to_check)
        missing = check_result.get("missing", [])

        if not missing:
            return {
                "status": "already_installed",
                "message": "All requested modules are already installed.",
                "modules": [m["name"] for m in modules_to_check],
            }

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
        skipped_heavy = []
        
        # Get timeout from args or use default
        timeout = args.get("timeout", 300) if isinstance(args, dict) else 300

        for item in missing:
            # Skip auto-install for heavy optional dependencies (e.g., tensorflow ~500MB)
            if item.get("optional_heavy", False):
                skipped_heavy.append({
                    "module": item["module"],
                    "reason": "Large optional dependency - manual install recommended",
                    "install": item.get("install", f"pip install {item['module']}"),
                })
                continue
            module_name = item["module"]
            # install field is the package spec (e.g., "tensorflow", "package[extra]==1.0")
            pkg_spec = item.get("install", module_name)

            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg_spec],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode == 0:
                    # Verify the import works now
                    # Clear import caches to recognize newly installed packages
                    importlib.invalidate_caches()
                    # Remove cached failed import attempts if any
                    if module_name in sys.modules and sys.modules[module_name] is None:
                        del sys.modules[module_name]
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

        # Build response based on results
        if skipped_heavy and not installed and not failed:
            return {
                "status": "skipped_heavy",
                "message": f"Skipped {len(skipped_heavy)} heavy optional dependency/ies (manual install recommended)",
                "skipped": skipped_heavy,
            }
        
        response = {
            "status": "success" if installed and not failed else ("partial" if installed else "error"),
            "message": "",
        }
        
        if installed:
            response["message"] = f"Successfully installed {len(installed)} module(s): {', '.join(installed)}"
            response["installed"] = installed
        if failed:
            response["message"] = (response.get("message", "") + f" Failed to install {len(failed)} module(s).").strip()
            response["failed"] = failed
        if skipped_heavy:
            response["message"] = (response.get("message", "") + f" Skipped {len(skipped_heavy)} heavy optional dependency/ies.").strip()
            response["skipped_heavy"] = skipped_heavy
            
        return response

    return {
        "name": "dependency_doctor_install",
        "description": "Check and optionally install missing Python dependencies. When auto_install=true, actually runs pip install for missing modules (e.g., tensorflow).",
        "parameters": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "description": "Modules to check/install. Items may be strings or {name, install, optional_heavy} objects. optional_heavy=true skips auto-install (for large packages like tensorflow).",
                    "items": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "install": {"type": "string", "description": "Package spec (e.g., 'tensorflow==2.0', 'package[extra]'). Not a shell command."},
                                    "optional_heavy": {"type": "boolean", "description": "If true, skip auto-install for this large dependency. Manual install recommended.", "default": False},
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
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds for pip install operations. Default 300 (5 minutes).",
                    "default": 300,
                },
            },
            "additionalProperties": False,
        },
        "execute": _do,
    }


def build_dependency_doctor_tools(_cfg=None):
    return [make_dependency_doctor_check(), make_dependency_doctor_install()]
