"""v2 medical/video gate: hash the artifacts a gate covers, approve, reject, resume.

Mirrors `workflows/review.py` (v1) but reads the v2 layout (`revisions/<id>/...`),
enforces the semantic asset manifest before a medical approval, and adds a
reject/resume path v1 never had. v1 stays untouched; this module never imports it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.asset_manifest import (
    AssetKind,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.gate_review import (
    GateApprovalRecord,
    GateKind,
    GateRejectionRecord,
)
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.license_ledger import LicenseLedger, validate_license_ledger
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.workflows.citations import resolve_citations
from healthvideo.workflows.visual_assets import recover_chart_asset_binding

MEDICAL_APPROVAL_ARTIFACT = "reviews/medical-approval.yaml"
VIDEO_APPROVAL_ARTIFACT = "reviews/video-approval.yaml"

_GATE_OPEN_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.AWAITING_MEDICAL_REVIEW,
    GateKind.VIDEO: WorkflowState.AWAITING_VIDEO_REVIEW,
}
_GATE_APPROVED_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.MEDICALLY_APPROVED,
    GateKind.VIDEO: WorkflowState.VIDEO_APPROVED,
}
_GATE_APPROVAL_ARTIFACT: dict[GateKind, str] = {
    GateKind.MEDICAL: MEDICAL_APPROVAL_ARTIFACT,
    GateKind.VIDEO: VIDEO_APPROVAL_ARTIFACT,
}
_GATE_SIDE_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.NEEDS_MEDICAL_REVISION,
    GateKind.VIDEO: WorkflowState.NEEDS_PRODUCTION_REVISION,
}


def medical_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the medical gate covers; missing entries are dropped by the caller."""
    paths = {
        "evidence/ledger.yaml": revision_root / "evidence" / "ledger.yaml",
        "script/script.yaml": revision_root / "script" / "script.yaml",
        "storyboard/storyboard.yaml": revision_root / "storyboard" / "storyboard.yaml",
        "assets/asset-manifest.yaml": revision_root / "assets" / "asset-manifest.yaml",
        "profiles/pronunciation.vi.yaml": pronunciation_module.PRONUNCIATION_PROFILE_PATH,
    }
    manifest_path = paths["assets/asset-manifest.yaml"]
    if manifest_path.is_file():
        manifest = load_asset_manifest(manifest_path)
        rights_path = revision_root / "assets" / "license-ledger.yaml"
        if rights_path.is_file():
            paths["assets/license-ledger.yaml"] = rights_path
        for asset in manifest.assets:
            if asset.semantic or asset.storyboard_role == "brand":
                paths[f"asset:{asset.path}"] = revision_root / asset.path
    return paths


def video_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the video gate covers: the render manifest and the MP4."""
    return {
        "renders/render-manifest.json": revision_root
        / "renders"
        / "render-manifest.json",
        "renders/video.mp4": revision_root / "renders" / "video.mp4",
    }


_REVIEWED_PATHS = {
    GateKind.MEDICAL: medical_reviewed_paths,
    GateKind.VIDEO: video_reviewed_paths,
}


def hash_reviewed_artifacts(paths: dict[str, Path]) -> dict[str, str]:
    """Hash whichever of `paths` exist; missing artifacts are silently omitted.

    Approve relies on the caller checking nothing is missing first; reject
    tolerates gaps, since "an asset is missing" can itself be the rejection
    reason and must not crash the audit trail.
    """
    return {
        name: _hash_artifact(path) for name, path in paths.items() if path.is_file()
    }


def _hash_artifact(path: Path) -> str:
    if path.suffix == ".yaml":
        return canonical_json_hash(read_yaml(path))
    if path.suffix == ".json":
        return canonical_json_hash(json.loads(path.read_text(encoding="utf-8")))
    return sha256_file(path)


def _load_project(project_dir: Path) -> ProjectManifestV2:
    manifest_path = project_dir / "project.yaml"
    manifest_data = read_yaml(manifest_path)
    if manifest_data.get("schema_version") != "2.0":
        raise ValueError(
            "gate review requires project schema 2.0; run 'healthvideo project migrate' first"
        )
    return ProjectManifestV2.model_validate(manifest_data)


def _revision_root(project_dir: Path, project: ProjectManifestV2) -> Path:
    return project_dir / "revisions" / project.active_revision


def approve_gate(
    project_dir: Path, kind: GateKind, *, reviewer: str, note: str = "", now: datetime
) -> GateApprovalRecord:
    """Approve `kind`'s gate: validate, hash, write the record once, advance state."""
    project = _load_project(project_dir)
    revision_root = _revision_root(project_dir, project)
    approval_path = revision_root / _GATE_APPROVAL_ARTIFACT[kind]
    if approval_path.is_file():
        raise FileExistsError(
            f"{kind.value} gate already approved for revision {project.active_revision}"
        )

    expected = _GATE_OPEN_STATE[kind]
    if project.state is not expected:
        raise ValueError(f"{kind.value} gate requires project state {expected.value}")

    if kind is GateKind.MEDICAL:
        recover_chart_asset_binding(project_dir)
        if (revision_root / "workflow/pending-hook-outro.yaml").exists():
            raise ValueError("medical gate refuses pending hook/outro authoring")
        manifest = load_asset_manifest(revision_root / "assets" / "asset-manifest.yaml")
        validate_asset_manifest(revision_root, manifest)
        hardened_highlights = [
            asset
            for asset in manifest.assets
            if asset.kind is AssetKind.EVIDENCE_HIGHLIGHT and asset.rights_required
        ]
        storyboard = Storyboard.model_validate(
            read_yaml(revision_root / "storyboard/storyboard.yaml")
        )
        validate_visual_budget(storyboard)
        script = Script.model_validate(read_yaml(revision_root / "script/script.yaml"))
        validate_hook_outro(script, storyboard, require_brand=True)
        referenced_storyboard_assets(revision_root, storyboard, manifest)
        if script.format_profile == "hook_outro_v1":
            resolve_citations(
                script,
                read_yaml(revision_root / "evidence/ledger.yaml"),
                storyboard.scenes,
                strict_line_ids=True,
            )
        for asset in hardened_highlights:
            if not any(
                scene.evidence_highlight is not None
                and scene.evidence_highlight.image == asset.path
                and scene.evidence_highlight.source_id == asset.source
                and scene.evidence_highlight.page is not None
                and scene.evidence_highlight.crop_x is not None
                for scene in storyboard.scenes
            ):
                raise ValueError(
                    "medical gate needs complete highlight crop provenance"
                )
        for scene in storyboard.scenes:
            highlight = scene.evidence_highlight
            if highlight is None or highlight.crop_x is None:
                continue
            if not any(
                asset.path == highlight.image
                and asset.kind is AssetKind.EVIDENCE_HIGHLIGHT
                and asset.rights_required
                and asset.source == highlight.source_id
                for asset in hardened_highlights
            ):
                raise ValueError(
                    "medical gate needs complete highlight crop provenance"
                )
        rights_path = revision_root / "assets/license-ledger.yaml"
        if (
            any(
                asset.kind is AssetKind.DATA_CHART or asset.rights_required
                for asset in manifest.assets
            )
            and not rights_path.is_file()
        ):
            raise FileNotFoundError("medical gate needs asset license ledger")
        if rights_path.is_file():
            validate_license_ledger(
                manifest,
                LicenseLedger.model_validate(read_yaml(rights_path)),
                revision_root.name,
            )
        pronunciation_module.load_pronunciation_lexicon(
            pronunciation_module.PRONUNCIATION_PROFILE_PATH
        )

    paths = _REVIEWED_PATHS[kind](revision_root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"{kind.value} gate needs artifacts: {', '.join(sorted(missing))}"
        )
    artifact_hashes = hash_reviewed_artifacts(paths)

    record = GateApprovalRecord(
        kind=kind,
        reviewer=reviewer,
        reviewed_at=now,
        artifact_hashes=artifact_hashes,
        note=note,
    )
    write_yaml_once(approval_path, record.model_dump(mode="json"))

    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(artifact_hashes),
        validated_artifacts=frozenset({_GATE_APPROVAL_ARTIFACT[kind]}),
    )
    changed = transition_v2(project, _GATE_APPROVED_STATE[kind], context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return record


def reject_gate(
    project_dir: Path,
    kind: GateKind,
    *,
    reviewer: str,
    reason: str,
    resume_state: WorkflowState,
    now: datetime,
) -> GateRejectionRecord:
    """Reject `kind`'s gate: record why, enter the matching side state."""
    project = _load_project(project_dir)
    expected = _GATE_OPEN_STATE[kind]
    if project.state is not expected:
        raise ValueError(f"{kind.value} gate requires project state {expected.value}")

    revision_root = _revision_root(project_dir, project)
    artifact_hashes = hash_reviewed_artifacts(_REVIEWED_PATHS[kind](revision_root))
    bound_hashes = artifact_hashes or {"none": "0" * 64}

    record = GateRejectionRecord(
        kind=kind,
        reviewer=reviewer,
        reviewed_at=now,
        reason=reason,
        resume_state=resume_state,
        artifact_hashes=bound_hashes,
    )
    timestamp = now.astimezone().strftime("%Y%m%dT%H%M%S%f")
    target_dir = revision_root / "reviews" / kind.value
    target_dir.mkdir(parents=True, exist_ok=True)
    rejection_path = target_dir / f"{timestamp}-rejected.yaml"
    counter = 1
    while rejection_path.is_file():
        rejection_path = target_dir / f"{timestamp}-rejected-{counter}.yaml"
        counter += 1

    write_yaml_once(rejection_path, record.model_dump(mode="json"))

    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(bound_hashes),
        validated_artifacts=frozenset(),
    )
    changed = transition_v2(
        project,
        _GATE_SIDE_STATE[kind],
        context,
        reason_code=reason,
        resume_state=resume_state,
        entered_at=now,
    )
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return record


def resume_gate(
    project_dir: Path,
    kind: GateKind,
    *,
    target: WorkflowState,
    reason_code: str | None = None,
    now: datetime,
) -> WorkflowState:
    """Exit the gate's side state back to `target` after the reviewer's note is addressed."""
    project = _load_project(project_dir)
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(
            {"resume": target.value, "at": now.isoformat()}
        ),
        validated_artifacts=frozenset(),
        reason_code=reason_code,
    )
    changed = transition_v2(project, target, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return changed.state
