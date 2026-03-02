"""Models API — multi-provider model browser, selection, and fallback chain management."""

import logging
import time
import urllib.request
import json
from flask import Blueprint, jsonify, request

import sys
from pathlib import Path

log = logging.getLogger(__name__)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ghost import load_config, save_config, DEFAULT_CONFIG
from ghost_responses_capabilities import normalize_responses_capabilities, get_responses_capabilities, get_responses_capabilities_scope
from ghost_providers import validate_model_for_provider

bp = Blueprint("models", __name__)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

_cache = {"models": [], "fetched_at": 0}
CACHE_TTL = 300


def _parse_provider(model_name):
    if ":" in model_name:
        return model_name.split(":")[0].strip()
    return ""


def _classify_tier(model_id, pricing):
    prompt_cost = float(pricing.get("prompt", "0"))
    if ":free" in model_id or prompt_cost == 0:
        return "free"
    per_m = prompt_cost * 1_000_000
    if per_m >= 3.0:
        return "premium"
    if per_m >= 0.5:
        return "standard"
    return "fast"


def _fetch_openrouter_models():
    now = time.time()
    if _cache["models"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["models"]

    try:
        req = urllib.request.Request(OPENROUTER_MODELS_URL, headers={"User-Agent": "Ghost-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        raw = data.get("data", [])
        models = []
        for m in raw:
            mid = m.get("id", "")
            name = m.get("name", mid)
            pricing = m.get("pricing", {})
            ctx = m.get("context_length", 0)
            arch = m.get("architecture", {})
            modality = arch.get("modality", "text->text")
            prompt_cost = float(pricing.get("prompt", "0"))
            completion_cost = float(pricing.get("completion", "0"))
            provider = _parse_provider(name)
            short_name = name.split(":", 1)[1].strip() if ":" in name else name

            models.append({
                "id": mid,
                "name": short_name,
                "provider": provider,
                "tier": _classify_tier(mid, pricing),
                "context_length": ctx,
                "modality": modality,
                "pricing": {
                    "prompt_per_m": round(prompt_cost * 1_000_000, 2),
                    "completion_per_m": round(completion_cost * 1_000_000, 2),
                },
                "description": (m.get("description") or "")[:200],
                "source": "openrouter",
            })

        _cache["models"] = models
        _cache["fetched_at"] = now
        return models

    except Exception:
        log.warning("Failed to fetch models from OpenRouter", exc_info=True)
        return _cache["models"] if _cache["models"] else []


def _get_provider_models(provider_id):
    """Get models for a specific direct provider."""
    from ghost_providers import get_provider
    prov = get_provider(provider_id)
    if not prov:
        return []
    return [
        {
            "id": m,
            "name": m,
            "provider": prov.name,
            "tier": "standard",
            "context_length": 0,
            "modality": "text->text",
            "pricing": {},
            "description": "",
            "source": provider_id,
        }
        for m in prov.models
    ]


@bp.route("/api/models")
def get_models():
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    cfg = daemon.cfg if daemon else load_config()
    current = cfg.get("model", DEFAULT_CONFIG["model"])

    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()
    primary = cfg.get("primary_provider", "openrouter")
    status = store.get_provider_status(primary)
    has_key = status.get("configured", False)
    masked = status.get("masked_key", "")

    all_models = _fetch_openrouter_models()

    return jsonify({
        "current": current,
        "models": all_models,
        "total": len(all_models),
        "has_api_key": has_key,
        "api_key_masked": masked,
    })


@bp.route("/api/models", methods=["PUT"])
def set_model():
    data = request.get_json(silent=True) or {}
    cfg = load_config()

    provider = (data.get("provider", "") or "").strip().lower() or "openrouter"
    model_id = data.get("model", "").strip()
    effective_model_id = ""

    if "api_key" in data and data["api_key"]:
        cfg["api_key"] = data["api_key"]

    if model_id:
        valid, normalized_or_reason = validate_model_for_provider(provider, model_id)
        if not valid:
            hint = ""
            if provider != "openrouter":
                hint = " Use provider-native model id, e.g. gemini-2.5-pro"
            return jsonify({
                "ok": False,
                "error": f"{normalized_or_reason}{hint}",
                "provider": provider,
                "model": model_id,
            }), 400

        normalized_model = normalized_or_reason
        if provider != "openrouter" and "/" in normalized_model:
            return jsonify({
                "ok": False,
                "error": "Invalid model format for direct provider. Use provider-native model id, e.g. gemini-2.5-pro",
                "provider": provider,
                "model": model_id,
            }), 400

        effective_model_id = normalized_model
        provider_models = cfg.setdefault("provider_models", {})
        provider_models[provider] = normalized_model
        full_model_id = f"{provider}:{normalized_model}" if provider != "openrouter" else normalized_model
        cfg["model"] = full_model_id

    save_config(cfg)

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        daemon.cfg.update(cfg)
        new_model = cfg.get("model")
        if new_model:
            if hasattr(daemon, 'llm'):
                daemon.llm.model = new_model
            if hasattr(daemon, 'engine'):
                daemon.engine.model = new_model

        if provider and effective_model_id and hasattr(daemon, 'engine'):
            chain = daemon._build_provider_chain(
                cfg.get("model", DEFAULT_CONFIG["model"]),
                cfg.get("fallback_models", []),
            )
            daemon.engine.fallback_chain.set_provider_chain(chain)

    return jsonify({
        "ok": True,
        "model": cfg.get("model"),
        "provider": provider,
        "provider_model": effective_model_id,
    })


# ═════════════════════════════════════════════════════════════════
#  Multi-provider endpoints
# ═════════════════════════════════════════════════════════════════

@bp.route("/api/providers")
def get_providers():
    """List all providers with their configuration status."""
    from ghost_providers import list_providers
    from ghost_auth_profiles import get_auth_store
    store = get_auth_store()
    providers = list_providers()
    cfg = load_config()
    responses_scope = get_responses_capabilities_scope()
    for p in providers:
        status = store.get_provider_status(p["id"])
        p.update(status)
        if p.get("id") in ("openai", "openai-codex"):
            p["responses_capabilities_scope"] = responses_scope
            p["responses_capabilities_ref"] = "global"
    return jsonify({"providers": providers})


@bp.route("/api/responses-capabilities")
def get_responses_caps_api():
    cfg = load_config()
    caps = get_responses_capabilities(cfg)
    return jsonify({"ok": True, "responses_capabilities": caps})


@bp.route("/api/responses-capabilities", methods=["PUT"])
def set_responses_caps_api():
    data = request.get_json(silent=True) or {}
    raw_caps = data.get("responses_capabilities", data)
    cfg = load_config()
    try:
        caps = normalize_responses_capabilities(raw_caps)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    cfg["responses_capabilities"] = caps
    save_config(cfg)

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        daemon.cfg.update(cfg)

    return jsonify({"ok": True, "responses_capabilities": caps})


@bp.route("/api/providers/<provider_id>/models")
def get_provider_models(provider_id):
    """Get available models for a specific provider."""
    if provider_id == "openrouter":
        models = _fetch_openrouter_models()
    elif provider_id == "ollama":
        models = _get_ollama_models()
    else:
        models = _get_provider_models(provider_id)
    return jsonify({"provider": provider_id, "models": models})


@bp.route("/api/providers/<provider_id>/test", methods=["POST"])
def test_provider_route(provider_id):
    """Test connection to a provider."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("api_key", "")
    if not api_key:
        from ghost_auth_profiles import get_auth_store
        store = get_auth_store()
        if provider_id == "openai-codex":
            try:
                from ghost_oauth import ensure_fresh_token
                api_key = ensure_fresh_token(store) or ""
            except Exception:
                api_key = store.get_api_key(provider_id)
        else:
            api_key = store.get_api_key(provider_id)

    from ghost_providers import test_provider_connection
    result = test_provider_connection(provider_id, api_key)
    return jsonify(result)


@bp.route("/api/fallback-chain")
def get_fallback_chain():
    """Get the current fallback chain status."""
    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, 'engine'):
        stats = daemon.engine.fallback_chain.stats
        return jsonify(stats)
    return jsonify({"chain": [], "active": ""})


@bp.route("/api/fallback-chain", methods=["PUT"])
def set_fallback_chain():
    """Update the fallback chain order."""
    data = request.get_json(silent=True) or {}
    chain = data.get("chain", [])

    if not chain:
        return jsonify({"ok": False, "error": "chain is required"}), 400

    parsed = []
    for item in chain:
        if isinstance(item, dict):
            parsed.append((item.get("provider", "openrouter"), item.get("model", "")))
        elif isinstance(item, str) and ":" in item:
            parts = item.split(":", 1)
            parsed.append((parts[0], parts[1]))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            parsed.append(tuple(item))

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon and hasattr(daemon, 'engine'):
        daemon.engine.fallback_chain.set_provider_chain(parsed)
        return jsonify({"ok": True, "chain": [f"{p}:{m}" for p, m in parsed]})

    return jsonify({"ok": False, "error": "Daemon not running"}), 503


@bp.route("/api/primary-provider", methods=["PUT"])
def set_primary_provider():
    """Set the primary LLM provider."""
    data = request.get_json(silent=True) or {}
    provider_id = data.get("provider", "").strip()

    if not provider_id:
        return jsonify({"ok": False, "error": "provider is required"}), 400

    from ghost_providers import get_provider
    if not get_provider(provider_id):
        return jsonify({"ok": False, "error": f"Unknown provider: {provider_id}"}), 400

    cfg = load_config()
    cfg["primary_provider"] = provider_id
    save_config(cfg)

    from ghost_dashboard import get_daemon
    daemon = get_daemon()
    if daemon:
        daemon.cfg["primary_provider"] = provider_id
        if hasattr(daemon, 'auth_store') and hasattr(daemon, 'engine'):
            model = cfg.get("model", DEFAULT_CONFIG["model"])
            fallback_models = cfg.get("fallback_models", [])
            new_chain = daemon._build_provider_chain(model, fallback_models)
            daemon.engine.fallback_chain.set_provider_chain(new_chain)

    return jsonify({"ok": True, "primary_provider": provider_id})


@bp.route("/api/primary-provider")
def get_primary_provider():
    """Get the current primary provider."""
    cfg = load_config()
    return jsonify({
        "primary_provider": cfg.get("primary_provider", DEFAULT_CONFIG.get("primary_provider", "openrouter")),
    })


def _get_ollama_models():
    """Fetch models from local Ollama instance."""
    try:
        import requests as req
        resp = req.get("http://localhost:11434/api/tags", timeout=5)
        if resp.ok:
            tags = resp.json().get("models", [])
            return [
                {
                    "id": m.get("name", ""),
                    "name": m.get("name", ""),
                    "provider": "Ollama",
                    "tier": "free",
                    "context_length": 0,
                    "modality": "text->text",
                    "pricing": {},
                    "description": f"Size: {m.get('size', 'unknown')}",
                    "source": "ollama",
                }
                for m in tags
            ]
    except Exception:
        pass
    return []
