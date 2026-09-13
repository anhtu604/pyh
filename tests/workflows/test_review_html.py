from datetime import UTC, datetime
from pathlib import Path

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture


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
