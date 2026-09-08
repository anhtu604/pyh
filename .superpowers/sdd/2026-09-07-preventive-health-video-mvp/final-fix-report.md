# Final review fix report

Date: 2026-09-08

Base: `8e934bf`

Commit: the single commit containing this report, subject `fix: close final production integrity gaps` (exact hash is reported in the task handoff because a commit cannot contain its own hash).

## Outcome

All six Important findings in `final-review-findings.md` are implemented as one coherent fix wave. The medical and video gates remain fail-closed, project media paths are project-confined relative POSIX paths, and subprocess execution remains argv-based with `shell=False`.

## Finding-by-finding changes

1. Windows launcher
   - Added shared subprocess launcher preparation in `src/healthvideo/process.py`.
   - Production resolves a direct `pnpm` executable first and Corepack as fallback.
   - Windows `.cmd`/`.bat` launchers run as an argv list through `%COMSPEC% /d /s /c call`; no `shell=True` is used.
   - Doctor uses the same batch/executable preparation boundary.
   - The CLI reconfigures Windows stdio to UTF-8 so Vietnamese review output does not fail under a CP1252 console.

2. Evidence assets in approvals and cache identity
   - Added `src/healthvideo/assets.py` to resolve storyboard evidence assets safely, reject absolute/traversal/backslash/drive paths and symlink escapes, require files, and hash bytes.
   - Medical review records now include `asset:<relative-path>` SHA-256 bindings.
   - Production input hash and run manifest include evidence asset hashes; staged/cache assets are byte-validated.
   - Replacing an approved evidence asset makes the medical approval stale and, after re-approval, creates a different production cache identity.

3. Packaging time-of-check/time-of-use integrity
   - Packaging captures the current immutable approval records.
   - Ledger, script, and storyboard are read once as snapshots and their canonical hashes are checked against the captured medical approval before caption/source generation.
   - After copying, staged `video.mp4` byte SHA-256 and canonical `render-input.json` hash are checked against the captured video approval before promotion.
   - Regression tests cover staged video/render-input mutation and medical-source mutation during copy.

4. Medical record required by `produce`
   - `ensure_approval_current` now rejects a missing record and returns the validated record.
   - `produce` requires a present, current medical approval before dry-run, cache handling, TTS, or rendering. Fixture helpers create real approvals for `script_approved` and later states.

5. Visible source markers
   - `WhiteboardScene` now renders a consistent high-contrast marker; chart scenes use the same routed component.
   - Added a focused component test and visually checked the marker in a frame extracted from the real golden render.

6. Golden evidence fixture and real render
   - Added `tests/fixtures/golden-project/assets/evidence-r01.svg`, explicitly labelled synthetic and not a real study/claim.
   - Medical approval validates that this referenced fixture exists.
   - Completed a real local Windows CLI production/render using the golden fixture and `SilentTTS`; output stayed outside the worktree in the system temporary directory.

Minor item completed naturally: Python now rejects whitespace-only storyboard `source_marker`, matching JSON Schema and Zod behavior.

## Files

Production:

- `src/healthvideo/assets.py`
- `src/healthvideo/process.py`
- `src/healthvideo/cli.py`
- `src/healthvideo/domain/storyboard.py`
- `src/healthvideo/workflows/doctor.py`
- `src/healthvideo/workflows/package.py`
- `src/healthvideo/workflows/produce.py`
- `src/healthvideo/workflows/review.py`
- `video/src/scenes/WhiteboardScene.tsx`

Tests and fixture:

- `tests/test_process.py`
- `tests/test_cli.py`
- `tests/helpers.py`
- `tests/render/test_input.py`
- `tests/workflows/test_doctor.py`
- `tests/workflows/test_produce.py`
- `tests/workflows/test_review.py`
- `tests/e2e/test_golden_project.py`
- `video/src/scenes/WhiteboardScene.test.tsx`
- `tests/fixtures/golden-project/assets/evidence-r01.svg`

Documentation:

- `README.md`
- `.superpowers/sdd/2026-09-07-preventive-health-video-mvp/final-fix-report.md`

## TDD evidence

Initial focused red run:

```powershell
python -m pytest tests/workflows/test_review.py tests/workflows/test_produce.py tests/e2e/test_golden_project.py -q
python -m pytest tests/test_process.py -q
corepack pnpm --dir video test -- WhiteboardScene.test.tsx
```

Observed: 13 intended Python failures covering missing asset bindings, stale approval, missing/unsafe assets, missing medical approval, asset cache invalidation, and staged package mutation; `healthvideo.process` was absent. The first video command initialized the local Corepack runtime before Vitest output was available, so the marker regression was subsequently mutation-checked explicitly: removing the `WhiteboardScene` marker route produced `1 failed` at `routedMarker?.props.sourceMarker`, restoring it produced `1 passed`.

Focused green run after implementation:

```powershell
python -m pytest tests/workflows/test_review.py tests/workflows/test_produce.py tests/e2e/test_golden_project.py tests/test_process.py tests/workflows/test_doctor.py tests/render/test_input.py tests/test_cli.py -q
python -m ruff check src tests tools
corepack pnpm --dir video test
corepack pnpm --dir video typecheck
```

Observed: `95 passed`; Ruff clean; video `4 files / 12 tests passed`; TypeScript exit 0.

The first real smoke then exposed two integration-only failures: nested quoting around a `.CMD` launcher with a repository path containing spaces, and CP1252 output failing on Vietnamese success text. Minimal reproductions identified the roots. New tests were watched failing, the wrapper was changed to expanded argv after `/c call`, and Windows stdio was configured to UTF-8. Focused re-run: `16 passed`; Ruff clean.

## Final verification

Commands required on the final tree:

```powershell
python -m pytest -v
python -m ruff check src tests tools
pnpm --dir video test
pnpm --dir video typecheck
git diff --check
git status --short
```

Final results are recorded immediately before commit: Python `122 passed`; Ruff `All checks passed!`; Vitest `4 files / 12 tests passed`; TypeScript exit 0; diff check exit 0. Before commit, status contains only the intended files listed above; after commit, status is clean.

Real Windows smoke command sequence (the randomized temp root shown in the result was `C:\Users\anhtu\AppData\Local\Temp\healthvideo-final-golden-smoke-f2474b6964244fed847ac9fd45cef858\golden-project`):

```powershell
Copy-Item tests\fixtures\golden-project <temp>\golden-project -Recurse
python -c "import sys; from pathlib import Path; from healthvideo.storage.files import read_yaml, write_yaml_atomic; p=Path(sys.argv[1]); d=read_yaml(p/'project.yaml'); d['state']='awaiting_medical_review'; write_yaml_atomic(p/'project.yaml', d)" <temp>\golden-project
.\.venv\Scripts\healthvideo.exe review medical <temp>\golden-project --reviewer "BS Smoke" --note "Synthetic golden smoke only" --yes
.\.venv\Scripts\healthvideo.exe produce <temp>\golden-project --tts silent
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of json <rendered-video.mp4>
ffmpeg -v error -ss 24 -i <rendered-video.mp4> -frames:v 1 -y <chart-marker-smoke.png>
```

Observed: review and real Remotion production exit 0; MP4 exists; `width=1080`, `height=1920`, `r_frame_rate=30/1`, `duration=45.056000`. Visual inspection of the extracted chart frame confirms the yellow `[1]` marker at the upper right.

## Self-review

- Approval enforcement precedes dry-run, cache reuse, TTS, and render side effects for valid production states.
- Asset resolution rejects traversal, absolute paths, Windows separators/drive paths, and resolved paths outside the project; missing files cannot be approved.
- Evidence asset bytes participate independently in approval bindings, input hash, run manifest, staging validation, and cache validation.
- Package promotion occurs only after staged output hashes match the captured video approval; generated text uses only medical snapshots validated against the captured approval.
- All subprocess calls remain list/argv based; `.cmd`/`.bat` uses the Windows command processor explicitly with `shell=False`.
- Golden fixture labels are unambiguously synthetic. Generated WAV/render/frame outputs remain untracked outside the worktree.

## Concerns

None blocking. The production smoke uses deterministic silent audio and synthetic evidence by design; it validates the local rendering pipeline, not publishable narration or medical content.
