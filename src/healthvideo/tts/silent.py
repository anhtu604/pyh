import os
import wave
from pathlib import Path

from healthvideo.tts.base import TTSRequest, TTSResult, word_timestamps

SAMPLE_RATE = 24_000
SAMPLE_WIDTH_BYTES = 2
CHANNELS = 1
WORDS_PER_SECOND = 2.7


class SilentTTS:
    """Offline deterministic TTS used for tests and render-pipeline smoke checks."""

    provider_name = "silent"

    def synthesize(self, request: TTSRequest, output: Path) -> TTSResult:
        words = request.text.split()
        duration_ms = max(1000, round(len(words) / WORDS_PER_SECOND * 1000))
        frame_count = round(duration_ms * SAMPLE_RATE / 1000)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(f"{output.suffix}.tmp")
        try:
            with wave.open(str(temporary), "wb") as wav:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(b"\x00" * frame_count * CHANNELS * SAMPLE_WIDTH_BYTES)
            os.replace(temporary, output)
        finally:
            if temporary.exists():
                temporary.unlink()

        return TTSResult(
            provider=self.provider_name,
            audio_file=output,
            duration_ms=duration_ms,
            word_timestamps=word_timestamps(words, duration_ms),
        )
