"""Tests for multi-channel posts in the queue runner, video review gate/packet, and packaging."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from healthvideo.agents import AgentResult
from healthvideo.cli import app
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.factory_deps import posts_ready, read_state
from healthvideo.workflows.gate_review import (
    VIDEO_APPROVAL_ARTIFACT,
    approve_gate,
)
from healthvideo.workflows.package import package_project
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_video_packet
from healthvideo.workflows.runner import RunDeps, run_queue
from tests.helpers import (
    advance_v2_project_to_video_review,
    create_v2_project_fixture,
    write_posts_fixture,
)

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _fake_renderer(argv: list[str]) -> int:
    output = Path(argv[argv.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"synthetic-v2-mp4")
    return 0


def _log_file(log_dir: Path, name: str = "fake-agent.log") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / name
    path.write_text("fake agent log\n", encoding="utf-8")
    return path


def test_run_queue_runs_posts_step_before_produce(tmp_path: Path) -> None:
    entry = QueueEntry(
        slug="muoi-va-huyet-ap-v2",
        title="Ăn mặn và tăng huyết áp",
        question="Vì sao ăn mặn làm tăng huyết áp?",
        doctor_note="Nhấn mạnh giảm muối từ từ.",
        added=date(2026, 10, 22),
    )
    add_to_queue(tmp_path, entry)

    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    project_dir = create_v2_project_fixture(
        projects_root, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision_root = project_dir / "revisions" / "001"
    posts_path = revision_root / "posts" / "posts.yaml"
    posts_path.unlink()
    assert not posts_ready(project_dir)

    events: list[str] = []
    prompts: list[str] = []

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        events.append("posts")
        prompts.append(prompt)
        write_posts_fixture(revision_root)
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    def fake_produce(target_dir: Path) -> None:
        assert posts_ready(target_dir)
        events.append("produce")
        produce_project(target_dir, SilentTTS(), _fake_renderer)

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=read_state,
        reject_note=lambda _p: None,
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
        posts_ready=posts_ready,
    )

    report = run_queue(tmp_path, deps)

    assert events == ["posts", "produce"]
    assert len(prompts) == 1
    assert "healthvideo step posts-check" in prompts[0]
    assert read_state(project_dir) == WorkflowState.AWAITING_VIDEO_REVIEW
    assert report.advanced == [entry.slug]
    assert report.at_gate == [entry.slug]
    assert report.blocked == []


def test_posts_step_success_without_state_change(tmp_path: Path) -> None:
    entry = QueueEntry(
        slug="muoi-va-huyet-ap-v2",
        title="Ăn mặn và tăng huyết áp",
        question="Vì sao ăn mặn làm tăng huyết áp?",
        doctor_note=None,
        added=date(2026, 10, 22),
    )
    add_to_queue(tmp_path, entry)

    projects_root = tmp_path / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    project_dir = create_v2_project_fixture(
        projects_root, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    revision_root = project_dir / "revisions" / "001"
    (revision_root / "posts" / "posts.yaml").unlink()

    def write_valid_posts_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        write_posts_fixture(revision_root)
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=read_state,
        reject_note=lambda _p: None,
        python_steps={"produce": lambda _p: None},
        changed_code_paths=lambda _root: [],
        invoke=write_valid_posts_invoke,
        posts_ready=posts_ready,
    )

    report = run_queue(tmp_path, deps, once=True)

    assert read_state(project_dir) == WorkflowState.MEDICALLY_APPROVED
    assert posts_ready(project_dir) is True
    assert report.advanced == [entry.slug]
    assert report.blocked == []
    assert not (tmp_path / "topics" / "logs" / entry.slug / "blocked.txt").exists()

    # When the posts agent fails to leave valid posts.yaml, the topic is blocked.
    (revision_root / "posts" / "posts.yaml").unlink()

    def noop_posts_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "noop-posts.log"),
        )

    failing_deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=read_state,
        reject_note=lambda _p: None,
        python_steps={"produce": lambda _p: None},
        changed_code_paths=lambda _root: [],
        invoke=noop_posts_invoke,
        posts_ready=posts_ready,
    )

    failing_report = run_queue(tmp_path, failing_deps, once=True)
    assert failing_report.blocked == [entry.slug]
    assert failing_report.advanced == []


def test_video_gate_refuses_missing_or_invalid_posts(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)
    revision_root = project_dir / "revisions" / "001"
    posts_path = revision_root / "posts" / "posts.yaml"

    # 1. Missing posts.yaml is refused.
    posts_path.unlink()
    with pytest.raises((FileNotFoundError, ValueError), match="posts/posts.yaml"):
        approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    assert not (revision_root / VIDEO_APPROVAL_ARTIFACT).exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"

    # 2. Invalid posts.yaml (unclaimed number + unapproved claim) is refused.
    write_posts_fixture(revision_root)
    invalid_posts = read_yaml(posts_path)
    invalid_posts["facebook_post"] = (
        "Giảm muối giúp hạ 10 mmHg huyết áp tâm thu. "
        "Số liệu chưa duyệt [claim:C99]."
    )
    write_yaml_atomic(posts_path, invalid_posts)

    with pytest.raises(ValueError, match="posts/posts.yaml"):
        approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    assert not (revision_root / VIDEO_APPROVAL_ARTIFACT).exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"

    # 3. Valid posts.yaml is approved and hashed in the video approval record.
    write_posts_fixture(revision_root)
    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    assert "posts/posts.yaml" in record.artifact_hashes
    assert (revision_root / VIDEO_APPROVAL_ARTIFACT).is_file()
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"


def test_video_packet_contains_posts(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)
    revision_root = project_dir / "revisions" / "001"
    posts_path = revision_root / "posts" / "posts.yaml"
    posts_data = read_yaml(posts_path)
    posts_data["youtube_titles"] = [
        "Tiêu đề YouTube <1> & thử [claim:C01]",
        "Tiêu đề YouTube thứ hai",
    ]
    posts_data["youtube_tags"] = ["tăng huyết áp", "muối & <tim>"]
    posts_data["clip_captions"] = {
        "CL01": {
            "tiktok": "TikTok caption <b>thử</b>",
            "shorts": "Shorts caption & thử",
            "reels": "Reels caption thử",
        }
    }
    posts_data["facebook_post"] = "Bài Facebook <script>alert(1)</script> an toàn."
    posts_data["youtube_community"] = "Câu hỏi Community & thảo luận?"
    write_yaml_atomic(posts_path, posts_data)

    html = render_video_packet(revision_root)

    assert "<h2>Bài đăng</h2>" in html
    assert "Tiêu đề YouTube &lt;1&gt; &amp; thử [claim:C01]" in html
    assert "Tiêu đề YouTube thứ hai" in html
    assert "muối &amp; &lt;tim&gt;" in html
    assert "CL01" in html
    assert "TikTok caption &lt;b&gt;thử&lt;/b&gt;" in html
    assert "Shorts caption &amp; thử" in html
    assert "Reels caption thử" in html
    assert "Bài Facebook &lt;script&gt;alert(1)&lt;/script&gt; an toàn." in html
    assert "Câu hỏi Community &amp; thảo luận?" in html
    assert "<script>alert(1)</script>" not in html


def test_package_copies_approved_posts_unchanged(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision_root = project_dir / "revisions" / "001"
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    produce_project(project_dir, SilentTTS(), _fake_renderer)

    posts_path = revision_root / "posts" / "posts.yaml"
    raw_with_comment = (
        "# Bản bài đăng đã được bác sĩ duyệt nguyên văn\n"
        + posts_path.read_text(encoding="utf-8")
    )
    posts_path.write_text(raw_with_comment, encoding="utf-8")
    expected_bytes = posts_path.read_bytes()

    approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)
    publish_dir = package_project(project_dir)

    assert (publish_dir / "posts.yaml").read_bytes() == expected_bytes
    posts_md = (publish_dir / "posts.md").read_text(encoding="utf-8")
    assert "# Bài đăng đa kênh" in posts_md
    assert "Ăn mặn và tăng huyết áp: cơ chế cần biết" in posts_md
    assert "Nhiều người ăn mặn mà không biết huyết áp đang tăng âm thầm." in posts_md
    assert "Bạn thường kiểm tra lượng muối ăn vào bằng cách nào?" in posts_md


def test_post_edit_after_video_approval_blocks_package(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    revision_root = project_dir / "revisions" / "001"
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    produce_project(project_dir, SilentTTS(), _fake_renderer)
    approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)

    posts_path = revision_root / "posts" / "posts.yaml"
    posts_data = read_yaml(posts_path)
    posts_data["youtube_community"] = "Nội dung bị sửa sau khi đã duyệt cổng video."
    write_yaml_atomic(posts_path, posts_data)

    with pytest.raises(ValueError, match="video approval|posts/posts.yaml"):
        package_project(project_dir)

    assert not (revision_root / "publish").exists()
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"


def test_posts_check_cli_reports_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)
    revision_root = project_dir / "revisions" / "001"
    posts_path = revision_root / "posts" / "posts.yaml"

    ok_result = runner.invoke(app, ["step", "posts-check", str(project_dir)])
    assert ok_result.exit_code == 0, ok_result.output
    assert ok_result.stdout.strip() == ""

    bad_posts = read_yaml(posts_path)
    bad_posts["facebook_post"] = "Giảm muối hạ 10 mmHg huyết áp tâm thu."
    bad_posts["youtube_community"] = "Giảm 20% nguy cơ tim mạch [claim:C99]."
    write_yaml_atomic(posts_path, bad_posts)

    err_result = runner.invoke(app, ["step", "posts-check", str(project_dir)])
    assert err_result.exit_code == 1
    assert "facebook_post: câu có số liệu thiếu [claim:…]:" in err_result.stdout
    assert "youtube_community: claim chưa duyệt y khoa: C99" in err_result.stdout
