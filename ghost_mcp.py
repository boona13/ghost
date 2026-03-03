"""
Ghost MCP (Model Context Protocol) Client

MCP is an open protocol for extending AI capabilities with external tools.
This module lets Ghost connect to MCP servers and use their tools.

Security:
- Process isolation via subprocess with separate process groups
- Command validation preventing shell injection
- Tool-level access control
- Timeout protection
"""

import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("ghost.mcp")
DEFAULT_MCP_TIMEOUT = 30.0


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout: float = DEFAULT_MCP_TIMEOUT
    allowed_tools: Optional[List[str]] = None
    blocked_tools: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "MCPServerConfig":
        return cls(
            name=name,
            command=d.get("command", ""),
            args=d.get("args", []),
            env=d.get("env", {}),
            enabled=d.get("enabled", True),
            timeout=d.get("timeout", DEFAULT_MCP_TIMEOUT),
            allowed_tools=d.get("allowed_tools"),
            blocked_tools=d.get("blocked_tools", []),
        )

    def validate(self) -> tuple[bool, str]:
        if not self.name or not re.match(r'^[a-zA-Z0-9_-]+$', self.name):
            return False, f"Invalid server name: {self.name}"
        if not self.command:
            return False, "Command is required"
        if re.search(r'[;&|`$(){}[\\]]', self.command):
            return False, "Command contains forbidden characters"
        return True, ""


@dataclass
class MCPConnection:
    """Active connection to an MCP server."""
    config: MCPServerConfig
    process: subprocess.Popen
    request_id: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    tools_cache: Optional[List[Dict[str, Any]]] = None
    connected_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def is_alive(self) -> bool:
        return self.process.poll() is None


class MCPClientManager:
    """Manages connections to MCP servers. Thread-safe.

    Features:
    - Auto-connect enabled servers on startup
    - Background health monitor with auto-reconnect for dead servers
    - Process isolation via subprocess with separate process groups
    """

    HEALTH_CHECK_INTERVAL = 30.0  # seconds between health checks
    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_BACKOFF = 5.0  # seconds between reconnect attempts

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, **kwargs):
        self.cfg = cfg or {}
        self._servers: Dict[str, MCPConnection] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp_")
        self._shutdown = False
        self._server_configs: Dict[str, MCPServerConfig] = {}
        self._reconnect_attempts: Dict[str, int] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        servers_cfg = self.cfg.get("mcp_servers", {})
        for name, scfg in servers_cfg.items():
            if isinstance(scfg, dict):
                self._server_configs[name] = MCPServerConfig.from_dict(name, scfg)

    def _validate_command(self, cmd: str) -> tuple[bool, str]:
        if not cmd:
            return False, "Empty command"
        if re.search(r'[;&|`$(){}[\\]<>]', cmd):
            return False, "Command contains shell metacharacters"
        if not re.match(r'^[a-zA-Z0-9_./\\~-]+$', cmd):
            return False, "Invalid characters in command"
        return True, ""

    def connect(self, server_name: str, config_override: Optional[Dict[str, Any]] = None, **kwargs) -> Future:
        future = Future()

        def _do_connect():
            try:
                with self._lock:
                    if self._shutdown:
                        future.set_result({"ok": False, "error": "MCP manager is shut down"})
                        return
                    if server_name in self._servers:
                        self._disconnect_one(server_name)

                if config_override:
                    config = MCPServerConfig.from_dict(server_name, config_override)
                elif server_name in self._server_configs:
                    config = self._server_configs[server_name]
                else:
                    future.set_result({"ok": False, "error": f"Unknown server: {server_name}"})
                    return

                valid, err = config.validate()
                if not valid:
                    future.set_result({"ok": False, "error": err})
                    return

                cmd_valid, cmd_err = self._validate_command(config.command)
                if not cmd_valid:
                    future.set_result({"ok": False, "error": f"Command validation failed: {cmd_err}"})
                    return

                env = os.environ.copy()
                env.update(config.env)
                cmd_list = [config.command] + config.args
                log.info(f"Starting MCP server \'{server_name}\': {' '.join(cmd_list)}")

                try:
                    process = subprocess.Popen(
                        cmd_list,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=env,
                        start_new_session=True,
                    )
                except FileNotFoundError:
                    future.set_result({"ok": False, "error": f"Command not found: {config.command}"})
                    return
                except PermissionError:
                    future.set_result({"ok": False, "error": f"Permission denied: {config.command}"})
                    return

                conn = MCPConnection(config=config, process=process)
                with self._lock:
                    self._servers[server_name] = conn

                init_result = self._send_request(conn, "initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Ghost", "version": "1.0.0"},
                }, timeout=config.timeout)

                if not init_result.get("ok"):
                    self._disconnect_one(server_name)
                    future.set_result({"ok": False, "error": f"Initialize failed: {init_result.get('error', 'unknown')}"})
                    return

                # MCP spec: client MUST send initialized notification before other requests
                try:
                    notify = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
                    conn.process.stdin.write(notify)
                    conn.process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    log.warning(f"Failed to send initialized notification to '{server_name}': {e}")

                tools_result = self._send_request(conn, "tools/list", {}, timeout=config.timeout)
                if tools_result.get("ok"):
                    conn.tools_cache = tools_result.get("result", {}).get("tools", [])

                log.info(f"MCP server \'{server_name}\' connected with {len(conn.tools_cache or [])} tools")

                future.set_result({
                    "ok": True,
                    "tools": conn.tools_cache or [],
                    "server": server_name,
                })

            except Exception as e:
                log.exception(f"Error connecting to MCP server {server_name}")
                future.set_result({"ok": False, "error": str(e)})

        self._executor.submit(_do_connect)
        return future

    def _send_request(self, conn, method: str, params: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        with conn.lock:
            if not conn.is_alive():
                return {"ok": False, "error": "Server process is not running"}
            conn.request_id += 1
            req_id = conn.request_id

        request = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        request_line = json.dumps(request) + "\n"

        try:
            if conn.process.stdin is None:
                return {"ok": False, "error": "Server stdin is closed"}
            conn.process.stdin.write(request_line)
            conn.process.stdin.flush()
        except BrokenPipeError:
            return {"ok": False, "error": "Server process closed stdin (broken pipe)"}
        except OSError as e:
            return {"ok": False, "error": f"IO error: {e}"}

        conn.last_used = time.time()
        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                if conn.process.stdout is None:
                    return {"ok": False, "error": "Server stdout is closed"}
                import select
                ready, _, _ = select.select([conn.process.stdout], [], [], 0.5)
                if not ready:
                    if not conn.is_alive():
                        return {"ok": False, "error": "Server process died"}
                    continue
                line = conn.process.stdout.readline()
                if not line:
                    if not conn.is_alive():
                        return {"ok": False, "error": "Server process died"}
                    continue
                try:
                    response = json.loads(line)
                    if response.get("id") == req_id:
                        if "error" in response:
                            return {"ok": False, "error": response["error"]}
                        return {"ok": True, "result": response.get("result", {})}
                except json.JSONDecodeError:
                    log.warning(f"Invalid JSON from MCP server: {line[:200]}")
                    continue
            return {"ok": False, "error": f"Timeout after {timeout}s"}
        except Exception as e:
            log.exception("Error reading MCP response")
            return {"ok": False, "error": f"Read error: {e}"}

    def _disconnect_one(self, server_name: str) -> None:
        if server_name not in self._servers:
            return
        conn = self._servers.pop(server_name)
        log.info(f"Disconnecting MCP server \'{server_name}\'")
        try:
            if conn.is_alive() and conn.process.stdin:
                try:
                    conn.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 9999, "method": "shutdown"}) + "\n")
                    conn.process.stdin.flush()
                    conn.process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            time.sleep(0.1)
            if conn.is_alive():
                try:
                    conn.process.terminate()
                    conn.process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(conn.process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        conn.process.kill()
                        conn.process.wait(timeout=1.0)
                    except Exception:
                        pass
        except Exception as e:
            log.warning(f"Error disconnecting {server_name}: {e}")

    def disconnect(self, server_name: str, **kwargs) -> Future:
        future = Future()
        def _do_disconnect():
            try:
                with self._lock:
                    self._disconnect_one(server_name)
                future.set_result({"ok": True})
            except Exception as e:
                future.set_result({"ok": False, "error": str(e)})
        self._executor.submit(_do_disconnect)
        return future

    def list_servers(self, **kwargs) -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for name, config in self._server_configs.items():
                conn = self._servers.get(name)
                alive = conn is not None and conn.is_alive()
                entry = {
                    "name": name,
                    "enabled": config.enabled,
                    "connected": alive,
                    "tool_count": len(conn.tools_cache) if conn and conn.tools_cache else 0,
                    "command": config.command,
                    "args": config.args,
                }
                if conn:
                    entry["connected_at"] = conn.connected_at
                    entry["last_used"] = conn.last_used
                    entry["idle_seconds"] = round(time.time() - conn.last_used, 1)
                    entry["request_count"] = conn.request_id
                result.append(entry)
            return result

    def list_tools(self, server_name: Optional[str] = None, **kwargs) -> Future:
        future = Future()
        def _do_list():
            try:
                with self._lock:
                    if server_name:
                        conn = self._servers.get(server_name)
                        if not conn:
                            future.set_result({"ok": False, "error": f"Server not connected: {server_name}"})
                            return
                        if not conn.is_alive():
                            future.set_result({"ok": False, "error": f"Server not running: {server_name}"})
                            return
                        tools_result = self._send_request(conn, "tools/list", {}, timeout=conn.config.timeout)
                        if tools_result.get("ok"):
                            conn.tools_cache = tools_result.get("result", {}).get("tools", [])
                            future.set_result({"ok": True, "tools": conn.tools_cache, "server": server_name})
                        else:
                            future.set_result(tools_result)
                    else:
                        all_tools = []
                        for name, conn in self._servers.items():
                            if conn.is_alive():
                                tools_result = self._send_request(conn, "tools/list", {}, timeout=conn.config.timeout)
                                if tools_result.get("ok"):
                                    tools = tools_result.get("result", {}).get("tools", [])
                                    conn.tools_cache = tools
                                    for t in tools:
                                        t["_server"] = name
                                    all_tools.extend(tools)
                        future.set_result({"ok": True, "tools": all_tools})
            except Exception as e:
                log.exception("Error listing MCP tools")
                future.set_result({"ok": False, "error": str(e)})
        self._executor.submit(_do_list)
        return future

    def _is_tool_allowed(self, conn, tool_name: str) -> bool:
        config = conn.config
        if tool_name in config.blocked_tools:
            return False
        if config.allowed_tools is not None:
            return tool_name in config.allowed_tools
        return True

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any], **kwargs) -> Future:
        future = Future()
        def _do_call():
            try:
                with self._lock:
                    conn = self._servers.get(server_name)
                    if not conn:
                        future.set_result({"ok": False, "error": f"Server not connected: {server_name}"})
                        return
                    if not conn.is_alive():
                        future.set_result({"ok": False, "error": f"Server not running: {server_name}"})
                        return
                    if not self._is_tool_allowed(conn, tool_name):
                        future.set_result({"ok": False, "error": f"Tool \'{tool_name}\' is not allowed"})
                        return
                result = self._send_request(conn, "tools/call", {"name": tool_name, "arguments": arguments}, timeout=conn.config.timeout)
                future.set_result(result)
            except Exception as e:
                log.exception(f"Error calling MCP tool {tool_name}")
                future.set_result({"ok": False, "error": str(e)})
        self._executor.submit(_do_call)
        return future

    def add_server(self, name: str, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new server config at runtime. Does NOT persist to config.json."""
        config = MCPServerConfig.from_dict(name, config_dict)
        valid, err = config.validate()
        if not valid:
            return {"ok": False, "error": err}
        with self._lock:
            self._server_configs[name] = config
        log.info(f"Added MCP server config '{name}'")
        return {"ok": True, "server": name}

    def remove_server(self, name: str) -> Dict[str, Any]:
        """Remove a server config and disconnect if connected."""
        with self._lock:
            if name not in self._server_configs:
                return {"ok": False, "error": f"Unknown server: {name}"}
            self._disconnect_one(name)
            del self._server_configs[name]
            self._reconnect_attempts.pop(name, None)
        log.info(f"Removed MCP server config '{name}'")
        return {"ok": True, "server": name}

    def auto_connect(self) -> Dict[str, Any]:
        """Connect all enabled servers. Called on daemon startup."""
        results = {}
        enabled = [
            name for name, cfg in self._server_configs.items()
            if cfg.enabled
        ]
        if not enabled:
            log.info("No enabled MCP servers to auto-connect")
            return results

        log.info(f"Auto-connecting {len(enabled)} MCP server(s): {', '.join(enabled)}")
        futures = {}
        for name in enabled:
            futures[name] = self.connect(name)

        for name, future in futures.items():
            try:
                result = future.result(timeout=60.0)
                results[name] = result
                if result.get("ok"):
                    tool_count = len(result.get("tools", []))
                    log.info(f"  [mcp] Auto-connected '{name}' ({tool_count} tools)")
                    self._reconnect_attempts[name] = 0
                else:
                    log.warning(f"  [mcp] Auto-connect failed for '{name}': {result.get('error')}")
            except Exception as e:
                err_msg = str(e) or f"{type(e).__name__} (no message)"
                results[name] = {"ok": False, "error": err_msg}
                log.warning(f"  [mcp] Auto-connect error for '{name}': {err_msg}")

        return results

    def health_check(self) -> Dict[str, Any]:
        """Check health of all connected servers. Returns per-server status."""
        report = {}
        with self._lock:
            for name, conn in list(self._servers.items()):
                alive = conn.is_alive()
                idle_seconds = time.time() - conn.last_used
                report[name] = {
                    "alive": alive,
                    "connected_at": conn.connected_at,
                    "last_used": conn.last_used,
                    "idle_seconds": round(idle_seconds, 1),
                    "tool_count": len(conn.tools_cache) if conn.tools_cache else 0,
                    "request_count": conn.request_id,
                }

            for name, cfg in self._server_configs.items():
                if name not in report and cfg.enabled:
                    report[name] = {
                        "alive": False,
                        "connected_at": None,
                        "last_used": None,
                        "idle_seconds": None,
                        "tool_count": 0,
                        "request_count": 0,
                        "note": "enabled but not connected",
                    }
        return report

    def reconnect_dead(self) -> Dict[str, Any]:
        """Reconnect servers that were connected but whose process died."""
        reconnected = {}
        with self._lock:
            dead_servers = [
                name for name, conn in self._servers.items()
                if not conn.is_alive()
            ]

        for name in dead_servers:
            attempts = self._reconnect_attempts.get(name, 0)
            if attempts >= self.MAX_RECONNECT_ATTEMPTS:
                log.warning(f"[mcp] Giving up reconnecting '{name}' after {attempts} attempts")
                reconnected[name] = {"ok": False, "error": "max reconnect attempts reached"}
                continue

            self._reconnect_attempts[name] = attempts + 1
            log.info(f"[mcp] Reconnecting dead server '{name}' (attempt {attempts + 1}/{self.MAX_RECONNECT_ATTEMPTS})")

            with self._lock:
                self._disconnect_one(name)

            try:
                future = self.connect(name)
                result = future.result(timeout=60.0)
                reconnected[name] = result
                if result.get("ok"):
                    self._reconnect_attempts[name] = 0
                    log.info(f"[mcp] Reconnected '{name}' successfully")
                else:
                    log.warning(f"[mcp] Reconnect failed for '{name}': {result.get('error')}")
            except Exception as e:
                reconnected[name] = {"ok": False, "error": str(e)}
                log.warning(f"[mcp] Reconnect error for '{name}': {e}")

        return reconnected

    def start_monitor(self) -> None:
        """Start background health monitor thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="mcp_health_monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        log.info("MCP health monitor started")

    def _monitor_loop(self) -> None:
        """Background loop: periodically check health and reconnect dead servers."""
        while not self._shutdown:
            time.sleep(self.HEALTH_CHECK_INTERVAL)
            if self._shutdown:
                break
            try:
                with self._lock:
                    dead = [
                        name for name, conn in self._servers.items()
                        if not conn.is_alive()
                    ]
                if dead:
                    log.info(f"[mcp] Health monitor detected {len(dead)} dead server(s): {', '.join(dead)}")
                    self.reconnect_dead()
            except Exception as e:
                log.warning(f"[mcp] Health monitor error: {e}")

    def shutdown(self, **kwargs) -> None:
        log.info("Shutting down MCP client manager")
        self._shutdown = True
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
        with self._lock:
            for name in list(self._servers.keys()):
                self._disconnect_one(name)
        self._executor.shutdown(wait=True)
        log.info("MCP client manager shut down complete")


def build_mcp_tools(cfg: Dict[str, Any], mcp_manager: Optional["MCPClientManager"] = None, **kwargs):
    """Build MCP tool definitions for Ghost daemon."""
    if mcp_manager is None:
        mcp_manager = MCPClientManager(cfg)

    def _result_from_future(future, timeout: float = 30.0):
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            return {"ok": False, "error": "Operation timed out"}

    def _list_tools_filtered(mcp_mgr, server_name: Optional[str] = None):
        """List tools with filtering applied."""
        result = _result_from_future(mcp_mgr.list_tools(server_name))
        if not result.get("ok"):
            return result
        tools = result.get("tools", [])
        if server_name:
            conn = mcp_mgr._servers.get(server_name)
            if conn:
                filtered = []
                for t in tools:
                    name = t.get("name", "")
                    if mcp_mgr._is_tool_allowed(conn, name):
                        filtered.append(t)
                result["tools"] = filtered
        return result

    tools = []

    tools.append({
        "name": "mcp_connect",
        "description": "Connect to an MCP (Model Context Protocol) server. MCP servers provide external tools like filesystem access, browser automation, database queries, etc. Example: mcp_connect with server_name='filesystem' to connect to a configured filesystem MCP server.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server to connect to (must be configured in config)"
                },
                "config_override": {
                    "type": "object",
                    "description": "Optional: override configuration. Keys: command, args (list), env (dict), timeout (number), allowed_tools (list), blocked_tools (list)"
                }
            },
            "required": ["server_name"]
        },
        "execute": lambda server_name, config_override=None, **kw: _result_from_future(
            mcp_manager.connect(server_name, config_override, **kw)
        )
    })

    tools.append({
        "name": "mcp_disconnect",
        "description": "Disconnect from an MCP server and terminate its process.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server to disconnect from"
                }
            },
            "required": ["server_name"]
        },
        "execute": lambda server_name, **kw: _result_from_future(mcp_manager.disconnect(server_name, **kw))
    })

    tools.append({
        "name": "mcp_list_servers",
        "description": "List all configured MCP servers and their connection status. Returns server names, whether they're enabled, connected, and how many tools each provides.",
        "parameters": {"type": "object", "properties": {}},
        "execute": lambda **kw: mcp_manager.list_servers(**kw)
    })

    tools.append({
        "name": "mcp_list_tools",
        "description": "List available tools from connected MCP servers. If server_name is provided, lists only tools from that server. Otherwise lists tools from all connected servers. Tools returned include name, description, and input schema.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Optional: specific server to list tools from. If omitted, lists tools from all connected servers."
                }
            }
        },
        "execute": lambda server_name=None, **kw: _list_tools_filtered(mcp_manager, server_name)
    })

    tools.append({
        "name": "mcp_call_tool",
        "description": "Call a tool on an MCP server. The tool must be from a connected server and must be in the allowed list (or not in the blocked list). Returns the tool's output.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server that provides this tool"
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to call"
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the tool (must match the tool's input schema)"
                }
            },
            "required": ["server_name", "tool_name", "arguments"]
        },
        "execute": lambda server_name, tool_name, arguments, **kw: _result_from_future(
            mcp_manager.call_tool(server_name, tool_name, arguments, **kw)
        )
    })

    def _add_server(name, command, args=None, env=None, enabled=True,
                    timeout=30, allowed_tools=None, blocked_tools=None,
                    auto_connect=True, **kw):
        server_cfg = {
            "command": command,
            "args": args or [],
            "env": env or {},
            "enabled": enabled,
            "timeout": timeout,
            "allowed_tools": allowed_tools,
            "blocked_tools": blocked_tools or [],
        }
        result = mcp_manager.add_server(name, server_cfg)
        if not result.get("ok"):
            return result

        try:
            from ghost import load_config, save_config
            cfg_data = load_config()
            if "mcp_servers" not in cfg_data:
                cfg_data["mcp_servers"] = {}
            cfg_data["mcp_servers"][name] = server_cfg
            save_config(cfg_data)
        except Exception as e:
            log.warning(f"Failed to persist MCP server '{name}' to config: {e}")

        if auto_connect and enabled:
            connect_result = _result_from_future(mcp_manager.connect(name))
            result["connect_result"] = connect_result
        return result

    tools.append({
        "name": "mcp_add_server",
        "description": "Add a new MCP server configuration and optionally connect to it. "
            "The server is persisted to Ghost's config so it survives restarts. "
            "Use this to integrate new external tools from MCP-compatible servers. "
            "Example: mcp_add_server(name='filesystem', command='npx', args=['-y', '@modelcontextprotocol/server-filesystem', '/tmp'])",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for this server (alphanumeric, hyphens, underscores)"
                },
                "command": {
                    "type": "string",
                    "description": "Command to start the MCP server (e.g. 'npx', 'node', 'python')"
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command arguments (e.g. ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'])"
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment variables for the server process"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Whether the server is enabled (default: true)"
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds (default: 30)"
                },
                "auto_connect": {
                    "type": "boolean",
                    "description": "Connect immediately after adding (default: true)"
                }
            },
            "required": ["name", "command"]
        },
        "execute": _add_server
    })

    def _remove_server(name, **kw):
        result = mcp_manager.remove_server(name)
        if result.get("ok"):
            try:
                from ghost import load_config, save_config
                cfg_data = load_config()
                mcp_servers = cfg_data.get("mcp_servers", {})
                if name in mcp_servers:
                    del mcp_servers[name]
                    cfg_data["mcp_servers"] = mcp_servers
                    save_config(cfg_data)
            except Exception as e:
                log.warning(f"Failed to remove MCP server '{name}' from config: {e}")
        return result

    tools.append({
        "name": "mcp_remove_server",
        "description": "Remove an MCP server. Disconnects if connected and removes from config permanently.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the MCP server to remove"
                }
            },
            "required": ["name"]
        },
        "execute": _remove_server
    })

    return tools
