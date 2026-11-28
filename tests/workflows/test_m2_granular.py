from pathlib import Path

import pytest

from healthvideo.company import COMPANY_PATH, load_company
from healthvideo.storage.files import read_yaml, write_yaml_atomic


def test_writer_rework_chain_and_independence(tmp_path):
    company = load_company()
    assert company.chain('writer')[0] == company.roles['writer'].models[0]
    assert company.chain('writer', rework=True)[0].model == 'gemini-4-neon-medium'
    data = read_yaml(COMPANY_PATH)
    data['roles']['writer']['rework_models'] = data['roles']['script_critic']['models']
    path = tmp_path / 'company.yaml'
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError, match='script_critic'):
        load_company(path)


@pytest.mark.parametrize('maker,critic', [('writer', 'script_critic'),
                                         ('storyboard_director', 'art_director'),
                                         ('editor', 'product_critic')])
def test_rework_cannot_alias_critic_fallback(tmp_path, maker, critic):
    data = read_yaml(COMPANY_PATH)
    fallback = data['roles'][critic]['models'][-1]
    data['roles'][maker]['rework_models'] = [fallback]
    path = tmp_path / 'company.yaml'
    write_yaml_atomic(path, data)
    with pytest.raises(ValueError, match='trùng model sửa'):
        load_company(path)


def test_parts_hash_and_assembly(tmp_path, monkeypatch):
    from healthvideo.workflows import storyboard_parts as parts

    root = tmp_path
    lines = [{'id': f'L{i:02}', 'text': f'Đây là cảnh {i}.'} for i in range(1, 4)]
    write_yaml_atomic(root / 'script/script.yaml', {'title': 'Test', 'lines': lines})
    assert parts.part_status(root) == dict.fromkeys(['S01', 'S02', 'S03'], 'missing')
    for i, line in enumerate(lines, 1):
        write_yaml_atomic(root / f'storyboard/parts/S{i:02}.yaml', {
            'id': f'S{i:02}', 'script_line_id': line['id'], 'narration': line['text'],
            'start_frame': (i - 1) * 100, 'duration_frames': 100, 'visual': 'whiteboard',
            'on_screen_text': 'Nhãn cảnh',
            'script_sha256': parts.script_hashes(root)[f'S{i:02}'],
        })
    monkeypatch.setattr(parts, '_validation_error', lambda _: None)
    assert parts.assemble(root) == []
    assert len(read_yaml(root / 'storyboard/storyboard.yaml')['scenes']) == 3
    lines[1]['text'] = 'Nội dung mới.'
    write_yaml_atomic(root / 'script/script.yaml', {'title': 'Test', 'lines': lines})
    assert parts.part_status(root) == {'S01': 'ok', 'S02': 'invalid', 'S03': 'ok'}


def test_preflight_requires_script(tmp_path):
    from healthvideo.workflows.step_preflight import preflight
    from tests.helpers import create_long_form_project_fixture

    project = create_long_form_project_fixture(tmp_path / 'projects')
    (project / 'revisions/001/script/script.yaml').unlink()
    assert 'script/script.yaml' in ' '.join(preflight('storyboard_design', project))
    assert preflight('posts', Path('unused')) == []


@pytest.fixture
def storyboard_job(tmp_path, monkeypatch):
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.workflows import runner
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    root = project / 'revisions/001'
    entry = QueueEntry(slug=project.name, title='Test', question='Test?', added='2026-11-26')
    calls = []

    def invoke(slots, prompt, **kwargs):
        from healthvideo.agents import AgentResult

        calls.append((slots, prompt))
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    deps = runner.RunDeps(create_project=lambda *a: project,
                         read_state=lambda _: WorkflowState.DRAFT_READY,
                         reject_note=lambda _: None, python_steps={}, invoke=invoke,
                         changed_code_paths=lambda _: [])

    def run(**kwargs):
        from dataclasses import replace

        report = runner.RunReport()
        active = replace(deps, invoke=kwargs.pop('invoke', invoke))
        result = runner._run_agent_invocation(
            tmp_path, active, entry, project, report, step=kwargs.pop('step', 'storyboard_design'),
            brief_context='test', log_dir=tmp_path / 'logs', defer_validation_record=True, **kwargs)
        return result, report

    return project, root, calls, run


@pytest.mark.parametrize('defect', [None, 'retrieved_at', 'author', 'license', 'source_page',
                                   'original_url', 'sha256', 'file'])
def test_catalog_preflight_and_zero_agent_calls(storyboard_job, defect):
    from healthvideo.workflows.step_preflight import preflight
    from tests.visuals.test_medanim_assets import DATA, record

    project, root, calls, run = storyboard_job
    write_yaml_atomic(root / 'workflow/standards.yaml', {'quality_standard': {'profile': 'r5_v1'}})
    data = record(retrieved_at='2026-11-26').model_dump(mode='json')
    catalog = root / 'assets/r5/catalog.yaml'
    catalog.parent.mkdir(parents=True, exist_ok=True)
    # Revision catalogs are revision-relative, like gate_review.snapshot_r5_assets reads them.
    (root / data['file']).parent.mkdir(parents=True, exist_ok=True)
    (root / data['file']).write_bytes(DATA)
    if defect == 'sha256':
        data['sha256'] = '0' * 64
    elif defect == 'file':
        (root / data['file']).unlink()
    elif defect:
        data[defect] = None
    write_yaml_atomic(catalog, {'assets': [data]})
    errors = preflight('storyboard_design', project)
    if defect is None:
        assert errors == []
    else:
        assert 'liver' in ' '.join(errors)
        if defect not in {'file', 'sha256'}:
            assert defect in ' '.join(errors)
        result, report = run()
        assert result[0] == 'blocked'
        assert calls == [] and report.blocked == [project.name]
        assert not (project.parents[1] / 'topics/logs' / project.name / 'agent-retry.yaml').exists()


def _three_scenes(root):
    from healthvideo.workflows import storyboard_parts as parts

    lines = [{'id': f'L{i:02}', 'text': f'Cảnh thử {i}.'} for i in range(1, 4)]
    write_yaml_atomic(root / 'script/script.yaml', {'title': 'Test', 'lines': lines})
    return [{
        'id': f'S{i:02}', 'script_line_id': line['id'], 'narration': line['text'],
        'start_frame': (i - 1) * 100, 'duration_frames': 100,
        'visual': 'whiteboard', 'on_screen_text': 'Nhãn cảnh',
        'script_sha256': parts.script_hashes(root)[f'S{i:02}'],
    } for i, line in enumerate(lines, 1)]


def test_runner_resumes_only_unfinished_and_restores_locked(storyboard_job, monkeypatch):
    from healthvideo.agents import AgentResult
    from healthvideo.workflows import runner
    from healthvideo.workflows import storyboard_parts as parts

    project, root, _, run = storyboard_job
    scenes = _three_scenes(root)
    (root / 'storyboard/storyboard.yaml').unlink()
    monkeypatch.setattr(parts, '_validation_error', lambda _: None)
    # Keep production prompt generation: only irrelevant pinned R5 blocks are absent.
    prompts = []

    def invoke(slots, prompt, **kwargs):
        prompts.append(prompt)
        if len(prompts) == 1:
            for scene in scenes[:2]:
                write_yaml_atomic(root / f"storyboard/parts/{scene['id']}.yaml", scene)
            write_yaml_atomic(root / 'storyboard/storyboard.yaml', {'scenes': [], 'title': 'partial'})
        else:
            assert 'S03' in prompt and 'đã khoá, không sửa: S01, S02' in prompt
            pending = prompt.split('pending:', 1)[1]
            assert 'script_line_id: L01' not in pending and 'script_line_id: L02' not in pending
            (root / 'storyboard/parts/S01.yaml').write_text('tampered: true', encoding='utf-8')
            (root / 'storyboard/parts/S02.yaml').unlink()
            write_yaml_atomic(root / 'storyboard/parts/S03.yaml', scenes[2])
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    result, report = run(invoke=invoke)
    assert result[0] == 'partial' and report.blocked == []
    assert not (root / 'storyboard/storyboard.yaml').exists()
    assert not (project.parents[1] / 'topics/logs' / project.name / 'agent-retry.yaml').exists()
    locked = {i: (root / f'storyboard/parts/S{i:02}.yaml').read_bytes() for i in (1, 2)}
    result, _ = run(invoke=invoke)
    assert result[0] == 'ok'
    for i, raw in locked.items():
        assert (root / f'storyboard/parts/S{i:02}.yaml').read_bytes() == raw
    assert len(read_yaml(root / 'storyboard/storyboard.yaml')['scenes']) == 3
    assert runner.storyboard_validation_error(project) is not None  # synthetic mini-board lacks outro


def test_assemble_uses_real_validator(storyboard_job):
    from healthvideo.workflows import storyboard_parts as parts
    from healthvideo.workflows.storyboard_design import storyboard_validation_error

    project, root, _, _ = storyboard_job
    assert storyboard_validation_error(project) is None
    board = read_yaml(root / 'storyboard/storyboard.yaml')
    write_yaml_atomic(root / parts.METADATA, {k: v for k, v in board.items() if k != 'scenes'})
    for i, scene in enumerate(board['scenes'], 1):
        scene_id = f'S{i:02}'
        write_yaml_atomic(root / f'storyboard/parts/{scene_id}.yaml', scene | {
            'id': scene_id, 'script_sha256': parts.script_hashes(root)[scene_id]})
    assert parts.assemble(root) == []
    assert storyboard_validation_error(project) is None


def test_validator_invalidates_only_named_scene_and_rolls_back(storyboard_job, monkeypatch):
    from healthvideo.workflows import storyboard_parts as parts

    _, root, _, _ = storyboard_job
    scenes = _three_scenes(root)
    before = (root / 'storyboard/storyboard.yaml').read_bytes()
    for scene in scenes:
        write_yaml_atomic(root / f"storyboard/parts/{scene['id']}.yaml", scene)
    locked = (root / 'storyboard/parts/S01.yaml').read_bytes()
    monkeypatch.setattr(parts, '_validation_error', lambda _: 'Scene S02: synthetic failure')
    assert parts.assemble(root) == ['Scene S02: synthetic failure']
    assert parts.part_status(root) == {'S01': 'ok', 'S02': 'invalid', 'S03': 'ok'}
    assert (root / 'storyboard/storyboard.yaml').read_bytes() == before
    assert (root / 'storyboard/parts/S01.yaml').read_bytes() == locked


def test_scoped_writer_rework_uses_neon_even_for_scope_retry(storyboard_job, monkeypatch):
    from healthvideo.agents import AgentResult
    from healthvideo.workflows import rework, runner

    project, root, _, run = storyboard_job
    rework.prepare(project, 'L01: sửa theo phạm vi')
    monkeypatch.setattr(runner, '_build_step_prompt', lambda *a, **kw: 'Fixture medical scope')
    chains = []

    def invoke(slots, prompt, **kwargs):
        chains.append(slots)
        if len(chains) == 1:
            evidence = root / 'evidence/ledger.yaml'
            evidence.write_text(evidence.read_text(encoding='utf-8') + '\n# outside scope\n', encoding='utf-8')
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    result, _ = run(step='revise_medical', invoke=invoke)
    assert result[0] == 'ok', result
    assert len(chains) == 2
    assert all(chain[0].model == 'gemini-4-neon-medium' for chain in chains)


@pytest.mark.parametrize('failures,expected', [(0, 'gemini-4-neon-medium'),
                                               (1, 'gemini-4-neon-medium'), (2, 'gpt-6.2-sol')])
def test_medium_escalation_uses_existing_retry_counter(storyboard_job, monkeypatch, failures, expected):
    from healthvideo.workflows import runner

    _, _, calls, run = storyboard_job
    monkeypatch.setattr(runner, 'agent_retry_status',
                        lambda *a: {'allowed': True, 'consecutive_failures': failures})
    assert run()[0][0] == 'ok'
    assert calls[0][0][0].model == expected


def test_existing_retry_hold_is_not_bypassed_for_escalation(storyboard_job, monkeypatch):
    from healthvideo.workflows import runner

    _, _, calls, run = storyboard_job
    monkeypatch.setattr(runner, 'agent_retry_status', lambda *a: {
        'allowed': False, 'consecutive_failures': 2, 'retry_after': None, 'reason': 'validation'})
    assert run()[0][0] == 'blocked' and calls == []


def test_storyboard_rework_unlocks_only_named_part(storyboard_job, monkeypatch):
    from healthvideo.agents import AgentResult
    from healthvideo.workflows import rework
    from healthvideo.workflows import storyboard_parts as parts

    project, root, _, run = storyboard_job
    scenes = _three_scenes(root)
    for scene in scenes:
        write_yaml_atomic(root / f"storyboard/parts/{scene['id']}.yaml", scene)
    board_path = root / 'storyboard/storyboard.yaml'
    write_yaml_atomic(board_path, {'title': 'Test', 'scenes': [
        {k: v for k, v in scene.items() if k != 'script_sha256'} for scene in scenes]})
    rework.storyboard_failure(project, {'storyboard/storyboard.yaml': board_path},
                              ValueError('Scene S02: change label'))
    locked = {i: (root / f'storyboard/parts/S{i:02}.yaml').read_bytes() for i in (1, 3)}
    monkeypatch.setattr(parts, '_validation_error', lambda _: None)

    def invoke(slots, prompt, **kwargs):
        assert 'đã khoá, không sửa: S01, S03' in prompt
        assert parts.part_status(root) == {'S01': 'ok', 'S02': 'invalid', 'S03': 'ok'}
        data = read_yaml(root / 'storyboard/parts/S02.yaml')
        data.pop('validation_error')
        data.update(status='ok', on_screen_text='Nhãn mới')
        write_yaml_atomic(root / 'storyboard/parts/S02.yaml', data)
        return AgentResult('fixture', True, False, kwargs['log_dir'] / 'agent.log')

    result, _ = run(invoke=invoke)
    assert result[0] == 'ok'
    assert not (root / rework.STORYBOARD_PLAN).exists()
    for i, raw in locked.items():
        assert (root / f'storyboard/parts/S{i:02}.yaml').read_bytes() == raw


def test_legacy_storyboard_is_not_split(storyboard_job):
    from healthvideo.workflows import storyboard_parts as parts

    project, root, calls, run = storyboard_job
    manifest = read_yaml(project / 'project.yaml')
    manifest['state'] = 'medically_approved'
    write_yaml_atomic(project / 'project.yaml', manifest)
    assert not parts.enabled(root)
    assert run()[0][0] == 'ok'
    assert '## Phân cảnh từng phần' not in calls[0][1]
    assert not (root / 'storyboard/parts').exists()


def test_needs_asset_does_not_discard_other_parts(storyboard_job):
    from healthvideo.workflows import storyboard_parts as parts

    _, root, _, _ = storyboard_job
    scenes = _three_scenes(root)
    for scene in scenes:
        write_yaml_atomic(root / f"storyboard/parts/{scene['id']}.yaml", scene)
    path = root / 'storyboard/parts/S02.yaml'
    write_yaml_atomic(path, scenes[1] | {'status': 'needs_asset', 'missing': 'Hình mô gan có phép'})
    before = (root / 'storyboard/parts/S01.yaml').read_bytes()
    assert parts.part_status(root) == {'S01': 'ok', 'S02': 'needs_asset', 'S03': 'ok'}
    assert 'Hình mô gan' in ' '.join(parts.assemble(root))
    assert (root / 'storyboard/parts/S01.yaml').read_bytes() == before


def test_no_progress_uses_existing_hold_and_does_not_reinvoke(storyboard_job):
    project, root, calls, run = storyboard_job
    _three_scenes(root)
    (root / 'storyboard/storyboard.yaml').unlink()
    assert run()[0][0] == 'blocked'
    assert len(calls) == 1
    retry = project.parents[1] / 'topics/logs' / project.name / 'agent-retry.yaml'
    assert read_yaml(retry)['steps']['storyboard_design']['kind'] == 'validation'
    assert run()[0][0] == 'blocked'
    assert len(calls) == 1


def test_invalid_script_schema_blocks_before_prompt_or_agent(storyboard_job):
    project, root, calls, run = storyboard_job
    write_yaml_atomic(root / 'script/script.yaml', {'lines': []})
    result, report = run()
    assert result[0] == 'blocked' and calls == [] and report.blocked == [project.name]
    assert 'script/script.yaml' in result[-1]['error']
    retry = project.parents[1] / 'topics/logs' / project.name / 'agent-retry.yaml'
    assert not retry.exists()
