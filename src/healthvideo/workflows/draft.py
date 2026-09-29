"""Validate an agent-authored v2 draft and submit it to the medical gate."""

from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.asset_manifest import (
    AssetManifest,
    validate_asset_manifest,
)
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.qa.script import review_script
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    replace_directory_atomic,
    write_yaml_atomic,
)
from healthvideo.workflows.citations import resolve_citations


def _project(project_dir: Path) -> ProjectManifestV2:
    data = read_yaml(project_dir / "project.yaml")
    if data.get("schema_version") != "2.0":
        raise ValueError("draft submission requires project schema 2.0")
    return ProjectManifestV2.model_validate(data)


def _validate(
    revision: Path,
    script: Script,
    storyboard: Storyboard,
    assets: AssetManifest,
) -> None:
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    if not script.lines or not storyboard.scenes:
        raise ValueError("draft requires nonempty script lines and storyboard scenes")
    claims = [EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])]
    issues = review_script(script, claims, [])
    blocking = [issue for issue in issues if issue.code == "unknown_claim"]
    if blocking:
        raise ValueError("script references unknown claim: " + blocking[0].message)
    validate_visual_budget(storyboard)
    validate_hook_outro(script, storyboard, require_brand=True)
    resolve_citations(
        script,
        ledger,
        storyboard.scenes,
        strict_line_ids=script.format_profile == "hook_outro_v1",
    )
    validate_asset_manifest(revision, assets)
    referenced_storyboard_assets(revision, storyboard, assets)


def submit_draft(
    project_dir: Path,
    script_file: Path,
    storyboard_file: Path,
    assets_file: Path,
) -> ProjectManifestV2:
    """Promote a complete validated draft without leaving partial revision files."""
    project = _project(project_dir)
    if project.state is not WorkflowState.EVIDENCE_READY:
        raise ValueError("draft submission requires evidence_ready")
    script = Script.model_validate(read_yaml(script_file))
    storyboard = Storyboard.model_validate(read_yaml(storyboard_file))
    assets = AssetManifest.model_validate(read_yaml(assets_file))
    revision = project_dir / "revisions" / project.active_revision
    staging = Path(mkdtemp(prefix=f".{revision.name}.draft-", dir=revision.parent))
    promoted = False
    try:
        shutil.copytree(revision, staging, dirs_exist_ok=True)
        write_yaml_atomic(staging / "script/script.yaml", script.model_dump(mode="json"))
        write_yaml_atomic(
            staging / "storyboard/storyboard.yaml", storyboard.model_dump(mode="json")
        )
        write_yaml_atomic(
            staging / "assets/asset-manifest.yaml", assets.model_dump(mode="json")
        )
        _validate(staging, script, storyboard, assets)
        script_data = read_yaml(staging / "script/script.yaml")
        context = TransitionContext(
            active_revision=project.active_revision,
            current_input_hash=canonical_json_hash(script_data),
            validated_artifacts=frozenset({"script/script.yaml"}),
        )
        changed = transition_v2(project, WorkflowState.DRAFT_READY, context)
        replace_directory_atomic(staging, revision)
        promoted = True
        write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
        return changed
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging)


def submit_medical_review(project_dir: Path) -> ProjectManifestV2:
    """Enter medical review after revalidating the active draft, without approval."""
    project = _project(project_dir)
    if project.state is not WorkflowState.DRAFT_READY:
        raise ValueError("medical submission requires draft_ready")
    revision = project_dir / "revisions" / project.active_revision
    script_data = read_yaml(revision / "script/script.yaml")
    script = Script.model_validate(script_data)
    storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    assets = AssetManifest.model_validate(read_yaml(revision / "assets/asset-manifest.yaml"))
    _validate(revision, script, storyboard, assets)
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(script_data),
        validated_artifacts=frozenset(
            {"script/script.yaml", "storyboard/storyboard.yaml", "assets/asset-manifest.yaml"}
        ),
    )
    changed = transition_v2(project, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return changed
