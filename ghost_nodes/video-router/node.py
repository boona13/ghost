"""
Video Router Node — smart routing between local and cloud video generation.

Picks the best backend based on quality preference, budget, and available providers.
Falls back gracefully: cloud → local if cloud unavailable/over-budget.
"""

import json
import logging

log = logging.getLogger("ghost.node.video_router")

CLOUD_PROVIDERS_PRIORITY = ["kling", "runway", "minimax", "luma", "pika", "runware"]

CLOUD_T2V_TOOLS = {
    "kling": "kling_text_to_video",
    "runway": "runway_text_to_video",
    "minimax": "minimax_text_to_video",
    "luma": "luma_text_to_video",
    "pika": "pika_text_to_video",
    "runware": "runware_text_to_video",
}

CLOUD_I2V_TOOLS = {
    "kling": "kling_image_to_video",
    "runway": "runway_image_to_video",
    "minimax": "minimax_image_to_video",
    "luma": "luma_image_to_video",
    "pika": "pika_image_to_video",
    "runware": "runware_image_to_video",
}

LOCAL_T2V_TOOL = "text_to_video"
LOCAL_I2V_TOOL = "image_to_video"


def register(api):
    cloud = api.cloud_providers
    registry = api._tool_registry

    def _find_best_cloud_provider(is_i2v=False):
        """Find the best available and within-budget cloud provider."""
        if not cloud:
            return None
        tool_map = CLOUD_I2V_TOOLS if is_i2v else CLOUD_T2V_TOOLS
        for prov_name in CLOUD_PROVIDERS_PRIORITY:
            if not cloud.is_enabled(prov_name):
                continue
            if not cloud.check_budget(prov_name):
                continue
            tool_name = tool_map.get(prov_name, "")
            if tool_name and registry.get(tool_name):
                return prov_name
        return None

    def _has_local_tool(is_i2v=False):
        tool_name = LOCAL_I2V_TOOL if is_i2v else LOCAL_T2V_TOOL
        return bool(registry.get(tool_name))

    def execute_generate_video(prompt="", image_path="", quality="auto",
                                provider="auto", duration=5,
                                aspect_ratio="16:9", resolution="auto",
                                mode="standard", negative_prompt="",
                                seed=None, filename="", **_kw):
        if not prompt and not image_path:
            return json.dumps({"status": "error", "error": "prompt or image_path is required"})

        is_i2v = bool(image_path)
        use_cloud = False
        chosen_provider = None
        reason = ""

        if provider != "auto" and provider != "local":
            if cloud and cloud.is_enabled(provider):
                if not cloud.check_budget(provider):
                    reason = f"{provider} budget exhausted, falling back"
                else:
                    tool_map = CLOUD_I2V_TOOLS if is_i2v else CLOUD_T2V_TOOLS
                    tool_name = tool_map.get(provider, "")
                    if tool_name and registry.get(tool_name):
                        use_cloud = True
                        chosen_provider = provider
                        reason = f"user requested {provider}"
                    else:
                        reason = f"{provider} tool not available, falling back"
            else:
                reason = f"{provider} not configured/enabled, falling back"

        elif provider == "local":
            reason = "user requested local"

        else:
            wants_high = quality in ("high", "best")
            wants_draft = quality in ("draft", "fast")
            wants_auto = quality in ("auto", "standard", "")

            if wants_draft:
                reason = "draft quality requested → local"
            elif wants_high:
                best = _find_best_cloud_provider(is_i2v)
                if best:
                    use_cloud = True
                    chosen_provider = best
                    reason = f"high quality → {best}"
                else:
                    reason = "high quality requested but no cloud provider available → local"
            elif wants_auto:
                needs_cloud = (
                    resolution in ("1080p", "720p")
                    or duration > 5
                    or (resolution == "auto" and quality == "")
                )
                if needs_cloud:
                    best = _find_best_cloud_provider(is_i2v)
                    if best:
                        use_cloud = True
                        chosen_provider = best
                        reason = f"auto (resolution/duration) → {best}"
                    else:
                        reason = "auto but no cloud provider → local"
                else:
                    reason = "auto (low requirements) → local"

        if use_cloud and chosen_provider:
            tool_map = CLOUD_I2V_TOOLS if is_i2v else CLOUD_T2V_TOOLS
            cloud_tool = tool_map[chosen_provider]
            api.log(f"Routing to cloud: {chosen_provider} ({reason})")

            if chosen_provider == "runware":
                ratio_to_dims = {
                    "16:9": (1280, 720), "9:16": (720, 1280), "1:1": (960, 960),
                }
                w, h = ratio_to_dims.get(aspect_ratio, (1280, 720))
                if resolution == "1080p":
                    w, h = {
                        "16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080),
                    }.get(aspect_ratio, (1920, 1080))
                params = {"prompt": prompt, "duration": duration, "width": w, "height": h}
            else:
                params = {"prompt": prompt, "duration": duration, "mode": mode}
                if aspect_ratio:
                    params["aspect_ratio"] = aspect_ratio
            if negative_prompt:
                params["negative_prompt"] = negative_prompt
            if image_path:
                params["image_path"] = image_path

            try:
                result_str = registry.execute(cloud_tool, params)
                result = json.loads(result_str) if isinstance(result_str, str) else result_str
                result["routed_to"] = chosen_provider
                result["routing_reason"] = reason
                return json.dumps(result)
            except Exception as e:
                api.log(f"Cloud provider {chosen_provider} failed: {e}. Falling back to local...")
                reason = f"{chosen_provider} failed, falling back to local"

        local_tool = LOCAL_I2V_TOOL if is_i2v else LOCAL_T2V_TOOL
        if not _has_local_tool(is_i2v):
            return json.dumps({
                "status": "error",
                "error": f"No video generation backend available. Local tool '{local_tool}' not loaded and no cloud provider configured.",
            })

        api.log(f"Routing to local video generation ({reason})")

        local_params = {"prompt": prompt}
        if image_path:
            local_params["image_path"] = image_path
        if seed is not None:
            local_params["seed"] = seed
        if filename:
            local_params["filename"] = filename

        num_frames = 81
        fps = 16
        if resolution == "1080p":
            local_params["width"] = 1920
            local_params["height"] = 1080
        elif resolution == "720p":
            local_params["width"] = 1280
            local_params["height"] = 720

        local_params["num_frames"] = num_frames
        local_params["fps"] = fps

        try:
            result_str = registry.execute(local_tool, local_params)
            result = json.loads(result_str) if isinstance(result_str, str) else result_str
            result["routed_to"] = "local"
            result["routing_reason"] = reason
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Local generation failed: {e}"})

    api.register_tool({
        "name": "generate_video",
        "description": (
            "Smart video generation — automatically picks the best backend (local or cloud). "
            "Use quality='draft' for free local generation, quality='high' for paid cloud (Kling/Runway). "
            "With quality='auto', Ghost picks based on resolution and duration needs. "
            "Supports both text-to-video and image-to-video (set image_path for I2V). "
            "Provider can be set explicitly: 'local', 'kling', 'runway', 'minimax', 'runware', or 'auto'. "
            "Use provider='runware' to access all models (Kling, Runway, Minimax, Veo, Sora) "
            "via a single Runware.ai API key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the video to generate."},
                "image_path": {"type": "string", "description": "Source image path for image-to-video (optional)."},
                "quality": {
                    "type": "string",
                    "description": "Quality tier: 'draft' (free local), 'standard', 'high' (cloud), or 'auto'. Default: auto.",
                    "enum": ["draft", "standard", "high", "best", "auto"],
                    "default": "auto",
                },
                "provider": {
                    "type": "string",
                    "description": "Force a specific provider: 'local', 'kling', 'runway', 'minimax', 'runware', or 'auto'. Default: auto.",
                    "default": "auto",
                },
                "duration": {"type": "integer", "description": "Duration in seconds (5 or 10 for cloud, ~5 for local). Default: 5.", "default": 5},
                "aspect_ratio": {
                    "type": "string",
                    "description": "Aspect ratio (cloud only). Default: 16:9.",
                    "enum": ["16:9", "9:16", "1:1"],
                    "default": "16:9",
                },
                "resolution": {
                    "type": "string",
                    "description": "Target resolution: '480p', '720p', '1080p', or 'auto'. Default: auto.",
                    "enum": ["480p", "720p", "1080p", "auto"],
                    "default": "auto",
                },
                "mode": {
                    "type": "string",
                    "description": "Cloud generation mode: 'standard' (cheaper) or 'pro' (best quality). Default: standard.",
                    "enum": ["standard", "pro"],
                    "default": "standard",
                },
                "negative_prompt": {"type": "string", "description": "Things to avoid in the video (optional)."},
                "seed": {"type": "integer", "description": "Random seed for reproducibility (local only)."},
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["prompt"],
        },
        "execute": execute_generate_video,
    })
