"""Long-form Gate 1 plans: script/outline.yaml and script/clip-plan.yaml."""

import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from healthvideo.audio.sfx import mix_sfx
from healthvideo.domain.asset_manifest import AssetKind, AssetManifest, AssetRecord
from healthvideo.domain.brand import (
    BrandProfile,
    LogoVariant,
    MascotPose,
    load_brand_profile,
)
from healthvideo.domain.clip_plan import (
    CLIP_MIN_FRAMES,
    ClipPlan,
    validate_clip_plan,
    vertical_clip_storyboard,
)
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.license_ledger import LicenseEntry, LicenseLedger
from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import (
    RenderInput,
    YouTubeCTA,
    audio_timing_qa,
    build_render_input,
)
from healthvideo.render.remotion import build_render_argv
from healthvideo.render.timing import concat_scene_audio
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.audio_checks import inspect_wav
from healthvideo.visuals.brand import render_pyh_logo
from healthvideo.visuals.mascot import mascot_asset
from healthvideo.workflows.factory_standards import style_a_active
from healthvideo.workflows.shorts_plan import (
    SHORTS_CLIP_MAX_FRAMES,
    SHORTS_PLAN_ARTIFACT,
    ShortsPlan,
    _revision_hash,
    _verify_medical_gate,
    resolve_revision_root,
    revision_tx_lock,
    sync_shorts_plan_to_clip_plan,
)
from healthvideo.workflows.visual_assets import BRAND_PROFILE_PATH

OUTLINE_ARTIFACT = "script/outline.yaml"
CLIP_PLAN_ARTIFACT = "script/clip-plan.yaml"
_LEGACY_FALLBACK_FIELDS = frozenset({
    "mascot_max_width_percent",
    "subtitle_position",
    "hook_window_seconds",
    "safe_zone_checked",
    "hook_text",
    "safety_caveat",
    "caption",
    "target_seconds",
    "loop_bridge",
    "revision_hash",
    "schema_version",
})


def _shorts_plan_applies(revision: Path) -> bool:
    """Shorts plan applies only after medical approval, with matching revision_hash and compatible schema."""
    from healthvideo.workflows.gate_review import MEDICAL_APPROVAL_ARTIFACT

    shorts_path = revision / SHORTS_PLAN_ARTIFACT
    if not shorts_path.is_file() or not (revision / MEDICAL_APPROVAL_ARTIFACT).is_file():
        return False
    has_clip_plan = (revision / CLIP_PLAN_ARTIFACT).is_file()
    try:
        raw = read_yaml(shorts_path)
    except (OSError, ValueError):
        return not (has_clip_plan and not style_a_active(revision))
    if not isinstance(raw, dict):
        return not (has_clip_plan and not style_a_active(revision))
    script_path = revision / "script/script.yaml"
    sb_path = revision / "storyboard/storyboard.yaml"
    if has_clip_plan and script_path.is_file() and sb_path.is_file():
        try:
            expected_rev_hash = _revision_hash(revision)
        except (OSError, ValueError):
            expected_rev_hash = ""
        plan_hash = raw.get("revision_hash")
        if expected_rev_hash and (
            not isinstance(plan_hash, str) or not plan_hash or plan_hash != expected_rev_hash
        ):
            return False
    if has_clip_plan and not style_a_active(revision):
        try:
            ShortsPlan.model_validate(raw)
        except (ValidationError, ValueError) as error:
            if _is_legacy_style_a_shorts_incompatibility(revision, error):
                return False
    return True


def _is_legacy_style_a_shorts_incompatibility(revision: Path, error: Exception) -> bool:
    """Return True only when a pre-Style-A revision has an old/incompatible shorts-plan schema."""
    if style_a_active(revision) or not (revision / CLIP_PLAN_ARTIFACT).is_file():
        return False
    if isinstance(error, ValidationError):
        has_legacy_field_error = False
        has_clips_too_short = False
        for item in error.errors():
            err_type = str(item.get("type", ""))
            loc_parts = {str(part) for part in item.get("loc", ())}
            if err_type in {"missing", "extra_forbidden"} or (loc_parts & _LEGACY_FALLBACK_FIELDS):
                if loc_parts & _LEGACY_FALLBACK_FIELDS:
                    has_legacy_field_error = True
                continue
            if err_type == "too_short" and item.get("loc") == ("clips",):
                has_clips_too_short = True
                continue
            return False
        if has_clips_too_short and not has_legacy_field_error:
            return False
        return bool(error.errors())
    message = str(error)
    return "9:16 safe zone must be verified" in message or "chuẩn A 9:16 yêu cầu" in message


def _resolve_effective_clip_plan(
    revision_root: Path,
    *,
    require_medical_approval: bool = True,
) -> tuple[ClipPlan, bool]:
    """Resolve ``(ClipPlan, used_shorts_plan)`` under ``revision_tx_lock``."""
    revision = resolve_revision_root(revision_root)
    with revision_tx_lock(revision):
        if _shorts_plan_applies(revision):
            try:
                return (
                    sync_shorts_plan_to_clip_plan(
                        revision, require_medical_approval=require_medical_approval
                    ),
                    True,
                )
            except (ValidationError, ValueError) as error:
                if not _is_legacy_style_a_shorts_incompatibility(revision, error):
                    raise
                _verify_medical_gate(revision, require_medical_approval=require_medical_approval)
        clip_plan_path = revision / CLIP_PLAN_ARTIFACT
        if not clip_plan_path.is_file():
            raise FileNotFoundError(f"youtube_long needs {CLIP_PLAN_ARTIFACT}")
        return ClipPlan.model_validate(read_yaml(clip_plan_path)), False


def load_effective_clip_specs(
    revision_root: Path,
    *,
    require_medical_approval: bool = True,
) -> ClipPlan:
    """Return effective vertical ClipPlan: synced ``posts/shorts-plan.yaml`` if present, else ``script/clip-plan.yaml``."""
    plan, _ = _resolve_effective_clip_plan(
        revision_root, require_medical_approval=require_medical_approval
    )
    return plan


def load_clip_scenes(
    revision_root: Path,
    storyboard: Storyboard,
    *,
    require_medical_approval: bool = True,
) -> dict[str, tuple[Scene, ...]]:
    """Validate outline + effective clip plan against storyboard and ledger; return each clip's scenes."""
    revision = resolve_revision_root(revision_root)
    with revision_tx_lock(revision):
        if not (revision / OUTLINE_ARTIFACT).is_file():
            raise FileNotFoundError(f"youtube_long needs {OUTLINE_ARTIFACT}")
        has_shorts_plan = _shorts_plan_applies(revision)
        if not has_shorts_plan and not (revision / CLIP_PLAN_ARTIFACT).is_file():
            raise FileNotFoundError(f"youtube_long needs {CLIP_PLAN_ARTIFACT}")
        ledger = read_yaml(revision / "evidence" / "ledger.yaml")
        claims = {
            claim.id: claim
            for claim in (
                EvidenceClaim.model_validate(item) for item in ledger.get("claims", [])
            )
        }
        outline = Outline.model_validate(read_yaml(revision / OUTLINE_ARTIFACT))
        validate_outline(outline, storyboard, claims.keys())
        plan, from_shorts = _resolve_effective_clip_plan(
            revision, require_medical_approval=require_medical_approval
        )
        if from_shorts:
            return validate_clip_plan(
                plan,
                storyboard,
                claims,
                min_frames=CLIP_MIN_FRAMES,
                max_frames=SHORTS_CLIP_MAX_FRAMES,
                require_style_a=True,
            )
        return validate_clip_plan(plan, storyboard, claims)


def clip_render_input(
    storyboard: Storyboard,
    scenes: Sequence[Scene],
    audio_file: str,
    *,
    brand: BrandProfile | None = None,
) -> RenderInput:
    """Re-time the clip's approved scenes from frame 0 as a 9:16 render (re-laid out, not cropped)."""
    board = vertical_clip_storyboard(storyboard, scenes)
    brand = brand or load_brand_profile(BRAND_PROFILE_PATH)
    result = build_render_input(board, audio_file)
    return RenderInput.model_validate(
        {
            **result.model_dump(),
            "youtube_cta": YouTubeCTA(
                text=brand.cta.youtube_full_video,
                mascot_path=("clips/cta/welcome.png" if brand.mascot.artwork is not None
                             else "clips/cta/welcome.svg"),
            ).model_dump(),
        }
    )


def render_clips(
    clip_scenes: Mapping[str, Sequence[Scene]],
    storyboard: Storyboard,
    staging_dir: Path,
    *,
    line_wavs: Mapping[str, Path],
    runner: Callable[[list[str]], int],
    brand: BrandProfile | None = None,
    revision: str = "001",
    sfx_events: list[dict] | None = None,
    min_frames: int = CLIP_MIN_FRAMES,
) -> dict[str, str]:
    """Reuse measured line audio for each clip; return run-relative mp4 paths."""
    # ponytail: clips re-render with every long-form render; cache per clip if it gets slow.
    brand = brand or load_brand_profile(BRAND_PROFILE_PATH)
    _register_clip_mascot(staging_dir, brand, revision)
    outputs: dict[str, str] = {}
    for clip_id, scenes in clip_scenes.items():
        frames = sum(scene.duration_frames for scene in scenes) + 90
        if not min_frames <= frames <= 5400:
            raise ValueError(
                f"Clip {clip_id}: {frames} frames including CTA; requires {min_frames}–5400 frames"
            )
        selected_lines = {scene.script_line_id for scene in scenes if scene.script_line_id}
        audio = f"audio/clips/{clip_id}.wav"
        render_input = clip_render_input(storyboard, scenes, audio, brand=brand)
        # The reviewed clip content is followed by an intentional silent CTA.
        cta = Scene(
            id=f"{clip_id}-CTA", start_frame=frames - 90, duration_frames=90,
            narration="", visual="whiteboard", on_screen_text=brand.cta.youtube_full_video,
        )
        board = storyboard.model_copy(update={"scenes": (*render_input.scenes, cta)})
        alignment = concat_scene_audio(
            board, {line: line_wavs[line] for line in selected_lines}, staging_dir / audio,
            source_board=storyboard,
        )
        # Reuse each selected scene's resolved cues, including original chapter defaults.
        # Remap their timestamps rather than introducing a new chapter cue at a clip cut.
        clip_events = []
        for original, retimed in zip(scenes, render_input.scenes, strict=True):
            for event in sfx_events or []:
                if event['scene'] == original.id:
                    clip_events.append({**event, 'time': retimed.start_frame / 30 + event['at']})
        if clip_events:
            voice = staging_dir / f'audio/clips/{clip_id}-voice.wav'
            shutil.copyfile(staging_dir / audio, voice)
            mix_sfx(voice, clip_events, out=staging_dir / audio)
            (staging_dir / f'audio/clips/{clip_id}.sfx.json').write_text(
                json.dumps(clip_events, ensure_ascii=False), encoding='utf-8',
            )
        duration_ms = inspect_wav(staging_dir / audio).duration_ms
        timing_record = {
            "schema_version": "1.0", "fps": 30, "audio_alignment": alignment,
            "intentional_tail_frames": 90,
        }
        timing_qa = audio_timing_qa(
            duration_ms, frames, timing_record=timing_record
        )
        timing_path = staging_dir / "clips" / f"{clip_id}.scene-timing.json"
        timing_path.parent.mkdir(parents=True, exist_ok=True)
        timing_path.write_text(
            json.dumps(timing_record),
            encoding="utf-8",
        )
        qa_path = staging_dir / "clips" / f"{clip_id}.video-qa.json"
        qa_path.parent.mkdir(parents=True, exist_ok=True)
        qa_path.write_text(json.dumps(timing_qa, sort_keys=True), encoding="utf-8")
        input_path = staging_dir / "clips" / f"{clip_id}.render-input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            json.dumps(
                render_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
            ),
            encoding="utf-8",
        )
        output = staging_dir / "clips" / f"{clip_id}.mp4"
        if (
            runner(build_render_argv(input_path, output, staging_dir)) != 0
            or not output.is_file()
        ):
            raise RuntimeError(f"Clip {clip_id} render failed")
        outputs[clip_id] = f"clips/{clip_id}.mp4"
    return outputs


def _register_clip_mascot(
    staging_dir: Path, brand: BrandProfile, revision: str
) -> None:
    """Register a render-owned decorative asset without changing reviewed artifacts."""
    content, suffix = mascot_asset(brand, MascotPose.WELCOME)
    assets = (
        (f"clips/cta/welcome{suffix}", content, AssetKind.MASCOT_REACTION,
         "mascot", "built_in:pyh-mascot", "Fixed welcome pose with no content fields."),
        ("clips/cta/logo.svg", render_pyh_logo(brand, LogoVariant.REVERSE), AssetKind.FLOURISH,
         "brand", "built_in:pyh-logo", "Fixed decorative PYH reverse logo geometry."),
    )
    records = []
    entries = []
    for path, content, kind, role, source, reason in assets:
        target = staging_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        record = AssetRecord(
            path=path, kind=kind, semantic=False, classification_reason=reason,
            sha256=sha256(content).hexdigest(), source=source,
            license=brand.assets.license, creator=brand.assets.creator,
            revision=revision, rights_required=True, storyboard_role=role,
        )
        records.append(record)
        entries.append(LicenseEntry(
            path=path, source=record.source, creator=record.creator,
            license=record.license, rights_basis=record.license,
            revision=revision, sha256=record.sha256,
        ))
    directory = staging_dir / "clips/cta"
    write_yaml_atomic(
        directory / "asset-manifest.yaml",
        AssetManifest(assets=tuple(records)).model_dump(mode="json"),
    )
    write_yaml_atomic(
        directory / "license-ledger.yaml",
        LicenseLedger(entries=tuple(entries)).model_dump(mode="json"),
    )
