"""
GHOST Device Pairing & Auth — Secure remote device pairing with token-based auth.

Allows remote devices (phones, tablets, other machines) to pair with Ghost
when it runs headless. Flow:
  1. Device requests pairing -> gets a short code
  2. User approves via the dashboard -> device gets an auth token
  3. Device uses Bearer token for all future API requests

Tokens are stored hashed (SHA-256). Pairing codes expire after a configurable TTL.
"""

import hashlib
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("ghost.device_auth")

GHOST_HOME = Path.home() / ".ghost"
DEVICES_DIR = GHOST_HOME / "devices"
PAIRING_FILE = DEVICES_DIR / "pairing.json"
PAIRED_FILE = DEVICES_DIR / "paired.json"

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
DEFAULT_TTL_MINUTES = 10
MAX_PENDING = 10
TOKEN_BYTES = 32

DEFAULT_SCOPES = ["read", "write"]
VALID_SCOPES = {"read", "write", "admin"}

_lock = threading.Lock()


def _ensure_dir():
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_code() -> str:
    """Generate an 8-char pairing code from unambiguous characters (AXBK-7M2P format)."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def _generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json(path: Path, data: dict):
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


class PairingStore:
    """Manages device pairing requests and paired device tokens."""

    def __init__(self, ttl_minutes: int = DEFAULT_TTL_MINUTES,
                 default_scopes: list[str] | None = None):
        self.ttl_minutes = ttl_minutes
        self.default_scopes = default_scopes or list(DEFAULT_SCOPES)
        _ensure_dir()

    def _load_pending(self) -> list[dict]:
        data = _load_json(PAIRING_FILE)
        return data.get("pending", [])

    def _save_pending(self, pending: list[dict]):
        _save_json(PAIRING_FILE, {"pending": pending})

    def _load_paired(self) -> list[dict]:
        data = _load_json(PAIRED_FILE)
        return data.get("devices", [])

    def _save_paired(self, devices: list[dict]):
        _save_json(PAIRED_FILE, {"devices": devices})

    def _prune_expired(self, pending: list[dict]) -> list[dict]:
        cutoff = _now_ts() - (self.ttl_minutes * 60)
        return [p for p in pending if p.get("created_at_ts", 0) > cutoff]

    def request_pairing(self, device_name: str,
                        device_type: str = "unknown") -> dict:
        """Create a new pairing request. Returns {code, request_id, expires_at}."""
        with _lock:
            pending = self._prune_expired(self._load_pending())

            if len(pending) >= MAX_PENDING:
                raise ValueError(
                    f"Too many pending pairing requests ({MAX_PENDING}). "
                    "Reject or wait for existing ones to expire."
                )

            request_id = secrets.token_hex(16)
            code = _generate_code()
            now = _now_ts()
            expires_at = now + (self.ttl_minutes * 60)

            entry = {
                "request_id": request_id,
                "code": code,
                "device_name": device_name,
                "device_type": device_type,
                "created_at": _now_iso(),
                "created_at_ts": now,
                "expires_at_ts": expires_at,
                "status": "pending",
            }
            pending.append(entry)
            self._save_pending(pending)

            log.info("Pairing request created: %s (%s) code=%s",
                     device_name, device_type, code)

            return {
                "request_id": request_id,
                "code": code,
                "expires_at": datetime.fromtimestamp(
                    expires_at, tz=timezone.utc
                ).isoformat(),
                "ttl_seconds": self.ttl_minutes * 60,
            }

    def list_pending(self) -> list[dict]:
        """List active (non-expired) pairing requests."""
        with _lock:
            pending = self._prune_expired(self._load_pending())
            self._save_pending(pending)
            return [
                {
                    "request_id": p["request_id"],
                    "code": p["code"],
                    "device_name": p["device_name"],
                    "device_type": p["device_type"],
                    "created_at": p["created_at"],
                    "expires_in_s": max(0, int(p["expires_at_ts"] - _now_ts())),
                }
                for p in pending if p.get("status") == "pending"
            ]

    def approve(self, request_id: str,
                scopes: list[str] | None = None) -> dict:
        """Approve a pairing request. Returns {token, device_id, device_name, scopes}.

        The raw token is returned ONCE. Only the hash is stored.
        """
        scopes = scopes or list(self.default_scopes)
        for s in scopes:
            if s not in VALID_SCOPES:
                raise ValueError(f"Invalid scope: {s!r}. Valid: {VALID_SCOPES}")

        with _lock:
            pending = self._prune_expired(self._load_pending())
            target = None
            for p in pending:
                if p["request_id"] == request_id and p["status"] == "pending":
                    target = p
                    break

            if not target:
                raise ValueError(f"Pairing request not found or expired: {request_id}")

            raw_token = _generate_token()
            device_id = secrets.token_hex(8)

            device = {
                "device_id": device_id,
                "device_name": target["device_name"],
                "device_type": target["device_type"],
                "token_hash": _hash_token(raw_token),
                "scopes": scopes,
                "paired_at": _now_iso(),
                "last_seen": _now_iso(),
            }

            devices = self._load_paired()
            devices.append(device)
            self._save_paired(devices)

            target["status"] = "approved"
            target["device_id"] = device_id
            self._save_pending(pending)

            log.info("Device paired: %s (%s) id=%s scopes=%s",
                     target["device_name"], target["device_type"],
                     device_id, scopes)

            return {
                "token": raw_token,
                "device_id": device_id,
                "device_name": target["device_name"],
                "scopes": scopes,
            }

    def reject(self, request_id: str) -> dict:
        """Reject a pairing request."""
        with _lock:
            pending = self._load_pending()
            for p in pending:
                if p["request_id"] == request_id and p["status"] == "pending":
                    p["status"] = "rejected"
                    self._save_pending(pending)
                    log.info("Pairing rejected: %s (%s)",
                             p["device_name"], p["device_type"])
                    return {"rejected": True, "device_name": p["device_name"]}
            raise ValueError(f"Pairing request not found: {request_id}")

    def poll(self, request_id: str) -> dict:
        """Poll the status of a pairing request (called by the device)."""
        with _lock:
            pending = self._load_pending()
            for p in pending:
                if p["request_id"] == request_id:
                    if p["status"] == "approved":
                        devices = self._load_paired()
                        for d in devices:
                            if d["device_id"] == p.get("device_id"):
                                return {
                                    "status": "approved",
                                    "device_id": d["device_id"],
                                }
                    return {"status": p["status"]}
            return {"status": "expired"}

    def verify_token(self, token: str) -> dict | None:
        """Verify a Bearer token. Returns device info or None."""
        token_hash = _hash_token(token)
        with _lock:
            devices = self._load_paired()
            for d in devices:
                if d["token_hash"] == token_hash:
                    d["last_seen"] = _now_iso()
                    self._save_paired(devices)
                    return {
                        "device_id": d["device_id"],
                        "device_name": d["device_name"],
                        "device_type": d["device_type"],
                        "scopes": d.get("scopes", []),
                        "paired_at": d["paired_at"],
                    }
        return None

    def list_paired(self) -> list[dict]:
        """List all paired devices (without token hashes)."""
        with _lock:
            devices = self._load_paired()
            return [
                {
                    "device_id": d["device_id"],
                    "device_name": d["device_name"],
                    "device_type": d["device_type"],
                    "scopes": d.get("scopes", []),
                    "paired_at": d["paired_at"],
                    "last_seen": d.get("last_seen", ""),
                }
                for d in devices
            ]

    def revoke(self, device_id: str) -> dict:
        """Revoke a paired device's access."""
        with _lock:
            devices = self._load_paired()
            updated = [d for d in devices if d["device_id"] != device_id]
            if len(updated) == len(devices):
                raise ValueError(f"Device not found: {device_id}")
            removed = [d for d in devices if d["device_id"] == device_id][0]
            self._save_paired(updated)
            log.info("Device revoked: %s (%s)",
                     removed["device_name"], device_id)
            return {
                "revoked": True,
                "device_id": device_id,
                "device_name": removed["device_name"],
            }

    def rotate_token(self, device_id: str) -> dict:
        """Rotate a device's auth token. Returns the new raw token once."""
        with _lock:
            devices = self._load_paired()
            for d in devices:
                if d["device_id"] == device_id:
                    new_token = _generate_token()
                    d["token_hash"] = _hash_token(new_token)
                    d["last_seen"] = _now_iso()
                    self._save_paired(devices)
                    log.info("Token rotated for device: %s", device_id)
                    return {"token": new_token, "device_id": device_id}
            raise ValueError(f"Device not found: {device_id}")


_store: PairingStore | None = None


def get_pairing_store(cfg: dict | None = None) -> PairingStore:
    """Get or create the global PairingStore singleton."""
    global _store
    if _store is None:
        cfg = cfg or {}
        _store = PairingStore(
            ttl_minutes=cfg.get("pairing_ttl_minutes", DEFAULT_TTL_MINUTES),
            default_scopes=cfg.get("default_device_scopes", DEFAULT_SCOPES),
        )
    return _store
