"""
LINE Channel Provider

Uses the LINE Messaging API.  Outbound via push/reply messages.
Inbound via webhook (LINE Platform POSTs events).
"""

import time
import logging
from typing import Dict, Any, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.line")

LINE_API = "https://api.line.me/v2/bot"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="line",
        label="LINE",
        emoji="\U0001f49a",  # green heart
        supports_media=True,
        supports_inbound=True,
        text_chunk_limit=5000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://developers.line.biz/en/docs/messaging-api/",
    )

    def __init__(self):
        self.channel_access_token: str = ""
        self.default_user_id: str = ""
        self._configured = False
        self._on_message: Optional[Callable] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.channel_access_token = config.get("channel_access_token", "")
        self.default_user_id = config.get("default_user_id", "")
        self._configured = bool(self.channel_access_token)
        return self._configured

    def _headers(self):
        return {"Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json"}

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        user_id = to or self.default_user_id
        if not user_id:
            return OutboundResult(ok=False, error="No user ID specified",
                                 channel_id=self.meta.id)
        url = f"{LINE_API}/message/push"
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        self._on_message = on_message
        return True

    def handle_webhook_event(self, data: dict):
        """Process LINE webhook event body."""
        if not self._on_message:
            return
        for event in data.get("events", []):
            if event.get("type") != "message":
                continue
            message = event.get("message", {})
            if message.get("type") != "text":
                continue
            source = event.get("source", {})
            msg = InboundMessage(
                channel_id="line",
                sender_id=source.get("userId", ""),
                sender_name=source.get("userId", "unknown"),
                text=message.get("text", ""),
                timestamp=event.get("timestamp", time.time() * 1000) / 1000.0,
                raw=event,
            )
            self._on_message(msg)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "has_token": bool(self.channel_access_token),
        }
        if self._configured:
            try:
                resp = requests.get(f"{LINE_API}/info",
                                    headers=self._headers(), timeout=5)
                if resp.status_code == 200:
                    status["status"] = "connected"
                    status["bot_name"] = resp.json().get("displayName", "")
                else:
                    status["status"] = "error"
                    status["last_error"] = f"HTTP {resp.status_code}"
            except Exception as exc:
                status["status"] = "error"
                status["last_error"] = str(exc)
        else:
            status["status"] = "not configured"
        return status

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "channel_access_token": {"type": "string", "required": True, "sensitive": True,
                                     "description": "LINE Messaging API channel access token"},
            "default_user_id": {"type": "string",
                                "description": "Default LINE user ID for push messages"},
        }
