# Discovery & Evidence Pipeline M3 Implementation Plan

> **For agentic workers:** Use TDD to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the upstream Discovery and Evidence pipeline (§8, §9, §17 of closed-loop workflow design): `TopicCard` and triage inbox, literature search clients (PubMed, Europe PMC, Crossref with strict Scopus exclusion per §17), extended evidence models (`certainty`, `population`, `applicability`, `evidence_direction`, `doctor_notes`), evidence synthesis workflow, review packet update, and CLI wiring, while preserving 100% backward compatibility with v1 and existing v2 golden fixtures.

**Architecture:**
- `src/healthvideo/domain/topic.py`: `TopicSignal`, `TopicScores`, `TopicCard`, deterministic triage ranking.
- `src/healthvideo/workflows/topic.py`: Topic storage in `topics/inbox/`, `topics/selected/`, `topics/rejected/`; doctor select/reject workflow driving `transition_v2(idea -> topic_selected)` with `topic/card.yaml`.
- `src/healthvideo/domain/evidence.py`: Extend `EvidenceClaim` and `SourceRecord` with fields deferred from M2; add `EvidenceQuestion` (PICO), `SearchLogRecord`, `CandidateSource`, `SourceSelection`.
- `src/healthvideo/evidence/clients.py`: Pure Python HTTP adapters via `urllib.request` with injectable transport for 100% offline testability (PubMed E-utilities, Europe PMC REST, Crossref REST, and explicit Scopus exclusion).
- `src/healthvideo/workflows/evidence.py`: Coordinate search logging, candidate ingestion, inclusion/exclusion, and `evidence/ledger.yaml` synthesis driving `research_in_progress -> evidence_ready` or `topic_rejected`.
- `src/healthvideo/workflows/review_html.py`: Update medical packet to render populated certainty, population, applicability, and notes.
- `src/healthvideo/cli.py`: Wire `healthvideo topic` and `healthvideo evidence` subcommands.

**Global Constraints:**
- No invented medical data, DOI, PMID, numbers, or doctor opinions.
- Offline tests only (frozen fixtures/mock transports; no real network, browser, or GPU).
- Tracked fixtures `tests/fixtures/golden-project` and `tests/fixtures/golden-project-v2` must not change by a single byte.
- 100% backward compatibility: existing 407 tests pass without regression.

---

### Task 1: Topic Domain Model & Triage Scoring

**Files:**
- Create: `src/healthvideo/domain/topic.py`
- Create: `tests/domain/test_topic.py`

**Interfaces:**
- `TopicSignal(BaseModel, frozen=True)`: `platform: str`, `url: str | None = None`, `query: str = ""`, `timestamp: datetime`, `trend_metric: float | None = None`.
- `TopicScores(BaseModel, frozen=True)`: `novelty: float = 0.5`, `preventive_value: float = 0.5`, `evidence_readiness: float = 0.5`, `clarity: float = 0.5`, `harm_risk: float = 0.5`, `production_cost: float = 0.5`.
- `TopicCard(BaseModel, frozen=True)`:
  - `schema_version: Literal["2.0"] = "2.0"`
  - `id: str`
  - `slug: str`
  - `title: str`
  - `question: str = ""`
  - `target_audience: str = ""`
  - `signals: list[TopicSignal] = Field(default_factory=list)`
  - `scores: TopicScores = Field(default_factory=TopicScores)`
  - `status: Literal["inbox", "selected", "rejected"] = "inbox"`
  - `rejection_reason: str | None = None`
  - `created_at: datetime | None = None`
  - `expires_at: datetime | None = None`
  - `synthetic_test_record: bool = False`
  - `origin: str | None = None`
- `calculate_triage_rank(scores: TopicScores) -> float`: Pure ranking formula prioritizing high `preventive_value`, high `evidence_readiness`, low `harm_risk`.

---

### Task 2: Topic Inbox & Selection Workflow

**Files:**
- Create: `src/healthvideo/workflows/topic.py`
- Create: `tests/workflows/test_topic.py`

**Interfaces:**
- `list_topics(inbox_dir: Path, status: str | None = None) -> list[TopicCard]`
- `create_topic(inbox_dir: Path, title: str, question: str, slug: str, target_audience: str, now: datetime) -> TopicCard`
- `select_topic(project_dir: Path, card: TopicCard, now: datetime) -> ProjectManifestV2` (writes `revisions/001/topic/card.yaml`, transitions `idea -> topic_selected`)
- `reject_topic(card_path: Path, reason: str, now: datetime) -> TopicCard`

---

### Task 3: Evidence Model Extension & Research Question

**Files:**
- Modify: `src/healthvideo/domain/evidence.py`
- Modify: `tests/domain/test_evidence.py`

**Interfaces:**
- `EvidenceClaim` extended fields: `certainty`, `population`, `applicability`, `evidence_direction`, `doctor_notes`.
- `SourceRecord` extended fields: `pmcid`, `journal`, `retraction_status`, `conflict_of_interest`, `key_findings`.
- `EvidenceQuestion(BaseModel, frozen=True)`: `schema_version: Literal["2.0"] = "2.0"`, `patient_population: str`, `intervention: str`, `comparison: str = ""`, `outcome: str`, `search_keywords: list[str] = Field(default_factory=list)`, `language: str = "vi"`.
- `SearchLogRecord(BaseModel, frozen=True)`: `database: str`, `query: str`, `searched_at: datetime`, `total_results: int`, `retrieved_count: int`.
- `CandidateSource(BaseModel, frozen=True)`: `source_id: str`, `database: str`, `title: str`, `authors: list[str] = Field(default_factory=list)`, `year: int | None = None`, `doi: str | None = None`, `pmid: str | None = None`, `abstract: str = ""`, `venue: str = ""`.
- `SourceSelection(BaseModel, frozen=True)`: `source_id: str`, `decision: Literal["included", "excluded"]`, `reason: str`.

---

### Task 4: Literature Search Clients (PubMed, Europe PMC, Crossref)

**Files:**
- Create: `src/healthvideo/evidence/clients.py`
- Create: `tests/evidence/test_clients.py`

**Interfaces:**
- `Transport = Callable[[urllib.request.Request], bytes]`
- `PubMedClient(email: str, tool: str = "healthvideo", transport: Transport | None = None)`:
  - `search(query: str, limit: int = 10) -> list[str]`
  - `fetch_summaries(pmids: list[str]) -> list[CandidateSource]`
- `EuropePMCClient(transport: Transport | None = None)`:
  - `search(query: str, limit: int = 10) -> list[CandidateSource]`
  - `check_retraction(id_val: str) -> str`
- `CrossrefClient(mailto: str, transport: Transport | None = None)`:
  - `lookup_doi(doi: str) -> CandidateSource | None`
- `ScopusPolicyError(Exception)`: raised on any automated attempt to scrape or retrieve Scopus per §17.

---

### Task 5: Evidence Synthesis & Ledger Builder Workflow

**Files:**
- Create: `src/healthvideo/workflows/evidence.py`
- Create: `tests/workflows/test_evidence.py`

**Interfaces:**
- `search_literature(project_dir: Path, question: EvidenceQuestion, clients: Sequence[Any], now: datetime) -> SearchLogRecord`
- `record_candidate_selection(project_dir: Path, selections: Sequence[SourceSelection], now: datetime) -> None`
- `build_evidence_ledger(project_dir: Path, claims: Sequence[EvidenceClaim], sources: Sequence[SourceRecord], now: datetime) -> Path` (validates references, retraction status, writes `evidence/ledger.yaml`, transitions `research_in_progress -> evidence_ready`)
- `reject_topic_insufficient_evidence(project_dir: Path, reason: str, now: datetime) -> ProjectManifestV2` (transitions `research_in_progress -> topic_rejected`)

---

### Task 6: Review Packet Integration & CLI Wiring

**Files:**
- Modify: `src/healthvideo/workflows/review_html.py`
- Modify: `src/healthvideo/cli.py`
- Modify: `tools/export_schemas.py`
- Modify: `.gitignore`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- `render_medical_packet` table now includes Population, Certainty, Applicability, Doctor Notes columns; drops `_NOT_YET_MODELED`.
- CLI commands:
  - `healthvideo topic list`
  - `healthvideo topic create`
  - `healthvideo topic select`
  - `healthvideo topic reject`
  - `healthvideo evidence search`
  - `healthvideo evidence ingest`
  - `healthvideo evidence build-ledger`
- `.gitignore` ignores `projects/**/evidence/source-cache/`.
- `README.md` updated with M3 progress table rows and acceptance notes.
