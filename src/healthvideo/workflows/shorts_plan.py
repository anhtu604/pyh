"""Vertical 9:16 Shorts / Reels / TikTok planning step (`shorts_plan`)."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.clip_plan import (
    CLIP_MIN_FRAMES,
    FPS,
    ClipPlan,
    ClipSpec,
    validate_clip_plan,
)
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.explainer import Nonblank
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.storage.revision_lock import revision_lock
from healthvideo.workflows.draft import _project

SHORTS_PLAN_ARTIFACT = "posts/shorts-plan.yaml"
_CLAIM_REF_RE = re.compile(r"\[claim:([^\]]+)\]")
STYLE_A_MASCOT_MAX_WIDTH_PERCENT = 28.0
STYLE_A_SUBTITLE_POSITION = "bottom_center"
STYLE_A_HOOK_MAX_SECONDS = 2.0
SHORTS_CLIP_MAX_FRAMES = 90 * FPS

_REVISION_LOCK_STATE = threading.local()
_REVISION_THREAD_GUARDS_LOCK = threading.Lock()
_REVISION_THREAD_GUARDS: dict[Path, threading.RLock] = {}


def _revision_thread_guard(resolved: Path) -> threading.RLock:
    with _REVISION_THREAD_GUARDS_LOCK:
        guard = _REVISION_THREAD_GUARDS.get(resolved)
        if guard is None:
            guard = threading.RLock()
            _REVISION_THREAD_GUARDS[resolved] = guard
        return guard


@contextmanager
def revision_tx_lock(revision: Path, *, timeout: float = 60) -> Iterator[None]:
    """Thread-reentrant wrapper around OS ``revision_lock`` for read/write sync."""
    resolved = revision.resolve()
    held: set[Path] | None = getattr(_REVISION_LOCK_STATE, "held", None)
    if held is None:
        held = set()
        _REVISION_LOCK_STATE.held = held
    if resolved in held:
        yield
        return
    guard = _revision_thread_guard(resolved)
    with guard, revision_lock(resolved, timeout=timeout):
        held.add(resolved)
        try:
            yield
        finally:
            held.discard(resolved)


class ShortClipSpec(BaseModel):
    """Validated vertical clip specification keeping medical caveats and 9:16 Style A safe zones."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CL\d{2}$")
    title: str = Field(min_length=1, max_length=120)
    hook_text: Nonblank
    start_scene_id: Nonblank
    end_scene_id: Nonblank
    target_seconds: int = Field(ge=45, le=90)
    loop_bridge: str = ""
    caption: Nonblank
    safety_caveat: Nonblank
    safe_zone_checked: bool = False
    mascot_max_width_percent: float = Field(
        default=STYLE_A_MASCOT_MAX_WIDTH_PERCENT,
        gt=0,
        le=STYLE_A_MASCOT_MAX_WIDTH_PERCENT,
        allow_inf_nan=False,
    )
    subtitle_position: Literal["bottom_center"] = STYLE_A_SUBTITLE_POSITION
    hook_window_seconds: float = Field(
        default=STYLE_A_HOOK_MAX_SECONDS,
        gt=0,
        le=STYLE_A_HOOK_MAX_SECONDS,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def _require_safe_zone(self) -> ShortClipSpec:
        if not self.safe_zone_checked:
            raise ValueError(f"{self.id}: 9:16 safe zone must be verified (safe_zone_checked=true)")
        return self


class ShortsPlan(BaseModel):
    """Collection of 1-4 vertical short plans derived from medically approved content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    revision_hash: str = ""
    clips: tuple[ShortClipSpec, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _unique_ids(self) -> ShortsPlan:
        ids = [clip.id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("shorts plan clip IDs must be unique")
        return self


def resolve_revision_root(revision_or_project: Path) -> Path:
    """Accept either a revision directory or a project directory and return its revision path."""
    if (revision_or_project / "project.yaml").is_file() and not (
        revision_or_project / "script/script.yaml"
    ).is_file():
        project = _project(revision_or_project)
        return revision_or_project / "revisions" / project.active_revision
    return revision_or_project


def _revision_hash(revision: Path) -> str:
    script_path = revision / "script/script.yaml"
    sb_path = revision / "storyboard/storyboard.yaml"
    if not script_path.is_file() or not sb_path.is_file():
        raise ValueError("shorts_plan requires script/script.yaml and storyboard/storyboard.yaml")
    return canonical_json_hash(
        {"script": read_yaml(script_path), "storyboard": read_yaml(sb_path)}
    )


def _verify_medical_gate(revision: Path, *, require_medical_approval: bool) -> None:
    if not require_medical_approval:
        return
    from healthvideo.domain.gate_review import GateApprovalRecord, GateKind
    from healthvideo.workflows.gate_review import (
        MEDICAL_APPROVAL_ARTIFACT,
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )

    approval_path = revision / MEDICAL_APPROVAL_ARTIFACT
    if not approval_path.is_file():
        raise ValueError("Mapping shorts_plan requires a current medical approval")
    approval = GateApprovalRecord.model_validate(read_yaml(approval_path))
    if approval.kind is not GateKind.MEDICAL:
        raise ValueError("Mapping shorts_plan requires a medical approval record")
    current_hashes = hash_reviewed_artifacts(medical_reviewed_paths(revision))
    if current_hashes != approval.artifact_hashes:
        raise ValueError("Mapping shorts_plan requires a current medical approval")


def _load_ledger_claims(revision: Path) -> dict[str, EvidenceClaim]:
    ledger_path = revision / "evidence/ledger.yaml"
    if not ledger_path.is_file():
        raise FileNotFoundError(f"shorts_plan requires {ledger_path}")
    ledger = read_yaml(ledger_path)
    return {
        claim.id: claim
        for claim in (
            EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])
        )
    }


def _validate_and_map_shorts_plan(
    plan: ShortsPlan,
    script: Script,
    storyboard: Storyboard,
    claims: Mapping[str, EvidenceClaim],
    *,
    require_long_form_bounds: bool,
) -> ClipPlan:
    scene_index = {scene.id: idx for idx, scene in enumerate(storyboard.scenes)}
    line_by_id = {line.id: line for line in script.lines}
    mapped_clips: list[ClipSpec] = []

    for clip in plan.clips:
        if clip.start_scene_id not in scene_index:
            raise ValueError(f"{clip.id}: unknown start_scene_id {clip.start_scene_id}")
        if clip.end_scene_id not in scene_index:
            raise ValueError(f"{clip.id}: unknown end_scene_id {clip.end_scene_id}")
        start_idx = scene_index[clip.start_scene_id]
        end_idx = scene_index[clip.end_scene_id]
        if start_idx > end_idx:
            raise ValueError(f"{clip.id}: start_scene_id must not come after end_scene_id")

        for text_field in (clip.hook_text, clip.caption, clip.safety_caveat):
            for cid in _CLAIM_REF_RE.findall(text_field):
                if cid not in claims:
                    raise ValueError(f"{clip.id}: unknown ledger claim {cid}")

        for scene in storyboard.scenes[start_idx : end_idx + 1]:
            if scene.script_line_id is not None:
                line = line_by_id.get(scene.script_line_id)
                if line is None or scene.narration != line.text:
                    raise ValueError(
                        f"{clip.id}: scene {scene.id} narration diverges from approved script"
                    )

        mapped_clips.append(
            ClipSpec(
                id=clip.id,
                title=clip.title.strip()[:100],
                first_scene_id=clip.start_scene_id,
                last_scene_id=clip.end_scene_id,
                mascot_max_width_percent=clip.mascot_max_width_percent,
                subtitle_position=clip.subtitle_position,
                hook_window_seconds=clip.hook_window_seconds,
            )
        )

    clip_plan = ClipPlan(clips=tuple(mapped_clips))
    if require_long_form_bounds:
        validate_clip_plan(
            clip_plan,
            storyboard,
            claims,
            min_frames=CLIP_MIN_FRAMES,
            max_frames=SHORTS_CLIP_MAX_FRAMES,
            require_style_a=True,
        )
    return clip_plan


def sync_shorts_plan_to_clip_plan(
    revision_root: Path,
    *,
    require_medical_approval: bool = True,
) -> ClipPlan:
    """Validate ``posts/shorts-plan.yaml`` against medically approved artifacts and map to ``ClipPlan``."""
    revision = resolve_revision_root(revision_root)
    with revision_tx_lock(revision):
        shorts_path = revision / SHORTS_PLAN_ARTIFACT
        if not shorts_path.is_file():
            raise FileNotFoundError(f"Missing shorts plan: {shorts_path}")

        _verify_medical_gate(revision, require_medical_approval=require_medical_approval)

        script_path = revision / "script/script.yaml"
        sb_path = revision / "storyboard/storyboard.yaml"
        ledger_path = revision / "evidence/ledger.yaml"
        for required in (script_path, sb_path, ledger_path):
            if not required.is_file():
                raise FileNotFoundError(f"shorts_plan sync requires {required}")

        script = Script.model_validate(read_yaml(script_path))
        storyboard = Storyboard.model_validate(read_yaml(sb_path))
        if storyboard.format_profile != "youtube_long":
            raise ValueError("sync_shorts_plan_to_clip_plan requires a youtube_long storyboard")

        claims = _load_ledger_claims(revision)
        plan = ShortsPlan.model_validate(read_yaml(shorts_path))
        expected_rev_hash = _revision_hash(revision)
        if not plan.revision_hash or plan.revision_hash != expected_rev_hash:
            raise ValueError(
                "posts/shorts-plan.yaml revision_hash does not match approved script/storyboard"
            )

        return _validate_and_map_shorts_plan(
            plan, script, storyboard, claims, require_long_form_bounds=True
        )


def load_effective_clip_specs(
    revision_root: Path,
    *,
    require_medical_approval: bool = True,
) -> ClipPlan:
    """Delegate to ``long_form.load_effective_clip_specs`` without top-level circular imports."""
    from healthvideo.workflows.long_form import load_effective_clip_specs as _load

    return _load(revision_root, require_medical_approval=require_medical_approval)


def save_shorts_plan(project_dir: Path, file_path: Path) -> Path:
    """Validate ``ShortsPlan`` against storyboard, ledger & 60–90s bounds, then save atomically."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    with revision_tx_lock(revision):
        rev_hash = _revision_hash(revision)
        script = Script.model_validate(read_yaml(revision / "script/script.yaml"))
        storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
        claims = _load_ledger_claims(revision)
        plan = ShortsPlan.model_validate(read_yaml(file_path))
        for clip in plan.clips:
            if not 60 <= clip.target_seconds <= 90:
                raise ValueError(
                    f"{clip.id}: target_seconds {clip.target_seconds}s must be between 60 and 90"
                )
        _validate_and_map_shorts_plan(
            plan,
            script,
            storyboard,
            claims,
            require_long_form_bounds=(storyboard.format_profile == "youtube_long"),
        )
        stamped = plan.model_copy(update={"revision_hash": rev_hash})
        target = revision / SHORTS_PLAN_ARTIFACT
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml_atomic(target, stamped.model_dump(mode="json"))
        return target


def shorts_plan_ready(project_dir: Path) -> bool:
    """Return True when active revision has a valid ``posts/shorts-plan.yaml`` for current revision."""
    if not (project_dir / "project.yaml").is_file():
        return False
    try:
        project = _project(project_dir)
        revision = project_dir / "revisions" / project.active_revision
        with revision_tx_lock(revision):
            target = revision / SHORTS_PLAN_ARTIFACT
            if not target.is_file():
                return False
            rev_hash = _revision_hash(revision)
            plan = ShortsPlan.model_validate(read_yaml(target))
    except (OSError, TypeError, ValueError):
        return False
    return plan.revision_hash == rev_hash
