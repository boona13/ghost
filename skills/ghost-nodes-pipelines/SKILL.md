---
name: ghost-nodes-pipelines
description: Create multi-step AI pipelines using GhostNodes — chain image, video, audio, vision, and utility tools
triggers:
  - pipeline
  - workflow
  - chain tools
  - multi-step
  - automate media flow
  - generate and then
  - product video
  - podcast workflow
  - document analysis pipeline
tools:
  - pipeline_create
  - pipeline_run
  - pipeline_status
  - pipeline_list
  - pipeline_cancel
  - text_to_image_local
  - image_to_image_local
  - remove_background
  - upscale_image
  - generate_video
  - bark_speak
  - generate_music
  - transcribe_audio
  - florence_analyze
  - ocr_extract
priority: 8
---

# GhostNodes Pipeline Skill

You have access to a powerful AI pipeline system that chains multiple local AI tools together. Use `pipeline_create` and `pipeline_run` to build multi-step workflows.

## Available Tool Groups

### Image
- `text_to_image_local` — local text-to-image generation
- `image_to_image_local` — transform an existing image
- `remove_background` — remove background from subject images
- `upscale_image` — improve resolution for final outputs

### Video
- `generate_video` — unified text-to-video and image-to-video entry point (provider auto-selection)

### Audio
- `bark_speak` — local expressive speech synthesis
- `generate_music` — local background music generation
- `transcribe_audio` — speech-to-text

### Vision / OCR
- `florence_analyze` — captioning and visual analysis
- `ocr_extract` — OCR extraction from image documents

## Pipeline Patterns

### 1) Product visual -> video teaser

```json
[
  {"id":"img","tool_name":"text_to_image_local","params":{"prompt":"studio product photo, clean background"}},
  {"id":"nobg","tool_name":"remove_background","params":{},"input_from":"img","input_key":"image_path"},
  {"id":"up","tool_name":"upscale_image","params":{"scale":2},"input_from":"nobg","input_key":"image_path"},
  {"id":"vid","tool_name":"generate_video","params":{"prompt":"slow cinematic reveal of product on neutral background","duration":5},"input_from":"up","input_key":"image_path"}
]
```

### 2) Podcast support workflow

```json
[
  {"id":"tx","tool_name":"transcribe_audio","params":{"audio_path":"/path/to/episode.mp3","model_size":"base"}},
  {"id":"cover","tool_name":"text_to_image_local","params":{"prompt":"minimal podcast cover art, microphone icon"}},
  {"id":"intro","tool_name":"generate_music","params":{"prompt":"short clean podcast intro sting","duration_secs":5}}
]
```

### 3) Document OCR + visual context

```json
[
  {"id":"ocr","tool_name":"ocr_extract","params":{"image_path":"/path/to/doc.png","languages":["en"]}},
  {"id":"cap","tool_name":"florence_analyze","params":{"image_path":"/path/to/doc.png","task":"detailed_caption"}}
]
```

## Execution Rules

1. Build with `pipeline_create` using JSON step arrays.
2. Run with `pipeline_run`.
3. Track with `pipeline_status`.
4. Reuse with `pipeline_list`.
5. Stop long runs with `pipeline_cancel`.

## Quality Guardrails

- Keep steps minimal and explicit.
- Use deterministic filenames/inputs where possible.
- Prefer `generate_video` over deprecated `text_to_video` / `image_to_video` references.
- If a step output key is ambiguous, set `input_key` explicitly.
