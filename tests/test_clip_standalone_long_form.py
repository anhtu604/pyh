"""Clip dialogue must not change contracts for the parent video."""

import pytest

from healthvideo.domain.hook_outro import OUTRO_TEXT, validate_hook_outro
from healthvideo.domain.quality_standards import validate_r5_contract
from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.script_style import lint_script_style
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.domain.visual_budget import calculate_visual_budget
from healthvideo.render.input import RenderInput
from healthvideo.render.quality import measure_r5_quality, resolve_r5_shots
from healthvideo.workflows.subtitles import render_subtitles
from tests.render.test_quality import board as quality_board
from tests.render.test_quality import shot


def sample():
    lines = [ScriptLine(id='L1', text='Bạn có thắc mắc gì?'),
             ScriptLine(id='L2', text=OUTRO_TEXT, purpose='outro'),
             ScriptLine(id='H1', text='Bạn có thắc mắc gì?', purpose='clip_hook', clip_id='CL01'),
             ScriptLine(id='O1', text='Hãy xem video đầy đủ trên kênh.', purpose='clip_outro', clip_id='CL01')]
    scenes = [Scene(id='S1', start_frame=0, duration_frames=90, script_line_id='L1',
                    chapter_id='CH01', narration=lines[0].text,
                    visual='whiteboard', on_screen_text='Câu hỏi'),
              Scene(id='S2', start_frame=90, duration_frames=180, script_line_id='L2',
                    chapter_id='CH01', narration=lines[1].text, visual='brand_outro'),
              Scene(id='H1', start_frame=0, duration_frames=90, script_line_id='H1',
                    clip_only='CL01', narration=lines[2].text,
                    visual='whiteboard', on_screen_text='Câu hỏi'),
              Scene(id='O1', start_frame=0, duration_frames=180, script_line_id='O1',
                    clip_only='CL01', narration=lines[3].text,
                    visual='whiteboard', on_screen_text='Xem trên kênh')]
    return Script(title='Ví dụ', format_profile='hook_outro_v1', lines=lines), Storyboard(
        title='Ví dụ', format_profile='youtube_long', visual_budget_profile='m6_5_v1', scenes=scenes)


def test_long_budget_and_pinned_outro_exclude_clip_dialogue():
    script, board = sample()
    assert calculate_visual_budget(board).total_frames == 270
    validate_hook_outro(script, board)


def test_clip_repetition_does_not_trip_long_form_style_lint():
    script, _ = sample()
    assert not [issue for issue in lint_script_style(script) if issue.rule == 'repeated_caveat']


def test_long_r5_measurement_excludes_clip_shots_and_contract_forbids_clip_lines():
    original = quality_board([shot(0, 120)], frames=120)
    main = original.scenes[0].model_copy(update={'chapter_id': 'CH01'})
    clip = main.model_copy(update={'id': 'HOOK', 'clip_only': 'CL01', 'chapter_id': None,
                                  'script_line_id': 'H1', 'shots': (), 'resolved_shots': ()})
    board = original.model_copy(update={'format_profile': 'youtube_long', 'scenes': (main, clip)})
    assert measure_r5_quality(board) == measure_r5_quality(original)
    # Clip-only shots still require resolution when the clip is produced.
    with pytest.raises(ValueError, match='missing R5 shots'):
        resolve_r5_shots(board)
    script = Script(title='Ví dụ', lines=[
        ScriptLine(id='L1', text='Question1? Question2? w0'),
        ScriptLine(id='H1', purpose='clip_hook', clip_id='CL01', text='Question1? Question2?')])
    validate_r5_contract(board, script)
    question = board.r5_contract.questions[0].model_copy(update={'hook_line_id': 'H1'})
    contract = board.r5_contract.model_copy(update={'questions': (question, board.r5_contract.questions[1])})
    with pytest.raises(ValueError, match='missing script line H1'):
        validate_r5_contract(board.model_copy(update={'r5_contract': contract}), script)


def test_long_sidecar_subtitles_exclude_clip_rows_and_dialogue():
    script, board = sample()
    render = RenderInput.model_construct(format_profile='youtube_long', scenes=board.scenes[:2])
    timing = {'fps': 30, 'scenes': [{'scene_id': s.id, 'script_line_id': s.script_line_id,
        'start_frame': s.start_frame, 'duration_frames': s.duration_frames,
        'audio_ms': 2000 if s.id == 'S1' else 6000} for s in board.scenes]}
    result = render_subtitles(script, render, timing)
    assert 'Hãy xem video đầy đủ' not in result
    assert result.count('Bạn có thắc mắc gì?') == 1
    captions = ' '.join(' '.join(block.splitlines()[2:]) for block in result.strip().split('\n\n'))
    assert OUTRO_TEXT in captions
    timing['scenes'].append(dict(timing['scenes'][0], scene_id='UNKNOWN'))
    with pytest.raises(ValueError):
        render_subtitles(script, render, timing)
