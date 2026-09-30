"""Long-form Gate 1 plans: script/outline.yaml and script/clip-plan.yaml."""

from pathlib import Path

from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard
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
