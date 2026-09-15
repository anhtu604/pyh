import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import calculate_visual_budget
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture
from tests.workflows.test_gate_review import _author_ai_clip, _create_ai_project


def _enable_packet_budget(project_dir: Path, *, override: bool = False) -> None:
    storyboard_path = project_dir / "revisions/001/storyboard/storyboard.yaml"
    board = read_yaml(storyboard_path)
    board["visual_budget_profile"] = "m6_5_v1"
    highlight = deepcopy(board["scenes"][0])
    board["scenes"] = [
        {
            "id": "S01",
            "start_frame": 0,
            "duration_frames": 900,
            "narration": "Visual whiteboard synthetic.",
            "claim_id": "C01",
            "source_marker": "[1]",
            "visual": "whiteboard",
        },
        {
            **highlight,
            "id": "S02",
            "start_frame": 900,
            "duration_frames": 300,
        },
    ]
    if override:
        board["visual_budget_override"] = {
            "rationale": "Cần <b>chart</b> cho fixture & review.",
            "whiteboard_svg": {"min_percent": 70, "max_percent": 80},
            "chart_crop": {"min_percent": 20, "max_percent": 30},
            "ai_clip": {"min_percent": 0, "max_percent": 0},
        }
    write_yaml_atomic(storyboard_path, board)


def test_medical_packet_shows_public_and_technical_claim_text_escaped(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    revision_root = project_dir / "revisions" / "001"

    html = render_medical_packet(revision_root)

    assert "Giảm muối giúp hạ huyết áp ở nhiều người." in html
    assert "Giảm natri ăn vào liên quan tới hạ huyết áp." in html
    assert "Bản ghi tổng hợp cho test: giảm muối và huyết áp" in html
    assert "<script>" not in html


def test_medical_packet_notes_fields_the_model_does_not_carry_yet(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    html = render_medical_packet(project_dir / "revisions" / "001")
    assert "chưa có trong hệ thống" in html


def test_medical_packet_shows_safe_ai_clip_provenance_and_rights(tmp_path: Path) -> None:
    project_dir = _create_ai_project(tmp_path)
    _author_ai_clip(project_dir)

    html = render_medical_packet(project_dir / "revisions/001")

    assert "AI clip M6.6" in html
    assert "google_vertex_ai" in html and "veo-3.1-fast-generate-001" in html
    assert "4000 ms" in html and "operator-recorded provider terms" in html
    assert "PRIVATE PROMPT" not in html and "&lt;script&gt;" not in html
    assert "cloud project" not in html.lower() and "token" not in html.lower()


def test_video_packet_references_the_mp4_by_relative_path_not_embedded(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(
        project_dir, now=datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
    )

    html = render_video_packet(project_dir / "revisions" / "001")

    assert "renders/video.mp4" in html
    assert len(html.encode("utf-8")) < 5000


def test_medical_packet_renders_certainty_and_population_when_present(
    tmp_path: Path,
) -> None:
    from healthvideo.storage.files import read_yaml, write_yaml_atomic

    project_dir = create_v2_project_fixture(tmp_path)
    ledger_path = project_dir / "revisions" / "001" / "evidence" / "ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["certainty"] = "moderate"
    ledger["claims"][0]["population"] = "Người trưởng thành"
    write_yaml_atomic(ledger_path, ledger)

    html = render_medical_packet(project_dir / "revisions" / "001")
    assert "moderate" in html
    assert "Người trưởng thành" in html


def test_medical_packet_shows_cropped_highlight_provenance_without_source_url(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    revision = project_dir / "revisions/001"
    storyboard_path = revision / "storyboard/storyboard.yaml"
    storyboard = read_yaml(storyboard_path)
    highlight = next(
        scene["evidence_highlight"]
        for scene in storyboard["scenes"]
        if scene["visual"] == "evidence_highlight"
    )
    highlight.update(
        {
            "source_id": "R01",
            "page": 3,
            "quote": "<script>alert(1)</script>",
            "image": "assets/paper-crop.png",
        }
    )
    write_yaml_atomic(storyboard_path, storyboard)
    html = render_medical_packet(revision)
    assert "R01" in html and "paper-crop.png" in html and "[1]" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>" not in html
    assert "example.invalid" not in html


def test_medical_packet_shows_deterministic_m6_5_visual_budget(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    _enable_packet_budget(project_dir)

    html = render_medical_packet(project_dir / "revisions/001")

    assert "Ngân sách visual M6.5" in html
    assert "m6_5_v1" in html
    assert "1200" in html
    assert "whiteboard_svg" in html and "900" in html and "7500 bp" in html
    assert "chart_crop" in html and "300" in html and "2500 bp" in html
    assert "65–75%" in html and "15–25%" in html and "0–10%" in html
    assert "Override: không" in html and "Kết quả: đạt" in html


def test_medical_packet_escapes_override_rationale(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    _enable_packet_budget(project_dir, override=True)

    html = render_medical_packet(project_dir / "revisions/001")

    assert "Override: có" in html
    assert "Cần &lt;b&gt;chart&lt;/b&gt; cho fixture &amp; review." in html
    assert "<b>chart</b>" not in html


def test_legacy_medical_packet_has_no_m6_5_section(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)

    html = render_medical_packet(project_dir / "revisions/001")

    assert "Ngân sách visual M6.5" not in html


@pytest.mark.parametrize(
    ("qa_budget", "status"),
    [
        ("recomputed", "QA production: khớp report tái tính"),
        ("tampered", "QA production: không khớp report tái tính"),
        ("missing", "QA production: thiếu visual_budget"),
    ],
)
def test_video_packet_shows_recomputed_m6_5_budget_against_recorded_qa(
    tmp_path: Path, qa_budget: str, status: str
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    _enable_packet_budget(project_dir)
    revision = project_dir / "revisions/001"
    board = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    recorded = calculate_visual_budget(board).model_dump(mode="json")
    if qa_budget == "tampered":
        recorded["override_active"] = 0
    qa = {"input_hash": "0" * 64}
    if qa_budget != "missing":
        qa["visual_budget"] = recorded
    (revision / "reviews").mkdir(parents=True, exist_ok=True)
    (revision / "reviews/video-qa.json").write_text(json.dumps(qa), encoding="utf-8")

    html = render_video_packet(revision)

    assert "Ngân sách visual M6.5" in html
    assert "7500 bp" in html and "2500 bp" in html and "Kết quả: đạt" in html
    assert status in html


def test_legacy_video_packet_has_no_m6_5_section(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(
        project_dir, now=datetime(2026, 9, 11, 9, 0, tzinfo=UTC)
    )

    html = render_video_packet(project_dir / "revisions/001")

    assert "Ngân sách visual M6.5" not in html and "QA production" not in html
