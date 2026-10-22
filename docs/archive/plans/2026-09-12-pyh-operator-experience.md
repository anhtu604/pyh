# `/pyh` Operator Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép bác sĩ vận hành một video từ khám phá/chọn chủ đề đến gói đăng bằng `/pyh`, trong khi M1–M3 tiếp tục sở hữu state, evidence, invalidation và hai cổng duyệt.

**Architecture:** `/pyh` là projection và router mỏng trên các workflow hiện có. Chỉ bổ sung hai seam còn thiếu—tạo project/brief v2 và production/package v2—cùng một hàm thuần xác định hành động kế tiếp; không tạo workflow engine, approval implementation, renderer hay state machine thứ hai.

**Tech Stack:** Python 3.11+, Pydantic 2.13.5, Typer 0.27.2, PyYAML 6.0.3, pytest 9.1.1, Remotion/TypeScript hiện có, Markdown repo-local skills.

**Spec:** `docs/superpowers/specs/2026-09-12-pyh-operator-experience-design.md`

## Global Constraints

- Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu hoặc trải nghiệm của bác sĩ.
- Không vượt medical gate hoặc video gate; không tự động xuất bản.
- Project mới dùng schema v2; v1 và migration vẫn hoạt động nhưng không nằm trên đường chạy mặc định.
- `/pyh` không ghi trực tiếp state hoặc approval; nó gọi workflow Python hiện có.
- `STATUS.md`, nếu được sinh, là projection có thể tái tạo và không tham gia hash, transition, invalidation hoặc project resolution.
- Dùng `pathlib.Path`; không thêm runtime dependency.
- Giữ public CLI hiện có và hành vi v1.
- Không thêm state, provider abstraction, intent framework, template registry hoặc renderer mới.
- Online discovery và TTS thật không phải acceptance; golden path dùng fixture đông lạnh, `SilentTTS` và fake runner.

---

### Task 1: Tạo project v2 và xác nhận author brief

**Files:**
- Create: `src/healthvideo/workflows/create_project_v2.py`
- Create: `src/healthvideo/workflows/author.py`
- Create: `tests/workflows/test_create_project_v2.py`
- Create: `tests/workflows/test_author.py`

**Interfaces:**
- Consumes: `ProjectManifestV2`, `AuthorBrief`, `transition_v2`, `write_yaml_atomic`.
- Produces: `create_project_v2(root: Path, slug: str, title: str, *, now: datetime) -> Path`; `save_author_brief(project_dir: Path, brief: AuthorBrief, *, confirm: bool, now: datetime) -> ProjectManifestV2`.

- [ ] **Step 1: Viết RED tests cho creation transaction**

```python
def test_create_project_v2_starts_at_idea_with_revision_001(tmp_path, frozen_now):
    project = create_project_v2(tmp_path, "muoi-va-huyet-ap", "Muối và huyết áp", now=frozen_now)
    manifest = ProjectManifestV2.model_validate(read_yaml(project / "project.yaml"))
    assert manifest.state is WorkflowState.IDEA
    assert manifest.active_revision == "001"
    assert (project / "revisions/001/author/brief.yaml").is_file()

def test_create_project_v2_leaves_no_partial_destination_on_failure(tmp_path, frozen_now, monkeypatch):
    monkeypatch.setattr("healthvideo.workflows.create_project_v2.write_yaml_atomic", Mock(side_effect=OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        create_project_v2(tmp_path, "muoi", "Muối", now=frozen_now)
    assert not (tmp_path / "muoi").exists()
```

- [ ] **Step 2: Viết RED tests cho brief draft và confirmation**

```python
def test_draft_brief_does_not_advance(v2_topic_project, frozen_now):
    result = save_author_brief(v2_topic_project, AuthorBrief(title="Muối"), confirm=False, now=frozen_now)
    assert result.state is WorkflowState.TOPIC_SELECTED

def test_confirmed_brief_uses_existing_transition(v2_topic_project, frozen_now):
    result = save_author_brief(v2_topic_project, AuthorBrief(title="Muối"), confirm=True, now=frozen_now)
    assert result.state is WorkflowState.AUTHOR_BRIEF_READY
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/workflows/test_create_project_v2.py tests/workflows/test_author.py -v`  
Expected: FAIL vì hai workflow chưa tồn tại.

- [ ] **Step 4: Cài tối thiểu và giữ nguyên schema `AuthorBrief`**

`create_project_v2` dùng sibling staging, chỉ tạo `project.yaml`, `revisions/001/` và các thư mục artifact M1–M3 cần. Validate trước khi rename một lần. `save_author_brief` ghi `author/brief.yaml`; `confirm=False` không transition, `confirm=True` chỉ hợp lệ từ `TOPIC_SELECTED` và gọi `transition_v2` với hash brief cùng `validated_artifacts={"author/brief.yaml"}`. Không sửa `domain/author.py`, schema export hay creator v1.

- [ ] **Step 5: GREEN và commit**

Run: `python -m pytest tests/workflows/test_create_project_v2.py tests/workflows/test_author.py tests/workflows/test_create_project.py tests/domain/test_state_graph.py -v`  
Expected: PASS.

```powershell
git add src/healthvideo/workflows/create_project_v2.py src/healthvideo/workflows/author.py tests/workflows/test_create_project_v2.py tests/workflows/test_author.py
git commit -m "feat: create and confirm pyh workflow v2 projects"
```

---

### Task 2: Chiếu state hiện có thành hành động `/pyh`

**Files:**
- Create: `src/healthvideo/workflows/operator.py`
- Create: `tests/workflows/test_operator.py`

**Interfaces:**
- Consumes: `resolve_project_layout(project_dir)` và manifest/side state đã validate.
- Produces: `OperatorActionKind`, `OperatorAction`, `get_next_action(project_dir: Path) -> OperatorAction`, `render_status(project_dir: Path) -> str`.

- [ ] **Step 1: Viết RED table cho main states**

```python
@pytest.mark.parametrize(("state", "kind"), [
    ("idea", "choose_topic"), ("topic_selected", "confirm_brief"),
    ("author_brief_ready", "research"), ("research_in_progress", "research"),
    ("evidence_ready", "draft"), ("draft_ready", "prepare_medical_review"),
    ("awaiting_medical_review", "await_medical_approval"),
    ("medically_approved", "produce"),
    ("awaiting_video_review", "await_video_approval"),
    ("video_approved", "package"), ("packaged", "complete"),
])
def test_next_action_is_projection_of_v2_state(v2_project_factory, state, kind):
    assert get_next_action(v2_project_factory(state)).kind.value == kind
```

- [ ] **Step 2: Viết RED cases cho compatibility, side states và status**

Test v1 trả `migrate_legacy`; `NEEDS_MEDICAL_REVISION`, `NEEDS_PRODUCTION_REVISION`, `BLOCKED`, browser/model wait có action riêng; manifest hỏng fail closed với path rõ ràng. `render_status` chạy hai lần byte-identical và không ghi file/state/hash.

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/workflows/test_operator.py -v`  
Expected: FAIL vì module chưa tồn tại.

- [ ] **Step 4: Cài projection thuần, không có `run_next()`**

```python
@dataclass(frozen=True)
class OperatorAction:
    kind: OperatorActionKind
    project_dir: Path
    message: str
    artifact: Path | None
    suggested_command: str

def get_next_action(project_dir: Path) -> OperatorAction: ...
def render_status(project_dir: Path) -> str: ...
```

Chỉ branch compatibility trong `resolve_project_layout`; không rải `schema_version` checks. Unknown main/side state fail closed. `STATUS.md` chưa được ghi tự động trong task này.

- [ ] **Step 5: GREEN và commit**

Run: `python -m pytest tests/workflows/test_operator.py tests/storage/test_project_layout.py tests/domain/test_state_graph.py -v`  
Expected: PASS.

```powershell
git add src/healthvideo/workflows/operator.py tests/workflows/test_operator.py
git commit -m "feat: project workflow state into pyh actions"
```

---

### Task 3: Mở rộng production và packaging hiện có cho v2

**Files:**
- Modify: `src/healthvideo/workflows/produce.py`
- Modify: `src/healthvideo/workflows/package.py`
- Modify: `tests/workflows/test_produce.py`
- Create: `tests/workflows/test_package.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`

**Interfaces:**
- Consumes: `resolve_project_layout`, active revision, v2 approval records từ `gate_review`.
- Produces: giữ nguyên `produce_project(project_dir, tts, runner, *, dry_run=False) -> Path`; giữ nguyên `package_project(project_dir) -> Path`, thêm hành vi v2.

- [ ] **Step 1: Viết RED production v2 tests**

Thêm test: từ chối trước `MEDICALLY_APPROVED`; từ chối approval stale; approval hợp lệ dùng active revision artifacts, giữ cache idempotent và kết thúc tại `AWAITING_VIDEO_REVIEW`. Các test v1 hiện có phải giữ nguyên.

```python
def test_v2_produce_requires_current_medical_approval(v2_medically_approved_project, fake_runner):
    invalidate_reviewed_script(v2_medically_approved_project)
    with pytest.raises(ValueError, match="medical approval"):
        produce_project(v2_medically_approved_project, SilentTTS(), fake_runner)
```

- [ ] **Step 2: Viết RED package v2 tests**

Thêm test: từ chối trước video approval; từ chối hash video/approval lệch; approval hợp lệ tạo bốn file package rồi transition `VIDEO_APPROVED -> PACKAGED`; lần lỗi không đổi state và không để package bán phần. Không có network/publish API.

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/workflows/test_produce.py tests/workflows/test_package.py tests/e2e/test_golden_workflow_versions.py -k "v2 or produce or package" -v`  
Expected: FAIL ở seam v2; v1 cases PASS.

- [ ] **Step 4: Cài branch v2 qua compatibility boundary**

Cả hai public function gọi `resolve_project_layout` một lần. V1 đi đúng path cũ. V2 dùng active revision, M2 gate record và canonical/byte hashes hiện có; tuyệt đối không gọi `workflows.review.ensure_approval_current` của v1 cho v2. Package chỉ transition sang `PACKAGED` sau atomic promotion thành công. Không tạo `produce_v2.py`, `package_v2.py`, renderer hoặc format package mới.

- [ ] **Step 5: GREEN và commit**

Run: `python -m pytest tests/workflows/test_produce.py tests/workflows/test_package.py tests/e2e/test_golden_project.py tests/e2e/test_golden_workflow_versions.py tests/workflows/test_gate_review.py -v`  
Expected: PASS; v1 không đổi hành vi.

```powershell
git add src/healthvideo/workflows/produce.py src/healthvideo/workflows/package.py tests/workflows/test_produce.py tests/workflows/test_package.py tests/e2e/test_golden_workflow_versions.py
git commit -m "feat: produce and package approved v2 projects"
```

---

### Task 4: Chứng minh một golden lifecycle qua hai cổng duyệt

**Files:**
- Create: `tests/e2e/test_pyh_operator_workflow.py`
- Modify only if test exposes a real missing seam: `src/healthvideo/workflows/review_html.py`

**Interfaces:**
- Consumes: Task 1–3, `select_topic`, evidence workflow, `approve_gate`, review packet renderers, `SilentTTS`, fake runner.
- Produces: một offline acceptance test từ topic selection đến `PACKAGED`.

- [ ] **Step 1: Viết E2E test dùng frozen evidence, không gọi mạng**

```python
def test_pyh_golden_stops_at_both_human_gates(tmp_path, frozen_now, fake_runner):
    project = create_project_v2(tmp_path, "muoi-va-huyet-ap", "Muối và huyết áp", now=frozen_now)
    select_frozen_topic_and_confirm_brief(project, now=frozen_now)
    install_frozen_evidence_and_draft(project, now=frozen_now)
    render_medical_packet(active_revision_root(project))
    assert get_next_action(project).kind is OperatorActionKind.AWAIT_MEDICAL_APPROVAL
    with pytest.raises(ValueError):
        produce_project(project, SilentTTS(), fake_runner)
    approve_gate(project, GateKind.MEDICAL, reviewer="BS Test", note="fixture", now=frozen_now)
    produce_project(project, SilentTTS(), fake_runner)
    render_video_packet(active_revision_root(project))
    assert get_next_action(project).kind is OperatorActionKind.AWAIT_VIDEO_APPROVAL
    with pytest.raises(ValueError):
        package_project(project)
    approve_gate(project, GateKind.VIDEO, reviewer="BS Test", note="fixture", now=frozen_now)
    package_project(project)
    assert get_next_action(project).kind is OperatorActionKind.COMPLETE
```

- [ ] **Step 2: Thêm invalidation assertions**

Sau medical approval: script/evidence/semantic asset edit → `NEEDS_MEDICAL_REVISION`; audio/timing/render/decorative asset edit → `NEEDS_PRODUCTION_REVISION`; unknown path → medical fail-closed. Dùng `evaluate_invalidation`, không tự chọn rollback state trong operator.

- [ ] **Step 3: Chạy E2E và sửa đúng seam bị lộ**

Run: `python -m pytest tests/e2e/test_pyh_operator_workflow.py -v`  
Expected: PASS sau khi nối helper cần thiết. `review_html.py` vốn nhận revision root nên không sửa nếu test đã chạy.

- [ ] **Step 4: Chạy regression y khoa/workflow**

Run: `python -m pytest tests/e2e tests/workflows/test_gate_review.py tests/domain/test_invalidation.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tests/e2e/test_pyh_operator_workflow.py src/healthvideo/workflows/review_html.py
git commit -m "test: prove pyh lifecycle across both review gates"
```

---

### Task 5: Thêm CLI primitives và slash adapter dùng chung

**Files:**
- Create: `src/healthvideo/commands/__init__.py`
- Create: `src/healthvideo/commands/operator.py`
- Create: `.agents/skills/pyh/SKILL.md`
- Create: `.claude/commands/pyh.md`
- Create: `tests/contracts/test_pyh_skill.py`
- Modify: `src/healthvideo/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1–4 và topic/review/produce/package commands hiện có.
- Produces: `healthvideo operator new|status|select|brief`; `/pyh` intents `discover|new|select|continue|edit|review|package|status`.

- [ ] **Step 1: Viết RED CLI tests**

Test `operator new` luôn tạo v2; `status --json` trả `OperatorAction`; `select` gọi đúng semantics của `select_topic`; `brief` chỉ advance với `--confirm`; help snapshot vẫn chứa tất cả command cũ. Không thêm operator approval command.

- [ ] **Step 2: Viết RED skill contract tests**

```python
def test_claude_adapter_points_to_one_canonical_workflow():
    canonical = Path(".agents/skills/pyh/SKILL.md").read_text(encoding="utf-8")
    shim = Path(".claude/commands/pyh.md").read_text(encoding="utf-8")
    assert "healthvideo operator status" in canonical
    assert ".agents/skills/pyh/SKILL.md" in shim
    assert "ổn" in canonical and "không tạo approval" in canonical
    assert "không tự động xuất bản" in canonical
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/test_cli.py -k operator -v`  
Run: `python -m pytest tests/contracts/test_pyh_skill.py -v`  
Expected: FAIL vì command/skill chưa tồn tại.

- [ ] **Step 4: Cài adapter mỏng**

`commands/operator.py` chỉ parse input và gọi workflow. `.agents/skills/pyh/SKILL.md` làm: xác định intent → resolve project → gọi `operator status --json` → thực hiện đúng một deterministic operation hoặc chạy đến human boundary → trình bày artifact → dừng. Discovery chỉ list/create/select topic cards M3 hoặc fixture đã có; không thêm scraping/network framework. Claude shim đọc canonical skill và chuyển `$ARGUMENTS`. Không sửa `AGENTS.md`/`CLAUDE.md` trừ khi smoke test chứng minh discovery cần đăng ký.

- [ ] **Step 5: GREEN và commit**

Run: `python -m pytest tests/test_cli.py tests/contracts/test_pyh_skill.py tests/workflows/test_operator.py -v`  
Expected: PASS.

```powershell
git add src/healthvideo/commands src/healthvideo/cli.py .agents/skills/pyh/SKILL.md .claude/commands/pyh.md tests/test_cli.py tests/contracts/test_pyh_skill.py
git commit -m "feat: expose shared pyh operator workflow"
```

---

### Task 6: Quick Start và acceptance toàn hệ thống

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-12-pyh-operator-experience-design.md`
- Optional only if demonstrated useful: write `STATUS.md` from `render_status()` in operator CLI.

**Interfaces:**
- Consumes: Task 1–5.
- Produces: một Quick Start một màn hình và milestone được kiểm chứng.

- [ ] **Step 1: Viết Quick Start đúng năng lực đã chứng minh**

Phần đầu README chỉ gồm cài đặt, `/pyh tìm chủ đề`, `/pyh chọn chủ đề`, `/pyh tiếp tục`, cách mở hai packet và vị trí `publish/`. Chuyển CLI kỹ thuật/migration xuống phần bảo trì. Nêu rõ online discovery và TTS thật chưa thuộc acceptance.

- [ ] **Step 2: Chạy full quality gate**

Run: `python -m pytest -q`  
Run: `python -m ruff check src tests tools`  
Run: `python tools/export_schemas.py`  
Run: `git diff --exit-code -- schemas`  
Run: `pnpm --dir video test`  
Run: `pnpm --dir video typecheck`  
Run: `git diff --check`  
Expected: tất cả PASS; v1 golden và command cũ giữ nguyên.

- [ ] **Step 3: Chạy smoke operator local**

Run: `healthvideo operator new tests/artifacts --slug pyh-smoke --title "Video kiểm thử"`  
Run: `healthvideo operator status tests/artifacts/pyh-smoke --json`  
Expected: project schema v2 ở state `idea`, action `choose_topic`, không approval và không publish artifact.

- [ ] **Step 4: Rà soát non-goal và cập nhật trạng thái**

Diff không được có web app, auto-post, template registry, provider/router framework, state mới hoặc xóa v1. Chỉ ghi `STATUS.md` tự động nếu golden/smoke chứng minh nó giúp tiếp tục workflow mà không tham gia state/hash. Đổi spec sang `Implemented` và cập nhật bảng tiến độ README chỉ sau khi Step 2–3 đạt.

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/superpowers/specs/2026-09-12-pyh-operator-experience-design.md
git commit -m "docs: complete pyh operator milestone"
```

## Success Criteria

- Project v2 mới đi hết offline golden lifecycle từ topic selection đến `PACKAGED`.
- `/pyh tiếp tục` chỉ chiếu action từ state/artifact hiện có và không vượt human boundary.
- Production không thể chạy thiếu medical approval hiện hành; package không thể chạy thiếu medical và video approval hiện hành.
- Thay đổi sau duyệt dùng invalidation policy M1 và quay lại đúng gate.
- Codex và Claude dùng một canonical workflow definition.
- Không thêm workflow state, approval implementation, renderer, provider/template/router framework, web app hoặc auto-publishing.
- Toàn bộ hành vi v1 và CLI cũ tiếp tục PASS.
