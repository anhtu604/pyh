"""List Vietnamese account and shared voices without exposing credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode

from healthvideo.env import load_dotenv
from healthvideo.tts.elevenlabs import ElevenLabsError, api_request

ROOT = Path(__file__).resolve().parents[2]


def _vietnamese_metadata(voice: dict) -> bool | None:
    """Require positive account metadata; unknown shared voices rely on API filtering."""
    labels = voice.get("labels") or {}
    languages = [voice.get("language"), labels.get("language")]
    languages.extend(item.get("language") for item in voice.get("verified_languages", []) or [])
    known = [value.strip().casefold().replace("_", "-") for value in languages
             if isinstance(value, str) and value.strip()]
    if not known:
        return None
    return any(value in {"vi", "vietnamese", "tiếng việt"} or value.startswith("vi-")
               for value in known)


def list_voices(api_key: str, *, opener=None) -> list[dict]:
    voices: dict[str, dict] = {}
    for source in ("account", "shared"):
        token, page = None, 0
        while True:
            query = {"language": "vi", "page_size": 100}
            if source == "account":
                if token:
                    query["next_page_token"] = token
                endpoint = "/v2/voices"
            else:
                query["page"] = page
                endpoint = "/v1/shared-voices"
            data = json.loads(api_request(endpoint + "?" + urlencode(query), api_key=api_key, opener=opener))
            for voice in data.get("voices", []):
                vietnamese = _vietnamese_metadata(voice)
                if vietnamese is True or (source == "shared" and vietnamese is None):
                    voices.setdefault(voice["voice_id"], {**voice, "source": source})
            if not data.get("has_more"):
                break
            if source == "account":
                next_token = data.get("next_page_token")
                if not next_token or next_token == token:
                    raise ElevenLabsError("ElevenLabs voice pagination did not advance.")
                token = next_token
            page += 1
    return list(voices.values())


def main() -> int:
    load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print('Set ELEVENLABS_API_KEY in .env, then run with PYTHONPATH=src: python tools/voice/list_voices.py')
        return 2
    try:
        for voice in list_voices(key):
            print(f"{voice.get('name', '')}\t{voice['voice_id']}\t{voice.get('description', '')}\t({voice['source']})")
    except (ElevenLabsError, ValueError, KeyError):
        print("ElevenLabs voice listing failed; check API permissions and network.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
