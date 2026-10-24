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


def test_line_cache_survives_failed_render_and_changes_with_settings(tmp_path):
    project, _, _ = voice_project(tmp_path)
    calls = []

    class Paid(SilentTTS):
        provider_name = 'elevenlabs'
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
