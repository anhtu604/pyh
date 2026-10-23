"""Scene-local word/cue/entrance timing derived from measured line audio."""
import re
from collections.abc import Mapping

from healthvideo.audio.align import normalize_word
from healthvideo.domain.storyboard import CaptionWord, Scene, Storyboard, TextEntrance


def _keyword_frame(text: str, words: tuple[CaptionWord, ...]) -> int | None:
    tokens = [normalize_word(t) for t in text.split()]
    normalized = [normalize_word(w.text) for w in words]
    if not tokens:
        return None
    for i in range(len(normalized)-len(tokens)+1):
        if normalized[i:i+len(tokens)] == tokens:
            return words[i].start_frame
    return None


def resolve_scene_entrances(scene: Scene) -> Scene:
    """Keep text intact, splitting only authored separators as the renderer does."""
    if scene.entrances or not scene.on_screen_text:
        return scene
    pieces = re.findall(r'[^;\n•]+[;\n•]?', scene.on_screen_text)
    entrances = []
    for i, text in enumerate(pieces):
        first = text.strip().split()[0] if text.strip() else ''
        start = _keyword_frame(first, scene.words)
        if start is None:
            fraction = (.35 if scene.duration_frames > 120 else 0) if len(pieces) == 1 else .7*i/(len(pieces)-1)
            start = round(scene.duration_frames*fraction)
        entrances.append(TextEntrance(text=text, start_frame=min(scene.duration_frames-1, start)))
    return scene.model_copy(update={'entrances': tuple(entrances)})


def apply_alignment(board: Storyboard, alignment: Mapping[str, list[dict]]) -> Storyboard:
    """Slice a shared line's words at scene boundaries; never repeat its full WAV."""
    origins = {}
    scenes = []
    for scene in board.scenes:
        line = scene.script_line_id
        origins.setdefault(line, scene.start_frame)
        offset = scene.start_frame - origins[line]
        words = []
        aligned_words = alignment.get(line, [])
        if aligned_words and not any(w.get('matched', True) for w in aligned_words):
            aligned_words = []  # No anchors: retain legacy caption/cue timing.
        for word in aligned_words:
            start, end = round(word['start']*30)-offset, round(word['end']*30)-offset
            if end <= 0 or start >= scene.duration_frames:
                continue
            words.append(CaptionWord(text=word['word'], start_frame=max(0, start),
                                     end_frame=min(scene.duration_frames, max(0, end))))
        updates = {'words': tuple(words)}
        if scene.anatomy and words:
            cues = []
            for cue in scene.anatomy.cues:
                start = _keyword_frame(cue.word, tuple(words))
                cues.append(cue.model_copy(update={'start_frame': start}))
            updates['anatomy'] = scene.anatomy.model_copy(update={'cues': tuple(cues)})
        scenes.append(scene.model_copy(update=updates))
    return board.model_copy(update={'scenes': tuple(scenes)})


def entrance_timing_qa(scene: Scene) -> None:
    """Validate the observable render contract, without inspecting React code."""
    starts = [e.start_frame for e in scene.entrances]
    starts += [c.start_frame for c in scene.anatomy.cues if c.start_frame is not None] if scene.anatomy else []
    if any(start < 0 or start >= scene.duration_frames for start in starts):
        raise ValueError(f'Scene {scene.id}: entrance timing outside scene')
    if scene.duration_frames > 120 and starts and all(start < .15*scene.duration_frames for start in starts):
        raise ValueError(f'Scene {scene.id}: front-loaded entrances all within first 15%')
