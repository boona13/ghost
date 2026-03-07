"""
GHOST Credential Management

Structured storage for service credentials (email accounts, social media, etc.).
Credentials are persisted in ~/.ghost/credentials.json as a JSON array.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

GHOST_HOME = Path.home() / ".ghost"
CREDENTIALS_FILE = GHOST_HOME / "credentials.json"


def _load_credentials() -> List[Dict[str, Any]]:
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_credentials(creds: List[Dict[str, Any]]):
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(json.dumps(creds, indent=2), encoding="utf-8")


def build_credential_tools() -> list:
    """Build credential management tools for the ghost tool registry."""

    def credential_save(
        service: str,
        username: str,
        password: str,
        email: str = "",
        notes: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        from ghost_audit_log import get_audit_log, AuditAction
        creds = _load_credentials()
        entry = {
            "service": service.strip().lower(),
            "username": username.strip(),
            "email": email.strip(),
            "password": password,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "notes": notes,
            "metadata": metadata or {},
        }
        creds.append(entry)
        _save_credentials(creds)
        # Audit log
        try:
            audit = get_audit_log()
            audit.log(
                action=AuditAction.CREDENTIAL_SAVE,
                resource_type="credential",
                resource_id=entry["service"],
                success=True,
                details={"username": username, "email": email},
            )
        except Exception as e:
            logging.getLogger("ghost.audit").warning("Audit log failed: %s", e)
        display_email = entry["email"] or entry["username"]
        return f"OK: credentials saved for {entry['service']} ({display_email})"

    def credential_get(service: str, show_password: bool = True) -> str:
        creds = _load_credentials()
        service_lower = service.strip().lower()
        matches = [
            c for c in creds
            if service_lower in c.get("service", "")
            or service_lower in c.get("email", "")
            or service_lower in c.get("username", "")
        ]
        if not matches:
            return f"No credentials found matching '{service}'."
        parts = []
        for c in matches:
            pwd = c["password"] if show_password else "********"
            line = (
                f"Service: {c['service']}\n"
                f"  Username: {c['username']}\n"
                f"  Email:    {c.get('email', 'N/A')}\n"
                f"  Password: {pwd}\n"
                f"  Created:  {c.get('created_at', 'unknown')}"
            )
            if c.get("notes"):
                line += f"\n  Notes:    {c['notes']}"
            parts.append(line)
        return "\n---\n".join(parts)

    def credential_list(show_password: bool = False) -> str:
        creds = _load_credentials()
        if not creds:
            return "No credentials stored yet."
        parts = []
        for i, c in enumerate(creds, 1):
            pwd = c["password"] if show_password else "********"
            parts.append(
                f"{i}. {c['service']} — {c.get('email') or c['username']} "
                f"(pwd: {pwd}, created: {c.get('created_at', '?')})"
            )
        return "\n".join(parts)

    return [
        {
            "name": "credential_save",
            "description": (
                "Save login credentials for a service (email provider, social media, etc.) "
                "to Ghost's secure credential store. Use after creating an account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name, e.g. 'mail.com', 'twitter', 'instagram'",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username or login handle",
                    },
                    "password": {
                        "type": "string",
                        "description": "Account password",
                    },
                    "email": {
                        "type": "string",
                        "description": "Full email address if applicable",
                        "default": "",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about this account",
                        "default": "",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional extra key-value data (recovery codes, security questions, etc.)",
                        "default": {},
                    },
                },
                "required": ["service", "username", "password"],
            },
            "execute": credential_save,
        },
        {
            "name": "credential_get",
            "description": (
                "Retrieve saved credentials for a service. "
                "Searches by service name, email, or username."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Service name, email, or username to search for",
                    },
                    "show_password": {
                        "type": "boolean",
                        "description": "Whether to include the password in the result",
                        "default": True,
                    },
                },
                "required": ["service"],
            },
            "execute": credential_get,
        },
        {
            "name": "credential_list",
            "description": (
                "List all saved credentials. "
                "Passwords are hidden by default — set show_password=true to reveal them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "show_password": {
                        "type": "boolean",
                        "description": "Show passwords in the listing",
                        "default": False,
                    },
                },
                "required": [],
            },
            "execute": credential_list,
        },
    ]
