import wave
from pathlib import Path

import pytest

from healthvideo.tts.base import TTSRequest, provider_identity
from healthvideo.tts.command import CommandTTS


def test_command_adapter_passes_unicode_as_file_and_validates_wav(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        assert Path(argv[2]).read_text(encoding="utf-8") == "Huyết áp tăng"
        with wave.open(argv[4], "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24_000)
            audio.writeframes(b"\x01\x00" * 24_000)
        return 0

    adapter = CommandTTS(
        executable="local-tts", arguments=("--input", "{input}", "--output", "{output}"),
        model_id="candidate-a", voice_id="generic-a", runner=runner,
    )
    output = tmp_path / "speech.wav"
    result = adapter.synthesize(TTSRequest(text="Huyết áp tăng", language="vi"), output)
    assert calls[0][0] == "local-tts"
    assert output.exists()
    assert result.duration_ms == 1000
    assert adapter.cache_identity()["model_id"] == "candidate-a"


def test_command_adapter_rejects_failure_without_replacing_output(tmp_path: Path) -> None:
    output = tmp_path / "speech.wav"
    output.write_bytes(b"existing")
    adapter = CommandTTS(
        executable="local-tts", arguments=("{input}", "{output}"),
        model_id="candidate-a", voice_id="generic-a", runner=lambda _: 2,
    )
    with pytest.raises(RuntimeError, match="exit code 2"):
        adapter.synthesize(TTSRequest(text="Xin chào", language="vi"), output)
    assert output.read_bytes() == b"existing"


@pytest.mark.parametrize("write_bad", [False, True])
def test_command_adapter_rejects_missing_or_malformed_wav(
    tmp_path: Path, write_bad: bool
) -> None:
    def runner(argv: list[str]) -> int:
        if write_bad:
            Path(argv[2]).write_bytes(b"not wav")
        return 0

    adapter = CommandTTS(
        executable="local-tts", arguments=("{input}", "{output}"),
        model_id="candidate-a", voice_id="generic-a", runner=runner,
    )
    error = ValueError if write_bad else FileNotFoundError
    with pytest.raises(error):
        adapter.synthesize(
            TTSRequest(text="Xin chào", language="vi"), tmp_path / "speech.wav"
        )


def test_command_identity_excludes_command_and_changes_with_voice() -> None:
    first = CommandTTS(
        executable="C:/private/tts.exe", arguments=("{input}", "{output}"),
        model_id="candidate-a", voice_id="a",
    )
    second = CommandTTS(
        executable="C:/private/tts.exe", arguments=("{input}", "{output}"),
        model_id="candidate-a", voice_id="b",
    )
    assert first.cache_identity() != second.cache_identity()
    assert "private" not in str(first.cache_identity())


@pytest.mark.parametrize(
    "unsafe", ["/home/user/private/model", "C:\\Users\\secret", "https://example.com/?key=abc", "a\nline"]
)
def test_provider_identity_rejects_nonpublic_aliases(unsafe: str) -> None:
    adapter = CommandTTS(
        executable="local-tts", arguments=("{input}", "{output}"),
        model_id=unsafe, voice_id="voice-1", runtime_id="rev_2026_09",
    )
    with pytest.raises(ValueError, match="identity"):
        provider_identity(adapter)
