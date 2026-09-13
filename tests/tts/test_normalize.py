import shutil
import wave
from pathlib import Path

import pytest

from healthvideo.tts.base import TTSRequest, TTSResult, provider_identity
from healthvideo.tts.normalize import NormalizedTTS


class _LoudTTS:
    provider_name = "command"
    require_signal = True

    def cache_identity(self) -> dict[str, str]:
        return {
            "provider": "command", "model_id": "m", "voice_id": "v", "runtime_id": "onnx-cpu"
        }

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24_000)
            audio.writeframes(bytes([0, 64, 0, 192]) * 12_000)
        return TTSResult(provider="command", audio_file=output, duration_ms=1000)


def _copy_runner(argv: list[str]) -> int:
    shutil.copy(argv[argv.index("-i") + 1], argv[-1])
    return 0


def test_normalized_identity_marks_runtime_and_keeps_provider() -> None:
    wrapped = NormalizedTTS(_LoudTTS(), runner=_copy_runner)
    identity = provider_identity(wrapped)
    assert identity["provider"] == "command"
    assert identity["runtime_id"] == "onnx-cpu-loudnorm"
    assert wrapped.require_signal is True


def test_normalized_runs_ffmpeg_on_staged_wav_and_fails_closed(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        raw, out = Path(argv[argv.index("-i") + 1]), Path(argv[-1])
        assert raw.is_file() and raw != out
        return _copy_runner(argv)

    wrapped = NormalizedTTS(_LoudTTS(), runner=runner)
    output = tmp_path / "audio" / "narration.wav"
    result = wrapped.synthesize(TTSRequest(text="Xin chào", language="vi"), output)
    assert output.is_file() and result.duration_ms == 1000
    joined = " ".join(calls[0])
    assert calls[0][0] == "ffmpeg" and "loudnorm" in joined
    assert "-ar 48000" in joined and "-ac 1" in joined and "pcm_s16le" in joined

    failing = NormalizedTTS(_LoudTTS(), runner=lambda argv: 1)
    output2 = tmp_path / "audio" / "other.wav"
    with pytest.raises(RuntimeError, match="ffmpeg"):
        failing.synthesize(TTSRequest(text="Xin chào", language="vi"), output2)
    assert not output2.exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_normalized_real_ffmpeg_outputs_48k_mono_pcm16(tmp_path: Path) -> None:
    from healthvideo.tts.audio_checks import inspect_wav

    output = tmp_path / "narration.wav"
    NormalizedTTS(_LoudTTS()).synthesize(TTSRequest(text="Xin chào", language="vi"), output)
    report = inspect_wav(output, require_signal=True)
    assert (report.sample_rate, report.channels, report.sample_width) == (48_000, 1, 2)
    assert 900 <= report.duration_ms <= 1200
