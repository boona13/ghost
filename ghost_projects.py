"""
GHOST Projects System

First-class project/workspace scoping for skills, config, and memory.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

GHOST_HOME = Path.home() / ".ghost"
PROJECTS_FILE = GHOST_HOME / "projects.json"

DEFAULT_PROJECT_CONFIG = {
    "name": "",
    "description": "",
    "skills": [],
    "disabled_skills": [],
    "config_overrides": {},
    "memory_scope": "inherit",
    "auto_activate_paths": [],
    "env_vars": {},
}


@dataclass
class Project:
    id: str
    name: str
    path: Path
    config_path: Path
    config: Dict[str, Any] = field(default_factory=dict)
    last_modified: float = 0

    @property
    def ghost_dir(self) -> Path:
        return self.path / ".ghost"

    @property
    def skills_dir(self) -> Path:
        return self.ghost_dir / "skills"

    @property
    def memory_scope(self) -> str:
        return self.config.get("memory_scope", "inherit")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": str(self.path),
            "description": self.config.get("description", ""),
            "skills": self.config.get("skills", []),
            "disabled_skills": self.config.get("disabled_skills", []),
            "memory_scope": self.memory_scope,
            "config_overrides": self.config.get("config_overrides", {}),
            "auto_activate_paths": self.config.get("auto_activate_paths", []),
            "last_modified": self.last_modified,
        }


class ProjectRegistry:
    def __init__(self, projects_dirs: Optional[List[Path]] = None):
        self._projects: Dict[str, Project] = {}
        self._projects_dirs = projects_dirs or self._default_projects_dirs()
        self._last_scan = 0
        self._scan_interval = 30
        self._load_registry()

    def _default_projects_dirs(self) -> List[Path]:
        dirs = []
        desktop = Path.home() / "Desktop"
        if desktop.exists():
            dirs.append(desktop)
        documents = Path.home() / "Documents"
        if documents.exists():
            dirs.append(documents)
        projects = Path.home() / "Projects"
        dirs.append(projects)
        return dirs

    def _load_registry(self):
        if PROJECTS_FILE.exists():
            try:
                data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
                for pid, pdict in data.get("projects", {}).items():
                    self._projects[pid] = Project(
                        id=pid,
                        name=pdict.get("name", "Unnamed"),
                        path=Path(pdict["path"]),
                        config_path=Path(pdict["path"]) / ".ghost" / "project.json",
                        config=pdict.get("config", {}),
                        last_modified=pdict.get("last_modified", 0),
                    )
            except Exception:
                pass

    def _save_registry(self):
        GHOST_HOME.mkdir(parents=True, exist_ok=True)
        data = {
            "projects": {pid: p.to_dict() for pid, p in self._projects.items()},
            "last_scan": time.time(),
        }
        PROJECTS_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _project_id(self, path: Path) -> str:
        import hashlib
        return hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]

    def _load_project_config(self, config_path: Path) -> Dict[str, Any]:
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            config = dict(DEFAULT_PROJECT_CONFIG)
            config.update(data)
            return config
        except Exception:
            return dict(DEFAULT_PROJECT_CONFIG)

    def scan(self, force: bool = False) -> List[Project]:
        now = time.time()
        if not force and (now - self._last_scan) < self._scan_interval:
            return list(self._projects.values())

        found_paths = set()

        for base_dir in self._projects_dirs:
            if not base_dir.exists():
                continue
            for ghost_dir in base_dir.rglob(".ghost"):
                if not ghost_dir.is_dir():
                    continue
                config_path = ghost_dir / "project.json"
                if config_path.exists():
                    path = ghost_dir.parent
                    pid = self._project_id(path)
                    found_paths.add(pid)

                    mtime = config_path.stat().st_mtime
                    if pid in self._projects:
                        if mtime > self._projects[pid].last_modified:
                            config = self._load_project_config(config_path)
                            self._projects[pid].config = config
                            self._projects[pid].name = config.get("name", path.name)
                            self._projects[pid].last_modified = mtime
                    else:
                        config = self._load_project_config(config_path)
                        self._projects[pid] = Project(
                            id=pid,
                            name=config.get("name", path.name),
                            path=path,
                            config_path=config_path,
                            config=config,
                            last_modified=mtime,
                        )

        for pid in list(self._projects.keys()):
            if pid in found_paths:
                continue
            project = self._projects[pid]
            config_path = project.path / ".ghost" / "project.json"
            if not config_path.exists():
                del self._projects[pid]
            else:
                mtime = config_path.stat().st_mtime
                if mtime > project.last_modified:
                    config = self._load_project_config(config_path)
                    project.config = config
                    project.name = config.get("name", project.path.name)
                    project.last_modified = mtime

        self._last_scan = now
        self._save_registry()
        return list(self._projects.values())

    def get(self, project_id: str) -> Optional[Project]:
        self.scan()
        return self._projects.get(project_id)

    def get_by_path(self, path: Path) -> Optional[Project]:
        self.scan()
        path = Path(path).resolve()
        for project in self._projects.values():
            try:
                path.relative_to(project.path)
                return project
            except ValueError:
                continue
        return None

    def resolve(self, path: Path) -> Optional[Project]:
        return self.get_by_path(path)

    def create(self, path: Path, name: str, description: str = "") -> Project:
        path = Path(path).resolve()
        ghost_dir = path / ".ghost"
        ghost_dir.mkdir(parents=True, exist_ok=True)

        config_path = ghost_dir / "project.json"
        config = dict(DEFAULT_PROJECT_CONFIG)
        config["name"] = name
        config["description"] = description

        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        pid = self._project_id(path)
        project = Project(
            id=pid,
            name=name,
            path=path,
            config_path=config_path,
            config=config,
            last_modified=config_path.stat().st_mtime,
        )
        self._projects[pid] = project
        self._save_registry()
        return project

    def update(self, project_id: str, updates: Dict[str, Any]) -> Optional[Project]:
        project = self._projects.get(project_id)
        if not project:
            return None

        allowed = {"name", "description", "skills", "disabled_skills",
                   "config_overrides", "memory_scope", "auto_activate_paths", "env_vars"}
        for key in allowed & set(updates.keys()):
            project.config[key] = updates[key]

        if "name" in updates:
            project.name = updates["name"]

        project.config_path.write_text(json.dumps(project.config, indent=2), encoding="utf-8")
        project.last_modified = project.config_path.stat().st_mtime
        self._save_registry()
        return project

    def delete(self, project_id: str) -> bool:
        if project_id in self._projects:
            del self._projects[project_id]
            self._save_registry()
            return True
        return False

    def list_all(self) -> List[Project]:
        self.scan()
        return sorted(self._projects.values(), key=lambda p: p.name.lower())


@dataclass
class ProjectContext:
    project: Project
    effective_config: Dict[str, Any] = field(default_factory=dict)
    enabled_skills: List[str] = field(default_factory=list)
    disabled_skills: List[str] = field(default_factory=list)

    def is_skill_enabled(self, skill_name: str) -> bool:
        if skill_name in self.disabled_skills:
            return False
        if self.enabled_skills:
            return skill_name in self.enabled_skills
        return True


def resolve_project_context(path: Path, base_config: Dict[str, Any]) -> Optional[ProjectContext]:
    registry = ProjectRegistry()
    project = registry.resolve(path)
    if not project:
        return None

    effective = dict(base_config)
    effective.update(project.config.get("config_overrides", {}))

    skills = project.config.get("skills", [])
    disabled = project.config.get("disabled_skills", [])

    return ProjectContext(
        project=project,
        effective_config=effective,
        enabled_skills=skills,
        disabled_skills=disabled,
    )


def get_active_project(cwd: Optional[Path] = None) -> Optional[Project]:
    if cwd is None:
        cwd = Path.cwd()
    registry = ProjectRegistry()
    return registry.resolve(cwd)


def format_project_for_prompt(project: Project) -> str:
    lines = [
        f"## ACTIVE PROJECT: {project.name}",
        f"Project path: {project.path}",
    ]
    if project.config.get("description"):
        lines.append(f"Description: {project.config['description']}")

    skills = project.config.get("skills", [])
    if skills:
        lines.append(f"Enabled skills: {', '.join(skills)}")

    disabled = project.config.get("disabled_skills", [])
    if disabled:
        lines.append(f"Disabled skills: {', '.join(disabled)}")

    lines.append(f"Memory scope: {project.memory_scope}")
    return "\n".join(lines)

def build_project_tools(registry: ProjectRegistry, base_config: Dict[str, Any]):
    """Build project-related tools for the LLM."""

    def project_list():
        """List all discovered projects."""
        projects = registry.list_all()
        return {
            "projects": [p.to_dict() for p in projects],
            "count": len(projects),
        }

    def project_get(project_id: str = ""):
        """Get details of a specific project by ID, or current project if empty."""
        if not project_id:
            project = get_active_project()
        else:
            project = registry.get(project_id)
        if not project:
            return {"error": "Project not found"}
        return project.to_dict()

    def project_create(path: str, name: str, description: str = ""):
        """Create a new project at the given path."""
        try:
            project = registry.create(Path(path), name, description)
            return {"ok": True, "project": project.to_dict()}
        except Exception as e:
            return {"error": str(e)}

    def project_update(project_id: str, **updates):
        """Update project configuration."""
        project = registry.update(project_id, updates)
        if not project:
            return {"error": "Project not found"}
        return {"ok": True, "project": project.to_dict()}

    def project_delete(project_id: str):
        """Remove project from registry (does not delete files)."""
        ok = registry.delete(project_id)
        return {"ok": ok}

    def project_resolve(path: str = ""):
        """Resolve which project contains the given path (or current directory)."""
        p = Path(path) if path else Path.cwd()
        project = registry.resolve(p)
        if not project:
            return {"project": None}
        ctx = resolve_project_context(p, base_config)
        return {
            "project": project.to_dict(),
            "effective_config_keys": list(ctx.effective_config.keys()) if ctx else [],
        }

    return [
        {
            "name": "project_list",
            "description": "List all discovered Ghost projects",
            "parameters": {"type": "object", "properties": {}},
            "execute": lambda **kw: project_list(),
        },
        {
            "name": "project_get",
            "description": "Get details of a specific project by ID, or the current active project",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID (omit for current project)"},
                },
            },
            "execute": project_get,
        },
        {
            "name": "project_create",
            "description": (
                "Create a new Ghost project at the given path. "
                "If the user doesn't specify a location, use "
                f"{Path.home() / 'Projects'}/<project-name> as the default. "
                "The directory will be created if it doesn't exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Absolute directory path for the project. "
                            f"Default to {Path.home() / 'Projects'}/<project-name> "
                            "if the user doesn't specify."
                        ),
                    },
                    "name": {"type": "string", "description": "Display name for the project"},
                    "description": {"type": "string", "description": "Optional description of the project purpose"},
                },
                "required": ["path", "name"],
            },
            "execute": project_create,
        },
        {
            "name": "project_update",
            "description": "Update project configuration (name, skills, config_overrides, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID to update"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "disabled_skills": {"type": "array", "items": {"type": "string"}},
                    "config_overrides": {"type": "object"},
                    "memory_scope": {"type": "string", "enum": ["isolated", "shared", "inherit"]},
                },
                "required": ["project_id"],
            },
            "execute": project_update,
        },
        {
            "name": "project_delete",
            "description": "Remove a project from the registry (does not delete files)",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project ID to delete"},
                },
                "required": ["project_id"],
            },
            "execute": project_delete,
        },
        {
            "name": "project_resolve",
            "description": "Resolve which project contains the given path (or current directory)",
            "parameters": {
                "type": "object",
                "properties": {

                    "path": {"type": "string", "description": "Path to resolve (omit for current directory)"},
                },
            },
            "execute": project_resolve,
        },
    ]
