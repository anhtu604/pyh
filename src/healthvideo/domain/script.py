import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from healthvideo.storage.files import read_yaml

VOICE_PROFILE_PATH = Path(__file__).resolve().parents[3] / "profiles" / "voice.yaml"
DEFAULT_DELIVERY_TAGS = frozenset({
    "sarcastic", "curious", "excited", "chuckles", "sighs", "whispers", "pause",
})
_DELIVERY_TAG = re.compile(r"\[([^\[\]]+)\]")


def allowed_delivery_tags() -> frozenset[str]:
    """Read the configured v3 tag allowlist without loading any credentials."""
    if not VOICE_PROFILE_PATH.is_file():
        return DEFAULT_DELIVERY_TAGS
    configured = read_yaml(VOICE_PROFILE_PATH).get("allowed_tags", DEFAULT_DELIVERY_TAGS)
    return frozenset(configured)


def strip_delivery_tags(text: str) -> str:
    return _DELIVERY_TAG.sub("", text).strip()


def _normalized_delivery(text: str) -> str:
    # Preserve words and numeric punctuation: removing a decimal separator,
    # range, sign or percent mark can change the approved medical meaning.
    normalized = unicodedata.normalize("NFC", text)
    pieces = []
    for index, char in enumerate(normalized):
        if unicodedata.category(char).startswith("P"):
            before = normalized[:index].rstrip()
            after = normalized[index + 1:].lstrip()
            numeric = ((before and before[-1].isnumeric())
                       or (after and after[0].isnumeric()))
            pieces.append(f" {char} " if numeric else " ")
        else:
            pieces.append(char)
    return " ".join("".join(pieces).split())


class Delivery(BaseModel):
    schema_version: str = "1.0"
    intent: str
    pace: str = "normal"
    pause_before_ms: int = 0
    pause_after_ms: int = 0
    emphasis_words: list[str] = Field(default_factory=list)
    emotional_color: str = ""


class ScriptLine(BaseModel):
    schema_version: str = "1.0"
    id: str
    text: str
    purpose: Literal["content", "outro"] = "content"
    claim_id: str | None = None
    source_marker: str | None = None
    arc_beat: int | None = Field(default=None, ge=1, le=7)
    explainer_layer_id: str | None = None
    delivery: str | Delivery | None = None

    @model_validator(mode="after")
    def validate_delivery(self) -> "ScriptLine":
        if not isinstance(self.delivery, str):
            return self
        tags = _DELIVERY_TAG.findall(self.delivery)
        remaining = strip_delivery_tags(self.delivery)
        if "[" in remaining or "]" in remaining:
            raise ValueError("delivery contains an unclosed or nested tag")
        if any(tag not in allowed_delivery_tags() for tag in tags):
            raise ValueError("delivery contains a tag not allowed by profiles/voice.yaml")
        if _normalized_delivery(remaining) != _normalized_delivery(self.text):
            raise ValueError("delivery must match text after removing tags and normalizing punctuation")
        return self

    def tts_text(self, *, expressive: bool = True) -> str:
        """Captions always retain text; only v3 receives expressive brackets."""
        if isinstance(self.delivery, str):
            return self.delivery if expressive else strip_delivery_tags(self.delivery)
        return self.text

    def delivery_beats(self) -> tuple[dict[str, Any], ...]:
        if isinstance(self.delivery, Delivery):
            return (self.delivery.model_dump(mode="json"),)
        return ()


class Script(BaseModel):
    schema_version: str = "1.0"
    title: str
    format_profile: Literal["hook_outro_v1", "explain_first_v1"] = "explain_first_v1"
    language: str = "vi"
    lines: list[ScriptLine] = Field(default_factory=list)
