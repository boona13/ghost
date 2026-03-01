"""
Ghost Model Context Protocol (MCP) Support

Connects Ghost to MCP servers for tool discovery and execution.
MCP is an open standard by Anthropic for AI model integration.

Features:
- MCP client over stdio transport (JSON-RPC 2.0)
- Tool discovery and execution
- Resource reading from MCP servers
- Config-driven server management
- Async support with proper error handling

Usage:
    Servers are configured in ~/.ghost/config.json under 'mcp_servers'.
    Tools are automatically discovered and registered with Ghost's tool registry.
"""

import json
import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import defaultdict

log = logging.getLogger("ghost.mcp")

GHOST_HOME = Path.home() / ".ghost"
MCP_SERVERS_FILE = GHOST_HOME / "mcp_servers.json"


# JSON-RPC 2.0 helpers
class JSONRPCError(Exception):
    """JSON-RPC error response."""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC Error {code}: {message}")


def _jsonrpc_request(method: str, params: Optional[dict] = None, msg_id: Optional[str] = None) -> dict:
    """Build a JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": msg_id or str(uuid.uuid4())
    }


def _jsonrpc_response(result: Any, msg_id: str) -> dict:
    """Build a JSON-RPC success response."""
    return {
        "jsonrpc": "2.0",
        "result": result,
        "id": msg_id
    }


def _jsonrpc_error(code: int, message: str, msg_id: Optional[str] = None, data: Any = None) -> dict:
    """Build a JSON-RPC error response."""
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {
        "jsonrpc": "2.0",
        "error": err,
        "id": msg_id
    }


# ═══════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════

@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""
    id: str
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: int = 30
    auto_connect: bool = True
    created_at: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "MCPServerConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class MCPTool:
    """An MCP tool discovered from a server."""
    name: str
    description: str
    input_schema: dict
    server_id: str
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class MCPResource:
    """An MCP resource discovered from a server."""
    uri: str
    name: str
    description: str
    mime_type: str
    server_id: str
    
    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
#  MCP CLIENT (stdio transport)
# ═══════════════════════════════════════════════════════════════

class MCPClient:
    """
    MCP client connecting via stdio transport.
    
    Manages the subprocess connection and JSON-RPC communication.
    Thread-safe for request/response handling.
    """
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._pending: Dict[str, threading.Event] = {}
        self._responses: Dict[str, dict] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._server_info: Optional[dict] = None
        self._tools: List[MCPTool] = []
        self._resources: List[MCPResource] = []
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._process is not None
    
    @property
    def tools(self) -> List[MCPTool]:
        return list(self._tools)
    
    @property
    def resources(self) -> List[MCPResource]:
        return list(self._resources)
    
    def connect(self, timeout: Optional[int] = None) -> bool:
        """Start the MCP server process and initialize connection."""
        if self._connected:
            return True
        
        timeout = timeout or self.config.timeout_seconds
        
        try:
            import os
            env = dict(os.environ)
            env.update(self.config.env)
            
            self._process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )
            
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            
            # Initialize with server
            init_result = self._call_method("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": False, "listChanged": True}
                },
                "clientInfo": {
                    "name": "ghost",
                    "version": "1.0.0"
                }
            }, timeout=timeout)
            
            if init_result:
                self._server_info = init_result
                self._connected = True
                log.info(f"MCP server '{self.config.name}' initialized")
                self._discover_capabilities()
                return True
            else:
                log.error(f"MCP server '{self.config.name}' initialization failed")
                self.disconnect()
                return False
                
        except Exception as e:
            log.error(f"Failed to connect to MCP server '{self.config.name}': {e}")
            self.disconnect()
            return False
    
    def disconnect(self):
        """Close connection and cleanup."""
        self._running = False
        self._connected = False
        
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        
        with self._lock:
            for event in self._pending.values():
                event.set()
            self._pending.clear()
            self._responses.clear()
        
        log.info(f"MCP server '{self.config.name}' disconnected")
    
    def _read_loop(self):
        """Background thread to read responses from stdout."""
        while self._running and self._process and self._process.poll() is None:
            try:
                line = self._process.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue
                
                try:
                    msg = json.loads(line.strip())
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    log.debug(f"Invalid JSON from MCP server: {line[:100]}")
                    
            except Exception as e:
                if self._running:
                    log.debug(f"MCP read error: {e}")
                time.sleep(0.1)
    
    def _handle_message(self, msg: dict):
        """Handle incoming JSON-RPC message."""
        msg_id = msg.get("id")
        
        if "result" in msg or "error" in msg:
            with self._lock:
                self._responses[msg_id] = msg
                if msg_id in self._pending:
                    self._pending[msg_id].set()
        else:
            log.debug(f"MCP notification: {msg.get('method')}")
    
    def _call_method(self, method: str, params: Optional[dict] = None, 
                     timeout: Optional[int] = None) -> Optional[Any]:
        """Call an MCP method and wait for response."""
        if not self._process or self._process.poll() is not None:
            return None
        
        msg_id = str(uuid.uuid4())
        request = _jsonrpc_request(method, params, msg_id)
        
        event = threading.Event()
        with self._lock:
            self._pending[msg_id] = event
        
        try:
            request_line = json.dumps(request) + "\n"
            self._process.stdin.write(request_line)
            self._process.stdin.flush()
            
            timeout = timeout or self.config.timeout_seconds
            if event.wait(timeout=timeout):
                with self._lock:
                    response = self._responses.pop(msg_id, None)
                
                if response is None:
                    return None
                
                if "error" in response:
                    err = response["error"]
                    raise JSONRPCError(err.get("code", -1), err.get("message", "Unknown error"), err.get("data"))
                
                return response.get("result")
            else:
                log.warning(f"MCP method '{method}' timed out after {timeout}s")
                return None
                
        except Exception as e:
            log.error(f"MCP method '{method}' failed: {e}")
            return None
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)
    
    def _discover_capabilities(self):
        """Discover tools and resources from the server."""
        try:
            tools_result = self._call_method("tools/list")
            if tools_result and "tools" in tools_result:
                self._tools = [
                    MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_id=self.config.id
                    )
                    for t in tools_result["tools"]
                ]
                log.info(f"Discovered {len(self._tools)} tools from '{self.config.name}'")
            
            resources_result = self._call_method("resources/list")
            if resources_result and "resources" in resources_result:
                self._resources = [
                    MCPResource(
                        uri=r.get("uri", ""),
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        mime_type=r.get("mimeType", "text/plain"),
                        server_id=self.config.id
                    )
                    for r in resources_result["resources"]
                ]
                log.info(f"Discovered {len(self._resources)} resources from '{self.config.name}'")
                
        except Exception as e:
            log.error(f"Failed to discover capabilities: {e}")
    
    def call_tool(self, tool_name: str, arguments: dict, timeout: Optional[int] = None) -> dict:
        """Call an MCP tool with the given arguments."""
        if not self._connected:
            return {"content": [{"type": "text", "text": "MCP server not connected"}], "isError": True}
        
        try:
            result = self._call_method("tools/call", {
                "name": tool_name,
                "arguments": arguments
            }, timeout=timeout)
            
            if result is None:
                return {"content": [{"type": "text", "text": "Tool call timed out"}], "isError": True}
            
            return result
            
        except JSONRPCError as e:
            return {
                "content": [{"type": "text", "text": f"MCP error: {e.message}"}],
                "isError": True
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Error calling tool: {e}"}],
                "isError": True
            }
    
    def read_resource(self, uri: str) -> Optional[str]:
        """Read an MCP resource by URI."""
        if not self._connected:
            return None
        
        try:
            result = self._call_method("resources/read", {"uri": uri})
            if result and "contents" in result:
                contents = result["contents"]
                if contents and len(contents) > 0:
                    return contents[0].get("text", "")
            return None
        except Exception as e:
            log.error(f"Failed to read resource '{uri}': {e}")
            return None


# ═══════════════════════════════════════════════════════════════
#  MCP MANAGER
# ═══════════════════════════════════════════════════════════════

class MCPManager:
    """Manages multiple MCP server connections and tool aggregation."""
    
    def __init__(self, cfg: dict):
        self.cfg = cfg or {}
        self._clients: Dict[str, MCPClient] = {}
        self._lock = threading.RLock()
        self._tool_index: Dict[str, MCPClient] = {}
        self._server_configs: Dict[str, MCPServerConfig] = {}
        self._load_configs()
    
    def _load_configs(self):
        """Load MCP server configs from config dict."""
        servers = self.cfg.get("mcp_servers", [])
        for s in servers:
            config = MCPServerConfig.from_dict(s)
            if not config.id:
                config.id = str(uuid.uuid4())[:8]
            self._server_configs[config.id] = config
    
    def start(self):
        """Connect to all auto-connect enabled servers."""
        for config in self._server_configs.values():
            if config.enabled and config.auto_connect:
                self.connect_server(config.id)
    
    def stop(self):
        """Disconnect all servers."""
        with self._lock:
            for client in list(self._clients.values()):
                client.disconnect()
            self._clients.clear()
            self._tool_index.clear()
    
    def connect_server(self, server_id: str) -> bool:
        """Connect to a specific server by ID."""
        config = self._server_configs.get(server_id)
        if not config:
            log.error(f"MCP server config not found: {server_id}")
            return False
        
        with self._lock:
            if server_id in self._clients:
                self._clients[server_id].disconnect()
            
            client = MCPClient(config)
            if client.connect():
                self._clients[server_id] = client
                
                # Index tools
                for tool in client.tools:
                    full_name = f"{config.name}.{tool.name}"
                    self._tool_index[full_name] = client
                    self._tool_index[tool.name] = client
                
                return True
            return False
    
    def disconnect_server(self, server_id: str):
        """Disconnect a specific server."""
        with self._lock:
            if server_id in self._clients:
                client = self._clients.pop(server_id)
                
                # Remove tools from index
                for tool in client.tools:
                    full_name = f"{client.config.name}.{tool.name}"
                    self._tool_index.pop(full_name, None)
                    self._tool_index.pop(tool.name, None)
                
                client.disconnect()
    
    def get_server_status(self, server_id: str) -> dict:
        """Get status of a specific server."""
        config = self._server_configs.get(server_id)
        if not config:
            return {"error": "Server not found"}
        
        with self._lock:
            client = self._clients.get(server_id)
            is_connected = client.is_connected if client else False
            
            return {
                "id": server_id,
                "name": config.name,
                "enabled": config.enabled,
                "connected": is_connected,
                "tool_count": len(client.tools) if client else 0,
                "resource_count": len(client.resources) if client else 0,
            }
    
    def get_all_tools(self) -> List[dict]:
        """Get all available tools from all connected servers."""
        tools = []
        with self._lock:
            for client in self._clients.values():
                for tool in client.tools:
                    tools.append({
                        "name": f"{client.config.name}.{tool.name}",
                        "original_name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "server_id": client.config.id,
                        "server_name": client.config.name,
                    })
        return tools
    
    def call_tool(self, tool_name: str, arguments: dict, timeout: Optional[int] = None) -> dict:
        """Call a tool by name (can be simple name or server.name format)."""
        with self._lock:
            client = self._tool_index.get(tool_name)
            if not client:
                return {
                    "content": [{"type": "text", "text": f"Tool '{tool_name}' not found"}],
                    "isError": True
                }
            
            # Extract simple tool name if full name was used
            simple_name = tool_name
            if "." in tool_name:
                simple_name = tool_name.split(".", 1)[1]
            
            return client.call_tool(simple_name, arguments, timeout)
    
    def add_server(self, config: MCPServerConfig) -> bool:
        """Add a new server config."""
        if not config.id:
            config.id = str(uuid.uuid4())[:8]
        self._server_configs[config.id] = config
        return True
    
    def remove_server(self, server_id: str) -> bool:
        """Remove a server config and disconnect if connected."""
        self.disconnect_server(server_id)
        if server_id in self._server_configs:
            del self._server_configs[server_id]
            return True
        return False
    
    def update_server(self, server_id: str, updates: dict) -> bool:
        """Update a server config."""
        if server_id not in self._server_configs:
            return False
        
        config = self._server_configs[server_id]
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return True
    
    def get_server_configs(self) -> List[dict]:
        """Get all server configs."""
        return [c.to_dict() for c in self._server_configs.values()]


# ═══════════════════════════════════════════════════════════════
#  TOOL BUILDER
# ═══════════════════════════════════════════════════════════════

def build_mcp_tools(mcp_manager: Optional[MCPManager] = None, cfg: dict = None):
    """
    Build Ghost tool definitions for MCP integration.
    
    Returns list of tool dicts that can be registered with Ghost's tool registry.
    """
    tools = []
    
    # Tool: List MCP servers
    def execute_list_servers():
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        return {"servers": mcp_manager.get_server_configs()}
    
    tools.append({
        "name": "mcp_list_servers",
        "description": "List all configured MCP servers with their connection status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "execute": lambda **kwargs: execute_list_servers()
    })
    
    # Tool: List available MCP tools
    def execute_list_tools():
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        return {"tools": mcp_manager.get_all_tools()}
    
    tools.append({
        "name": "mcp_list_tools",
        "description": "List all available tools from connected MCP servers.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "execute": lambda **kwargs: execute_list_tools()
    })
    
    # Tool: Call MCP tool
    def execute_call_tool(tool_name: str, arguments: dict = None, timeout: int = 30):
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        
        result = mcp_manager.call_tool(tool_name, arguments or {}, timeout)
        
        # Format content for display
        content_parts = result.get("content", [])
        text_parts = []
        for part in content_parts:
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        
        return {
            "result": "\\n".join(text_parts),
            "is_error": result.get("isError", False)
        }
    
    tools.append({
        "name": "mcp_call_tool",
        "description": (
            "Call a tool from an MCP server. Use mcp_list_tools first to see available tools. "
            "Tool names can be in format 'server.toolname' or just 'toolname'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to call (format: 'server.toolname' or just 'toolname')"
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the tool"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30
                }
            },
            "required": ["tool_name"]
        },
        "execute": lambda **kwargs: execute_call_tool(
            kwargs.get("tool_name"),
            kwargs.get("arguments"),
            kwargs.get("timeout", 30)
        )
    })
    
    # Tool: Connect to MCP server
    def execute_connect_server(server_id: str):
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        
        success = mcp_manager.connect_server(server_id)
        if success:
            status = mcp_manager.get_server_status(server_id)
            return {"success": True, "status": status}
        return {"success": False, "error": f"Failed to connect to server {server_id}"}
    
    tools.append({
        "name": "mcp_connect_server",
        "description": "Connect to a specific MCP server by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "The ID of the MCP server to connect"
                }
            },
            "required": ["server_id"]
        },
        "execute": lambda **kwargs: execute_connect_server(kwargs.get("server_id"))
    })
    
    # Tool: Disconnect from MCP server
    def execute_disconnect_server(server_id: str):
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        
        mcp_manager.disconnect_server(server_id)
        return {"success": True, "message": f"Disconnected from server {server_id}"}
    
    tools.append({
        "name": "mcp_disconnect_server",
        "description": "Disconnect from a specific MCP server by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "The ID of the MCP server to disconnect"
                }
            },
            "required": ["server_id"]
        },
        "execute": lambda **kwargs: execute_disconnect_server(kwargs.get("server_id"))
    })
    
    # Tool: Get server status
    def execute_server_status(server_id: str = None):
        if not mcp_manager:
            return {"error": "MCP manager not available"}
        
        if server_id:
            return {"status": mcp_manager.get_server_status(server_id)}
        else:
            # Get status for all servers
            configs = mcp_manager.get_server_configs()
            statuses = {}
            for cfg in configs:
                statuses[cfg["id"]] = mcp_manager.get_server_status(cfg["id"])
            return {"statuses": statuses}
    
    tools.append({
        "name": "mcp_server_status",
        "description": "Get connection status of MCP servers. If server_id is omitted, returns all servers.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "Optional: ID of specific server to check"
                }
            },
            "required": []
        },
        "execute": lambda **kwargs: execute_server_status(kwargs.get("server_id"))
    })
    
    return tools
