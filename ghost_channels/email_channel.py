"""
Email Channel Provider

Outbound via SMTP.  Inbound via IMAP IDLE polling.
Uses only Python stdlib (smtplib, imaplib, email) — zero extra dependencies.
"""

import email
import email.mime.text
import email.mime.multipart
import email.mime.base
import imaplib
import smtplib
import ssl
import time
import threading
import logging
from typing import Dict, Any, Callable, Optional
from pathlib import Path

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.email")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="email",
        label="Email",
        emoji="\U00002709",  # envelope
        supports_media=True,
        supports_inbound=True,
        text_chunk_limit=50000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="",
    )

    def __init__(self):
        self.smtp_host: str = ""
        self.smtp_port: int = 587
        self.imap_host: str = ""
        self.imap_port: int = 993
        self.username: str = ""
        self.password: str = ""
        self.from_addr: str = ""
        self.default_to: str = ""
        self.use_tls: bool = True
        self._configured = False
        self._stop_event = threading.Event()
        self._imap_thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.smtp_host = config.get("smtp_host", "")
        self.smtp_port = int(config.get("smtp_port", 587))
        self.imap_host = config.get("imap_host", "")
        self.imap_port = int(config.get("imap_port", 993))
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.from_addr = config.get("from_addr", self.username)
        self.default_to = config.get("default_to", "")
        self.use_tls = config.get("use_tls", True)
        self._configured = bool(self.smtp_host and self.username and self.password)
        return self._configured

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        recipient = to or self.default_to
        if not recipient:
            return OutboundResult(ok=False, error="No recipient email address",
                                 channel_id=self.meta.id)
        subject = kwargs.get("title", kwargs.get("subject", "Ghost Notification"))
        msg = email.mime.text.MIMEText(text, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = recipient

        try:
            ctx = ssl.create_default_context()
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port,
                                          context=ctx, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                if self.use_tls:
                    server.starttls(context=ctx)
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, [recipient], msg.as_string())
            server.quit()
            return OutboundResult(ok=True, channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def send_media(self, to: str, media_path: str, caption: str = "",
                   **kwargs) -> OutboundResult:
        recipient = to or self.default_to
        if not recipient:
            return OutboundResult(ok=False, error="No recipient email address",
                                 channel_id=self.meta.id)
        subject = kwargs.get("title", kwargs.get("subject", "Ghost Notification"))
        msg = email.mime.multipart.MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = recipient

        if caption:
            msg.attach(email.mime.text.MIMEText(caption, "plain", "utf-8"))

        p = Path(media_path)
        if p.exists():
            with open(p, "rb") as f:
                part = email.mime.base.MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            email.encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={p.name}")
            msg.attach(part)

        try:
            ctx = ssl.create_default_context()
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port,
                                          context=ctx, timeout=15)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                if self.use_tls:
                    server.starttls(context=ctx)
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, [recipient], msg.as_string())
            server.quit()
            return OutboundResult(ok=True, channel_id=self.meta.id)
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self.imap_host or not self.username or not self.password:
            return False
        self._stop_event.clear()
        self._imap_thread = threading.Thread(
            target=self._poll_imap, args=(on_message,),
            daemon=True, name="email-imap-inbound",
        )
        self._imap_thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._imap_thread:
            self._imap_thread.join(timeout=10)
            self._imap_thread = None

    def _poll_imap(self, on_message: Callable[[InboundMessage], None]):
        """Poll IMAP for new unseen messages every 30 seconds."""
        while not self._stop_event.is_set():
            try:
                ctx = ssl.create_default_context()
                conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port,
                                         ssl_context=ctx)
                conn.login(self.username, self.password)
                conn.select("INBOX")

                _, msg_nums = conn.search(None, "UNSEEN")
                for num in msg_nums[0].split():
                    if not num:
                        continue
                    _, data = conn.fetch(num, "(RFC822)")
                    raw_email = data[0][1]
                    parsed = email.message_from_bytes(raw_email)
                    body = ""
                    if parsed.is_multipart():
                        for part in parsed.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain":
                                payload = part.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="replace")
                                break
                    else:
                        payload = parsed.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")

                    if body.strip():
                        raw_from = parsed.get("From", "unknown")
                        sender_name, sender_addr = email.utils.parseaddr(raw_from)
                        sender_id = sender_addr or raw_from
                        msg = InboundMessage(
                            channel_id="email",
                            sender_id=sender_id,
                            sender_name=sender_name or sender_id,
                            text=body.strip(),
                            timestamp=time.time(),
                            raw={"subject": parsed.get("Subject", ""),
                                 "from": raw_from},
                        )
                        on_message(msg)

                conn.logout()
            except Exception as exc:
                if not self._stop_event.is_set():
                    log.debug("IMAP poll error: %s", exc)

            for _ in range(30):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self._configured,
            "smtp_host": self.smtp_host,
            "imap_host": self.imap_host,
            "username": self.username,
            "has_password": bool(self.password),
        }
        if self._configured:
            try:
                ctx = ssl.create_default_context()
                if self.smtp_port == 465:
                    s = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port,
                                         context=ctx, timeout=5)
                else:
                    s = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5)
                    s.starttls(context=ctx)
                s.login(self.username, self.password)
                s.quit()
                status["status"] = "connected"
            except Exception as exc:
                status["status"] = "error"
                status["last_error"] = str(exc)
        else:
            status["status"] = "not configured"
        return status

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "smtp_host": {"type": "string", "required": True,
                          "description": "SMTP server hostname"},
            "smtp_port": {"type": "integer", "default": 587,
                          "description": "SMTP port (587 for STARTTLS, 465 for SSL)"},
            "imap_host": {"type": "string",
                          "description": "IMAP server hostname (for inbound)"},
            "imap_port": {"type": "integer", "default": 993,
                          "description": "IMAP SSL port"},
            "username": {"type": "string", "required": True,
                         "description": "Email login username"},
            "password": {"type": "string", "required": True, "sensitive": True,
                         "description": "Email login password or app password"},
            "from_addr": {"type": "string",
                          "description": "From address (defaults to username)"},
            "default_to": {"type": "string",
                           "description": "Default recipient email address"},
            "use_tls": {"type": "boolean", "default": True,
                        "description": "Use STARTTLS for SMTP"},
        }
