"""MCP (Model Context Protocol) Dashboard API Routes."""

import json
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

bp = Blueprint("mcp", __name__)


def _get_manager():
    """Get the MCP manager from the daemon."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, "mcp_manager") and daemon.mcp_manager:
        return daemon.mcp_manager
    return None


def _result_from_future(future, timeout: float = 30.0):
    """Extract result from a concurrent.futures.Future with timeout."""
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        return {"ok": False, "error": "Operation timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Server Management ────────────────────────────────────────────

@bp.route("/api/mcp/servers", methods=["GET"])
def list_servers():
    """List all configured MCP servers and their connection status."""
    manager = _get_manager()
    if not manager:
        return jsonify({"servers": [], "error": "MCP not initialized"}), 503
    try:
        servers = manager.list_servers()
        return jsonify({"servers": servers})
    except Exception as e:
        return jsonify({"servers": [], "error": str(e)}), 500


@bp.route("/api/mcp/servers/<server_name>/connect", methods=["POST"])
def connect_server(server_name):
    """Connect to an MCP server."""
    manager = _get_manager()
    if not manager:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503
    
    data = request.get_json(force=True, silent=True) or {}
    config_override = data.get("config_override")
    
    try:
        future = manager.connect(server_name, config_override)
        result = _result_from_future(future, timeout=60.0)
        status_code = 200 if result.get("ok") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/mcp/servers/<server_name>/disconnect", methods=["POST"])
def disconnect_server(server_name):
    """Disconnect from an MCP server."""
    manager = _get_manager()
    if not manager:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503
    
    try:
        future = manager.disconnect(server_name)
        result = _result_from_future(future, timeout=10.0)
        status_code = 200 if result.get("ok") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Tools ────────────────────────────────────────────────────────

@bp.route("/api/mcp/tools", methods=["GET"])
def list_tools():
    """List all tools from connected MCP servers."""
    manager = _get_manager()
    if not manager:
        return jsonify({"tools": [], "error": "MCP not initialized"}), 503
    
    server_name = request.args.get("server_name")
    
    try:
        future = manager.list_tools(server_name)
        result = _result_from_future(future, timeout=30.0)
        if result.get("ok"):
            return jsonify({"tools": result.get("tools", []), "server": result.get("server")})
        return jsonify({"tools": [], "error": result.get("error", "Unknown error")}), 400
    except Exception as e:
        return jsonify({"tools": [], "error": str(e)}), 500


@bp.route("/api/mcp/tools/call", methods=["POST"])
def call_tool():
    """Call a tool on an MCP server."""
    manager = _get_manager()
    if not manager:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503
    
    data = request.get_json(force=True, silent=True) or {}
    server_name = data.get("server_name")
    tool_name = data.get("tool_name")
    arguments = data.get("arguments", {})
    
    if not server_name or not tool_name:
        return jsonify({"ok": False, "error": "server_name and tool_name are required"}), 400
    
    try:
        future = manager.call_tool(server_name, tool_name, arguments)
        result = _result_from_future(future, timeout=60.0)
        status_code = 200 if result.get("ok") else 400
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Configuration ────────────────────────────────────────────────

@bp.route("/api/mcp/config", methods=["GET"])
def get_config():
    """Get MCP configuration (server configs without sensitive data)."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon:
        return jsonify({"servers": {}, "enabled": False}), 503
    
    try:
        cfg = daemon.cfg if hasattr(daemon, "cfg") else {}
        mcp_enabled = cfg.get("enable_mcp", True)
        mcp_servers = cfg.get("mcp_servers", {})
        
        # Return sanitized config (no sensitive env vars)
        servers = {}
        for name, scfg in mcp_servers.items():
            if isinstance(scfg, dict):
                servers[name] = {
                    "name": name,
                    "command": scfg.get("command", ""),
                    "args": scfg.get("args", []),
                    "enabled": scfg.get("enabled", True),
                    "timeout": scfg.get("timeout", 30.0),
                    "allowed_tools": scfg.get("allowed_tools"),
                    "blocked_tools": scfg.get("blocked_tools", []),
                }
        
        return jsonify({"servers": servers, "enabled": mcp_enabled})
    except Exception as e:
        return jsonify({"servers": {}, "enabled": False, "error": str(e)}), 500


@bp.route("/api/mcp/config", methods=["POST"])
def update_config():
    """Update MCP configuration (add/update server config)."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon:
        return jsonify({"ok": False, "error": "Daemon not available"}), 503
    
    data = request.get_json(force=True, silent=True) or {}
    server_name = data.get("name", "").strip()
    
    if not server_name:
        return jsonify({"ok": False, "error": "Server name is required"}), 400
    
    # Validate server name
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', server_name):
        return jsonify({"ok": False, "error": "Invalid server name. Use only letters, numbers, underscores, and hyphens."}), 400
    
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"ok": False, "error": "Command is required"}), 400
    
    # Validate command (prevent shell injection)
    if re.search(r'[;&|`$(){}[\]<>]', command):
        return jsonify({"ok": False, "error": "Command contains forbidden characters"}), 400
    
    try:
        cfg = daemon.cfg if hasattr(daemon, "cfg") else {}
        mcp_servers = cfg.get("mcp_servers", {})
        
        # Build server config
        server_config = {
            "command": command,
            "args": data.get("args", []),
            "env": data.get("env", {}),
            "enabled": data.get("enabled", True),
            "timeout": data.get("timeout", 30.0),
        }
        
        # Optional fields
        if "allowed_tools" in data:
            server_config["allowed_tools"] = data["allowed_tools"]
        if "blocked_tools" in data:
            server_config["blocked_tools"] = data["blocked_tools"]
        
        # Update config
        mcp_servers[server_name] = server_config
        cfg["mcp_servers"] = mcp_servers
        
        # Also update manager's internal config if available
        manager = _get_manager()
        if manager:
            from ghost_mcp import MCPServerConfig
            manager._server_configs[server_name] = MCPServerConfig.from_dict(server_name, server_config)
        
        # Persist config
        if hasattr(daemon, "_save_config"):
            daemon._save_config()
        
        return jsonify({"ok": True, "server": {"name": server_name, **server_config}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/mcp/config/servers/<server_name>", methods=["DELETE"])
def delete_server_config(server_name):
    """Delete a server configuration."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if not daemon:
        return jsonify({"ok": False, "error": "Daemon not available"}), 503
    
    try:
        cfg = daemon.cfg if hasattr(daemon, "cfg") else {}
        mcp_servers = cfg.get("mcp_servers", {})
        
        if server_name not in mcp_servers:
            return jsonify({"ok": False, "error": "Server not found"}), 404
        
        # Disconnect if connected
        manager = _get_manager()
        if manager and server_name in manager._servers:
            future = manager.disconnect(server_name)
            _result_from_future(future, timeout=10.0)
        
        # Remove from manager's internal config
        if manager and server_name in manager._server_configs:
            del manager._server_configs[server_name]
        
        # Remove from config
        del mcp_servers[server_name]
        cfg["mcp_servers"] = mcp_servers
        
        # Persist config
        if hasattr(daemon, "_save_config"):
            daemon._save_config()
        
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
