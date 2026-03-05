"""
Installer — install ComfyUI custom node packages via CNR or git clone.

Two install paths (adapted from ComfyUI-Manager's UnifiedManager):
  1. CNR install: download versioned zip from api.comfy.org, extract, run deps
  2. Git install: git clone --depth 1, then run requirements.txt + install.py

CNR is preferred when a CNR ID is known; git clone is the fallback.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ghost_comfy_manager.pip_utils import execute_install_script
from ghost_comfy_manager.registry import NodeRegistry

log = logging.getLogger("ghost.comfy_manager.installer")

GHOST_HOME = Path.home() / ".ghost"
CUSTOM_NODES_DIR = GHOST_HOME / "comfyui" / "custom_nodes"

CNR_BASE_URL = "https://api.comfy.org"


@dataclass
class InstallResult:
    success: bool
    method: str  # "cnr", "git", or "skip"
    path: Optional[Path] = None
    error: str = ""


@dataclass
class NodeVersion:
    """CNR node version info from api.comfy.org."""
    changelog: str = ""
    dependencies: list[str] = field(default_factory=list)
    deprecated: bool = False
    id: str = ""
    version: str = ""
    download_url: str = ""


def _cnr_get_install_info(node_id: str, version: str | None = None) -> Optional[NodeVersion]:
    """Call api.comfy.org to get download URL for a CNR package.

    Adapted from ComfyUI-Manager's cnr_utils.install_node().
    """
    if version is None:
        url = f"{CNR_BASE_URL}/nodes/{node_id}/install"
    else:
        url = f"{CNR_BASE_URL}/nodes/{node_id}/install?version={version}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ghost/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))

        return NodeVersion(
            changelog=data.get("changelog", ""),
            dependencies=data.get("dependencies", []),
            deprecated=data.get("deprecated", False),
            id=data.get("id", ""),
            version=data.get("version", ""),
            download_url=data.get("downloadUrl", ""),
        )
    except Exception as exc:
        log.debug("CNR lookup failed for %s: %s", node_id, exc)
        return None


def _download_file(url: str, dest: Path) -> bool:
    """Download a file with User-Agent header."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Ghost/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        return True
    except Exception as exc:
        log.error("Download failed %s: %s", url, exc)
        return False


def _extract_zip(zip_path: Path, dest_dir: Path) -> Optional[list[str]]:
    """Extract a zip file and return list of extracted filenames."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
            return zf.namelist()
    except zipfile.BadZipFile:
        log.error("Bad zip file: %s", zip_path)
        return None


def cnr_install(
    node_id: str,
    version: str | None = None,
    custom_nodes_dir: Path = CUSTOM_NODES_DIR,
    no_deps: bool = False,
) -> InstallResult:
    """Install a custom node package from the Comfy Node Registry.

    Adapted from ComfyUI-Manager's UnifiedManager.cnr_install().

    1. Query api.comfy.org for download URL
    2. Download zip to temp file
    3. Extract to custom_nodes/{node_id}/
    4. Write .tracking file
    5. Run execute_install_script (requirements.txt + install.py)
    """
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)

    node_info = _cnr_get_install_info(node_id, version)
    if node_info is None or not node_info.download_url:
        return InstallResult(
            success=False, method="cnr",
            error=f"CNR package not found: {node_id}@{version or 'latest'}",
        )

    install_path = custom_nodes_dir / node_id
    if install_path.exists():
        log.info("CNR package already installed at %s", install_path)
        return InstallResult(success=True, method="skip", path=install_path)

    archive_name = f"CNR_temp_{uuid.uuid4().hex[:12]}.zip"
    download_path = custom_nodes_dir / archive_name

    log.info("CNR installing %s@%s", node_id, node_info.version)

    if not _download_file(node_info.download_url, download_path):
        return InstallResult(
            success=False, method="cnr",
            error=f"Failed to download: {node_info.download_url}",
        )

    install_path.mkdir(parents=True, exist_ok=True)
    extracted = _extract_zip(download_path, install_path)

    try:
        download_path.unlink()
    except OSError:
        pass

    if extracted is None:
        shutil.rmtree(install_path, ignore_errors=True)
        return InstallResult(
            success=False, method="cnr",
            error=f"Empty or corrupt archive: {node_id}@{node_info.version}",
        )

    tracking_file = install_path / ".tracking"
    tracking_file.write_text("\n".join(extracted), encoding="utf-8")

    if not no_deps:
        execute_install_script(install_path)

    log.info("CNR install complete: %s → %s", node_id, install_path)
    return InstallResult(success=True, method="cnr", path=install_path)


def git_install(
    repo_url: str,
    custom_nodes_dir: Path = CUSTOM_NODES_DIR,
    no_deps: bool = False,
    timeout: int = 300,
) -> InstallResult:
    """Install a custom node package by cloning its git repository.

    Adapted from ComfyUI-Manager's UnifiedManager.repo_install().

    1. git clone --depth 1 --recursive
    2. Run execute_install_script (requirements.txt + install.py)
    """
    custom_nodes_dir.mkdir(parents=True, exist_ok=True)

    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    dest = custom_nodes_dir / repo_name

    if dest.exists():
        log.info("Custom node dir exists: %s — pulling latest", dest)
        try:
            result = subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                log.warning("git pull failed for %s: %s", dest, result.stderr[:300])
        except Exception as exc:
            log.warning("git pull error for %s: %s", dest, exc)

        if not no_deps:
            execute_install_script(dest)

        return InstallResult(success=True, method="git", path=dest)

    log.info("Cloning %s → %s", repo_url, dest)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--recursive", repo_url, str(dest)],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            log.error("git clone failed: %s\n%s", repo_url, result.stderr[:500])
            return InstallResult(
                success=False, method="git",
                error=f"git clone failed: {result.stderr[:200]}",
            )
    except subprocess.TimeoutExpired:
        log.error("git clone timed out: %s", repo_url)
        return InstallResult(success=False, method="git", error="clone timed out")
    except Exception as exc:
        log.error("git clone error: %s — %s", repo_url, exc)
        return InstallResult(success=False, method="git", error=str(exc))

    if not no_deps:
        execute_install_script(dest)

    log.info("Git install complete: %s → %s", repo_url, dest)
    return InstallResult(success=True, method="git", path=dest)


def install_package(
    repo_url: str,
    registry: NodeRegistry | None = None,
    custom_nodes_dir: Path = CUSTOM_NODES_DIR,
    no_deps: bool = False,
) -> InstallResult:
    """Install a custom node package, preferring CNR over git clone.

    1. Check if repo has a CNR ID (from custom-node-list.json)
    2. If yes, try CNR install (versioned zip from api.comfy.org)
    3. If CNR fails or no ID, fall back to git clone
    """
    if registry is None:
        registry = NodeRegistry.get()

    cnr_id = registry.get_cnr_id(repo_url)

    if cnr_id:
        log.info("Found CNR ID '%s' for %s — trying CNR install", cnr_id, repo_url)
        result = cnr_install(cnr_id, custom_nodes_dir=custom_nodes_dir, no_deps=no_deps)
        if result.success:
            return result
        log.info("CNR install failed for %s, falling back to git: %s", cnr_id, result.error)

    return git_install(repo_url, custom_nodes_dir=custom_nodes_dir, no_deps=no_deps)
