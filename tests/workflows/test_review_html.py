from datetime import UTC, datetime
from pathlib import Path

from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture


def test_medical_packet_shows_public_and_technical_claim_text_escaped(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    revision_root = project_dir / "revisions" / "001"

    html = render_medical_packet(revision_root)

    assert "Giảm muối giúp hạ huyết áp ở nhiều người." in html
    assert "Giảm natri ăn vào liên quan tới hạ huyết áp." in html
    assert "Bản ghi tổng hợp cho test: giảm muối và huyết áp" in html
    assert "<script>" not in html


def test_medical_packet_notes_fields_the_model_does_not_carry_yet(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    html = render_medical_packet(project_dir / "revisions" / "001")
    assert "chưa có trong hệ thống" in html


def test_video_packet_references_the_mp4_by_relative_path_not_embedded(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=datetime(2026, 9, 11, 9, 0, tzinfo=UTC))

    html = render_video_packet(project_dir / "revisions" / "001")

    assert "renders/video.mp4" in html
    assert len(html.encode("utf-8")) < 5000
