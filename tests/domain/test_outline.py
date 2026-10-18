import pytest
from pydantic import ValidationError

from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard

CHAPTERS = ("CH01", "CH02", "CH03", "CH04", "CH05")


def _chapters(ids: tuple[str, ...] = CHAPTERS, seconds: int = 240) -> list[dict]:
    return [
        {
            "id": chapter,
            "title": f"Chương {chapter}",
            "goal": "Giải thích một ý chính",
            "claim_ids": ["C01"] if chapter == "CH01" else [],
            "target_seconds": seconds,
        }
        for chapter in ids
    ]


def _outline(chapters: list[dict] | None = None) -> Outline:
    return Outline.model_validate(
        {"title": "Muối và huyết áp", "chapters": chapters or _chapters()}
    )


def _board(claims: dict[str, str] | None = None) -> Storyboard:
    claims = {"S01": "C01"} if claims is None else claims
    scenes = tuple(
        Scene(
            id=f"S{index:02d}", start_frame=(index - 1) * 900, duration_frames=900,
            narration="Nội dung", visual="whiteboard", chapter_id=chapter,
            claim_id=claims.get(f"S{index:02d}"),
        )
        for index, chapter in enumerate(CHAPTERS, start=1)
    )
    return Storyboard(title="PYH", scenes=scenes, format_profile="youtube_long")


def test_valid_outline_matches_storyboard() -> None:
    validate_outline(_outline(), _board(), {"C01"})


def test_outline_needs_five_to_eight_chapters() -> None:
    with pytest.raises(ValidationError, match="at least 5"):
        _outline(_chapters(CHAPTERS[:4], seconds=300))
    with pytest.raises(ValidationError, match="at most 8"):
        _outline(_chapters(tuple(f"CH{i:02d}" for i in range(1, 10)), seconds=120))


def test_outline_target_must_be_15_to_25_minutes() -> None:
    with pytest.raises(ValidationError, match="outline target 500 s"):
        _outline(_chapters(seconds=100))
    with pytest.raises(ValidationError, match="outline target 1600 s"):
        _outline(_chapters(seconds=320))


def test_outline_chapter_ids_unique() -> None:
    chapters = _chapters()
    chapters[1]["id"] = "CH01"
    with pytest.raises(ValidationError, match="unique"):
        _outline(chapters)


def test_outline_rejects_free_text_fields() -> None:
    chapters = _chapters()
    chapters[0]["narration"] = "Lời mới"
    with pytest.raises(ValidationError):
        _outline(chapters)


def test_outline_order_must_match_storyboard() -> None:
    chapters = _chapters()
    chapters[0], chapters[1] = chapters[1], chapters[0]
    with pytest.raises(ValueError, match="do not match storyboard"):
        validate_outline(_outline(chapters), _board(), {"C01"})


def test_outline_claim_must_exist_in_ledger() -> None:
    with pytest.raises(ValueError, match="CH01: unknown claim C01"):
        validate_outline(_outline(), _board(), set())


def test_scene_claim_must_be_planned_in_its_chapter() -> None:
    with pytest.raises(ValueError, match="Scene S02: claim C01 is not planned in chapter CH02"):
        validate_outline(_outline(), _board({"S01": "C01", "S02": "C01"}), {"C01"})


def test_outline_requires_youtube_long_storyboard() -> None:
    board = Storyboard(
        title="PYH",
        scenes=(Scene(id="S01", start_frame=0, duration_frames=1350, narration="N", visual="whiteboard"),),
    )
    with pytest.raises(ValueError, match="requires a youtube_long storyboard"):
        validate_outline(_outline(), board, {"C01"})
