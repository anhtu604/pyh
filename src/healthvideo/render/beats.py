"""Resolve approved visual beats and reject long stretches without visible changes."""
from itertools import pairwise

from healthvideo.audio.align import normalize_word
from healthvideo.domain.storyboard import CaptionWord, Scene
from healthvideo.render.word_timing import _keyword_frame, resolve_scene_entrances


def resolve_scene_beats(scene: Scene, *, fps: int = 30, clamp_outside: bool = False) -> Scene:
    """Use existing Whisper word anchors; proportional tokens only for draft/offline fallback."""
    words = scene.words
    if not words:
        tokens = scene.narration.split()
        words = tuple(CaptionWord(text=text, start_frame=round(i*scene.duration_frames/len(tokens)),
                                  end_frame=round((i+1)*scene.duration_frames/len(tokens)))
                      for i, text in enumerate(tokens))
    beats = []
    for beat in scene.beats:
        start = (_keyword_frame(beat.at, words) if isinstance(beat.at, str)
                 else round(beat.at*fps))
        if start is None:
            raise ValueError(f"Scene {scene.id}: beat keyword has no scene-local alignment: {beat.at}")
        if not 0 <= start < scene.duration_frames and not clamp_outside:
            raise ValueError(f"Scene {scene.id}: beat at {beat.at!r} ({start} frames) "
                             f"outside timed scene of {scene.duration_frames} frames")
        beats.append(beat.model_copy(update={"start_frame": start}))
    starts = [beat.start_frame for beat in beats]
    if starts != sorted(starts) or len(starts) != len(set(starts)):
        raise ValueError(f"Scene {scene.id}: beats must have distinct increasing times")
    if clamp_outside and starts and starts[-1] >= scene.duration_frames:
        if len(starts) > scene.duration_frames:
            raise ValueError(f"Scene {scene.id}: {len(starts)} beats cannot fit "
                             f"{scene.duration_frames} frames")
        # Work backwards so several overflowing beats occupy distinct final frames.
        ceiling = scene.duration_frames - 1
        for index in range(len(beats) - 1, -1, -1):
            start = min(starts[index], ceiling)
            updates = {"start_frame": start}
            if start != starts[index]:
                updates["at"] = start / fps
            beats[index] = beats[index].model_copy(update=updates)
            ceiling = start - 1
    result = resolve_scene_entrances(scene.model_copy(update={"beats": tuple(beats)}))
    return result.model_copy(update={"words": words})


def visual_rhythm_qa(scene: Scene, *, fps: int = 30) -> None:
    """Cuts, changed focus/labels/actions and newly visible text reset the six-second clock."""
    changes = {0, scene.duration_frames}
    focus, labels = None, ()
    useful_beats = 0
    actions: set[str] = set()
    for beat in scene.beats:
        if beat.start_frame is None or not 0 <= beat.start_frame < scene.duration_frames:
            raise ValueError(f"Scene {scene.id}: beat requires resolved timing inside scene")
        # An action is a new process event; repeated unchanged focus/labels alone is not a change.
        if beat.focus != focus or set(beat.labels) != set(labels) or (beat.action is not None and beat.action not in actions):
            changes.add(beat.start_frame)
            useful_beats += 1
        focus, labels = beat.focus, beat.labels
        if beat.action:
            actions.add(beat.action)
    if scene.duration_frames > 12*fps and scene.anatomy is not None and useful_beats < 2:
        raise ValueError(f"Scene {scene.id}: scene over 12 seconds needs at least 2 visual beats")
    visible_text: set[str] = set()
    for entrance in scene.entrances:
        text = entrance.text.strip()
        if text and text not in visible_text:
            changes.add(entrance.start_frame)
            visible_text.add(text)
    if scene.anatomy:
        for cue in scene.anatomy.cues:
            if cue.start_frame is not None and cue.action not in actions:
                changes.add(cue.start_frame)
                actions.add(cue.action)
    # These words are explicitly carried into render-input, including the offline caption fallback.
    # SourceCardScene suppresses captions when the interpretation already equals narration.
    hidden_captions = bool(scene.source_card and
                           scene.source_card.interpretation.strip() == scene.narration.strip())
    if not hidden_captions:
        previous = None
        for word in scene.words:
            text = normalize_word(word.text)
            if text and text != previous:
                changes.add(word.start_frame)
            previous = text
    ordered = sorted(changes)
    for start, end in pairwise(ordered):
        if end-start > 6*fps:
            raise ValueError(f"Scene {scene.id}: visual gap {(end-start)/fps:.2f}s exceeds 6 seconds "
                             f"at {start/fps:.2f}s; add a focus, label, action, text entrance or cut")


def draft_visual_rhythm_qa(scenes: tuple[Scene, ...]) -> None:
    for scene in scenes:
        visual_rhythm_qa(resolve_scene_beats(scene))
