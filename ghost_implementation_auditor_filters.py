"""Helpers for implementation-auditor candidate selection and dedupe.

This module is intentionally narrow: it computes which recently implemented
features should be audited now, skipping ones that already have active
wiring-fix backlog entries.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set, Any


def _parse_iso(ts: str) -> datetime | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        # Accept trailing Z for UTC.
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def select_recent_implemented_features(
    implemented_features: List[Dict[str, Any]],
    now: datetime | None = None,
    hours: int = 24,
) -> List[Dict[str, Any]]:
    """Return implemented features whose implemented_at is within `hours`.

    Invalid/missing timestamps are excluded (fail closed for recency filter).
    """
    ref = now or datetime.now()
    cutoff = ref - timedelta(hours=max(1, int(hours)))
    out: List[Dict[str, Any]] = []
    for feat in implemented_features or []:
        implemented_at = _parse_iso(str(feat.get("implemented_at", "")))
        if not implemented_at:
            continue
        # If timezone-aware values exist, normalize by dropping tz safely.
        try:
            cmp_value = implemented_at.replace(tzinfo=None)
        except Exception:
            cmp_value = implemented_at
        if cmp_value >= cutoff:
            out.append(feat)
    return out


def build_active_wiring_fix_index(
    active_features: List[Dict[str, Any]],
) -> Tuple[Set[str], Set[str]]:
    """Build dedupe indexes from active implementation-auditor wiring fixes.

    Returns:
      - feature_ids referenced in description/proposed approach/dependencies
      - affected file paths referenced by queued fixes
    """
    target_feature_ids: Set[str] = set()
    affected_files: Set[str] = set()

    for fix in active_features or []:
        source = str(fix.get("source", "")).strip()
        title = str(fix.get("title", "")).strip()
        if source != "implementation_auditor":
            continue
        if not title.startswith("Wiring fix:"):
            continue

        # Try explicit dependencies first if present.
        deps = str(fix.get("dependencies", ""))
        for dep in [x.strip() for x in deps.split(",") if x.strip()]:
            target_feature_ids.add(dep)

        blob = " ".join(
            [
                str(fix.get("description", "")),
                str(fix.get("proposed_approach", "")),
            ]
        )
        # Heuristic: feature IDs are 10-char hex in this system.
        tokens = [tok.strip("[](){}<>,.:;\"'\n\t ") for tok in blob.split()]
        for tok in tokens:
            if len(tok) == 10 and all(c in "0123456789abcdef" for c in tok.lower()):
                target_feature_ids.add(tok.lower())

        af = str(fix.get("affected_files", ""))
        for path in [x.strip() for x in af.split(",") if x.strip()]:
            affected_files.add(path)

    return target_feature_ids, affected_files


def should_skip_feature_for_active_fix(
    feature: Dict[str, Any],
    target_feature_ids: Set[str],
    active_affected_files: Set[str],
) -> bool:
    """True when feature already has an active fix queued.

    Dedupes by:
      1) direct feature ID match
      2) any overlap between feature affected_files and active fix affected_files
    """
    fid = str(feature.get("id", "")).strip().lower()
    if fid and fid in target_feature_ids:
        return True

    this_files_raw = str(feature.get("affected_files", ""))
    this_files = {x.strip() for x in this_files_raw.split(",") if x.strip()}
    if this_files and (this_files & active_affected_files):
        return True

    return False


def is_already_audited(feature: Dict[str, Any]) -> bool:
    """True if the feature has been stamped as audited."""
    return bool(feature.get("audited_at"))


def is_auditor_own_output(feature: Dict[str, Any]) -> bool:
    """True if the feature was created by the auditor itself (wiring fixes)."""
    title = str(feature.get("title", ""))
    source = str(feature.get("source", ""))
    return title.startswith("Wiring fix:") or source == "implementation_auditor"


def build_implementation_auditor_candidate_report(
    implemented_features: List[Dict[str, Any]],
    active_fix_features: List[Dict[str, Any]],
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Compute audited/skipped candidates for implementation auditor."""
    recent = select_recent_implemented_features(implemented_features, now=now, hours=24)
    target_ids, active_files = build_active_wiring_fix_index(active_fix_features)

    candidates: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    skipped_audited: int = 0
    skipped_own: int = 0
    for feat in recent:
        if is_already_audited(feat):
            skipped.append(feat)
            skipped_audited += 1
        elif is_auditor_own_output(feat):
            skipped.append(feat)
            skipped_own += 1
        elif should_skip_feature_for_active_fix(feat, target_ids, active_files):
            skipped.append(feat)
        else:
            candidates.append(feat)

    return {
        "recent_count": len(recent),
        "candidate_count": len(candidates),
        "skipped_count": len(skipped),
        "skipped_already_audited": skipped_audited,
        "skipped_own_output": skipped_own,
        "candidates": candidates,
        "skipped": skipped,
        "active_fix_target_ids": sorted(target_ids),
        "active_fix_file_count": len(active_files),
    }


def build_implementation_auditor_filter_tools():
    """Diagnostics tool to preview implementation-auditor candidate filtering."""

    def _preview(
        implemented_features: list,
        active_fix_features: list,
    ):
        if not isinstance(implemented_features, list):
            return "implemented_features must be a list"
        if not isinstance(active_fix_features, list):
            return "active_fix_features must be a list"
        report = build_implementation_auditor_candidate_report(
            implemented_features=implemented_features,
            active_fix_features=active_fix_features,
        )
        return (
            f"Implementation auditor filter preview:\n"
            f"- recent_24h: {report['recent_count']}\n"
            f"- candidates: {report['candidate_count']}\n"
            f"- skipped_due_to_active_fix: {report['skipped_count']}\n"
            f"- skipped_already_audited: {report.get('skipped_already_audited', 0)}\n"
            f"- skipped_own_output: {report.get('skipped_own_output', 0)}\n"
            f"- active_fix_target_ids: {len(report['active_fix_target_ids'])}\n"
            f"- active_fix_affected_files: {report['active_fix_file_count']}"
        )

    return [
        {
            "name": "implementation_auditor_filter_preview",
            "description": "Preview 24h filtering and wiring-fix dedupe for implementation auditor",
            "parameters": {
                "type": "object",
                "properties": {
                    "implemented_features": {"type": "array", "items": {"type": "object"}},
                    "active_fix_features": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["implemented_features", "active_fix_features"],
            },
            "execute": _preview,
        }
    ]
