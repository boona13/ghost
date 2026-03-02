"""Pull Requests API — PR management for the Git-backed review system."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_pr import get_pr_store

bp = Blueprint("prs", __name__, url_prefix="/api/prs")
store = get_pr_store()


@bp.route("/list")
def list_prs():
    """List PRs with optional status and feature_id filters.

    Strips the diff and full discussion text from list results to keep
    the payload small. Use GET /api/prs/<pr_id> for full details.
    """
    status = request.args.get("status", "")
    feature_id = request.args.get("feature_id", "")
    limit = request.args.get("limit", 50, type=int)

    prs = store.list_prs(
        status=status or None,
        feature_id=feature_id or None,
    )
    summary_fields = ("pr_id", "evolution_id", "feature_id", "branch",
                      "title", "status", "verdict", "blocked_reason",
                      "files_changed", "review_rounds", "max_rounds",
                      "created_at", "merged_at")
    summaries = [
        {k: pr[k] for k in summary_fields if k in pr}
        for pr in prs[:limit]
    ]
    return jsonify({"ok": True, "prs": summaries})


@bp.route("/<pr_id>")
def get_pr(pr_id):
    """Get a single PR with full details."""
    pr = store.get_pr(pr_id)
    if not pr:
        return jsonify({"ok": False, "error": "PR not found"}), 404
    return jsonify({"ok": True, "pr": pr})


@bp.route("/<pr_id>/force-approve", methods=["POST"])
def force_approve(pr_id):
    """Force-approve a PR (user override).

    Attempts merge first — only marks approved if merge succeeds, so the
    PR never ends up in an 'approved but not merged' limbo state.
    """
    pr = store.get_pr(pr_id)
    if not pr:
        return jsonify({"ok": False, "error": "PR not found"}), 404
    if pr["status"] == "merged":
        return jsonify({"ok": False, "error": "PR already merged"}), 400

    try:
        import ghost_git
        branch = pr.get("branch", "")
        if not branch or not ghost_git.branch_exists(branch):
            store.set_verdict(pr_id, "approved")
            return jsonify({"ok": True, "merged": False,
                            "message": "PR force-approved. Branch no longer exists — manual merge needed."})

        ghost_git.checkout("main")
        ok, msg = ghost_git.merge(branch)
        if not ok:
            return jsonify({"ok": False,
                            "error": f"Merge failed: {msg}. PR status unchanged."}), 500

        ghost_git.delete_branch(branch)
        store.set_verdict(pr_id, "approved")
        store.mark_merged(pr_id)

        feature_id = pr.get("feature_id")
        if feature_id:
            try:
                from ghost_future_features import FutureFeaturesStore
                FutureFeaturesStore().mark_implemented(
                    feature_id, f"Force-approved via dashboard (PR {pr_id})")
            except Exception:
                log.warning("Failed to mark feature as implemented", exc_info=True)

        from ghost_evolve import DEPLOY_MARKER, get_engine
        import json, time
        backup_path = None
        evo = get_engine()._active_evolutions.get(
            pr.get("evolution_id", ""))
        if evo:
            backup_path = evo.get("backup_path")
        DEPLOY_MARKER.write_text(json.dumps({
            "evolution_id": pr.get("evolution_id", "force_approve"),
            "backup_path": backup_path,
            "timestamp": time.time(),
        }))
        return jsonify({"ok": True, "merged": True,
                        "message": "PR force-approved and merged. Ghost will restart."})
    except Exception as e:
        return jsonify({"ok": False,
                        "error": f"Merge error: {e}. PR status unchanged."}), 500


@bp.route("/<pr_id>/force-block", methods=["POST"])
def force_block(pr_id):
    """Force-block a PR (user override)."""
    pr = store.get_pr(pr_id)
    if not pr:
        return jsonify({"ok": False, "error": "PR not found"}), 404

    data = request.get_json() or {}
    reason = data.get("reason", "Blocked by user")
    store.set_verdict(pr_id, "blocked", reason)

    try:
        import ghost_git
        branch = pr.get("branch", "")
        if branch and ghost_git.branch_exists(branch):
            ghost_git.checkout("main")
            ghost_git.delete_branch(branch)
    except Exception:
        log.warning("Failed to delete branch on force_block", exc_info=True)

    feature_id = pr.get("feature_id")
    if feature_id:
        try:
            from ghost_future_features import FutureFeaturesStore
            fs = FutureFeaturesStore()
            fs.mark_blocked(feature_id, reason)
            try:
                from ghost_dashboard.routes.future_features import _notify_queue
                _notify_queue()
            except Exception:
                log.warning("Failed to notify queue on force_block", exc_info=True)
        except Exception:
            log.warning("Failed to mark feature as blocked", exc_info=True)

    return jsonify({"ok": True, "message": "PR blocked and feature marked as blocked."})


@bp.route("/<pr_id>/force-merge", methods=["POST"])
def force_merge(pr_id):
    """Force-merge a PR regardless of review status (user override)."""
    pr = store.get_pr(pr_id)
    if not pr:
        return jsonify({"ok": False, "error": "PR not found"}), 404
    if pr["status"] == "merged":
        return jsonify({"ok": False, "error": "PR already merged"}), 400

    try:
        import ghost_git
        branch = pr.get("branch", "")
        if not branch or not ghost_git.branch_exists(branch):
            return jsonify({"ok": False, "error": "Feature branch not found"}), 400

        ghost_git.checkout("main")
        ok, msg = ghost_git.merge(branch)
        if not ok:
            return jsonify({"ok": False, "error": f"Merge failed: {msg}"}), 500

        ghost_git.delete_branch(branch)
        store.set_verdict(pr_id, "approved")
        store.mark_merged(pr_id)

        feature_id = pr.get("feature_id")
        if feature_id:
            try:
                from ghost_future_features import FutureFeaturesStore
                FutureFeaturesStore().mark_implemented(
                    feature_id, f"Force-merged via dashboard (PR {pr_id})")
            except Exception:
                log.warning("Failed to mark feature as implemented", exc_info=True)

        from ghost_evolve import DEPLOY_MARKER, get_engine
        import json, time
        backup_path = None
        evo = get_engine()._active_evolutions.get(
            pr.get("evolution_id", ""))
        if evo:
            backup_path = evo.get("backup_path")
        DEPLOY_MARKER.write_text(json.dumps({
            "evolution_id": pr.get("evolution_id", "force_merge"),
            "backup_path": backup_path,
            "timestamp": time.time(),
        }))
        return jsonify({"ok": True, "message": "PR force-merged. Ghost will restart."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/stats")
def pr_stats():
    """Get PR statistics."""
    all_prs = store.list_prs()
    stats = {
        "total": len(all_prs),
        "open": sum(1 for p in all_prs if p["status"] == "open"),
        "reviewing": sum(1 for p in all_prs if p["status"] == "reviewing"),
        "approved": sum(1 for p in all_prs if p["status"] == "approved"),
        "merged": sum(1 for p in all_prs if p["status"] == "merged"),
        "blocked": sum(1 for p in all_prs if p["status"] == "blocked"),
        "rejected": sum(1 for p in all_prs if p["status"] == "rejected"),
    }
    return jsonify({"ok": True, "stats": stats})
