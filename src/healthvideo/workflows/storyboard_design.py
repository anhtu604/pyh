"""Storyboard & visual asset validation step for Storyboard Director (`storyboard_design`)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.domain.asset_manifest import AssetManifest
from healthvideo.domain.clip_plan import ClipPlan
from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    replace_directory_atomic,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.revision_lock import revision_lock
from healthvideo.workflows.draft import _project, _validate, validate_estimated_layout


def storyboard_ready(project_dir: Path) -> bool:
    """Return True when active revision has valid storyboard, asset manifest, and clip plan if required."""
    project_file = project_dir / "project.yaml"
    if not project_file.is_file():
        return False
    try:
        project = _project(project_dir)
    except (OSError, TypeError, ValueError):
        return False
    revision = project_dir / "revisions" / project.active_revision
    required = (
        revision / "script/script.yaml",
        revision / "storyboard/storyboard.yaml",
        revision / "assets/asset-manifest.yaml",
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        script = Script.model_validate(read_yaml(required[0]))
        storyboard = Storyboard.model_validate(read_yaml(required[1]))
        assets = AssetManifest.model_validate(read_yaml(required[2]))
        _validate(revision, script, storyboard, assets, project=project)
        validate_estimated_layout(project_dir, script, storyboard, assets)
        clip_path = revision / "script/clip-plan.yaml"
        if storyboard.format_profile == "youtube_long" and clip_path.is_file():
            ClipPlan.model_validate(read_yaml(clip_path))
        outline_path = revision / "script/outline.yaml"
        if outline_path.is_file():
            ledger = read_yaml(revision / "evidence/ledger.yaml")
            claim_ids = [
                str(item.get("id"))
                for item in ledger.get("claims", [])
                if isinstance(item, dict) and item.get("id")
            ]
            validate_outline(Outline.model_validate(read_yaml(outline_path)), storyboard, claim_ids)
    except (OSError, TypeError, ValueError):
        return False
    return True


def submit_storyboard_design(
    project_dir: Path,
    storyboard_file: Path,
    assets_file: Path,
    *,
    clip_plan_file: Path | None = None,
    outline_file: Path | None = None,
) -> ProjectManifestV2:
    """Validate and atomically store storyboard, asset manifest, and optional clip-plan."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    # The sibling lock survives whole-revision promotion and coordinates voice
    # saves from other CLI processes. Agent reasoning happens before this call.
    with revision_lock(revision):
        from healthvideo.workflows import rework

        files = {'storyboard/storyboard.yaml': storyboard_file, 'assets/asset-manifest.yaml': assets_file}
        if clip_plan_file is not None:
            files['script/clip-plan.yaml'] = clip_plan_file
        if outline_file is not None:
            files['script/outline.yaml'] = outline_file
        rework.check_storyboard(project_dir, files)
        try:
            result = _submit_storyboard_design(
                project_dir, storyboard_file, assets_file,
                clip_plan_file=clip_plan_file, outline_file=outline_file,
            )
        except ValueError as error:
            rework.storyboard_failure(project_dir, files, error)
            raise
        (revision / rework.STORYBOARD_PLAN).unlink(missing_ok=True)
        return result


def _submit_storyboard_design(
    project_dir: Path,
    storyboard_file: Path,
    assets_file: Path,
    *,
    clip_plan_file: Path | None = None,
    outline_file: Path | None = None,
) -> ProjectManifestV2:
    project = _project(project_dir)
    if project.state not in {
        WorkflowState.EVIDENCE_READY,
        WorkflowState.DRAFT_READY,
        WorkflowState.NEEDS_MEDICAL_REVISION,
    }:
        raise ValueError(
            "storyboard submission requires evidence_ready, draft_ready, or needs_medical_revision"
        )
    revision = project_dir / "revisions" / project.active_revision
    script_path = revision / "script/script.yaml"
    if not script_path.is_file():
        raise ValueError("storyboard submission requires script/script.yaml first")
    script_data = read_yaml(script_path)
    script = Script.model_validate(script_data)
    storyboard = Storyboard.model_validate(read_yaml(storyboard_file))
    assets = AssetManifest.model_validate(read_yaml(assets_file))
    clip_plan = ClipPlan.model_validate(read_yaml(clip_plan_file)) if clip_plan_file else None
    outline = Outline.model_validate(read_yaml(outline_file)) if outline_file else None

    staging = Path(mkdtemp(prefix=f".{revision.name}.storyboard-", dir=revision.parent))
    promoted = False
    try:
        shutil.copytree(revision, staging, dirs_exist_ok=True)
        write_yaml_atomic(
            staging / "storyboard/storyboard.yaml", storyboard.model_dump(mode="json")
        )
        write_yaml_atomic(
            staging / "assets/asset-manifest.yaml", assets.model_dump(mode="json")
        )
        if clip_plan is not None:
            write_yaml_atomic(
                staging / "script/clip-plan.yaml", clip_plan.model_dump(mode="json")
            )
        if outline is not None:
            write_yaml_atomic(
                staging / "script/outline.yaml", outline.model_dump(mode="json")
            )
        style_issues = _validate(staging, script, storyboard, assets, project=project)
        validate_estimated_layout(project_dir, script, storyboard, assets, clip_plan=clip_plan)
        if (staging / "script/outline.yaml").is_file():
            ledger = read_yaml(staging / "evidence/ledger.yaml")
            claim_ids = [
                str(item.get("id"))
                for item in ledger.get("claims", [])
                if isinstance(item, dict) and item.get("id")
            ]
            validate_outline(
                Outline.model_validate(read_yaml(staging / "script/outline.yaml")),
                storyboard,
                claim_ids,
            )
        write_text_atomic(
            staging / "reviews/style-lint.json",
            json.dumps(
                {"issues": [issue.to_dict() for issue in style_issues]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        changed = project
        if project.state is WorkflowState.EVIDENCE_READY:
            context = TransitionContext(
                active_revision=project.active_revision,
                current_input_hash=canonical_json_hash(script_data),
                validated_artifacts=frozenset({"script/script.yaml"}),
            )
            changed = transition_v2(project, WorkflowState.DRAFT_READY, context)
        from healthvideo.workflows.rework import STORYBOARD_PLAN

        if (revision / STORYBOARD_PLAN).is_file():
            # Inputs have passed the same validators above. Preserve their exact source
            # so model defaults/serialization cannot rewrite accepted sibling scenes.
            originals = {'storyboard/storyboard.yaml': storyboard_file,
                         'assets/asset-manifest.yaml': assets_file,
                         'script/clip-plan.yaml': clip_plan_file, 'script/outline.yaml': outline_file}
            for relative, original in originals.items():
                if original is not None:
                    (staging / relative).write_bytes(original.read_bytes())
        replace_directory_atomic(staging, revision)
        promoted = True
        if changed != project:
            write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
        return changed
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
