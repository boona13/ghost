"""Obsidian vault management API routes."""

import json
from pathlib import Path
from flask import Blueprint, jsonify, request

obsidian_bp = Blueprint("obsidian", __name__, url_prefix="/api/obsidian")

GHOST_HOME = Path.home() / ".ghost"
CONFIG_FILE = GHOST_HOME / "config.json"
OBSIDIAN_CONFIG_FILE = GHOST_HOME / "obsidian_config.json"


def _load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(cfg):
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def _load_obsidian_config():
    if OBSIDIAN_CONFIG_FILE.exists():
        try:
            return json.loads(OBSIDIAN_CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_obsidian_config(cfg):
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    OBSIDIAN_CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


@obsidian_bp.route("/vaults", methods=["GET"])
def get_vaults():
    """Get list of configured vaults."""
    cfg = _load_config()
    obs_cfg = _load_obsidian_config()
    
    vault_paths = obs_cfg.get("vault_paths", [])
    vaults = []
    
    for path in vault_paths:
        p = Path(path).expanduser()
        vaults.append({
            "path": path,
            "name": p.name,
            "exists": p.exists() and p.is_dir(),
        })
    
    return jsonify({
        "vaults": vaults,
        "enabled": cfg.get("enable_obsidian", True),
        "default_vault": obs_cfg.get("default_vault", ""),
    })


@obsidian_bp.route("/vaults", methods=["POST"])
def add_vault():
    """Add a new vault path."""
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    
    if not path:
        return jsonify({"error": "Path is required"}), 400
    
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return jsonify({"error": f"Path does not exist or is not a directory: {path}"}), 400
    
    cfg = _load_obsidian_config()
    paths = cfg.get("vault_paths", [])
    path_str = str(p)
    
    if path_str in paths:
        return jsonify({"error": "Vault already configured"}), 409
    
    paths.append(path_str)
    cfg["vault_paths"] = paths
    _save_obsidian_config(cfg)
    
    return jsonify({
        "success": True,
        "vault": {"path": path_str, "name": p.name, "exists": True}
    })


@obsidian_bp.route("/vaults/<path:vault_path>", methods=["DELETE"])
def remove_vault(vault_path):
    """Remove a vault path."""
    cfg = _load_obsidian_config()
    paths = cfg.get("vault_paths", [])
    
    # Find and remove the path
    decoded_path = vault_path.replace("%2F", "/")
    removed = None
    
    for p in paths:
        if p == decoded_path or p.endswith(decoded_path):
            removed = p
            paths.remove(p)
            break
    
    if not removed:
        return jsonify({"error": "Vault not found"}), 404
    
    cfg["vault_paths"] = paths
    _save_obsidian_config(cfg)
    
    return jsonify({"success": True, "removed": removed})


@obsidian_bp.route("/config", methods=["GET"])
def get_config():
    """Get Obsidian configuration."""
    cfg = _load_config()
    obs_cfg = _load_obsidian_config()
    
    return jsonify({
        "enabled": cfg.get("enable_obsidian", True),
        "default_vault": obs_cfg.get("default_vault", ""),
        "daily_notes_folder": obs_cfg.get("daily_notes_folder", "Daily"),
        "capture_folder": obs_cfg.get("capture_folder", "Clippings"),
    })


@obsidian_bp.route("/config", methods=["POST"])
def update_config():
    """Update Obsidian configuration."""
    data = request.get_json() or {}
    
    cfg = _load_config()
    obs_cfg = _load_obsidian_config()
    
    if "enabled" in data:
        cfg["enable_obsidian"] = bool(data["enabled"])
        _save_config(cfg)
    
    if "default_vault" in data:
        obs_cfg["default_vault"] = data["default_vault"]
    
    if "daily_notes_folder" in data:
        obs_cfg["daily_notes_folder"] = data["daily_notes_folder"]
    
    if "capture_folder" in data:
        obs_cfg["capture_folder"] = data["capture_folder"]
    
    _save_obsidian_config(obs_cfg)
    
    return jsonify({"success": True})


@obsidian_bp.route("/discover", methods=["GET"])
def discover_vaults():
    """Discover vaults from obsidian.json."""
    import os
    
    # Find obsidian.json
    paths_to_check = [
        Path.home() / "Library/Application Support/obsidian/obsidian.json",  # macOS
        Path.home() / ".config/obsidian/obsidian.json",  # Linux
    ]
    
    obsidian_json = None
    for p in paths_to_check:
        if p.exists():
            obsidian_json = p
            break
    
    if not obsidian_json:
        return jsonify({"vaults": [], "message": "obsidian.json not found"})
    
    try:
        data = json.loads(obsidian_json.read_text())
        vaults = []
        for vault_id, vault_info in data.get("vaults", {}).items():
            path = vault_info.get("path", "")
            if path:
                p = Path(path)
                vaults.append({
                    "id": vault_id,
                    "path": path,
                    "name": p.name,
                    "exists": p.exists(),
                })
        return jsonify({"vaults": vaults, "source": str(obsidian_json)})
    except (json.JSONDecodeError, OSError) as e:
        return jsonify({"error": str(e)}), 500


@obsidian_bp.route("/notes", methods=["GET"])
def list_notes():
    """List notes in a vault."""
    vault_path = request.args.get("vault", "")
    folder = request.args.get("folder", "")
    limit = int(request.args.get("limit", 50))
    
    if not vault_path:
        return jsonify({"error": "Vault path is required"}), 400
    
    vault = Path(vault_path).expanduser()
    if not vault.exists():
        return jsonify({"error": "Vault not found"}), 404
    
    search_path = vault / folder if folder else vault
    if not search_path.exists():
        return jsonify({"error": "Folder not found"}), 404
    
    notes = []
    try:
        for md_file in search_path.rglob("*.md"):
            if len(notes) >= limit:
                break
            # Skip hidden and system folders
            rel = md_file.relative_to(vault)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            
            notes.append({
                "name": md_file.stem,
                "path": str(rel),
                "folder": str(rel.parent) if rel.parent != Path(".") else "",
                "modified": md_file.stat().st_mtime,
            })
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    
    notes.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"notes": notes, "count": len(notes)})


@obsidian_bp.route("/notes/search", methods=["GET"])
def search_notes():
    """Search notes by query."""
    vault_path = request.args.get("vault", "")
    query = request.args.get("query", "").lower()
    limit = int(request.args.get("limit", 20))
    
    if not vault_path:
        return jsonify({"error": "Vault path is required"}), 400
    if not query:
        return jsonify({"error": "Query is required"}), 400
    
    vault = Path(vault_path).expanduser()
    if not vault.exists():
        return jsonify({"error": "Vault not found"}), 404
    
    results = []
    try:
        for md_file in vault.rglob("*.md"):
            if len(results) >= limit:
                break
            rel = md_file.relative_to(vault)
            if any(part.startswith(".") for part in rel.parts[:-1]):
                continue
            
            name_match = query in md_file.stem.lower()
            content_match = False
            
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                content_match = query in content.lower()
            except (OSError, UnicodeDecodeError):
                pass
            
            if name_match or content_match:
                results.append({
                    "name": md_file.stem,
                    "path": str(rel),
                    "name_match": name_match,
                    "content_match": content_match,
                })
    except OSError as e:
        return jsonify({"error": str(e)}), 500
    
    return jsonify({"results": results, "query": query, "count": len(results)})
