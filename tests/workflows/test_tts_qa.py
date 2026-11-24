import json
from collections import Counter

import pytest

import healthvideo.tts.pronunciation as pronunciation_module
import healthvideo.workflows.produce as production
from healthvideo.audio.align import _expand_asr_words, map_words
from healthvideo.audio.tts_qa import line_qa
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import doctor_questions
from healthvideo.workflows.gate_review import approve_gate
from tests.helpers import submit_medical_review_fixture
from tests.workflows.test_produce import (
    V2_REVIEWED_AT,
    _r5_project,
    _write_synthetic_output,
)


def _project(tmp_path, monkeypatch):
    project = _r5_project(tmp_path, state=WorkflowState.DRAFT_READY, monkeypatch=monkeypatch)
    profile = pronunciation_module.PRONUNCIATION_PROFILE_PATH
    data = read_yaml(profile)
    data['entries'] = [e for e in data['entries'] if e['written'] != 'viêm gan B']
    data['entries'].append({'written': 'viêm gan B', 'spoken': 'viêm gan bê', 'needs_doctor_review': False})
    write_yaml_atomic(profile, data)
    script_path = project / 'revisions/001/script/script.yaml'
    data = read_yaml(script_path)
    data['lines'][1]['text'] += ' viêm gan B.'
    write_yaml_atomic(script_path, data)
    board_path = project / 'revisions/001/storyboard/storyboard.yaml'
    board = read_yaml(board_path)
    board['scenes'][1]['narration'] = data['lines'][1]['text']
    write_yaml_atomic(board_path, board)
    submit_medical_review_fixture(project)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)
    return project


@pytest.mark.parametrize('correct_retry', [False, True])
def test_pre_render_retry_question_and_exact_wav_acceptance(tmp_path, monkeypatch, correct_retry):
    project = _project(tmp_path, monkeypatch)
    calls = Counter()
    synthesis = []

    class MockVibi(SilentTTS):
        def synthesize(self, request, output):
            synthesis.append(request.text)
            return super().synthesize(request, output)

    def aligner(wavs, scripts, *, out_dir, asr_lexicon=None):
        result = {}
        out_dir.mkdir(parents=True, exist_ok=True)
        for key, text in scripts.items():
            calls[(key, str(out_dir.parent))] += 1
            heard = text
            if 'viêm gan bê' in text and (not correct_retry or calls[(key, str(out_dir.parent))] == 1):
                heard = heard.replace('viêm gan bê', 'viêm gan bơ')
            from healthvideo.tts.audio_checks import inspect_wav
            duration = inspect_wav(wavs[key]).duration_ms / 1000
            raw = [{'word': w, 'start': i * duration / len(heard.split()),
                    'end': (i + 1) * duration / len(heard.split()), 'prob': .99}
                   for i, w in enumerate(heard.split())]
            result[key] = map_words(text, raw, duration=duration)
            (out_dir / f'{key}.json').write_text(json.dumps(result[key]), encoding='utf8')
        return result

    monkeypatch.setattr(production, 'align_lines', aligner)
    renders = []

    def runner(argv):
        renders.append(argv)
        _write_synthetic_output(argv)
        return 0

    if correct_retry:
        production.produce_project(project, MockVibi(), runner, music=False)
        assert renders
        assert doctor_questions.open_question(tmp_path, read_yaml(project / 'project.yaml')['slug']) is None
    else:
        with pytest.raises(ValueError, match='blocked before render'):
            production.produce_project(project, MockVibi(), runner, music=False)
        assert not renders
        question = doctor_questions.open_question(tmp_path, read_yaml(project / 'project.yaml')['slug'])
        assert len(question['tts_lines']) == 1
        audio = question['tts_lines'][0]
        assert 'bơ' in str(audio['flags'])
        before = len(synthesis)
        with pytest.raises(ValueError, match='blocked before render'):
            production.produce_project(project, MockVibi(), runner, music=False)
        assert len(synthesis) == before
        assert doctor_questions.open_question(tmp_path, read_yaml(project / 'project.yaml')['slug'])['id'] == question['id']
        doctor_questions.answer(tmp_path, read_yaml(project / 'project.yaml')['slug'], question['id'], 'retry')
        with pytest.raises(ValueError, match='blocked before render'):
            production.produce_project(project, MockVibi(), runner, music=False)
        retried = doctor_questions.open_question(tmp_path, read_yaml(project / 'project.yaml')['slug'])
        assert retried['id'] != question['id']
        assert len(synthesis) == before + 2
        question = retried
        before = len(synthesis)
        doctor_questions.answer(tmp_path, read_yaml(project / 'project.yaml')['slug'], question['id'], 'accept')
        production.produce_project(project, MockVibi(), runner, music=False)
        assert renders and len(synthesis) == before
        report = json.loads((project / 'revisions/001/renders/pronunciation-qa.json').read_text(encoding='utf8'))
        assert not report['blocked']
    assert sum('viêm gan bê' in text for text in synthesis) == (2 if correct_retry else 4)


@pytest.mark.parametrize(('heard', 'written', 'spoken'), [
    ('HBS-AG', 'HBsAg', 'hát bê ét a dê'),
    ('20%', '20%', 'hai mươi phần trăm'),
    ('2', '2', 'hai'),
])
def test_itn_equivalence_does_not_block(heard, written, spoken):
    raw = [{'word': heard, 'start': 0, 'end': 1, 'prob': .9}]
    expanded = _expand_asr_words(raw, {written: spoken})
    result = map_words(spoken, expanded, duration=1)
    assert not line_qa({'L1': result}, terms=[spoken])['blocked']


def test_change_pronunciation_invalidates_medical_approval(tmp_path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    q = doctor_questions.ask(tmp_path, read_yaml(project / 'project.yaml')['slug'], station='09', kind='tts_qa',
                             question='Nghe lại', options=[{'id': 'accept', 'label': 'Đúng'},
                                                         {'id': 'change', 'label': 'Đổi'}])
    doctor_questions.answer(tmp_path, read_yaml(project / 'project.yaml')['slug'], q['id'], 'change',
                            json.dumps({'viêm gan B': 'viêm gan bê mới'}))
    with pytest.raises(ValueError, match='current medical approval'):
        production.produce_project(project, SilentTTS(), lambda _: pytest.fail('render'), music=False)


@pytest.mark.parametrize('option', ['accept', 'retry'])
def test_doctor_answer_releases_only_tts_validation_hold(tmp_path, option):
    q = doctor_questions.ask(tmp_path, 'gan', station='09', kind='tts_qa', question='Nghe lại',
                             options=[{'id': 'accept', 'label': 'Đúng'}, {'id': 'retry', 'label': 'Đọc lại'}])
    logs = doctor_questions.question_path(tmp_path, 'gan').parent
    hold = logs / 'production-retry.yaml'
    write_yaml_atomic(hold, {'reason': 'Whisper TTS QA blocked before render; chờ bác sĩ nghe lại.'})
    (logs / 'blocked.txt').write_text('bước produce lỗi: Whisper TTS QA blocked before render', encoding='utf8')
    doctor_questions.answer(tmp_path, 'gan', q['id'], option)
    assert not hold.exists()
    assert not (logs / 'blocked.txt').exists()
