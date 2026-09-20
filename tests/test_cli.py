import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app, main
from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.lease import LeaseOwner
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.storage.lease import acquire_write_lease
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.ai_clips import AIClipRights
from healthvideo.workflows.doctor import CheckResult
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import approve_medical
from tests.helpers import (
    create_project_fixture,
    create_v2_project_fixture,
    synthesize_fixture_audio,
)

runner = CliRunner()


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_operator_new_status_select_and_confirm_brief(tmp_path) -> None:
    import json

    from healthvideo.domain.topic import TopicCard

    created = runner.invoke(app, ["operator", "new", str(tmp_path), "--slug", "muoi-va-huyet-ap", "--title", "Ăn mặn"])
    project = tmp_path / "muoi-va-huyet-ap"
    assert created.exit_code == 0, created.stdout
    assert read_yaml(project / "project.yaml")["schema_version"] == "2.0"
    initial = runner.invoke(app, ["operator", "status", str(project), "--json"])
    assert json.loads(initial.stdout)["kind"] == "choose_topic"

    card_file = tmp_path / "card.yaml"
    write_yaml_atomic(card_file, TopicCard(slug="muoi-va-huyet-ap", title="Ăn mặn", question="Ăn mặn ảnh hưởng huyết áp?", synthetic_test_record=True).model_dump(mode="json"))
    selected = runner.invoke(app, ["operator", "select", str(project), "--file", str(card_file)])
    assert selected.exit_code == 0, selected.stdout
    draft = runner.invoke(app, ["operator", "brief", str(project), "--title", "Ăn mặn"])
    assert draft.exit_code == 0, draft.stdout
    assert read_yaml(project / "project.yaml")["state"] == "topic_selected"
    confirmed = runner.invoke(app, ["operator", "brief", str(project), "--title", "Ăn mặn", "--confirm"])
    assert confirmed.exit_code == 1
    assert "awaiting_editorial_direction" in confirmed.stdout
    assert read_yaml(project / "project.yaml")["state"] == "topic_selected"


def test_operator_orientation_command_researches_without_confirming(tmp_path) -> None:
    """The orientation command may research, and must not confirm a brief or a gate."""
    from healthvideo.domain.topic import TopicCard

    runner.invoke(
        app,
        ["operator", "new", str(tmp_path), "--slug", "muoi-va-huyet-ap", "--title", "Ăn mặn"],
    )
    project = tmp_path / "muoi-va-huyet-ap"
    card_file = tmp_path / "card.yaml"
    write_yaml_atomic(
        card_file,
        TopicCard(
            slug="muoi-va-huyet-ap",
            title="Ăn mặn",
            question="Ăn mặn ảnh hưởng huyết áp?",
            synthetic_test_record=True,
        ).model_dump(mode="json"),
    )
    runner.invoke(app, ["operator", "select", str(project), "--file", str(card_file)])
    scope_file = tmp_path / "scope.yaml"
    write_yaml_atomic(
        scope_file,
        {
            "topic_question": "Ăn mặn ảnh hưởng huyết áp?",
            "intended_audience": "Người trưởng thành",
        },
    )

    started = runner.invoke(
        app, ["operator", "orientation", str(project), "--scope", str(scope_file)]
    )

    assert started.exit_code == 0, started.stdout
    assert started.stdout.strip() == "orientation_research_in_progress"
    assert (project / "revisions/001/orientation/scope.yaml").is_file()


def test_operator_help_preserves_existing_cli_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("operator", "project", "review", "topic", "evidence", "produce", "package"):
        assert name in result.stdout


def test_backup_cli_creates_and_restores_a_snapshot(tmp_path) -> None:
    project = create_v2_project_fixture(tmp_path / "source")

    created = runner.invoke(
        app,
        ["backup", "create", str(project), str(tmp_path / "backups"), "--id", "cli"],
    )
    restored = runner.invoke(
        app,
        ["backup", "restore", str(tmp_path / "backups" / "cli"), str(tmp_path / "restored")],
    )

    assert created.exit_code == 0, created.stdout
    assert restored.exit_code == 0, restored.stdout
    assert (tmp_path / "restored" / "project.yaml").read_bytes() == (
        project / "project.yaml"
    ).read_bytes()


def test_mutating_cli_refuses_busy_project_but_status_remains_read_only(tmp_path) -> None:
    from healthvideo.domain.topic import TopicCard

    project = create_v2_project_fixture(tmp_path)
    card_file = tmp_path / "card.yaml"
    write_yaml_atomic(
        card_file,
        TopicCard(
            slug="muoi",
            title="Muối",
            question="Muối ảnh hưởng sức khỏe?",
            synthetic_test_record=True,
        ).model_dump(mode="json"),
    )
    handle = acquire_write_lease(
        project,
        operation="holder",
        active_revision="001",
        owner=LeaseOwner(
            host_id="other-host", pid=999, process_start_fingerprint="other-start"
        ),
        now=datetime.now(tz=UTC),
        ttl_seconds=60,
    )
    before = (project / "project.yaml").read_bytes()

    blocked = runner.invoke(
        app, ["topic", "select", str(project), "--file", str(card_file)]
    )
    readable = runner.invoke(app, ["operator", "status", str(project), "--json"])

    assert blocked.exit_code == 1
    assert "busy" in blocked.stdout.lower()
    assert (project / "project.yaml").read_bytes() == before
    assert readable.exit_code == 0, readable.stdout
    assert '"busy": true' in readable.stdout.lower()
    assert "other-host" in readable.stdout
    handle.release()


def test_lease_inspect_and_explicit_foreign_recovery(tmp_path) -> None:
    project = create_v2_project_fixture(tmp_path)
    handle = acquire_write_lease(
        project,
        operation="holder",
        active_revision="001",
        owner=LeaseOwner(
            host_id="other-host", pid=999, process_start_fingerprint="other-start"
        ),
        now=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        ttl_seconds=60,
    )

    inspected = runner.invoke(app, ["lease", "inspect", str(project)])
    refused = runner.invoke(app, ["lease", "recover", str(project)])
    recovered = runner.invoke(
        app, ["lease", "recover", str(project), "--allow-foreign-host"]
    )

    assert inspected.exit_code == 0, inspected.stdout
    assert "holder" in inspected.stdout
    assert "other-host" in inspected.stdout
    assert str(project) not in inspected.stdout
    assert refused.exit_code == 1
    assert "foreign-host" in refused.stdout
    assert recovered.exit_code == 0, recovered.stdout
    assert handle.lease_id not in recovered.stdout
    assert not (project / ".healthvideo" / "write-lease.yaml").exists()
    assert list((project / ".healthvideo" / "stale-leases").glob("*.yaml"))


def test_review_packet_open_remains_available_while_project_is_busy(tmp_path) -> None:
    project = create_v2_project_fixture(tmp_path)
    handle = acquire_write_lease(
        project,
        operation="holder",
        active_revision="001",
        owner=LeaseOwner(
            host_id="other-host", pid=999, process_start_fingerprint="other-start"
        ),
        now=datetime.now(tz=UTC),
        ttl_seconds=60,
    )

    before = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    result = runner.invoke(app, ["review", "open", str(project), "--gate", "medical"])
    after = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    assert result.exit_code == 0, result.stdout
    assert "<html" in result.stdout.lower()
    assert after == before
    handle.release()


def test_agent_review_cli_requests_and_completes_without_model_call(tmp_path) -> None:
    from datetime import UTC, datetime

    from healthvideo.storage.files import canonical_json_hash

    project = create_v2_project_fixture(tmp_path)
    requested = runner.invoke(app, ["agent", "review-request", str(project), "--reason", "conflicting_evidence"])
    assert requested.exit_code == 0, requested.stdout
    request_dir = Path(requested.stdout.strip())
    request = read_yaml(request_dir / "request.yaml")
    response_file = tmp_path / "review-response.yaml"
    write_yaml_atomic(response_file, {
        "schema_version": "2.0",
        "request_id": request["request_id"],
        "revision": request["revision"],
        "request_hash": canonical_json_hash(request),
        "reviewer": "Second model",
        "model": "fixture",
        "reviewed_at": datetime(2026, 9, 12, tzinfo=UTC).isoformat(),
        "issues": [],
        "summary": "No blocking issue",
    })
    completed = runner.invoke(app, ["agent", "review-complete", str(project), "--file", str(response_file)])
    assert completed.exit_code == 0, completed.stdout
    assert read_yaml(project / "project.yaml")["state"] == "draft_ready"


def test_agent_review_cli_fails_closed_for_invalid_state_or_response(tmp_path) -> None:
    project = create_v2_project_fixture(tmp_path)
    invalid_file = tmp_path / "invalid.yaml"
    write_yaml_atomic(invalid_file, {"bad": True})
    result = runner.invoke(app, ["agent", "review-complete", str(project), "--file", str(invalid_file)])
    assert result.exit_code != 0


def test_cli_configures_windows_stdio_for_vietnamese_output(monkeypatch) -> None:
    configured: list[str] = []

    class Console:
        def reconfigure(self, *, encoding: str) -> None:
            configured.append(encoding)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", Console())
    monkeypatch.setattr(sys, "stderr", Console())

    main()

    assert configured == ["utf-8", "utf-8"]


def test_doctor_allows_a_missing_optional_cuda_check(monkeypatch) -> None:
    """CUDA absence must be reported without making `healthvideo doctor` fail."""
    monkeypatch.setattr(
        "healthvideo.cli.check_environment",
        lambda _run: [
            CheckResult("python", True, "3.14.3", ">=3.11", "Install Python."),
            CheckResult("cuda", False, "not detected", "optional", "CUDA is optional."),
        ],
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "WARN cuda: not detected (requires optional)" in result.stdout


def test_doctor_exits_nonzero_for_a_missing_required_dependency(monkeypatch) -> None:
    """A missing FFmpeg binary must block the environment doctor command."""
    monkeypatch.setattr(
        "healthvideo.cli.check_environment",
        lambda _run: [
            CheckResult(
                "ffmpeg", False, "not found", ">=8", "Install FFmpeg 8 or newer."
            ),
        ],
    )

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Install FFmpeg 8 or newer." in result.stdout


def test_project_new_creates_project_and_reports_duplicate_without_overwrite(
    tmp_path,
) -> None:
    runner = CliRunner()
    command = [
        "project",
        "new",
        "muoi-va-huyet-ap",
        "--title",
        "Ăn mặn và tăng huyết áp",
        "--root",
        str(tmp_path),
    ]

    created = runner.invoke(app, command)
    duplicate = runner.invoke(app, command)

    assert created.exit_code == 0
    assert (tmp_path / "muoi-va-huyet-ap" / "project.yaml").is_file()
    assert duplicate.exit_code != 0
    assert "Project already exists" in duplicate.stdout
    assert read_yaml(tmp_path / "muoi-va-huyet-ap" / "author-brief.yaml")["title"] == (
        "Ăn mặn và tăng huyết áp"
    )


def test_produce_dry_run_prints_remotion_command_without_changing_state(
    tmp_path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    synthesize_fixture_audio(project_dir)
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "awaiting_medical_review"
    write_yaml_atomic(project_dir / "project.yaml", project)
    approve_medical(project_dir, reviewer="BS An")
    original_manifest = (project_dir / "project.yaml").read_bytes()

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 0
    assert "--dir" in result.stdout
    assert "video" in result.stdout
    assert not (project_dir / "renders" / "video.mp4").exists()
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_prints_remotion_command_for_a_cache_hit(tmp_path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    synthesize_fixture_audio(project_dir)
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "awaiting_medical_review"
    write_yaml_atomic(project_dir / "project.yaml", project)
    approve_medical(project_dir, reviewer="BS An")

    def successful_runner(argv: list[str]) -> int:
        output = Path(argv[argv.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic-mp4")
        return 0

    produce_project(project_dir, SilentTTS(), successful_runner)
    original_manifest = (project_dir / "project.yaml").read_bytes()

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 0
    assert "--dir" in result.stdout
    assert "video" in result.stdout
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_rejects_invalid_state_before_printing_command(
    tmp_path,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)
    project = read_yaml(project_dir / "project.yaml")
    project["state"] = "idea"
    write_yaml_atomic(project_dir / "project.yaml", project)

    result = CliRunner().invoke(
        app, ["produce", str(project_dir), "--tts", "silent", "--dry-run"]
    )

    assert result.exit_code == 1
    assert "pnpm --dir" not in result.stdout


def test_review_medical_requires_the_typed_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        ["review", "medical", str(project_dir), "--reviewer", "BS An"],
        input="ok\n",
    )

    assert result.exit_code == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"
    assert list((project_dir / "reviews").glob("*.yaml")) == []


def test_review_medical_approves_after_the_typed_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        [
            "review",
            "medical",
            str(project_dir),
            "--reviewer",
            "BS An",
            "--note",
            "Đã đối chiếu số liệu",
        ],
        input="APPROVE\n",
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "script_approved"
    records = list((project_dir / "reviews").glob("medical-*.yaml"))
    assert len(records) == 1
    assert read_yaml(records[0])["reviewer"] == "BS An"


def test_review_video_with_yes_skips_the_confirmation(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_video_review")

    result = CliRunner().invoke(
        app, ["review", "video", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "approved_to_publish"
    assert len(list((project_dir / "reviews").glob("video-*.yaml"))) == 1


def test_review_medical_reports_the_state_gate(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")

    result = CliRunner().invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 1
    assert "awaiting_medical_review" in result.stdout


def test_revision_create_rejects_v1_project(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    project_dir = tmp_path / "golden-project"
    shutil.copytree(fixture, project_dir)

    result = CliRunner().invoke(
        app, ["revision", "create", str(project_dir), "--reason", "Sửa"]
    )

    assert result.exit_code == 1
    assert "migrate" in result.stdout


def test_revision_create_switches_the_active_revision(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project-v2"
    project_dir = tmp_path / "golden-project-v2"
    shutil.copytree(fixture, project_dir)

    result = CliRunner().invoke(
        app,
        ["revision", "create", str(project_dir), "--reason", "Sửa luận điểm"],
    )

    assert result.exit_code == 0
    assert "002" in result.stdout
    assert read_yaml(project_dir / "project.yaml")["active_revision"] == "002"
    assert (project_dir / "revisions" / "002" / "workflow.yaml").is_file()


def test_project_migrate_dry_run_is_read_only(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    source = tmp_path / "golden-project"
    shutil.copytree(fixture, source)
    before = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }

    result = CliRunner().invoke(app, ["project", "migrate", str(source), "--dry-run"])

    assert result.exit_code == 0
    assert "revisions/001" in result.stdout
    assert "script_approved -> medically_approved" in result.stdout
    assert {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == before
    assert not source.with_name("golden-project-v2").exists()


def test_project_migrate_creates_sibling_and_keeps_source(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    source = tmp_path / "golden-project"
    shutil.copytree(fixture, source)
    before = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }

    result = CliRunner().invoke(app, ["project", "migrate", str(source)])

    assert result.exit_code == 0
    assert "Migrated project:" in result.stdout
    assert source.with_name("golden-project-v2").is_dir()
    assert {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == before


def test_project_migrate_reports_existing_destination(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project"
    source = tmp_path / "golden-project"
    shutil.copytree(fixture, source)
    source.with_name("golden-project-v2").mkdir()

    result = CliRunner().invoke(app, ["project", "migrate", str(source)])

    assert result.exit_code == 1
    assert "existing destination" in result.stdout


def test_status_reports_state_and_a_stale_approval(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")
    runner = CliRunner()
    runner.invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    approved = runner.invoke(app, ["status", str(project_dir)])
    script_path = project_dir / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["title"] = "Ăn mặn và tăng huyết áp — bản sửa"
    write_yaml_atomic(script_path, script)
    stale = runner.invoke(app, ["status", str(project_dir)])

    assert approved.exit_code == 0
    assert "state=script_approved" in approved.stdout
    assert "approval_stale=false" in approved.stdout
    assert "BS An" in approved.stdout
    assert stale.exit_code == 0
    assert "approval_stale=true" in stale.stdout


def test_review_approve_medical_requires_gate_flag_and_confirmation(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )

    result = runner.invoke(
        app,
        [
            "review",
            "approve",
            str(project_dir),
            "--gate",
            "medical",
            "--reviewer",
            "BS Nguyễn Văn An",
            "--yes",
        ],
    )

    assert result.exit_code == 0
    assert "Đã duyệt" in result.stdout


def test_review_reject_then_resume_round_trip(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(
        tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW
    )

    reject_result = runner.invoke(
        app,
        [
            "review",
            "reject",
            str(project_dir),
            "--gate",
            "medical",
            "--reviewer",
            "BS Nguyễn Văn An",
            "--reason",
            "Thiếu nguồn.",
            "--resume-to",
            "draft_ready",
            "--yes",
        ],
    )
    assert reject_result.exit_code == 0

    resume_result = runner.invoke(
        app,
        [
            "review",
            "resume",
            str(project_dir),
            "--gate",
            "medical",
            "--to",
            "draft_ready",
        ],
    )
    assert resume_result.exit_code == 0


def test_review_open_prints_html_without_writing_project(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)

    result = runner.invoke(
        app, ["review", "open", str(project_dir), "--gate", "medical"]
    )

    assert result.exit_code == 0
    packet_path = project_dir / "revisions" / "001" / "reviews" / "medical-packet.html"
    assert not packet_path.exists()
    assert "<html" in result.stdout.lower()


def test_review_v1_commands_are_unaffected(tmp_path: Path) -> None:
    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = runner.invoke(
        app,
        [
            "review",
            "medical",
            str(project_dir),
            "--reviewer",
            "BS Nguyễn Văn An",
            "--yes",
        ],
    )
    assert result.exit_code == 0


def test_cli_topic_create_list_and_reject(tmp_path: Path) -> None:
    inbox = tmp_path / "topics"
    create_res = runner.invoke(
        app,
        [
            "topic",
            "create",
            "--title",
            "Ăn mặn và huyết áp",
            "--question",
            "Ăn mặn có làm tăng huyết áp không?",
            "--slug",
            "an-man-va-huyet-ap",
            "--inbox",
            str(inbox),
        ],
    )
    assert create_res.exit_code == 0
    assert "an-man-va-huyet-ap" in create_res.stdout

    list_res = runner.invoke(app, ["topic", "list", "--inbox", str(inbox)])
    assert list_res.exit_code == 0
    assert "an-man-va-huyet-ap" in list_res.stdout

    card_file = inbox / "an-man-va-huyet-ap.yaml"
    reject_res = runner.invoke(
        app,
        ["topic", "reject", str(card_file), "--reason", "Không phù hợp thời điểm này"],
    )
    assert reject_res.exit_code == 0
    assert "Đã từ chối" in reject_res.stdout


def test_cli_topic_select_advances_project_state(tmp_path: Path) -> None:
    project_dir = tmp_path / "project-v2"
    project_dir.mkdir(parents=True)
    (project_dir / "revisions" / "001" / "topic").mkdir(parents=True)

    initial_manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=WorkflowState.IDEA,
        active_revision="001",
    )
    write_yaml_atomic(
        project_dir / "project.yaml", initial_manifest.model_dump(mode="json")
    )

    inbox = tmp_path / "topics"
    runner.invoke(
        app,
        [
            "topic",
            "create",
            "--title",
            "Ăn mặn và huyết áp",
            "--question",
            "Ăn mặn có làm tăng huyết áp không?",
            "--slug",
            "an-man-va-huyet-ap",
            "--inbox",
            str(inbox),
        ],
    )

    select_res = runner.invoke(
        app,
        [
            "topic",
            "select",
            str(project_dir),
            "--slug",
            "an-man-va-huyet-ap",
            "--inbox",
            str(inbox),
        ],
    )
    assert select_res.exit_code == 0
    assert "Đã chọn chủ đề" in select_res.stdout

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state == WorkflowState.TOPIC_SELECTED


def test_cli_evidence_search_and_build_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MockClient:
        def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
            return [
                CandidateSource(
                    source_id="mock-1",
                    database="pubmed",
                    title="Sodium reduction trial",
                    authors=["Author A"],
                    year=2023,
                    doi="10.1000/1",
                )
            ]

    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: [MockClient()])

    project_dir = tmp_path / "project-v2"
    project_dir.mkdir(parents=True)
    rev_dir = project_dir / "revisions" / "001"
    for sub in ("topic", "author", "evidence", "script", "storyboard", "assets"):
        (rev_dir / sub).mkdir(parents=True)

    write_yaml_atomic(
        rev_dir / "author" / "brief.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn",
            "personal_position": "Giảm muối",
            "reasoning": "Tốt cho tim mạch",
            "emotion": "bình tĩnh",
            "audience_concern": "Huyết áp",
            "phrases_to_keep": [],
        },
    )

    initial_manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=WorkflowState.AUTHOR_BRIEF_READY,
        active_revision="001",
    )
    write_yaml_atomic(
        project_dir / "project.yaml", initial_manifest.model_dump(mode="json")
    )

    search_res = runner.invoke(
        app,
        ["evidence", "search", str(project_dir), "--query", "sodium reduction"],
    )
    assert search_res.exit_code == 0
    assert "Tìm thấy" in search_res.stdout

    # Now simulate a synthesized claim and verified source in evidence directory
    ledger_content = {
        "schema_version": "1.0",
        "records": [
            {
                "id": "R01",
                "title": "Sodium reduction trial",
                "authors": ["Author A"],
                "year": 2023,
                "study_design": "RCT",
                "doi": "10.1000/1",
                "retraction_status": "clean",
            }
        ],
        "claims": [
            {
                "id": "C01",
                "text_public": "Giảm muối giúp hạ áp",
                "text_technical": "Sodium reduction lowers BP",
                "type": "evidence",
                "sources": ["R01"],
            }
        ],
    }
    write_yaml_atomic(rev_dir / "evidence" / "ledger.yaml", ledger_content)

    build_res = runner.invoke(app, ["evidence", "build-ledger", str(project_dir)])
    assert build_res.exit_code == 0
    assert "Đã tổng hợp ledger" in build_res.stdout

    updated = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert updated.state == WorkflowState.EVIDENCE_READY


def test_cli_evidence_ingest(tmp_path: Path) -> None:
    project_dir = tmp_path / "project-v2"
    project_dir.mkdir(parents=True)
    rev_dir = project_dir / "revisions" / "001"
    (rev_dir / "evidence").mkdir(parents=True)

    initial_manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=WorkflowState.RESEARCH_IN_PROGRESS,
        active_revision="001",
    )
    write_yaml_atomic(
        project_dir / "project.yaml", initial_manifest.model_dump(mode="json")
    )

    ingest_res = runner.invoke(
        app,
        [
            "evidence",
            "ingest",
            str(project_dir),
            "--source-id",
            "PMID:12345",
            "--decision",
            "included",
            "--rationale",
            "Well-designed RCT on sodium and blood pressure",
        ],
    )
    assert ingest_res.exit_code == 0
    assert "Đã nạp 1 lựa chọn bằng chứng" in ingest_res.stdout
    assert (rev_dir / "evidence" / "included-sources.yaml").is_file()


def test_tts_benchmark_runs_command_provider_and_reports_objective_verdicts(tmp_path) -> None:
    import json

    fake = tmp_path / "fake_tts.py"
    fake.write_text(
        "import sys, wave\n"
        "text = open(sys.argv[1], encoding='utf-8').read()\n"
        "words = len(text.split())\n"
        "with wave.open(sys.argv[2], 'wb') as w:\n"
        "    w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)\n"
        "    w.writeframes(bytes([16, 0]) * (48000 * words // 3))\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        "cases:\n  - id: so-lieu\n    text: Huyết áp một trăm bốn mươi trên chín mươi\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "tts-benchmark", str(cases), "--output", str(tmp_path / "out"),
            "--command", sys.executable, "--arg", str(fake), "--arg", "{input}",
            "--arg", "{output}", "--model-id", "fake-model", "--voice-id", "fake-voice",
        ],
    )
    assert result.exit_code == 0, result.stdout
    report = json.loads((tmp_path / "out" / "benchmark.json").read_text(encoding="utf-8"))
    assert report["summary"] == {"passed": 1, "total": 1}
    assert report["verdicts"][0]["passed"] is True
    assert report["verdicts"][0]["provider_identity"]["model_id"] == "fake-model"
    assert str(fake) not in json.dumps(report)


def test_tts_benchmark_exits_nonzero_when_a_case_fails(tmp_path) -> None:
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases:\n  - id: a\n    text: Xin chào\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "tts-benchmark", str(cases), "--output", str(tmp_path / "out"),
            "--command", sys.executable, "--arg", "-c", "--arg", "raise SystemExit(3)",
            "--arg", "{input}", "--arg", "{output}", "--model-id", "m", "--voice-id", "v",
        ],
    )
    assert result.exit_code == 1
    assert "synthesis_failed:RuntimeError" in result.stdout


def test_tts_benchmark_accepts_asr_command_and_reports_wer(tmp_path) -> None:
    import json

    fake_tts = tmp_path / "fake_tts.py"
    fake_tts.write_text(
        "import sys, wave\n"
        "with wave.open(sys.argv[2], 'wb') as w:\n"
        "    w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)\n"
        "    w.writeframes(bytes([16, 0]) * 96000)\n",
        encoding="utf-8",
    )
    fake_asr = tmp_path / "fake_asr.py"
    fake_asr.write_text(
        "import sys, json\n"
        "json.dump({'text': 'Hãy đo lại sau năm phút.'}, open(sys.argv[2], 'w', encoding='utf-8'))\n",
        encoding="utf-8",
    )
    cases = tmp_path / "cases.yaml"
    cases.write_text("cases:\n  - id: a\n    text: Hãy đo lại sau năm phút.\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "tts-benchmark", str(cases), "--output", str(tmp_path / "out"),
            "--command", sys.executable, "--arg", str(fake_tts), "--arg", "{input}",
            "--arg", "{output}", "--model-id", "m", "--voice-id", "v",
            "--asr-command", sys.executable, "--asr-arg", str(fake_asr),
            "--asr-arg", "{input}", "--asr-arg", "{output}", "--asr-model-id", "fake-asr",
        ],
    )
    assert result.exit_code == 0, result.stdout
    report = json.loads((tmp_path / "out" / "benchmark.json").read_text(encoding="utf-8"))
    assert report["records"][0]["wer"] == 0.0
    assert report["records"][0]["asr_identity"] == {"provider": "command", "model_id": "fake-asr"}


def test_produce_vieneu_requires_voice_and_builds_normalized_command_provider(tmp_path) -> None:
    from healthvideo.cli import build_vieneu_tts

    result = runner.invoke(app, ["produce", str(tmp_path), "--tts", "vieneu"])
    assert result.exit_code == 1
    assert "--voice" in result.stdout

    provider = build_vieneu_tts(
        python=Path("C:/private/tts-venv/python.exe"), voice="Adam", precision="int8"
    )
    identity = provider.cache_identity()
    assert identity == {
        "provider": "command", "model_id": "vieneu-v3-turbo",
        "voice_id": "adam", "runtime_id": "onnx-cpu-int8-loudnorm",
    }
    assert "private" not in str(identity)
    assert provider.inner.arguments[-2:] == ("--precision", "int8")
    assert "--voice" in provider.inner.arguments and "Adam" in provider.inner.arguments


def test_ai_clip_cli_requires_explicit_live_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_calls: list[int] = []
    monkeypatch.setattr(
        "healthvideo.cli._gcloud_access_token", lambda: token_calls.append(1)
    )
    result = runner.invoke(
        app,
        [
            "ai-clip", "generate", str(tmp_path), "--scene-id", "S04",
            "--prompt", "Minh họa", "--duration-seconds", "4",
            "--google-project", "cloud-project", "--location", "us-central1",
            "--source", "source", "--creator", "creator", "--license", "terms",
            "--rights-basis", "confirmed",
        ],
    )
    assert result.exit_code == 1
    assert "--allow-live-generation" in result.stdout
    assert token_calls == []


def test_ai_clip_cli_builds_authoring_request_after_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class StubTransport:
        def __init__(self, **kwargs: object) -> None:
            captured["transport"] = kwargs

    def stub_generate(project_dir: Path, **kwargs: object) -> Path:
        captured["project"] = project_dir
        captured.update(kwargs)
        return project_dir / "revisions/001/assets/ai-clips/S04.mp4"

    monkeypatch.setattr("healthvideo.cli.GoogleVeoTransport", StubTransport)
    monkeypatch.setattr("healthvideo.cli.generate_ai_clip", stub_generate)
    result = runner.invoke(
        app,
        [
            "ai-clip", "generate", str(tmp_path), "--scene-id", "S04",
            "--prompt", "Minh họa", "--duration-seconds", "4",
            "--allow-live-generation", "--google-project", "cloud-project",
            "--location", "us-central1", "--source", "source",
            "--creator", "creator", "--license", "terms",
            "--rights-basis", "confirmed", "--requested-seed", "9",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["scene_id"] == "S04"
    assert captured["requested_seed"] == 9
    assert isinstance(captured["rights"], AIClipRights)
