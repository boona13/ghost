"""
Microsoft Teams Channel Provider

Outbound via incoming webhook connector or MS Graph API.
Inbound via Bot Framework (requires registered bot).
"""

import logging
from typing import Dict, Any, Callable

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.msteams")

GRAPH_API = "https://graph.microsoft.com/v1.0"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="msteams",
        label="Microsoft Teams",
        emoji="\U0001f4bc",  # briefcase
        supports_media=True,
        supports_threads=True,
        supports_groups=True,
        supports_inbound=True,
        text_chunk_limit=28000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview",
    )

    def __init__(self):
        self.webhook_url: str = ""
        self.access_token: str = ""
        self.team_id: str = ""
        self.channel_id: str = ""
        self._configured = False

    def configure(self, config: Dict[str, Any]) -> bool:
        self.webhook_url = config.get("webhook_url", "")
        self.access_token = config.get("access_token", "")
        self.team_id = config.get("team_id", "")
        self.channel_id = config.get("channel_id", "")
        self._configured = bool(self.webhook_url or self.access_token)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        if self.webhook_url:
            return self._send_webhook(text)
        if self.access_token and (to or self.channel_id):
            return self._send_graph(to or self.channel_id, text)
        return OutboundResult(ok=False, error="No webhook_url or access_token configured",
                             channel_id=self.meta.id)

    def _send_webhook(self, text: str) -> OutboundResult:
        payload = {
            "@type": "MessageCard",
            "summary": "Ghost",
            "text": text,
        }
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def _send_graph(self, channel_id: str, text: str) -> OutboundResult:
        url = f"{GRAPH_API}/teams/{self.team_id}/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bearer {self.access_token}",
                   "Content-Type": "application/json"}
        payload = {"body": {"content": text, "contentType": "text"}}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                return OutboundResult(ok=True, message_id=resp.json().get("id", ""),
                                      channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "has_webhook": bool(self.webhook_url),
            "has_graph_token": bool(self.access_token),
            "status": "ready" if self._configured else "not configured",
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "webhook_url": {"type": "string", "sensitive": True,
                            "description": "Teams Incoming Webhook URL"},
            "access_token": {"type": "string", "sensitive": True,
                             "description": "MS Graph API access token (for bot mode)"},
            "team_id": {"type": "string",
                        "description": "Team ID (for Graph API)"},
            "channel_id": {"type": "string",
                           "description": "Channel ID (for Graph API)"},
        }
