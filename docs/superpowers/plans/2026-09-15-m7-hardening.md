# M7 Hardening Implementation Plan

**Trạng thái 17-09-2026:** Task 1–6 hoàn thành; acceptance và C2C review vòng 2 đạt `DONE`.
Các checkbox gốc bên dưới là trình tự thực hiện, còn số đo và commit từng lát nằm
trong bảng tiến độ `README.md`. M7 complete; chỉ đăng video thủ công sau hai cổng duyệt.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project mutations single-writer on supported shared filesystems, add byte-verifiable backup/restore, process-boundary E2E coverage, and deterministic operational security checks.

**Architecture:** A standalone runtime lease guards every mutating CLI workflow without changing project manifests or gates. Immutable directory snapshots carry their own hash manifest and restore only to a new validated destination. Offline audit, filesystem probes, subprocess E2E tests, and an operator runbook make those guarantees executable.

**Tech Stack:** Python 3.11, Pydantic v2, Typer, pathlib, pytest, JSON Schema, PowerShell-compatible subprocess argv.

**Spec:** `docs/superpowers/specs/2026-09-15-m7-hardening-design.md`

## Global Constraints

- Work only in `E:\Protect Your Health\.worktrees\m1-workflow-kernel`; run `git status --short --branch` before each task and preserve unrelated edits.
- Use test-first development. Each task runs its RED test before implementation and commits only after focused tests, Ruff, and `git diff --check` pass.
- Supported concurrency is one shared project directory on a filesystem that passes exclusive-create and same-directory atomic-rename probes.
- TTL never authorizes automatic lease stealing. Foreign-host stale recovery is explicit and preserves the old record.
- Do not change `ProjectManifest`, `ProjectManifestV2`, workflow states, or `GateKind`; exactly two human gates remain.
- Backup/restore never migrates, resigns, refreshes approvals, produces, packages, renders, or publishes.
- Tests are offline and deterministic: no provider, network, browser, GPU, credential, live TTS/render, or publishing.
- Use `pathlib.Path`; do not commit audio, video, render, cache, models, credentials, source-page images, or copyrighted full text.
- Update the README progress table in each implementation commit. Record execution and obtain C2C `DONE` before declaring M7 complete.

---

### Task 1: Lease contract and concurrency-safe storage

**Files:**
- Create: `src/healthvideo/domain/lease.py`
- Create: `src/healthvideo/storage/lease.py`
- Modify: `src/healthvideo/storage/files.py`
- Modify: `src/healthvideo/storage/__init__.py`
- Modify: `tools/export_schemas.py`
- Create: `schemas/project-lease.schema.json`
- Create: `tests/domain/test_lease.py`
- Create: `tests/storage/test_lease.py`
- Modify: `tests/storage/test_files.py`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `.gitignore`
- Modify: `tests/test_gitignore.py`
- Modify: `README.md`

**Interfaces:**
- Produces `ProjectLease`, `LeaseOwner`, `LeaseBusyError`, `LeaseRecoveryError`.
- Produces `acquire_write_lease(project_dir, *, operation, active_revision, owner, now, ttl_seconds) -> WriteLeaseHandle`.
- `WriteLeaseHandle.heartbeat(*, now) -> None` and `.release() -> None` require the same `lease_id`.
- Produces `recover_stale_lease(project_dir, *, requester, process_probe, now, allow_foreign_host) -> Path` returning the preserved stale record.

- [ ] Add RED model tests for closed schema, timezone-aware timestamps, nonblank identity, bounded TTL, and deterministic JSON schema.
- [ ] Add RED storage tests with two synchronized contenders: exactly one acquires; wrong-token heartbeat/release fails; expired lease remains; same-host dead PID + mismatched start fingerprint recovers; live/reused PID and foreign host block; recovery preserves old bytes.
- [ ] Add RED atomic-write tests proving concurrent writers use distinct same-directory temp names, a failed writer removes only its own temp, successful replace has complete bytes, and no owned temp remains.
- [ ] Run `python -m pytest tests/domain/test_lease.py tests/storage/test_lease.py tests/storage/test_files.py tests/contracts/test_schemas.py tests/test_gitignore.py -q` and confirm failures describe missing lease/unique-temp behavior.
- [ ] Implement frozen Pydantic models, exclusive-create acquisition, token-owned heartbeat/release, explicit recovery, unique temp files, file/directory fsync where supported, and runtime ignore rules.
- [ ] Run the focused tests, `python tools/export_schemas.py`, verify only `project-lease.schema.json` is added and existing project schemas are byte-identical, then run Ruff and `git diff --check`.
- [ ] Update README and commit `feat: add project write leases`.

### Task 2: Guard every mutating CLI path and expose recovery UX

**Files:**
- Modify: `src/healthvideo/cli.py`
- Modify: `src/healthvideo/commands/operator.py`
- Modify: `src/healthvideo/workflows/operator.py`
- Create: `src/healthvideo/workflows/operations.py`
- Modify: `.agents/skills/pyh/SKILL.md`
- Modify: `tests/test_cli.py`
- Modify: `tests/workflows/test_operator.py`
- Modify: `tests/contracts/test_pyh_skill.py`
- Create: `tests/e2e/test_concurrent_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces `mutation_lease(project_dir, operation) -> ContextManager[WriteLeaseHandle]` as the only CLI mutation boundary.
- Adds `healthvideo lease inspect <project>` and `healthvideo lease recover <project> [--allow-foreign-host]`.
- `status` reports sanitized owner/operation and remains read-only while busy.

- [ ] Inventory every Typer command and write a parameterized RED contract asserting each mutating command enters `mutation_lease` before workflow mutation; explicitly classify `status`, packet open, doctor, and audit as read-only.
- [ ] Add RED subprocess tests using a barrier: a holder pauses after acquire, a second mutating CLI exits busy with no project diff, status succeeds, and holder failure releases only its own lease.
- [ ] Add RED recovery UX tests for same-host dead owner, live owner, PID reuse, expired foreign host without/with explicit flag, stale-record preservation, sanitized output, and unchanged workflow state.
- [ ] Run the focused CLI/operator/E2E tests and confirm RED.
- [ ] Implement the shared context manager, wrap the complete mutation inventory, add inspect/recover commands, and update `/pyh` instructions with exact commands.
- [ ] Run focused tests twice to expose race flakes, Ruff, and `git diff --check`.
- [ ] Update README and commit `feat: serialize project mutations`.

### Task 3: Immutable backup and fail-closed restore

**Files:**
- Create: `src/healthvideo/domain/backup.py`
- Create: `src/healthvideo/storage/backup.py`
- Create: `src/healthvideo/workflows/backup.py`
- Modify: `src/healthvideo/cli.py`
- Modify: `tools/export_schemas.py`
- Create: `schemas/backup-manifest.schema.json`
- Create: `tests/domain/test_backup.py`
- Create: `tests/storage/test_backup.py`
- Create: `tests/workflows/test_backup.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/contracts/test_schemas.py`
- Modify: `README.md`

**Interfaces:**
- Produces `BackupEntry(path: str, size: int, sha256: str)` and `BackupManifest` schema `1.0`.
- Produces `create_backup(project_dir, backup_root, *, backup_id, now) -> Path` and `restore_backup(snapshot_dir, destination_dir) -> Path`.
- CLI adds `healthvideo backup create` and `healthvideo backup restore`.

- [ ] Add RED domain/schema tests for canonical POSIX ordering, injected id/time, unique normalized paths, size/hash validation, and stable export for v1/v2 snapshots.
- [ ] Add RED create tests for authoritative-file inclusion; runtime/temp/cache/secret/source-fulltext exclusions; referenced forbidden artifact refusal; active-writer refusal; immutable destination; rehash-before-promotion; interrupted copy/promotion.
- [ ] Add RED restore tests for absolute/drive/parent paths, duplicate and case-colliding paths, symlink/junction, missing/extra/tampered entries, existing destination, invalid v1/v2 layout, malformed approval records, and missing artifacts referenced by an approval. Do not reject an intact approval only because its reviewed hash is stale against current project bytes.
- [ ] Add paired RED round-trip tests proving every manifest byte is identical, active revision/state/approval hashes are unchanged, `packaged` stays `packaged`, a current approval remains current, and an intentionally stale but structurally valid approval restores successfully and remains stale.
- [ ] Run focused tests and confirm RED.
- [ ] Implement manifest walking with `Path`, no archive extraction, lease-held snapshot, pre/post-copy verification, new-destination staging and atomic promotion.
- [ ] Export schemas twice; verify only the standalone backup schema changes; run focused tests, Ruff, and `git diff --check`.
- [ ] Update README and commit `feat: add verified project backup restore`.

### Task 4: Process-boundary offline system E2E

**Files:**
- Create: `tests/e2e/test_system_hardening.py`
- Create: `tests/helpers/subprocess_worker.py`
- Modify: `tests/e2e/test_golden_workflow_versions.py` only if a shared fixture must be exposed
- Modify: `README.md`

**Interfaces:**
- Test worker accepts argv plus explicit barrier paths and returns structured JSON; it never imports provider/live runtime configuration.
- E2E exercises public CLI commands and validates project bytes after each contention/recovery boundary.

- [ ] Write RED E2E for a golden v2 path through medical approval, production, video approval, package, backup, restore, and validators; assert hook frame 0, pinned outro/logo PYH, content duration, two approvals, state `packaged`, and no publish call.
- [ ] Write RED multi-process cases for simultaneous writers, killed holder and same-host recovery, foreign-host stale refusal, backup during writer contention, and restore while source project is read-only.
- [ ] Add v1 compatibility assertions for unchanged 45–90-second behavior and no migration; add zero-AI and AI fake-byte coverage without live generation.
- [ ] Replace every timing sleep with an explicit barrier/event and run `python -m pytest tests/e2e/test_system_hardening.py -q` repeatedly until deterministic.
- [ ] Make only minimal fixture/helper corrections required for the public workflow; do not weaken production validation.
- [ ] Run all E2E tests, Ruff, and `git diff --check`.
- [ ] Update README and commit `test: cover M7 process boundaries`.

### Task 5: Security audit, filesystem doctor, and operational runbook

**Files:**
- Create: `src/healthvideo/security.py`
- Modify: `src/healthvideo/workflows/doctor.py`
- Modify: `src/healthvideo/cli.py`
- Create: `tests/test_security.py`
- Modify: `tests/workflows/test_doctor.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_gitignore.py`
- Create: `docs/operations/m7-hardening-runbook.md`
- Modify: `AGENTS.md`
- Modify: `.agents/skills/pyh/SKILL.md`
- Modify: `tests/contracts/test_pyh_skill.py`
- Modify: `README.md`

**Interfaces:**
- Produces `AuditFinding(rule_id, relative_path, reason, remediation)` and `audit_project(project_dir) -> tuple[AuditFinding, ...]`.
- `healthvideo security-audit <project>` prints deterministic sanitized findings and exits nonzero on failure.
- Doctor exposes disposable `exclusive_create` and `atomic_rename` capability results for the project filesystem.

- [ ] Add RED audit tests for tracked/generated media, runtime/cache/model/credential paths, sanitized secret findings, symlink/reparse escape, prohibited publish automation/API imports, exactly two `GateKind` values, package terminal behavior, and backup policy drift.
- [ ] Add RED doctor tests for success, unsupported exclusive create, failed atomic rename, cleanup ownership, and paths containing spaces on PowerShell.
- [ ] Draft the runbook with executable doctor/status/lease/backup/restore/audit commands and failure tables stating what happened, what remains preserved, and the next safe command; add contract tests that every documented command exists.
- [ ] Run focused tests and confirm RED before implementing audit/probes.
- [ ] Implement deterministic offline rules and probes; update AGENTS and `/pyh` only with M7 operational commands and unchanged human-gate rules.
- [ ] Run focused tests, Ruff, the documented audit against disposable fixtures, and `git diff --check`.
- [ ] Update README and commit `feat: add M7 operational security checks`.

### Task 6: Acceptance, repository audit, and C2C closeout

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-15-m7-hardening-design.md` only for verified corrections
- Modify: `docs/superpowers/plans/2026-09-15-m7-hardening.md` only for verified corrections/status

- [ ] Run `python -m pytest -q` and record the measured pass count.
- [ ] Run `python -m ruff check src tests tools`.
- [ ] Run `python tools/export_schemas.py` twice and require a clean schema diff after the first committed export.
- [ ] Run `corepack pnpm --dir video test` and `corepack pnpm --dir video typecheck`.
- [ ] Run the process-boundary E2E repeatedly and `healthvideo security-audit` on disposable v1/v2 fixtures.
- [ ] Run `git diff --check`, inspect `git status --short`, and audit the M7 commit range for tracked audio/video/model/cache/credential/source-fulltext artifacts and publish/provider calls.
- [ ] Verify `GateKind` is exactly `medical | video`, packaged workflows stop at `packaged`, `published_manual` requires the existing human action, and no test used network/provider/browser/GPU.
- [ ] Update README with actual commands/counts and commit `docs: record M7 acceptance`.
- [ ] Record the execution with `C:\Users\anhtu\codex-with-chatgpt\bin\c2c.js`, send `EXECUTED`, address independent review until `DONE`, and commit only review-driven corrections.
- [ ] Declare M7 complete only after clean worktree, all acceptance gates, and C2C `DONE`; do not publish.
