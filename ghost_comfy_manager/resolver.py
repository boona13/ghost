"""
Resolver — find which package provides a given ComfyUI node class_type,
and extract all node dependencies from a workflow JSON.

Adapted from ComfyUI-Manager's extract_nodes_from_workflow() with
preemption handling, nodename_pattern regex matching, and CNR ID lookup.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from ghost_comfy_manager.registry import NodeRegistry, CORE_REPO

log = logging.getLogger("ghost.comfy_manager.resolver")

_SKIP_REPOS = {
    CORE_REPO,
    CORE_REPO + ".git",
}


def find_package_for_node(
    class_type: str,
    registry: NodeRegistry | None = None,
) -> Optional[str]:
    """Look up the best repo URL for a ComfyUI node class_type.

    Resolution order (mirrors ComfyUI-Manager):
      1. Preemption map (explicit overrides from extension metadata)
      2. Direct lookup in extension-node-map
      3. Regex nodename_pattern matching
    Skips the core comfyanonymous/ComfyUI repo.

    Returns repo URL string or None.
    """
    if registry is None:
        registry = NodeRegistry.get()
    registry.ensure_loaded()

    repo = registry.lookup_node(class_type)
    if repo and repo.rstrip("/") not in _SKIP_REPOS:
        return repo
    return None


def find_cnr_id_for_node(
    class_type: str,
    registry: NodeRegistry | None = None,
) -> Optional[str]:
    """Find the CNR package ID for a node, if available.

    First finds the repo URL, then maps it to a CNR ID via custom-node-list.
    """
    repo = find_package_for_node(class_type, registry)
    if not repo:
        return None
    if registry is None:
        registry = NodeRegistry.get()
    return registry.get_cnr_id(repo)


def extract_workflow_deps(
    workflow: dict,
    registry: NodeRegistry | None = None,
) -> tuple[dict[str, str], set[str]]:
    """Analyze a workflow and return its custom node dependencies.

    Adapted from ComfyUI-Manager's extract_nodes_from_workflow().

    Args:
        workflow: Parsed ComfyUI workflow JSON (UI format with 'nodes' key,
                  or API format with node-id keys).
        registry: Optional pre-loaded NodeRegistry.

    Returns:
        (extensions, unknown_nodes) where:
          extensions = {repo_url: "title or repo name"}
          unknown_nodes = set of class_types not found in any registry
    """
    if registry is None:
        registry = NodeRegistry.get()
    registry.ensure_loaded()

    used_types = _extract_node_types(workflow)

    extensions: dict[str, str] = {}
    unknown: set[str] = set()

    for class_type in used_types:
        repo = registry.lookup_node(class_type)
        if repo:
            if repo.rstrip("/") in _SKIP_REPOS:
                continue
            if repo not in extensions:
                meta = registry.get_package_metadata(repo)
                title = meta.get("title", repo.split("/")[-1]) if meta else repo.split("/")[-1]
                extensions[repo] = title
        else:
            unknown.add(class_type)

    return extensions, unknown


_VIRTUAL_NODES = {"Reroute", "Note"}


def _extract_node_types(workflow: dict) -> set[str]:
    """Extract all node class_types from a workflow JSON.

    Handles both UI format (has 'nodes' key) and API format (top-level
    dict of node_id -> node_data). Also handles grouped nodes in
    workflow['extra']['groupNodes'].
    """
    types: set[str] = set()

    if "nodes" in workflow:
        _collect_from_ui_workflow(workflow, types)
    else:
        _collect_from_api_workflow(workflow, types)

    return types


def _collect_from_ui_workflow(workflow: dict, types: set[str]):
    """Collect types from UI-format workflow (has 'nodes' list)."""
    for node in workflow.get("nodes", []):
        node_type = node.get("type")
        if not node_type:
            continue
        if node_type in _VIRTUAL_NODES:
            continue
        if node_type.startswith("workflow/") or node_type.startswith("workflow>"):
            continue
        types.add(node_type)

    extra = workflow.get("extra", {})
    for group_data in extra.get("groupNodes", {}).values():
        for node in group_data.get("nodes", []):
            node_type = node.get("type")
            if node_type and node_type not in _VIRTUAL_NODES:
                if not (node_type.startswith("workflow/") or node_type.startswith("workflow>")):
                    types.add(node_type)


def _collect_from_api_workflow(workflow: dict, types: set[str]):
    """Collect types from API-format workflow (node_id -> node_data)."""
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type")
        if class_type and class_type not in _VIRTUAL_NODES:
            types.add(class_type)
