"""Company roles and model tiers loaded from profiles/company.yaml."""

from pathlib import Path

import pytest
import yaml

from healthvideo.company import COMPANY_PATH, ModelSlot, load_company
from healthvideo.workflows.runner import AGENT_STEPS


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / 'company.yaml'
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
    return path


def _raw() -> dict:
    return yaml.safe_load(COMPANY_PATH.read_text(encoding='utf-8'))


def test_every_agent_step_has_exactly_one_role():
    company = load_company()
    for step in AGENT_STEPS:
        owners = [role.id for role in company.roles.values() if step in role.steps]
        assert len(owners) == 1, step
        assert company.role_for_step(step).id == owners[0]


def test_critic_first_slot_differs_from_maker():
    company = load_company()
    assert company.chain('script_critic')[0] != company.chain('writer')[0]
    assert company.chain('product_critic')[0] != company.chain('editor')[0]


def test_chain_uses_override_then_tier():
    company = load_company()
    assert company.chain('script_critic')[0] == ModelSlot(cli='codex', model='gpt-6.1-sol')
    assert company.chain('writer') == company.tiers['hard']


def test_duplicate_step_rejected(tmp_path):
    data = _raw()
    data['roles']['researcher']['steps'].append('draft')
    with pytest.raises(ValueError, match='draft'):
        load_company(_write(tmp_path, data))


def test_unknown_cli_rejected(tmp_path):
    data = _raw()
    data['tiers']['bulk'][0]['cli'] = 'gemini'
    with pytest.raises(ValueError):
        load_company(_write(tmp_path, data))


def test_bulk_roles_never_start_on_hard_tier():
    company = load_company()
    for role_id in ('copywriter', 'scout'):
        assert company.chain(role_id)[0] in company.tiers['bulk']
        assert company.chain(role_id)[0] not in company.tiers['hard']


def test_missing_agent_step_rejected(tmp_path):
    data = _raw()
    data['roles']['researcher']['steps'] = []
    with pytest.raises(ValueError, match='research'):
        load_company(_write(tmp_path, data))


def test_empty_override_rejected(tmp_path):
    data = _raw()
    data['roles']['writer']['models'] = []
    with pytest.raises(ValueError):
        load_company(_write(tmp_path, data))


@pytest.mark.parametrize('content', ['roles: {writer: 42}', 'roles: []', '42'])
def test_malformed_structure_is_vietnamese_value_error(tmp_path, content):
    path = tmp_path / 'company.yaml'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='không hợp lệ'):
        load_company(path)


def test_model_slot_is_frozen_and_hashable():
    slot = ModelSlot(cli='codex', model='gpt-6-astra')
    assert {slot: True}[ModelSlot(cli='codex', model='gpt-6-astra')]
    with pytest.raises(ValueError):
        slot.model = 'changed'
