"""Domain models and validators for multi-channel post drafts (spec §5.4)."""

import re
from collections.abc import Iterator, Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CLAIM_REF = re.compile(r"\[claim:([A-Za-z0-9_.-]+)\]")
_CHAPTER_TIMESTAMP_PREFIX = re.compile(
    r"^\s*\d{1,2}:\d{2}(?::\d{2})?(?=\s|$|[-–—:])\s*[-–—:]?\s*"
)
_SENTENCE_SPLIT = re.compile(r"[!?]+|\.(?!(?<=\d\.)\d)")
_DIGIT_RE = re.compile(r"\d")

TitleStr = Annotated[str, Field(min_length=1, max_length=100)]
TagStr = Annotated[str, Field(min_length=1)]


class ClipCaptions(BaseModel):
    """Per-platform captions for one vertical clip."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tiktok: str = Field(min_length=1, max_length=2200)
    shorts: str = Field(min_length=1, max_length=5000)
    reels: str = Field(min_length=1, max_length=2200)


class ThumbnailSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    headline: str = Field(min_length=1, max_length=60)
    background_prompt: str = Field(min_length=1, pattern=r"\S")
    seed: int = Field(strict=True, ge=0, lt=2**63)

    @field_validator("headline")
    @classmethod
    def _visible_headline(cls, value: str) -> str:
        if not CLAIM_REF.sub("", value).strip():
            raise ValueError("thumbnail headline must contain visible text")
        return value


class PostSet(BaseModel):
    """Multi-channel post drafts prepared before the video review gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    youtube_titles: list[TitleStr] = Field(min_length=2, max_length=3)
    youtube_description: str = Field(min_length=1, max_length=5000)
    youtube_tags: list[TagStr] = Field(default_factory=list)
    clip_captions: dict[str, ClipCaptions] = Field(default_factory=dict)
    facebook_post: str = Field(min_length=1)
    youtube_community: str = Field(min_length=1)
    thumbnail: ThumbnailSpec | None = None

    @field_validator("youtube_tags", mode="after")
    @classmethod
    def _check_tags_total_length(cls, value: list[str]) -> list[str]:
        total = sum(len(tag) for tag in value)
        if total > 500:
            raise ValueError(f"youtube_tags total length {total} exceeds 500 characters")
        return value


def iter_texts(posts: PostSet) -> Iterator[tuple[str, str]]:
    """Yield ``(field_path, text)`` for every text entry in ``posts``."""
    for index, title in enumerate(posts.youtube_titles):
        yield (f"youtube_titles[{index}]", title)
    yield ("youtube_description", posts.youtube_description)
    for index, tag in enumerate(posts.youtube_tags):
        yield (f"youtube_tags[{index}]", tag)
    for clip_id, captions in posts.clip_captions.items():
        yield (f"clip_captions[{clip_id}].tiktok", captions.tiktok)
        yield (f"clip_captions[{clip_id}].shorts", captions.shorts)
        yield (f"clip_captions[{clip_id}].reels", captions.reels)
    yield ("facebook_post", posts.facebook_post)
    yield ("youtube_community", posts.youtube_community)
    if posts.thumbnail is not None:
        yield ("thumbnail.headline", posts.thumbnail.headline)


def _split_sentences(text: str, *, strip_chapter_timestamps: bool) -> list[str]:
    sentences: list[str] = []
    for raw_line in text.splitlines():
        line = (
            _CHAPTER_TIMESTAMP_PREFIX.sub("", raw_line)
            if strip_chapter_timestamps
            else raw_line
        )
        protected = CLAIM_REF.sub(lambda m: m.group(0).replace(".", "\x00"), line)
        for piece in _SENTENCE_SPLIT.split(protected):
            restored = piece.replace("\x00", ".").strip()
            if restored:
                sentences.append(restored)
    return sentences


def _shorten(sentence: str, limit: int = 80) -> str:
    compact = " ".join(sentence.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def validate_posts(
    posts: PostSet,
    *,
    approved_claim_ids: set[str],
    chapter_titles: Sequence[str],
    source_labels: Sequence[str],
) -> list[str]:
    """Return validation errors for ``posts`` (empty list when valid)."""
    errors: list[str] = []

    if not 2 <= len(posts.youtube_titles) <= 3:
        errors.append(
            f"youtube_titles: cần 2–3 tiêu đề, hiện có {len(posts.youtube_titles)}"
        )

    ordered_chapters = sorted(
        (title for title in chapter_titles if title),
        key=len,
        reverse=True,
    )

    for field_path, text in iter_texts(posts):
        is_description = field_path == "youtube_description"
        for sentence in _split_sentences(
            text, strip_chapter_timestamps=is_description
        ):
            without_claims = CLAIM_REF.sub("", sentence)
            for chapter_title in (
                ordered_chapters if field_path != "thumbnail.headline" else ()
            ):
                without_claims = without_claims.replace(chapter_title, "")
            if _DIGIT_RE.search(without_claims) and not CLAIM_REF.search(sentence):
                errors.append(
                    f"{field_path}: câu có số liệu thiếu [claim:…]: {_shorten(sentence)}"
                )

        for match in CLAIM_REF.finditer(text):
            claim_id = match.group(1)
            if claim_id not in approved_claim_ids:
                errors.append(f"{field_path}: claim chưa duyệt y khoa: {claim_id}")

    for chapter_title in chapter_titles:
        if chapter_title not in posts.youtube_description:
            errors.append(f"youtube_description: thiếu chương: {chapter_title}")

    for source_label in source_labels:
        if source_label not in posts.youtube_description:
            errors.append(f"youtube_description: thiếu nguồn: {source_label}")

    return errors
