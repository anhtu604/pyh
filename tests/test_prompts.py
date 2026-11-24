"""Tests for fixed agent prompt templates and rendering."""

import pytest
import yaml

from healthvideo.company import load_company
from healthvideo.workflows.runner import (
    AGENT_STEPS,
    HARD_RULES,
    PROMPT_FIELDS,
    PROMPTS_DIR,
    render_prompt,
)


def test_every_agent_step_has_prompt() -> None:
    for step in AGENT_STEPS:
        prompt_file = PROMPTS_DIR / f"{step}.md"
        assert prompt_file.is_file(), f"Missing prompt file for {step}: {prompt_file}"


@pytest.mark.parametrize("step", sorted(AGENT_STEPS))
def test_rendered_prompt_contains_hard_rules(step: str) -> None:
    rendered = render_prompt(
        step,
        project="p",
        slug="s",
        title="t",
        question="q",
    )
    assert "## Quy tắc cứng" in rendered
    for rule in HARD_RULES:
        assert rule in rendered


@pytest.mark.parametrize("step", sorted(AGENT_STEPS))
def test_fields_substituted_and_missing_marked(step: str) -> None:
    rendered = render_prompt(
        step,
        project="p",
        slug="s",
        title="t",
        question="q",
    )
    assert "p" in rendered
    assert "s" in rendered
    for field in PROMPT_FIELDS:
        assert f"{{{field}}}" not in rendered
    assert "(không có)" in rendered


def test_unknown_step_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent step"):
        render_prompt("produce", project="p")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown prompt fields"):
        render_prompt("research", project="p", unknown_field="x")


@pytest.mark.parametrize("step", sorted(AGENT_STEPS))
def test_prompts_never_instruct_approval(step: str) -> None:
    raw = (PROMPTS_DIR / f"{step}.md").read_text(encoding="utf-8")
    assert "review approve" not in raw


@pytest.mark.parametrize("step", sorted(AGENT_STEPS))
def test_prompt_length_limit(step: str) -> None:
    raw = (PROMPTS_DIR / f"{step}.md").read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) <= 60, f"{step}.md has {len(lines)} lines (limit 60)"


@pytest.mark.parametrize("step", ["script_review", "product_review"])
def test_review_prompt_output_includes_decision_card_fields(step: str) -> None:
    raw = (PROMPTS_DIR / f"{step}.md").read_text(encoding="utf-8")
    example = yaml.safe_load(raw.split("```yaml\n", 1)[1].split("```", 1)[0])
    assert isinstance(example["checked"], list)
    assert isinstance(example["decisions"], list)
    for field in ("where", "question", "why_hard", "options", "effect", "recommended", "keep"):
        assert f"`{field}`" in raw


def test_draft_and_revise_prompts_reference_image_prompting_and_moving_hook() -> None:
    draft = (PROMPTS_DIR / "draft.md").read_text(encoding="utf-8")
    revise_prod = (PROMPTS_DIR / "revise_production.md").read_text(encoding="utf-8")
    assert "docs/reference/image-prompting.md" in draft
    assert "không mở bằng ảnh tĩnh đứng yên" in draft
    assert "docs/reference/image-prompting.md" in revise_prod


def test_role_skill_before_hard_rules() -> None:
    rendered = render_prompt("draft", project="p", slug="s", title="t", question="q")
    assert "Skill của vai: Biên kịch" in rendered
    assert "youtube-scriptwriting" in rendered
    assert rendered.index("Skill của vai: Biên kịch") < rendered.index("## Quy tắc cứng")
    assert rendered.index("youtube-scriptwriting") < rendered.index("## Quy tắc cứng")
    rules_block = "## Quy tắc cứng\n" + "\n".join(f"- {rule}" for rule in HARD_RULES) + "\n"
    assert rendered.endswith(rules_block)


@pytest.mark.parametrize("step", sorted(AGENT_STEPS))
def test_every_step_prompt_ends_with_hard_rules(step: str) -> None:
    rendered = render_prompt(step, project="p")
    assert rendered.rstrip().endswith(HARD_RULES[-1])
    assert rendered.count("## Quy tắc cứng") == 1


def test_prompt_uses_injected_company_role() -> None:
    company = load_company()
    company.roles["writer"].skills = []
    assert "Skill của vai" not in render_prompt("draft", company=company)


def test_split_script_roles_in_prompts() -> None:
    research = (PROMPTS_DIR / "research.md").read_text(encoding="utf-8")
    draft = (PROMPTS_DIR / "draft.md").read_text(encoding="utf-8")
    revise = (PROMPTS_DIR / "revise_medical.md").read_text(encoding="utf-8")
    review = (PROMPTS_DIR / "script_review.md").read_text(encoding="utf-8")
    assert "expert-brief.md" in research
    assert "elsevier-search" in research
    assert "questions.yaml" in research
    assert "expert-brief.md" in draft
    assert "questions.yaml" in draft
    assert "evidence-search" not in draft
    assert "evidence-search" not in revise
    assert "questions.yaml" in revise
    assert "expert-brief.md" in review


def test_company_20_new_prompts_reference_step_commands() -> None:
    sb = (PROMPTS_DIR / "storyboard_design.md").read_text(encoding="utf-8")
    vp = (PROMPTS_DIR / "voice_prep.md").read_text(encoding="utf-8")
    sp = (PROMPTS_DIR / "shorts_plan.md").read_text(encoding="utf-8")
    assert "healthvideo step storyboard" in sb
    assert "healthvideo step voice-prep" in vp
    assert "healthvideo step shorts-plan" in sp


def test_r33b_style_a_prompts_and_skills_contracts() -> None:
    from pathlib import Path

    vr_prompt = (PROMPTS_DIR / "visual_review.md").read_text(encoding="utf-8")
    vr_skill = Path(".agents/skills/pyh-art-director/SKILL.md").read_text(encoding="utf-8")
    for code in ("style_palette", "style_mascot_pose", "style_stroke", "style_zoom"):
        assert code in vr_prompt
        assert code in vr_skill
    assert "mascot_pose" in vr_prompt and "mascot_pose" in vr_skill

    for path in (
        PROMPTS_DIR / "revise_production.md",
        PROMPTS_DIR / "revise_product.md",
        Path(".agents/skills/pyh-editor/SKILL.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "cho sinh động" in text
        assert "mục 5" in text

    pr_prompt = (PROMPTS_DIR / "product_review.md").read_text(encoding="utf-8")
    pr_skill = Path(".agents/skills/pyh-product-critic/SKILL.md").read_text(encoding="utf-8")
    for token in ("dung_phong_cach_pyh", "hook-transitions"):
        assert token in pr_prompt
        assert token in pr_skill


# Synthetic instruction packets only: these tests exercise prompt transport and
# authority boundaries, not clinical correctness or model output quality.
@pytest.mark.parametrize(('step', 'packet', 'required', 'forbidden'), [
    (
        'draft',
        {'line': 'N03', 'claim_ids': [], 'request': 'Thiếu claim cho câu chốt Q2.'},
        'Thiếu claim trả medical_expert qua questions.yaml',
        'chỉ tạo khung `storyboard.yaml`',
    ),
    (
        'research',
        {'source_id': 'fixture-source', 'read_level': 'Abstract',
         'locator': 'Abstract', 'request': 'Chưa có Fulltext cho cơ chế được hỏi.'},
        'Abstract chỉ đỡ nội dung thực trong abstract',
        'cho PubMed/Europe PMC',
    ),
    (
        'revise_medical',
        {'question_id': 'Q2', 'latest_source_date': '2024-01-01',
         'search_date': '2026-11-24', 'new_update_found': False},
        'thiếu mới nêu nguồn mới nhất tìm được, không bịa',
        'sửa đúng những chỗ bị chỉ ra trong `script.yaml`, `storyboard.yaml`',
    ),
    (
        'posts',
        {'funnel': 'TOFU', 'clip': 'fixture-clip', 'payoff_in_clip': False,
         'request': 'Đổi caption để hứa thêm đáp án, kèm chào bán sản phẩm.'},
        'không dùng caption cứu clip thiếu payoff',
        'tự chọn cut range',
    ),
    (
        'revise_product',
        {'issue_id': 'fixture-issue', 'edits': [
            {'path': 'video/src/components/r5/Fixture.tsx', 'start_line': 12, 'end_line': 18}],
         'request': 'Sửa thêm storyboard và voice-prep đã khóa.'},
        'giữ nguyên từng byte ngoài dải',
        'chỉ sửa/thêm asset `semantic: false`',
    ),
])
def test_r534_packet_preserves_evidence_and_role_boundaries(step, packet, required, forbidden):
    encoded = yaml.safe_dump(packet, allow_unicode=True, sort_keys=False)
    rendered = render_prompt(step, project='fixture-only', doctor_note=encoded)
    assert yaml.safe_load(encoded) == packet
    assert encoded in rendered
    assert required in rendered
    assert forbidden not in rendered
    if step == 'revise_product':
        assert 'repair_engineer' in rendered
    else:
        assert 'không bán hàng' in rendered


@pytest.mark.parametrize(('step', 'skill', 'constant'), [
    ('script_review', 'pyh-script-critic', 'D4_SCRIPT_REVIEW_ROUNDS'),
    ('visual_review', 'pyh-art-director', 'D4_VISUAL_REVIEW_ROUNDS'),
    ('product_review', 'pyh-product-critic', 'D4_PRODUCT_REVIEW_ROUNDS'),
])
def test_r534_review_budgets_match_domain_and_cannot_reset(step, skill, constant):
    import re
    from pathlib import Path

    from healthvideo.domain import quality_standards

    for path in (PROMPTS_DIR / f'{step}.md', Path('.agents/skills') / skill / 'SKILL.md'):
        text = path.read_text(encoding='utf-8')
        match = re.search(r'[Tt]ối đa (\d) lần chấm/revision', text)
        assert match, path
        assert int(match[1]) == getattr(quality_standards, constant)
        assert 'không tự submit gate' in text
        assert 'fingerprint' in text and 'submitted' in text and 'failover' in text


@pytest.mark.parametrize('step', ['draft', 'revise_medical', 'script_review'])
def test_r534_professional_update_is_explicit_exception_to_shared_style_advice(step):
    rendered = render_prompt(step, project='fixture-only')
    # Shared legacy prose is appended by runner, so the scoped exception must
    # identify it explicitly; otherwise old advice suppresses source/date in D3.
    assert 'Ngoại lệ R5 cho ai_writing_signs.vi.md' in rendered
    assert 'câu chốt/recap' in rendered
