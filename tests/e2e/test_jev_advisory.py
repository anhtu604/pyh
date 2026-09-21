from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.security import audit_project
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from tests.helpers import create_v2_project_fixture

runner = CliRunner()


def test_e2e_jev_workflow_preserves_all_invariants(tmp_path: Path) -> None:
    # 1. Setup project fixture
    project = create_v2_project_fixture(tmp_path / "golden_project")
    initial_manifest = read_yaml(project / "project.yaml")
    initial_state = initial_manifest["state"]
    assert initial_state == WorkflowState.DRAFT_READY.value

    # 2. Run topic triage via CLI
    card_path = tmp_path / "topic.yaml"
    card = TopicCard(
        slug="preventive-exercise",
        title="Tập thể dục dự phòng",
        question="Bao nhiêu phút mỗi tuần?",
        scores=TopicScores(preventive_value=0.9, evidence_readiness=0.8),
    )
    write_yaml_atomic(card_path, card.model_dump(mode="json"))
    res_topic = runner.invoke(app, ["jev", "triage-topic", str(card_path)])
    assert res_topic.exit_code == 0
    assert "Topic triage advisory:" in res_topic.output

    # 3. Run claim triage via CLI with --save
    res_claim = runner.invoke(app, ["jev", "triage-claims", str(project), "--save"])
    assert res_claim.exit_code == 0
    assert "Claim triage advisory:" in res_claim.output

    # 4. Run second-model recommendation via CLI with --save
    res_review = runner.invoke(app, ["jev", "recommend-review", str(project), "--save"])
    assert res_review.exit_code == 0
    assert "Second-model recommendation:" in res_review.output

    # 5. Verify state machine and manifest invariance
    current_manifest = read_yaml(project / "project.yaml")
    assert current_manifest["state"] == initial_state
    assert current_manifest["active_revision"] == initial_manifest["active_revision"]

    # 6. Verify security audit passes on project with Jev advisory artifacts
    findings = audit_project(project)
    assert findings == ()
