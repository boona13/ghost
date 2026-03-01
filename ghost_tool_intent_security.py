"""Tool intent envelope security: signing + verification + anti-replay."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import OrderedDict
from typing import Any


class ToolIntentSecurity:
    """Creates and verifies signed tool intent envelopes with anti-replay."""

    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enable_tool_intent_security", True))
        self.ttl_seconds = int(cfg.get("intent_ttl_seconds", 120))
        self.max_skew_seconds = int(cfg.get("intent_max_skew_seconds", 30))
        self._secret = self._load_secret(cfg)
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._seen_limit = int(cfg.get("intent_nonce_cache_size", 5000))

    @staticmethod
    def _load_secret(cfg: dict) -> bytes:
        env_secret = os.getenv("GHOST_TOOL_INTENT_SECRET", "").strip()
        cfg_secret = str(cfg.get("tool_intent_secret", "")).strip()
        raw = env_secret or cfg_secret
        if not raw:
            raw = "ghost-default-local-secret"
        return raw.encode("utf-8")

    @staticmethod
    def _canonical_args(args: dict[str, Any]) -> str:
        return json.dumps(args or {}, sort_keys=True, separators=(",", ":"), default=str)

    def args_digest(self, args: dict[str, Any]) -> str:
        return hashlib.sha256(self._canonical_args(args).encode("utf-8")).hexdigest()

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hmac.new(self._secret, raw, hashlib.sha256).hexdigest()

    def create_envelope(self, tool_name: str, args: dict[str, Any], session_id: str, policy_level: str = "standard") -> dict[str, Any]:
        now = int(time.time())
        payload = {
            "tool_name": str(tool_name or ""),
            "args_digest": self.args_digest(args or {}),
            "issued_at": now,
            "nonce": secrets.token_urlsafe(16),
            "policy_level": str(policy_level or "standard"),
            "session_id": str(session_id or ""),
        }
        payload["signature"] = self._sign_payload(payload)
        return payload

    def _consume_nonce(self, nonce: str, now: int) -> tuple[bool, str]:
        cutoff = now - self.ttl_seconds
        for k, ts in list(self._seen.items()):
            if ts < cutoff:
                self._seen.pop(k, None)
            else:
                break

        if nonce in self._seen:
            return False, "replay_detected"

        self._seen[nonce] = now
        self._seen.move_to_end(nonce)
        if len(self._seen) > self._seen_limit:
            self._seen.popitem(last=False)
        return True, "ok"

    def verify_envelope(self, envelope: dict[str, Any], tool_name: str, args: dict[str, Any], session_id: str) -> tuple[bool, str]:
        if not self.enabled:
            return True, "disabled"

        required = {"tool_name", "args_digest", "issued_at", "nonce", "policy_level", "session_id", "signature"}
        if not isinstance(envelope, dict) or not required.issubset(set(envelope.keys())):
            return False, "invalid_envelope"

        now = int(time.time())
        issued_at = int(envelope.get("issued_at", 0))
        if abs(now - issued_at) > (self.ttl_seconds + self.max_skew_seconds):
            return False, "stale_or_skewed"

        if envelope.get("tool_name") != str(tool_name or ""):
            return False, "tool_mismatch"

        if envelope.get("session_id") != str(session_id or ""):
            return False, "session_mismatch"

        expected_digest = self.args_digest(args or {})
        if envelope.get("args_digest") != expected_digest:
            return False, "args_tampered"

        signed = dict(envelope)
        sent_sig = str(signed.pop("signature", ""))
        expected_sig = self._sign_payload(signed)
        if not hmac.compare_digest(sent_sig, expected_sig):
            return False, "signature_mismatch"

        ok, reason = self._consume_nonce(str(envelope.get("nonce", "")), now)
        if not ok:
            return False, reason

        return True, "ok"
