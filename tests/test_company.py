"""Company roles and model tiers loaded from profiles/company.yaml."""

from pathlib import Path

import pytest
import yaml

from healthvideo.company import (
    COMPANY_PATH,
    CRITIC_OF,
    REPO_ROOT,
    SKILL_RULE,
    SKILL_SECTION_GUIDES,
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
    assert company.chain('script_critic')[0] == ModelSlot(cli='codex', model='gpt-6.1-terra')
    assert company.chain('writer')[0] == ModelSlot(cli='codex', model='gpt-6.1-sol')
    assert company.chain('medical_expert')[0] == ModelSlot(cli='agy', model='gemini-4-neon-medium')
    assert company.chain('scout') == company.tiers['bulk']


def test_every_role_uses_verified_direct_models_and_safe_fallbacks():
    company = load_company()
    for chain in [*company.tiers.values(), *(company.chain(r) for r in company.roles)]:
        assert chain[0].cli in {'agy', 'codex'}
        assert len(set(chain)) == len(chain)
        for slot in chain:
            assert slot.cli != 'claude'
            assert not any(banned in slot.model.lower() for banned in (
                'opus', 'astra', 'carbon-high', 'orchestrator', 'auto/',
            ))


def test_r534_primary_assignment_and_critic_independence():
    company = load_company()
    sol = {'writer', 'art_director', 'product_critic', 'coordinator_senior', 'repair_engineer'}
    for role in company.roles:
        expected = ('codex', 'gpt-6.1-sol') if role in sol else ('agy', 'gemini-4-neon-medium')
        if role == 'script_critic':
            expected = ('codex', 'gpt-6.1-terra')
        assert company.chain(role)[0].model_identity == expected, role
    for critic, makers in {**CRITIC_OF, 'art_director': ('storyboard_director',)}.items():
        for maker in makers:
            assert company.chain(critic)[0].model_identity != company.chain(maker)[0].model_identity
            assert {slot.model_identity for slot in company.chain(critic)}.isdisjoint(
                slot.model_identity for slot in company.chain(maker)
            ), (critic, maker)


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
        assert first.model == 'gemini-4-neon-medium'


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
    # Company 2.0 standardized 16-role skills (1-3 skills per role).
    expected = {
        'coordinator': ['pyh-coordinator'],
        'coordinator_senior': ['pyh-coordinator', 'pyh-coordinator-senior'],
        'researcher': ['content-strategy', 'pyh-researcher'],
        'scout': ['content-strategy', 'pyh-scout'],
        'medical_expert': ['pyh-medical-expert'],
        'writer': ['youtube-scriptwriting', 'short-form-video', 'pyh-writer'],
        'storyboard_director': ['scripting-and-storyboarding', 'visual-style', 'pyh-storyboard-director'],
        'voice_director': ['pyh-voice-director'],
        'script_critic': ['copy-editing', 'pyh-script-critic'],
        'art_director': ['pyh-art-director'],
        'editor': ['remotion-best-practices', 'motion-design', 'pyh-editor'],
        'product_critic': ['character-animation-qa', 'pyh-product-critic'],
        'copywriter': ['social', 'copy-editing', 'pyh-copywriter'],
        'shorts_producer': ['short-form-video', 'social', 'pyh-shorts-producer'],
        'feedback_analyst': ['pyh-feedback-analyst'],
        'repair_engineer': ['pyh-repair-engineer'],
    }
    company = load_company()
    assert {role_id: role.skills for role_id, role in company.roles.items()} == expected
    assert all(1 <= len(skills) <= 3 for skills in expected.values())
    assert all('systematic-literature-review' not in role.skills for role in company.roles.values())


def test_split_script_roles_have_new_names():
    company = load_company()
    assert len(company.roles) == 16
    assert 'researcher' in company.roles
    assert 'repair_engineer' in company.roles
    assert company.role_for_step('topic_research').id == 'researcher'
    assert company.role_for_step('channel_analytics').id == 'researcher'
    assert company.role_for_step('research').id == 'medical_expert'
    assert company.role_for_step('repair').id == 'repair_engineer'
    assert company.roles['medical_expert'].name == 'Chuyên gia y học'
    assert company.roles['writer'].name == 'Biên kịch viral'
    assert company.roles['coordinator'].name == 'Trưởng nhóm Điều phối'
    assert company.roles['repair_engineer'].name == 'Kỹ sư sửa lỗi'


def test_critic_of_invariant_for_all_makers_and_no_banned_models():
    company = load_company()
    for critic_id, maker_ids in CRITIC_OF.items():
        critic_first = company.chain(critic_id)[0]
        for maker_id in maker_ids:
            maker_first = company.chain(maker_id)[0]
            assert critic_first.model_identity != maker_first.model_identity, (critic_id, maker_id)
    for role_id in company.roles:
        for slot in company.chain(role_id):
            assert 'opus' not in slot.model.lower()
            assert 'astra' not in slot.model.lower()


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


def test_skill_section_guides_cover_general_skills_and_scope_role_blocks():
    expected_guided = {
        'content-strategy',
        'copy-editing',
        'social',
        'youtube-scriptwriting',
        'short-form-video',
        'scripting-and-storyboarding',
        'visual-style',
        'motion-design',
        'remotion-best-practices',
        'character-animation-qa',
    }
    assert expected_guided <= SKILL_SECTION_GUIDES.keys()
    assert 'Binge Loop' in role_skill_block('writer')
    assert 'Buyer Stage' in role_skill_block('researcher')
    assert 'Studio' in role_skill_block('editor')
    assert 'npm run sfx' in role_skill_block('editor')
    assert 'Playwright' in role_skill_block('product_critic')
    assert 'Publishing' in role_skill_block('copywriter')
    assert 'Sweep 4' in role_skill_block('script_critic')


def test_r35_pyh_skills_alignment_and_writer_ownership():
    skills_dir = REPO_ROOT / '.agents/skills'
    writer_skill = (skills_dir / 'pyh-writer/SKILL.md').read_text(encoding='utf-8')
    assert 'storyboard_director' in writer_skill
    assert 'script/script.yaml' in writer_skill
    assert 'script/outline.yaml' in writer_skill
    assert '`slug: chung` hiện hành' in writer_skill

    researcher_skill = (skills_dir / 'pyh-researcher/SKILL.md').read_text(encoding='utf-8')
    for key in ('viral_engagement', 'urgency_prevention', 'evidence_readiness', 'short_feasibility'):
        assert key in researcher_skill

    assert 'CoordinatorReply' in (skills_dir / 'pyh-coordinator/SKILL.md').read_text(encoding='utf-8')
    senior = (skills_dir / 'pyh-coordinator-senior/SKILL.md').read_text(encoding='utf-8')
    assert 'repair_diagnose' in senior and 'CoordinatorReply' in senior
    assert 'không tự gán GRADE' in (skills_dir / 'pyh-medical-expert/SKILL.md').read_text(encoding='utf-8')
    assert 'resolved_issues' in (skills_dir / 'pyh-script-critic/SKILL.md').read_text(encoding='utf-8')
    assert 'voice-prep-cache.yaml' in (skills_dir / 'pyh-voice-director/SKILL.md').read_text(encoding='utf-8')
    assert 'không lặp dựng lại bản không đổi' in (skills_dir / 'pyh-editor/SKILL.md').read_text(encoding='utf-8')
    assert 'trích ý bác sĩ' in (skills_dir / 'pyh-feedback-analyst/SKILL.md').read_text(encoding='utf-8')
    assert 'không nạp toàn bộ thư mục log' in (skills_dir / 'pyh-repair-engineer/SKILL.md').read_text(encoding='utf-8')
    assert 'phiên điều hành' in (skills_dir / 'pyh/SKILL.md').read_text(encoding='utf-8')
    assert 'discover' in (skills_dir / 'pyh-scout/SKILL.md').read_text(encoding='utf-8')

    draft_prompt = (REPO_ROOT / 'src/healthvideo/prompts/draft.md').read_text(encoding='utf-8')
    assert 'storyboard_director' in draft_prompt
    assert 'mascot_pose' in draft_prompt
    assert 'step draft-script' in draft_prompt
    assert 'slug: chung` hiện hành' in draft_prompt


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


def test_r534_voice_is_pinned_without_replacement():
    voice = yaml.safe_load((REPO_ROOT / 'profiles/voice.yaml').read_text(encoding='utf-8'))
    assert voice['voice_id'] == 'c081d39a-4922-4c88-9615-78bb240337cd'
    assert voice['settings']['speed'] == 1.18


@pytest.mark.parametrize('role', sorted(load_company().roles))
def test_r534_role_contract_has_completion_and_return_destination(role):
    skill = 'pyh-' + role.replace('_', '-')
    text = (REPO_ROOT / '.agents/skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
    contract = yaml.safe_load(text.split('```yaml\n', 1)[1].split('```', 1)[0])
    assert set(contract) == {'input', 'output', 'done_when', 'missing_data_to'}
    assert all(isinstance(value, str) and value.strip() for value in contract.values())


@pytest.mark.parametrize('critic', ['script_critic', 'art_director', 'product_critic'])
def test_r534_exhausted_independent_models_never_invoke_maker(tmp_path, critic):
    from healthvideo.agents import invoke_with_failover

    company = load_company()
    calls = []

    def forbidden_runner(*args, **kwargs):
        calls.append(args)
        raise AssertionError('No model call is allowed')

    # Exhaust the actual configured chain, including proxy aliases of the same model.
    with pytest.raises(ValueError, match='model độc lập'):
        invoke_with_failover(
            company.chain(critic), 'fixture only', cwd=tmp_path, log_dir=tmp_path / 'logs',
            role=critic, slug='fixture', step='script_review',
            exclude_slots=company.chain(critic),
            runner=forbidden_runner,
        )
    assert calls == []
