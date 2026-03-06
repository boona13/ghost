"""
GHOST Plugin System

Plugins are Python modules that extend Ghost with new tools, hooks, and capabilities.
Drop a plugin folder into ~/.ghost/plugins/ with an __init__.py that exports register(api).
"""

import os
import sys
import importlib
import importlib.util
import traceback
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional


GHOST_HOME = Path.home() / ".ghost"
PLUGINS_DIR = GHOST_HOME / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════
#  HOOK SYSTEM
# ═════════════════════════════════════════════════════════════════════

VALID_HOOKS = [
    "before_analyze",      # (content_type, text) -> modified text or None
    "after_analyze",       # (content_type, text, result) -> modified result or None
    "before_tool_call",    # (tool_name, args) -> modified args or None
    "after_tool_call",     # (tool_name, args, result) -> modified result or None
    "on_classify",         # (text) -> content_type override or None
    "on_screenshot",       # (image_path) -> None
    "on_feed_append",      # (entry) -> modified entry or None
    "on_startup",          # () -> None
    "on_shutdown",         # () -> None
    "on_action",           # (action_id, source, ctype) -> None
    "on_session_end",      # (session_entries: list[dict]) -> None
]


class HookRunner:
    """Manages and runs lifecycle hooks registered by plugins."""

    def __init__(self):
        self._hooks: Dict[str, List[tuple]] = {h: [] for h in VALID_HOOKS}

    def register(self, hook_name, handler, priority=0, plugin_id="unknown"):
        if hook_name not in self._hooks:
            raise ValueError(f"Unknown hook: '{hook_name}'. Valid: {VALID_HOOKS}")
        self._hooks[hook_name].append((priority, plugin_id, handler))
        self._hooks[hook_name].sort(key=lambda x: -x[0])

    def run(self, hook_name, *args, **kwargs):
        """
        Run all handlers for a hook. For modifying hooks, each handler
        can return a modified value which is passed to the next handler.
        Returns the final value (or None if no handler modified it).
        """
        result = None
        for priority, plugin_id, handler in self._hooks.get(hook_name, []):
            try:
                ret = handler(*args, **kwargs)
                if ret is not None:
                    result = ret
                    if len(args) > 0:
                        args = (ret,) + args[1:]
            except Exception as e:
                print(f"  [plugin:{plugin_id}] Hook {hook_name} error: {e}")
        return result

    def run_void(self, hook_name, *args, **kwargs):
        """Run all handlers without collecting return values."""
        for priority, plugin_id, handler in self._hooks.get(hook_name, []):
            try:
                handler(*args, **kwargs)
            except Exception as e:
                print(f"  [plugin:{plugin_id}] Hook {hook_name} error: {e}")


# ═════════════════════════════════════════════════════════════════════
#  PLUGIN API (exposed to plugins)
# ═════════════════════════════════════════════════════════════════════

class PluginAPI:
    """API surface exposed to each plugin during registration."""

    def __init__(self, plugin_id, tool_registry, hook_runner, config, memory_db=None):
        self.id = plugin_id
        self._tool_registry = tool_registry
        self._hook_runner = hook_runner
        self._config = config
        self._memory = memory_db
        self._registered_tools = []
        self._registered_hooks = []

    @property
    def config(self):
        """Read-only access to ghost config."""
        return dict(self._config)

    @property
    def memory(self):
        """Access to the memory database (if available)."""
        return self._memory

    @property
    def ghost_home(self):
        return GHOST_HOME

    def register_tool(self, tool_def):
        """Register a new tool. tool_def must have: name, description, parameters, execute."""
        required = {"name", "description", "parameters", "execute"}
        missing = required - set(tool_def.keys())
        if missing:
            raise ValueError(f"Tool definition missing keys: {missing}")
        self._tool_registry.register(tool_def)
        self._registered_tools.append(tool_def["name"])

    def on(self, hook_name, handler, priority=0):
        """Register a lifecycle hook handler."""
        self._hook_runner.register(hook_name, handler, priority=priority, plugin_id=self.id)
        self._registered_hooks.append(hook_name)

    def log(self, message):
        """Print a log message tagged with the plugin ID."""
        print(f"  [plugin:{self.id}] {message}")

    def read_plugin_data(self, filename):
        """Read a file from the plugin's data directory."""
        data_dir = GHOST_HOME / "plugin_data" / self.id
        path = data_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def write_plugin_data(self, filename, content):
        """Write a file to the plugin's data directory."""
        data_dir = GHOST_HOME / "plugin_data" / self.id
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / filename).write_text(content, encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════
#  PLUGIN LOADER
# ═════════════════════════════════════════════════════════════════════

class PluginInfo:
    """Metadata about a loaded plugin."""
    __slots__ = ("id", "path", "tools", "hooks", "error")

    def __init__(self, id, path, tools=None, hooks=None, error=None):
        self.id = id
        self.path = path
        self.tools = tools or []
        self.hooks = hooks or []
        self.error = error


class PluginLoader:
    """Discovers and loads plugins from ~/.ghost/plugins/."""

    def __init__(self, tool_registry, hook_runner, config, memory_db=None):
        self.tool_registry = tool_registry
        self.hook_runner = hook_runner
        self.config = config
        self.memory_db = memory_db
        self.plugins: Dict[str, PluginInfo] = {}

    def load_all(self):
        """Discover and load all plugins."""
        if not PLUGINS_DIR.is_dir():
            return

        for item in sorted(PLUGINS_DIR.iterdir()):
            if item.is_dir() and (item / "__init__.py").exists():
                self._load_plugin(item)
            elif item.is_file() and item.suffix == ".py" and item.stem != "__init__":
                self._load_single_file_plugin(item)

    def _load_plugin(self, plugin_dir):
        """Load a plugin from a directory with __init__.py."""
        plugin_id = plugin_dir.name
        init_file = plugin_dir / "__init__.py"

        api = PluginAPI(
            plugin_id=plugin_id,
            tool_registry=self.tool_registry,
            hook_runner=self.hook_runner,
            config=self.config,
            memory_db=self.memory_db,
        )

        try:
            spec = importlib.util.spec_from_file_location(
                f"ghost_plugin_{plugin_id}", str(init_file),
                submodule_search_locations=[str(plugin_dir)]
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"ghost_plugin_{plugin_id}"] = module
            spec.loader.exec_module(module)

            if hasattr(module, "register"):
                module.register(api)
            elif hasattr(module, "plugin") and hasattr(module.plugin, "register"):
                module.plugin.register(api)
            else:
                self.plugins[plugin_id] = PluginInfo(
                    id=plugin_id, path=str(plugin_dir),
                    error="No register() function found"
                )
                return

            self.plugins[plugin_id] = PluginInfo(
                id=plugin_id,
                path=str(plugin_dir),
                tools=list(api._registered_tools),
                hooks=list(api._registered_hooks),
            )
            print(f"  Loaded plugin: {plugin_id} "
                  f"(tools: {len(api._registered_tools)}, hooks: {len(api._registered_hooks)})")

        except Exception as e:
            self.plugins[plugin_id] = PluginInfo(
                id=plugin_id, path=str(plugin_dir),
                error=f"{e}\n{traceback.format_exc()[-300:]}"
            )
            print(f"  Plugin error ({plugin_id}): {e}")

    def _load_single_file_plugin(self, plugin_file):
        """Load a single .py file as a plugin."""
        plugin_id = plugin_file.stem

        api = PluginAPI(
            plugin_id=plugin_id,
            tool_registry=self.tool_registry,
            hook_runner=self.hook_runner,
            config=self.config,
            memory_db=self.memory_db,
        )

        try:
            spec = importlib.util.spec_from_file_location(
                f"ghost_plugin_{plugin_id}", str(plugin_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "register"):
                module.register(api)

            self.plugins[plugin_id] = PluginInfo(
                id=plugin_id,
                path=str(plugin_file),
                tools=list(api._registered_tools),
                hooks=list(api._registered_hooks),
            )
        except Exception as e:
            self.plugins[plugin_id] = PluginInfo(
                id=plugin_id, path=str(plugin_file),
                error=str(e)
            )

    def list_plugins(self):
        return list(self.plugins.values())

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)
