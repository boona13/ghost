"""Ghost Extensions API — extension management, pages, settings."""

import logging
from pathlib import Path
from flask import Blueprint, jsonify, request

from ghost_dashboard.rate_limiter import rate_limit

log = logging.getLogger(__name__)

bp = Blueprint("extensions", __name__)


def _get_daemon():
    from ghost_dashboard import get_daemon
    return get_daemon()


def _get_ext_manager():
    daemon = _get_daemon()
    if daemon and hasattr(daemon, "extension_manager"):
        return daemon.extension_manager
    return None


@bp.route("/api/extensions")
def list_extensions():
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"extensions": [], "error": "Extension system not initialized"}), 503

    category = request.args.get("category", "")
    exts = mgr.list_extensions(category=category or None)
    categories = {}
    for e in exts:
        m = e.get("manifest") or {}
        cat = m.get("category", "utility")
        categories.setdefault(cat, 0)
        categories[cat] += 1

    return jsonify({
        "extensions": exts,
        "total": len(exts),
        "categories": categories,
    })


@bp.route("/api/extensions/<name>")
def get_extension(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503

    info = mgr.get_extension(name)
    if not info:
        return jsonify({"error": "Extension not found"}), 404
    return jsonify(info.to_dict())


@bp.route("/api/extensions/<name>/enable", methods=["POST"])
def enable_extension(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503
    ok = mgr.enable_extension(name)
    # Audit log
    try:
        from ghost_audit_log import get_audit_log, AuditAction
        audit = get_audit_log()
        audit.log(
            action=AuditAction.EXTENSION_ENABLE,
            resource_type="extension",
            resource_id=name,
            success=ok,
        )
    except Exception as e:
        logging.getLogger("ghost.audit").warning("Audit log failed: %s", e)
    return jsonify({"ok": ok, "message": f"Enabled {name}" if ok else "Extension not found"})


@bp.route("/api/extensions/<name>/disable", methods=["POST"])
def disable_extension(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503
    ok = mgr.disable_extension(name)
    # Audit log
    try:
        from ghost_audit_log import get_audit_log, AuditAction
        audit = get_audit_log()
        audit.log(
            action=AuditAction.EXTENSION_DISABLE,
            resource_type="extension",
            resource_id=name,
            success=ok,
        )
    except Exception as e:
        logging.getLogger("ghost.audit").warning("Audit log failed: %s", e)
    return jsonify({"ok": ok, "message": f"Disabled {name}" if ok else "Extension not found"})


@bp.route("/api/extensions/install", methods=["POST"])
@rate_limit(requests_per_minute=5)
def install_extension():
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503

    data = request.get_json(silent=True) or {}
    source = data.get("source", "")
    if not source:
        return jsonify({"error": "source is required"}), 400

    if source.startswith("https://github.com/") or source.startswith("git@github.com:"):
        result = mgr.install_from_github(source)
    else:
        result = mgr.install_local(source)
    # Audit log
    try:
        from ghost_audit_log import get_audit_log, AuditAction
        audit = get_audit_log()
        audit.log(
            action=AuditAction.EXTENSION_INSTALL,
            resource_type="extension",
            resource_id=source,
            success=result.get("ok", False),
            details={"source": source},
        )
    except Exception as e:
        logging.getLogger("ghost.audit").warning("Audit log failed: %s", e)
    return jsonify(result)


@bp.route("/api/extensions/<name>/uninstall", methods=["POST"])
def uninstall_extension(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503
    ok = mgr.uninstall_extension(name)
    # Audit log
    try:
        from ghost_audit_log import get_audit_log, AuditAction
        audit = get_audit_log()
        audit.log(
            action=AuditAction.EXTENSION_UNINSTALL,
            resource_type="extension",
            resource_id=name,
            success=ok,
        )
    except Exception as e:
        logging.getLogger("ghost.audit").warning("Audit log failed: %s", e)
    return jsonify({"ok": ok})


@bp.route("/api/extensions/pages")
def list_extension_pages():
    """Return all dashboard pages registered by loaded extensions."""
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"pages": []}), 503

    pages = mgr.get_all_pages()
    return jsonify({"pages": pages})


@bp.route("/api/extensions/<name>/settings")
def get_extension_settings(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503

    info = mgr.get_extension(name)
    if not info:
        return jsonify({"error": "Extension not found"}), 404

    settings = mgr.get_settings(name)
    schema = info.manifest.settings if info.manifest else []
    return jsonify({"settings": settings, "schema": schema})


@bp.route("/api/extensions/unified")
def unified_view():
    """Return unified view of extensions + nodes (convergence)."""
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"items": [], "error": "Extension system not initialized"}), 503

    items = mgr.get_unified_view()
    return jsonify({"items": items, "total": len(items)})


@bp.route("/api/extensions/<name>/settings", methods=["POST"])
def save_extension_settings(name):
    mgr = _get_ext_manager()
    if not mgr:
        return jsonify({"error": "Extension system not initialized"}), 503

    data = request.get_json(silent=True) or {}
    settings = data.get("settings", {})
    try:
        mgr.save_settings(name, settings)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


# ── Community Hub endpoints ────────────────────────────────────

def _get_hub():
    daemon = _get_daemon()
    if daemon and hasattr(daemon, "community_hub"):
        return daemon.community_hub
    return None


@bp.route("/api/hub/extensions")
def hub_extensions():
    """Browse community hub extensions."""
    hub = _get_hub()
    if not hub:
        return jsonify({"extensions": [], "error": "Community Hub not initialized"})

    query = request.args.get("q", "")
    category = request.args.get("category", "")
    force = request.args.get("refresh", "") == "1"

    if query:
        items = hub.search(query, category=category, kind="extensions")
    else:
        items = hub.fetch_extensions_index(force_refresh=force)
        if category:
            items = [i for i in items if i.get("category") == category]

    return jsonify({"extensions": items, "total": len(items)})


@bp.route("/api/hub/nodes")
def hub_nodes():
    """Browse community hub nodes."""
    hub = _get_hub()
    if not hub:
        return jsonify({"nodes": [], "error": "Community Hub not initialized"})

    query = request.args.get("q", "")
    category = request.args.get("category", "")
    force = request.args.get("refresh", "") == "1"

    if query:
        items = hub.search(query, category=category, kind="nodes")
    else:
        items = hub.fetch_nodes_index(force_refresh=force)
        if category:
            items = [i for i in items if i.get("category") == category]

    return jsonify({"nodes": items, "total": len(items)})


@bp.route("/api/hub/install", methods=["POST"])
@rate_limit(requests_per_minute=10)
def hub_install():
    """Install an extension or node from the community hub."""
    hub = _get_hub()
    if not hub:
        return jsonify({"error": "Community Hub not initialized"}), 503

    daemon = _get_daemon()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    kind = data.get("kind", "extension")

    if not name:
        return jsonify({"error": "name is required"}), 400

    if kind == "node":
        nm = getattr(daemon, "node_manager", None) if daemon else None
        if not nm:
            return jsonify({"error": "Node manager not available"}), 503
        result = hub.install_node_from_hub(name, nm)
    else:
        mgr = _get_ext_manager()
        if not mgr:
            return jsonify({"error": "Extension manager not available"}), 503
        result = hub.install_from_hub(name, mgr)

    return jsonify(result)


@bp.route("/api/hub/publish", methods=["POST"])
def hub_publish():
    """Publish an extension or node to the community hub."""
    hub = _get_hub()
    if not hub:
        return jsonify({"error": "Community Hub not initialized"}), 503

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    kind = data.get("kind", "extension")

    if not name:
        return jsonify({"error": "name is required"}), 400

    daemon = _get_daemon()
    if kind == "node":
        nm = getattr(daemon, "node_manager", None) if daemon else None
        if not nm:
            return jsonify({"error": "Node manager not available"}), 503
        info = nm.get_node(name)
        if not info:
            return jsonify({"error": f"Node '{name}' not found"}), 404
        result = hub.publish_node(Path(info.path))
    else:
        mgr = _get_ext_manager()
        if not mgr:
            return jsonify({"error": "Extension manager not available"}), 503
        info = mgr.get_extension(name)
        if not info:
            return jsonify({"error": f"Extension '{name}' not found"}), 404
        result = hub.publish_extension(Path(info.path))

    return jsonify(result)


@bp.route("/api/hub/status")
def hub_status():
    """Check community hub connectivity."""
    hub = _get_hub()
    if not hub:
        return jsonify({"reachable": False, "error": "Community Hub not initialized"})
    return jsonify(hub.get_hub_status())
