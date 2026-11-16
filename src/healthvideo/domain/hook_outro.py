from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard

OUTRO_TEXT = (
    "Nếu mình có gì sai sót, hoặc bạn có bất kỳ câu hỏi nào, "
    "hãy để lại phản hồi dưới phần bình luận nhé. Cảm ơn bạn đã xem video."
)
CHANNEL_OUTRO_TEXT = (
    "Trên đây chỉ là thông tin tổng hợp, không phải là lời khuyên y khoa. "
    "Nếu thấy hay và thích video, xin hãy để lại 1 lượt like và subscribe cho chúng mình. "
    "Cảm ơn bạn đã xem video!"
)


def validate_hook_outro(
    script: Script, storyboard: Storyboard, *, require_brand: bool = False,
    allow_line_references: bool = False,
) -> None:
    if len(script.lines) < 2 or len(script.lines) != len(storyboard.scenes):
        raise ValueError("M6.4 script and storyboard must align with one outro")
    if [line.purpose for line in script.lines].count("outro") != 1:
        raise ValueError("M6.4 requires exactly one outro")
    outro = script.lines[-1]
    # Existing revisions can still carry the original pinned outro.
    if outro.purpose != "outro" or outro.text not in {CHANNEL_OUTRO_TEXT, OUTRO_TEXT}:
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
        raise ValueError("M6.4 outro requires exactly one declared PYH logo")
