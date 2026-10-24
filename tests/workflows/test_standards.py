from datetime import datetime

import pytest

from healthvideo.workflows import standards


def test_record_appends_and_skips_empty(tmp_path):
    assert standards.record(tmp_path, slug='a', gate='medical', revision='001', kind='reject', text='  ') is None
    standards.record(tmp_path, slug='a', gate='medical', revision='001', kind='reject', text='Sửa N07',
                     at=datetime(2026, 10, 24, 21, 0).astimezone())
    standards.record(tmp_path, slug='a', gate='video', revision='001', kind='comment',
                     items=[{'target': 'video', 'text': 'Giọng quá đều'}, {'target': 'x', 'text': ' '}])
    entries = standards.load(tmp_path)
    assert [e['kind'] for e in entries] == ['reject', 'comment']
    assert entries[1]['items'] == [{'target': 'video', 'text': 'Giọng quá đều'}]


def test_record_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError, match='không hợp lệ'):
        standards.record(tmp_path, slug='a', gate='g', revision='1', kind='publish', text='x')


def test_compose_reason_joins_general_and_items():
    reason = standards.compose_reason('Chung', [{'target': 'N07', 'text': 'cắt đuôi'}, {'target': '', 'text': 'gọn'}])
    assert reason == 'Chung\n- N07: cắt đuôi\n- gọn'
    assert standards.compose_reason(' ', []) == ''


def test_prompt_block_newest_first_within_budget(tmp_path, monkeypatch):
    assert standards.prompt_block(tmp_path) == ''
    for index in range(30):
        standards.record(tmp_path, slug='a', gate='medical', revision='001', kind='reject',
                         text=f'góp ý số {index} ' + 'x' * 200)
    monkeypatch.setattr(standards, 'PROMPT_CHAR_BUDGET', 1500)
    block = standards.prompt_block(tmp_path)
    assert block.startswith('## Chuẩn của bác sĩ')
    assert block.index('góp ý số 29') < block.index('góp ý số 28')
    assert 'góp ý số 0 ' not in block
    assert 'góp ý cũ hơn' in block
    assert len(block) < 1800


def test_reject_gate_remembers_reason(tmp_path):
    from healthvideo.domain.gate_review import GateKind
    from healthvideo.domain.project_v2 import WorkflowState
    from healthvideo.workflows.gate_review import reject_gate
    from tests.helpers import create_v2_project_fixture

    project = create_v2_project_fixture(tmp_path / 'projects', state='awaiting_medical_review')
    reject_gate(project, GateKind.MEDICAL, reviewer='Tu', reason='M11 đổi nguồn sang NIAMS',
                resume_state=WorkflowState.DRAFT_READY, now=datetime.now().astimezone())
    entries = standards.load(tmp_path)
    assert entries[-1]['kind'] == 'reject'
    assert entries[-1]['slug'] == project.name
    assert entries[-1]['text'] == 'M11 đổi nguồn sang NIAMS'
