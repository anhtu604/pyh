import json
from pathlib import Path

from healthvideo.domain.project import ProjectManifest, ProjectState, transition
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.render.run import (
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
    production_run_dir,
)
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)

REVIEWS_DIRECTORY = "reviews"
PROJECT_MANIFEST_NAME = "project.yaml"
GATES: dict[ReviewKind, tuple[ProjectState, ProjectState]] = {
    ReviewKind.MEDICAL: (
        ProjectState.AWAITING_MEDICAL_REVIEW,
        ProjectState.SCRIPT_APPROVED,
    ),
    ReviewKind.VIDEO: (
        ProjectState.AWAITING_VIDEO_REVIEW,
        ProjectState.APPROVED_TO_PUBLISH,
    ),
}


def approve_medical(
    project_dir: Path, *, reviewer: str, note: str = ""
) -> ReviewRecord:
    """Record the medical gate over the evidence, script and storyboard."""
    return _approve(project_dir, ReviewKind.MEDICAL, reviewer=reviewer, note=note)


def approve_video(project_dir: Path, *, reviewer: str, note: str = "") -> ReviewRecord:
    """Record the video gate over the rendered MP4 and its render input."""
    return _approve(project_dir, ReviewKind.VIDEO, reviewer=reviewer, note=note)


def latest_approval(project_dir: Path, kind: ReviewKind) -> ReviewRecord | None:
    """Return the most recent approval of `kind`, or None when the gate is open."""
    directory = project_dir / REVIEWS_DIRECTORY
    if not directory.is_dir():
        return None
    records = [
        ReviewRecord.model_validate(read_yaml(path))
        for path in sorted(directory.glob(f"{kind.value}-*.yaml"))
    ]
    if not records:
        return None
    return max(records, key=lambda record: (record.reviewed_at, str(record.id)))


def approval_is_stale(
    project_dir: Path, project: ProjectManifest, kind: ReviewKind
) -> bool:
    """Report whether reviewed artifacts changed after the latest approval."""
    record = latest_approval(project_dir, kind)
    if record is None:
        return False
    current = _current_artifact_hashes(project_dir, project, kind)
    return current != record.artifact_hashes


def ensure_approval_current(
    project_dir: Path, project: ProjectManifest, kind: ReviewKind
) -> None:
    """Refuse to move a project forward on an approval its artifacts outgrew."""
    if approval_is_stale(project_dir, project, kind):
        raise ValueError(
            f"{kind.value} approval is stale: artifacts changed after review; "
            f"run 'healthvideo review {kind.value}' again"
        )


def _reviewed_paths(
    project_dir: Path, project: ProjectManifest, kind: ReviewKind
) -> dict[str, Path]:
    """Name the artifacts a gate covers; empty when there is nothing to review."""
    if kind is ReviewKind.MEDICAL:
        return {
            "evidence": project_dir / "evidence" / "ledger.yaml",
            "script": project_dir / "script" / "script.yaml",
            "storyboard": project_dir / "storyboard" / "storyboard.yaml",
        }
    input_hash = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if input_hash is None:
        return {}
    run_dir = production_run_dir(project_dir, input_hash)
    return {
        "render_input": run_dir / RENDER_INPUT_NAME,
        "video": run_dir / OUTPUT_NAME,
    }


def _current_artifact_hashes(
    project_dir: Path, project: ProjectManifest, kind: ReviewKind
) -> dict[str, str]:
    """Hash the artifacts a gate covers, omitting the ones that are missing."""
    return {
        name: _hash_artifact(path)
        for name, path in _reviewed_paths(project_dir, project, kind).items()
        if path.is_file()
    }


def _hash_artifact(path: Path) -> str:
    """Hash documents by meaning and rendered media by bytes."""
    if path.suffix == ".yaml":
        return canonical_json_hash(read_yaml(path))
    if path.suffix == ".json":
        return canonical_json_hash(json.loads(path.read_text(encoding="utf-8")))
    return sha256_file(path)


def _approve(
    project_dir: Path, kind: ReviewKind, *, reviewer: str, note: str
) -> ReviewRecord:
    manifest_path = project_dir / PROJECT_MANIFEST_NAME
    project = ProjectManifest.model_validate(read_yaml(manifest_path))
    gate, approved_state = GATES[kind]
    if project.state is not gate:
        raise ValueError(f"{kind.value} review requires project state {gate.value}")

    paths = _reviewed_paths(project_dir, project, kind)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if not paths or missing:
        raise FileNotFoundError(
            f"{kind.value} review needs artifacts: {', '.join(missing) or 'none found'}"
        )
    artifact_hashes = _current_artifact_hashes(project_dir, project, kind)

    record = ReviewRecord(
        kind=kind, reviewer=reviewer, note=note, artifact_hashes=artifact_hashes
    )
    write_yaml_atomic(
        project_dir / REVIEWS_DIRECTORY / f"{kind.value}-{record.id}.yaml",
        record.model_dump(mode="json"),
    )
    write_yaml_atomic(
        manifest_path, transition(project, approved_state).model_dump(mode="json")
    )
    return record
