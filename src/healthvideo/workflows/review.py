from datetime import datetime
from pathlib import Path

from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2
from healthvideo.storage.files import read_yaml
from healthvideo.storage.project_layout import resolve_project_layout
from healthvideo.workflows.gate_review import (
    approve_gate,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    video_reviewed_paths,
)


def approve_medical(project_dir: Path, *, reviewer: str, note: str = "") -> GateApprovalRecord:
    """Approve the active revision through the v2 medical gate."""
    return approve_gate(
        project_dir, GateKind.MEDICAL, reviewer=reviewer, note=note,
        now=datetime.now().astimezone(),
    )


def approve_video(project_dir: Path, *, reviewer: str, note: str = "") -> GateApprovalRecord:
    """Approve the active revision through the v2 video gate."""
    return approve_gate(
        project_dir, GateKind.VIDEO, reviewer=reviewer, note=note,
        now=datetime.now().astimezone(),
    )


def latest_approval(project_dir: Path, kind: GateKind) -> GateApprovalRecord | None:
    """Read the immutable approval bound to the active revision."""
    revision = resolve_project_layout(project_dir).artifact_root
    path = revision / "reviews" / f"{kind.value}-approval.yaml"
    return GateApprovalRecord.model_validate(read_yaml(path)) if path.is_file() else None


def approval_is_stale(
    project_dir: Path, project: ProjectManifestV2, kind: GateKind,
) -> bool:
    """Report whether the active revision's reviewed artifacts changed."""
    record = latest_approval(project_dir, kind)
    if record is None:
        return False
    revision = project_dir / "revisions" / project.active_revision
    paths = medical_reviewed_paths(revision) if kind is GateKind.MEDICAL else video_reviewed_paths(revision)
    return hash_reviewed_artifacts(paths) != record.artifact_hashes
