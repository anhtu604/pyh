# M8.1 Format Profile + Long-Form Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a 16:9 YouTube long-form video (up to 25 min) chapter by chapter with per-chapter cache, while every existing 9:16 project renders exactly as before.

**Architecture:** A `format_profile` (`vertical_clip` | `youtube_long`) on the storyboard flows into `RenderInput`, which fixes frame size and duration bounds. Remotion reads the size from props and picks a layout table through React context; the vertical table holds today's pixel values unchanged. For `youtube_long`, produce renders each chapter muted with `--frames`, caches the part by content hash, then FFmpeg concatenates parts and muxes the narration once.

**Tech Stack:** Python 3.14 + Pydantic 2 + pytest; Remotion 4.0.522 + React 19 + zod 4 + vitest; FFmpeg ≥ 8.

**Spec:** `docs/superpowers/specs/2026-09-29-n2n-longform-channel-design.md` (§4, §4.1, §12 M8.1)

## Global Constraints

- Hai cổng duyệt giữ nguyên; không tự động xuất bản; không đổi state graph.
- Project/storyboard cũ không có `format_profile` → mặc định `vertical_clip`; mọi test hiện có (973 passed, 3 skipped Python; vitest hiện có) phải vẫn qua không sửa kỳ vọng.
- `youtube_long`: 1920×1080, 30 fps, 60 s ≤ thời lượng ≤ 25 phút (sàn 60 s là cho fixture; mục tiêu 15 phút thuộc outline QA M8.2).
- `vertical_clip`: 1080×1920, 30 fps, 45–90 s với `duration_policy="v1"` như hiện tại.
- Chapter ID khớp `^CH\d{2}$`; mọi cảnh `youtube_long` có `chapter_id`; một chương là dải cảnh liên tục.
- Dùng `pathlib.Path`; lệnh chạy được trong PowerShell; không commit render/cache.
- Mỗi commit cập nhật dòng M8 trong bảng tiến độ `README.md` (CLAUDE.md quy tắc 6).
- Trước mỗi commit: `python -m pytest -q` phần liên quan, `python -m ruff check src tests`, `pnpm --dir video test`, `pnpm --dir video typecheck` khi đụng `video/`.

## File map

| File | Trách nhiệm |
|---|---|
| `src/healthvideo/domain/format_profile.py` (mới) | `FormatProfile`, `FormatSpec`, `FORMAT_SPECS` |
| `src/healthvideo/domain/storyboard.py` | `Scene.chapter_id`, `Storyboard.format_profile`, kiểm tra chương |
| `src/healthvideo/render/input.py` | `RenderInput` theo profile; giới hạn thời lượng theo profile |
| `schemas/*.schema.json` | xuất lại từ Pydantic |
| `video/src/format.ts` (mới) | kích thước theo profile (TS) |
| `video/src/types.ts` | `format_profile`, `chapter_id`, width/height theo profile |
| `video/src/Root.tsx` | kích thước từ props; composition `LongForm` để xem trong Studio |
| `video/src/layout.ts` (mới) | bảng bố cục dọc/ngang + `LayoutContext` |
| `video/src/HealthVideo.tsx`, `components/*`, `scenes/*` | đọc bố cục từ context |
| `src/healthvideo/render/chapters.py` (mới) | tách chương, khóa cache chương, render + ghép |
| `src/healthvideo/render/remotion.py` | `--frames`, `--muted`; argv FFmpeg concat |
| `src/healthvideo/workflows/produce.py` | nhánh `youtube_long` trong `_produce_v2` |
| `.gitignore` | `projects/**/renders-cache/` |

---

### Task 1: Format profile trong domain và RenderInput

**Files:**
- Create: `src/healthvideo/domain/format_profile.py`
- Modify: `src/healthvideo/domain/storyboard.py` (class `Scene` ~dòng 106, class `Storyboard` ~dòng 151)
- Modify: `src/healthvideo/render/input.py`
- Modify: `schemas/storyboard.schema.json`, `schemas/render-input.schema.json` (sinh lại)
- Test: `tests/render/test_format_profile.py`

**Interfaces:**
- Produces: `FormatProfile = Literal["vertical_clip", "youtube_long"]`; `FORMAT_SPECS: dict[str, FormatSpec]` với `FormatSpec(width, height, min_frames, max_frames)`; `Scene.chapter_id: str | None`; `Storyboard.format_profile: FormatProfile`; `RenderInput.format_profile`, `RenderInput.width: Literal[1080, 1920]`, `RenderInput.height: Literal[1920, 1080]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/render/test_format_profile.py
import pytest
from pydantic import ValidationError

from healthvideo.domain.format_profile import FORMAT_SPECS
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.input import RenderInput, build_render_input


def _scene(scene_id: str, start: int, frames: int, chapter: str | None) -> Scene:
    return Scene(
        id=scene_id, start_frame=start, duration_frames=frames,
        narration="Nội dung", visual="whiteboard", chapter_id=chapter,
    )


def _long(*chapters: tuple[str, int]) -> Storyboard:
    scenes, start = [], 0
    for index, (chapter, frames) in enumerate(chapters, start=1):
        scenes.append(_scene(f"S{index:02d}", start, frames, chapter))
        start += frames
    return Storyboard(title="PYH", scenes=tuple(scenes), format_profile="youtube_long")


def test_legacy_storyboard_defaults_to_vertical_clip() -> None:
    board = Storyboard(title="PYH", scenes=(_scene("S01", 0, 1350, None),))
    result = build_render_input(board, "audio/a.wav")
    assert (result.format_profile, result.width, result.height) == ("vertical_clip", 1080, 1920)


def test_youtube_long_is_landscape_and_allows_25_minutes() -> None:
    result = build_render_input(_long(("CH01", 25 * 60 * 30)), "audio/a.wav")
    assert (result.format_profile, result.width, result.height) == ("youtube_long", 1920, 1080)


@pytest.mark.parametrize("frames", [60 * 30 - 1, 25 * 60 * 30 + 1])
def test_youtube_long_enforces_bounds_under_both_policies(frames: int) -> None:
    for policy in ("v1", "v2"):
        with pytest.raises(ValueError, match="total duration"):
            build_render_input(_long(("CH01", frames)), "audio/a.wav", duration_policy=policy)


def test_youtube_long_requires_chapter_on_every_scene() -> None:
    with pytest.raises(ValidationError, match="S02: youtube_long scene requires chapter_id"):
        Storyboard(
            title="PYH", format_profile="youtube_long",
            scenes=(_scene("S01", 0, 900, "CH01"), _scene("S02", 900, 900, None)),
        )


def test_youtube_long_rejects_non_contiguous_chapter() -> None:
    with pytest.raises(ValidationError, match="S03: chapter CH01 must be contiguous"):
        _long(("CH01", 900), ("CH02", 900), ("CH01", 900))


def test_chapter_id_pattern() -> None:
    with pytest.raises(ValidationError):
        _scene("S01", 0, 900, "chapter-1")


def test_render_input_rejects_size_that_mismatches_profile() -> None:
    with pytest.raises(ValidationError, match="youtube_long requires 1920x1080"):
        RenderInput(title="PYH", audio_file="audio/a.wav", format_profile="youtube_long")


def test_specs_match_spec_document() -> None:
    assert FORMAT_SPECS["vertical_clip"].max_frames == 90 * 30
    assert FORMAT_SPECS["youtube_long"].max_frames == 25 * 60 * 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/render/test_format_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'healthvideo.domain.format_profile'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/domain/format_profile.py
"""Publishing targets: frame size and renderer duration bounds per profile."""

from dataclasses import dataclass
from typing import Literal

FormatProfile = Literal["vertical_clip", "youtube_long"]
FPS = 30


@dataclass(frozen=True)
class FormatSpec:
    width: int
    height: int
    min_frames: int
    max_frames: int


FORMAT_SPECS: dict[str, FormatSpec] = {
    "vertical_clip": FormatSpec(1080, 1920, 45 * FPS, 90 * FPS),
    # ponytail: 60 s floor keeps fixtures small; the 15-min editorial target is
    # outline QA (M8.2), not a renderer rule.
    "youtube_long": FormatSpec(1920, 1080, 60 * FPS, 25 * 60 * FPS),
}
```

In `src/healthvideo/domain/storyboard.py`:
- add import `from healthvideo.domain.format_profile import FormatProfile`
- in `class Scene`, after `claim_id`:

```python
    chapter_id: str | None = Field(default=None, pattern=r"^CH\d{2}$")
```

- in `class Storyboard`, after `visual_budget_profile`, add the field and a validator (keep any existing validators):

```python
    format_profile: FormatProfile = "vertical_clip"

    @model_validator(mode="after")
    def validate_chapters(self) -> "Storyboard":
        if self.format_profile != "youtube_long":
            return self
        seen: list[str] = []
        for scene in self.scenes:
            if scene.chapter_id is None:
                raise ValueError(f"Scene {scene.id}: youtube_long scene requires chapter_id")
            if seen and seen[-1] == scene.chapter_id:
                continue
            if scene.chapter_id in seen:
                raise ValueError(
                    f"Scene {scene.id}: chapter {scene.chapter_id} must be contiguous"
                )
            seen.append(scene.chapter_id)
        return self
```

(`model_validator` is already imported in this module for `Scene.validate_scene`.)

In `src/healthvideo/render/input.py`:
- add import `from healthvideo.domain.format_profile import FORMAT_SPECS, FormatProfile`
- keep `MIN_DURATION_FRAMES` / `MAX_DURATION_FRAMES` (tests import them).
- replace the three size fields of `RenderInput` with:

```python
    format_profile: FormatProfile = "vertical_clip"
    width: Literal[1080, 1920] = 1080
    height: Literal[1920, 1080] = 1920
    fps: Literal[30] = FRAMES_PER_SECOND
```

- at the top of `validate_m6_5_chart_refs`, before the scene loop, add:

```python
        spec = FORMAT_SPECS[self.format_profile]
        if (self.width, self.height) != (spec.width, spec.height):
            raise ValueError(
                f"{self.format_profile} requires {spec.width}x{spec.height}"
            )
```

- in `build_render_input`, replace the `if duration_policy == "v1" and not ...` block and the `return RenderInput(...)` with:

```python
    spec = FORMAT_SPECS[storyboard.format_profile]
    bounded = storyboard.format_profile == "youtube_long" or duration_policy == "v1"
    if bounded and not spec.min_frames <= expected_start <= spec.max_frames:
        raise ValueError(
            f"Scene {storyboard.scenes[-1].id}: total duration must be between "
            f"{spec.min_frames} and {spec.max_frames} frames"
        )

    return RenderInput(
        title=storyboard.title,
        audio_file=audio_file,
        scenes=storyboard.scenes,
        visual_budget_profile=storyboard.visual_budget_profile,
        format_profile=storyboard.format_profile,
        width=spec.width,
        height=spec.height,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/render tests/domain -q`
Expected: PASS (new file + all existing render/domain tests)

- [ ] **Step 5: Regenerate schemas and run contract tests**

Run: `python tools/export_schemas.py`
Then: `python -m pytest tests/contracts -q`
Expected: PASS; `git diff --stat schemas` shows only `storyboard.schema.json` and `render-input.schema.json` (plus any schema embedding `Scene`).

- [ ] **Step 6: Full suite + lint, README row, commit**

Run: `python -m pytest -q -p no:cacheprovider` → `973+8 passed, 3 skipped`; `python -m ruff check src tests` → clean.
Add row to `README.md` progress table after the M8 design row:
`| M8.1 Task 1 format profile | format_profile vertical_clip/youtube_long, chapter_id, RenderInput 1920×1080, giới hạn 60 s–25 phút | complete | <pytest count>; Ruff; contracts | \`feat: add format profiles for long-form render\` |`

```bash
git add src/healthvideo/domain/format_profile.py src/healthvideo/domain/storyboard.py src/healthvideo/render/input.py schemas tests/render/test_format_profile.py README.md
git commit -m "feat: add format profiles for long-form render"
```

---

### Task 2: Remotion schema, kích thước từ props và composition LongForm

**Files:**
- Create: `video/src/format.ts`, `video/src/Root.test.ts`
- Modify: `video/src/types.ts` (`SceneSchema` ~dòng 75, `RenderInputSchema` ~dòng 136)
- Modify: `video/src/Root.tsx`

**Interfaces:**
- Consumes: Python `RenderInput` JSON from Task 1 (`format_profile`, `width`, `height`, `scenes[].chapter_id`).
- Produces: `FORMAT_SIZES: Record<FormatProfile, {width: number; height: number}>`; `type FormatProfile = 'vertical_clip' | 'youtube_long'`; `metadataFromProps(props: unknown): {durationInFrames: number; width: number; height: number}`; composition ids `HealthVideo` (render, unchanged id) and `LongForm` (Studio preview).

- [ ] **Step 1: Write the failing test**

```ts
// video/src/Root.test.ts
import {describe, expect, it} from 'vitest';
import {metadataFromProps} from './Root';
import {parseRenderInput} from './types';

const scene = {id: 'S01', start_frame: 0, duration_frames: 1800, narration: 'N',
  visual: 'whiteboard' as const, chapter_id: 'CH01'};

describe('format profile', () => {
  it('keeps legacy input vertical', () => {
    expect(metadataFromProps({title: 'T', audio_file: 'a.wav', scenes: [scene]}))
      .toEqual({durationInFrames: 1800, width: 1080, height: 1920});
  });

  it('renders youtube_long landscape', () => {
    expect(metadataFromProps({title: 'T', audio_file: 'a.wav', scenes: [scene],
      format_profile: 'youtube_long', width: 1920, height: 1080}))
      .toEqual({durationInFrames: 1800, width: 1920, height: 1080});
  });

  it('rejects size that mismatches the profile', () => {
    expect(() => parseRenderInput({title: 'T', audio_file: 'a.wav',
      format_profile: 'youtube_long', width: 1080, height: 1920}))
      .toThrow(/youtube_long requires 1920x1080/);
  });

  it('rejects malformed chapter ids', () => {
    expect(() => parseRenderInput({title: 'T', audio_file: 'a.wav',
      scenes: [{...scene, chapter_id: 'one'}]})).toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir video test -- Root.test.ts`
Expected: FAIL — `metadataFromProps` is not exported

- [ ] **Step 3: Write minimal implementation**

```ts
// video/src/format.ts
export type FormatProfile = 'vertical_clip' | 'youtube_long';

export const FORMAT_SIZES: Record<FormatProfile, {width: number; height: number}> = {
  vertical_clip: {width: 1080, height: 1920},
  youtube_long: {width: 1920, height: 1080},
};
```

In `video/src/types.ts`:
- add `import {FORMAT_SIZES} from './format';`
- in `SceneSchema` object, after `claim_id`: `chapter_id: z.string().regex(/^CH\d{2}$/).nullable().optional(),`
- in `RenderInputSchema`, replace the `width`/`height` lines with:

```ts
  format_profile: z.enum(['vertical_clip', 'youtube_long']).default('vertical_clip'),
  width: z.union([z.literal(1080), z.literal(1920)]).default(1080),
  height: z.union([z.literal(1920), z.literal(1080)]).default(1920),
```

- at the start of its `.superRefine((input, context) => {`, before `if (input.visual_budget_profile !== 'm6_5_v1')`:

```ts
  const size = FORMAT_SIZES[input.format_profile];
  if (input.width !== size.width || input.height !== size.height) {
    context.addIssue({
      code: 'custom',
      path: ['width'],
      message: `${input.format_profile} requires ${size.width}x${size.height}`,
    });
  }
```

In `video/src/Root.tsx`, add after `durationFromScenes`:

```ts
export const metadataFromProps = (props: unknown) => {
  const input = parseRenderInput(props);
  return {durationInFrames: durationFromScenes(input.scenes), width: input.width, height: input.height};
};

const longFormDefaults: RenderInput = {
  ...defaultProps,
  format_profile: 'youtube_long',
  width: 1920,
  height: 1080,
  scenes: [{...defaultProps.scenes[0], duration_frames: 1800, chapter_id: 'CH01'}],
};
```

and replace `RemotionRoot` with:

```tsx
export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="HealthVideo"
      component={HealthVideo}
      defaultProps={defaultProps}
      durationInFrames={MIN_DURATION_IN_FRAMES}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={({props}) => metadataFromProps(props)}
    />
    <Composition
      id="LongForm"
      component={HealthVideo}
      defaultProps={longFormDefaults}
      durationInFrames={1800}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={({props}) => metadataFromProps(props)}
    />
  </>
);
```

Also add `format_profile: 'vertical_clip',` to `defaultProps`.

- [ ] **Step 4: Run tests + typecheck**

Run: `pnpm --dir video test` → all pass; `pnpm --dir video typecheck` → no errors.

- [ ] **Step 5: README row + commit**

Row: `| M8.1 Task 2 Remotion format | Kích thước từ props, composition LongForm cho Studio, chapter_id | complete | vitest; tsc | \`feat: size Remotion compositions from format profile\` |`

```bash
git add video/src/format.ts video/src/types.ts video/src/Root.tsx video/src/Root.test.ts README.md
git commit -m "feat: size Remotion compositions from format profile"
```

---

### Task 3: Bảng bố cục dọc/ngang qua React context

**Files:**
- Create: `video/src/layout.ts`, `video/src/layout.test.ts`
- Modify: `video/src/HealthVideo.tsx`, `video/src/components/Captions.tsx`, `video/src/components/VisualAsset.tsx`, `video/src/scenes/WhiteboardScene.tsx`, `video/src/scenes/ChartScene.tsx`, `video/src/scenes/AiClipScene.tsx`, `video/src/scenes/OutroScene.tsx`, `video/src/scenes/EvidenceHighlightScene.tsx`, `video/src/scenes/highlightGeometry.ts`

**Interfaces:**
- Consumes: `FormatProfile` from Task 2.
- Produces: `type Box`; `type FrameLayout`; `LAYOUTS: Record<FormatProfile, FrameLayout>`; `LayoutContext` (default `LAYOUTS.vertical_clip`); `useLayout(): FrameLayout`; `visualAssetBox(asset, outro = false, layout = LAYOUTS.vertical_clip)`; `highlightImageLayout(highlight, frame = LAYOUTS.vertical_clip.frame)`.

Vertical values below are copied from today's components, so existing vitest cases keep passing without a provider.

- [ ] **Step 1: Write the failing test**

```ts
// video/src/layout.test.ts
import {describe, expect, it} from 'vitest';
import {visualAssetBox} from './components/VisualAsset';
import {LAYOUTS} from './layout';
import type {Box} from './layout';

const inside = (box: Box, frame: {width: number; height: number}) =>
  box.left >= 0 && box.top >= 0 && box.left + box.width <= frame.width && box.top + box.height <= frame.height;

describe('layouts', () => {
  it('vertical table equals the pre-M8 pixel values', () => {
    const v = LAYOUTS.vertical_clip;
    expect(v.frame).toEqual({width: 1080, height: 1920});
    expect(v.captions).toMatchObject({left: 72, bottom: 174, width: 936, height: 136, fontSize: 48, maxWords: 6});
    expect(v.narration).toEqual({left: 96, right: 96, top: 760, fontSize: 72});
    expect(v.assets.standard).toEqual({left: 60, top: 650, width: 570, height: 690});
  });

  it('every landscape box fits in 1920x1080', () => {
    const l = LAYOUTS.youtube_long;
    const boxes = [l.chart.image, ...Object.values(l.assets)];
    boxes.forEach((box) => expect(inside(box, l.frame)).toBe(true));
    expect(l.captions.left + l.captions.width).toBeLessThanOrEqual(1920);
  });

  it('visualAssetBox uses the given layout', () => {
    const asset = {path: 'a.svg', role: 'mascot' as const, pose: 'explain' as const};
    expect(visualAssetBox(asset, false, LAYOUTS.youtube_long)).toEqual(LAYOUTS.youtube_long.assets.explain);
    expect(visualAssetBox(asset)).toEqual(LAYOUTS.vertical_clip.assets.explain);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir video test -- layout.test.ts`
Expected: FAIL — cannot resolve `./layout`

- [ ] **Step 3: Write the layout table**

```ts
// video/src/layout.ts
import {createContext, useContext} from 'react';
import type {FormatProfile} from './format';

export type Box = {left: number; top: number; width: number; height: number};

export type FrameLayout = {
  frame: {width: number; height: number};
  captions: {left: number; bottom: number; width: number; height: number;
    fontSize: number; maxTextWidth: number; rowY: [number, number]; maxWords: number};
  narration: {left: number; right: number; top: number; fontSize: number};
  sourceMarker: {right: number; top: number; fontSize: number};
  whiteboardPath: string;
  chart: {image: Box; narrationBottom: number; narrationFontSize: number; narrationInset: number};
  outroText: {left: number; top: number; width: number; fontSize: number};
  quote: {bottom: number; inset: number; fontSize: number};
  assets: {brand: Box; outroBrand: Box; outroMascot: Box; whiteboard: Box; explain: Box; standard: Box};
};

export const LAYOUTS: Record<FormatProfile, FrameLayout> = {
  vertical_clip: {
    frame: {width: 1080, height: 1920},
    captions: {left: 72, bottom: 174, width: 936, height: 136, fontSize: 48,
      maxTextWidth: 900, rowY: [52, 116], maxWords: 6},
    narration: {left: 96, right: 96, top: 760, fontSize: 72},
    sourceMarker: {right: 72, top: 96, fontSize: 52},
    whiteboardPath: 'M150 570 C 350 400, 650 740, 930 530',
    chart: {image: {left: 70, top: 210, width: 940, height: 1040},
      narrationBottom: 430, narrationFontSize: 58, narrationInset: 84},
    outroText: {left: 90, top: 850, width: 900, fontSize: 54},
    quote: {bottom: 390, inset: 72, fontSize: 46},
    assets: {
      brand: {left: 210, top: 250, width: 660, height: 480},
      outroBrand: {left: 130, top: 250, width: 520, height: 340},
      outroMascot: {left: 650, top: 250, width: 320, height: 360},
      whiteboard: {left: 90, top: 190, width: 900, height: 980},
      explain: {left: 390, top: 650, width: 570, height: 690},
      standard: {left: 60, top: 650, width: 570, height: 690},
    },
  },
  youtube_long: {
    frame: {width: 1920, height: 1080},
    captions: {left: 360, bottom: 60, width: 1200, height: 120, fontSize: 44,
      maxTextWidth: 1160, rowY: [48, 104], maxWords: 10},
    narration: {left: 160, right: 160, top: 380, fontSize: 64},
    sourceMarker: {right: 72, top: 56, fontSize: 44},
    whiteboardPath: 'M260 300 C 620 180, 1180 460, 1660 280',
    chart: {image: {left: 260, top: 90, width: 1400, height: 700},
      narrationBottom: 210, narrationFontSize: 48, narrationInset: 160},
    outroText: {left: 360, top: 420, width: 1200, fontSize: 54},
    quote: {bottom: 200, inset: 160, fontSize: 40},
    assets: {
      brand: {left: 1320, top: 60, width: 520, height: 300},
      outroBrand: {left: 200, top: 200, width: 520, height: 340},
      outroMascot: {left: 1300, top: 200, width: 400, height: 400},
      whiteboard: {left: 460, top: 60, width: 1000, height: 760},
      explain: {left: 1380, top: 180, width: 460, height: 620},
      standard: {left: 80, top: 180, width: 460, height: 620},
    },
  },
};

export const LayoutContext = createContext<FrameLayout>(LAYOUTS.vertical_clip);
export const useLayout = (): FrameLayout => useContext(LayoutContext);
```

- [ ] **Step 4: Wire components to the layout (mechanical replacements)**

`HealthVideo.tsx`: import `{LAYOUTS, LayoutContext}` from `./layout`; destructure `format_profile` from `parseRenderInput(rawInput)`; wrap the returned `<AbsoluteFill>` in `<LayoutContext.Provider value={LAYOUTS[format_profile]}>…</LayoutContext.Provider>`.

`components/VisualAsset.tsx`: replace `visualAssetBox` and read the layout in the component:

```ts
export const visualAssetBox = (
  asset: VisualAssetRef, outro = false, layout: FrameLayout = LAYOUTS.vertical_clip,
): VisualAssetBox => {
  const a = layout.assets;
  if (asset.role === 'brand') return outro ? a.outroBrand : a.brand;
  if (outro && asset.role === 'mascot') return a.outroMascot;
  if (asset.role === 'whiteboard') return a.whiteboard;
  return asset.pose === 'explain' ? a.explain : a.standard;
};
```

and in `VisualAsset`: `const box = visualAssetBox(asset, outro, useLayout());`.

`components/Captions.tsx`: in `Captions`, add `const c = useLayout().captions;`, use `captionRows(words, activeWord, c.maxWords)`; the `<svg>` gets `viewBox={\`0 0 ${c.width} ${c.height}\`}` and style `{bottom: c.bottom, height: c.height, left: c.left, position: 'absolute', width: c.width}` (drop `right`); each `<text>` uses `fontSize={String(c.fontSize)}`, `x={String(c.width / 2)}`, `y={c.rowY[rowIndex === 0 ? 0 : 1]}`, and `captionTextLength(..., c.fontSize, c.maxTextWidth)`. Keep `MAX_CAPTION_WORDS` exported as `6` for existing tests.

`scenes/WhiteboardScene.tsx`: `SourceMarker` reads `const m = useLayout().sourceMarker;` → `fontSize: m.fontSize, right: m.right, top: m.top`. `WhiteboardScene` reads `const layout = useLayout();` → svg `viewBox={\`0 0 ${layout.frame.width} ${layout.frame.height}\`}`, path `d={layout.whiteboardPath}`, narration div `fontSize/left/right/top` from `layout.narration`.

`scenes/ChartScene.tsx`: `const {chart} = useLayout();` → `<Img style={{...chart.image, objectFit: 'contain', position: 'absolute'}}>`; narration div `bottom: chart.narrationBottom, fontSize: chart.narrationFontSize, left: chart.narrationInset, right: chart.narrationInset`.

`scenes/AiClipScene.tsx`: `const {frame} = useLayout();` → style `{height: frame.height, left: 0, objectFit: 'cover', position: 'absolute', top: 0, width: frame.width}`.

`scenes/OutroScene.tsx`: `const t = useLayout().outroText;` → `top: t.top, left: t.left, width: t.width, fontSize: t.fontSize`.

`scenes/highlightGeometry.ts`: delete `FRAME_WIDTH`/`FRAME_HEIGHT`; add param `frame: {width: number; height: number} = {width: 1080, height: 1920}` to `cropImageLayout(pixelWidth, pixelHeight, frame)` and `highlightImageLayout(highlight, frame)`; replace every `FRAME_WIDTH` with `frame.width` and `FRAME_HEIGHT` with `frame.height`; pass `frame` from `highlightImageLayout` into `cropImageLayout`.

`scenes/EvidenceHighlightScene.tsx`: `const layout = useLayout();` → `highlightImageLayout(highlight, layout.frame)`; quote div `bottom: layout.quote.bottom, fontSize: layout.quote.fontSize, left: layout.quote.inset, right: layout.quote.inset`.

- [ ] **Step 5: Run tests + typecheck**

Run: `pnpm --dir video test` → all pass (existing tests unchanged, new `layout.test.ts` passes); `pnpm --dir video typecheck` → clean.

- [ ] **Step 6: Visual check in Studio (manual, 5 min)**

Run: `pnpm --dir video exec remotion studio src/index.ts`
Open composition `LongForm`, scrub frame 0 and 900: narration, whiteboard stroke and captions sit inside the 16:9 frame. Open `HealthVideo`: identical to before.

- [ ] **Step 7: README row + commit**

Row: `| M8.1 Task 3 layout 16:9 | Bảng bố cục dọc/ngang qua LayoutContext; bố cục dọc giữ nguyên giá trị cũ | complete | vitest; tsc; Studio check | \`feat: add landscape layout table for long-form\` |`

```bash
git add video/src README.md
git commit -m "feat: add landscape layout table for long-form"
```

---

### Task 4: Tách chương và khóa cache chương

**Files:**
- Create: `src/healthvideo/render/chapters.py`
- Test: `tests/render/test_chapters.py`

**Interfaces:**
- Consumes: `RenderInput`, `Scene.chapter_id` (Task 1); `canonical_json_hash` from `healthvideo.storage.files`.
- Produces: `ChapterSpan(chapter_id: str, start_frame: int, end_frame: int)` (end exclusive); `chapter_spans(render_input) -> tuple[ChapterSpan, ...]`; `chapter_cache_key(render_input, span, asset_hashes: Mapping[str, str], renderer_identity: Mapping[str, str]) -> str`.

The video part is rendered muted, so its content depends on scenes, assets and renderer only — not on audio. Scene frames are rebased to the chapter start, so lengthening chapter 1 does not invalidate chapter 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/render/test_chapters.py
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.chapters import ChapterSpan, chapter_cache_key, chapter_spans
from healthvideo.render.input import build_render_input

RENDERER = {"name": "remotion", "package_version": "4.0.522", "source_sha256": "x"}


def _input(*chapters: tuple[str, int, str]):
    scenes, start = [], 0
    for index, (chapter, frames, text) in enumerate(chapters, start=1):
        scenes.append(Scene(id=f"S{index:02d}", start_frame=start, duration_frames=frames,
                            narration=text, visual="whiteboard", chapter_id=chapter))
        start += frames
    board = Storyboard(title="PYH", scenes=tuple(scenes), format_profile="youtube_long")
    return build_render_input(board, "audio/narration.wav", duration_policy="v2")


def test_spans_merge_contiguous_scenes() -> None:
    spans = chapter_spans(_input(("CH01", 900, "a"), ("CH01", 900, "b"), ("CH02", 600, "c")))
    assert spans == (ChapterSpan("CH01", 0, 1800), ChapterSpan("CH02", 1800, 2400))


def test_key_ignores_absolute_position_of_chapter() -> None:
    short = _input(("CH01", 900, "a"), ("CH02", 900, "same"))
    longer = _input(("CH01", 1200, "a2"), ("CH02", 900, "same"))
    key = lambda ri: chapter_cache_key(ri, chapter_spans(ri)[1], {}, RENDERER)  # noqa: E731
    assert key(short) == key(longer)


def test_key_changes_with_text_renderer_and_assets() -> None:
    base = _input(("CH01", 1800, "a"))
    span = chapter_spans(base)[0]
    original = chapter_cache_key(base, span, {}, RENDERER)
    edited = _input(("CH01", 1800, "b"))
    assert chapter_cache_key(edited, chapter_spans(edited)[0], {}, RENDERER) != original
    assert chapter_cache_key(base, span, {}, {**RENDERER, "source_sha256": "y"}) != original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/render/test_chapters.py -q`
Expected: FAIL — `No module named 'healthvideo.render.chapters'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/healthvideo/render/chapters.py
"""Chapter spans and content-addressed cache keys for long-form render."""

from collections.abc import Mapping
from dataclasses import dataclass

from healthvideo.render.input import RenderInput
from healthvideo.storage.files import canonical_json_hash


@dataclass(frozen=True)
class ChapterSpan:
    chapter_id: str
    start_frame: int
    end_frame: int  # exclusive


def chapter_spans(render_input: RenderInput) -> tuple[ChapterSpan, ...]:
    spans: list[ChapterSpan] = []
    for scene in render_input.scenes:
        if scene.chapter_id is None:
            raise ValueError(f"Scene {scene.id}: youtube_long scene requires chapter_id")
        end = scene.start_frame + scene.duration_frames
        if spans and spans[-1].chapter_id == scene.chapter_id:
            spans[-1] = ChapterSpan(scene.chapter_id, spans[-1].start_frame, end)
        else:
            spans.append(ChapterSpan(scene.chapter_id, scene.start_frame, end))
    return tuple(spans)


def chapter_cache_key(
    render_input: RenderInput,
    span: ChapterSpan,
    asset_hashes: Mapping[str, str],
    renderer_identity: Mapping[str, str],
) -> str:
    scenes = []
    paths: set[str] = set()
    for scene in render_input.scenes:
        if scene.chapter_id != span.chapter_id:
            continue
        data = scene.model_dump(mode="json")
        data["start_frame"] = scene.start_frame - span.start_frame
        scenes.append(data)
        paths.update(asset.path for asset in scene.visual_assets)
        if scene.evidence_highlight is not None:
            paths.add(scene.evidence_highlight.image)
    return canonical_json_hash(
        {
            "format_profile": render_input.format_profile,
            "fps": render_input.fps,
            "scenes": scenes,
            "assets": {path: asset_hashes.get(path, "") for path in sorted(paths)},
            "renderer": dict(renderer_identity),
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/render/test_chapters.py -q` → 3 passed.

- [ ] **Step 5: Lint, README row, commit**

Row: `| M8.1 Task 4 chapter spans | Tách chương, khóa cache chương không phụ thuộc vị trí tuyệt đối | complete | pytest; Ruff | \`feat: add chapter spans and cache keys\` |`

```bash
git add src/healthvideo/render/chapters.py tests/render/test_chapters.py README.md
git commit -m "feat: add chapter spans and cache keys"
```

---

### Task 5: Render từng chương + ghép FFmpeg

**Files:**
- Modify: `src/healthvideo/render/remotion.py`
- Modify: `src/healthvideo/render/chapters.py`
- Test: `tests/render/test_remotion.py`, `tests/render/test_chapters.py`

**Interfaces:**
- Consumes: Task 4 `chapter_spans`, `chapter_cache_key`.
- Produces: `build_render_argv(render_input, output, public_dir, *, frames: tuple[int, int] | None = None, muted: bool = False) -> list[str]`; `build_concat_argv(concat_list: Path, audio: Path, output: Path) -> list[str]`; `render_long_form(*, render_input_path: Path, render_input: RenderInput, public_dir: Path, audio: Path, output: Path, cache_dir: Path, asset_hashes: Mapping[str, str], renderer_identity: Mapping[str, str], runner: Callable[[list[str]], int]) -> tuple[str, ...]` returning the chapter part file names in order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/render/test_remotion.py`:

```python
from healthvideo.render.remotion import build_concat_argv


def test_render_argv_frame_range_and_muted() -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), Path("."), frames=(900, 1799), muted=True)
    assert "--frames=900-1799" in argv and "--muted" in argv


def test_render_argv_unchanged_without_options() -> None:
    argv = build_render_argv(Path("i.json"), Path("o.mp4"), Path("."))
    assert not any(arg.startswith("--frames") or arg == "--muted" for arg in argv)


def test_concat_argv_copies_video_and_muxes_narration() -> None:
    argv = build_concat_argv(Path("list.txt"), Path("a.wav"), Path("out.mp4"))
    assert argv[0] == "ffmpeg" and ["-c:v", "copy"] == argv[argv.index("-c:v"):argv.index("-c:v") + 2]
    assert ["-map", "0:v", "-map", "1:a"] == argv[argv.index("-map"):argv.index("-map") + 4]
```

Append to `tests/render/test_chapters.py`:

```python
from pathlib import Path

from healthvideo.render.chapters import render_long_form


def _fake_runner(calls: list[list[str]]):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0
    return run


def _render(tmp_path: Path, render_input, calls: list[list[str]]):
    (tmp_path / "ri.json").write_text("{}", encoding="utf-8")
    return render_long_form(
        render_input_path=tmp_path / "ri.json", render_input=render_input,
        public_dir=tmp_path, audio=tmp_path / "a.wav", output=tmp_path / "out" / "video.mp4",
        cache_dir=tmp_path / "cache", asset_hashes={}, renderer_identity=RENDERER,
        runner=_fake_runner(calls),
    )


def test_renders_each_chapter_then_concats(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    parts = _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b")), calls)
    assert [p.split("-")[0] for p in parts] == ["CH01", "CH02"]
    assert "--frames=0-899" in calls[0] and "--frames=900-1799" in calls[1]
    assert calls[2][0] == "ffmpeg" and (tmp_path / "out" / "video.mp4").is_file()
    listing = (tmp_path / "out" / "chapters.txt").read_text(encoding="utf-8")
    assert listing.count("file '") == 2


def test_second_run_reuses_unchanged_chapters(tmp_path: Path) -> None:
    _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b")), [])
    calls: list[list[str]] = []
    _render(tmp_path, _input(("CH01", 900, "a"), ("CH02", 900, "b-edited")), calls)
    rendered = [c for c in calls if c[0] != "ffmpeg"]
    assert len(rendered) == 1 and "--frames=900-1799" in rendered[0]


def test_failed_chapter_raises_and_leaves_no_part(tmp_path: Path) -> None:
    import pytest
    (tmp_path / "ri.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Chapter CH01 render failed"):
        render_long_form(
            render_input_path=tmp_path / "ri.json", render_input=_input(("CH01", 1800, "a")),
            public_dir=tmp_path, audio=tmp_path / "a.wav", output=tmp_path / "video.mp4",
            cache_dir=tmp_path / "cache", asset_hashes={}, renderer_identity=RENDERER,
            runner=lambda argv: 1,
        )
    assert not list((tmp_path / "cache").glob("*.mp4"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/render/test_remotion.py tests/render/test_chapters.py -q`
Expected: FAIL — `build_concat_argv` / `render_long_form` import errors

- [ ] **Step 3: Implement**

In `src/healthvideo/render/remotion.py`, change `build_render_argv` signature and tail:

```python
def build_render_argv(
    render_input: Path,
    output: Path,
    public_dir: Path,
    *,
    frames: tuple[int, int] | None = None,
    muted: bool = False,
) -> list[str]:
    ...  # existing docstring and list unchanged, assigned to `argv`
    if frames is not None:
        argv.append(f"--frames={frames[0]}-{frames[1]}")
    if muted:
        argv.append("--muted")
    return argv


def build_concat_argv(concat_list: Path, audio: Path, output: Path) -> list[str]:
    """Join muted chapter parts losslessly, then mux the reviewed narration once."""
    return [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list.resolve()),
        "-i", str(audio.resolve()),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(output.resolve()),
    ]
```

Append to `src/healthvideo/render/chapters.py` (move the new imports to the top of the module):

```python
from collections.abc import Callable
from pathlib import Path

from healthvideo.render.remotion import build_concat_argv, build_render_argv


def render_long_form(
    *,
    render_input_path: Path,
    render_input: RenderInput,
    public_dir: Path,
    audio: Path,
    output: Path,
    cache_dir: Path,
    asset_hashes: Mapping[str, str],
    renderer_identity: Mapping[str, str],
    runner: Callable[[list[str]], int],
) -> tuple[str, ...]:
    # ponytail: parts are never garbage-collected; delete renders-cache/ by hand
    # if disk matters.
    cache_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for span in chapter_spans(render_input):
        key = chapter_cache_key(render_input, span, asset_hashes, renderer_identity)
        part = cache_dir / f"{span.chapter_id}-{key[:16]}.mp4"
        if not part.is_file():
            staged = cache_dir / f".{part.stem}.partial.mp4"
            argv = build_render_argv(
                render_input_path, staged, public_dir,
                frames=(span.start_frame, span.end_frame - 1), muted=True,
            )
            if runner(argv) != 0 or not staged.is_file():
                staged.unlink(missing_ok=True)
                raise RuntimeError(f"Chapter {span.chapter_id} render failed")
            staged.replace(part)
        parts.append(part)
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_list = output.with_name("chapters.txt")
    concat_list.write_text(
        "".join(f"file '{part.resolve().as_posix()}'\n" for part in parts),
        encoding="utf-8",
    )
    if runner(build_concat_argv(concat_list, audio, output)) != 0 or not output.is_file():
        raise RuntimeError("FFmpeg chapter concat failed")
    return tuple(part.name for part in parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/render -q` → all pass.

- [ ] **Step 5: Lint, README row, commit**

Row: `| M8.1 Task 5 chapter render | Render muted theo --frames, cache chương, FFmpeg concat + mux narration | complete | pytest; Ruff | \`feat: render long-form by chapter with FFmpeg concat\` |`

```bash
git add src/healthvideo/render tests/render README.md
git commit -m "feat: render long-form by chapter with FFmpeg concat"
```

---

### Task 6: Nối vào produce v2 + smoke render thật

**Files:**
- Modify: `src/healthvideo/workflows/produce.py` (block `staged_output = ...` in `_produce_v2`, ~dòng 346–354)
- Modify: `.gitignore`
- Test: `tests/workflows/test_produce_long_form.py`

**Interfaces:**
- Consumes: `render_long_form` (Task 5); fixture helper `create_v2_project_fixture` from `tests/helpers.py`; `approve_gate` from `healthvideo.workflows.gate_review`.
- Produces: constant `CHAPTER_CACHE_DIRECTORY = "renders-cache"` in `produce.py`; v2 manifest key `"chapter_parts"` (list of part names) for `youtube_long` runs only.

- [ ] **Step 1: Write the failing test**

```python
# tests/workflows/test_produce_long_form.py
import json
from datetime import UTC, datetime
from pathlib import Path

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.project_v2 import WorkflowState
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_v2_project_fixture

REVIEWED_AT = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)


def _long_form_project(tmp_path: Path) -> Path:
    project_dir = create_v2_project_fixture(tmp_path, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    path = project_dir / "revisions" / "001" / "storyboard" / "storyboard.yaml"
    board = read_yaml(path)
    board["format_profile"] = "youtube_long"
    board["scenes"][0]["duration_frames"] = 1800
    for scene in board["scenes"]:
        scene["chapter_id"] = "CH01"
    write_yaml_atomic(path, board)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=REVIEWED_AT)
    return project_dir


def test_youtube_long_renders_by_chapter(tmp_path: Path) -> None:
    project_dir = _long_form_project(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0

    output = produce_project(project_dir, SilentTTS(), runner)
    renders = project_dir / "revisions" / "001" / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    render_input = json.loads((renders / "render-input.json").read_text(encoding="utf-8"))

    assert output == renders / "video.mp4" and output.is_file()
    assert (render_input["width"], render_input["height"]) == (1920, 1080)
    assert manifest["chapter_parts"][0].startswith("CH01-")
    assert "--frames=0-1799" in calls[0] and "--muted" in calls[0]
    assert calls[-1][0] == "ffmpeg"
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_video_review"
    assert list((project_dir / "revisions" / "001" / "renders-cache").glob("CH01-*.mp4"))
```

If the fixture storyboard has several scenes, total frames must stay ≥ 1800; the `--frames=0-<last>` assertion then uses the summed length minus one.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/workflows/test_produce_long_form.py -q`
Expected: FAIL — `KeyError: 'chapter_parts'` or no `--frames` in the first call (produce still renders in one pass)

- [ ] **Step 3: Implement the branch**

In `src/healthvideo/workflows/produce.py`:
- add import `from healthvideo.render.chapters import render_long_form`
- add module constant `CHAPTER_CACHE_DIRECTORY = "renders-cache"`
- in `_produce_v2`, replace:

```python
        staged_output = staging_dir / OUTPUT_NAME
        argv = build_render_argv(staged_render_input, staged_output, staging_dir)
        exit_code = runner(argv)
        if exit_code != 0:
            raise RuntimeError(f"Remotion render failed with exit code {exit_code}")
        if not staged_output.is_file():
            raise FileNotFoundError(
                f"Remotion render did not create output: {staged_output}"
            )
```

with:

```python
        staged_output = staging_dir / OUTPUT_NAME
        chapter_parts: tuple[str, ...] = ()
        if render_input.format_profile == "youtube_long":
            chapter_parts = render_long_form(
                render_input_path=staged_render_input,
                render_input=render_input,
                public_dir=staging_dir,
                audio=staged_audio,
                output=staged_output,
                cache_dir=layout.artifact_root / CHAPTER_CACHE_DIRECTORY,
                asset_hashes=asset_hashes,
                renderer_identity=renderer_identity_data,
                runner=runner,
            )
        else:
            argv = build_render_argv(staged_render_input, staged_output, staging_dir)
            exit_code = runner(argv)
            if exit_code != 0:
                raise RuntimeError(f"Remotion render failed with exit code {exit_code}")
            if not staged_output.is_file():
                raise FileNotFoundError(
                    f"Remotion render did not create output: {staged_output}"
                )
```

- in the `V2_RENDER_MANIFEST_NAME` dict right below, add `**({"chapter_parts": list(chapter_parts)} if chapter_parts else {}),` so vertical manifests stay byte-identical.
- If `_validate_v2_staged_run` rejects unknown manifest keys, add `"chapter_parts"` to its allowed optional keys in the same edit.

In `.gitignore`, after `projects/**/renders/`, add `projects/**/renders-cache/`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/workflows/test_produce_long_form.py tests/workflows/test_produce.py -q` → pass.
Run: `python -m pytest -q -p no:cacheprovider` → all pass; `python -m ruff check src tests` → clean.

- [ ] **Step 5: Real smoke render (manual, needs FFmpeg + pnpm)**

Save as `cache/m8-smoke.py` (gitignored) and run `python cache/m8-smoke.py`:

```python
import subprocess
import time
from pathlib import Path

from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.render.chapters import render_long_form
from healthvideo.render.input import build_render_input
from healthvideo.render.remotion import renderer_identity
from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS

root = Path("cache/m8-smoke")
scenes = tuple(
    Scene(id=f"S0{i}", start_frame=(i - 1) * 900, duration_frames=900,
          narration=f"Chương {i}", visual="whiteboard", chapter_id=f"CH0{i}")
    for i in (1, 2)
)
render_input = build_render_input(
    Storyboard(title="Smoke", scenes=scenes, format_profile="youtube_long"), "audio/silence.wav"
)
(root / "audio").mkdir(parents=True, exist_ok=True)
(root / "render-input.json").write_text(render_input.model_dump_json(), encoding="utf-8")
SilentTTS().synthesize(TTSRequest(text="x", language="vi", delivery_beats=()), root / "audio/silence.wav")
started = time.monotonic()
parts = render_long_form(
    render_input_path=root / "render-input.json", render_input=render_input, public_dir=root,
    audio=root / "audio/silence.wav", output=root / "out/video.mp4", cache_dir=root / "parts",
    asset_hashes={}, renderer_identity=renderer_identity(),
    runner=lambda argv: subprocess.run(argv, check=False).returncode,
)
print(parts, f"{time.monotonic() - started:.0f}s")
```

Then: `ffprobe -v error -show_entries stream=codec_type,width,height -show_entries format=duration -of compact cache/m8-smoke/out/video.mp4`

Expected: one video stream 1920×1080, one audio stream, duration ≈ 60 s. Record the printed render time in the README row (spec §4.1 asks to measure). If `SilentTTS` needs other `TTSRequest` fields, copy them from `tests/tts/test_silent.py`.

- [ ] **Step 6: README row + commit**

Update the M8 design row status to `M8.1 complete` and add:
`| M8.1 Task 6 produce long-form | produce v2 render youtube_long theo chương, cache renders-cache/, manifest chapter_parts; smoke 1920×1080 thật | complete | <pytest count>; Ruff; smoke <thời gian render> | \`feat: produce youtube_long by chapter\` |`

```bash
git add src/healthvideo/workflows/produce.py tests/workflows/test_produce_long_form.py .gitignore README.md
git commit -m "feat: produce youtube_long by chapter"
```

---

## Sau M8.1

Các plan tiếp theo, viết khi M8.1 xong: M8.2 outline + clip-plan + `VerticalClip`, M8.3 VoiceStudio, M8.4 board 10 bước, M8.5 Studio props + HyperFrames, M8.6 SEO/thumbnail, M8.7 kênh, M8.8 Antigravity.
