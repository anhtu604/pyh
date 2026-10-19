"""Offline CLI coverage for the resumable orientation steps."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.orientation import begin_orientation, run_orientation_search
from tests.workflows.test_orientation import (
    FROZEN_NOW,
    SCOPE,
    FailingClient,
    StubClient,
    _candidate,
    _completed,
    _researching_project,
    _topic_project,
)

runner = CliRunner()


def _snapshot(project: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("outcome", ["completed", "failed", "zero_results"])
def test_orientation_search_records_provider_outcome(tmp_path, monkeypatch, outcome):
    project = _researching_project(tmp_path)
    client = (
        FailingClient() if outcome == "failed"
        else StubClient("pubmed", [_candidate()] if outcome == "completed" else [])
    )
    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: [client])

    result = runner.invoke(app, ["operator", "orientation-search", str(project)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["candidate_count"] == (1 if outcome == "completed" else 0)
    recorded = read_yaml(project / "revisions/001/orientation/search-log.yaml")
    assert payload["provider_outcomes"] == recorded["provider_outcomes"]
    provider = payload["provider_outcomes"][0]
    assert provider["status"] == outcome
    assert provider["failure_class"] == ("OSError" if outcome == "failed" else None)
    assert provider["result_count"] == (
        None if outcome == "failed" else 1 if outcome == "completed" else 0
    )
    candidates = (project / "revisions/001/orientation/candidates.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(candidates) == payload["candidate_count"]
    assert read_yaml(project / "project.yaml")["state"] == "orientation_research_in_progress"


@pytest.fixture
def searched_project(tmp_path, monkeypatch):
    project = _researching_project(tmp_path)
    monkeypatch.setattr(
        "healthvideo.cli.get_default_clients", lambda: [StubClient("pubmed", [_candidate()])]
    )
    run_orientation_search(project, [StubClient("pubmed", [_candidate()])], now=FROZEN_NOW)
    return project


def test_orientation_complete_opens_editorial_boundary(tmp_path, searched_project):
    project = searched_project
    file = tmp_path / "completed.yaml"
    write_yaml_atomic(file, _completed(project).model_dump(mode="json"))

    result = runner.invoke(
        app, ["operator", "orientation-complete", str(project), "--file", str(file)]
    )

    assert result.exit_code == 0, result.stdout
    assert result.stdout.strip() == "awaiting_editorial_direction"
    assert read_yaml(project / "project.yaml")["state"] == "awaiting_editorial_direction"
    assert read_yaml(project / "revisions/001/orientation/completed/run-001.yaml") == read_yaml(file)


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        ("stale_hash", "stale topic/scope input hash"),
        ("unbound_candidate", "included candidate is missing"),
        ("wrong_state", "requires orientation_research_in_progress"),
        ("wrong_revision", "active revision"),
        ("invalid_record", "run_id"),
        ("invalid_yaml", "expected"),
    ],
)
def test_orientation_complete_rejects_without_writes(
    tmp_path, searched_project, invalid, message
):
    project = searched_project
    payload = _completed(project).model_dump(mode="json")
    if invalid == "stale_hash":
        payload["topic_input_hash"] = "0" * 64
    elif invalid == "unbound_candidate":
        (project / "revisions/001/orientation/candidates.jsonl").write_text("", encoding="utf-8")
    elif invalid == "wrong_state":
        manifest = read_yaml(project / "project.yaml")
        manifest["state"] = "topic_selected"
        write_yaml_atomic(project / "project.yaml", manifest)
    elif invalid == "wrong_revision":
        payload["revision"] = "002"
    else:
        payload.pop("run_id")
    file = tmp_path / "completed.yaml"
    write_yaml_atomic(file, payload)
    if invalid == "invalid_yaml":
        file.write_text("run_id: [", encoding="utf-8")
    before = _snapshot(project)

    result = runner.invoke(
        app, ["operator", "orientation-complete", str(project), "--file", str(file)]
    )

    assert result.exit_code == 1
    assert message in result.stdout
    assert _snapshot(project) == before


def test_orientation_status_guides_begin_search_complete(tmp_path, monkeypatch):
    project = _topic_project(tmp_path)

    def guidance():
        result = runner.invoke(app, ["operator", "status", str(project), "--json"])
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert set(payload) == {
            "kind", "project_dir", "message", "artifact", "suggested_command", "busy", "writer"
        }
        assert payload["suggested_command"] == "/pyh tìm hiểu chủ đề"
        return payload["message"]

    message = guidance()
    assert "scope file from the topic card" in message
    assert f'healthvideo operator orientation "{project}" --scope <scope-input.yaml>' in message
    assert "orientation/scope.yaml" not in message
    begin_orientation(project, SCOPE)
    assert "operator orientation-search " in guidance()
    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: [FailingClient()])
    result = runner.invoke(app, ["operator", "orientation-search", str(project)])
    assert result.exit_code == 0, result.stdout
    assert "operator orientation-search " in guidance()
    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: [StubClient("pubmed", [])])
    result = runner.invoke(app, ["operator", "orientation-search", str(project)])
    assert result.exit_code == 0, result.stdout
    assert "operator orientation-search " in guidance()
    monkeypatch.setattr(
        "healthvideo.cli.get_default_clients", lambda: [StubClient("pubmed", [_candidate()])]
    )
    result = runner.invoke(app, ["operator", "orientation-search", str(project)])
    assert result.exit_code == 0, result.stdout
    message = guidance()
    assert "completed record using only recorded candidates" in message
    assert f'healthvideo operator orientation-complete "{project}" --file <completed.yaml>' in message
    begin_orientation(project, SCOPE.model_copy(update={"topic_question": "New scope?"}))
    assert "operator orientation-search " in guidance()


def test_orientation_search_passes_repeatable_queries(tmp_path, monkeypatch):
    project = _researching_project(tmp_path)
    calls = []

    class RecordingClient(StubClient):
        def search(self, query: str, limit: int = 10):
            calls.append(query)
            return super().search(query, limit)

    monkeypatch.setattr(
        "healthvideo.cli.get_default_clients", lambda: [RecordingClient("pubmed", [])]
    )
    result = runner.invoke(
        app, ["operator", "orientation-search", str(project), "--query", "a", "--query", "b"]
    )
    assert result.exit_code == 0, result.stdout
    assert calls == ["a", "b"]
    log = read_yaml(project / "revisions/001/orientation/search-log.yaml")
    assert log["queries"] == [
        {"query": "a", "query_ids": ["pubmed-0"]},
        {"query": "b", "query_ids": ["pubmed-1"]},
    ]
