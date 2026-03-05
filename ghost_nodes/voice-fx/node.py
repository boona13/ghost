"""
Voice Effects Node — fun audio transformations with zero model downloads.

Apply voice effects to any audio recording:
- Robot: metallic robotic voice
- Chipmunk: high-pitched fast voice
- Deep: deep bass voice
- Echo: canyon echo effect
- Whisper: soft whisper effect
- Alien: otherworldly warped voice
- Reverse: play audio backwards
- Slow-mo: dramatic slow motion
- Fast: sped up audio
- Chorus: layered chorus/choir effect
"""

import json
import logging
import time
import io
from pathlib import Path

log = logging.getLogger("ghost.node.voice_fx")

EFFECTS = {
    "robot": "Metallic robotic voice with harmonics",
    "chipmunk": "High-pitched fast chipmunk voice",
    "deep": "Deep bass voice like a giant",
    "echo": "Canyon echo / delay effect",
    "whisper": "Soft breathy whisper",
    "alien": "Otherworldly warped alien voice",
    "reverse": "Play audio backwards",
    "slow_mo": "Dramatic slow motion (half speed)",
    "fast": "Sped up audio (2x speed)",
    "chorus": "Layered choir / chorus effect",
    "underwater": "Muffled underwater sound",
    "radio": "Old AM radio / walkie-talkie",
}


def _apply_effect(audio, sr, effect):
    """Apply the given effect to audio numpy array."""
    import numpy as np
    from scipy import signal as sig

    audio = audio.astype(np.float64)

    if effect == "robot":
        t = np.arange(len(audio)) / sr
        carrier = np.sin(2 * np.pi * 80 * t)
        modulated = audio * carrier
        harmonics = audio * np.sin(2 * np.pi * 160 * t) * 0.3
        result = modulated + harmonics
        return np.clip(result, -1, 1).astype(np.float32)

    elif effect == "chipmunk":
        indices = np.arange(0, len(audio), 1.8)
        indices = indices[indices < len(audio)].astype(int)
        return audio[indices].astype(np.float32)

    elif effect == "deep":
        stretched = np.interp(
            np.linspace(0, len(audio), int(len(audio) * 1.6)),
            np.arange(len(audio)), audio,
        )
        return stretched.astype(np.float32)

    elif effect == "echo":
        delay_samples = int(sr * 0.3)
        decay = 0.5
        result = np.copy(audio)
        for i in range(1, 4):
            offset = delay_samples * i
            if offset < len(result):
                end = min(len(result), len(audio) + offset) - offset
                result[offset:offset + end] += audio[:end] * (decay ** i)
        return np.clip(result, -1, 1).astype(np.float32)

    elif effect == "whisper":
        noise = np.random.randn(len(audio)) * 0.15
        b, a = sig.butter(4, [300 / (sr / 2), 3000 / (sr / 2)], btype='band')
        filtered = sig.filtfilt(b, a, audio)
        result = filtered * 0.4 + noise * np.abs(filtered)
        return np.clip(result, -1, 1).astype(np.float32)

    elif effect == "alien":
        t = np.arange(len(audio)) / sr
        wobble = np.sin(2 * np.pi * 5 * t) * 0.3
        pitch_shift = np.sin(2 * np.pi * 200 * t + wobble * np.cumsum(audio) * 0.001)
        result = audio * 0.6 + audio * pitch_shift * 0.4
        return np.clip(result, -1, 1).astype(np.float32)

    elif effect == "reverse":
        return audio[::-1].copy().astype(np.float32)

    elif effect == "slow_mo":
        indices = np.linspace(0, len(audio) - 1, int(len(audio) * 2))
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    elif effect == "fast":
        indices = np.arange(0, len(audio), 2)
        return audio[indices].astype(np.float32)

    elif effect == "chorus":
        offsets = [int(sr * d) for d in [0.02, 0.035, 0.05]]
        result = audio.copy()
        for off in offsets:
            delayed = np.zeros_like(audio)
            delayed[off:] = audio[:-off] if off > 0 else audio
            t = np.arange(len(audio)) / sr
            mod = np.sin(2 * np.pi * 0.5 * t) * int(sr * 0.002)
            result += delayed * 0.3
        return np.clip(result / 2, -1, 1).astype(np.float32)

    elif effect == "underwater":
        b, a = sig.butter(4, 500 / (sr / 2), btype='low')
        filtered = sig.filtfilt(b, a, audio)
        t = np.arange(len(audio)) / sr
        bubble = np.sin(2 * np.pi * 3 * t) * 0.1
        result = filtered * (1 + bubble)
        return np.clip(result, -1, 1).astype(np.float32)

    elif effect == "radio":
        b, a = sig.butter(4, [300 / (sr / 2), 3400 / (sr / 2)], btype='band')
        filtered = sig.filtfilt(b, a, audio)
        noise = np.random.randn(len(audio)) * 0.02
        clipped = np.clip(filtered * 2, -0.8, 0.8)
        return (clipped + noise).astype(np.float32)

    return audio.astype(np.float32)


def register(api):

    def execute_voice_fx(audio_path="", effect="robot", chain="",
                          filename="", **_kw):
        if not audio_path:
            return json.dumps({"status": "error", "error": "audio_path is required"})
        if not Path(audio_path).exists():
            return json.dumps({"status": "error", "error": f"File not found: {audio_path}"})

        try:
            import numpy as np
            import soundfile as sf

            audio, sr = sf.read(audio_path, dtype="float32")
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)

            effects_to_apply = []
            if chain:
                effects_to_apply = [e.strip() for e in chain.split("+") if e.strip() in EFFECTS]
            if not effects_to_apply:
                effects_to_apply = [effect if effect in EFFECTS else "robot"]

            api.log(f"Applying effects: {' + '.join(effects_to_apply)}")
            t0 = time.time()

            result = audio
            for fx in effects_to_apply:
                api.log(f"  Applying: {fx} ({EFFECTS[fx]})")
                result = _apply_effect(result, sr, fx)

            elapsed = time.time() - t0

            buf = io.BytesIO()
            sf.write(buf, result, sr, format="WAV")
            audio_bytes = buf.getvalue()

            ts = time.strftime("%Y%m%d_%H%M%S")
            fx_name = "_".join(effects_to_apply)
            fname = filename or f"fx_{fx_name}_{ts}.wav"

            path = api.save_media(
                data=audio_bytes, filename=fname, media_type="audio",
                prompt=f"Voice FX: {' + '.join(effects_to_apply)}",
                params={"effects": effects_to_apply},
                metadata={
                    "source": str(audio_path),
                    "effects": effects_to_apply,
                    "duration_secs": round(len(result) / sr, 2),
                    "elapsed_secs": round(elapsed, 2),
                },
            )
            return json.dumps({
                "status": "ok", "path": path,
                "effects": effects_to_apply,
                "duration_secs": round(len(result) / sr, 2),
                "elapsed_secs": round(elapsed, 2),
            })

        except Exception as e:
            log.error("Voice FX error: %s", e, exc_info=True)
            return json.dumps({"status": "error", "error": str(e)[:500]})

    effects_list = ", ".join(EFFECTS.keys())
    api.register_tool({
        "name": "apply_voice_effect",
        "description": (
            "Apply fun voice effects to any audio file (local). Available effects: "
            f"{effects_list}. Chain multiple effects with '+' (e.g. 'robot+echo'). "
            "No model downloads needed — instant processing. No API key needed.\n\n"
            "Examples: 'robot' for metallic voice, 'chipmunk' for high-pitched, "
            "'echo' for canyon echo, 'underwater' for muffled sound."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to input audio file (WAV/MP3/FLAC)."},
                "effect": {
                    "type": "string",
                    "enum": list(EFFECTS.keys()),
                    "description": f"Effect to apply. Options: {effects_list}. Default: robot.",
                },
                "chain": {
                    "type": "string",
                    "description": "Chain multiple effects with '+' (e.g. 'robot+echo+slow_mo'). Overrides effect.",
                },
                "filename": {"type": "string", "description": "Output filename (optional)."},
            },
            "required": ["audio_path"],
        },
        "execute": execute_voice_fx,
    })
