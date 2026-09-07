import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import EvidenceHighlight, Scene, Storyboard
from healthvideo.render.input import build_render_input


def valid_highlight_scene(**overrides: object) -> Scene:
    values: dict[str, object] = {
        "id": "S01",
        "start_frame": 0,
        "duration_frames": 1350,
        "narration": "Một nghiên cứu cho thấy giảm muối có thể hạ huyết áp.",
        "source_marker": "[1]",
        "visual": "evidence_highlight",
        "evidence_highlight": EvidenceHighlight(
            image="assets/paper-r01.png",
            quote="giảm huyết áp tâm thu",
            x=0.12,
            y=0.42,
            width=0.64,
            height=0.08,
        ),
    }
    values.update(overrides)
    return Scene(**values)


def test_build_render_input_keeps_evidence_highlight_in_vertical_contract() -> None:
    board = Storyboard(title="Muối", scenes=[valid_highlight_scene()])

    result = build_render_input(board, audio_file="audio/narration.wav")

    assert result.width == 1080
    assert result.height == 1920
    assert result.fps == 30
    assert result.scenes[0].evidence_highlight.quote == "giảm huyết áp tâm thu"


@pytest.mark.parametrize(
    ("field", "value"),
    [("start_frame", -1), ("duration_frames", 0)],
)
def test_scene_rejects_invalid_frame_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match="S01"):
        valid_highlight_scene(**{field: value})


def test_highlight_rejects_bounds_outside_normalized_canvas() -> None:
    with pytest.raises(ValidationError, match=r"x \+ width"):
        EvidenceHighlight(
            image="assets/paper-r01.png",
            quote="giảm huyết áp tâm thu",
            x=0.5,
            y=0.42,
            width=0.64,
            height=0.08,
        )


@pytest.mark.parametrize(
    ("source_marker", "highlight"),
    [(None, "present"), ("[1]", None)],
)
def test_evidence_highlight_scene_requires_source_marker_and_highlight(
    source_marker: str | None, highlight: str | None
) -> None:
    values: dict[str, object] = {"source_marker": source_marker}
    if highlight is None:
        values["evidence_highlight"] = None

    with pytest.raises(ValidationError, match="S01"):
        valid_highlight_scene(**values)


def test_build_render_input_rejects_gap_with_scene_id() -> None:
    board = Storyboard(
        title="Muối",
        scenes=[
            valid_highlight_scene(duration_frames=675),
            Scene(
                id="S02",
                start_frame=700,
                duration_frames=675,
                narration="Phần kết luận.",
                visual="whiteboard",
            ),
        ],
    )

    with pytest.raises(ValueError, match="S02"):
        build_render_input(board, audio_file="audio/narration.wav")


@pytest.mark.parametrize(
    "audio_file", ["audio\\narration.wav", "/audio/narration.wav"]
)
def test_build_render_input_rejects_non_posix_relative_media_paths(
    audio_file: str,
) -> None:
    board = Storyboard(title="Muối", scenes=[valid_highlight_scene()])

    with pytest.raises(ValueError, match="audio"):
        build_render_input(board, audio_file=audio_file)


@pytest.mark.parametrize("duration_frames", [1349, 2701])
def test_build_render_input_enforces_video_duration_range(duration_frames: int) -> None:
    board = Storyboard(
        title="Muối", scenes=[valid_highlight_scene(duration_frames=duration_frames)]
    )

    with pytest.raises(ValueError, match="S01"):
        build_render_input(board, audio_file="audio/narration.wav")


def test_render_input_is_immutable() -> None:
    result = build_render_input(
        Storyboard(title="Muối", scenes=[valid_highlight_scene()]),
        audio_file="audio/narration.wav",
    )

    with pytest.raises(ValidationError):
        result.width = 720
