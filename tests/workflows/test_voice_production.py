"""Production contracts for expressive speech, canonical captions and paid cache."""
import json

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows import produce
from healthvideo.workflows.gate_review import approve_gate
from tests.helpers import create_v2_project_fixture
from tests.workflows.test_produce import V2_REVIEWED_AT, _write_synthetic_output


def voice_project(tmp_path, *, delivery=False):
    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision = project / 'revisions/001'
    script = read_yaml(revision / 'script/script.yaml')
    if delivery:
        script['lines'][0]['delivery'] = '[sarcastic] ' + script['lines'][0]['text']
        write_yaml_atomic(revision / 'script/script.yaml', script)
    approve_gate(project, GateKind.MEDICAL, reviewer='doctor', now=V2_REVIEWED_AT)
    return project, revision, script


@pytest.mark.parametrize('provider', ['elevenlabs', 'vibi_minimax'])
def test_line_cache_survives_failed_render_and_changes_with_settings(tmp_path, provider):
    project, _, _ = voice_project(tmp_path)
    calls = []

    class Paid(SilentTTS):
        provider_name = provider
        settings = 'settings-1'

        def cache_identity(self):
            return {'provider': self.provider_name, 'model_id': 'eleven_v3',
                    'voice_id': 'test-voice', 'runtime_id': self.settings}

        def synthesize(self, request, output):
            calls.append(request.text)
            return super().synthesize(request, output)

    tts = Paid()
    with pytest.raises(RuntimeError, match='Remotion'):
        produce.produce_project(project, tts, lambda _: 1)
    count = len(calls)
    assert count > 0
    with pytest.raises(RuntimeError, match='Remotion'):
        produce.produce_project(project, tts, lambda _: 1)
    assert len(calls) == count
    tts.settings = 'settings-2'
    produce.produce_project(project, tts, lambda argv: (_write_synthetic_output(argv) or 0))
    assert len(calls) == 2 * count


@pytest.mark.parametrize('provider', ['elevenlabs', 'command'])
def test_pronunciation_applied_for_all_providers(tmp_path, monkeypatch, provider):
    from healthvideo.tts import pronunciation

    profile = tmp_path / 'pronunciation.yaml'
    write_yaml_atomic(profile, {'schema_version': '1.0', 'language': 'vi', 'version': 'test',
                               'entries': [{'written': 'Synthetic', 'spoken': 'sin-thét-tíc'}]})
    monkeypatch.setattr(pronunciation, 'PRONUNCIATION_PROFILE_PATH', profile)
    project, revision, script = voice_project(tmp_path)
    requests = []
    compared = []

    class Spy(SilentTTS):
        provider_name = provider

        def synthesize(self, request, output):
            requests.append(request.text)
            return super().synthesize(request, output)

    def align(wavs, scripts, *, out_dir):
        compared.append(scripts)
        return {}

    monkeypatch.setattr(produce, 'align_lines', align)
    produce.produce_project(project, Spy(), lambda argv: (_write_synthetic_output(argv) or 0))
    assert all('Synthetic' not in text for text in requests)
    assert any('sin-thét-tíc' in text for text in requests)
    assert any('sin thét tíc' in text for mapping in compared for text in mapping.values())
    rendered = json.loads((revision / 'renders/render-input.json').read_text(encoding='utf-8'))
    assert rendered['scenes'][0]['narration'] == script['lines'][0]['text']


def test_captions_use_text_not_delivery(tmp_path):
    project, revision, script = voice_project(tmp_path, delivery=True)
    requests = []

    class Expressive(SilentTTS):
        provider_name = 'elevenlabs'

        def synthesize(self, request: TTSRequest, output):
            requests.append(request.text)
            return super().synthesize(request, output)

    produce.produce_project(project, Expressive(), lambda argv: (_write_synthetic_output(argv) or 0))
    assert requests[0].startswith('[sarcastic]')
    rendered = (revision / 'renders/render-input.json').read_text(encoding='utf-8')
    assert '[sarcastic]' not in rendered
    assert json.loads(rendered)['scenes'][0]['narration'] == script['lines'][0]['text']


def test_blocking_pronunciation_renders_but_fails_video_qa(tmp_path, monkeypatch):
    project, revision, _ = voice_project(tmp_path)
    monkeypatch.setattr(produce, 'pronunciation_qa', lambda *args, **kwargs: {
        'blocked': True, 'flags': [{'severity': 'block'}], 'lines': [], 'status': 'aligned',
    })
    output = produce.produce_project(
        project, SilentTTS(), lambda argv: (_write_synthetic_output(argv) or 0),
    )
    assert output.is_file()
    qa = read_yaml(revision / 'reviews/video-qa.json')
    assert qa['status'] == 'failed'
    assert qa['pronunciation']['passed'] is False
    assert qa['pronunciation']['blocking_count'] == 1
    with pytest.raises(ValueError, match='blocking pronunciation'):
        approve_gate(project, GateKind.VIDEO, reviewer='doctor', now=V2_REVIEWED_AT)
    # A flagged render remains inspectable and idempotent while awaiting listening.
    assert produce.produce_project(
        project, SilentTTS(), lambda _: pytest.fail('render on retry'),
    ) == output


@pytest.mark.parametrize('change', ['text', 'speed', 'language', 'voice_id', 'model_id', 'runtime_id', 'corrupt'])
def test_vibi_line_cache_binds_request_and_voice_and_checks_bytes(tmp_path, change):
    from healthvideo.storage.files import sha256_file

    class Paid(SilentTTS):
        provider_name = 'vibi_minimax'

        def __init__(self):
            self.calls = 0
            self.identity = {'provider': self.provider_name, 'voice_id': 'clone-1',
                             'model_id': 'speech-2.8-hd', 'runtime_id': 'settings-1'}

        def cache_identity(self):
            return self.identity

        def synthesize(self, request, output):
            self.calls += 1
            return super().synthesize(request, output)

    tts = Paid()
    request = TTSRequest(text='Test narration', language='vi')
    output = tmp_path / 'line.wav'
    cache = tmp_path / 'cache'
    produce._synthesize_cached_line(tts, request, output, cache_dir=cache)
    original = sha256_file(output)
    output.unlink()
    produce._synthesize_cached_line(tts, request, output, cache_dir=cache)
    assert tts.calls == 1 and sha256_file(output) == original
    if change in ('text', 'speed', 'language'):
        request = request.model_copy(update={change: {'text': 'Changed narration', 'speed': 1.1, 'language': 'en'}[change]})
    elif change == 'corrupt':
        next(cache.glob('*.wav')).write_bytes(b'broken')
    else:
        tts.identity[change] = 'changed'
    produce._synthesize_cached_line(tts, request, output, cache_dir=cache)
    assert tts.calls == 2


def test_vibi_normalized_cache_rejects_bad_provider_audio_and_skips_duplicate_usage(tmp_path):
    import io
    import shutil
    import subprocess
    import wave

    from healthvideo.tts.elevenlabs import VoiceProfile
    from healthvideo.tts.normalize import NormalizedTTS
    from healthvideo.tts.vibi import VibiError, VibiTTS

    profile = VoiceProfile.model_validate({
        'provider': 'vibi_minimax', 'model_id': 'speech-2.8-hd', 'voice_id': 'clone-1',
        'settings': {'speed': 1.0, 'pitch': 0, 'vol': 1.0},
    })
    post_calls = []
    mode = {'state': 'silent'}

    def opener(request, *, timeout):
        if request.get_method() == 'POST':
            post_calls.append(request.full_url)
            return io.BytesIO(b'{"id": "t1"}')
        if '/v1/history/' in request.full_url:
            return io.BytesIO(b'{"status": "completed", "result": {"audio_url": "https://api.vibi.pro/a.mp3"}}')
        return io.BytesIO(b'mp3')

    def decode_runner(argv, **kwargs):
        out = argv[-1]
        if mode['state'] == 'unreadable':
            with open(out, 'wb') as f:
                f.write(b'corrupt-wav')
        else:
            sample = b'\x00\x00' if mode['state'] == 'silent' else b'\x01\x00'
            with wave.open(out, 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(sample * 4800)
        return subprocess.CompletedProcess(argv, 0)

    def loudnorm_runner(argv):
        shutil.copyfile(argv[argv.index('-i') + 1], argv[-1])
        return 0

    usage = tmp_path / 'audio/tts-usage.json'
    vibi = VibiTTS(profile, api_key='secret-key', opener=opener, runner=decode_runner,
                   sleep=lambda _: None, usage_path=usage)
    wrapped = NormalizedTTS(vibi, runner=loudnorm_runner)
    cache = tmp_path / 'cache/tts'
    output = tmp_path / 'out/line.wav'
    output.parent.mkdir(parents=True, exist_ok=True)
    req = TTSRequest(text='Gút cấp', language='vi')

    with pytest.raises(ValueError, match='unsupported audio tag'):
        produce._synthesize_cached_line(wrapped, TTSRequest(text='[shouts] Gút', language='vi'), output, cache_dir=cache)
    assert post_calls == []

    for bad_state in ('silent', 'unreadable'):
        mode['state'] = bad_state
        with pytest.raises(VibiError) as caught:
            produce._synthesize_cached_line(wrapped, req, output, cache_dir=cache)
        assert not isinstance(caught.value, ValueError)
        assert not list(cache.glob('*'))

    usage.unlink(missing_ok=True)
    post_calls.clear()
    mode['state'] = 'good'
    produce._synthesize_cached_line(wrapped, req, output, cache_dir=cache)
    assert len(post_calls) == 1
    assert len(json.loads(usage.read_text(encoding='utf-8'))['requests']) == 1

    output.unlink()
    produce._synthesize_cached_line(wrapped, req, output, cache_dir=cache)
    assert len(post_calls) == 1
    assert len(json.loads(usage.read_text(encoding='utf-8'))['requests']) == 1

    # Raw VibiTTS has a different runtime_id (without -loudnorm), so it misses the loudnorm cache.
    produce._synthesize_cached_line(vibi, req, output, cache_dir=cache)
    assert len(post_calls) == 2
