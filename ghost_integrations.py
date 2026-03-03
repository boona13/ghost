"""
GHOST Integrations Module

Manages connections to external APIs including:
- Google services (Gmail, Calendar, Drive, Docs, Sheets)
- Grok/X API

Handles OAuth flows, token storage, and API client initialization.
"""

import os
import json
import base64
import secrets
import hashlib
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, parse_qs

GHOST_HOME = Path.home() / ".ghost"
INTEGRATIONS_FILE = GHOST_HOME / "integrations.json"

# Ghost's Google OAuth app credentials (from environment or config)
def get_ghost_google_credentials() -> tuple[Optional[str], Optional[str]]:
    """Get Ghost's Google OAuth credentials from environment or config file.
    
    Priority:
    1. Environment variables (GHOST_GOOGLE_CLIENT_ID, GHOST_GOOGLE_CLIENT_SECRET)
    2. Config file (~/.ghost/google_oauth.json)
    3. Return None (user will need to set up credentials)
    """
    # Check environment variables first
    client_id = os.environ.get("GHOST_GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GHOST_GOOGLE_CLIENT_SECRET")
    
    if client_id:
        return client_id, client_secret
    
    # Check config file
    oauth_file = GHOST_HOME / "google_oauth.json"
    if oauth_file.exists():
        try:
            config = json.loads(oauth_file.read_text())
            return config.get("client_id"), config.get("client_secret")
        except Exception:
            pass
    
    return None, None


def save_ghost_google_credentials(client_id: str, client_secret: Optional[str] = None):
    """Save Ghost's Google OAuth credentials to config file."""
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    oauth_file = GHOST_HOME / "google_oauth.json"
    config = {"client_id": client_id}
    if client_secret:
        config["client_secret"] = client_secret
    oauth_file.write_text(json.dumps(config, indent=2))


def has_ghost_google_credentials() -> bool:
    """Check if Ghost has Google OAuth credentials configured."""
    client_id, _ = get_ghost_google_credentials()
    return bool(client_id)

# Google OAuth configuration
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REFRESH_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Google API endpoints
GOOGLE_APIS = {
    "gmail": "https://gmail.googleapis.com/gmail/v1",
    "calendar": "https://www.googleapis.com/calendar/v3",
    "drive": "https://www.googleapis.com/drive/v3",
    "docs": "https://docs.googleapis.com/v1",
    "sheets": "https://sheets.googleapis.com/v4",
}

# Grok/X API configuration
GROK_API_BASE = "https://api.x.ai/v1"

# OAuth scopes for Google services
GOOGLE_SCOPES = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ],
    "drive": [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    ],
    "docs": [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/documents.readonly",
    ],
    "sheets": [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ],
}


def load_integrations_config() -> Dict[str, Any]:
    """Load integrations configuration from file."""
    if INTEGRATIONS_FILE.exists():
        try:
            return json.loads(INTEGRATIONS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_integrations_config(config: Dict[str, Any]):
    """Save integrations configuration to file."""
    GHOST_HOME.mkdir(parents=True, exist_ok=True)
    INTEGRATIONS_FILE.write_text(json.dumps(config, indent=2))


def generate_pkce_challenge() -> tuple:
    """Generate PKCE code verifier and challenge."""
    code_verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode().rstrip("=")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    return code_verifier, code_challenge


class GoogleIntegration:
    """Manages Google OAuth and API access."""
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.config = load_integrations_config()
        
        # Use provided credentials, or Ghost's credentials, or user's stored credentials
        ghost_client_id, ghost_client_secret = get_ghost_google_credentials()
        
        self.client_id = client_id or ghost_client_id or self.config.get("google", {}).get("client_id")
        self.client_secret = client_secret or ghost_client_secret or self.config.get("google", {}).get("client_secret")
        self.tokens = self.config.get("google", {}).get("tokens", {})
    
    def is_connected(self, service: Optional[str] = None) -> bool:
        """Check if Google is connected (optionally check specific service)."""
        if not self.tokens or not self.tokens.get("access_token"):
            return False
        if service and service not in self.config.get("google", {}).get("services", []):
            return False
        # Check if token is expired
        expires_at = self.tokens.get("expires_at")
        if expires_at:
            if datetime.fromisoformat(expires_at) < datetime.now():
                # Try to refresh
                return self.refresh_token()
        return True
    
    def get_auth_url(self, services: List[str], redirect_uri: str) -> Dict[str, str]:
        """Generate OAuth authorization URL."""
        if not self.client_id:
            raise ValueError("Google client ID not configured")
        
        # Collect all requested scopes
        scopes = set()
        for service in services:
            scopes.update(GOOGLE_SCOPES.get(service, []))
        
        # Generate PKCE challenge
        code_verifier, code_challenge = generate_pkce_challenge()
        
        # Store state for verification
        state = secrets.token_urlsafe(32)
        
        # Build auth URL
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        
        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        
        # Store PKCE verifier temporarily
        self.config["google"] = self.config.get("google", {})
        self.config["google"]["pkce"] = {
            "code_verifier": code_verifier,
            "state": state,
            "services": services,
            "redirect_uri": redirect_uri,
        }
        save_integrations_config(self.config)
        
        return {
            "auth_url": auth_url,
            "state": state,
        }
    
    def exchange_code(self, code: str, state: str) -> bool:
        """Exchange authorization code for tokens."""
        pkce = self.config.get("google", {}).get("pkce", {})
        
        if pkce.get("state") != state:
            raise ValueError("Invalid state parameter")
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": pkce.get("redirect_uri"),
            "code_verifier": pkce.get("code_verifier"),
        }
        
        response = requests.post(GOOGLE_TOKEN_URL, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        
        # Calculate expiration
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # Get user info
        user_info = self._get_user_info(token_data["access_token"])
        
        # Store tokens
        self.config["google"] = self.config.get("google", {})
        self.config["google"]["tokens"] = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at.isoformat(),
            "token_type": token_data.get("token_type", "Bearer"),
        }
        self.config["google"]["services"] = pkce.get("services", [])
        self.config["google"]["user"] = user_info
        self.config["google"].pop("pkce", None)  # Clear PKCE data
        
        save_integrations_config(self.config)
        self.tokens = self.config["google"]["tokens"]
        
        return True
    
    def refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            return False
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        
        try:
            response = requests.post(GOOGLE_REFRESH_URL, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            self.config["google"]["tokens"]["access_token"] = token_data["access_token"]
            self.config["google"]["tokens"]["expires_at"] = expires_at.isoformat()
            self.config["google"]["tokens"]["token_type"] = token_data.get("token_type", "Bearer")
            
            save_integrations_config(self.config)
            self.tokens = self.config["google"]["tokens"]
            return True
        except Exception:
            return False
    
    def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Google."""
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(GOOGLE_USERINFO_URL, headers=headers)
        if response.ok:
            return response.json()
        return {}
    
    def get_access_token(self) -> Optional[str]:
        """Get valid access token, refreshing if necessary."""
        if not self.is_connected():
            return None
        return self.tokens.get("access_token")
    
    def disconnect(self):
        """Disconnect Google integration."""
        if "google" in self.config:
            del self.config["google"]
            save_integrations_config(self.config)
    
    def api_request(self, service: str, endpoint: str, method: str = "GET", 
                    params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """Make an API request to a Google service."""
        access_token = self.get_access_token()
        if not access_token:
            raise ValueError("Not authenticated with Google")
        
        base_url = GOOGLE_APIS.get(service)
        if not base_url:
            raise ValueError(f"Unknown service: {service}")
        
        url = f"{base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, params=params)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code == 403:
            body = response.text
            if "has not been used in project" in body or "it is disabled" in body:
                api_names = {
                    "gmail": "Gmail API",
                    "calendar": "Google Calendar API",
                    "drive": "Google Drive API",
                    "docs": "Google Docs API",
                    "sheets": "Google Sheets API",
                }
                api_label = api_names.get(service, service)
                raise ValueError(
                    f"{api_label} is not enabled in your Google Cloud project. "
                    f"Go to https://console.cloud.google.com/apis/library and search for "
                    f"'{api_label}', then click 'Enable'. Wait a minute and try again."
                )
        response.raise_for_status()
        return response.json() if response.content else {}


class GrokIntegration:
    """Manages Grok/X API access."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.config = load_integrations_config()
        self.api_key = api_key or self.config.get("grok", {}).get("api_key")
    
    def is_connected(self) -> bool:
        """Check if Grok API is configured."""
        return bool(self.api_key)
    
    def save_api_key(self, api_key: str):
        """Save Grok API key."""
        self.config["grok"] = {"api_key": api_key}
        save_integrations_config(self.config)
        self.api_key = api_key
    
    def disconnect(self):
        """Remove Grok API key."""
        if "grok" in self.config:
            del self.config["grok"]
            save_integrations_config(self.config)
            self.api_key = None
    
    def api_request(self, endpoint: str, method: str = "GET",
                    params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """Make an API request to Grok."""
        if not self.api_key:
            raise ValueError("Grok API key not configured")
        
        url = f"{GROK_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        response.raise_for_status()
        return response.json() if response.content else {}
    
    def generate_text(self, prompt: str, model: str = "grok-2-latest", 
                      max_tokens: int = 4096) -> str:
        """Generate text using Grok API."""
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        
        result = self.api_request("chat/completions", method="POST", data=data)
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")


# ═════════════════════════════════════════════════════════════════════
#  INTEGRATION TOOLS FOR GHOST
# ═════════════════════════════════════════════════════════════════════

def make_google_gmail_tool(cfg):
    """Create tool for Gmail operations."""
    
    def execute(action: str, **kwargs) -> str:
        google = GoogleIntegration()
        if not google.is_connected("gmail"):
            return "Error: Gmail not connected. Connect via Integrations page."
        
        try:
            if action == "list_messages":
                params = {"maxResults": kwargs.get("max_results", 10)}
                if "query" in kwargs:
                    params["q"] = kwargs["query"]
                if "label_ids" in kwargs:
                    labels = kwargs["label_ids"]
                    if isinstance(labels, str):
                        labels = [labels]
                    for lid in labels:
                        params.setdefault("labelIds", [])
                        params["labelIds"].append(lid)
                
                result = google.api_request("gmail", "users/me/messages", params=params)
                messages = result.get("messages", [])
                return json.dumps(messages, indent=2)
            
            elif action == "get_message":
                msg_id = kwargs.get("message_id")
                if not msg_id:
                    return "Error: 'message_id' is required for get_message."
                format_type = kwargs.get("format", "full")
                result = google.api_request("gmail", f"users/me/messages/{msg_id}", 
                                          params={"format": format_type})
                
                headers = {}
                for h in result.get("payload", {}).get("headers", []):
                    if h["name"] in ("From", "To", "Subject", "Date", "Cc", "Bcc"):
                        headers[h["name"]] = h["value"]
                snippet = result.get("snippet", "")
                body_text = ""
                payload = result.get("payload", {})
                if payload.get("body", {}).get("data"):
                    body_text = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
                else:
                    for part in payload.get("parts", []):
                        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                            body_text = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                            break
                
                return json.dumps({
                    "id": result.get("id"),
                    "threadId": result.get("threadId"),
                    "labelIds": result.get("labelIds", []),
                    "headers": headers,
                    "snippet": snippet,
                    "body": body_text[:5000] if body_text else snippet,
                }, indent=2)
            
            elif action == "send_message":
                from email.mime.text import MIMEText
                
                to = kwargs.get("to")
                if not to:
                    return "Error: 'to' is required for send_message."
                
                msg = MIMEText(kwargs.get("body", ""))
                msg["to"] = to
                msg["subject"] = kwargs.get("subject", "")
                if "cc" in kwargs:
                    msg["cc"] = kwargs["cc"]
                if "bcc" in kwargs:
                    msg["bcc"] = kwargs["bcc"]
                
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                result = google.api_request("gmail", "users/me/messages/send",
                                          method="POST", data={"raw": raw})
                return f"Message sent: {result.get('id')}"
            
            elif action == "create_draft":
                from email.mime.text import MIMEText
                
                msg = MIMEText(kwargs.get("body", ""))
                msg["to"] = kwargs.get("to", "")
                msg["subject"] = kwargs.get("subject", "")
                if "cc" in kwargs:
                    msg["cc"] = kwargs["cc"]
                
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                result = google.api_request("gmail", "users/me/drafts",
                                          method="POST", data={"message": {"raw": raw}})
                return f"Draft created: {result.get('id')}"
            
            elif action == "list_labels":
                result = google.api_request("gmail", "users/me/labels")
                labels = result.get("labels", [])
                return json.dumps([{"id": l["id"], "name": l["name"], "type": l.get("type")} for l in labels], indent=2)
            
            elif action == "modify_message":
                msg_id = kwargs.get("message_id")
                if not msg_id:
                    return "Error: 'message_id' is required for modify_message."
                body = {}
                if "add_labels" in kwargs:
                    body["addLabelIds"] = kwargs["add_labels"] if isinstance(kwargs["add_labels"], list) else [kwargs["add_labels"]]
                if "remove_labels" in kwargs:
                    body["removeLabelIds"] = kwargs["remove_labels"] if isinstance(kwargs["remove_labels"], list) else [kwargs["remove_labels"]]
                if not body:
                    return "Error: provide 'add_labels' and/or 'remove_labels'."
                result = google.api_request("gmail", f"users/me/messages/{msg_id}/modify",
                                          method="POST", data=body)
                return f"Message modified. Labels: {result.get('labelIds', [])}"
            
            elif action == "trash_message":
                msg_id = kwargs.get("message_id")
                if not msg_id:
                    return "Error: 'message_id' is required for trash_message."
                google.api_request("gmail", f"users/me/messages/{msg_id}/trash", method="POST")
                return "Message moved to trash"
            
            elif action == "search":
                query = kwargs.get("query")
                if not query:
                    return "Error: 'query' is required for search. Example: 'from:alice subject:report'"
                params = {"q": query, "maxResults": kwargs.get("max_results", 10)}
                result = google.api_request("gmail", "users/me/messages", params=params)
                return json.dumps(result.get("messages", []), indent=2)
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Gmail error: {e}"
    
    return {
        "name": "google_gmail",
        "description": "Access Gmail - list messages, read emails, send emails, manage labels",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_messages", "get_message", "send_message", "create_draft", 
                            "list_labels", "modify_message", "trash_message", "search"],
                    "description": "Gmail action to perform"
                },
                "message_id": {
                    "type": "string",
                    "description": "Message ID. Required for get_message, modify_message, trash_message."
                },
                "to": {
                    "type": "string",
                    "description": "Recipient email address. Required for send_message, optional for create_draft."
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line."
                },
                "body": {
                    "type": "string",
                    "description": "Email body text."
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients (comma-separated)."
                },
                "bcc": {
                    "type": "string",
                    "description": "BCC recipients (comma-separated)."
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query for list_messages/search. Example: 'from:alice subject:report is:unread'"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max messages to return (default: 10)."
                },
                "label_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by label IDs for list_messages. Example: ['INBOX', 'UNREAD']"
                },
                "format": {
                    "type": "string",
                    "description": "Message format for get_message: 'full', 'metadata', 'minimal', 'raw'. Default: 'full'."
                },
                "add_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to add for modify_message."
                },
                "remove_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Label IDs to remove for modify_message."
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def make_google_calendar_tool(cfg):
    """Create tool for Google Calendar operations."""
    
    def execute(action: str, **kwargs) -> str:
        google = GoogleIntegration()
        if not google.is_connected("calendar"):
            return "Error: Google Calendar not connected. Connect via Integrations page."
        
        try:
            calendar_id = kwargs.get("calendar_id", "primary")
            
            if action == "list_calendars":
                result = google.api_request("calendar", "users/me/calendarList")
                calendars = result.get("items", [])
                return json.dumps([{"id": c["id"], "summary": c["summary"], "primary": c.get("primary", False)} for c in calendars], indent=2)
            
            elif action == "list_events":
                params = {
                    "maxResults": kwargs.get("max_results", 10),
                    "singleEvents": True,
                    "orderBy": kwargs.get("order_by", "startTime"),
                }
                if "time_min" in kwargs:
                    params["timeMin"] = kwargs["time_min"]
                else:
                    params["timeMin"] = datetime.now().isoformat() + "Z"
                if "time_max" in kwargs:
                    params["timeMax"] = kwargs["time_max"]
                
                result = google.api_request("calendar", f"calendars/{calendar_id}/events", params=params)
                events = result.get("items", [])
                simplified = []
                for e in events:
                    simplified.append({
                        "id": e["id"],
                        "summary": e.get("summary", "No title"),
                        "start": e.get("start", {}),
                        "end": e.get("end", {}),
                        "location": e.get("location", ""),
                        "description": e.get("description", ""),
                        "status": e.get("status", ""),
                    })
                return json.dumps(simplified, indent=2)
            
            elif action == "create_event":
                start = kwargs.get("start")
                end = kwargs.get("end")
                if not start or not end:
                    return "Error: 'start' and 'end' are required for create_event. Example: {\"dateTime\": \"2026-03-01T10:00:00\", \"timeZone\": \"America/New_York\"}"
                event_data = {
                    "summary": kwargs.get("summary", "New Event"),
                    "start": start,
                    "end": end,
                }
                if "description" in kwargs:
                    event_data["description"] = kwargs["description"]
                if "location" in kwargs:
                    event_data["location"] = kwargs["location"]
                if "attendees" in kwargs:
                    event_data["attendees"] = kwargs["attendees"]
                
                result = google.api_request("calendar", f"calendars/{calendar_id}/events",
                                          method="POST", data=event_data)
                return f"Event created: {result.get('id')} — {result.get('htmlLink', '')}"
            
            elif action == "update_event":
                event_id = kwargs.get("event_id")
                if not event_id:
                    return "Error: 'event_id' is required for update_event."
                current = google.api_request("calendar", f"calendars/{calendar_id}/events/{event_id}")
                for field in ("summary", "description", "location", "start", "end", "attendees", "status"):
                    if field in kwargs:
                        current[field] = kwargs[field]
                result = google.api_request("calendar", f"calendars/{calendar_id}/events/{event_id}",
                                          method="PUT", data=current)
                return f"Event updated: {result.get('id')}"
            
            elif action == "get_event":
                event_id = kwargs.get("event_id")
                if not event_id:
                    return "Error: 'event_id' is required for get_event."
                result = google.api_request("calendar", f"calendars/{calendar_id}/events/{event_id}")
                return json.dumps({
                    "id": result.get("id"),
                    "summary": result.get("summary"),
                    "start": result.get("start"),
                    "end": result.get("end"),
                    "location": result.get("location", ""),
                    "description": result.get("description", ""),
                    "attendees": result.get("attendees", []),
                    "status": result.get("status"),
                    "htmlLink": result.get("htmlLink"),
                }, indent=2)
            
            elif action == "delete_event":
                event_id = kwargs.get("event_id")
                if not event_id:
                    return "Error: 'event_id' is required for delete_event."
                google.api_request("calendar", f"calendars/{calendar_id}/events/{event_id}",
                                 method="DELETE")
                return "Event deleted"
            
            elif action == "quick_add":
                text = kwargs.get("text")
                if not text:
                    return "Error: 'text' is required for quick_add. Example: 'Meeting tomorrow at 3pm'"
                result = google.api_request("calendar", f"calendars/{calendar_id}/events/quickAdd",
                                          method="POST", params={"text": text})
                return f"Event created: {result.get('id')} — {result.get('summary', '')} ({result.get('start', {}).get('dateTime', result.get('start', {}).get('date', ''))})"
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Calendar error: {e}"
    
    return {
        "name": "google_calendar",
        "description": "Access Google Calendar - list events, create events, manage calendars",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_calendars", "list_events", "get_event", "create_event",
                            "update_event", "delete_event", "quick_add"],
                    "description": "Calendar action to perform"
                },
                "calendar_id": {
                    "type": "string",
                    "description": "Calendar ID (default: 'primary'). Use 'primary' for the main calendar."
                },
                "event_id": {
                    "type": "string",
                    "description": "Event ID. Required for get_event, update_event, delete_event."
                },
                "summary": {
                    "type": "string",
                    "description": "Event title for create_event/update_event."
                },
                "start": {
                    "type": "object",
                    "description": "Start time. For timed events: {\"dateTime\": \"2026-03-01T10:00:00\", \"timeZone\": \"America/New_York\"}. For all-day: {\"date\": \"2026-03-01\"}"
                },
                "end": {
                    "type": "object",
                    "description": "End time (same format as start). Required for create_event."
                },
                "description": {
                    "type": "string",
                    "description": "Event description."
                },
                "location": {
                    "type": "string",
                    "description": "Event location."
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Attendees list, e.g. [{\"email\": \"alice@example.com\"}]"
                },
                "text": {
                    "type": "string",
                    "description": "Natural language text for quick_add. Example: 'Lunch with Bob tomorrow at noon'"
                },
                "time_min": {
                    "type": "string",
                    "description": "ISO datetime lower bound for list_events. Default: now."
                },
                "time_max": {
                    "type": "string",
                    "description": "ISO datetime upper bound for list_events."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max events to return for list_events (default: 10)."
                },
                "order_by": {
                    "type": "string",
                    "description": "Sort order for list_events: 'startTime' (default) or 'updated'."
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def make_google_drive_tool(cfg):
    """Create tool for Google Drive operations."""
    
    def execute(action: str, **kwargs) -> str:
        google = GoogleIntegration()
        if not google.is_connected("drive"):
            return "Error: Google Drive not connected. Connect via Integrations page."
        
        try:
            if action == "list_files":
                params = {
                    "pageSize": kwargs.get("page_size", 10),
                    "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
                    "orderBy": kwargs.get("order_by", "modifiedTime desc"),
                }
                if "query" in kwargs:
                    params["q"] = kwargs["query"]
                
                result = google.api_request("drive", "files", params=params)
                return json.dumps(result.get("files", []), indent=2)
            
            elif action == "search":
                query = kwargs.get("query")
                if not query:
                    return "Error: 'query' is required for search."
                params = {
                    "pageSize": kwargs.get("page_size", 10),
                    "q": f"name contains '{query}' and trashed=false",
                    "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)"
                }
                result = google.api_request("drive", "files", params=params)
                return json.dumps(result.get("files", []), indent=2)
            
            elif action == "get_file":
                file_id = kwargs.get("file_id")
                if not file_id:
                    return "Error: 'file_id' is required for get_file."
                result = google.api_request("drive", f"files/{file_id}", 
                                          params={"fields": "id,name,mimeType,modifiedTime,size,webViewLink,parents"})
                return json.dumps(result, indent=2)
            
            elif action == "download_file":
                file_id = kwargs.get("file_id")
                if not file_id:
                    return "Error: 'file_id' is required for download_file."
                meta = google.api_request("drive", f"files/{file_id}", params={"fields": "mimeType,name"})
                mime = meta.get("mimeType", "")
                
                export_map = {
                    "application/vnd.google-apps.document": ("text/plain", ".txt"),
                    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
                    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
                }
                
                access_token = google.get_access_token()
                headers = {"Authorization": f"Bearer {access_token}"}
                
                if mime in export_map:
                    export_mime, _ = export_map[mime]
                    url = f"{GOOGLE_APIS['drive']}/files/{file_id}/export"
                    response = requests.get(url, headers=headers, params={"mimeType": export_mime})
                else:
                    url = f"{GOOGLE_APIS['drive']}/files/{file_id}"
                    response = requests.get(url, headers=headers, params={"alt": "media"})
                
                response.raise_for_status()
                content = response.text[:10000]
                return f"File: {meta.get('name')}\n\n{content}"
            
            elif action == "upload_file":
                name = kwargs.get("name")
                content = kwargs.get("content", "")
                if not name:
                    return "Error: 'name' is required for upload_file."
                mime_type = kwargs.get("mime_type", "text/plain")
                
                metadata = {"name": name, "mimeType": mime_type}
                if "folder_id" in kwargs:
                    metadata["parents"] = [kwargs["folder_id"]]
                
                access_token = google.get_access_token()
                boundary = "ghost_boundary_12345"
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: {mime_type}\r\n\r\n"
                    f"{content}\r\n"
                    f"--{boundary}--"
                )
                
                response = requests.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": f"multipart/related; boundary={boundary}",
                    },
                    data=body.encode("utf-8"),
                )
                response.raise_for_status()
                result = response.json()
                return f"File uploaded: {result.get('id')} — {result.get('name')}"
            
            elif action == "create_folder":
                metadata = {
                    "name": kwargs.get("name", "New Folder"),
                    "mimeType": "application/vnd.google-apps.folder"
                }
                if "parent_id" in kwargs:
                    metadata["parents"] = [kwargs["parent_id"]]
                
                result = google.api_request("drive", "files", method="POST", data=metadata)
                return f"Folder created: {result.get('id')}"
            
            elif action == "share_file":
                file_id = kwargs.get("file_id")
                email = kwargs.get("email")
                role = kwargs.get("role", "reader")
                if not file_id:
                    return "Error: 'file_id' is required for share_file."
                if not email:
                    return "Error: 'email' is required for share_file."
                permission = {
                    "type": "user",
                    "role": role,
                    "emailAddress": email,
                }
                result = google.api_request("drive", f"files/{file_id}/permissions",
                                          method="POST", data=permission)
                return f"Shared with {email} as {role}. Permission ID: {result.get('id')}"
            
            elif action == "delete_file":
                file_id = kwargs.get("file_id")
                if not file_id:
                    return "Error: 'file_id' is required for delete_file."
                google.api_request("drive", f"files/{file_id}", method="DELETE")
                return "File deleted"
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Drive error: {e}"
    
    return {
        "name": "google_drive",
        "description": "Access Google Drive - list/search files, upload/download files, create folders, share files",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_files", "get_file", "download_file", "upload_file",
                            "create_folder", "delete_file", "share_file", "search"],
                    "description": "Drive action to perform"
                },
                "file_id": {
                    "type": "string",
                    "description": "File/folder ID. Required for get_file, download_file, delete_file, share_file."
                },
                "name": {
                    "type": "string",
                    "description": "Filename for upload_file, or folder name for create_folder."
                },
                "content": {
                    "type": "string",
                    "description": "Text content to upload (for upload_file)."
                },
                "mime_type": {
                    "type": "string",
                    "description": "MIME type for upload_file (default: 'text/plain'). Example: 'text/csv', 'application/json'."
                },
                "folder_id": {
                    "type": "string",
                    "description": "Parent folder ID for upload_file."
                },
                "query": {
                    "type": "string",
                    "description": "For search: filename to search. For list_files: Drive API q syntax, e.g. \"mimeType='application/pdf'\"."
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)."
                },
                "order_by": {
                    "type": "string",
                    "description": "Sort order for list_files (default: 'modifiedTime desc'). Options: modifiedTime, name, createdTime."
                },
                "parent_id": {
                    "type": "string",
                    "description": "Parent folder ID for create_folder."
                },
                "email": {
                    "type": "string",
                    "description": "Email address to share with (for share_file)."
                },
                "role": {
                    "type": "string",
                    "description": "Permission role for share_file: 'reader', 'writer', or 'commenter'. Default: 'reader'."
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def make_google_docs_tool(cfg):
    """Create tool for Google Docs operations."""
    
    def _extract_doc_text(doc: dict) -> str:
        """Extract plain text from a Google Docs document resource."""
        text_parts = []
        for elem in doc.get("body", {}).get("content", []):
            para = elem.get("paragraph", {})
            for pe in para.get("elements", []):
                run = pe.get("textRun", {})
                if run.get("content"):
                    text_parts.append(run["content"])
        return "".join(text_parts)
    
    def execute(action: str, **kwargs) -> str:
        google = GoogleIntegration()
        if not google.is_connected("docs"):
            return "Error: Google Docs not connected. Connect via Integrations page."
        
        try:
            if action == "create_document":
                data = {"title": kwargs.get("title", "Untitled Document")}
                result = google.api_request("docs", "documents", method="POST", data=data)
                return f"Document created: {result.get('documentId')}"
            
            elif action == "get_document":
                doc_id = kwargs.get("document_id")
                if not doc_id:
                    return "Error: 'document_id' is required for get_document."
                result = google.api_request("docs", f"documents/{doc_id}")
                text = _extract_doc_text(result)
                return json.dumps({
                    "documentId": result.get("documentId"),
                    "title": result.get("title"),
                    "text": text[:10000],
                    "revisionId": result.get("revisionId"),
                }, indent=2)
            
            elif action == "insert_text":
                doc_id = kwargs.get("document_id")
                if not doc_id:
                    return "Error: 'document_id' is required for insert_text."
                text = kwargs.get("text", "")
                if not text:
                    return "Error: 'text' is required for insert_text."
                requests_data = {
                    "requests": [{
                        "insertText": {
                            "location": {"index": kwargs.get("index", 1)},
                            "text": text
                        }
                    }]
                }
                result = google.api_request("docs", f"documents/{doc_id}:batchUpdate",
                                          method="POST", data=requests_data)
                return "Text inserted successfully"
            
            elif action == "replace_text":
                doc_id = kwargs.get("document_id")
                if not doc_id:
                    return "Error: 'document_id' is required for replace_text."
                old_text = kwargs.get("old_text", "")
                new_text = kwargs.get("new_text", "")
                if not old_text:
                    return "Error: 'old_text' is required for replace_text."
                requests_data = {
                    "requests": [{
                        "replaceAllText": {
                            "containsText": {"text": old_text, "matchCase": True},
                            "replaceText": new_text
                        }
                    }]
                }
                result = google.api_request("docs", f"documents/{doc_id}:batchUpdate",
                                          method="POST", data=requests_data)
                replies = result.get("replies", [{}])
                count = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0) if replies else 0
                return f"Replaced {count} occurrence(s)"
            
            elif action == "update_document":
                doc_id = kwargs.get("document_id")
                if not doc_id:
                    return "Error: 'document_id' is required for update_document."
                doc_requests = kwargs.get("requests")
                if not doc_requests:
                    return "Error: 'requests' is required for update_document. It must be a list of Docs API request objects."
                requests_data = {"requests": doc_requests}
                result = google.api_request("docs", f"documents/{doc_id}:batchUpdate",
                                          method="POST", data=requests_data)
                return f"Document updated. {len(result.get('replies', []))} operation(s) applied."
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Docs error: {e}"
    
    return {
        "name": "google_docs",
        "description": "Access Google Docs - create documents, read content, insert/replace/update text",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_document", "get_document", "update_document", 
                            "insert_text", "replace_text"],
                    "description": "Docs action to perform"
                },
                "document_id": {
                    "type": "string",
                    "description": "The document ID (from the URL: docs.google.com/document/d/{ID}/edit). Required for all actions except create_document."
                },
                "title": {
                    "type": "string",
                    "description": "Title for create_document."
                },
                "text": {
                    "type": "string",
                    "description": "Text to insert (for insert_text)."
                },
                "index": {
                    "type": "integer",
                    "description": "Character index for insert_text (default: 1 = start of document body)."
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to find and replace (for replace_text). Case-sensitive."
                },
                "new_text": {
                    "type": "string",
                    "description": "Replacement text (for replace_text). Use empty string to delete."
                },
                "requests": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Raw Docs API batchUpdate requests (for update_document). Advanced usage for formatting, tables, etc."
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def make_google_sheets_tool(cfg):
    """Create tool for Google Sheets operations."""
    
    def execute(action: str, **kwargs) -> str:
        google = GoogleIntegration()
        if not google.is_connected("sheets"):
            return "Error: Google Sheets not connected. Connect via Integrations page."
        
        try:
            if action == "create_spreadsheet":
                title = kwargs.get("title", "Untitled Spreadsheet")
                data = {"properties": {"title": title}}
                if "sheet_titles" in kwargs:
                    data["sheets"] = [{"properties": {"title": t}} for t in kwargs["sheet_titles"]]
                result = google.api_request("sheets", "spreadsheets", method="POST", data=data)
                sid = result.get("spreadsheetId")
                return f"Spreadsheet created: {sid}\nURL: https://docs.google.com/spreadsheets/d/{sid}/edit"
            
            elif action == "get_values":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                range_name = kwargs.get("range")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for get_values."
                if not range_name:
                    return "Error: 'range' is required for get_values. Example: 'Sheet1!A1:D10' or 'Sheet1'"
                result = google.api_request("sheets", f"spreadsheets/{spreadsheet_id}/values/{range_name}")
                values = result.get("values", [])
                return json.dumps({"range": result.get("range"), "values": values}, indent=2)
            
            elif action == "update_values":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                range_name = kwargs.get("range")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for update_values."
                if not range_name:
                    return "Error: 'range' is required for update_values. Example: 'Sheet1!A1:D10'"
                values = kwargs.get("values", [])
                if not values:
                    return "Error: 'values' is required for update_values. Example: [[\"Name\",\"Age\"],[\"Alice\",\"30\"]]"
                data = {"range": range_name, "majorDimension": "ROWS", "values": values}
                result = google.api_request("sheets", f"spreadsheets/{spreadsheet_id}/values/{range_name}",
                                          method="PUT", data=data,
                                          params={"valueInputOption": "USER_ENTERED"})
                return f"Updated {result.get('updatedCells')} cells in {result.get('updatedRange')}"
            
            elif action == "append_values":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                range_name = kwargs.get("range")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for append_values."
                if not range_name:
                    return "Error: 'range' is required for append_values. Example: 'Sheet1!A1:D10'"
                values = kwargs.get("values", [])
                if not values:
                    return "Error: 'values' is required for append_values."
                data = {"range": range_name, "majorDimension": "ROWS", "values": values}
                result = google.api_request("sheets", f"spreadsheets/{spreadsheet_id}/values/{range_name}:append",
                                          method="POST", data=data,
                                          params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"})
                updates = result.get("updates", {})
                return f"Appended {updates.get('updatedRows', 0)} rows to {updates.get('updatedRange', range_name)}"
            
            elif action == "clear_values":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                range_name = kwargs.get("range")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for clear_values."
                if not range_name:
                    return "Error: 'range' is required for clear_values. Example: 'Sheet1!A1:D10'"
                google.api_request("sheets", f"spreadsheets/{spreadsheet_id}/values/{range_name}:clear",
                                  method="POST", data={})
                return f"Cleared range: {range_name}"
            
            elif action == "add_sheet":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                title = kwargs.get("title", "New Sheet")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for add_sheet."
                data = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
                result = google.api_request("sheets", f"spreadsheets/{spreadsheet_id}:batchUpdate",
                                          method="POST", data=data)
                new_id = result.get("replies", [{}])[0].get("addSheet", {}).get("properties", {}).get("sheetId")
                return f"Added sheet '{title}' (sheetId: {new_id})"
            
            elif action == "get_spreadsheet":
                spreadsheet_id = kwargs.get("spreadsheet_id")
                if not spreadsheet_id:
                    return "Error: 'spreadsheet_id' is required for get_spreadsheet."
                result = google.api_request("sheets", f"spreadsheets/{spreadsheet_id}",
                                          params={"fields": "spreadsheetId,properties.title,sheets.properties"})
                sheets = [{"title": s["properties"]["title"], "sheetId": s["properties"]["sheetId"], 
                          "rowCount": s["properties"].get("gridProperties", {}).get("rowCount"),
                          "columnCount": s["properties"].get("gridProperties", {}).get("columnCount")}
                         for s in result.get("sheets", [])]
                return json.dumps({
                    "spreadsheetId": result.get("spreadsheetId"),
                    "title": result.get("properties", {}).get("title"),
                    "sheets": sheets,
                }, indent=2)
            
            else:
                return f"Unknown action: {action}"
                
        except Exception as e:
            return f"Sheets error: {e}"
    
    return {
        "name": "google_sheets",
        "description": "Access Google Sheets - read/write cells, create spreadsheets, manage data",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_spreadsheet", "get_spreadsheet", "get_values", "update_values", 
                            "append_values", "clear_values", "add_sheet"],
                    "description": "Sheets action to perform"
                },
                "spreadsheet_id": {
                    "type": "string",
                    "description": "The spreadsheet ID (from URL: docs.google.com/spreadsheets/d/{ID}/edit). Required for all actions except create_spreadsheet."
                },
                "range": {
                    "type": "string",
                    "description": "Cell range in A1 notation. Examples: 'Sheet1!A1:D10', 'Sheet1', 'A1:C5'. Required for get/update/append/clear_values."
                },
                "title": {
                    "type": "string",
                    "description": "Title for create_spreadsheet or add_sheet."
                },
                "sheet_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sheet tab names for create_spreadsheet. Example: [\"Data\", \"Summary\"]"
                },
                "values": {
                    "type": "array",
                    "description": "2D array of cell values for update_values/append_values. Example: [[\"Name\",\"Age\"],[\"Alice\",\"30\"]]",
                    "items": {"type": "array", "items": {}}
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def _resolve_openrouter_key() -> Optional[str]:
    """Resolve the OpenRouter API key from env, auth store, or config."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key and key != "__SETUP_PENDING__":
        return key
    try:
        from ghost_auth_profiles import get_auth_store
        store = get_auth_store()
        key = store.get_api_key("openrouter")
        if key and key != "__SETUP_PENDING__":
            return key
    except Exception:
        pass
    try:
        cfg_file = GHOST_HOME / "config.json"
        if cfg_file.exists():
            data = json.loads(cfg_file.read_text())
            k = data.get("api_key", "")
            if k and k != "__SETUP_PENDING__":
                return k
    except Exception:
        pass
    return None


def _get_grok_openrouter_model(cfg: Dict) -> str:
    """Resolve the Grok model ID for OpenRouter from config."""
    try:
        from ghost_config_tool import get_tool_model
        return get_tool_model("grok_openrouter", cfg)
    except ImportError:
        return cfg.get("tool_models", {}).get("grok_openrouter", "x-ai/grok-4-fast")


def make_grok_tool(cfg):
    """Create tool for Grok/X AI operations.

    Tries the direct xAI API first.  If no xAI key is configured, falls
    back to routing through OpenRouter (which hosts Grok models).  The
    OpenRouter model is configurable via ``tool_models.grok_openrouter``
    in the Ghost config (default: ``x-ai/grok-4-fast``).

    Capabilities:
      - generate / create_content  (text, works via OpenRouter fallback)
      - analyze_image              (vision, works via OpenRouter fallback)
      - web_search / x_search      (live grounded search, xAI-only)
      - generate_image / edit_image (Grok Imagine, xAI-only)
    """

    OPENROUTER_BASE = "https://openrouter.ai/api/v1"

    def _require_xai(action_name: str):
        """Return an error string if no direct xAI key, else None."""
        grok = GrokIntegration()
        if grok.is_connected():
            return None
        return (
            f"Error: '{action_name}' requires a direct xAI API key. "
            "This feature is not available via OpenRouter. "
            "Add an xAI key on the Integrations page."
        )

    def _chat_completion(messages, model, max_tokens=4096):
        """Route a chat/completions call to xAI or OpenRouter."""
        grok = GrokIntegration()
        if grok.is_connected():
            data = {"model": model, "messages": messages, "max_tokens": max_tokens}
            result = grok.api_request("chat/completions", method="POST", data=data)
            return result, "xai"

        or_key = _resolve_openrouter_key()
        if or_key:
            or_model = _get_grok_openrouter_model(cfg)
            data = {"model": or_model, "messages": messages, "max_tokens": max_tokens}
            resp = requests.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/ghost-ai",
                    "X-Title": "Ghost Grok Tool",
                },
                json=data,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json(), "openrouter"

        raise ValueError(
            "No Grok API key and no OpenRouter key available. "
            "Add an xAI key on the Integrations page, or set up OpenRouter on the Models page."
        )

    def _responses_call(user_input: str, tools: list, model: str = "grok-3-fast"):
        """Call xAI /v1/responses endpoint (xAI-only, no OpenRouter)."""
        grok = GrokIntegration()
        body = {
            "model": model,
            "input": [{"role": "user", "content": user_input}],
            "tools": tools,
        }
        url = f"{GROK_API_BASE}/responses"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {grok.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def _extract_responses_content(data: dict) -> tuple:
        """Extract text + citations from a /v1/responses result."""
        content = ""
        citations = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        content += part.get("text", "")
                    elif part.get("type") == "cite":
                        url = part.get("url", "")
                        if url:
                            citations.append(url)
        if not content:
            content = data.get("output_text", "")
        url_citations = data.get("citations", [])
        if url_citations:
            citations = url_citations
        return content, citations

    def _format_with_citations(content: str, citations: list) -> str:
        if not citations:
            return content
        lines = [content, "", "Sources:"]
        for i, url in enumerate(citations[:10], 1):
            lines.append(f"  {i}. {url}")
        return "\n".join(lines)

    # ── action handlers ─────────────────────────────────────────

    def _do_generate(kwargs):
        prompt = kwargs.get("prompt")
        if not prompt:
            return "Error: 'prompt' is required for generate."
        model = kwargs.get("model", "grok-2-latest")
        max_tokens = kwargs.get("max_tokens", 4096)
        messages = [{"role": "user", "content": prompt}]
        result, via = _chat_completion(messages, model, max_tokens)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return f"[via {via}] {content}" if via == "openrouter" else content

    def _do_create_content(kwargs):
        content_type = kwargs.get("content_type", "social_post")
        topic = kwargs.get("topic") or kwargs.get("prompt")
        if not topic:
            return "Error: 'topic' (or 'prompt') is required for create_content."
        tone = kwargs.get("tone", "witty")
        max_tokens = kwargs.get("max_tokens", 4096)

        type_instructions = {
            "social_post": "Write a compelling social media post (Twitter/X length). Include relevant hashtags.",
            "thread": "Write an engaging Twitter/X thread (5-8 tweets, numbered). Each tweet under 280 chars. Include a hook opener.",
            "blog_draft": "Write a blog post draft with a catchy title, introduction, main sections with subheadings, and conclusion.",
            "newsletter": "Write a newsletter segment: punchy subject line, brief intro, 3-5 key points with context, and a sign-off.",
            "caption": "Write a short, engaging caption for an image/video post. Include relevant emojis and hashtags.",
            "headline": "Generate 5-10 headline variations. Each should be punchy, curiosity-driving, and shareable.",
            "summary": "Write a concise, engaging summary of the topic. Highlight key points, names, dates, and significance.",
        }
        instruction = type_instructions.get(content_type, type_instructions["social_post"])
        system = (
            "You are Grok, a witty and sharp AI created by xAI. You have a distinctive voice — "
            "direct, clever, occasionally irreverent, always insightful. "
            f"Tone: {tone}. "
            f"Task: {instruction}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": topic},
        ]
        result, via = _chat_completion(messages, "grok-2-latest", max_tokens)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return f"[via {via}] {content}" if via == "openrouter" else content

    def _do_analyze_image(kwargs):
        image_url = kwargs.get("image_url")
        if not image_url:
            return "Error: 'image_url' is required for analyze_image."
        prompt = kwargs.get("prompt", "Describe this image in detail")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }]
        result, via = _chat_completion(messages, "grok-2-vision-latest", 4096)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return f"[via {via}] {content}" if via == "openrouter" else content

    def _do_web_search(kwargs):
        err = _require_xai("web_search")
        if err:
            return err
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' is required for web_search."
        tool_def = {"type": "web_search"}
        allowed = kwargs.get("allowed_domains")
        excluded = kwargs.get("excluded_domains")
        if allowed:
            tool_def["allowed_domains"] = allowed[:5]
        if excluded:
            tool_def["excluded_domains"] = excluded[:5]
        data = _responses_call(query, [tool_def])
        content, citations = _extract_responses_content(data)
        return _format_with_citations(content, citations)

    def _do_x_search(kwargs):
        err = _require_xai("x_search")
        if err:
            return err
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' is required for x_search."
        tool_def = {"type": "x_search"}
        handles = kwargs.get("allowed_x_handles")
        excluded_handles = kwargs.get("excluded_x_handles")
        from_date = kwargs.get("from_date")
        to_date = kwargs.get("to_date")
        if handles:
            tool_def["allowed_x_handles"] = handles[:10]
        if excluded_handles:
            tool_def["excluded_x_handles"] = excluded_handles[:10]
        if from_date:
            tool_def["from_date"] = from_date
        if to_date:
            tool_def["to_date"] = to_date
        data = _responses_call(query, [tool_def])
        content, citations = _extract_responses_content(data)
        return _format_with_citations(content, citations)

    def _do_generate_image(kwargs):
        err = _require_xai("generate_image")
        if err:
            return err
        prompt = kwargs.get("prompt")
        if not prompt:
            return "Error: 'prompt' is required for generate_image."
        grok = GrokIntegration()
        body = {
            "model": "grok-imagine-image",
            "prompt": prompt,
        }
        n = kwargs.get("n")
        if n and n > 1:
            body["n"] = min(int(n), 4)
        aspect = kwargs.get("aspect_ratio")
        if aspect:
            body["aspect_ratio"] = aspect
        resp = requests.post(
            f"{GROK_API_BASE}/images/generations",
            headers={
                "Authorization": f"Bearer {grok.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("data", [])
        if not images:
            return "No images generated."
        lines = [f"Generated {len(images)} image(s):"]
        for i, img in enumerate(images, 1):
            url = img.get("url", "")
            lines.append(f"  {i}. {url}")
        return "\n".join(lines)

    def _do_edit_image(kwargs):
        err = _require_xai("edit_image")
        if err:
            return err
        prompt = kwargs.get("prompt")
        image_url = kwargs.get("image_url")
        if not prompt:
            return "Error: 'prompt' is required for edit_image."
        if not image_url:
            return "Error: 'image_url' is required for edit_image."
        grok = GrokIntegration()
        body = {
            "model": "grok-imagine-image",
            "prompt": prompt,
            "image": {"url": image_url, "type": "image_url"},
        }
        aspect = kwargs.get("aspect_ratio")
        if aspect:
            body["aspect_ratio"] = aspect
        resp = requests.post(
            f"{GROK_API_BASE}/images/edits",
            headers={
                "Authorization": f"Bearer {grok.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        images = data.get("data", [])
        if not images:
            return "No images generated."
        return f"Edited image: {images[0].get('url', '')}"

    # ── dispatcher ──────────────────────────────────────────────

    ACTION_MAP = {
        "generate": _do_generate,
        "create_content": _do_create_content,
        "analyze_image": _do_analyze_image,
        "web_search": _do_web_search,
        "x_search": _do_x_search,
        "search_x": _do_x_search,  # backward compat alias
        "generate_image": _do_generate_image,
        "edit_image": _do_edit_image,
    }

    def execute(action: str, **kwargs) -> str:
        handler = ACTION_MAP.get(action)
        if not handler:
            return f"Unknown action: {action}. Available: {', '.join(ACTION_MAP)}"
        try:
            return handler(kwargs)
        except Exception as e:
            return f"Grok error ({action}): {e}"

    return {
        "name": "grok_api",
        "description": (
            "Access Grok / X AI — generate text, create content, search the web and X/Twitter "
            "with live grounding and citations, generate and edit images, analyze images. "
            "Text actions (generate, create_content, analyze_image) work via OpenRouter fallback "
            "when no xAI key is configured. Search and image actions require a direct xAI key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "generate", "create_content", "analyze_image",
                        "web_search", "x_search",
                        "generate_image", "edit_image",
                    ],
                    "description": (
                        "Action to perform. "
                        "generate: general text generation. "
                        "create_content: content creation (social posts, threads, blogs, newsletters, captions, headlines, summaries). "
                        "analyze_image: describe/analyze an image. "
                        "web_search: live web search with citations (xAI key required). "
                        "x_search: live X/Twitter search with citations and handle/date filters (xAI key required). "
                        "generate_image: create images from text prompts (xAI key required). "
                        "edit_image: edit an existing image with natural language instructions (xAI key required)."
                    ),
                },
                "prompt": {
                    "type": "string",
                    "description": "Text prompt. Used by: generate, create_content (as 'topic'), analyze_image, generate_image, edit_image.",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic for create_content. Alias for 'prompt'.",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["social_post", "thread", "blog_draft", "newsletter", "caption", "headline", "summary"],
                    "description": "Type of content to create (default: social_post). Only for create_content.",
                },
                "tone": {
                    "type": "string",
                    "description": "Tone for create_content (default: 'witty'). E.g. 'professional', 'humorous', 'serious', 'casual', 'inspirational'.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for web_search or x_search.",
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For web_search: limit results to these domains (max 5). E.g. ['bbc.com', 'reuters.com'].",
                },
                "excluded_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For web_search: exclude these domains (max 5).",
                },
                "allowed_x_handles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For x_search: only include posts from these X handles (max 10). E.g. ['elonmusk', 'xaboratory'].",
                },
                "excluded_x_handles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For x_search: exclude posts from these X handles (max 10).",
                },
                "from_date": {
                    "type": "string",
                    "description": "For x_search: start date in ISO8601 (e.g. '2026-01-01').",
                },
                "to_date": {
                    "type": "string",
                    "description": "For x_search: end date in ISO8601 (e.g. '2026-03-01').",
                },
                "image_url": {
                    "type": "string",
                    "description": "Image URL for analyze_image or edit_image.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "For generate_image/edit_image: e.g. '1:1', '16:9', '9:16', '4:3', 'auto'. Default: auto.",
                },
                "n": {
                    "type": "integer",
                    "description": "For generate_image: number of images to generate (1-4). Default: 1.",
                },
                "model": {
                    "type": "string",
                    "description": "Grok model override for generate (default: grok-2-latest). Ignored when using OpenRouter fallback.",
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max tokens for text actions (default: 4096).",
                },
            },
            "required": ["action"],
        },
        "execute": execute,
    }


def build_integration_tools(cfg: Dict[str, Any]) -> List[Dict]:
    """Build all integration tools."""
    tools = []
    
    # Only add tools if integrations are enabled
    if cfg.get("enable_integrations", True):
        tools.extend([
            make_google_gmail_tool(cfg),
            make_google_calendar_tool(cfg),
            make_google_drive_tool(cfg),
            make_google_docs_tool(cfg),
            make_google_sheets_tool(cfg),
            make_grok_tool(cfg),
        ])
    
    return tools
