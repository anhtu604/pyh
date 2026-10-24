"""Tests for default factory queue runner dependencies."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from healthvideo.agents import AgentResult
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows.factory_deps import (
    changed_code_paths,
    code_snapshot,
    default_run_deps,
)
from healthvideo.workflows.gate_review import reject_gate
from healthvideo.workflows.runner import run_queue
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
        " M src/healthvideo/cli.py\0"
        "?? video/src/anatomy/KidneyNephrons.tsx\0"
        "M  projects/an-man-va-huyet-ap/project.yaml\0"
        "?? topics/queue.yaml\0"
        "?? topics/logs/an-man-va-huyet-ap/blocked.txt\0"
        "?? cache/tts-venv/pyvenv.cfg\0"
        "?? .claude/skills/example.md\0"
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

    assert captured_calls == [(
        ["git", "status", "--porcelain", "-z", "--untracked-files=all"], tmp_path,
    )]
    assert result == [
        Path("src/healthvideo/cli.py"),
        Path("video/src/anatomy/KidneyNephrons.tsx"),
    ]
    assert changed_code_paths(tmp_path, runner=fake_git_runner) == result


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)


def test_changed_code_paths_ignores_preexisting_untracked(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    for name in ("New Recording.m4a", ".remotion/cache", ".agents/skills/test.md"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"existing")
    before = code_snapshot(tmp_path)
    assert changed_code_paths(tmp_path, before) == []


def test_changed_code_paths_reports_new_and_modified(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    tracked = tmp_path / "tracked.py"
    tracked.write_text("original", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    tracked.write_text("already dirty", encoding="utf-8")
    untracked = tmp_path / "existing untracked.py"
    untracked.write_text("old", encoding="utf-8")
    before = code_snapshot(tmp_path)
    tracked.write_text("changed again", encoding="utf-8")
    untracked.write_text("new", encoding="utf-8")
    (tmp_path / "new.py").write_text("new", encoding="utf-8")
    for directory in ("projects", "topics", "cache", ".claude"):
        path = tmp_path / directory / "ignored.py"
        path.parent.mkdir()
        path.write_text("ignore", encoding="utf-8")
    assert set(changed_code_paths(tmp_path, before)) == {
        Path("tracked.py"), Path("existing untracked.py"), Path("new.py"),
    }


def test_run_queue_snapshots_each_agent_step(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "preexisting.py").write_text("leave alone", encoding="utf-8")
    for slug in ("first-topic", "second-topic"):
        add_to_queue(tmp_path, _queue_entry(slug))

    calls = 0

    def invoke(agents, prompt, *, cwd, log_dir):
        nonlocal calls
        calls += 1
        (cwd / "shared.py").write_text(str(calls), encoding="utf-8")
        manifest_path = cwd / "projects" / log_dir.name / "project.yaml"
        manifest = read_yaml(manifest_path)
        manifest["state"] = (
            "evidence_ready" if manifest["state"] == "topic_selected"
            else "awaiting_medical_review"
        )
        write_yaml_atomic(manifest_path, manifest)
        return AgentResult("fake", True, False, log_dir / "fake.log")

    deps = replace(default_run_deps(tmp_path), invoke=invoke)
    report = run_queue(tmp_path, deps)
    assert report.at_gate == ["first-topic", "second-topic"]
    assert report.code_changes == [Path("shared.py")]
    entries = read_yaml(tmp_path / "topics/code-review.yaml")["entries"]
    assert [(entry["path"], entry["slug"]) for entry in entries] == [
        ("shared.py", "first-topic"), ("shared.py", "first-topic"),
        ("shared.py", "second-topic"), ("shared.py", "second-topic"),
    ]


def test_changed_code_paths_reports_removed_untracked(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    path = tmp_path / "removed.py"
    path.write_text("old", encoding="utf-8")
    before = code_snapshot(tmp_path)
    path.unlink()
    assert changed_code_paths(tmp_path, before) == [Path("removed.py")]


def test_reject_note_reads_latest_reopen(tmp_path: Path) -> None:
    deps = default_run_deps(tmp_path)
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    reject_gate(
        project_dir, GateKind.MEDICAL, reviewer="BS An", reason="Lý do từ chối cũ.",
        resume_state=WorkflowState.DRAFT_READY, now=datetime(2026, 10, 22, 8, 0, tzinfo=UTC),
    )
    write_yaml_atomic(project_dir / "revisions/001/reviews/medical/99991231T000000000000-reopened.yaml",
                      {"reason": "Viết lại theo văn phong mới."})
    assert deps.reject_note(project_dir) == "Viết lại theo văn phong mới."
