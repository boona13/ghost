"""
Pip utilities — safe package installation with blacklisting.

Adapted from ComfyUI-Manager's manager_util.py and manager_core.py.
Prevents accidental uninstall/downgrade of torch, torchvision, etc.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("ghost.comfy_manager.pip")

PIP_BLACKLIST: set[str] = {
    "torch", "torchaudio", "torchsde", "torchvision",
}

PIP_DOWNGRADE_BLACKLIST: set[str] = {
    "torch", "torchaudio", "torchsde", "torchvision",
    "transformers", "safetensors", "kornia",
}

PIP_OVERRIDES: dict[str, str] = {}

_installed_cache: dict[str, str] | None = None


@lru_cache(maxsize=2)
def get_pip_cmd() -> list[str]:
    """Return the base pip command list, falling back to uv if needed."""
    embedded = "python_embeded" in sys.executable
    base = [sys.executable] + (["-s"] if embedded else [])

    try:
        subprocess.check_output(
            base + ["-m", "pip", "--version"],
            stderr=subprocess.DEVNULL, timeout=5,
        )
        return base + ["-m", "pip"]
    except Exception:
        pass

    import shutil
    try:
        subprocess.check_output(
            base + ["-m", "uv", "--version"],
            stderr=subprocess.DEVNULL, timeout=5,
        )
        return base + ["-m", "uv", "pip"]
    except Exception:
        pass

    if shutil.which("uv"):
        return ["uv", "pip"]

    log.error("Neither pip nor uv are available")
    return base + ["-m", "pip"]


def make_pip_cmd(args: list[str]) -> list[str]:
    """Build a complete pip command: base + args."""
    return get_pip_cmd() + args


def get_installed_packages(renew: bool = False) -> dict[str, str]:
    """Return {normalized_name: version} of all installed pip packages."""
    global _installed_cache
    if not renew and _installed_cache is not None:
        return _installed_cache

    try:
        result = subprocess.check_output(
            make_pip_cmd(["list", "--format=columns"]),
            universal_newlines=True, timeout=30,
        )
        packages: dict[str, str] = {}
        for line in result.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] != "Package" and not parts[0].startswith("-"):
                packages[parts[0].lower().replace("-", "_")] = parts[1]
        _installed_cache = packages
        return packages
    except Exception:
        log.warning("Failed to list installed packages")
        return _installed_cache or {}


def is_blacklisted(name: str) -> bool:
    """Check if a package name is blacklisted from install/downgrade.

    Adapted from ComfyUI-Manager's is_blacklisted().
    """
    name = name.strip()
    pattern = r"([^<>!~=]+)([<>!~=]=?)([^ ]*)"
    match = re.search(pattern, name)

    pkg_name = match.group(1) if match else name

    if pkg_name in PIP_BLACKLIST:
        return True

    if pkg_name in PIP_DOWNGRADE_BLACKLIST:
        pips = get_installed_packages()
        if match is None:
            return pkg_name in pips
        if match.group(2) in ("<=", "==", "<", "~="):
            if pkg_name in pips:
                from ghost_comfy_manager._version import StrictVersion
                try:
                    if StrictVersion(pips[pkg_name]) >= StrictVersion(match.group(3)):
                        return True
                except Exception:
                    pass

    return False


def remap_pip_package(pkg: str) -> str:
    """Apply pip overrides/remappings."""
    if pkg in PIP_OVERRIDES:
        remapped = PIP_OVERRIDES[pkg]
        log.info("Pip package '%s' remapped to '%s'", pkg, remapped)
        return remapped
    return pkg


def execute_install_script(
    repo_path: Path | str,
    no_deps: bool = False,
    timeout: int = 300,
) -> bool:
    """Run requirements.txt and install.py for a custom node package.

    Adapted from ComfyUI-Manager's execute_install_script().
    Respects the pip blacklist and handles --index-url in requirements.
    """
    repo_path = Path(repo_path)
    requirements_path = repo_path / "requirements.txt"
    install_script = repo_path / "install.py"

    success = True

    if requirements_path.exists() and not no_deps:
        log.info("Installing pip dependencies from %s", requirements_path)
        for line in requirements_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "#" in line:
                line = line.split("#")[0].strip()

            package_name = remap_pip_package(line)
            if not package_name:
                continue

            if is_blacklisted(package_name):
                log.info("Skipping blacklisted package: %s", package_name)
                continue

            if "--index-url" in package_name:
                parts = package_name.split("--index-url")
                cmd = make_pip_cmd([
                    "install", parts[0].strip(),
                    "--index-url", parts[1].strip(),
                ])
            else:
                cmd = make_pip_cmd(["install", package_name])

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=timeout,
                    cwd=str(repo_path),
                )
                if result.returncode != 0:
                    log.warning(
                        "pip install failed for '%s': %s",
                        package_name, result.stderr[:300],
                    )
                    success = False
            except subprocess.TimeoutExpired:
                log.error("pip install timed out for '%s'", package_name)
                success = False
            except Exception as exc:
                log.error("pip install error for '%s': %s", package_name, exc)
                success = False

    if install_script.exists():
        log.info("Running install.py for %s", repo_path.name)
        try:
            result = subprocess.run(
                [sys.executable, "install.py"],
                capture_output=True, text=True, timeout=timeout,
                cwd=str(repo_path),
                env={**os.environ, "COMFYUI_PATH": "", "COMFYUI_FOLDERS_BASE_PATH": ""},
            )
            if result.returncode != 0:
                log.warning(
                    "install.py failed for %s: %s",
                    repo_path.name, result.stderr[:500],
                )
                success = False
        except subprocess.TimeoutExpired:
            log.error("install.py timed out for %s", repo_path.name)
            success = False
        except Exception as exc:
            log.error("install.py error for %s: %s", repo_path.name, exc)
            success = False

    return success
