"""Literal, word-boundary-aware pronunciation resolution."""

import re
from pathlib import Path

from healthvideo.domain.pronunciation import PronunciationLexicon
from healthvideo.storage.files import canonical_json_hash, read_yaml

PRONUNCIATION_PROFILE_PATH = (
    Path(__file__).resolve().parents[3] / "profiles" / "pronunciation.vi.yaml"
)


def load_pronunciation_lexicon(path: Path) -> PronunciationLexicon:
    return PronunciationLexicon.model_validate(read_yaml(path))


def pronunciation_hash(lexicon: PronunciationLexicon) -> str:
    return canonical_json_hash(lexicon.model_dump(mode="json"))


def apply_pronunciation(text: str, lexicon: PronunciationLexicon) -> str:
    if not lexicon.entries:
        return text
    choices = sorted(lexicon.entries, key=lambda entry: -len(entry.written))
    pattern = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(e.written) for e in choices) + r")(?!\w)",
        flags=re.IGNORECASE | re.UNICODE,
    )
    mapping = {entry.written.casefold(): entry.spoken for entry in choices}
    return pattern.sub(lambda match: mapping[match.group().casefold()], text)
