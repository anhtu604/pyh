# M6.6 Optional Veo Implementation Plan

> **For agentic workers:** Execute task-by-task with test-first development. Do
> not delegate unless the user explicitly requests parallel agents.

**Goal:** Add an explicitly opted-in Veo authoring path whose exact generated
bytes, provenance, evidence classification, and rights are covered by the existing
medical gate, then render and package the approved clip without changing zero-AI,
legacy, gate, or publishing behavior.

**Architecture:** A typed conditional `AIClipProvenance` extends the existing asset
manifest. A provider-neutral authoring workflow calls an injected transport before
medical review, probes the returned MP4, and commits bytes plus manifest, license
ledger, and storyboard through a recoverable intent. Medical review hashes every
referenced clip. Production only stages approved bytes; Remotion renders a muted
declared clip. Packaging emits deterministic manual disclosure guidance.

**Spec:** `docs/superpowers/specs/2026-09-14-optional-veo-m6-6-design.md`

## Global constraints

- Work only in `E:\Protect Your Health\.worktrees\m1-workflow-kernel`; inspect
  Git status before every task and preserve unrelated edits.
- Run RED tests before implementation for each task.
- Live generation requires `--allow-live-generation`; missing opt-in means zero
  token/network calls. CI uses only an injected fake transport and local MP4 fixture.
- Use `veo-3.1-fast-generate-001`, 9:16, 1080p, 24 fps, one 4/6/8-second output.
- Storyboard scene duration is respectively 120/180/240 frames at 30 fps. Reject
  mismatches; do not trim, loop, pad, or alter playback rate.
- Never generate inside production, never infer rights, never add a third gate,
  never auto-publish, and never persist credentials or Google project IDs.
- Preserve M6.4 timing QA, M6.5 budget/cache, zero-AI, legacy v2 and v1 45–90 s.
- Use `pathlib.Path`; do not commit generated audio/video, including test MP4
  fixtures, render/cache/model, credentials, raw provider responses, source-page
  images or copyrighted full text. Tests create disposable bytes under `tmp_path`
  and inject deterministic media-probe metadata.
- Update README in every task commit. Send execution records to C2C and apply
  independent review until `DONE`.

## Task 1: AI clip schema, provenance, ownership, and integrity

**Files**

- Create `src/healthvideo/domain/ai_clip.py`
- Modify `src/healthvideo/domain/asset_manifest.py`
- Modify `src/healthvideo/domain/storyboard.py`
- Modify `src/healthvideo/assets.py`
- Modify `src/healthvideo/domain/license_ledger.py` only if conditional validation
  cannot remain in the manifest/resolver
- Modify schema exports
- Test `tests/domain/test_ai_clip.py`, `tests/domain/test_asset_manifest.py`,
  `tests/domain/test_storyboard.py`, `tests/test_assets.py`,
  `tests/contracts/test_schemas.py`
- Modify `README.md`

**Interfaces**

- `AIClipProvenance` with provider/model/prompt/requested seed/generated time,
  request/output hashes, MIME/container and measured media fields.
- `AssetKind.AI_CLIP`; role `ai_clip` in manifest/storyboard.
- `validate_ai_clip_media_contract(provenance)` for exact allowed tuples.
- `referenced_storyboard_assets()` enforces one-to-one AI ownership and bytes for
  both semantic and decorative clips.

- [ ] RED: conditional provenance required/forbidden; output hash equality;
  rights-required rule; explicit decorative rationale; semantic/decorative scene
  shape; exact 120/180/240 scene durations for enabled M6.5 only; wrong/missing/
  duplicate/orphan role; missing/tampered decorative AI bytes; legacy parses.
- [ ] Run focused tests and confirm RED.
- [ ] Implement frozen models and cross-artifact resolver rules. Do not globally
  byte-validate legacy decorative assets.
- [ ] Export schemas, inspect only intended additive diffs, run focused tests,
  Ruff and `git diff --check`.
- [ ] Update README and commit `feat: define reviewed AI clip assets`.

## Task 2: Veo adapter and recoverable authoring workflow

**Files**

- Create `src/healthvideo/video_ai/__init__.py`
- Create `src/healthvideo/video_ai/base.py`
- Create `src/healthvideo/video_ai/veo.py`
- Create `src/healthvideo/workflows/ai_clips.py`
- Modify `src/healthvideo/workflows/visual_assets.py` only to reuse narrow helpers
- Modify `src/healthvideo/cli.py`
- Test `tests/video_ai/test_veo.py`, `tests/workflows/test_ai_clips.py`,
  `tests/test_cli.py`
- Modify `README.md`

**Interfaces**

- `VeoRequest`, `VeoResult`, `VeoTransport.generate(request)`.
- `GoogleVeoTransport` hides Vertex REST submit/poll/base64 and receives an
  injected short-lived token provider and HTTP callable.
- `generate_ai_clip(project_dir, *, scene_id, prompt, duration_seconds,
  requested_seed, rights, transport, now) -> Path`.
- `recover_ai_clip_generation(project_dir) -> None`.
- CLI group `healthvideo ai-clip generate` creates the live adapter only after
  explicit opt-in and gets tokens through argv, never shell.

- [ ] RED provider tests: canonical request hash; exact request fields; submit and
  polling; timeout/failure/malformed/multiple/empty/base64/MIME responses; token
  absent from errors and persisted data; fake path requires no network. Create
  disposable synthetic bytes under `tmp_path` and inject probe metadata; do not
  track an MP4 fixture.
- [ ] RED workflow tests: valid semantic and decorative registration; pre-medical
  state only; no approval; safe deterministic path; generation failure leaves no
  mutation; probe failure leaves no declared asset; promotion interruption and
  recovery at every boundary; identical retry makes zero provider calls; unrelated
  edits, changed target/request/rights/hash and storyboard-first fail closed.
- [ ] RED CLI: absent `--allow-live-generation` makes zero token/network calls;
  required rights strings; error exit; no project ID/token in tracked artifacts.
- [ ] Implement adapter with stdlib HTTP and safe subprocess argv. Probe with the
  existing FFmpeg/FFprobe environment using argv and parse deterministic JSON.
- [ ] Implement staged bytes and `workflow/pending-ai-clip-generation.yaml` with
  canonical old/desired payload hashes and recoverable promotion.
- [ ] Run focused tests, Ruff and `git diff --check`.
- [ ] Update README and commit `feat: author optional Veo clips safely`.

## Task 3: Medical gate, evidence binding, and review packet

**Files**

- Modify `src/healthvideo/workflows/gate_review.py`
- Modify `src/healthvideo/workflows/review_html.py`
- Modify citation validation only through existing public helpers
- Test `tests/workflows/test_gate_review.py`, `tests/workflows/test_review_html.py`,
  `tests/workflows/test_ai_clips.py`
- Modify `README.md`

- [ ] RED: gate recovers valid pending AI transaction before validation; all
  referenced AI bytes enter `medical_reviewed_paths` even decorative; license
  ledger is present/current; semantic clip requires scene+script claim/marker and
  real citation; decorative requires rationale and no claim/marker; mutation of
  bytes, prompt/provenance, classification, rights or binding makes approval stale.
- [ ] RED: packet escapes and displays classification, provider/model, duration,
  request hash prefix and explicit rights entry without exposing prompt, token or
  cloud project ID. It still creates only the existing medical approval.
- [ ] Run focused tests and confirm RED.
- [ ] Add targeted AI validation and reviewed-path inclusion. Reuse strict citation
  resolution; do not treat provider `source` as medical evidence.
- [ ] Run focused tests, Ruff and `git diff --check`.
- [ ] Update README and commit `feat: bind AI clips to medical review`.

## Task 4: Production staging and muted Remotion rendering

**Files**

- Modify `src/healthvideo/render/input.py`
- Modify `src/healthvideo/workflows/produce.py`
- Modify `video/src/types.ts`, `video/src/HealthVideo.tsx`
- Create `video/src/scenes/AiClipScene.tsx`
- Test `tests/render/test_input.py`, `tests/workflows/test_produce.py`,
  `video/src/types.test.ts`, `video/src/HealthVideo.test.tsx`,
  `video/src/scenes/AiClipScene.test.tsx`
- Export changed schemas
- Modify `README.md`

- [ ] RED: render input carries exactly one AI ref; production includes its hash in
  input identity, stages only that approved file and rejects missing/tampered/wrong
  role/media metadata before TTS/render. Assert provider is never called from
  production and failures make zero TTS/renderer calls with no state change.
- [ ] RED: zero-AI M6.5 cache remains unchanged; AI cache hit/recovery does not
  repeat TTS/render; M6.4 timing and M6.5 visual QA remain authoritative.
- [ ] RED video: Zod exact ownership/duration; AI dispatch never falls through to
  whiteboard; `staticFile()` used once; media component is muted, non-looping and
  has no playback-rate override; generic image overlay excludes `ai_clip`.
- [ ] Run focused Python/video tests and confirm RED.
- [ ] Implement the production path, then remove the M6.5 refusal only after every
  validation is active. Add a narrow `AiClipScene`.
- [ ] Export schemas and inspect diff; run focused tests, video tests/typecheck,
  Ruff and `git diff --check`.
- [ ] Update README and commit `feat: render approved AI clips`.

## Task 5: Disclosure package and dual-path E2E

**Files**

- Modify `src/healthvideo/workflows/package.py`
- Modify `src/healthvideo/workflows/review_html.py` if the video packet needs an
  approved AI summary
- Test `tests/workflows/test_package.py`, `tests/workflows/test_review_html.py`,
  `tests/e2e/test_golden_workflow_versions.py`
- Modify `README.md`

- [ ] RED: approved AI package contains deterministic `ai-disclosure.json`, lists
  scene/path/provider/model/classification, contains manual-label guidance, omits
  full prompt/project/token, and is covered by package manifest hash. Zero-AI and
  legacy packages retain their exact prior payload set.
- [ ] RED E2E: synthetic AI clip authoring through fake transport → medical review
  → production fake renderer → video review → manual package. Verify two and only
  two manual gates; no provider call in production/package; hook frame 0, no intro,
  pinned outro/logo, 30 fps exact content duration, M6.5 budget/QA, muted AI visual
  and no publish API/state transition.
- [ ] Run focused tests and confirm RED.
- [ ] Generate disclosure from approved snapshots and add it conditionally to the
  existing atomic package promotion.
- [ ] Run focused package/E2E tests, Ruff, video regression and typecheck.
- [ ] Update README and commit `feat: package AI disclosure guidance`.

## Task 6: Acceptance, security audit, and C2C closeout

**Files**

- Modify `README.md`
- Modify these design/plan documents only if implementation revealed an approved
  contract correction

- [ ] Inspect every M6.6 commit for any tracked MP4/WAV (including fixtures),
  render/cache/model, token,
  credential, cloud project ID, raw response, source-page image or full text. Remove
  prohibited tracked artifacts without deleting user-owned untracked work.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check src tests tools`.
- [ ] Run `python tools/export_schemas.py`, inspect schema diff, and confirm a
  second export is clean.
- [ ] Run `pnpm --dir video test` and `pnpm --dir video typecheck`.
- [ ] Run `git diff --check` and confirm worktree/branch/commit sequence.
- [ ] Update README M6.6 rows with actual results and commit
  `docs: record M6.6 acceptance`.
- [ ] Record execution with `C:\Users\anhtu\codex-with-chatgpt\bin\c2c.js`, send
  `EXECUTED` to ChatGPT, apply concrete review fixes and resend until `STATE: DONE`.
- [ ] Declare M6.6 complete only after C2C `DONE`; do not publish.
