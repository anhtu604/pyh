# Workflow Kernel M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai M1 thành kernel workflow v2 có state graph và side states, revision bất biến, stage manifest, semantic asset manifest, invalidation xác định và migration v1→v2 không phá dữ liệu, trong khi đường chạy MVP v1 luôn giữ nguyên hành vi và luôn xanh.

**Architecture:** Giữ `src/healthvideo/domain/project.py`, `ProjectState`, `ORDER` và `transition()` làm compatibility kernel v1. Kernel v2 được đặt cạnh v1 trong các module domain/storage/workflow riêng, được chọn bằng `schema_version`; reader hiểu cả hai layout, writer mới chỉ ghi v2. Mọi thay đổi v2 diễn ra trong active revision, dùng record bất biến và promotion cùng volume. `project migrate` dựng một project v2 mới ở staging cạnh đích, validate toàn bộ rồi promote một lần; project v1 nguồn không bị sửa.

**Tech Stack:** Python 3.11+, Pydantic 2.13.5, Typer 0.27.2, PyYAML 6.0.3, pytest 9.1.1, Ruff 0.16.6; `pathlib.Path`, `hashlib`, `shutil`, `os.replace`; không thêm dependency runtime mới trong M1.

**Spec:** `docs/superpowers/specs/2026-09-09-closed-loop-healthvideo-workflow-design.md` tại commit `8a2b9a7`, đặc biệt §5–§7, §14–§16 và §20.

## Global Constraints

- Không đổi giá trị, thứ tự hoặc hành vi của `ProjectState`, `ORDER`, `ProjectManifest` và `transition()` v1. Không đưa side state v2 vào `ORDER`.
- Trước Task 1 phải ghi baseline thực tế bằng `python -m pytest -q`; sau **mỗi** task phải chạy focused tests, dual-golden checkpoint, full pytest và Ruff. Không khóa plan vào con số 91 hay 124 vì số test thay đổi; tiêu chí là không có regression.
- Golden v1 hiện tại và golden v2 mới phải chạy song song từ Task 1. `tests/e2e/test_golden_project.py` tiếp tục kiểm tra MVP v1; `tests/e2e/test_golden_workflow_versions.py` là checkpoint v1/v2 được mở rộng sau mỗi task.
- Mỗi task bắt đầu bằng test RED có nguyên nhân đúng, chỉ cài phần tối thiểu để GREEN, cập nhật `README.md` trong cùng commit với mã, rồi commit riêng. Không gộp task khi một task trước chưa xanh.
- Test hoàn toàn offline: không mạng, tài khoản AI, Scopus, GPU hay browser login. Thời gian và UUID phải inject/freeze; filesystem dùng `tmp_path`.
- Đường dẫn nội bộ dùng `pathlib.Path`; đường dẫn lưu trong YAML là POSIX tương đối, không dùng symlink để chọn active revision.
- Không vượt medical/video gate, không tự ký lại approval, không tự động đăng. M1 chỉ cung cấp kernel và migration; tích hợp review packet/gate v2 thuộc M2.
- Migration không sửa project v1 tại chỗ, không xóa nguồn và không ghi đè project đích. Staging phải là sibling của đích để promotion là một thao tác rename cùng volume.
- Hash YAML/JSON là canonical JSON hash hiện có; hash asset là SHA-256 byte. Unknown state, artifact hoặc metadata field phải fail closed.
- Không commit file media, cache, audio, render, secret hoặc toàn văn có bản quyền. Không chạm file video untracked ở workspace.

## File map

| File | Trách nhiệm M1 | Quan hệ với v1 |
|---|---|---|
| `src/healthvideo/domain/project.py` | Kernel tuyến tính v1 | Giữ nguyên hành vi; test khóa regression |
| `src/healthvideo/domain/project_v2.py` | State enum, manifest v2 và side-state record | Nằm cạnh, không thay thế v1 |
| `src/healthvideo/domain/state_graph.py` | Cạnh graph, precondition và `transition_v2` | API mới chỉ nhận manifest v2 |
| `src/healthvideo/domain/stage.py` | Model stage manifest bất biến | Mới |
| `src/healthvideo/domain/revision.py` | Revision ID và metadata revision | Mới |
| `src/healthvideo/domain/asset_manifest.py` | Asset record, `semantic` và policy phân loại | Mới; `assets.py` v1 giữ nguyên |
| `src/healthvideo/domain/invalidation.py` | Quyết định gate stale từ thay đổi artifact | Mới |
| `src/healthvideo/storage/project_layout.py` | Reader phân biệt layout v1/v2 | Không đổi writer v1 |
| `src/healthvideo/storage/immutable.py` | Ghi file/dir một lần, promotion không ghi đè | Dùng lại primitive storage hiện có |
| `src/healthvideo/storage/stages.py` | Append-only stage manifests | Mới |
| `src/healthvideo/storage/revisions.py` | Tạo và validate revision bất biến | Mới |
| `src/healthvideo/workflows/migrate.py` | Plan, validate và thực thi migration | Mới |
| `src/healthvideo/cli.py` | Thêm `revision create`, `project migrate` | Lệnh v1 giữ nguyên |
| `tools/export_schemas.py` | Xuất schema v2/stage/asset | Không đổi schema v1 hiện có |
| `schemas/project-v2.schema.json` | Contract project v2 | Mới |
| `schemas/stage-manifest.schema.json` | Contract stage record | Mới |
| `schemas/asset-manifest.schema.json` | Contract semantic asset | Mới |
| `tests/fixtures/golden-project-v2/` | Fixture revisioned v2 | Chạy cạnh `golden-project/` v1 |
| `tests/e2e/test_golden_workflow_versions.py` | Checkpoint compatibility xuyên suốt M1 | Bắt buộc chạy mỗi task |
| `README.md` | Tiến độ, test và commit từng task M1 | Cập nhật cùng commit |

---

### Task 1: Contract project v2 và dual-golden checkpoint

**Files:**
- Create: `src/healthvideo/domain/project_v2.py`
- Create: `src/healthvideo/storage/project_layout.py`
- Create: `tests/domain/test_project_v2.py`
- Create: `tests/storage/test_project_layout.py`
- Create: `tests/fixtures/golden-project-v2/project.yaml`
- Create: `tests/fixtures/golden-project-v2/revisions/001/` với artifact golden v1 được ánh xạ theo bảng Task 8
- Create: `tests/fixtures/golden-project-v2/revisions/001/topic/card.yaml`
- Create: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `tools/export_schemas.py`
- Create: `schemas/project-v2.schema.json`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `README.md`

**Interfaces:**
- `WorkflowState`: 13 main states và 6 side states đúng §6.
- `ProjectManifestV2`: frozen Pydantic model, `schema_version="2.0"`, `active_revision="001"`.
- `resolve_project_layout(project_dir: Path) -> ProjectLayout` trả `artifact_root=project_dir` cho v1 và `artifact_root=project_dir / "revisions" / active_revision` cho v2.

- [ ] **Step 1: Ghi baseline trước thay đổi**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Expected: cả hai PASS; ghi số test thực tế và ngày chạy vào hàng `M1.1` mới trong `README.md` trước khi commit task.

- [ ] **Step 2: Viết RED tests cho manifest và reader hai version**

```python
def test_reader_resolves_v1_and_v2_artifact_roots() -> None:
    v1 = resolve_project_layout(Path("tests/fixtures/golden-project"))
    v2 = resolve_project_layout(Path("tests/fixtures/golden-project-v2"))
    assert v1.schema_version == "1.0"
    assert v1.artifact_root == v1.project_dir
    assert v2.schema_version == "2.0"
    assert v2.artifact_root == v2.project_dir / "revisions" / "001"


def test_v1_and_v2_golden_are_available_from_first_m1_task() -> None:
    layouts = [resolve_project_layout(path) for path in GOLDEN_PROJECTS]
    assert [layout.schema_version for layout in layouts] == ["1.0", "2.0"]
    for layout in layouts:
        assert (layout.artifact_root / "evidence" / "ledger.yaml").is_file()
        assert (layout.artifact_root / "script" / "script.yaml").is_file()
        assert (layout.artifact_root / "storyboard" / "storyboard.yaml").is_file()
```

- [ ] **Step 3: Chạy RED**

Run: `python -m pytest tests/domain/test_project_v2.py tests/storage/test_project_layout.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: FAIL vì module và fixture v2 chưa tồn tại; test v1 hiện hữu vẫn PASS khi chạy riêng.

- [ ] **Step 4: Cài model và reader tối thiểu**

```python
class WorkflowState(StrEnum):
    IDEA = "idea"
    TOPIC_SELECTED = "topic_selected"
    AUTHOR_BRIEF_READY = "author_brief_ready"
    RESEARCH_IN_PROGRESS = "research_in_progress"
    EVIDENCE_READY = "evidence_ready"
    DRAFT_READY = "draft_ready"
    AWAITING_MEDICAL_REVIEW = "awaiting_medical_review"
    MEDICALLY_APPROVED = "medically_approved"
    PRODUCTION_IN_PROGRESS = "production_in_progress"
    AWAITING_VIDEO_REVIEW = "awaiting_video_review"
    VIDEO_APPROVED = "video_approved"
    PACKAGED = "packaged"
    PUBLISHED_MANUAL = "published_manual"
    AWAITING_BROWSER_LOGIN = "awaiting_browser_login"
    AWAITING_SECOND_MODEL_REVIEW = "awaiting_second_model_review"
    NEEDS_MEDICAL_REVISION = "needs_medical_revision"
    NEEDS_PRODUCTION_REVISION = "needs_production_revision"
    BLOCKED = "blocked"
    TOPIC_REJECTED = "topic_rejected"


class ProjectManifestV2(BaseModel):
    model_config = ConfigDict(frozen=True)
    schema_version: Literal["2.0"] = "2.0"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    language: str = "vi"
    state: WorkflowState = WorkflowState.IDEA
    active_revision: str = Field(default="001", pattern=r"^[0-9]{3}$")
    side_state: SideStateRecord | None = None
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
```

`SideStateRecord` là discriminated union: năm side state có `resume_state`, `reason_code`, `entered_at`; `topic_rejected` không có `resume_state` nhưng vẫn có lý do và thời điểm. Model validator bắt buộc `side_state.type == state` khi state là side state và `side_state is None` khi state là main state.

`resolve_project_layout` chỉ chấp nhận chính xác schema `1.0` hoặc `2.0`, validate bằng model tương ứng và từ chối active revision thiếu. Fixture v2 bắt đầu ở `idea`, chứa artifact kiểm thử dưới `revisions/001` nhưng không tạo state hoặc approval giả; các task sau chỉ chuyển state trên bản sao trong `tmp_path`. Task 1 phải tạo `topic/card.yaml` tổng hợp từ `project.slug` và tiêu đề trong `author-brief.yaml`, với đúng payload tối thiểu dưới đây; đây là fixture tổng hợp phục vụ main-edge checkpoint, không phải topic evidence thật:

```yaml
schema_version: "2.0"
synthetic_test_record: true
slug: muoi-va-huyet-ap
title: Ăn mặn và tăng huyết áp
origin: migration_fixture
```

- [ ] **Step 5: Xuất schema và chạy GREEN**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_project_v2.py tests/storage/test_project_layout.py tests/e2e/test_golden_workflow_versions.py tests/contracts/test_schemas.py -v`

Expected: PASS; chạy exporter lần hai không đổi `schemas/project-v2.schema.json`.

- [ ] **Step 6: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: toàn bộ PASS; `tests/e2e/test_golden_project.py` v1 không đổi. Cập nhật `README.md` với M1.1, số test và commit cùng mã.

Commit: `git commit -m "feat: add parallel v2 project contract"`

---

### Task 2: Main-path graph v2 với precondition

**Files:**
- Create: `src/healthvideo/domain/state_graph.py`
- Create: `tests/domain/test_state_graph.py`
- Modify: `tests/domain/test_project.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `TransitionContext(active_revision, current_input_hash, validated_artifacts, reason_code, new_revision_from)`; `new_revision_from` mặc định `None` và chỉ do revision service xác nhận.
- `transition_v2(project, target, context) -> ProjectManifestV2`.
- `MAIN_RULES: Mapping[tuple[WorkflowState, WorkflowState], TransitionRule]`.

- [ ] **Step 1: Viết RED tests cho graph và khóa v1**

```python
def test_main_graph_requires_artifacts_and_active_revision() -> None:
    project = ProjectManifestV2(slug="muoi-va-huyet-ap", state="draft_ready")
    context = TransitionContext(
        active_revision="001",
        current_input_hash="0" * 64,
        validated_artifacts=frozenset(),
    )
    with pytest.raises(TransitionError, match="missing required artifacts"):
        transition_v2(project, WorkflowState.AWAITING_MEDICAL_REVIEW, context)


def test_v1_linear_order_and_transition_are_unchanged() -> None:
    assert [state.value for state in ORDER] == EXPECTED_V1_ORDER
    project = ProjectManifest(slug="muoi-va-huyet-ap")
    assert transition(project, ProjectState.EVIDENCE_IN_PROGRESS).state is ProjectState.EVIDENCE_IN_PROGRESS
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(project, ProjectState.RENDERED)
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_state_graph.py tests/domain/test_project.py -v`

Expected: test v2 FAIL do chưa có graph; regression v1 PASS.

- [ ] **Step 3: Cài các cạnh main path và precondition xác định**

`MAIN_RULES` phải có đúng chuỗi §6, cạnh phục hồi `production_in_progress -> medically_approved`, và các artifact tối thiểu sau: `topic/card.yaml`, `author/brief.yaml`, `evidence/ledger.yaml`, `script/script.yaml`, `storyboard/storyboard.yaml`, `assets/asset-manifest.yaml`, medical approval binding, render/video-QA binding, video approval binding, publish manifest và `publish/receipt.yaml`. Mọi cạnh bắt buộc `current_input_hash` hợp lệ, context khớp `active_revision`, và tập artifact riêng của cạnh đã validate.

```python
def transition_v2(
    project: ProjectManifestV2,
    target: WorkflowState,
    context: TransitionContext,
) -> ProjectManifestV2:
    rule = MAIN_RULES.get((project.state, target))
    if rule is None:
        raise TransitionError(f"invalid v2 transition: {project.state} -> {target}")
    rule.validate(project, context)
    return project.model_copy(update={"state": target, "side_state": None})
```

- [ ] **Step 4: GREEN và mở rộng dual-golden**

Run: `python -m pytest tests/domain/test_state_graph.py tests/domain/test_project.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: PASS; dual-golden test xác nhận v2 đi được một cạnh hợp lệ bằng dữ liệu fixture và v1 vẫn chỉ đi đúng bước kế tiếp.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật hàng M1.2 trong `README.md` cùng commit.

Commit: `git commit -m "feat: add preconditioned v2 state graph"`

---

### Task 3: Side-state graph và đường resume/reject

**Files:**
- Modify: `src/healthvideo/domain/state_graph.py`
- Modify: `tests/domain/test_state_graph.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- Mở rộng `transition_v2(..., *, reason_code, resume_state, entered_at)` để vào side state.
- `SIDE_ENTRY_RULES` và `SIDE_EXIT_RULES` biểu diễn đúng bảng §6.

- [ ] **Step 1: Viết RED tests dạng table cho toàn bộ side states**

```python
@pytest.mark.parametrize(("source", "side", "resume"), SIDE_ENTRY_CASES)
def test_side_state_entry_records_resume_reason_and_time(source, side, resume, frozen_now) -> None:
    changed = transition_v2(
        manifest_at(source), side, valid_context(),
        reason_code="review_required", resume_state=resume, entered_at=frozen_now,
    )
    assert changed.side_state is not None
    assert changed.side_state.reason_code == "review_required"
    assert changed.side_state.entered_at == frozen_now


def test_topic_rejected_reopens_only_as_new_revision() -> None:
    rejected = manifest_at(WorkflowState.TOPIC_REJECTED, active_revision="001")
    with pytest.raises(TransitionError, match="new revision"):
        transition_v2(rejected, WorkflowState.TOPIC_SELECTED, valid_context("001"))
```

Tests phải phủ cả cạnh bị cấm: login sai resume, second-model sai nguồn, medical revision bỏ qua gate, production revision phát hiện semantic issue, blocked resume sai state và topic rejected không tăng revision.

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_state_graph.py -v`

Expected: FAIL ở các case side-state chưa được graph hỗ trợ.

- [ ] **Step 3: Cài table side-state và validator**

Không dùng `if/elif` rải rác. Rule lưu tập source, tập exit, yêu cầu revision tăng và cách kiểm `resume_state`. `topic_rejected -> topic_selected` chỉ hợp lệ sau khi revision service đã tăng `project.active_revision` và context chứng minh `new_revision_from` là revision cha; không so sánh với một active revision cũ trong chính manifest. `needs_medical_revision` không thể ra state sau gate; `needs_production_revision -> draft_ready` dùng reason class `semantic_issue`.

- [ ] **Step 4: GREEN, dual-golden và full regression**

Run: `python -m pytest tests/domain/test_state_graph.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS; v1 fixture không có side state và vẫn chạy.

- [ ] **Step 5: README và commit**

Cập nhật M1.3 trong `README.md`, liệt kê 6 side states và lệnh test đã chạy.

Commit: `git commit -m "feat: add v2 side-state transitions"`

---

### Task 4: Stage manifest bất biến và append-only storage

**Files:**
- Create: `src/healthvideo/domain/stage.py`
- Create: `src/healthvideo/storage/immutable.py`
- Create: `src/healthvideo/storage/stages.py`
- Create: `tests/domain/test_stage.py`
- Create: `tests/storage/test_immutable.py`
- Create: `tests/storage/test_stages.py`
- Modify: `tools/export_schemas.py`
- Create: `schemas/stage-manifest.schema.json`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `StageStatus`: `running|complete|failed`.
- `StageManifest`: frozen model với đủ 11 trường §4.
- `append_stage_manifest(revision_root: Path, manifest: StageManifest) -> Path`.
- `write_yaml_once(path: Path, payload: Mapping[str, object]) -> None` từ chối overwrite.

- [ ] **Step 1: Viết RED tests cho invariant và append-only**

```python
def test_complete_stage_requires_output_hash_and_completed_at() -> None:
    with pytest.raises(ValidationError):
        StageManifest(**COMPLETE_WITHOUT_OUTPUT)


def test_stage_record_cannot_be_overwritten(tmp_path: Path) -> None:
    path = append_stage_manifest(tmp_path, stage_manifest())
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_yaml_once(path, {"status": "failed"})
    assert path.read_bytes() == original
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_stage.py tests/storage/test_immutable.py tests/storage/test_stages.py -v`

Expected: FAIL vì model/storage chưa tồn tại.

- [ ] **Step 3: Cài model và đường dẫn record**

`StageManifest` chứa `stage`, `status`, `input_hash`, `output_hash`, `tool_version`, `agent`, `model`, `started_at`, `completed_at`, `estimated_input_tokens`, `estimated_output_tokens`. Hash dùng regex 64 ký tự hex thường; thời gian phải timezone-aware; token không âm. Record lưu tại `workflow/stages/<stage>/<started-at>-<input-hash-prefix>.yaml`; tên được chuẩn hóa không chứa `:` để chạy Windows. `write_yaml_once` tạo parent bằng `Path.mkdir`, mở exclusive, flush và `os.fsync`; nếu đích tồn tại không đổi byte.

- [ ] **Step 4: Xuất schema, GREEN và dual-golden**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_stage.py tests/storage/test_immutable.py tests/storage/test_stages.py tests/contracts/test_schemas.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: PASS; dual-golden ghi/read stage chỉ trong bản sao `tmp_path`, không sửa fixture tracked.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M1.4 trong `README.md` cùng commit.

Commit: `git commit -m "feat: add immutable stage manifests"`

---

### Task 5: Revision bất biến và lệnh `revision create`

**Files:**
- Create: `src/healthvideo/domain/revision.py`
- Create: `src/healthvideo/storage/revisions.py`
- Create: `tests/domain/test_revision.py`
- Create: `tests/storage/test_revisions.py`
- Modify: `src/healthvideo/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `RevisionRecord(schema_version, revision, parent_revision, reason, created_at)` frozen.
- `create_revision(project_dir: Path, reason: str, *, now: datetime) -> str`.
- CLI `healthvideo revision create <project> --reason "..."`.

- [ ] **Step 1: Viết RED tests cho copy-on-write và CLI**

```python
def test_create_revision_preserves_parent_bytes_and_switches_active_revision(tmp_path: Path) -> None:
    project = copy_golden_v2(tmp_path)
    before = snapshot_tree(project / "revisions" / "001")
    revision = create_revision(project, "Sửa luận điểm", now=FROZEN_NOW)
    assert revision == "002"
    assert snapshot_tree(project / "revisions" / "001") == before
    assert read_yaml(project / "project.yaml")["active_revision"] == "002"


def test_revision_create_rejects_v1_project() -> None:
    result = runner.invoke(app, ["revision", "create", str(GOLDEN_V1), "--reason", "Sửa"])
    assert result.exit_code == 1
    assert "migrate" in result.stdout
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_revision.py tests/storage/test_revisions.py tests/test_cli.py -v`

Expected: FAIL vì revision API/subcommand chưa có.

- [ ] **Step 3: Cài revision transaction**

Nguồn copy gồm `topic/`, `author/`, `evidence/`, `script/`, `storyboard/`, `assets/`; không copy `handoffs/`, `reviews/`, `audio/`, `renders/`, `publish/`. Dựng `revisions/.002-stage-<uuid>`, ghi `workflow.yaml`, validate tất cả path, rồi promote sang `revisions/002` bằng `promote_directory_once`. Chỉ sau promotion mới ghi nguyên tử `project.yaml.active_revision=002`. Nếu lỗi, xóa đúng staging vừa tạo, giữ project manifest và revision 001 nguyên vẹn. Nếu `002` tồn tại, fail; không replace.

```python
revision_app = typer.Typer(no_args_is_help=True)
app.add_typer(revision_app, name="revision")


@revision_app.command("create")
def revision_create(project_dir: ProjectDir, reason: Annotated[str, typer.Option("--reason")]) -> None:
    revision = create_revision(project_dir, reason, now=datetime.now().astimezone())
    typer.echo(f"Created revision: {revision}")
```

- [ ] **Step 4: GREEN, failure injection và dual-golden**

Run: `python -m pytest tests/domain/test_revision.py tests/storage/test_revisions.py tests/test_cli.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: PASS, gồm test copy failure, validation failure và destination collision; mọi case xác nhận parent bytes không đổi.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M1.5 trong `README.md` cùng commit.

Commit: `git commit -m "feat: create immutable workflow revisions"`

---

### Task 6: Semantic asset manifest và policy phân loại

**Files:**
- Create: `src/healthvideo/domain/asset_manifest.py`
- Create: `tests/domain/test_asset_manifest.py`
- Create: `tests/fixtures/golden-project-v2/revisions/001/assets/asset-manifest.yaml`
- Modify: `tools/export_schemas.py`
- Create: `schemas/asset-manifest.schema.json`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `AssetKind`: `evidence_highlight|data_chart|medical_diagram|medical_text|background|texture|flourish|transition`.
- `AssetRecord(path, kind, semantic, classification_reason, sha256, source, license, creator, revision)` frozen.
- `AssetManifest(schema_version="2.0", assets)` frozen.
- `validate_asset_manifest(revision_root: Path, manifest: AssetManifest) -> None`.

- [ ] **Step 1: Viết RED tests cho semantic policy và byte hash**

```python
@pytest.mark.parametrize("kind", SEMANTIC_REQUIRED_KINDS)
def test_medical_asset_kinds_cannot_be_marked_decorative(kind: AssetKind) -> None:
    with pytest.raises(ValidationError, match="semantic=true"):
        AssetRecord(**asset_payload(kind=kind, semantic=False))


def test_manifest_rejects_missing_or_changed_asset_bytes(tmp_path: Path) -> None:
    revision = copy_golden_v2_revision(tmp_path)
    manifest = load_asset_manifest(revision / "assets" / "asset-manifest.yaml")
    (revision / manifest.assets[0].path).write_bytes(b"changed")
    with pytest.raises(AssetIntegrityError, match="sha256"):
        validate_asset_manifest(revision, manifest)
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_asset_manifest.py tests/contracts/test_schemas.py -v`

Expected: FAIL vì asset contract chưa tồn tại.

- [ ] **Step 3: Cài contract và policy đúng §7**

`evidence_highlight`, chart mang số liệu/claim, medical diagram và medical text/marker luôn `semantic=true`; chỉ background, texture, flourish, transition mới được `false`. Storyboard/editorial agent đặt cờ ở bước I; validator cưỡng chế policy; bác sĩ xác nhận ở M2. `classification_reason` bắt buộc khi một asset trang trí được hạ từ `true` xuống `false`; helper so sánh hai manifest từ chối reclassification thiếu lý do. Path phải POSIX tương đối, nằm trong revision, không `..`, không absolute. Mọi asset semantic phải tồn tại và khớp SHA-256 byte trước khi đủ điều kiện vào medical gate. Duplicate path bị từ chối.

- [ ] **Step 4: Xuất schema, GREEN và dual-golden**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_asset_manifest.py tests/contracts/test_schemas.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: PASS; golden v2 khai báo `assets/evidence-r01.svg` là `evidence_highlight`, `semantic: true`, hash đúng; golden v1 vẫn dùng compatibility logic hiện hữu.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M1.6 trong `README.md` cùng commit.

Commit: `git commit -m "feat: classify semantic workflow assets"`

---

### Task 7: Invalidation engine xác định và fail-closed

**Files:**
- Create: `src/healthvideo/domain/invalidation.py`
- Create: `tests/domain/test_invalidation.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `InvalidationLevel`: `none|package|video|medical` theo thứ tự tăng dần.
- `ArtifactChange(path: Path, json_pointers: frozenset[str])`.
- `InvalidationDecision(level, target_state, reason_codes)` frozen.
- `evaluate_invalidation(changes, asset_manifest) -> InvalidationDecision`.

- [ ] **Step 1: Viết RED matrix cho mọi loại thay đổi**

```python
@pytest.mark.parametrize(
    ("path", "pointers", "expected"),
    [
        ("evidence/ledger.yaml", frozenset(), InvalidationLevel.MEDICAL),
        ("script/script.yaml", frozenset(), InvalidationLevel.MEDICAL),
        ("audio/narration.wav", frozenset(), InvalidationLevel.VIDEO),
        ("publish/metadata.yaml", frozenset({"/posting/visibility"}), InvalidationLevel.PACKAGE),
        ("publish/metadata.yaml", frozenset({"/posting/caption_text"}), InvalidationLevel.MEDICAL),
        ("unknown/file.yaml", frozenset(), InvalidationLevel.MEDICAL),
    ],
)
def test_invalidation_matrix(path, pointers, expected, asset_manifest) -> None:
    result = evaluate_invalidation([ArtifactChange(path=Path(path), json_pointers=pointers)], asset_manifest)
    assert result.level is expected
```

Thêm test semantic asset→medical, decorative asset→video, nhiều change lấy mức cao nhất, và metadata pointer rỗng/không chuẩn→medical.

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/domain/test_invalidation.py -v`

Expected: FAIL vì engine chưa tồn tại.

- [ ] **Step 3: Cài policy thuần dữ liệu**

Allowlist duy nhất không làm medical stale là: `/posting/platform`, `/posting/account_handle`, `/posting/scheduled_at`, `/posting/visibility`, `/posting/allow_comments`, `/posting/allow_duet`, `/posting/allow_stitch`, `/tracking/campaign_id`. Ngoài danh sách, gồm caption, hashtag, disclaimer, source list, thumbnail text và pinned comment, trả medical. Evidence/script/storyboard/semantic asset trả `needs_medical_revision`; audio/timing/render/decorative asset trả `needs_production_revision`; allowlisted publish metadata chỉ yêu cầu rebuild package và không đổi gate. Unknown fail closed về medical.

- [ ] **Step 4: GREEN, dual-golden và full regression**

Run: `python -m pytest tests/domain/test_invalidation.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS; fixture v1 không bị áp policy v2.

- [ ] **Step 5: README và commit**

Cập nhật M1.7 trong `README.md`, ghi rõ allowlist và fail-closed behavior.

Commit: `git commit -m "feat: evaluate deterministic gate invalidation"`

---

### Task 8: Migration planner và ánh xạ state v1→v2

**Files:**
- Create: `src/healthvideo/workflows/migrate.py`
- Create: `tests/workflows/test_migrate_plan.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `MigrationPlan(source, destination, source_state, proposed_state, files, hashes, approval_disposition)` frozen.
- `plan_migration(source: Path) -> MigrationPlan` thuần read-only.
- Đích mặc định: sibling `source.parent / f"{source.name}-v2"`.

**Bảng ánh xạ path v1→v2 bắt buộc:**

| Path/source v1 | Path v2 | Xử lý |
|---|---|---|
| `project.yaml` | `project.yaml` ở root project đích | Transform schema/state, thêm `active_revision: "001"`; không copy nguyên văn |
| `author-brief.yaml` | `revisions/001/author/brief.yaml` | Copy nội dung canonical, không đổi nghĩa |
| `evidence/ledger.yaml` | `revisions/001/evidence/ledger.yaml` | Copy nội dung canonical |
| `script/script.yaml` | `revisions/001/script/script.yaml` | Copy nội dung canonical |
| `storyboard/storyboard.yaml` | `revisions/001/storyboard/storyboard.yaml` | Copy nội dung canonical |
| `assets/evidence-r01.svg` | `revisions/001/assets/evidence-r01.svg` | Copy đúng byte; khai báo `semantic: true` trong asset manifest |
| Không có path v1; tổng hợp từ `project.slug` + `author-brief.yaml.title` | `revisions/001/topic/card.yaml` | Sinh đúng payload synthetic đã khóa ở Task 1 |
| Không có path v1 | `revisions/001/assets/asset-manifest.yaml` | Sinh ở migration từ asset được storyboard tham chiếu; không tự nhận approval |

Golden v1 hiện không có artifact nào bị bỏ. Nếu fixture v1 có thêm path tracked trước lúc implement, dừng như một mâu thuẫn plan/fixture thay vì tự chọn copy hoặc bỏ. `MigrationPlan.files` và fixture v2 Task 1 phải dùng chính xác bảng này; mọi path dẫn xuất ngoài bảng là lỗi contract.

- [ ] **Step 1: Viết RED table cho đủ 10 state v1**

```python
@pytest.mark.parametrize(
    ("v1", "v2"),
    [
        ("idea", "idea"),
        ("evidence_in_progress", "research_in_progress"),
        ("evidence_ready", "evidence_ready"),
        ("awaiting_medical_review", "awaiting_medical_review"),
        ("script_approved", "medically_approved"),
        ("producing", "production_in_progress"),
        ("rendered", "awaiting_video_review"),
        ("awaiting_video_review", "awaiting_video_review"),
        ("approved_to_publish", "video_approved"),
        ("published", "published_manual"),
    ],
)
def test_migration_state_map(v1, v2, tmp_path: Path) -> None:
    source = make_v1_project(tmp_path, state=v1)
    assert plan_migration(source).proposed_state.value == v2
```

Thêm test snapshot toàn bộ byte project nguồn trước/sau dry plan và test v2 source bị từ chối.

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/workflows/test_migrate_plan.py -v`

Expected: FAIL vì planner chưa tồn tại.

- [ ] **Step 3: Cài planner không ghi filesystem**

Planner liệt kê từng hàng trong bảng path v1→v2 ở trên, destination dưới root/revision tương ứng, SHA-256/canonical hash và state map. `rendered` bị loại khỏi v2 và map `awaiting_video_review`. Planner đọc approval record hiện có nhưng chỉ ghi `retain_candidate`; chưa được khẳng định `retained` trước bước equivalence của Task 9. Nếu destination đã tồn tại, plan báo conflict và executor sau này phải từ chối.

- [ ] **Step 4: GREEN, dual-golden và full regression**

Run: `python -m pytest tests/workflows/test_migrate_plan.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS; snapshot xác nhận planner không tạo destination/staging và không sửa source.

- [ ] **Step 5: README và commit**

Cập nhật M1.8 trong `README.md` với state map và semantics của đích sibling.

Commit: `git commit -m "feat: plan non-destructive project migration"`

---

### Task 9: Migration transaction và approval equivalence

**Files:**
- Modify: `src/healthvideo/workflows/migrate.py`
- Create: `tests/workflows/test_migrate_execute.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `migrate_project(source: Path, *, now: datetime, migration_id: UUID) -> Path`.
- `evaluate_approval_equivalence(source: Path, staged_revision: Path) -> ApprovalDisposition`.
- Không có tùy chọn in-place hoặc overwrite.

- [ ] **Step 1: Viết RED tests cho transaction và downgrade gate**

```python
def test_migration_promotes_new_v2_project_without_changing_v1(tmp_path: Path) -> None:
    source = copy_golden_v1(tmp_path)
    before = snapshot_tree(source)
    destination = migrate_project(source, now=FROZEN_NOW, migration_id=FIXED_UUID)
    assert snapshot_tree(source) == before
    assert destination == source.parent / f"{source.name}-v2"
    assert resolve_project_layout(destination).schema_version == "2.0"


@pytest.mark.parametrize(
    ("medical_equal", "video_equal", "render_valid", "expected_state"),
    [
        (False, False, False, "awaiting_medical_review"),
        (True, False, True, "awaiting_video_review"),
        (True, False, False, "medically_approved"),
        (True, True, True, "video_approved"),
    ],
)
def test_migration_never_self_approves_unproven_hashes(
    medical_equal, video_equal, render_valid, expected_state, migration_case
) -> None:
    assert migration_case.result_state == expected_state
```

Thêm failure injection tại copy, asset synthesis, validation và promotion; mọi case phải giữ source byte-identical, không để destination bán phần và dọn đúng staging của migration.

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/workflows/test_migrate_execute.py -v`

Expected: FAIL vì executor/equivalence chưa tồn tại.

- [ ] **Step 3: Cài copy→validate→promote nguyên tử**

Tạo sibling `.<destination-name>.migrate-<uuid>`, copy dữ liệu v1 vào `revisions/001`, chuyển `author-brief.yaml` sang `author/brief.yaml`, tạo `asset-manifest.yaml`, và mặc định mọi evidence highlight v1 là `semantic=true`. Giữ review record dưới revision chỉ khi binding nguồn và binding target tính lại bằng canonical/byte hash khớp chính xác. Validate Pydantic models, active revision, manifest/hash asset và mọi file plan trước `promote_directory_once(staging, destination)`. Không dùng primitive replace có thể ghi đè destination.

Quy tắc state sau equivalence:

- Medical không chứng minh được → `awaiting_medical_review`; không mang approval sang.
- Medical chứng minh được, video không chứng minh được, render hợp lệ → `awaiting_video_review`.
- Medical chứng minh được nhưng render thiếu/hỏng → `medically_approved`.
- Cả hai gate chứng minh được và render hợp lệ → giữ state map tối đa tới `video_approved`; `published_manual` chỉ giữ khi receipt v1 có thể ánh xạ/validate, nếu không hạ về `video_approved`.

- [ ] **Step 4: GREEN, idempotency refusal và dual-golden**

Run: `python -m pytest tests/workflows/test_migrate_execute.py tests/e2e/test_golden_workflow_versions.py -v`

Expected: PASS; gọi lần hai trả `FileExistsError`, không thay source hay destination. Dual-golden chạy trên source v1 và project v2 vừa migrate.

- [ ] **Step 5: Full regression, README và commit**

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `git diff --check`

Expected: PASS. Cập nhật M1.9 trong `README.md`, gồm matrix downgrade approval.

Commit: `git commit -m "feat: migrate v1 projects atomically"`

---

### Task 10: CLI `project migrate` và acceptance M1

**Files:**
- Modify: `src/healthvideo/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- `healthvideo project migrate <project> --dry-run` in file/hash/state/destination plan, không ghi.
- `healthvideo project migrate <project>` tạo sibling v2 mới và in đường dẫn; không có `--in-place`, `--force` hoặc auto approval.

- [ ] **Step 1: Viết RED CLI tests**

```python
def test_project_migrate_dry_run_is_read_only(tmp_path: Path) -> None:
    source = copy_golden_v1(tmp_path)
    before = snapshot_tree(source)
    result = runner.invoke(app, ["project", "migrate", str(source), "--dry-run"])
    assert result.exit_code == 0
    assert "revisions/001" in result.stdout
    assert snapshot_tree(source) == before
    assert not source.with_name(f"{source.name}-v2").exists()


def test_project_migrate_creates_sibling_and_keeps_source(tmp_path: Path) -> None:
    source = copy_golden_v1(tmp_path)
    before = snapshot_tree(source)
    result = runner.invoke(app, ["project", "migrate", str(source)])
    assert result.exit_code == 0
    assert snapshot_tree(source) == before
    assert source.with_name(f"{source.name}-v2").is_dir()
```

- [ ] **Step 2: Chạy RED**

Run: `python -m pytest tests/test_cli.py -k "project_migrate" -v`

Expected: FAIL vì subcommand chưa được nối vào CLI.

- [ ] **Step 3: Cài Typer adapter mỏng**

```python
@project_app.command("migrate")
def migrate_project_command(
    project_dir: ProjectDir,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    if dry_run:
        typer.echo(format_migration_plan(plan_migration(project_dir)))
        return
    destination = migrate_project(
        project_dir,
        now=datetime.now().astimezone(),
        migration_id=uuid4(),
    )
    typer.echo(f"Migrated project: {destination}")
```

Adapter bắt `FileNotFoundError`, `FileExistsError`, validation/integrity errors, in thông báo hành động được và exit 1; không nuốt traceback của lỗi lập trình ngoài danh sách.

- [ ] **Step 4: GREEN và M1 acceptance offline**

Run: `python -m pytest tests/test_cli.py -k "project_migrate or revision_create" -v`

Run: `python -m pytest tests/e2e/test_golden_project.py tests/e2e/test_golden_workflow_versions.py -v`

Run: `python -m pytest -q`

Run: `python -m ruff check src tests tools`

Run: `python tools/export_schemas.py`

Run: `git diff --exit-code -- schemas`

Run: `git diff --check`

Expected: tất cả PASS offline; schema export deterministic; v1 full golden vẫn giữ hành vi cũ; v2 golden chứng minh reader, graph, side states, stage append-only, revision, semantic assets, invalidation và migration.

- [ ] **Step 5: Cập nhật README và commit plan execution**

Đổi milestone M1 thành `complete` chỉ khi toàn bộ acceptance ở Step 4 PASS. Ghi số test thực tế, ngày, các commit M1, lệnh migrate/dry-run, chính sách không in-place và giới hạn “review integration thuộc M2”.

Commit: `git commit -m "feat: expose safe project migration"`

---

## M1 exit criteria

- Kernel v1 giữ nguyên `ORDER` và transition tuyến tính; toàn bộ MVP suite/golden v1 PASS sau từng task.
- Golden v1/v2 tồn tại và chạy song song từ Task 1 đến Task 10.
- Graph v2 biểu diễn đủ main/side transitions, recovery và precondition của §6.
- Revision/stage record đã publish là bất biến; tạo mới không overwrite lịch sử.
- `asset-manifest.yaml` cưỡng chế `semantic` và hash byte; invalidation dùng allowlist metadata chính xác và fail closed.
- `project migrate --dry-run` không ghi; migration thật copy sang sibling staging, validate rồi promote nguyên tử, giữ v1 byte-identical.
- Approval chỉ được giữ khi hash logic tương đương; mọi trường hợp không chứng minh được quay về gate phù hợp và không tự ký lại.
- Test M1 chạy PowerShell/offline, không cần mạng, AI, Scopus hoặc GPU.

## Deferred milestones

- **M2 — Review experience:** Sinh medical/video HTML packet, nối semantic manifest vào gate và hỗ trợ reject/revise có audit trail.
- **M3 — Discovery & evidence:** Intake trend cùng PubMed/Europe PMC/Crossref; Scopus chỉ theo quyết định và phạm vi §17.
- **M4 — Agent routing:** Chuẩn hóa packet, risk routing và contract phối hợp Codex–Claude–Gemini với token ledger.
- **M5 — Vietnamese voice:** Benchmark/adapter VieNeu-TTS, pronunciation/ASR back-check và ElevenLabs fallback.
- **M6 — Visual production:** Chart/SVG, paper highlight, Veo adapter và license ledger truy vết được.
- **M7 — Hardening:** E2E toàn hệ thống, đồng thời đa tiến trình/đa máy, backup, security và tài liệu vận hành.

## Plan review gate

Không bắt đầu Task 1 trước khi bác sĩ duyệt plan này. Việc duyệt plan không đồng nghĩa duyệt y khoa, duyệt video, push hoặc merge; từng hành động đó vẫn theo gate riêng.
