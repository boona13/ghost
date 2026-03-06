"""
Grok Video Generation Extension

Generates videos from text prompts using xAI's Grok Imagine Video API.
Requires a direct xAI API key (not available via OpenRouter).

API Reference: https://docs.x.ai/docs/api-reference#video-generation
"""

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger("ghost.extensions.grok_video")

GROK_API_BASE = "https://api.x.ai/v1"
VIDEO_HISTORY_FILE = "video_history.json"
VIDEO_HISTORY_MAX = 100

_file_lock = threading.Lock()


def _atomic_write_json(path: Path, data: Any):
    """Thread-safe atomic JSON write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, str(path))
    except BaseException:
        if Path(tmp).exists():
            os.unlink(tmp)
        raise


def _load_video_history(data_dir: Path) -> List[Dict]:
    """Load video generation history from disk."""
    path = data_dir / VIDEO_HISTORY_FILE
    if not path.exists():
        return []
    try:
        with _file_lock:
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                return []
            data = json.loads(raw)
            if isinstance(data, list):
                return data[-VIDEO_HISTORY_MAX:]
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("Failed to load video history: %s", exc)
    return []


def _save_video_history(data_dir: Path, entry: Dict):
    """Append entry to video history."""
    path = data_dir / VIDEO_HISTORY_FILE
    with _file_lock:
        history = _load_video_history(data_dir)
        history.append(entry)
        history = history[-VIDEO_HISTORY_MAX:]
        _atomic_write_json(path, history)


def _generate_video(
    api_key: str,
    prompt: str,
    aspect_ratio: str = "16:9",
    n: int = 1,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Generate video using xAI Grok Imagine Video API.
    
    Args:
        api_key: Direct xAI API key
        prompt: Text description of the video to generate
        aspect_ratio: Video aspect ratio (16:9, 9:16, 1:1)
        n: Number of videos to generate (1-4)
        timeout: Request timeout in seconds
    
    Returns:
        Dict with 'success', 'videos', 'error' keys
    """
    if not api_key:
        return {"success": False, "error": "xAI API key not configured"}
    
    if not prompt or not prompt.strip():
        return {"success": False, "error": "Prompt is required"}
    
    valid_ratios = ["16:9", "9:16", "1:1"]
    if aspect_ratio not in valid_ratios:
        return {"success": False, "error": f"Invalid aspect_ratio. Use: {valid_ratios}"}
    
    n = max(1, min(n, 4))  # Clamp between 1-4
    
    url = f"{GROK_API_BASE}/video/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt.strip(),
        "aspect_ratio": aspect_ratio,
        "n": n,
    }
    
    try:
        log.info("Generating video with prompt: %s...", prompt[:60])
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        
        videos = []
        for item in data.get("data", []):
            video_info = {
                "url": item.get("url"),
                "revised_prompt": item.get("revised_prompt", prompt),
                "aspect_ratio": aspect_ratio,
            }
            videos.append(video_info)
        
        return {
            "success": True,
            "videos": videos,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }
    
    except requests.exceptions.Timeout:
        log.error("Video generation timed out after %s seconds", timeout)
        return {"success": False, "error": f"Request timed out after {timeout}s"}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        try:
            err_data = exc.response.json() if exc.response else {}
            err_msg = err_data.get("error", {}).get("message", str(exc))
        except Exception:
            err_msg = str(exc)
        log.error("HTTP error %s: %s", status, err_msg)
        return {"success": False, "error": f"HTTP {status}: {err_msg}"}
    except requests.exceptions.RequestException as exc:
        log.error("Request error: %s", exc)
        return {"success": False, "error": f"Request failed: {str(exc)}"}
    except Exception as exc:
        log.error("Unexpected error: %s", exc)
        return {"success": False, "error": f"Unexpected error: {str(exc)}"}


def _build_grok_video_tool(api, data_dir: Path):
    """Build the grok_video tool definition."""
    
    def _execute(prompt: str, aspect_ratio: str = "16:9", n: int = 1, **kwargs):
        # Get API key from extension settings
        api_key = api.get_setting("xai_api_key", "")
        
        if not api_key:
            return {
                "success": False,
                "error": "xAI API key not configured. Set it in the Grok Video dashboard page.",
            }
        
        result = _generate_video(
            api_key=api_key,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            n=n,
        )
        
        # Save to history
        history_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n,
            "success": result.get("success", False),
            "videos": result.get("videos", []),
            "error": result.get("error"),
        }
        _save_video_history(data_dir, history_entry)
        
        # Format response
        if result.get("success"):
            videos = result.get("videos", [])
            if videos:
                urls = [v.get("url") for v in videos if v.get("url")]
                return {
                    "success": True,
                    "message": f"Generated {len(videos)} video(s)",
                    "videos": videos,
                    "urls": urls,
                }
            return {"success": True, "message": "Video generation completed but no URLs returned"}
        
        return result
    
    return {
        "name": "grok_video",
        "description": "Generate videos from text prompts using xAI's Grok Imagine Video API. Requires direct xAI API key (not available via OpenRouter).",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the video to generate. Be detailed and descriptive.",
                },
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio of the generated video",
                    "enum": ["16:9", "9:16", "1:1"],
                    "default": "16:9",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of videos to generate (1-4)",
                    "minimum": 1,
                    "maximum": 4,
                    "default": 1,
                },
            },
            "required": ["prompt"],
        },
        "execute": _execute,
    }


def register(api):
    """Register the Grok Video extension."""
    log.info("Registering Grok Video extension")
    
    data_dir = api.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Register settings
    api.register_setting({
        "key": "xai_api_key",
        "type": "string",
        "default": "",
        "label": "xAI API Key",
        "description": "Your direct xAI API key (get from https://console.x.ai). Not available via OpenRouter.",
    })
    
    # Register the tool
    tool = _build_grok_video_tool(api, data_dir)
    api.register_tool(tool)
    log.info("Registered grok_video tool")
    
    # Register hook to log on boot
    def on_boot():
        api_key = api.get_setting("xai_api_key", "")
        if api_key:
            masked = api_key[:8] + "..." if len(api_key) > 12 else "***"
            api.log(f"Grok Video extension ready (API key: {masked})")
        else:
            api.log("Grok Video extension loaded (no API key configured)")
    
    api.register_hook("on_boot", on_boot)
    
    # Register routes
    bp = _build_routes(api, data_dir)
    api.register_route(bp)
    
    log.info("Grok Video extension registered successfully")


# ── Flask Routes for Dashboard ───────────────────────────────────────────────

def _build_routes(api, data_dir: Path):
    """Build Flask blueprint for dashboard API routes."""
    from flask import Blueprint, jsonify, request
    
    bp = Blueprint("grok_video", __name__, url_prefix="/api/grok_video")
    
    @bp.route("/settings", methods=["GET"])
    def get_settings():
        """Get current settings (API key masked)."""
        api_key = api.get_setting("xai_api_key", "")
        return jsonify({
            "xai_api_key": api_key,
            "has_key": bool(api_key),
        })
    
    @bp.route("/settings", methods=["POST"])
    def set_settings():
        """Save API key."""
        data = request.get_json() or {}
        if "xai_api_key" in data:
            api.set_setting("xai_api_key", data["xai_api_key"])
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "No API key provided"}), 400
    
    @bp.route("/test", methods=["POST"])
    def test_connection():
        """Test the xAI API connection."""
        api_key = api.get_setting("xai_api_key", "")
        if not api_key:
            return jsonify({"success": False, "error": "API key not configured"})
        
        # Test with a minimal request to check auth
        try:
            resp = requests.get(
                f"{GROK_API_BASE}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                return jsonify({"success": True})
            elif resp.status_code == 401:
                return jsonify({"success": False, "error": "Invalid API key"})
            else:
                return jsonify({"success": False, "error": f"HTTP {resp.status_code}"})
        except requests.exceptions.RequestException as exc:
            return jsonify({"success": False, "error": str(exc)})
    
    @bp.route("/generate", methods=["POST"])
    def generate():
        """Generate a video via API."""
        data = request.get_json() or {}
        prompt = data.get("prompt", "").strip()
        aspect_ratio = data.get("aspect_ratio", "16:9")
        n = data.get("n", 1)
        
        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required"}), 400
        
        api_key = api.get_setting("xai_api_key", "")
        if not api_key:
            return jsonify({"success": False, "error": "API key not configured"}), 400
        
        result = _generate_video(
            api_key=api_key,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            n=n,
        )
        
        # Save to history
        history_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n,
            "success": result.get("success", False),
            "videos": result.get("videos", []),
            "error": result.get("error"),
        }
        _save_video_history(data_dir, history_entry)
        
        return jsonify(result)
    
    @bp.route("/history", methods=["GET"])
    def get_history():
        """Get video generation history."""
        history = _load_video_history(data_dir)
        return jsonify({"history": history})
    
    @bp.route("/history", methods=["DELETE"])
    def clear_history():
        """Clear video generation history."""
        path = data_dir / VIDEO_HISTORY_FILE
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                return jsonify({"success": False, "error": str(exc)}), 500
        return jsonify({"success": True})
    
    return bp
