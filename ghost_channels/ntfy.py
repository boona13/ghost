"""
ntfy.sh Channel Provider

Zero-signup push notifications via ntfy.sh (or self-hosted instance).
Outbound: HTTP POST to topic.  Inbound: SSE subscription on background thread.
Requires only `requests` (already a Ghost dependency).
"""

import json
import time
import threading
import logging
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.ntfy")

DEFAULT_SERVER = "https://ntfy.sh"


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="ntfy",
        label="ntfy",
        emoji="\U0001f514",  # bell
        supports_media=True,
        supports_inbound=True,
        text_chunk_limit=4096,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://docs.ntfy.sh/",
    )

    def __init__(self):
        self.server: str = DEFAULT_SERVER
        self.topic: str = ""
        self.token: str = ""
        self._configured = False
        self._stop_event = threading.Event()
        self._inbound_thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.server = config.get("server", DEFAULT_SERVER).rstrip("/")
        self.topic = config.get("topic", "")
        self.token = config.get("token", "")
        self._configured = bool(self.topic)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        topic = to or self.topic
        if not topic:
            return OutboundResult(ok=False, error="No ntfy topic configured",
                                 channel_id=self.meta.id)
        url = f"{self.server}/{topic}"
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        title = kwargs.get("title", "Ghost")
        priority = kwargs.get("priority", "default")
        ntfy_priority = {"low": "2", "normal": "3", "high": "4", "critical": "5"}.get(
            priority, "3")

        headers["Title"] = title
        headers["Priority"] = ntfy_priority
        tags = kwargs.get("tags", "robot")
        if tags:
            headers["Tags"] = tags

        try:
            resp = requests.post(url, data=text.encode("utf-8"), headers=headers,
                                 timeout=15)
            if resp.status_code in (200, 201):
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return OutboundResult(ok=True, message_id=body.get("id", ""),
                                      channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def send_media(self, to: str, media_path: str, caption: str = "",
                   **kwargs) -> OutboundResult:
        topic = to or self.topic
        if not topic:
            return OutboundResult(ok=False, error="No ntfy topic configured",
                                 channel_id=self.meta.id)
        url = f"{self.server}/{topic}"
        headers: Dict[str, str] = {"Filename": Path(media_path).name}
        if caption:
            headers["Message"] = caption
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with open(media_path, "rb") as f:
                resp = requests.put(url, data=f, headers=headers, timeout=30)
            if resp.status_code in (200, 201):
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self._configured or not self.topic:
            return False
        self._stop_event.clear()
        self._inbound_thread = threading.Thread(
            target=self._poll_sse, args=(on_message,),
            daemon=True, name=f"ntfy-inbound-{self.topic}",
        )
        self._inbound_thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._inbound_thread:
            self._inbound_thread.join(timeout=5)
            self._inbound_thread = None

    def _poll_sse(self, on_message: Callable[[InboundMessage], None]):
        """Subscribe to the ntfy topic via SSE and relay messages."""
        url = f"{self.server}/{self.topic}/sse"
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        while not self._stop_event.is_set():
            try:
                with requests.get(url, headers=headers, stream=True, timeout=90) as resp:
                    for line in resp.iter_lines(decode_unicode=True):
                        if self._stop_event.is_set():
                            break
                        if not line or not line.startswith("data: "):
                            continue
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        if data.get("event") != "message":
                            continue
                        msg = InboundMessage(
                            channel_id="ntfy",
                            sender_id=data.get("topic", self.topic),
                            sender_name="ntfy",
                            text=data.get("message", ""),
                            timestamp=data.get("time", time.time()),
                            raw=data,
                        )
                        if msg.text:
                            on_message(msg)
            except Exception as exc:
                if not self._stop_event.is_set():
                    log.debug("ntfy SSE reconnecting after error: %s", exc)
                    time.sleep(5)

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "server": self.server,
            "topic": self.topic,
            "has_token": bool(self.token),
            "status": "ready" if self._configured else "not configured",
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "topic": {"type": "string", "required": True,
                      "description": "ntfy topic name (e.g. 'ghost-alerts')"},
            "server": {"type": "string", "default": DEFAULT_SERVER,
                       "description": "ntfy server URL"},
            "token": {"type": "string", "sensitive": True,
                      "description": "Access token (optional, for private topics)"},
        }
