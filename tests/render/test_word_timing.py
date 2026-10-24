import pytest
from pydantic import ValidationError

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import build_render_input
from healthvideo.render.word_timing import apply_alignment


def mechanism(**updates):
    data = {'id': 'S01', 'start_frame': 0, 'duration_frames': 300, 'script_line_id': 'LN01',
                'narration': 'Tinh thể urat lớn rồi lắng đọng', 'visual': 'process_animation',
                'anatomy': {'subject': 'joint_fluid_urate_to_inflammation', 'state': 'diseased',
                             'severity': .8, 'motion': 'crystals',
                             'cues': [{'word': 'lắng', 'action': 'deposit'}]}}
    data.update(updates)
    return Scene.model_validate(data)


def test_cue_word_must_be_in_narration():
    with pytest.raises(ValidationError, match='cue word must be in narration'):
        mechanism(narration='không có từ đó')


def test_cue_action_must_exist():
    with pytest.raises(ValidationError, match='cue action must exist'):
        mechanism(anatomy={'subject': 'joint_fluid_urate_to_inflammation', 'state': 'diseased',
                              'motion': 'test', 'cues': [{'word': 'urat', 'action': 'alarm'}]})


def test_render_input_carries_word_frames():
    board = Storyboard(title='test', scenes=(mechanism(),))
    aligned = {'LN01': [{'word': 'Tinh', 'start': .2, 'end': .5},
                        {'word': 'lắng', 'start': 5, 'end': 5.5}]}
    result = build_render_input(apply_alignment(board, aligned), 'audio/narration.wav')
    scene = result.model_dump(mode='json')['scenes'][0]
    assert scene['words'][0] == {'text': 'Tinh', 'start_frame': 6, 'end_frame': 15}
    assert scene['anatomy']['cues'][0]['start_frame'] == 150


def test_render_input_slices_shared_line_words_and_local_cues():
    first = mechanism(duration_frames=150, anatomy={'subject': 'immune_cell_alarm',
                      'state': 'diseased', 'motion': 'test', 'cues': []})
    second = mechanism(id='S02', start_frame=150, duration_frames=150)
    board = Storyboard(title='test', scenes=(first, second))
    aligned = {'LN01': [{'word': 'Tinh', 'start': 0, 'end': .5},
                        {'word': 'lắng', 'start': 6, 'end': 6.5}]}
    result = apply_alignment(board, aligned)
    assert [w.text for w in result.scenes[1].words] == ['lắng']
    assert result.scenes[1].words[0].start_frame == 30
    assert result.scenes[1].anatomy.cues[0].start_frame == 30


def test_front_loaded_entrances_rejected():
    board = Storyboard(title='test', scenes=(Scene.model_validate({
        'id': 'S01', 'start_frame': 0, 'duration_frames': 300, 'narration': 'test', 'visual': 'whiteboard',
        'on_screen_text': 'một; hai', 'entrances': [{'text': 'một;', 'start_frame': 0},
                                              {'text': ' hai', 'start_frame': 30}]}),))
    with pytest.raises(ValidationError, match='front-loaded'):
        build_render_input(board, 'audio/narration.wav')


def test_text_entrances_use_keyword_and_spread_fallback():
    scene = Scene(id='S01', start_frame=0, duration_frames=300, narration='test', visual='whiteboard',
                  on_screen_text='Tinh thể; thiếu', words=[{'text': 'Tinh', 'start_frame': 60, 'end_frame': 75}])
    result = build_render_input(Storyboard(title='test', scenes=(scene,)), 'audio/narration.wav')
    assert [e.start_frame for e in result.scenes[0].entrances] == [60, 210]
