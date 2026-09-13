# PHY Brand and Mascot M6.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic PHY identity, fixed whiteboard SVG templates, and a three-pose non-clinical mascot that Remotion renders only through declared revision assets.

**Architecture:** A frozen brand profile supplies all visual tokens to pure Python SVG generators. Additive storyboard references point to manifest-declared assets; v2 gate and production preflight validate those references before Remotion receives them. Existing v1 and asset-free v2 scenes retain their current paths.

**Tech Stack:** Python 3.11, Pydantic 2, PyYAML, pytest, TypeScript, React, Remotion, Zod

**Spec:** `docs/superpowers/specs/2026-09-13-pyh-brand-mascot-m6-3-design.md`

## Global Constraints

- The canvas remains exactly 1080 × 1920 at 30 fps.
- Use `#12304A`, `#18A6A6`, `#F4B942`, `#F7F4EC`, and `#263238` through the brand profile, not duplicated production literals.
- Mascot poses are exactly `welcome`, `explain`, and `caution`.
- The mascot wears navy–teal professional outerwear, never a white coat, and has no stethoscope, examination, diagnosis, or prescribing props.
- `mascot_reaction` is always decorative; `mascot_medical_annotation` is always semantic.
- Do not derive medical text, numbers, claims, citations, sources, rights, or doctor statements.
- SVG output contains no script, filter, external reference, embedded raster, `foreignObject`, or embedded font.
- Keep v1, both manual gates, manual publishing, M6.1 charts, and M6.2 highlights compatible.
- Do not implement intro/outro (M6.4), visual-budget enforcement (M6.5), or Veo (M6.6).
- Do not commit generated concept PNGs, audio, models, caches, renders, or credentials.

---

### Task 1: Brand profile contract and PHY logo

**Files:**
- Create: `src/healthvideo/domain/brand.py`
- Create: `src/healthvideo/visuals/brand.py`
- Create: `tests/domain/test_brand.py`
- Create: `tests/visuals/test_brand.py`
- Modify: `profiles/brand.vi.yaml`
- Modify: `tools/export_schemas.py`
- Modify: `tests/contracts/test_schemas.py`
- Create: `schemas/brand.schema.json` through the exporter

**Interfaces:**
- Produces: `BrandProfile`, `BrandColors`, `MascotPose`, `LogoVariant`, `load_brand_profile(path: Path) -> BrandProfile`, and `render_phy_logo(brand: BrandProfile, variant: LogoVariant) -> bytes`.
- Consumes: `read_yaml(Path)` and Pydantic v2 conventions already used by domain models.

- [ ] **Step 1: Write failing brand-profile tests**

```python
def test_checked_in_brand_profile_has_approved_phy_tokens() -> None:
    brand = load_brand_profile(Path("profiles/brand.vi.yaml"))
    assert brand.canvas == BrandCanvas(width=1080, height=1920, fps=30)
    assert brand.colors.model_dump() == {
        "navy": "#12304A",
        "teal": "#18A6A6",
        "yellow": "#F4B942",
        "off_white": "#F7F4EC",
        "charcoal": "#263238",
    }
    assert brand.mascot.poses == (
        MascotPose.WELCOME,
        MascotPose.EXPLAIN,
        MascotPose.CAUTION,
    )


@pytest.mark.parametrize("color", ["12304A", "#xyzxyz", "#12304AFF"])
def test_brand_profile_rejects_non_rgb_hex(color: str) -> None:
    data = valid_brand_data()
    data["colors"]["navy"] = color
    with pytest.raises(ValidationError):
        BrandProfile.model_validate(data)
```

- [ ] **Step 2: Run the brand tests and confirm RED**

Run: `python -m pytest tests/domain/test_brand.py -q`

Expected: FAIL because `healthvideo.domain.brand` does not exist.

- [ ] **Step 3: Implement the frozen profile and update YAML**

Use `ConfigDict(extra="forbid", frozen=True)`, an anchored `^#[0-9A-F]{6}$`
color pattern, literal canvas dimensions, nonblank internal `creator` and `license`,
and an exact ordered tuple of the three poses. Do not add signature dialogue or
intro/outro fields.

- [ ] **Step 4: Add failing deterministic-logo tests**

```python
@pytest.mark.parametrize("variant", list(LogoVariant))
def test_phy_logo_is_safe_and_deterministic(brand: BrandProfile, variant: LogoVariant) -> None:
    first = render_phy_logo(brand, variant)
    assert first == render_phy_logo(brand, variant)
    assert first.endswith(b"\n")
    assert b"<script" not in first
    assert b"<filter" not in first
    assert b"href=" not in first
    assert b"foreignObject" not in first
    assert b"<image" not in first


def test_logo_variants_have_distinct_geometry(brand: BrandProfile) -> None:
    assert len({render_phy_logo(brand, item) for item in LogoVariant}) == 3
```

- [ ] **Step 5: Run logo tests and confirm RED**

Run: `python -m pytest tests/visuals/test_brand.py -q`

Expected: FAIL because `render_phy_logo` is missing.

- [ ] **Step 6: Implement font-free P/H/Y-check geometry**

Construct the wordmark from paths and primitive shapes. Give safe internal IDs
such as `phy-p-bubble`, `phy-h-plus`, and `phy-y-check`; never emit forbidden
motif IDs. Serialize fixed strings in stable order and use only colors read from
`BrandProfile`.

- [ ] **Step 7: Export and test the brand schema**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_brand.py tests/visuals/test_brand.py tests/contracts/test_schemas.py -q`

Expected: PASS.

- [ ] **Step 8: Commit checkpoint A1**

```powershell
git add profiles/brand.vi.yaml schemas/brand.schema.json src/healthvideo/domain/brand.py src/healthvideo/visuals/brand.py tests/domain/test_brand.py tests/visuals/test_brand.py tests/contracts/test_schemas.py tools/export_schemas.py
git commit -m "feat: define the PHY visual identity"
```

---

### Task 2: Deterministic mascot rig and whiteboard templates

**Files:**
- Create: `src/healthvideo/visuals/mascot.py`
- Create: `src/healthvideo/visuals/whiteboard.py`
- Create: `tests/visuals/test_mascot.py`
- Create: `tests/visuals/test_whiteboard.py`
- Modify: `src/healthvideo/visuals/__init__.py`

**Interfaces:**
- Consumes: `BrandProfile` and `MascotPose` from Task 1.
- Produces: `render_mascot(brand: BrandProfile, pose: MascotPose) -> bytes`, `WhiteboardTemplate`, `WhiteboardPayload`, and `render_whiteboard(brand: BrandProfile, template: WhiteboardTemplate, payload: WhiteboardPayload) -> bytes`.

- [ ] **Step 1: Write failing mascot tests**

```python
@pytest.mark.parametrize("pose", list(MascotPose))
def test_mascot_pose_is_safe_and_deterministic(brand: BrandProfile, pose: MascotPose) -> None:
    svg = render_mascot(brand, pose)
    assert svg == render_mascot(brand, pose)
    assert svg.endswith(b"\n")
    assert b"mascot-p-badge" in svg
    assert b"mascot-h-seam" in svg
    assert b"mascot-y-check" in svg
    for forbidden in (b"<script", b"<filter", b"href=", b"foreignObject", b"<image"):
        assert forbidden not in svg


def test_mascot_poses_differ_but_share_the_rig(brand: BrandProfile) -> None:
    outputs = {pose: render_mascot(brand, pose) for pose in MascotPose}
    assert len(set(outputs.values())) == 3
    assert all(b"mascot-short-hair" in svg for svg in outputs.values())
```

Also assert the public function signature has no text, claim, source, marker,
number, or arbitrary SVG parameter and that clinical prop/garment IDs are absent.

- [ ] **Step 2: Run mascot tests and confirm RED**

Run: `python -m pytest tests/visuals/test_mascot.py -q`

Expected: FAIL because the mascot module does not exist.

- [ ] **Step 3: Implement the fixed three-pose rig**

Build a font-free SVG with shared head/body/glasses/outerwear geometry and
pose-specific arm paths. The `explain` arm points toward the content region; the
`caution` hand remains restrained. Use brand tokens only.

- [ ] **Step 4: Write failing whiteboard-template tests**

```python
def test_whiteboard_is_deterministic_and_escapes_operator_text(brand: BrandProfile) -> None:
    payload = WhiteboardPayload(labels=("A < B", "C & D"))
    svg = render_whiteboard(brand, WhiteboardTemplate.COMPARISON, payload)
    assert svg == render_whiteboard(brand, WhiteboardTemplate.COMPARISON, payload)
    assert b"A &lt; B" in svg
    assert b"C &amp; D" in svg
    assert b"<script" not in svg


def test_whiteboard_rejects_payload_shape_for_template(brand: BrandProfile) -> None:
    with pytest.raises(ValueError, match="comparison requires exactly two labels"):
        render_whiteboard(brand, WhiteboardTemplate.COMPARISON, WhiteboardPayload())
```

Cover exactly `connector`, `comparison`, `three_step`, and `callout`. Assert the
generator never adds a number, source marker, or medical label absent from input.

- [ ] **Step 5: Run whiteboard tests and confirm RED**

Run: `python -m pytest tests/visuals/test_whiteboard.py -q`

Expected: FAIL because the whiteboard module does not exist.

- [ ] **Step 6: Implement finite templates**

Validate label counts per template, escape text with XML rules, and reject
control characters. The caller supplies every visible value; the generator only
lays values out. Keep deterministic serialization and safe SVG restrictions.

- [ ] **Step 7: Run checkpoint A tests**

Run: `python -m pytest tests/domain/test_brand.py tests/visuals/test_brand.py tests/visuals/test_mascot.py tests/visuals/test_whiteboard.py -q`

Expected: PASS.

- [ ] **Step 8: Commit checkpoint A2**

```powershell
git add src/healthvideo/visuals tests/visuals
git commit -m "feat: generate fixed PHY visual assets"
```

---

### Task 3: Mascot policy, storyboard references, and declared-asset resolver

**Files:**
- Modify: `src/healthvideo/domain/asset_manifest.py`
- Modify: `src/healthvideo/domain/storyboard.py`
- Modify: `src/healthvideo/render/input.py`
- Modify: `src/healthvideo/assets.py`
- Modify: `tests/domain/test_asset_manifest.py`
- Modify: `tests/render/test_input.py`
- Create or modify: `tests/test_assets.py`
- Modify generated: `schemas/asset-manifest.schema.json`
- Modify generated: `schemas/storyboard.schema.json`
- Modify generated: `schemas/render-input.schema.json`

**Interfaces:**
- Produces: `VisualAssetRole`, `VisualAssetRef(path: str, role: VisualAssetRole, pose: MascotPose | None)`, additive `Scene.visual_assets: tuple[VisualAssetRef, ...] = ()`, and `referenced_storyboard_assets(revision_root: Path, storyboard: Storyboard, manifest: AssetManifest) -> tuple[Path, ...]`.
- Keeps: `referenced_evidence_assets(...)` behavior for existing consumers.

- [ ] **Step 1: Write RED asset-kind policy tests**

```python
def test_mascot_reaction_must_be_decorative() -> None:
    with pytest.raises(ValidationError, match="mascot_reaction.*semantic=false"):
        AssetRecord(**record_data(kind="mascot_reaction", semantic=True))


def test_mascot_annotation_must_be_semantic() -> None:
    with pytest.raises(ValidationError, match="mascot_medical_annotation.*semantic=true"):
        AssetRecord(**record_data(kind="mascot_medical_annotation", semantic=False))
```

- [ ] **Step 2: Implement exact mascot policy**

Add both enum values. Put `MASCOT_MEDICAL_ANNOTATION` in
`SEMANTIC_REQUIRED_KINDS` and `MASCOT_REACTION` in `DECORATIVE_KINDS`. Add an
explicit validator that rejects a semantic reaction; do not weaken current kinds.

- [ ] **Step 3: Write RED `VisualAssetRef` tests**

```python
def test_visual_asset_ref_role_and_pose_are_consistent() -> None:
    mascot = VisualAssetRef(path="assets/guide.svg", role="mascot", pose="welcome")
    assert mascot.pose is MascotPose.WELCOME
    with pytest.raises(ValidationError):
        VisualAssetRef(path="../guide.svg", role="mascot", pose="welcome")
    with pytest.raises(ValidationError, match="whiteboard.*pose"):
        VisualAssetRef(path="assets/board.svg", role="whiteboard", pose="welcome")
```

Also test duplicate paths in one scene and round-trip through `RenderInput`; load
an unchanged legacy fixture and assert `visual_assets == ()`.

- [ ] **Step 4: Implement additive storyboard references**

Reuse the POSIX path rules from render input without accepting backslashes,
absolute roots, drive prefixes, or `..`. The ref model contains no semantic,
claim, source, marker, text, license, or creator fields.

- [ ] **Step 5: Write RED resolver tests**

```python
def test_storyboard_asset_resolver_rejects_undeclared_path(revision: Path) -> None:
    storyboard = storyboard_with_ref("assets/missing.svg", role="mascot", pose="welcome")
    with pytest.raises(ValueError, match="not declared"):
        referenced_storyboard_assets(revision, storyboard, AssetManifest())


def test_storyboard_asset_resolver_rejects_role_kind_mismatch(revision: Path) -> None:
    storyboard, manifest = fixture_ref_and_record(role="mascot", kind="medical_text")
    with pytest.raises(ValueError, match="role.*kind"):
        referenced_storyboard_assets(revision, storyboard, manifest)
```

Cover missing bytes, SHA mismatch, mascot/whiteboard compatibility, and existing
evidence-highlight resolution.

- [ ] **Step 6: Implement the generalized resolver**

Resolve paths inside the revision, require one manifest record, validate all
referenced bytes including decorative assets, and apply this table:

| Role | Allowed kinds |
| --- | --- |
| `mascot` | `mascot_reaction`, `mascot_medical_annotation` |
| `whiteboard` | `background`, `texture`, `flourish`, `transition`, `medical_diagram`, `medical_text` |

Do not infer semantics from SVG contents or vocabulary.

- [ ] **Step 7: Export schemas and run checkpoint B**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_asset_manifest.py tests/render/test_input.py tests/test_assets.py tests/contracts/test_schemas.py -q`

Expected: PASS; legacy fixture behavior remains.

- [ ] **Step 8: Commit checkpoint B**

```powershell
git add src/healthvideo/domain/asset_manifest.py src/healthvideo/domain/storyboard.py src/healthvideo/render/input.py src/healthvideo/assets.py tests/domain/test_asset_manifest.py tests/render/test_input.py tests/test_assets.py schemas
git commit -m "feat: declare storyboard visual assets"
```

---

### Task 4: Crash-safe visual registration and medical-gate consistency

**Files:**
- Modify: `src/healthvideo/workflows/visual_assets.py`
- Modify: `src/healthvideo/workflows/gate_review.py`
- Modify: `tests/workflows/test_visual_assets.py`
- Modify: `tests/workflows/test_gate_review.py`

**Interfaces:**
- Produces: `create_mascot_reaction_asset(...) -> Path`, `create_mascot_annotation_asset(...) -> Path`, `create_whiteboard_asset(...) -> Path`, and an internal `_register_generated_svg(...) -> Path`.
- Consumes: Task 1 profile loader; Task 2 generators; Task 3 asset kinds, visual refs, and resolver.

- [ ] **Step 1: Write RED registration success tests**

```python
def test_create_mascot_reaction_registers_decorative_declared_asset(project_v2: Path) -> None:
    result = create_mascot_reaction_asset(
        project_v2,
        scene_id="S01",
        asset_name="phy-guide-welcome",
        pose=MascotPose.WELCOME,
    )
    manifest = load_asset_manifest(active_revision(project_v2) / "assets/asset-manifest.yaml")
    record = next(item for item in manifest.assets if item.path.endswith("phy-guide-welcome.svg"))
    assert result.is_file()
    assert record.kind is AssetKind.MASCOT_REACTION
    assert record.semantic is False
    assert scene_ref(project_v2, "S01", record.path).pose is MascotPose.WELCOME
    assert load_project(project_v2).state is WorkflowState.DRAFT_READY
```

Add matching tests for semantic mascot annotation and decorative/semantic
whiteboard registration. Semantic inputs must explicitly name their claim,
source, and script marker; invalid mappings must fail before disk writes.

- [ ] **Step 2: Run registration tests and confirm RED**

Run: `python -m pytest tests/workflows/test_visual_assets.py -k "mascot or whiteboard" -q`

Expected: FAIL because the APIs do not exist.

- [ ] **Step 3: Implement small public APIs over one registration helper**

Require v2 pre-medical-review state, no existing approval, a safe public asset
name, and the checked-in brand profile. Write storyboard intent first, stage the
SVG plus updated manifest/rights ledger, verify the staged hash, then promote the
asset directory atomically. Use explicit built-in source, creator, license, and
rights values from the brand profile; never infer rights.

Reaction API accepts no text/claim/source/marker parameter. Annotation API is
separate and validates scene → script → claim → source before generating a
semantic SVG. Do not silently convert one API into the other.

- [ ] **Step 4: Add RED crash/retry tests**

Monkeypatch `replace_directory_atomic` to fail after storyboard intent is
written. Assert medical approval rejects the incomplete reference. Retry with
the same input; assert one storyboard ref, one manifest record, one rights entry,
matching bytes/hash, and unchanged project state. Assert a same-name retry with
different pose, payload, or provenance raises `FileExistsError`.

- [ ] **Step 5: Implement convergent retry**

Before treating an existing path as conflict, compare the requested deterministic
bytes and full provenance. Repair the missing half only when all values match.
Never overwrite different bytes or provenance.

- [ ] **Step 6: Add RED two-way medical-gate tests**

Cover storyboard ref without manifest, semantic mascot record without coherent
scene usage, tampered annotation bytes, and reaction byte tampering. The gate
must hash annotation bytes. It need not hash reaction bytes separately, but
manifest/storyboard YAML remains reviewed and production catches reaction hash
mismatch.

- [ ] **Step 7: Implement generic visual-ref validation in the medical gate**

Run the Task 3 resolver before approval. Keep the existing hardened-highlight
checks. Require scene coherence for generated semantic annotations without
requiring a new gate or state.

- [ ] **Step 8: Run checkpoint C**

Run: `python -m pytest tests/workflows/test_visual_assets.py tests/workflows/test_gate_review.py -q`

Expected: PASS.

- [ ] **Step 9: Commit checkpoint C**

```powershell
git add src/healthvideo/workflows/visual_assets.py src/healthvideo/workflows/gate_review.py tests/workflows/test_visual_assets.py tests/workflows/test_gate_review.py
git commit -m "feat: register review-safe PHY visuals"
```

---

### Task 5: Production preflight and Remotion rendering

**Files:**
- Modify: `src/healthvideo/workflows/produce.py`
- Modify: `tests/workflows/test_produce.py`
- Modify: `video/src/types.ts`
- Modify: `video/src/types.test.ts`
- Create: `video/src/components/VisualAsset.tsx`
- Create: `video/src/components/VisualAsset.test.tsx`
- Modify: `video/src/scenes/WhiteboardScene.tsx`
- Modify: `video/src/scenes/WhiteboardScene.test.tsx`

**Interfaces:**
- Consumes: Task 3 `Scene.visual_assets` and `referenced_storyboard_assets`.
- Produces: Zod-equivalent `VisualAssetRefSchema` and a `VisualAsset` component that renders only `staticFile(ref.path)`.

- [ ] **Step 1: Write RED production-preflight tests**

```python
def test_produce_v2_refuses_undeclared_visual_before_renderer(project_v2: Path) -> None:
    add_storyboard_ref(project_v2, path="assets/not-declared.svg", role="mascot", pose="welcome")
    renderer = RecordingRenderer()
    with pytest.raises(ValueError, match="not declared"):
        produce_v2(project_v2, tts=SilentTTS(), renderer=renderer)
    assert renderer.calls == []


def test_decorative_mascot_bytes_participate_in_production_hash(project_v2: Path) -> None:
    first = production_input_hash(project_v2)
    mutate_declared_mascot_bytes_and_hash(project_v2)
    second = production_input_hash(project_v2)
    assert first != second
```

Also test declared asset staging, wrong hash refusal, and unchanged v1/M6.2
production behavior.

- [ ] **Step 2: Run focused production tests and confirm RED**

Run: `python -m pytest tests/workflows/test_produce.py -k "visual_asset or mascot" -q`

Expected: FAIL because v2 production resolves only evidence highlights.

- [ ] **Step 3: Generalize only the v2 production branch**

Load storyboard and manifest once, run the generalized resolver, include each
referenced asset SHA in the canonical production input hash, and copy only those
validated files into staging. Preserve v1 `_copy_project_assets` and M6.2 paths.

- [ ] **Step 4: Write RED Zod and component tests**

```tsx
it('accepts declared mascot refs and keeps legacy scenes valid', () => {
  expect(SceneSchema.parse(legacyScene).visual_assets).toEqual([]);
  expect(SceneSchema.parse({...legacyScene, visual_assets: [
    {path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'},
  ]}).visual_assets).toHaveLength(1);
});

it('renders the supplied static asset path', () => {
  const markup = renderToStaticMarkup(
    <VisualAsset asset={{path: 'assets/guide.svg', role: 'mascot', pose: 'welcome'}} />,
  );
  expect(markup).toContain('assets/guide.svg');
});
```

Add tests for unsafe paths, role/pose mismatch, all three deterministic placement
styles, and non-overlap with the source-marker and caption safe zones.

- [ ] **Step 5: Run video tests and confirm RED**

Run: `pnpm --dir video test`

Expected: FAIL because Zod and `VisualAsset` do not support the refs.

- [ ] **Step 6: Implement asset-backed rendering with exact legacy fallback**

Mirror Python ref validation in Zod. `VisualAsset` uses only
`<Img src={staticFile(asset.path)}>` plus fixed pose-based boxes and deterministic
frame transforms. It never renders claim text, source markers, or arbitrary
annotations. `WhiteboardScene` uses refs when present and otherwise preserves the
current stroke, narration, marker, and captions exactly.

- [ ] **Step 7: Run checkpoint D**

Run: `python -m pytest tests/workflows/test_produce.py -q`

Run: `pnpm --dir video test`

Run: `pnpm --dir video typecheck`

Expected: PASS.

- [ ] **Step 8: Commit checkpoint D**

```powershell
git add src/healthvideo/workflows/produce.py tests/workflows/test_produce.py video/src
git commit -m "feat: render declared PHY visual assets"
```

---

### Task 6: Documentation, full verification, and independent review

**Files:**
- Modify: `README.md`
- Modify: `.superpowers/sdd/2026-09-12-pyh-operator-experience/progress.md`
- Modify generated schemas only if Task 5 changed their expected output

**Interfaces:**
- Consumes: all Tasks 1–5.
- Produces: documented M6.3 completion and one reviewable implementation diff.

- [ ] **Step 1: Update README and progress ledger**

Record the PHY logo/palette, non-clinical navy–teal mascot, three poses,
decorative reaction versus semantic annotation, declared-only Remotion path, and
the M6.4–M6.6 exclusions. Use measured test counts only after final commands run.

- [ ] **Step 2: Run the full Python suite**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 3: Run Ruff**

Run: `python -m ruff check src tests tools`

Expected: PASS.

- [ ] **Step 4: Export schemas and verify the diff**

Run: `python tools/export_schemas.py`

Run: `git diff --exit-code -- schemas` after staging the intended exported schema changes, or inspect `git diff -- schemas` before staging.

Expected: no unexplained generated changes.

- [ ] **Step 5: Run the full video checks**

Run: `pnpm --dir video test`

Run: `pnpm --dir video typecheck`

Expected: PASS.

- [ ] **Step 6: Run compatibility and whitespace checks**

Run: `python -m pytest tests/e2e/test_golden_project.py tests/workflows/test_produce.py tests/workflows/test_gate_review.py -q`

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 7: Record C2C execution iteration 2**

Write the combined command output to a local temporary file outside Git, then run:

```powershell
node C:\Users\anhtu\codex-with-chatgpt\bin\c2c.js record -w "E:\Protect Your Health\.worktrees\m1-workflow-kernel" --task c2c_9f31 --iteration 2 --changed-files "README.md,.superpowers/sdd/2026-09-12-pyh-operator-experience/progress.md,profiles/brand.vi.yaml,schemas,src,tests,tools/export_schemas.py,video/src" --tests "Full Python, Ruff, schema export/diff, video tests, typecheck, compatibility, and diff check passed" --exit-status ok --command "full M6.3 verification" --output-file "$env:TEMP\pyh-m6-3-c2c.log" --exit-code 0
```

- [ ] **Step 8: Send C2C `STATE: EXECUTED` and wait for review**

Ask ChatGPT to inspect the diff and released execution output. If it returns
`STATE: PLAN`, apply the next iteration, re-run proportionate checks, record it,
and resubmit. Do not commit implementation completion until ChatGPT returns
`STATE: DONE`.

- [ ] **Step 9: Commit M6.3 completion**

```powershell
git add README.md .superpowers/sdd/2026-09-12-pyh-operator-experience/progress.md profiles schemas src tests tools video
git commit -m "feat: add the PHY visual identity and mascot"
```

- [ ] **Step 10: Confirm the worktree is clean**

Run: `git status --short --branch`

Expected: branch header only, with no modified or untracked files.
