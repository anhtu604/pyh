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
from healthvideo.workflows.ai_clips import AIClipRights
from healthvideo.workflows.doctor import CheckResult
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review import approve_medical
from tests.helpers import (
    create_v2_project_fixture,
    synthesize_fixture_audio,
)

runner = CliRunner()


@pytest.mark.parametrize(
    "command", [["operator", "orientation"], ["operator", "orientation-search"], ["operator", "orientation-complete"], ["operator", "brief"], ["agent"], ["lease"], ["backup"], ["security-audit"], ["migrate"], ["project", "create"], ["project", "new"], ["project", "migrate"]]
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
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_operator_new_status_select_and_research(tmp_path) -> None:
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
    status = runner.invoke(app, ["operator", "status", str(project), "--json"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["kind"] == "research"
    assert "evidence search" in json.loads(status.stdout)["message"]


def test_operator_help_preserves_existing_cli_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("operator", "review", "topic", "evidence", "produce", "package"):
        assert name in result.stdout


def test_operator_status_is_read_only_without_writer_fields(tmp_path) -> None:
    import json

    project = create_v2_project_fixture(tmp_path)
    before = {
        path.relative_to(project): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    readable = runner.invoke(app, ["operator", "status", str(project), "--json"])
    assert readable.exit_code == 0, readable.stdout
    payload = json.loads(readable.stdout)
    assert payload["kind"] == "prepare_medical_review"
    assert "busy" not in payload
    assert "writer" not in payload

    text = runner.invoke(app, ["operator", "status", str(project)])
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
        ["review", "medical", str(project_dir), "--reviewer", "BS An"],
        input="ok\n",
    )

    assert result.exit_code == 1
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"
    assert list((project_dir / "revisions" / "001" / "reviews").glob("*.yaml")) == []


def test_review_medical_approves_after_the_typed_confirmation(tmp_path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")

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
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"
    records = list((project_dir / "revisions" / "001" / "reviews").glob("medical-*.yaml"))
    assert len(records) == 1
    assert read_yaml(records[0])["reviewer"] == "BS An"


def test_review_video_with_yes_skips_the_confirmation(tmp_path) -> None:
    from datetime import UTC, datetime

    from tests.helpers import advance_v2_project_to_video_review

    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=datetime(2026, 10, 22, tzinfo=UTC))

    result = CliRunner().invoke(
        app, ["review", "video", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 0
    assert read_yaml(project_dir / "project.yaml")["state"] == "video_approved"
    assert len(list((project_dir / "revisions" / "001" / "reviews").glob("video-*.yaml"))) == 1


def test_review_medical_reports_the_state_gate(tmp_path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)

    result = CliRunner().invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    assert result.exit_code == 1
    assert "awaiting_medical_review" in result.stdout


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


def test_status_reports_state_and_a_stale_approval(tmp_path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")
    runner = CliRunner()
    runner.invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )

    approved = runner.invoke(app, ["status", str(project_dir)])
    script_path = project_dir / "revisions" / "001" / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["title"] = "Ăn mặn và tăng huyết áp — bản sửa"
    write_yaml_atomic(script_path, script)
    stale = runner.invoke(app, ["status", str(project_dir)])

    assert approved.exit_code == 0
    assert "state=medically_approved" in approved.stdout
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


def test_review_alias_commands_use_v2_gates(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state="awaiting_medical_review")

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

    approval = project_dir / "revisions/001/reviews/medical-approval.yaml"
    original = approval.read_bytes()
    duplicate = runner.invoke(
        app, ["review", "medical", str(project_dir), "--reviewer", "BS An", "--yes"]
    )
    assert duplicate.exit_code == 1
    assert "already approved" in duplicate.stdout
    assert approval.read_bytes() == original


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

    from tests.helpers import write_explainer_fixture

    write_explainer_fixture(rev_dir, "C01")

    build_res = runner.invoke(app, ["evidence", "build-ledger", str(project_dir)])
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
        "evidence", "search", str(project), "--query", "sodium", "--query", "blood pressure",
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

    result = runner.invoke(app, ["evidence", "search", str(project), "--query", "synthetic"])

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
