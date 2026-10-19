import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.long_form import clip_render_input
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_video_packet
from tests.helpers import create_long_form_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _runner(calls: list[list[str]]):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0
    return run


def _produced(tmp_path: Path) -> tuple[Path, list[list[str]]]:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    calls: list[list[str]] = []
    produce_project(project_dir, SilentTTS(), _runner(calls))
    return project_dir, calls


def test_clip_render_input_is_vertical_and_retimed(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    board = Storyboard.model_validate(
        read_yaml(project_dir / "revisions/001/storyboard/storyboard.yaml")
    )
    result = clip_render_input(board, board.scenes[2:4], "audio/clips/CL02.wav")
    assert (result.format_profile, result.width, result.height) == ("vertical_clip", 1080, 1920)
    assert [(s.id, s.start_frame, s.chapter_id) for s in result.scenes] == [
        ("S03", 0, None), ("S04", 900, None)
    ]
    assert [s.narration for s in result.scenes] == [s.narration for s in board.scenes[2:4]]


@pytest.mark.parametrize("artwork", [False, True])
def test_produce_renders_each_clip_vertical(tmp_path: Path, artwork_brand, monkeypatch, artwork) -> None:
    if artwork:
        from healthvideo.storage.files import write_yaml_atomic
        from healthvideo.workflows import produce

        data, _root = artwork_brand
        profile = tmp_path / 'artwork-brand.yaml'
        write_yaml_atomic(profile, data)
        monkeypatch.setattr(produce, 'BRAND_PROFILE_PATH', profile)
    project_dir, calls = _produced(tmp_path)
    renders = project_dir / "revisions" / "001" / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"] == {
        "CL01": "clips/CL01.mp4", "CL02": "clips/CL02.mp4", "CL03": "clips/CL03.mp4"
    }
    clip_input = json.loads(
        (renders / "clips" / "CL01.render-input.json").read_text(encoding="utf-8")
    )
    assert (clip_input["width"], clip_input["height"]) == (1080, 1920)
    assert [scene["id"] for scene in clip_input["scenes"]] == ["S01", "S02"]
    assert clip_input["youtube_cta"]["duration_frames"] == 90
    mascot = renders / clip_input["youtube_cta"]["mascot_path"]
    if artwork:
        assert mascot.suffix == '.png'
        assert mascot.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    else:
        assert b"mascot-pose-welcome" in mascot.read_bytes()
        assert b"<text" not in mascot.read_bytes()
    assets = read_yaml(renders / "clips/cta/asset-manifest.yaml")
    assert assets["assets"][0]["kind"] == "mascot_reaction"
    assert assets["assets"][0]["semantic"] is False
    from healthvideo.storage.files import sha256_file
    assert assets["assets"][0]["sha256"] == sha256_file(mascot)
    rights = read_yaml(renders / "clips/cta/license-ledger.yaml")
    assert rights["entries"][0]["sha256"] == sha256_file(mascot)
    assert (renders / "audio" / "clips" / "CL01.wav").is_file()
    assert all((renders / relative).is_file() for relative in manifest["clips"].values())
    assert calls[-1][0] == "ffmpeg"
    clip_calls = [c for c in calls if c[0] != "ffmpeg" and not any(a.startswith("--frames") for a in c)]
    assert len(clip_calls) == 3
    html = render_video_packet(renders.parent)
    assert html.count("mascot đang dùng hình tạm") == (0 if artwork else 1)
    # The informational warning must allow Gate 2 approval in both cases.
    approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)


def test_video_gate_binds_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)
    assert {f"renders/clips/CL0{n}.mp4" for n in (1, 2, 3)} <= record.artifact_hashes.keys()


def test_video_gate_refuses_missing_clip(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    (project_dir / "revisions/001/renders/clips/CL02.mp4").unlink()
    with pytest.raises(FileNotFoundError, match="renders/clips/CL02.mp4"):
        approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)


def test_video_packet_lists_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    html = render_video_packet(project_dir / "revisions" / "001")
    assert "../renders/clips/CL01.mp4" in html


def test_mascot_warning_in_both_review_packets_and_produce_qa(tmp_path: Path) -> None:
    from healthvideo.domain.brand import MascotPose
    from healthvideo.workflows.review_html import render_medical_packet
    from healthvideo.workflows.visual_assets import create_mascot_reaction_asset

    project = create_long_form_project_fixture(tmp_path)
    revision = project / "revisions/001"
    for number in (1, 2, 3):
        create_mascot_reaction_asset(
            project, scene_id=f"S{number:02d}", asset_name=f"test-guide-{number}",
            pose=MascotPose.WELCOME,
        )
    assert "Mascot share exceeds 35%" in render_medical_packet(revision)
    before = (revision / "storyboard/storyboard.yaml").read_bytes()
    approve_gate(project, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    produce_project(project, SilentTTS(), _runner([]))
    assert (revision / "storyboard/storyboard.yaml").read_bytes() == before
    assert "Mascot share exceeds 35%" in render_video_packet(revision)
    qa = json.loads((revision / "reviews/video-qa.json").read_text(encoding="utf-8"))
    assert qa["visual_budget"]["mascot_frames"] == 2700
    assert qa["visual_budget"]["warnings"]
    approve_gate(project, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)


@pytest.mark.parametrize("artwork", [False, True])
def test_clip_cta_registers_reverse_logo_and_selected_mascot(tmp_path, artwork_brand, artwork) -> None:
    from healthvideo.domain.brand import BrandProfile
    from healthvideo.domain.storyboard import Storyboard
    from healthvideo.workflows.long_form import render_clips

    data, _root = artwork_brand
    if not artwork:
        data["mascot"]["artwork"] = None
    brand = BrandProfile.model_validate(data)
    project = create_long_form_project_fixture(tmp_path / "fixture")
    board = Storyboard.model_validate(read_yaml(project / "revisions/001/storyboard/storyboard.yaml"))
    stage = tmp_path / "stage"
    def voice(text, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic")
        return 57000
    def run(argv):
        output = Path(argv[argv.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic")
        return 0
    # Existing fixture scenes each last 900 frames; two give a 60s clip plus CTA.
    render_clips({"CL01": board.scenes[:2]}, board, stage, synthesize=voice,
                 runner=run, brand=brand)
    result = json.loads((stage / "clips/CL01.render-input.json").read_text(encoding="utf-8"))
    suffix = ".png" if artwork else ".svg"
    assert result["youtube_cta"]["mascot_path"] == f"clips/cta/welcome{suffix}"
    assert result["youtube_cta"]["logo_path"] == "clips/cta/logo.svg"
    logo = stage / result["youtube_cta"]["logo_path"]
    assert b"#F7F4EC" in logo.read_bytes()
    assets = read_yaml(stage / "clips/cta/asset-manifest.yaml")["assets"]
    rights = read_yaml(stage / "clips/cta/license-ledger.yaml")["entries"]
    from healthvideo.storage.files import sha256_file
    assert len(assets) == len(rights) == 2
    for asset, entry in zip(assets, rights, strict=True):
        assert asset["sha256"] == entry["sha256"] == sha256_file(stage / asset["path"])
        assert asset["semantic"] is False
    assert assets[1]["kind"] == "flourish"
    assert assets[1]["storyboard_role"] == "brand"
