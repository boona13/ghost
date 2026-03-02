"""MCP (Model Context Protocol) dashboard API — server management, tool discovery, and testing."""

from flask import Blueprint, jsonify, request

bp = Blueprint("mcp", __name__)


def _get_mcp_manager():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, "mcp_manager") and daemon.mcp_manager:
        return daemon.mcp_manager
    return None


def _get_cfg():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        return daemon.cfg
    return {}


def _future_result(future, timeout=30.0):
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        return {"ok": False, "error": "Operation timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@bp.route("/api/mcp")
def mcp_overview():
    mgr = _get_mcp_manager()
    cfg = _get_cfg()
    enabled = cfg.get("enable_mcp", True)

    if not enabled:
        return jsonify({
            "enabled": False,
            "servers": [],
            "total_tools": 0,
        })

    if not mgr:
        return jsonify({
            "enabled": True,
            "servers": [],
            "total_tools": 0,
            "error": "MCP manager not initialized",
        }), 503

    servers = mgr.list_servers()
    total_tools = sum(s.get("tool_count", 0) for s in servers)

    return jsonify({
        "enabled": True,
        "servers": servers,
        "total_tools": total_tools,
        "connected_count": sum(1 for s in servers if s.get("connected")),
        "configured_count": len(servers),
    })


@bp.route("/api/mcp/servers")
def list_servers():
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"servers": [], "error": "MCP not initialized"}), 503
    return jsonify({"servers": mgr.list_servers()})


@bp.route("/api/mcp/servers/<server_name>/connect", methods=["POST"])
def connect_server(server_name):
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503

    data = request.get_json(silent=True) or {}
    config_override = data.get("config_override")
    result = _future_result(mgr.connect(server_name, config_override))
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@bp.route("/api/mcp/servers/<server_name>/disconnect", methods=["POST"])
def disconnect_server(server_name):
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503

    result = _future_result(mgr.disconnect(server_name))
    return jsonify(result)


@bp.route("/api/mcp/servers/<server_name>/tools")
def list_server_tools(server_name):
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503

    result = _future_result(mgr.list_tools(server_name))
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@bp.route("/api/mcp/tools")
def list_all_tools():
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "tools": [], "error": "MCP not initialized"}), 503

    result = _future_result(mgr.list_tools())
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@bp.route("/api/mcp/tools/call", methods=["POST"])
def call_tool():
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Request body required"}), 400

    server_name = data.get("server_name")
    tool_name = data.get("tool_name")
    arguments = data.get("arguments", {})

    if not server_name or not tool_name:
        return jsonify({"ok": False, "error": "server_name and tool_name are required"}), 400

    result = _future_result(mgr.call_tool(server_name, tool_name, arguments))
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@bp.route("/api/mcp/servers/add", methods=["POST"])
def add_server():
    """Add a new MCP server config. Persists to config.json and registers at runtime."""
    mgr = _get_mcp_manager()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Request body required"}), 400

    name = data.get("name", "").strip()
    command = data.get("command", "").strip()
    if not name or not command:
        return jsonify({"ok": False, "error": "name and command are required"}), 400

    server_cfg = {
        "command": command,
        "args": data.get("args", []),
        "env": data.get("env", {}),
        "enabled": data.get("enabled", True),
        "timeout": data.get("timeout", 30),
        "allowed_tools": data.get("allowed_tools"),
        "blocked_tools": data.get("blocked_tools", []),
    }

    from ghost import load_config, save_config
    cfg = load_config()
    if "mcp_servers" not in cfg:
        cfg["mcp_servers"] = {}
    cfg["mcp_servers"][name] = server_cfg
    save_config(cfg)

    if mgr:
        mgr.add_server(name, server_cfg)

    daemon = None
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if daemon:
            daemon.cfg["mcp_servers"] = cfg.get("mcp_servers", {})
    except Exception:
        pass

    auto_connect = data.get("auto_connect", True)
    if auto_connect and mgr and server_cfg.get("enabled", True):
        result = _future_result(mgr.connect(name))
        return jsonify({"ok": True, "server": name, "connect_result": result})

    return jsonify({"ok": True, "server": name})


@bp.route("/api/mcp/servers/<server_name>/remove", methods=["POST"])
def remove_server(server_name):
    """Remove an MCP server. Disconnects, removes from runtime and config.json."""
    mgr = _get_mcp_manager()

    from ghost import load_config, save_config
    cfg = load_config()
    mcp_servers = cfg.get("mcp_servers", {})
    if server_name in mcp_servers:
        del mcp_servers[server_name]
        cfg["mcp_servers"] = mcp_servers
        save_config(cfg)

    if mgr:
        mgr.remove_server(server_name)

    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if daemon:
            daemon.cfg["mcp_servers"] = cfg.get("mcp_servers", {})
    except Exception:
        pass

    return jsonify({"ok": True, "server": server_name})


@bp.route("/api/mcp/health")
def mcp_health():
    """Health check for all MCP servers with uptime and request stats."""
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503
    return jsonify({"ok": True, "servers": mgr.health_check()})


@bp.route("/api/mcp/reconnect", methods=["POST"])
def mcp_reconnect():
    """Force reconnect dead servers."""
    mgr = _get_mcp_manager()
    if not mgr:
        return jsonify({"ok": False, "error": "MCP not initialized"}), 503
    results = mgr.reconnect_dead()
    return jsonify({"ok": True, "results": results})


@bp.route("/api/mcp/config")
def mcp_config():
    """Return current MCP configuration (server definitions from config)."""
    cfg = _get_cfg()
    mcp_servers = cfg.get("mcp_servers", {})
    sanitized = {}
    for name, scfg in mcp_servers.items():
        if isinstance(scfg, dict):
            sanitized[name] = {
                "command": scfg.get("command", ""),
                "args": scfg.get("args", []),
                "enabled": scfg.get("enabled", True),
                "timeout": scfg.get("timeout", 30),
                "allowed_tools": scfg.get("allowed_tools"),
                "blocked_tools": scfg.get("blocked_tools", []),
            }
    return jsonify({"mcp_servers": sanitized, "enable_mcp": cfg.get("enable_mcp", True)})
