"""
Signal Channel Provider

Communicates with a locally-running signal-cli REST API daemon.
See: https://github.com/bbernhard/signal-cli-rest-api

Outbound: POST to signal-cli API.  Inbound: polling /v1/receive.
Zero Python dependencies beyond `requests`.
"""

import time
import threading
import logging
from typing import Dict, Any, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.signal")

DEFAULT_API_URL = "http://localhost:8080"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="signal",
        label="Signal",
        emoji="\U0001f510",  # locked
        supports_media=True,
        supports_groups=True,
        supports_inbound=True,
        text_chunk_limit=4000,
        delivery_mode=DeliveryMode.GATEWAY,
        docs_url="https://github.com/bbernhard/signal-cli-rest-api",
    )

    def __init__(self):
        self.api_url: str = DEFAULT_API_URL
        self.phone_number: str = ""
        self.default_recipient: str = ""
        self._configured = False
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.api_url = config.get("api_url", DEFAULT_API_URL).rstrip("/")
        self.phone_number = config.get("phone_number", "")
        self.default_recipient = config.get("default_recipient", "")
        self._configured = bool(self.phone_number)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        recipient = to or self.default_recipient
        if not recipient:
            return OutboundResult(ok=False, error="No recipient specified",
                                 channel_id=self.meta.id)
        url = f"{self.api_url}/v2/send"
        payload: Dict[str, Any] = {
            "message": text,
            "number": self.phone_number,
            "recipients": [recipient],
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code in (200, 201):
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                 channel_id=self.meta.id)
        except requests.ConnectionError:
            return OutboundResult(ok=False,
                                 error=f"Cannot connect to signal-cli at {self.api_url}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def send_media(self, to: str, media_path: str, caption: str = "",
                   **kwargs) -> OutboundResult:
        recipient = to or self.default_recipient
        if not recipient:
            return OutboundResult(ok=False, error="No recipient specified",
                                 channel_id=self.meta.id)
        url = f"{self.api_url}/v2/send"
        try:
            import base64
            with open(media_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            payload = {
                "message": caption,
                "number": self.phone_number,
                "recipients": [recipient],
                "base64_attachments": [f"data:application/octet-stream;base64,{b64}"],
            }
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code in (200, 201):
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self._configured:
            return False
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_receive, args=(on_message,),
            daemon=True, name="signal-inbound",
        )
        self._poll_thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None

    def _poll_receive(self, on_message: Callable[[InboundMessage], None]):
        url = f"{self.api_url}/v1/receive/{self.phone_number}"
        while not self._stop_event.is_set():
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    for entry in resp.json():
                        envelope = entry.get("envelope", {})
                        data_msg = envelope.get("dataMessage", {})
                        text = data_msg.get("message", "")
                        if not text:
                            continue
                        msg = InboundMessage(
                            channel_id="signal",
                            sender_id=envelope.get("source", ""),
                            sender_name=envelope.get("sourceName",
                                                     envelope.get("source", "unknown")),
                            text=text,
                            thread_id=data_msg.get("groupInfo", {}).get("groupId", ""),
                            timestamp=envelope.get("timestamp", time.time()) / 1000.0,
                            raw=entry,
                        )
                        on_message(msg)
            except requests.ConnectionError:
                pass
            except Exception as exc:
                if not self._stop_event.is_set():
                    log.debug("Signal poll error: %s", exc)

            for _ in range(5):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "api_url": self.api_url,
            "phone_number": self.phone_number,
        }
        if self._configured:
            try:
                resp = requests.get(f"{self.api_url}/v1/about", timeout=5)
                if resp.status_code == 200:
                    status["status"] = "connected"
                    status["api_version"] = resp.json().get("versions", [])
                else:
                    status["status"] = "error"
                    status["last_error"] = f"HTTP {resp.status_code}"
            except requests.ConnectionError:
                status["status"] = "error"
                status["last_error"] = f"Cannot connect to {self.api_url}"
            except Exception as exc:
                status["status"] = "error"
                status["last_error"] = str(exc)
        else:
            status["status"] = "not configured"
        return status

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "api_url": {"type": "string", "default": DEFAULT_API_URL,
                        "description": "signal-cli REST API base URL"},
            "phone_number": {"type": "string", "required": True,
                             "description": "Your registered Signal phone number (e.g. +1234567890)"},
            "default_recipient": {"type": "string",
                                  "description": "Default recipient phone number"},
        }
