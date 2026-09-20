"""Read-only projection of validated project workflow state into operator actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.lease import read_write_lease
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout


class OperatorActionKind(StrEnum):
    """The next human or system action presented by the thin `/pyh` router."""

    MIGRATE_LEGACY = "migrate_legacy"
    CHOOSE_TOPIC = "choose_topic"
    ORIENTATION_RESEARCH = "orientation_research"
    AWAIT_EDITORIAL_DIRECTION = "await_editorial_direction"
    CONFIRM_BRIEF = "confirm_brief"
    RESEARCH = "research"
    DRAFT = "draft"
    PREPARE_MEDICAL_REVIEW = "prepare_medical_review"
    AWAIT_MEDICAL_APPROVAL = "await_medical_approval"
    PRODUCE = "produce"
    AWAIT_VIDEO_APPROVAL = "await_video_approval"
    PACKAGE = "package"
    COMPLETE = "complete"
    AWAIT_BROWSER_LOGIN = "await_browser_login"
    AWAIT_SECOND_MODEL_REVIEW = "await_second_model_review"
    REVISE_MEDICAL = "revise_medical"
    REVISE_PRODUCTION = "revise_production"
    RESOLVE_BLOCKER = "resolve_blocker"
    REOPEN_TOPIC = "reopen_topic"


@dataclass(frozen=True)
class OperatorAction:
    """A human-readable next step without any authority to execute it."""

    kind: OperatorActionKind
    project_dir: Path
    message: str
    artifact: Path | None
    suggested_command: str


def _validated_layout(project_dir: Path) -> ProjectLayout:
    manifest_path = project_dir / "project.yaml"
    try:
        return resolve_project_layout(project_dir)
    except (FileNotFoundError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid project manifest at {manifest_path}: {error}") from error


def _action(
    project_dir: Path,
    artifact_root: Path,
    kind: OperatorActionKind,
    message: str,
    artifact_path: str | None,
    suggested_command: str,
    *,
    reason_code: str | None = None,
) -> OperatorAction:
    if reason_code is not None:
        message = f"{message} Reason: {reason_code}."
    artifact = (
        artifact_root / artifact_path
        if artifact_path is not None
        else None
    )
    return OperatorAction(
        kind=kind,
        project_dir=project_dir,
        message=message,
        artifact=artifact,
        suggested_command=suggested_command,
    )


def get_next_action(project_dir: Path) -> OperatorAction:
    """Return the next action from existing validated state without writing anything."""
    layout = _validated_layout(project_dir)
    manifest = layout.manifest
    if isinstance(manifest, ProjectManifest):
        return OperatorAction(
            kind=OperatorActionKind.MIGRATE_LEGACY,
            project_dir=layout.project_dir,
            message="This legacy v1 project must be migrated before using `/pyh`.",
            artifact=layout.project_dir / "project.yaml",
            suggested_command=f"healthvideo project migrate {layout.project_dir}",
        )
    if not isinstance(manifest, ProjectManifestV2):
        raise TypeError(f"Unsupported validated project manifest at {project_dir / 'project.yaml'}")

    reason_code = manifest.side_state.reason_code if manifest.side_state is not None else None
    match manifest.state:
        case WorkflowState.IDEA:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.CHOOSE_TOPIC,
                "Choose a topic before continuing.",
                "topic/card.yaml",
                "/pyh chọn chủ đề",
            )
        case WorkflowState.TOPIC_SELECTED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.ORIENTATION_RESEARCH,
                "Research and validate orientation sources for this topic.",
                "orientation/scope.yaml",
                "/pyh tìm hiểu chủ đề",
            )
        case WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.ORIENTATION_RESEARCH,
                "Resume orientation research; record source failures rather than guessing.",
                "orientation/scope.yaml",
                "/pyh tìm hiểu chủ đề",
            )
        case WorkflowState.AWAITING_EDITORIAL_DIRECTION:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.AWAIT_EDITORIAL_DIRECTION,
                "Present the orientation findings, limits and options, then ask the "
                "doctor for their own editorial view before any brief is confirmed.",
                "orientation/editorial-orientation.yaml",
                "/pyh chốt nội dung",
            )
        case WorkflowState.AUTHOR_BRIEF_READY:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.RESEARCH,
                "Research and validate the evidence for the confirmed brief.",
                "evidence/ledger.yaml",
                "/pyh tiếp tục",
            )
        case WorkflowState.RESEARCH_IN_PROGRESS:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.RESEARCH,
                "Continue research and validate the evidence ledger.",
                "evidence/ledger.yaml",
                "/pyh tiếp tục",
            )
        case WorkflowState.EVIDENCE_READY:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.DRAFT,
                "Draft the script and storyboard from validated evidence.",
                "script/script.yaml",
                "/pyh tiếp tục",
            )
        case WorkflowState.DRAFT_READY:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.PREPARE_MEDICAL_REVIEW,
                "Prepare the medical review packet; do not approve it automatically.",
                "reviews/medical-approval.yaml",
                "/pyh mở bản duyệt y khoa",
            )
        case WorkflowState.AWAITING_MEDICAL_REVIEW:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.AWAIT_MEDICAL_APPROVAL,
                "Await the doctor's explicit medical approval.",
                "reviews/medical-approval.yaml",
                "/pyh mở bản duyệt y khoa",
            )
        case WorkflowState.MEDICALLY_APPROVED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.PRODUCE,
                "Produce the approved video revision.",
                "reviews/medical-approval.yaml",
                "/pyh tiếp tục",
            )
        case WorkflowState.PRODUCTION_IN_PROGRESS:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.PRODUCE,
                "Continue producing the approved video revision.",
                "renders/render-manifest.json",
                "/pyh tiếp tục",
            )
        case WorkflowState.AWAITING_VIDEO_REVIEW:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.AWAIT_VIDEO_APPROVAL,
                "Await the doctor's explicit video approval.",
                "reviews/video-approval.yaml",
                "/pyh mở bản duyệt video",
            )
        case WorkflowState.VIDEO_APPROVED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.PACKAGE,
                "Create the posting package; publishing remains manual.",
                "publish/manifest.json",
                "/pyh tạo gói đăng",
            )
        case WorkflowState.PACKAGED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.COMPLETE,
                "The posting package is ready for manual publishing.",
                "publish/manifest.json",
                "/pyh trạng thái",
            )
        case WorkflowState.PUBLISHED_MANUAL:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.COMPLETE,
                "The project has been recorded as manually published.",
                "publish/receipt.yaml",
                "/pyh trạng thái",
            )
        case WorkflowState.AWAITING_BROWSER_LOGIN:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.AWAIT_BROWSER_LOGIN,
                "Sign in to the required browser session before resuming.",
                None,
                "/pyh tiếp tục",
                reason_code=reason_code,
            )
        case WorkflowState.AWAITING_SECOND_MODEL_REVIEW:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.AWAIT_SECOND_MODEL_REVIEW,
                "Await the required second-model review before resuming.",
                None,
                "/pyh tiếp tục",
                reason_code=reason_code,
            )
        case WorkflowState.NEEDS_MEDICAL_REVISION:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.REVISE_MEDICAL,
                "Revise medical content and return through the medical gate.",
                "reviews",
                "/pyh sửa nội dung",
                reason_code=reason_code,
            )
        case WorkflowState.NEEDS_PRODUCTION_REVISION:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.REVISE_PRODUCTION,
                "Revise the production output and return through the video gate.",
                "reviews",
                "/pyh sửa video",
                reason_code=reason_code,
            )
        case WorkflowState.BLOCKED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.RESOLVE_BLOCKER,
                "Resolve the recorded blocker before resuming.",
                None,
                "/pyh tiếp tục",
                reason_code=reason_code,
            )
        case WorkflowState.TOPIC_REJECTED:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.REOPEN_TOPIC,
                "Choose a new topic or reopen this one in a new revision.",
                "topic/card.yaml",
                "/pyh chọn chủ đề",
                reason_code=reason_code,
            )
        case _:
            raise ValueError(
                f"Unknown v2 workflow state at {project_dir / 'project.yaml'}: "
                f"{manifest.state!r}"
            )


def render_status(project_dir: Path) -> str:
    """Render a stable, read-only text status for a project."""
    action = get_next_action(project_dir)
    lease = read_write_lease(project_dir)
    artifact = str(action.artifact) if action.artifact is not None else "none"
    lines = [
            f"Project: {action.project_dir}",
            f"Next action: {action.kind.value}",
            f"Message: {action.message}",
            f"Artifact: {artifact}",
            f"Suggested command: {action.suggested_command}",
    ]
    if lease is not None:
        lines.extend(
            [
                "Writer: busy",
                f"Writer host: {lease.host_id}",
                f"Writer PID: {lease.pid}",
                f"Writer operation: {lease.operation}",
            ]
        )
    else:
        lines.append("Writer: idle")
    return "\n".join(lines) + "\n"
