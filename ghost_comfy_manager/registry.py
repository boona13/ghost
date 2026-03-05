"""
Registry — fetch, cache, and index ComfyUI-Manager data files.

Data sources (from ltdrdata/ComfyUI-Manager GitHub):
  - extension-node-map.json  : class_type → repo URL
  - custom-node-list.json    : rich package metadata (pip, preemptions, patterns)
  - model-list.json          : model download URLs + save paths

All files cached under ~/.ghost/comfyui/ and refreshed every 24 hours.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger("ghost.comfy_manager.registry")

GHOST_HOME = Path.home() / ".ghost"
CACHE_DIR = GHOST_HOME / "comfyui"

_BASE_RAW = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main"

_URLS = {
    "extension-node-map": f"{_BASE_RAW}/extension-node-map.json",
    "custom-node-list": f"{_BASE_RAW}/custom-node-list.json",
    "model-list": f"{_BASE_RAW}/model-list.json",
}

_CACHE_TTL = 86400  # 24 hours

CORE_REPO = "https://github.com/comfyanonymous/ComfyUI"


def _fetch_json(url: str, cache_path: Path) -> dict | list:
    """Download JSON from *url*, caching to *cache_path* for 24 h."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < _CACHE_TTL:
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    try:
        log.info("Fetching %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "Ghost/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data
    except Exception as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        return {}


class NodeRegistry:
    """Indexed view over ComfyUI-Manager's data files.

    Builds three lookup structures on first access:
      - node_to_repos   : class_type → [repo_url, ...]
      - preemption_map   : class_type → repo_url (takes priority)
      - patterns         : [(compiled_regex, repo_url), ...]
      - cnr_id_for_repo  : repo_url → cnr_id (from custom-node-list)
      - repo_for_cnr_id  : cnr_id → repo_url
    """

    _instance: Optional["NodeRegistry"] = None

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self._cache_dir = cache_dir
        self._ext_map: dict | None = None
        self._custom_nodes: list | None = None
        self._model_list: list | None = None

        self.node_to_repos: dict[str, list[str]] = {}
        self.preemption_map: dict[str, str] = {}
        self.patterns: list[tuple[re.Pattern, str]] = []
        self.cnr_id_for_repo: dict[str, str] = {}
        self.repo_for_cnr_id: dict[str, str] = {}
        self._indexed = False

    @classmethod
    def get(cls, cache_dir: Path = CACHE_DIR) -> "NodeRegistry":
        if cls._instance is None or cls._instance._cache_dir != cache_dir:
            cls._instance = cls(cache_dir)
        return cls._instance

    @classmethod
    def invalidate(cls):
        cls._instance = None

    def ensure_loaded(self):
        if self._indexed:
            return
        self._load_extension_node_map()
        self._load_custom_node_list()
        self._indexed = True

    def _load_extension_node_map(self):
        cache_path = self._cache_dir / "extension-node-map.json"
        self._ext_map = _fetch_json(_URLS["extension-node-map"], cache_path)
        if not isinstance(self._ext_map, dict):
            self._ext_map = {}

        for repo_url, entry in self._ext_map.items():
            node_names: list[str] = []
            metadata: dict = {}

            if isinstance(entry, list) and len(entry) >= 1:
                node_names = entry[0] if isinstance(entry[0], list) else entry
                if len(entry) >= 2 and isinstance(entry[1], dict):
                    metadata = entry[1]
            elif isinstance(entry, dict):
                node_names = entry.get("nodenames", entry.get("nodes", []))
                metadata = entry

            is_core = repo_url.rstrip("/").rstrip(".git") == CORE_REPO

            if is_core:
                for name in node_names:
                    self.preemption_map.setdefault(name, repo_url)
                continue

            for name in node_names:
                self.node_to_repos.setdefault(name, []).append(repo_url)

            if "preemptions" in metadata:
                for name in metadata["preemptions"]:
                    self.preemption_map[name] = repo_url

            if "nodename_pattern" in metadata:
                try:
                    pat = re.compile(metadata["nodename_pattern"])
                    self.patterns.append((pat, repo_url))
                except re.error:
                    pass

    def _load_custom_node_list(self):
        cache_path = self._cache_dir / "custom-node-list.json"
        raw = _fetch_json(_URLS["custom-node-list"], cache_path)

        nodes = raw.get("custom_nodes", []) if isinstance(raw, dict) else []
        self._custom_nodes = nodes

        for node_info in nodes:
            cnr_id = node_info.get("id", "")
            files = node_info.get("files", [])
            if not cnr_id or not files:
                continue
            for url in files:
                if isinstance(url, str) and url.startswith("http"):
                    normalized = url.rstrip("/")
                    self.cnr_id_for_repo[normalized] = cnr_id
                    self.repo_for_cnr_id[cnr_id] = normalized

    def get_extension_node_map(self) -> dict:
        self.ensure_loaded()
        return self._ext_map or {}

    def get_custom_node_list(self) -> list[dict]:
        self.ensure_loaded()
        return self._custom_nodes or []

    def get_model_list(self) -> list[dict]:
        if self._model_list is None:
            cache_path = self._cache_dir / "model-list.json"
            raw = _fetch_json(_URLS["model-list"], cache_path)
            self._model_list = raw.get("models", []) if isinstance(raw, dict) else []
        return self._model_list

    def lookup_node(self, class_type: str) -> Optional[str]:
        """Find the best repo URL for a node class_type.

        Priority: preemption > direct map > regex pattern.
        Returns None if not found. Skips core ComfyUI repo.
        """
        self.ensure_loaded()

        if class_type in self.preemption_map:
            repo = self.preemption_map[class_type]
            if repo.rstrip("/").rstrip(".git") == CORE_REPO:
                return None
            return repo

        repos = self.node_to_repos.get(class_type)
        if repos:
            return repos[0]

        for pat, repo_url in self.patterns:
            if pat.search(class_type):
                return repo_url

        return None

    def get_cnr_id(self, repo_url: str) -> Optional[str]:
        """Map a repo URL to its CNR package ID, if known."""
        self.ensure_loaded()
        normalized = repo_url.rstrip("/")
        cnr_id = self.cnr_id_for_repo.get(normalized)
        if cnr_id:
            return cnr_id
        if normalized.endswith(".git"):
            return self.cnr_id_for_repo.get(normalized[:-4])
        return self.cnr_id_for_repo.get(normalized + ".git")

    def get_package_metadata(self, repo_url: str) -> Optional[dict]:
        """Get rich metadata for a package from custom-node-list."""
        self.ensure_loaded()
        normalized = repo_url.rstrip("/")
        for node_info in (self._custom_nodes or []):
            for url in node_info.get("files", []):
                if isinstance(url, str) and url.rstrip("/") == normalized:
                    return node_info
        return None
