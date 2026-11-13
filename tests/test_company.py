"""Company roles and model tiers loaded from profiles/company.yaml."""

from pathlib import Path

import pytest
import yaml

from healthvideo.company import (
    COMPANY_PATH,
    REPO_ROOT,
    SKILL_RULE,
    ModelSlot,
    load_company,
    role_skill_block,
)
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
    data['roles']['medical_expert']['steps'].append('draft')
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
    data['roles']['medical_expert']['steps'] = []
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


def test_every_role_skill_exists():
    company = load_company()
    for role in company.roles.values():
        for skill in role.skills:
            assert (REPO_ROOT / '.agents/skills' / skill / 'SKILL.md').is_file(), (role.id, skill)


def test_role_skills_follow_spec_table():
    # Spec 2026-11-08 §5.3 + §5.8: researcher became medical_expert.
    expected = {
        'coordinator': [],
        'coordinator_senior': [],
        'scout': ['content-strategy'],
        'medical_expert': ['systematic-literature-review'],
        'writer': ['youtube-scriptwriting', 'short-form-video'],
        'script_critic': ['copy-editing'],
        'art_director': ['scripting-and-storyboarding', 'visual-style'],
        'editor': ['remotion-best-practices', 'motion-design'],
        'product_critic': ['video-understand', 'character-animation-qa'],
        'copywriter': ['social'],
        'feedback_analyst': [],
    }
    company = load_company()
    assert {role_id: role.skills for role_id, role in company.roles.items()} == expected


def test_split_script_roles_have_new_names():
    company = load_company()
    assert 'researcher' not in company.roles
    assert company.role_for_step('research').id == 'medical_expert'
    assert company.roles['medical_expert'].name == 'Chuyên gia y học'
    assert company.roles['writer'].name == 'Biên kịch viral'


def test_role_without_skills_has_no_block():
    assert role_skill_block('coordinator') == ''


def test_role_skill_block_lists_skill_paths():
    block = role_skill_block('writer')
    assert block.startswith('## Skill của vai: Biên kịch viral')
    assert '- .agents/skills/youtube-scriptwriting/SKILL.md' in block
    assert '- .agents/skills/short-form-video/SKILL.md' in block
    assert SKILL_RULE in block


@pytest.mark.parametrize('skills', [['../evil'], ['a/b'], ['a', 'b', 'c', 'd']])
def test_bad_skill_list_rejected(tmp_path, skills):
    data = _raw()
    data['roles']['writer']['skills'] = skills
    with pytest.raises(ValueError):
        load_company(_write(tmp_path, data))


def test_old_single_skill_field_rejected(tmp_path):
    data = _raw()
    data['roles']['writer']['skill'] = '.agents/skills/pyh-writer/SKILL.md'
    with pytest.raises(ValueError, match='không hợp lệ'):
        load_company(_write(tmp_path, data))


def test_model_slot_is_frozen_and_hashable():
    slot = ModelSlot(cli='codex', model='gpt-6-astra')
    assert {slot: True}[ModelSlot(cli='codex', model='gpt-6-astra')]
    with pytest.raises(ValueError):
        slot.model = 'changed'
