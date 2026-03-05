"""
Voice Clone Node — clone any voice from a short audio sample using OpenVoice V2.

Feed a 10-30 second voice sample and text, get speech in that voice.
Supports cross-lingual cloning: the cloned voice can speak any language.
"""

import json
import logging
import time
import io
from pathlib import Path

log = logging.getLogger("ghost.node.voice_clone")

_tone_converter = None
_base_tts = None
_device = None


def _ensure_models(api):
    global _tone_converter, _base_tts, _device

    if _tone_converter is not None:
        api.resource_manager.touch("openvoice-v2")
        return

    try:
        import torch
    except ImportError:
        raise RuntimeError("Required: pip install torch")

    _device = api.acquire_gpu("openvoice-v2", estimated_vram_gb=1.0)

    try:
        from openvoice.api import ToneColorConverter
        from openvoice import se_extractor
        from melo.api import TTS as MeloTTS
    except ImportError:
        raise RuntimeError(
            "Required: pip install git+https://github.com/myshell-ai/OpenVoice.git "
            "git+https://github.com/myshell-ai/MeloTTS.git"
        )

    ckpt_dir = Path(api.models_dir) / "openvoice_v2"
    if not ckpt_dir.exists():
        api.log("Downloading OpenVoice V2 checkpoints...")
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(
                "myshell-ai/OpenVoiceV2",
                local_dir=str(ckpt_dir),
                cache_dir=api.models_dir,
                token=getattr(api, 'hf_token', None),
            )
        except Exception as e:
            raise RuntimeError(f"Failed to download OpenVoice V2: {e}")

    converter_ckpt = ckpt_dir / "converter"
    api.log("Loading OpenVoice tone color converter...")
    _tone_converter = ToneColorConverter(
        str(converter_ckpt / "config.json"),
        device=_device,
    )
    _tone_converter.load_ckpt(str(converter_ckpt / "checkpoint.pth"))

    api.log("Loading MeloTTS base speaker...")
    _base_tts = MeloTTS(language="EN", device=_device)

    api.log("Voice clone models ready")


def register(api):

    def execute_clone(text="", reference_audio="", language="EN",
                      speed=1.0, filename="", **_kw):
        if not text:
            return json.dumps({"status": "error", "error": "text is required"})
        if not reference_audio:
            return json.dumps({"status": "error", "error": "reference_audio path is required"})
        if not Path(reference_audio).exists():
            return json.dumps({"status": "error", "error": f"File not found: {reference_audio}"})

        try:
            import torch
            from openvoice import se_extractor

            _ensure_models(api)

            api.log(f"Extracting voice signature from reference audio...")
            t0 = time.time()

            target_se, _ = se_extractor.get_se(
                reference_audio, _tone_converter, vad=True
            )

            base_dir = Path(api.models_dir) / "openvoice_v2" / "base_speakers" / "ses"
            src_se_path = base_dir / "en-default.pth"
            if not src_se_path.exists():
                src_se_path = base_dir / "en-us.pth"
            if not src_se_path.exists():
                se_files = list(base_dir.glob("*.pth"))
                if not se_files:
                    return json.dumps({"status": "error", "error": "No base speaker embeddings found"})
                src_se_path = se_files[0]

            source_se = torch.load(str(src_se_path), map_location=_device, weights_only=True)

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_base:
                base_wav = tmp_base.name

            lang_upper = language.upper()[:2]
            speaker_ids = _base_tts.hps.data.spk2id
            default_speaker = list(speaker_ids.keys())[0]

            api.log(f"Generating base speech ({len(text)} chars)...")
            _base_tts.tts_to_file(
                text, speaker_ids[default_speaker], base_wav,
                speed=float(speed),
            )

            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = filename or f"cloned_{ts}.wav"
            out_path = Path(api.models_dir).parent / "media" / "audio" / fname
            out_path.parent.mkdir(parents=True, exist_ok=True)

            api.log("Applying voice tone color...")
            _tone_converter.convert(
                audio_src_path=base_wav,
                src_se=source_se,
                tgt_se=target_se,
                output_path=str(out_path),
            )

            Path(base_wav).unlink(missing_ok=True)
            elapsed = time.time() - t0

            audio_bytes = out_path.read_bytes()
            saved = api.save_media(
                data=audio_bytes, filename=fname, media_type="audio",
                prompt=f"Voice clone: '{text[:80]}'",
                params={"language": language, "speed": speed},
                metadata={
                    "reference": str(reference_audio), "text": text[:200],
                    "language": language, "elapsed_secs": round(elapsed, 2),
                },
            )
            return json.dumps({
                "status": "ok", "path": saved,
                "language": language,
                "elapsed_secs": round(elapsed, 2),
            })

        except Exception as e:
            log.error("Voice clone error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    api.register_tool({
        "name": "clone_voice",
        "description": (
            "Clone a voice from a reference audio sample and generate speech "
            "in that voice (local, OpenVoice V2). Provide a 10-30 second audio "
            "sample as reference and the text to speak. Supports cross-lingual "
            "cloning — the cloned voice can speak any language. No API key needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak in the cloned voice."},
                "reference_audio": {"type": "string", "description": "Path to voice sample audio (10-30 sec WAV/MP3)."},
                "language": {
                    "type": "string",
                    "description": "Language for TTS: EN, ES, FR, ZH, JP, KR. Default: EN.",
                },
                "speed": {"type": "number", "description": "Speech speed multiplier (default: 1.0)."},
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["text", "reference_audio"],
        },
        "execute": execute_clone,
    })
