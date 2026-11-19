"""Vertical 9:16 Shorts / Reels / TikTok planning step (`shorts_plan`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.explainer import Nonblank
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import canonical_json_hash, read_yaml, write_yaml_atomic
from healthvideo.workflows.draft import _project

SHORTS_PLAN_ARTIFACT = "posts/shorts-plan.yaml"
_CLAIM_REF_RE = re.compile(r"\[claim:([^\]]+)\]")
STYLE_A_MASCOT_MAX_WIDTH_PERCENT = 28.0
STYLE_A_SUBTITLE_POSITION = "bottom_center"
STYLE_A_HOOK_MAX_SECONDS = 2.0


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


def _revision_hash(revision: Path) -> str:
    script_path = revision / "script/script.yaml"
    sb_path = revision / "storyboard/storyboard.yaml"
    if not script_path.is_file() or not sb_path.is_file():
        raise ValueError("shorts_plan requires script/script.yaml and storyboard/storyboard.yaml")
    return canonical_json_hash(
        {"script": read_yaml(script_path), "storyboard": read_yaml(sb_path)}
    )


def save_shorts_plan(project_dir: Path, file_path: Path) -> Path:
    """Validate ``ShortsPlan`` against storyboard & ledger and save ``posts/shorts-plan.yaml``."""
    project = _project(project_dir)
    revision = project_dir / "revisions" / project.active_revision
    rev_hash = _revision_hash(revision)
    Script.model_validate(read_yaml(revision / "script/script.yaml"))
    storyboard = Storyboard.model_validate(read_yaml(revision / "storyboard/storyboard.yaml"))
    scene_index = {scene.id: idx for idx, scene in enumerate(storyboard.scenes)}
    ledger = read_yaml(revision / "evidence/ledger.yaml")
    claim_ids = {
        str(item.get("id"))
        for item in ledger.get("claims", [])
        if isinstance(item, dict) and item.get("id")
    }
    plan = ShortsPlan.model_validate(read_yaml(file_path))
    for clip in plan.clips:
        if clip.start_scene_id not in scene_index:
            raise ValueError(f"{clip.id}: unknown start_scene_id {clip.start_scene_id}")
        if clip.end_scene_id not in scene_index:
            raise ValueError(f"{clip.id}: unknown end_scene_id {clip.end_scene_id}")
        if scene_index[clip.start_scene_id] > scene_index[clip.end_scene_id]:
            raise ValueError(f"{clip.id}: start_scene_id must not come after end_scene_id")
        for text_field in (clip.hook_text, clip.caption, clip.safety_caveat):
            for cid in _CLAIM_REF_RE.findall(text_field):
                if cid not in claim_ids:
                    raise ValueError(f"{clip.id}: unknown ledger claim {cid}")
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
        rev_hash = _revision_hash(revision)
        target = revision / SHORTS_PLAN_ARTIFACT
        if not target.is_file():
            return False
        plan = ShortsPlan.model_validate(read_yaml(target))
    except (OSError, TypeError, ValueError):
        return False
    return plan.revision_hash == rev_hash
