"""Read-only projection of validated project workflow state into operator actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from healthvideo.domain.project import ProjectManifest
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout


class OperatorActionKind(StrEnum):
    """The next human or system action presented by the thin `/pyh` router."""

    MIGRATE_LEGACY = "migrate_legacy"
    CHOOSE_TOPIC = "choose_topic"
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


@dataclass(frozen=True)
class _ActionTemplate:
    kind: OperatorActionKind
    message: str
    artifact_path: str | None
    suggested_command: str


_MAIN_ACTIONS: dict[WorkflowState, _ActionTemplate] = {
    WorkflowState.IDEA: _ActionTemplate(
        OperatorActionKind.CHOOSE_TOPIC,
        "Choose a topic before continuing.",
        "topic/card.yaml",
        "/pyh chọn chủ đề",
    ),
    WorkflowState.TOPIC_SELECTED: _ActionTemplate(
        OperatorActionKind.CONFIRM_BRIEF,
        "Confirm the author brief before research begins.",
        "author/brief.yaml",
        "/pyh chốt nội dung",
    ),
    WorkflowState.AUTHOR_BRIEF_READY: _ActionTemplate(
        OperatorActionKind.RESEARCH,
        "Research and validate the evidence for the confirmed brief.",
        "evidence/ledger.yaml",
        "/pyh tiếp tục",
    ),
    WorkflowState.RESEARCH_IN_PROGRESS: _ActionTemplate(
        OperatorActionKind.RESEARCH,
        "Continue research and validate the evidence ledger.",
        "evidence/ledger.yaml",
        "/pyh tiếp tục",
    ),
    WorkflowState.EVIDENCE_READY: _ActionTemplate(
        OperatorActionKind.DRAFT,
        "Draft the script and storyboard from validated evidence.",
        "script/script.yaml",
        "/pyh tiếp tục",
    ),
    WorkflowState.DRAFT_READY: _ActionTemplate(
        OperatorActionKind.PREPARE_MEDICAL_REVIEW,
        "Prepare the medical review packet; do not approve it automatically.",
        "reviews/medical-approval.yaml",
        "/pyh mở bản duyệt y khoa",
    ),
    WorkflowState.AWAITING_MEDICAL_REVIEW: _ActionTemplate(
        OperatorActionKind.AWAIT_MEDICAL_APPROVAL,
        "Await the doctor's explicit medical approval.",
        "reviews/medical-approval.yaml",
        "/pyh mở bản duyệt y khoa",
    ),
    WorkflowState.MEDICALLY_APPROVED: _ActionTemplate(
        OperatorActionKind.PRODUCE,
        "Produce the approved video revision.",
        "reviews/medical-approval.yaml",
        "/pyh tiếp tục",
    ),
    WorkflowState.PRODUCTION_IN_PROGRESS: _ActionTemplate(
        OperatorActionKind.PRODUCE,
        "Continue producing the approved video revision.",
        "renders/render-manifest.json",
        "/pyh tiếp tục",
    ),
    WorkflowState.AWAITING_VIDEO_REVIEW: _ActionTemplate(
        OperatorActionKind.AWAIT_VIDEO_APPROVAL,
        "Await the doctor's explicit video approval.",
        "reviews/video-approval.yaml",
        "/pyh mở bản duyệt video",
    ),
    WorkflowState.VIDEO_APPROVED: _ActionTemplate(
        OperatorActionKind.PACKAGE,
        "Create the posting package; publishing remains manual.",
        "publish/manifest.json",
        "/pyh tạo gói đăng",
    ),
    WorkflowState.PACKAGED: _ActionTemplate(
        OperatorActionKind.COMPLETE,
        "The posting package is ready for manual publishing.",
        "publish/manifest.json",
        "/pyh trạng thái",
    ),
    WorkflowState.PUBLISHED_MANUAL: _ActionTemplate(
        OperatorActionKind.COMPLETE,
        "The project has been recorded as manually published.",
        "publish/receipt.yaml",
        "/pyh trạng thái",
    ),
}

_SIDE_ACTIONS: dict[WorkflowState, _ActionTemplate] = {
    WorkflowState.AWAITING_BROWSER_LOGIN: _ActionTemplate(
        OperatorActionKind.AWAIT_BROWSER_LOGIN,
        "Sign in to the required browser session before resuming.",
        None,
        "/pyh tiếp tục",
    ),
    WorkflowState.AWAITING_SECOND_MODEL_REVIEW: _ActionTemplate(
        OperatorActionKind.AWAIT_SECOND_MODEL_REVIEW,
        "Await the required second-model review before resuming.",
        None,
        "/pyh tiếp tục",
    ),
    WorkflowState.NEEDS_MEDICAL_REVISION: _ActionTemplate(
        OperatorActionKind.REVISE_MEDICAL,
        "Revise medical content and return through the medical gate.",
        "reviews",
        "/pyh sửa nội dung",
    ),
    WorkflowState.NEEDS_PRODUCTION_REVISION: _ActionTemplate(
        OperatorActionKind.REVISE_PRODUCTION,
        "Revise the production output and return through the video gate.",
        "reviews",
        "/pyh sửa video",
    ),
    WorkflowState.BLOCKED: _ActionTemplate(
        OperatorActionKind.RESOLVE_BLOCKER,
        "Resolve the recorded blocker before resuming.",
        None,
        "/pyh tiếp tục",
    ),
    WorkflowState.TOPIC_REJECTED: _ActionTemplate(
        OperatorActionKind.REOPEN_TOPIC,
        "Choose a new topic or reopen this one in a new revision.",
        "topic/card.yaml",
        "/pyh chọn chủ đề",
    ),
}


def _validated_layout(project_dir: Path) -> ProjectLayout:
    manifest_path = project_dir / "project.yaml"
    try:
        return resolve_project_layout(project_dir)
    except (FileNotFoundError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid project manifest at {manifest_path}: {error}") from error


def _action_from_template(
    project_dir: Path,
    artifact_root: Path,
    template: _ActionTemplate,
    *,
    reason_code: str | None = None,
) -> OperatorAction:
    message = template.message
    if reason_code is not None:
        message = f"{message} Reason: {reason_code}."
    artifact = (
        artifact_root / template.artifact_path
        if template.artifact_path is not None
        else None
    )
    return OperatorAction(
        kind=template.kind,
        project_dir=project_dir,
        message=message,
        artifact=artifact,
        suggested_command=template.suggested_command,
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

    template = _MAIN_ACTIONS.get(manifest.state) or _SIDE_ACTIONS.get(manifest.state)
    if template is None:
        raise ValueError(f"Unknown v2 workflow state at {project_dir / 'project.yaml'}: {manifest.state!r}")
    reason_code = manifest.side_state.reason_code if manifest.side_state is not None else None
    return _action_from_template(
        layout.project_dir,
        layout.artifact_root,
        template,
        reason_code=reason_code,
    )


def render_status(project_dir: Path) -> str:
    """Render a stable, read-only text status for a project."""
    action = get_next_action(project_dir)
    artifact = str(action.artifact) if action.artifact is not None else "none"
    return "\n".join(
        (
            f"Project: {action.project_dir}",
            f"Next action: {action.kind.value}",
            f"Message: {action.message}",
            f"Artifact: {artifact}",
            f"Suggested command: {action.suggested_command}",
        )
    ) + "\n"
