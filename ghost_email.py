"""
GHOST Email Tools

Create and manage email accounts via the mail.tm REST API.
No browser automation needed — pure HTTP requests.
Accounts are persistent and can receive emails (useful for social media signups).
"""

import json
import secrets
import string
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

GHOST_HOME = Path.home() / ".ghost"
CREDENTIALS_FILE = GHOST_HOME / "credentials.json"

API_BASE = "https://api.mail.tm"
REQUEST_TIMEOUT = 15


def _random_username(length=12):
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def _random_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_sym = any(c in "!@#$%&*" for c in pwd)
        if has_upper and has_lower and has_digit and has_sym:
            return pwd


def _get_available_domain():
    resp = requests.get(
        f"{API_BASE}/domains",
        headers={"Accept": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    domains = resp.json()
    if isinstance(domains, dict) and "hydra:member" in domains:
        domains = domains["hydra:member"]
    for d in domains:
        if d.get("isActive"):
            return d["domain"]
    return None


def _load_credentials():
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_credentials(creds):
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2))


def _get_token(address, password):
    resp = requests.post(
        f"{API_BASE}/token",
        json={"address": address, "password": password},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("token")


def _find_credential(email):
    creds = _load_credentials()
    for c in creds:
        if c.get("email", "").lower() == email.lower():
            return c
        if c.get("username", "").lower() == email.lower():
            return c
    return None


def build_email_tools():
    """Build email management tools for the ghost tool registry."""

    def email_create(username: str = "", notes: str = "") -> str:
        try:
            domain = _get_available_domain()
            if not domain:
                return "ERROR: No active email domains available on mail.tm right now. Try again later."

            uname = username.strip().lower() if username else _random_username()
            address = f"{uname}@{domain}"
            password = _random_password()

            resp = requests.post(
                f"{API_BASE}/accounts",
                json={"address": address, "password": password},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 422:
                uname = _random_username()
                address = f"{uname}@{domain}"
                resp = requests.post(
                    f"{API_BASE}/accounts",
                    json={"address": address, "password": password},
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    timeout=REQUEST_TIMEOUT,
                )

            if resp.status_code not in (200, 201):
                return f"ERROR: Failed to create account. Status {resp.status_code}: {resp.text[:200]}"

            account_data = resp.json()

            token = _get_token(address, password)

            creds = _load_credentials()
            creds.append({
                "service": "mail.tm",
                "username": uname,
                "email": address,
                "password": password,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "notes": notes or "Created via mail.tm API",
                "metadata": {
                    "account_id": account_data.get("id", ""),
                    "domain": domain,
                    "token": token,
                },
            })
            _save_credentials(creds)

            return (
                f"SUCCESS: Email account created!\n"
                f"  Email:    {address}\n"
                f"  Password: {password}\n"
                f"  Domain:   {domain}\n"
                f"  Account ID: {account_data.get('id', 'N/A')}\n"
                f"Credentials saved. Use email_inbox(email='{address}') to check for messages."
            )
        except requests.RequestException as e:
            return f"ERROR: Network error creating email: {e}"
        except Exception as e:
            return f"ERROR: {e}"

    def email_inbox(email: str, limit: int = 10) -> str:
        try:
            cred = _find_credential(email)
            if not cred:
                return f"ERROR: No saved credentials for '{email}'. Create an account first with email_create."

            password = cred["password"]
            token = cred.get("metadata", {}).get("token")

            if not token:
                token = _get_token(email, password)
                cred.setdefault("metadata", {})["token"] = token
                creds = _load_credentials()
                for c in creds:
                    if c.get("email", "").lower() == email.lower():
                        c.setdefault("metadata", {})["token"] = token
                        break
                _save_credentials(creds)

            resp = requests.get(
                f"{API_BASE}/messages",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                params={"page": 1},
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 401:
                token = _get_token(email, password)
                creds = _load_credentials()
                for c in creds:
                    if c.get("email", "").lower() == email.lower():
                        c.setdefault("metadata", {})["token"] = token
                        break
                _save_credentials(creds)
                resp = requests.get(
                    f"{API_BASE}/messages",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    params={"page": 1},
                    timeout=REQUEST_TIMEOUT,
                )

            resp.raise_for_status()
            data = resp.json()
            messages = data if isinstance(data, list) else data.get("hydra:member", [])

            if not messages:
                return f"Inbox for {email}: empty (0 messages)"

            messages = messages[:limit]
            parts = [f"Inbox for {email}: {len(messages)} message(s)\n"]
            for i, msg in enumerate(messages, 1):
                sender = msg.get("from", {}).get("address", "unknown")
                subject = msg.get("subject", "(no subject)")
                date = msg.get("createdAt", "")[:19].replace("T", " ")
                msg_id = msg.get("id", "")
                seen = "read" if msg.get("seen") else "unread"
                parts.append(f"  {i}. [{seen}] From: {sender}\n     Subject: {subject}\n     Date: {date}\n     ID: {msg_id}")
            parts.append(f"\nUse email_read(email='{email}', message_id='...') to read a specific message.")
            return "\n".join(parts)

        except requests.RequestException as e:
            return f"ERROR: Network error checking inbox: {e}"
        except Exception as e:
            return f"ERROR: {e}"

    def email_read(email: str, message_id: str) -> str:
        try:
            cred = _find_credential(email)
            if not cred:
                return f"ERROR: No saved credentials for '{email}'."

            password = cred["password"]
            token = cred.get("metadata", {}).get("token")
            if not token:
                token = _get_token(email, password)

            resp = requests.get(
                f"{API_BASE}/messages/{message_id}",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 401:
                token = _get_token(email, password)
                resp = requests.get(
                    f"{API_BASE}/messages/{message_id}",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout=REQUEST_TIMEOUT,
                )

            resp.raise_for_status()
            msg = resp.json()

            sender = msg.get("from", {}).get("address", "unknown")
            subject = msg.get("subject", "(no subject)")
            date = msg.get("createdAt", "")[:19].replace("T", " ")
            text_body = msg.get("text", "")
            html_body = msg.get("html", [""])[0] if msg.get("html") else ""
            body = text_body or html_body or "(empty body)"

            if len(body) > 5000:
                body = body[:5000] + "\n...(truncated)"

            return (
                f"From:    {sender}\n"
                f"Subject: {subject}\n"
                f"Date:    {date}\n"
                f"---\n{body}"
            )
        except requests.RequestException as e:
            return f"ERROR: Network error reading message: {e}"
        except Exception as e:
            return f"ERROR: {e}"

    return [
        {
            "name": "email_create",
            "description": (
                "Create a new free email account instantly via mail.tm API. "
                "No browser needed, no verification, no captcha. "
                "Returns the email address and saves credentials automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Desired username (without @domain). Leave empty to auto-generate.",
                        "default": "",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about this account (e.g. 'for twitter signup')",
                        "default": "",
                    },
                },
                "required": [],
            },
            "execute": email_create,
        },
        {
            "name": "email_inbox",
            "description": (
                "Check the inbox of a mail.tm email account. "
                "Shows sender, subject, date, and message IDs. "
                "Use this to find verification emails after signing up for services."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The email address to check (must be a mail.tm account created with email_create)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to show",
                        "default": 10,
                    },
                },
                "required": ["email"],
            },
            "execute": email_inbox,
        },
        {
            "name": "email_read",
            "description": (
                "Read the full content of a specific email message. "
                "Use the message ID from email_inbox to read verification codes, "
                "confirmation links, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "The email address (mail.tm account)",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "The message ID from email_inbox results",
                    },
                },
                "required": ["email", "message_id"],
            },
            "execute": email_read,
        },
    ]
