import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from healthvideo.domain.evidence import (
    CandidateSource,
    EvidenceClaim,
    EvidenceQuestion,
    SourceRecord,
    SourceSelection,
)
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.evidence.clients import ProviderResponseError, PubMedClient
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.evidence import (
    build_evidence_ledger,
    record_question,
    record_source_selections,
    reject_topic_for_lack_of_evidence,
    search_literature,
)


def _setup_project_at(tmp_path: Path, state: WorkflowState) -> Path:
    project_dir = tmp_path / "evidence-project"
    project_dir.mkdir(parents=True, exist_ok=True)
    rev_dir = project_dir / "revisions" / "001"
    for sub in ("topic", "author", "evidence", "script", "storyboard", "assets"):
        (rev_dir / sub).mkdir(parents=True, exist_ok=True)

    # author brief
    write_yaml_atomic(
        rev_dir / "author" / "brief.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "personal_position": "Giảm muối giúp hạ huyết áp",
            "reasoning": "Nghiên cứu lâm sàng chứng minh",
            "emotion": "bình tĩnh",
            "audience_concern": "Sức khỏe tim mạch",
            "phrases_to_keep": [],
        },
    )

    manifest = ProjectManifestV2(
        schema_version="2.0",
        slug="an-man-va-huyet-ap",
        state=state,
        active_revision="001",
    )
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
    return project_dir


def test_record_question_writes_yaml_and_advances_state(tmp_path: Path) -> None:
    project_dir = _setup_project_at(tmp_path, WorkflowState.AUTHOR_BRIEF_READY)
    question = EvidenceQuestion(
        patient_population="Người trưởng thành",
        intervention="Giảm muối",
        outcome="Hạ huyết áp",
        search_keywords=["sodium", "blood pressure"],
    )

    question_path, updated_manifest = record_question(project_dir, question)
    assert question_path.is_file()
    assert updated_manifest.state == WorkflowState.RESEARCH_IN_PROGRESS
    saved = read_yaml(question_path)
    assert saved["intervention"] == "Giảm muối"


def test_search_literature_appends_search_log_and_candidates(tmp_path: Path) -> None:
    project_dir = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    question = EvidenceQuestion(
        patient_population="Người lớn",
        intervention="Giảm muối",
        outcome="Huyết áp",
        search_keywords=["salt reduction"],
    )

    esearch_resp = json.dumps({"esearchresult": {"idlist": ["12345"]}}).encode("utf-8")
    esummary_resp = json.dumps({
        "result": {
            "uids": ["12345"],
            "12345": {
                "title": "Salt trial",
                "authors": [{"name": "Dr A"}],
                "pubdate": "2023",
                "source": "Lancet",
            },
        }
    }).encode("utf-8")

    def mock_transport(req: Request) -> bytes:
        if "esearch.fcgi" in req.full_url:
            return esearch_resp
        if "esummary.fcgi" in req.full_url:
            return esummary_resp
        return b"{}"

    client = PubMedClient(transport=mock_transport)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    log = search_literature(project_dir, question, [client], now=now)
    assert log.retrieved_count == 1

    search_log_file = project_dir / "revisions" / "001" / "evidence" / "search-log.yaml"
    assert search_log_file.is_file()

    candidates_file = project_dir / "revisions" / "001" / "evidence" / "candidates.jsonl"
    assert candidates_file.is_file()
    assert "Salt trial" in candidates_file.read_text(encoding="utf-8")
    second = search_literature(project_dir, question, [client], now=now)
    saved = read_yaml(search_log_file)
    assert saved == {
        "schema_version": "1.0",
        "searches": [log.model_dump(mode="json"), second.model_dump(mode="json")],
    }
    assert len(candidates_file.read_text(encoding="utf-8").splitlines()) == 2


def test_record_source_selections_splits_included_and_excluded(tmp_path: Path) -> None:
    project_dir = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    selections = [
        SourceSelection(source_id="S01", decision="included", reason="Nghiên cứu chất lượng cao"),
        SourceSelection(source_id="S02", decision="excluded", reason="Cỡ mẫu quá nhỏ"),
    ]

    inc_path, exc_path = record_source_selections(project_dir, selections)
    assert inc_path.is_file()
    assert exc_path.is_file()
    inc = read_yaml(inc_path)["sources"]
    exc = read_yaml(exc_path)["sources"]
    assert len(inc) == 1
    assert inc[0]["source_id"] == "S01"
    assert len(exc) == 1
    assert exc[0]["source_id"] == "S02"


def test_build_evidence_ledger_validates_retraction_and_advances_state(tmp_path: Path) -> None:
    project_dir = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)

    clean_source = SourceRecord(
        id="R01",
        title="Valid Trial",
        retraction_status="clean",
        doi="10.1000/1",
    )
    claim = EvidenceClaim(
        id="C01",
        text_public="Ăn bớt mặn giúp huyết áp tốt hơn",
        text_technical="Sodium reduction lowers systolic blood pressure",
        type="evidence",
        sources=["R01"],
        certainty="high",
        population="Người lớn",
        applicability="Phù hợp người Việt",
    )

    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
    ledger_path, manifest = build_evidence_ledger(project_dir, [claim], [clean_source], now=now)

    assert ledger_path.is_file()
    assert manifest.state == WorkflowState.EVIDENCE_READY

    # Retracted source must be rejected
    retracted_source = SourceRecord(
        id="R02",
        title="Retracted Fraud Study",
        retraction_status="retracted",
    )
    retracted_claim = EvidenceClaim(
        id="C02",
        text_public="...",
        text_technical="...",
        type="evidence",
        sources=["R02"],
    )
    with pytest.raises(ValueError, match="retracted"):
        build_evidence_ledger(project_dir, [retracted_claim], [retracted_source], now=now)


def test_reject_topic_for_lack_of_evidence_enters_topic_rejected(tmp_path: Path) -> None:
    project_dir = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)

    manifest = reject_topic_for_lack_of_evidence(
        project_dir, reason="Không tìm thấy nghiên cứu lâm sàng nào đạt chuẩn", now=now
    )
    assert manifest.state == WorkflowState.TOPIC_REJECTED
    assert manifest.side_state is not None
    assert manifest.side_state.reason_code == "Không tìm thấy nghiên cứu lâm sàng nào đạt chuẩn"


@pytest.mark.parametrize("status", ["unverified", "expression_of_concern", "clean"])
def test_mechanism_requires_a_clean_referenced_source(tmp_path: Path, status: str) -> None:
    project = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    claim = EvidenceClaim(
        id="M-TEST-01", type="mechanism", sources=["R-TEST-01"],
        text_public="Mô hình thử gồm hai khối.", text_technical="Synthetic model.",
    )
    source = SourceRecord.model_validate({
        "id": "R-TEST-01", "title": "Nguồn minh họa, không phải tài liệu y khoa",
        "retraction_status": status, "synthetic_test_record": True,
    })
    # An unrelated clean record must not satisfy the claim's requirement.
    unrelated = SourceRecord(
        id="R-TEST-02", title="Nguồn thử khác", retraction_status="clean",
        synthetic_test_record=True,
    )
    if status == "clean":
        path, manifest = build_evidence_ledger(project, [claim], [source, unrelated])
        assert path.is_file()
        assert manifest.state == WorkflowState.EVIDENCE_READY
    else:
        with pytest.raises(ValueError, match="verified source"):
            build_evidence_ledger(project, [claim], [source, unrelated])
        assert not (project / "revisions/001/evidence/ledger.yaml").exists()
        assert read_yaml(project / "project.yaml")["state"] == "research_in_progress"


def test_mechanism_accepts_one_clean_source_among_multiple(tmp_path: Path) -> None:
    project = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    claim = EvidenceClaim(
        id="M-TEST-01", type="mechanism", sources=["R-TEST-01", "R-TEST-02"],
        text_public="Mô hình thử.", text_technical="Synthetic model.",
    )
    sources = [SourceRecord(
        id=source_id, title="Nguồn minh họa", retraction_status=status,
        synthetic_test_record=True,
    ) for source_id, status in [("R-TEST-01", "unverified"), ("R-TEST-02", "clean")]]
    assert build_evidence_ledger(project, [claim], sources)[0].is_file()


class WorkingClient:
    name = "working"

    def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
        return [CandidateSource(source_id="fake-1", database="fake", title="Synthetic trial")]


class BlockedClient:
    name = "pubmed"

    def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
        raise ProviderResponseError("NCBI IP blocked")


def test_search_records_provider_failure_and_keeps_working_candidates(tmp_path: Path) -> None:
    project = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    question = EvidenceQuestion(patient_population="test", intervention="test", outcome="test")
    log = search_literature(project, question, [BlockedClient(), WorkingClient()])
    failed, completed = log.provider_outcomes
    assert failed.provider == "pubmed"
    assert failed.status == "failed"
    assert failed.failure_class == "ProviderResponseError"
    assert failed.error_summary == "NCBI IP blocked"
    assert completed.status == "completed"
    assert completed.result_count == 1
    candidates = project / "revisions/001/evidence/candidates.jsonl"
    assert json.loads(candidates.read_text(encoding="utf-8"))["source_id"] == "fake-1"


@pytest.mark.parametrize("existing", ["legacy", "empty"])
def test_search_preserves_legacy_log_and_accepts_empty_file(tmp_path: Path, existing: str) -> None:
    project = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    question = EvidenceQuestion(patient_population="test", intervention="test", outcome="test")
    path = project / "revisions/001/evidence/search-log.yaml"
    legacy = {
        "database": "multi", "query": "old", "searched_at": "2026-09-12T10:00:00+00:00",
        "total_results": 1, "retrieved_count": 1,
    }
    if existing == "legacy":
        write_yaml_atomic(path, legacy)
    else:
        path.write_text("", encoding="utf-8")
    log = search_literature(project, question, [WorkingClient()])
    searches = read_yaml(path)["searches"]
    assert searches == ([legacy] if existing == "legacy" else []) + [log.model_dump(mode="json")]


def test_search_records_zero_results(tmp_path: Path) -> None:
    class EmptyClient:
        def search(self, query: str, limit: int = 10) -> list[CandidateSource]:
            return []

    project = _setup_project_at(tmp_path, WorkflowState.RESEARCH_IN_PROGRESS)
    question = EvidenceQuestion(patient_population="test", intervention="test", outcome="test")
    outcome, = search_literature(project, question, [EmptyClient()]).provider_outcomes
    assert outcome.status == "zero_results"
    assert outcome.result_count == 0
