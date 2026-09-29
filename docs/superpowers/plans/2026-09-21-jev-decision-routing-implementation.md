# Jev (TypeSafe) Decision Routing Implementation Plan

> Historical plan only. The Jev integration has been removed from the active runtime after a simplification review; do not execute these tasks as the current project plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate TypeSafe Jev as an opt-in, structured decision-routing layer providing advisory topic triage, claim triage, and second-model review recommendations with strict fail-closed safety and zero automated state mutations or medical verdicts.

**Architecture:** An injected adapter isolates the official `typesafe-sdk` behind an internal transport protocol so all workflow and domain layers operate offline with fake transports during development and CI. Advisory decision records are immutable, versioned, write-once, carry canonical input hashes, and never alter project states, claim ledgers, author briefs, or gate approvals.

**Tech Stack:** Python 3.11+ (tested on Python 3.14), Pydantic v2, Typer, PyYAML, pytest, `typesafe-sdk` (optional/injected), `pathlib.Path`.

**Spec:** `docs/superpowers/specs/2026-09-21-jev-decision-routing-design.md`
**Operations Runbook:** `docs/operations/m7-hardening-runbook.md`

## Global Constraints

- Do not write production code or change schemas in planning; do not alter `ProjectManifest`, `ProjectManifestV2`, `WorkflowState`, or `GateKind`.
- Advisory only: Jev output never auto-transitions workflow state, never selects or rejects topics automatically, never alters `TopicScores` or evidence ledger, never issues medical verdicts, never generates script/content, never creates handoff XML packets automatically, never signs gates, and never triggers production, packaging, rendering, or publishing.
- Fail-closed: Missing `TYPESAFE_API_KEY`, transport/network errors, HTTP timeouts, malformed JSON, unrecognized enum/choice, low confidence (< 0.90), or oversized inputs (> 16384 bytes) always resolve cleanly to `manual_review_required` advisory records without throwing unhandled exceptions, altering project state, or writing partial files.
- Data safety & secrets: `TYPESAFE_API_KEY` is loaded from the process environment first, falling back only to `%LOCALAPPDATA%\ProtectYourHealth\typesafe.env` outside the repository. No secrets, credentials, or `.env` files may be committed, logged, or copied into project artifacts.
- Zero raw response / token persistence: Advisory records must never persist raw provider responses, full prompts, or any fields named `token` or matching `_SENSITIVE_KEYS`.
- Injected adapter & zero CI network: The official `typesafe-sdk` must only be used behind an injected `JevTransport` adapter. Unit, contract, and E2E tests must never make live network calls and must rely solely on fake transports. Live network calls are restricted to explicit operator invocation of `healthvideo jev check --live`.
- Platform & path conventions: Internal paths must use `pathlib.Path` and POSIX-normalized forward slashes in records and manifests for Windows/PowerShell compatibility.
- Untracked files: Existing untracked files are user-owned; never touch, stage, or modify them.
- Produce, package, and render boundaries: Do not add network calls or decision dependencies to `produce`, `package`, or `render`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/healthvideo/jev/__init__.py` | Package root for Jev decision routing. |
| `src/healthvideo/jev/config.py` | Safe secret resolution (`TYPESAFE_API_KEY`), precedence, masking, input limits (`max_input_bytes = 16384`), and timeout configuration. |
| `src/healthvideo/domain/jev_decision.py` | Immutable Pydantic models for request inputs (`TopicTriageInput`, `ClaimTriageInput`, `SecondModelRoutingInput`), outcome enums, and versioned advisory records (`JevAdvisoryRecord`) with input hash and sensitive key redaction. |
| `src/healthvideo/jev/client.py` | Injected `JevTransport` protocol, `FakeJevTransport` test double, `TypeSafeSdkTransport` concrete SDK adapter (using `typesafe_sdk.Choice` and `system_one`), canonical hashing, and `JevClient` with fail-closed decision methods. |
| `src/healthvideo/workflows/jev_triage.py` | Pure advisory workflows (`triage_topic_advisory`, `triage_claims_advisory`, `recommend_second_model_review`) reading domain data and optionally writing write-once advisory YAML without project mutation. |
| `src/healthvideo/commands/jev.py` | Explicit CLI subcommands (`healthvideo jev check`, `triage-topic`, `triage-claims`, `recommend-review`). |
| `src/healthvideo/cli.py` | CLI registration of `jev` command group. |
| `tests/jev/test_config.py` | Unit tests for configuration, precedence, fallback, and masking. |
| `tests/domain/test_jev_decision.py` | Domain unit tests for immutability, timezone validation, hash format, and sensitive key rejection. |
| `tests/jev/test_client.py` | Protocol, adapter, and client unit tests covering success paths and all fail-closed modes. |
| `tests/workflows/test_jev_triage.py` | Workflow tests verifying read-only execution, write-once artifact generation, and zero state mutation. |
| `tests/test_jev_cli.py` | CLI invocation and output format tests. |
| `tests/test_security.py` | Security audit verification confirming Jev artifacts pass `audit_project` and adhere to M7 constraints. |
| `tests/e2e/test_jev_advisory.py` | End-to-end integration and non-transition regression test. |

---

### Task 1: Jev Configuration, Secret Resolution, and Input Limits

**Files:**
- Create: `src/healthvideo/jev/__init__.py`
- Create: `src/healthvideo/jev/config.py`
- Create: `tests/jev/__init__.py`
- Create: `tests/jev/test_config.py`

**Interfaces:**
- Consumes: `os.environ`, `pathlib.Path`
- Produces:
  - `JevConfig(api_key: str | None = None, base_url: str | None = None, model: str = "jev-v1", confidence_threshold: float = 0.90, timeout_seconds: float = 10.0, max_input_bytes: int = 16384)`
  - `resolve_jev_config(env: Mapping[str, str] | None = None, appdata_dir: Path | None = None) -> JevConfig`
  - Property: `JevConfig.is_configured -> bool`
  - Property: `JevConfig.masked_key -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/jev/test_config.py
from collections.abc import Mapping
from pathlib import Path

from healthvideo.jev.config import JevConfig, resolve_jev_config


def test_resolve_config_from_process_env_precedence(tmp_path: Path) -> None:
    # Arrange appdata file
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("TYPESAFE_API_KEY=file-secret-key\n", encoding="utf-8")

    env: Mapping[str, str] = {
        "TYPESAFE_API_KEY": "env-secret-key",
        "TYPESAFE_MODEL": "jev-custom-model",
    }

    config = resolve_jev_config(env=env, appdata_dir=appdata)

    assert config.api_key == "env-secret-key"
    assert config.model == "jev-custom-model"
    assert config.is_configured is True
    assert config.masked_key == "***"
    assert "env-secret-key" not in repr(config)
    assert "env-secret-key" not in str(config)


def test_resolve_config_from_local_appdata_fallback(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("TYPESAFE_API_KEY=file-fallback-key\n", encoding="utf-8")

    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key == "file-fallback-key"
    assert config.is_configured is True
    assert "file-fallback-key" not in repr(config)


def test_resolve_config_missing_fails_closed(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key is None
    assert config.is_configured is False
    assert config.masked_key == "not configured"
    assert config.confidence_threshold == 0.90
    assert config.max_input_bytes == 16384


def test_resolve_config_ignores_malformed_file(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    secret_dir = appdata / "ProtectYourHealth"
    secret_dir.mkdir(parents=True)
    (secret_dir / "typesafe.env").write_text("MALFORMED_LINE_WITHOUT_EQUALS\n", encoding="utf-8")

    config = resolve_jev_config(env={}, appdata_dir=appdata)

    assert config.api_key is None
    assert config.is_configured is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .venv\Scripts\python.exe -m pytest tests/jev/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'healthvideo.jev'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/jev/__init__.py
"""Jev structured decision-routing integration package."""

# src/healthvideo/jev/config.py
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JevConfig:
    api_key: str | None = None
    base_url: str | None = None
    model: str = "jev-v1"
    confidence_threshold: float = 0.90
    timeout_seconds: float = 10.0
    max_input_bytes: int = 16384

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @property
    def masked_key(self) -> str:
        return "***" if self.is_configured else "not configured"

    def __repr__(self) -> str:
        return (
            f"JevConfig(api_key={self.masked_key!r}, model={self.model!r}, "
            f"confidence_threshold={self.confidence_threshold}, "
            f"timeout_seconds={self.timeout_seconds}, max_input_bytes={self.max_input_bytes})"
        )

    def __str__(self) -> str:
        return self.__repr__()


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip().strip("'\"")
    except OSError:
        return {}
    return values


def resolve_jev_config(
    env: Mapping[str, str] | None = None,
    appdata_dir: Path | None = None,
) -> JevConfig:
    active_env = os.environ if env is None else env
    api_key = active_env.get("TYPESAFE_API_KEY")
    base_url = active_env.get("TYPESAFE_BASE_URL")
    model = active_env.get("TYPESAFE_MODEL", "jev-v1")

    if not api_key:
        local_appdata = (
            appdata_dir
            if appdata_dir is not None
            else (
                Path(active_env["LOCALAPPDATA"])
                if "LOCALAPPDATA" in active_env
                else Path.home() / "AppData" / "Local"
            )
        )
        secret_file = local_appdata / "ProtectYourHealth" / "typesafe.env"
        file_vars = _read_env_file(secret_file)
        api_key = file_vars.get("TYPESAFE_API_KEY")
        if not base_url:
            base_url = file_vars.get("TYPESAFE_BASE_URL")
        if model == "jev-v1" and "TYPESAFE_MODEL" in file_vars:
            model = file_vars["TYPESAFE_MODEL"]

    return JevConfig(
        api_key=api_key.strip() if api_key else None,
        base_url=base_url.strip() if base_url else None,
        model=model.strip() if model else "jev-v1",
        confidence_threshold=0.90,
        timeout_seconds=10.0,
        max_input_bytes=16384,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .venv\Scripts\python.exe -m pytest tests/jev/test_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/healthvideo/jev/__init__.py src/healthvideo/jev/config.py tests/jev/__init__.py tests/jev/test_config.py
git commit -m "feat: resolve safe Jev configuration and secrets"
```

---

### Task 2: Immutable Advisory Decision Domain Models

**Files:**
- Create: `src/healthvideo/domain/jev_decision.py`
- Create: `tests/domain/test_jev_decision.py`

**Interfaces:**
- Consumes: `pydantic`, `datetime`, `enum`
- Produces:
  - Enums:
    - `JevDecisionKind`: `TOPIC_TRIAGE = "topic_triage"`, `CLAIM_TRIAGE = "claim_triage"`, `SECOND_MODEL_ROUTING = "second_model_routing"`
    - `TopicPriorityBand`: `HIGH = "high"`, `STANDARD = "standard"`, `LOW = "low"`, `MANUAL_REVIEW_REQUIRED = "manual_review_required"`
    - `ClaimCheckFlag`: `CITATION_CHECK = "citation_check"`, `ABSOLUTE_LANGUAGE_CHECK = "absolute_language_check"`, `POPULATION_APPLICABILITY_CHECK = "population_applicability_check"`, `CLEAR_FOR_REVIEW = "clear_for_review"`, `MANUAL_REVIEW_REQUIRED = "manual_review_required"`
    - `SecondModelRecommendation`: `NOT_RECOMMENDED = "not_recommended"`, `CONSIDER_REVIEW = "consider_review"`, `MANUAL_REVIEW_REQUIRED = "manual_review_required"`
    - `TopicRiskFlag`: `NOVEL_UNVERIFIED_CLAIM = "novel_unverified_claim"`, `HIGH_HARM_POTENTIAL = "high_harm_potential"`, `VULNERABLE_POPULATION = "vulnerable_population"`, `COMMERCIAL_BIAS = "commercial_bias"`
  - Request Input Models:
    - `TopicTriageInput(slug: str, title: str, question: str, target_audience: str, preventive_value: float, evidence_readiness: float, clarity: float, harm_risk: float, production_cost: float)`
    - `ClaimTriageInput(claim_id: str, text_public: str, text_technical: str, claim_type: str, certainty: str, source_count: int, source_types: list[str])`
    - `SecondModelRoutingInput(project_slug: str, revision: str, source_state: str, claim_count: int, unrated_certainty_count: int, low_certainty_count: int, has_doctor_notes: bool)`
  - Advisory Output Model:
    - `JevAdvisoryRecord(schema_version: Literal["1.0"] = "1.0", decision_id: str, decision_kind: JevDecisionKind, normalized_choice: str, confidence: float, model_identifier: str, input_hash: str, created_at: datetime, reason: str, policy_threshold: float = 0.90, flags: list[str] = [], metadata: dict[str, str] = {})`

- [ ] **Step 1: Write the failing test**

```python
# tests/domain/test_jev_decision.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevAdvisoryRecord,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicRiskFlag,
    TopicTriageInput,
)


def test_topic_triage_input_validation() -> None:
    inp = TopicTriageInput(
        slug="sleep-hygiene",
        title="Vệ sinh giấc ngủ",
        question="Làm sao ngủ ngon?",
        target_audience="Người lớn tuổi",
        preventive_value=0.8,
        evidence_readiness=0.9,
        clarity=0.7,
        harm_risk=0.1,
        production_cost=0.3,
    )
    assert inp.slug == "sleep-hygiene"
    with pytest.raises(ValidationError):
        inp.slug = "mutated"  # frozen check


def test_jev_advisory_record_valid_model() -> None:
    now = datetime.now(UTC)
    record = JevAdvisoryRecord(
        decision_id="20260921T120000Z-deadbeef",
        decision_kind=JevDecisionKind.TOPIC_TRIAGE,
        normalized_choice=TopicPriorityBand.HIGH.value,
        confidence=0.95,
        model_identifier="jev-v1",
        input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        created_at=now,
        reason="Độ sẵn sàng bằng chứng cao và rủi ro thấp",
        flags=[TopicRiskFlag.NOVEL_UNVERIFIED_CLAIM.value],
    )
    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.confidence == 0.95
    assert record.is_high_confidence is True


def test_jev_advisory_record_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        JevAdvisoryRecord(
            decision_id="20260921T120000Z-deadbeef",
            decision_kind=JevDecisionKind.CLAIM_TRIAGE,
            normalized_choice=ClaimCheckFlag.CITATION_CHECK.value,
            confidence=0.85,
            model_identifier="jev-v1",
            input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            created_at=datetime(2026, 9, 21, 12, 0, 0),  # naive!
            reason="Thiếu citation",
        )


def test_jev_advisory_record_forbids_sensitive_metadata_keys() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="sensitive or forbidden key"):
        JevAdvisoryRecord(
            decision_id="20260921T120000Z-deadbeef",
            decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
            normalized_choice=SecondModelRecommendation.NOT_RECOMMENDED.value,
            confidence=0.92,
            model_identifier="jev-v1",
            input_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            created_at=now,
            reason="Độ rủi ro thấp",
            metadata={"raw_response": "forbidden-dump", "api_token": "secret"},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .venv\Scripts\python.exe -m pytest tests/domain/test_jev_decision.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'healthvideo.domain.jev_decision'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/domain/jev_decision.py
from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HASH_REGEX = r"^[0-9a-f]{64}$"
_DECISION_ID_REGEX = r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$"
_FORBIDDEN_KEY_PATTERN = re.compile(
    r"(?:token|secret|password|api[_-]?key|raw[_-]?(?:provider[_-]?)?response)",
    re.IGNORECASE,
)


class JevDecisionKind(StrEnum):
    TOPIC_TRIAGE = "topic_triage"
    CLAIM_TRIAGE = "claim_triage"
    SECOND_MODEL_ROUTING = "second_model_routing"


class TopicPriorityBand(StrEnum):
    HIGH = "high"
    STANDARD = "standard"
    LOW = "low"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ClaimCheckFlag(StrEnum):
    CITATION_CHECK = "citation_check"
    ABSOLUTE_LANGUAGE_CHECK = "absolute_language_check"
    POPULATION_APPLICABILITY_CHECK = "population_applicability_check"
    CLEAR_FOR_REVIEW = "clear_for_review"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class SecondModelRecommendation(StrEnum):
    NOT_RECOMMENDED = "not_recommended"
    CONSIDER_REVIEW = "consider_review"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class TopicRiskFlag(StrEnum):
    NOVEL_UNVERIFIED_CLAIM = "novel_unverified_claim"
    HIGH_HARM_POTENTIAL = "high_harm_potential"
    VULNERABLE_POPULATION = "vulnerable_population"
    COMMERCIAL_BIAS = "commercial_bias"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class TopicTriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question: str = ""
    target_audience: str = ""
    preventive_value: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_readiness: float = Field(default=0.5, ge=0.0, le=1.0)
    clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    harm_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    production_cost: float = Field(default=0.5, ge=0.0, le=1.0)


class ClaimTriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1)
    text_public: str = Field(min_length=1)
    text_technical: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    certainty: str = Field(min_length=1)
    source_count: int = Field(ge=0)
    source_types: list[str] = Field(default_factory=list)


class SecondModelRoutingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_slug: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9]{3}$")
    source_state: str = Field(min_length=1)
    claim_count: int = Field(ge=0)
    unrated_certainty_count: int = Field(ge=0)
    low_certainty_count: int = Field(ge=0)
    has_doctor_notes: bool = False


class JevAdvisoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    decision_id: str = Field(pattern=_DECISION_ID_REGEX)
    decision_kind: JevDecisionKind
    normalized_choice: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    model_identifier: str = Field(min_length=1)
    input_hash: str = Field(pattern=_HASH_REGEX)
    created_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    policy_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    flags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def validate_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_clean_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        for key in value:
            if _FORBIDDEN_KEY_PATTERN.search(key):
                raise ValueError(f"metadata contains sensitive or forbidden key: {key!r}")
        return value

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= self.policy_threshold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .venv\Scripts\python.exe -m pytest tests/domain/test_jev_decision.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/healthvideo/domain/jev_decision.py tests/domain/test_jev_decision.py
git commit -m "feat: define immutable Jev advisory decision models"
```

---

### Task 3: Injected Adapter and Fake Transport Protocol

**Files:**
- Create: `src/healthvideo/jev/client.py`
- Create: `tests/jev/test_client.py`

**Interfaces:**
- Consumes: `JevConfig`, `JevAdvisoryRecord`, `TopicTriageInput`, `ClaimTriageInput`, `SecondModelRoutingInput`
- Produces:
  - `JevTransport(Protocol)`:
    - `def decide(self, *, decision_type: str, input_payload: dict[str, Any], model: str) -> dict[str, Any]: ...`
  - `FakeJevTransport(JevTransport)`
  - `TypeSafeSdkTransport(JevTransport)` (uses official `typesafe_sdk.Choice` and `system_one`)
  - `JevClient(config: JevConfig, transport: JevTransport | None = None)`
    - `def evaluate_topic(self, input_data: TopicTriageInput, *, now: datetime | None = None) -> JevAdvisoryRecord`
    - `def evaluate_claim(self, input_data: ClaimTriageInput, *, now: datetime | None = None) -> JevAdvisoryRecord`
    - `def evaluate_second_model(self, input_data: SecondModelRoutingInput, *, now: datetime | None = None) -> JevAdvisoryRecord`

- [ ] **Step 1: Write the failing test**

```python
# tests/jev/test_client.py
from datetime import UTC, datetime
from typing import Any

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicTriageInput,
)
from healthvideo.jev.client import FakeJevTransport, JevClient
from healthvideo.jev.config import JevConfig


def test_client_success_topic_triage() -> None:
    config = JevConfig(api_key="valid-key", model="jev-v1", confidence_threshold=0.90)
    fake_transport = FakeJevTransport(
        default_response={
            "choice": "high",
            "confidence": 0.96,
            "flags": ["novel_unverified_claim"],
            "reason": "Chủ đề có tính sẵn sàng bằng chứng và phòng ngừa cao",
        }
    )
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = TopicTriageInput(
        slug="topic-a",
        title="Title A",
        question="Q?",
        target_audience="Adults",
        preventive_value=0.9,
        evidence_readiness=0.8,
        clarity=0.8,
        harm_risk=0.1,
        production_cost=0.2,
    )

    record = client.evaluate_topic(inp, now=now)

    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.normalized_choice == TopicPriorityBand.HIGH.value
    assert record.confidence == 0.96
    assert record.flags == ["novel_unverified_claim"]
    assert record.created_at == now
    assert len(fake_transport.calls) == 1
    assert fake_transport.calls[0]["decision_type"] == "topic_triage"


def test_client_fail_closed_missing_key() -> None:
    config = JevConfig(api_key=None)
    fake_transport = FakeJevTransport()
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = TopicTriageInput(
        slug="topic-a",
        title="Title A",
        question="Q?",
        target_audience="Adults",
        preventive_value=0.5,
        evidence_readiness=0.5,
        clarity=0.5,
        harm_risk=0.5,
        production_cost=0.5,
    )

    record = client.evaluate_topic(inp, now=now)

    assert record.normalized_choice == TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.0
    assert "chưa được cấu hình" in record.reason.lower() or "not configured" in record.reason.lower()
    assert len(fake_transport.calls) == 0  # Transport never called


def test_client_fail_closed_transport_error() -> None:
    config = JevConfig(api_key="valid-key")

    class FailingTransport:
        def decide(self, *, decision_type: str, input_payload: dict[str, Any], model: str) -> dict[str, Any]:
            raise ConnectionError("TypeSafe API endpoint unreachable")

    client = JevClient(config=config, transport=FailingTransport())  # type: ignore
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = ClaimTriageInput(
        claim_id="CLM-001",
        text_public="Uống nước ấm trị bách bệnh",
        text_technical="Nước ấm chữa mọi bệnh",
        claim_type="evidence",
        certainty="unrated",
        source_count=0,
        source_types=[],
    )

    record = client.evaluate_claim(inp, now=now)

    assert record.normalized_choice == ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.0
    assert "lỗi transport" in record.reason.lower() or "transport error" in record.reason.lower()


def test_client_fail_closed_low_confidence() -> None:
    config = JevConfig(api_key="valid-key", confidence_threshold=0.90)
    fake_transport = FakeJevTransport(
        default_response={
            "choice": "consider_review",
            "confidence": 0.72,  # below 0.90
            "flags": [],
            "reason": "Có thể cần phản biện",
        }
    )
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = SecondModelRoutingInput(
        project_slug="proj-1",
        revision="001",
        source_state="evidence_ready",
        claim_count=3,
        unrated_certainty_count=1,
        low_certainty_count=1,
        has_doctor_notes=True,
    )

    record = client.evaluate_second_model(inp, now=now)

    # Choice forced to manual_review_required because confidence < 0.90
    assert record.normalized_choice == SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.72
    assert "ngưỡng tin cậy" in record.reason.lower() or "confidence below threshold" in record.reason.lower()


def test_client_fail_closed_oversized_input() -> None:
    config = JevConfig(api_key="valid-key", max_input_bytes=100)
    fake_transport = FakeJevTransport()
    client = JevClient(config=config, transport=fake_transport)
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)

    inp = ClaimTriageInput(
        claim_id="CLM-001",
        text_public="A" * 500,  # exceeds 100 bytes limit
        text_technical="B" * 500,
        claim_type="evidence",
        certainty="unrated",
        source_count=0,
        source_types=[],
    )

    record = client.evaluate_claim(inp, now=now)

    assert record.normalized_choice == ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value
    assert record.confidence == 0.0
    assert "kích thước" in record.reason.lower() or "exceeds" in record.reason.lower()
    assert len(fake_transport.calls) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .venv\Scripts\python.exe -m pytest tests/jev/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'healthvideo.jev.client'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/jev/client.py
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    ClaimTriageInput,
    JevAdvisoryRecord,
    JevDecisionKind,
    SecondModelRecommendation,
    SecondModelRoutingInput,
    TopicPriorityBand,
    TopicTriageInput,
)
from healthvideo.jev.config import JevConfig


class JevTransport(Protocol):
    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        """Send decision request and return structured response payload."""
        ...


class FakeJevTransport:
    def __init__(self, default_response: dict[str, Any] | None = None) -> None:
        self.default_response = default_response or {
            "choice": "standard",
            "confidence": 0.95,
            "flags": [],
            "reason": "OK",
        }
        self.calls: list[dict[str, Any]] = []

    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "decision_type": decision_type,
                "input_payload": input_payload,
                "model": model,
            }
        )
        return dict(self.default_response)


class TypeSafeSdkTransport:
    def __init__(self, api_key: str | None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def decide(
        self,
        *,
        decision_type: str,
        input_payload: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("TypeSafe API key is required")
        try:
            from typesafe_sdk import Choice, TypeSafeClient
        except ImportError as err:
            raise RuntimeError(
                "Official typesafe-sdk package is not installed."
            ) from err

        with TypeSafeClient(api_key=self.api_key, base_url=self.base_url) as client:
            if decision_type == "topic_triage":
                response = client.system_one(
                    state=input_payload,
                    questions={
                        "choice": Choice(
                            instructions="Classify topic priority into high, standard, low, or manual_review_required.",
                            criteria={
                                "high": "High preventive value and evidence readiness",
                                "standard": "Standard preventive topic suitable for production",
                                "low": "Low priority or weak preventive focus",
                                "manual_review_required": "Uncertain or flagged for human review",
                            },
                        ),
                    },
                    model=model,
                )
                choice_ans = response.choices.get("choice")
                return {
                    "choice": choice_ans.choice if choice_ans else "manual_review_required",
                    "confidence": choice_ans.confidence if choice_ans else 0.0,
                    "flags": [],
                    "reason": "Topic triage evaluation via TypeSafe System One",
                }
            elif decision_type == "claim_triage":
                response = client.system_one(
                    state=input_payload,
                    questions={
                        "choice": Choice(
                            instructions="Evaluate claim verification flag.",
                            criteria={
                                "citation_check": "Needs additional citation verification",
                                "absolute_language_check": "Contains absolute or unhedged language",
                                "population_applicability_check": "Applicability to target population is unclear",
                                "clear_for_review": "Clean claim ready for medical review",
                                "manual_review_required": "Uncertain or flagged for human review",
                            },
                        ),
                    },
                    model=model,
                )
                choice_ans = response.choices.get("choice")
                return {
                    "choice": choice_ans.choice if choice_ans else "manual_review_required",
                    "confidence": choice_ans.confidence if choice_ans else 0.0,
                    "flags": [choice_ans.choice] if choice_ans and choice_ans.choice != "clear_for_review" else [],
                    "reason": "Claim triage evaluation via TypeSafe System One",
                }
            elif decision_type == "second_model_routing":
                response = client.system_one(
                    state=input_payload,
                    questions={
                        "choice": Choice(
                            instructions="Recommend whether second model review is warranted.",
                            criteria={
                                "not_recommended": "Risk is low, second model review not needed",
                                "consider_review": "High risk or uncertainty, recommend second model review",
                                "manual_review_required": "Uncertain or flagged for human review",
                            },
                        ),
                    },
                    model=model,
                )
                choice_ans = response.choices.get("choice")
                return {
                    "choice": choice_ans.choice if choice_ans else "manual_review_required",
                    "confidence": choice_ans.confidence if choice_ans else 0.0,
                    "flags": [],
                    "reason": "Second-model routing evaluation via TypeSafe System One",
                }
            else:
                raise ValueError(f"Unknown decision_type: {decision_type}")


def _canonical_hash(payload: dict[str, Any], max_bytes: int = 16384) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded = serialized.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError(f"Input payload exceeds maximum allowed size ({len(encoded)} > {max_bytes} bytes)")
    return hashlib.sha256(encoded).hexdigest()


class JevClient:
    def __init__(self, config: JevConfig, transport: JevTransport | None = None) -> None:
        self.config = config
        self.transport = transport or TypeSafeSdkTransport(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def _generate_decision_id(self, now: datetime) -> str:
        timestamp_str = now.strftime("%Y%m%dT%H%M%SZ")
        digest = hashlib.sha256(str(now.timestamp()).encode("utf-8")).hexdigest()[:8]
        return f"{timestamp_str}-{digest}"

    def evaluate_topic(
        self,
        input_data: TopicTriageInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        decision_id = self._generate_decision_id(timestamp)

        try:
            input_hash = _canonical_hash(payload, max_bytes=self.config.max_input_bytes)
        except ValueError as val_err:
            fallback_hash = hashlib.sha256(str(timestamp.timestamp()).encode("utf-8")).hexdigest()
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=fallback_hash,
                created_at=timestamp,
                reason=f"Payload vượt kích thước tối đa: {val_err}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
            )

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="topic_triage",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Topic triage evaluation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                    normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {b.value for b in TopicPriorityBand}
            choice = raw_choice if raw_choice in valid_choices else TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.TOPIC_TRIAGE,
                normalized_choice=TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[TopicPriorityBand.MANUAL_REVIEW_REQUIRED.value],
            )

    def evaluate_claim(
        self,
        input_data: ClaimTriageInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        decision_id = self._generate_decision_id(timestamp)

        try:
            input_hash = _canonical_hash(payload, max_bytes=self.config.max_input_bytes)
        except ValueError as val_err:
            fallback_hash = hashlib.sha256(str(timestamp.timestamp()).encode("utf-8")).hexdigest()
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=fallback_hash,
                created_at=timestamp,
                reason=f"Payload vượt kích thước tối đa: {val_err}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
            )

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="claim_triage",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Claim triage evaluation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                    normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {f.value for f in ClaimCheckFlag}
            choice = raw_choice if raw_choice in valid_choices else ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.CLAIM_TRIAGE,
                normalized_choice=ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[ClaimCheckFlag.MANUAL_REVIEW_REQUIRED.value],
            )

    def evaluate_second_model(
        self,
        input_data: SecondModelRoutingInput,
        *,
        now: datetime | None = None,
    ) -> JevAdvisoryRecord:
        timestamp = now or datetime.now(UTC)
        payload = input_data.model_dump(mode="json")
        decision_id = self._generate_decision_id(timestamp)

        try:
            input_hash = _canonical_hash(payload, max_bytes=self.config.max_input_bytes)
        except ValueError as val_err:
            fallback_hash = hashlib.sha256(str(timestamp.timestamp()).encode("utf-8")).hexdigest()
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=fallback_hash,
                created_at=timestamp,
                reason=f"Payload vượt kích thước tối đa: {val_err}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
            )

        if not self.config.is_configured:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason="TYPESAFE_API_KEY chưa được cấu hình (fail-closed manual review)",
                policy_threshold=self.config.confidence_threshold,
                flags=[SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
            )

        try:
            raw = self.transport.decide(
                decision_type="second_model_routing",
                input_payload=payload,
                model=self.config.model,
            )
            raw_confidence = float(raw.get("confidence", 0.0))
            raw_choice = str(raw.get("choice", "")).strip().lower()
            flags = [str(f) for f in raw.get("flags", [])]
            raw_reason = str(raw.get("reason", "Second-model routing evaluation")).strip()

            if raw_confidence < self.config.confidence_threshold:
                return JevAdvisoryRecord(
                    decision_id=decision_id,
                    decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                    normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                    confidence=raw_confidence,
                    model_identifier=self.config.model,
                    input_hash=input_hash,
                    created_at=timestamp,
                    reason=f"Độ tin cậy ({raw_confidence:.2f}) dưới ngưỡng tin cậy ({self.config.confidence_threshold:.2f})",
                    policy_threshold=self.config.confidence_threshold,
                    flags=flags or [SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
                )

            valid_choices = {r.value for r in SecondModelRecommendation}
            choice = raw_choice if raw_choice in valid_choices else SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value

            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=choice,
                confidence=raw_confidence,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=raw_reason[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=flags,
            )
        except Exception as exc:
            return JevAdvisoryRecord(
                decision_id=decision_id,
                decision_kind=JevDecisionKind.SECOND_MODEL_ROUTING,
                normalized_choice=SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value,
                confidence=0.0,
                model_identifier=self.config.model,
                input_hash=input_hash,
                created_at=timestamp,
                reason=f"Lỗi transport hoặc phản hồi không hợp lệ: {exc}"[:490],
                policy_threshold=self.config.confidence_threshold,
                flags=[SecondModelRecommendation.MANUAL_REVIEW_REQUIRED.value],
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .venv\Scripts\python.exe -m pytest tests/jev/test_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/healthvideo/jev/client.py tests/jev/test_client.py
git commit -m "feat: implement injected Jev adapter and client"
```

---

### Task 4: Advisory Workflows for Topic, Claim, and Review Triage

**Files:**
- Create: `src/healthvideo/workflows/jev_triage.py`
- Create: `tests/workflows/test_jev_triage.py`

**Interfaces:**
- Consumes: `TopicCard`, `EvidenceClaim`, `SourceRecord`, `ProjectManifestV2`, `JevClient`, `JevAdvisoryRecord`
- Produces:
  - `triage_topic_advisory(card: TopicCard, *, client: JevClient | None = None, now: datetime | None = None) -> JevAdvisoryRecord`
  - `triage_claims_advisory(project_dir: Path, *, client: JevClient | None = None, now: datetime | None = None, write_artifact: bool = False) -> tuple[JevAdvisoryRecord, ...]`
  - `recommend_second_model_review(project_dir: Path, *, client: JevClient | None = None, now: datetime | None = None, write_artifact: bool = False) -> JevAdvisoryRecord`

- [ ] **Step 1: Write the failing test**

```python
# tests/workflows/test_jev_triage.py
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.jev_decision import (
    ClaimCheckFlag,
    JevDecisionKind,
    SecondModelRecommendation,
    TopicPriorityBand,
)
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.jev.client import FakeJevTransport, JevClient
from healthvideo.jev.config import JevConfig
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.jev_triage import (
    recommend_second_model_review,
    triage_claims_advisory,
    triage_topic_advisory,
)
from tests.helpers import create_v2_project_fixture


def test_triage_topic_advisory_preserves_card_and_scores() -> None:
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
    scores = TopicScores(preventive_value=0.8, evidence_readiness=0.85)
    card = TopicCard(
        slug="topic-card-test",
        title="Tiêu đề test",
        question="Câu hỏi?",
        scores=scores,
        status="inbox",
        created_at=now,
    )
    transport = FakeJevTransport(
        default_response={
            "choice": "high",
            "confidence": 0.94,
            "flags": [],
            "reason": "Ưu tiên cao",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)

    record = triage_topic_advisory(card, client=client, now=now)

    assert record.decision_kind == JevDecisionKind.TOPIC_TRIAGE
    assert record.normalized_choice == TopicPriorityBand.HIGH.value
    # Guarantee immutability: card status and scores are unchanged
    assert card.status == "inbox"
    assert card.scores.preventive_value == 0.8


def test_triage_claims_advisory_reads_ledger_without_mutation(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "project")
    transport = FakeJevTransport(
        default_response={
            "choice": "citation_check",
            "confidence": 0.91,
            "flags": ["citation_check"],
            "reason": "Cần thêm trích dẫn",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)
    manifest_bytes_before = (project_dir / "project.yaml").read_bytes()
    ledger_bytes_before = (project_dir / "revisions/001/evidence/ledger.yaml").read_bytes()

    records = triage_claims_advisory(project_dir, client=client, write_artifact=True)

    assert len(records) > 0
    assert records[0].normalized_choice == ClaimCheckFlag.CITATION_CHECK.value
    # Manifest and ledger are completely unchanged
    assert (project_dir / "project.yaml").read_bytes() == manifest_bytes_before
    assert (project_dir / "revisions/001/evidence/ledger.yaml").read_bytes() == ledger_bytes_before
    # Advisory artifact written write-once
    advisory_path = project_dir / "revisions/001/evidence/jev-claim-advisory.yaml"
    assert advisory_path.is_file()
    data = read_yaml(advisory_path)
    assert "advisories" in data


def test_recommend_second_model_review_advisory_only(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path / "project")
    transport = FakeJevTransport(
        default_response={
            "choice": "consider_review",
            "confidence": 0.92,
            "flags": [],
            "reason": "Chủ đề rủi ro cao, đề xuất phản biện",
        }
    )
    client = JevClient(config=JevConfig(api_key="k"), transport=transport)
    state_before = (project_dir / "project.yaml").read_text(encoding="utf-8")

    record = recommend_second_model_review(project_dir, client=client, write_artifact=True)

    assert record.decision_kind == JevDecisionKind.SECOND_MODEL_ROUTING
    assert record.normalized_choice == SecondModelRecommendation.CONSIDER_REVIEW.value
    # State has NOT changed to awaiting_second_model_review
    state_after = (project_dir / "project.yaml").read_text(encoding="utf-8")
    assert state_before == state_after
    # No handoff XML was generated
    assert not (project_dir / "revisions/001/handoffs/second-model").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .venv\Scripts\python.exe -m pytest tests/workflows/test_jev_triage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'healthvideo.workflows.jev_triage'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/workflows/jev_triage.py
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.jev_decision import (
    ClaimTriageInput,
    JevAdvisoryRecord,
    SecondModelRoutingInput,
    TopicTriageInput,
)
from healthvideo.domain.topic import TopicCard
from healthvideo.jev.client import JevClient
from healthvideo.jev.config import resolve_jev_config
from healthvideo.storage.files import read_yaml
from healthvideo.storage.immutable import write_yaml_once
from healthvideo.storage.project_layout import resolve_project_layout


def triage_topic_advisory(
    card: TopicCard,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
) -> JevAdvisoryRecord:
    active_client = client or JevClient(config=resolve_jev_config())
    inp = TopicTriageInput(
        slug=card.slug,
        title=card.title,
        question=card.question,
        target_audience=card.target_audience,
        preventive_value=card.scores.preventive_value,
        evidence_readiness=card.scores.evidence_readiness,
        clarity=card.scores.clarity,
        harm_risk=card.scores.harm_risk,
        production_cost=card.scores.production_cost,
    )
    return active_client.evaluate_topic(inp, now=now)


def triage_claims_advisory(
    project_dir: Path,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
    write_artifact: bool = False,
) -> tuple[JevAdvisoryRecord, ...]:
    layout = resolve_project_layout(project_dir)
    ev_dir = layout.artifact_root / "evidence"
    ledger_path = ev_dir / "ledger.yaml"
    claims_path = ev_dir / "claims.yaml"
    sources_path = ev_dir / "records.yaml"

    claims: list[EvidenceClaim] = []
    sources_map: dict[str, SourceRecord] = {}

    if ledger_path.is_file():
        data = read_yaml(ledger_path)
        claims = [EvidenceClaim.model_validate(c) for c in data.get("claims", [])]
        for r in data.get("records", []):
            rec = SourceRecord.model_validate(r)
            sources_map[rec.id] = rec
    elif claims_path.is_file() and sources_path.is_file():
        c_data = read_yaml(claims_path)
        s_data = read_yaml(sources_path)
        raw_claims = c_data.get("claims", c_data) if isinstance(c_data, dict) else c_data
        raw_sources = s_data.get("records", s_data) if isinstance(s_data, dict) else s_data
        claims = [EvidenceClaim.model_validate(c) for c in raw_claims]
        for r in raw_sources:
            rec = SourceRecord.model_validate(r)
            sources_map[rec.id] = rec

    active_client = client or JevClient(config=resolve_jev_config())
    results: list[JevAdvisoryRecord] = []

    for claim in claims:
        source_types = [
            sources_map[s_id].study_design
            for s_id in claim.sources
            if s_id in sources_map and sources_map[s_id].study_design
        ]
        inp = ClaimTriageInput(
            claim_id=claim.id,
            text_public=claim.text_public,
            text_technical=claim.text_technical,
            claim_type=claim.type,
            certainty=claim.certainty,
            source_count=len(claim.sources),
            source_types=source_types,
        )
        record = active_client.evaluate_claim(inp, now=now)
        results.append(record)

    if write_artifact and results:
        target_file = ev_dir / "jev-claim-advisory.yaml"
        payload = {
            "schema_version": "1.0",
            "evaluated_at": (now or datetime.now(UTC)).isoformat(),
            "advisories": [r.model_dump(mode="json") for r in results],
        }
        write_yaml_once(target_file, payload)

    return tuple(results)


def recommend_second_model_review(
    project_dir: Path,
    *,
    client: JevClient | None = None,
    now: datetime | None = None,
    write_artifact: bool = False,
) -> JevAdvisoryRecord:
    layout = resolve_project_layout(project_dir)
    ev_dir = layout.artifact_root / "evidence"
    ledger_path = ev_dir / "ledger.yaml"

    claim_count = 0
    unrated_count = 0
    low_count = 0
    has_notes = False

    if ledger_path.is_file():
        data = read_yaml(ledger_path)
        for c in data.get("claims", []):
            claim = EvidenceClaim.model_validate(c)
            claim_count += 1
            if claim.certainty in ("unrated", ""):
                unrated_count += 1
            elif claim.certainty in ("low", "very_low"):
                low_count += 1
            if claim.doctor_notes.strip():
                has_notes = True

    inp = SecondModelRoutingInput(
        project_slug=layout.manifest.slug,
        revision=getattr(layout.manifest, "active_revision", "001"),
        source_state=getattr(layout.manifest, "state", "unknown"),
        claim_count=claim_count,
        unrated_certainty_count=unrated_count,
        low_certainty_count=low_count,
        has_doctor_notes=has_notes,
    )

    active_client = client or JevClient(config=resolve_jev_config())
    record = active_client.evaluate_second_model(inp, now=now)

    if write_artifact:
        handoffs_dir = layout.artifact_root / "handoffs"
        target_file = handoffs_dir / "jev-review-advisory.yaml"
        payload = {
            "schema_version": "1.0",
            "evaluated_at": (now or datetime.now(UTC)).isoformat(),
            "recommendation": record.model_dump(mode="json"),
        }
        write_yaml_once(target_file, payload)

    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .venv\Scripts\python.exe -m pytest tests/workflows/test_jev_triage.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/healthvideo/workflows/jev_triage.py tests/workflows/test_jev_triage.py
git commit -m "feat: add advisory Jev triage workflows"
```

---

### Task 5: Explicit CLI Commands and Security Audit Integration

**Files:**
- Create: `src/healthvideo/commands/jev.py`
- Modify: `src/healthvideo/cli.py`
- Create: `tests/test_jev_cli.py`
- Modify: `tests/test_security.py`

**Interfaces:**
- Consumes: `jev_triage` workflows, `Typer`, `audit_project`
- Produces:
  - Typer app `jev_app`:
    - `healthvideo jev check [--json] [--live]`
    - `healthvideo jev triage-topic <card_path> [--json]`
    - `healthvideo jev triage-claims <project_dir> [--save] [--json]`
    - `healthvideo jev recommend-review <project_dir> [--save] [--json]`
  - Security audit validation: `audit_project` passes cleanly on valid Jev advisory artifacts and rejects raw provider dumps.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jev_cli.py
from pathlib import Path

from typer.testing import CliRunner

from healthvideo.cli import app
from healthvideo.domain.topic import TopicCard, TopicScores
from healthvideo.storage.files import write_yaml_atomic
from tests.helpers import create_v2_project_fixture

runner = CliRunner()


def test_jev_cli_check_offline() -> None:
    result = runner.invoke(app, ["jev", "check"])
    assert result.exit_code == 0
    assert "TypeSafe Jev status" in result.output
    # Ensure key is masked
    assert "api_key" in result.output.lower()
    assert "***" in result.output or "not configured" in result.output


def test_jev_cli_triage_topic(tmp_path: Path) -> None:
    card_path = tmp_path / "card.yaml"
    card = TopicCard(
        slug="cli-test-card",
        title="CLI Test Topic",
        question="Question?",
        scores=TopicScores(preventive_value=0.9),
    )
    write_yaml_atomic(card_path, card.model_dump(mode="json"))

    result = runner.invoke(app, ["jev", "triage-topic", str(card_path)])
    assert result.exit_code == 0
    assert "Topic triage advisory:" in result.output
    assert "manual_review_required" in result.output or "priority:" in result.output.lower()


def test_jev_cli_triage_claims(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    result = runner.invoke(app, ["jev", "triage-claims", str(project), "--save"])
    assert result.exit_code == 0
    assert "Claim triage advisory:" in result.output


def test_jev_cli_recommend_review(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    result = runner.invoke(app, ["jev", "recommend-review", str(project), "--save"])
    assert result.exit_code == 0
    assert "Second-model recommendation:" in result.output
    # Must instruct operator on manual command if review needed
    assert "healthvideo agent review-request" in result.output or "manual" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .venv\Scripts\python.exe -m pytest tests/test_jev_cli.py -v`
Expected: FAIL with `No such command 'jev'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/commands/jev.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from healthvideo.domain.topic import TopicCard
from healthvideo.jev.config import resolve_jev_config
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.jev_triage import (
    recommend_second_model_review,
    triage_claims_advisory,
    triage_topic_advisory,
)

app = typer.Typer(help="Jev (TypeSafe) structured advisory decision-routing.")


@app.command("check")
def jev_check(
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
    live: Annotated[bool, typer.Option("--live", help="Kiểm tra kết nối tới TypeSafe API (gọi mạng)")] = False,
) -> None:
    """Xác nhận cấu hình và trạng thái opt-in của Jev decision engine."""
    config = resolve_jev_config()
    payload: dict[str, object] = {
        "status": "configured" if config.is_configured else "unconfigured",
        "api_key": config.masked_key,
        "model": config.model,
        "confidence_threshold": config.confidence_threshold,
        "timeout_seconds": config.timeout_seconds,
        "max_input_bytes": config.max_input_bytes,
        "live_check": "skipped" if not live else "unperformed",
    }
    if live and config.is_configured:
        try:
            from typesafe_sdk import TypeSafeClient

            with TypeSafeClient(api_key=config.api_key, base_url=config.base_url) as client:
                models_resp = client.models.list()
                model_names = [m.name for m in models_resp.models] if hasattr(models_resp, "models") else []
                payload["live_check"] = "ok"
                payload["available_models"] = model_names
        except Exception as exc:
            payload["live_check"] = f"failed: {exc}"

    if as_json:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        typer.echo("TypeSafe Jev status:")
        typer.echo(f"  Configuration: {payload['status']}")
        typer.echo(f"  API Key: {payload['api_key']}")
        typer.echo(f"  Model: {payload['model']}")
        typer.echo(f"  Confidence threshold: {payload['confidence_threshold']}")
        if live:
            typer.echo(f"  Live probe: {payload['live_check']}")
            if "available_models" in payload:
                models_list = payload["available_models"]
                typer.echo(f"  Models: {', '.join(models_list) if isinstance(models_list, list) else ''}")


@app.command("triage-topic")
def jev_triage_topic(
    card_path: Annotated[Path, typer.Argument(help="Đường dẫn tới topic card YAML")],
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Chạy topic triage advisory không làm biến đổi topic card."""
    if not card_path.is_file():
        typer.echo(f"Không tìm thấy topic card: {card_path}", err=True)
        raise typer.Exit(code=1)
    card = TopicCard.model_validate(read_yaml(card_path))
    record = triage_topic_advisory(card)
    if as_json:
        typer.echo(record.model_dump_json(indent=2))
    else:
        typer.echo("Topic triage advisory:")
        typer.echo(f"  Priority band: {record.normalized_choice}")
        typer.echo(f"  Confidence: {record.confidence:.2f}")
        typer.echo(f"  Flags: {', '.join(record.flags) if record.flags else 'none'}")
        typer.echo(f"  Reason: {record.reason}")


@app.command("triage-claims")
def jev_triage_claims(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project v2")],
    save: Annotated[bool, typer.Option("--save", help="Lưu advisory record vào revision")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Chạy claim triage advisory cho các claim đã có nguồn."""
    if not project_dir.is_dir():
        typer.echo(f"Không tìm thấy project: {project_dir}", err=True)
        raise typer.Exit(code=1)
    records = triage_claims_advisory(project_dir, write_artifact=save)
    if as_json:
        typer.echo(json.dumps([r.model_dump(mode="json") for r in records], indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Claim triage advisory: Đã đánh giá {len(records)} claim(s)")
        for r in records:
            typer.echo(f"  - Flag: {r.normalized_choice} (conf={r.confidence:.2f}) - {r.reason}")


@app.command("recommend-review")
def jev_recommend_review(
    project_dir: Annotated[Path, typer.Argument(help="Thư mục project v2")],
    save: Annotated[bool, typer.Option("--save", help="Lưu advisory record vào revision")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="In JSON format")] = False,
) -> None:
    """Đề xuất có nên chạy second-model review hay không theo policy."""
    if not project_dir.is_dir():
        typer.echo(f"Không tìm thấy project: {project_dir}", err=True)
        raise typer.Exit(code=1)
    record = recommend_second_model_review(project_dir, write_artifact=save)
    if as_json:
        typer.echo(record.model_dump_json(indent=2))
    else:
        typer.echo("Second-model recommendation:")
        typer.echo(f"  Recommendation: {record.normalized_choice}")
        typer.echo(f"  Confidence: {record.confidence:.2f}")
        typer.echo(f"  Reason: {record.reason}")
        if record.normalized_choice == "consider_review":
            typer.echo("  Lệnh tiếp theo (thủ công):")
            typer.echo("    healthvideo agent review-request <project> --reason high_risk_claim")
```

Register `jev_app` in `src/healthvideo/cli.py`:
```python
# In src/healthvideo/cli.py:
from healthvideo.commands.jev import app as jev_app
# In app registrations:
app.add_typer(jev_app, name="jev")
```

And add security audit coverage in `tests/test_security.py`:
```python
# Add to tests/test_security.py:
def test_security_audit_passes_on_jev_advisory_artifacts(tmp_path: Path) -> None:
    project = create_v2_project_fixture(tmp_path / "project")
    advisory_file = project / "revisions/001/evidence/jev-claim-advisory.yaml"
    advisory_file.write_text("schema_version: '1.0'\nadvisories: []\n", encoding="utf-8")
    findings = audit_project(project)
    assert findings == ()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .venv\Scripts\python.exe -m pytest tests/test_jev_cli.py tests/test_security.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/healthvideo/commands/jev.py src/healthvideo/cli.py tests/test_jev_cli.py tests/test_security.py
git commit -m "feat: expose explicit Jev CLI commands"
```

---

### Task 6: End-to-End Non-Transition and Regression Verification

**Files:**
- Create: `tests/e2e/test_jev_advisory.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: All public CLI commands and workflows
- Produces:
  - Verified non-transition test proving Jev advisory calls leave project manifests, gates, audio, and renders completely untouched.

- [ ] **Step 1: Write the failing test**

```python
# tests/e2e/test_jev_advisory.py
from datetime import UTC, datetime
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
    assert initial_state == WorkflowState.EVIDENCE_READY.value

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

    # 3. Run claim triage via CLI with --save
    res_claim = runner.invoke(app, ["jev", "triage-claims", str(project), "--save"])
    assert res_claim.exit_code == 0

    # 4. Run second-model recommendation via CLI with --save
    res_review = runner.invoke(app, ["jev", "recommend-review", str(project), "--save"])
    assert res_review.exit_code == 0

    # 5. Verify state machine and manifest invariance
    current_manifest = read_yaml(project / "project.yaml")
    assert current_manifest["state"] == initial_state
    assert current_manifest["active_revision"] == initial_manifest["active_revision"]

    # 6. Verify security audit passes on project with Jev advisory artifacts
    findings = audit_project(project)
    assert findings == ()
```

- [ ] **Step 2: Run test to verify it fails if Jev commands are missing**

Run: `& .venv\Scripts\python.exe -m pytest tests/e2e/test_jev_advisory.py -v`
Expected: PASS once Tasks 1-5 are completed.

- [ ] **Step 3: Run full verification suite**

Run:
```powershell
& .venv\Scripts\python.exe -m pytest -q
& .venv\Scripts\python.exe -m ruff check src tests tools
& .venv\Scripts\python.exe tools/export_schemas.py
git diff --check
```
Expected: All tests pass, Ruff clean, zero schema diff.

- [ ] **Step 4: Update README progress table row to complete**

Update row `Jev decision routing` in `README.md` to `complete`.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/test_jev_advisory.py README.md
git commit -m "test: verify Jev non-transition and regression safety"
```

---

## Self-Review

### 1. Spec Coverage Matrix

| Spec Requirement (§) | Plan Task & Verification |
| --- | --- |
| §1–2 Scope limited to advisory topic triage, claim triage, second-model routing | Tasks 2, 3, 4, 5, 6 |
| §2 Out-of-scope: no lit search, content gen, verdicts, gate bypass, render/package changes | Tasks 4, 6 (explicit non-transition assertions) |
| §3 Protocol & injected adapter boundary for TypeSafe SDK | Task 3 (`JevTransport`, `TypeSafeSdkTransport`, `FakeJevTransport`) |
| §3 Immutable advisory record with input hash, choice, confidence, model, reason | Task 2 (`JevAdvisoryRecord`) |
| §4 Secret resolution: `TYPESAFE_API_KEY` env first, `%LOCALAPPDATA%\ProtectYourHealth\typesafe.env` fallback | Task 1 (`resolve_jev_config`) |
| §4 Masked secret, no secret in Git/log/artifact | Tasks 1, 5, 6 (audit and repr tests) |
| §4 No raw provider response, prompt, or `token` field in records | Tasks 2, 3, 5 (`_FORBIDDEN_KEY_PATTERN` and audit) |
| §5 Fail-closed: missing key, transport error, low confidence (<0.90), oversized input (>16384 bytes) -> `manual_review_required` | Tasks 1, 3, 4 (thorough RED tests) |
| §6 Use cases: topic triage, claim triage, second-model recommendation | Tasks 3, 4, 5 |
| §7 Components: `config.py`, `client.py`, `jev_decision.py`, `jev_triage.py`, CLI `healthvideo jev` | Tasks 1–5 |
| §8 Compatibility: zero schema migration, no GateKind change, offline CI | Tasks 1–6 |
| §9 Acceptance criteria & test-first TDD | Tasks 1–6 |

### 2. Placeholder Scan

- Searched for `TODO`, `TBD`, `implement later`, `fill in details`, `similar to`: 0 matches found.
- Every step contains concrete code, concrete commands, and exact expected results.

### 3. Type Consistency

- `JevConfig`: verified attributes across Tasks 1, 3, 4, 5.
- `JevAdvisoryRecord`: verified attributes across Tasks 2, 3, 4, 5, 6.
- `TopicPriorityBand`, `ClaimCheckFlag`, `SecondModelRecommendation`, `TopicRiskFlag`: all enum values consistent.
- `JevTransport`: `decide(decision_type: str, input_payload: dict[str, Any], model: str) -> dict[str, Any]` consistent between protocol and implementations.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-21-jev-decision-routing-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks, fast iteration.
**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
