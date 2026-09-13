"""Local VieNeu-TTS v3 Turbo command for CommandTTS: text file in, PCM16 WAV out.

Runs inside a separate venv (see README, M5.3); imports `vieneu` lazily so the
pure WAV helper stays testable from the project venv without the model.
"""

import argparse
import struct
import sys
import wave
from collections.abc import Callable, Sequence
from pathlib import Path

DEFAULT_VOICE = "Adam"
SAMPLE_RATE = 48_000

Infer = Callable[[str, str], Sequence[float]]


def write_pcm16_wav(samples: Sequence[float], sample_rate: int, output: Path) -> None:
    if len(samples) == 0:
        raise ValueError("TTS engine returned empty audio")
    pcm = struct.pack(
        f"<{len(samples)}h",
        *(int(max(-1.0, min(1.0, float(value))) * 32767) for value in samples),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm)


def synthesize_file(text_file: Path, output: Path, *, voice: str, infer: Infer) -> None:
    text = text_file.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Narration text is empty")
    write_pcm16_wav(infer(text, voice), SAMPLE_RATE, output)


def _vieneu_infer(backend: str, precision: str) -> Infer:
    from vieneu import Vieneu  # type: ignore[import-not-found]

    engine = Vieneu(backend=backend, precision=precision)

    def infer(text: str, voice: str) -> Sequence[float]:
        return engine.infer(text, voice=voice)

    return infer


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--backend", default="onnx", choices=("onnx", "auto"))
    parser.add_argument("--precision", default="fp32", choices=("fp32", "int8"))
    args = parser.parse_args(argv)
    synthesize_file(
        args.input, args.output, voice=args.voice, infer=_vieneu_infer(args.backend, args.precision)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
