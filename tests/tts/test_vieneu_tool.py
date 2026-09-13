"""The VieNeu wrapper runs in a separate venv; only its pure WAV helper is tested here."""

import importlib.util
import wave
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "tts" / "vieneu_synth.py"


def _load():
    spec = importlib.util.spec_from_file_location("vieneu_synth", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_pcm16_wav_clips_and_writes_mono_48k(tmp_path: Path) -> None:
    tool = _load()
    output = tmp_path / "out.wav"
    tool.write_pcm16_wav([0.0, 0.5, -0.5, 1.7, -1.7], 48_000, output)
    with wave.open(str(output), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 48_000)
        frames = audio.readframes(5)
    samples = [int.from_bytes(frames[i : i + 2], "little", signed=True) for i in range(0, 10, 2)]
    assert samples == [0, 16383, -16383, 32767, -32767]


def test_write_pcm16_wav_rejects_empty_audio(tmp_path: Path) -> None:
    tool = _load()
    with pytest.raises(ValueError, match="empty"):
        tool.write_pcm16_wav([], 48_000, tmp_path / "out.wav")


def test_synthesize_file_uses_injected_engine(tmp_path: Path) -> None:
    tool = _load()
    text_file = tmp_path / "in.txt"
    text_file.write_text("Huyết áp\n", encoding="utf-8")
    seen: dict[str, str] = {}

    def infer(text: str, voice: str) -> list[float]:
        seen.update(text=text, voice=voice)
        return [0.1] * 480

    tool.synthesize_file(text_file, tmp_path / "out.wav", voice="Adam", infer=infer)
    assert seen == {"text": "Huyết áp", "voice": "Adam"}
    assert (tmp_path / "out.wav").stat().st_size > 44
