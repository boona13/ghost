"""Skills API — list, view, edit, enable/disable, requirements check."""

import os
import shutil
import platform
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_skills import SkillLoader, SKILLS_BUNDLED_DIR, SKILLS_USER_DIR
from ghost import load_config, save_config
from ghost_skill_registry import SkillRegistryClient, SkillRegistryManager

bp = Blueprint("skills", __name__)

_standalone_loader = None


def _get_loader():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and daemon.skill_loader:
        daemon.skill_loader.check_reload()
        return daemon.skill_loader

    global _standalone_loader
    if _standalone_loader is None:
        _standalone_loader = SkillLoader()
    else:
        _standalone_loader.check_reload()
    return _standalone_loader


def _check_bin(name):
    return shutil.which(name) is not None


def _check_env(name):
    return bool(os.environ.get(name))


def _skill_source(skill_path):
    p = str(skill_path)
    bundled = str(SKILLS_BUNDLED_DIR)
    user = str(SKILLS_USER_DIR)
    if p.startswith(bundled):
        return "bundled"
    elif p.startswith(user):
        return "user"
    return "other"


def _build_skill_status(skill, disabled_skills):
    """Build a full status report for a single skill."""
    requires = skill.requires or {}

    req_bins = requires.get("bins", [])
    if isinstance(req_bins, str):
        req_bins = [req_bins]
    req_env = requires.get("env", [])
    if isinstance(req_env, str):
        req_env = [req_env]

    missing_bins = [b for b in req_bins if not _check_bin(b)]
    missing_env = [e for e in req_env if not _check_env(e)]

    source = _skill_source(skill.path)
    disabled = skill.name in disabled_skills
    os_ok = True
    if skill.os_filter:
        os_list = skill.os_filter if isinstance(skill.os_filter, list) else [skill.os_filter]
        os_ok = platform.system().lower() in [o.lower() for o in os_list]

    eligible = (not disabled) and os_ok and (not missing_bins) and (not missing_env)

    return {
        "name": skill.name,
        "description": skill.description or "",
        "triggers": skill.triggers or [],
        "tools": skill.tools or [],
        "priority": skill.priority,
        "os_filter": skill.os_filter,
        "path": skill.path,
        "source": source,
        "disabled": disabled,
        "eligible": eligible,
        "os_ok": os_ok,
        "model": skill.model,  # Per-skill model override
        "requirements": {
            "bins": req_bins,
            "env": req_env,
        },
        "missing": {
            "bins": missing_bins,
            "env": missing_env,
        },
    }


@bp.route("/api/skills")
def list_skills():
    loader = _get_loader()
    cfg = load_config()
    disabled_skills = set(cfg.get("disabled_skills", []))

    skills = []
    for s in loader.list_all():
        skills.append(_build_skill_status(s, disabled_skills))
    skills.sort(key=lambda x: x["name"])

    bundled = [s for s in skills if s["source"] == "bundled"]
    user = [s for s in skills if s["source"] == "user"]
    other = [s for s in skills if s["source"] == "other"]

    total = len(skills)
    eligible_count = sum(1 for s in skills if s["eligible"])
    disabled_count = sum(1 for s in skills if s["disabled"])
    missing_count = sum(1 for s in skills if s["missing"]["bins"] or s["missing"]["env"])

    return jsonify({
        "groups": {
            "bundled": bundled,
            "user": user,
            "other": other,
        },
        "stats": {
            "total": total,
            "eligible": eligible_count,
            "disabled": disabled_count,
            "missing_reqs": missing_count,
        },
        "bundled_dir": str(SKILLS_BUNDLED_DIR),
        "user_dir": str(SKILLS_USER_DIR),
    })


@bp.route("/api/skills/<name>")
def get_skill(name):
    loader = _get_loader()
    skill = loader.skills.get(name)
    if not skill:
        return jsonify({"error": f"Skill '{name}' not found"}), 404
    try:
        content = Path(skill.path).read_text()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    cfg = load_config()
    disabled_skills = set(cfg.get("disabled_skills", []))
    status = _build_skill_status(skill, disabled_skills)
    status["content"] = content

    return jsonify(status)


@bp.route("/api/skills/<name>", methods=["PUT"])
def update_skill(name):
    loader = _get_loader()
    skill = loader.skills.get(name)
    if not skill:
        return jsonify({"error": f"Skill '{name}' not found"}), 404

    data = request.get_json(silent=True) or {}

    if "content" in data:
        try:
            Path(skill.path).write_text(data["content"])
            loader.reload()
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if "enabled" in data:
        cfg = load_config()
        disabled = set(cfg.get("disabled_skills", []))
        if data["enabled"]:
            disabled.discard(name)
        else:
            disabled.add(name)
        cfg["disabled_skills"] = sorted(disabled)
        save_config(cfg)

    return jsonify({"ok": True})


# Registry (GhostHub) endpoints

@bp.route("/api/skills/registry/search")
def registry_search():
    """Search the public skill registry."""
    query = request.args.get("q", "")
    tags = request.args.getlist("tag")
    author = request.args.get("author", "")
    force_refresh = request.args.get("refresh", "false").lower() == "true"

    try:
        client = SkillRegistryClient()
        skills = client.search_skills(
            query=query,
            tags=tags if tags else None,
            author=author,
            force_refresh=force_refresh,
        )
        return jsonify({
            "ok": True,
            "count": len(skills),
            "skills": [s.to_dict() for s in skills],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/skills/registry/<name>")
def registry_get_skill(name):
    """Get a specific skill from the registry."""
    try:
        client = SkillRegistryClient()
        skill = client.get_skill(name)
        if not skill:
            return jsonify({"ok": False, "error": "Skill not found"}), 404
        return jsonify({"ok": True, "skill": skill.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/skills/registry/<name>/install", methods=["POST"])
def registry_install(name):
    """Install a skill from the registry."""
    data = request.get_json(silent=True) or {}
    overwrite = data.get("overwrite", False)

    try:
        manager = SkillRegistryManager(load_config, save_config)
        result = manager.install_skill(name, overwrite=overwrite)
        if result.get("ok"):
            # Reload skills after install
            loader = _get_loader()
            loader.reload()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/skills/registry/stats")
def registry_stats():
    """Get registry statistics."""
    try:
        client = SkillRegistryClient()
        skills = client.list_skills()
        tags = set()
        authors = set()
        for s in skills:
            tags.update(s.tags or [])
            if s.author:
                authors.add(s.author)
        return jsonify({
            "ok": True,
            "total_skills": len(skills),
            "unique_tags": len(tags),
            "unique_authors": len(authors),
            "tags": sorted(tags)[:50],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/skills/registry/refresh", methods=["POST"])
def registry_refresh():
    """Force refresh the registry cache."""
    try:
        client = SkillRegistryClient()
        # Force refresh by fetching with force=True
        data = client.fetch_index(force=True)
        skills = client.list_skills(force_refresh=True)
        return jsonify({
            "ok": True,
            "message": f"Registry cache refreshed. {len(skills)} skills available.",
            "count": len(skills),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
