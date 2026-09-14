# M6.5 Visual Budget QA Implementation Plan

> **For agentic workers:** Execute task-by-task with test-first development. Do
> not delegate unless the user explicitly requests parallel agents.

**Goal:** Enforce deterministic frame-based visual budgets for explicitly enabled
v2 storyboards, render declared chart SVGs, and record recomputable production QA
without changing legacy projects, the two manual gates, or manual publishing.

**Architecture:** A pure domain calculator partitions every reviewed scene into
one primary category. An additive storyboard profile activates exact integer
bounds and an optional reviewed override. The medical gate validates the policy;
production repeats it and stores the report in existing video QA. Remotion only
renders predeclared chart bytes. M6.6 owns AI providers.

**Spec:** `docs/superpowers/specs/2026-09-14-visual-budget-m6-5-design.md`

## Global constraints

- Work only in `E:\Protect Your Health\.worktrees\m1-workflow-kernel`; check Git
  status before every task and preserve unrelated edits.
- Activate only with `Storyboard.visual_budget_profile=m6_5_v1`; absent remains
  `legacy`. Do not infer from hook/outro or assets.
- Count frames by primary visual with integer cross-multiplication. Do not retime,
  synthesize missing visuals or round a display value for validation.
- Override remains inside storyboard and medical hash; no third gate.
- Chart uses one declared semantic `DATA_CHART` SVG; no data/right inference.
- `ai_clip` production fails before TTS/render until M6.6. Do not add Veo/provider,
  network or generated fixtures.
- Preserve M6.4 duration/audio QA, 1080×1920/30 fps, v1, atomic promotion, both
  manual gates and manual publishing.
- Use `pathlib.Path`; never commit audio, render, cache, credentials, model files,
  full source pages or copyrighted full text.
- Update README in each task commit. Send final execution records to C2C and fix
  review findings until `DONE`.

## Task 1: Pure visual-budget contract

**Files**

- Create `src/healthvideo/domain/visual_budget.py`
- Modify `src/healthvideo/domain/storyboard.py`
- Create `tests/domain/test_visual_budget.py`
- Modify `tests/domain/test_storyboard.py`, `tests/contracts/test_schemas.py`
- Export changed schemas; modify `README.md`

**Interfaces**

- `VisualCategory`: `whiteboard_svg | chart_crop | ai_clip`
- `PercentRange(min_percent, max_percent)`
- `VisualBudgetOverride(rationale, whiteboard_svg, chart_crop, ai_clip)`
- `VisualBudgetReport(profile, override_active, total_frames, category_frames,
  category_basis_points, effective_bounds, passed)`
- `classify_scene_visual(visual)`, `calculate_visual_budget(storyboard)`,
  `validate_visual_budget(storyboard)`

- [ ] Write RED tests for legacy bypass; exact default boundaries; one-frame
  failures; every visual mapping; partition equality; no overlay double-count;
  invalid/infeasible bounds; blank rationale; valid override; unknown mapping
  fail closed. Verify old fixture data parses unchanged.
- [ ] Run `python -m pytest tests/domain/test_visual_budget.py
  tests/domain/test_storyboard.py tests/contracts/test_schemas.py -q`; expect RED.
- [ ] Implement frozen additive Pydantic models and pure integer calculator.
  `Storyboard` defaults profile to `legacy`; override is forbidden with legacy.
- [ ] Run the focused tests, `python tools/export_schemas.py`, inspect schema diff,
  Ruff and `git diff --check`.
- [ ] Update README M6.5 contract row and commit
  `feat: define deterministic M6.5 visual budgets`.

## Task 2: Medical gate and review packet binding

**Files**

- Modify `src/healthvideo/workflows/gate_review.py`
- Modify `src/healthvideo/workflows/review_html.py`
- Test `tests/workflows/test_gate_review.py`,
  `tests/workflows/test_review_html.py`
- Modify `README.md`

- [ ] RED: enabled pass/fail; override pass and out-of-override fail; packet shows
  profile, exact frames, effective ranges and escaped rationale; mutation of
  profile/override/timing after approval makes approval stale. Assert one medical
  record only and legacy v2/v1 unchanged.
- [ ] Run focused tests and confirm RED.
- [ ] Call the pure validator before medical approval is written. Render a compact
  budget table/rationale in medical HTML. Reuse storyboard hashing; add no sidecar
  or approval type.
- [ ] Run focused tests and Ruff.
- [ ] Update README and commit `feat: bind M6.5 budget to medical review`.

## Task 3: Declared chart SVG rendering

**Files**

- Modify `src/healthvideo/domain/storyboard.py`,
  `src/healthvideo/domain/asset_manifest.py`, `src/healthvideo/assets.py`
- Modify `src/healthvideo/workflows/visual_assets.py` only as required
- Modify `video/src/types.ts`, `video/src/HealthVideo.tsx`
- Create `video/src/scenes/ChartScene.tsx` if it keeps dispatch/layout narrow
- Test `tests/test_assets.py`, `tests/workflows/test_visual_assets.py`,
  `video/src/types.test.ts`, `video/src/HealthVideo.test.tsx`
- Modify schemas and `README.md`

- [ ] RED: chart scene requires exactly one `role=chart`; resolver accepts only
  `DATA_CHART`, semantic, chart-owned record with valid bytes/right ledger. Missing,
  duplicate, wrong kind/owner/hash/unbound ref fail. Video tests require one SVG
  render and safe marker/caption layout.
- [ ] Run Python and video focused tests; confirm RED.
- [ ] Add `chart` role to both models/resolver and registration ownership. Dispatch
  chart to a component that uses the declared `staticFile` only; never calculate
  chart data in TypeScript.
- [ ] Run focused Python, schema export/diff, video tests/typecheck and Ruff.
- [ ] Update README and commit `feat: render declared M6.1 chart assets`.

## Task 4: Production visual QA and cache integrity

**Files**

- Modify `src/healthvideo/workflows/produce.py`
- Test `tests/workflows/test_produce.py`, `tests/render/test_input.py`
- Modify `README.md`

- [ ] RED: out-of-budget production stops before TTS/renderer; AI clip stops with
  an M6.6 error; pass writes exact `visual_budget` report beside M6.4 timing data;
  awaiting-video-review retry and medically-approved crash recovery reuse cache
  without TTS/render. Tampered frames, basis points, profile, bounds, input or
  changed render input invalidate QA.
- [ ] Run focused tests and confirm RED.
- [ ] Re-run the pure calculation after current medical approval validation and
  before staging. Include report in staged `video-qa.json`. Recompute expected
  report when validating staged/promoted QA, using reviewed storyboard/canonical
  input rather than trusting stored totals.
- [ ] Run focused tests and Ruff; preserve timing QA and current promotion order.
- [ ] Update README and commit `feat: record recomputable M6.5 visual QA`.

## Task 5: Video packet and end-to-end acceptance

**Files**

- Modify `src/healthvideo/workflows/review_html.py`
- Test `tests/workflows/test_review_html.py`,
  `tests/e2e/test_golden_workflow_versions.py`
- Modify `README.md`

- [ ] RED: synthetic enabled v2 path uses a production-supported 75% whiteboard
  and 25% chart/crop allocation with 0% AI. Verify hook at frame 0, outro counted
  as whiteboard, exact duration, chart provenance, manual medical gate, production
  QA, manual video gate and manual package. Video packet shows recomputed report.
  Legacy fixtures stay compatible.
- [ ] Run focused tests and confirm RED.
- [ ] Add only missing packet/integration wiring; keep HTML escaped and package
  behavior unchanged.
- [ ] Run focused Python tests, video tests/typecheck and Ruff.
- [ ] Update README and commit `feat: integrate reviewed M6.5 visual budgets`.

## Task 6: Acceptance and independent review

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check src tests tools`.
- [ ] Run `python tools/export_schemas.py` and inspect schema diff.
- [ ] Run `pnpm --dir video test` and `pnpm --dir video typecheck`.
- [ ] Run `git diff --check`; verify no generated audio, render, cache, credential,
  model, full page or copyrighted text is staged.
- [ ] Update README to complete only after all checks pass; commit acceptance.
- [ ] Record execution with C2C, send `EXECUTED`, address `PLAN` findings and repeat
  until ChatGPT returns `DONE`. Do not mark M6.5 complete earlier.

## Success criteria

The enabled storyboard is partitioned exactly once with deterministic integer
math; valid reviewed overrides change bounds without weakening accounting; chart
SVG bytes are declared and rendered rather than regenerated; AI production fails
closed until M6.6; medical and video gates remain separate/manual; QA and cache are
recomputable; M6.4 and all legacy behavior remain compatible; full acceptance and
C2C independent review pass.
