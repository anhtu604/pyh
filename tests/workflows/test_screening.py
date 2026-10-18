import csv
import json
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.lease import LeaseOwner
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.evidence.screening import DualLLMScreener
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.lease import acquire_write_lease
from healthvideo.workflows.screening import screen_candidates
from tests.evidence.test_screening import FakeJudge, candidate
from tests.helpers import create_v2_project_fixture


def setup_screening(tmp_path):
    project = create_v2_project_fixture(
        tmp_path, state=WorkflowState.RESEARCH_IN_PROGRESS
    )
    # Use a non-default active revision to catch hard-coded output paths.
    manifest = read_yaml(project / "project.yaml")
    manifest["active_revision"] = "002"
    write_yaml_atomic(project / "project.yaml", manifest)
    revision = project / "revisions" / "002"
    ledger = revision / "evidence" / "ledger.yaml"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("claims: []\nsources: []\n", encoding="utf-8")
    input_path = tmp_path / "candidates.jsonl"
    raw = candidate(pub_type="synthetic review").model_dump(mode="json")
    old_shape = candidate().model_dump(mode="json")
    old_shape.pop("pub_type")
    old_shape["source_id"] = "R-TEST-02"
    input_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in [raw, old_shape])
        + "\n",
        encoding="utf-8",
    )
    criteria_path = tmp_path / "criteria.yaml"
    write_yaml_atomic(
        criteria_path, {"question": "Ví dụ?", "include": ["Mẫu A"], "exclude": []}
    )
    return project, input_path, criteria_path


def screener():
    return DualLLMScreener(
        FakeJudge("include", "Lý do A"),
        FakeJudge("exclude", "Lý do B"),
        FakeJudge("include", 'Phân xử, "ví dụ"\nxuống dòng'),
    )


def test_writes_bom_csv_all_rounds_and_preserves_ledger_manifest_and_input(tmp_path):
    project, input_path, criteria_path = setup_screening(tmp_path)
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    original_input = input_path.read_bytes()
    output = screen_candidates(project, criteria_path, input_path, screener=screener())
    assert output == project / "revisions" / "002" / "research" / "screening.csv"
    assert output.read_bytes().startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == [
            "id",
            "title",
            "year",
            "pub_type",
            "decision",
            "reason",
            "reviewer_1",
            "reviewer_2",
            "arbiter",
        ]
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["id"] == "R-TEST-01"
    assert rows[0]["title"] == "Ví dụ minh họa"
    assert rows[0]["year"] == "2026"
    assert rows[0]["pub_type"] == "synthetic review"
    assert rows[1]["pub_type"] == ""
    assert rows[0]["decision"] == "include"
    assert rows[0]["reason"] == 'Phân xử, "ví dụ"\nxuống dòng'
    for column, decision, reason in [
        ("reviewer_1", "include", "Lý do A"),
        ("reviewer_2", "exclude", "Lý do B"),
        ("arbiter", "include", rows[0]["reason"]),
    ]:
        review = json.loads(rows[0][column])
        assert review == {
            "decision": decision,
            "reason": reason,
            "reviewer": "fake",
            "probability": 0.7,
        }
    assert all(path.read_bytes() == content for path, content in before.items())
    assert input_path.read_bytes() == original_input


def test_consensus_leaves_arbiter_cell_empty(tmp_path):
    project, input_path, criteria_path = setup_screening(tmp_path)
    output = screen_candidates(
        project,
        criteria_path,
        input_path,
        screener=DualLLMScreener(FakeJudge(), FakeJudge(), FakeJudge()),
    )
    with output.open(encoding="utf-8-sig", newline="") as stream:
        assert next(csv.DictReader(stream))["arbiter"] == ""


@pytest.mark.parametrize("invalid", ["criteria", "candidate"])
def test_invalid_input_is_validated_before_any_judge_or_output(tmp_path, invalid):
    project, input_path, criteria_path = setup_screening(tmp_path)
    if invalid == "criteria":
        criteria_path.write_text(
            "question: example\ninclude: invalid\nexclude: []\n", encoding="utf-8"
        )
    else:
        with input_path.open("a", encoding="utf-8") as stream:
            stream.write('{"bad":"candidate"}\n')
    judge = FakeJudge()
    with pytest.raises(ValueError):
        screen_candidates(
            project,
            criteria_path,
            input_path,
            screener=DualLLMScreener(judge, judge, judge),
        )
    assert not judge.calls
    assert not (project / "revisions" / "002" / "research" / "screening.csv").exists()


def test_atomic_csv_failure_keeps_previous_complete_output(tmp_path, monkeypatch):
    project, input_path, criteria_path = setup_screening(tmp_path)
    output = screen_candidates(project, criteria_path, input_path, screener=screener())
    previous = output.read_bytes()

    def fail_replace(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("healthvideo.storage.files.os.replace", fail_replace)
    with pytest.raises(OSError):
        screen_candidates(project, criteria_path, input_path, screener=screener())
    assert output.read_bytes() == previous
    assert sorted(p.name for p in output.parent.iterdir()) == ["screening.csv"]


def test_cli_screens_without_command_config_or_ledger_mutation(tmp_path, monkeypatch):
    project, input_path, criteria_path = setup_screening(tmp_path)
    monkeypatch.delenv("HEALTHVIDEO_SCREEN_CMD", raising=False)
    ledger = project / "revisions" / "002" / "evidence" / "ledger.yaml"
    before = ledger.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "evidence",
            "screen",
            str(project),
            "--criteria",
            str(criteria_path),
            "--input",
            str(input_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "screening.csv" in result.output
    output = ledger.parent.parent / "research" / "screening.csv"
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert all(row["decision"] == "unsure" for row in rows)
    assert ledger.read_bytes() == before
    assert not (project / ".healthvideo" / "write-lease.yaml").exists()


def test_cli_cannot_screen_while_another_writer_owns_lease(tmp_path):
    project, input_path, criteria_path = setup_screening(tmp_path)
    handle = acquire_write_lease(
        project,
        operation="test",
        active_revision="002",
        owner=LeaseOwner(
            host_id="test-host", pid=123, process_start_fingerprint="test"
        ),
        now=datetime.now(UTC),
        ttl_seconds=300,
    )
    try:
        result = CliRunner().invoke(
            app,
            [
                "evidence",
                "screen",
                str(project),
                "--criteria",
                str(criteria_path),
                "--input",
                str(input_path),
            ],
        )
        assert result.exit_code == 1
        assert "Project busy" in result.output
        assert not (
            project / "revisions" / "002" / "research" / "screening.csv"
        ).exists()
    finally:
        handle.release()
