"""Author the fixed M6.4 outro before medical review, with recoverable two-file writes."""

from pathlib import Path

from healthvideo.domain.hook_outro import OUTRO_TEXT, validate_hook_outro
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic


def _append(
    script: Script, board: Storyboard, duration_frames: int
) -> tuple[Script, Storyboard]:
    if duration_frames <= 0:
        raise ValueError("outro duration must be positive")
    if script.format_profile != "legacy" or any(line.id == "OUTRO" for line in script.lines):
        raise ValueError("outro already exists or ID conflicts")
    if len(script.lines) != len(board.scenes) or not board.scenes:
        raise ValueError("script and storyboard must have matching content")
    end = 0
    content: list[Scene] = []
    for line, scene in zip(script.lines, board.scenes, strict=True):
        if scene.start_frame != end or line.text != scene.narration:
            raise ValueError("storyboard must be contiguous and match script")
        end += scene.duration_frames
        content.append(scene.model_copy(update={"script_line_id": line.id}))
    line = ScriptLine(
        id="OUTRO", text=OUTRO_TEXT, purpose="outro", delivery=Delivery(intent="close")
    )
    final = Scene(
        id="OUTRO", start_frame=end, duration_frames=duration_frames,
        narration=OUTRO_TEXT, script_line_id="OUTRO", visual="brand_outro",
    )
    next_script = script.model_copy(update={
        "format_profile": "hook_outro_v1", "lines": [*script.lines, line],
    })
    next_board = board.model_copy(update={"scenes": (*content, final)})
    validate_hook_outro(next_script, next_board)
    return next_script, next_board


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
    intent_path = revision / "workflow/pending-hook-outro.yaml"
    current_script = read_yaml(script_path)
    current_board = read_yaml(board_path)
    if intent_path.exists():
        intent = read_yaml(intent_path)
        if intent.get("revision") != project.active_revision or intent.get("duration_frames") != duration_frames:
            raise ValueError("pending outro intent belongs to another revision or duration")
    else:
        script = Script.model_validate(current_script)
        board = Storyboard.model_validate(current_board)
        if script.format_profile == "hook_outro_v1":
            validate_hook_outro(script, board)
            if board.scenes[-1].duration_frames != duration_frames:
                raise ValueError("outro already authored with another duration")
            return
        desired_script, desired_board = _append(script, board, duration_frames)
        intent = {
            "revision": project.active_revision,
            "duration_frames": duration_frames,
            "old_script_hash": canonical_json_hash(current_script),
            "old_board_hash": canonical_json_hash(current_board),
            "desired_script": desired_script.model_dump(mode="json"),
            "desired_board": desired_board.model_dump(mode="json"),
        }
        intent["desired_script_hash"] = canonical_json_hash(intent["desired_script"])
        intent["desired_board_hash"] = canonical_json_hash(intent["desired_board"])
        write_yaml_atomic(intent_path, intent)

    script_hash = canonical_json_hash(current_script)
    board_hash = canonical_json_hash(current_board)
    if script_hash not in {intent["old_script_hash"], intent["desired_script_hash"]}:
        raise ValueError("script changed after pending outro intent; refusing overwrite")
    if board_hash not in {intent["old_board_hash"], intent["desired_board_hash"]}:
        raise ValueError("storyboard changed after pending outro intent; refusing overwrite")
    if script_hash == intent["old_script_hash"]:
        write_yaml_atomic(script_path, intent["desired_script"])
    if board_hash == intent["old_board_hash"]:
        write_yaml_atomic(board_path, intent["desired_board"])
    if (
        canonical_json_hash(read_yaml(script_path)) != intent["desired_script_hash"]
        or canonical_json_hash(read_yaml(board_path)) != intent["desired_board_hash"]
    ):
        raise ValueError("outro transaction did not converge")
    intent_path.unlink()
