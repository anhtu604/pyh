"""Regression tests for M3a incidents (PYH-001/S25, rework scope, playbook guards, outro normalization)."""

from __future__ import annotations

import yaml

from healthvideo.domain.hook_outro import CHANNEL_OUTRO_TEXT
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows import (
    chat,
    dashboard,
    doctor_questions,
    factory,
    playbook,
    repair_service,
    rework,
    storyboard_parts,
)
from healthvideo.workflows.storyboard_design import (
    normalize_outro,
    storyboard_validation_error,
    submit_storyboard_design,
)
from tests.helpers import create_v2_project_fixture


def test_pre_gate_legacy_storyboard_auto_migrates_and_isolates_drifted_scene(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    root = project / 'revisions/001'
    board_path = root / 'storyboard/storyboard.yaml'
    original_board_bytes = board_path.read_bytes()

    # Simulate PYH-001/S25: writer edits one script line after storyboard already exists.
    script_path = root / 'script/script.yaml'
    script_data = read_yaml(script_path)
    target_idx = 1
    script_data['lines'][target_idx]['text'] = 'Lời thoại đã được biên kịch chỉnh sửa sau kiểm duyệt.'
    write_yaml_atomic(script_path, script_data)

    assert not (root / 'storyboard/parts').exists()
    assert storyboard_parts.enabled(root) is True
    assert (root / 'storyboard/parts').is_dir()
    assert (root / storyboard_parts.METADATA).is_file()
    # Original monolithic storyboard.yaml must remain untouched.
    assert board_path.read_bytes() == original_board_bytes

    details = storyboard_parts.part_details(root)
    expected_invalid = f'S{target_idx + 1:02}'
    invalid_ids = [sid for sid, (status, _) in details.items() if status == 'invalid']
    ok_ids = [sid for sid, (status, _) in details.items() if status == 'ok']
    assert invalid_ids == [expected_invalid]
    assert len(ok_ids) == len(script_data['lines']) - 1
    assert 'narration' in details[expected_invalid][1]

    prompt = storyboard_parts.prompt_context(root)
    pending_section = prompt.split('pending:', 1)[1]
    assert f'{expected_invalid}:' in pending_section
    for ok_id in ok_ids:
        assert f'{ok_id}:' not in pending_section
        assert ok_id in prompt


def test_post_gate_legacy_storyboard_is_not_split(tmp_path):
    for state in (
        WorkflowState.AWAITING_MEDICAL_REVIEW,
        WorkflowState.MEDICALLY_APPROVED,
        WorkflowState.PRODUCTION_IN_PROGRESS,
    ):
        project = create_v2_project_fixture(tmp_path / state.value, state=WorkflowState.DRAFT_READY)
        manifest = read_yaml(project / 'project.yaml')
        manifest['state'] = state.value
        write_yaml_atomic(project / 'project.yaml', manifest)
        root = project / 'revisions/001'
        assert storyboard_parts.enabled(root) is False
        assert not (root / 'storyboard/parts').exists()


def test_rework_auto_locates_mismatched_scene_and_line_id_without_scene_id_in_error(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    root = project / 'revisions/001'
    board_path = root / 'storyboard/storyboard.yaml'
    script_path = root / 'script/script.yaml'

    # Drift scene 2 narration vs script line 2.
    script_data = read_yaml(script_path)
    script_data['lines'][1]['text'] = 'Câu lời thoại mới khiến cảnh 2 lệch.'
    write_yaml_atomic(script_path, script_data)

    # Error message has NO scene ID at all (like original PYH-001 failure).
    rework.storyboard_failure(
        project,
        {'storyboard/storyboard.yaml': board_path},
        ValueError('M6.4 line and scene mismatch'),
    )
    plan = read_yaml(root / rework.STORYBOARD_PLAN)
    expected_scene_id = read_yaml(board_path)['scenes'][1]['id']
    assert plan['scope']['storyboard/storyboard.yaml'] == [expected_scene_id]
    assert plan['still_open_rounds'] == 1
    ctx = rework.storyboard_context(project)
    assert expected_scene_id in ctx

    # Simulate previous plan had empty scope -> newly located scope must reset still_open_rounds to 1.
    plan['scope']['storyboard/storyboard.yaml'] = []
    plan['still_open_rounds'] = 2
    write_yaml_atomic(root / rework.STORYBOARD_PLAN, plan)
    rework.storyboard_failure(
        project,
        {'storyboard/storyboard.yaml': board_path},
        ValueError('M6.4 line and scene mismatch'),
    )
    updated = read_yaml(root / rework.STORYBOARD_PLAN)
    assert updated['scope']['storyboard/storyboard.yaml'] == [expected_scene_id]
    assert updated['still_open_rounds'] == 1

    # Same issue_id AND same scope increments still_open_rounds.
    rework.storyboard_failure(
        project,
        {'storyboard/storyboard.yaml': board_path},
        ValueError('M6.4 line and scene mismatch'),
    )
    assert read_yaml(root / rework.STORYBOARD_PLAN)['still_open_rounds'] == 2


def test_rework_maps_line_id_in_error_to_scene(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    root = project / 'revisions/001'
    board_path = root / 'storyboard/storyboard.yaml'
    script_data = read_yaml(root / 'script/script.yaml')
    first_line_id = script_data['lines'][0]['id']
    first_scene_id = read_yaml(board_path)['scenes'][0]['id']

    rework.storyboard_failure(
        project,
        {'storyboard/storyboard.yaml': board_path},
        ValueError(f'Line reference {first_line_id} failed alignment'),
    )
    plan = read_yaml(root / rework.STORYBOARD_PLAN)
    assert plan['scope']['storyboard/storyboard.yaml'] == [first_scene_id]


def test_dashboard_does_not_learn_from_inferred_role_and_slug_scopes_match_rule(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    (tmp_path / 'topics/logs' / project.name).mkdir(parents=True)
    sig = 'repair:valueerror:inferred_role_guard_test'

    monkeypatch.setattr(repair_service, '_release', lambda root, slug: None)
    monkeypatch.setattr(factory, 'wake_background', lambda root: None)
    monkeypatch.setattr(chat, 'start', lambda *args, **kwargs: None)

    # 1. Doctor answers reopen_or_delegate with text -> role is inferred -> MUST NOT learn rule.
    q1 = doctor_questions.ask(
        tmp_path,
        project.name,
        station='repair',
        kind='escalation',
        question='Storyboard lệch lời cảnh S25',
        options=[
            {'id': 'reopen_or_delegate', 'label': 'Giao lại xử lý', 'detail': 'Nhập hướng dẫn'},
            {'id': 'pause_project', 'label': 'Tạm dừng', 'detail': 'Để xem sau'},
        ],
        signature=sig,
    )
    dashboard.answer_doctor_question(
        tmp_path,
        project.name,
        {
            'question_id': q1['id'],
            'option_id': 'reopen_or_delegate',
            'text': 'Sửa lại đúng cảnh S25.',
            'expected_revision': '001',
        },
    )
    assert playbook.match_rule(tmp_path, station='repair', signature=sig) is None
    assert playbook.load_playbook(tmp_path).rules == []

    # 2. Doctor selects explicit delegate_role option -> learns rule scoped to project.name.
    q2 = doctor_questions.ask(
        tmp_path,
        project.name,
        station='repair',
        kind='escalation',
        question='Storyboard lệch lời cảnh S25',
        options=[
            {
                'id': 'opt-sb',
                'label': 'Giao đạo diễn hình ảnh sửa S25',
                'detail': 'Chỉ sửa S25',
                'action': 'delegate',
                'delegate_role': 'storyboard_director',
                'direction': 'Chỉ sửa cảnh S25 cho khớp lời.',
            },
            {'id': 'pause_project', 'label': 'Tạm dừng', 'detail': 'Để xem sau'},
        ],
        signature=sig,
    )
    dashboard.answer_doctor_question(
        tmp_path,
        project.name,
        {
            'question_id': q2['id'],
            'option_id': 'opt-sb',
            'text': '',
            'expected_revision': '001',
        },
    )
    matched_a = playbook.match_rule(tmp_path, station='repair', signature=sig, slug=project.name)
    assert matched_a is not None
    assert matched_a.slug == project.name
    assert matched_a.delegate_role == 'storyboard_director'

    # Rule with slug A must NOT match project B.
    assert playbook.match_rule(tmp_path, station='repair', signature=sig, slug='other-project-b') is None

    # General rule (slug=None) still matches any project.
    general_sig = 'repair:valueerror:general_seed_rule'
    playbook.append_rule(
        tmp_path,
        source='seed',
        station='repair',
        signature=general_sig,
        action='retry_cycle',
        direction='Thử lại chu kỳ.',
        slug=None,
    )
    assert playbook.match_rule(tmp_path, station='repair', signature=general_sig, slug='other-project-b') is not None


def test_normalize_outro_on_submit_and_parts_assemble(tmp_path):
    project = create_v2_project_fixture(tmp_path / 'projects', state=WorkflowState.DRAFT_READY)
    root = project / 'revisions/001'
    script_path = root / 'script/script.yaml'
    board_path = root / 'storyboard/storyboard.yaml'
    assets_path = root / 'assets/asset-manifest.yaml'

    # Verify script ends with pinned outro text (fixture already uses OUTRO_TEXT or CHANNEL_OUTRO_TEXT).
    script_data = read_yaml(script_path)
    script_data['lines'][-1]['text'] = CHANNEL_OUTRO_TEXT
    write_yaml_atomic(script_path, script_data)

    # Corrupt the final scene with wrong visual, claim_id, and source_marker.
    board_data = read_yaml(board_path)
    board_data['scenes'][-1]['narration'] = CHANNEL_OUTRO_TEXT
    board_data['scenes'][-1]['visual'] = 'whiteboard'
    board_data['scenes'][-1]['claim_id'] = 'C01'
    board_data['scenes'][-1]['source_marker'] = '[R01]'
    submitted_board = tmp_path / 'submitted-storyboard.yaml'
    submitted_board.write_text(yaml.safe_dump(board_data, allow_unicode=True, sort_keys=False), encoding='utf-8')

    # Direct helper check
    normalized = normalize_outro(board_data, script_data)
    assert normalized['scenes'][-1]['visual'] == 'brand_outro'
    assert normalized['scenes'][-1]['claim_id'] is None
    assert normalized['scenes'][-1]['source_marker'] is None

    # Submit via submit_storyboard_design succeeds and writes normalized outro.
    submit_storyboard_design(project, submitted_board, assets_path)
    saved = read_yaml(board_path)
    assert saved['scenes'][-1]['visual'] == 'brand_outro'
    assert saved['scenes'][-1]['claim_id'] is None
    assert saved['scenes'][-1]['source_marker'] is None
    assert storyboard_validation_error(project) is None

    # Parts mode assemble also normalizes final scene before validation.
    assert storyboard_parts.enabled(root) is True
    last_id = f"S{len(saved['scenes']):02}"
    last_part_path = root / f'storyboard/parts/{last_id}.yaml'
    last_part = read_yaml(last_part_path)
    last_part['visual'] = 'whiteboard'
    last_part['on_screen_text'] = 'Cảm ơn bạn'
    last_part['source_marker'] = '[R01]'
    write_yaml_atomic(last_part_path, last_part)

    assert storyboard_parts.assemble(root) == []
    reassembled = read_yaml(board_path)
    assert reassembled['scenes'][-1]['visual'] == 'brand_outro'
    assert reassembled['scenes'][-1]['claim_id'] is None
    assert reassembled['scenes'][-1]['source_marker'] is None
