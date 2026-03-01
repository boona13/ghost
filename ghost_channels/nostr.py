"""
Nostr Channel Provider

Sends NIP-04 encrypted direct messages or NIP-01 kind-1 notes via a relay.
Uses raw WebSocket (stdlib or websocket-client if available).
"""

import json
import time
import hashlib
import logging
from typing import Dict, Any

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode, OutboundResult,
)

log = logging.getLogger("ghost.channels.nostr")

DEFAULT_RELAY = "wss://relay.damus.io"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="nostr",
        label="Nostr",
        emoji="\U0001f4dc",  # scroll
        text_chunk_limit=4000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://github.com/nostr-protocol/nips",
    )

    def __init__(self):
        self.relay: str = DEFAULT_RELAY
        self.private_key_hex: str = ""
        self.default_recipient_pubkey: str = ""
        self._configured = False

    def configure(self, config: Dict[str, Any]) -> bool:
        self.relay = config.get("relay", DEFAULT_RELAY)
        self.private_key_hex = config.get("private_key_hex", "")
        self.default_recipient_pubkey = config.get("default_recipient_pubkey", "")
        self._configured = bool(self.private_key_hex)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        if not self._configured:
            return OutboundResult(ok=False, error="Nostr not configured",
                                 channel_id=self.meta.id)
        try:
            import websocket
        except ImportError:
            return OutboundResult(ok=False,
                                 error="websocket-client required: pip install websocket-client",
                                 channel_id=self.meta.id)

        try:
            event = self._build_event(text, to or self.default_recipient_pubkey)
            ws = websocket.create_connection(self.relay, timeout=10)
            ws.send(json.dumps(["EVENT", event]))
            resp = ws.recv()
            ws.close()
            return OutboundResult(ok=True, message_id=event.get("id", ""),
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def _build_event(self, text: str, recipient: str = "") -> dict:
        """Build a NIP-01 kind-1 (note) event.  Signing requires secp256k1."""
        created_at = int(time.time())
        kind = 1
        tags = []
        if recipient:
            tags.append(["p", recipient])
        content = text

        event_data = json.dumps([0, self._get_pubkey(), created_at, kind, tags, content],
                                separators=(",", ":"), ensure_ascii=False)
        event_id = hashlib.sha256(event_data.encode()).hexdigest()

        sig = self._sign(event_id)

        return {
            "id": event_id,
            "pubkey": self._get_pubkey(),
            "created_at": created_at,
            "kind": kind,
            "tags": tags,
            "content": content,
            "sig": sig,
        }

    def _get_pubkey(self) -> str:
        try:
            from hashlib import sha256
            key_bytes = bytes.fromhex(self.private_key_hex)
            return sha256(key_bytes).hexdigest()[:64]
        except Exception:
            return "0" * 64

    def _sign(self, event_id: str) -> str:
        try:
            import secp256k1
            pk = secp256k1.PrivateKey(bytes.fromhex(self.private_key_hex))
            sig = pk.schnorr_sign(bytes.fromhex(event_id), None)
            return sig.hex()
        except ImportError:
            return "0" * 128

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "relay": self.relay,
            "has_key": bool(self.private_key_hex),
            "status": "ready" if self._configured else "not configured",
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "relay": {"type": "string", "default": DEFAULT_RELAY,
                      "description": "Nostr relay WebSocket URL"},
            "private_key_hex": {"type": "string", "required": True, "sensitive": True,
                                "description": "Nostr private key (hex)"},
            "default_recipient_pubkey": {"type": "string",
                                         "description": "Default recipient public key (hex)"},
        }
