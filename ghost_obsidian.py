"""GHOST Obsidian Vault Integration"""

import json
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

GHOST_HOME = Path.home() / ".ghost"
CONFIG_FILE = GHOST_HOME / "obsidian_config.json"

def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def _save_config(cfg: dict):
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def _get_obsidian_json_path() -> Optional[Path]:
    system = os.name
    if system == "posix":
        mac_path = Path.home() / "Library/Application Support/obsidian/obsidian.json"
        if mac_path.exists():
            return mac_path
        linux_path = Path.home() / ".config/obsidian/obsidian.json"
        if linux_path.exists():
            return linux_path
    return None

def _discover_vaults() -> List[Dict]:
    obs_json = _get_obsidian_json_path()
    if not obs_json:
        return []
    try:
        data = json.loads(obs_json.read_text())
        vaults = []
        for vault_id, info in data.get("vaults", {}).items():
            path = info.get("path", "")
            if path and Path(path).exists():
                vaults.append({"id": vault_id, "path": path, "name": Path(path).name})
        return vaults
    except (json.JSONDecodeError, OSError):
        return []

def _sanitize_path(path: str) -> Optional[str]:
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return None
    has_obs = (p / ".obsidian").exists()
    has_md = len(list(p.glob("*.md"))) > 0
    if not has_obs and not has_md:
        return None
    return str(p)

def _parse_tags(content: str) -> List[str]:
    return list(set(re.findall(r"#(\w+)", content)))

def _parse_links(content: str) -> List[str]:
    pattern = r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
    return list(set(re.findall(pattern, content)))

def build_obsidian_tools(cfg: dict = None):
    """Build Obsidian vault integration tools."""
    cfg = cfg or {}
    vault_paths = cfg.get("obsidian_vault_paths", [])
    
    def obsidian_vault_discover() -> dict:
        """Discover Obsidian vaults from obsidian.json file."""
        vaults = _discover_vaults()
        # Add configured paths
        for path in vault_paths:
            sanitized = _sanitize_path(path)
            if sanitized and not any(v["path"] == sanitized for v in vaults):
                vaults.append({"id": f"manual", "path": sanitized, "name": Path(sanitized).name})
        return {"vaults": vaults, "count": len(vaults), "obsidian_json_found": _get_obsidian_json_path() is not None}
    
    def obsidian_vault_add(path: str) -> str:
        """Add a vault path to configuration."""
        sanitized = _sanitize_path(path)
        if not sanitized:
            return f"ERROR: Invalid vault path: {path}"
        config = _load_config()
        paths = config.get("vault_paths", [])
        if sanitized in paths:
            return f"Vault already configured: {sanitized}"
        paths.append(sanitized)
        config["vault_paths"] = paths
        _save_config(config)
        return f"SUCCESS: Added vault at {sanitized}"
    
    def obsidian_vault_remove(path: str) -> str:
        """Remove a vault path from configuration."""
        config = _load_config()
        paths = config.get("vault_paths", [])
        removed = None
        if path in paths:
            paths.remove(path)
            removed = path
        else:
            for p in paths:
                if path in p or p in path:
                    paths.remove(p)
                    removed = p
                    break
        if removed:
            config["vault_paths"] = paths
            _save_config(config)
            return f"SUCCESS: Removed vault {removed}"
        return f"ERROR: Vault not found: {path}"
    
    def obsidian_note_search(query: str, vault_path: str = "", limit: int = 10) -> dict:
        """Search for notes by name or content."""
        search_path = vault_path
        if not search_path:
            config = _load_config()
            paths = config.get("vault_paths", [])
            if not paths:
                paths = vault_paths
            if paths:
                search_path = paths[0]
        if not search_path:
            return {"error": "No vault configured"}
        
        vault = Path(search_path)
        if not vault.exists():
            return {"error": f"Vault not found: {search_path}"}
        
        results = []
        query_lower = query.lower()
        
        for md_file in vault.rglob("*.md"):
            if "/." in str(md_file.relative_to(vault)):
                continue
            name_match = query_lower in md_file.stem.lower()
            content_match = False
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                content_match = query_lower in content.lower()
                if name_match or content_match:
                    results.append({
                        "path": str(md_file),
                        "relative": str(md_file.relative_to(vault)),
                        "name": md_file.stem,
                        "tags": _parse_tags(content[:5000]),
                        "links": _parse_links(content[:5000]),
                    })
                    if len(results) >= limit:
                        break
            except Exception:
                continue
        
        return {"query": query, "vault": str(vault), "results": results, "count": len(results)}
    
    def obsidian_note_create(title: str, content: str = "", vault_path: str = "", folder: str = "", tags: str = "", links: str = "") -> str:
        """Create a new note in a vault."""
        target_path = vault_path
        if not target_path:
            config = _load_config()
            paths = config.get("vault_paths", [])
            if not paths:
                paths = vault_paths
            if paths:
                target_path = paths[0]
        if not target_path:
            return "ERROR: No vault configured"
        
        vault = Path(target_path)
        if not vault.exists():
            return f"ERROR: Vault not found: {target_path}"
        
        safe_title = re.sub(r'[<>:"/\\\\|?*]', "_", title).strip()
        if not safe_title:
            return "ERROR: Invalid note title"
        
        if folder:
            note_dir = vault / folder
            note_dir.mkdir(parents=True, exist_ok=True)
        else:
            note_dir = vault
        
        note_path = note_dir / f"{safe_title}.md"
        
        parts = []
        if tags:
            parts.append(" ".join(f"#{t.strip()}" for t in tags.split(",") if t.strip()))
            parts.append("")
        parts.append(content)
        if links:
            parts.append("")
            parts.append("## Related")
            for link in links.split(","):
                if link.strip():
                    parts.append(f"- [[{link.strip()}]]")
        
        try:
            note_path.write_text("\\n\\n".join(parts), encoding="utf-8")
            return f"SUCCESS: Created note at {note_path}"
        except Exception as e:
            return f"ERROR: Failed to create note: {e}"
    
    def obsidian_daily_note(content: str = "", vault_path: str = "") -> str:
        """Create or append to today's daily note."""
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        date_title = today.strftime("%Y-%m-%d %A")
        
        target_path = vault_path
        if not target_path:
            config = _load_config()
            paths = config.get("vault_paths", [])
            if not paths:
                paths = vault_paths
            if paths:
                target_path = paths[0]
        if not target_path:
            return "ERROR: No vault configured"
        
        vault = Path(target_path)
        if not vault.exists():
            return f"ERROR: Vault not found: {target_path}"
        
        daily_folder = vault / "Daily"
        if not daily_folder.exists():
            daily_folder = vault
        
        note_path = daily_folder / f"{date_str}.md"
        timestamp = today.strftime("%H:%M")
        entry = f"- {timestamp}: {content}" if content else f"- {timestamp}"
        
        try:
            if note_path.exists():
                existing = note_path.read_text(encoding="utf-8")
                new_content = existing.rstrip() + "\\n" + entry + "\\n"
                note_path.write_text(new_content, encoding="utf-8")
                return f"SUCCESS: Appended to daily note {note_path}"
            else:
                header = f"# {date_title}\\n\\n"
                note_path.write_text(header + entry + "\\n", encoding="utf-8")
                return f"SUCCESS: Created daily note {note_path}"
        except Exception as e:
            return f"ERROR: {e}"
    
    def obsidian_note_read(note_path: str) -> dict:
        """Read an existing note."""
        path = Path(note_path)
        if not path.exists():
            return {"error": f"Note not found: {note_path}"}
        try:
            content = path.read_text(encoding="utf-8")
            return {
                "path": str(path), "name": path.stem, "content": content,
                "tags": _parse_tags(content), "links": _parse_links(content),
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat()
            }
        except Exception as e:
            return {"error": str(e)}
    
    def obsidian_note_append(note_path: str, content: str) -> str:
        """Append content to an existing note."""
        path = Path(note_path)
        if not path.exists():
            return f"ERROR: Note not found: {note_path}"
        try:
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing.rstrip() + "\\n\\n" + content + "\\n", encoding="utf-8")
            return f"SUCCESS: Appended to {note_path}"
        except Exception as e:
            return f"ERROR: {e}"
    
    def obsidian_knowledge_capture(title: str, content: str, source: str = "", tags: str = "", vault_path: str = "") -> str:
        """Capture knowledge as a new note with metadata."""
        timestamp = datetime.now().isoformat(timespec="minutes")
        parts = [f"# {title}", f"Captured: {timestamp}"]
        if source:
            parts.append(f"Source: {source}")
        if tags:
            parts.append("Tags: " + " ".join(f"#{t.strip()}" for t in tags.split(",")))
        parts.append("")
        parts.append(content)
        full_content = "\\n\\n".join(parts)
        return obsidian_note_create(title=title, content=full_content, vault_path=vault_path, folder="Clippings")
    
    return [
        {
            "name": "obsidian_vault_discover",
            "description": obsidian_vault_discover.__doc__,
            "parameters": {"type": "object", "properties": {}, "required": []},
            "execute": lambda **kw: obsidian_vault_discover()
        },
        {
            "name": "obsidian_vault_add",
            "description": obsidian_vault_add.__doc__,
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            "execute": obsidian_vault_add
        },
        {
            "name": "obsidian_vault_remove",
            "description": obsidian_vault_remove.__doc__,
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            "execute": obsidian_vault_remove
        },
        {
            "name": "obsidian_note_search",
            "description": obsidian_note_search.__doc__,
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "vault_path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
            "execute": obsidian_note_search
        },
        {
            "name": "obsidian_note_create",
            "description": obsidian_note_create.__doc__,
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "vault_path": {"type": "string"}, "folder": {"type": "string"}, "tags": {"type": "string"}, "links": {"type": "string"}}, "required": ["title"]},
            "execute": obsidian_note_create
        },
        {
            "name": "obsidian_daily_note",
            "description": obsidian_daily_note.__doc__,
            "parameters": {"type": "object", "properties": {"content": {"type": "string"}, "vault_path": {"type": "string"}}, "required": []},
            "execute": obsidian_daily_note
        },
        {
            "name": "obsidian_note_read",
            "description": obsidian_note_read.__doc__,
            "parameters": {"type": "object", "properties": {"note_path": {"type": "string"}}, "required": ["note_path"]},
            "execute": obsidian_note_read
        },
        {
            "name": "obsidian_note_append",
            "description": obsidian_note_append.__doc__,
            "parameters": {"type": "object", "properties": {"note_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["note_path", "content"]},
            "execute": obsidian_note_append
        },
        {
            "name": "obsidian_knowledge_capture",
            "description": obsidian_knowledge_capture.__doc__,
            "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "source": {"type": "string"}, "tags": {"type": "string"}, "vault_path": {"type": "string"}}, "required": ["title", "content"]},
            "execute": obsidian_knowledge_capture
        },
    ]
