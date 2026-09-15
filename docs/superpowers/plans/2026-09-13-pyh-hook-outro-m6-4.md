# M6.4 Hook-First and Reviewed Outro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not delegate unless the user explicitly requests parallel agents.

**Goal:** Produce v2 videos that open on the authored hook and close on the reviewed PYH outro, with content-sized duration and no change to v1 or either manual gate.

**Architecture:** `Script.format_profile` activates strict M6.4 validation without changing legacy files. Script and storyboard own speech and timing; a declared `FLOURISH` logo and optional decorative mascot supply the final scene. Python validates audio against the final frame before Remotion; Remotion renders `brand_outro` and derives duration from storyboard.

**Tech Stack:** Python 3.11+, Pydantic, Typer, pytest, Ruff, TypeScript, Zod, Remotion, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-13-pyh-hook-outro-m6-4-design.md`

## Global Constraints

- Work only in `E:\Protect Your Health\.worktrees\m1-workflow-kernel`; inspect `git status` before each task and preserve unrelated edits.
- New v2 authoring writes `format_profile=hook_outro_v1`; absent profile remains legacy, without automatic migration.
- The sole standard outro text is: “Nếu mình có gì sai sót, hoặc bạn có bất kỳ câu hỏi nào, hãy để lại phản hồi dưới phần bình luận nhé. Cảm ơn bạn đã xem video.”
- `brand_outro` is the final `Scene.visual` value; no standalone intro, extra TTS, medical gate, video gate, or automatic publishing.
- v2 has no 45–90 second clamp; v1 retains it. Both remain 1080×1920 at 30 fps.
- WAV guard: fail when `30 * audio_duration_ms > 1000 * (final_frame + 1)`; do not retime approved artifacts.
- Logo is declared `AssetKind.FLOURISH`, `semantic=false`, `storyboard_role=brand`; existing `FLOURISH` whiteboards remain valid.
- Do not add M6.5 visual-budget enforcement or M6.6 Veo. Do not commit audio, render, cache, model weights, credentials, full pages, or copyrighted full text.
- Use `pathlib.Path` for internal paths; add README progress in the same commit as each implementation task.

## File ownership map

| Unit | Responsibility | Files |
| --- | --- | --- |
| M6.4 contract | Profile, purpose, scene ID and cross-artifact validation | `src/healthvideo/domain/script.py`, `src/healthvideo/domain/storyboard.py`, new `src/healthvideo/domain/hook_outro.py` |
| Authoring | Insert pinned line and final scene before medical review; idempotent edits | new `src/healthvideo/workflows/hook_outro.py`, `src/healthvideo/cli.py` |
| Declared brand asset | Register exact logo SVG with rights/hash and resolve `brand` role | `src/healthvideo/workflows/visual_assets.py`, `src/healthvideo/domain/asset_manifest.py`, `src/healthvideo/assets.py` |
| Timing and QA | Version-aware render input, WAV overflow guard and `video-qa.json` fields | `src/healthvideo/render/input.py`, `src/healthvideo/workflows/produce.py` |
| Rendering | Zod contract, exact composition duration, final scene and safe asset layout | `video/src/types.ts`, `video/src/Root.tsx`, `video/src/HealthVideo.tsx`, new `video/src/scenes/OutroScene.tsx` |
| Integration | Shared citation binding, review display, package hook behavior, schema and fixture compatibility | new `src/healthvideo/workflows/citations.py`, `src/healthvideo/workflows/gate_review.py`, `src/healthvideo/workflows/review_html.py`, `src/healthvideo/workflows/package.py`, `schemas/`, `README.md` |

---

### Task 1: Profile and script–storyboard contract

**Files:**
- Modify: `src/healthvideo/domain/script.py`, `src/healthvideo/domain/storyboard.py`
- Create: `src/healthvideo/domain/hook_outro.py`
- Test: `tests/domain/test_script.py`, new `tests/domain/test_hook_outro.py`, `tests/contracts/test_schemas.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Script`, `ScriptLine`, `Storyboard`, `Scene`.
- Produces: `OUTRO_TEXT: str`, `validate_hook_outro(script: Script, storyboard: Storyboard, *, require_brand: bool = False) -> None`. Authoring allows a temporarily unbranded final scene; medical gate and production set `require_brand=True`. Legacy artifacts remain unchanged.

- [ ] **Step 1: Write RED contract tests.** Use `tests/helpers.py` fixture data. Assert absent `format_profile` parses as `legacy`; `hook_outro_v1` with no outro, wrong text, repeated/not-last outro, no final `brand_outro`, mismatched `script_line_id`/narration, claim/marker/highlight on outro, or role outside `{brand, mascot}` fails. `require_brand=True` rejects zero or two brand refs, accepts exactly one plus an optional mascot ref. Brand ref with pose and mascot ref without pose fail structurally; kind/semantic/ownership checks wait until Task 3 resolver has the manifest. Assert old v1/v2 fixture bytes are unchanged. Representative test:

```python
script = Script.model_validate({**legacy_script, "format_profile": "hook_outro_v1"})
with pytest.raises(ValueError, match="outro"):
    validate_hook_outro(script, legacy_storyboard)
```

- [ ] **Step 2: Verify RED.** Run `python -m pytest tests/domain/test_hook_outro.py tests/domain/test_script.py -q`; expect missing profile/validator tests to fail.
- [ ] **Step 3: Implement minimal model and pure validator.** Add `format_profile: Literal["legacy", "hook_outro_v1"] = "legacy"`, `purpose: Literal["content", "outro"] = "content"`, `Scene.script_line_id: str | None = None`, `brand_outro` to `Scene.visual`, and `brand` to `VisualAssetRef.role` with no pose. In `validate_hook_outro`, return for `legacy` only when it contains no M6.4-only fields; for `hook_outro_v1`, compare ordered IDs/text, require exactly one pinned final line and one final `brand_outro` scene, and reject medical fields/structurally invalid refs. Manifest kind/semantic/ownership checks belong to Task 3, not this pure validator.

```python
OUTRO_TEXT = (
    "Nếu mình có gì sai sót, hoặc bạn có bất kỳ câu hỏi nào, "
    "hãy để lại phản hồi dưới phần bình luận nhé. Cảm ơn bạn đã xem video."
)

def validate_hook_outro(
    script: Script, storyboard: Storyboard, *, require_brand: bool = False
) -> None:
    if script.format_profile == "legacy":
        if any(line.purpose == "outro" for line in script.lines) or any(
            scene.visual == "brand_outro" for scene in storyboard.scenes
        ):
            raise ValueError("legacy script cannot contain M6.4 outro")
        return
    if len(script.lines) < 2 or len(script.lines) != len(storyboard.scenes):
        raise ValueError("M6.4 script and storyboard must align")
    if [line.purpose for line in script.lines].count("outro") != 1:
        raise ValueError("M6.4 requires one outro")
    if script.lines[-1].purpose != "outro" or script.lines[-1].text != OUTRO_TEXT:
        raise ValueError("M6.4 final outro must match pinned text")
    if storyboard.scenes[0].start_frame != 0 or any(
        scene.visual == "brand_outro" for scene in storyboard.scenes[:-1]
    ):
        raise ValueError("M6.4 hook must start at zero; outro must be last")
    for line, scene in zip(script.lines, storyboard.scenes, strict=True):
        if scene.script_line_id != line.id or scene.narration != line.text:
            raise ValueError("M6.4 line and scene mismatch")
    final = storyboard.scenes[-1]
    if final.visual != "brand_outro" or final.claim_id or final.source_marker:
        raise ValueError("M6.4 final scene must be nonmedical brand_outro")
    if final.evidence_highlight or script.lines[-1].claim_id or script.lines[-1].source_marker:
        raise ValueError("M6.4 outro cannot carry medical evidence")
    if any(ref.role not in {"brand", "mascot"} for ref in final.visual_assets):
        raise ValueError("M6.4 outro has invalid visual role")
    if require_brand and sum(ref.role == "brand" for ref in final.visual_assets) != 1:
        raise ValueError("M6.4 outro requires exactly one declared PYH logo")
```
- [ ] **Step 4: Verify GREEN and schemas.** Run `python -m pytest tests/domain/test_hook_outro.py tests/domain/test_script.py tests/contracts/test_schemas.py -q`, `python tools/export_schemas.py`, then inspect `git diff -- schemas` and `python -m ruff check src tests tools`; expect only additive schema fields/enums.
- [ ] **Step 5: Update README row and commit.** Run `git diff --check`; stage only Task 1 files and README. Commit `feat: define M6.4 script storyboard contract`.

### Task 2: Pre-medical authoring and review binding

**Files:**
- Create: `src/healthvideo/workflows/hook_outro.py`
- Create: `src/healthvideo/workflows/citations.py`
- Modify: `src/healthvideo/cli.py`, `src/healthvideo/workflows/gate_review.py`, `src/healthvideo/workflows/review_html.py`, `src/healthvideo/workflows/package.py`
- Test: new `tests/workflows/test_hook_outro.py`, `tests/workflows/test_gate_review.py`, `tests/workflows/test_review_html.py`, `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `validate_hook_outro`, v2 active revision and existing atomic YAML writes.
- Produces: `author_hook_outro(project_dir: Path, *, duration_frames: int) -> None`; Typer `healthvideo outro author <project> --duration-frames N`; `resolve_citations(script: Script, ledger: Mapping[str, Any], scenes: Sequence[Scene], *, strict_line_ids: bool = False) -> dict[str, list[SourceRecord]]`. The operator retains control of scene timing; the authoring command does not synthesize audio or approve anything.

- [ ] **Step 1: Write RED workflow tests.** From a v2 pre-medical fixture with content script/storyboard, assert one invocation adds `format_profile=hook_outro_v1`, the pinned final `ScriptLine` and contiguous `brand_outro` scene with matching ID/text/duration. Inject interruptions after pending intent, after the first YAML write, and after both writes; retry must converge byte-for-byte. Unexpected operator edits after interruption must refuse without overwrite. Approved revision, non-v2 project, invalid duration or noncontiguous storyboard refuses. The medical gate refuses while pending intent exists; it also refuses zero-logo outro, hook unknown claim, hook claim without marker, hook line/scene marker mismatch, missing claim source, marker without claim, and conflicting marker reuse. A valid source-bound hook reaches normal manual approval once Task 3 has attached its logo; a later content claim without marker remains compatible. Exercise CLI command and medical packet text.
- [ ] **Step 2: Verify RED.** Run `python -m pytest tests/workflows/test_hook_outro.py -q`; expect missing command/function.
- [ ] **Step 3: Implement authoring and a finite recovery protocol.** Use `ProjectManifestV2` active revision; require pre-medical state and no approval file. Compute old script/storyboard hashes and desired payloads/hashes. Atomically write `workflow/pending-hook-outro.yaml` with all four hashes, `duration_frames`, fixed `OUTRO` ID and the exact desired serialized payloads; the intent belongs to the active revision only. Write desired script and storyboard separately with `write_yaml_atomic`, verify their hashes, then remove the exact pending intent. On retry with an intent, allow only old/old, desired/old, old/desired, or desired/desired hash pairs; finish missing writes or clear intent. Any other hash pair refuses as a conflicting operator edit. A clean repeated invocation compares exact desired data and returns without change. Add CLI and medical HTML. At medical gate, refuse pending intent, then call `validate_hook_outro(..., require_brand=True)`, resolve the one declared logo with M6.3 asset resolver, and validate content citations before approval. Keep legacy v2 and v1 paths unchanged.

```python
def append_outro(script: Script, storyboard: Storyboard, duration_frames: int) -> tuple[Script, Storyboard]:
    if duration_frames <= 0 or any(line.id == "OUTRO" for line in script.lines):
        raise ValueError("outro duration or ID conflicts")
    end_frame = storyboard.scenes[-1].start_frame + storyboard.scenes[-1].duration_frames
    line = ScriptLine(id="OUTRO", text=OUTRO_TEXT, purpose="outro", delivery=Delivery(intent="close"))
    scene = Scene(id="OUTRO", start_frame=end_frame, duration_frames=duration_frames,
                  narration=OUTRO_TEXT, script_line_id="OUTRO", visual="brand_outro")
    next_script = script.model_copy(update={"format_profile": "hook_outro_v1", "lines": [*script.lines, line]})
    content_scenes = tuple(
        old.model_copy(update={"script_line_id": spoken.id})
        for spoken, old in zip(script.lines, storyboard.scenes, strict=True)
    )
    next_storyboard = storyboard.model_copy(update={"scenes": (*content_scenes, scene)})
    validate_hook_outro(next_script, next_storyboard, require_brand=False)
    return next_script, next_storyboard
```

The transaction implementation must use four explicit states (`old/old`, `desired/old`, `old/desired`, `desired/desired`) and compare hashes before every write. It may remove only the exact `workflow/pending-hook-outro.yaml` after both desired hashes match. This file is not an approval artifact; a medical approval attempt while it exists always fails. Extract package `_citations` resolution into `workflows/citations.py`, preserving legacy package behavior. In strict M6.4 mode match each scene to `script_line_id` and require line/scene claim and marker equality. A present claim must exist and all its listed sources must exist. A present marker requires a claim and consistent marker-to-source reuse. Specifically the first line/scene (hook) with a claim must also have a marker; later content may retain `claim_id` without `source_marker`. This keeps the hook claim/source/marker-bound without breaking legacy-style later content.
- [ ] **Step 4: Verify GREEN.** Run `python -m pytest tests/workflows/test_hook_outro.py tests/workflows/test_gate_review.py tests/workflows/test_review_html.py tests/workflows/test_package.py tests/test_cli.py -q` and Ruff. Add test that changing final text or timing after medical approval makes approval stale and production refuses. Task 2 medical gate remains closed for M6.4 until Task 3 attaches the required logo.
- [ ] **Step 5: Update README row and commit.** Run `git diff --check`; commit only Task 2 files with `feat: author reviewed PYH outro before medical gate`.

### Task 3: Declared PYH logo and reverse manifest checks

**Files:**
- Modify: `src/healthvideo/domain/asset_manifest.py`, `src/healthvideo/domain/storyboard.py`, `src/healthvideo/assets.py`, `src/healthvideo/workflows/visual_assets.py`
- Test: `tests/domain/test_asset_manifest.py`, `tests/workflows/test_visual_assets.py`, `tests/workflows/test_gate_review.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `render_pyh_logo(brand, variant) -> bytes`, M6.3 `_register_generated_svg`, `referenced_storyboard_assets`.
- Produces: `create_brand_logo_asset(project_dir: Path, *, scene_id: str, asset_name: str, variant: LogoVariant) -> Path`, with `FLOURISH`, `semantic=False`, `storyboard_role="brand"`.

- [ ] **Step 1: Write RED asset tests.** A brand-role ref resolves only a declared decorative `FLOURISH` logo; missing file/hash/rights, role–kind mismatch, orphan owned logo, and wrong scene role refuse. Medical approval refuses zero or two brand refs; exactly one declared logo passes, with optional valid `MASCOT_REACTION`; semantic mascot annotation on outro refuses. Brand ref to whiteboard-owned `FLOURISH` refuses. Existing decorative whiteboard `FLOURISH` remains valid. Verify two same-input registrations converge and a conflicting existing path fails without overwrite.
- [ ] **Step 2: Verify RED.** Run `python -m pytest tests/workflows/test_visual_assets.py -q`; expect brand role/logo API to be missing.
- [ ] **Step 3: Extend the M6.3 registration path.** Add `brand` to `AssetRecord.storyboard_role`; `VisualAssetRef.role` and pose rules were added in Task 1. Add `brand: {AssetKind.FLOURISH}` to resolver, but require record ownership `storyboard_role=brand`, `semantic=false` for a brand ref. For `brand_outro`, optional mascot must resolve to `MASCOT_REACTION`, `semantic=false`, with matching owned role; semantic mascot annotation is rejected. Reuse rights ledger and intent-first asset promotion; register deterministic logo bytes with project-owned creator/license and a truthful classification reason. Require target scene `visual=brand_outro`, `format_profile=hook_outro_v1`, and pre-medical state. Preserve whiteboard `FLOURISH` behavior. The Task 2 medical gate can pass only after this registration supplies its exact one-brand-ref requirement.

```python
def create_brand_logo_asset(
    project_dir: Path, *, scene_id: str, asset_name: str, variant: LogoVariant
) -> Path:
    brand = load_brand_profile(BRAND_PROFILE_PATH)
    return _register_generated_svg(
        project_dir, scene_id=scene_id, asset_name=asset_name,
        svg_bytes=render_pyh_logo(brand, variant), kind=AssetKind.FLOURISH,
        semantic=False, pose=None, source="built_in:pyh-logo",
        creator=brand.assets.creator, license=brand.assets.license,
        rights_basis=brand.assets.license, role="brand",
        classification_reason="Fixed decorative PYH logo geometry.",
    )
```
- [ ] **Step 4: Verify GREEN.** Run `python -m pytest tests/workflows/test_visual_assets.py tests/workflows/test_gate_review.py tests/domain/test_asset_manifest.py -q`, `python tools/export_schemas.py`, inspect schema diff, and Ruff.
- [ ] **Step 5: Update README row and commit.** Run `git diff --check`; commit `feat: register declared PYH logo for outro`.

### Task 4: Version-aware duration and measured WAV guard

**Files:**
- Modify: `src/healthvideo/render/input.py`, `src/healthvideo/workflows/produce.py`
- Test: `tests/render/test_input.py`, `tests/workflows/test_produce.py`, `tests/e2e/test_golden_workflow_versions.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: final storyboard frame `F`, `AudioReport.duration_ms` from `inspect_wav`, and `Script.format_profile`.
- Produces: `build_render_input(storyboard, audio_file, *, duration_policy: Literal["v1", "v2"] = "v1") -> RenderInput`; pure `audio_timing_qa(audio_duration_ms: int, final_frame: int) -> dict[str, int]`. V2 production calls policy `v2`; v1 calls default `v1`.

- [ ] **Step 1: Write RED timing tests.** Check 20s and 140s v2 scenes pass while v1 rejects; both reject zero duration/gap/overlap/path escapes. Test integer audio boundary: `30*A <= 1000*(F+1)` passes and `>` fails. Assert `ceil(1000*F/30)` and tail fields are exact. Ensure TTS receives pinned outro once and renderer is not invoked when WAV exceeds timeline.
- [ ] **Step 2: Verify RED.** Run `python -m pytest tests/render/test_input.py tests/workflows/test_produce.py -q`; expect v2-duration tests to fail.
- [ ] **Step 3: Implement the version boundary and guard.** Preserve legacy default. In `_produce_v2`, validate M6.4 script/storyboard, build input with `duration_policy="v2"`, inspect staged WAV, call `audio_timing_qa` before render, and put the three observations in v2 `video-qa.json`. On overflow raise `ValueError`; staging cleanup leaves project state/reviewed artifacts unchanged. Existing cache identity already includes script/storyboard/provider/asset hashes; validate cached QA fields for M6.4 instead of reusing an old report silently.

```python
def audio_timing_qa(audio_duration_ms: int, final_frame: int) -> dict[str, int]:
    if 30 * audio_duration_ms > 1000 * (final_frame + 1):
        raise ValueError("narration WAV exceeds reviewed storyboard timeline")
    composition_ms = (1000 * final_frame + 29) // 30
    return {
        "audio_duration_ms": audio_duration_ms,
        "composition_duration_ms": composition_ms,
        "trailing_visual_ms": max(0, composition_ms - audio_duration_ms),
    }
```
- [ ] **Step 4: Verify GREEN.** Run `python -m pytest tests/render/test_input.py tests/workflows/test_produce.py tests/e2e/test_golden_workflow_versions.py -q` and Ruff. Verify unchanged v1 output/fixture and retry/cache behavior.
- [ ] **Step 5: Update README row and commit.** Run `git diff --check`; commit `feat: match v2 video duration to reviewed audio timeline`.

### Task 5: Remotion hook-first outro scene and exact duration

**Files:**
- Modify: `video/src/types.ts`, `video/src/Root.tsx`, `video/src/HealthVideo.tsx`, `video/src/components/VisualAsset.tsx`
- Create: `video/src/scenes/OutroScene.tsx`
- Test: `video/src/types.test.ts`, `video/src/HealthVideo.test.tsx`, `video/src/timing.test.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: `RenderInput` containing `Scene.visual="brand_outro"`, declared `visual_assets`, final frame.
- Produces: `durationFromScenes(scenes)` returning exact last end frame; `OutroScene` rendering declared logo and optional mascot with deterministic frame-based motion, without new audio or slogan.

- [ ] **Step 1: Write RED video tests.** Parse new role/visual/`script_line_id`; reject mascot/brand pose misuse. Assert 20s and 140s compositions report exact frames, frame 0 is content hook, last scene dispatches `OutroScene`, asset URLs occur once, and caption area remains unobscured at representative frames. Retain legacy-scene snapshot tests.
- [ ] **Step 2: Verify RED.** Run `pnpm --dir video test`; expect new enum/duration/scene tests to fail.
- [ ] **Step 3: Implement minimal rendering.** Extend Zod enums and local `brand_outro` constraints (profile-to-script linkage remains Python-owned), dispatch `brand_outro` before whiteboard fallback, reuse common declared-asset layer without rendering assets twice, and derive exact end frame for nonempty scenes. Keep finite preview `defaultProps`; `calculateMetadata` uses real end frame. `OutroScene` uses `useCurrentFrame` plus deterministic opacity/translate/scale, with fixed safe areas for caption and brand assets. No network/random/clock/intro sequence.

```tsx
export const durationFromScenes = (scenes: Scene[]): number =>
  Math.max(...scenes.map((scene) => scene.start_frame + scene.duration_frames));

// Inside the existing Sequence; common VisualAsset mapping remains outside.
{scene.visual === 'brand_outro' ? <OutroScene scene={scene} />
  : scene.visual === 'evidence_highlight' ? <EvidenceHighlightScene scene={scene} />
  : <WhiteboardScene scene={scene} />}
```
- [ ] **Step 4: Verify GREEN.** Run `pnpm --dir video test` and `pnpm --dir video typecheck`; inspect one test still at frame 0 and one final frame without committing generated renders. Check v1/v2 render props parse.
- [ ] **Step 5: Update README row and commit.** Run `git diff --check`; commit `feat: render hook-first PYH outro at exact duration`.

### Task 6: End-to-end gates, packet, package, and acceptance

**Files:**
- Modify: `src/healthvideo/workflows/review_html.py`, `src/healthvideo/workflows/package.py`, `README.md`
- Test: `tests/e2e/test_golden_workflow_versions.py`, `tests/workflows/test_gate_review.py`, `tests/workflows/test_review_html.py`, `tests/workflows/test_package.py`
- Modify generated schemas in `schemas/` only when export requires them.

**Interfaces:**
- Consumes: all Task 1–5 contracts.
- Produces: a fixture-backed v2 path from authored hook/outro through both manual gates and package; v1 and legacy v2 remain unchanged.

- [ ] **Step 1: Write RED integration cases.** Use synthetic evidence only. Assert new v2 hook starts at frame 0, final script/scene/asset appear in medical packet, changing reviewed text/timing/manifest invalidates medical approval, rendered video QA carries measured duration fields, video gate remains manual, package caption begins with hook rather than outro, and citations contain only actual claim/source markers. Compare unchanged v1 and legacy v2 fixtures.
- [ ] **Step 2: Verify RED.** Run `python -m pytest tests/e2e/test_golden_workflow_versions.py tests/workflows/test_review_html.py tests/workflows/test_package.py -q`; expect new integration assertions to fail.
- [ ] **Step 3: Complete only missing integration wiring.** Keep packet HTML escaped; show profile/hook/outro/timing/brand provenance. Do not synthesize medical facts or change package publishing behavior. Ensure package never uses outro as upload hook/title and that a missing declared logo blocks before render.

```python
def hook_text(script: Script) -> str:
    if not script.lines or script.lines[0].purpose == "outro":
        raise ValueError("package requires a content hook")
    return script.lines[0].text
```
- [ ] **Step 4: Run acceptance.** `python -m pytest -q`; `python -m ruff check src tests tools`; `python tools/export_schemas.py` then inspect schema diff; `pnpm --dir video test`; `pnpm --dir video typecheck`; `git diff --check`. Verify no generated audio/render/cache/credential is staged.
- [ ] **Step 5: Update README M6.4 to complete only if all checks pass.** Commit Task 6 with `feat: complete reviewed M6.4 hook and outro workflow`, then send the execution record to C2C for independent review. Apply requested fixes and repeat tests/review until `DONE`; do not mark M6.4 finished before that review.
