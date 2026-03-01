---
name: moonshine-stt
description: Fast, accurate speech-to-text using Moonshine ASR - open-weights model with higher accuracy than Whisper, optimized for edge devices
homepage: https://github.com/usefulsensors/moonshine
triggers:
  - moonshine
  - transcribe
  - transcription
  - speech to text
  - audio to text
  - stt
  - .mp3
  - .wav
  - .m4a
  - .flac
  - .ogg
  - .webm
tools:
  - shell_exec
  - file_read
  - notify
priority: 75
requires:
  bins: ["python3"]
  python: ["useful-moonshine-onnx", "soundfile", "numpy"]
content_types: ["audio", "transcription"]
---

# Moonshine STT Skill

Fast, accurate automatic speech recognition using Moonshine - an open-weights ASR model that outperforms Whisper on accuracy while being optimized for edge devices.

## Capabilities

- Higher accuracy than Whisper on English speech (per paper benchmarks)
- Optimized for edge devices (on-device transcription)
- Low latency, even on CPU
- Open weights (fully self-hostable)
- Small model sizes (base ~70MB, tiny ~30MB)

## Installation

```bash
pip install useful-moonshine-onnx soundfile numpy
```

## Usage

### Simple API

```python
import moonshine_onnx
import soundfile as sf

# Load audio
audio, sr = sf.read('/path/to/audio.wav')

# Transcribe (model downloads on first use)
transcript = moonshine_onnx.transcribe(audio, model='moonshine/tiny')
print(transcript)
```

### Advanced: Direct Model Usage

```python
from moonshine_onnx import MoonshineOnnxModel, load_audio

# Load model
model = MoonshineOnnxModel(model_name='moonshine/tiny')

# Load and transcribe audio
audio = load_audio('/path/to/audio.wav')
transcript = model(audio)
print(transcript)
```

### CLI-style one-liner

```bash
python3 -c "
import moonshine_onnx
import soundfile as sf
import sys

audio, sr = sf.read(sys.argv[1])
print(moonshine_onnx.transcribe(audio, model='moonshine/tiny'))
" /path/to/audio.wav
```

## Available Models

- `moonshine/tiny` (~27M params, ~30MB) - Fastest, good accuracy
- `moonshine/base` (~70M params, ~70MB) - Higher accuracy

## Examples

- "Transcribe this interview recording"
- "Convert meeting-audio.m4a to text with Moonshine"
- "Use moonshine for faster transcription than whisper"

## Notes

- Moonshine uses ONNX Runtime for efficient inference
- Models download automatically on first use
- Supports WAV, MP3, FLAC, and other formats via soundfile
- Benchmarks show 2x faster than Whisper with better WER on test sets
- Open source (MIT license) from Useful Sensors
