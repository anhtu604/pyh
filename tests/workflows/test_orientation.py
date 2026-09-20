"""Resumable, source-bound orientation research before the editorial boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.orientation import (
    CompletedOrientation,
    EditorialOption,
    OrientationScope,
    SourceBackedContext,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.topic import TopicCard
from healthvideo.storage.files import read_yaml
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.workflows.create_project_v2 import create_project_v2
from healthvideo.workflows.orientation import (
    begin_orientation,
    complete_orientation,
    read_authoritative_orientation,
    run_orientation_search,
)
from healthvideo.workflows.topic import select_topic

FROZEN_NOW = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)

SCOPE = OrientationScope(
    topic_question="Muối ảnh hưởng huyết áp như thế nào?",
    intended_audience="Người trưởng thành",
    scope=("Dinh dưỡng phòng bệnh",),
    exclusions=("Không tư vấn cá nhân hóa",),
)


class StubClient:
    """A minimal literature client that returns a fixed candidate list."""

    def __init__(self, name: str, candidates: list[CandidateSource]) -> None:
        self.name = name
        self._candidates = candidates

    def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
        del query, limit
        return list(self._candidates)


class FailingClient:
    """A client whose transport fails; it must never look like a zero-result search."""

    name = "pubmed"

    def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
        del query, limit
        raise OSError("connection reset by peer")


def _candidate(source_id: str = "pubmed-9") -> CandidateSource:
    return CandidateSource(
        source_id=source_id,
        database="pubmed",
        title="Giảm natri và huyết áp",
        year=2020,
    )


def _topic_project(tmp_path: Path) -> Path:
    project = create_project_v2(tmp_path, "muoi", "Muối", now=FROZEN_NOW)
    select_topic(
        project,
        TopicCard(
            slug="muoi",
            title="Muối",
            question="Muối ảnh hưởng huyết áp như thế nào?",
        ),
        now=FROZEN_NOW,
    )
    return project


def _researching_project(tmp_path: Path) -> Path:
    project = _topic_project(tmp_path)
    begin_orientation(project, SCOPE)
    return project


def _completed(project: Path, **overrides: object) -> CompletedOrientation:
    payload: dict[str, object] = {
        "run_id": "run-001",
        "revision": "001",
        "topic_input_hash": read_yaml(
            project / "revisions/001/orientation/scope.yaml"
        )["topic_input_hash"],
        "included_source_ids": ("pubmed-9",),
        "context_points": (
            SourceBackedContext(
                text="Giảm natri liên quan tới hạ huyết áp.",
                limitation="Bằng chứng chủ yếu ở người trưởng thành.",
                source_ids=("pubmed-9",),
            ),
        ),
        "options": (
            EditorialOption(
                id="opt-1",
                title="Bắt đầu từ thói quen nêm nếm",
                framing="Khung trung tính về thói quen hằng ngày.",
                context_source_ids=("pubmed-9",),
                questions_for_doctor=("Bác sĩ muốn nhấn vào điều gì?",),
            ),
            EditorialOption(
                id="opt-2",
                title="Bắt đầu từ nhãn thực phẩm",
                framing="Khung trung tính về đọc nhãn.",
                context_source_ids=("pubmed-9",),
                questions_for_doctor=("Khán giả nào cần ưu tiên?",),
            ),
        ),
    }
    payload.update(overrides)
    return CompletedOrientation(**payload)  # type: ignore[arg-type]


def test_begin_orientation_records_scope_and_enters_research(tmp_path: Path) -> None:
    """Orientation research must be a recorded, resumable state, not an implicit step."""
    project = _topic_project(tmp_path)

    manifest = begin_orientation(project, SCOPE)

    assert manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS
    scope_file = read_yaml(project / "revisions/001/orientation/scope.yaml")
    assert scope_file["topic_question"] == SCOPE.topic_question
    assert len(scope_file["topic_input_hash"]) == 64


def test_begin_orientation_is_idempotent_for_unchanged_input(tmp_path: Path) -> None:
    """Re-running orientation on unchanged input must not fail or fork the run."""
    project = _researching_project(tmp_path)
    first = read_yaml(project / "revisions/001/orientation/scope.yaml")

    manifest = begin_orientation(project, SCOPE)

    assert manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS
    assert read_yaml(project / "revisions/001/orientation/scope.yaml") == first


def test_provider_failure_is_not_zero_results(tmp_path: Path) -> None:
    """A provider error must stay distinguishable from a valid empty search."""
    project = _researching_project(tmp_path)

    result = run_orientation_search(project, [FailingClient()], now=FROZEN_NOW)

    outcome = result.provider_outcomes[0]
    assert outcome.status == "failed"
    assert outcome.failure_class == "OSError"
    assert outcome.result_count is None
    assert result.manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS


def test_empty_provider_result_is_recorded_as_zero_results(tmp_path: Path) -> None:
    """An empty but successful search must not be reported as a provider failure."""
    project = _researching_project(tmp_path)

    result = run_orientation_search(
        project, [StubClient("europepmc", [])], now=FROZEN_NOW
    )

    outcome = result.provider_outcomes[0]
    assert (outcome.status, outcome.result_count) == ("zero_results", 0)
    assert outcome.failure_class is None


def test_search_persists_candidates_for_later_binding(tmp_path: Path) -> None:
    """Candidates are working output that a completed record must later resolve."""
    project = _researching_project(tmp_path)

    result = run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )

    assert [candidate.source_id for candidate in result.candidates] == ["pubmed-9"]
    candidate_file = project / "revisions/001/orientation/candidates.jsonl"
    assert "pubmed-9" in candidate_file.read_text(encoding="utf-8")


def test_complete_orientation_advances_to_editorial_direction(tmp_path: Path) -> None:
    """Only a validated completed record may open the human editorial boundary."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )

    manifest = complete_orientation(project, _completed(project), now=FROZEN_NOW)

    assert manifest.state is WorkflowState.AWAITING_EDITORIAL_DIRECTION
    record = project / "revisions/001/orientation/completed/run-001.yaml"
    assert record.is_file()


def test_completed_record_cannot_be_rewritten(tmp_path: Path) -> None:
    """A published completed record is history; a retry must not replace it."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )
    complete_orientation(project, _completed(project), now=FROZEN_NOW)
    original = (
        project / "revisions/001/orientation/completed/run-001.yaml"
    ).read_bytes()

    with pytest.raises(ValueError, match="orientation_research_in_progress"):
        complete_orientation(project, _completed(project), now=FROZEN_NOW)
    with pytest.raises(FileExistsError):
        write_yaml_once(
            project / "revisions/001/orientation/completed/run-001.yaml",
            {"run_id": "run-001"},
        )

    assert (
        project / "revisions/001/orientation/completed/run-001.yaml"
    ).read_bytes() == original


def test_completion_rejects_an_unresolved_source_id(tmp_path: Path) -> None:
    """An included source that no candidate produced would be a fabricated source."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )

    with pytest.raises(ValueError, match="included candidate is missing"):
        complete_orientation(
            project,
            _completed(
                project,
                included_source_ids=("pubmed-404",),
                context_points=(
                    SourceBackedContext(
                        text="Bối cảnh",
                        limitation="Giới hạn",
                        source_ids=("pubmed-404",),
                    ),
                ),
                options=(
                    EditorialOption(
                        id="opt-1",
                        title="A",
                        framing="Khung A",
                        context_source_ids=("pubmed-404",),
                        questions_for_doctor=("Câu hỏi?",),
                    ),
                    EditorialOption(
                        id="opt-2",
                        title="B",
                        framing="Khung B",
                        context_source_ids=(),
                        questions_for_doctor=("Câu hỏi?",),
                    ),
                ),
            ),
            now=FROZEN_NOW,
        )
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS


def test_completion_rejects_a_stale_topic_input_hash(tmp_path: Path) -> None:
    """Orientation output bound to different inputs must never become authoritative."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )

    with pytest.raises(ValueError, match="topic/scope input hash"):
        complete_orientation(
            project, _completed(project, topic_input_hash="0" * 64), now=FROZEN_NOW
        )


def test_completion_rejects_a_wrong_revision(tmp_path: Path) -> None:
    """A record from another revision cannot advance this revision."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )

    with pytest.raises(ValueError, match="active revision"):
        complete_orientation(
            project, _completed(project, revision="002"), now=FROZEN_NOW
        )


def test_completion_requires_the_research_state(tmp_path: Path) -> None:
    """Completion from topic selection would skip the recorded research attempt."""
    project = _topic_project(tmp_path)
    (project / "revisions/001/orientation").mkdir(parents=True)

    with pytest.raises(ValueError, match="orientation_research_in_progress"):
        complete_orientation(
            project,
            CompletedOrientation(
                run_id="run-001",
                topic_input_hash="0" * 64,
                included_source_ids=("pubmed-9",),
                context_points=(
                    SourceBackedContext(
                        text="Bối cảnh",
                        limitation="Giới hạn",
                        source_ids=("pubmed-9",),
                    ),
                ),
                options=(
                    EditorialOption(
                        id="opt-1",
                        title="A",
                        framing="Khung A",
                        context_source_ids=(),
                        questions_for_doctor=("Câu hỏi?",),
                    ),
                    EditorialOption(
                        id="opt-2",
                        title="B",
                        framing="Khung B",
                        context_source_ids=(),
                        questions_for_doctor=("Câu hỏi?",),
                    ),
                ),
            ),
            now=FROZEN_NOW,
        )


def test_authoritative_record_comes_from_the_latest_complete_stage(
    tmp_path: Path,
) -> None:
    """Only the completed record named by a successful stage record may be trusted."""
    project = _researching_project(tmp_path)
    run_orientation_search(
        project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW
    )
    complete_orientation(project, _completed(project), now=FROZEN_NOW)

    record = read_authoritative_orientation(project)

    assert record.run_id == "run-001"
    assert record.included_source_ids == ("pubmed-9",)


def test_no_authoritative_record_before_completion(tmp_path: Path) -> None:
    """A partial attempt must not be readable as a completed orientation."""
    project = _researching_project(tmp_path)
    run_orientation_search(project, [FailingClient()], now=FROZEN_NOW)

    with pytest.raises(ValueError, match="no completed orientation"):
        read_authoritative_orientation(project)
