"""Provider-scoped API key posture analyzer.

Detects key capability drift / bleed-through risk and key hygiene gaps without
exposing secrets. Output is designed for security audit + dashboard UX.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


@dataclass
class PostureFinding:
    check_id: str
    severity: str
    title: str
    remediation: str
    confidence: str = "medium"
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "title": self.title,
            "remediation": self.remediation,
            "confidence": self.confidence,
            "evidence": self.evidence or {},
        }


def _mask_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        return ""
    if len(key) < 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _key_fingerprint(key: str) -> str:
    if not isinstance(key, str) or not key:
        return ""
    return sha256(key.encode("utf-8")).hexdigest()[:16]


def analyze_provider_key_posture(auth_store, cfg: dict | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    profiles = auth_store.profiles if auth_store else {}

    findings: list[PostureFinding] = []
    by_fp: dict[str, list[dict[str, Any]]] = {}

    for profile_id, profile in (profiles or {}).items():
        if not isinstance(profile, dict):
            continue
        if profile.get("type") != "api_key":
            continue
        key = profile.get("key", "")
        fp = _key_fingerprint(key)
        if not fp:
            continue
        provider = profile.get("provider", profile_id.split(":")[0])
        by_fp.setdefault(fp, []).append({
            "provider": provider,
            "profile_id": profile_id,
            "masked": _mask_key(key),
            "scope_intent": profile.get("scope_intent", ""),
            "project_id_hash": profile.get("project_id_hash", ""),
            "rotation_days": profile.get("rotation_days", 0),
            "last_rotated_at": profile.get("last_rotated_at", ""),
        })

    # Detector A: Google key reused across profiles/workflows with Gemini enabled
    gemini_enabled = bool(cfg.get("enable_gemini", True)) and bool(auth_store.get_api_key("gemini"))
    if gemini_enabled:
        for fp, entries in by_fp.items():
            providers = {e["provider"] for e in entries}
            if "gemini" in providers and len(entries) > 1:
                findings.append(PostureFinding(
                    check_id="key_scope_drift_google",
                    severity=SEVERITY_WARNING,
                    title="Potential Gemini key capability drift (shared key fingerprint)",
                    remediation="Use separate Google API keys per capability/project; avoid sharing Gemini key across workflows.",
                    confidence="medium",
                    evidence={
                        "fingerprint": fp,
                        "providers": sorted(providers),
                        "profiles": [e["profile_id"] for e in entries],
                        "masked_examples": sorted({e["masked"] for e in entries if e["masked"]}),
                    },
                ))

    # Detector B: same key reused across multiple providers (high blast radius)
    for fp, entries in by_fp.items():
        providers = sorted({e["provider"] for e in entries})
        if len(providers) >= 2:
            findings.append(PostureFinding(
                check_id="key_reuse_cross_provider",
                severity=SEVERITY_CRITICAL,
                title="API key material appears reused across providers",
                remediation="Rotate keys and issue distinct provider-scoped keys for each integration.",
                confidence="high",
                evidence={"fingerprint": fp, "providers": providers, "profiles": [e["profile_id"] for e in entries]},
            ))

    # Detector C: missing metadata for least-privilege / rotation hygiene
    for fp, entries in by_fp.items():
        for e in entries:
            missing = []
            if not e.get("scope_intent"):
                missing.append("scope_intent")
            if not e.get("project_id_hash"):
                missing.append("project_id_hash")
            if not e.get("rotation_days"):
                missing.append("rotation_days")
            if not e.get("last_rotated_at"):
                missing.append("last_rotated_at")
            if missing:
                findings.append(PostureFinding(
                    check_id="key_metadata_missing",
                    severity=SEVERITY_INFO,
                    title="API key metadata incomplete",
                    remediation="Populate key metadata (scope intent, project hash, and rotation fields) for governance and drift detection.",
                    confidence="high",
                    evidence={
                        "fingerprint": fp,
                        "profile_id": e["profile_id"],
                        "provider": e["provider"],
                        "missing_fields": missing,
                    },
                ))

    severity_rank = {SEVERITY_INFO: 1, SEVERITY_WARNING: 2, SEVERITY_CRITICAL: 3}
    top = max((severity_rank.get(f.severity, 1) for f in findings), default=0)
    posture = "green" if top <= 1 else ("yellow" if top == 2 else "red")

    return {
        "posture": posture,
        "finding_count": len(findings),
        "findings": [f.to_dict() for f in findings],
        "summary": {
            "critical": sum(1 for f in findings if f.severity == SEVERITY_CRITICAL),
            "warning": sum(1 for f in findings if f.severity == SEVERITY_WARNING),
            "info": sum(1 for f in findings if f.severity == SEVERITY_INFO),
        },
    }
