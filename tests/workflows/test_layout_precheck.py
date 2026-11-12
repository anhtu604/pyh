import wave
from pathlib import Path

import pytest

from healthvideo.domain.clip_plan import ClipPlan, ClipSpec
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Script, ScriptLine
from healthvideo.domain.storyboard import Scene, SceneBeat, Storyboard, TextEntrance
from healthvideo.render.beats import resolve_scene_beats
from healthvideo.render.timing import retime_storyboard
from healthvideo.storage.files import read_yaml


def fixture_board():
    # 12% whiteboard, 20% chart, 68% mechanism; no speech anchors needed.
    board = Storyboard.model_validate(read_yaml(Path(
        'tests/fixtures/golden-project-v2/revisions/001/storyboard/storyboard.yaml')))
    start, scenes = 0, []
    for scene, frames in zip(board.scenes, [600, 510, 510, 510, 510, 180, 180], strict=True):
        if scene.anatomy:
            subjects = ['artery_cross_section', 'heart', 'liver_organ', 'liver_lobule']
            scene = scene.model_copy(update={'anatomy': scene.anatomy.model_copy(update={
                'subject': subjects[len(scenes) - 1]})})
        scenes.append(scene.model_copy(update={'start_frame': start, 'duration_frames': frames,
                                              'script_line_id': None, 'chapter_id': 'CH01'}))
        start += frames
    return board.model_copy(update={'scenes': tuple(scenes), 'format_profile': 'youtube_long'})


@pytest.mark.parametrize('failure,match', [
    ('budget', 'chart_crop=.*16-24%'),
    ('beat', 'S02.*outside timed scene'),
    ('entrance', 'S02.*first 15%'),
    ('clip', 'CL02.*1980.*4860'),
])
def test_precheck_catches_duration_failures(tmp_path, failure, match):
    from healthvideo.workflows.draft import validate_estimated_layout

    board = fixture_board()
    scenes = list(board.scenes)
    plan = None
    if failure == 'budget':
        scenes[1] = scenes[1].model_copy(update={'visual': 'chart'})
    elif failure == 'beat':
        scenes[1] = scenes[1].model_copy(update={'beats': (SceneBeat(at=30),)})
    elif failure == 'entrance':
        scenes[1] = scenes[1].model_copy(update={'beats': (), 'entrances': (TextEntrance(text='early', start_frame=1),)})
    else:
        plan = ClipPlan(clips=(ClipSpec(id='CL02', title='short', first_scene_id='S01', last_scene_id='S02'),))
    plan = plan or ClipPlan(clips=(ClipSpec(id='CL01', title='ok', first_scene_id='S01', last_scene_id='OUTRO'),))
    board = board.model_copy(update={'scenes': tuple(scenes)})
    with pytest.raises(ValueError, match=match):
        validate_estimated_layout(tmp_path, Script(title='Fixture'), board, clip_plan=plan)


def test_valid_precheck_and_eight_percent_longer(tmp_path):
    from healthvideo.workflows.draft import validate_estimated_layout

    board = fixture_board()
    plan = ClipPlan(clips=(ClipSpec(id='CL01', title='ok', first_scene_id='S01', last_scene_id='OUTRO'),))
    from healthvideo.domain.clip_plan import validate_clip_plan
    from healthvideo.domain.visual_budget import validate_visual_budget
    from healthvideo.render.timing import (
        FALLBACK_CHARACTERS_PER_SECOND,
        estimate_line_ms,
    )
    from healthvideo.render.word_timing import entrance_timing_qa

    script = Script(title='Fixture', lines=[ScriptLine(
        id=scene.id, text='x' * round((scene.duration_frames - 9) / 30 * FALLBACK_CHARACTERS_PER_SECOND),
    ) for scene in board.scenes])
    board = board.model_copy(update={'scenes': tuple(
        s.model_copy(update={'script_line_id': s.id}) for s in board.scenes)})
    claims = {key: EvidenceClaim(id=key, text_public='Synthetic', text_technical='Synthetic',
                                 type='evidence', sources=['R01']) for key in ('C01', 'C02')}
    validate_estimated_layout(tmp_path, script, board, clip_plan=plan, claims=claims)
    actual_ms = {key: round(value * 1.08) for key, value in estimate_line_ms(script, tmp_path).items()}
    timed, _ = retime_storyboard(board, actual_ms)
    validate_visual_budget(timed)
    validate_clip_plan(plan, timed, claims)
    for scene in timed.scenes:
        entrance_timing_qa(resolve_scene_beats(scene, clamp_outside=True))


def test_clamp_keeps_beats_distinct_and_approved_scene_immutable():
    scene = Scene(id='S', narration='word', on_screen_text='word', start_frame=0, duration_frames=90, visual='whiteboard').model_copy(
        update={'beats': (SceneBeat(at=1), SceneBeat(at=3), SceneBeat(at=4))})
    result = resolve_scene_beats(scene, clamp_outside=True)
    assert [b.start_frame for b in result.beats] == [30, 88, 89]
    assert [b.at for b in scene.beats] == [1, 3, 4]
    assert resolve_scene_beats(result) == result


def test_character_estimate_uses_only_matching_verified_voice_cache(tmp_path):
    from healthvideo.render.timing import estimate_line_ms
    from healthvideo.storage.files import (
        canonical_json_hash,
        sha256_file,
        write_yaml_atomic,
    )

    profile = {'provider': 'vibi_minimax', 'model_id': 'm', 'voice_id': 'v', 'settings': {'speed': 1.0}}
    cache = tmp_path / 'cache/tts'
    cache.mkdir(parents=True)
    for voice, text, seconds in [('v', 'a' * 20, 2), ('other', 'a' * 200, 2)]:
        provider = {**profile, 'voice_id': voice}
        request = {'text': text, 'language': 'vi', 'speed': 1.0, 'delivery_beats': []}
        payload = {'request': request, 'provider': provider}
        path = cache / f'{canonical_json_hash(payload)}.wav'
        with wave.open(str(path), 'wb') as out:
            out.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\1\0' * seconds * 1000)
        write_yaml_atomic(path.with_suffix('.json'), {**payload, 'sha256': sha256_file(path)})
    script = Script(title='Fixture', lines=[ScriptLine(id='L', text='b' * 30)])
    assert estimate_line_ms(script, tmp_path, voice_profile=profile) == {'L': 3000}


def test_fallback_character_rate_and_pronunciation(tmp_path, monkeypatch):
    from healthvideo.domain.pronunciation import (
        PronunciationEntry,
        PronunciationLexicon,
    )
    from healthvideo.render.timing import estimate_line_ms
    from healthvideo.tts import pronunciation

    lexicon = PronunciationLexicon(
        schema_version='1.0', language='vi', version='test',
        entries=(PronunciationEntry(written='term', spoken='x' * 20),),
    )
    monkeypatch.setattr(pronunciation, 'load_pronunciation_lexicon', lambda _: lexicon)
    script = Script(title='Synthetic calibration', lines=[
        ScriptLine(id='POOLED', text='x' * 9254),
        ScriptLine(id='PRONUNCIATION', text='term', delivery='[pause]term'),
    ])
    # Pooled constant: 9254 / 564.55; replacement has 20 spoken characters.
    assert estimate_line_ms(script, tmp_path, voice_profile={'provider': 'vibi_minimax'}) == {
        'POOLED': 564550, 'PRONUNCIATION': 1221,
    }


@pytest.mark.parametrize('failure', ['budget', 'beat', 'entrance', 'clip'])
def test_submission_keeps_state_and_review_cycle_on_layout_failure(tmp_path, failure):
    from healthvideo.storage.files import write_yaml_atomic
    from healthvideo.workflows.draft import submit_medical_review
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path)
    revision = project / 'revisions/001'
    board = fixture_board()
    scenes = list(board.scenes)
    if failure == 'budget':
        scenes[0] = scenes[0].model_copy(update={'duration_frames': 1200})
        for index in range(1, len(scenes)):
            scenes[index] = scenes[index].model_copy(update={'start_frame': scenes[index].start_frame + 600})
    elif failure == 'beat':
        scenes[1] = scenes[1].model_copy(update={'beats': (SceneBeat(at=30),)})
    elif failure == 'entrance':
        scenes[1] = scenes[1].model_copy(update={'beats': (), 'entrances': (TextEntrance(text='early', start_frame=1),)})
    board = board.model_copy(update={'scenes': tuple(scenes)})
    plan = ClipPlan(clips=(ClipSpec(id='CL02', title='fixture', first_scene_id='S01',
                                   last_scene_id='S02' if failure == 'clip' else 'OUTRO'),))
    write_yaml_atomic(revision / 'storyboard/storyboard.yaml', board.model_dump(mode='json'))
    write_yaml_atomic(revision / 'script/script.yaml', Script(title='Fixture').model_dump(mode='json'))
    write_yaml_atomic(revision / 'script/clip-plan.yaml', plan.model_dump(mode='json'))
    before = {path: path.read_bytes() for path in project.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='Estimated layout precheck failed'):
        submit_medical_review(project)
    after = {path: path.read_bytes() for path in project.rglob('*') if path.is_file()}
    assert before == after


@pytest.mark.parametrize('times,frames', [([1, 1], 60), ([2, 1], 60), ([1, 2, 3], 2)])
def test_clamping_does_not_hide_bad_order_or_impossible_density(times, frames):
    scene = Scene(id='S', narration='word', visual='whiteboard', on_screen_text='word',
                  start_frame=0, duration_frames=frames).model_copy(update={
                      'beats': tuple(SceneBeat(at=time) for time in times)})
    with pytest.raises(ValueError):
        resolve_scene_beats(scene, clamp_outside=True)
