"""
Slack Channel Provider

Two modes:
  1. Webhook mode (outbound only): Just needs a webhook URL.  Zero dependencies.
  2. Bot mode (bidirectional): Uses `slack_sdk` if installed, falls back to raw API.

Inbound uses Socket Mode when slack_sdk is available, otherwise not supported.
"""

import json
import time
import threading
import logging
from typing import Dict, Any, Callable, Optional

import requests

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)
from ghost_channels.actions import ActionsMixin, ActionType, ActionResult
from ghost_channels.threading_ext import ThreadingMixin, ThreadMessage
from ghost_channels.streaming import StreamingMixin, StreamConfig
from ghost_channels.health import HealthMixin
from ghost_channels.security import SecurityMixin
from ghost_channels.onboard import OnboardingMixin, SetupStep, StepType, StepValidation
from ghost_channels.mentions import MentionMixin

log = logging.getLogger("ghost.channels.slack")

SLACK_API = "https://slack.com/api"


class Provider(ChannelProvider, ActionsMixin, ThreadingMixin, StreamingMixin,
               HealthMixin, SecurityMixin, OnboardingMixin, MentionMixin):

    meta = ChannelMeta(
        id="slack",
        label="Slack",
        emoji="\U0001f4ac",
        supports_media=True,
        supports_threads=True,
        supports_reactions=True,
        supports_groups=True,
        supports_inbound=True,
        supports_edit=True,
        supports_unsend=True,
        supports_streaming=True,
        text_chunk_limit=4000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://api.slack.com/",
    )

    def __init__(self):
        self.bot_token: str = ""
        self.app_token: str = ""
        self.webhook_url: str = ""
        self.default_channel: str = ""
        self._configured = False
        self._stop_event = threading.Event()
        self._socket_thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.bot_token = config.get("bot_token", "")
        self.app_token = config.get("app_token", "")
        self.webhook_url = config.get("webhook_url", "")
        self.default_channel = config.get("default_channel", "")
        self._configured = bool(self.bot_token or self.webhook_url)
        return self._configured

    def _api_post(self, method: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self.bot_token}",
                   "Content-Type": "application/json"}
        resp = requests.post(f"{SLACK_API}/{method}", json=kwargs,
                             headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("error", "Slack API error"))
        return data

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        channel = to or self.default_channel
        thread_ts = kwargs.get("thread_id")

        if self.webhook_url and not channel:
            return self._send_webhook(text, **kwargs)

        if not self.bot_token:
            if self.webhook_url:
                return self._send_webhook(text, **kwargs)
            return OutboundResult(ok=False, error="No bot_token or webhook_url",
                                 channel_id=self.meta.id)
        if not channel:
            return OutboundResult(ok=False, error="No channel specified",
                                 channel_id=self.meta.id)
        try:
            params: Dict[str, Any] = {"channel": channel, "text": text}
            if thread_ts:
                params["thread_ts"] = thread_ts
            data = self._api_post("chat.postMessage", **params)
            ts = data.get("ts", "")
            return OutboundResult(ok=True, message_id=ts, channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def _send_webhook(self, text: str, **kwargs) -> OutboundResult:
        try:
            payload: Dict[str, Any] = {"text": text}
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            if resp.status_code == 200:
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=f"HTTP {resp.status_code}",
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def send_media(self, to: str, media_path: str, caption: str = "",
                   **kwargs) -> OutboundResult:
        if not self.bot_token:
            return OutboundResult(ok=False, error="Media upload requires bot_token",
                                 channel_id=self.meta.id)
        channel = to or self.default_channel
        if not channel:
            return OutboundResult(ok=False, error="No channel specified",
                                 channel_id=self.meta.id)
        try:
            with open(media_path, "rb") as f:
                resp = requests.post(
                    f"{SLACK_API}/files.upload",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data={"channels": channel, "initial_comment": caption},
                    files={"file": f},
                    timeout=60,
                )
            data = resp.json()
            if data.get("ok"):
                return OutboundResult(ok=True, channel_id=self.meta.id)
            return OutboundResult(ok=False, error=data.get("error", ""),
                                 channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self.bot_token or not self.app_token:
            return False
        try:
            from slack_sdk.socket_mode import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError:
            log.info("slack_sdk not installed; Slack inbound disabled. "
                     "pip install slack_sdk")
            return False

        self._stop_event.clear()
        client = SocketModeClient(app_token=self.app_token)

        def _handler(cli, req: SocketModeRequest):
            cli.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
            if req.type != "events_api" or not req.payload:
                return
            event = req.payload.get("event", {})
            if event.get("type") != "message" or event.get("subtype"):
                return
            if event.get("bot_id"):
                return
            msg = InboundMessage(
                channel_id="slack",
                sender_id=event.get("user", ""),
                sender_name=event.get("user", "unknown"),
                text=event.get("text", ""),
                thread_id=event.get("thread_ts", event.get("ts", "")),
                timestamp=float(event.get("ts", time.time())),
                raw=event,
            )
            if msg.text:
                on_message(msg)

        client.socket_mode_request_listeners.append(_handler)
        self._socket_thread = threading.Thread(
            target=client.connect, daemon=True, name="slack-socket-mode",
        )
        self._socket_thread.start()
        self._stop_client = client
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if hasattr(self, "_stop_client"):
            try:
                self._stop_client.close()
            except Exception:
                pass
        if self._socket_thread:
            self._socket_thread.join(timeout=5)
            self._socket_thread = None

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "has_bot_token": bool(self.bot_token),
            "has_app_token": bool(self.app_token),
            "has_webhook": bool(self.webhook_url),
            "default_channel": self.default_channel,
        }
        if self.bot_token:
            try:
                data = self._api_post("auth.test")
                status["team"] = data.get("team", "")
                status["bot_user"] = data.get("user", "")
                status["status"] = "connected"
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
            "bot_token": {"type": "string", "sensitive": True,
                          "description": "Slack Bot User OAuth Token (xoxb-...)"},
            "app_token": {"type": "string", "sensitive": True,
                          "description": "Slack App-Level Token for Socket Mode (xapp-...)"},
            "webhook_url": {"type": "string", "sensitive": True,
                            "description": "Incoming Webhook URL (outbound only, no bot_token needed)"},
            "default_channel": {"type": "string",
                                "description": "Default channel ID (e.g. C0123456)"},
        }

    # ── Phase 2: Actions ─────────────────────────────────────

    def supported_actions(self):
        return [ActionType.REACT, ActionType.EDIT, ActionType.UNSEND, ActionType.PIN]

    def react(self, message_id: str, emoji: str, to: str = "",
              **kwargs) -> ActionResult:
        if not self.bot_token:
            return ActionResult(ok=False, action="react", error="No bot_token",
                                channel_id=self.meta.id)
        channel = to or self.default_channel
        if not channel:
            return ActionResult(ok=False, action="react", error="No channel",
                                channel_id=self.meta.id)
        try:
            self._api_post("reactions.add", channel=channel,
                            timestamp=message_id, name=emoji.strip(":"))
            return ActionResult(ok=True, action="react", message_id=message_id,
                                channel_id=self.meta.id)
        except Exception as exc:
            return ActionResult(ok=False, action="react", error=str(exc),
                                channel_id=self.meta.id)

    def edit_message(self, message_id: str, new_text: str, to: str = "",
                     **kwargs) -> ActionResult:
        if not self.bot_token:
            return ActionResult(ok=False, action="edit", error="No bot_token",
                                channel_id=self.meta.id)
        channel = to or self.default_channel
        try:
            self._api_post("chat.update", channel=channel,
                            ts=message_id, text=new_text)
            return ActionResult(ok=True, action="edit", message_id=message_id,
                                channel_id=self.meta.id)
        except Exception as exc:
            return ActionResult(ok=False, action="edit", error=str(exc),
                                channel_id=self.meta.id)

    def unsend(self, message_id: str, to: str = "",
               **kwargs) -> ActionResult:
        if not self.bot_token:
            return ActionResult(ok=False, action="unsend", error="No bot_token",
                                channel_id=self.meta.id)
        channel = to or self.default_channel
        try:
            self._api_post("chat.delete", channel=channel, ts=message_id)
            return ActionResult(ok=True, action="unsend", message_id=message_id,
                                channel_id=self.meta.id)
        except Exception as exc:
            return ActionResult(ok=False, action="unsend", error=str(exc),
                                channel_id=self.meta.id)

    # ── Phase 2: Streaming ───────────────────────────────────

    def supports_streaming(self) -> bool:
        return bool(self.bot_token)

    def block_streaming_coalesce_defaults(self) -> StreamConfig:
        return StreamConfig(min_chars=50, idle_ms=500, max_edits_per_second=2.0)

    def edit_message_text(self, message_id: str, new_text: str,
                           to: str = "", **kwargs) -> bool:
        channel = to or self.default_channel
        if not self.bot_token or not channel:
            return False
        try:
            self._api_post("chat.update", channel=channel,
                            ts=message_id, text=new_text)
            return True
        except Exception:
            return False

    def send_placeholder(self, to: str, placeholder: str = "...",
                          **kwargs) -> Optional[str]:
        channel = to or self.default_channel
        if not self.bot_token or not channel:
            return None
        try:
            data = self._api_post("chat.postMessage", channel=channel,
                                   text=placeholder)
            return data.get("ts", "")
        except Exception:
            return None

    # ── Phase 2: Threading ───────────────────────────────────

    def get_thread_history(self, thread_id: str, to: str = "",
                           limit: int = 20):
        if not self.bot_token:
            return []
        channel = to or self.default_channel
        if not channel:
            return []
        try:
            data = self._api_post("conversations.replies",
                                   channel=channel, ts=thread_id, limit=limit)
            messages = []
            for msg in data.get("messages", []):
                messages.append(ThreadMessage(
                    message_id=msg.get("ts", ""),
                    sender_id=msg.get("user", ""),
                    sender_name=msg.get("user", "unknown"),
                    text=msg.get("text", ""),
                    timestamp=float(msg.get("ts", 0)),
                    is_bot=bool(msg.get("bot_id")),
                ))
            return messages
        except Exception:
            return []

    # ── Phase 2: Onboarding ──────────────────────────────────

    def get_setup_steps(self):
        return [
            SetupStep(
                id="bot_token", label="Bot Token",
                description="Bot User OAuth Token (xoxb-...)",
                step_type=StepType.SECRET_INPUT, required=True,
                config_key="bot_token",
                help_url="https://api.slack.com/authentication/token-types",
                validation_regex=r'^xoxb-.+$',
                validation_message="Should start with xoxb-",
            ),
            SetupStep(
                id="app_token", label="App Token (Socket Mode)",
                description="App-Level Token (xapp-...) for bidirectional messaging",
                step_type=StepType.SECRET_INPUT, required=False,
                config_key="app_token",
                validation_regex=r'^xapp-.+$',
                validation_message="Should start with xapp-",
            ),
            SetupStep(
                id="default_channel", label="Default Channel",
                description="Channel ID for outbound messages (e.g. C0123456)",
                step_type=StepType.TEXT_INPUT, required=False,
                config_key="default_channel",
            ),
        ]

    def validate_step(self, step_id: str, user_input: str) -> StepValidation:
        if step_id == "bot_token" and user_input:
            try:
                headers = {"Authorization": f"Bearer {user_input}"}
                resp = requests.post(f"{SLACK_API}/auth.test", headers=headers,
                                     timeout=10)
                data = resp.json()
                if data.get("ok"):
                    team = data.get("team", "")
                    return StepValidation(ok=True,
                                          message=f"Valid! Team: {team}")
                return StepValidation(ok=False,
                                      message=data.get("error", "Invalid token"))
            except Exception as exc:
                return StepValidation(ok=False, message=f"Connection error: {exc}")
        return super().validate_step(step_id, user_input)
