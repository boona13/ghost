"""
Ghost Extension Manager — discover, install, load, enable/disable feature extensions.

An "extension" is a self-contained feature plugin (tools, dashboard pages, routes,
cron jobs, event hooks, settings) that registers with Ghost's core systems via
ExtensionAPI without modifying Ghost source code.

Extension directory layout:
    ghost_extensions/<name>/        — bundled (shipped with Ghost)
    ~/.ghost/extensions/<name>/     — user/AI-installed

    <name>/
        EXTENSION.yaml          — manifest (required)
        extension.py            — register(api) entry point (required)
        routes/                 — optional Flask blueprints
        static/                 — optional frontend assets (JS, CSS)
        templates/              — optional Jinja templates
        requirements.txt        — pip dependencies (optional)
"""

import importlib
import importlib.util
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("ghost.extension_manager")

GHOST_HOME = Path.home() / ".ghost"
EXTENSIONS_DIR = GHOST_HOME / "extensions"
EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
BUNDLED_EXTENSIONS_DIR = Path(__file__).resolve().parent / "ghost_extensions"

EXTENSION_CATEGORIES = [
    "integration", "dashboard", "tool", "channel",
    "automation", "monitoring", "utility",
]


def _load_yaml(path: Path) -> dict:
    """Load YAML with fallback to JSON or minimal hand-parser."""
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
    """Bare-bones YAML-subset parser for EXTENSION.yaml when PyYAML is missing."""
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
#  EXTENSION MANIFEST
# ═════════════════════════════════════════════════════════════════════

@dataclass
class ExtensionManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    category: str = "utility"
    license: str = "MIT"

    ghost_version: str = ""
    deps: list = field(default_factory=list)
    extension_deps: list = field(default_factory=list)

    tools: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    cron_jobs: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    hooks: list = field(default_factory=list)

    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_yaml(cls, path: Path) -> "ExtensionManifest":
        data = _load_yaml(path)
        req = data.get("requires", {})
        if not isinstance(req, dict):
            req = {}
        provides = data.get("provides", {})
        if not isinstance(provides, dict):
            provides = {}
        return cls(
            name=data.get("name", path.parent.name),
            version=str(data.get("version", "0.1.0")),
            description=data.get("description", ""),
            author=data.get("author", ""),
            category=data.get("category", "utility"),
            license=data.get("license", "MIT"),
            ghost_version=req.get("ghost_version", ""),
            deps=req.get("deps", []),
            extension_deps=req.get("extensions", []),
            tools=provides.get("tools", []),
            routes=provides.get("routes", []),
            pages=provides.get("pages", []),
            cron_jobs=provides.get("cron_jobs", []),
            settings=provides.get("settings", []),
            hooks=data.get("hooks", []),
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
            "ghost_version": self.ghost_version,
            "deps": self.deps,
            "extension_deps": self.extension_deps,
            "tools": self.tools,
            "routes": self.routes,
            "pages": self.pages,
            "cron_jobs": self.cron_jobs,
            "settings": self.settings,
            "hooks": self.hooks,
        }


# ═════════════════════════════════════════════════════════════════════
#  EXTENSION EVENT BUS
# ═════════════════════════════════════════════════════════════════════

class ExtensionEventBus:
    """Lightweight pub/sub for extension lifecycle hooks."""

    def __init__(self):
        self._handlers: dict[str, list[tuple[str, Callable]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback: Callable, extension_id: str):
        with self._lock:
            self._handlers[event].append((extension_id, callback))

    def unsubscribe_all(self, extension_id: str):
        with self._lock:
            for event in self._handlers:
                self._handlers[event] = [
                    (eid, cb) for eid, cb in self._handlers[event]
                    if eid != extension_id
                ]

    def emit(self, event: str, **kwargs):
        with self._lock:
            handlers = list(self._handlers.get(event, []))
        for ext_id, cb in handlers:
            try:
                cb(**kwargs)
            except Exception as e:
                log.warning("Extension %s hook failed for %s: %s", ext_id, event, e)

    def get_subscribers(self, event: str) -> list[str]:
        with self._lock:
            return [eid for eid, _ in self._handlers.get(event, [])]


# ═════════════════════════════════════════════════════════════════════
#  EXTENSION API (exposed to extensions during registration)
# ═════════════════════════════════════════════════════════════════════

_EXTENSION_CRON_CALLBACKS: dict[tuple[str, str], Callable] = {}


def get_extension_cron_callback(extension_id: str, callback_name: str) -> Optional[Callable]:
    """Look up a cron callback registered by an extension."""
    return _EXTENSION_CRON_CALLBACKS.get((extension_id, callback_name))


class ExtensionAPI:
    """API surface exposed to each extension's register() function."""

    def __init__(self, extension_id: str, manifest: ExtensionManifest,
                 tool_registry, event_bus: ExtensionEventBus,
                 cron_service=None, config: dict = None,
                 daemon_ref=None, ext_path: Optional[Path] = None):
        self.id = extension_id
        self.manifest = manifest
        self._tool_registry = tool_registry
        self._event_bus = event_bus
        self._cron_service = cron_service
        self._config = config or {}
        self._daemon_ref = daemon_ref
        self._registered_tools: list[str] = []
        self._registered_routes: list = []
        self._registered_pages: list[dict] = []
        self._registered_cron: list[str] = []
        self._registered_hooks: list[str] = []
        self._registered_settings: list[dict] = []
        self._ext_dir = ext_path or (EXTENSIONS_DIR / extension_id)
        self._data_dir = GHOST_HOME / "extension_data" / extension_id
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_file = GHOST_HOME / "extension_settings" / f"{extension_id}.json"
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def config(self) -> dict:
        return dict(self._config)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def extension_dir(self) -> Path:
        return self._ext_dir

    # ── Tool registration ──────────────────────────────────────────

    def register_tool(self, tool_def: dict):
        """Register a tool with Ghost's tool registry."""
        required = {"name", "description", "parameters", "execute"}
        missing = required - set(tool_def.keys())
        if missing:
            raise ValueError(f"Tool definition missing keys: {missing}")
        tool_def.setdefault("_extension_id", self.id)
        self._tool_registry.register(tool_def)
        self._registered_tools.append(tool_def["name"])

    # ── Dashboard integration ──────────────────────────────────────

    def register_route(self, blueprint):
        """Register a Flask blueprint for dashboard API routes."""
        self._registered_routes.append(blueprint)

    def register_page(self, page_def: dict):
        """Register a dashboard SPA page.

        page_def: {id, label, icon, section, js_path}
        js_path is relative to the extension's static/ directory.
        """
        page_def.setdefault("_extension_id", self.id)
        if "js_path" in page_def and not page_def.get("js_url"):
            page_def["js_url"] = f"/extensions/{self.id}/static/{page_def['js_path']}"
        self._registered_pages.append(page_def)

    # ── Cron integration ───────────────────────────────────────────

    def register_cron(self, name: str, callback: Callable,
                      schedule: str, description: str = ""):
        """Register a cron job that runs on a schedule.

        schedule: cron expression (e.g. '*/5 * * * *') or interval seconds.
        callback: function to call when the job fires.
        """
        if not self._cron_service:
            log.warning("Extension %s: cron service not available, skipping cron %s", self.id, name)
            return

        job_name = f"ext_{self.id}_{name}"
        _EXTENSION_CRON_CALLBACKS[(self.id, name)] = callback
        self._cron_service.add_job(
            name=job_name,
            schedule={"kind": "cron", "expr": schedule},
            payload={"type": "extension_cron", "extension_id": self.id, "callback_name": name},
            description=f"[ext:{self.id}] {description}",
        )
        self._registered_cron.append(job_name)

    # ── Event hooks ────────────────────────────────────────────────

    def register_hook(self, event: str, callback: Callable):
        """Subscribe to a lifecycle event (on_boot, on_chat_message, etc.)."""
        self._event_bus.subscribe(event, callback, self.id)
        self._registered_hooks.append(event)

    # ── Settings ───────────────────────────────────────────────────

    def register_setting(self, schema: dict):
        """Declare a configurable setting for this extension.

        schema: {key, type, default, label, description}
        """
        self._registered_settings.append(schema)
        key = schema.get("key")
        if key and "default" in schema:
            settings = self._load_settings()
            if key not in settings:
                settings[key] = schema["default"]
                self._save_settings(settings)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Read a setting value for this extension."""
        settings = self._load_settings()
        return settings.get(key, default)

    def set_setting(self, key: str, value: Any):
        """Write a setting value for this extension."""
        settings = self._load_settings()
        settings[key] = value
        self._save_settings(settings)

    def _load_settings(self) -> dict:
        if self._settings_file.exists():
            try:
                return json.loads(self._settings_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_settings(self, settings: dict):
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    # ── Data persistence ───────────────────────────────────────────

    def read_data(self, filename: str) -> Optional[str]:
        path = self._data_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else None

    def write_data(self, filename: str, content: str):
        (self._data_dir / filename).write_text(content, encoding="utf-8")

    # ── Logging ────────────────────────────────────────────────────

    def log(self, message: str):
        log.info("[ext:%s] %s", self.id, message)

    # ── Access to core services ────────────────────────────────────

    def get_daemon_ref(self):
        return self._daemon_ref

    def get_tool_registry(self):
        return self._tool_registry

    def get_memory_db(self):
        if self._daemon_ref and hasattr(self._daemon_ref, "memory_db"):
            return self._daemon_ref.memory_db
        return None

    def get_auth_store(self):
        if self._daemon_ref and hasattr(self._daemon_ref, "auth_store"):
            return self._daemon_ref.auth_store
        return None

    def get_media_store(self):
        if self._daemon_ref and hasattr(self._daemon_ref, "media_store"):
            return self._daemon_ref.media_store
        return None

    def save_media(self, data: bytes, filename: str, media_type: str = "image",
                   metadata: Optional[dict] = None, prompt: str = "",
                   params: Optional[dict] = None) -> str:
        """Save generated media through the media store. Returns file path."""
        ms = self.get_media_store()
        if ms:
            return ms.save(
                data=data, filename=filename, media_type=media_type,
                source_node=self.id, prompt=prompt, params=params,
                metadata=metadata,
            )
        out = GHOST_HOME / "media" / media_type / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return str(out)


# ═════════════════════════════════════════════════════════════════════
#  EXTENSION INFO
# ═════════════════════════════════════════════════════════════════════

@dataclass
class ExtensionInfo:
    name: str
    path: str
    manifest: Optional[ExtensionManifest] = None
    enabled: bool = True
    loaded: bool = False
    tools: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    cron_jobs: list = field(default_factory=list)
    hooks: list = field(default_factory=list)
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
            "pages": self.pages,
            "route_count": len(self.routes),
            "cron_jobs": self.cron_jobs,
            "hooks": self.hooks,
            "error": self.error,
            "source": self.source,
        }


# ═════════════════════════════════════════════════════════════════════
#  EXTENSION MANAGER
# ═════════════════════════════════════════════════════════════════════

class ExtensionManager:
    """Discover, load, and manage Ghost extensions."""

    def __init__(self, tool_registry, event_bus: ExtensionEventBus,
                 cron_service=None, cfg: Optional[dict] = None,
                 daemon_ref=None):
        self.tool_registry = tool_registry
        self.event_bus = event_bus
        self.cron_service = cron_service
        self.cfg = cfg or {}
        self.daemon_ref = daemon_ref
        self.extensions: dict[str, ExtensionInfo] = {}
        self._disabled: set[str] = self._load_disabled()
        self._lock = threading.Lock()
        self._install_progress: dict[str, dict] = {}

    def discover_all(self):
        """Scan bundled and user extension directories for EXTENSION.yaml manifests."""
        for source, scan_dir in [("bundled", BUNDLED_EXTENSIONS_DIR), ("user", EXTENSIONS_DIR)]:
            if not scan_dir.is_dir():
                continue
            for item in sorted(scan_dir.iterdir()):
                if not item.is_dir():
                    continue
                manifest_path = item / "EXTENSION.yaml"
                if not manifest_path.exists():
                    manifest_path = item / "EXTENSION.yml"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = ExtensionManifest.from_yaml(manifest_path)
                    self.extensions[manifest.name] = ExtensionInfo(
                        name=manifest.name,
                        path=str(item),
                        manifest=manifest,
                        enabled=manifest.name not in self._disabled,
                        source=source,
                    )
                except Exception as e:
                    self.extensions[item.name] = ExtensionInfo(
                        name=item.name,
                        path=str(item),
                        error=f"Manifest error: {e}",
                        source=source,
                    )

    def load_all(self):
        """Load all discovered and enabled extensions (respecting dependency order)."""
        self.discover_all()
        load_order = self._resolve_load_order()
        for name in load_order:
            info = self.extensions.get(name)
            if info and info.enabled and not info.loaded and not info.error:
                self._load_extension(name)

    def _resolve_load_order(self) -> list[str]:
        """Topological sort on extension_deps for correct load order."""
        graph: dict[str, list[str]] = {}
        for name, info in self.extensions.items():
            deps = []
            if info.manifest and info.manifest.extension_deps:
                deps = [d for d in info.manifest.extension_deps if d in self.extensions]
            graph[name] = deps

        visited = set()
        order = []

        def visit(node):
            if node in visited:
                return
            visited.add(node)
            for dep in graph.get(node, []):
                visit(dep)
            order.append(node)

        for name in graph:
            visit(name)
        return order

    def _load_extension(self, name: str):
        """Load a single extension by name."""
        info = self.extensions.get(name)
        if not info or not info.manifest:
            return

        ext_dir = Path(info.path)
        ext_py = ext_dir / "extension.py"
        if not ext_py.exists():
            info.error = "No extension.py found"
            return

        site_packages = ext_dir / "site-packages"
        if site_packages.is_dir() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))

        api = ExtensionAPI(
            extension_id=name,
            manifest=info.manifest,
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
            cron_service=self.cron_service,
            config=self.cfg,
            daemon_ref=self.daemon_ref,
            ext_path=ext_dir,
        )

        try:
            spec = importlib.util.spec_from_file_location(
                f"ghost_ext_{name}", str(ext_py),
                submodule_search_locations=[str(ext_dir)],
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"ghost_ext_{name}"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register"):
                module.register(api)
            else:
                info.error = "No register() function found"
                return

            info.loaded = True
            info.tools = list(api._registered_tools)
            info.pages = list(api._registered_pages)
            info.routes = list(api._registered_routes)
            info.cron_jobs = list(api._registered_cron)
            info.hooks = list(api._registered_hooks)
            log.info("Extension loaded: %s (tools=%s, pages=%d, routes=%d)",
                     name, info.tools, len(info.pages), len(info.routes))

        except Exception as e:
            info.error = f"{e}\n{traceback.format_exc()[-500:]}"
            log.error("Extension load error (%s): %s", name, e)

    def enable_extension(self, name: str) -> bool:
        info = self.extensions.get(name)
        if not info:
            return False
        self._disabled.discard(name)
        info.enabled = True
        info.error = None
        self._persist_disabled()
        if not info.loaded:
            self._load_extension(name)
        return True

    def disable_extension(self, name: str) -> bool:
        info = self.extensions.get(name)
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
            self.event_bus.unsubscribe_all(name)

            for cron_name in info.cron_jobs:
                if self.cron_service:
                    try:
                        all_jobs = self.cron_service.list_jobs()
                        for job in all_jobs:
                            if job.get("name") == cron_name:
                                self.cron_service.remove_job(job["id"])
                                break
                    except Exception:
                        pass
            keys_to_remove = [k for k in _EXTENSION_CRON_CALLBACKS if k[0] == name]
            for k in keys_to_remove:
                _EXTENSION_CRON_CALLBACKS.pop(k, None)

            info.loaded = False
            info.tools.clear()
            info.pages.clear()
            info.cron_jobs.clear()
            info.hooks.clear()
            mod_key = f"ghost_ext_{name}"
            sys.modules.pop(mod_key, None)
            log.info("Extension disabled: %s", name)

        return True

    def _persist_disabled(self):
        disabled_file = GHOST_HOME / "disabled_extensions.json"
        try:
            disabled_file.write_text(json.dumps(sorted(self._disabled)), encoding="utf-8")
        except Exception as e:
            log.warning("Failed to persist disabled extensions: %s", e)

    def _load_disabled(self) -> set[str]:
        disabled = set(self.cfg.get("disabled_extensions", []))
        disabled_file = GHOST_HOME / "disabled_extensions.json"
        if disabled_file.exists():
            try:
                disabled.update(json.loads(disabled_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return disabled

    @staticmethod
    def _sanitize_name(name: str) -> Optional[str]:
        clean = name.strip().lower()
        if not clean or not re.match(r"^[a-z0-9][a-z0-9._-]*$", clean):
            return None
        if ".." in clean or "/" in clean or "\\" in clean:
            return None
        return clean

    def install_local(self, source_path: str) -> dict:
        """Install an extension from a local directory."""
        src = Path(source_path)
        manifest_path = src / "EXTENSION.yaml"
        if not manifest_path.exists():
            manifest_path = src / "EXTENSION.yml"
        if not manifest_path.exists():
            return {"status": "error", "error": "No EXTENSION.yaml found in source directory"}

        if not (src / "extension.py").exists():
            return {"status": "error", "error": "No extension.py entry point found"}

        try:
            manifest = ExtensionManifest.from_yaml(manifest_path)
        except Exception as e:
            return {"status": "error", "error": f"Invalid manifest: {e}"}

        safe_name = self._sanitize_name(manifest.name)
        if not safe_name:
            return {"status": "error", "error": f"Invalid extension name: {manifest.name!r}"}
        manifest.name = safe_name

        dest = EXTENSIONS_DIR / safe_name
        if dest.exists():
            shutil.rmtree(dest)

        def _ignore_git(directory, contents):
            return [".git"] if ".git" in contents else []

        shutil.copytree(src, dest, ignore=_ignore_git)

        req_file = dest / "requirements.txt"
        dep_result = None
        if req_file.exists():
            dep_result = self._install_deps(safe_name, req_file)

        self.extensions[safe_name] = ExtensionInfo(
            name=safe_name,
            path=str(dest),
            manifest=manifest,
            enabled=True,
            source="user",
        )
        self._load_extension(safe_name)

        info = self.extensions[safe_name]
        result = {
            "status": "ok",
            "name": safe_name,
            "tools": info.tools,
            "pages": [p.get("id") for p in info.pages],
        }
        if info.error:
            result["warning"] = f"Extension installed but failed to load: {info.error}"
        if dep_result and dep_result.get("status") == "error":
            result["dep_warning"] = dep_result.get("error", "Dependency install failed")
        return result

    def install_from_github(self, repo_url: str, subdir: str = "") -> dict:
        """Install an extension from a GitHub repository."""
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

    def uninstall_extension(self, name: str) -> bool:
        info = self.extensions.get(name)
        if not info:
            return False
        if info.source == "bundled":
            log.warning("Cannot uninstall bundled extension: %s", name)
            return False

        if info.loaded:
            self.disable_extension(name)

        mod_name = f"ghost_ext_{name}"
        sys.modules.pop(mod_name, None)

        ext_path = Path(info.path)
        if ext_path.exists():
            shutil.rmtree(ext_path, ignore_errors=True)

        del self.extensions[name]
        self._disabled.discard(name)
        self._persist_disabled()
        return True

    def _install_deps(self, name: str, req_file: Path) -> dict:
        target = EXTENSIONS_DIR / name / "site-packages"
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
                log.error("Extension dep install failed for %s: %s", name, error_msg)
                self._install_progress[name] = {"status": "failed", "error": error_msg}
                return {"status": "error", "error": error_msg}
            self._install_progress[name] = {"status": "completed"}
            return {"status": "ok"}
        except subprocess.TimeoutExpired:
            self._install_progress[name] = {"status": "timeout"}
            return {"status": "error", "error": "Install timed out (600s)"}
        except Exception as e:
            self._install_progress[name] = {"status": "failed", "error": str(e)}
            return {"status": "error", "error": str(e)}

    def list_extensions(self, category: Optional[str] = None) -> list[dict]:
        exts = []
        for info in self.extensions.values():
            if category and info.manifest and info.manifest.category != category:
                continue
            exts.append(info.to_dict())
        return sorted(exts, key=lambda e: (e.get("source", ""), e.get("name", "")))

    def get_extension(self, name: str) -> Optional[ExtensionInfo]:
        return self.extensions.get(name)

    def get_all_pages(self) -> list[dict]:
        """Return all pages registered by loaded extensions."""
        pages = []
        for info in self.extensions.values():
            if info.loaded and info.enabled:
                pages.extend(info.pages)
        return pages

    def get_all_routes(self) -> list:
        """Return all Flask blueprints registered by loaded extensions."""
        routes = []
        for info in self.extensions.values():
            if info.loaded and info.enabled:
                routes.extend(info.routes)
        return routes

    def get_extension_tools(self) -> list[str]:
        tools = []
        for info in self.extensions.values():
            if info.loaded and info.enabled:
                tools.extend(info.tools)
        return tools

    def get_extension_dir(self, name: str) -> Optional[Path]:
        info = self.extensions.get(name)
        if info:
            return Path(info.path)
        return None

    @staticmethod
    def _safe_ext_name(name: str) -> str:
        """Sanitize extension name for filesystem paths (prevent traversal)."""
        import re
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not sanitized or sanitized.startswith("."):
            raise ValueError(f"Invalid extension name: {name!r}")
        return sanitized

    def get_settings(self, name: str) -> dict:
        safe_name = self._safe_ext_name(name)
        settings_file = GHOST_HOME / "extension_settings" / f"{safe_name}.json"
        if settings_file.exists():
            try:
                return json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_settings(self, name: str, settings: dict):
        safe_name = self._safe_ext_name(name)
        settings_dir = GHOST_HOME / "extension_settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file = settings_dir / f"{safe_name}.json"
        settings_file.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    def get_install_progress(self, name: str) -> dict:
        return self._install_progress.get(name, {})

    def get_unified_view(self) -> list[dict]:
        """Return a unified list of extensions and nodes (for convergence).

        Nodes from NodeManager are represented with category='node' alongside
        regular extensions. This provides a single view for the dashboard.
        """
        items = []
        for info in self.extensions.values():
            d = info.to_dict()
            d["kind"] = "extension"
            items.append(d)

        if self.daemon_ref and hasattr(self.daemon_ref, "node_manager") and self.daemon_ref.node_manager:
            for node_info in self.daemon_ref.node_manager.nodes.values():
                nd = node_info.to_dict()
                nd["kind"] = "node"
                if nd.get("manifest"):
                    nd["manifest"]["category"] = "node"
                items.append(nd)

        return sorted(items, key=lambda x: (x.get("kind", ""), x.get("name", "")))


# ═════════════════════════════════════════════════════════════════════
#  TOOL BUILDER
# ═════════════════════════════════════════════════════════════════════

def build_extension_manager_tools(ext_manager: ExtensionManager):
    """Build tools for managing Ghost extensions from the LLM tool loop."""

    def execute_list(category: str = "", **_kw):
        exts = ext_manager.list_extensions(category=category or None)
        return json.dumps({"status": "ok", "count": len(exts), "extensions": exts}, default=str)

    def execute_install(source: str = "", **_kw):
        if not source:
            return json.dumps({"status": "error", "error": "source path or URL required"})
        if source.startswith("http") and "github" in source:
            result = ext_manager.install_from_github(source)
        else:
            result = ext_manager.install_local(source)
        return json.dumps(result, default=str)

    def execute_enable(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "extension name required"})
        ok = ext_manager.enable_extension(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Enabled {name}" if ok else f"Extension not found: {name}"})

    def execute_disable(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "extension name required"})
        ok = ext_manager.disable_extension(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Disabled {name}" if ok else f"Extension not found: {name}"})

    def execute_uninstall(name: str = "", **_kw):
        if not name:
            return json.dumps({"status": "error", "error": "extension name required"})
        ok = ext_manager.uninstall_extension(name)
        return json.dumps({"status": "ok" if ok else "error",
                           "message": f"Uninstalled {name}" if ok else f"Cannot uninstall: {name}"})

    return [
        {
            "name": "extensions_list",
            "description": (
                "List all installed Ghost extensions (feature plugins). "
                "Optionally filter by category: integration, dashboard, tool, channel, automation, monitoring, utility."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category",
                        "enum": EXTENSION_CATEGORIES,
                    },
                },
            },
            "execute": execute_list,
        },
        {
            "name": "extensions_install",
            "description": "Install a Ghost extension from a local path or GitHub URL.",
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
            "name": "extensions_enable",
            "description": "Enable a disabled Ghost extension.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Extension name"}},
                "required": ["name"],
            },
            "execute": execute_enable,
        },
        {
            "name": "extensions_disable",
            "description": "Disable a Ghost extension (keeps it installed but unloads tools/routes).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Extension name"}},
                "required": ["name"],
            },
            "execute": execute_disable,
        },
        {
            "name": "extensions_uninstall",
            "description": "Uninstall a user-installed Ghost extension (cannot uninstall bundled).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Extension name"}},
                "required": ["name"],
            },
            "execute": execute_uninstall,
        },
    ]
