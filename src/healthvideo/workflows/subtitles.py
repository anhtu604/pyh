"""Vietnamese sidecar subtitles from approved text and measured production timing."""

from itertools import groupby

from healthvideo.domain.long_form import long_form_lines
from healthvideo.domain.script import Script
from healthvideo.render.input import RenderInput

SUBTITLES_NAME = 'subtitles.vi.srt'


def _wrap(words: list[str]) -> str | None:
    lines = ['']
    for word in words:
        if len(word) > 42:
            return None
        candidate = f'{lines[-1]} {word}'.strip()
        if len(candidate) <= 42:
            lines[-1] = candidate
        else:
            lines.append(word)
        if len(lines) > 2:
            return None
    return '\n'.join(lines)


def split_line_srt(text: str, start_ms: int, duration_ms: int) -> list[tuple[int, int, str]]:
    """Partition at words, preferring punctuation; keep proportional millisecond bounds.

    Refuse infeasible text/timing rather than drop words, stretch speech, or emit
    unreadable cues. Spaces separating cues count toward the preceding cue.
    """
    words = text.split()
    if not words or start_ms < 0 or duration_ms < 1000:
        raise ValueError('Cannot satisfy subtitle limits for this line')
    offsets = [0]
    for index, word in enumerate(words):
        offsets.append(offsets[-1] + len(word) + (index < len(words) - 1))
    times = [start_ms + round(duration_ms * offset / offsets[-1]) for offset in offsets]
    # Shortest path over word boundaries, avoiding greedy splits with tiny tails.
    best: dict[int, tuple[float, int, str]] = {len(words): (0, len(words), '')}
    for i in range(len(words) - 1, -1, -1):
        for j in range(i + 1, len(words) + 1):
            caption = _wrap(words[i:j])
            elapsed = times[j] - times[i]
            if caption is None or elapsed > 6000:
                break
            if elapsed < 1000 or j not in best:
                continue
            punctuation = words[j - 1][-1] in '.!?;,:…'
            cost = best[j][0] + 1 + (0 if punctuation else .4) + ((elapsed - 3000) / 6000) ** 2
            if i not in best or cost < best[i][0]:
                best[i] = (cost, j, caption)
    if 0 not in best:
        raise ValueError('Cannot satisfy subtitle limits for this line')
    result = []
    i = 0
    while i < len(words):
        _, j, caption = best[i]
        result.append((times[i], times[j], caption))
        i = j
    return result


def _timestamp(ms: int) -> str:
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{millis:03}'


def render_subtitles(script: Script, render_input: RenderInput, timing: dict) -> str:
    """Read existing measured line spans; never estimate or retime the storyboard.

    Consecutive scenes sharing a line contain the full audio_ms repeatedly. Speak
    that line once from the first scene start; exclude visual padding/silent scenes.
    The caller verifies the timing file against the approved render manifest.
    """
    if render_input.format_profile != 'youtube_long':
        raise ValueError('Sidecar subtitles require youtube_long')
    clip_line_ids = {line.id for line in script.lines if line.clip_id is not None}
    render_ids = {scene.id for scene in render_input.scenes}
    rows = [row for row in timing['scenes']
            if row['scene_id'] in render_ids or row['script_line_id'] not in clip_line_ids]
    if timing['fps'] != render_input.fps or len(rows) != len(render_input.scenes):
        raise ValueError('Subtitle timing does not match render input')
    for row, scene in zip(rows, render_input.scenes, strict=True):
        if any(row[key] != getattr(scene, key) for key in
               ('script_line_id', 'start_frame', 'duration_frames')) or row['scene_id'] != scene.id:
            raise ValueError('Subtitle timing does not match render input')
    long_lines = long_form_lines(script)
    lines = {line.id: line.text for line in long_lines}
    if len(lines) != len(long_lines):
        raise ValueError('Duplicate subtitle script line')
    seen: set[str] = set()
    cues = []
    previous_end = 0
    for line_id, group in groupby(rows, key=lambda row: row['script_line_id']):
        group = list(group)
        if line_id is None:
            continue
        if line_id not in lines or line_id in seen:
            raise ValueError('Unknown or nonconsecutive subtitle script line')
        seen.add(line_id)
        duration = group[0]['audio_ms']
        if type(duration) is not int or duration <= 0 or any(row['audio_ms'] != duration for row in group):
            raise ValueError('Invalid measured subtitle duration')
        start = round(group[0]['start_frame'] * 1000 / render_input.fps)
        last = group[-1]
        end = round((last['start_frame'] + last['duration_frames']) * 1000 / render_input.fps)
        if start < previous_end or start + duration > end:
            raise ValueError('Overlapping or out-of-scene subtitle speech')
        cues.extend(split_line_srt(lines[line_id], start, duration))
        previous_end = start + duration
    if seen != set(lines):
        raise ValueError('Missing subtitle script line timing')
    return ''.join(f'{i}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n\n'
                   for i, (start, end, text) in enumerate(cues, 1))
