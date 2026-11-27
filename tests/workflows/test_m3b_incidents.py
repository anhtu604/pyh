"""M3b regression tests: stale edit_script expiry, dev-ticket repair, and step preflight."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from healthvideo.agents import AgentResult
from healthvideo.company import load_company
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows import (
    change_request,
    expert,
    playbook,
    script_review,
)
from healthvideo.workflows import (
    repair_service as repair,
)
from healthvideo.workflows.production_retry import clear_agent_retry
from healthvideo.workflows.runner import RunDeps, run_queue
from healthvideo.workflows.step_preflight import preflight
from tests.helpers import create_v2_project_fixture


def _record_passing_script_review(project: Path) -> None:
    revision = project / "revisions/001"
    report = {
        "scores": dict.fromkeys(script_review.CRITERIA, 8),
        "summary": "Kịch bản đạt chuẩn.",
        "issues": [],
        "resolved_issues": [],
        "checked": ["hook"],
        "decisions": [],
        "issue_statuses": {},
    }
    write_yaml_atomic(revision / script_review.REPORT, report)
    script_review.record_review(project, script_review.script_hash(project))


def _setup_queue_project(
    tmp_path: Path,
    *,
    state: WorkflowState = WorkflowState.DRAFT_READY,
) -> Path:
    add_to_queue(
        tmp_path,
        QueueEntry(
            slug="muoi-va-huyet-ap-v2",
            title="M3b Topic",
            question="Câu hỏi test M3b?",
            added=date(2026, 11, 27),
        ),
    )
    return create_v2_project_fixture(tmp_path / "projects", state=state)


def _fake_result(log_dir: Path, step: str, *, ok: bool = True) -> AgentResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{step}.log"
    log_path.write_text("ok\n" if ok else "failed\n", encoding="utf-8")
    return AgentResult(
        agent="codex",
        ok=ok,
        quota_exhausted=False,
        log_path=log_path,
        model="gpt-6.1-sol",
    )


def _deps(invoke, *, storyboard_ready: bool = True, voice_prep_ready: bool = True) -> RunDeps:
    return RunDeps(
        company=load_company(),
        invoke=invoke,
        python_steps={"submit_medical": lambda p: None},
        create_project=lambda root, entry: root / "projects" / entry.slug,
        read_state=lambda p: WorkflowState(read_yaml(p / "project.yaml")["state"]),
        reject_note=lambda p: None,
        changed_code_paths=lambda root: set(),
        expert_brief_ready=lambda p: True,
        storyboard_ready=lambda p: storyboard_ready,
        voice_prep_ready=lambda p: voice_prep_ready,
        parallel_branches=False,
    )


def test_edit_script_without_line_ids_unchanged_script_marks_applied_and_advances(tmp_path):
    project = _setup_queue_project(tmp_path, state=WorkflowState.DRAFT_READY)
    revision = project / "revisions/001"
    (revision / expert.EXPERT_BRIEF).write_text("# Expert brief\n", encoding="utf-8")

    # Storyboard-like note recorded as edit_script without mentioning any script line IDs.
    change_request.request_change(
        project,
        "edit_script",
        "Đổi màu nền cảnh kết cho rõ hơn.",
        {"revision": "001", "source": "doctor-chat"},
        now=datetime.now(UTC),
    )

    calls: list[str] = []

    def fake_invoke(slots, prompt, *, cwd, log_dir, role, slug, step, **kwargs):
        calls.append(step)
        # Writer keeps script/script.yaml unchanged and reports ok.
        return _fake_result(log_dir, step, ok=True)

    # First step: draft keeps script unchanged -> auto-applied, no block/incident.
    report = run_queue(tmp_path, _deps(fake_invoke, storyboard_ready=True), once=True)
    assert calls == ["draft"]
    assert not report.blocked
    assert not (tmp_path / "topics/logs" / project.name / "blocked.txt").exists()
    assert not change_request.pending(project)

    req_files = list((revision / "reviews/changes").glob("*-requested.yaml"))
    assert len(req_files) == 1
    req_data = read_yaml(req_files[0])
    assert req_data["applied"] is True
    assert req_data["outcome"] == "no_script_change"

    log_data = read_yaml(revision / script_review.LOG)
    assert "rewrite_pending_hash" not in log_data

    retry_file = tmp_path / "topics/logs" / project.name / "agent-retry.yaml"
    if retry_file.is_file():
        assert "draft" not in (read_yaml(retry_file).get("steps") or {})

    # Next step: the fixture's passed review still matches the unchanged script, so no
    # critic round is spent; the python submit_medical step runs instead.
    calls.clear()
    run_queue(tmp_path, _deps(fake_invoke, storyboard_ready=True), once=True)
    assert calls == []

    # When review already passed and storyboard is not ready -> next step is storyboard_design.
    _record_passing_script_review(project)
    change_request.request_change(
        project,
        "edit_script",
        "Làm sáng bố cục cảnh minh hoạ.",
        {"revision": "001", "source": "doctor-chat"},
        now=datetime.now(UTC),
    )
    calls.clear()
    report2 = run_queue(tmp_path, _deps(fake_invoke, storyboard_ready=False), once=True)
    assert calls == ["draft"]
    assert not report2.blocked
    assert not change_request.pending(project)

    calls.clear()
    run_queue(tmp_path, _deps(fake_invoke, storyboard_ready=False), once=True)
    assert calls == ["storyboard_design"]


def test_restore_repair_does_not_revert_applied_change_request(tmp_path):
    project = _setup_queue_project(tmp_path, state=WorkflowState.DRAFT_READY)
    revision = project / "revisions/001"
    (revision / expert.EXPERT_BRIEF).write_text("# Expert brief\n", encoding="utf-8")

    change_request.request_change(
        project,
        "edit_script",
        "Ghi chú cũ đã xử lý.",
        {"revision": "001"},
        now=datetime.now(UTC),
    )
    req_file = next((revision / "reviews/changes").glob("*-requested.yaml"))

    # Trigger scoped_script (rewriting in DRAFT_READY) with a failing agent that marks request applied
    # mid-run and then fails scope check -> restore_repair() runs.
    def fake_invoke(slots, prompt, *, cwd, log_dir, role, slug, step, **kwargs):
        change_request.mark_applied(project, outcome="no_script_change")
        # Create an unexpected file in script/ to force restore_repair() via scope violation.
        (revision / "script/extra-illegal.yaml").write_text("bad: true\n", encoding="utf-8")
        return _fake_result(log_dir, step, ok=True)

    report = run_queue(tmp_path, _deps(fake_invoke), once=True)
    assert project.name in report.blocked
    assert not (revision / "script/extra-illegal.yaml").exists()
    # Crucially, restore_repair() must NOT revert reviews/changes/* back to applied: false.
    assert read_yaml(req_file)["applied"] is True
    assert not change_request.pending(project)


def test_edit_script_abandoned_after_two_attempts_without_third_agent_call(tmp_path):
    project = _setup_queue_project(tmp_path, state=WorkflowState.DRAFT_READY)
    revision = project / "revisions/001"
    (revision / expert.EXPERT_BRIEF).write_text("# Expert brief\n", encoding="utf-8")
    _record_passing_script_review(project)

    # Request explicitly names line L01 so unchanged script is treated as a real failure.
    change_request.request_change(
        project,
        "edit_script",
        "Sửa dòng L01 cho ngắn gọn hơn.",
        {"revision": "001", "source": "doctor-chat"},
        now=datetime.now(UTC),
    )
    req_file = next((revision / "reviews/changes").glob("*-requested.yaml"))

    calls: list[str] = []

    def fake_invoke(slots, prompt, *, cwd, log_dir, role, slug, step, **kwargs):
        calls.append(step)
        return _fake_result(log_dir, step, ok=True)

    # Attempt 1: agent leaves L01 unchanged -> blocked, attempts == 1.
    report1 = run_queue(tmp_path, _deps(fake_invoke), once=True)
    assert project.name in report1.blocked
    assert calls == ["draft"]
    assert read_yaml(req_file)["attempts"] == 1
    assert read_yaml(req_file)["applied"] is False

    # Clear retry hold and try Attempt 2 -> blocked, attempts == 2.
    clear_agent_retry(tmp_path, project.name, "draft")
    (tmp_path / "topics/logs" / project.name / "blocked.txt").unlink(missing_ok=True)
    report2 = run_queue(tmp_path, _deps(fake_invoke), once=True)
    assert project.name in report2.blocked
    assert calls == ["draft", "draft"]
    assert read_yaml(req_file)["attempts"] == 2
    assert read_yaml(req_file)["applied"] is False

    # Attempt 3: exceeds MAX_EDIT_SCRIPT_ATTEMPTS (2) -> abandoned, chat notice logged, NO 3rd draft call.
    clear_agent_retry(tmp_path, project.name, "draft")
    (tmp_path / "topics/logs" / project.name / "blocked.txt").unlink(missing_ok=True)
    run_queue(tmp_path, _deps(fake_invoke), once=True)

    req_data = read_yaml(req_file)
    assert req_data["applied"] is True
    assert req_data["outcome"] == "abandoned"
    assert calls.count("draft") == 2

    chat_file = project / "chat.jsonl"
    assert chat_file.is_file()
    messages = [json.loads(line) for line in chat_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any("abandoned" in m.get("text", "") for m in messages)


def test_repair_action_opens_dev_ticket_without_invoking_repair_engineer(tmp_path, monkeypatch):
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.DRAFT_READY)
    logs = tmp_path / "topics/logs" / project.name
    logs.mkdir(parents=True)
    (logs / "blocked.txt").write_text("RuntimeError: parser crash on scene S02\n", encoding="utf-8")

    monkeypatch.setattr(repair, "_active", lambda *args: False)
    monkeypatch.setattr(playbook, "DEFAULT_AUTO_RETRIES", 0)

    def forbidden_maintenance(*args, **kwargs):
        raise AssertionError("_maintenance must not be entered for action=repair")

    monkeypatch.setattr(repair, "_maintenance", forbidden_maintenance)

    stages: list[tuple[str, str]] = []

    def fake_ask(root, slug, role, step, *args):
        stages.append((role, step))
        if step == "repair_diagnose":
            return repair.Diagnosis(
                action="repair",
                cause="Parser crash on empty scene payload",
                evidence=["blocked.txt"],
                files=["src/healthvideo/workflows/runner.py"],
                tests=["tests/workflows/test_m3b_incidents.py"],
                brief="Guard empty payload before parsing.",
            )
        raise AssertionError(f"Unexpected agent call: {role}/{step}")

    monkeypatch.setattr(repair, "_ask", fake_ask)

    phase = repair.repair_once(tmp_path, project.name)
    assert phase == "awaiting_dev"
    assert stages == [("coordinator_senior", "repair_diagnose")]

    tickets = list((tmp_path / "topics/dev-tickets").glob(f"*-{project.name}.yaml"))
    assert len(tickets) == 1
    assert re.match(rf"^\d{{8}}T\d{{6}}-{re.escape(project.name)}\.yaml$", tickets[0].name)

    ticket = read_yaml(tickets[0])
    assert ticket["slug"] == project.name
    assert ticket["revision"] == "001"
    assert ticket["cause"] == "Parser crash on empty scene payload"
    assert ticket["files"] == ["src/healthvideo/workflows/runner.py"]
    assert ticket["tests"] == ["tests/workflows/test_m3b_incidents.py"]
    assert ticket["brief"] == "Guard empty payload before parsing."
    assert ticket["status"] == "open"
    assert datetime.fromisoformat(ticket["created_at"]).tzinfo is not None

    report = read_yaml(logs / repair.REPORT)
    assert report["phase"] == "awaiting_dev"
    assert report["attempts"] == 0

    blocked_text = (logs / "blocked.txt").read_text(encoding="utf-8").strip()
    assert "\n" not in blocked_text
    assert blocked_text.startswith("Chờ dev lead sửa code:")
    assert "Parser crash" in blocked_text

    # Calling repair_once again does not re-diagnose or create duplicate tickets.
    assert repair.repair_once(tmp_path, project.name) == "awaiting_dev"
    assert len(list((tmp_path / "topics/dev-tickets").glob(f"*-{project.name}.yaml"))) == 1


def test_preflight_blocks_draft_missing_ledger_with_zero_agent_calls(tmp_path):
    project = _setup_queue_project(tmp_path, state=WorkflowState.DRAFT_READY)
    manifest = read_yaml(project / "project.yaml")
    manifest["state"] = WorkflowState.EVIDENCE_READY.value
    write_yaml_atomic(project / "project.yaml", manifest)
    revision = project / "revisions/001"
    (revision / expert.EXPERT_BRIEF).write_text("# Expert brief\n", encoding="utf-8")
    (revision / "evidence/ledger.yaml").unlink()

    calls: list[str] = []

    def fake_invoke(slots, prompt, *, cwd, log_dir, role, slug, step, **kwargs):
        calls.append(step)
        return _fake_result(log_dir, step, ok=True)

    report = run_queue(tmp_path, _deps(fake_invoke), once=True)
    assert calls == []
    assert project.name in report.blocked
    blocked_text = (tmp_path / "topics/logs" / project.name / "blocked.txt").read_text(encoding="utf-8")
    assert "evidence/ledger.yaml" in blocked_text


def test_preflight_checks_script_review_voice_prep_and_shorts_plan(tmp_path):
    project = create_v2_project_fixture(tmp_path / "projects", state=WorkflowState.DRAFT_READY)
    revision = project / "revisions/001"

    # draft missing expert-brief.md
    draft_errors = preflight("draft", project)
    assert any("expert-brief.md" in err for err in draft_errors)

    # script_review with invalid script.yaml
    (revision / "script/script.yaml").write_text("lines: []\n", encoding="utf-8")
    sr_errors = preflight("script_review", project)
    assert any("script/script.yaml" in err for err in sr_errors)

    # voice_prep and shorts_plan missing storyboard.yaml
    (revision / "storyboard/storyboard.yaml").unlink(missing_ok=True)
    for step in ("voice_prep", "shorts_plan"):
        errs = preflight(step, project)
        assert any("storyboard/storyboard.yaml" in err for err in errs)
