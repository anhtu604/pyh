# Evidence-first Editorial Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-validated orientation phase before author-brief confirmation, without weakening either review gate or manual publication.

**Architecture:** Insert `orientation_research_in_progress` and `awaiting_editorial_direction` after topic selection. Strict, run-scoped orientation records bind source candidates to scope/revision hashes; author confirmation consumes one validated completed record. The existing full evidence workflow re-evaluates sources independently.

**Tech Stack:** Python, Pydantic v2, Typer, PyYAML, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-09-20-evidence-first-editorial-exploration-design.md`

## Global Constraints

- Preserve `PACKAGED = "packaged"`, both review gates, and manual publication.
- Do not fabricate source IDs, medical claims, or doctor opinions.
- Use `pathlib.Path`, atomic writes, and append-only stage records.
- Run focused pytest and Ruff before every task commit; update `README.md` with it.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/healthvideo/domain/project_v2.py` | New main states. |
| `src/healthvideo/domain/orientation.py` | Strict orientation models. |
| `src/healthvideo/domain/state_graph.py` | Edges, artifact labels, side-state policy. |
| `src/healthvideo/workflows/orientation.py` | Research, retry, source binding, completion. |
| `src/healthvideo/workflows/author.py` | New brief-confirmation boundary. |
| `src/healthvideo/workflows/operator.py` | Read-only guidance. |
| `src/healthvideo/commands/operator.py` | Orientation command. |

### Task 1: Add and guard states

**Files:** Modify `src/healthvideo/domain/project_v2.py`, `src/healthvideo/domain/state_graph.py`; test `tests/domain/test_state_graph.py`.

**Interfaces:** `WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS`; `WorkflowState.AWAITING_EDITORIAL_DIRECTION`; graph labels `orientation/scope.yaml`, `orientation/completed/<run_id>.yaml`.

- [ ] **Step 1: Write failing tests**

```python
def test_topic_cannot_skip_orientation() -> None:
    project = ProjectManifestV2(slug="muoi", state=WorkflowState.TOPIC_SELECTED)
    with pytest.raises(TransitionError, match="invalid v2 transition"):
        transition_v2(project, WorkflowState.AUTHOR_BRIEF_READY, valid_context())
```

- [ ] **Step 2: Run** `python -m pytest tests/domain/test_state_graph.py -q`; expect failure because states and edges do not exist.

- [ ] **Step 3: Implement minimum rules**

```python
MAIN_RULES[(WorkflowState.TOPIC_SELECTED, WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS)] = _rule("orientation/scope.yaml")
MAIN_RULES[(WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS, WorkflowState.AWAITING_EDITORIAL_DIRECTION)] = _rule("orientation/completed/<run_id>.yaml")
MAIN_RULES[(WorkflowState.AWAITING_EDITORIAL_DIRECTION, WorkflowState.AUTHOR_BRIEF_READY)] = _rule("orientation/completed/<run_id>.yaml", "author/brief.yaml")
```

Keep `PACKAGED` and downstream rules unchanged. Add explicit `blocked` tests for both new main states.

- [ ] **Step 4: Run** `python -m pytest tests/domain/test_state_graph.py -q; python -m ruff check src tests`; expect pass.
- [ ] **Step 5: Commit** `feat: add orientation workflow states` with state files, tests, and README.

### Task 2: Add strict orientation contracts

**Files:** Create `src/healthvideo/domain/orientation.py`; test `tests/domain/test_orientation.py`.

**Interfaces:** frozen `OrientationScope`, `ProviderOutcome`, `EditorialOption`, `CompletedOrientation`; `CompletedOrientation.validate_candidate_binding(candidates: Sequence[CandidateSource]) -> None`.

- [ ] **Step 1: Write failing tests**

```python
def test_completed_orientation_rejects_unknown_candidate() -> None:
    record = CompletedOrientation(run_id="run-001", topic_input_hash="0" * 64, included_source_ids=["pubmed-9"], options=[valid_option("pubmed-9"), valid_option("pubmed-9")])
    with pytest.raises(ValueError, match="included candidate"):
        record.validate_candidate_binding([])
```

- [ ] **Step 2: Run** `python -m pytest tests/domain/test_orientation.py -q`; expect failure because the module is absent.

- [ ] **Step 3: Implement models**

```python
class EditorialOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    title: str
    framing: str
    context_source_ids: list[str]
    questions_for_doctor: list[str]
```

Require two or three options, unique same-run candidate IDs, source-backed limitations, and forbid fields for doctor decision, recommendation, script, approval, or publication.

- [ ] **Step 4: Run** `python -m pytest tests/domain/test_orientation.py -q; python -m ruff check src tests`; expect pass.
- [ ] **Step 5: Commit** `feat: define validated orientation artifacts` with models, tests, and README.

### Task 3: Build resumable research

**Files:** Create `src/healthvideo/workflows/orientation.py`; test `tests/workflows/test_orientation.py`; modify `src/healthvideo/storage/stages.py` only if its append-only public API is insufficient.

**Interfaces:** `begin_orientation(project_dir: Path, scope: OrientationScope) -> ProjectManifestV2`; `run_orientation_search(project_dir: Path, clients: Sequence[Any], now: datetime) -> OrientationRunResult`; `complete_orientation(project_dir: Path, completed: CompletedOrientation) -> ProjectManifestV2`.

- [ ] **Step 1: Write failing tests**

```python
def test_provider_failure_is_not_zero_results(tmp_path: Path) -> None:
    result = run_orientation_search(project, [FailingClient()], FROZEN_NOW)
    assert result.provider_outcomes[0].status == "failed"
    assert result.manifest.state is WorkflowState.ORIENTATION_RESEARCH_IN_PROGRESS
```

- [ ] **Step 2: Run** `python -m pytest tests/workflows/test_orientation.py -q`; expect failure because the workflow is absent.

- [ ] **Step 3: Implement run records**

Write retryable scope/log/candidate files under `revisions/<active>/orientation/`; write completed content once at `orientation/completed/<run_id>.yaml`; make the latest successful stage record authoritative. Hash canonical topic+scope before starting and completed output before advance. Convert `TypeError`, `ValueError`, and `OSError` into structured provider failures rather than swallowing them.

```python
def complete_orientation(project_dir: Path, completed: CompletedOrientation) -> ProjectManifestV2:
    manifest = _read_manifest(project_dir)
    _validate_completed_orientation(project_dir, manifest, completed)
    write_yaml_once(_completed_path(project_dir, manifest, completed), completed.model_dump(mode="json"))
    return _advance(project_dir, manifest, completed)
```

- [ ] **Step 4: Run** `python -m pytest tests/workflows/test_orientation.py tests/storage/test_stages.py -q; python -m ruff check src tests`; expect pass for retry, partial-output, stale-hash, wrong-revision, duplicate-ID and provider-error cases.
- [ ] **Step 5: Commit** `feat: add resumable orientation research` with workflow, tests, any storage change, and README.

### Task 4: Move doctor-confirmation boundary and expose it

**Files:** Modify `src/healthvideo/workflows/author.py`, `src/healthvideo/workflows/operator.py`, `src/healthvideo/commands/operator.py`; test `tests/workflows/test_author.py`, `tests/workflows/test_operator.py`, `tests/test_cli.py`.

**Interfaces:** `save_author_brief(..., confirm=True)` accepts only `AWAITING_EDITORIAL_DIRECTION`; add `OperatorActionKind.ORIENTATION_RESEARCH`, `OperatorActionKind.AWAIT_EDITORIAL_DIRECTION`, and `healthvideo operator orientation <project> --scope <yaml>`.

- [ ] **Step 1: Write failing tests**

```python
def test_confirming_from_topic_selected_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="awaiting_editorial_direction"):
        save_author_brief(project_at_topic_selected, AuthorBrief(title="Muối"), confirm=True, now=FROZEN_NOW)
```

- [ ] **Step 2: Run** `python -m pytest tests/workflows/test_author.py tests/workflows/test_operator.py tests/test_cli.py -q`; expect failure because the old boundary remains.

- [ ] **Step 3: Implement guarded UI contract**

At `topic_selected`, request research. At `awaiting_editorial_direction`, present verified limits/options and request the doctor’s own words. Require authoritative orientation plus `author/brief.yaml` when confirming. Draft saves do not transition. Decorate the new CLI command with `@project_mutation`; it may not invoke brief confirmation.

- [ ] **Step 4: Run** `python -m pytest tests/workflows/test_author.py tests/workflows/test_operator.py tests/test_cli.py -q; python -m ruff check src tests`; expect pass.
- [ ] **Step 5: Commit** `feat: guide operators through orientation` with files, tests, and README.

### Task 5: Prove compatibility and gates end-to-end

**Files:** Modify `tests/e2e/test_pyh_operator_workflow.py`, `tests/e2e/test_golden_workflow_versions.py`, and `README.md`.

**Interfaces:** v1 stays migration-only; v2 from `author_brief_ready` onward stays unchanged; selected v2 topics require orientation then explicit doctor confirmation.

- [ ] **Step 1: Write failing E2E test**

```python
def test_selected_topic_requires_orientation_then_confirmed_brief(tmp_path: Path) -> None:
    project = create_selected_topic_project(tmp_path)
    complete_valid_orientation(project)
    save_author_brief(project, AuthorBrief(title="Muối"), confirm=True, now=FROZEN)
    assert read_manifest(project).state is WorkflowState.AUTHOR_BRIEF_READY
```

- [ ] **Step 2: Run** `python -m pytest tests/e2e/test_pyh_operator_workflow.py tests/e2e/test_golden_workflow_versions.py -q`; expect failure before integration.

- [ ] **Step 3: Add the smallest v2 fixture and assertions**

Assert no orientation run reaches medical/video approval or publication; assert v1 fixture bytes remain identical; update README with delivered behavior and real results.

- [ ] **Step 4: Run** `python -m pytest -q; python -m ruff check src tests tools; git diff --check`; expect pass.
- [ ] **Step 5: Commit** `test: verify evidence-first editorial workflow` with tests and README.

## Self-review

Tasks 1–2 cover graph and strict artifact contracts. Task 3 separates mutable working files from append-only records and makes provider failure observable. Task 4 preserves doctor authorship. Task 5 proves v1/v2 compatibility, both gates, and manual publication. All interfaces are declared before their consumers.
