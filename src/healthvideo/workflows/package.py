"""Assemble a reviewed video's upload payload and audit manifest.

Packaging is the last step before a human uploads the video by hand: it copies
the approved MP4 next to the caption, the full source list and an audit
manifest. It never calls a publishing API; v2 advances to ``packaged`` only
after the payload directory is atomically promoted.
"""

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, TypeVar

from pydantic import BaseModel

from healthvideo.domain.asset_manifest import AssetKind, AssetManifest
from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
from healthvideo.domain.project import ProjectManifest, ProjectState
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.review import ReviewKind, ReviewRecord
from healthvideo.domain.script import Script
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.domain.storyboard import Storyboard
from healthvideo.render.input import RenderInput
from healthvideo.render.run import (
    OUTPUT_NAME,
    PRODUCTION_ARTIFACT,
    RENDER_INPUT_NAME,
    production_run_dir,
)
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    replace_directory_atomic,
    sha256_file,
    write_text_atomic,
    write_yaml_atomic,
)
from healthvideo.storage.project_layout import ProjectLayout, resolve_project_layout
from healthvideo.workflows.citations import resolve_citations
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    VIDEO_APPROVAL_ARTIFACT,
    hash_reviewed_artifacts,
    medical_reviewed_paths,
    video_reviewed_paths,
)
from healthvideo.workflows.review import ensure_approval_current

LedgerEntry = TypeVar("LedgerEntry", bound=BaseModel)

PUBLISH_DIRECTORY = "publish"
CAPTION_NAME = "caption.txt"
SOURCES_NAME = "sources.md"
PACKAGE_MANIFEST_NAME = "manifest.json"
PROJECT_MANIFEST_NAME = "project.yaml"
AI_DISCLOSURE_NAME = "ai-disclosure.json"
AI_DISCLOSURE_GUIDANCE = (
    "Video có đoạn minh họa do AI tạo. Khi đăng thủ công, operator bật nhãn nội "
    "dung do AI tạo (AI-generated content) nếu nền tảng yêu cầu. Tệp này không gọi "
    "API đăng bài, không tự bật nhãn và không xác nhận đã đáp ứng mọi yêu cầu của "
    "nền tảng."
)
DISCLAIMER = (
    "Nội dung chỉ mang tính thông tin chung, không thay thế khám, chẩn đoán "
    "hoặc điều trị y khoa. Hãy trao đổi với bác sĩ của bạn trước khi thay đổi "
    "chế độ ăn hoặc thuốc."
)


def package_project(project_dir: Path) -> Path:
    """Publish `publish/` for a project whose video approval is still current.

    Returns the published directory. Refuses a project that has not passed the
    video gate, and refuses an approval that is missing or stale, so no package
    leaves the machine without an auditable doctor approval behind it.
    """
    layout = resolve_project_layout(project_dir)
    if layout.schema_version == "2.0":
        return _package_v2(layout)
    return _package_v1(layout)


def _package_v1(layout: ProjectLayout) -> Path:
    project_dir = layout.project_dir
    project = layout.manifest
    assert isinstance(project, ProjectManifest)
    if project.state is not ProjectState.APPROVED_TO_PUBLISH:
        raise ValueError(
            "Packaging requires project state "
            f"{ProjectState.APPROVED_TO_PUBLISH.value}, not {project.state.value}"
        )
    try:
        medical_approval = ensure_approval_current(
            project_dir, project, ReviewKind.MEDICAL
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(
            "Packaging requires a medical approval record; "
            "run 'healthvideo review medical'"
        ) from error
    try:
        video_approval = ensure_approval_current(
            project_dir, project, ReviewKind.VIDEO
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(
            "Packaging requires a video approval record; "
            "run 'healthvideo review video'"
        ) from error

    ledger, script, _storyboard = _approved_medical_snapshots(
        project_dir, medical_approval
    )

    run_dir = _active_run_dir(project_dir, project)
    video = run_dir / OUTPUT_NAME
    if not video.is_file():
        raise FileNotFoundError(f"Approved video is missing: {video}")

    render_input_path = run_dir / RENDER_INPUT_NAME
    render_input_data = json.loads(render_input_path.read_text(encoding="utf-8"))
    _require_approved_hash(
        video_approval,
        "render_input",
        canonical_json_hash(render_input_data),
    )
    render_input = RenderInput.model_validate(render_input_data)
    citations = _citations(script, ledger, render_input)

    publish_dir = project_dir / PUBLISH_DIRECTORY
    staging_dir = Path(mkdtemp(prefix=f".{project.slug}.package-", dir=project_dir))
    try:
        shutil.copy2(video, staging_dir / OUTPUT_NAME)
        shutil.copy2(render_input_path, staging_dir / RENDER_INPUT_NAME)
        _validate_staged_video_artifacts(staging_dir, video_approval)
        write_text_atomic(staging_dir / CAPTION_NAME, _caption(script, citations))
        write_text_atomic(staging_dir / SOURCES_NAME, _sources(script, citations))
        write_text_atomic(
            staging_dir / PACKAGE_MANIFEST_NAME,
            _manifest_json(
                project=project,
                script=script,
                medical_approval=medical_approval,
                video_approval=video_approval,
                staging_dir=staging_dir,
                citations=citations,
            ),
        )
        replace_directory_atomic(staging_dir, publish_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return publish_dir


def _package_v2(layout: ProjectLayout) -> Path:
    project = layout.manifest
    assert isinstance(project, ProjectManifestV2)
    if project.state is not WorkflowState.VIDEO_APPROVED:
        raise ValueError(
            "Packaging requires v2 project state video_approved, "
            f"not {project.state.value}"
        )

    medical_approval = _ensure_v2_gate_approval(
        layout.artifact_root, GateKind.MEDICAL
    )
    video_approval = _ensure_v2_gate_approval(
        layout.artifact_root, GateKind.VIDEO
    )
    ledger, script, storyboard = _approved_v2_medical_snapshots(
        layout.artifact_root, medical_approval
    )
    ai_disclosure = _ai_disclosure(layout.artifact_root, medical_approval, storyboard)

    renders_dir = layout.artifact_root / "renders"
    video = renders_dir / OUTPUT_NAME
    render_input_path = renders_dir / RENDER_INPUT_NAME
    render_manifest_path = renders_dir / "render-manifest.json"
    if not video.is_file():
        raise FileNotFoundError(f"Approved video is missing: {video}")
    if not render_input_path.is_file():
        raise FileNotFoundError(
            f"Approved render input is missing: {render_input_path}"
        )
    render_manifest = json.loads(
        render_manifest_path.read_text(encoding="utf-8")
    )
    render_input_data = json.loads(
        render_input_path.read_text(encoding="utf-8")
    )
    approved_render_input_hash = render_manifest.get("render_input_sha256")
    if approved_render_input_hash != canonical_json_hash(render_input_data):
        raise ValueError(
            "render input does not match the approved video render manifest"
        )
    render_input = RenderInput.model_validate(render_input_data)
    citations = _citations(script, ledger, render_input)

    publish_dir = layout.artifact_root / PUBLISH_DIRECTORY
    staging_dir = Path(
        mkdtemp(
            prefix=f".{project.slug}.package-", dir=layout.artifact_root
        )
    )
    try:
        shutil.copy2(video, staging_dir / OUTPUT_NAME)
        shutil.copy2(render_input_path, staging_dir / RENDER_INPUT_NAME)
        _validate_staged_v2_video_artifacts(
            staging_dir, video_approval, approved_render_input_hash
        )
        write_text_atomic(staging_dir / CAPTION_NAME, _caption(script, citations))
        write_text_atomic(staging_dir / SOURCES_NAME, _sources(script, citations))
        if ai_disclosure is not None:
            write_text_atomic(staging_dir / AI_DISCLOSURE_NAME, ai_disclosure)
        write_text_atomic(
            staging_dir / PACKAGE_MANIFEST_NAME,
            _manifest_json(
                project=project,
                script=script,
                medical_approval=medical_approval,
                video_approval=video_approval,
                staging_dir=staging_dir,
                citations=citations,
            ),
        )
        replace_directory_atomic(staging_dir, publish_dir)
        package_manifest = json.loads(
            (publish_dir / PACKAGE_MANIFEST_NAME).read_text(encoding="utf-8")
        )
        context = TransitionContext(
            active_revision=project.active_revision,
            current_input_hash=canonical_json_hash(package_manifest),
            validated_artifacts=frozenset({"publish/manifest.json"}),
        )
        changed = transition_v2(project, WorkflowState.PACKAGED, context)
        write_yaml_atomic(
            layout.project_dir / PROJECT_MANIFEST_NAME,
            changed.model_dump(mode="json"),
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return publish_dir


def _ensure_v2_gate_approval(
    revision_root: Path, kind: GateKind
) -> GateApprovalRecord:
    approval_name = {
        GateKind.MEDICAL: MEDICAL_APPROVAL_ARTIFACT,
        GateKind.VIDEO: VIDEO_APPROVAL_ARTIFACT,
    }[kind]
    approval_path = revision_root / approval_name
    if not approval_path.is_file():
        raise FileNotFoundError(
            f"Packaging requires a {kind.value} approval record for the active revision"
        )
    approval = GateApprovalRecord.model_validate(read_yaml(approval_path))
    if approval.kind is not kind:
        raise ValueError(f"Packaging requires a {kind.value} approval record")
    reviewed_paths = {
        GateKind.MEDICAL: medical_reviewed_paths,
        GateKind.VIDEO: video_reviewed_paths,
    }[kind](revision_root)
    current_hashes = hash_reviewed_artifacts(reviewed_paths)
    if current_hashes != approval.artifact_hashes:
        raise ValueError(
            f"Packaging requires a current {kind.value} approval"
        )
    return approval


def _approved_v2_medical_snapshots(
    revision_root: Path, approval: GateApprovalRecord
) -> tuple[dict[str, Any], Script, Storyboard]:
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    script_data = read_yaml(revision_root / "script" / "script.yaml")
    storyboard_data = read_yaml(
        revision_root / "storyboard" / "storyboard.yaml"
    )
    for name, data in (
        ("evidence/ledger.yaml", ledger),
        ("script/script.yaml", script_data),
        ("storyboard/storyboard.yaml", storyboard_data),
    ):
        _require_approved_hash(approval, name, canonical_json_hash(data))
    return (
        ledger,
        Script.model_validate(script_data),
        Storyboard.model_validate(storyboard_data),
    )


def _ai_disclosure(
    revision_root: Path, approval: GateApprovalRecord, storyboard: Storyboard
) -> str | None:
    """Describe approved AI clips for manual upload labelling; None when there are none."""
    manifest_path = revision_root / "assets" / "asset-manifest.yaml"
    if not manifest_path.is_file():
        return None
    manifest_data = read_yaml(manifest_path)
    _require_approved_hash(
        approval, "assets/asset-manifest.yaml", canonical_json_hash(manifest_data)
    )
    records = {
        record.path: record
        for record in AssetManifest.model_validate(manifest_data).assets
        if record.kind is AssetKind.AI_CLIP and record.ai_provenance is not None
    }
    clips = [
        {
            "scene_id": scene.id,
            "path": ref.path,
            "provider": records[ref.path].ai_provenance.provider,
            "model": records[ref.path].ai_provenance.model,
            "classification": "semantic" if records[ref.path].semantic else "decorative",
        }
        for scene in storyboard.scenes
        for ref in scene.visual_assets
        if ref.role == "ai_clip" and ref.path in records
    ]
    if not clips:
        return None
    disclosure = {
        "schema_version": "1.0",
        "contains_ai": True,
        "clips": clips,
        "operator_guidance": AI_DISCLOSURE_GUIDANCE,
    }
    return json.dumps(disclosure, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _validate_staged_v2_video_artifacts(
    staging_dir: Path,
    approval: GateApprovalRecord,
    approved_render_input_hash: str,
) -> None:
    _require_approved_hash(
        approval,
        "renders/video.mp4",
        sha256_file(staging_dir / OUTPUT_NAME),
        staged=True,
    )
    staged_render_input = json.loads(
        (staging_dir / RENDER_INPUT_NAME).read_text(encoding="utf-8")
    )
    if canonical_json_hash(staged_render_input) != approved_render_input_hash:
        raise ValueError(
            "staged render_input does not match the approved video render manifest"
        )


def _approved_medical_snapshots(
    project_dir: Path, approval: ReviewRecord
) -> tuple[dict[str, Any], Script, Storyboard]:
    """Capture medical inputs once and prove each snapshot is doctor-approved."""
    ledger = read_yaml(project_dir / "evidence" / "ledger.yaml")
    script_data = read_yaml(project_dir / "script" / "script.yaml")
    storyboard_data = read_yaml(project_dir / "storyboard" / "storyboard.yaml")
    for name, data in (
        ("evidence", ledger),
        ("script", script_data),
        ("storyboard", storyboard_data),
    ):
        _require_approved_hash(approval, name, canonical_json_hash(data))
    return (
        ledger,
        Script.model_validate(script_data),
        Storyboard.model_validate(storyboard_data),
    )


def _validate_staged_video_artifacts(
    staging_dir: Path, approval: ReviewRecord
) -> None:
    """Reject package bytes that no longer match the captured video approval."""
    staged_video = staging_dir / OUTPUT_NAME
    _require_approved_hash(approval, "video", sha256_file(staged_video), staged=True)
    staged_render_input = json.loads(
        (staging_dir / RENDER_INPUT_NAME).read_text(encoding="utf-8")
    )
    _require_approved_hash(
        approval,
        "render_input",
        canonical_json_hash(staged_render_input),
        staged=True,
    )


def _require_approved_hash(
    approval: ReviewRecord | GateApprovalRecord,
    name: str,
    actual_hash: str,
    *,
    staged: bool = False,
) -> None:
    expected = approval.artifact_hashes.get(name)
    if expected != actual_hash:
        prefix = "staged " if staged else ""
        raise ValueError(
            f"{prefix}{name} does not match the approved {approval.kind.value} artifact"
        )


def _active_run_dir(project_dir: Path, project: ProjectManifest) -> Path:
    input_hash = project.artifact_hashes.get(PRODUCTION_ARTIFACT)
    if input_hash is None:
        raise FileNotFoundError(
            "Packaging needs an active production run in "
            f"project.yaml.artifact_hashes.{PRODUCTION_ARTIFACT}"
        )
    return production_run_dir(project_dir, input_hash)


def _citations(
    script: Script, ledger: Mapping[str, Any], render_input: RenderInput
) -> dict[str, list[SourceRecord]]:
    """Resolve each on-screen marker to the evidence records standing behind it.

    Markers appear in the video as bare `[n]`, so every one of them must name at
    least one record here; a marker no record backs is refused rather than
    published as evidence.
    """
    if script.format_profile == "hook_outro_v1":
        return resolve_citations(
            script, ledger, render_input.scenes, strict_line_ids=True
        )
    records = {
        record.id: record
        for record in _validated(SourceRecord, ledger.get("records", []))
    }
    claims = {
        claim.id: claim for claim in _validated(EvidenceClaim, ledger.get("claims", []))
    }
    citations: dict[str, list[SourceRecord]] = {}
    for scene in render_input.scenes:
        marker = scene.source_marker
        if marker is None:
            continue
        matching_line = next(
            (
                line
                for line in script.lines
                if line.source_marker == marker and line.claim_id == scene.claim_id
            ),
            None,
        )
        if matching_line is None:
            raise ValueError(
                f"Render scene {scene.id} shows {marker} without a script claim/source "
                "mapping"
            )
        claim = claims.get(matching_line.claim_id or "")
        if claim is None:
            raise ValueError(
                f"Render scene {scene.id} shows {marker} through script line "
                f"{matching_line.id} and undefined claim {matching_line.claim_id!r}"
            )
        cited = [
            _record(records, record_id, matching_line.id) for record_id in claim.sources
        ]
        if not cited:
            raise ValueError(
                f"Render scene {scene.id} shows {marker} but claim {claim.id} "
                f"({claim.type}) lists no source"
            )
        existing = citations.get(marker)
        if existing is not None and [record.id for record in existing] != [
            record.id for record in cited
        ]:
            raise ValueError(
                f"Render scene {scene.id} reuses {marker} for a different source "
                "mapping"
            )
        citations[marker] = cited
    return citations


def _validated(model: type[LedgerEntry], items: Any) -> list[LedgerEntry]:
    if not isinstance(items, list):
        raise TypeError(f"Evidence ledger {model.__name__} section must be a list")
    return [model.model_validate(item) for item in items]


def _record(
    records: Mapping[str, SourceRecord], record_id: str, line_id: str
) -> SourceRecord:
    record = records.get(record_id)
    if record is None:
        raise ValueError(
            f"Script line {line_id} cites source {record_id}, "
            "which the evidence ledger does not define"
        )
    return record


def _caption(script: Script, citations: Mapping[str, list[SourceRecord]]) -> str:
    """Write the upload caption: a short hook, the disclaimer and the sources."""
    hook = script.lines[0].text if script.lines else script.title
    blocks = [script.title, hook, DISCLAIMER]
    if citations:
        sources = "\n".join(
            f"{marker} " + "; ".join(_short_citation(record) for record in records)
            for marker, records in citations.items()
        )
        blocks.append(f"Nguồn:\n{sources}")
    return "\n\n".join(blocks) + "\n"


def _short_citation(record: SourceRecord) -> str:
    parts = [record.title]
    if record.authors:
        parts.append(", ".join(record.authors))
    if record.year is not None:
        parts.append(str(record.year))
    if record.doi is not None:
        parts.append(f"DOI: {record.doi}")
    elif record.pmid is not None:
        parts.append(f"PMID: {record.pmid}")
    elif record.url is not None:
        parts.append(record.url)
    return ". ".join(parts)


def _sources(script: Script, citations: Mapping[str, list[SourceRecord]]) -> str:
    """Write the full source list the video only hints at with `[n]`."""
    lines = [f"# Nguồn tham khảo — {script.title}", ""]
    if not citations:
        lines.append("Video này không hiển thị dấu trích dẫn nào.")
        return "\n".join(lines) + "\n"
    for marker, records in citations.items():
        lines.append(f"## {marker}")
        lines.append("")
        for record in records:
            lines.append(f"### {record.id} — {record.title}")
            lines.append("")
            lines.extend(_source_fields(record))
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _source_fields(record: SourceRecord) -> list[str]:
    fields: list[tuple[str, Any]] = [
        ("Tác giả", ", ".join(record.authors) if record.authors else None),
        ("Năm", record.year),
        ("Thiết kế nghiên cứu", record.study_design or None),
        ("Cỡ mẫu", record.sample_size),
        ("DOI", record.doi),
        ("PMID", record.pmid),
        ("URL", record.url),
    ]
    return [f"- {label}: {value}" for label, value in fields if value is not None]


def _manifest_json(
    *,
    project: ProjectManifest | ProjectManifestV2,
    script: Script,
    medical_approval: ReviewRecord | GateApprovalRecord,
    video_approval: ReviewRecord | GateApprovalRecord,
    staging_dir: Path,
    citations: Mapping[str, list[SourceRecord]],
) -> str:
    """Describe the package: what was approved, by whom, and the file hashes."""
    manifest = {
        "schema_version": "1.0",
        "slug": project.slug,
        "language": project.language,
        "title": script.title,
        "production_input_hash": project.artifact_hashes[PRODUCTION_ARTIFACT],
        "approval_stale": False,
        "approval_bindings": {
            "medical": _approval_binding(medical_approval),
            "video": _approval_binding(video_approval),
        },
        "payload_sha256": {
            CAPTION_NAME: sha256_file(staging_dir / CAPTION_NAME),
            OUTPUT_NAME: sha256_file(staging_dir / OUTPUT_NAME),
            SOURCES_NAME: sha256_file(staging_dir / SOURCES_NAME),
            RENDER_INPUT_NAME: sha256_file(staging_dir / RENDER_INPUT_NAME),
            **(
                {AI_DISCLOSURE_NAME: sha256_file(staging_dir / AI_DISCLOSURE_NAME)}
                if (staging_dir / AI_DISCLOSURE_NAME).is_file()
                else {}
            ),
        },
        "source_markers": {
            marker: [record.id for record in records]
            for marker, records in citations.items()
        },
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _approval_binding(
    approval: ReviewRecord | GateApprovalRecord,
) -> dict[str, Any]:
    """Make approval identity distinct from hashes of package payload bytes."""
    binding = {
        "approval_sha256": canonical_json_hash(approval.model_dump(mode="json")),
        "reviewer": approval.reviewer,
        "reviewed_at": approval.reviewed_at.isoformat(),
        "artifact_hashes": approval.artifact_hashes,
    }
    if isinstance(approval, ReviewRecord):
        binding["id"] = str(approval.id)
    return binding
