"""Validate an already authored fixed M6.4 outro before medical review."""

from pathlib import Path

from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml


def author_hook_outro(project_dir: Path, *, duration_frames: int) -> None:
    if duration_frames <= 0:
        raise ValueError("outro duration must be positive")
    raw_project = read_yaml(project_dir / "project.yaml")
    if raw_project.get("schema_version") != "2.0":
        raise ValueError("outro authoring requires v2 project")
    project = ProjectManifestV2.model_validate(raw_project)
    if project.state not in {
        WorkflowState.DRAFT_READY, WorkflowState.AWAITING_MEDICAL_REVIEW,
    }:
        raise ValueError("outro authoring requires pre-medical-review draft")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("medical approval already exists")
    script_path = revision / "script/script.yaml"
    board_path = revision / "storyboard/storyboard.yaml"
    script = Script.model_validate(read_yaml(script_path))
    board = Storyboard.model_validate(read_yaml(board_path))
    if script.format_profile != "hook_outro_v1":
        raise ValueError("outro already exists or ID conflicts")
    validate_hook_outro(script, board)
    if board.scenes[-1].duration_frames != duration_frames:
        raise ValueError("outro already authored with another duration")
