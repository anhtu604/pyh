"""Read-only projection of validated project workflow state into operator actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout


class OperatorActionKind(StrEnum):
    """The next human or system action presented by the thin `/pyh` router."""

    CHOOSE_TOPIC = "choose_topic"
    RESEARCH = "research"
    DRAFT = "draft"
    PREPARE_MEDICAL_REVIEW = "prepare_medical_review"
    AWAIT_MEDICAL_APPROVAL = "await_medical_approval"
    PRODUCE = "produce"
    AWAIT_VIDEO_APPROVAL = "await_video_approval"
    PACKAGE = "package"
    COMPLETE = "complete"
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
    reason_code = manifest.side_state.reason_code if manifest.side_state is not None else None
    explainer_reminder = ""
    if (
        manifest.content_profile == "explain_first_v1"
        and not (layout.artifact_root / "explainer/explainer.yaml").is_file()
    ):
        explainer_reminder = " Create explainer/explainer.yaml before evidence_ready."
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
        case WorkflowState.TOPIC_SELECTED | WorkflowState.RESEARCH_IN_PROGRESS:
            return _action(
                layout.project_dir,
                layout.artifact_root,
                OperatorActionKind.RESEARCH,
                f'Run `healthvideo step evidence-search "{layout.project_dir}" '
                "--query <English-query>` and validate the evidence ledger."
                + explainer_reminder,
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
    artifact = str(action.artifact) if action.artifact is not None else "none"
    lines = [
            f"Project: {action.project_dir}",
            f"Next action: {action.kind.value}",
            f"Message: {action.message}",
            f"Artifact: {artifact}",
            f"Suggested command: {action.suggested_command}",
    ]
    return "\n".join(lines) + "\n"
