"""
Mattermost Channel Provider

Outbound via incoming webhook or Mattermost API.
Inbound via WebSocket (Mattermost API v4).
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

log = logging.getLogger("ghost.channels.mattermost")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="mattermost",
        label="Mattermost",
        emoji="\U0001f4e2",  # loudspeaker
        supports_media=True,
        supports_threads=True,
        supports_groups=True,
        supports_inbound=True,
        text_chunk_limit=16383,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://api.mattermost.com/",
    )

    def __init__(self):
        self.server_url: str = ""
        self.access_token: str = ""
        self.webhook_url: str = ""
        self.default_channel_id: str = ""
        self._configured = False
        self._stop_event = threading.Event()
        self._ws_thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.server_url = config.get("server_url", "").rstrip("/")
        self.access_token = config.get("access_token", "")
        self.webhook_url = config.get("webhook_url", "")
        self.default_channel_id = config.get("default_channel_id", "")
        self._configured = bool(self.webhook_url or (self.server_url and self.access_token))
        return self._configured

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"}

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        if self.webhook_url and not to:
            return self._send_webhook(text, **kwargs)
        if self.access_token and self.server_url:
            channel_id = to or self.default_channel_id
            if not channel_id:
                return OutboundResult(ok=False, error="No channel_id specified",
                                     channel_id=self.meta.id)
            return self._send_api(channel_id, text, **kwargs)
        if self.webhook_url:
            return self._send_webhook(text, **kwargs)
        return OutboundResult(ok=False, error="Not configured",
                             channel_id=self.meta.id)

    def _send_webhook(self, text: str, **kwargs) -> OutboundResult:
        payload = {"text": text}
        if kwargs.get("channel"):
            payload["channel"] = kwargs["channel"]
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def _send_api(self, channel_id: str, text: str, **kwargs) -> OutboundResult:
        url = f"{self.server_url}/api/v4/posts"
        payload: Dict[str, Any] = {"channel_id": channel_id, "message": text}
        root_id = kwargs.get("thread_id")
        if root_id:
            payload["root_id"] = root_id
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=15)
            if resp.status_code in (200, 201):
                return OutboundResult(ok=True, message_id=resp.json().get("id", ""),
                                      channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                                  channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self.server_url or not self.access_token:
            return False
        try:
            import websocket
        except ImportError:
            log.info("websocket-client required for Mattermost inbound: "
                     "pip install websocket-client")
            return False
        self._stop_event.clear()
        self._ws_thread = threading.Thread(
            target=self._ws_listen, args=(on_message,),
            daemon=True, name="mattermost-ws",
        )
        self._ws_thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._ws_thread:
            self._ws_thread.join(timeout=5)
            self._ws_thread = None

    def _ws_listen(self, on_message: Callable[[InboundMessage], None]):
        import websocket
        import json
        ws_url = self.server_url.replace("https://", "wss://").replace(
            "http://", "ws://") + "/api/v4/websocket"

        while not self._stop_event.is_set():
            try:
                ws = websocket.create_connection(ws_url, timeout=5)
                auth = {"seq": 1, "action": "authentication_challenge",
                        "data": {"token": self.access_token}}
                ws.send(json.dumps(auth))
                ws.settimeout(1)

                while not self._stop_event.is_set():
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    data = json.loads(raw)
                    if data.get("event") != "posted":
                        continue
                    post = json.loads(data.get("data", {}).get("post", "{}"))
                    text = post.get("message", "")
                    if not text:
                        continue
                    msg = InboundMessage(
                        channel_id="mattermost",
                        sender_id=post.get("user_id", ""),
                        sender_name=post.get("user_id", "unknown"),
                        text=text,
                        thread_id=post.get("root_id", ""),
                        timestamp=post.get("create_at", time.time() * 1000) / 1000.0,
                        raw=post,
                    )
                    on_message(msg)
                ws.close()
            except Exception as exc:
                if not self._stop_event.is_set():
                    log.debug("Mattermost WS error: %s", exc)
                    time.sleep(5)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "server_url": self.server_url,
            "has_token": bool(self.access_token),
            "has_webhook": bool(self.webhook_url),
        }
        if self.access_token and self.server_url:
            try:
                resp = requests.get(f"{self.server_url}/api/v4/users/me",
                                    headers=self._headers(), timeout=5)
                if resp.status_code == 200:
                    status["username"] = resp.json().get("username", "")
                    status["status"] = "connected"
                else:
                    status["status"] = "error"
                    status["last_error"] = f"HTTP {resp.status_code}"
            except Exception as exc:
                status["status"] = "error"
                status["last_error"] = str(exc)
        elif self.webhook_url:
            status["status"] = "webhook-only"
        else:
            status["status"] = "not configured"
        return status

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "server_url": {"type": "string",
                           "description": "Mattermost server URL (e.g. https://mattermost.example.com)"},
            "access_token": {"type": "string", "sensitive": True,
                             "description": "Personal access token or bot token"},
            "webhook_url": {"type": "string", "sensitive": True,
                            "description": "Incoming webhook URL (outbound only)"},
            "default_channel_id": {"type": "string",
                                   "description": "Default channel ID for API messages"},
        }
