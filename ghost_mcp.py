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
    """Manages connections to MCP servers. Thread-safe."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, **kwargs):
        self.cfg = cfg or {}
        self._servers: Dict[str, MCPConnection] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp_")
        self._shutdown = False
        self._server_configs: Dict[str, MCPServerConfig] = {}
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
                result.append({
                    "name": name,
                    "enabled": config.enabled,
                    "connected": conn is not None and conn.is_alive(),
                    "tool_count": len(conn.tools_cache) if conn and conn.tools_cache else 0,
                    "command": config.command,
                    "args": config.args,
                })
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

    def shutdown(self, **kwargs) -> None:
        log.info("Shutting down MCP client manager")
        self._shutdown = True
        with self._lock:
            for name in list(self._servers.keys()):
                self._disconnect_one(name)
        self._executor.shutdown(wait=True)
        log.info("MCP client manager shut down complete")


def build_mcp_tools(cfg: Dict[str, Any], **kwargs):
    """Build MCP tool definitions for Ghost daemon."""
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

    return tools
