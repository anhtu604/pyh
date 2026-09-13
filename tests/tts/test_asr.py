import json
import wave
from pathlib import Path

import pytest

from healthvideo.tts.asr import CommandASR, normalize_transcript, word_error_rate


def test_normalize_transcript_folds_case_punctuation_and_unicode_form() -> None:
    decomposed = "Huye\u0302\u0301t a\u0301p"  # NFD
    assert normalize_transcript(decomposed) == "huyết áp"
    assert normalize_transcript("  Đo lại, sau 5 phút!  ") == "đo lại sau 5 phút"


@pytest.mark.parametrize(
    ("reference", "hypothesis", "expected"),
    [
        ("một hai ba", "một hai ba", 0.0),
        ("một hai ba", "một hai", pytest.approx(1 / 3)),
        ("một hai ba", "một hay ba bốn", pytest.approx(2 / 3)),
        ("một", "", 1.0),
    ],
)
def test_word_error_rate_is_levenshtein_over_normalized_words(
    reference: str, hypothesis: str, expected: float
) -> None:
    assert word_error_rate(reference, hypothesis) == expected


def test_word_error_rate_rejects_empty_reference() -> None:
    with pytest.raises(ValueError, match="empty"):
        word_error_rate("   ", "xin chào")


def test_command_asr_reads_transcript_json_and_hides_command(tmp_path: Path) -> None:
    wav = tmp_path / "in.wav"
    with wave.open(str(wav), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48_000)
        audio.writeframes(bytes([1, 0]) * 4800)

    def runner(argv: list[str]) -> int:
        assert argv[1] == str(wav)
        Path(argv[2]).write_text(json.dumps({"text": "Xin chào"}), encoding="utf-8")
        return 0

    asr = CommandASR(
        executable="C:/private/asr.exe", arguments=("{input}", "{output}"),
        model_id="whisper-small", runner=runner,
    )
    assert asr.transcribe(wav) == "Xin chào"
    assert asr.identity() == {"provider": "command", "model_id": "whisper-small"}


def test_command_asr_rejects_failure_and_bad_output(tmp_path: Path) -> None:
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"")
    asr = CommandASR(
        executable="asr", arguments=("{input}", "{output}"), model_id="m", runner=lambda _: 4
    )
    with pytest.raises(RuntimeError, match="exit code 4"):
        asr.transcribe(wav)

    def bad(argv: list[str]) -> int:
        Path(argv[2]).write_text("{}", encoding="utf-8")
        return 0

    asr = CommandASR(
        executable="asr", arguments=("{input}", "{output}"), model_id="m", runner=bad
    )
    with pytest.raises(ValueError, match="text"):
        asr.transcribe(wav)
