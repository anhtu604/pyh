"""Shared projections of approved content onto the long-form timeline."""

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene, Storyboard

CLIP_PURPOSES = frozenset({"clip_hook", "clip_outro"})


def long_form_lines(script: Script) -> tuple[ScriptLine, ...]:
    return tuple(line for line in script.lines if line.purpose not in CLIP_PURPOSES)


def long_form_scenes(storyboard: Storyboard) -> tuple[Scene, ...]:
    if storyboard.format_profile != "youtube_long":
        return storyboard.scenes
    return tuple(scene for scene in storyboard.scenes if scene.clip_only is None)


def long_form_script(script: Script) -> Script:
    return script.model_copy(update={"lines": list(long_form_lines(script))})


def long_form_storyboard(storyboard: Storyboard) -> Storyboard:
    return storyboard.model_copy(update={"scenes": long_form_scenes(storyboard)})
