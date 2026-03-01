"""
Google Chat Channel Provider

Outbound via incoming webhook.  Google Chat webhooks accept simple JSON.
"""

import logging
from typing import Dict, Any

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode, OutboundResult,
)

log = logging.getLogger("ghost.channels.googlechat")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="googlechat",
        label="Google Chat",
        emoji="\U0001f4e7",
        supports_groups=True,
        text_chunk_limit=4096,
        delivery_mode=DeliveryMode.WEBHOOK,
        docs_url="https://developers.google.com/workspace/chat/quickstart/webhooks",
    )

    def __init__(self):
        self.webhook_url: str = ""
        self._configured = False

    def configure(self, config: Dict[str, Any]) -> bool:
        self.webhook_url = config.get("webhook_url", "")
        self._configured = bool(self.webhook_url)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        url = to or self.webhook_url
        if not url:
            return OutboundResult(ok=False, error="No webhook URL",
                                 channel_id=self.meta.id)
        try:
            resp = requests.post(url, json={"text": text}, timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "has_webhook": bool(self.webhook_url),
            "status": "ready" if self._configured else "not configured",
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "webhook_url": {"type": "string", "required": True, "sensitive": True,
                            "description": "Google Chat space webhook URL"},
        }
