"""Ghost Tools API — list, configure settings, enable/disable, and delete LLM-callable tools."""

import json
import logging
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("tools", __name__)


def _get_daemon():
    from ghost_dashboard import get_daemon
    return get_daemon()


def _get_tool_manager():
    daemon = _get_daemon()
    if not daemon or not hasattr(daemon, "tool_manager") or not daemon.tool_manager:
        return None
    return daemon.tool_manager


@bp.route("/api/tools")
def list_tools():
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"tools": [], "error": "Tool system not initialized"})

    tools = []
    for info in tm.tools.values():
        entry = info.to_dict()
        manifest = info.manifest
        if manifest and manifest.settings:
            entry["settings_schema"] = manifest.settings
        else:
            entry["settings_schema"] = []
        tools.append(entry)

    return jsonify({"tools": tools, "total": len(tools)})


@bp.route("/api/tools/<name>/detail")
def get_tool_detail(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    info = tm.tools.get(name)
    if not info:
        return jsonify({"error": f"Tool '{name}' not found"}), 404

    entry = info.to_dict()

    daemon = _get_daemon()
    registry = getattr(daemon, "tool_registry", None) if daemon else None
    llm_tools = []
    if registry and info.loaded and info.tools:
        for tool_name in info.tools:
            tool_def = registry.get(tool_name)
            if tool_def:
                llm_tools.append({
                    "name": tool_def.get("name", tool_name),
                    "description": tool_def.get("description", ""),
                    "parameters": tool_def.get("parameters", {}),
                })
    entry["llm_tools"] = llm_tools
    return jsonify(entry)


@bp.route("/api/tools/<name>/settings")
def get_tool_settings(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    info = tm.tools.get(name)
    if not info:
        return jsonify({"error": f"Tool '{name}' not found"}), 404

    schema = []
    if info.manifest and info.manifest.settings:
        schema = info.manifest.settings

    daemon = _get_daemon()
    saved = {}
    if daemon:
        saved = daemon.cfg.get("tool_settings", {}).get(name, {})

    return jsonify({"name": name, "schema": schema, "values": saved})


@bp.route("/api/tools/<name>/settings", methods=["POST"])
def save_tool_settings(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    info = tm.tools.get(name)
    if not info:
        return jsonify({"error": f"Tool '{name}' not found"}), 404

    data = request.get_json(silent=True) or {}
    settings = data.get("settings", {})

    daemon = _get_daemon()
    if not daemon:
        return jsonify({"error": "Daemon not available"}), 503

    if "tool_settings" not in daemon.cfg:
        daemon.cfg["tool_settings"] = {}
    daemon.cfg["tool_settings"][name] = settings

    try:
        from ghost import save_config
        save_config(daemon.cfg)
    except Exception as e:
        log.error("Failed to save tool settings: %s", e)
        return jsonify({"error": "Failed to persist settings"}), 500

    return jsonify({"ok": True})


@bp.route("/api/tools/<name>/enable", methods=["POST"])
def enable_tool(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    result = tm.enable_tool(name)
    status_code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), status_code


@bp.route("/api/tools/<name>/disable", methods=["POST"])
def disable_tool(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    result = tm.disable_tool(name)
    status_code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), status_code


@bp.route("/api/tools/<name>/delete", methods=["POST"])
def delete_tool(name):
    tm = _get_tool_manager()
    if not tm:
        return jsonify({"error": "Tool system not initialized"}), 503

    result = tm.uninstall_tool(name)
    status_code = 200 if result.get("status") == "ok" else 400
    return jsonify(result), status_code
