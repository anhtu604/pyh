from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard

OUTRO_TEXT = (
    "Nếu mình có gì sai sót, hoặc bạn có bất kỳ câu hỏi nào, "
    "hãy để lại phản hồi dưới phần bình luận nhé. Cảm ơn bạn đã xem video."
)


def validate_hook_outro(
    script: Script, storyboard: Storyboard, *, require_brand: bool = False
) -> None:
    if script.format_profile == "legacy":
        if any(line.purpose == "outro" for line in script.lines) or any(
            scene.visual == "brand_outro" or scene.script_line_id is not None
            for scene in storyboard.scenes
        ):
            raise ValueError("legacy script cannot contain M6.4 fields")
        return
    if len(script.lines) < 2 or len(script.lines) != len(storyboard.scenes):
        raise ValueError("M6.4 script and storyboard must align with one outro")
    if [line.purpose for line in script.lines].count("outro") != 1:
        raise ValueError("M6.4 requires exactly one outro")
    if script.lines[-1].purpose != "outro" or script.lines[-1].text != OUTRO_TEXT:
        raise ValueError("M6.4 final outro must match pinned text")
    if storyboard.scenes[0].start_frame != 0 or any(
        scene.visual == "brand_outro" for scene in storyboard.scenes[:-1]
    ):
        raise ValueError("M6.4 hook must start at zero and outro must be last")
    if len({line.id for line in script.lines}) != len(script.lines):
        raise ValueError("M6.4 script line IDs must be unique")
    for line, scene in zip(script.lines, storyboard.scenes, strict=True):
        if scene.script_line_id != line.id or scene.narration != line.text:
            raise ValueError("M6.4 line and scene mismatch")
    final = storyboard.scenes[-1]
    if final.visual != "brand_outro" or final.claim_id or final.source_marker:
        raise ValueError("M6.4 final scene must be nonmedical brand_outro")
    if final.evidence_highlight or script.lines[-1].claim_id or script.lines[-1].source_marker:
        raise ValueError("M6.4 outro cannot carry medical evidence")
    if any(ref.role not in {"brand", "mascot"} for ref in final.visual_assets):
        raise ValueError("M6.4 outro has invalid visual role")
    if require_brand and sum(ref.role == "brand" for ref in final.visual_assets) != 1:
        raise ValueError("M6.4 outro requires exactly one declared PHY logo")
