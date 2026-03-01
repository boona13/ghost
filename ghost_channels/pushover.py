"""
Pushover Channel Provider

Push notifications via the Pushover API.  Requires a Pushover account
and application token.  Zero dependencies beyond `requests`.
"""

import logging
from typing import Dict, Any

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode, OutboundResult,
)

log = logging.getLogger("ghost.channels.pushover")

PUSHOVER_API = "https://api.pushover.net/1/messages.json"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="pushover",
        label="Pushover",
        emoji="\U0001f4f3",  # vibration
        text_chunk_limit=1024,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://pushover.net/api",
    )

    def __init__(self):
        self.app_token: str = ""
        self.user_key: str = ""
        self.default_device: str = ""
        self._configured = False

    def configure(self, config: Dict[str, Any]) -> bool:
        self.app_token = config.get("app_token", "")
        self.user_key = config.get("user_key", "")
        self.default_device = config.get("device", "")
        self._configured = bool(self.app_token and self.user_key)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        if not self._configured:
            return OutboundResult(ok=False, error="Pushover not configured",
                                 channel_id=self.meta.id)
        title = kwargs.get("title", "Ghost")
        priority_map = {"low": "-1", "normal": "0", "high": "1", "critical": "2"}
        priority = priority_map.get(kwargs.get("priority", "normal"), "0")

        payload = {
            "token": self.app_token,
            "user": to or self.user_key,
            "message": text,
            "title": title,
            "priority": priority,
        }
        if self.default_device:
            payload["device"] = self.default_device
        if priority == "2":
            payload["retry"] = 60
            payload["expire"] = 3600

        try:
            resp = requests.post(PUSHOVER_API, data=payload, timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "has_app_token": bool(self.app_token),
            "has_user_key": bool(self.user_key),
        }
        if self._configured:
            try:
                resp = requests.post("https://api.pushover.net/1/users/validate.json",
                                     data={"token": self.app_token, "user": self.user_key},
                                     timeout=5)
                if resp.status_code == 200 and resp.json().get("status") == 1:
                    status["status"] = "connected"
                    status["devices"] = resp.json().get("devices", [])
                else:
                    status["status"] = "error"
                    status["last_error"] = resp.text[:200]
            except Exception as exc:
                status["status"] = "error"
                status["last_error"] = str(exc)
        else:
            status["status"] = "not configured"
        return status

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "app_token": {"type": "string", "required": True, "sensitive": True,
                          "description": "Pushover application API token"},
            "user_key": {"type": "string", "required": True, "sensitive": True,
                         "description": "Pushover user key"},
            "device": {"type": "string",
                       "description": "Target device name (optional, sends to all if empty)"},
        }
