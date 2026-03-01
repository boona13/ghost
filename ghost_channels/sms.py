"""
SMS Channel Provider (via Twilio)

Outbound via Twilio REST API.  Inbound via Twilio webhook.
Requires a Twilio account with SID, auth token, and a phone number.
"""

import time
import logging
from typing import Dict, Any, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.sms")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="sms",
        label="SMS (Twilio)",
        emoji="\U0001f4f1",  # mobile
        supports_inbound=True,
        text_chunk_limit=1600,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://www.twilio.com/docs/sms",
    )

    def __init__(self):
        self.account_sid: str = ""
        self.auth_token: str = ""
        self.from_number: str = ""
        self.default_to: str = ""
        self._configured = False
        self._on_message: Optional[Callable] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.account_sid = config.get("account_sid", "")
        self.auth_token = config.get("auth_token", "")
        self.from_number = config.get("from_number", "")
        self.default_to = config.get("default_to", "")
        self._configured = bool(self.account_sid and self.auth_token and self.from_number)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        recipient = to or self.default_to
        if not recipient:
            return OutboundResult(ok=False, error="No recipient phone number",
                                 channel_id=self.meta.id)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        payload = {
            "From": self.from_number,
            "To": recipient,
            "Body": text,
        }
        try:
            resp = requests.post(url, data=payload,
                                 auth=(self.account_sid, self.auth_token),
                                 timeout=15)
            if resp.status_code in (200, 201):
                data = resp.json()
                return OutboundResult(ok=True, message_id=data.get("sid", ""),
                                      channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        self._on_message = on_message
        return True

    def handle_webhook_event(self, form_data: dict):
        """Process Twilio SMS webhook (form-encoded POST body)."""
        if not self._on_message:
            return
        text = form_data.get("Body", "")
        if not text:
            return
        msg = InboundMessage(
            channel_id="sms",
            sender_id=form_data.get("From", ""),
            sender_name=form_data.get("From", "unknown"),
            text=text,
            timestamp=time.time(),
            raw=form_data,
        )
        self._on_message(msg)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "from_number": self.from_number,
            "has_credentials": bool(self.account_sid and self.auth_token),
        }
        if self._configured:
            try:
                url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}.json"
                resp = requests.get(url, auth=(self.account_sid, self.auth_token),
                                    timeout=5)
                if resp.status_code == 200:
                    status["status"] = "connected"
                    status["friendly_name"] = resp.json().get("friendly_name", "")
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
            "account_sid": {"type": "string", "required": True, "sensitive": True,
                            "description": "Twilio Account SID"},
            "auth_token": {"type": "string", "required": True, "sensitive": True,
                           "description": "Twilio Auth Token"},
            "from_number": {"type": "string", "required": True,
                            "description": "Twilio phone number (e.g. +1234567890)"},
            "default_to": {"type": "string",
                           "description": "Default recipient phone number"},
        }
