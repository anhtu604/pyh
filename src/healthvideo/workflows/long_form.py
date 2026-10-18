"""Long-form Gate 1 plans: script/outline.yaml and script/clip-plan.yaml."""

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import RenderInput, audio_timing_qa, build_render_input
from healthvideo.render.remotion import build_render_argv
from healthvideo.storage.files import read_yaml

OUTLINE_ARTIFACT = "script/outline.yaml"
CLIP_PLAN_ARTIFACT = "script/clip-plan.yaml"


def load_clip_scenes(revision_root: Path, storyboard: Storyboard) -> dict[str, tuple[Scene, ...]]:
    """Validate outline + clip plan against storyboard and ledger; return each clip's scenes."""
    for name in (OUTLINE_ARTIFACT, CLIP_PLAN_ARTIFACT):
        if not (revision_root / name).is_file():
            raise FileNotFoundError(f"youtube_long needs {name}")
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    claims = {
        claim.id: claim
        for claim in (EvidenceClaim.model_validate(item) for item in ledger.get("claims", []))
    }
    outline = Outline.model_validate(read_yaml(revision_root / OUTLINE_ARTIFACT))
    validate_outline(outline, storyboard, claims.keys())
    plan = ClipPlan.model_validate(read_yaml(revision_root / CLIP_PLAN_ARTIFACT))
    return validate_clip_plan(plan, storyboard, claims)


def clip_render_input(
    storyboard: Storyboard, scenes: Sequence[Scene], audio_file: str
) -> RenderInput:
    """Re-time the clip's approved scenes from frame 0 as a 9:16 render (re-laid out, not cropped)."""
    retimed: list[Scene] = []
    start = 0
    for scene in scenes:
        retimed.append(scene.model_copy(update={"start_frame": start, "chapter_id": None}))
        start += scene.duration_frames
    board = Storyboard(
        title=storyboard.title,
        scenes=tuple(retimed),
        visual_budget_profile=storyboard.visual_budget_profile,
        format_profile="vertical_clip",
    )
    return build_render_input(board, audio_file, duration_policy="v2")


def render_clips(
    clip_scenes: Mapping[str, Sequence[Scene]],
    storyboard: Storyboard,
    staging_dir: Path,
    *,
    synthesize: Callable[[str, Path], int],
    runner: Callable[[list[str]], int],
) -> dict[str, str]:
    """Voice and render each approved clip; return clip ID -> mp4 path relative to the run."""
    # ponytail: clips re-render with every long-form render; cache per clip if it gets slow.
    outputs: dict[str, str] = {}
    for clip_id, scenes in clip_scenes.items():
        audio = f"audio/clips/{clip_id}.wav"
        duration_ms = synthesize(" ".join(scene.narration for scene in scenes), staging_dir / audio)
        audio_timing_qa(duration_ms, sum(scene.duration_frames for scene in scenes))
        render_input = clip_render_input(storyboard, scenes, audio)
        input_path = staging_dir / "clips" / f"{clip_id}.render-input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            json.dumps(render_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        output = staging_dir / "clips" / f"{clip_id}.mp4"
        if runner(build_render_argv(input_path, output, staging_dir)) != 0 or not output.is_file():
            raise RuntimeError(f"Clip {clip_id} render failed")
        outputs[clip_id] = f"clips/{clip_id}.mp4"
    return outputs
