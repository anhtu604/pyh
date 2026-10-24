"""Medical/video gates for revisioned v2 projects, with immutable review records."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.asset_manifest import (
    AssetKind,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.gate_review import (
    GateApprovalRecord,
    GateKind,
    GateRejectionRecord,
    GateReopenRecord,
)
from healthvideo.domain.hook_outro import validate_hook_outro
from healthvideo.domain.invalidation import (
    ArtifactChange,
    InvalidationLevel,
    evaluate_invalidation,
)
from healthvideo.domain.license_ledger import LicenseLedger, validate_license_ledger
from healthvideo.domain.outline import Outline
from healthvideo.domain.posts import PostSet, validate_posts
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import (
    _POST_MEDICAL_GATE_STATES,
    TransitionContext,
    transition_v2,
)
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
from healthvideo.workflows.long_form import (
    CLIP_PLAN_ARTIFACT,
    OUTLINE_ARTIFACT,
    load_clip_scenes,
)
from healthvideo.workflows.visual_assets import recover_chart_asset_binding

MEDICAL_APPROVAL_ARTIFACT = "reviews/medical-approval.yaml"
VIDEO_APPROVAL_ARTIFACT = "reviews/video-approval.yaml"
POSTS_ARTIFACT = "posts/posts.yaml"


class _MissingPostsError(FileNotFoundError, ValueError):
    """Raised when posts/posts.yaml is missing at the video gate."""


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


def check_revision_posts(
    revision_root: Path,
    *,
    require_medical_approval: bool = False,
) -> list[str]:
    """Validate ``posts/posts.yaml`` against the revision's approved ledger and outline."""
    posts_path = revision_root / POSTS_ARTIFACT
    if not posts_path.is_file():
        return [f"{POSTS_ARTIFACT}: thiếu file bài đăng"]

    try:
        raw_posts = read_yaml(posts_path)
        posts = PostSet.model_validate(raw_posts)
    except Exception as exc:  # noqa: BLE001
        return [f"{POSTS_ARTIFACT}: {exc}"]

    ledger_path = revision_root / "evidence" / "ledger.yaml"
    if not ledger_path.is_file():
        return ["evidence/ledger.yaml: thiếu sổ cái bằng chứng"]
    ledger_data = read_yaml(ledger_path)

    approval_path = revision_root / MEDICAL_APPROVAL_ARTIFACT
    if approval_path.is_file():
        try:
            approval = GateApprovalRecord.model_validate(read_yaml(approval_path))
        except Exception as exc:  # noqa: BLE001
            return [f"{MEDICAL_APPROVAL_ARTIFACT}: {exc}"]
        if approval.kind is not GateKind.MEDICAL:
            return [f"{MEDICAL_APPROVAL_ARTIFACT}: không phải bản duyệt y khoa"]
        if approval.artifact_hashes.get("evidence/ledger.yaml") != canonical_json_hash(
            ledger_data
        ):
            return [
                "evidence/ledger.yaml: không khớp với bản đã duyệt ở cổng y khoa"
            ]
    elif require_medical_approval:
        return [f"{MEDICAL_APPROVAL_ARTIFACT}: thiếu bản duyệt cổng y khoa"]

    claims = [
        EvidenceClaim.model_validate(item) for item in ledger_data.get("claims", [])
    ]
    sources = [
        SourceRecord.model_validate(item) for item in ledger_data.get("records", [])
    ]
    approved_claim_ids = {claim.id for claim in claims}
    source_labels = [source.title for source in sources]

    outline_path = revision_root / OUTLINE_ARTIFACT
    chapter_titles: list[str] = []
    if outline_path.is_file():
        outline_data = read_yaml(outline_path)
        if (
            approval_path.is_file()
            and OUTLINE_ARTIFACT in approval.artifact_hashes
            and approval.artifact_hashes.get(OUTLINE_ARTIFACT)
            != canonical_json_hash(outline_data)
        ):
            return [
                f"{OUTLINE_ARTIFACT}: không khớp với bản đã duyệt ở cổng y khoa"
            ]
        outline = Outline.model_validate(outline_data)
        chapter_titles = [chapter.title for chapter in outline.chapters]

    return validate_posts(
        posts,
        approved_claim_ids=approved_claim_ids,
        chapter_titles=chapter_titles,
        source_labels=source_labels,
    )


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
    storyboard_path = paths["storyboard/storyboard.yaml"]
    if (
        storyboard_path.is_file()
        and read_yaml(storyboard_path).get("format_profile") == "youtube_long"
    ):
        for name in (OUTLINE_ARTIFACT, CLIP_PLAN_ARTIFACT):
            paths[name] = revision_root / name
    if manifest_path.is_file():
        manifest = load_asset_manifest(manifest_path)
        rights_path = revision_root / "assets" / "license-ledger.yaml"
        if rights_path.is_file():
            paths["assets/license-ledger.yaml"] = rights_path
        for asset in manifest.assets:
            if (
                asset.semantic
                or asset.storyboard_role == "brand"
            ):
                paths[f"asset:{asset.path}"] = revision_root / asset.path
    return paths


def video_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the video gate covers: render manifest, MP4, every clip, and posts."""
    renders = revision_root / "renders"
    paths = {
        "renders/render-manifest.json": renders / "render-manifest.json",
        "renders/video.mp4": renders / "video.mp4",
    }
    visual_index = revision_root / "reviews/visual/candidates.yaml"
    if visual_index.is_file():
        for relative in ("reviews/visual/candidates.yaml", "reviews/visual-review.yaml"):
            paths[relative] = revision_root / relative
        visual = read_yaml(visual_index)
        for asset in visual.get("assets", []):
            for candidate in asset.get("candidates", []):
                relative = candidate["path"]
                target = revision_root / relative
                if not target.resolve().is_relative_to(revision_root.resolve()):
                    raise ValueError("Visual review candidate path escapes revision")
                paths[relative] = target
        sheets = visual.get('contact_sheets') or ([visual['contact_sheet']] if visual.get('contact_sheet') else [])
        final_path = revision_root / 'reviews/visual/final-contact-sheets.yaml'
        if final_path.is_file():
            paths['reviews/visual/final-contact-sheets.yaml'] = final_path
            final = read_yaml(final_path)
            if final.get('render_sha256') != sha256_file(renders / 'video.mp4'):
                raise ValueError('Final visual contact sheets do not match current render')
            sheets = [*sheets, *final.get('sheets', [])]
        for sheet in sheets:
            relative = sheet["path"]
            target = revision_root / relative
            if not target.resolve().is_relative_to(revision_root.resolve()):
                raise ValueError("Visual review contact sheet escapes revision")
            if not target.is_file() or sha256_file(target) != sheet['sha256']:
                raise ValueError('Visual review contact sheet changed')
            paths[relative] = target
    manifest_path = renders / "render-manifest.json"
    if manifest_path.is_file():
        clips = json.loads(manifest_path.read_text(encoding="utf-8")).get("clips", {})
        for relative in clips.values():
            paths[f"renders/{relative}"] = renders / relative
        if json.loads(manifest_path.read_text(encoding="utf-8")).get('sfx'):
            for name in ('sfx.json', 'license-ledger.yaml'):
                paths[f'renders/{name}'] = renders / name
    posts_path = revision_root / POSTS_ARTIFACT
    if posts_path.is_file():
        paths[POSTS_ARTIFACT] = posts_path
        # Rejection/status must still be able to hash malformed post drafts.
        # Approval validates the PostSet before requiring these paths.
        if read_yaml(posts_path).get("thumbnail") is not None:
            for name in ("thumbnail.png", "thumbnail-background.png", "license-ledger.yaml"):
                paths[f"posts/{name}"] = revision_root / "posts" / name
    return paths


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
            "gate review requires project schema 2.0"
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
        validate_visual_budget(storyboard, manifest)
        script = Script.model_validate(read_yaml(revision_root / "script/script.yaml"))
        validate_hook_outro(script, storyboard, require_brand=True, allow_line_references=True)
        if storyboard.format_profile == "youtube_long":
            load_clip_scenes(revision_root, storyboard)
        referenced_storyboard_assets(revision_root, storyboard, manifest)
        if script.format_profile == "hook_outro_v1" or any(
            scene.source_card is not None or scene.on_screen_text is not None
            for scene in storyboard.scenes
        ):
            resolve_citations(
                script,
                read_yaml(revision_root / "evidence/ledger.yaml"),
                storyboard.scenes,
                strict_line_ids=script.format_profile == "hook_outro_v1",
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

    if kind is GateKind.VIDEO:
        posts_path = revision_root / POSTS_ARTIFACT
        if not posts_path.is_file():
            raise _MissingPostsError(
                f"video gate needs artifacts: {POSTS_ARTIFACT}"
            )
        post_errors = check_revision_posts(
            revision_root,
            require_medical_approval=False,
        )
        if post_errors:
            raise ValueError(
                "video gate refuses invalid posts/posts.yaml: "
                + "; ".join(post_errors)
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
    reason_code: str | None = None,
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
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(bound_hashes),
        validated_artifacts=frozenset(),
    )
    changed = transition_v2(
        project,
        _GATE_SIDE_STATE[kind],
        context,
        reason_code=reason if reason_code is None else reason_code,
        resume_state=resume_state,
        entered_at=now,
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
    if target is WorkflowState.PRODUCTION_IN_PROGRESS:
        revision_root = _revision_root(project_dir, project)
        approval_path = revision_root / MEDICAL_APPROVAL_ARTIFACT
        approved = (
            GateApprovalRecord.model_validate(read_yaml(approval_path)).artifact_hashes
            if approval_path.is_file() else None
        )
        if approved != hash_reviewed_artifacts(medical_reviewed_paths(revision_root)):
            raise ValueError(
                "Tệp đã duyệt y khoa (storyboard, assets, script, ledger…) đã đổi; "
                "bác sĩ phải chạy `review reopen --gate medical` rồi nộp lại cổng y khoa"
            )
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


def reopen_gate(
    project_dir: Path,
    kind: GateKind,
    *,
    reviewer: str,
    reason: str,
    changed: list[str],
    resume_state: WorkflowState,
    now: datetime,
) -> GateReopenRecord:
    """Reopen medical review, preserving superseded approvals as audit history."""
    if kind is not GateKind.MEDICAL:
        raise ValueError("only the medical gate can be reopened")
    project = _load_project(project_dir)
    if project.state not in _POST_MEDICAL_GATE_STATES:
        raise ValueError(f"medical reopen is not allowed from {project.state.value}")
    if not changed:
        raise ValueError("changed artifacts must be nonempty")
    for relative in changed:
        if (
            not relative
            or "\\" in relative
            or PurePosixPath(relative).is_absolute()
            or PureWindowsPath(relative).drive
            or ".." in PurePosixPath(relative).parts
            or not PurePosixPath(relative).parts
        ):
            raise ValueError(f"changed artifact must be a revision-relative POSIX path: {relative!r}")
    revision_root = _revision_root(project_dir, project)
    manifest = load_asset_manifest(revision_root / "assets/asset-manifest.yaml")
    decision = evaluate_invalidation(
        [ArtifactChange(Path(path), frozenset()) for path in changed], manifest
    )
    reasons = sorted(decision.reason_codes)
    if decision.level is not InvalidationLevel.MEDICAL:
        raise ValueError(
            f"change does not need medical re-review: {decision.level.name.lower()}: "
            + ",".join(reasons)
        )
    prior = GateApprovalRecord.model_validate(
        read_yaml(revision_root / MEDICAL_APPROVAL_ARTIFACT)
    )
    hashes = hash_reviewed_artifacts(medical_reviewed_paths(revision_root)) or {"none": "0" * 64}
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(hashes),
        validated_artifacts=frozenset(),
    )
    updated = transition_v2(
        project, WorkflowState.NEEDS_MEDICAL_REVISION, context,
        reason_code="medical_reopen:" + ",".join(reasons),
        resume_state=resume_state, entered_at=now,
    )
    timestamp = now.astimezone().strftime("%Y%m%dT%H%M%S%f")

    def history_path(gate: GateKind, suffix: str) -> Path:
        directory = revision_root / "reviews" / gate.value
        path = directory / f"{timestamp}-{suffix}.yaml"
        counter = 1
        while path.exists():
            path = directory / f"{timestamp}-{suffix}-{counter}.yaml"
            counter += 1
        return path

    moves = {
        gate: history_path(gate, "superseded-approval")
        for gate in GateKind
        if (revision_root / _GATE_APPROVAL_ARTIFACT[gate]).exists()
    }
    record = GateReopenRecord(
        kind=kind, reviewer=reviewer, reopened_at=now, from_state=project.state,
        reason=reason, resume_state=resume_state, changed_artifacts=changed,
        invalidation_reasons=reasons,
        superseded_approvals={gate.value: path.relative_to(revision_root).as_posix()
                              for gate, path in moves.items()},
        prior_approval_hashes=prior.artifact_hashes, artifact_hashes=hashes,
    )
    record_path = history_path(kind, "reopened")
    # ponytail: a crash between approval moves and project write keeps the old state
    # without current approval, failing closed in production; upgrade = recovery check.
    for gate, destination in moves.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(revision_root / _GATE_APPROVAL_ARTIFACT[gate], destination)
    write_yaml_once(record_path, record.model_dump(mode="json"))
    write_yaml_atomic(project_dir / "project.yaml", updated.model_dump(mode="json"))
    return record
