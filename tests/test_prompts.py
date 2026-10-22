"""Tests for fixed agent prompt templates and rendering."""

import pytest

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
