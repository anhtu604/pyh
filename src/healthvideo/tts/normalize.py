"""Loudness/sample-rate normalization wrapper around any TTS provider (FFmpeg)."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.tts.base import TTSProvider, TTSRequest, TTSResult, provider_identity
from healthvideo.tts.command import Runner, _run

# EBU R128 target used by short-form platforms; mono PCM16 48 kHz matches inspect_wav.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"
SAMPLE_RATE = 48_000


def build_ffmpeg_argv(ffmpeg: str, source: Path, target: Path) -> list[str]:
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source), "-af", LOUDNORM_FILTER,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(target),
    ]


class NormalizedTTS:
    """Synthesize with ``inner`` then normalize; identity marks the runtime as ``-loudnorm``."""

    def __init__(
        self, inner: TTSProvider, *, ffmpeg: str = "ffmpeg", runner: Runner = _run
    ) -> None:
        self.inner = inner
        self.ffmpeg = ffmpeg
        self.runner = runner
        self.provider_name = provider_identity(inner)["provider"]
        self.require_signal = bool(getattr(inner, "require_signal", False))

    def cache_identity(self) -> dict[str, str]:
        identity = provider_identity(self.inner)
        identity["runtime_id"] = f"{identity.get('runtime_id', 'default')}-loudnorm"
        return identity

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".loudnorm-", dir=output.parent) as temporary:
            raw = Path(temporary) / "raw.wav"
            normalized = Path(temporary) / "normalized.wav"
            result = self.inner.synthesize(request, raw)
            exit_code = self.runner(build_ffmpeg_argv(self.ffmpeg, raw, normalized))
            if exit_code != 0:
                raise RuntimeError(f"ffmpeg loudnorm failed with exit code {exit_code}")
            if not normalized.is_file():
                raise FileNotFoundError("ffmpeg loudnorm did not write a WAV file")
            report = inspect_wav(normalized, require_signal=self.require_signal)
            os.replace(normalized, output)
        return result.model_copy(
            update={"audio_file": output, "duration_ms": report.duration_ms}
        )
