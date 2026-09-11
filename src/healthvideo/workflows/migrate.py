"""Read-only planning for non-destructive v1 to v2 project migration."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import canonical_json_hash, read_yaml, sha256_file


class ApprovalDisposition(StrEnum):
    RETAIN_CANDIDATE = "retain_candidate"


@dataclass(frozen=True)
class MigrationFile:
    source: Path | None
    destination: Path


@dataclass(frozen=True)
class MigrationPlan:
    source: Path
    destination: Path
    source_state: ProjectState
    proposed_state: WorkflowState
    files: tuple[MigrationFile, ...]
    hashes: dict[str, str]
    approval_disposition: ApprovalDisposition
    destination_conflict: bool


STATE_MAP: dict[ProjectState, WorkflowState] = {
    ProjectState.IDEA: WorkflowState.IDEA,
    ProjectState.EVIDENCE_IN_PROGRESS: WorkflowState.RESEARCH_IN_PROGRESS,
    ProjectState.EVIDENCE_READY: WorkflowState.EVIDENCE_READY,
    ProjectState.AWAITING_MEDICAL_REVIEW: WorkflowState.AWAITING_MEDICAL_REVIEW,
    ProjectState.SCRIPT_APPROVED: WorkflowState.MEDICALLY_APPROVED,
    ProjectState.PRODUCING: WorkflowState.PRODUCTION_IN_PROGRESS,
    ProjectState.RENDERED: WorkflowState.AWAITING_VIDEO_REVIEW,
    ProjectState.AWAITING_VIDEO_REVIEW: WorkflowState.AWAITING_VIDEO_REVIEW,
    ProjectState.APPROVED_TO_PUBLISH: WorkflowState.VIDEO_APPROVED,
    ProjectState.PUBLISHED: WorkflowState.PUBLISHED_MANUAL,
}


PATH_MAP: tuple[MigrationFile, ...] = (
    MigrationFile(Path("project.yaml"), Path("project.yaml")),
    MigrationFile(
        Path("author-brief.yaml"), Path("revisions/001/author/brief.yaml")
    ),
    MigrationFile(
        Path("evidence/ledger.yaml"), Path("revisions/001/evidence/ledger.yaml")
    ),
    MigrationFile(
        Path("script/script.yaml"), Path("revisions/001/script/script.yaml")
    ),
    MigrationFile(
        Path("storyboard/storyboard.yaml"),
        Path("revisions/001/storyboard/storyboard.yaml"),
    ),
    MigrationFile(
        Path("assets/evidence-r01.svg"),
        Path("revisions/001/assets/evidence-r01.svg"),
    ),
    MigrationFile(None, Path("revisions/001/topic/card.yaml")),
    MigrationFile(None, Path("revisions/001/assets/asset-manifest.yaml")),
)


def plan_migration(source: Path) -> MigrationPlan:
    """Describe a migration without creating or changing any filesystem entry."""
    source = Path(source)
    manifest_data = read_yaml(source / "project.yaml")
    if manifest_data.get("schema_version") != "1.0":
        raise ValueError("Migration source must use schema version 1.0")
    manifest = ProjectManifest.model_validate(manifest_data)
    destination = source.with_name(f"{source.name}-v2")
    derived = _derived_payloads(source, manifest)
    hashes: dict[str, str] = {}
    for item in PATH_MAP:
        key = item.destination.as_posix()
        if item.source is None or item.source == Path("project.yaml"):
            hashes[key] = canonical_json_hash(derived[key])
        elif item.source.suffix.lower() in {".yaml", ".yml", ".json"}:
            hashes[key] = canonical_json_hash(read_yaml(source / item.source))
        else:
            hashes[key] = sha256_file(source / item.source)
    return MigrationPlan(
        source=source,
        destination=destination,
        source_state=manifest.state,
        proposed_state=STATE_MAP[manifest.state],
        files=PATH_MAP,
        hashes=hashes,
        approval_disposition=ApprovalDisposition.RETAIN_CANDIDATE,
        destination_conflict=destination.exists(),
    )


def _derived_payloads(
    source: Path, manifest: ProjectManifest
) -> dict[str, dict[str, object]]:
    brief = read_yaml(source / "author-brief.yaml")
    asset_path = Path("assets/evidence-r01.svg")
    return {
        "project.yaml": {
            "schema_version": "2.0",
            "slug": manifest.slug,
            "language": manifest.language,
            "state": STATE_MAP[manifest.state].value,
            "active_revision": "001",
            "artifact_hashes": manifest.artifact_hashes,
        },
        "revisions/001/topic/card.yaml": {
            "schema_version": "2.0",
            "synthetic_test_record": True,
            "slug": manifest.slug,
            "title": brief["title"],
            "origin": "migration_fixture",
        },
        "revisions/001/assets/asset-manifest.yaml": {
            "schema_version": "2.0",
            "assets": [
                {
                    "path": asset_path.as_posix(),
                    "kind": "evidence_highlight",
                    "semantic": True,
                    "classification_reason": (
                        "Evidence highlight changes the medical meaning."
                    ),
                    "sha256": sha256_file(source / asset_path),
                    "source": "synthetic_test_fixture",
                    "license": "synthetic_test_only",
                    "creator": "repository_fixture",
                    "revision": "001",
                }
            ],
        },
    }
