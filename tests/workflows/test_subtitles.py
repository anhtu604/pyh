
import pytest

from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene
from healthvideo.render.input import RenderInput
from healthvideo.workflows.subtitles import render_subtitles, split_line_srt


@pytest.mark.parametrize('duration', [6000, 12501, 24000])
def test_srt_preserves_vietnamese_with_bounded_proportional_cues(duration):
    text = 'Hãy đọc nhãn thực phẩm. Giảm muối từ từ để vị giác quen dần; không tự ý ngừng thuốc.'
    blocks = split_line_srt(text, 3_601_123, duration)
    recovered = []
    previous = 3_601_123
    for start, end, caption in blocks:
        assert start == previous
        assert 1000 <= end - start <= 6000
        assert 1 <= len(caption.splitlines()) <= 2
        assert all(len(line) <= 42 for line in caption.splitlines())
        recovered.extend(caption.split())
        previous = end
    assert previous == 3_601_123 + duration
    assert recovered == text.split()
    weights = [len(caption.replace('\n', ' ')) + (i < len(blocks) - 1)
               for i, (_, _, caption) in enumerate(blocks)]
    for (start, end, _), weight in zip(blocks, weights, strict=True):
        assert abs((end - start) - duration * weight / sum(weights)) <= 1


@pytest.mark.parametrize(('text', 'duration'), [('Xin chào', 999), ('a' * 43, 3000),
                                            ('Xin', 7000), ('từ ' * 100, 1000)])
def test_srt_refuses_impossible_limits_instead_of_extending_speech(text, duration):
    with pytest.raises(ValueError, match='subtitle'):
        split_line_srt(text, 0, duration)


def _shared_line_input():
    script = Script.model_construct(lines=(
        ScriptLine.model_construct(id='L01', text='Hãy đọc nhãn thực phẩm.'),
        ScriptLine.model_construct(id='OUTRO', text='Chúc bạn sức khỏe.'),
    ))
    rows = [
        {'scene_id': 'S01', 'script_line_id': 'L01', 'start_frame': 30, 'duration_frames': 60, 'audio_ms': 4000},
        {'scene_id': 'S02', 'script_line_id': 'L01', 'start_frame': 90, 'duration_frames': 69, 'audio_ms': 4000},
        {'scene_id': 'S03', 'script_line_id': None, 'start_frame': 159, 'duration_frames': 30, 'audio_ms': 0},
        {'scene_id': 'S04', 'script_line_id': 'OUTRO', 'start_frame': 189, 'duration_frames': 69, 'audio_ms': 2000},
    ]
    scenes = tuple(Scene.model_construct(id=row['scene_id'], **{
        k: row[k] for k in ('script_line_id', 'start_frame', 'duration_frames')
    }) for row in rows)
    render_input = RenderInput.model_construct(format_profile='youtube_long', scenes=scenes)
    return script, render_input, {'fps': 30, 'scenes': rows}


def test_srt_shared_line_spoken_once_excludes_silent_padding_and_keeps_outro():
    assert render_subtitles(*_shared_line_input()) == (
        '1\n00:00:01,000 --> 00:00:05,000\nHãy đọc nhãn thực phẩm.\n\n'
        '2\n00:00:06,300 --> 00:00:08,300\nChúc bạn sức khỏe.\n\n'
    )


@pytest.mark.parametrize('damage', ['fps', 'scene', 'shared_duration', 'missing_line', 'overflow'])
def test_srt_refuses_inconsistent_measured_timing(damage):
    script, render_input, timing = _shared_line_input()
    if damage == 'fps':
        timing['fps'] = 24
    elif damage == 'scene':
        timing['scenes'][0]['start_frame'] = 0
    elif damage == 'shared_duration':
        timing['scenes'][1]['audio_ms'] = 3999
    elif damage == 'missing_line':
        script = script.model_copy(update={'lines': (*script.lines, ScriptLine.model_construct(id='L03', text='Thiếu.'))})
    else:
        timing['scenes'][0]['audio_ms'] = timing['scenes'][1]['audio_ms'] = 5000
    with pytest.raises(ValueError):
        render_subtitles(script, render_input, timing)
