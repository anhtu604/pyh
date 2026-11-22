"""Loudness/sample-rate normalization wrapper around any TTS provider (FFmpeg)."""

import json
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from healthvideo.tts.audio_checks import AudioReport, inspect_wav
from healthvideo.tts.base import TTSProvider, TTSRequest, TTSResult, provider_identity
from healthvideo.tts.command import Runner, _run

# EBU R128 target used by short-form platforms; mono PCM16 48 kHz matches inspect_wav.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"
SAMPLE_RATE = 48_000
MASTER_LOUDNESS_TARGETS: dict[str, tuple[float, float, float]] = {
    "youtube_long": (-14.0, -1.0, 11.0),
    "hook_outro_v1": (-14.0, -1.0, 11.0),
    "youtube_shorts": (-16.0, -1.5, 11.0),
    "short_form": (-16.0, -1.5, 11.0),
}


def master_loudness_target(format_profile: str | None = None) -> tuple[float, float, float]:
    """Return (target_lufs, true_peak_db, lra) for the target format profile."""
    return MASTER_LOUDNESS_TARGETS.get(str(format_profile or ""), (-14.0, -1.0, 11.0))


def build_ffmpeg_argv(ffmpeg: str, source: Path, target: Path) -> list[str]:
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source), "-af", LOUDNORM_FILTER,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(target),
    ]


def build_master_loudnorm_argv(
    ffmpeg: str,
    source: Path,
    target: Path,
    *,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    lra: float = 11.0,
    duration_s: float | None = None,
    channels: int = 2,
) -> list[str]:
    filter_expr = f"loudnorm=I={target_lufs:g}:TP={true_peak_db:g}:LRA={lra:g},aresample={SAMPLE_RATE}"
    if duration_s is not None and duration_s > 0:
        filter_expr += f",apad,atrim=duration={duration_s:.9f}"
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source), "-af", filter_expr,
        "-ar", str(SAMPLE_RATE), "-ac", str(channels), "-c:a", "pcm_s16le", str(target),
    ]


def normalize_master_wav(
    source: Path,
    target: Path,
    *,
    format_profile: str | None = None,
    ffmpeg: str = "ffmpeg",
    runner: Runner = _run,
) -> AudioReport:
    """Normalize a mixed master narration WAV to broadcast loudness while preserving duration."""
    source_report = inspect_wav(source, require_signal=False)
    target_lufs, true_peak_db, lra = master_loudness_target(format_profile)
    duration_s = source_report.duration_ms / 1000.0
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".master-loudnorm-", dir=target.parent) as temporary:
        staged = Path(temporary) / "master.wav"
        argv = build_master_loudnorm_argv(
            ffmpeg,
            source,
            staged,
            target_lufs=target_lufs,
            true_peak_db=true_peak_db,
            lra=lra,
            duration_s=duration_s,
            channels=source_report.channels,
        )
        exit_code = runner(argv)
        if exit_code != 0:
            raise RuntimeError(f"ffmpeg master loudnorm failed with exit code {exit_code}")
        if not staged.is_file():
            raise FileNotFoundError("ffmpeg master loudnorm did not write a WAV file")
        report = inspect_wav(staged, require_signal=source_report.has_signal)
        os.replace(staged, target)
    return report


def measure_loudness(
    path: Path,
    *,
    format_profile: str | None = None,
    ffmpeg: str = "ffmpeg",
    runner=subprocess.run,
) -> dict[str, float]:
    """Measure integrated LUFS and true peak via FFmpeg loudnorm JSON output."""
    target_lufs, true_peak_db, lra = master_loudness_target(format_profile)
    argv = [
        ffmpeg, "-hide_banner", "-nostdin", "-i", str(path),
        "-af", f"loudnorm=I={target_lufs:g}:TP={true_peak_db:g}:LRA={lra:g}:print_format=json",
        "-f", "null", "-",
    ]
    result = runner(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg loudness measure failed (exit {result.returncode})")
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", result.stderr or "", re.DOTALL)
    if not match:
        raise RuntimeError("ffmpeg loudness measure did not emit JSON summary")
    data = json.loads(match.group(0))
    return {
        "input_i": float(data["input_i"]),
        "input_tp": float(data["input_tp"]),
        "input_lra": float(data["input_lra"]),
        "target_i": target_lufs,
        "target_tp": true_peak_db,
    }


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

    def set_usage_path(self, path: Path) -> None:
        setter = getattr(self.inner, "set_usage_path", None)
        if callable(setter):
            setter(path)

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
            try:
                report = inspect_wav(normalized, require_signal=self.require_signal)
            except ValueError as error:
                raise RuntimeError(f"ffmpeg loudnorm produced invalid WAV: {error}") from None
            os.replace(normalized, output)
        return result.model_copy(
            update={"audio_file": output, "duration_ms": report.duration_ms}
        )
