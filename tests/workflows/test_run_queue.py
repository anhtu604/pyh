"""Tests for the run_queue factory loop with injected dependencies."""

import subprocess
from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from healthvideo.agents import (
    DEFAULT_AGENTS,
    AgentCli,
    AgentResult,
    AllAgentsExhausted,
    invoke_with_failover,
)
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.domain.queue import QueueEntry
from healthvideo.storage.files import read_yaml
from healthvideo.storage.queue import add_to_queue
from healthvideo.workflows.runner import (
    HARD_RULES,
    RunDeps,
    render_prompt,
    run_queue,
)


def _entry(
    slug: str = "tang-huyet-ap",
    *,
    title: str = "Tăng huyết áp thầm lặng",
    question: str = "Vì sao huyết áp cao làm dày thành mạch?",
    doctor_note: str | None = "Lưu ý nhấn mạnh đo huyết áp tại nhà.",
) -> QueueEntry:
    return QueueEntry(
        slug=slug,
        title=title,
        question=question,
        doctor_note=doctor_note,
        added=date(2026, 10, 22),
    )


def _log_file(log_dir: Path, name: str = "fake-codex.log") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / name
    log_path.write_text("fake agent log\n", encoding="utf-8")
    return log_path


def test_run_reviews_visuals_after_produce_before_video_gate(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    state = {'value': WorkflowState.MEDICALLY_APPROVED, 'pending': False, 'reviewed': False}
    calls = []

    def produce(_project):
        calls.append('produce')
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW if state['reviewed'] else WorkflowState.PRODUCTION_IN_PROGRESS
        state['pending'] = not state['reviewed']

    def invoke(agents, prompt, *, cwd, log_dir):
        assert 'visual-review.yaml' in prompt
        assert state['value'] == WorkflowState.PRODUCTION_IN_PROGRESS
        calls.append('visual_review')
        state['reviewed'] = True
        return AgentResult('codex', True, False, _log_file(log_dir))

    deps = RunDeps(
        create_project=lambda *_: project, read_state=lambda _: state['value'],
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], invoke=invoke,
        visual_review_pending=lambda _: state['pending'],
    )
    result = run_queue(tmp_path, deps)
    assert calls == ['produce', 'visual_review', 'produce']
    assert result.at_gate == [entry.slug]
    assert not result.blocked


def test_run_stops_at_medical_gate(tmp_path: Path) -> None:
    entry = _entry("tang-huyet-ap")
    add_to_queue(tmp_path, entry)
    stale_block = tmp_path / "topics" / "logs" / "tang-huyet-ap" / "blocked.txt"
    stale_block.parent.mkdir(parents=True)
    stale_block.write_text("lỗi từ lần chạy trước\n", encoding="utf-8")

    states: dict[str, WorkflowState] = {}
    created: list[str] = []
    prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        created.append(item.slug)
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        prompts.append(prompt)
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert created == ["tang-huyet-ap"]
    assert len(prompts) == 2
    assert states["tang-huyet-ap"] == WorkflowState.AWAITING_MEDICAL_REVIEW
    assert report.advanced == ["tang-huyet-ap"]
    assert report.at_gate == ["tang-huyet-ap"]
    assert report.blocked == []
    assert report.exhausted is False
    assert not stale_block.exists()


def test_run_rerun_resumes_same_step(tmp_path: Path) -> None:
    entry = _entry("suy-tim-man")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    created_calls: list[str] = []
    run1_prompts: list[str] = []
    run2_prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        created_calls.append(item.slug)
        return project_dir

    def interrupted_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        run1_prompts.append(prompt)
        return AgentResult(
            agent="codex",
            ok=False,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "interrupted.log"),
        )

    deps1 = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=interrupted_invoke,
    )

    report1 = run_queue(tmp_path, deps1)

    assert report1.blocked == ["suy-tim-man"]
    assert report1.advanced == []
    assert states["suy-tim-man"] == WorkflowState.TOPIC_SELECTED
    blocked_file = tmp_path / "topics" / "logs" / "suy-tim-man" / "blocked.txt"
    assert blocked_file.is_file()
    assert "interrupted.log" in blocked_file.read_text(encoding="utf-8")

    def normal_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        run2_prompts.append(prompt)
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "resumed.log"),
        )

    deps2 = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=normal_invoke,
    )

    report2 = run_queue(tmp_path, deps2)

    assert created_calls == ["suy-tim-man"]
    expected_research_prompt = render_prompt(
        "research",
        project=str(tmp_path / "projects" / "suy-tim-man"),
        slug=entry.slug,
        title=entry.title,
        question=entry.question,
        doctor_note=entry.doctor_note or "",
    )
    assert run1_prompts == [expected_research_prompt]
    assert run2_prompts[0] == expected_research_prompt
    assert report2.advanced == ["suy-tim-man"]
    assert report2.at_gate == ["suy-tim-man"]
    assert report2.blocked == []


def test_unchanged_state_marks_blocked(tmp_path: Path) -> None:
    entry = _entry("gan-nhiem-mo")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def noop_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir, "noop.log"),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=noop_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert report.blocked == ["gan-nhiem-mo"]
    assert report.advanced == []
    assert report.at_gate == []
    blocked_text = (
        tmp_path / "topics" / "logs" / "gan-nhiem-mo" / "blocked.txt"
    ).read_text(encoding="utf-8")
    assert "agent không làm đổi trạng thái" in blocked_text


def test_all_exhausted_stops_run_and_keeps_state(tmp_path: Path) -> None:
    entry1 = _entry("chu-de-1")
    entry2 = _entry("chu-de-2")
    add_to_queue(tmp_path, entry1)
    add_to_queue(tmp_path, entry2)

    states: dict[str, WorkflowState] = {}

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def exhausted_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        raise AllAgentsExhausted("All agents exhausted quota: codex, agy")

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=exhausted_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert report.exhausted is True
    assert report.advanced == []
    assert report.at_gate == []
    assert report.blocked == []
    assert states["chu-de-1"] == WorkflowState.TOPIC_SELECTED
    assert "chu-de-2" not in states


def test_code_changes_recorded(tmp_path: Path) -> None:
    entry = _entry("xo-vua-dong-mach")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    current_changed: list[Path] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        slug = log_dir.name
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
            current_changed[:] = [Path("video/src/anatomy/ArteryWall.tsx")]
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
            current_changed[:] = [
                Path("video/src/anatomy/ArteryWall.tsx"),
                Path("video/src/anatomy/ArteryWall.test.tsx"),
            ]
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: list(current_changed),
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert report.code_changes == [
        Path("video/src/anatomy/ArteryWall.tsx"),
        Path("video/src/anatomy/ArteryWall.test.tsx"),
    ]
    review_path = tmp_path / "topics" / "code-review.yaml"
    assert review_path.is_file()
    payload = read_yaml(review_path)
    assert payload["version"] == 1
    entries = payload["entries"]
    assert len(entries) == 2
    assert entries[0]["path"] == "video/src/anatomy/ArteryWall.tsx"
    assert entries[0]["slug"] == "xo-vua-dong-mach"
    datetime.fromisoformat(entries[0]["at"])
    assert entries[1]["path"] == "video/src/anatomy/ArteryWall.test.tsx"
    assert entries[1]["slug"] == "xo-vua-dong-mach"
    datetime.fromisoformat(entries[1]["at"])


def test_run_never_invokes_approve(tmp_path: Path) -> None:
    dep_field_names = {f.name for f in fields(RunDeps)}
    assert not any("approve" in name.lower() for name in dep_field_names)

    entry = _entry("kiem-soat-duong-huyet")
    add_to_queue(tmp_path, entry)

    states: dict[str, WorkflowState] = {}
    recorded_argv: list[list[str]] = []
    recorded_prompts: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_subprocess_runner(
        argv: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        recorded_argv.append(list(argv))
        prompt_text = kwargs.get("input") or ""
        recorded_prompts.append(prompt_text)
        slug = "kiem-soat-duong-huyet"
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY or states[slug] == WorkflowState.NEEDS_MEDICAL_REVISION:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        elif states[slug] == WorkflowState.NEEDS_PRODUCTION_REVISION:
            states[slug] = WorkflowState.PRODUCTION_IN_PROGRESS
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

    def invoke_via_fake_runner(
        agents: tuple[AgentCli, ...],
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        return invoke_with_failover(
            agents,
            prompt,
            cwd=cwd,
            log_dir=log_dir,
            runner=fake_subprocess_runner,
        )

    def fake_produce(project_dir: Path) -> None:
        states[project_dir.name] = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: "Cần chỉnh lại mô tả cơ chế.",
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _root: [],
        invoke=invoke_via_fake_runner,
    )

    run_queue(tmp_path, deps, agents=(DEFAULT_AGENTS[0],))
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_MEDICAL_REVIEW

    states["kiem-soat-duong-huyet"] = WorkflowState.NEEDS_MEDICAL_REVISION
    run_queue(tmp_path, deps, agents=(DEFAULT_AGENTS[0],))
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_MEDICAL_REVIEW

    states["kiem-soat-duong-huyet"] = WorkflowState.NEEDS_PRODUCTION_REVISION
    run_queue(tmp_path, deps, agents=(DEFAULT_AGENTS[0],))
    assert states["kiem-soat-duong-huyet"] == WorkflowState.AWAITING_VIDEO_REVIEW

    assert len(recorded_prompts) == 4
    for argv in recorded_argv:
        for token in argv:
            assert "review approve" not in token

    for prompt in recorded_prompts:
        stripped = prompt
        for rule in HARD_RULES:
            stripped = stripped.replace(rule, "")
        assert "review approve" not in stripped


def test_produce_runs_python_step(tmp_path: Path) -> None:
    entry = _entry("soi-than")
    add_to_queue(tmp_path, entry)

    project_dir = tmp_path / "projects" / entry.slug
    project_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, WorkflowState] = {
        entry.slug: WorkflowState.MEDICALLY_APPROVED,
    }
    produced_dirs: list[Path] = []
    agent_calls: list[str] = []

    def fake_produce(target_dir: Path) -> None:
        produced_dirs.append(target_dir)
        states[target_dir.name] = WorkflowState.AWAITING_VIDEO_REVIEW

    def unexpected_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        agent_calls.append(prompt)
        raise AssertionError("Agent should not be invoked for produce step")

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=lambda _p: None,
        python_steps={"produce": fake_produce},
        changed_code_paths=lambda _root: [],
        invoke=unexpected_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert produced_dirs == [project_dir]
    assert agent_calls == []
    assert states[entry.slug] == WorkflowState.AWAITING_VIDEO_REVIEW
    assert report.advanced == [entry.slug]
    assert report.at_gate == [entry.slug]
    assert report.blocked == []


def test_once_runs_single_step(tmp_path: Path) -> None:
    entry1 = _entry("chu-de-mot")
    entry2 = _entry("chu-de-hai")
    add_to_queue(tmp_path, entry1)
    add_to_queue(tmp_path, entry2)

    states: dict[str, WorkflowState] = {}
    invoked_slugs: list[str] = []

    def create_project(root: Path, item: QueueEntry) -> Path:
        project_dir = root / "projects" / item.slug
        project_dir.mkdir(parents=True, exist_ok=True)
        states[item.slug] = WorkflowState.TOPIC_SELECTED
        return project_dir

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        slug = log_dir.name
        invoked_slugs.append(slug)
        if states[slug] == WorkflowState.TOPIC_SELECTED:
            states[slug] = WorkflowState.EVIDENCE_READY
        elif states[slug] == WorkflowState.EVIDENCE_READY:
            states[slug] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=create_project,
        read_state=lambda project_dir: states[project_dir.name],
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps, once=True)

    assert invoked_slugs == ["chu-de-mot"]
    assert states["chu-de-mot"] == WorkflowState.EVIDENCE_READY
    assert "chu-de-hai" not in states
    assert report.advanced == ["chu-de-mot"]
    assert report.at_gate == []
    assert report.blocked == []


def test_revise_step_gets_reject_note(tmp_path: Path) -> None:
    entry = _entry("benh-gut")
    add_to_queue(tmp_path, entry)

    project_dir = tmp_path / "projects" / entry.slug
    project_dir.mkdir(parents=True, exist_ok=True)
    states: dict[str, WorkflowState] = {
        entry.slug: WorkflowState.NEEDS_MEDICAL_REVISION,
    }
    captured_prompts: list[str] = []
    reject_note_calls: list[Path] = []
    note_text = "Bổ sung RCT về ngưỡng acid uric mục tiêu dưới 6 mg/dL."

    def get_reject_note(target_dir: Path) -> str | None:
        reject_note_calls.append(target_dir)
        return note_text

    def fake_invoke(
        agents: Any,
        prompt: str,
        *,
        cwd: Path,
        log_dir: Path,
    ) -> AgentResult:
        captured_prompts.append(prompt)
        states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(
            agent="codex",
            ok=True,
            quota_exhausted=False,
            log_path=_log_file(log_dir),
        )

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=get_reject_note,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )

    report = run_queue(tmp_path, deps)

    assert reject_note_calls == [project_dir]
    assert len(captured_prompts) == 1
    assert note_text in captured_prompts[0]
    assert report.advanced == [entry.slug]
    assert report.at_gate == [entry.slug]


def test_agent_prompt_carries_doctor_standards(tmp_path: Path) -> None:
    from healthvideo.workflows import standards

    entry = _entry("benh-gut")
    add_to_queue(tmp_path, entry)
    (tmp_path / "projects" / entry.slug).mkdir(parents=True, exist_ok=True)
    standards.record(tmp_path, slug="khac", gate="medical", revision="001", kind="reject",
                     text="Cắt đuôi giải thích ở mọi dòng.")
    states = {entry.slug: WorkflowState.NEEDS_MEDICAL_REVISION}
    captured: list[str] = []

    def fake_invoke(agents: Any, prompt: str, *, cwd: Path, log_dir: Path) -> AgentResult:
        captured.append(prompt)
        states[log_dir.name] = WorkflowState.AWAITING_MEDICAL_REVIEW
        return AgentResult(agent="codex", ok=True, quota_exhausted=False, log_path=_log_file(log_dir))

    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda p: states[p.name],
        reject_note=lambda _p: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=fake_invoke,
    )
    run_queue(tmp_path, deps)

    assert len(captured) == 1
    assert "Chuẩn của bác sĩ" in captured[0]
    assert "Cắt đuôi giải thích ở mọi dòng." in captured[0]


def test_packaged_topic_is_not_reported_at_gate(tmp_path: Path) -> None:
    add_to_queue(tmp_path, _entry("da-dong-goi"))
    (tmp_path / "projects" / "da-dong-goi").mkdir(parents=True)
    deps = RunDeps(
        create_project=lambda root, item: root / "projects" / item.slug,
        read_state=lambda _project_dir: WorkflowState.PACKAGED,
        reject_note=lambda _project_dir: None,
        python_steps={},
        changed_code_paths=lambda _root: [],
        invoke=lambda *a, **kw: None,
    )
    report = run_queue(tmp_path, deps)
    assert report.at_gate == [] and report.blocked == []


def test_produce_validation_failure_waits_for_changed_inputs(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    manifest = project / 'project.yaml'
    manifest.write_text('revision: 001', encoding='utf-8')
    calls = []

    def produce(_):
        calls.append('produce')
        raise ValueError('visual budget failed: chart_crop')

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    for _ in range(3):
        assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert calls == ['produce']
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'
    assert retry_file.is_file()
    assert read_yaml(retry_file)['kind'] == 'validation'
    manifest.write_text('revision: 002', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert calls == ['produce', 'produce']
    profile = tmp_path / 'profiles/voice.yaml'
    profile.parent.mkdir()
    profile.write_text('model: changed', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert len(calls) == 3
    code = tmp_path / 'src/healthvideo/workflows/produce.py'
    code.parent.mkdir(parents=True)
    code.write_text('# fixed production validation', encoding='utf-8')
    run_queue(tmp_path, deps)
    assert len(calls) == 4
    for relative in ('assets/illustration.png', 'reviews/visual-review.yaml',
                     'reviews/visual/candidates.yaml', 'storyboard/storyboard.yaml'):
        artifact = project / 'revisions/001' / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b'changed')
        before = len(calls)
        run_queue(tmp_path, deps)
        assert len(calls) == before + 1
        run_queue(tmp_path, deps)
        assert len(calls) == before + 1


def test_transient_produce_failure_bounds_retries_with_backoff_and_clears_on_success(
    tmp_path, monkeypatch
):
    from healthvideo.workflows import production_retry

    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    manifest = project / 'project.yaml'
    manifest.write_text('revision: 001', encoding='utf-8')
    clock = {'now': datetime(2026, 10, 25, 9, 0, 0, tzinfo=UTC)}
    monkeypatch.setattr(production_retry, '_now', lambda: clock['now'])
    state = {'value': WorkflowState.MEDICALLY_APPROVED, 'should_fail': True}
    calls = []

    def produce(_):
        calls.append(clock['now'])
        if state['should_fail']:
            raise OSError('temporary network failure')
        state['value'] = WorkflowState.AWAITING_VIDEO_REVIEW

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: state['value'],
        reject_note=lambda _: None, python_steps={'produce': produce},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'

    # Attempt 1 fails -> backoff 120s
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 1
    assert read_yaml(retry_file)['attempts'] == 1

    # Before 120s: held without calling produce
    clock['now'] += timedelta(seconds=60)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 1

    # At 120s: attempt 2 fails -> backoff 600s
    clock['now'] += timedelta(seconds=60)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 2
    assert read_yaml(retry_file)['attempts'] == 2

    # Before 600s: held
    clock['now'] += timedelta(seconds=599)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 2

    # At 600s: attempt 3 fails -> permanently held for this fingerprint
    clock['now'] += timedelta(seconds=1)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 3
    assert read_yaml(retry_file)['attempts'] == 3
    assert read_yaml(retry_file)['retry_after'] is None

    # Even after hours/restart, attempt 4 is not made automatically
    clock['now'] += timedelta(hours=5)
    assert run_queue(tmp_path, deps).blocked == [entry.slug]
    assert len(calls) == 3

    # Input repair + successful produce clears retry record
    state['should_fail'] = False
    manifest.write_text('revision: 002', encoding='utf-8')
    report = run_queue(tmp_path, deps)
    assert len(calls) == 4
    assert report.at_gate == [entry.slug]
    assert not retry_file.exists()


def test_corrupt_retry_file_blocks_without_calling_produce(tmp_path):
    entry = _entry()
    add_to_queue(tmp_path, entry)
    project = tmp_path / 'projects' / entry.slug
    project.mkdir(parents=True)
    retry_file = tmp_path / 'topics/logs' / entry.slug / 'production-retry.yaml'
    retry_file.parent.mkdir(parents=True, exist_ok=True)
    retry_file.write_text(':::corrupt-yaml:::\n[', encoding='utf-8')
    calls = []

    deps = RunDeps(
        create_project=lambda *_: project,
        read_state=lambda _: WorkflowState.MEDICALLY_APPROVED,
        reject_note=lambda _: None, python_steps={'produce': lambda _: calls.append('produce')},
        changed_code_paths=lambda _: [], visual_review_pending=lambda _: False,
    )
    report = run_queue(tmp_path, deps)
    assert report.blocked == [entry.slug]
    assert calls == []
