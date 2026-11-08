import importlib
import threading
from datetime import date

import pytest

from healthvideo.agents import AgentResult, AllAgentsExhausted
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import factory, standards
from healthvideo.workflows.script_review import CRITERIA
from tests.helpers import create_v2_project_fixture


def module():
    return importlib.import_module('healthvideo.workflows.factory_trials')


def _fake_invoke(agents, prompt, *, cwd, log_dir, **_):
    del agents, cwd
    project_dir = log_dir.parent / 'project'
    rev = project_dir / 'revisions' / '001'
    log_dir.mkdir(parents=True, exist_ok=True)
    step = 'research' if '(`research`)' in prompt else 'draft'
    if '(`script_review`)' in prompt:
        log_path = log_dir / 'review-fake.log'
        write_yaml_atomic(rev / 'reviews/script-review.yaml', {
            'scores': dict.fromkeys(CRITERIA, 8), 'summary': 'Đạt.', 'issues': [],
        })
        return AgentResult(agent='fake-codex', ok=True, quota_exhausted=False, log_path=log_path)
    log_path = log_dir / f'{step}-fake.log'
    log_path.write_text(prompt, encoding='utf-8')
    if step == 'research':
        write_yaml_atomic(rev / 'evidence/ledger.yaml', {
            'schema_version': '1.0',
            'records': [{
                'id': 'R01',
                'title': 'Knuckle cracking and hand osteoarthritis',
                'year': 2011,
                'journal': 'J Am Board Fam Med',
                'pmid': '21415251',
                'doi': '10.3122/jabfm.2011.02.100156',
            }],
            'claims': [{
                'id': 'C01',
                'text_public': 'Bẻ khớp ngón tay thường xuyên không làm tăng thoái hóa khớp bàn tay.',
                'text_technical': 'Habitual knuckle cracking was not associated with hand osteoarthritis.',
                'type': 'evidence',
                'sources': ['R01'],
                'support': [{
                    'source_id': 'R01',
                    'locator': 'Abstract',
                    'quote': 'A history of habitual knuckle cracking was not a risk factor for hand osteoarthritis.',
                }],
            }],
        })
    else:
        write_yaml_atomic(rev / 'script/script.yaml', {
            'schema_version': '1.0',
            'format_profile': 'explain_first_v1',
            'title': 'Bẻ ngón tay và thoái hóa khớp',
            'language': 'vi',
            'lines': [{
                'id': 'L01',
                'text': 'Tiếng rắc khi bẻ ngón tay là bọt khí trong dịch khớp vỡ ra.',
                'claim_id': 'C01',
                'source_marker': '[R01]',
            }],
        })
    return AgentResult(agent='fake-codex', ok=True, quota_exhausted=False, log_path=log_path)


def test_stage1_run_returns_running_then_ready_with_script_outputs(tmp_path):
    trials = module()
    standards.record(tmp_path, slug='chung', gate='chung', revision='-', kind='comment',
                     text='Đi thẳng vào cơ chế giải phẫu.')
    topic = 'Bẻ ngón tay gây to khớp thoái hóa; bẻ cổ khi massage kêu rắc giúp thư giãn kinh lạc.'
    prompts: list[str] = []

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        prompts.append(prompt)
        return _fake_invoke(agents, prompt, cwd=cwd, log_dir=log_dir)

    trial = trials.create_trial(tmp_path, 1, topic=topic)
    running = trials.run_trial(tmp_path, trial['id'], invoke=invoke)
    assert running['status'] == 'running'
    assert running['step'] == 'research'
    assert running['started_at']

    ready = trials.wait_trial(tmp_path, trial['id'])
    assert ready['status'] == 'ready'
    paths = [o['path'] for o in ready['outputs']]
    assert 'project/revisions/001/script/script.yaml' in paths
    assert 'project/revisions/001/evidence/ledger.yaml' in paths
    assert ready['lines'][0]['id'] == 'L01'
    assert ready['lines'][0]['claim_id'] == 'C01'
    assert ready['claims'][0]['id'] == 'C01'
    assert ready['claims'][0]['support'][0]['source_id'] == 'R01'
    assert ready['records'][0]['pmid'] == '21415251'

    assert len(prompts) == 3
    assert '(`research`)' in prompts[0]
    assert '(`draft`)' in prompts[1]
    assert '(`script_review`)' in prompts[2]
    assert ready['script_review']['passed'] is True
    for prompt in prompts:
        assert topic in prompt
        assert 'Đi thẳng vào cơ chế giải phẫu.' in prompt
        assert trials.TRIAL_ISOLATION_LINE in prompt
        from healthvideo.workflows.runner import HARD_RULES
        assert prompt.rstrip().endswith('\n'.join(f'- {rule}' for rule in HARD_RULES))
        from healthvideo.workflows.runner import HARD_RULES
        assert prompt.rstrip().endswith('\n'.join(f'- {rule}' for rule in HARD_RULES))

    tdir = trials.trial_dir(tmp_path, trial['id'])
    card = read_yaml(tdir / 'project/revisions/001/topic/card.yaml')
    assert card['title'] == topic
    assert card['question'] == topic
    assert list((tdir / 'logs').glob('*.log'))


@pytest.mark.parametrize('mode', ['agent_error', 'quota_exhausted'])
def test_stage1_invoke_failure_sets_failed_with_vietnamese_reason(tmp_path, mode):
    trials = module()

    def failing_invoke(agents, prompt, *, cwd, log_dir, **_):
        del agents, prompt, cwd
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'fail.log'
        log_path.write_text('failed', encoding='utf-8')
        if mode == 'quota_exhausted':
            raise AllAgentsExhausted()
        return AgentResult(agent='codex', ok=False, quota_exhausted=False, log_path=log_path)

    trial = trials.create_trial(tmp_path, 1, topic='Chủ đề thử lỗi')
    running = trials.run_trial(tmp_path, trial['id'], invoke=failing_invoke)
    assert running['status'] == 'running'
    failed = trials.wait_trial(tmp_path, trial['id'])
    assert failed['status'] == 'failed'
    assert failed['outputs'] == []
    if mode == 'quota_exhausted':
        assert 'hạn mức' in failed['reason']
    else:
        assert 'gặp lỗi' in failed['reason']


def test_orphan_running_trial_marked_failed_on_bundle_read(tmp_path):
    trials = module()
    trial = trials.create_trial(tmp_path, 1, topic='Chủ đề mồ côi')
    path = trials.trial_dir(tmp_path, trial['id']) / 'trial.yaml'
    record = read_yaml(path)
    record.update(status='running', step='draft', started_at='2026-10-27T09:00:00+07:00')
    write_yaml_atomic(path, record)

    bundle = trials.trial_bundle(tmp_path, trial['id'])
    assert bundle['status'] == 'failed'
    assert bundle['reason'] == 'App đã tắt khi mẫu đang chạy; bấm chạy lại.'
    assert read_yaml(path)['status'] == 'failed'


def test_stage1_real_trial_never_mutates_topics_or_projects_fixtures(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Production worker called')

    monkeypatch.setattr(factory, 'start_background', forbidden)
    create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    add_to_queue(
        tmp_path,
        QueueEntry(
            slug='existing-topic',
            title='Chủ đề thật trong hàng đợi',
            question='Câu hỏi thật?',
            added=date(2026, 10, 27),
        ),
    )
    before = {
        p: p.read_bytes()
        for folder in ('projects', 'topics')
        for p in sorted((tmp_path / folder).rglob('*'))
        if p.is_file()
    }

    trials = module()
    trial = trials.create_trial(tmp_path, 1, topic='Bẻ ngón tay có gây thoái hóa khớp không?')
    trials.run_trial(tmp_path, trial['id'], invoke=_fake_invoke)
    result = trials.wait_trial(tmp_path, trial['id'])
    assert result['status'] == 'ready'

    after = {
        p: p.read_bytes()
        for folder in ('projects', 'topics')
        for p in sorted((tmp_path / folder).rglob('*'))
        if p.is_file()
    }
    assert after == before
    assert not (tmp_path / 'profiles').exists()
    tdir = trials.trial_dir(tmp_path, trial['id'])
    assert not list(tdir.rglob('*approval*.yaml'))


def test_concurrent_second_run_rejected_while_running(tmp_path):
    trials = module()
    started = threading.Event()
    release = threading.Event()

    def slow_invoke(agents, prompt, *, cwd, log_dir, **_):
        started.set()
        release.wait(timeout=5)
        return _fake_invoke(agents, prompt, cwd=cwd, log_dir=log_dir)

    t1 = trials.create_trial(tmp_path, 1, topic='Mẫu 1 đang chạy')
    t2 = trials.create_trial(tmp_path, 1, topic='Mẫu 2 bấm song song')
    trials.run_trial(tmp_path, t1['id'], invoke=slow_invoke)
    assert started.wait(timeout=2)
    try:
        with pytest.raises(ValueError, match='Đang có mẫu chạy'):
            trials.run_trial(tmp_path, t1['id'], invoke=slow_invoke)
        with pytest.raises(ValueError, match='Đang có mẫu chạy'):
            trials.run_trial(tmp_path, t2['id'], invoke=slow_invoke)
    finally:
        release.set()
    assert trials.wait_trial(tmp_path, t1['id'])['status'] == 'ready'


@pytest.mark.parametrize('stage', [2, 3, 4])
def test_stages_2_to_4_keep_offline_path_without_calling_agent(tmp_path, monkeypatch, stage):
    def forbidden(*args, **kwargs):
        pytest.fail('Agent or production worker called during offline stage 2-4')

    monkeypatch.setattr(factory, 'start_background', forbidden)
    trials = module()
    trial = trials.create_trial(tmp_path, stage)
    result = trials.run_trial(tmp_path, trial['id'], invoke=forbidden)
    assert result['status'] == 'ready'
    assert result['outputs']
    assert trials.trial_bundle(tmp_path, trial['id'])['input_hash'] == result['input_hash']
    assert not (tmp_path / 'topics').exists()
    assert not (tmp_path / 'projects').exists()
    assert not (tmp_path / 'profiles').exists()
    assert all(p.is_relative_to(trials.trial_root(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())


@pytest.mark.parametrize('bad', ['../x', '..', 'a/b', 'a\\b', '/x', 'C:x'])
def test_trial_path_traversal(tmp_path, bad):
    with pytest.raises((ValueError, LookupError)):
        module().trial_bundle(tmp_path, bad)


def test_changed_output_and_input_are_stale(tmp_path):
    trials = module()
    trial = trials.create_trial(tmp_path, 1)
    trials.run_trial(tmp_path, trial['id'], invoke=_fake_invoke)
    result = trials.wait_trial(tmp_path, trial['id'])
    output = trials.trial_root(tmp_path) / trial['id'] / result['outputs'][0]['path']
    output.write_text('changed', encoding='utf-8')
    assert trials.trial_bundle(tmp_path, trial['id'])['status'] == 'stale'
    record = trials.trial_root(tmp_path) / trial['id'] / 'trial.yaml'
    data = read_yaml(record)
    data['topic'] = 'changed input'
    write_yaml_atomic(record, data)
    assert trials.trial_bundle(tmp_path, trial['id'])['status'] == 'stale'


def test_real_service_is_fail_closed_for_offline_stages_and_stage_validated(tmp_path):
    trials = module()
    for stage in [0, 5, True, '1']:
        with pytest.raises(ValueError):
            trials.create_trial(tmp_path, stage)
    trial = trials.create_trial(tmp_path, 2)
    with pytest.raises(ValueError, match='real_service'):
        trials.run_trial(tmp_path, trial['id'], real_service=True)


def test_stage_one_script_links_nonmedical_lines(tmp_path):
    outputs = module().build_stage_sample(tmp_path, 1)
    script = read_yaml(next(p for p in outputs if p.name == 'script.yaml'))
    assert script['mode'] == 'TEST'
    assert script['sources'] == []
    assert script['scenes'][0]['script_line'] == script['lines'][0]['id']


def test_samples_include_image_audio_and_seekable_video(tmp_path):
    import wave

    from PIL import Image

    from tools.factory_trial_samples import build_samples
    samples = build_samples(tmp_path)
    assert set(samples) == {1, 2, 3, 4}
    script = read_yaml(next(p for p in samples[1] if p.name == 'script.yaml'))
    assert script['mode'] == 'TEST'
    assert script['sources'] == []
    assert script['scenes'][0]['script_line'] == script['lines'][0]['id']
    assert all(p.is_relative_to(module().trial_root(tmp_path)) for paths in samples.values() for p in paths)
    image = next(p for p in samples[2] if p.suffix == '.png')
    with Image.open(image) as picture:
        assert picture.size == (640, 360)
    audio = next(p for p in samples[2] if p.suffix == '.wav')
    with wave.open(str(audio)) as sound:
        assert sound.getnframes() / sound.getframerate() == 2
    assert len([p for p in samples[3] if p.suffix == '.mp4']) == 2
    assert all(p.stat().st_size > 1000 for p in samples[3] if p.suffix == '.mp4')


def _git_repo(path):
    import subprocess

    def git(*args):
        subprocess.run(['git', *args], cwd=path, check=True, capture_output=True)

    git('init', '-q')
    git('config', 'user.email', 't@example.test')
    git('config', 'user.name', 't')
    (path / 'video/src/anatomy').mkdir(parents=True)
    (path / 'video/src/anatomy/library.json').write_text('{}', encoding='utf-8')
    git('add', '.')
    git('commit', '-qm', 'init')


def test_stage1_agent_edits_land_in_disposable_checkout(tmp_path, monkeypatch, trial_checkout_stub):
    trials = module()
    monkeypatch.setattr(trials, 'trial_checkout', trial_checkout_stub)
    _git_repo(tmp_path)
    cwds = []

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        cwds.append(cwd)
        (cwd / 'video/src/anatomy/NewOrgan.tsx').write_text('x', encoding='utf-8')
        (cwd / 'video/src/anatomy/library.json').write_text('{"NewOrgan": {}}', encoding='utf-8')
        return _fake_invoke(agents, prompt, cwd=cwd, log_dir=log_dir)

    trial = trials.create_trial(tmp_path, 1, topic='Chủ đề cách ly')
    trials.run_trial(tmp_path, trial['id'], invoke=invoke)
    ready = trials.wait_trial(tmp_path, trial['id'])
    assert ready['status'] == 'ready', ready.get('reason')
    assert all(cwd != tmp_path for cwd in cwds)
    assert not (tmp_path / 'video/src/anatomy/NewOrgan.tsx').exists()
    assert (tmp_path / 'video/src/anatomy/library.json').read_text(encoding='utf-8') == '{}'
    assert not cwds[0].exists()


def test_stage1_fails_when_agent_writes_into_real_repo(tmp_path, monkeypatch, trial_checkout_stub):
    trials = module()
    monkeypatch.setattr(trials, 'trial_checkout', trial_checkout_stub)
    _git_repo(tmp_path)

    def invoke(agents, prompt, *, cwd, log_dir, **_):
        (tmp_path / 'video/src/anatomy/Leak.tsx').write_text('x', encoding='utf-8')
        return _fake_invoke(agents, prompt, cwd=cwd, log_dir=log_dir)

    trial = trials.create_trial(tmp_path, 1, topic='Chủ đề rò rỉ')
    trials.run_trial(tmp_path, trial['id'], invoke=invoke)
    failed = trials.wait_trial(tmp_path, trial['id'])
    assert failed['status'] == 'failed'
    assert 'video/src/anatomy/Leak.tsx' in failed['reason']
