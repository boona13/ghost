"""
GhostNodes Node Manager — discover, install, load, enable/disable AI node packages.

A "node" is a self-contained AI capability (image gen, TTS, STT, etc.) that
registers tools with Ghost's ToolRegistry and can request GPU resources via
the ResourceManager.

Node directory layout:
    ~/.ghost/nodes/<name>/
        NODE.yaml          — manifest
        node.py            — register(api) entry point
        requirements.txt   — pip dependencies (optional)
        models/            — symlinks to shared model cache (optional)
"""

import importlib
import importlib.util
import json
import logging
import shutil
import subprocess
import sys
import threading
import traceback
import time

# Thread-local storage for progress callbacks from executing nodes
_node_progress = threading.local()
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ghost.node_manager")

GHOST_HOME = Path.home() / ".ghost"
NODES_DIR = GHOST_HOME / "nodes"
NODES_DIR.mkdir(parents=True, exist_ok=True)
BUNDLED_NODES_DIR = Path(__file__).resolve().parent / "ghost_nodes"
MODELS_CACHE_DIR = GHOST_HOME / "models"
MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

NODE_CATEGORIES = [
    "image_generation", "video", "audio", "vision",
    "llm", "3d", "data", "utility",
]

IO_TYPES = [
    "text", "image", "audio", "video", "mesh_3d",
    "embeddings", "json", "binary",
]


def _load_yaml(path: Path) -> dict:
    """Load YAML with fallback to a minimal hand-parser if pyyaml unavailable."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    return _minimal_yaml_parse(text)


def _minimal_yaml_parse(text: str) -> dict:
    """Bare-bones YAML-subset parser for NODE.yaml when PyYAML is missing.

    Handles only flat key: value pairs and simple lists. Enough for
    manifest loading — not a general-purpose parser.
    """
    result = {}
    current_key = None
    current_list = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_key and current_list is not None:
            val = stripped[2:].strip().strip('"').strip("'")
            if val.startswith("{"):
                try:
                    current_list.append(json.loads(val))
                except json.JSONDecodeError:
                    current_list.append(val)
            else:
                current_list.append(val)
            continue

        if ":" in stripped:
            if current_key and current_list is not None:
                result[current_key] = current_list
                current_list = None

            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            if not val:
                current_key = key
                current_list = []
            elif val.startswith("[") and val.endswith("]"):
                items = val[1:-1]
                result[key] = [
                    i.strip().strip('"').strip("'")
                    for i in items.split(",") if i.strip()
                ]
                current_key = None
                current_list = None
            elif val.lower() in ("true", "false"):
                result[key] = val.lower() == "true"
                current_key = None
                current_list = None
            else:
                try:
                    result[key] = int(val)
                except ValueError:
                    try:
                        result[key] = float(val)
                    except ValueError:
                        result[key] = val
                current_key = None
                current_list = None

    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


# ═════════════════════════════════════════════════════════════════════
#  NODE MANIFEST
# ═════════════════════════════════════════════════════════════════════

@dataclass
class NodeManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    category: str = "utility"
    license: str = "MIT"

    requires_gpu: bool = False
    estimated_vram_gb: float = 0
    estimated_disk_gb: float = 0
    python_requires: str = ">=3.10"
    deps: list = field(default_factory=list)

    cloud_provider: str = ""
    api_key_env: str = ""

    models: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    tags: list = field(default_factory=list)

    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)

    node_deps: list = field(default_factory=list)

    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "NodeManifest":
        data = _load_yaml(path)
        req = data.get("requires", {})
        return cls(
            name=data.get("name", path.parent.name),
            version=str(data.get("version", "0.1.0")),
            description=data.get("description", ""),
            author=data.get("author", ""),
            category=data.get("category", "utility"),
            license=data.get("license", "MIT"),
            requires_gpu=req.get("gpu", False),
            estimated_vram_gb=req.get("vram_gb", 0),
            estimated_disk_gb=req.get("disk_gb", 0),
            python_requires=req.get("python", ">=3.10"),
            deps=req.get("deps", []),
            cloud_provider=req.get("cloud_provider", ""),
            api_key_env=req.get("api_key_env", ""),
            models=data.get("models", []),
            tools=data.get("tools", []),
            tags=data.get("tags", []),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            node_deps=data.get("node_deps", []),
            _raw=data,
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category,
            "license": self.license,
            "requires_gpu": self.requires_gpu,
            "estimated_vram_gb": self.estimated_vram_gb,
            "estimated_disk_gb": self.estimated_disk_gb,
            "deps": self.deps,
            "cloud_provider": self.cloud_provider,
            "api_key_env": self.api_key_env,
            "models": self.models,
            "tools": self.tools,
            "tags": self.tags,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }

    @property
    def default_model(self) -> Optional[dict]:
        for m in self.models:
            if m.get("default", False):
                return m
        return self.models[0] if self.models else None


# ═════════════════════════════════════════════════════════════════════
#  NODE API (exposed to nodes during registration)
# ═════════════════════════════════════════════════════════════════════

class NodeAPI:
    """API surface exposed to each node's register() function."""

    def __init__(self, node_id: str, manifest: NodeManifest,
                 tool_registry, resource_manager, media_store, config: dict,
                 cloud_providers=None):
        self.id = node_id
        self.manifest = manifest
        self._tool_registry = tool_registry
        self._resource_manager = resource_manager
        self._media_store = media_store
        self._cloud_providers = cloud_providers
        self._config = config
        self._registered_tools: list[str] = []
        self._node_dir = NODES_DIR / node_id
        self._models_dir = MODELS_CACHE_DIR
        self._data_dir = GHOST_HOME / "node_data" / node_id
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cfg = config

    @property
    def config(self) -> dict:
        return dict(self._config)

    @property
    def resource_manager(self):
        return self._resource_manager

    @property
    def media_store(self):
        return self._media_store

    @property
    def models_dir(self) -> Path:
        return self._models_dir

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def node_dir(self) -> Path:
        return self._node_dir

    @property
    def cloud_providers(self):
        """Access the cloud provider registry for API keys, polling, and cost tracking."""
        return self._cloud_providers

    def get_provider_key(self, provider_name: str) -> Optional[str]:
        """Get API key for a cloud provider. Returns None if not configured."""
        if self._cloud_providers:
            return self._cloud_providers.get_api_key(provider_name)
        return None

    @property
    def hf_token(self):
        """HuggingFace token for gated model access (FLUX, etc.)."""
        return self._get_hf_token()

    def register_tool(self, tool_def: dict):
        """Register a tool with Ghost's tool registry."""
        required = {"name", "description", "parameters", "execute"}
        missing = required - set(tool_def.keys())
        if missing:
            raise ValueError(f"Tool definition missing keys: {missing}")
        tool_def.setdefault("_node_id", self.id)
        self._tool_registry.register(tool_def)
        self._registered_tools.append(tool_def["name"])

    def acquire_gpu(self, model_id: str, estimated_vram_gb: float = 0, model_obj=None) -> str:
        """Request GPU allocation for a model. Returns device string.

        The load balancer serializes concurrent model loads to prevent OOM.
        If another model is currently loading, this call blocks until the
        gate is released. Call notify_model_ready() after loading completes
        to release the gate promptly; otherwise a 5-minute watchdog timeout
        auto-releases it.
        """
        device = self._resource_manager.acquire(
            model_id=model_id,
            estimated_vram_gb=estimated_vram_gb,
            model_obj=model_obj,
            metadata={"node_id": self.id},
        )
        self._last_acquired_model = model_id
        return device

    def notify_model_ready(self, model_id: str = ""):
        """Signal that a model has finished loading. Releases the load
        balancer gate so the next queued model can start loading.

        If model_id is omitted, uses the last model passed to acquire_gpu().
        """
        mid = model_id or getattr(self, "_last_acquired_model", "")
        if mid and hasattr(self._resource_manager, "notify_load_complete"):
            self._resource_manager.notify_load_complete(mid)

    def release_gpu(self, model_id: str) -> bool:
        return self._resource_manager.release(model_id)

    def get_device(self, estimated_vram_gb: float = 0) -> str:
        """Get best available device for given VRAM requirement."""
        return self._resource_manager.best_device_for(estimated_vram_gb)

    def save_media(self, data: bytes, filename: str, media_type: str = "image",
                   metadata: dict | None = None, prompt: str = "",
                   params: dict | None = None, tags: list | None = None,
                   ttl_secs: int = 0, pipeline_id: str = "",
                   provider: str = "local", cost_usd: float = 0.0) -> str:
        """Save generated media through the media store. Returns file path."""
        if self._media_store:
            return self._media_store.save(
                data=data, filename=filename, media_type=media_type,
                source_node=self.id, prompt=prompt, params=params,
                metadata=metadata, ttl_secs=ttl_secs,
                pipeline_id=pipeline_id, tags=tags,
                provider=provider, cost_usd=cost_usd,
            )
        out = GHOST_HOME / "media" / media_type / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return str(out)

    def log(self, message: str):
        log.info("[node:%s] %s", self.id, message)
        cb = getattr(_node_progress, "callback", None)
        if cb:
            try:
                cb(self.id, message)
            except Exception:
                pass

    def read_data(self, filename: str) -> Optional[str]:
        path = self._data_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_data(self, filename: str, content: str):
        (self._data_dir / filename).write_text(content, encoding="utf-8")

    def download_model(self, repo_id: str, filename: str | None = None,
                       revision: str = "main") -> Path:
        """Download a model from Hugging Face Hub into the shared cache."""
        try:
            from huggingface_hub import hf_hub_download
            token = self._get_hf_token()
            path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                revision=revision,
                cache_dir=str(self._models_dir),
                token=token,
            )
            return Path(path)
        except ImportError:
            raise RuntimeError(
                "huggingface-hub not installed. Run: pip install huggingface-hub"
            )

    def _get_hf_token(self):
        """Resolve HF token from config, env var, or cached login."""
        import os
        token = self._config.get("hf_token") or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if token:
            return token
        try:
            from huggingface_hub import HfFolder
            return HfFolder.get_token()
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════════════
#  NODE INFO
# ═════════════════════════════════════════════════════════════════════

@dataclass
class NodeInfo:
    name: str
    path: str
    manifest: Optional[NodeManifest] = None
    enabled: bool = True
    loaded: bool = False
    tools: list = field(default_factory=list)
    error: Optional[str] = None
    source: str = "user"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "enabled": self.enabled,
            "loaded": self.loaded,
            "tools": self.tools,
            "error": self.error,
            "source": self.source,
        }


# ═════════════════════════════════════════════════════════════════════
#  NODE MANAGER
# ═════════════════════════════════════════════════════════════════════

class NodeManager:
    """Discover, load, and manage GhostNodes."""

    def __init__(self, tool_registry, resource_manager, media_store=None,
                 cloud_providers=None, cfg: dict | None = None):
        self.tool_registry = tool_registry
        self.resource_manager = resource_manager
        self.media_store = media_store
        self.cloud_providers = cloud_providers
        self.cfg = cfg or {}
        self.nodes: dict[str, NodeInfo] = {}
        self.nodes_dir = NODES_DIR
        self._disabled: set[str] = self._load_disabled()
        self._lock = threading.Lock()
        self._install_progress: dict[str, dict] = {}

    def discover_all(self):
        """Scan bundled and user node directories for NODE.yaml manifests."""
        for source, scan_dir in [("bundled", BUNDLED_NODES_DIR), ("user", NODES_DIR)]:
            if not scan_dir.is_dir():
                continue
            for item in sorted(scan_dir.iterdir()):
                if not item.is_dir():
                    continue
                manifest_path = item / "NODE.yaml"
                if not manifest_path.exists():
                    manifest_path = item / "NODE.yml"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = NodeManifest.from_yaml(manifest_path)
                    self.nodes[manifest.name] = NodeInfo(
                        name=manifest.name,
                        path=str(item),
                        manifest=manifest,
                        enabled=manifest.name not in self._disabled,
                        source=source,
                    )
                except Exception as e:
                    self.nodes[item.name] = NodeInfo(
                        name=item.name,
                        path=str(item),
                        error=f"Manifest error: {e}",
                        source=source,
                    )

    def load_all(self):
        """Load all discovered and enabled nodes."""
        self.discover_all()
        for name, info in list(self.nodes.items()):
            if info.enabled and not info.loaded and not info.error:
                self._load_node(name)

    def _load_node(self, name: str):
        """Load a single node by name."""
        info = self.nodes.get(name)
        if not info or not info.manifest:
            return

        node_dir = Path(info.path)
        node_py = node_dir / "node.py"
        if not node_py.exists():
            info.error = "No node.py found"
            return

        site_packages = node_dir / "site-packages"
        if site_packages.is_dir() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))

        api = NodeAPI(
            node_id=name,
            manifest=info.manifest,
            tool_registry=self.tool_registry,
            resource_manager=self.resource_manager,
            media_store=self.media_store,
            config=self.cfg,
            cloud_providers=self.cloud_providers,
        )

        try:
            spec = importlib.util.spec_from_file_location(
                f"ghost_node_{name}", str(node_py),
                submodule_search_locations=[str(node_dir)],
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"ghost_node_{name}"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register"):
                module.register(api)
            else:
                info.error = "No register() function found"
                return

            info.loaded = True
            info.tools = list(api._registered_tools)
            log.info("Node loaded: %s (tools: %s)", name, info.tools)

        except Exception as e:
            info.error = f"{e}\n{traceback.format_exc()[-500:]}"
            log.error("Node load error (%s): %s", name, e)

    def enable_node(self, name: str) -> bool:
        info = self.nodes.get(name)
        if not info:
            return False
        self._disabled.discard(name)
        info.enabled = True
        info.error = None
        self._persist_disabled()
        if not info.loaded:
            self._load_node(name)
        return True

    def disable_node(self, name: str) -> bool:
        info = self.nodes.get(name)
        if not info:
            return False
        self._disabled.add(name)
        info.enabled = False
        self._persist_disabled()

        if info.loaded:
            for tool_name in info.tools:
                try:
                    self.tool_registry.unregister(tool_name)
                except Exception:
                    pass
            info.loaded = False
            mod_key = f"ghost_node_{name}"
            sys.modules.pop(mod_key, None)
            log.info("Node disabled and tools unregistered: %s (tools: %s)", name, info.tools)

        return True

    def _persist_disabled(self):
        """Save the disabled nodes list to config so it survives restarts."""
        disabled_file = GHOST_HOME / "disabled_nodes.json"
        try:
            disabled_file.write_text(json.dumps(sorted(self._disabled)))
        except Exception as e:
            log.warning("Failed to persist disabled nodes: %s", e)

    def _load_disabled(self) -> set[str]:
        """Load disabled nodes from config and persistent file."""
        disabled = set(self.cfg.get("disabled_nodes", []))
        disabled_file = GHOST_HOME / "disabled_nodes.json"
        if disabled_file.exists():
            try:
                disabled.update(json.loads(disabled_file.read_text()))
            except Exception:
                pass
        return disabled

    @staticmethod
    def _sanitize_node_name(name: str) -> str | None:
        """Sanitize node name to prevent path traversal. Returns None if invalid."""
        import re
        clean = name.strip().lower()
        if not clean or not re.match(r"^[a-z0-9][a-z0-9._-]*$", clean):
            return None
        if ".." in clean or "/" in clean or "\\" in clean:
            return None
        return clean

    def install_local(self, source_path: str) -> dict:
        """Install a node from a local directory."""
        src = Path(source_path)
        manifest_path = src / "NODE.yaml"
        if not manifest_path.exists():
            manifest_path = src / "NODE.yml"
        if not manifest_path.exists():
            return {"status": "error", "error": "No NODE.yaml found in source directory"}

        if not (src / "node.py").exists():
            return {"status": "error", "error": "No node.py entry point found in source directory"}

        try:
            manifest = NodeManifest.from_yaml(manifest_path)
        except Exception as e:
            return {"status": "error", "error": f"Invalid manifest: {e}"}

        safe_name = self._sanitize_node_name(manifest.name)
        if not safe_name:
            return {"status": "error", "error": f"Invalid node name: {manifest.name!r} (must be alphanumeric with hyphens/dots)"}
        manifest.name = safe_name

        dest = NODES_DIR / safe_name
        if dest.exists():
            shutil.rmtree(dest)

        def _ignore_git(directory, contents):
            return [".git"] if ".git" in contents else []

        shutil.copytree(src, dest, ignore=_ignore_git)

        req_file = dest / "requirements.txt"
        dep_result = None
        if req_file.exists():
            dep_result = self._install_deps(safe_name, req_file)

        self.nodes[safe_name] = NodeInfo(
            name=safe_name,
            path=str(dest),
            manifest=manifest,
            enabled=True,
            source="user",
        )
        self._load_node(safe_name)

        info = self.nodes[safe_name]
        result = {
            "status": "ok",
            "name": safe_name,
            "tools": info.tools,
        }
        if info.error:
            result["warning"] = f"Node installed but failed to load: {info.error}"
        if dep_result and dep_result.get("status") == "error":
            result["dep_warning"] = dep_result.get("error", "Dependency install failed")

        return result

    def install_from_github(self, repo_url: str, subdir: str = "") -> dict:
        """Install a node from a GitHub repository."""
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", repo_url, str(tmp / "repo")],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return {"status": "error", "error": f"Git clone failed: {result.stderr[:300]}"}

            src = tmp / "repo" / subdir if subdir else tmp / "repo"
            return self.install_local(str(src))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def uninstall_node(self, name: str) -> bool:
        info = self.nodes.get(name)
        if not info:
            return False
        if info.source == "bundled":
            log.warning("Cannot uninstall bundled node: %s", name)
            return False

        mod_name = f"ghost_node_{name}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        node_path = Path(info.path)
        if node_path.exists():
            shutil.rmtree(node_path, ignore_errors=True)

        del self.nodes[name]
        return True

    def _install_deps(self, name: str, req_file: Path) -> dict:
        """Install node dependencies to isolated site-packages. Returns status dict."""
        target = NODES_DIR / name / "site-packages"
        target.mkdir(parents=True, exist_ok=True)
        self._install_progress[name] = {"status": "installing", "started": time.time()}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 "-r", str(req_file),
                 "--target", str(target),
                 "--quiet", "--no-warn-script-location"],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "Unknown pip error"
                log.error("Dependency install failed for %s: %s", name, error_msg)
                self._install_progress[name] = {"status": "failed", "error": error_msg}
                return {"status": "error", "error": error_msg}
            self._install_progress[name] = {"status": "completed"}
            return {"status": "ok"}
        except subprocess.TimeoutExpired:
            log.error("Dependency install timed out for %s", name)
            self._install_progress[name] = {"status": "timeout"}
            return {"status": "error", "error": "Install timed out (600s)"}
        except Exception as e:
            log.error("Dependency install failed for %s: %s", name, e)
            self._install_progress[name] = {"status": "failed", "error": str(e)}
            return {"status": "error", "error": str(e)}

    def list_nodes(self, category: str | None = None) -> list[dict]:
        """List all nodes, optionally filtered by category."""
        nodes = []
        for info in self.nodes.values():
            if category and info.manifest and info.manifest.category != category:
                continue
            nodes.append(info.to_dict())
        return sorted(nodes, key=lambda n: (n.get("source", ""), n.get("name", "")))

    def get_node(self, name: str) -> Optional[NodeInfo]:
        return self.nodes.get(name)

    def get_node_tools(self) -> list[str]:
        """Get all tool names registered by nodes."""
        tools = []
        for info in self.nodes.values():
            if info.loaded and info.enabled:
                tools.extend(info.tools)
        return tools

    def get_install_progress(self, name: str) -> dict:
        return self._install_progress.get(name, {})


def set_node_progress_callback(callback):
    """Set a thread-local callback for node progress updates.

    callback(node_id: str, message: str) is called by NodeAPI.log().
    """
    _node_progress.callback = callback


def clear_node_progress_callback():
    """Clear the thread-local progress callback."""
    _node_progress.callback = None


# ═════════════════════════════════════════════════════════════════════
#  TOOL BUILDER
# ═════════════════════════════════════════════════════════════════════

def build_node_manager_tools(node_manager: NodeManager):
    """Build tools for managing GhostNodes from the LLM tool loop."""

    def execute_list(category: str = "", **_kw):
        nodes = node_manager.list_nodes(category=category or None)
        return json.dumps({"status": "ok", "count": len(nodes), "nodes": nodes}, default=str)

    def execute_install(source: str = "", **_kw):
        if not source:
            return json.dumps({"status": "error", "error": "source path or URL required"})
        if source.startswith("http") and "github" in source:
            result = node_manager.install_from_github(source)
        else:
            result = node_manager.install_local(source)
        return json.dumps(result, default=str)

    def execute_enable(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "node name required"})
        ok = node_manager.enable_node(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Enabled {name}" if ok else f"Node not found: {name}"})

    def execute_disable(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "node name required"})
        ok = node_manager.disable_node(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Disabled {name}" if ok else f"Node not found: {name}"})

    def execute_uninstall(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "node name required"})
        ok = node_manager.uninstall_node(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Uninstalled {name}" if ok else f"Cannot uninstall: {name}"})

    return [
        {
            "name": "nodes_list",
            "description": (
                "List all installed GhostNodes (AI capability plugins). "
                "Optionally filter by category: image_generation, video, audio, vision, llm, 3d, data, utility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category",
                        "enum": NODE_CATEGORIES,
                    },
                },
            },
            "execute": execute_list,
        },
        {
            "name": "nodes_install",
            "description": "Install a GhostNode from a local path or GitHub URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Local directory path or GitHub repo URL",
                    },
                },
                "required": ["source"],
            },
            "execute": execute_install,
        },
        {
            "name": "nodes_enable",
            "description": "Enable a disabled GhostNode.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Node name"}},
                "required": ["name"],
            },
            "execute": execute_enable,
        },
        {
            "name": "nodes_disable",
            "description": "Disable a GhostNode (keeps it installed but unloads its tools).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Node name"}},
                "required": ["name"],
            },
            "execute": execute_disable,
        },
        {
            "name": "nodes_uninstall",
            "description": "Uninstall a user-installed GhostNode (cannot uninstall bundled nodes).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Node name"}},
                "required": ["name"],
            },
            "execute": execute_uninstall,
        },
    ]
