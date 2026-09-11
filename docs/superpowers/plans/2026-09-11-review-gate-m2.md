# Review Packet & Gate M2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port medical/video approve+reject+resume onto the v2 kernel (semantic asset manifest, state graph, write-once storage from M1), and generate static HTML review packets, while the v1 MVP review path (`review medical`/`review video`, `workflows/review.py`, `domain/review.py`) keeps working unchanged for schema `1.0` projects.

**Architecture:** New v2-only modules sit beside the v1 ones, selected by the caller reading `project.yaml.schema_version` — the same pattern M1 used for `project_v2.py`/`state_graph.py`. `domain/gate_review.py` defines the v2 approval/rejection records. `workflows/gate_review.py` hashes the artifacts each gate covers, writes the approval/rejection record, and drives `transition_v2`/`_enter_side_state`/`_exit_side_state` (all already built in M1). `workflows/review_html.py` is pure, read-only rendering: plain Python string-building functions with `html.escape`, no new dependency, no filesystem writes of its own. The CLI wires four new v2 subcommands (`review approve/reject/open/resume`) that all take `--gate medical|video`; the two existing v1 subcommands (`review medical`, `review video`) are untouched.

**Tech Stack:** Python 3.11+, Pydantic 2.13.5, Typer 0.27.2, PyYAML 6.0.3, pytest 9.1.1, Ruff 0.16.6; `pathlib.Path`, `hashlib`, `html.escape`; no new runtime dependency in M2 (no Jinja2, no web framework — packets are static files opened locally).

**Spec:** `docs/superpowers/specs/2026-09-09-closed-loop-healthvideo-workflow-design.md`, especially §5 (CLI), §6 (state machine), §7 (asset/invalidation policy), §14 ("Hai gói review"). Design decisions below were confirmed in conversation on 2026-09-11 (no separate brainstorming spec file — see that session for the approved sketch); this plan is the first written record of the concrete choices.

## Global Constraints

- Không đổi hành vi, CLI hay dữ liệu của v1: `src/healthvideo/workflows/review.py`, `src/healthvideo/domain/review.py`, và các lệnh `healthvideo review medical` / `healthvideo review video` giữ nguyên, tiếp tục chỉ nhận project schema `1.0`. M2 **không** đổi tên hay xoá hai lệnh này — dù bản ghi thiết kế ban đầu nói "đổi tên", việc đó sẽ phá v1 đang chạy tốt; thay vào đó bốn lệnh v2 mới (`review approve/reject/open/resume`, đều nhận `--gate medical|video`) khớp đúng cú pháp spec §5 và chỉ nhận schema `2.0`. Nếu người dùng thực sự muốn xoá hai lệnh v1, đó là quyết định riêng cần xác nhận lại, ngoài phạm vi plan này.
- Trước Task 1 phải ghi baseline bằng `python -m pytest -q` và `python -m ruff check src tests tools`. Sau **mỗi** task: focused tests, dual-golden checkpoint (`tests/e2e/test_golden_workflow_versions.py`), full `python -m pytest -q`, `python -m ruff check src tests tools`, `git diff --check`. Không khoá plan vào một con số test cụ thể; tiêu chí là không regression.
- Test hoàn toàn offline: không mạng, không AI, không GPU, không browser thật. Freeze `datetime`/UUID trong mọi test; filesystem thao tác qua `tmp_path`. Golden v1 (`tests/fixtures/golden-project`) và golden v2 (`tests/fixtures/golden-project-v2`) không bị task nào sửa byte trực tiếp — mọi thao tác gate diễn ra trên bản `shutil.copytree` sang `tmp_path`, theo đúng mẫu `test_dual_golden_creates_a_revision_without_touching_the_tracked_fixture` đã có.
- Đường dẫn nội bộ dùng `pathlib.Path`. Approval record dùng `write_yaml_once` (bất biến, một lần mỗi revision — vì `create_revision` không copy `reviews/`, mỗi revision mới bắt đầu với `reviews/` rỗng, nên approval chỉ có thể ghi một lần cho tới khi có revision mới, đúng tinh thần "không tự ký lại"). Rejection record dùng `write_yaml_once` tại đường dẫn có timestamp (như `storage/stages.py`), vì một revision có thể bị reject nhiều lần trước khi được approve. HTML packet dùng `write_text_atomic` (ghi đè được), vì đó là bản render lại từ dữ liệu hiện tại, không phải audit trail.
- Không vượt gate: `approve_gate` bắt buộc gọi `validate_asset_manifest` (cho medical) trước khi cho phép approve; artifact thiếu hoặc sai byte làm approve thất bại, không có đường tắt. CLI approve/reject dùng lại cơ chế gõ xác nhận đã có ở v1 (`typer.prompt`, hằng số `CONFIRMATION`/`REJECT_CONFIRMATION`), có thể bỏ qua bằng `--yes` khi test.
- **Giới hạn dữ liệu đã biết, không được bịa thêm:** `EvidenceClaim` (domain/evidence.py) hiện chỉ có `text_public`, `text_technical`, `type`, `sources`; `SourceRecord` có `title/authors/year/study_design/sample_size/doi/pmid/url`. Không có field `population`, `certainty`, `applicability`, hay "quan điểm bác sĩ theo từng claim" trong model M1. HTML medical packet ở M2 **chỉ hiển thị field thật sự tồn tại trong model**; các mục §14 nói tới nhưng model chưa có (population riêng, certainty, applicability, per-claim doctor note) bị bỏ qua có ghi chú rõ trong packet ("chưa có trong hệ thống"), không tự sinh văn bản thay thế. Mở rộng model đó là việc của milestone sau khi có luồng trích xuất thật (M3+).
- Không commit media/cache/secret. Thêm `projects/**/reviews/*.html` vào `.gitignore` (packet là bản render lại, không phải audit trail); `reviews/*.yaml` (approval/rejection record) tiếp tục được track như các artifact khác của revision.
- README.md cập nhật cùng commit với từng task, theo đúng khuôn mẫu bảng M1.1–M1.10 đã có.

## File map

| File | Trách nhiệm M2 | Quan hệ với v1/M1 |
|---|---|---|
| `src/healthvideo/domain/gate_review.py` | `GateKind`, `GateApprovalRecord`, `GateRejectionRecord` (v2) | Mới, cạnh `domain/review.py` v1 |
| `src/healthvideo/workflows/gate_review.py` | Hash artifact theo gate, `approve_gate`/`reject_gate`/`resume_gate` | Mới, cạnh `workflows/review.py` v1; dùng `state_graph.transition_v2`, `asset_manifest.validate_asset_manifest` |
| `src/healthvideo/workflows/review_html.py` | Render HTML packet y khoa/video, hàm thuần + `html.escape` | Mới |
| `src/healthvideo/cli.py` | Thêm `review approve/reject/open/resume` | Lệnh `review medical/video` v1 giữ nguyên |
| `.gitignore` | Thêm dòng loại trừ packet HTML | Mới dòng |
| `tests/domain/test_gate_review.py` | Test model record | Mới |
| `tests/workflows/test_gate_review.py` | Test approve/reject/resume, cả hai gate | Mới |
| `tests/workflows/test_review_html.py` | Test render HTML | Mới |
| `tests/test_cli.py` | Test CLI 4 lệnh mới | Modify |
| `tests/helpers.py` | Thêm `create_v2_gate_fixture` | Modify |
| `tests/e2e/test_golden_workflow_versions.py` | Checkpoint gate v2 trên golden copy | Modify |
| `README.md` | Tiến độ M2.1–M2.5 | Modify |

---

### Task 1: Gate review v2 domain model

**Files:**
- Create: `src/healthvideo/domain/gate_review.py`
- Create: `tests/domain/test_gate_review.py`
- Modify: `README.md`

**Interfaces:**
- `GateKind(StrEnum)`: `MEDICAL = "medical"`, `VIDEO = "video"`.
- `GateApprovalRecord(BaseModel, frozen=True)`: `schema_version: Literal["2.0"] = "2.0"`, `kind: GateKind`, `reviewer: str`, `reviewed_at: datetime` (tz-aware), `artifact_hashes: dict[str, str]` (non-empty), `note: str = ""`.
- `GateRejectionRecord(BaseModel, frozen=True)`: `schema_version: Literal["2.0"] = "2.0"`, `kind: GateKind`, `reviewer: str`, `reviewed_at: datetime` (tz-aware), `reason: str` (non-blank), `resume_state: WorkflowState`, `artifact_hashes: dict[str, str]` (non-empty — may hash whatever currently exists, even if incomplete).

- [ ] **Step 1: Ghi baseline**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Expected: cả hai PASS; ghi số test và ngày vào hàng `M2.1` mới trong `README.md` trước khi commit task.

- [ ] **Step 2: Viết RED tests**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from healthvideo.domain.gate_review import GateApprovalRecord, GateKind, GateRejectionRecord
from healthvideo.domain.project_v2 import WorkflowState

REVIEWER = "BS Nguyễn Văn An"


def test_gate_approval_rejects_blank_reviewer_and_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer="   ",
            reviewed_at=datetime.now(UTC),
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(),
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )


def test_gate_approval_requires_at_least_one_artifact_hash() -> None:
    with pytest.raises(ValidationError):
        GateApprovalRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(UTC),
            artifact_hashes={},
        )


def test_gate_rejection_requires_non_blank_reason() -> None:
    with pytest.raises(ValidationError):
        GateRejectionRecord(
            kind=GateKind.MEDICAL,
            reviewer=REVIEWER,
            reviewed_at=datetime.now(UTC),
            reason="   ",
            resume_state=WorkflowState.DRAFT_READY,
            artifact_hashes={"evidence/ledger.yaml": "0" * 64},
        )


def test_gate_rejection_round_trips_resume_state() -> None:
    record = GateRejectionRecord(
        kind=GateKind.VIDEO,
        reviewer=REVIEWER,
        reviewed_at=datetime.now(UTC),
        reason="Màu sắc chưa đúng brand.",
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        artifact_hashes={"renders/render-manifest.json": "1" * 64},
    )
    assert record.resume_state is WorkflowState.PRODUCTION_IN_PROGRESS
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/domain/test_gate_review.py -v`

Expected: FAIL vì `healthvideo.domain.gate_review` chưa tồn tại.

- [ ] **Step 4: Cài model tối thiểu**

```python
"""v2 gate approval/rejection records — reviewer accountability for one gate."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthvideo.domain.project_v2 import WorkflowState


class GateKind(StrEnum):
    MEDICAL = "medical"
    VIDEO = "video"


class GateApprovalRecord(BaseModel):
    """Audit trail of one gate approval, bound to the artifacts it covers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    kind: GateKind
    reviewer: str
    reviewed_at: datetime
    artifact_hashes: dict[str, str]
    note: str = ""

    @field_validator("reviewer")
    @classmethod
    def _require_named_reviewer(cls, value: str) -> str:
        reviewer = value.strip()
        if not reviewer:
            raise ValueError("reviewer must name the approving doctor")
        return reviewer

    @field_validator("reviewed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def _require_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("artifact_hashes must bind the reviewed artifacts")
        return value


class GateRejectionRecord(BaseModel):
    """Audit trail of one gate rejection: why, and where the workflow resumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["2.0"] = "2.0"
    kind: GateKind
    reviewer: str
    reviewed_at: datetime
    reason: str = Field(pattern=r"\S")
    resume_state: WorkflowState
    artifact_hashes: dict[str, str]

    @field_validator("reviewer")
    @classmethod
    def _require_named_reviewer(cls, value: str) -> str:
        reviewer = value.strip()
        if not reviewer:
            raise ValueError("reviewer must name the approving doctor")
        return reviewer

    @field_validator("reviewed_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @field_validator("artifact_hashes")
    @classmethod
    def _require_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("artifact_hashes must bind the reviewed artifacts")
        return value
```

Hai class lặp lại 3 validator giống hệt nhau; đây là lặp có chủ đích (mirroring cách `domain/review.py`/`domain/revision.py` của v1 đã làm cho từng model riêng), không rút thành base class dùng chung vì hai model có tập field khác nhau (`note` vs `reason`/`resume_state`) và §14 coi approve/reject là hai đối tượng audit độc lập.

- [ ] **Step 5: GREEN**

Run: `python -m pytest tests/domain/test_gate_review.py -v`

Expected: PASS.

- [ ] **Step 6: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M2.1 trong `README.md` cùng commit.

Commit: `git commit -m "feat: add v2 gate review records"`

---

### Task 2: Medical gate — artifact hashing, approve/reject/resume core

**Files:**
- Create: `src/healthvideo/workflows/gate_review.py`
- Create: `tests/workflows/test_gate_review.py`
- Modify: `tests/helpers.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `MEDICAL_APPROVAL_ARTIFACT = "reviews/medical-approval.yaml"`, `VIDEO_APPROVAL_ARTIFACT = "reviews/video-approval.yaml"` (đúng tên artifact mà `state_graph.MAIN_RULES` đã yêu cầu từ M1).
- `medical_reviewed_paths(revision_root: Path) -> dict[str, Path]`: `evidence/ledger.yaml`, `script/script.yaml`, `storyboard/storyboard.yaml`, `assets/asset-manifest.yaml`, cộng `asset:<path>` cho mọi asset `semantic=true` trong manifest.
- `hash_reviewed_artifacts(paths: dict[str, Path]) -> dict[str, str]`: YAML → `canonical_json_hash`, JSON → `canonical_json_hash`, còn lại → `sha256_file`; bỏ qua path không tồn tại (dùng cho reject, nơi artifact có thể thiếu).
- `approve_gate(project_dir: Path, kind: GateKind, *, reviewer: str, note: str = "", now: datetime) -> GateApprovalRecord`.
- `reject_gate(project_dir: Path, kind: GateKind, *, reviewer: str, reason: str, resume_state: WorkflowState, now: datetime) -> GateRejectionRecord`.
- `resume_gate(project_dir: Path, kind: GateKind, *, target: WorkflowState, reason_code: str | None = None, now: datetime) -> WorkflowState`.
- Task 2 cài đủ hạ tầng chung và wiring cho `GateKind.MEDICAL`; Task 3 thêm `video_reviewed_paths` và bật `GateKind.VIDEO` qua cùng ba hàm trên (không đổi chữ ký).

- [ ] **Step 1: Viết fixture builder v2 trong `tests/helpers.py`**

Thêm vào `tests/helpers.py` (không đổi hàm v1 đã có):

```python
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2


def create_v2_project_fixture(root: Path, *, state: WorkflowState = WorkflowState.DRAFT_READY) -> Path:
    """Build a synthetic schema-2.0 project at `revisions/001`, ready for gate tests."""
    project_dir = root / "muoi-va-huyet-ap-v2"
    revision_root = project_dir / "revisions" / "001"
    for name in ("topic", "author", "evidence", "script", "storyboard", "assets"):
        (revision_root / name).mkdir(parents=True, exist_ok=True)

    asset_bytes = b"<svg xmlns='http://www.w3.org/2000/svg'><text>synthetic</text></svg>"
    (revision_root / "assets" / "evidence-r01.svg").write_bytes(asset_bytes)
    asset_sha256 = sha256_file(revision_root / "assets" / "evidence-r01.svg")

    write_yaml_atomic(
        revision_root / "topic" / "card.yaml",
        {
            "schema_version": "2.0",
            "synthetic_test_record": True,
            "slug": "muoi-va-huyet-ap",
            "title": "Ăn mặn và tăng huyết áp",
            "origin": "test_fixture",
        },
    )
    write_yaml_atomic(
        revision_root / "author" / "brief.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "personal_position": "Giảm muối là một bước thực tế.",
            "reasoning": "Huyết áp thường đáp ứng với lượng muối.",
            "emotion": "bình tĩnh",
            "audience_concern": "Người trưởng thành quan tâm huyết áp.",
            "phrases_to_keep": [],
        },
    )
    write_yaml_atomic(
        revision_root / "evidence" / "ledger.yaml",
        {
            "schema_version": "1.0",
            "records": [
                {
                    "id": "R01",
                    "title": "Bản ghi tổng hợp cho test: giảm muối và huyết áp",
                    "authors": ["Nguyen A", "Tran B"],
                    "year": 2020,
                    "study_design": "tổng quan hệ thống",
                    "doi": "10.0000/synthetic-salt-bp",
                    "synthetic_test_record": True,
                }
            ],
            "claims": [
                {
                    "id": "C01",
                    "text_public": "Giảm muối giúp hạ huyết áp ở nhiều người.",
                    "text_technical": "Giảm natri ăn vào liên quan tới hạ huyết áp.",
                    "type": "evidence",
                    "sources": ["R01"],
                    "synthetic_test_record": True,
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "script" / "script.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "language": "vi",
            "lines": [
                {
                    "id": "L01",
                    "text": "Ăn mặn có thể làm huyết áp tăng.",
                    "claim_id": "C01",
                    "source_marker": "[1]",
                    "delivery": {"intent": "explain"},
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "storyboard" / "storyboard.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "scenes": [
                {
                    "id": "S01",
                    "start_frame": 0,
                    "duration_frames": 225,
                    "narration": "Ăn mặn có thể làm huyết áp tăng.",
                    "claim_id": "C01",
                    "source_marker": "[1]",
                    "visual": "evidence_highlight",
                    "evidence_highlight": {
                        "image": "assets/evidence-r01.svg",
                        "quote": "Synthetic evidence fixture for tests only.",
                        "x": 0.1,
                        "y": 0.2,
                        "width": 0.8,
                        "height": 0.2,
                    },
                }
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "assets" / "asset-manifest.yaml",
        {
            "schema_version": "2.0",
            "assets": [
                {
                    "path": "assets/evidence-r01.svg",
                    "kind": "evidence_highlight",
                    "semantic": True,
                    "classification_reason": "Evidence highlight changes the medical meaning.",
                    "sha256": asset_sha256,
                    "source": "synthetic_test_fixture",
                    "license": "synthetic_test_only",
                    "creator": "repository_fixture",
                    "revision": "001",
                }
            ],
        },
    )
    write_yaml_atomic(
        project_dir / "project.yaml",
        {
            "schema_version": "2.0",
            "slug": "muoi-va-huyet-ap",
            "language": "vi",
            "state": WorkflowState.DRAFT_READY.value,
            "active_revision": "001",
            "artifact_hashes": {},
        },
    )
    if state is not WorkflowState.DRAFT_READY:
        _advance_v2_state(project_dir, state)
    return project_dir


def _advance_v2_state(project_dir: Path, state: WorkflowState) -> None:
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {"script/script.yaml", "storyboard/storyboard.yaml", "assets/asset-manifest.yaml"}
        ),
    )
    changed = transition_v2(manifest, state, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
```

`sha256_file`, `read_yaml`, `write_yaml_atomic` đã import sẵn ở đầu `tests/helpers.py` cho v1 — dùng lại nguyên import đó, chỉ thêm hai import mới (`ProjectManifestV2`/`WorkflowState`/`TransitionContext`/`transition_v2`) vào khối import hiện có.

- [ ] **Step 2: Viết RED tests cho hashing và approve/reject/resume**

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.workflows.gate_review import (
    MEDICAL_APPROVAL_ARTIFACT,
    approve_gate,
    medical_reviewed_paths,
    reject_gate,
    resume_gate,
)
from tests.helpers import create_v2_project_fixture

REVIEWER = "BS Nguyễn Văn An"
NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)


def _advance_to_awaiting_medical_review(project_dir: Path) -> None:
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {"script/script.yaml", "storyboard/storyboard.yaml", "assets/asset-manifest.yaml"}
        ),
    )
    changed = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))


def test_medical_reviewed_paths_includes_ledger_script_storyboard_manifest_and_semantic_assets(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision_root = project_dir / "revisions" / "001"
    paths = medical_reviewed_paths(revision_root)
    assert set(paths) == {
        "evidence/ledger.yaml",
        "script/script.yaml",
        "storyboard/storyboard.yaml",
        "assets/asset-manifest.yaml",
        "asset:assets/evidence-r01.svg",
    }


def test_approve_medical_rejects_missing_semantic_asset_bytes(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    (project_dir / "revisions" / "001" / "assets" / "evidence-r01.svg").write_bytes(b"changed")

    with pytest.raises(Exception, match="sha256"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_approve_medical_writes_record_once_and_advances_state(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)

    approval_path = project_dir / "revisions" / "001" / MEDICAL_APPROVAL_ARTIFACT
    assert approval_path.is_file()
    assert read_yaml(approval_path)["reviewer"] == REVIEWER
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.MEDICALLY_APPROVED
    assert record.artifact_hashes

    with pytest.raises(FileExistsError):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=NOW)


def test_reject_medical_enters_side_state_and_can_repeat_before_approval(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    first = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Thiếu nguồn cho claim C01.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.NEEDS_MEDICAL_REVISION
    assert manifest.side_state.resume_state is WorkflowState.DRAFT_READY
    assert first.reason == "Thiếu nguồn cho claim C01."

    resume_gate(project_dir, GateKind.MEDICAL, target=WorkflowState.DRAFT_READY, now=NOW)
    _advance_to_awaiting_medical_review(project_dir)

    second = reject_gate(
        project_dir,
        GateKind.MEDICAL,
        reviewer=REVIEWER,
        reason="Vẫn còn một câu chưa khớp claim.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )
    assert first != second


def test_reject_gate_requires_non_blank_reason(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    with pytest.raises(Exception, match="reason"):
        reject_gate(
            project_dir,
            GateKind.MEDICAL,
            reviewer=REVIEWER,
            reason="   ",
            resume_state=WorkflowState.DRAFT_READY,
            now=NOW,
        )
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/workflows/test_gate_review.py -v`

Expected: FAIL vì `healthvideo.workflows.gate_review` chưa tồn tại.

- [ ] **Step 4: Cài `workflows/gate_review.py`**

```python
"""v2 medical/video gate: hash the artifacts a gate covers, approve, reject, resume.

Mirrors `workflows/review.py` (v1) but reads the v2 layout (`revisions/<id>/...`),
enforces the semantic asset manifest before a medical approval, and adds a
reject/resume path v1 never had. v1 stays untouched; this module never imports it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from healthvideo.domain.asset_manifest import load_asset_manifest, validate_asset_manifest
from healthvideo.domain.gate_review import GateApprovalRecord, GateKind, GateRejectionRecord
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.domain.state_graph import TransitionContext, transition_v2
from healthvideo.storage.files import canonical_json_hash, read_yaml, sha256_file, write_yaml_atomic
from healthvideo.storage.immutable import write_yaml_once

MEDICAL_APPROVAL_ARTIFACT = "reviews/medical-approval.yaml"
VIDEO_APPROVAL_ARTIFACT = "reviews/video-approval.yaml"

_GATE_OPEN_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.AWAITING_MEDICAL_REVIEW,
    GateKind.VIDEO: WorkflowState.AWAITING_VIDEO_REVIEW,
}
_GATE_APPROVED_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.MEDICALLY_APPROVED,
    GateKind.VIDEO: WorkflowState.VIDEO_APPROVED,
}
_GATE_APPROVAL_ARTIFACT: dict[GateKind, str] = {
    GateKind.MEDICAL: MEDICAL_APPROVAL_ARTIFACT,
    GateKind.VIDEO: VIDEO_APPROVAL_ARTIFACT,
}
_GATE_SIDE_STATE: dict[GateKind, WorkflowState] = {
    GateKind.MEDICAL: WorkflowState.NEEDS_MEDICAL_REVISION,
    GateKind.VIDEO: WorkflowState.NEEDS_PRODUCTION_REVISION,
}


def medical_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the medical gate covers; missing entries are dropped by the caller."""
    paths = {
        "evidence/ledger.yaml": revision_root / "evidence" / "ledger.yaml",
        "script/script.yaml": revision_root / "script" / "script.yaml",
        "storyboard/storyboard.yaml": revision_root / "storyboard" / "storyboard.yaml",
        "assets/asset-manifest.yaml": revision_root / "assets" / "asset-manifest.yaml",
    }
    manifest_path = paths["assets/asset-manifest.yaml"]
    if manifest_path.is_file():
        manifest = load_asset_manifest(manifest_path)
        for asset in manifest.assets:
            if asset.semantic:
                paths[f"asset:{asset.path}"] = revision_root / asset.path
    return paths


def video_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the video gate covers: the render manifest and the MP4."""
    return {
        "renders/render-manifest.json": revision_root / "renders" / "render-manifest.json",
        "renders/video.mp4": revision_root / "renders" / "video.mp4",
    }


_REVIEWED_PATHS = {
    GateKind.MEDICAL: medical_reviewed_paths,
    GateKind.VIDEO: video_reviewed_paths,
}


def hash_reviewed_artifacts(paths: dict[str, Path]) -> dict[str, str]:
    """Hash whichever of `paths` exist; missing artifacts are silently omitted.

    Approve relies on the caller checking nothing is missing first; reject
    tolerates gaps, since "an asset is missing" can itself be the rejection
    reason and must not crash the audit trail.
    """
    return {name: _hash_artifact(path) for name, path in paths.items() if path.is_file()}


def _hash_artifact(path: Path) -> str:
    if path.suffix == ".yaml":
        return canonical_json_hash(read_yaml(path))
    if path.suffix == ".json":
        return canonical_json_hash(json.loads(path.read_text(encoding="utf-8")))
    return sha256_file(path)


def _load_project(project_dir: Path) -> ProjectManifestV2:
    manifest_path = project_dir / "project.yaml"
    manifest_data = read_yaml(manifest_path)
    if manifest_data.get("schema_version") != "2.0":
        raise ValueError(
            "gate review requires project schema 2.0; run 'healthvideo project migrate' first"
        )
    return ProjectManifestV2.model_validate(manifest_data)


def _revision_root(project_dir: Path, project: ProjectManifestV2) -> Path:
    return project_dir / "revisions" / project.active_revision


def approve_gate(
    project_dir: Path, kind: GateKind, *, reviewer: str, note: str = "", now: datetime
) -> GateApprovalRecord:
    """Approve `kind`'s gate: validate, hash, write the record once, advance state."""
    project = _load_project(project_dir)
    expected = _GATE_OPEN_STATE[kind]
    if project.state is not expected:
        raise ValueError(f"{kind.value} gate requires project state {expected.value}")

    revision_root = _revision_root(project_dir, project)
    if kind is GateKind.MEDICAL:
        manifest = load_asset_manifest(revision_root / "assets" / "asset-manifest.yaml")
        validate_asset_manifest(revision_root, manifest)

    paths = _REVIEWED_PATHS[kind](revision_root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{kind.value} gate needs artifacts: {', '.join(sorted(missing))}")
    artifact_hashes = hash_reviewed_artifacts(paths)

    record = GateApprovalRecord(
        kind=kind, reviewer=reviewer, reviewed_at=now, artifact_hashes=artifact_hashes, note=note
    )
    write_yaml_once(revision_root / _GATE_APPROVAL_ARTIFACT[kind], record.model_dump(mode="json"))

    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(artifact_hashes),
        validated_artifacts=frozenset({_GATE_APPROVAL_ARTIFACT[kind]}),
    )
    changed = transition_v2(project, _GATE_APPROVED_STATE[kind], context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return record


def reject_gate(
    project_dir: Path,
    kind: GateKind,
    *,
    reviewer: str,
    reason: str,
    resume_state: WorkflowState,
    now: datetime,
) -> GateRejectionRecord:
    """Reject `kind`'s gate: record why, enter the matching side state."""
    project = _load_project(project_dir)
    expected = _GATE_OPEN_STATE[kind]
    if project.state is not expected:
        raise ValueError(f"{kind.value} gate requires project state {expected.value}")

    revision_root = _revision_root(project_dir, project)
    artifact_hashes = hash_reviewed_artifacts(_REVIEWED_PATHS[kind](revision_root))
    bound_hashes = artifact_hashes or {"none": "0" * 64}

    record = GateRejectionRecord(
        kind=kind,
        reviewer=reviewer,
        reviewed_at=now,
        reason=reason,
        resume_state=resume_state,
        artifact_hashes=bound_hashes,
    )
    timestamp = now.astimezone().strftime("%Y%m%dT%H%M%S%f")
    write_yaml_once(
        revision_root / "reviews" / kind.value / f"{timestamp}-rejected.yaml",
        record.model_dump(mode="json"),
    )

    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash(bound_hashes),
        validated_artifacts=frozenset(),
    )
    changed = transition_v2(
        project,
        _GATE_SIDE_STATE[kind],
        context,
        reason_code=reason,
        resume_state=resume_state,
        entered_at=now,
    )
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return record


def resume_gate(
    project_dir: Path,
    kind: GateKind,
    *,
    target: WorkflowState,
    reason_code: str | None = None,
    now: datetime,
) -> WorkflowState:
    """Exit the gate's side state back to `target` after the reviewer's note is addressed."""
    project = _load_project(project_dir)
    context = TransitionContext(
        active_revision=project.active_revision,
        current_input_hash=canonical_json_hash({"resume": target.value, "at": now.isoformat()}),
        validated_artifacts=frozenset(),
        reason_code=reason_code,
    )
    changed = transition_v2(project, target, context)
    write_yaml_atomic(project_dir / "project.yaml", changed.model_dump(mode="json"))
    return changed.state
```

Ghi chú thiết kế quan trọng cần giữ đúng khi review code (không phải placeholder, mà là quyết định đã chốt):
- `approve_gate` ghi `reviews/<kind>-approval.yaml` bằng `write_yaml_once`: revision đã approve rồi mà gọi lại approve lần hai sẽ nhận `FileExistsError` — đây **là** hành vi đúng ("không tự ký lại"), không phải bug cần sửa.
- `reject_gate` ghi vào `reviews/<kind>/<timestamp>-rejected.yaml` (thư mục con theo kind, không trùng với file approval phẳng `reviews/<kind>-approval.yaml`), cho phép reject nhiều lần trong cùng revision trước khi approve.
- `resume_gate` truyền `reason_code` qua `context.reason_code`, **không** qua kwarg `reason_code=` của `transition_v2` — kwarg đó chỉ hợp lệ khi *vào* side state, gọi nó khi *thoát* side state sẽ luôn ném `TransitionError` (xem `_reject_side_state_fields` trong `state_graph.py`).

- [ ] **Step 5: GREEN, dual-golden checkpoint và full regression**

Thêm vào `tests/e2e/test_golden_workflow_versions.py` (dùng lại `_snapshot_tree`/tương đương đã có trong file, theo đúng mẫu các checkpoint revision/stage hiện tại):

```python
def test_dual_golden_medical_gate_approves_on_a_copy_without_touching_the_tracked_fixture(
    tmp_path: Path,
) -> None:
    v2_source = GOLDEN_PROJECTS[1]
    before = _snapshot_tree(v2_source)
    copy_dir = tmp_path / "copy"
    shutil.copytree(v2_source, copy_dir)
    _advance_v2_state(copy_dir, WorkflowState.AWAITING_MEDICAL_REVIEW)

    record = approve_gate(copy_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=GOLDEN_ENTERED_AT)

    assert record.artifact_hashes
    assert _snapshot_tree(v2_source) == before
```

Run: `python -m pytest tests/workflows/test_gate_review.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 6: README và commit**

Cập nhật M2.2 trong `README.md`, ghi rõ giới hạn write-once approval mỗi revision.

Commit: `git commit -m "feat: add v2 medical gate approve, reject and resume"`

---

### Task 3: Video gate wiring

**Files:**
- Modify: `tests/workflows/test_gate_review.py` (`workflows/gate_review.py` đã version-agnostic từ Task 2 — không cần sửa)
- Modify: `tests/helpers.py` (thêm hàm dựng render fixture v2 tổng hợp)
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:** không thêm hàm mới trong `src/` — `approve_gate`/`reject_gate`/`resume_gate` đã nhận `GateKind` từ Task 2; task này chỉ chứng minh chúng đúng cho video bằng fixture render tổng hợp (chưa có pipeline render v2 thật — đó là M6).

- [ ] **Step 1: Thêm helper fixture render v2 tổng hợp vào `tests/helpers.py`**

```python
from healthvideo.workflows.gate_review import GateKind, approve_gate


def advance_v2_project_to_video_review(project_dir: Path, *, now: datetime) -> None:
    """Push a draft_ready v2 fixture through to awaiting_video_review with synthetic renders."""
    revision_root = project_dir / "revisions" / "001"
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(
            {"script/script.yaml", "storyboard/storyboard.yaml", "assets/asset-manifest.yaml"}
        ),
    )
    manifest = transition_v2(manifest, WorkflowState.AWAITING_MEDICAL_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=now)

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    (revision_root / "renders").mkdir(parents=True, exist_ok=True)
    _write_json(revision_root / "renders" / "render-manifest.json", {"provider": "silent", "frames": 225})
    (revision_root / "renders" / "video.mp4").write_bytes(b"synthetic-mp4")
    _write_json(revision_root / "reviews" / "video-qa.json", {"codec": "h264", "issues": []})
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset({"renders/render-manifest.json", "reviews/video-qa.json"}),
    )
    manifest = transition_v2(manifest, WorkflowState.PRODUCTION_IN_PROGRESS, context)
    manifest = transition_v2(manifest, WorkflowState.AWAITING_VIDEO_REVIEW, context)
    write_yaml_atomic(project_dir / "project.yaml", manifest.model_dump(mode="json"))
```

`_write_json` đã có sẵn trong `tests/helpers.py` cho v1 — dùng lại nguyên hàm, không viết trùng. `renders/reviews/video-qa.json` nằm dưới `revision_root/reviews/`, tách khỏi `renders/`; sửa lại đường dẫn `_write_json` thứ hai thành `revision_root / "reviews" / "video-qa.json"` (đã ghi đúng ở trên) và tạo thư mục `reviews/` trước khi ghi nếu `_write_json` không tự `mkdir` (kiểm tra hàm hiện có; nếu chưa tự tạo thư mục cha, thêm `(revision_root / "reviews").mkdir(parents=True, exist_ok=True)` trước lời gọi).

- [ ] **Step 2: Viết RED tests cho video gate**

```python
def test_approve_video_hashes_render_manifest_and_mp4(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=NOW)

    assert set(record.artifact_hashes) == {"renders/render-manifest.json", "renders/video.mp4"}
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.VIDEO_APPROVED


def test_reject_video_with_semantic_issue_must_resume_to_draft_ready_with_that_reason_class(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Phát hiện câu thoại sai claim khi xem lại video.",
        resume_state=WorkflowState.DRAFT_READY,
        now=NOW,
    )

    with pytest.raises(Exception, match="reason class"):
        resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.DRAFT_READY, now=NOW)

    resume_gate(
        project_dir,
        GateKind.VIDEO,
        target=WorkflowState.DRAFT_READY,
        reason_code="semantic_issue",
        now=NOW,
    )
    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.DRAFT_READY


def test_reject_video_without_semantic_issue_resumes_to_production_in_progress(
    tmp_path: Path,
) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=NOW)

    reject_gate(
        project_dir,
        GateKind.VIDEO,
        reviewer=REVIEWER,
        reason="Âm lượng chưa chuẩn hoá.",
        resume_state=WorkflowState.PRODUCTION_IN_PROGRESS,
        now=NOW,
    )
    resume_gate(project_dir, GateKind.VIDEO, target=WorkflowState.PRODUCTION_IN_PROGRESS, now=NOW)

    manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
    assert manifest.state is WorkflowState.PRODUCTION_IN_PROGRESS
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/workflows/test_gate_review.py -v -k video`

Expected: FAIL trên các case mới cho đến khi fixture helper khớp đúng layout mà `video_reviewed_paths`/`transition_v2` mong đợi.

- [ ] **Step 4: Sửa tối thiểu nếu RED lộ sai lệch**

`resume_gate`/`reject_gate`/`approve_gate` không cần đổi (đã version-agnostic từ Task 2). Nếu RED lộ sai lệch, đó thường là fixture helper (Step 1) chưa khớp tên path `video_reviewed_paths` mong đợi — sửa fixture, không sửa `gate_review.py`.

- [ ] **Step 5: GREEN, dual-golden và full regression**

Run: `python -m pytest tests/workflows/test_gate_review.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 6: README và commit**

Cập nhật M2.3 trong `README.md`.

Commit: `git commit -m "feat: wire the v2 video gate onto the same approve/reject/resume core"`

---

### Task 4: HTML review packets

**Files:**
- Create: `src/healthvideo/workflows/review_html.py`
- Create: `tests/workflows/test_review_html.py`
- Modify: `README.md`

**Interfaces:**
- `render_medical_packet(revision_root: Path) -> str`
- `render_video_packet(revision_root: Path) -> str`

Cả hai chỉ đọc (không ghi file); CLI (Task 5) chịu trách nhiệm ghi ra đĩa bằng `write_text_atomic` đã có sẵn trong `storage/files.py`.

- [ ] **Step 1: Viết RED tests**

```python
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.workflows.review_html import render_medical_packet, render_video_packet
from tests.helpers import advance_v2_project_to_video_review, create_v2_project_fixture


def test_medical_packet_shows_public_and_technical_claim_text_escaped(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    revision_root = project_dir / "revisions" / "001"

    html = render_medical_packet(revision_root)

    assert "Giảm muối giúp hạ huyết áp ở nhiều người." in html
    assert "Giảm natri ăn vào liên quan tới hạ huyết áp." in html
    assert "Bản ghi tổng hợp cho test: giảm muối và huyết áp" in html
    assert "<script>" not in html


def test_medical_packet_notes_fields_the_model_does_not_carry_yet(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    html = render_medical_packet(project_dir / "revisions" / "001")
    assert "chưa có trong hệ thống" in html


def test_video_packet_references_the_mp4_by_relative_path_not_embedded(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    advance_v2_project_to_video_review(project_dir, now=datetime(2026, 9, 11, 9, 0, tzinfo=UTC))

    html = render_video_packet(project_dir / "revisions" / "001")

    assert "renders/video.mp4" in html
    assert len(html.encode("utf-8")) < 5000
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/workflows/test_review_html.py -v`

Expected: FAIL vì `healthvideo.workflows.review_html` chưa tồn tại.

- [ ] **Step 3: Cài render packet**

```python
"""Static, read-only HTML review packets — no JS, no self-signing, no network.

Only renders fields that exist today on `EvidenceClaim`/`SourceRecord`
(`domain/evidence.py`): `text_public`, `text_technical`, `sources`/`title`.
The §14 spec also wants population/certainty/applicability/per-claim doctor
notes; those fields do not exist on the model yet, so the packet says so
explicitly rather than inventing text for them — extending the model is a
later milestone's job, once there is a real extraction pipeline feeding it.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from healthvideo.domain.evidence import EvidenceClaim, SourceRecord
from healthvideo.domain.script import Script
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml

_NOT_YET_MODELED = (
    "Chưa có trong hệ thống: population, certainty, applicability, "
    "quan điểm bác sĩ theo từng claim."
)


def render_medical_packet(revision_root: Path) -> str:
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    sources = {
        record["id"]: SourceRecord.model_validate(record) for record in ledger.get("records", [])
    }
    claims = [EvidenceClaim.model_validate(claim) for claim in ledger.get("claims", [])]
    script = Script.model_validate(read_yaml(revision_root / "script" / "script.yaml"))
    storyboard = Storyboard.model_validate(read_yaml(revision_root / "storyboard" / "storyboard.yaml"))

    lines_by_claim: dict[str, list[str]] = {}
    for line in script.lines:
        if line.claim_id:
            lines_by_claim.setdefault(line.claim_id, []).append(line.text)
    markers_by_claim: dict[str, list[str]] = {}
    for scene in storyboard.scenes:
        if scene.claim_id and scene.source_marker:
            markers_by_claim.setdefault(scene.claim_id, []).append(scene.source_marker)

    rows = []
    for claim in claims:
        source_titles = ", ".join(
            escape(sources[source_id].title) for source_id in claim.sources if source_id in sources
        )
        script_lines = "; ".join(escape(text) for text in lines_by_claim.get(claim.id, []))
        markers = ", ".join(escape(marker) for marker in markers_by_claim.get(claim.id, []))
        rows.append(
            "<tr>"
            f"<td>{escape(claim.id)}</td>"
            f"<td>{escape(claim.text_public)}</td>"
            f"<td>{escape(claim.text_technical)}</td>"
            f"<td>{source_titles}</td>"
            f"<td>{script_lines}</td>"
            f"<td>{markers}</td>"
            "</tr>"
        )

    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt y khoa</title></head><body>"
        f"<h1>{escape(storyboard.title)}</h1>"
        '<table border="1"><thead><tr>'
        "<th>Claim</th><th>Câu công chúng</th><th>Mệnh đề kỹ thuật</th>"
        "<th>Nguồn</th><th>Câu thoại</th><th>Marker</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
        f"<p>{escape(_NOT_YET_MODELED)}</p>"
        "</body></html>"
    )


def render_video_packet(revision_root: Path) -> str:
    manifest_path = revision_root / "renders" / "render-manifest.json"
    manifest = read_yaml(manifest_path) if manifest_path.is_file() else {}
    qa_path = revision_root / "reviews" / "video-qa.json"
    qa = read_yaml(qa_path) if qa_path.is_file() else {}

    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        "<title>Gói duyệt video</title></head><body>"
        '<video controls src="../renders/video.mp4"></video>'
        f"<pre>{escape(str(manifest))}</pre>"
        f"<pre>{escape(str(qa))}</pre>"
        "</body></html>"
    )
```

Assertion `"Bản ghi tổng hợp cho test: giảm muối và huyết áp" in html` trong Step 1 khớp `sources[source_id].title` mà `render_medical_packet` đưa vào cột "Nguồn". `read_yaml` đọc được cả `.json` vì JSON là tập con hợp lệ của YAML; dùng lại nguyên hàm thay vì viết `read_json` riêng.

- [ ] **Step 4: GREEN**

Run: `python -m pytest tests/workflows/test_review_html.py -v`

Expected: PASS, không còn assertion giữ chỗ nào trong file test.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M2.4 trong `README.md`, ghi rõ giới hạn field chưa model hoá.

Commit: `git commit -m "feat: render static medical and video review packets"`

---

### Task 5: CLI wiring, .gitignore và acceptance M2

**Files:**
- Modify: `src/healthvideo/cli.py`
- Modify: `.gitignore`
- Modify: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- `healthvideo review approve <project> --gate medical|video --reviewer "..." [--note "..."] [--yes]`
- `healthvideo review reject <project> --gate medical|video --reviewer "..." --reason "..." --resume-to <state> [--yes]`
- `healthvideo review open <project> --gate medical|video` — in đường dẫn file HTML vừa ghi, không tự mở trình duyệt.
- `healthvideo review resume <project> --gate medical|video --to <state> [--reason-class semantic_issue]`
- Lệnh `review medical` / `review video` (v1) không đổi.

- [ ] **Step 1: Viết RED CLI tests**

```python
from datetime import UTC, datetime

from healthvideo.domain.project_v2 import WorkflowState
from tests.helpers import create_v2_project_fixture


def test_review_approve_medical_requires_gate_flag_and_confirmation(tmp_path):
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    result = runner.invoke(
        app,
        [
            "review", "approve", str(project_dir),
            "--gate", "medical", "--reviewer", "BS Nguyễn Văn An", "--yes",
        ],
    )

    assert result.exit_code == 0
    assert "Đã duyệt" in result.stdout


def test_review_reject_then_resume_round_trip(tmp_path):
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)

    reject_result = runner.invoke(
        app,
        [
            "review", "reject", str(project_dir),
            "--gate", "medical", "--reviewer", "BS Nguyễn Văn An",
            "--reason", "Thiếu nguồn.", "--resume-to", "draft_ready", "--yes",
        ],
    )
    assert reject_result.exit_code == 0

    resume_result = runner.invoke(
        app, ["review", "resume", str(project_dir), "--gate", "medical", "--to", "draft_ready"]
    )
    assert resume_result.exit_code == 0


def test_review_open_writes_html_and_prints_path(tmp_path):
    project_dir = create_v2_project_fixture(tmp_path)

    result = runner.invoke(app, ["review", "open", str(project_dir), "--gate", "medical"])

    assert result.exit_code == 0
    packet_path = project_dir / "revisions" / "001" / "reviews" / "medical-packet.html"
    assert packet_path.is_file()
    assert str(packet_path) in result.stdout


def test_review_v1_commands_are_unaffected(tmp_path):
    from tests.helpers import create_project_fixture

    project_dir = create_project_fixture(tmp_path, state="awaiting_medical_review")

    result = runner.invoke(
        app,
        ["review", "medical", str(project_dir), "--reviewer", "BS Nguyễn Văn An", "--yes"],
    )
    assert result.exit_code == 0
```

`runner`/`app` dùng đúng import đã có ở đầu `tests/test_cli.py` (không tạo `CliRunner()` mới trong mỗi test).

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/test_cli.py -k "review_approve or review_reject or review_open or review_v1" -v`

Expected: FAIL trên các case v2 mới; case v1 PASS ngay (chứng minh chưa đổi gì ở v1).

- [ ] **Step 3: Cài Typer adapter**

Thêm vào `src/healthvideo/cli.py`, cạnh các import và hằng số đã có (không sửa `review_medical`/`review_video`):

```python
from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import ProjectManifestV2, WorkflowState
from healthvideo.storage.files import write_text_atomic
from healthvideo.workflows.gate_review import approve_gate, reject_gate, resume_gate
from healthvideo.workflows.review_html import render_medical_packet, render_video_packet

REJECT_CONFIRMATION = "REJECT"
Gate = Annotated[GateKind, typer.Option("--gate", help="medical hoặc video")]
Reason = Annotated[str, typer.Option("--reason", help="Lý do từ chối")]
ResumeTo = Annotated[str, typer.Option("--resume-to", help="Trạng thái nối lại sau khi sửa")]
ResumeTarget = Annotated[str, typer.Option("--to", help="Trạng thái muốn quay lại")]
ReasonClass = Annotated[
    str | None,
    typer.Option("--reason-class", help='Bắt buộc là "semantic_issue" khi resume video về draft_ready'),
]

_RENDER_PACKET = {GateKind.MEDICAL: render_medical_packet, GateKind.VIDEO: render_video_packet}
_PACKET_NAME = {GateKind.MEDICAL: "medical-packet.html", GateKind.VIDEO: "video-packet.html"}


@review_app.command("approve")
def review_approve(
    project_dir: ProjectDir, gate: Gate, reviewer: Reviewer, note: Note = "", yes: SkipConfirmation = False
) -> None:
    """Duyệt cổng y khoa hoặc video cho project schema 2.0."""
    if not yes:
        typed = typer.prompt(f"Gõ {CONFIRMATION} để duyệt {gate.value}")
        if typed.strip() != CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        record = approve_gate(
            project_dir, gate, reviewer=reviewer, note=note, now=datetime.now().astimezone()
        )
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã duyệt {gate.value}: {record.reviewed_at.isoformat()}")


@review_app.command("reject")
def review_reject(
    project_dir: ProjectDir,
    gate: Gate,
    reviewer: Reviewer,
    reason: Reason,
    resume_to: ResumeTo,
    yes: SkipConfirmation = False,
) -> None:
    """Từ chối cổng y khoa hoặc video, ghi lý do và điểm nối lại."""
    if not yes:
        typed = typer.prompt(f"Gõ {REJECT_CONFIRMATION} để từ chối {gate.value}")
        if typed.strip() != REJECT_CONFIRMATION:
            typer.echo(f"Đã hủy: cần gõ {REJECT_CONFIRMATION} để xác nhận.")
            raise typer.Exit(code=1)
    try:
        resume_state = WorkflowState(resume_to)
        reject_gate(
            project_dir,
            gate,
            reviewer=reviewer,
            reason=reason,
            resume_state=resume_state,
            now=datetime.now().astimezone(),
        )
    except (FileNotFoundError, FileExistsError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Đã từ chối {gate.value}, nối lại tại {resume_state.value}")


@review_app.command("open")
def review_open(project_dir: ProjectDir, gate: Gate) -> None:
    """Render gói HTML duyệt hiện tại và in đường dẫn; không tự mở trình duyệt."""
    try:
        manifest = ProjectManifestV2.model_validate(read_yaml(project_dir / "project.yaml"))
        revision_root = project_dir / "revisions" / manifest.active_revision
        html = _RENDER_PACKET[gate](revision_root)
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    packet_path = revision_root / "reviews" / _PACKET_NAME[gate]
    write_text_atomic(packet_path, html)
    typer.echo(str(packet_path))


@review_app.command("resume")
def review_resume(
    project_dir: ProjectDir, gate: Gate, to: ResumeTarget, reason_class: ReasonClass = None
) -> None:
    """Thoát needs_medical_revision/needs_production_revision về trạng thái chính."""
    try:
        target = WorkflowState(to)
        new_state = resume_gate(
            project_dir, gate, target=target, reason_code=reason_class, now=datetime.now().astimezone()
        )
    except (FileNotFoundError, TypeError, ValueError) as error:
        typer.echo(str(error))
        raise typer.Exit(code=1) from error
    typer.echo(f"Trạng thái mới: {new_state.value}")
```

Thêm dòng vào `.gitignore` (cạnh các dòng `projects/**/...` đã có):

```
projects/**/reviews/*.html
```

- [ ] **Step 4: GREEN và acceptance M2 offline**

Run: `python -m pytest tests/test_cli.py -k "review_approve or review_reject or review_open or review_resume or review_v1" -v`

Run: `python -m pytest tests/workflows/test_gate_review.py tests/workflows/test_review_html.py tests/e2e/test_golden_workflow_versions.py tests/e2e/test_golden_project.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: tất cả PASS offline; golden v1 full suite không đổi hành vi; golden v2 chứng minh approve/reject/resume/HTML packet cho cả hai gate trên project v2.

- [ ] **Step 5: Cập nhật README và commit**

Đổi milestone M2 thành `complete` chỉ khi Step 4 PASS toàn bộ. Ghi số test thực tế, ngày, các commit M2.1–M2.5, giới hạn field HTML chưa model hoá, và việc `review medical`/`review video` v1 không đổi.

Commit: `git commit -m "feat: expose v2 review gate approve, reject, open and resume"`

---

## M2 exit criteria

- `review medical`/`review video` (v1) và toàn bộ MVP suite/golden v1 PASS không đổi hành vi.
- `review approve/reject/open/resume --gate medical|video` (v2) hoạt động trên project schema `2.0`, từ chối schema `1.0` với thông báo yêu cầu `project migrate`.
- Medical approve bắt buộc `validate_asset_manifest` qua trước khi ký; asset semantic thiếu hoặc sai byte chặn approve.
- Approval ghi một lần mỗi revision (`write_yaml_once`); reject ghi audit trail lặp lại được, có `reason` và `resume_state`; resume dùng đúng `required_reason_class="semantic_issue"` khi video quay lại `draft_ready`.
- HTML packet chỉ hiển thị field thật có trong domain model, không tự sinh certainty/applicability/population/doctor note; không tự ký, không tự mở trình duyệt.
- `projects/**/reviews/*.html` không vào Git; `reviews/*.yaml` tiếp tục track.
- Test M2 chạy PowerShell/offline, không cần mạng, AI hay browser thật.

## Deferred milestones

- **M3 — Discovery & evidence:** Intake trend cùng PubMed/Europe PMC/Crossref; đồng thời là nơi hợp lý để mở rộng `EvidenceClaim`/`SourceRecord` với population/certainty/applicability nếu có luồng trích xuất thật.
- **M4 — Agent routing:** Chuẩn hoá packet, risk routing và contract phối hợp Codex–Claude–Gemini với token ledger.
- **M5 — Vietnamese voice:** Benchmark/adapter VieNeu-TTS, pronunciation/ASR back-check và ElevenLabs fallback.
- **M6 — Visual production:** Pipeline render v2 thật (`renders/render-manifest.json`/`video.mp4` hiện là fixture tổng hợp trong test, chưa có lệnh production sinh ra chúng), chart/SVG, paper highlight, Veo adapter.
- **M7 — Hardening:** E2E toàn hệ thống, đồng thời đa tiến trình/đa máy, backup, security và tài liệu vận hành.
- **Ngoài phạm vi cố ý:** lệnh `workflow resume` tổng quát cho cả 5 side state (bao gồm `awaiting_browser_login`, `awaiting_second_model_review`, `blocked`) — M2 chỉ cài `review resume` hẹp cho hai side state của riêng gate y khoa/video; side state còn lại thuộc milestone sở hữu khái niệm đó (M3 cho browser login, M4 cho second-model review).

## Plan review gate

Không bắt đầu Task 1 trước khi bác sĩ duyệt plan này. Việc duyệt plan không đồng nghĩa duyệt y khoa, duyệt video, push hay merge; từng hành động đó vẫn theo gate riêng.
