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
        first = company.chain(role_id)[0]
        assert first in company.tiers['bulk']
        # agy's Orchestrator sizes the model itself (2026-11-13); any other first slot stays light.
        assert first.model == 'gemini-pro-orchestrator' or first not in company.tiers['hard']


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
    # Standardized skills per role (task 3.7): each role has 1-3 skills tailored to its step.
    expected = {
        'coordinator': ['pyh-coordinator'],
        'coordinator_senior': ['pyh-coordinator', 'pyh-coordinator-senior'],
        'scout': ['content-strategy', 'pyh-scout'],
        'medical_expert': ['pyh-medical-expert'],
        'writer': ['youtube-scriptwriting', 'short-form-video', 'pyh-writer'],
        'script_critic': ['copy-editing', 'pyh-script-critic'],
        'art_director': ['pyh-art-director'],
        'editor': ['remotion-best-practices', 'motion-design', 'pyh-editor'],
        'product_critic': ['character-animation-qa', 'pyh-product-critic'],
        'copywriter': ['social', 'pyh-copywriter'],
        'feedback_analyst': ['pyh-feedback-analyst'],
    }
    company = load_company()
    assert {role_id: role.skills for role_id, role in company.roles.items()} == expected
    assert all(1 <= len(skills) <= 3 for skills in expected.values())


def test_split_script_roles_have_new_names():
    company = load_company()
    assert 'researcher' not in company.roles
    assert company.role_for_step('research').id == 'medical_expert'
    assert company.roles['medical_expert'].name == 'Chuyên gia y học'
    assert company.roles['writer'].name == 'Biên kịch viral'


def test_role_without_skills_has_no_block():
    company = load_company()
    company.roles['coordinator'].skills = []
    assert role_skill_block('coordinator', company) == ''


def test_role_skill_block_lists_skill_paths():
    block = role_skill_block('writer')
    assert block.startswith('## Skill của vai: Biên kịch viral')
    assert '- .agents/skills/youtube-scriptwriting/SKILL.md' in block
    assert '- .agents/skills/short-form-video/SKILL.md' in block
    assert '- .agents/skills/pyh-writer/SKILL.md' in block
    assert SKILL_RULE in block


def test_writer_and_critic_skills_reference_doctor_principles():
    for skill in ('pyh-writer', 'pyh-script-critic'):
        text = (REPO_ROOT / '.agents/skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
        assert 'profiles/doctor-feedback.yaml' in text
        assert 'slug: chung' in text


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
