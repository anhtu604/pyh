"""Read-only planning for non-destructive v1 to v2 project migration."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from healthvideo.assets import referenced_evidence_assets
from healthvideo.domain.asset_manifest import AssetManifest, validate_asset_manifest
from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.review import ReviewKind
from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.run import OUTPUT_NAME, PRODUCTION_ARTIFACT, RENDER_INPUT_NAME
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.immutable import promote_directory_once
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.review import approval_is_stale, latest_approval


class ApprovalDisposition(StrEnum):
    RETAIN_CANDIDATE = "retain_candidate"
    UNPROVEN = "unproven"
    MEDICAL_RETAINED = "medical_retained"
    VIDEO_RETAINED = "video_retained"


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


def evaluate_approval_equivalence(
    source: Path, staged_revision: Path
) -> ApprovalDisposition:
    """Prove gate equivalence from source and staged artifact hashes."""
    project = ProjectManifest.model_validate(read_yaml(source / "project.yaml"))
    medical = latest_approval(source, ReviewKind.MEDICAL)
    if (
        medical is None
        or approval_is_stale(source, project, ReviewKind.MEDICAL)
        or _medical_hashes(staged_revision) != medical.artifact_hashes
    ):
        return ApprovalDisposition.UNPROVEN
    video = latest_approval(source, ReviewKind.VIDEO)
    if (
        video is not None
        and not approval_is_stale(source, project, ReviewKind.VIDEO)
        and _video_hashes(staged_revision, project) == video.artifact_hashes
    ):
        return ApprovalDisposition.VIDEO_RETAINED
    return ApprovalDisposition.MEDICAL_RETAINED


def migrate_project(
    source: Path, *, now: datetime, migration_id: UUID
) -> Path:
    """Copy, validate and atomically promote a new v2 sibling project."""
    if now.utcoffset() is None:
        raise ValueError("migration time must be timezone-aware")
    plan = plan_migration(source)
    if plan.destination_conflict:
        raise FileExistsError(
            f"Refusing to replace an existing destination: {plan.destination}"
        )
    staging = plan.destination.with_name(
        f".{plan.destination.name}.migrate-{migration_id}"
    )
    if staging.exists():
        raise FileExistsError(f"Migration staging already exists: {staging}")
    try:
        _materialize_plan(plan, staging)
        revision = staging / "revisions" / "001"
        project = ProjectManifest.model_validate(read_yaml(source / "project.yaml"))
        _copy_render_candidate(source, revision, project)
        disposition = evaluate_approval_equivalence(source, revision)
        _retain_equivalent_reviews(source, revision, disposition)
        final_state = _state_after_equivalence(
            plan.proposed_state,
            disposition,
            render_valid=_render_is_valid(revision, project),
        )
        project_payload = _project_payload(source, final_state)
        write_yaml_atomic(staging / "project.yaml", project_payload)
        _validate_staged_project(staging, plan, project_payload)
        promote_directory_once(staging, plan.destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return plan.destination


def _materialize_plan(plan: MigrationPlan, staging: Path) -> None:
    manifest = ProjectManifest.model_validate(read_yaml(plan.source / "project.yaml"))
    derived = _derived_payloads(plan.source, manifest)
    for item in plan.files:
        destination = staging / item.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        key = item.destination.as_posix()
        if item.source is None or item.source == Path("project.yaml"):
            write_yaml_atomic(destination, derived[key])
        elif item.source.suffix.lower() in {".yaml", ".yml", ".json"}:
            write_yaml_atomic(destination, read_yaml(plan.source / item.source))
        else:
            shutil.copy2(plan.source / item.source, destination)


def _state_after_equivalence(
    proposed: WorkflowState,
    disposition: ApprovalDisposition,
    *,
    render_valid: bool,
) -> WorkflowState:
    gated_states = {
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.PRODUCTION_IN_PROGRESS,
        WorkflowState.AWAITING_VIDEO_REVIEW,
        WorkflowState.VIDEO_APPROVED,
        WorkflowState.PACKAGED,
        WorkflowState.PUBLISHED_MANUAL,
    }
    if proposed not in gated_states:
        return proposed
    if disposition is ApprovalDisposition.UNPROVEN:
        return WorkflowState.AWAITING_MEDICAL_REVIEW
    if proposed is WorkflowState.MEDICALLY_APPROVED:
        return proposed
    if disposition is ApprovalDisposition.VIDEO_RETAINED and render_valid:
        return WorkflowState.VIDEO_APPROVED
    if render_valid:
        return WorkflowState.AWAITING_VIDEO_REVIEW
    return WorkflowState.MEDICALLY_APPROVED


def _copy_render_candidate(
    source: Path, staged_revision: Path, project: ProjectManifest
) -> None:
    production = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if production is None:
        return
    source_run = source / "renders" / production
    if source_run.is_dir():
        shutil.copytree(source_run, staged_revision / "renders" / production)


def _retain_equivalent_reviews(
    source: Path,
    staged_revision: Path,
    disposition: ApprovalDisposition,
) -> None:
    if disposition is ApprovalDisposition.VIDEO_RETAINED:
        kinds = (ReviewKind.MEDICAL, ReviewKind.VIDEO)
    elif disposition is ApprovalDisposition.MEDICAL_RETAINED:
        kinds = (ReviewKind.MEDICAL,)
    else:
        return
    for kind in kinds:
        record = latest_approval(source, kind)
        if record is None:
            raise ValueError(f"Proven {kind.value} approval record disappeared")
        write_yaml_atomic(
            staged_revision / "reviews" / f"{kind.value}-{record.id}.yaml",
            record.model_dump(mode="json"),
        )


def _medical_hashes(revision: Path) -> dict[str, str]:
    paths = {
        "evidence": revision / "evidence" / "ledger.yaml",
        "script": revision / "script" / "script.yaml",
        "storyboard": revision / "storyboard" / "storyboard.yaml",
    }
    if not all(path.is_file() for path in paths.values()):
        return {}
    storyboard = Storyboard.model_validate(read_yaml(paths["storyboard"]))
    paths.update(
        {
            f"asset:{relative}": path
            for relative, path in referenced_evidence_assets(
                revision, storyboard
            ).items()
        }
    )
    return {
        name: (
            canonical_json_hash(read_yaml(path))
            if path.suffix == ".yaml"
            else sha256_file(path)
        )
        for name, path in paths.items()
        if path.is_file()
    }


def _video_hashes(
    revision: Path, project: ProjectManifest
) -> dict[str, str]:
    production = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if production is None:
        return {}
    run = revision / "renders" / production
    render_input = run / RENDER_INPUT_NAME
    video = run / OUTPUT_NAME
    if not render_input.is_file() or not video.is_file():
        return {}
    return {
        "render_input": canonical_json_hash(
            json.loads(render_input.read_text(encoding="utf-8"))
        ),
        "video": sha256_file(video),
    }


def _render_is_valid(revision: Path, project: ProjectManifest) -> bool:
    return set(_video_hashes(revision, project)) == {"render_input", "video"}


def _project_payload(source: Path, state: WorkflowState) -> dict[str, object]:
    manifest = ProjectManifest.model_validate(read_yaml(source / "project.yaml"))
    return {
        "schema_version": "2.0",
        "slug": manifest.slug,
        "language": manifest.language,
        "state": state.value,
        "active_revision": "001",
        "artifact_hashes": manifest.artifact_hashes,
    }


def _validate_staged_project(
    staging: Path, plan: MigrationPlan, project_payload: dict[str, object]
) -> None:
    ProjectManifestV2.model_validate(project_payload)
    layout = resolve_project_layout(staging)
    manifest_path = layout.artifact_root / "assets" / "asset-manifest.yaml"
    assets = AssetManifest.model_validate(read_yaml(manifest_path))
    validate_asset_manifest(layout.artifact_root, assets)
    for item in plan.files:
        path = staging / item.destination
        if not path.is_file():
            raise FileNotFoundError(f"Migration output is missing: {item.destination}")
        key = item.destination.as_posix()
        if item.destination == Path("project.yaml"):
            expected = canonical_json_hash(project_payload)
        else:
            expected = plan.hashes[key]
        if path.suffix.lower() in {".yaml", ".yml", ".json"}:
            actual = canonical_json_hash(read_yaml(path))
        else:
            actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"Migration output hash mismatch: {item.destination}")


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
