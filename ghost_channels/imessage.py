"""
iMessage Channel Provider (macOS only)

Bidirectional iMessage channel for user ↔ Ghost communication.
Inbound: Polls ~/Library/Messages/chat.db for new messages (requires Full Disk Access).
Outbound: Sends via AppleScript to Messages.app.
Echo detection via is_from_me flag + hash-based sent cache.
"""

import platform
import subprocess
import logging
import sqlite3
import threading
import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Set
from dataclasses import dataclass

from ghost_channels import (
    ChannelProvider, ChannelMeta, DeliveryMode, OutboundResult, InboundMessage,
)

GHOST_HOME = Path.home() / ".ghost"
IMESSAGE_STATE_FILE = GHOST_HOME / "imessage_state.json"


@dataclass
class IMessageConversation:
    """Tracks a conversation thread for proper reply routing."""
    handle: str  # Phone number or Apple ID
    chat_id: Optional[str] = None
    last_message_id: Optional[str] = None
    last_message_time: float = 0.0
    is_group: bool = False
    display_name: str = ""

log = logging.getLogger("ghost.channels.imessage")


class Provider(ChannelProvider):
    """
    iMessage channel with bidirectional support.
    
    Outbound: AppleScript to Messages.app
    Inbound: Polls ~/Library/Messages/chat.db for new messages
    """

    meta = ChannelMeta(
        id="imessage",
        label="iMessage",
        emoji="📱",
        supports_media=False,
        supports_threads=True,
        supports_reactions=False,
        supports_groups=True,
        supports_inbound=True,
        supports_edit=False,
        supports_unsend=False,
        supports_polls=False,
        supports_streaming=False,
        supports_directory=False,
        supports_gateway=False,
        text_chunk_limit=20000,
        delivery_mode=DeliveryMode.DIRECT,
        docs_url="",
    )

    def __init__(self):
        self.default_recipient: str = ""
        self.allowed_senders: list = []  # empty = owner-only (auto-detected)
        self.poll_interval: float = 3.0  # seconds
        self._configured = False
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._on_message: Optional[Callable[[InboundMessage], None]] = None
        self._seen_message_ids: Set[str] = set()
        self._conversations: Dict[str, IMessageConversation] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._db_path = Path.home() / "Library" / "Messages" / "chat.db"
        self._last_check_time: float = 0.0
        self._owner_handles: Set[str] = set()

        self._load_state()

    def _load_state(self):
        """Load persistent state (seen messages, conversations)."""
        if IMESSAGE_STATE_FILE.exists():
            try:
                data = json.loads(IMESSAGE_STATE_FILE.read_text(encoding="utf-8"))
                self._seen_message_ids = set(data.get("seen_ids", []))
                self._last_check_time = data.get("last_check_time", 0.0)
                conv_data = data.get("conversations", {})
                self._conversations = {
                    k: IMessageConversation(**v) for k, v in conv_data.items()
                }
            except Exception as e:
                log.warning(f"Failed to load iMessage state: {e}")

    def _save_state(self):
        """Save persistent state."""
        try:
            GHOST_HOME.mkdir(parents=True, exist_ok=True)
            data = {
                "seen_ids": list(self._seen_message_ids),
                "last_check_time": self._last_check_time,
                "conversations": {
                    k: {
                        "handle": v.handle,
                        "chat_id": v.chat_id,
                        "last_message_id": v.last_message_id,
                        "last_message_time": v.last_message_time,
                        "is_group": v.is_group,
                        "display_name": v.display_name,
                    }
                    for k, v in self._conversations.items()
                },
            }
            IMESSAGE_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"Failed to save iMessage state: {e}")

    def configure(self, config: Dict[str, Any]) -> bool:
        self.default_recipient = config.get("default_recipient", "")
        self.poll_interval = float(config.get("poll_interval", 3.0))
        raw_allowed = config.get("allowed_senders", [])
        if isinstance(raw_allowed, str):
            raw_allowed = [s.strip() for s in raw_allowed.split(",") if s.strip()]
        self.allowed_senders = [s.lower().strip() for s in raw_allowed]

        is_mac = platform.system() == "Darwin"
        if not is_mac:
            self._configured = False
            return False

        self._configured = True

        if self._db_path.exists():
            self._detect_owner_handles()
        else:
            log.warning("Messages database not found at %s", self._db_path)
            log.warning("Grant Full Disk Access to Ghost for iMessage inbound support")

        return self._configured

    def _detect_owner_handles(self):
        """Auto-detect the owner's Apple ID handles from chat.db."""
        conn = self._get_db_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT h.id
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.is_from_me = 0
                ORDER BY m.date DESC
                LIMIT 200
            """)
            recent_senders = {row[0].lower().strip() for row in cursor.fetchall() if row[0]}

            cursor.execute("""
                SELECT DISTINCT h.id
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.is_from_me = 1
                LIMIT 50
            """)
            outgoing_handles = {row[0].lower().strip() for row in cursor.fetchall() if row[0]}

            if outgoing_handles:
                self._owner_handles = outgoing_handles
                log.debug("Auto-detected owner iMessage handles: %s",
                          ", ".join(sorted(self._owner_handles)))
        except Exception as e:
            log.debug("Failed to detect owner handles: %s", e)
        finally:
            conn.close()

    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Get a connection to the Messages database."""
        try:
            # Use URI mode with mode=ro for read-only access
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            log.error(f"Failed to connect to Messages DB: {e}")
            return None

    def _is_sender_allowed(self, sender_handle: str) -> bool:
        """Check if a sender is allowed to communicate with Ghost."""
        if not sender_handle:
            return False
        sender_lower = sender_handle.lower().strip()

        if self.allowed_senders:
            if "*" in self.allowed_senders:
                return True
            return sender_lower in self.allowed_senders

        return True

    def _is_echo(self, sender_handle: str, text: str) -> bool:
        """Check if this message is an echo of something Ghost sent."""
        msg_hash = hashlib.sha256(f"{sender_handle}:{text}".encode()).hexdigest()[:16]
        with self._lock:
            return msg_hash in self._seen_message_ids

    def _poll_messages(self):
        """Poll for new messages from the database."""
        conn = self._get_db_connection()
        if not conn:
            return
        
        try:
            cursor = conn.cursor()
            
            # Query for recent messages
            # message.date is in Apple Cocoa time (seconds since 2001-01-01)
            # We need to convert from Unix epoch
            apple_epoch_offset = 978307200  # Seconds between 1970-01-01 and 2001-01-01
            
            query = """
                SELECT 
                    m.ROWID as message_id,
                    m.text,
                    m.date,
                    m.is_from_me,
                    m.service,
                    h.id as sender_handle,
                    c.display_name as chat_name,
                    c.ROWID as chat_id,
                    c.chat_identifier as chat_identifier,
                    m.associated_message_guid,
                    m.cache_has_attachments
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE m.date > ?
                    AND m.text IS NOT NULL
                    AND length(m.text) > 0
                ORDER BY m.date ASC
            """
            
            # Convert last check time to Apple time
            apple_time = int((self._last_check_time - apple_epoch_offset) * 1e9)
            
            cursor.execute(query, (apple_time,))
            rows = cursor.fetchall()
            
            for row in rows:
                self._process_message_row(dict(row))
            
            # Update last check time
            self._last_check_time = time.time()
            self._save_state()
            
        except Exception as e:
            log.error(f"Error polling Messages DB: {e}")
        finally:
            conn.close()

    def _process_message_row(self, row: Dict[str, Any]):
        """Process a single message row from the database."""
        message_id = str(row.get("message_id", ""))
        text = row.get("text", "")
        is_from_me = bool(row.get("is_from_me", 0))
        sender_handle = row.get("sender_handle", "") or ""
        chat_id = str(row.get("chat_id", "")) if row.get("chat_id") else None
        chat_identifier = row.get("chat_identifier", "")

        if is_from_me:
            return

        if not text or not text.strip():
            return

        if not self._is_sender_allowed(sender_handle):
            log.debug("iMessage from %s blocked (not in allowed_senders)", sender_handle)
            return

        if self._is_echo(sender_handle, text):
            log.debug("Skipping echo message from %s", sender_handle)
            return

        msg_uid = f"imsg_{message_id}"

        with self._lock:
            if msg_uid in self._seen_message_ids:
                return
            self._seen_message_ids.add(msg_uid)
            if len(self._seen_message_ids) > 1000:
                self._seen_message_ids = set(list(self._seen_message_ids)[-500:])

        thread_id = chat_identifier or sender_handle

        with self._lock:
            conv_key = thread_id
            if conv_key not in self._conversations:
                self._conversations[conv_key] = IMessageConversation(
                    handle=sender_handle,
                    chat_id=chat_id,
                )
            conv = self._conversations[conv_key]
            conv.last_message_id = message_id
            conv.last_message_time = time.time()
            conv.chat_id = chat_id

        inbound = InboundMessage(
            channel_id=self.meta.id,
            sender_id=sender_handle,
            sender_name=sender_handle,
            text=text.strip(),
            thread_id=sender_handle,
            raw=dict(row),
            timestamp=time.time(),
        )

        log.info("iMessage from %s: %s", sender_handle, text[:50])

        if self._on_message:
            try:
                self._on_message(inbound)
            except Exception as e:
                log.error("Error dispatching iMessage: %s", e)

    def _poll_loop(self):
        """Main polling loop running in background thread."""
        log.info(f"iMessage inbound polling started (interval: {self.poll_interval}s)")
        
        while not self._stop_event.is_set():
            try:
                self._poll_messages()
            except Exception as e:
                log.error(f"Error in iMessage poll loop: {e}")
            
            # Wait for next poll interval
            self._stop_event.wait(self.poll_interval)
        
        log.info("iMessage inbound polling stopped")

    def start_inbound(self, on_message: Callable[[InboundMessage], None]) -> bool:
        """Start listening for incoming iMessages."""
        if platform.system() != "Darwin":
            log.error("iMessage inbound requires macOS")
            return False
        
        if not self._db_path.exists():
            log.error(f"Messages database not accessible: {self._db_path}")
            log.error("Grant Full Disk Access to Ghost in System Preferences > Security & Privacy")
            return False
        
        if self._running:
            log.warning("iMessage inbound already running")
            return True
        
        self._on_message = on_message
        self._stop_event.clear()
        self._running = True
        
        # Set initial check time to avoid processing old messages
        if self._last_check_time == 0:
            self._last_check_time = time.time()
        
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        
        return True

    def stop_inbound(self):
        """Stop listening for incoming iMessages."""
        if not self._running:
            return
        
        log.info("Stopping iMessage inbound...")
        self._stop_event.set()
        self._running = False
        
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5.0)
        
        self._save_state()

    def send_text(self, to: str, text: str, **kwargs) -> OutboundResult:
        """Send an iMessage via AppleScript."""
        if platform.system() != "Darwin":
            return OutboundResult(ok=False, error="iMessage requires macOS",
                                 channel_id=self.meta.id)

        recipient = to or self.default_recipient
        if not recipient:
            return OutboundResult(ok=False, error="No recipient — nobody to reply to.",
                                 channel_id=self.meta.id)

        msg_hash = hashlib.sha256(f"{recipient}:{text}".encode()).hexdigest()[:16]
        with self._lock:
            self._seen_message_ids.add(msg_hash)

        safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
        safe_recipient = recipient.replace('"', '\\"')

        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st account whose service type = iMessage\n'
            f'  set targetBuddy to participant "{safe_recipient}" of targetService\n'
            f'  send "{safe_text}" to targetBuddy\n'
            f'end tell'
        )

        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=10
            )

            if r.returncode == 0:
                with self._lock:
                    if recipient not in self._conversations:
                        self._conversations[recipient] = IMessageConversation(handle=recipient)
                    self._conversations[recipient].last_message_time = time.time()
                return OutboundResult(ok=True, channel_id=self.meta.id)

            return OutboundResult(
                ok=False,
                error=r.stderr.strip() or "AppleScript error",
                channel_id=self.meta.id,
            )
        except Exception as exc:
            return OutboundResult(ok=False, error=str(exc), channel_id=self.meta.id)

    def health_check(self) -> Dict[str, Any]:
        """Return provider health status."""
        is_mac = platform.system() == "Darwin"
        db_accessible = self._db_path.exists() if is_mac else False

        status_msg = "unsupported (requires macOS)"
        if is_mac:
            if db_accessible and self._configured:
                status_msg = "ready (bidirectional)"
            elif self._configured:
                status_msg = "ready (outbound only — grant Full Disk Access for inbound)"
            else:
                status_msg = "not configured"

        result: Dict[str, Any] = {
            "configured": self._configured,
            "is_macos": is_mac,
            "db_accessible": db_accessible,
            "inbound_running": self._running,
            "conversations_tracked": len(self._conversations),
            "status": status_msg,
        }
        if self._owner_handles:
            result["owner_handles"] = sorted(self._owner_handles)
        if self.allowed_senders:
            result["allowed_senders"] = self.allowed_senders
        return result

    def get_config_schema(self) -> Dict[str, Any]:
        """Return configuration schema."""
        return {
            "default_recipient": {
                "type": "string",
                "required": False,
                "description": "Your phone number or Apple ID (for dashboard Quick Send). Not needed for inbound replies.",
            },
            "allowed_senders": {
                "type": "string",
                "required": False,
                "description": "Comma-separated phone numbers/Apple IDs that can message Ghost. Leave empty to allow everyone.",
            },
            "poll_interval": {
                "type": "number",
                "required": False,
                "default": 3.0,
                "description": "Polling interval in seconds (default: 3)",
            },
        }
