"""
IRC Channel Provider

Connects to an IRC server via raw sockets (stdlib only).
Outbound: PRIVMSG.  Inbound: listen for PRIVMSG on joined channels.
"""

import socket
import time
import threading
import logging
from typing import Dict, Any, Callable, Optional

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode,
    OutboundResult, InboundMessage,
)

log = logging.getLogger("ghost.channels.irc")


class Provider(ChannelProvider):

    meta = ChannelMeta(
        id="irc",
        label="IRC",
        emoji="\U0001f4bb",  # laptop
        supports_groups=True,
        supports_inbound=True,
        text_chunk_limit=450,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="https://datatracker.ietf.org/doc/html/rfc1459",
    )

    def __init__(self):
        self.server: str = ""
        self.port: int = 6667
        self.nick: str = "GhostBot"
        self.channel: str = ""
        self.password: str = ""
        self.use_ssl: bool = False
        self._configured = False
        self._sock: Optional[socket.socket] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def configure(self, config: Dict[str, Any]) -> bool:
        self.server = config.get("server", "")
        self.port = int(config.get("port", 6667))
        self.nick = config.get("nick", "GhostBot")
        self.channel = config.get("channel", "")
        self.password = config.get("password", "")
        self.use_ssl = config.get("use_ssl", False)
        self._configured = bool(self.server and self.channel)
        return self._configured

    def _connect(self):
        import ssl as ssl_mod
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        if self.use_ssl:
            ctx = ssl_mod.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=self.server)
        sock.connect((self.server, self.port))
        if self.password:
            sock.send(f"PASS {self.password}\r\n".encode())
        sock.send(f"NICK {self.nick}\r\n".encode())
        sock.send(f"USER {self.nick} 0 * :Ghost Bot\r\n".encode())
        time.sleep(2)
        sock.send(f"JOIN {self.channel}\r\n".encode())
        self._sock = sock
        return sock

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        target = to or self.channel
        if not target:
            return OutboundResult(ok=False, error="No channel specified",
                                 channel_id=self.meta.id)
        try:
            if not self._sock:
                self._connect()
            for chunk in self.chunk_text(text):
                for line in chunk.split("\n"):
                    if line.strip():
                        self._sock.send(f"PRIVMSG {target} :{line}\r\n".encode())
            return OutboundResult(ok=True, channel_id=self.meta.id)
        except Exception as exc:
            self._sock = None
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        if not self._configured:
            return False
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen, args=(on_message,),
            daemon=True, name="irc-inbound",
        )
        self._thread.start()
        return True

    def stop_inbound(self):
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.send(b"QUIT :Ghost signing off\r\n")
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _listen(self, on_message: Callable[[InboundMessage], None]):
        while not self._stop_event.is_set():
            try:
                if not self._sock:
                    self._connect()
                self._sock.settimeout(1)
                buf = ""
                while not self._stop_event.is_set():
                    try:
                        data = self._sock.recv(4096).decode("utf-8", errors="replace")
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buf += data
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        if line.startswith("PING"):
                            self._sock.send(f"PONG {line[5:]}\r\n".encode())
                            continue
                        parts = line.split(" ", 3)
                        if len(parts) >= 4 and parts[1] == "PRIVMSG":
                            sender = parts[0].lstrip(":").split("!")[0]
                            channel = parts[2]
                            text = parts[3].lstrip(":")
                            if sender == self.nick:
                                continue
                            msg = InboundMessage(
                                channel_id="irc",
                                sender_id=sender,
                                sender_name=sender,
                                text=text,
                                thread_id=channel,
                                timestamp=time.time(),
                            )
                            on_message(msg)
            except Exception as exc:
                self._sock = None
                if not self._stop_event.is_set():
                    log.debug("IRC connection error: %s", exc)
                    time.sleep(10)

    def health_check(self) -> Dict[str, Any]:
        return {
            "configured": self._configured,
            "server": self.server,
            "channel": self.channel,
            "nick": self.nick,
            "connected": self._sock is not None,
            "status": "connected" if self._sock else ("ready" if self._configured else "not configured"),
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "server": {"type": "string", "required": True,
                       "description": "IRC server hostname"},
            "port": {"type": "integer", "default": 6667,
                     "description": "IRC server port"},
            "nick": {"type": "string", "default": "GhostBot",
                     "description": "Bot nickname"},
            "channel": {"type": "string", "required": True,
                        "description": "IRC channel to join (e.g. #ghost)"},
            "password": {"type": "string", "sensitive": True,
                         "description": "Server password (optional)"},
            "use_ssl": {"type": "boolean", "default": False,
                        "description": "Use SSL/TLS connection"},
        }
