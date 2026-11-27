"""Medical/video gates for revisioned v2 projects, with immutable review records."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from healthvideo.approver_pin import verify_pin
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
from healthvideo.domain.license_ledger import (
    LicenseEntry,
    LicenseLedger,
    validate_license_ledger,
)
from healthvideo.domain.outline import Outline
from healthvideo.domain.posts import PostSet, validate_posts
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.quality_standards import QualityReport, validate_r5_contract
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import (
    _POST_MEDICAL_GATE_STATES,
    TransitionContext,
    transition_v2,
)
from healthvideo.domain.storyboard import Storyboard
from healthvideo.domain.visual_budget import validate_visual_budget
from healthvideo.render.input import R5RevisionAsset
from healthvideo.render.quality import (
    measure_r5_quality,
    resolve_r5_shots,
    validate_r5_quality,
)
from healthvideo.storage.files import (
    canonical_json_hash,
    read_agent_yaml,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.visuals.medanim_assets import (
    MAX_ASSET_BYTES,
    assert_safe_path,
    copy_used_assets,
    load_asset_catalog,
)
from healthvideo.workflows.citations import resolve_citations
from healthvideo.workflows.long_form import (
    CLIP_PLAN_ARTIFACT,
    OUTLINE_ARTIFACT,
    load_clip_scenes,
)
from healthvideo.workflows.standards import remember
from healthvideo.workflows.visual_assets import recover_chart_asset_binding

MEDICAL_APPROVAL_ARTIFACT = "reviews/medical-approval.yaml"
VIDEO_APPROVAL_ARTIFACT = "reviews/video-approval.yaml"
POSTS_ARTIFACT = "posts/posts.yaml"
R5_CATALOG = "assets/r5/catalog.yaml"
R5_USED_ASSETS = "assets/r5/used-assets.yaml"
R5_LICENSE_LEDGER = "assets/r5/license-ledger.yaml"
R5_QUALITY_REPORT = "reviews/quality-report.json"


def _r5_asset_paths(board: Storyboard) -> set[str]:
    return {path for scene in board.scenes for shot in scene.shots for path in shot.asset_paths}


def snapshot_r5_assets(
    revision_root: Path,
    board: Storyboard,
    *,
    source_root: Path | None = None,
) -> None:
    """Pin only selected catalog records/bytes before medical submission.

    When ``source_root`` points to an external library directory distinct from
    ``revision_root``, selected assets are copied and verified via
    ``copy_used_assets(records, ids, source_root, revision_root)``. When assets
    are already staged in ``revision_root`` (``source_root`` is ``None`` or the
    same directory), files are verified in place without self-overwriting.
    Refuses to overwrite once medical approval exists.
    """
    used_paths = _r5_asset_paths(board)
    if board.quality_profile != "r5_v1" or not used_paths:
        return
    if (revision_root / MEDICAL_APPROVAL_ARTIFACT).exists():
        raise ValueError("R5 snapshot requires reopening the medical gate")
    records = load_asset_catalog(revision_root / R5_CATALOG)
    by_path = {record.file: record for record in records}
    missing = used_paths - by_path.keys()
    if missing:
        raise ValueError(f"R5 catalog missing used asset: {min(missing)}")
    selected_ids = [by_path[path].id for path in sorted(used_paths)]
    rev_resolved = assert_safe_path(revision_root).resolve()
    if source_root is not None and assert_safe_path(source_root).resolve() != rev_resolved:
        used = copy_used_assets(records, selected_ids, source_root, revision_root)
    else:
        used = tuple(by_path[path] for path in sorted(used_paths))
        for record in used:
            asset_path = assert_safe_path(revision_root / record.file)
            if not asset_path.resolve().is_relative_to(rev_resolved) or not asset_path.is_file():
                raise ValueError(f"R5 asset missing or escapes revision: {record.file}")
            if asset_path.stat().st_size > MAX_ASSET_BYTES or sha256_file(asset_path) != record.sha256:
                raise ValueError(f"R5 asset size/SHA-256 mismatch: {record.file}")
    # Preserve the complete provenance, including evidence, acquisition date and changes.
    write_yaml_atomic(revision_root / R5_USED_ASSETS,
                      {"assets": [record.model_dump(mode="json") for record in used]})
    ledger = LicenseLedger(entries=tuple(LicenseEntry(
        path=r.file, source=r.source_page, creator=r.author, license=r.license,
        rights_basis=r.license_evidence or r.license_url or r.source_page,
        revision=revision_root.name, sha256=r.sha256,
    ) for r in used))
    write_yaml_atomic(revision_root / R5_LICENSE_LEDGER, ledger.model_dump(mode="json"))
    load_r5_revision_assets(revision_root, board)


def load_r5_revision_assets(revision_root: Path, board: Storyboard) -> tuple[R5RevisionAsset, ...]:
    """Read and verify the pinned snapshot only; refuse missing provenance/rights."""
    paths = _r5_asset_paths(board)
    if board.quality_profile != "r5_v1" or not paths:
        return ()
    records = load_asset_catalog(revision_root / R5_USED_ASSETS)
    if {r.file for r in records} != paths:
        raise ValueError("R5 used-asset snapshot differs from the approved shots")
    manifest = load_asset_manifest(revision_root / "assets/asset-manifest.yaml")
    index = {asset.path: asset for asset in manifest.assets}
    ledger = LicenseLedger.model_validate(read_yaml(revision_root / R5_LICENSE_LEDGER))
    rights = {entry.path: entry for entry in ledger.entries}
    mechanism_paths = {p for scene in board.scenes for shot in scene.shots
                       if shot.kind == "mechanism" for p in shot.asset_paths}
    result = []
    for record in records:
        path = assert_safe_path(revision_root / record.file)
        if not path.resolve().is_relative_to(revision_root.resolve()) or sha256_file(path) != record.sha256:
            raise ValueError(f"R5 asset changed: {record.file}")
        asset, right = index.get(record.file), rights.get(record.file)
        if asset is None or asset.sha256 != record.sha256 or asset.license != record.license:
            raise ValueError(f"R5 asset manifest differs from catalog: {record.file}")
        if record.file in mechanism_paths and not asset.semantic:
            raise ValueError(f"R5 mechanism asset must be semantic: {record.file}")
        if (right is None or right.sha256 != record.sha256 or right.license != record.license
                or right.creator != record.author or right.source != record.source_page
                or right.revision != revision_root.name):
            raise ValueError(f"R5 asset license ledger mismatch: {record.file}")
        result.append(R5RevisionAsset(
            id=record.id, path=record.file, title=record.attribution or Path(record.file).stem,
            author=record.author, repository=urlsplit(record.source_page).hostname,
            license=record.license, license_url=record.license_url,
            source_page=record.source_page, sha256=record.sha256,
        ))
    return tuple(result)


def r5_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Byte-bind R5 source/provenance files and every shot asset, including missing ones."""
    board_path = revision_root / "storyboard/storyboard.yaml"
    if not board_path.is_file():
        return {}
    raw = read_yaml(board_path)
    if raw.get("quality_profile") != "r5_v1":
        return {}
    paths = {}
    for scene in raw.get("scenes", []):
        for shot in scene.get("shots", []):
            for relative in shot.get("asset_paths", []):
                target = assert_safe_path(revision_root / relative)
                if not target.resolve().is_relative_to(revision_root.resolve()):
                    raise ValueError("R5 asset escapes revision")
                paths[f"r5-byte:{relative}"] = target
    if paths:
        for relative in (R5_CATALOG, R5_USED_ASSETS, R5_LICENSE_LEDGER):
            paths[f"r5-byte:{relative}"] = assert_safe_path(revision_root / relative)
    for source in sorted((revision_root / "evidence").rglob("*")):
        if source.is_file():
            paths[f"r5-byte:{source.relative_to(revision_root).as_posix()}"] = assert_safe_path(source)
    return paths


def validate_r5_render_report(revision_root: Path, run_dir: Path | None = None) -> None:
    """Recompute the same aligned validator and bind it to the actual rendered input."""
    run_dir = run_dir or revision_root / "renders"
    approved = Storyboard.model_validate(read_yaml(revision_root / "storyboard/storyboard.yaml"))
    if approved.quality_profile != "r5_v1":
        return
    data = json.loads((run_dir / "render-input.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "render-manifest.json").read_text(encoding="utf-8"))
    report_path = run_dir / "quality-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    board = Storyboard.model_validate(data)
    resolved = resolve_r5_shots(board)
    measured = measure_r5_quality(resolved)
    validate_r5_quality(measured, estimated=False)
    if (board.quality_profile != "r5_v1" or board.r5_contract != approved.r5_contract
            or canonical_json_hash(report.get("quality")) != canonical_json_hash(measured.model_dump(mode="json"))
            or report.get("input_hash") != manifest.get("input_hash")
            or report.get("renderer_identity") != manifest.get("renderer_identity")
            or report.get("render_input_sha256") != canonical_json_hash(data)
            or manifest.get("render_input_sha256") != canonical_json_hash(data)
            or manifest.get("quality_report_sha256") != sha256_file(report_path)
            or any(a.resolved_shots != b.resolved_shots for a, b in zip(board.scenes, resolved.scenes, strict=True))):
        raise ValueError("R5 quality report differs from current render input/renderer")
    QualityReport.model_validate(report["quality"])
    if data.get("r5_assets", []) != [a.model_dump(mode="json") for a in load_r5_revision_assets(revision_root, approved)]:
        raise ValueError("R5 rendered asset metadata differs from revision snapshot")


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
        raw_posts = read_agent_yaml(posts_path)
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
    from healthvideo.workflows.external_revision import EXTERNAL, is_external

    if is_external(revision_root):
        return {
            name: path for name, path in [
                ('script/script.yaml', revision_root / 'script/script.yaml'),
                ('evidence/ledger.yaml', revision_root / 'evidence/ledger.yaml'),
                (EXTERNAL, revision_root / EXTERNAL),
                ('profiles/pronunciation.vi.yaml', pronunciation_module.PRONUNCIATION_PROFILE_PATH),
                ('external/pronunciation.vi.yaml', revision_root / 'profiles/pronunciation.vi.yaml'),
                ('reviews/script-review-log.yaml', revision_root / 'reviews/script-review-log.yaml'),
            ]
        }
    paths = {
        "evidence/ledger.yaml": revision_root / "evidence" / "ledger.yaml",
        "script/script.yaml": revision_root / "script" / "script.yaml",
        "storyboard/storyboard.yaml": revision_root / "storyboard" / "storyboard.yaml",
        "assets/asset-manifest.yaml": revision_root / "assets" / "asset-manifest.yaml",
        "profiles/pronunciation.vi.yaml": pronunciation_module.PRONUNCIATION_PROFILE_PATH,
    }
    if (revision_root / 'workflow/standards.yaml').is_file():
        paths['workflow/standards.yaml'] = revision_root / 'workflow/standards.yaml'
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
    paths.update(r5_reviewed_paths(revision_root))
    return paths


def video_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the video gate covers: render manifest, MP4, every clip, and posts."""
    renders = revision_root / "renders"
    paths = {
        "renders/render-manifest.json": renders / "render-manifest.json",
        "renders/video.mp4": renders / "video.mp4",
    }
    from healthvideo.workflows.external_revision import EXTERNAL, is_external

    if is_external(revision_root):
        paths[EXTERNAL] = revision_root / EXTERNAL
        paths['reviews/product-review-log.yaml'] = revision_root / 'reviews/product-review-log.yaml'
        paths['reviews/video-qa.json'] = revision_root / 'reviews/video-qa.json'
        thumb = revision_root / 'posts/thumbnail.png'
        if thumb.is_file():
            paths['posts/thumbnail.png'] = thumb
    board_path = revision_root / "storyboard/storyboard.yaml"
    if board_path.is_file() and read_yaml(board_path).get("quality_profile") == "r5_v1":
        paths.update(r5_reviewed_paths(revision_root))
        for relative in ("renders/render-input.json", "renders/quality-report.json", R5_QUALITY_REPORT):
            paths[relative] = revision_root / relative
    if (revision_root / 'workflow/standards.yaml').is_file():
        paths['workflow/standards.yaml'] = revision_root / 'workflow/standards.yaml'
    from healthvideo.workflows.review_frames import imported_reviewed_paths

    paths.update(imported_reviewed_paths(revision_root))
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
    for name in ('video-qa.json', 'pronunciation-qa.json'):
        path = revision_root / 'reviews' / name
        if path.is_file():
            paths[f'reviews/{name}'] = path
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
        name: (sha256_file(path) if name.startswith("r5-byte:") else _hash_artifact(path))
        for name, path in paths.items() if path.is_file()
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
    project_dir: Path, kind: GateKind, *, reviewer: str, note: str = "", now: datetime,
    accept_pronunciation: bool = False, pronunciation_pin: str | None = None,
    pin_file: Path | None = None,
    doctor_pin: str | None = None,
) -> GateApprovalRecord:
    """Approve `kind`'s gate: validate, hash, write the record once, advance state."""
    project = _load_project(project_dir)
    revision_root = _revision_root(project_dir, project)
    pronunciation_acceptance = None
    approval_path = revision_root / _GATE_APPROVAL_ARTIFACT[kind]
    if approval_path.is_file():
        raise FileExistsError(
            f"{kind.value} gate already approved for revision {project.active_revision}"
        )

    expected = _GATE_OPEN_STATE[kind]
    if project.state is not expected:
        raise ValueError(f"{kind.value} gate requires project state {expected.value}")

    from healthvideo.workflows.external_revision import (
        is_external,
        validate_import,
        validate_render,
    )

    external = is_external(revision_root)
    if external and (not doctor_pin or not verify_pin(doctor_pin, path=pin_file)):
        raise ValueError('Bản dựng ngoài cần PIN bác sĩ đúng để duyệt cổng')
    if kind is GateKind.MEDICAL and external:
        if (revision_root / 'workflow/pending-hook-outro.yaml').exists():
            raise ValueError('medical gate refuses pending hook/outro authoring')
        validate_import(revision_root)
        pronunciation_module.load_pronunciation_lexicon(pronunciation_module.PRONUNCIATION_PROFILE_PATH)
        pronunciation_module.load_pronunciation_lexicon(revision_root / 'profiles/pronunciation.vi.yaml')
    if kind is GateKind.MEDICAL and not external:
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
        if storyboard.quality_profile == "r5_v1":
            load_r5_revision_assets(revision_root, storyboard)
        validate_visual_budget(storyboard, manifest)
        script = Script.model_validate(read_yaml(revision_root / "script/script.yaml"))
        from healthvideo.domain.clip_plan import validate_clip_script

        validate_clip_script(script, storyboard)
        if storyboard.quality_profile == "r5_v1":
            validate_r5_contract(storyboard, script)
            # Same timing source as submission (measured draft voice, else estimate); a raw
            # agent-frame check here let a submitted draft fail approval on S17 (PYH-001).
            from healthvideo.workflows.draft import validate_estimated_layout

            validate_estimated_layout(project_dir, script, storyboard, manifest)
        validate_hook_outro(script, storyboard, require_brand=True, allow_line_references=True)
        if storyboard.format_profile == "youtube_long":
            # The medical approval record does not exist yet while this gate is being approved.
            load_clip_scenes(revision_root, storyboard, require_medical_approval=False)
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
        if external:
            from healthvideo.workflows.produce import (
                _ensure_v2_medical_approval_current,
            )

            _ensure_v2_medical_approval_current(revision_root)
            validate_render(revision_root)
        if not external and read_yaml(revision_root / "storyboard/storyboard.yaml").get("quality_profile") == "r5_v1":
            approval = GateApprovalRecord.model_validate(read_yaml(revision_root / MEDICAL_APPROVAL_ARTIFACT))
            if hash_reviewed_artifacts(medical_reviewed_paths(revision_root)) != approval.artifact_hashes:
                raise ValueError("R5 video gate requires current medical approval")
            validate_r5_render_report(revision_root)
            if sha256_file(revision_root / R5_QUALITY_REPORT) != sha256_file(revision_root / "renders/quality-report.json"):
                raise ValueError("R5 quality report is stale")
        pronunciation_acceptance = _check_video_qa(
            revision_root, accept_pronunciation=accept_pronunciation,
            pronunciation_pin=pronunciation_pin, pin_file=pin_file,
        )
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

    from healthvideo.workflows import product_review, script_review

    if external:
        script_review.require_passed_review(project_dir)
        if kind is GateKind.VIDEO:
            product_review.require_passed_review(project_dir)
    paths = _REVIEWED_PATHS[kind](revision_root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"{kind.value} gate needs artifacts: {', '.join(sorted(missing))}"
        )
    artifact_hashes = hash_reviewed_artifacts(paths)

    from healthvideo.workflows import product_review, script_review

    script_review.require_passed_review(project_dir)
    if kind is GateKind.VIDEO:
        product_review.require_passed_review(project_dir)

    record = GateApprovalRecord(
        kind=kind,
        reviewer=reviewer,
        reviewed_at=now,
        artifact_hashes=artifact_hashes,
        note=note,
        pronunciation_acceptance=pronunciation_acceptance,
    )
    write_yaml_once(approval_path, record.model_dump(mode="json"))

    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(artifact_hashes),
        validated_artifacts=frozenset({_GATE_APPROVAL_ARTIFACT[kind]}),
    )
    changed = transition_v2(project, _GATE_APPROVED_STATE[kind], context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    remember(project_dir, gate=kind.value, revision=project.active_revision,
             kind="approve_note", text=note, reviewer=reviewer, at=now)
    return record


def _check_video_qa(revision_root: Path, *, accept_pronunciation: bool,
                    pronunciation_pin: str | None, pin_file: Path | None) -> str | None:
    """A doctor's listening decision covers only the exact pronunciation report."""
    qa_path = revision_root / 'reviews/video-qa.json'
    report_path = revision_root / 'reviews/pronunciation-qa.json'
    qa = read_yaml(qa_path) if qa_path.is_file() else {}
    if qa_path.is_file():
        status = qa.get('status')
        # 'failed' is emitted for pronunciation blocks, whose existing doctor/PIN
        # exception remains below. Every unknown or absent state fails closed.
        if not isinstance(status, str) or status not in {'render_complete', 'passed', 'failed', 'error'}:
            raise ValueError('video gate refuses missing or unknown video QA status')
    pronunciation = read_yaml(report_path) if report_path.is_file() else {}
    manifest_path = revision_root / 'renders/render-manifest.json'
    manifest = read_yaml(manifest_path) if manifest_path.is_file() else {}
    alignment_hashes = manifest.get('alignment_sha256', {})
    if 'pronunciation-qa.json' in alignment_hashes:
        if not qa_path.is_file() or not report_path.is_file():
            raise ValueError('video QA requires the rendered pronunciation and video QA reports')
        if sha256_file(report_path) != alignment_hashes['pronunciation-qa.json']:
            raise ValueError('pronunciation QA report hash does not match render manifest')
        if manifest.get('input_hash') is not None and qa.get('input_hash') != manifest['input_hash']:
            raise ValueError('video QA input_hash does not match render manifest')
    blocked = any(flag.get('severity') == 'block' for flag in pronunciation.get('flags', []))
    pronunciation_qa = qa.get('pronunciation', {})
    blocked = blocked or pronunciation_qa.get('passed') is False
    if qa:
        failed_checks = [key for key, passed in qa.get('checks', {}).items()
                         if passed is False]
        other_failed = any(isinstance(value, dict) and value.get('passed') is False
                           for key, value in qa.items() if key != 'pronunciation')
        if (failed_checks or other_failed or qa.get('errors')
                or qa.get('status') == 'error'
                or (qa.get('status') == 'failed' and not blocked)):
            raise ValueError('video gate refuses failed video QA')
        expected = pronunciation_qa.get('report_sha256')
        if expected and (not report_path.is_file() or sha256_file(report_path) != expected):
            raise ValueError('video pronunciation QA report hash does not match render')
    if not blocked:
        return None
    if not accept_pronunciation:
        raise ValueError('video gate refuses blocking pronunciation QA; bác sĩ cần đã nghe, chấp nhận')
    if not pronunciation_pin or not verify_pin(pronunciation_pin, path=pin_file):
        raise ValueError('pronunciation acceptance requires correct doctor PIN')
    if not report_path.is_file():
        raise ValueError('pronunciation acceptance requires the pronunciation QA report')
    return canonical_json_hash(pronunciation)


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
    remember(project_dir, gate=kind.value, revision=project.active_revision,
             kind="reject", text=reason, reviewer=reviewer, at=now)
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
                "bác sĩ bấm \"Mở lại cổng y khoa để sửa\" trên thẻ dự án trong app"
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
    remember(project_dir, gate=kind.value, revision=project.active_revision,
             kind="reopen", text=reason, reviewer=reviewer, at=now)
    return record
