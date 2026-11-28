import json

import pytest

from healthvideo.domain.script import Script
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts import pronunciation as pronunciation_module
from healthvideo.tts.pronunciation import (
    apply_pronunciation,
    load_pronunciation_lexicon,
)
from healthvideo.workflows import doctor_questions, voice_prep


def _profile(root, entries=()):
    path = root / 'profiles/pronunciation.vi.yaml'
    write_yaml_atomic(path, {'schema_version': '1.0', 'language': 'vi', 'version': '3', 'entries': list(entries)})
    return path


def _script(text):
    return Script.model_validate({'schema_version': '1.0', 'title': 'Gan', 'lines': [{'id': 'L01', 'text': text}]})


def test_unknown_terms_wait_as_one_question_and_doctor_answer_confirms(tmp_path):
    path = _profile(tmp_path)
    script = _script('Xét nghiệm HBsAg và MASLD.')
    lexicon = load_pronunciation_lexicon(path)
    assert not voice_prep.require_doctor_pronunciations(tmp_path, 'gan', script, lexicon)
    q = doctor_questions.open_question(tmp_path, 'gan')
    assert {t['written'] for t in q['pronunciation_terms']} == {'HBsAg', 'MASLD'}
    assert all(len(t['options']) in (2, 3) and t['context'] for t in q['pronunciation_terms'])
    assert not voice_prep.require_doctor_pronunciations(tmp_path, 'gan', script, lexicon)
    assert doctor_questions.open_question(tmp_path, 'gan')['id'] == q['id']
    doctor_questions.answer(tmp_path, 'gan', q['id'], text=json.dumps({'HBsAg': 'hát bê ét a giê', 'MASLD': 'mát eo đi'}))
    updated = load_pronunciation_lexicon(path)
    assert all(not e.needs_doctor_review and e.note.startswith('Bác sĩ chọn ') for e in updated.entries)
    assert voice_prep.require_doctor_pronunciations(tmp_path, 'gan', script, updated)
    assert apply_pronunciation(script.lines[0].text, updated) == 'Xét nghiệm hát bê ét a giê và mát eo đi.'
    assert doctor_questions.open_question(tmp_path, 'gan') is None
    assert len(doctor_questions.history(tmp_path, 'gan')) == 1


@pytest.mark.parametrize('text', ['không phải JSON', '{}', '{"HBsAg": ""}', '{"HBsAg": 12}', '{"HBsAg": "abc", "extra": "x"}'])
def test_invalid_pronunciation_answer_keeps_question_and_profile(tmp_path, text):
    path = _profile(tmp_path)
    before = path.read_bytes()
    voice_prep.require_doctor_pronunciations(tmp_path, 'gan', _script('HBsAg.'), load_pronunciation_lexicon(path))
    q = doctor_questions.open_question(tmp_path, 'gan')
    with pytest.raises(ValueError, match='cách đọc'):
        doctor_questions.answer(tmp_path, 'gan', q['id'], text=text)
    assert path.read_bytes() == before
    assert doctor_questions.open_question(tmp_path, 'gan')['id'] == q['id']
    assert not doctor_questions.history(tmp_path, 'gan')


def test_confirm_pending_preserves_yaml_comments_order_and_doctor_overrides_agent(tmp_path):
    path = _profile(tmp_path)
    original = "# Từ điển\nschema_version: '1.0'\nlanguage: vi\nversion: '3'\nentries:\n  - written: gout # giữ lại\n    spoken: gút\n  - written: HBsAg\n    spoken: cũ\n    needs_doctor_review: true # chờ\n    note: đề xuất\n"
    path.write_text(original, encoding='utf-8')
    voice_prep.require_doctor_pronunciations(tmp_path, 'gan', _script('HBsAg.'), load_pronunciation_lexicon(path))
    q = doctor_questions.open_question(tmp_path, 'gan')
    doctor_questions.answer(tmp_path, 'gan', q['id'], text=json.dumps({'HBsAg': 'bác sĩ đọc'}))
    assert path.read_text(encoding='utf-8').startswith(original.split('  - written: HBsAg')[0])
    assert 'false # chờ' in path.read_text(encoding='utf-8')
    assert [e['written'] for e in read_yaml(path)['entries']] == ['gout', 'HBsAg']
    revision = tmp_path / 'revision'
    write_yaml_atomic(revision / 'storyboard/storyboard.yaml', {'quality_profile': 'r5_v1'})
    write_yaml_atomic(revision / 'script/voice-prep.yaml', {'pronunciations': [{'written': 'HBsAg', 'spoken': 'agent sai'}]})
    merged = voice_prep.load_voice_prep_lexicon(revision, load_pronunciation_lexicon(path))
    assert apply_pronunciation('HBsAg', merged) == 'bác sĩ đọc'


def test_plain_vietnamese_does_not_ask(tmp_path):
    path = _profile(tmp_path)
    assert voice_prep.require_doctor_pronunciations(tmp_path, 'gan', _script('Uống đủ nước để gan khỏe.'), load_pronunciation_lexicon(path))
    assert doctor_questions.open_question(tmp_path, 'gan') is None


def test_narration_scan_ignores_metadata_and_approved_syllable_forms(tmp_path):
    path = _profile(tmp_path, [{'written': 'HBsAg', 'spoken': 'hát-bê-ét-a-giê'}])
    data = {'title': 'IllustrativeVisualization Synthetic whiteboard', 'lines': [{
        'id': 'Synthetic', 'text': 'HBsAg chỉ cho biết một chỉ số. Chia sẻ chung để ghi nhớ.',
        'delivery': {'intent': 'ForeignMetadataOnly'},
    }]}
    result = voice_prep.narration_pronunciation_candidates(Script.model_validate(data), load_pronunciation_lexicon(path))
    assert result['terms'] == []


def test_legacy_submit_check_does_not_load_lexicon_or_ask(tmp_path, monkeypatch):
    from tests.helpers import create_v2_project_fixture
    project = create_v2_project_fixture(tmp_path)
    monkeypatch.setattr(pronunciation_module, 'PRONUNCIATION_PROFILE_PATH', tmp_path / 'missing.yaml')
    assert voice_prep.check_before_medical(project)
    assert not list(tmp_path.rglob('doctor-question.yaml'))


def test_pending_update_and_new_entry_preserve_yaml_in_same_answer(tmp_path):
    from healthvideo.tts.pronunciation import save_doctor_pronunciations
    path = _profile(tmp_path, [{'written': 'HBsAg', 'spoken': 'cũ', 'needs_doctor_review': True}])
    save_doctor_pronunciations(path, {'HBsAg': 'hát bê', 'MASLD': 'mát'}, '2026-11-25')
    assert [(e.written, e.spoken) for e in load_pronunciation_lexicon(path).entries] == [('HBsAg', 'hát bê'), ('MASLD', 'mát')]


def test_produce_blocks_before_any_tts_without_question_or_lexicon_write(tmp_path, monkeypatch):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows.gate_review import (
        approve_gate,
    )
    from healthvideo.workflows.produce import produce_project
    from tests.helpers import submit_medical_review_fixture
    from tests.workflows.test_produce import V2_REVIEWED_AT, _r5_project
    project = _r5_project(tmp_path, state=WorkflowState.DRAFT_READY)
    revision = project / 'revisions/001'
    path = _profile(tmp_path)
    monkeypatch.setattr(pronunciation_module, 'PRONUNCIATION_PROFILE_PATH', path)
    data = read_yaml(revision / 'script/script.yaml')
    data['lines'][1]['text'] += ' HBsAg.'
    write_yaml_atomic(revision / 'script/script.yaml', data)
    board = read_yaml(revision / 'storyboard/storyboard.yaml')
    for scene in board['scenes']:
        if scene['script_line_id'] == data['lines'][1]['id']:
            scene['narration'] = data['lines'][1]['text']
    write_yaml_atomic(revision / 'storyboard/storyboard.yaml', board)
    submit_medical_review_fixture(project)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)
    before = (project / 'project.yaml').read_bytes()

    class CaptureTTS:
        provider_name = 'mock'
        def synthesize(self, request, output):
            raise AssertionError('Không được gọi TTS khi chờ bác sĩ')

    with pytest.raises(ValueError, match='Chưa có cách đọc'):
        produce_project(project, CaptureTTS(), lambda _: pytest.fail('render khi chờ'), music=False)
    assert (project / 'project.yaml').read_bytes() == before
    slug = read_yaml(project / 'project.yaml')['slug']
    assert doctor_questions.open_question(tmp_path, slug) is None


def test_submit_waits_then_approval_hash_includes_doctor_choice(tmp_path, monkeypatch):
    from healthvideo.commands.operator import submit_medical
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows.gate_review import approve_gate
    from tests.helpers import submit_medical_review_fixture
    from tests.workflows.test_produce import V2_REVIEWED_AT, _r5_project
    project = _r5_project(tmp_path, state=WorkflowState.DRAFT_READY)
    revision = project / 'revisions/001'
    path = _profile(tmp_path)
    monkeypatch.setattr(pronunciation_module, 'PRONUNCIATION_PROFILE_PATH', path)
    data = read_yaml(revision / 'script/script.yaml')
    data['lines'][1]['text'] += ' HBsAg.'
    write_yaml_atomic(revision / 'script/script.yaml', data)
    board = read_yaml(revision / 'storyboard/storyboard.yaml')
    for scene in board['scenes']:
        if scene['script_line_id'] == data['lines'][1]['id']:
            scene['narration'] = data['lines'][1]['text']
    write_yaml_atomic(revision / 'storyboard/storyboard.yaml', board)
    before = (project / 'project.yaml').read_bytes()
    submit_medical(project)
    assert (project / 'project.yaml').read_bytes() == before
    slug = read_yaml(project / 'project.yaml')['slug']
    q = doctor_questions.open_question(tmp_path, slug)
    choices = {t['written']: t['written'] for t in q['pronunciation_terms']}
    choices['HBsAg'] = 'hát bê ét a giê'
    doctor_questions.answer(tmp_path, slug, q['id'], text=json.dumps(choices))
    assert voice_prep.check_before_medical(project)
    # Prepare the independent script critic fixture, then use the real CLI submission.
    submit_medical_review_fixture(project)
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = 'draft_ready'
    write_yaml_atomic(project / 'project.yaml', manifest)
    submit_medical(project)
    assert read_yaml(project / 'project.yaml')['state'] == 'awaiting_medical_review'
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)
    from healthvideo.workflows.gate_review import MEDICAL_APPROVAL_ARTIFACT
    approval = read_yaml(revision / MEDICAL_APPROVAL_ARTIFACT)
    used = pronunciation_module.used_pronunciation_hash(path, revision / 'script/script.yaml')
    assert approval['artifact_hashes']['profiles/pronunciation.vi.yaml'] == used
    from healthvideo.domain.project_v2 import ProjectManifestV2
    from healthvideo.workflows.review import approval_is_stale

    def stale():
        manifest = ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml'))
        return approval_is_stale(project, manifest, GateKind.MEDICAL)

    # The shared lexicon gains a term another project chose: this approval stays current.
    pronunciation_module.save_doctor_pronunciations(path, {'ESGE': 'e ét gờ e'}, '2026-11-28')
    assert not stale()
    # A term this script speaks changes: the medical gate must reopen.
    pronunciation_module.save_doctor_pronunciations(path, {'HBsAg': 'hát bê ét a'}, '2026-11-28')
    assert stale()
