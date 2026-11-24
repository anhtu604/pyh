import json

import pytest

from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import produce, voice_preview
from tests.helpers import create_v2_project_fixture


class Local(SilentTTS):
    provider_name = 'voicestudio'


def test_preview_selected_lines_measures_audio_without_changing_gate_inputs(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path, state='awaiting_medical_review')
    rev = project / 'revisions/001'
    before = {p: p.read_bytes() for p in project.rglob('*') if p.is_file()}
    from healthvideo.workflows.gate_review import (
        hash_reviewed_artifacts,
        medical_reviewed_paths,
    )

    gate_hashes = hash_reviewed_artifacts(medical_reviewed_paths(rev))
    script = read_yaml(rev / 'script/script.yaml')
    line = script['lines'][0]
    calls = []

    class Spy(Local):
        def synthesize(self, request, output):
            calls.append(request.text)
            return super().synthesize(request, output)

    monkeypatch.setattr(voice_preview, '_preview_provider', lambda root: Spy())
    result = voice_preview.voice_preview(project, [line['id']])
    assert len(calls) == 1
    assert result['provider'] == 'voicestudio'
    assert result['duration_ms'] > 0 and len(result['lines']) == 1
    assert result['lines'][0]['url'].startswith('/media/')
    voice_preview.voice_preview(project, [line['id']])
    assert len(calls) == 1
    assert all(p.read_bytes() == contents for p, contents in before.items())
    assert hash_reviewed_artifacts(medical_reviewed_paths(rev)) == gate_hashes
    with pytest.raises(ValueError, match='dòng'):
        voice_preview.voice_preview(project, ['missing'])


def test_produce_rejects_local_provider_even_during_dry_run(tmp_path):
    project = create_v2_project_fixture(tmp_path, state='awaiting_medical_review')
    with pytest.raises(ValueError, match='Vibi'):
        produce.produce_project(project, Local(), lambda _: pytest.fail('render'), dry_run=True)


def test_cache_separates_backends_and_rejects_foreign_receipt(tmp_path):
    class Paid(SilentTTS):
        provider_name = 'vibi_minimax'

    request = TTSRequest(text='Một câu nghe thử.', language='vi')
    assert produce.tts_cache_key(Paid(), request) != produce.tts_cache_key(Local(), request)
    cache = tmp_path / 'cache'
    output = tmp_path / 'out.wav'
    produce._synthesize_cached_line(Paid(), request, output, cache_dir=cache)
    receipt = next(cache.glob('*.json'))
    data = json.loads(receipt.read_text())
    data['provider'] = {'provider': 'voicestudio'}
    write_yaml_atomic(receipt, data)
    with pytest.raises(ValueError, match='Vibi'):
        produce._synthesize_cached_line(Paid(), request, output, cache_dir=cache)


def test_vibi_rejects_wrong_backend_result(tmp_path):
    class Impostor(Local):
        provider_name = 'vibi_minimax'

        def synthesize(self, request, output):
            return super().synthesize(request, output).model_copy(update={'provider': 'voicestudio'})

    with pytest.raises(ValueError, match='Vibi'):
        produce._synthesize_cached_line(Impostor(), TTSRequest(text='Thử.', language='vi'),
                                        tmp_path / 'out.wav', cache_dir=tmp_path / 'cache')


def test_old_voice_profile_keeps_vibi_identity():
    from healthvideo.tts.vibi import VibiTTS, VoiceProfile
    from healthvideo.tts.voicestudio import VoiceStudioSettings

    old = VoiceProfile(voice_id='old-voice')
    assert old.voicestudio is None
    local = old.model_copy(update={'voicestudio': VoiceStudioSettings(
        ref_audio='ref.wav', ref_text='Mẫu.',
    )})
    assert VibiTTS(old, api_key='fake').cache_identity() == VibiTTS(local, api_key='fake').cache_identity()


def test_preview_pronunciation_and_all_lines(tmp_path, monkeypatch):
    from healthvideo.tts import pronunciation

    project = create_v2_project_fixture(tmp_path, state='awaiting_medical_review')
    lexicon = tmp_path / 'pronunciation.yaml'
    write_yaml_atomic(lexicon, {'schema_version': '1.0', 'language': 'vi', 'version': 'test',
                              'entries': [{'written': 'Synthetic', 'spoken': 'sin-thét-tíc'}]})
    monkeypatch.setattr(pronunciation, 'PRONUNCIATION_PROFILE_PATH', lexicon)
    requests = []

    class Spy(Local):
        def synthesize(self, request, output):
            requests.append(request.text)
            return super().synthesize(request, output)

    monkeypatch.setattr(voice_preview, '_preview_provider', lambda root: Spy())
    result = voice_preview.voice_preview(project)
    assert len(result['lines']) == len(read_yaml(project / 'revisions/001/script/script.yaml')['lines'])
    assert requests and all('Synthetic' not in text for text in requests)
    assert any('sin-thét-tíc' in text for text in requests)


def test_draft_timing_old_configuration_does_not_call_server(tmp_path, monkeypatch):
    from healthvideo.domain.script import Script

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    script = Script.model_validate(read_yaml(project / 'revisions/001/script/script.yaml'))
    write_yaml_atomic(tmp_path / 'profiles/voice.yaml', {'voice_id': 'old-voice'})
    monkeypatch.setattr(voice_preview, '_preview_provider', lambda _: pytest.fail('local server'))
    assert voice_preview.draft_line_ms(project, script) is None


def test_draft_timing_uses_supplied_script(tmp_path, monkeypatch):
    from healthvideo.domain.script import Script

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    script = Script.model_validate(read_yaml(project / 'revisions/001/script/script.yaml'))
    voice = {'voice_id': 'vibi', 'voicestudio': {'ref_audio': 'ref.wav', 'ref_text': 'Mẫu.'}}
    write_yaml_atomic(tmp_path / 'profiles/voice.yaml', voice)
    monkeypatch.setattr(voice_preview, '_preview_provider', lambda _: Local())
    result = voice_preview.draft_line_ms(project, script)
    assert result and set(result) == {line.id for line in script.lines}
    assert all(ms > 0 for ms in result.values())


def test_r5_precheck_uses_measured_local_duration(tmp_path, monkeypatch):
    from healthvideo.domain.script import Script
    from healthvideo.render import timing
    from healthvideo.workflows.draft import validate_estimated_layout
    from tests.render.test_quality import board, shot

    b = board([shot(0, 90, kind='story')], 90)
    script = Script(title='Synthetic', lines=[{'id': 'L1', 'text': 'w0 Question1? Question2?'}])
    monkeypatch.setattr(voice_preview, 'draft_line_ms', lambda *args: {'L1': 2700})
    monkeypatch.setattr(timing, 'estimate_line_ms', lambda *args: pytest.fail('character estimate'))
    before = b.model_dump_json(), script.model_dump_json()
    runtime = validate_estimated_layout(tmp_path, script, b)
    assert runtime.scenes[0].resolved_shots[0].end_frame == 90
    assert before == (b.model_dump_json(), script.model_dump_json())


def test_draft_line_ms_falls_back_when_voicestudio_down(monkeypatch, tmp_path):
    from healthvideo.tts.voicestudio import VoiceStudioError
    from healthvideo.workflows import voice_preview

    profile = tmp_path / 'profiles/voice.yaml'
    profile.parent.mkdir(parents=True)
    profile.write_text('x', encoding='utf-8')
    monkeypatch.setattr(voice_preview, '_telemetry_root', lambda project: tmp_path)
    monkeypatch.setattr(voice_preview, 'load_voice_profile',
                        lambda path: type('P', (), {'voicestudio': object()})())

    def down(*args, **kwargs):
        raise VoiceStudioError('Voice Studio chưa chạy.')

    monkeypatch.setattr(voice_preview, '_voice_preview', down)
    assert voice_preview.draft_line_ms(tmp_path, object()) is None
