"""Offline checks for the shared agent file boundary."""

import base64
import shutil
import subprocess
import sys

import pytest

from healthvideo.storage.files import write_yaml_atomic


@pytest.mark.parametrize('payload', [
    {'reply': 'Trong d? li?u hi?n t?i kh?ng th?y m?c 003'},
    {'options': [{'label': 'M? d? ?n ho?c t?c v?'}]},
    {'summary': 'Kh?ng c? issue m? c?n x? l? trong v?ng n?y.'},
    {'brief': 'Ch?a ?? ng? c?nh'},
    {'scenes': [{'reason': 'H?nh kh?p l?i ??c'}]},
    {'title': 'KH?NG C? L?I C?N S?A'},
])
def test_agent_file_rejects_loss_before_consumption(tmp_path, payload):
    from healthvideo.storage.files import read_agent_yaml

    path = tmp_path / 'report.yaml'
    write_yaml_atomic(path, payload)
    before = path.read_bytes()
    with pytest.raises(ValueError, match=r'văn bản bị mất dấu \(mã hóa\)'):
        read_agent_yaml(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('text', [
    'Vì sao? Không có vấn đề cần xử lý.',
    'https://example.org/a?b=c&d=e?f=g',
    'Chọn A?B hay C?D?',
    'A? Một câu hỏi thật?',
])
def test_agent_file_preserves_questions(tmp_path, text):
    from healthvideo.storage.files import read_agent_yaml

    path = tmp_path / 'report.yaml'
    write_yaml_atomic(path, {'reply': text})
    assert read_agent_yaml(path) == {'reply': text}


def test_powershell_pipe_can_corrupt_even_when_python_writes_utf8(tmp_path):
    powershell = shutil.which('powershell.exe')
    if not powershell:
        pytest.skip('Windows PowerShell reproduction')
    text = 'Không có vấn đề cần xử lý.'
    # EncodedCommand delivers the original Unicode intact to PowerShell itself.
    source = "import sys; from pathlib import Path; Path(sys.argv[1]).write_text(" + repr(text) + ", encoding='utf-8')"
    def run(name, encoding):
        path = tmp_path / name
        command = (
            f"$OutputEncoding = New-Object System.Text.{encoding}; "
            f"@'\n{source}\n'@ | & '{sys.executable}' - '{path}'"
        )
        result = subprocess.run(
            [powershell, '-NoProfile', '-EncodedCommand',
             base64.b64encode(command.encode('utf-16-le')).decode('ascii')],
            capture_output=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        return path.read_text(encoding='utf-8')

    assert run('bad.txt', 'ASCIIEncoding') != text
    assert '?' in (tmp_path / 'bad.txt').read_text(encoding='utf-8')
    assert run('good.txt', 'UTF8Encoding') == text


@pytest.mark.parametrize('recover', [False, True])
def test_chat_retries_encoding_without_publishing_broken_reply(tmp_path, recover):
    from healthvideo.agents import AgentResult
    from healthvideo.workflows import chat

    message = chat.post(tmp_path, None, 'Mục 003 ở đâu?', {}, start_worker=False)
    bad = 'Trong d? li?u hi?n t?i kh?ng th?y m?c 003'
    good = 'Vì sao? Không thấy mục 003 trong dữ liệu hiện tại.'
    calls = []

    def invoke(slots, prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 2:
            assert 'văn bản bị mất dấu (mã hóa)' in prompt
        text = good if recover and len(calls) == 2 else bad
        write_yaml_atomic(kwargs['log_dir'] / f"{message['id']}.yaml", {
            'reply': text, 'action': 'ask', 'options': [
                {'label': text, 'effect': text},
                {'label': 'Gửi tên kế hoạch', 'effect': 'Đối chiếu mục trong kế hoạch.'},
            ],
        })
        return AgentResult('fake', True, False, kwargs['log_dir'] / 'fake.log')

    result = chat.run_coordinator(tmp_path, message['id'], invoke=invoke)
    assert len(calls) == 2
    rows = chat.load(tmp_path, None)
    assert bad not in (tmp_path / 'topics/chat.jsonl').read_text(encoding='utf-8')
    if recover:
        assert result['text'] == result['options'][0]['label'] == good
    else:
        assert result['status'] == 'failed'
        assert not [row for row in rows if row['who'] == 'coordinator']


@pytest.mark.parametrize('model_name', ['Diagnosis', 'RepairResult', 'Acceptance'])
def test_repair_roles_reject_encoding_before_acceptance(tmp_path, model_name):
    from healthvideo.agents import AgentResult
    from healthvideo.storage.files import AgentEncodingError
    from healthvideo.workflows import repair_service as repair

    report = tmp_path / 'result.yaml'

    def invoke(slots, prompt, **kwargs):
        write_yaml_atomic(report, {'summary': 'Kh?ng c? l?i c?n s?a'})
        return AgentResult('fake', True, False, tmp_path / 'fake.log')

    with pytest.raises(AgentEncodingError):
        repair._ask(tmp_path, 'fixture', 'repair_engineer', 'repair', 'fixture',
                    report, getattr(repair, model_name), invoke)


def test_agent_invocation_forces_utf8_and_instructs_all_roles(tmp_path, monkeypatch):
    from healthvideo import agents

    monkeypatch.setattr(agents, 'child_env', lambda: {'pythonutf8': '0', 'PYTHONIOENCODING': 'cp1252'})
    monkeypatch.setattr(agents, 'prepare_subprocess_argv', lambda argv: argv)
    seen = []

    def runner(argv, **kwargs):
        seen.append(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout='Đã ghi báo cáo.', stderr='')

    result = agents.invoke(agents.CODEX, 'fixture', cwd=tmp_path,
                           log_dir=tmp_path / 'logs', runner=runner)
    assert result.ok
    assert seen[0]['env'] == {'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
    assert 'here-string/pipe' in seen[0]['input']
    assert 'Đã ghi báo cáo.' in result.log_path.read_text(encoding='utf-8')


def test_encoding_error_is_retryable():
    from healthvideo.failures import classify_failure
    from healthvideo.storage.files import AgentEncodingError, validate_agent_text

    with pytest.raises(AgentEncodingError) as caught:
        validate_agent_text({'summary': 'Kh?ng c? l?i'})
    assert classify_failure(caught.value) == 'transient'


@pytest.mark.parametrize('raw', [b'reply: "\xff"', 'reply: "Hình bị lỗi"'.encode('utf-16')])
def test_non_utf8_submission_is_rejected(tmp_path, raw):
    from healthvideo.storage.files import AgentEncodingError, read_agent_yaml

    path = tmp_path / 'result.yaml'
    path.write_bytes(raw)
    with pytest.raises(AgentEncodingError):
        read_agent_yaml(path)


def test_scoped_rewrite_rejects_lost_accents_in_allowed_line():
    from healthvideo.storage.files import AgentEncodingError
    from healthvideo.workflows.scoped_review import check_script

    before = b'lines:\n- id: N01\n  text: Original\n'
    bad = b'lines:\n- id: N01\n  text: Kh?ng c? l?i\n'
    with pytest.raises(AgentEncodingError):
        check_script(before, bad, {'N01'})
    good = 'lines:\n- id: N01\n  text: Vì sao? Không có lỗi.\n'.encode()
    check_script(before, good, {'N01'})


@pytest.mark.parametrize(('step', 'relative'), [
    ('research', 'evidence/expert-brief.md'),
    ('research', 'evidence/records.yaml'),
    ('draft', 'script/script.yaml'),
    ('draft', 'script/questions.yaml'),
    ('storyboard_design', 'storyboard/storyboard.yaml'),
    ('voice_prep', 'script/voice-prep.yaml'),
    ('shorts_plan', 'posts/shorts-plan.yaml'),
    ('posts', 'posts/posts.yaml'),
    ('revise_product', 'posts/posts.yaml'),
    ('revise_production', 'assets/asset-manifest.yaml'),
])
def test_runner_rejects_direct_agent_files_even_without_cli_submission(tmp_path, step, relative):
    from healthvideo.storage.files import AgentEncodingError
    from healthvideo.workflows.runner import _validate_agent_step_files
    from tests.workflows.test_script_review import _project

    project = _project(tmp_path)
    path = project / 'revisions/001' / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.md':
        path.write_text('Kh?ng c? k?t qu? ph? h?p', encoding='utf-8')
    else:
        write_yaml_atomic(path, {'summary': 'Kh?ng c? k?t qu? ph? h?p'})
    before = path.read_bytes()
    with pytest.raises(AgentEncodingError):
        _validate_agent_step_files(project, step)
    assert path.read_bytes() == before


def test_utf8_bom_is_accepted(tmp_path):
    from healthvideo.storage.files import read_agent_yaml

    path = tmp_path / 'result.yaml'
    path.write_text('reply: Vì sao? Không có lỗi.', encoding='utf-8-sig')
    assert read_agent_yaml(path) == {'reply': 'Vì sao? Không có lỗi.'}
