import wave

from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS


def test_silent_tts_writes_deterministic_wav(tmp_path) -> None:
    output = tmp_path / "narration.wav"

    result = SilentTTS().synthesize(
        TTSRequest(text="Xin chào bạn", language="vi"), output
    )

    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
    assert result.duration_ms == 1111
    assert result.provider == "silent"


def test_silent_tts_writes_identical_bytes_for_identical_request(tmp_path) -> None:
    request = TTSRequest(text="Một hai ba bốn", language="vi")
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"

    SilentTTS().synthesize(request, first)
    SilentTTS().synthesize(request, second)

    assert first.read_bytes() == second.read_bytes()
