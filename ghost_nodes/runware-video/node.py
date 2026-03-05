"""
Runware Video Node — unified cloud video generation via Runware.ai middleware.

Single API key gives access to multiple providers: Kling, Runway, Minimax,
Google (Veo), OpenAI (Sora), and more through one REST API.

API docs: https://runware.ai/docs/video-inference/api-reference
Auth:     https://runware.ai/docs/getting-started/how-to-connect

Request flow:
  1. POST https://api.runware.ai/v1 with [videoInference task, deliveryMethod: async]
  2. Poll with POST [getResponse task] until status is "success" or "error"
  3. Download videoURL, save via api.save_media(), track cost

Model IDs use AIR format: provider:id@version (e.g. klingai:kling-video@3-pro)
"""

import base64
import json
import logging
import time
import uuid
from pathlib import Path

log = logging.getLogger("ghost.node.runware_video")

PROVIDER = "runware"
API_URL = "https://api.runware.ai/v1"

MODEL_ALIASES = {
    "auto": "klingai:kling-video@3-pro",
    "best": "klingai:kling-video@3-pro",
    "kling-v3-pro": "klingai:kling-video@3-pro",
    "kling-v3-std": "klingai:kling-video@3-standard",
    "kling-o3-pro": "klingai:kling-video@o3-pro",
    "kling-o3-std": "klingai:kling-video@o3-standard",
    "kling-2.6-pro": "klingai:kling-video@2.6-pro",
    "runway-gen4.5": "runway:1@2",
    "runway-gen4-turbo": "runway:1@1",
    "runway-aleph": "runway:2@1",
    "veo3": "google:3@0",
    "veo3.5": "google:3@2",
    "sora2": "openai:3@2",
    "minimax-s2v": "minimax:4@1",
    "hailuo": "minimax:4@1",
    "hailuo-live": "minimax:4@2",
}

MODEL_CATALOG = [
    {
        "alias": "kling-v3-pro", "air_id": "klingai:kling-video@3-pro",
        "provider": "Kling AI", "name": "Kling V3 Pro",
        "workflows": ["T2V", "I2V"], "duration": "3-15s",
        "resolutions": ["1920x1080", "1280x720", "960x960"],
        "features": ["multi-shot", "native audio", "start/end frame"],
    },
    {
        "alias": "kling-v3-std", "air_id": "klingai:kling-video@3-standard",
        "provider": "Kling AI", "name": "Kling V3 Standard",
        "workflows": ["T2V", "I2V"], "duration": "3-15s",
        "resolutions": ["1280x720", "960x960"],
        "features": ["multi-shot", "native audio"],
    },
    {
        "alias": "kling-o3-pro", "air_id": "klingai:kling-video@o3-pro",
        "provider": "Kling AI", "name": "Kling O3 Pro",
        "workflows": ["T2V", "I2V"], "duration": "3-15s",
        "resolutions": ["1920x1080", "1280x720"],
        "features": ["reference-guided", "native audio"],
    },
    {
        "alias": "kling-o3-std", "air_id": "klingai:kling-video@o3-standard",
        "provider": "Kling AI", "name": "Kling O3 Standard",
        "workflows": ["T2V", "I2V"], "duration": "3-15s",
        "resolutions": ["1280x720"],
        "features": ["reference-guided", "native audio"],
    },
    {
        "alias": "runway-gen4.5", "air_id": "runway:1@2",
        "provider": "Runway", "name": "Runway Gen-4.5",
        "workflows": ["T2V", "I2V"], "duration": "5, 8, 10s",
        "resolutions": ["1280x720", "720x1280", "960x960"],
        "features": ["cinematic motion", "24fps"],
    },
    {
        "alias": "runway-gen4-turbo", "air_id": "runway:1@1",
        "provider": "Runway", "name": "Runway Gen-4 Turbo",
        "workflows": ["I2V"], "duration": "2-10s",
        "resolutions": ["1280x720", "720x1280", "960x960"],
        "features": ["fast generation", "image-to-video only"],
    },
    {
        "alias": "veo3", "air_id": "google:3@0",
        "provider": "Google", "name": "Google Veo 3",
        "workflows": ["T2V", "I2V"], "duration": "6, 8s",
        "resolutions": ["1280x720", "720x1280"],
        "features": ["native audio", "prompt enhancement"],
    },
    {
        "alias": "veo3.5", "air_id": "google:3@2",
        "provider": "Google", "name": "Google Veo 3.5 Flash",
        "workflows": ["T2V", "I2V"], "duration": "5-8s",
        "resolutions": ["1280x720", "720x1280"],
        "features": ["fast generation", "native audio"],
    },
    {
        "alias": "sora2", "air_id": "openai:3@2",
        "provider": "OpenAI", "name": "OpenAI Sora 2 Pro",
        "workflows": ["T2V", "I2V"], "duration": "5-20s",
        "resolutions": ["1920x1080", "1280x720"],
        "features": ["synchronized audio", "cinematic"],
    },
    {
        "alias": "minimax-s2v", "air_id": "minimax:4@1",
        "provider": "Minimax", "name": "Minimax S2V-01",
        "workflows": ["T2V", "I2V"], "duration": "2-10s",
        "resolutions": ["1280x720", "720x1280", "960x960"],
        "features": ["fast generation"],
    },
    {
        "alias": "hailuo-live", "air_id": "minimax:4@2",
        "provider": "Minimax", "name": "Minimax S2V-01 Live",
        "workflows": ["T2V", "I2V"], "duration": "2-10s",
        "resolutions": ["1280x720", "720x1280"],
        "features": ["live-action style"],
    },
]


def _resolve_model(model_input: str) -> str:
    """Resolve a user-friendly alias or pass through a raw AIR ID."""
    if not model_input:
        return MODEL_ALIASES["auto"]
    lower = model_input.lower().strip()
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    if ":" in model_input and "@" in model_input:
        return model_input
    return MODEL_ALIASES.get("auto", "klingai:kling-video@3-pro")


def _runware_post(cloud, payload_tasks: list, timeout: int = 30) -> dict:
    """POST a task array to Runware's API. Returns parsed JSON response."""
    import urllib.request
    import urllib.error

    headers = cloud.get_auth_headers(PROVIDER)
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload_tasks).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode()[:500]
        except Exception:
            pass
        raise RuntimeError(f"Runware API error HTTP {e.code}: {error_body}")


def _poll_runware(cloud, task_uuid: str, timeout: float = 600,
                  initial_delay: float = 10) -> dict:
    """Poll Runware getResponse until success, error, or timeout.

    Returns the successful data item dict with videoURL and cost.
    """
    time.sleep(initial_delay)
    start = time.time()
    interval = 5.0
    max_interval = 15.0
    last_status = ""

    while time.time() - start < timeout:
        poll_uuid = str(uuid.uuid4())
        try:
            result = _runware_post(cloud, [
                {"taskType": "getResponse", "taskUUID": poll_uuid}
            ], timeout=30)
        except RuntimeError as e:
            log.warning("Runware poll error: %s", e)
            time.sleep(interval)
            interval = min(interval * 1.3, max_interval)
            continue

        data_items = result.get("data", [])
        errors = result.get("errors", [])

        for err in errors:
            if err.get("taskUUID") == task_uuid:
                msg = err.get("message", "Unknown error")
                raise RuntimeError(f"Runware job failed: {msg}")

        for item in data_items:
            if item.get("taskUUID") != task_uuid:
                continue
            status = item.get("status", "")
            if status != last_status:
                log.info("Runware job %s status: %s", task_uuid[:8], status)
                last_status = status
            if status == "success":
                return item
            if status == "error":
                raise RuntimeError(
                    f"Runware job failed: {item.get('error', item.get('message', 'unknown'))}"
                )

        time.sleep(interval)
        interval = min(interval * 1.3, max_interval)

    raise RuntimeError(f"Runware job timed out after {timeout}s (task: {task_uuid[:8]})")


def register(api):
    cloud = api.cloud_providers
    if not cloud:
        log.warning("Cloud providers not available — runware-video node disabled")
        return

    def _check_runware():
        """Verify Runware is configured and within budget. Returns error JSON or None."""
        key = api.get_provider_key(PROVIDER)
        if not key:
            return json.dumps({
                "status": "error",
                "error": (
                    "Runware API key not configured. Get one at https://my.runware.ai/signup "
                    "then add it in Dashboard > Config > Cloud Providers, "
                    "or set RUNWARE_API_KEY env var."
                ),
            })
        if not cloud.check_budget(PROVIDER):
            remaining = cloud.get_budget_remaining(PROVIDER)
            return json.dumps({
                "status": "error",
                "error": f"Monthly Runware budget exhausted (remaining: ${remaining:.2f}).",
            })
        return None

    def execute_runware_t2v(prompt="", model="auto", duration=10,
                            width=1280, height=720, seed=None,
                            negative_prompt="", generate_audio=True,
                            output_format="MP4", **_kw):
        if not prompt:
            return json.dumps({"status": "error", "error": "prompt is required"})

        err = _check_runware()
        if err:
            return err

        air_model = _resolve_model(model)
        api.log(f"Submitting Runware T2V ({air_model}, {duration}s, {width}x{height})...")
        t0 = time.time()

        task_uuid = str(uuid.uuid4())
        task = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": air_model,
            "positivePrompt": prompt[:1000],
            "duration": duration,
            "width": width,
            "height": height,
            "deliveryMethod": "async",
            "includeCost": True,
            "outputFormat": output_format,
            "numberResults": 1,
        }
        if seed is not None:
            task["seed"] = seed
        if negative_prompt:
            task["negativePrompt"] = negative_prompt[:500]

        provider_settings = {}
        provider_key = air_model.split(":")[0] if ":" in air_model else ""
        if generate_audio and provider_key in ("klingai", "google"):
            provider_settings[provider_key] = {"generateAudio": True}
        if provider_settings:
            task["providerSettings"] = provider_settings

        try:
            result = _runware_post(cloud, [task])
        except RuntimeError as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

        errors = result.get("errors", [])
        if errors:
            msg = errors[0].get("message", "Submission failed")
            return json.dumps({"status": "error", "error": msg})

        api.log(f"Runware job submitted (task: {task_uuid[:8]}). Polling...")

        try:
            completed = _poll_runware(cloud, task_uuid, timeout=600, initial_delay=15)
        except RuntimeError as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

        return _download_and_save(api, cloud, completed, prompt, t0, air_model, duration)

    def execute_runware_i2v(prompt="", image_path="", model="auto",
                            duration=10, width=1280, height=720,
                            seed=None, generate_audio=True,
                            output_format="MP4", **_kw):
        if not image_path:
            return json.dumps({"status": "error", "error": "image_path is required"})

        err = _check_runware()
        if err:
            return err

        p = Path(image_path)
        if not p.exists():
            return json.dumps({"status": "error", "error": f"File not found: {image_path}"})
        if p.stat().st_size > 20 * 1024 * 1024:
            return json.dumps({"status": "error", "error": "Image exceeds 20MB limit"})

        image_data = p.read_bytes()
        b64 = base64.b64encode(image_data).decode("utf-8")
        suffix = p.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp"}.get(suffix, "image/jpeg")
        data_uri = f"data:{mime};base64,{b64}"

        air_model = _resolve_model(model)
        api.log(f"Submitting Runware I2V ({air_model}, {duration}s, {width}x{height})...")
        t0 = time.time()

        task_uuid = str(uuid.uuid4())
        task = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": air_model,
            "positivePrompt": (prompt or "animate this image with natural cinematic motion")[:1000],
            "duration": duration,
            "width": width,
            "height": height,
            "frameImages": [{"inputImage": data_uri, "frame": "first"}],
            "deliveryMethod": "async",
            "includeCost": True,
            "outputFormat": output_format,
            "numberResults": 1,
        }
        if seed is not None:
            task["seed"] = seed

        provider_settings = {}
        provider_key = air_model.split(":")[0] if ":" in air_model else ""
        if generate_audio and provider_key in ("klingai", "google"):
            provider_settings[provider_key] = {"generateAudio": True}
        if provider_settings:
            task["providerSettings"] = provider_settings

        try:
            result = _runware_post(cloud, [task])
        except RuntimeError as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

        errors = result.get("errors", [])
        if errors:
            msg = errors[0].get("message", "Submission failed")
            return json.dumps({"status": "error", "error": msg})

        api.log(f"Runware I2V job submitted (task: {task_uuid[:8]}). Polling...")

        try:
            completed = _poll_runware(cloud, task_uuid, timeout=600, initial_delay=15)
        except RuntimeError as e:
            return json.dumps({"status": "error", "error": str(e)[:500]})

        return _download_and_save(api, cloud, completed, prompt, t0, air_model, duration,
                                  source_image=image_path)

    def _download_and_save(api, cloud, completed_data, prompt, t0, model,
                           duration, source_image=""):
        video_url = completed_data.get("videoURL", "")
        if not video_url:
            return json.dumps({
                "status": "error",
                "error": f"No videoURL in response: {json.dumps(completed_data)[:500]}",
            })

        api.log("Downloading video from Runware...")
        try:
            video_bytes = cloud.download_file(video_url)
        except Exception as e:
            return json.dumps({"status": "error", "error": f"Download failed: {e}"})

        elapsed = time.time() - t0
        cost = completed_data.get("cost", 0.0)

        ts = time.strftime("%Y%m%d_%H%M%S")
        model_short = model.split(":")[-1].replace("@", "-") if ":" in model else model
        fname = f"runware_{model_short}_{ts}.mp4"

        params_dict = {
            "model": model, "duration": duration,
            "provider": PROVIDER, "via": "runware",
        }
        if source_image:
            params_dict["source_image"] = str(source_image)

        path = api.save_media(
            data=video_bytes,
            filename=fname,
            media_type="video",
            prompt=(prompt or "")[:200],
            params=params_dict,
            metadata={
                "provider": PROVIDER, "model": model,
                "duration_secs": duration, "cost_usd": cost,
                "elapsed_secs": round(elapsed, 2),
                "prompt": (prompt or "")[:200],
                "video_uuid": completed_data.get("videoUUID", ""),
            },
            provider=PROVIDER,
            cost_usd=cost,
        )

        cloud.track_cost(
            PROVIDER,
            "text_to_video" if not source_image else "image_to_video",
            cost,
        )
        api.log(f"Runware video saved: {fname} (${cost:.2f}, {elapsed:.1f}s)")

        return json.dumps({
            "status": "ok",
            "path": path,
            "provider": PROVIDER,
            "model": model,
            "cost_usd": cost,
            "duration_secs": duration,
            "elapsed_secs": round(elapsed, 2),
        })

    def execute_runware_list_models(**_kw):
        return json.dumps({
            "status": "ok",
            "models": MODEL_CATALOG,
            "aliases": MODEL_ALIASES,
        }, indent=2)

    all_aliases = ", ".join(
        f"'{a}'" for a in MODEL_ALIASES if a not in ("auto", "best")
    )

    api.register_tool({
        "name": "runware_text_to_video",
        "description": (
            "Generate video from text via Runware.ai (unified cloud API). "
            "Access Kling V3, Runway Gen4.5, Google Veo 3, OpenAI Sora 2, Minimax Hailuo "
            "with a single Runware API key. "
            f"Model aliases: {all_aliases}, or use raw AIR IDs. "
            "Default model: Kling V3 Pro. "
            "PAID service — costs vary by model. Requires a Runware API key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the video to generate (max 1000 chars).",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Model to use. Aliases: 'kling-v3-pro', 'runway-gen4.5', 'veo3', "
                        "'sora2', 'minimax-s2v', etc. Or use raw AIR ID like 'klingai:kling-video@3-pro'. "
                        "Default: 'auto' (Kling V3 Pro)."
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds. Range depends on model (typically 2-15s). Default: 10.",
                },
                "width": {
                    "type": "integer",
                    "description": "Video width in pixels. Common: 1280 (landscape), 720 (portrait), 960 (square). Default: 1280.",
                },
                "height": {
                    "type": "integer",
                    "description": "Video height in pixels. Common: 720 (landscape), 1280 (portrait), 960 (square). Default: 720.",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility (optional).",
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "Things to avoid in the video (optional).",
                },
                "generate_audio": {
                    "type": "boolean",
                    "description": "Generate native audio (supported by Kling, Google models). Default: true.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format. Default: MP4.",
                    "enum": ["MP4", "WEBM", "MOV"],
                },
            },
            "required": ["prompt"],
        },
        "execute": execute_runware_t2v,
    })

    api.register_tool({
        "name": "runware_image_to_video",
        "description": (
            "Animate an image into video via Runware.ai (unified cloud API). "
            "Access Kling V3, Runway Gen4.5/Turbo, Google Veo 3, Minimax Hailuo "
            "with a single Runware API key. "
            "Takes a source image (JPG/PNG, max 20MB) and optional prompt. "
            "PAID service — requires a Runware API key."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "How to animate the image (e.g. 'slow zoom in', 'the dog runs forward').",
                },
                "image_path": {
                    "type": "string",
                    "description": "Path to the source image (JPG/PNG/WebP, max 20MB).",
                },
                "model": {
                    "type": "string",
                    "description": (
                        "Model to use. Aliases: 'kling-v3-pro', 'runway-gen4.5', 'runway-gen4-turbo', "
                        "'veo3', 'minimax-s2v', etc. Default: 'auto' (Kling V3 Pro)."
                    ),
                },
                "duration": {
                    "type": "integer",
                    "description": "Duration in seconds. Default: 10.",
                },
                "width": {
                    "type": "integer",
                    "description": "Video width in pixels. Default: 1280.",
                },
                "height": {
                    "type": "integer",
                    "description": "Video height in pixels. Default: 720.",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility (optional).",
                },
                "generate_audio": {
                    "type": "boolean",
                    "description": "Generate native audio (Kling, Google models). Default: true.",
                },
                "output_format": {
                    "type": "string",
                    "description": "Output format. Default: MP4.",
                    "enum": ["MP4", "WEBM", "MOV"],
                },
            },
            "required": ["image_path"],
        },
        "execute": execute_runware_i2v,
    })

    api.register_tool({
        "name": "runware_list_models",
        "description": (
            "List all video models available through Runware.ai, "
            "including their aliases, AIR IDs, capabilities, and supported features."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "execute": execute_runware_list_models,
    })
