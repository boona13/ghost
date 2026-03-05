---
name: ghost-nodes-pipelines
description: "Create multi-step AI pipelines using GhostNodes — chain image gen, video, audio, vision, and 3D tools"
triggers: ["pipeline", "create video", "product video", "podcast", "document analysis", "image and", "generate and then", "chain", "workflow", "multi-step"]
tools: ["pipeline_create", "pipeline_run", "pipeline_status", "pipeline_list", "pipeline_cancel", "text_to_image_local", "image_to_image_local", "remove_background", "upscale_image", "text_to_video", "image_to_video", "bark_speak", "generate_music", "transcribe_audio", "florence_analyze", "ocr_extract", "image_to_3d_model"]
priority: 8
---

# GhostNodes Pipeline Skill

You have access to a powerful AI pipeline system that chains multiple local AI tools together. Use `pipeline_create` and `pipeline_run` to build multi-step workflows.

## Available Nodes & Tools

### Image Generation
- `text_to_image_local` — FLUX.2 / FLUX.1 / SDXL: text-to-image, auto-selects best model for hardware
- `image_to_image_local` — Transform existing images with a prompt
- `remove_background` — Remove backgrounds (REMBG/U2-Net)
- `upscale_image` — Upscale 2x-4x (Real-ESRGAN)

### Video
- `text_to_video` — Generate video clips from text (CogVideoX)
- `image_to_video` — Animate an image into a video (CogVideoX img2video)

### Audio & Voice
- `bark_speak` — Expressive TTS with Suno Bark (13+ languages, laughter, effects)
- `generate_music` — Create music from text descriptions (Meta MusicGen)
- `transcribe_audio` — Speech-to-text with Whisper (99 languages)

### Vision & Understanding
- `florence_analyze` — Image captioning, OCR, object detection (Florence-2)
- `ocr_extract` — Document OCR for 90+ languages (Surya)

### 3D
- `image_to_3d_model` — Single-image 3D reconstruction (TripoSR)

## Demo Pipelines

### Product Video Pipeline
Create a product video with generated images, animation, music, and voiceover:

```json
[
  {"id": "img", "tool_name": "text_to_image_local", "params": {"prompt": "professional product photo of [product], studio lighting, white background"}},
  {"id": "nobg", "tool_name": "remove_background", "params": {}, "input_from": "img", "input_key": "image_path"},
  {"id": "upscale", "tool_name": "upscale_image", "params": {"scale": 4}, "input_from": "nobg", "input_key": "image_path"},
  {"id": "music", "tool_name": "generate_music", "params": {"prompt": "upbeat corporate background music, modern", "duration_secs": 15}},
  {"id": "voice", "tool_name": "bark_speak", "params": {"text": "[voiceover script]"}}
]
```

### Podcast Creator Pipeline
Transcribe audio, generate summary, create cover art, and add intro music:

```json
[
  {"id": "transcribe", "tool_name": "transcribe_audio", "params": {"audio_path": "/path/to/recording.mp3", "model_size": "medium"}},
  {"id": "cover", "tool_name": "text_to_image_local", "params": {"prompt": "podcast cover art, modern minimalist design, microphone icon"}},
  {"id": "intro", "tool_name": "generate_music", "params": {"prompt": "podcast intro jingle, short and catchy", "duration_secs": 5}}
]
```

### Document Analyzer Pipeline
Extract text from documents and caption visual elements in parallel:

```json
[
  {"id": "ocr", "tool_name": "ocr_extract", "params": {"image_path": "/path/to/document.png"}},
  {"id": "analyze", "tool_name": "florence_analyze", "params": {"image_path": "/path/to/document.png", "task": "detailed_caption"}}
]
```

### Social Media Content Pipeline
Generate an image, remove background, add style, and generate a caption:

```json
[
  {"id": "gen", "tool_name": "text_to_image_local", "params": {"prompt": "[subject], vibrant colors, social media style"}},
  {"id": "caption", "tool_name": "florence_analyze", "params": {"task": "detailed_caption"}, "input_from": "gen", "input_key": "image_path"}
]
```

## How to Create Pipelines

1. Use `pipeline_create` with a name and JSON array of steps
2. Each step has: `id`, `tool_name`, `params`, and optionally `input_from` + `input_key`
3. `input_from` references the `id` of a previous step — its output `path` is passed to the next step
4. `input_key` specifies which parameter receives the previous step's output (default: "path")
5. Use `pipeline_run` to execute the pipeline (add `"async_mode": "true"` for background execution)
6. Check progress with `pipeline_status`
7. Use `pipeline_list` to see all saved pipelines
8. Use `pipeline_cancel` to stop a running pipeline

## Tips

- All tools run locally — no API keys needed for node tools
- Check GPU status with `gpu_status` before running heavy pipelines
- Use `media_list` to browse generated outputs
- Intermediate results are cached — re-running with tweaks is fast
