import wave
from pathlib import Path

import pytest

from healthvideo.tts.audio_checks import inspect_wav


def _wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24_000)
        audio.writeframes(frames)


def test_wav_report_uses_bytes_and_can_require_signal(tmp_path: Path) -> None:
    output = tmp_path / "speech.wav"
    _wav(output, b"\x01\x00" * 24_000)
    report = inspect_wav(output, require_signal=True)
    assert report.duration_ms == 1000
    assert report.sample_rate == 24_000
    assert report.has_signal


def test_silence_fails_when_signal_required(tmp_path: Path) -> None:
    output = tmp_path / "silent.wav"
    _wav(output, b"\x00\x00" * 24_000)
    assert not inspect_wav(output).has_signal
    with pytest.raises(ValueError, match="silent"):
        inspect_wav(output, require_signal=True)


@pytest.mark.parametrize("payload", [b"", b"not a wav"])
def test_invalid_wav_fails(tmp_path: Path, payload: bytes) -> None:
    output = tmp_path / "bad.wav"
    output.write_bytes(payload)
    with pytest.raises(ValueError, match="WAV"):
        inspect_wav(output)
