"""Publishing targets: frame size and renderer duration bounds per profile."""

from dataclasses import dataclass
from typing import Literal

FormatProfile = Literal["vertical_clip", "youtube_long"]
FPS = 30


@dataclass(frozen=True)
class FormatSpec:
    width: int
    height: int
    min_frames: int
    max_frames: int


FORMAT_SPECS: dict[str, FormatSpec] = {
    "vertical_clip": FormatSpec(1080, 1920, 45 * FPS, 90 * FPS),
    # ponytail: 60 s floor keeps fixtures small; the 15-min editorial target is
    # outline QA (M8.2), not a renderer rule.
    "youtube_long": FormatSpec(1920, 1080, 60 * FPS, 25 * 60 * FPS),
}
