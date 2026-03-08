"""
Ghost Future Features System — Prioritized backlog for autonomous feature implementation.

Provides:
  - FutureFeaturesStore: CRUD for feature queue with prioritization
  - Feature prioritization logic (priority + dependencies + readiness)
  - Integration with growth routines for autonomous impl
  - LLM-callable tools for adding/listing/updating features

Tech Scout and Competitive Intel add features here instead of dropping them.
The feature_implementer routine picks highest-priority items and implements them.
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

GHOST_HOME = Path.home() / ".ghost"
FUTURE_FEATURES_FILE = GHOST_HOME / "future_features.json"
FEATURE_CHANGELOG_FILE = GHOST_HOME / "feature_changelog.json"

# Priority levels (P0 requires approval, P1-P3 auto-implement)
PRIORITY_LEVELS = {
    "P0": 100,  # Critical - requires user approval
    "P1": 75,   # High - auto-implement
    "P2": 50,   # Medium - auto-implement when idle
    "P3": 25,   # Low - manual trigger only
    # Legacy mappings for backwards compatibility
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}

# Feature statuses
STATUS_PENDING = "pending"
STATUS_APPROVAL_REQUIRED = "approval_required"
STATUS_IN_PROGRESS = "in_progress"
STATUS_IMPLEMENTED = "implemented"
STATUS_COMPLETED = "completed"  # Alias
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
STATUS_REVIEW_REJECTED = "review_rejected"
STATUS_DEFERRED = "deferred"
FEATURE_STATUSES = [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, 
                    STATUS_IMPLEMENTED, STATUS_COMPLETED, STATUS_FAILED, STATUS_REJECTED,
                    STATUS_REVIEW_REJECTED, STATUS_DEFERRED]

# Feature sources
SOURCE_TECH_SCOUT = "tech_scout"
SOURCE_COMPETITIVE_INTEL = "competitive_intel"
SOURCE_USER_REQUEST = "user_request"
SOURCE_USER = "user"
SOURCE_ACTION_ITEM = "action_item"
SOURCE_BUG_HUNTER = "bug_hunter"
SOURCE_MANUAL = "manual"
SOURCE_OTHER = "other"
SOURCE_IMPL_AUDITOR = "implementation_auditor"
FEATURE_SOURCES = [SOURCE_TECH_SCOUT, SOURCE_COMPETITIVE_INTEL, SOURCE_USER_REQUEST, 
                   SOURCE_USER, SOURCE_ACTION_ITEM, SOURCE_BUG_HUNTER, SOURCE_MANUAL, SOURCE_OTHER,
                   SOURCE_IMPL_AUDITOR]

# Feature categories
CATEGORY_FEATURE = "feature"
CATEGORY_BUGFIX = "bugfix"
CATEGORY_SECURITY = "security"
CATEGORY_REFACTOR = "refactor"
CATEGORY_IMPROVEMENT = "improvement"
CATEGORY_SOUL_UPDATE = "soul_update"
FEATURE_CATEGORIES = [
    CATEGORY_FEATURE, CATEGORY_BUGFIX, CATEGORY_SECURITY,
    CATEGORY_REFACTOR, CATEGORY_IMPROVEMENT, CATEGORY_SOUL_UPDATE,
]


def _classify_implementation_type(category: str) -> str:
    """Classify implementation type for a feature.

    All features are implemented as core changes via the evolve pipeline.
    """
    return "core"


class FutureFeaturesStore:
    """CRUD for future feature backlog."""

    def __init__(self):
        GHOST_HOME.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if FUTURE_FEATURES_FILE.exists():
            try:
                return json.loads(FUTURE_FEATURES_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, items: List[Dict]):
        FUTURE_FEATURES_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def add(self, title: str, description: str, priority: str = "P2",
            source: str = SOURCE_MANUAL, dependencies: List[str] = None,
            estimated_effort: str = "medium", auto_implement: bool = True,
            source_detail: str = "", tags: List[str] = None,
            category: str = CATEGORY_FEATURE,
            affected_files: str = "", proposed_approach: str = "") -> Dict:
        """Add a new feature to the backlog."""
        features = self._load()
        
        # Normalize priority
        priority = priority.lower() if priority else "P2"
        if priority in ["critical", "high", "medium", "low"]:
            mapping = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}
            priority = mapping.get(priority, "P2")
        priority = priority.upper()
        if priority not in PRIORITY_LEVELS:
            priority = "P2"

        # Normalize category
        if category not in FEATURE_CATEGORIES:
            category = CATEGORY_FEATURE
        
        # Check for duplicates: exact title match against active AND implemented features
        title_lower = title.lower()
        title_words = set(title_lower.split())
        for f in features:
            f_title = f.get("title", "").lower()
            f_status = f.get("status", "")

            if f_title == title_lower:
                if f_status in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_REVIEW_REJECTED]:
                    return {**f, "_warning": "Duplicate feature (already in backlog)"}
                if f_status in [STATUS_IMPLEMENTED, STATUS_COMPLETED]:
                    return {**f, "_warning": "Duplicate feature (already implemented)"}

            # Fuzzy match: if 70%+ of words overlap, likely the same feature
            if f_status in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS,
                            STATUS_REVIEW_REJECTED, STATUS_IMPLEMENTED, STATUS_COMPLETED]:
                f_words = set(f_title.split())
                if title_words and f_words:
                    overlap = len(title_words & f_words) / max(len(title_words), len(f_words))
                    if overlap >= 0.7:
                        label = "already implemented" if f_status in [STATUS_IMPLEMENTED, STATUS_COMPLETED] else "already in backlog"
                        return {**f, "_warning": f"Similar feature ({label}): '{f.get('title', '')}'"}

        
        # P0 always requires approval, regardless of auto_implement
        status = STATUS_APPROVAL_REQUIRED if priority == "P0" else STATUS_PENDING
        if not auto_implement and priority != "P0":
            status = STATUS_APPROVAL_REQUIRED
        
        impl_type = _classify_implementation_type(category)

        feature = {
            "id": uuid.uuid4().hex[:10],
            "title": title,
            "description": description,
            "priority": priority,
            "priority_score": PRIORITY_LEVELS.get(priority, 50),
            "category": category,
            "implementation_type": impl_type,
            "source": source,
            "source_detail": source_detail,
            "affected_files": affected_files,
            "proposed_approach": proposed_approach,
            "status": status,
            "dependencies": dependencies or [],
            "estimated_effort": estimated_effort,
            "auto_implement": auto_implement,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "started_at": None,
            "implemented_at": None,
            "completed_at": None,
            "implementation_attempts": 0,
            "implementation_log": [],
            "last_error": None,
            "evolution_id": None,
        }
        features.insert(0, feature)
        self._save(features)
        return feature

    def get_by_id(self, feature_id: str) -> Optional[Dict]:
        """Get a feature by ID."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                return f
        return None

    def get_pending(self, limit: Optional[int] = None) -> List[Dict]:
        """Get actionable features sorted by priority.

        Includes ``pending``, ``approval_required``, and ``review_rejected``
        (the latter have branch context for fix-and-resubmit).
        """
        features = self._load()
        pending = [
            f for f in features 
            if f.get("status") in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_REVIEW_REJECTED]
        ]
        pending.sort(key=lambda x: (-x.get("priority_score", 0), x.get("created_at", "")))
        if limit:
            pending = pending[:limit]
        return pending

    def get_all(self, status_filter: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get all features, optionally filtered by status."""
        features = self._load()
        if status_filter:
            features = [f for f in features if f.get("status") == status_filter]
        return features[:limit]

    def get_next_implementable(self) -> Optional[Dict]:
        """Get the highest priority feature that can be implemented now.

        Picks up both fresh ``pending`` features and ``review_rejected`` features
        that are past their cooldown window (the latter have branch context
        preserved for fix-and-resubmit).
        """
        features = self._load()
        pending = [
            f for f in features 
            if f.get("status") in (STATUS_PENDING, STATUS_REVIEW_REJECTED)
            and f.get("auto_implement", True)
        ]
        
        if not pending:
            return None
        
        # Sort by priority score (desc), then by creation date (asc - older first)
        pending.sort(key=lambda f: (-f.get("priority_score", 0), f.get("created_at", "")))
        
        # Find first feature with all dependencies satisfied
        implemented_ids = {f["id"] for f in features if f.get("status") in [STATUS_IMPLEMENTED, STATUS_COMPLETED]}
        now = datetime.now()
        
        for feature in pending:
            retry_after = feature.get("retry_after")
            if retry_after:
                try:
                    if datetime.fromisoformat(retry_after) > now:
                        continue
                except (ValueError, TypeError):
                    pass
            deps = feature.get("dependencies", [])
            if all(dep_id in implemented_ids for dep_id in deps):
                return feature
        
        return None

    def has_in_progress(self) -> bool:
        """Return True if any feature is currently being implemented."""
        features = self._load()
        return any(f.get("status") == STATUS_IN_PROGRESS for f in features)

    def is_queue_ready(self) -> bool:
        """Return True if there's implementable work AND nothing is in progress."""
        if self.has_in_progress():
            return False
        return self.get_next_implementable() is not None

    def mark_in_progress(self, feature_id: str, evolution_id: str = None,
                         force: bool = False) -> tuple:
        """Mark a feature as being implemented.

        Returns (success: bool, error: str | None).
        Rejects if another feature is already in_progress, unless force=True.
        Rejects if the feature is still in cooldown (retry_after not yet reached).
        """
        features = self._load()

        if not force:
            already_running = [
                f for f in features
                if f.get("status") == STATUS_IN_PROGRESS and f["id"] != feature_id
            ]
            if already_running:
                other = already_running[0]
                return False, f"Another feature is already being implemented: [{other['id']}] {other.get('title', '?')}"

        for f in features:
            if f["id"] == feature_id:
                current_status = f.get("status", "")
                if current_status in (STATUS_IMPLEMENTED, STATUS_COMPLETED, STATUS_REJECTED) and not force:
                    return False, (
                        f"Feature is already {current_status} and cannot be re-started. "
                        f"Use a new feature entry if re-implementation is needed."
                    )
                retry_after = f.get("retry_after")
                if retry_after and not force:
                    try:
                        cooldown_end = datetime.fromisoformat(retry_after)
                        now = datetime.now()
                        if cooldown_end > now:
                            remaining_s = int((cooldown_end - now).total_seconds())
                            remaining_min = max(1, remaining_s // 60)
                            return False, (
                                f"Feature is in cooldown (~{remaining_min} min remaining). "
                                f"Pick a DIFFERENT feature from the list. This feature will "
                                f"be available after {retry_after}."
                            )
                    except (ValueError, TypeError):
                        pass
                f["status"] = STATUS_IN_PROGRESS
                f["updated_at"] = datetime.now().isoformat()
                is_resume = bool(f.get("current_branch") and f.get("current_evolution_id"))
                if not is_resume:
                    f["started_at"] = datetime.now().isoformat()
                    f["implementation_attempts"] = f.get("implementation_attempts", 0) + 1
                if evolution_id:
                    f["evolution_id"] = evolution_id
                self._save(features)
                return True, None
        return False, "Feature not found"

    def reset_stale_in_progress(self, max_age_seconds: int = 3600) -> List[str]:
        """Reset features stuck in_progress for longer than max_age_seconds back to pending.

        This handles the case where Ghost restarts (due to deploy or crash) while
        the Evolution Runner is mid-implementation, leaving a feature in_progress forever.
        If the feature's evolution_id was successfully deployed, mark it as implemented
        instead of resetting (handles the case where evolve_deploy ran before
        complete_future_feature).
        Returns list of reset feature IDs.
        """
        deploy_info = []  # list of (timestamp, evolution_id)
        try:
            evolve_history = GHOST_HOME / "evolve" / "history.json"
            if evolve_history.exists():
                history = json.loads(evolve_history.read_text(encoding="utf-8"))
                if isinstance(history, list):
                    for entry in history:
                        if entry.get("status") == "deployed" and entry.get("deployed_at"):
                            try:
                                dt = datetime.fromisoformat(entry["deployed_at"])
                                evo_id = entry.get("id", "")
                                deploy_info.append((dt, evo_id))
                            except (ValueError, TypeError):
                                pass
        except Exception:
            pass

        # Also check last_deploy.json for the most recent deploy
        try:
            last_deploy = GHOST_HOME / "evolve" / "last_deploy.json"
            if last_deploy.exists():
                ld = json.loads(last_deploy.read_text(encoding="utf-8"))
                if ld.get("feature_id"):
                    deploy_info.append((datetime.now(), ld.get("evolution_id", "")))
        except Exception:
            pass

        features = self._load()
        reset_ids = []
        changed = False
        now = datetime.now()
        for f in features:
            if f.get("status") != STATUS_IN_PROGRESS:
                continue
            started = f.get("started_at", "")
            if not started:
                f["status"] = STATUS_PENDING
                f["updated_at"] = now.isoformat()
                reset_ids.append(f["id"])
                changed = True
                continue
            try:
                started_dt = datetime.fromisoformat(started)
                age = (now - started_dt).total_seconds()
                if age > max_age_seconds:
                    feature_evo_id = f.get("evolution_id", "")
                    # First: try exact match via evolution_id
                    evo_match = any(
                        evo_id == feature_evo_id
                        for _, evo_id in deploy_info
                        if feature_evo_id and evo_id
                    )
                    # Fallback: any deploy at or after the feature started
                    time_match = any(dt >= started_dt for dt, _ in deploy_info)

                    if evo_match or time_match:
                        f["status"] = STATUS_IMPLEMENTED
                        f["updated_at"] = now.isoformat()
                        f["completed_at"] = now.isoformat()
                        f["implemented_at"] = now.isoformat()
                        changed = True
                    else:
                        f["status"] = STATUS_PENDING
                        f["updated_at"] = now.isoformat()
                        reset_ids.append(f["id"])
                        changed = True
            except (ValueError, TypeError):
                continue
        if changed:
            self._save(features)
        return reset_ids

    def approve(self, feature_id: str) -> bool:
        """Approve a feature for implementation (moves from approval_required to pending)."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                if f.get("status") == STATUS_APPROVAL_REQUIRED:
                    f["status"] = STATUS_PENDING
                    f["updated_at"] = datetime.now().isoformat()
                    self._save(features)
                    return True
        return False

    def reject(self, feature_id: str, reason: str = "") -> bool:
        """Reject a feature."""
        return self._update_status(feature_id, STATUS_REJECTED, reason)

    def mark_implemented(self, feature_id: str, details: str = "") -> bool:
        """Mark a feature as successfully implemented."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                f["status"] = STATUS_IMPLEMENTED
                f["updated_at"] = datetime.now().isoformat()
                f["implemented_at"] = datetime.now().isoformat()
                f["completed_at"] = datetime.now().isoformat()
                f["implementation_details"] = details
                self._save(features)
                return True
        return False

    def mark_audited(self, feature_id: str, result: str, notes: str = "") -> bool:
        """Stamp a feature as audited so the auditor never re-examines it.

        Args:
            feature_id: The feature to mark.
            result: 'pass', 'fail_fix_queued', or 'fail_no_fix'.
            notes: Brief summary of audit findings.
        Returns True if the feature was found and updated.
        """
        valid_results = ("pass", "fail_fix_queued", "fail_no_fix")
        if result not in valid_results:
            result = "pass"
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                f["audited_at"] = datetime.now().isoformat()
                f["audit_result"] = result
                f["audit_notes"] = notes
                f["updated_at"] = datetime.now().isoformat()
                self._save(features)
                return True
        return False

    def is_audited(self, feature_id: str) -> bool:
        """Return True if the feature has already been audited."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                return bool(f.get("audited_at"))
        return False
    
    def _update_status(self, feature_id: str, status: str, log_message: str = "") -> bool:
        """Update feature status and optionally add log entry."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                old_status = f.get("status")
                f["status"] = status
                f["updated_at"] = datetime.now().isoformat()
                
                if status == STATUS_IN_PROGRESS and old_status != STATUS_IN_PROGRESS:
                    f["started_at"] = datetime.now().isoformat()
                
                if status in [STATUS_IMPLEMENTED, STATUS_COMPLETED, STATUS_REJECTED, STATUS_FAILED, STATUS_DEFERRED]:
                    f["completed_at"] = datetime.now().isoformat()
                
                if log_message:
                    if "implementation_log" not in f:
                        f["implementation_log"] = []
                    f["implementation_log"].append({
                        "timestamp": datetime.now().isoformat(),
                        "message": log_message,
                    })
                
                self._save(features)
                return True
        return False

    def mark_failed(self, feature_id: str, error: str = "") -> bool:
        """Mark a feature as failed (will be retried later)."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                f["status"] = STATUS_FAILED
                f["updated_at"] = datetime.now().isoformat()
                f["last_error"] = error
                # After 3 failures, mark as deferred
                if f.get("implementation_attempts", 0) >= 3:
                    f["status"] = STATUS_DEFERRED
                    f["defer_reason"] = f"Failed {f['implementation_attempts']} times"
                if "implementation_log" not in f:
                    f["implementation_log"] = []
                f["implementation_log"].append({
                    "timestamp": datetime.now().isoformat(),
                    "message": f"Failed: {error}",
                })
                self._save(features)
                return True
        return False

    def mark_review_rejected(self, feature_id: str, reason: str = "",
                             max_retries: int = 5,
                             reviewer_feedback: str = "",
                             evolution_id: str = "",
                             branch_name: str = "",
                             pr_id: str = "") -> tuple[bool, str]:
        """Handle PR reviewer rejection by re-queuing with branch context preserved.

        GitHub-style: the branch and evolution stay alive so the next attempt
        can do targeted fixes instead of rebuilding from scratch.

        Behavior:
        - If implementation_attempts < max_retries: set back to pending, preserve
          branch/PR/evolution context for fix-and-resubmit.
        - Otherwise: set deferred, clear context fields.
        - Accumulates ALL reviewer feedback in pr_rejections[].

        Returns:
            (ok, status) where status is "pending" or "deferred".
        """
        features = self._load()
        now = datetime.now().isoformat()
        for f in features:
            if f["id"] != feature_id:
                continue

            attempts = int(f.get("implementation_attempts", 0))
            if attempts >= max_retries:
                f["status"] = STATUS_DEFERRED
                f["defer_reason"] = (
                    f"PR reviewer rejected after {attempts} attempts"
                )
                f.pop("current_branch", None)
                f.pop("current_pr_id", None)
                f.pop("current_evolution_id", None)
                f.pop("review_round", None)
                final_status = STATUS_DEFERRED
            else:
                f["status"] = STATUS_REVIEW_REJECTED
                f["retry_after"] = (
                    datetime.now() + timedelta(minutes=15)
                ).isoformat()
                if evolution_id:
                    f["current_evolution_id"] = evolution_id
                if branch_name:
                    f["current_branch"] = branch_name
                if pr_id:
                    f["current_pr_id"] = pr_id
                f["review_round"] = f.get("review_round", 0) + 1
                final_status = STATUS_REVIEW_REJECTED

            f["updated_at"] = now
            f["last_error"] = reason

            if "pr_rejections" not in f:
                f["pr_rejections"] = []
            f["pr_rejections"].append({
                "attempt": attempts,
                "timestamp": now,
                "feedback": (reviewer_feedback or reason)[:2000],
            })

            if "implementation_log" not in f:
                f["implementation_log"] = []
            f["implementation_log"].append({
                "timestamp": now,
                "message": (
                    f"PR reviewer rejected (attempt {attempts}). "
                    f"{'Deferred after max retries' if final_status == STATUS_DEFERRED else 'Re-queued for fix-and-resubmit (branch preserved)'}."
                ),
            })
            self._save(features)
            return True, final_status

        return False, ""

    def defer(self, feature_id: str, reason: str = "") -> bool:
        """Defer a feature to be reconsidered later."""
        features = self._load()
        for f in features:
            if f["id"] == feature_id:
                f["status"] = STATUS_DEFERRED
                f["updated_at"] = datetime.now().isoformat()
                f["defer_reason"] = reason
                self._save(features)
                return True
        return False

    def delete(self, feature_id: str) -> bool:
        """Permanently delete a feature."""
        features = self._load()
        features = [f for f in features if f.get("id") != feature_id]
        self._save(features)
        return True

    def count_by_status(self) -> Dict[str, int]:
        """Count features by status."""
        features = self._load()
        counts = {
            STATUS_PENDING: 0,
            STATUS_APPROVAL_REQUIRED: 0,
            STATUS_IN_PROGRESS: 0,
            STATUS_IMPLEMENTED: 0,
            STATUS_FAILED: 0,
            STATUS_REJECTED: 0,
            STATUS_REVIEW_REJECTED: 0,
            STATUS_DEFERRED: 0,
            "total": len(features),
        }
        for f in features:
            status = f.get("status", "unknown")
            if status in counts:
                counts[status] += 1
        return counts

    def get_stats(self) -> Dict:
        """Get statistics about the feature backlog."""
        features = self._load()
        counts = self.count_by_status()
        stats = {
            "total": counts["total"],
            "pending": counts[STATUS_PENDING],
            "approval_required": counts[STATUS_APPROVAL_REQUIRED],
            "in_progress": counts[STATUS_IN_PROGRESS],
            "implemented": counts[STATUS_IMPLEMENTED],
            "failed": counts[STATUS_FAILED],
            "rejected": counts[STATUS_REJECTED],
            "review_rejected": counts[STATUS_REVIEW_REJECTED],
            "deferred": counts[STATUS_DEFERRED],
            "by_priority": {
                "P0": len([f for f in features if f.get("priority") == "P0" and f.get("status") in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_REVIEW_REJECTED]]),
                "P1": len([f for f in features if f.get("priority") == "P1" and f.get("status") in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_REVIEW_REJECTED]]),
                "P2": len([f for f in features if f.get("priority") == "P2" and f.get("status") in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_REVIEW_REJECTED]]),
                "P3": len([f for f in features if f.get("priority") == "P3" and f.get("status") in [STATUS_PENDING, STATUS_APPROVAL_REQUIRED, STATUS_IN_PROGRESS, STATUS_REVIEW_REJECTED]]),
            }
        }
        return stats


class FeatureChangelog:
    """Tracks completed features for changelog generation."""

    def __init__(self):
        GHOST_HOME.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if FEATURE_CHANGELOG_FILE.exists():
            try:
                return json.loads(FEATURE_CHANGELOG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, entries: List[Dict]):
        entries = entries[:500]  # Keep last 500
        FEATURE_CHANGELOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def add(self, feature: Dict, implementation_summary: str = ""):
        """Add a completed feature to the changelog."""
        entries = self._load()
        entry = {
            "id": feature.get("id"),
            "title": feature.get("title"),
            "description": feature.get("description"),
            "priority": feature.get("priority"),
            "source": feature.get("source"),
            "tags": feature.get("tags", []),
            "completed_at": datetime.now().isoformat(),
            "implementation_summary": implementation_summary,
        }
        entries.insert(0, entry)
        self._save(entries)

    def get_recent(self, limit: int = 50) -> List[Dict]:
        return self._load()[:limit]

    def generate_markdown(self, since_days: int = 7) -> str:
        """Generate a markdown changelog for recent features."""
        from datetime import timedelta
        entries = self._load()
        cutoff = datetime.now() - timedelta(days=since_days)
        
        recent = [
            e for e in entries 
            if datetime.fromisoformat(e.get("completed_at", "2000-01-01")) > cutoff
        ]
        
        if not recent:
            return f"## Recent Changes (last {since_days} days)\n\nNo new features implemented."
        
        lines = [f"## Recent Changes (last {since_days} days)\n"]
        
        by_priority = {"P0": [], "P1": [], "P2": [], "P3": []}
        for e in recent:
            p = e.get("priority", "P2")
            if p in by_priority:
                by_priority[p].append(e)
        
        for priority in ["P0", "P1", "P2", "P3"]:
            items = by_priority[priority]
            if items:
                lines.append(f"\n### {priority} Priority\n")
                for item in items:
                    lines.append(f"- **{item['title']}** — {item.get('description', '')[:100]}")
                    if item.get("implementation_summary"):
                        lines.append(f"  *{item['implementation_summary'][:150]}*")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
#  LLM-CALLABLE TOOLS
# ═══════════════════════════════════════════════════════════════

def build_future_features_tools(cfg, on_queue_change=None):
    """Build LLM-callable tools for the future features system.

    Args:
        cfg: Ghost configuration dict.
        on_queue_change: Optional callback fired when the queue state changes
                         (feature added, approved, completed, or failed).
                         The callback is responsible for guarding against parallel
                         implementations — it should check is_queue_ready() before
                         firing the implementer.
    """
    store = FutureFeaturesStore()
    changelog = FeatureChangelog()

    # On startup, reset ALL features stuck in_progress from a previous run.
    # max_age_seconds=0 ensures every in_progress feature is caught because
    # a fresh process means no Feature Implementer thread is running — any
    # in_progress feature is orphaned regardless of how recently it started.
    stale_ids = store.reset_stale_in_progress(max_age_seconds=0)
    if stale_ids:
        print(f"  [FUTURE_FEATURES] Reset {len(stale_ids)} in_progress features on startup: {stale_ids}")

    def _notify_queue():
        """Safely invoke on_queue_change callback."""
        if on_queue_change:
            try:
                on_queue_change()
            except Exception:
                pass

    # On startup, if cooled-down features are ready, fire the implementer.
    # Delay slightly so the daemon is fully initialized before cron fires.
    if store.get_next_implementable() and on_queue_change:
        import threading as _th
        _startup_timer = _th.Timer(10.0, _notify_queue)
        _startup_timer.daemon = True
        _startup_timer.start()

    def _add_future_feature(title: str, description: str, priority: str = "P2",
                           source: str = SOURCE_MANUAL, dependencies: str = "",
                           estimated_effort: str = "medium", auto_implement: bool = True,
                           source_detail: str = "", tags: str = "",
                           category: str = CATEGORY_FEATURE,
                           affected_files: str = "",
                           proposed_approach: str = "",
                           confirmed_not_duplicate: bool = False,
                           **kwargs):
        deps = [d.strip() for d in dependencies.split(",") if d.strip()]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        feature = store.add(title, description, priority, source, deps, 
                           estimated_effort, auto_implement, source_detail, tag_list,
                           category=category,
                           affected_files=affected_files,
                           proposed_approach=proposed_approach)
        if feature.get("_warning"):
            return f"Feature already exists: [{feature['id']}] {feature['title']}"

        # Notify the queue processor whenever an implementable feature is added.
        # P0 needs approval first — the callback will see nothing actionable and skip.
        # P1/P2 with auto_implement go straight to pending — the callback checks the guard.
        if feature.get("status") == STATUS_PENDING and feature.get("auto_implement", True):
            _notify_queue()

        status_note = "(requires approval)" if feature["status"] == STATUS_APPROVAL_REQUIRED else ""
        return f"Feature added: [{feature['id']}] {feature['title']} [{feature['priority']}] {status_note}"

    def _list_future_features(status: str = "", limit: int = 50):
        """List features in the backlog.
        
        Args:
            status: Filter by status (pending/approval_required/in_progress/implemented/failed/rejected/deferred)
            limit: Max features to return
        """
        items = store.get_all(status if status else None, limit)
        if not items:
            return "No features found."
        # Sort by priority (P0 first) then by creation date (oldest first)
        items.sort(key=lambda f: (-f.get("priority_score", 0), f.get("created_at", "")))
        lines = [f"Future Features ({len(items)} shown, highest priority first):"]
        for f in items:
            status_emoji = {
                STATUS_PENDING: "⏳",
                STATUS_APPROVAL_REQUIRED: "🛑",
                STATUS_IN_PROGRESS: "🔄",
                STATUS_IMPLEMENTED: "✅",
                STATUS_COMPLETED: "✅",
                STATUS_REJECTED: "❌",
                STATUS_REVIEW_REJECTED: "🔁",
                STATUS_FAILED: "⚠️",
                STATUS_DEFERRED: "📋",
            }.get(f.get("status"), "❓")
            deps = f.get("dependencies", [])
            dep_str = f" [deps: {','.join(deps)}]" if deps else ""
            cat = f.get("category", "")
            cat_str = f" ({cat})" if cat else ""
            impl_type = f.get("implementation_type", "core")
            impl_str = f" [{impl_type}]"
            audited_str = " [AUDITED]" if f.get("audited_at") else ""
            cooldown_str = ""
            if f.get("retry_after"):
                try:
                    if datetime.fromisoformat(f["retry_after"]) > datetime.now():
                        cooldown_str = " ⏳cooldown"
                except (ValueError, TypeError):
                    pass
            lines.append(f"  {status_emoji} [{f['id']}] {f['title']} [{f.get('priority', '?')}]{cat_str}{impl_str}{dep_str}{audited_str}{cooldown_str}")
        return "\n".join(lines)

    def _get_future_feature(feature_id: str):
        """Get detailed info about a specific feature."""
        f = store.get_by_id(feature_id)
        if not f:
            return f"Feature not found: {feature_id}"
        impl_type = f.get("implementation_type", "core")
        lines = [
            f"Feature: {f['title']}",
            f"ID: {f['id']}",
            f"Priority: {f.get('priority', 'unknown')}",
            f"Category: {f.get('category', 'feature')}",
            f"Implementation Type: {impl_type}",
            f"Status: {f.get('status', 'unknown')}",
            f"Source: {f.get('source', 'unknown')}",
            f"Effort: {f.get('estimated_effort', 'unknown')}",
            f"Attempts: {f.get('implementation_attempts', 0)}",
            f"Created: {f.get('created_at', 'unknown')}",
        ]
        if f.get("retry_after"):
            lines.append(f"Retry After: {f['retry_after']}")
        if f.get("last_error"):
            lines.append(f"Last Error: {f['last_error']}")
        if f.get("description"):
            lines.append(f"\nDescription:\n{f['description']}")
        if f.get("affected_files"):
            lines.append(f"\nAffected Files: {f['affected_files']}")
        if f.get("proposed_approach"):
            lines.append(f"\nProposed Approach:\n{f['proposed_approach']}")
        if f.get("source_detail"):
            lines.append(f"\nSource Detail: {f['source_detail']}")
        if f.get("started_at"):
            lines.append(f"\nStarted: {f['started_at']}")
        if f.get("completed_at"):
            lines.append(f"Completed: {f['completed_at']}")
        if f.get("audited_at"):
            lines.append(f"\nAudited: {f['audited_at']} (result={f.get('audit_result', '?')})")
            if f.get("audit_notes"):
                lines.append(f"Audit Notes: {f['audit_notes']}")
        if f.get("current_branch"):
            lines.append(f"\n🔴🔴🔴 RESUME CONTEXT (fix-and-resubmit) — YOU MUST USE evolve_resume 🔴🔴🔴")
            lines.append(f"  Branch: {f.get('current_branch')}")
            lines.append(f"  Evolution ID: {f.get('current_evolution_id', 'unknown')}")
            lines.append(f"  PR ID: {f.get('current_pr_id', 'unknown')}")
            lines.append(f"  Review Round: {f.get('review_round', 0)}")
            lines.append(f"  ACTION: Call start_future_feature THEN evolve_resume(evolution_id='{f.get('current_evolution_id')}')")
            lines.append(f"  DO NOT call evolve_plan. DO NOT start fresh. Resume the existing branch.")
        if f.get("pr_rejections"):
            lines.append(f"\n⚠️  PAST PR REJECTIONS ({len(f['pr_rejections'])} total) — YOU MUST address ALL of these:")
            for i, rej in enumerate(f["pr_rejections"], 1):
                lines.append(f"\n--- Rejection #{i} (attempt {rej.get('attempt', '?')}) ---")
                lines.append(rej.get("feedback", "(no feedback)"))
        if f.get("implementation_log"):
            lines.append(f"\nImplementation Log:")
            for entry in f["implementation_log"][-5:]:
                lines.append(f"  - {entry['timestamp']}: {entry['message']}")
        return "\n".join(lines)

    def _approve_future_feature(feature_id: str):
        """Approve a P0 or manually-held feature for implementation."""
        ok = store.approve(feature_id)
        if ok:
            _notify_queue()
            return f"Feature approved for implementation: {feature_id}"
        return f"Could not approve feature (may not exist or not require approval): {feature_id}"

    def _start_future_feature(feature_id: str):
        """Mark a feature as in_progress. Auto-resumes if branch exists."""
        if not cfg.get("enable_future_features", True):
            return "BLOCKED — Future Features is disabled in config. Do NOT attempt to implement any feature. Call task_complete now."
        item = store.get_by_id(feature_id)
        resume_evo = None
        resume_branch = None
        if item:
            resume_evo = item.get("current_evolution_id")
            resume_branch = item.get("current_branch")
        ok, error = store.mark_in_progress(feature_id)
        if not ok:
            return f"Cannot start feature: {error}"

        try:
            from ghost_loop import EvolveContextLogger
            EvolveContextLogger.get().set_feature(
                feature_id=feature_id,
                feature_title=(item.get("title", "") if item else ""),
            )
        except Exception:
            pass
        if resume_evo and resume_branch:
            try:
                from ghost_evolve import get_engine
                evo_engine = get_engine()
                rok, result = evo_engine.resume_evolution(resume_evo)
                if rok:
                    ctx = result
                    lines = [
                        f"Feature started: {feature_id}",
                        f"\n🔀 AUTO-RESUMED evolution {ctx['evolution_id']} on branch {ctx['branch']}.",
                        f"Review round: {ctx['review_round']}",
                        f"Previous files: {', '.join(ctx['files_changed'])}",
                        f"PR ID: {ctx['pr_id']}",
                    ]
                    if ctx.get("last_reviewer_feedback"):
                        feedback = ctx["last_reviewer_feedback"][:3000]
                        lines.append(f"\nLAST REVIEWER FEEDBACK:\n{feedback}")
                    lines.append(
                        "\nYou are NOW on the feature branch. The code from the previous "
                        "attempt is already here. Do NOT call evolve_plan. Do NOT start fresh.\n"
                        "Apply TARGETED fixes via evolve_apply patches, then evolve_test, "
                        "then evolve_submit_pr."
                    )
                    return "\n".join(lines)
                else:
                    return (
                        f"Feature started: {feature_id}\n"
                        f"Resume failed ({result}). Proceed with a fresh implementation."
                    )
            except Exception as exc:
                return (
                    f"Feature started: {feature_id}\n"
                    f"Resume error ({exc}). Proceed with a fresh implementation."
                )
        return f"Feature started: {feature_id}"

    def _complete_future_feature(feature_id: str, implementation_summary: str = ""):
        """Mark a feature as completed. Requires an approved+merged PR."""
        item = store.get_by_id(feature_id)
        if not item:
            return f"Feature not found: {feature_id}"
        pr_id = item.get("current_pr_id", "")
        if pr_id:
            try:
                from ghost_pr import get_pr_store
                pr = get_pr_store().get_pr(pr_id)
                if pr and pr.get("verdict") != "approved" and pr.get("status") != "merged":
                    return (
                        f"BLOCKED: Cannot complete feature {feature_id} — "
                        f"PR {pr_id} verdict is '{pr.get('verdict', 'none')}', not 'approved'. "
                        f"Call task_complete instead. The feature will be retried."
                    )
            except Exception:
                pass
        store.mark_implemented(feature_id, implementation_summary)
        changelog.add(item, implementation_summary)
        _notify_queue()
        try:
            from ghost_autonomy import GrowthLog
            GrowthLog().add(
                routine="feature_implementer",
                summary=f"Completed: {item['title']}",
                details=implementation_summary or "No details",
                category=item.get("category", "feature"),
            )
        except Exception:
            pass
        try:
            from ghost_loop import EvolveContextLogger
            EvolveContextLogger.get().clear()
        except Exception:
            pass
        return f"Feature completed: [{feature_id}] {item['title']}"

    def _fail_future_feature(feature_id: str, error: str = ""):
        """Mark a feature as failed."""
        ok = store.mark_failed(feature_id, error)
        if ok:
            _notify_queue()
            try:
                from ghost_loop import EvolveContextLogger
                EvolveContextLogger.get().clear()
            except Exception:
                pass
            return f"Feature marked as failed: {feature_id}"
        return f"Feature not found: {feature_id}"

    def _reject_future_feature(feature_id: str, reason: str = "", **kwargs):
        """Permanently reject a feature (e.g. already implemented, not applicable)."""
        ok = store.reject(feature_id, reason)
        if ok:
            _notify_queue()
            return f"Feature rejected: {feature_id} — {reason}"
        return f"Feature not found: {feature_id}"

    def _mark_feature_audited(feature_id: str, result: str = "pass", notes: str = ""):
        """Stamp a feature as audited so the auditor never re-examines it."""
        if store.is_audited(feature_id):
            return f"Feature {feature_id} was already audited — skipping."
        ok = store.mark_audited(feature_id, result, notes)
        if ok:
            return f"Feature {feature_id} marked as audited (result={result})."
        return f"Feature not found: {feature_id}"

    def _get_feature_stats():
        """Get statistics about the feature backlog."""
        stats = store.get_stats()
        return (
            f"Feature Backlog Stats:\n"
            f"  Total: {stats['total']}\n"
            f"  Pending: {stats['pending']}\n"
            f"  Approval Required: {stats['approval_required']}\n"
            f"  In Progress: {stats['in_progress']}\n"
            f"  Implemented: {stats['implemented']}\n"
            f"  Failed: {stats['failed']}\n"
            f"  Rejected: {stats['rejected']}\n"
            f"  Review Rejected (awaiting retry): {stats['review_rejected']}\n"
            f"  Deferred: {stats['deferred']}\n"
            f"\nBy Priority (active):\n"
            f"  P0 (Critical): {stats['by_priority']['P0']}\n"
            f"  P1 (High): {stats['by_priority']['P1']}\n"
            f"  P2 (Medium): {stats['by_priority']['P2']}\n"
            f"  P3 (Low): {stats['by_priority']['P3']}"
        )

    return [
        {
            "name": "add_future_feature",
            "description": (
                "Queue a change for the serial Evolution Runner. "
                "Do NOT use this for user-requested projects like 'build me a website' — "
                "do those directly with file_write/shell_exec.\n"
                "List the actual files that need to be created or patched in affected_files. "
                "Be specific about root causes and line numbers for bug fixes.\n"
                "P0/P1 items trigger the Evolution Runner immediately. "
                "Write an implementation-ready brief — the Evolution Runner will "
                "act on your description, affected_files, and proposed_approach WITHOUT "
                "re-doing your investigation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title (e.g. 'Bug fix: crash in chat handler', 'Feature: dark mode toggle')"},
                    "description": {"type": "string", "description": "What and why: describe the problem/opportunity. For bugs: include the error message, traceback snippet, and root cause. For features: what it does and why it matters."},
                    "affected_files": {"type": "string", "description": "Comma-separated file paths to create or patch (e.g. 'ghost_tools.py, ghost_dashboard/routes/chat.py'). The Evolution Runner uses this for evolve_plan."},
                    "proposed_approach": {"type": "string", "description": "Step-by-step implementation plan. The exact fix — which function, what to change, what to add."},
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"], "default": "P2", "description": "P0=user-requested(needs approval), P1=urgent(auto), P2=normal(auto), P3=low(manual)"},
                    "source": {"type": "string", "enum": FEATURE_SOURCES, "default": SOURCE_MANUAL, "description": "Where this request came from"},
                    "category": {"type": "string", "enum": FEATURE_CATEGORIES, "default": CATEGORY_FEATURE, "description": "Type: feature/bugfix/security/refactor/improvement/soul_update"},
                    "dependencies": {"type": "string", "default": "", "description": "Comma-separated feature IDs this depends on"},
                    "estimated_effort": {"type": "string", "enum": ["small", "medium", "large"], "default": "medium", "description": "Implementation effort"},
                    "auto_implement": {"type": "boolean", "default": True, "description": "Auto-implement (false = requires approval)"},
                    "source_detail": {"type": "string", "default": "", "description": "Additional source context (URL, issue link)"},
                    "tags": {"type": "string", "default": "", "description": "Comma-separated tags"},
                },
                "required": ["title", "description"],
            },
            "execute": _add_future_feature,
        },
        {
            "name": "list_future_features",
            "description": "List features in the backlog",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["", "pending", "approval_required", "in_progress", "implemented", "failed", "rejected", "review_rejected", "deferred"], "default": "", "description": "Filter by status"},
                    "limit": {"type": "integer", "default": 50, "description": "Max features to return"},
                },
            },
            "execute": _list_future_features,
        },
        {
            "name": "get_future_feature",
            "description": "Get detailed info about a specific feature",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID"},
                },
                "required": ["feature_id"],
            },
            "execute": _get_future_feature,
        },
        {
            "name": "approve_future_feature",
            "description": "Approve a P0 or manually-held feature for implementation",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID"},
                },
                "required": ["feature_id"],
            },
            "execute": _approve_future_feature,
        },
        {
            "name": "start_future_feature",
            "description": "Mark a feature as in_progress (used by feature_implementer routine)",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID"},
                },
                "required": ["feature_id"],
            },
            "execute": _start_future_feature,
        },
        {
            "name": "complete_future_feature",
            "description": "Mark a feature as completed and add to changelog (used by feature_implementer)",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID"},
                    "implementation_summary": {"type": "string", "default": "", "description": "Summary of what was implemented"},
                },
                "required": ["feature_id"],
            },
            "execute": _complete_future_feature,
        },
        {
            "name": "fail_future_feature",
            "description": "Mark a feature as failed",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID"},
                    "error": {"type": "string", "default": "", "description": "Error message"},
                },
                "required": ["feature_id"],
            },
            "execute": _fail_future_feature,
        },
        {
            "name": "reject_future_feature",
            "description": (
                "Permanently reject a feature that should NOT be implemented. "
                "Use this when a feature is already implemented in the codebase, "
                "duplicates existing functionality, or is no longer applicable. "
                "Unlike fail_future_feature, rejected features are never retried."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID to reject"},
                    "reason": {"type": "string", "default": "", "description": "Why (e.g. 'Already implemented in ghost_voice.py — moonshine_onnx is imported and used')"},
                },
                "required": ["feature_id", "reason"],
            },
            "execute": _reject_future_feature,
        },
        {
            "name": "mark_feature_audited",
            "description": (
                "Stamp a feature as audited so it is never re-examined. "
                "Call this AFTER you finish auditing a feature, whether it passed or you queued a fix. "
                "result must be 'pass', 'fail_fix_queued', or 'fail_no_fix'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_id": {"type": "string", "description": "Feature ID to mark as audited"},
                    "result": {"type": "string", "enum": ["pass", "fail_fix_queued", "fail_no_fix"], "default": "pass", "description": "Audit result"},
                    "notes": {"type": "string", "default": "", "description": "Brief audit findings summary"},
                },
                "required": ["feature_id", "result"],
            },
            "execute": _mark_feature_audited,
        },
        {
            "name": "get_feature_stats",
            "description": "Get statistics about the feature backlog",
            "parameters": {"type": "object", "properties": {}},
            "execute": _get_feature_stats,
        },
    ]


# ═══════════════════════════════════════════════════════════════
#  FEATURE IMPLEMENTER ROUTINE PROMPT
# ═══════════════════════════════════════════════════════════════

