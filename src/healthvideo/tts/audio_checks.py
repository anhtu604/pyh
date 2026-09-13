"""Objective checks on staged PCM WAV bytes; not a listening or ASR review."""

import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioReport:
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    has_signal: bool


def inspect_wav(path: Path, *, require_signal: bool = False) -> AudioReport:
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            frame_count = audio.getnframes()
            if channels not in (1, 2) or sample_width != 2 or sample_rate not in (
                24_000, 48_000
            ) or frame_count <= 0:
                raise ValueError("WAV has unsupported or empty PCM format")
            has_signal = False
            frames_read = 0
            while frames_read < frame_count:
                chunk = audio.readframes(min(4096, frame_count - frames_read))
                count = len(chunk) // (channels * sample_width)
                if not chunk or len(chunk) % (channels * sample_width):
                    raise ValueError("WAV is truncated")
                frames_read += count
                has_signal |= any(chunk)
            duration_ms = round(frame_count * 1000 / sample_rate)
    except (OSError, EOFError, wave.Error) as error:
        raise ValueError("WAV is unreadable") from error
    if require_signal and not has_signal:
        raise ValueError("WAV is wholly silent")
    return AudioReport(duration_ms, sample_rate, channels, sample_width, has_signal)
