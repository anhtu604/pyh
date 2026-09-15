"""Recoverable, pre-medical authoring of explicitly requested AI clips."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from healthvideo.assets import referenced_storyboard_assets
from healthvideo.domain.ai_clip import (
    AIClipProvenance,
    validate_ai_clip_media_contract,
)
from healthvideo.domain.asset_manifest import (
    AssetKind,
    AssetManifest,
    AssetRecord,
    _posix_relative_path,
    load_asset_manifest,
    validate_asset_manifest,
)
from healthvideo.domain.license_ledger import (
    LicenseEntry,
    LicenseLedger,
    validate_license_ledger,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.storyboard import Storyboard, VisualAssetRef
from healthvideo.storage.files import (
    canonical_json_hash,
    read_yaml,
    sha256_file,
    write_yaml_atomic,
)
from healthvideo.video_ai.base import (
    VeoRequest,
    VeoTransport,
    VideoProbeResult,
    veo_request_sha256,
)

AI_CLIP_INTENT = "workflow/pending-ai-clip-generation.yaml"
_SCENE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_PRE_MEDICAL = {
    WorkflowState.DRAFT_READY,
    WorkflowState.AWAITING_MEDICAL_REVIEW,
}
_DECORATIVE_REASON = (
    "AI clip is decorative; target scene carries no medical claim/source marker."
)


class AIClipRights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    creator: str
    license: str
    rights_basis: str

    @field_validator("source", "creator", "license", "rights_basis")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("AI clip rights fields must be nonblank")
        return value


def probe_ai_clip_media(path: Path) -> VideoProbeResult:
    """Measure one local clip with ffprobe argv and reject ambiguous metadata."""

    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate,nb_read_frames:format=format_name,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        format_data = payload["format"]
        videos = [item for item in streams if item.get("codec_type") == "video"]
        if len(videos) != 1:
            raise ValueError("AI clip must contain exactly one video stream")
        video = videos[0]
        fps = Fraction(str(video["r_frame_rate"]))
        if fps.denominator != 1:
            raise ValueError("AI clip frame rate must be an exact integer")
        duration_decimal = Decimal(str(format_data["duration"])) * 1000
        if duration_decimal != duration_decimal.to_integral_value():
            raise ValueError("AI clip duration must be exact milliseconds")
        format_names = str(format_data["format_name"]).split(",")
        if "mp4" not in format_names:
            raise ValueError("AI clip container must be MP4")
        result = VideoProbeResult(
            mime_type="video/mp4",
            container="mp4",
            width=int(video["width"]),
            height=int(video["height"]),
            source_fps=int(fps),
            duration_ms=int(duration_decimal),
            source_frame_count=int(video["nb_read_frames"]),
            video_stream_count=1,
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError, InvalidOperation) as error:
        if isinstance(error, ValueError) and str(error).startswith("AI clip"):
            raise
        raise ValueError("ffprobe returned incomplete AI clip metadata") from error
    _validate_probe(result)
    return result


def generate_ai_clip(
    project_dir: Path,
    *,
    scene_id: str,
    prompt: str,
    duration_seconds: int,
    requested_seed: int | None,
    rights: AIClipRights,
    transport: VeoTransport,
    now: datetime,
    probe: Callable[[Path], VideoProbeResult] = probe_ai_clip_media,
) -> Path:
    """Generate, validate, and atomically register one reviewed-target clip."""

    recover_ai_clip_generation(project_dir)
    context = _load_preflight(project_dir, scene_id, prompt, duration_seconds, rights)
    request = VeoRequest(
        prompt=prompt,
        duration_seconds=duration_seconds,
        requested_seed=requested_seed,
    )
    target = context["revision"] / context["asset_path"]
    existing = _existing_idempotent_result(
        context, request=request, rights=rights, target=target
    )
    if existing:
        return target

    result = transport.generate(request)
    staging_path = context["revision"] / (
        f"workflow/staged-ai-clips/{scene_id}-{sha256(result.video_bytes).hexdigest()}.mp4"
    )
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        staging_path.write_bytes(result.video_bytes)
        output_hash = sha256_file(staging_path)
        measured = probe(staging_path)
        _validate_probe(measured)
        if measured.duration_ms != duration_seconds * 1000:
            raise ValueError("AI clip measured duration differs from request")
        provenance = AIClipProvenance(
            provider="google_vertex_ai",
            model=request.model,
            prompt=prompt,
            requested_seed=requested_seed,
            generated_at=now,
            request_sha256=veo_request_sha256(request),
            output_sha256=output_hash,
            mime_type=measured.mime_type,
            container=measured.container,
            width=measured.width,
            height=measured.height,
            source_fps=measured.source_fps,
            duration_ms=measured.duration_ms,
            source_frame_count=measured.source_frame_count,
        )
        desired = _build_desired(context, rights, provenance)
        intent = _build_intent(context, desired, staging_path, request, rights)
        write_yaml_atomic(context["revision"] / AI_CLIP_INTENT, intent)
    except Exception:
        if not (context["revision"] / AI_CLIP_INTENT).exists():
            staging_path.unlink(missing_ok=True)
        raise
    recover_ai_clip_generation(project_dir)
    return target


def recover_ai_clip_generation(project_dir: Path) -> None:
    """Advance only the exact recorded R0-R4 transaction states."""

    project_data = read_yaml(project_dir / "project.yaml")
    if project_data.get("schema_version") != "2.0":
        return
    project = ProjectManifestV2.model_validate(project_data)
    revision = project_dir / "revisions" / project.active_revision
    intent_path = revision / AI_CLIP_INTENT
    if not intent_path.is_file():
        return
    if project.state not in _PRE_MEDICAL or (
        revision / "reviews/medical-approval.yaml"
    ).exists():
        raise ValueError("pending AI clip cannot recover after medical review")
    intent = read_yaml(intent_path)
    _validate_intent(intent, project.active_revision)
    desired_manifest = AssetManifest.model_validate(intent["desired_manifest"])
    desired_ledger = LicenseLedger.model_validate(intent["desired_ledger"])
    desired_storyboard = Storyboard.model_validate(intent["desired_storyboard"])
    current_manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    ledger_path = revision / "assets/license-ledger.yaml"
    current_ledger = (
        LicenseLedger.model_validate(read_yaml(ledger_path))
        if ledger_path.is_file()
        else LicenseLedger()
    )
    current_storyboard = Storyboard.model_validate(
        read_yaml(revision / "storyboard/storyboard.yaml")
    )
    current = (
        canonical_json_hash(current_manifest.model_dump(mode="json")),
        canonical_json_hash(current_ledger.model_dump(mode="json")),
        canonical_json_hash(current_storyboard.model_dump(mode="json")),
    )
    old = (intent["old_manifest_hash"], intent["old_ledger_hash"], intent["old_storyboard_hash"])
    desired = (
        intent["desired_manifest_hash"],
        intent["desired_ledger_hash"],
        intent["desired_storyboard_hash"],
    )
    asset_path = _revision_path(revision, intent["asset_path"])
    staged_path = _revision_path(revision, intent["staging_path"])
    expected_hash = intent["output_sha256"]

    if current != old and (
        not asset_path.is_file() or sha256_file(asset_path) != expected_hash
    ):
        raise ValueError("pending AI clip final byte hash conflict")

    if current == old:
        if asset_path.exists():
            if sha256_file(asset_path) != expected_hash:
                raise ValueError("pending AI clip final byte hash conflict")
        else:
            if not staged_path.is_file() or sha256_file(staged_path) != expected_hash:
                raise ValueError("pending AI clip staged byte hash conflict")
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_path, asset_path)
            if sha256_file(asset_path) != expected_hash:
                raise ValueError("pending AI clip final byte hash conflict")
        _write_manifest(revision, desired_manifest)
        current = (desired[0], current[1], current[2])
    if current == (desired[0], old[1], old[2]):
        _write_ledger(revision, desired_ledger)
        current = (current[0], desired[1], current[2])
    if current == (desired[0], desired[1], old[2]):
        _write_storyboard(revision, desired_storyboard)
        current = (current[0], current[1], desired[2])
    if current != desired:
        raise ValueError("pending AI clip conflict with unrelated or reordered edits")
    if not asset_path.is_file() or sha256_file(asset_path) != expected_hash:
        raise ValueError("pending AI clip final byte hash conflict")
    validate_license_ledger(desired_manifest, desired_ledger, project.active_revision)
    referenced_storyboard_assets(revision, desired_storyboard, desired_manifest)
    intent_path.unlink()
    staged_path.unlink(missing_ok=True)


def _load_preflight(
    project_dir: Path,
    scene_id: str,
    prompt: str,
    duration_seconds: int,
    rights: AIClipRights,
) -> dict[str, Any]:
    project_data = read_yaml(project_dir / "project.yaml")
    if project_data.get("schema_version") != "2.0":
        raise ValueError("AI clip generation requires a v2 project")
    project = ProjectManifestV2.model_validate(project_data)
    if project.state not in _PRE_MEDICAL:
        raise ValueError("AI clip generation requires pre-medical authoring state")
    revision = project_dir / "revisions" / project.active_revision
    if (revision / "reviews/medical-approval.yaml").exists():
        raise ValueError("AI clip generation refuses an existing medical approval")
    if not _SCENE_ID.fullmatch(scene_id):
        raise ValueError("AI clip scene ID is unsafe")
    if not prompt.strip():
        raise ValueError("AI clip prompt must be nonblank")
    if duration_seconds not in {4, 6, 8}:
        raise ValueError("AI clip duration must be 4, 6, or 8 seconds")
    board_path = revision / "storyboard/storyboard.yaml"
    storyboard = Storyboard.model_validate(read_yaml(board_path))
    if storyboard.visual_budget_profile != "m6_5_v1":
        raise ValueError("AI clip generation requires M6.5 storyboard profile")
    scene = next((item for item in storyboard.scenes if item.id == scene_id), None)
    if scene is None or scene.visual != "ai_clip":
        raise ValueError("AI clip target must be an existing ai_clip scene")
    if scene.duration_frames != duration_seconds * 30:
        raise ValueError("AI clip requested duration does not match scene duration")
    claim = scene.claim_id is not None
    marker = scene.source_marker is not None and bool(scene.source_marker.strip())
    if claim != marker:
        raise ValueError("AI clip scene must have both claim and source marker or neither")
    manifest = load_asset_manifest(revision / "assets/asset-manifest.yaml")
    validate_asset_manifest(revision, manifest)
    ledger_path = revision / "assets/license-ledger.yaml"
    ledger = (
        LicenseLedger.model_validate(read_yaml(ledger_path))
        if ledger_path.is_file()
        else LicenseLedger()
    )
    validate_license_ledger(manifest, ledger, project.active_revision)
    asset_path = f"assets/ai-clips/{scene_id}.mp4"
    _posix_relative_path(asset_path)
    return {
        "project": project,
        "revision": revision,
        "scene": scene,
        "storyboard": storyboard,
        "manifest": manifest,
        "ledger": ledger,
        "asset_path": asset_path,
        "semantic": claim,
    }


def _existing_idempotent_result(
    context: Mapping[str, Any],
    *,
    request: VeoRequest,
    rights: AIClipRights,
    target: Path,
) -> bool:
    matches = [
        item for item in context["manifest"].assets if item.path == context["asset_path"]
    ]
    refs = [
        (scene.id, ref)
        for scene in context["storyboard"].scenes
        for ref in scene.visual_assets
        if ref.path == context["asset_path"] or ref.role == "ai_clip"
    ]
    ledger_matches = [
        item for item in context["ledger"].entries if item.path == context["asset_path"]
    ]
    if not matches and not refs and not ledger_matches and not target.exists():
        return False
    if len(matches) != 1 or len(refs) != 1 or len(ledger_matches) != 1:
        raise ValueError("AI clip target has conflicting ownership or declaration")
    record = matches[0]
    entry = ledger_matches[0]
    provenance = record.ai_provenance
    expected_ref = VisualAssetRef(path=context["asset_path"], role="ai_clip")
    if (
        record.kind is not AssetKind.AI_CLIP
        or provenance is None
        or refs != [(context["scene"].id, expected_ref)]
        or provenance.request_sha256 != veo_request_sha256(request)
        or provenance.prompt != request.prompt
        or provenance.requested_seed != request.requested_seed
        or provenance.duration_ms != request.duration_seconds * 1000
        or record.source != rights.source
        or record.creator != rights.creator
        or record.license != rights.license
        or entry.rights_basis != rights.rights_basis
        or not target.is_file()
        or sha256_file(target) != record.sha256
    ):
        raise ValueError("existing AI clip differs from requested operation")
    return True


def _validate_probe(measured: VideoProbeResult) -> None:
    if measured.video_stream_count != 1:
        raise ValueError("AI clip must contain exactly one video stream")
    placeholder = AIClipProvenance.model_construct(
        mime_type=measured.mime_type,
        container=measured.container,
        width=measured.width,
        height=measured.height,
        source_fps=measured.source_fps,
        duration_ms=measured.duration_ms,
        source_frame_count=measured.source_frame_count,
    )
    validate_ai_clip_media_contract(placeholder)


def _build_desired(
    context: Mapping[str, Any], rights: AIClipRights, provenance: AIClipProvenance
) -> tuple[AssetManifest, LicenseLedger, Storyboard]:
    path = context["asset_path"]
    if any(item.path == path or item.storyboard_role == "ai_clip" for item in context["manifest"].assets):
        raise ValueError("AI clip target conflicts with an existing asset")
    if any(item.path == path for item in context["ledger"].entries):
        raise ValueError("AI clip target conflicts with existing rights")
    board_data = context["storyboard"].model_dump(mode="json")
    scene_data = next(item for item in board_data["scenes"] if item["id"] == context["scene"].id)
    if any(ref["role"] == "ai_clip" or ref["path"] == path for ref in scene_data["visual_assets"]):
        raise ValueError("AI clip target scene already has conflicting ownership")
    scene_data["visual_assets"].append(VisualAssetRef(path=path, role="ai_clip").model_dump(mode="json"))
    storyboard = Storyboard.model_validate(board_data)
    record = AssetRecord(
        path=path,
        kind=AssetKind.AI_CLIP,
        semantic=context["semantic"],
        classification_reason=None if context["semantic"] else _DECORATIVE_REASON,
        sha256=provenance.output_sha256,
        source=rights.source,
        license=rights.license,
        creator=rights.creator,
        revision=context["project"].active_revision,
        rights_required=True,
        storyboard_role="ai_clip",
        ai_provenance=provenance,
    )
    manifest = AssetManifest(assets=(*context["manifest"].assets, record))
    entry = LicenseEntry(
        path=path,
        source=rights.source,
        creator=rights.creator,
        license=rights.license,
        rights_basis=rights.rights_basis,
        revision=context["project"].active_revision,
        sha256=provenance.output_sha256,
    )
    ledger = LicenseLedger(entries=(*context["ledger"].entries, entry))
    validate_license_ledger(manifest, ledger, context["project"].active_revision)
    return manifest, ledger, storyboard


def _build_intent(
    context: Mapping[str, Any],
    desired: tuple[AssetManifest, LicenseLedger, Storyboard],
    staging_path: Path,
    request: VeoRequest,
    rights: AIClipRights,
) -> dict[str, Any]:
    old_objects = (context["manifest"], context["ledger"], context["storyboard"])
    old_payloads = [item.model_dump(mode="json") for item in old_objects]
    desired_payloads = [item.model_dump(mode="json") for item in desired]
    staging_relative = staging_path.relative_to(context["revision"]).as_posix()
    output_hash = sha256_file(staging_path)
    return {
        "schema_version": "1.0",
        "revision": context["project"].active_revision,
        "scene_id": context["scene"].id,
        "asset_path": context["asset_path"],
        "staging_path": staging_relative,
        "request_sha256": veo_request_sha256(request),
        "output_sha256": output_hash,
        "rights_hash": canonical_json_hash(rights.model_dump(mode="json")),
        "old_manifest": old_payloads[0],
        "desired_manifest": desired_payloads[0],
        "old_ledger": old_payloads[1],
        "desired_ledger": desired_payloads[1],
        "old_storyboard": old_payloads[2],
        "desired_storyboard": desired_payloads[2],
        "old_manifest_hash": canonical_json_hash(old_payloads[0]),
        "desired_manifest_hash": canonical_json_hash(desired_payloads[0]),
        "old_ledger_hash": canonical_json_hash(old_payloads[1]),
        "desired_ledger_hash": canonical_json_hash(desired_payloads[1]),
        "old_storyboard_hash": canonical_json_hash(old_payloads[2]),
        "desired_storyboard_hash": canonical_json_hash(desired_payloads[2]),
    }


def _validate_intent(intent: Mapping[str, Any], revision: str) -> None:
    required = {
        "schema_version", "revision", "scene_id", "asset_path", "staging_path",
        "request_sha256", "output_sha256", "rights_hash", "old_manifest",
        "desired_manifest", "old_ledger", "desired_ledger", "old_storyboard",
        "desired_storyboard", "old_manifest_hash", "desired_manifest_hash",
        "old_ledger_hash", "desired_ledger_hash", "old_storyboard_hash",
        "desired_storyboard_hash",
    }
    if set(intent) != required or intent.get("schema_version") != "1.0" or intent.get("revision") != revision:
        raise ValueError("pending AI clip intent is invalid")
    if not _SCENE_ID.fullmatch(str(intent["scene_id"])):
        raise ValueError("pending AI clip intent is invalid")
    expected_path = f"assets/ai-clips/{intent['scene_id']}.mp4"
    if intent["asset_path"] != expected_path:
        raise ValueError("pending AI clip intent target is invalid")
    for name in ("asset_path", "staging_path"):
        _posix_relative_path(str(intent[name]))
    for kind in ("manifest", "ledger", "storyboard"):
        for state in ("old", "desired"):
            payload = intent[f"{state}_{kind}"]
            if intent[f"{state}_{kind}_hash"] != canonical_json_hash(payload):
                raise ValueError("pending AI clip intent payload hash is invalid")
    old_manifest = AssetManifest.model_validate(intent["old_manifest"])
    desired_manifest = AssetManifest.model_validate(intent["desired_manifest"])
    old_ledger = LicenseLedger.model_validate(intent["old_ledger"])
    desired_ledger = LicenseLedger.model_validate(intent["desired_ledger"])
    old_storyboard = Storyboard.model_validate(intent["old_storyboard"])
    desired_storyboard = Storyboard.model_validate(intent["desired_storyboard"])
    target = str(intent["asset_path"])
    records = [item for item in desired_manifest.assets if item.path == target]
    entries = [item for item in desired_ledger.entries if item.path == target]
    if (
        len(records) != 1
        or len(entries) != 1
        or any(item.path == target for item in old_manifest.assets)
        or any(item.path == target for item in old_ledger.entries)
        or desired_manifest.assets != (*old_manifest.assets, records[0])
        or desired_ledger.entries != (*old_ledger.entries, entries[0])
    ):
        raise ValueError("pending AI clip intent metadata transition is invalid")
    record = records[0]
    entry = entries[0]
    provenance = record.ai_provenance
    rights_payload = {
        "source": record.source,
        "creator": record.creator,
        "license": record.license,
        "rights_basis": entry.rights_basis,
    }
    if (
        record.kind is not AssetKind.AI_CLIP
        or provenance is None
        or record.sha256 != intent["output_sha256"]
        or provenance.output_sha256 != intent["output_sha256"]
        or provenance.request_sha256 != intent["request_sha256"]
        or entry.sha256 != record.sha256
        or entry.source != record.source
        or entry.creator != record.creator
        or entry.license != record.license
        or intent["rights_hash"] != canonical_json_hash(rights_payload)
    ):
        raise ValueError("pending AI clip intent identity is invalid")
    expected_staging = (
        f"workflow/staged-ai-clips/{intent['scene_id']}-{intent['output_sha256']}.mp4"
    )
    if intent["staging_path"] != expected_staging:
        raise ValueError("pending AI clip staging identity is invalid")
    board_data = old_storyboard.model_dump(mode="json")
    scene = next(
        (item for item in board_data["scenes"] if item["id"] == intent["scene_id"]),
        None,
    )
    if scene is None or scene["visual"] != "ai_clip" or any(
        ref["role"] == "ai_clip" or ref["path"] == target
        for ref in scene["visual_assets"]
    ):
        raise ValueError("pending AI clip storyboard transition is invalid")
    scene["visual_assets"].append(
        VisualAssetRef(path=target, role="ai_clip").model_dump(mode="json")
    )
    if desired_storyboard != Storyboard.model_validate(board_data):
        raise ValueError("pending AI clip storyboard transition is invalid")


def _revision_path(revision: Path, relative: object) -> Path:
    safe = _posix_relative_path(str(relative))
    path = revision.joinpath(*safe.parts)
    if revision.resolve() not in path.resolve().parents:
        raise ValueError("pending AI clip path escapes revision")
    return path


def _write_manifest(revision: Path, manifest: AssetManifest) -> None:
    write_yaml_atomic(revision / "assets/asset-manifest.yaml", manifest.model_dump(mode="json"))


def _write_ledger(revision: Path, ledger: LicenseLedger) -> None:
    write_yaml_atomic(revision / "assets/license-ledger.yaml", ledger.model_dump(mode="json"))


def _write_storyboard(revision: Path, storyboard: Storyboard) -> None:
    write_yaml_atomic(revision / "storyboard/storyboard.yaml", storyboard.model_dump(mode="json"))
