import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app, main
from healthvideo.domain.evidence import CandidateSource
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.doctor import CheckResult
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import approve_medical
from tests.helpers import (
    create_v2_project_fixture,
    synthesize_fixture_audio,
)

runner = CliRunner()


@pytest.mark.parametrize(
    "command", [["tts-benchmark"], ["ai-clip"], ["ai-clip", "generate"], ["operator", "orientation"], ["operator", "orientation-search"], ["operator", "orientation-complete"], ["operator", "brief"], ["agent"], ["lease"], ["backup"], ["security-audit"], ["migrate"], ["project", "create"], ["project", "new"], ["project", "migrate"]]
)
def test_removed_commands_absent(command):
    result = CliRunner().invoke(app, [*command, "--help"])
    assert result.exit_code != 0


def test_review_reject_help_lists_resume_states() -> None:
    result = runner.invoke(app, ["review", "reject", "--help"])
    assert result.exit_code == 0
    assert "research_in_progress" in result.stdout
    assert "production_in_progress" in result.stdout


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["step", "version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_operator_new_status_select_and_research(tmp_path) -> None:
    import json

    from healthvideo.domain.topic import TopicCard

    created = runner.invoke(app, ["step", "new", str(tmp_path), "--slug", "muoi-va-huyet-ap", "--title", "Ăn mặn"])
    project = tmp_path / "muoi-va-huyet-ap"
    assert created.exit_code == 0, created.stdout
    assert read_yaml(project / "project.yaml")["schema_version"] == "2.0"
    initial = runner.invoke(app, ["status", str(project), "--json"])
    assert json.loads(initial.stdout)["kind"] == "choose_topic"

    card_file = tmp_path / "card.yaml"
    write_yaml_atomic(card_file, TopicCard(slug="muoi-va-huyet-ap", title="Ăn mặn", question="Ăn mặn ảnh hưởng huyết áp?", synthetic_test_record=True).model_dump(mode="json"))
    selected = runner.invoke(app, ["step", "select", str(project), "--file", str(card_file)])
    assert selected.exit_code == 0, selected.stdout
    status = runner.invoke(app, ["status", str(project), "--json"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["kind"] == "research"
    assert "step evidence-search" in json.loads(status.stdout)["message"]


def test_operator_status_is_read_only_without_writer_fields(tmp_path) -> None:
    import json

    project = create_v2_project_fixture(tmp_path)
    before = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    readable = runner.invoke(app, ["status", str(project), "--json"])
    assert readable.exit_code == 0, readable.stdout
    payload = json.loads(readable.stdout)
    assert payload["kind"] == "prepare_medical_review"
    assert "busy" not in payload
    assert "writer" not in payload

    text = runner.invoke(app, ["status", str(project)])
    assert text.exit_code == 0, text.stdout
    assert "Writer:" not in text.stdout
    assert {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    } == before


def test_review_packet_open_is_read_only(tmp_path) -> None:
    project = create_v2_project_fixture(tmp_path)
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


def test_produce_dry_run_prints_remotion_command_without_changing_state(
    tmp_path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    synthesize_fixture_audio(project_dir / "revisions" / "001")
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
    assert not (project_dir / "revisions" / "001" / "renders" / "video.mp4").exists()
    assert not list((project_dir / "revisions" / "001" / "renders").rglob("*.woff2"))
    assert (project_dir / "project.yaml").read_bytes() == original_manifest


def test_produce_dry_run_prints_remotion_command_for_a_cache_hit(tmp_path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    synthesize_fixture_audio(project_dir / "revisions" / "001")
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
    fixture = Path(__file__).parent / "fixtures" / "golden-project-v2"
    project_dir = tmp_path / "golden-project-v2"
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
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        ["review", "approve", "--gate", "medical", str(project_dir), "--reviewer", "BS An"],
        input="ok\n",
    )

    assert result.exit_code == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"
    assert list((project_dir / "revisions" / "001" / "reviews").glob("*.yaml")) == []


def test_review_medical_approves_with_authenticated_pin(tmp_path, authenticated_pin) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")

    result = CliRunner().invoke(
        app,
        [
            "review", "approve", "--gate", "medical",
            str(project_dir),
            "--reviewer",
            "BS An",
            "--note",
            "Đã đối chiếu số liệu",
        ],
        input="APPROVE\n",
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"
    records = list((project_dir / "revisions" / "001" / "reviews").glob("medical-*.yaml"))
    assert len(records) == 1
    assert read_yaml(records[0])["reviewer"] == "BS An"


def test_review_video_requires_authenticated_pin(tmp_path, authenticated_pin) -> None:
    from datetime import UTC, datetime

    from tests.helpers import advance_v2_project_to_video_review

    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=datetime(2026, 10, 22, tzinfo=UTC))

    result = CliRunner().invoke(
        app, ["review", "approve", "--gate", "video", str(project_dir), "--reviewer", "BS An"]
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"
    assert len(list((project_dir / "revisions" / "001" / "reviews").glob("video-*.yaml"))) == 1


def test_review_medical_reports_the_state_gate(tmp_path, authenticated_pin) -> None:
    project_dir = create_v2_project_fixture(tmp_path)

    result = CliRunner().invoke(
        app, ["review", "approve", "--gate", "medical", str(project_dir), "--reviewer", "BS An"]
    )

    assert result.exit_code == 1
    assert "awaiting_medical_review" in result.stdout


def test_revision_create_switches_the_active_revision(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "golden-project-v2"
    project_dir = tmp_path / "golden-project-v2"
    shutil.copytree(fixture, project_dir)

    result = CliRunner().invoke(
        app,
        ["step", "revision-create", str(project_dir), "--reason", "Sửa luận điểm"],
    )

    assert result.exit_code == 0
    assert "002" in result.stdout
    assert read_yaml(project_dir / "project.yaml")["active_revision"] == "002"
    assert (project_dir / "revisions" / "002" / "workflow.yaml").is_file()


def test_status_reports_operator_action_after_script_change(tmp_path, authenticated_pin) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    runner = CliRunner()
    runner.invoke(
        app, ["review", "approve", "--gate", "medical", str(project_dir), "--reviewer", "BS An"]
    )

    approved = runner.invoke(app, ["status", str(project_dir)])
    script_path = project_dir / "revisions" / "001" / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["title"] = "Ăn mặn và tăng huyết áp — bản sửa"
    write_yaml_atomic(script_path, script)
    stale = runner.invoke(app, ["status", str(project_dir)])

    assert approved.exit_code == 0
    assert "Next action: produce" in approved.stdout
    assert stale.exit_code == 0
    assert "Next action: produce" in stale.stdout


def test_review_approve_medical_requires_gate_and_pin(
    tmp_path: Path, authenticated_pin,
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
        ],
    )

    assert result.exit_code == 0
    assert "Đã duyệt" in result.stdout


def test_review_reject_then_resume_round_trip(tmp_path: Path, authenticated_pin) -> None:
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
            "step", "resume",
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


def test_review_approve_preserves_existing_record(tmp_path: Path, authenticated_pin) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")

    result = runner.invoke(
        app,
        [
            "review", "approve", "--gate", "medical",
            str(project_dir),
            "--reviewer",
            "BS Nguyễn Văn An",
        ],
    )
    assert result.exit_code == 0

    approval = project_dir / "revisions/001/reviews/medical-approval.yaml"
    original = approval.read_bytes()
    duplicate = runner.invoke(
        app, ["review", "approve", "--gate", "medical", str(project_dir), "--reviewer", "BS An"]
    )
    assert duplicate.exit_code == 1
    assert "already approved" in duplicate.stdout
    assert approval.read_bytes() == original


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
    for sub in ("topic", "evidence", "script", "storyboard", "assets"):
        (rev_dir / sub).mkdir(parents=True)


    initial_manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=WorkflowState.TOPIC_SELECTED,
        active_revision="001",
    )
    write_yaml_atomic(
        project_dir / "project.yaml", initial_manifest.model_dump(mode="json")
    )

    search_res = runner.invoke(
        app,
        ["step", "evidence-search", str(project_dir), "--query", "sodium reduction"],
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

    from tests.helpers import write_explainer_fixture

    write_explainer_fixture(rev_dir, "C01")

    build_res = runner.invoke(app, ["step", "build-ledger", str(project_dir)])
    assert build_res.exit_code == 0
    assert "Đã tổng hợp ledger" in build_res.stdout

    updated = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert updated.state == WorkflowState.EVIDENCE_READY


def test_cli_evidence_search_repeatable_queries_and_existing_question(tmp_path, monkeypatch):
    project = tmp_path / "project"
    write_yaml_atomic(project / "project.yaml", ProjectManifestV2(
        slug="test", state=WorkflowState.TOPIC_SELECTED,
    ).model_dump(mode="json"))
    evidence = project / "revisions/001/evidence"
    write_yaml_atomic(evidence / "question.yaml", {
        "patient_population": "adults", "intervention": "salt", "outcome": "BP",
        "search_keywords": ["fallback query"],
    })

    class Client:
        name = "pubmed"

        def search(self, query, limit=10):
            if limit != 3:
                raise ValueError("wrong limit")
            return [CandidateSource(source_id=query, database="pubmed", title="Synthetic record")]

    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: [Client()])
    result = runner.invoke(app, [
        "step", "evidence-search", str(project), "--query", "sodium", "--query", "blood pressure",
        "--limit", "3",
    ])
    assert result.exit_code == 0, result.stdout
    log = read_yaml(evidence / "search-log.yaml")["searches"][-1]
    assert log["retrieved_count"] == 2
    assert log["queries"] == [
        {"query": "sodium", "query_ids": ["pubmed-0"]},
        {"query": "blood pressure", "query_ids": ["pubmed-1"]},
    ]
    assert read_yaml(project / "project.yaml")["state"] == "research_in_progress"
    assert not list((project / "revisions/001/reviews").glob("*"))


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
            "step", "evidence-ingest",
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


@pytest.mark.parametrize("all_failed", [False, True])
def test_cli_evidence_search_surfaces_provider_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, all_failed: bool
) -> None:
    from healthvideo.evidence.clients import ProviderResponseError

    class BlockedClient:
        name = "pubmed"

        def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
            raise ProviderResponseError("NCBI IP blocked")

    class WorkingClient:
        def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
            return [CandidateSource(source_id="fake-1", database="fake", title="Synthetic trial")]

    clients = [BlockedClient()] if all_failed else [BlockedClient(), WorkingClient()]
    monkeypatch.setattr("healthvideo.cli.get_default_clients", lambda: clients)
    project = tmp_path / "project"
    manifest = ProjectManifestV2(
        slug="test", state=WorkflowState.RESEARCH_IN_PROGRESS, active_revision="001"
    )
    write_yaml_atomic(project / "project.yaml", manifest.model_dump(mode="json"))

    result = runner.invoke(app, ["step", "evidence-search", str(project), "--query", "synthetic"])

    assert result.exit_code == (1 if all_failed else 0)
    lines = result.stdout.splitlines()
    assert f"Tìm thấy {0 if all_failed else 1} tài liệu ứng viên." in lines
    assert "pubmed (pubmed-0): ProviderResponseError: NCBI IP blocked" in lines


@pytest.mark.parametrize("changed,exit_code", [("storyboard/storyboard.yaml", 0), ("renders/video.mp4", 1)])
def test_review_reopen_cli(tmp_path: Path, changed: str, exit_code: int) -> None:
    from datetime import UTC, datetime

    from healthvideo.domain.gate_review import GateKind
    from healthvideo.workflows.gate_review import approve_gate

    project = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    approve_gate(project, GateKind.MEDICAL, reviewer="BS An", now=datetime.now(UTC))
    result = runner.invoke(app, [
        "review", "reopen", str(project), "--gate", "medical", "--reviewer", "BS An",
        "--reason", "Revise storyboard", "--changed", changed, "--resume-to", "draft_ready", "--yes",
    ])
    assert result.exit_code == exit_code, result.stdout
    assert ("\u0110\u00e3 m\u1edf l\u1ea1i c\u1ed5ng medical" if exit_code == 0 else "medical re-review") in result.stdout


def test_public_command_surface():
    from typer.main import get_command

    root = get_command(app)
    expected = {
        (): {"topic", "run", "status", "review", "preview", "produce", "package", "doctor", "duyet", "xuong"},
        ("topic",): {"discover", "add", "list"},
        ("review",): {"open", "approve", "reject", "reopen", "set-pin"},
    }
    for path, names in expected.items():
        command = root
        for part in path:
            command = command.commands[part]
        assert {name for name, child in command.commands.items() if not child.hidden} == names
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0
        for name in names:
            assert name in result.stdout
    assert root.commands["step"].hidden


@pytest.fixture
def authenticated_pin(tmp_path, monkeypatch):
    from healthvideo.approver_pin import set_pin
    path = tmp_path / "approver-pin.json"
    set_pin("123456", path=path)
    monkeypatch.setattr("healthvideo.cli.pin_path", lambda: path)
    # CliRunner replaces stdin while invoking; patch that stream's class.
    from typer.testing import _NamedTextIOWrapper
    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: True)
    monkeypatch.setattr("healthvideo.cli.getpass.getpass", lambda prompt: "123456")
    return path


def test_approve_refuses_without_tty(tmp_path):
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["review", "approve", str(project), "--gate", "medical", "--reviewer", "Test"])
    assert result.exit_code != 0
    assert "TTY" in result.stdout
    assert before == {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}


def test_approve_refuses_when_no_pin_set(tmp_path, authenticated_pin):
    authenticated_pin.unlink()
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    result = runner.invoke(app, ["review", "approve", str(project), "--gate", "medical", "--reviewer", "Test"])
    assert result.exit_code != 0
    assert "Chưa đặt PIN" in result.stdout
    assert not list((project / "revisions/001/reviews").glob("*approval*"))


def test_approve_refuses_wrong_pin(tmp_path, authenticated_pin, monkeypatch):
    monkeypatch.setattr("healthvideo.cli.getpass.getpass", lambda prompt: "wrong-pin")
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = runner.invoke(app, ["review", "approve", str(project), "--gate", "medical", "--reviewer", "Test"])
    assert result.exit_code != 0
    assert "PIN không đúng" in result.stdout
    assert before == {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}


def test_approve_with_correct_pin_writes_record(tmp_path, authenticated_pin):
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    result = runner.invoke(app, ["review", "approve", str(project), "--gate", "medical", "--reviewer", "Doctor", "--note", "Checked"])
    assert result.exit_code == 0, result.output
    record = read_yaml(project / "revisions/001/reviews/medical-approval.yaml")
    assert record["reviewer"] == "Doctor"
    assert record["note"] == "Checked"


def test_no_cli_path_approves_without_pin(tmp_path, monkeypatch):
    from typer.core import TyperGroup
    from typer.main import get_command

    from healthvideo import cli
    from healthvideo.workflows import gate_review, review

    calls = []
    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("approval called without PIN")
    monkeypatch.setattr(cli, "approve_gate", forbidden)
    monkeypatch.setattr(gate_review, "approve_gate", forbidden)
    monkeypatch.setattr(review, "approve_medical", forbidden)
    monkeypatch.setattr(review, "approve_video", forbidden)
    from typer.testing import _NamedTextIOWrapper
    monkeypatch.setattr(_NamedTextIOWrapper, "isatty", lambda self: False)
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    paths = []
    def walk(command, path=()):
        if isinstance(command, TyperGroup):
            for name, child in command.commands.items():
                walk(child, (*path, name))
        else:
            paths.append((path, command))
    walk(get_command(app))
    # Exercise every registered leaf, including hidden commands, with all required
    # parameters supplied. Missing-argument parsing must not hide an approval alias.
    import inspect

    def can_approve(callback, seen=None):
        callback = inspect.unwrap(callback)
        if not inspect.isfunction(callback):
            return False
        seen = set() if seen is None else seen
        if callback in seen:
            return False
        seen.add(callback)
        # Globals have already been replaced with the spy, so reaching the spy
        # is evidence of a possible approval call, regardless of command name.
        if callback is forbidden:
            return True
        if not callback.__module__.startswith("healthvideo"):
            return False
        for name in callback.__code__.co_names:
            value = callback.__globals__.get(name)
            if inspect.isfunction(value) and can_approve(value, seen):
                return True
            if inspect.ismodule(value) and value.__name__.startswith("healthvideo"):
                for attr in callback.__code__.co_names:
                    if can_approve(getattr(value, attr, None), seen):
                        return True
        return False

    approvals = []
    for path, command in paths:
        if can_approve(command.callback):
            approvals.append(path)
            for gate in ("medical", "video"):
                if path == ('duyet',):
                    monkeypatch.setattr(cli.factory, 'projects', lambda _: [(project, ProjectManifestV2.model_validate(read_yaml(project / 'project.yaml')))])
                    result = runner.invoke(app, [*path, '--root', str(tmp_path)])
                else:
                    result = runner.invoke(app, [*path, str(project), "--gate", gate, "--reviewer", "Test"])
                assert result.exit_code != 0
                assert "TTY" in result.output
    assert set(approvals) == {("review", "approve"), ("duyet",)}
    assert calls == []
    assert before == {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}


def test_set_pin_requires_tty(tmp_path, monkeypatch):
    path = tmp_path / "pin.json"
    monkeypatch.setattr("healthvideo.cli.pin_path", lambda: path)
    result = runner.invoke(app, ["review", "set-pin"])
    assert result.exit_code != 0
    assert not path.exists()


def test_set_pin_confirmation_and_reset(tmp_path, authenticated_pin, monkeypatch):
    from healthvideo.approver_pin import verify_pin
    answers = iter(["123456", "654321", "different"])
    monkeypatch.setattr("healthvideo.cli.getpass.getpass", lambda prompt: next(answers))
    assert runner.invoke(app, ["review", "set-pin"]).exit_code != 0
    assert verify_pin("123456", path=authenticated_pin)
    answers = iter(["wrong", "654321", "654321"])
    assert runner.invoke(app, ["review", "set-pin"]).exit_code != 0
    assert verify_pin("123456", path=authenticated_pin)
    answers = iter(["123456", "654321", "654321"])
    assert runner.invoke(app, ["review", "set-pin"]).exit_code == 0
    assert verify_pin("654321", path=authenticated_pin)


def test_topic_queue_and_status(tmp_path):
    from healthvideo.storage.queue import load_queue
    added = runner.invoke(app, ["topic", "add", "--slug", "salt-test", "--title", "Salt", "--question", "Salt?", "--note", "Doctor note", "--root", str(tmp_path)])
    assert added.exit_code == 0, added.output
    assert load_queue(tmp_path)[0].doctor_note == "Doctor note"
    duplicate = runner.invoke(app, ["topic", "add", "--slug", "salt-test", "--title", "Salt", "--question", "Salt?", "--root", str(tmp_path)])
    assert duplicate.exit_code == 1
    for command in (["topic", "list"], ["status"]):
        result = runner.invoke(app, [*command, "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "salt-test | Salt | chưa bắt đầu" in result.output
    result = runner.invoke(app, ["status", "--root", str(tmp_path)])
    assert "create" in result.output


def test_run_empty_queue_exits_zero(tmp_path):
    result = runner.invoke(app, ["run", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Chủ đề đã tiến: không có" in result.output


@pytest.mark.parametrize("pubmed_fails", [False, True])
def test_topic_discover_offline(tmp_path, monkeypatch, pubmed_fails):
    from datetime import UTC, datetime

    from healthvideo.discovery.models import MissingApiKey, Signal, SourceError
    calls = []
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    def youtube(query, *, api_key):
        calls.append((query, api_key))
        raise MissingApiKey("missing test key")
    def reddit(query):
        raise SourceError("reddit", "test failure")
    monkeypatch.setattr("healthvideo.cli.youtube.fetch_signals", youtube)
    monkeypatch.setattr("healthvideo.cli.reddit.fetch_signals", reddit)
    monkeypatch.setattr("healthvideo.cli.trends.fetch_signals", lambda: [Signal(source="trends", url="https://example.test", text="salt", fetched=datetime.now(UTC)), Signal(source="trends", url="https://unrelated.test", text="football scores", metric=999999, fetched=datetime.now(UTC))])
    class Client:
        def count(self, query):
            assert query == "salt"
            if pubmed_fails:
                raise ValueError("bad response")
            return 12000
    monkeypatch.setattr("healthvideo.cli.PubMedClient", Client)
    result = runner.invoke(app, ["topic", "discover", "--query", "salt", "--title", "Salt title", "--question", "Salt?", "--layers", "anatomy, physiology", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [("salt", "test-key")]
    from datetime import date
    payload = read_yaml(tmp_path / "topics/discovered" / f"{date.today().isoformat()}.yaml")  # noqa: DTZ011
    assert payload["cards"][0]["pubmed_count"] == (None if pubmed_fails else 12000)
    assert [item["text"] for item in payload["cards"][0]["misconceptions"]] == ["salt"]
    assert payload["cards"][0]["heat"] is None
    assert payload["cards"][0]["layers"] == ["anatomy", "physiology"]
    assert payload["cards"][0]["title"] == "Salt title"
    assert {item["source"] for item in payload["failures"]} == ({"youtube", "reddit", "pubmed"} if pubmed_fails else {"youtube", "reddit"})
    assert "hot" not in result.output.lower()
    assert "reddit: test failure" in result.output


def test_set_pin_first_time(authenticated_pin, monkeypatch):
    from healthvideo.approver_pin import verify_pin
    authenticated_pin.unlink()
    answers = iter(["new-pin", "new-pin"])
    monkeypatch.setattr("healthvideo.cli.getpass.getpass", lambda prompt: next(answers))
    result = runner.invoke(app, ["review", "set-pin"])
    assert result.exit_code == 0, result.output
    assert verify_pin("new-pin", path=authenticated_pin)


@pytest.mark.parametrize("state,expected", [
    ("topic_selected", "research"),
    ("awaiting_medical_review", "chờ cổng awaiting_medical_review"),
    ("awaiting_video_review", "chờ cổng awaiting_video_review"),
])
def test_queue_status_shows_existing_project_and_next_step(tmp_path, state, expected):
    result = runner.invoke(app, ["topic", "add", "--slug", "salt-test", "--title", "Salt", "--question", "Salt?", "--root", str(tmp_path)])
    assert result.exit_code == 0
    project = tmp_path / "projects/salt-test"
    write_yaml_atomic(project / "project.yaml", ProjectManifestV2(slug="salt-test", state=state, active_revision="001").model_dump(mode="json"))
    result = runner.invoke(app, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert f"salt-test | Salt | {state} | {expected}" in result.output


def test_topic_add_rejects_existing_project_and_uses_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects/salt-test").mkdir(parents=True)
    result = runner.invoke(app, ["topic", "add", "--slug", "salt-test", "--title", "Salt", "--question", "Salt?"])
    assert result.exit_code == 1
    assert "Project already exists" in result.output
    assert not (tmp_path / "topics/queue.yaml").exists()


def test_approve_has_no_yes_option(authenticated_pin, tmp_path):
    project = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    result = runner.invoke(app, ["review", "approve", str(project), "--gate", "medical", "--reviewer", "Test", "--yes"])
    assert result.exit_code == 2
    assert not (project / "revisions/001/reviews/medical-approval.yaml").exists()
