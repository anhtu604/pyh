"""Incremental reviews preserve accepted work and exact repair boundaries."""

from copy import deepcopy

import pytest

from healthvideo.workflows import scoped_review as scoped
from healthvideo.workflows.product_review import ProductReviewReport
from healthvideo.workflows.script_review import ScriptReviewReport


@pytest.mark.parametrize('model', [ProductReviewReport, ScriptReviewReport])
@pytest.mark.parametrize('statuses, expected', [
    ([{'issue_id': 'PR3-01', 'status': 'still_open'},
      {'issue_id': 'PR3-02', 'status': 'resolved'}],
     {'PR3-01': 'still_open', 'PR3-02': 'resolved'}),
    ([{'id': 'I1', 'status': 'resolved'}], {'I1': 'resolved'}),
    ([{'issue_id': 'I1', 'status': 'resolved'}] * 2, {'I1': 'resolved'}),
    ([{'issue_id': 'I1', 'id': 'I1', 'status': 'still_open'}], {'I1': 'still_open'}),
    ({'I1': 'still_open', 'I2': 'resolved'}, {'I1': 'still_open', 'I2': 'resolved'}),
    ([], {}),
    ({}, {}),
])
def test_review_issue_statuses_normalizes_shape_without_changing_report(model, statuses, expected):
    payload = {'scores': {'criterion': 6}, 'summary': 'Needs correction',
               'overall': 'Still blocked', 'issue_statuses': statuses}
    original = deepcopy(payload)
    report = model.model_validate(payload).model_dump()
    assert report['issue_statuses'] == expected
    assert report['scores'] == payload['scores']
    assert report['summary'] == payload['summary']
    assert report['overall'] == payload['overall']
    assert payload == original


@pytest.mark.parametrize('model', [ProductReviewReport, ScriptReviewReport])
@pytest.mark.parametrize('statuses', [
    [{'issue_id': 'I1', 'status': 'resolved'}, {'issue_id': 'I1', 'status': 'still_open'}],
    [{'issue_id': 'I1', 'status': 'unknown'}],
    {'I1': 'unknown'},
    [{'issue_id': 'I1'}],
    [{'status': 'resolved'}],
    [{'id': 'I1', 'status': 'unknown'}],
    [{'issue_id': 'I1', 'id': 'I2', 'status': 'resolved'}],
    [{'issue_id': '', 'status': 'resolved'}],
    [{'issue_id': 1, 'status': 'resolved'}],
    [{'issue_id': ['I1'], 'status': 'resolved'}],
    [{'issue_id': 'I1', 'status': []}],
    [{'issue_id': 'I1', 'status': 'resolved', 'extra': 'do not discard'}],
    ['I1'],
    None,
])
def test_review_issue_statuses_rejects_invalid_or_ambiguous_data(model, statuses):
    with pytest.raises(ValueError):
        model.model_validate({'scores': {}, 'summary': 'Review', 'issue_statuses': statuses})


def issue(**changes):
    return {'issue_id': 'I1', 'line': 'N02', 'criterion': 'voice', 'problem': 'dry',
                'fix': 'simplify'} | changes


def test_reviewer_gets_open_issues_and_diff_without_unchanged_body():
    before = 'lines:\n- id: N01\n  text: PRIVATE_UNCHANGED\n- id: N02\n  text: old\n'
    after = before.replace('old', 'new')
    packet = scoped.packet([issue()], {'script': before}, {'script': after}, context=0)
    assert 'I1' in packet and '-  text: old' in packet and '+  text: new' in packet
    assert 'PRIVATE_UNCHANGED' not in packet


def test_script_scope_preserves_other_lines_and_metadata():
    before = b'title: same\nlines:\n- id: N01\n  text: keep\n- id: N02\n  text: old\n'
    scoped.check_script(before, before.replace(b'old', b'new'), {'N02'})
    with pytest.raises(ValueError, match='scope'):
        scoped.check_script(before, before.replace(b'keep', b'changed'), {'N02'})
    with pytest.raises(ValueError, match='scope'):
        scoped.check_script(before, before.replace(b'same', b'other'), {'N02'})


def test_resolved_issue_cannot_reopen_except_blocking_safety():
    previous = {'scores': {'voice': 8, 'meaning': 6}, 'issues': [issue()],
                    'issue_statuses': {'I0': 'resolved'}}
    dropped = scoped.reconcile(previous, {'scores': {'voice': 1, 'meaning': 8},
                                        'issues': [issue(issue_id='I0')]}, 'line')
    assert dropped['issues'] == []
    assert dropped['dropped_issues'][0]['issue']['issue_id'] == 'I0'
    assert dropped['dropped_issues'][0]['reason']
    result = scoped.reconcile(previous, {'scores': {'voice': 1, 'meaning': 8},
                              'issues': [issue(issue_id='I0', blocking_safety=True)]}, 'line')
    assert result['scores']['meaning'] == 6
    assert result['issue_statuses']['I0'] == 'still_open'


@pytest.mark.parametrize('changes', [
    {'line': 'N03'}, {'criterion': 'meaning'}, {'related_lines': ['N03']},
    {'edits': [{'path': 'posts.yaml', 'start_line': 1, 'end_line': 9}]},
])
def test_changed_issue_scope_is_restored_and_traced(changes):
    original = issue(related_lines=['N02'], edits=[])
    result = scoped.reconcile({'scores': {'voice': 6}, 'issues': [original]},
                              {'scores': {'voice': 7}, 'issues': [original | changes]}, 'line')
    assert result['issues'] == [original]
    assert result['dropped_issues'][0]['issue'] == original | changes
    assert result['dropped_issues'][0]['reason']


def test_new_issue_on_unchanged_line_is_dropped_and_round_is_recorded(tmp_path):
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import script_review as sr
    from tests.workflows.test_script_review import _project, _report

    project = _project(tmp_path)
    write_yaml_atomic(sr.script_path(project), {'lines': [
        {'id': 'N01', 'text': 'old'}, {'id': 'N02', 'text': 'unchanged'}]})
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 8) | {'ca_tinh': 6},
            issues=[issue(line='N01', criterion='ca_tinh')])
    sr.record_review(project, sr.script_hash(project))
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 8),
            issues=[issue(issue_id='I2', line='N02', criterion='hinh_anh')])
    entry = sr.record_review(project, sr.script_hash(project))
    assert entry['issues'] == []
    assert entry['dropped_issues'][0]['issue']['issue_id'] == 'I2'
    assert entry['dropped_issues'][0]['reason']
    assert read_yaml(project / 'revisions/001' / sr.LOG)['rounds'][-1] == entry


@pytest.mark.parametrize('station', ['script', 'product'])
@pytest.mark.parametrize('followup', [False, True])
def test_scores_at_threshold_pass_with_open_issue(tmp_path, station, followup):
    if station == 'script':
        from healthvideo.workflows import script_review as review
        from tests.workflows.test_script_review import _project, _report
        open_issue = issue(line='N01', criterion='ca_tinh')
        hash_of = review.script_hash
        next_action = review.next_script_action
        expected = 'submit_medical'
    else:
        from healthvideo.workflows import product_review as review
        from tests.workflows.test_product_review import _project, _report
        open_issue = {'issue_id': 'P1', 'at': 'S02', 'criterion': 'hinh_ro',
                      'problem': 'small', 'fix': 'enlarge', 'fixable': True}
        hash_of = review.render_hash
        next_action = review.next_product_action
        expected = 'submit_video'
    project = _project(tmp_path)
    if followup:
        _report(project, scores=dict.fromkeys(review.CRITERIA, 8) | {open_issue['criterion']: 6},
                issues=[open_issue])
        review.record_review(project, hash_of(project))
    _report(project, score=7, issues=[open_issue])
    entry = review.record_review(project, hash_of(project))
    assert entry['passed'] is True
    assert entry['issues'][0]['issue_id'] == open_issue['issue_id']
    review.require_passed_review(project)
    assert next_action(project) == expected


def test_duplicate_issue_ids_still_fail():
    with pytest.raises(ValueError, match='Duplicate issue_id'):
        scoped.reconcile(None, {'scores': {'voice': 8}, 'issues': [issue(), issue()]}, 'line')


def test_new_issue_on_nonexistent_line_still_fails(tmp_path):
    from healthvideo.workflows import script_review as sr
    from tests.workflows.test_script_review import _project, _report

    project = _project(tmp_path)
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 8) | {'ca_tinh': 6},
            issues=[issue(line='N01', criterion='ca_tinh')])
    sr.record_review(project, sr.script_hash(project))
    _report(project, issues=[issue(issue_id='I2', line='N99', criterion='ca_tinh')])
    with pytest.raises(ValueError, match='N99'):
        sr.record_review(project, sr.script_hash(project))


def test_same_issue_twice_is_stuck():
    row = {'issues': [issue()], 'issue_statuses': {'I1': 'still_open'}}
    assert scoped.stuck([row, row]) == {'I1'}
    assert not scoped.stuck([row, {'issues': [], 'issue_statuses': {'I1': 'resolved'}}])


def test_script_round_two_packet_and_score_freezing_and_doctor_card(tmp_path):
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import script_review as sr
    from tests.workflows.test_script_review import _project, _report

    project = _project(tmp_path)
    path = sr.script_path(project)
    script = {'lines': [{'id': f'N{n:02}', 'text': f'UNCHANGED_{n}'} for n in range(1, 12)]}
    write_yaml_atomic(path, script)
    open_issue = issue(line='N06', criterion='ca_tinh')
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 8) | {'ca_tinh': 6}, issues=[open_issue])
    first = sr.record_review(project, sr.script_hash(project))
    path.write_bytes(path.read_bytes().replace(b'UNCHANGED_6', b'fixed'))
    packet = sr.incremental_context(project)
    assert 'I1' in packet and '+  text: fixed' in packet and 'UNCHANGED_1\n' not in packet
    # A reviewer attempting to reduce an accepted criterion cannot change that score.
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 1) | {'ca_tinh': 6}, issues=[open_issue])
    second = sr.record_review(project, sr.script_hash(project))
    assert second['scores']['hinh_anh'] == first['scores']['hinh_anh'] == 8
    from healthvideo.workflows import doctor_questions

    assert sr.next_script_action(project, root=tmp_path) == 'wait_doctor'
    question = doctor_questions.open_question(tmp_path, project.name)
    assert question is not None and question['station'] == '07' and question['kind'] == 'stuck_issue'
    assert read_yaml(project / 'revisions/001' / sr.LOG)['rounds'][-1]['passed'] is False


def test_script_direct_review_rejects_out_of_scope_edit(tmp_path):
    from healthvideo.workflows import script_review as sr
    from tests.workflows.test_script_review import _project, _report

    project = _project(tmp_path)
    _report(project, scores=dict.fromkeys(sr.CRITERIA, 8) | {'ca_tinh': 6},
            issues=[issue(line='N01', criterion='ca_tinh')])
    sr.record_review(project, sr.script_hash(project))
    path = sr.script_path(project)
    path.write_bytes(b'title: unauthorized\n' + path.read_bytes())
    _report(project)
    with pytest.raises(ValueError, match='scope'):
        sr.record_review(project, sr.script_hash(project))


@pytest.mark.parametrize('tamper', ['text', 'report'])
def test_writer_scope_violation_rolls_back_and_retries_once(tmp_path, tamper):
    from healthvideo.agents import AgentResult
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import script_review as sr
    from healthvideo.workflows.runner import run_queue
    from tests.workflows.test_script_review import _deps, _queue, _report

    project = _queue(tmp_path)
    _report(project, 6)
    sr.record_review(project, sr.script_hash(project))
    before = sr.script_path(project).read_bytes()
    calls = []

    def invoke(agents, prompt, *, log_dir, step, **kwargs):
        assert step == 'draft'
        calls.append(prompt)
        if len(calls) == 1:
            sr.script_path(project).write_bytes(b'title: unauthorized\n' + before)
            if tamper == 'report':
                path = project / 'revisions/001' / sr.LOG
                data = read_yaml(path)
                data['rounds'][-1]['passed'] = True
                data['rounds'][-1]['issues'] = []
                write_yaml_atomic(path, data)
        else:
            assert sr.script_path(project).read_bytes() == before
            assert 'Repair scope violation' in prompt
            sr.script_path(project).write_bytes(before.replace(
                b'text:', b'text: fixed '))
        return AgentResult(agents[0].cli, True, False, log_dir / 'test.log')

    report = run_queue(tmp_path, _deps({'value': WorkflowState.DRAFT_READY}, invoke), once=True)
    assert len(calls) == 2 and not report.blocked
    assert 'title: unauthorized' not in sr.script_path(project).read_text(encoding='utf-8')


def test_product_round_two_packet_boundaries_and_stuck(tmp_path):
    from healthvideo.workflows import product_review as pr
    from tests.workflows.test_product_review import REV, _project, _render, _report

    project = _project(tmp_path)
    posts = project / REV / 'posts/posts.yaml'
    posts.parent.mkdir(parents=True, exist_ok=True)
    posts.write_bytes(b'title: old\nkeep: exact\n')
    relative = posts.relative_to(tmp_path).as_posix()
    target = {'path': relative, 'start_line': 1, 'end_line': 1}
    open_issue = {'issue_id': 'P1', 'at': 'posts', 'criterion': 'bai_dang',
                  'problem': 'wrong title', 'fix': 'fix title', 'fixable': True, 'edits': [target]}
    scores = dict.fromkeys(pr.CRITERIA, 8) | {'bai_dang': 6}
    _report(project, scores=scores, issues=[open_issue])
    pr.record_review(project, pr.render_hash(project))
    before = pr.repair_files(project)
    posts.write_bytes(b'title: fixed\nkeep: exact\n')
    pr.check_repair(project, before)
    assert 'P1' in pr.incremental_context(project)
    posts.write_bytes(b'title: fixed\nkeep: BROKEN\n')
    with pytest.raises(ValueError, match='scope'):
        pr.check_repair(project, before)
    posts.write_bytes(b'title: fixed\nkeep: exact\n')
    _render(project, 2)
    _report(project, scores=scores, issues=[open_issue])
    pr.record_review(project, pr.render_hash(project))
    from healthvideo.workflows import doctor_questions

    assert pr.next_product_action(project, root=tmp_path) == 'wait_doctor'
    question = doctor_questions.open_question(tmp_path, project.name)
    assert question is not None and question['station'] == '12' and question['kind'] == 'stuck_issue'


def test_medical_rework_only_authorizes_explicit_ids(tmp_path):
    from healthvideo.workflows import rework, script_review
    from tests.workflows.test_script_review import _project

    project = _project(tmp_path)
    path = script_review.script_path(project)
    before = path.read_bytes()
    plan = rework.prepare(project, 'N01: sửa lời cho tự nhiên')
    assert plan['scope']['script/script.yaml'] == ['N01']
    path.write_bytes(before.replace(b'text:', b'text: fixed '))
    rework.check(project)
    path.write_bytes(b'title: changed\n' + path.read_bytes())
    with pytest.raises(ValueError, match='scope'):
        rework.check(project)


def test_byte_guard_preserves_crlf_and_does_not_allow_neighbor_rewrites():
    before = b'lines:\r\n- id: N01\r\n  text: keep\r\n- id: N02\r\n  text: old\r\n'
    scoped.check_script(before, before.replace(b'old', b'new'), {'N02'})
    with pytest.raises(ValueError, match='scope'):
        scoped.check_script(before, before.replace(b'\r\n', b'\n'), {'N02'})


def test_storyboard_retry_preserves_accepted_scenes_and_stops_same_issue(tmp_path):
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import rework
    from tests.workflows.test_script_review import _project

    project = _project(tmp_path)
    path = project / 'revisions/001/storyboard/storyboard.yaml'
    files = {'storyboard/storyboard.yaml': path}
    before = read_yaml(path)
    scene_id = before['scenes'][0]['id']
    rework.storyboard_failure(project, files, ValueError(f'{scene_id}: bad layout'))
    assert scene_id in rework.storyboard_context(project)
    before['scenes'][0]['narration'] += ' fixed'
    write_yaml_atomic(path, before)
    rework.check_storyboard(project, files)
    before['title'] = 'unauthorized'
    write_yaml_atomic(path, before)
    with pytest.raises(ValueError, match='scope'):
        rework.check_storyboard(project, files)
    rework.storyboard_failure(project, files, ValueError(f'{scene_id}: bad layout'))
    with pytest.raises(ValueError, match='Storyboard cần hướng dẫn'):
        rework.storyboard_context(project)
    with pytest.raises(ValueError, match='Storyboard cần hướng dẫn'):
        rework.check_storyboard(project, files)


@pytest.mark.parametrize('failure', ['quota', 'exception', 'failed_result'])
def test_failed_writer_invocation_restores_accepted_text(tmp_path, failure):
    from datetime import UTC, datetime, timedelta

    from healthvideo.agents import AgentResult, AllAgentsExhausted
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows import script_review as sr
    from healthvideo.workflows.runner import run_queue
    from tests.workflows.test_script_review import _deps, _queue, _report

    project = _queue(tmp_path)
    _report(project, 6)
    sr.record_review(project, sr.script_hash(project))
    before = sr.script_path(project).read_bytes()

    def invoke(agents, prompt, *, log_dir, **kwargs):
        sr.script_path(project).write_bytes(b'title: outside_scope\n' + before)
        if failure == 'quota':
            raise AllAgentsExhausted(datetime.now(UTC) + timedelta(hours=1))
        if failure == 'exception':
            raise RuntimeError('tool failed')
        return AgentResult(agents[0].cli, False, False, log_dir / 'failure.log')

    report = run_queue(tmp_path, _deps({'value': WorkflowState.DRAFT_READY}, invoke), once=True)
    assert sr.script_path(project).read_bytes() == before
    assert report.waiting_model if failure == 'quota' else report.blocked


def test_storyboard_scope_guard_preserves_concurrent_voice_save(tmp_path):
    from datetime import date

    from healthvideo.agents import AgentResult
    from healthvideo.domain.queue import QueueEntry
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import rework
    from healthvideo.workflows.runner import RunReport, _run_agent_invocation
    from tests.workflows.test_script_review import SLUG, _deps, _queue

    project = _queue(tmp_path)
    root = project / 'revisions/001'
    board = root / 'storyboard/storyboard.yaml'
    rework.storyboard_failure(project, {'storyboard/storyboard.yaml': board},
                              ValueError(read_yaml(board)['scenes'][0]['id'] + ': layout'))
    voice = root / 'script/voice-prep.yaml'
    voice.unlink(missing_ok=True)

    def invoke(agents, prompt, *, log_dir, **kwargs):
        voice.write_bytes(b'voice: sibling_save\n')
        return AgentResult(agents[0].cli, True, False, log_dir / 'success.log')

    entry = QueueEntry(slug=SLUG, title='Test', question='Why?', added=date(2026, 11, 17))
    result = _run_agent_invocation(tmp_path, _deps({}, invoke), entry, project, RunReport(),
                                   step='storyboard_design', brief_context='', log_dir=tmp_path / 'logs')
    assert result[0] == 'ok'
    assert voice.read_bytes() == b'voice: sibling_save\n'


def test_storyboard_retry_promotion_does_not_serialize_accepted_nodes(tmp_path, monkeypatch):
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import rework, storyboard_design
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    root = project / 'revisions/001'
    board = root / 'storyboard/storyboard.yaml'
    assets = root / 'assets/asset-manifest.yaml'
    data = read_yaml(board)
    for scene in data['scenes']:
        scene.pop('labels', None)
    write_yaml_atomic(board, data)
    rework.storyboard_failure(project, {'storyboard/storyboard.yaml': board,
                                       'assets/asset-manifest.yaml': assets},
                              ValueError(data['scenes'][0]['id'] + ': layout'))
    data['scenes'][0]['narration'] += ' fixed'
    write_yaml_atomic(board, data)
    expected = board.read_bytes()
    monkeypatch.setattr(storyboard_design, '_validate', lambda *args, **kwargs: [])
    monkeypatch.setattr(storyboard_design, 'validate_estimated_layout', lambda *args, **kwargs: None)
    storyboard_design.submit_storyboard_design(project, board, assets)
    assert board.read_bytes() == expected


def test_allowed_scene_ids_extracts_from_at_and_edits_only_when_fixable():
    from healthvideo.workflows.product_review import _allowed_scene_ids

    issues = [
        {'at': 'S42@04:37-04:50', 'criterion': 'hinh_khop_loi', 'fixable': True, 'edits': []},
        {'at': 'S03, S08, S20, S24', 'criterion': 'nhip_dung', 'fixable': True, 'edits': []},
        {'at': 'S99@01:00', 'criterion': 'hinh_ro', 'fixable': False, 'edits': []},
        {
            'at': 'posts',
            'criterion': 'bai_dang',
            'fixable': True,
            'edits': [{'path': 'video/src/anatomy/S12Helper.tsx', 'start_line': 1, 'end_line': 2}],
        },
    ]
    assert _allowed_scene_ids(issues) == {'S42', 'S03', 'S08', 'S20', 'S24'}

    with_scene_edit = [
        {
            'at': 'layout',
            'criterion': 'hinh_ro',
            'fixable': True,
            'edits': [{'path': 'scenes/S15/card.tsx', 'start_line': 1, 'end_line': 5}],
        }
    ]
    assert _allowed_scene_ids(with_scene_edit) == {'S15'}


def test_repair_files_and_snapshot_filtering(tmp_path):
    from healthvideo.workflows import product_review as pr
    from tests.workflows.test_product_review import REV, _project, _report

    project = _project(tmp_path)
    anatomy = tmp_path / 'video/src/anatomy'
    components = tmp_path / 'video/src/components'
    scenes = tmp_path / 'video/src/scenes'
    for directory in (anatomy, components, scenes):
        directory.mkdir(parents=True)
    (anatomy / 'ArterySection.tsx').write_text('export const Artery = 1;\n', encoding='utf-8')
    (anatomy / 'Heart.tsx').write_text('export const Heart = 1;\n', encoding='utf-8')
    (anatomy / 'Heart.test.tsx').write_text('test("heart", () => {});\n', encoding='utf-8')
    (anatomy / 'Unused.tsx').write_text('export const Unused = 1;\n', encoding='utf-8')
    (components / 'VisualAsset.tsx').write_text('export const VA = 1;\n', encoding='utf-8')
    (scenes / 'OutroScene.tsx').write_text('export const Outro = 1;\n', encoding='utf-8')
    (scenes / 'OutroScene.test.tsx').write_text('test("outro", () => {});\n', encoding='utf-8')

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'hinh_ro': 6},
        issues=[{
            'at': 'S36',
            'criterion': 'hinh_ro',
            'problem': 'Test fail.',
            'fix': 'Update test scope.',
            'fixable': True,
            'edits': [{'path': 'video/src/scenes/OutroScene.test.tsx', 'start_line': 1, 'end_line': 1}],
        }],
    )
    entry = pr.record_review(project, pr.render_hash(project))
    captured = pr.repair_files(project)
    assert 'video/src/anatomy/ArterySection.tsx' in captured
    assert 'video/src/components/VisualAsset.tsx' in captured
    assert 'video/src/scenes/OutroScene.test.tsx' in captured
    assert 'video/src/anatomy/Heart.test.tsx' not in captured

    snap = entry['snapshot']
    assert 'video/src/anatomy/ArterySection.tsx' in snap
    assert 'video/src/scenes/OutroScene.test.tsx' in snap
    assert 'video/src/anatomy/Unused.tsx' not in snap
    assert 'video/src/components/VisualAsset.tsx' not in snap
    assert f'projects/{project.name}/{REV.as_posix()}/storyboard/storyboard.yaml' in snap


def test_product_repair_blocks_unflagged_scene_and_narration_and_allows_outro_when_open(tmp_path):
    from healthvideo.storage.files import read_yaml, write_yaml_atomic
    from healthvideo.workflows import product_review as pr
    from tests.workflows.test_product_review import REV, _project, _report

    project = _project(tmp_path)
    (tmp_path / 'video/src/scenes').mkdir(parents=True)
    outro = tmp_path / 'video/src/scenes/OutroScene.tsx'
    outro.write_text('export const Outro = 1;\n', encoding='utf-8')

    _report(
        project,
        scores={**dict.fromkeys(pr.CRITERIA, 8), 'mo_ket': 5},
        issues=[{
            'at': 'S02',
            'criterion': 'mo_ket',
            'problem': 'Logo outro mờ.',
            'fix': 'Tăng tương phản.',
            'fixable': True,
        }],
    )
    pr.record_review(project, pr.render_hash(project))
    before = pr.repair_files(project)

    outro.write_text('export const Outro = 2;\n', encoding='utf-8')
    pr.check_repair(project, before)

    sb_path = project / REV / 'storyboard/storyboard.yaml'
    orig_sb = sb_path.read_bytes()
    sb = read_yaml(sb_path)
    sb['scenes'][0]['on_screen_text'] = 'Unauthorized S01'
    write_yaml_atomic(sb_path, sb)
    with pytest.raises(ValueError, match='Repair scope violation'):
        pr.check_repair(project, before)
    sb_path.write_bytes(orig_sb)

    sb = read_yaml(sb_path)
    sb['scenes'][1]['claim_id'] = 'C999'
    write_yaml_atomic(sb_path, sb)
    with pytest.raises(ValueError, match='Repair scope violation'):
        pr.check_repair(project, before)


def test_safety_issue_cannot_be_downgraded():
    from healthvideo.workflows.scoped_review import reconcile
    prior = {'scores': {'safe': 3}, 'issues': [
        {'line': 'N01', 'criterion': 'safe', 'issue_id': 'safety', 'blocking_safety': True}]}
    report = {'scores': {'safe': 8}, 'issues': [
        {'line': 'N01', 'criterion': 'safe', 'issue_id': 'safety', 'blocking_safety': False}]}
    assert reconcile(prior, report, 'line')['issues'][0]['blocking_safety'] is True


def test_medical_note_line_range_names_every_line_inside(tmp_path):
    # PYH-001 2026-11-27: "chọn trong N01–N53" scoped only N01 and N53.
    from healthvideo.storage.files import read_yaml
    from healthvideo.workflows import rework
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects')
    ids = [line['id'] for line in read_yaml(project / 'revisions/001/script/script.yaml')['lines']]
    numbered = ids[:-1]  # the fixture ends with a non-numbered OUTRO line
    plan = rework.prepare(project, f'Biên kịch tự chọn trong {numbered[0]}–{numbered[-1]}.')
    assert plan['scope']['script/script.yaml'] == numbered
    single = rework.prepare(project, f'Chỉ sửa {ids[0]}.')
    assert single['scope']['script/script.yaml'] == [ids[0]]
