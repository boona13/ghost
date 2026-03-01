"""Projects API — CRUD for Ghost project workspaces."""

import os
from flask import Blueprint, jsonify, request
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_projects import ProjectRegistry, get_active_project

bp = Blueprint("projects", __name__)

_registry = None


def _get_registry():
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry


@bp.route("/api/projects")
def list_projects():
    registry = _get_registry()
    projects = registry.list_all()
    return jsonify({
        "projects": [p.to_dict() for p in projects],
        "count": len(projects),
    })


@bp.route("/api/projects/<project_id>")
def get_project(project_id):
    registry = _get_registry()
    project = registry.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project.to_dict())


@bp.route("/api/projects/active")
def get_active():
    project = get_active_project()
    if not project:
        return jsonify({"project": None})
    return jsonify({"project": project.to_dict()})


@bp.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()

    if not path or not name:
        return jsonify({"error": "path and name are required"}), 400

    registry = _get_registry()
    try:
        project = registry.create(Path(path), name, description)
        extra_fields = {"skills", "disabled_skills", "config_overrides",
                        "memory_scope", "auto_activate_paths", "env_vars"}
        extras = {k: v for k, v in data.items() if k in extra_fields and v}
        if extras:
            project = registry.update(project.id, extras)
        return jsonify({"ok": True, "project": project.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    registry = _get_registry()
    project = registry.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json(silent=True) or {}
    allowed = {"name", "description", "skills", "disabled_skills",
               "config_overrides", "memory_scope", "auto_activate_paths", "env_vars"}
    updates = {k: v for k, v in data.items() if k in allowed}

    try:
        updated = registry.update(project_id, updates)
        return jsonify({"ok": True, "project": updated.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    registry = _get_registry()
    project = registry.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    registry.delete(project_id)
    return jsonify({"ok": True})


@bp.route("/api/projects/resolve")
def resolve_project():
    path_str = request.args.get("path", "").strip()
    if path_str:
        path = Path(path_str).resolve()
    else:
        path = Path.cwd()

    registry = _get_registry()
    project = registry.resolve(path)
    if not project:
        return jsonify({"project": None})
    return jsonify({"project": project.to_dict()})


@bp.route("/api/projects/browse")
def browse_directory():
    """List directories at a given path for the folder picker."""
    path_str = request.args.get("path", "").strip()
    if not path_str:
        path_str = str(Path.home())

    target = Path(path_str).resolve()
    if not target.is_dir():
        return jsonify({"error": "Not a directory", "path": str(target)}), 400

    dirs = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: e.name.lower()):
            if entry.name.startswith('.'):
                continue
            if not entry.is_dir():
                continue
            try:
                has_children = any(
                    c.is_dir() and not c.name.startswith('.')
                    for c in entry.iterdir()
                )
            except PermissionError:
                has_children = False
            dirs.append({
                "name": entry.name,
                "path": str(entry),
                "has_children": has_children,
            })
    except PermissionError:
        return jsonify({"error": "Permission denied", "path": str(target)}), 403

    parent = str(target.parent) if target != target.parent else None

    return jsonify({
        "current": str(target),
        "parent": parent,
        "directories": dirs,
    })
