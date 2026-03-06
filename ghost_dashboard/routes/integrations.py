"""Integrations API — manage connections to Google services, Grok/X API, and Web Search."""

import logging
from flask import Blueprint, jsonify, request
import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost_integrations import (
    GoogleIntegration, GrokIntegration, 
    load_integrations_config, save_integrations_config,
    GOOGLE_SCOPES, has_ghost_google_credentials, 
    get_ghost_google_credentials, save_ghost_google_credentials
)
from ghost_web_search import get_available_providers as get_search_providers

bp = Blueprint("integrations", __name__)


def _get_feature_provider_status():
    """Get provider status for image gen, vision, and TTS features."""
    import os

    auth_store = None
    try:
        from ghost_dashboard import get_daemon
        daemon = get_daemon()
        if daemon:
            auth_store = daemon.auth_store
    except Exception:
        pass

    def _has_key(provider_id):
        if auth_store:
            try:
                key = auth_store.get_api_key(provider_id)
                if key and key != "__SETUP_PENDING__":
                    return True
            except Exception:
                pass
        from ghost_providers import get_provider
        prov = get_provider(provider_id)
        if prov and prov.env_key:
            val = os.environ.get(prov.env_key, "")
            if val and val != "__SETUP_PENDING__":
                return True
        return False

    image_gen = [
        {"name": "OpenRouter (Gemini 3 Pro)", "id": "openrouter", "available": _has_key("openrouter")},
        {"name": "Google Gemini Direct", "id": "google", "available": _has_key("google")},
        {"name": "OpenAI (gpt-image-1)", "id": "openai", "available": _has_key("openai")},
    ]

    vision = [
        {"name": "OpenAI (GPT-4o)", "id": "openai", "available": _has_key("openai")},
        {"name": "OpenRouter (GPT-4o)", "id": "openrouter", "available": _has_key("openrouter")},
        {"name": "Google Gemini", "id": "google", "available": _has_key("google")},
        {"name": "Anthropic (Claude)", "id": "anthropic", "available": _has_key("anthropic")},
        {"name": "DeepSeek", "id": "deepseek", "available": _has_key("deepseek")},
        {"name": "Ollama (local)", "id": "ollama", "available": True},
    ]

    edge_tts_available = False
    try:
        import edge_tts
        edge_tts_available = True
    except ImportError:
        pass
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY", "")
    tts = [
        {"name": "Edge TTS (free)", "id": "edge", "available": edge_tts_available},
        {"name": "OpenAI TTS", "id": "openai", "available": _has_key("openai")},
        {"name": "ElevenLabs", "id": "elevenlabs", "available": bool(elevenlabs_key)},
    ]

    return {
        "image_gen": {"providers": image_gen, "active_count": sum(1 for p in image_gen if p["available"])},
        "vision": {"providers": vision, "active_count": sum(1 for p in vision if p["available"])},
        "tts": {"providers": tts, "active_count": sum(1 for p in tts if p["available"])},
    }


@bp.route("/api/integrations")
def get_integrations():
    """Get current integrations status."""
    config = load_integrations_config()
    
    google = GoogleIntegration()
    grok = GrokIntegration()
    
    google_status = {
        "connected": google.is_connected(),
        "services": config.get("google", {}).get("services", []),
        "user": config.get("google", {}).get("user", {}),
        "client_id_configured": bool(google.client_id),
        "ghost_credentials_configured": has_ghost_google_credentials(),
    }
    
    or_fallback = False
    if not grok.is_connected():
        try:
            from ghost_integrations import _resolve_openrouter_key
            or_fallback = bool(_resolve_openrouter_key())
        except Exception:
            pass
    grok_status = {
        "connected": grok.is_connected(),
        "openrouter_fallback": or_fallback,
    }
    
    web_search_providers = get_search_providers()
    web_search_status = {
        "providers": web_search_providers,
        "active_count": sum(1 for p in web_search_providers if p["available"]),
    }

    features = _get_feature_provider_status()

    return jsonify({
        "google": google_status,
        "grok": grok_status,
        "web_search": web_search_status,
        "image_gen": features["image_gen"],
        "vision": features["vision"],
        "tts": features["tts"],
        "available_services": list(GOOGLE_SCOPES.keys()),
    })


@bp.route("/api/integrations/google/config", methods=["PUT"])
def configure_google():
    """Configure Ghost's Google OAuth app credentials (admin setup)."""
    data = request.get_json(silent=True) or {}
    
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    
    if not client_id:
        return jsonify({"error": "client_id is required"}), 400
    
    save_ghost_google_credentials(client_id, client_secret)
    
    return jsonify({"ok": True, "message": "Google OAuth credentials configured"})


@bp.route("/api/integrations/google/config", methods=["GET"])
def get_google_config():
    """Get Ghost's Google OAuth configuration status."""
    configured = has_ghost_google_credentials()
    client_id, _ = get_ghost_google_credentials()
    
    return jsonify({
        "configured": configured,
        "client_id": client_id[:10] + "..." if client_id and len(client_id) > 10 else client_id,
        "has_client_secret": bool(get_ghost_google_credentials()[1]),
    })


@bp.route("/api/integrations/google/auth")
def get_google_auth_url():
    """Get Google OAuth authorization URL."""
    services = request.args.getlist("services") or ["gmail", "calendar", "drive"]
    
    # Use dashboard URL as redirect URI
    host = request.host_url.rstrip("/")
    redirect_uri = f"{host}/api/integrations/google/callback"
    
    try:
        google = GoogleIntegration()
        result = google.get_auth_url(services, redirect_uri)
        return jsonify({
            "ok": True,
            "auth_url": result["auth_url"],
            "state": result["state"],
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/integrations/google/callback")
def google_callback():
    """Handle Google OAuth callback."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    
    if error:
        return jsonify({"error": f"OAuth error: {error}"}), 400
    
    if not code or not state:
        return jsonify({"error": "Missing code or state"}), 400
    
    try:
        google = GoogleIntegration()
        google.exchange_code(code, state)
        
        # Return HTML that closes the popup and notifies parent
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Authentication Successful</title></head>
        <body>
            <script>
                if (window.opener) {
                    window.opener.postMessage({type: 'google-auth-success'}, '*');
                }
                window.close();
            </script>
            <p>Authentication successful! You can close this window.</p>
        </body>
        </html>
        """
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/integrations/google/disconnect", methods=["POST"])
def disconnect_google():
    """Disconnect Google integration."""
    google = GoogleIntegration()
    google.disconnect()
    return jsonify({"ok": True, "message": "Google disconnected"})


@bp.route("/api/integrations/grok", methods=["PUT"])
def configure_grok():
    """Configure Grok API key."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key")
    
    if not api_key:
        return jsonify({"error": "api_key is required"}), 400
    
    grok = GrokIntegration()
    grok.save_api_key(api_key)
    
    return jsonify({"ok": True, "message": "Grok API key saved"})


@bp.route("/api/integrations/grok", methods=["DELETE"])
def disconnect_grok():
    """Remove Grok API key."""
    grok = GrokIntegration()
    grok.disconnect()
    return jsonify({"ok": True, "message": "Grok disconnected"})


@bp.route("/api/integrations/google/test/<service>")
def test_google_service(service):
    """Test a Google service connection."""
    google = GoogleIntegration()
    
    if not google.is_connected(service):
        return jsonify({"error": f"{service} not connected"}), 400
    
    try:
        if service == "gmail":
            result = google.api_request("gmail", "users/me/profile")
            return jsonify({"ok": True, "data": result})
        
        elif service == "calendar":
            result = google.api_request("calendar", "users/me/calendarList")
            return jsonify({"ok": True, "calendars": len(result.get("items", []))})
        
        elif service == "drive":
            result = google.api_request("drive", "files", params={"pageSize": 1})
            return jsonify({"ok": True, "files": len(result.get("files", []))})
        
        elif service == "docs":
            # Docs doesn't have a simple list endpoint, just check auth
            return jsonify({"ok": True, "message": "Docs API accessible"})
        
        elif service == "sheets":
            # Sheets doesn't have a simple list endpoint, just check auth
            return jsonify({"ok": True, "message": "Sheets API accessible"})
        
        else:
            return jsonify({"error": "Unknown service"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/integrations/elevenlabs", methods=["PUT"])
def configure_elevenlabs():
    """Configure ElevenLabs API key for TTS."""
    import os
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "api_key is required"}), 400

    os.environ["ELEVENLABS_API_KEY"] = api_key

    config_file = Path.home() / ".ghost" / "config.json"
    if config_file.exists():
        try:
            import json
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            cfg["elevenlabs_api_key"] = api_key
            config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            log.warning("Failed to save ElevenLabs API key", exc_info=True)

    return jsonify({"ok": True, "message": "ElevenLabs API key saved"})


@bp.route("/api/integrations/elevenlabs", methods=["DELETE"])
def disconnect_elevenlabs():
    """Remove ElevenLabs API key."""
    import os
    os.environ.pop("ELEVENLABS_API_KEY", None)

    config_file = Path.home() / ".ghost" / "config.json"
    if config_file.exists():
        try:
            import json
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            cfg.pop("elevenlabs_api_key", None)
            config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            log.warning("Failed to remove ElevenLabs API key", exc_info=True)

    return jsonify({"ok": True, "message": "ElevenLabs disconnected"})
