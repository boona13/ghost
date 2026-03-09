"""
GHOST Multi-Provider Image Generation

Generate images via multiple providers with automatic fallback:
  1. OpenRouter (Gemini 3 Pro Image Preview) — uses existing OpenRouter key
  2. Google Gemini direct (Gemini 3 Pro Image Preview) — uses Google AI API key
  3. OpenAI direct (DALL-E 3 / gpt-image-1) — uses OpenAI API key

If the primary provider fails or isn't configured, falls through to the next.
"""

import base64
import json
import re
import time
import requests
from pathlib import Path

GHOST_HOME = Path.home() / ".ghost"
IMAGES_DIR = GHOST_HOME / "generated_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_URL = "https://api.openai.com/v1/images/generations"

REQUEST_TIMEOUT = 120


def _slugify(text, max_len=40):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]


def _save_image(image_b64: str, prompt: str, filename: str | None = None) -> tuple[str, dict]:
    """Save base64-encoded image data to disk. Returns (path, info_dict)."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    if filename:
        out_name = filename if filename.endswith(".png") else f"{filename}.png"
    else:
        slug = _slugify(prompt)
        out_name = f"{ts}-{slug}.png"

    out_path = IMAGES_DIR / out_name
    out_path.write_bytes(base64.b64decode(image_b64))
    size_kb = round(out_path.stat().st_size / 1024, 1)
    return str(out_path), {"size_kb": size_kb, "filename": out_name}


# ═════════════════════════════════════════════════════════════════════
#  PROVIDER IMPLEMENTATIONS
# ═════════════════════════════════════════════════════════════════════

def _generate_openrouter(api_key: str, prompt: str, model: str = "google/gemini-3-pro-image-preview") -> str | None:
    """Generate via OpenRouter. Returns base64 image data or None."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ghost-ai",
        "X-Title": "Ghost AI Agent",
    }
    payload = {
        "model": model,
        "modalities": ["text", "image"],
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices", [])
    if not choices:
        return None

    message = choices[0].get("message", {})
    for img in message.get("images", []):
        url = ""
        if isinstance(img, dict):
            url = img.get("image_url", {}).get("url", "") if isinstance(img.get("image_url"), dict) else ""
        if url.startswith("data:"):
            return url.split(",", 1)[1]

    content = message.get("content")
    if isinstance(content, list):
        for part in content:
            if part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    return url.split(",", 1)[1]
    return None


def _generate_gemini(api_key: str, prompt: str, model: str = "gemini-3-pro-image-preview") -> str | None:
    """Generate via Google Gemini direct API. Returns base64 image data or None."""
    endpoint = f"{GEMINI_BASE}/models/{model}:generateContent"
    resp = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData", {})
            if inline.get("data") and "image" in inline.get("mimeType", ""):
                return inline["data"]
    return None


def _generate_openai(api_key: str, prompt: str, model: str = "gpt-image-1") -> str | None:
    """Generate via OpenAI Images API (DALL-E 3 / gpt-image-1). Returns base64 data or None."""
    resp = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    for item in data.get("data", []):
        b64 = item.get("b64_json")
        if b64:
            return b64
        url = item.get("url")
        if url:
            img_resp = requests.get(url, timeout=60)
            img_resp.raise_for_status()
            return base64.b64encode(img_resp.content).decode()
    return None


# ═════════════════════════════════════════════════════════════════════
#  KEY RESOLUTION (auth_profiles → env → config)
# ═════════════════════════════════════════════════════════════════════

def _resolve_image_providers(auth_store=None, cfg=None) -> list[dict]:
    """Build ordered list of available image generation providers."""
    from ghost_config_tool import get_tool_model

    candidates = {
        "openrouter": lambda: {
            "name": "openrouter", "fn": _generate_openrouter,
            "key": _resolve_key("openrouter", auth_store, cfg),
            "model": get_tool_model("image_gen_openrouter", cfg),
        },
        "google": lambda: {
            "name": "google-gemini", "fn": _generate_gemini,
            "key": _resolve_key("google", auth_store, cfg),
            "model": get_tool_model("image_gen_gemini", cfg),
        },
        "openai": lambda: {
            "name": "openai", "fn": _generate_openai,
            "key": _resolve_key("openai", auth_store, cfg),
            "model": get_tool_model("image_gen_openai", cfg),
        },
    }

    chain = (cfg or {}).get("provider_chains", {}).get("image_gen",
             ["openrouter", "google", "openai"])

    providers = []
    seen = set()
    for pid in chain:
        if pid in candidates and pid not in seen:
            seen.add(pid)
            p = candidates[pid]()
            if p["key"]:
                providers.append(p)
    for pid, factory in candidates.items():
        if pid not in seen:
            p = factory()
            if p["key"]:
                providers.append(p)

    return providers


def _resolve_key(provider_id: str, auth_store=None, cfg=None) -> str:
    """Resolve API key from auth_store, env, or config."""
    import os

    if auth_store:
        try:
            key = auth_store.get_api_key(provider_id)
            if key and key != "__SETUP_PENDING__":
                return key
        except Exception:
            pass

    from ghost_providers import get_provider
    prov = get_provider(provider_id)
    if prov and prov.env_key:
        env_val = os.environ.get(prov.env_key, "")
        if env_val and env_val != "__SETUP_PENDING__":
            return env_val

    if provider_id == "openrouter" and cfg:
        api_key = cfg.get("api_key", "")
        if api_key and api_key != "__SETUP_PENDING__":
            return api_key

    return ""


def _generate_with_fallback(prompt: str, auth_store=None, cfg=None,
                            filename: str | None = None) -> tuple[str | None, str | dict]:
    """Try each available provider in order. Returns (path, info_or_error)."""
    providers = _resolve_image_providers(auth_store, cfg)

    if not providers:
        return None, (
            "No image generation providers available. "
            "Ghost needs at least one of: OpenRouter API key, Google AI API key, or OpenAI API key. "
            "Set one up in the Providers panel on the dashboard."
        )

    errors = []
    for p in providers:
        try:
            image_b64 = p["fn"](p["key"], prompt, model=p["model"])
            if image_b64:
                path, info = _save_image(image_b64, prompt, filename)
                info["provider"] = p["name"]
                info["model"] = p["model"]
                return path, info
            errors.append(f"{p['name']}: model returned no image")
        except Exception as e:
            errors.append(f"{p['name']}: {e}")
            continue

    return None, "All image providers failed:\n" + "\n".join(f"  - {e}" for e in errors)


# ═════════════════════════════════════════════════════════════════════
#  TOOL BUILDER
# ═════════════════════════════════════════════════════════════════════

def build_image_gen_tools(auth_store=None, cfg=None, api_key=None):
    """Build the generate_image tool with multi-provider fallback.

    Args:
        auth_store: AuthProfileStore instance (preferred — resolves keys for all providers)
        cfg: Ghost config dict
        api_key: Legacy OpenRouter API key (fallback for backward compat)
    """
    cfg = cfg or {}

    def execute(prompt, filename=None, style=None, size=None, **_extra):
        if not prompt:
            return json.dumps({"status": "error", "error": "prompt is required"})

        full_prompt = prompt
        if style:
            full_prompt = f"{prompt}. Style: {style}"
        if size and size in ("landscape", "portrait", "square"):
            aspect_hints = {
                "landscape": "Wide landscape aspect ratio (16:9)",
                "portrait": "Tall portrait aspect ratio (9:16)",
                "square": "Square aspect ratio (1:1)",
            }
            full_prompt += f". {aspect_hints[size]}"

        try:
            path, info = _generate_with_fallback(
                full_prompt, auth_store=auth_store, cfg=cfg, filename=filename,
            )
            if path is None:
                return json.dumps({"status": "error", "error": info})

            try:
                from ghost_artifacts import auto_register
                auto_register(path)
            except Exception:
                pass

            return json.dumps({
                "status": "ok",
                "path": path,
                "size_kb": info["size_kb"],
                "filename": info["filename"],
                "provider": info.get("provider", "unknown"),
                "model": info.get("model", ""),
                "hint": "Use this file path to attach the image to a tweet or show to the user.",
            })
        except requests.exceptions.HTTPError as e:
            body = e.response.text[:300] if e.response else str(e)
            return json.dumps({"status": "error", "error": f"API error: {body}"})
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)[:300]})

    available = _resolve_image_providers(auth_store, cfg)
    provider_names = ", ".join(p["name"] for p in available) if available else "none configured"

    return [
        {
            "name": "generate_image",
            "description": (
                f"Generate an image using AI (providers: {provider_names}).\n"
                "Returns a file path to the saved PNG image.\n\n"
                "Use this tool when you need to:\n"
                "- Create images for tweets (tweets with media get 2-3x more engagement)\n"
                "- Generate illustrations, diagrams, or visual content\n"
                "- Create social media graphics\n"
                "- Produce any visual asset the user requests\n\n"
                "The image is saved to ~/.ghost/generated_images/ and the path is returned.\n"
                "To attach it to a tweet, use the browser to upload the file on X's compose page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the image to generate. Be specific about subject, style, colors, composition.",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional output filename (without path). Auto-generated if not provided.",
                    },
                    "style": {
                        "type": "string",
                        "description": "Optional style hint: photorealistic, illustration, digital art, watercolor, minimalist, etc.",
                    },
                    "size": {
                        "type": "string",
                        "enum": ["landscape", "portrait", "square"],
                        "description": "Aspect ratio. Use 'landscape' for tweets, 'portrait' for stories, 'square' for profile images.",
                    },
                },
                "required": ["prompt"],
            },
            "execute": execute,
        }
    ]
