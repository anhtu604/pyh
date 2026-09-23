from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.storage.files import write_yaml_atomic
from healthvideo.workflows.operations import mutation_lease
from tests.helpers import create_v2_project_fixture

runner = CliRunner()


def test_jev_cli_check_offline() -> None:
    result = runner.invoke(app, ["jev", "check"])
    assert result.exit_code == 0
    assert "TypeSafe Jev status" in result.output
    assert "api key:" in result.output.lower()
    assert "***" in result.output or "not configured" in result.output


def test_jev_cli_triage_topic(tmp_path: Path) -> None:
    card_path = tmp_path / "card.yaml"
    card = TopicCard(
        slug="cli-test-card",
        title="CLI Test Topic",
        question="Question?",
        scores=TopicScores(preventive_value=0.9),
    )
    write_yaml_atomic(card_path, card.model_dump(mode="json"))

    result = runner.invoke(app, ["jev", "triage-topic", str(card_path)])
    assert result.exit_code == 0
    assert "Topic triage advisory:" in result.output
    assert "manual_review_required" in result.output or "priority:" in result.output.lower()


def test_jev_cli_triage_claims(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    result = runner.invoke(app, ["jev", "triage-claims", str(project), "--save"])
    assert result.exit_code == 0
    assert "Claim triage advisory:" in result.output


def test_jev_cli_recommend_review(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    result = runner.invoke(app, ["jev", "recommend-review", str(project), "--save"])
    assert result.exit_code == 0
    assert "Second-model recommendation:" in result.output
    assert "healthvideo agent review-request" in result.output or "manual" in result.output.lower()


def test_jev_save_respects_project_write_lease(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    target = project / "revisions" / "001" / "handoffs" / "jev-review-advisory.yaml"
    with mutation_lease(project, "other_writer"):
        result = runner.invoke(app, ["jev", "recommend-review", str(project), "--save"])
        assert result.exit_code != 0
        assert not target.exists()
