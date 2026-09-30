import pytest
from pydantic import ValidationError

from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.storyboard import Scene, Storyboard

LAYOUT = (("S01", "CH01", 900, "C01"), ("S02", "CH02", 900, "C02"), ("S03", "CH03", 900, None),
          ("S04", "CH04", 900, None), ("S05", "CH05", 900, None), ("S06", "CH05", 600, None))


def _board(profile: str = "youtube_long") -> Storyboard:
    scenes, start = [], 0
    for scene_id, chapter, frames, claim in LAYOUT:
        scenes.append(Scene(
            id=scene_id, start_frame=start, duration_frames=frames, narration=f"Lời {scene_id}",
            visual="whiteboard", claim_id=claim,
            chapter_id=chapter if profile == "youtube_long" else None,
        ))
        start += frames
    return Storyboard(title="PYH", scenes=tuple(scenes), format_profile=profile)


def _claim(claim_id: str, caveats: list[str]) -> EvidenceClaim:
    return EvidenceClaim(
        id=claim_id, text_public="Câu công chúng", text_technical="Mệnh đề kỹ thuật",
        type="evidence", sources=["R01"], caveat_claim_ids=caveats,
    )


CLAIMS = {"C01": _claim("C01", ["C02"]), "C02": _claim("C02", [])}


def _clip(clip_id: str, first: str, last: str, **extra: str) -> dict:
    return {"id": clip_id, "title": f"Clip {clip_id}", "first_scene_id": first,
            "last_scene_id": last, **extra}


def _plan(*clips: dict) -> ClipPlan:
    if not clips:
        clips = (_clip("CL01", "S01", "S02"), _clip("CL02", "S03", "S04"),
                 _clip("CL03", "S05", "S06"))
    return ClipPlan.model_validate({"clips": list(clips)})


def _with(first: dict) -> ClipPlan:
    return _plan(first, _clip("CL02", "S03", "S04"), _clip("CL03", "S05", "S06"))


def test_valid_plan_resolves_scenes_in_order() -> None:
    resolved = validate_clip_plan(_plan(), _board(), CLAIMS)
    assert [scene.id for scene in resolved["CL01"]] == ["S01", "S02"]
    assert list(resolved) == ["CL01", "CL02", "CL03"]


def test_hook_and_outro_wrap_the_range() -> None:
    plan = _with(_clip("CL01", "S03", "S03", hook_scene_id="S02", outro_scene_id="S04"))
    resolved = validate_clip_plan(plan, _board(), CLAIMS)
    assert [scene.id for scene in resolved["CL01"]] == ["S02", "S03", "S04"]


def test_claim_without_its_caveat_is_blocked() -> None:
    plan = _with(_clip("CL01", "S01", "S01", outro_scene_id="S03"))
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02 in the clip"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_hook_claim_also_needs_its_caveat() -> None:
    plan = _with(_clip("CL01", "S03", "S04", hook_scene_id="S01"))
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_claim_must_be_in_ledger() -> None:
    with pytest.raises(ValueError, match="CL01: claim C01 is not in the ledger"):
        validate_clip_plan(_plan(), _board(), {})


def test_caveat_must_be_in_ledger() -> None:
    with pytest.raises(ValueError, match="CL01: caveat C02 of claim C01 is not in the ledger"):
        validate_clip_plan(_plan(), _board(), {"C01": CLAIMS["C01"]})


@pytest.mark.parametrize(("first", "last", "frames"), [("S06", "S06", 600), ("S01", "S04", 3600)])
def test_clip_must_last_30_to_90_seconds(first: str, last: str, frames: int) -> None:
    plan = _with(_clip("CL01", first, last))
    with pytest.raises(ValueError, match=f"CL01: duration {frames} frames"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_unknown_scene() -> None:
    with pytest.raises(ValueError, match="CL01: unknown scene S99"):
        validate_clip_plan(_with(_clip("CL01", "S01", "S99")), _board(), CLAIMS)


def test_reversed_range() -> None:
    with pytest.raises(ValueError, match="CL01: first scene must not come after last scene"):
        validate_clip_plan(_with(_clip("CL01", "S02", "S01")), _board(), CLAIMS)


def test_hook_inside_range() -> None:
    plan = _with(_clip("CL01", "S01", "S02", hook_scene_id="S02"))
    with pytest.raises(ValueError, match="CL01: scene S02 is already inside the clip range"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_plan_needs_three_to_six_clips() -> None:
    with pytest.raises(ValidationError):
        _plan(_clip("CL01", "S01", "S02"), _clip("CL02", "S03", "S04"))
    with pytest.raises(ValidationError):
        _plan(*(_clip(f"CL{i:02d}", "S03", "S04") for i in range(1, 8)))


def test_clip_ids_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        _plan(_clip("CL01", "S01", "S02"), _clip("CL01", "S03", "S04"), _clip("CL03", "S05", "S06"))


def test_clip_cannot_carry_new_wording() -> None:
    with pytest.raises(ValidationError):
        _with(_clip("CL01", "S01", "S02", narration="Câu mới chưa duyệt"))


def test_clip_plan_requires_youtube_long_storyboard() -> None:
    with pytest.raises(ValueError, match="requires a youtube_long storyboard"):
        validate_clip_plan(_plan(), _board("vertical_clip"), CLAIMS)


def test_legacy_claim_has_no_caveats() -> None:
    claim = EvidenceClaim(id="C09", text_public="a", text_technical="b", type="evidence")
    assert claim.caveat_claim_ids == []
