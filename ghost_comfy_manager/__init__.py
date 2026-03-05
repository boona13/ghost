"""
ghost_comfy_manager — ComfyUI node/model package manager for Ghost.

Extracted and adapted from ComfyUI-Manager (ltdrdata/ComfyUI-Manager)
to work standalone without a full ComfyUI installation.
"""

from ghost_comfy_manager.registry import NodeRegistry
from ghost_comfy_manager.resolver import find_package_for_node, extract_workflow_deps
from ghost_comfy_manager.installer import install_package, cnr_install, git_install

__all__ = [
    "NodeRegistry",
    "find_package_for_node",
    "extract_workflow_deps",
    "install_package",
    "cnr_install",
    "git_install",
]
