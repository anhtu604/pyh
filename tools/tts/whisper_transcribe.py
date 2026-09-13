"""Local ASR command for CommandASR: WAV in, JSON ``{"text": ...}`` out (faster-whisper).

Runs inside the separate TTS venv (``cache/tts-venv``). Vietnamese is forced so
the back-check measures the narration, not language detection.
"""

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="small", help="faster-whisper model size or path")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args(argv)

    from faster_whisper import WhisperModel  # type: ignore[import-not-found]

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, _info = model.transcribe(str(args.input), language="vi", beam_size=5)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
