import shutil
from pathlib import Path

import pytest

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.migrate import ApprovalDisposition, plan_migration

GOLDEN_V1 = Path("tests/fixtures/golden-project")


def _copy_v1(tmp_path: Path, state: str) -> Path:
    source = tmp_path / "golden-project"
    shutil.copytree(GOLDEN_V1, source)
    manifest = read_yaml(source / "project.yaml")
    manifest["state"] = state
    write_yaml_atomic(source / "project.yaml", manifest)
    return source


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("v1", "v2"),
    [
        ("idea", WorkflowState.IDEA),
        ("evidence_in_progress", WorkflowState.RESEARCH_IN_PROGRESS),
        ("evidence_ready", WorkflowState.EVIDENCE_READY),
        ("awaiting_medical_review", WorkflowState.AWAITING_MEDICAL_REVIEW),
        ("script_approved", WorkflowState.MEDICALLY_APPROVED),
        ("producing", WorkflowState.PRODUCTION_IN_PROGRESS),
        ("rendered", WorkflowState.AWAITING_VIDEO_REVIEW),
        ("awaiting_video_review", WorkflowState.AWAITING_VIDEO_REVIEW),
        ("approved_to_publish", WorkflowState.VIDEO_APPROVED),
        ("published", WorkflowState.PUBLISHED_MANUAL),
    ],
)
def test_migration_state_map(
    v1: str, v2: WorkflowState, tmp_path: Path
) -> None:
    source = _copy_v1(tmp_path, state=v1)

    assert plan_migration(source).proposed_state is v2


def test_plan_uses_the_locked_path_contract_and_hashes_every_input(
    tmp_path: Path,
) -> None:
    source = _copy_v1(tmp_path, state="script_approved")

    plan = plan_migration(source)

    assert plan.destination == source.with_name("golden-project-v2")
    assert plan.source_state == "script_approved"
    assert plan.approval_disposition is ApprovalDisposition.RETAIN_CANDIDATE
    assert [(item.source, item.destination) for item in plan.files] == [
        (Path("project.yaml"), Path("project.yaml")),
        (Path("author-brief.yaml"), Path("revisions/001/author/brief.yaml")),
        (Path("evidence/ledger.yaml"), Path("revisions/001/evidence/ledger.yaml")),
        (Path("script/script.yaml"), Path("revisions/001/script/script.yaml")),
        (
            Path("storyboard/storyboard.yaml"),
            Path("revisions/001/storyboard/storyboard.yaml"),
        ),
        (
            Path("assets/evidence-r01.svg"),
            Path("revisions/001/assets/evidence-r01.svg"),
        ),
        (None, Path("revisions/001/topic/card.yaml")),
        (None, Path("revisions/001/assets/asset-manifest.yaml")),
    ]
    assert set(plan.hashes) == {
        item.destination.as_posix() for item in plan.files
    }
    assert all(len(value) == 64 for value in plan.hashes.values())


def test_plan_is_read_only_for_source_destination_and_staging(tmp_path: Path) -> None:
    source = _copy_v1(tmp_path, state="awaiting_medical_review")
    before = _snapshot(source)

    plan = plan_migration(source)

    assert _snapshot(source) == before
    assert not plan.destination.exists()
    assert list(source.parent.glob(f".{plan.destination.name}.migrate-*")) == []


def test_plan_reports_an_existing_destination_conflict(tmp_path: Path) -> None:
    source = _copy_v1(tmp_path, state="idea")
    destination = source.with_name("golden-project-v2")
    destination.mkdir()

    plan = plan_migration(source)

    assert plan.destination_conflict is True
    assert destination.is_dir()


def test_plan_rejects_a_v2_source(tmp_path: Path) -> None:
    source = tmp_path / "golden-project-v2"
    shutil.copytree(Path("tests/fixtures/golden-project-v2"), source)

    with pytest.raises(ValueError, match="schema version 1.0"):
        plan_migration(source)

