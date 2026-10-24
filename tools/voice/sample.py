"""Generate four approved gout lines as comparable expressive voice samples."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
from pathlib import Path

from healthvideo.env import load_dotenv
from healthvideo.storage.files import read_yaml
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.elevenlabs import (
    ElevenLabsError,
    ElevenLabsTTS,
    VoiceProfile,
    load_voice_profile,
)
from healthvideo.tts.normalize import NormalizedTTS
from healthvideo.tts.pronunciation import (
    PRONUNCIATION_PROFILE_PATH,
    apply_pronunciation,
    load_pronunciation_lexicon,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path("E:/Protect Your Health/projects/gout-tinh-the-urat/revisions/001/script/script.yaml")


def sample_delivery(text: str, index: int) -> str:
    # Tags affect delivery only: every approved word stays exactly as written.
    if "Khoan mở phiên tòa xét thực đơn." in text:
        return "[curious] " + text.replace(
            "Khoan mở phiên tòa xét thực đơn.",
            "[sarcastic] Khoan mở phiên tòa xét thực đơn. [curious]",
        )
    if "Đừng đếm chấm" in text:
        return "[curious] " + text.replace("Đừng đếm chấm", "[sarcastic] Đừng đếm chấm")
    return f"[{('curious', 'curious', 'excited', 'curious')[index % 4]}] {text}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voices", required=True, help="Comma-separated voice IDs")
    parser.add_argument("--settings", default="{}", help='JSON object, e.g. {"stability":0.5,"speed":1.0}')
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ELEVENLABS_API_KEY", "").strip():
        print("Set ELEVENLABS_API_KEY in .env; run tools/voice/list_voices.py, then sample.py --voices id1,id2 --settings '{}'.")
        return 2
    try:
        profile = load_voice_profile()
        settings = {**profile.settings.model_dump(), **json.loads(args.settings)}
        voices = [voice.strip() for voice in args.voices.split(",") if voice.strip()]
        if not voices:
            raise ValueError("At least one voice ID is required")
        profiles = [VoiceProfile(voice_id=voice, settings=settings, allowed_tags=profile.allowed_tags) for voice in voices]
        lines = read_yaml(SCRIPT)["lines"][:4]
        if len(lines) != 4:
            raise ValueError("Four script lines are required")
        lexicon = load_pronunciation_lexicon(PRONUNCIATION_PROFILE_PATH)
        root = ROOT / "cache" / "voice-test"
        rows = []
        for selected in profiles:
            folder = root / selected.voice_id
            folder.mkdir(parents=True, exist_ok=True)
            provider = NormalizedTTS(ElevenLabsTTS(selected, usage_path=folder / "tts-usage.json"))
            samples = []
            for index, line in enumerate(lines):
                delivery = sample_delivery(line["text"], index)
                spoken = apply_pronunciation(delivery, lexicon)
                wav, mp3 = folder / f"{index + 1}.wav", folder / f"{index + 1}.mp3"
                provider.synthesize(TTSRequest(text=spoken, language="vi"), wav)
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(wav), str(mp3)],
                               check=True, capture_output=True)
                wav.unlink()
                samples.append({"text": line["text"], "delivery": delivery, "tts_text": spoken})
                samples_html = (f'<p>{html.escape(line["text"])}</p><audio controls src="'
                                f'{selected.voice_id}/{mp3.name}"></audio>')
                rows.append(f"<section><h2>{html.escape(selected.voice_id)} · {index + 1}</h2>{samples_html}</section>")
            (folder / "samples.json").write_text(json.dumps({"voice": selected.model_dump(), "lines": samples}, ensure_ascii=False, indent=2), encoding="utf-8")
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Voice comparison</title><h1>So sánh giọng đọc</h1>' + "\n".join(rows), encoding="utf-8")
        print(root / "index.html")
    except (ElevenLabsError, ValueError, OSError, KeyError, subprocess.SubprocessError):
        print("Voice samples failed; check the read-only gout script, settings, API permissions and ffmpeg.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
