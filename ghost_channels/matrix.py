"""
Matrix Channel Provider

Uses the Matrix client-server API via plain HTTP requests.
Optional: `matrix-nio` for end-to-end encryption and sync.
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
from ghost_channels.health import HealthMixin
from ghost_channels.security import SecurityMixin
from ghost_channels.onboard import OnboardingMixin
from ghost_channels.mentions import MentionMixin

log = logging.getLogger("ghost.channels.matrix")


class Provider(ChannelProvider, HealthMixin, SecurityMixin,
               OnboardingMixin, MentionMixin):

    meta = ChannelMeta(
        id="matrix",
        label="Matrix",
        emoji="\U0001f30d",
        supports_media=True,
        supports_threads=True,
        supports_groups=True,
        supports_inbound=True,
        text_chunk_limit=65536,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://spec.matrix.org/latest/client-server-api/",
    )

    def __init__(self):
        self.homeserver: str = ""
        self.access_token: str = ""
        self.default_room_id: str = ""
        self._configured = False
        self._stop_event = threading.Event()
        self._sync_thread: Optional[threading.Thread] = None
        self._next_batch: str = ""

    def configure(self, config: Dict[str, Any]) -> bool:
        self.homeserver = config.get("homeserver", "").rstrip("/")
        self.access_token = config.get("access_token", "")
        self.default_room_id = config.get("default_room_id", "")
        self._configured = bool(self.homeserver and self.access_token)
        return self._configured

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"}

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        room_id = to or self.default_room_id
        if not room_id:
            return OutboundResult(ok=False, error="No room_id specified",
                                 channel_id=self.meta.id)
        txn_id = str(int(time.time() * 1000))
        url = f"{self.homeserver}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"
        body = {"msgtype": "m.text", "body": text}
        if kwargs.get("formatted"):
            body["format"] = "org.matrix.custom.html"
            body["formatted_body"] = kwargs["formatted"]
        try:
            resp = requests.put(url, json=body, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                event_id = resp.json().get("event_id", "")
                return OutboundResult(ok=True, message_id=event_id,
                                      channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self._configured:
            return False
        self._stop_event.clear()
        self._sync_thread = threading.Thread(
            target=self._sync_loop, args=(on_message,),
            daemon=True, name="matrix-sync",
        )
        self._sync_thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
            self._sync_thread = None

    def _sync_loop(self, on_message: Callable[[InboundMessage], None]):
        url_base = f"{self.homeserver}/_matrix/client/v3/sync"
        while not self._stop_event.is_set():
            params: Dict[str, Any] = {"timeout": 30000}
            if self._next_batch:
                params["since"] = self._next_batch
            else:
                params["filter"] = '{"room":{"timeline":{"limit":0}}}'
            try:
                resp = requests.get(url_base, params=params,
                                    headers=self._headers(), timeout=35)
                if resp.status_code != 200:
                    time.sleep(5)
                    continue
                data = resp.json()
                self._next_batch = data.get("next_batch", self._next_batch)

                for room_id, room_data in data.get("rooms", {}).get("join", {}).items():
                    for event in room_data.get("timeline", {}).get("events", []):
                        if event.get("type") != "m.room.message":
                            continue
                        content = event.get("content", {})
                        text = content.get("body", "")
                        if not text:
                            continue
                        msg = InboundMessage(
                            channel_id="matrix",
                            sender_id=event.get("sender", ""),
                            sender_name=event.get("sender", "unknown"),
                            text=text,
                            thread_id=room_id,
                            timestamp=event.get("origin_server_ts", 0) / 1000.0,
                            raw=event,
                        )
                        on_message(msg)
            except Exception as exc:
                if not self._stop_event.is_set():
                    log.debug("Matrix sync error: %s", exc)
                    time.sleep(5)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "homeserver": self.homeserver,
            "default_room_id": self.default_room_id,
        }
        if self._configured:
            try:
                resp = requests.get(f"{self.homeserver}/_matrix/client/v3/account/whoami",
                                    headers=self._headers(), timeout=5)
                if resp.status_code == 200:
                    status["user_id"] = resp.json().get("user_id", "")
                    status["status"] = "connected"
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
            "homeserver": {"type": "string", "required": True,
                           "description": "Matrix homeserver URL (e.g. https://matrix.org)"},
            "access_token": {"type": "string", "required": True, "sensitive": True,
                             "description": "Matrix access token"},
            "default_room_id": {"type": "string",
                                "description": "Default room ID (e.g. !abc:matrix.org)"},
        }
