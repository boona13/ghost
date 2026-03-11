from importlib import util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "ghost_nodes" / "voice-fx" / "node.py"


def _load_voice_fx_module():
    spec = util.spec_from_file_location("voice_fx_node", MODULE_PATH)
    module = util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_detect_audio_format_magic_bytes(tmp_path):
    node = _load_voice_fx_module()

    wav_path = tmp_path / "sample.wav"
    wav_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert node._detect_audio_format(wav_path) == "wav"

    m4a_path = tmp_path / "sample.m4a"
    m4a_path.write_bytes(b"\x00\x00\x00\x18ftypM4A ")
    assert node._detect_audio_format(m4a_path) == "m4a"

    mp3_path = tmp_path / "sample.mp3"
    mp3_path.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00")
    assert node._detect_audio_format(mp3_path) == "mp3"


def test_detect_audio_format_reads_stream_header_only(tmp_path, monkeypatch):
    node = _load_voice_fx_module()
    input_path = tmp_path / "big.m4a"
    input_path.write_bytes(b"\x00\x00\x00\x18ftypM4A " + b"x" * 4096)

    read_sizes = []
    orig_open = Path.open

    def _tracked_open(path_obj, *args, **kwargs):
        handle = orig_open(path_obj, *args, **kwargs)
        original_read = handle.read

        def _tracked_read(size=-1):
            read_sizes.append(size)
            return original_read(size)

        handle.read = _tracked_read
        return handle

    monkeypatch.setattr(Path, "open", _tracked_open)
    assert node._detect_audio_format(input_path) == "m4a"
    assert 32 in read_sizes
    assert -1 not in read_sizes


def test_load_audio_with_ffmpeg_fallback(monkeypatch, tmp_path):
    node = _load_voice_fx_module()
    input_path = tmp_path / "input.m4a"
    input_path.write_bytes(b"\x00\x00\x00\x18ftypM4A ")

    calls = []

    def _fake_read(path):
        calls.append(Path(path))
        if len(calls) == 1:
            raise RuntimeError("native decode failed")
        return np.zeros(8, dtype=np.float32), 44100

    monkeypatch.setattr(node, "_read_audio_native", _fake_read)
    monkeypatch.setattr(node, "_transcode_to_wav", lambda src, dst, ffmpeg: None)
    monkeypatch.setattr(node.shutil, "which", lambda cmd: "/usr/bin/ffmpeg")

    audio, sample_rate, used_fallback = node._load_audio_with_fallback(input_path)
    assert isinstance(audio, np.ndarray)
    assert sample_rate == 44100
    assert used_fallback is True
    assert len(calls) == 2
    assert calls[0] == input_path
    assert calls[1].suffix == ".wav"
