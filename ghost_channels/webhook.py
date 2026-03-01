"""
Generic Webhook Channel Provider

Outbound: POST JSON to a user-specified URL.
Inbound:  Registers a Flask endpoint that other services can POST to.
Zero external dependencies (uses requests + stdlib).
"""

import json
import time
import threading
import logging
import hashlib
import hmac
from typing import Dict, Any, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.webhook")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="webhook",
        label="Webhook",
        emoji="\U0001f517",  # link
        supports_media=False,
        supports_inbound=True,
        text_chunk_limit=65536,
        delivery_mode=DeliveryMode.WEBHOOK,
        docs_url="",
    )

    def __init__(self):
        self.outbound_url: str = ""
        self.outbound_headers: Dict[str, str] = {}
        self.inbound_secret: str = ""
        self.inbound_path: str = "/api/channels/webhook/inbound"
        self._configured = False
        self._on_message: Optional[Callable] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.outbound_url = config.get("outbound_url", "")
        raw_headers = config.get("outbound_headers", {})
        self.outbound_headers = raw_headers if isinstance(raw_headers, dict) else {}
        self.inbound_secret = config.get("inbound_secret", "")
        self.inbound_path = config.get("inbound_path", self.inbound_path)
        self._configured = bool(self.outbound_url)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        url = to or self.outbound_url
        if not url:
            return OutboundResult(ok=False, error="No webhook URL configured",
                                 channel_id=self.meta.id)
        payload = {
            "text": text,
            "source": "ghost",
            "timestamp": time.time(),
        }
        payload.update({k: v for k, v in kwargs.items()
                        if k in ("title", "priority", "tags")})
        headers = {"Content-Type": "application/json"}
        headers.update(self.outbound_headers)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code < 300:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        self._on_message = on_message
        return True

    def handle_inbound_request(self, data: dict, headers: dict = None) -> bool:
        """Called by the dashboard route when a POST hits the inbound webhook path."""
        if self.inbound_secret:
            sig = (headers or {}).get("X-Ghost-Signature", "")
            body_bytes = json.dumps(data, sort_keys=True).encode()
            expected = hmac.new(self.inbound_secret.encode(), body_bytes,
                                hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                log.warning("Webhook inbound signature mismatch")
                return False

        text = data.get("text", data.get("message", data.get("content", "")))
        if not text:
            return False

        msg = InboundMessage(
            channel_id="webhook",
            sender_id=data.get("sender_id", data.get("user", "webhook")),
            sender_name=data.get("sender_name", "Webhook"),
            text=str(text),
            timestamp=data.get("timestamp", time.time()),
            raw=data,
        )
        if self._on_message:
            self._on_message(msg)
        return True

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "outbound_url": bool(self.outbound_url),
            "has_inbound_secret": bool(self.inbound_secret),
            "inbound_path": self.inbound_path,
            "status": "ready" if self._configured else "not configured",
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "outbound_url": {"type": "string", "required": True,
                             "description": "URL to POST outbound messages to"},
            "outbound_headers": {"type": "object",
                                 "description": "Extra HTTP headers for outbound requests"},
            "inbound_secret": {"type": "string", "sensitive": True,
                               "description": "HMAC secret for verifying inbound webhooks"},
            "inbound_path": {"type": "string", "default": "/api/channels/webhook/inbound",
                             "description": "Flask route path for inbound webhook"},
        }
