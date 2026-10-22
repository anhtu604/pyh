"""Tests for default factory queue runner dependencies."""

from __future__ import annotations

import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.factory_deps import (
    changed_code_paths,
    default_run_deps,
)
from healthvideo.workflows.gate_review import reject_gate
from tests.helpers import create_v2_project_fixture


def _queue_entry(slug: str = "an-man-va-huyet-ap") -> QueueEntry:
    return QueueEntry(
        slug=slug,
        title="Ăn mặn và huyết áp",
        question="Vì sao ăn mặn làm tăng huyết áp?",
        doctor_note="Nhấn mạnh vai trò giữ nước ở thận.",
        added=date(2026, 10, 22),
    )


def test_create_project_selects_card_from_queue_entry(tmp_path: Path) -> None:
    deps = default_run_deps(tmp_path)
    entry = _queue_entry()

    project_dir = deps.create_project(tmp_path, entry)

    assert project_dir == tmp_path / "projects" / entry.slug
    layout = resolve_project_layout(project_dir)
    assert layout.manifest.state == WorkflowState.TOPIC_SELECTED
    card_path = layout.artifact_root / "topic" / "card.yaml"
    assert card_path.is_file()
    card = TopicCard.model_validate(read_yaml(card_path))
    assert card.slug == entry.slug
    assert card.title == entry.title
    assert card.question == entry.question
    assert card.status == "selected"
    assert card.signals == []
    assert card.scores == TopicScores()


def test_read_state(tmp_path: Path) -> None:
    deps = default_run_deps(tmp_path)
    entry = _queue_entry("do-huyet-ap-tai-nha")
    project_dir = deps.create_project(tmp_path, entry)

    assert deps.read_state(project_dir) == WorkflowState.TOPIC_SELECTED

    manifest = read_yaml(project_dir / "project.yaml")
    manifest["state"] = WorkflowState.EVIDENCE_READY.value
    write_yaml_atomic(project_dir / "project.yaml", manifest)

    assert deps.read_state(project_dir) == WorkflowState.EVIDENCE_READY


def test_reject_note_reads_latest_rejection(tmp_path: Path) -> None:
    deps = default_run_deps(tmp_path)
    project_dir = create_v2_project_fixture(
        tmp_path,
        state=WorkflowState.AWAITING_MEDICAL_REVIEW,
    )

    assert deps.reject_note(project_dir) is None

    reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS An",
        reason="Lý do cũ: thiếu trích dẫn RCT.",
        resume_state=WorkflowState.DRAFT_READY,
        now=datetime(2026, 10, 22, 8, 0, tzinfo=UTC),
    )
    assert deps.reject_note(project_dir) == "Lý do cũ: thiếu trích dẫn RCT."

    manifest = read_yaml(project_dir / "project.yaml")
    manifest["state"] = WorkflowState.AWAITING_MEDICAL_REVIEW.value
    manifest["side_state"] = None
    write_yaml_atomic(project_dir / "project.yaml", manifest)
    reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer="BS An",
        reason="Lý do mới nhất: cần làm rõ cơ chế giữ natri.",
        resume_state=WorkflowState.DRAFT_READY,
        now=datetime(2026, 10, 22, 10, 30, tzinfo=UTC),
    )

    assert (
        deps.reject_note(project_dir)
        == "Lý do mới nhất: cần làm rõ cơ chế giữ natri."
    )


def test_changed_code_paths_excludes_projects_topics_cache(
    tmp_path: Path,
) -> None:
    captured_calls: list[tuple[list[str], Path]] = []
    porcelain_output = (
        " M src/healthvideo/cli.py\n"
        "?? video/src/anatomy/KidneyNephrons.tsx\n"
        "M  projects/an-man-va-huyet-ap/project.yaml\n"
        "?? topics/queue.yaml\n"
        "?? topics/logs/an-man-va-huyet-ap/blocked.txt\n"
        "?? cache/tts-venv/pyvenv.cfg\n"
    )

    def fake_git_runner(
        argv: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        captured_calls.append((list(argv), kwargs["cwd"]))
        assert not kwargs.get("shell", False)
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout=porcelain_output,
            stderr="",
        )

    deps = default_run_deps(tmp_path, git_runner=fake_git_runner)
    result = deps.changed_code_paths(tmp_path)

    assert captured_calls == [(["git", "status", "--porcelain"], tmp_path)]
    assert result == [
        Path("src/healthvideo/cli.py"),
        Path("video/src/anatomy/KidneyNephrons.tsx"),
    ]
    assert changed_code_paths(tmp_path, runner=fake_git_runner) == result
