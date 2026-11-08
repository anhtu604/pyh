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
