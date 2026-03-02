"""Sub-Agents API — Manage and monitor sub-agent instances."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_subagents import get_registry, SubAgentStatus

bp = Blueprint("subagents", __name__, url_prefix="/api/subagents")


@bp.route("", methods=["GET"])
def list_subagents():
    """List all sub-agents."""
    try:
        registry = get_registry()
        status_filter = request.args.get("status")
        
        status = SubAgentStatus(status_filter) if status_filter else None
        agents = registry.list_agents(status=status)
        
        return jsonify({
            "success": True,
            "agents": [agent.to_dict() for agent in agents],
            "count": len(agents),
        })
        
    except (ValueError, TypeError) as e:
        log.warning("Invalid status filter: %s", e)
        return jsonify({"error": "Invalid status filter"}), 400
    except Exception:
        log.exception("Failed to list sub-agents")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<agent_id>", methods=["GET"])
def get_subagent(agent_id):
    """Get a specific sub-agent."""
    try:
        registry = get_registry()
        agent = registry.get(agent_id)
        
        if not agent:
            return jsonify({"error": "Sub-agent not found"}), 404
        
        return jsonify({
            "success": True,
            "agent": agent.to_dict(),
        })
        
    except Exception:
        log.exception("Failed to get sub-agent")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<agent_id>/cancel", methods=["POST"])
def cancel_subagent(agent_id):
    """Cancel a running sub-agent."""
    try:
        registry = get_registry()
        success = registry.cancel(agent_id)
        
        if not success:
            return jsonify({"error": "Failed to cancel sub-agent - may not be running"}), 400
        
        return jsonify({
            "success": True,
            "message": f"Sub-agent {agent_id} cancelled",
        })
        
    except Exception:
        log.exception("Failed to cancel sub-agent")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/<agent_id>", methods=["DELETE"])
def delete_subagent(agent_id):
    """Remove a completed sub-agent from the registry."""
    try:
        registry = get_registry()
        success = registry.remove(agent_id)
        
        if not success:
            return jsonify({"error": "Failed to remove sub-agent - may still be running"}), 400
        
        return jsonify({
            "success": True,
            "message": f"Sub-agent {agent_id} removed",
        })
        
    except Exception:
        log.exception("Failed to delete sub-agent")
        return jsonify({"error": "Internal server error"}), 500
