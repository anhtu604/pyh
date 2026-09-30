# M8.2 Outline + Clip Plan + VerticalClip Implementation Plan

> **For agentic workers:** Từ M8.2, code do Antigravity CLI (`agy`) viết theo brief trong từng task;
> Claude review diff, tự chạy lại kiểm tra, rồi commit. Steps dùng checkbox (`- [ ]`).

**Goal:** Video dài `youtube_long` có `outline.yaml` (5–8 chương) và `clip-plan.yaml` (3–6 clip 9:16)
được bác sĩ duyệt ở Cổng 1; produce render từng clip dọc từ chính các cảnh đã duyệt; clip vào Cổng 2
cùng video dài.

**Architecture:** Hai model mới (`Outline`, `ClipPlan`) nằm trong `script/` của revision. Clip chỉ
tham chiếu ID cảnh có sẵn (dải liên tục + hook/outro tùy chọn), `extra="forbid"` nên không chứa được
lời mới → không thể thêm claim mới. Ledger có thêm `caveat_claim_ids`: claim nào có câu giới hạn thì
clip chứa claim đó phải chứa cảnh mang claim giới hạn. Produce dựng lại clip thành `RenderInput`
`vertical_clip` (1080×1920, bố cục dọc sẵn có — không crop khung 16:9), đọc lại lời thoại bằng TTS
cho riêng clip, render bằng composition `HealthVideo` (kích thước lấy từ props).

**Tech Stack:** Python 3.14 + Pydantic 2 + pytest; Remotion 4.0.522 + React 19 + zod 4 + vitest.

**Spec:** `docs/superpowers/specs/2026-09-29-n2n-longform-channel-design.md` (§3 bước 3 và 9, §4.1,
§4.2, §11, §12 M8.2). Plan mẫu: `docs/superpowers/plans/2026-09-29-m8-1-format-profile-long-form.md`.

## Global Constraints

- Hai cổng duyệt giữ nguyên; không tự động xuất bản; không đổi state graph.
- Project `vertical_clip` cũ không cần outline/clip-plan; hash Cổng 1 của chúng không đổi.
- `youtube_long` bắt buộc `script/outline.yaml` và `script/clip-plan.yaml` trước khi duyệt y khoa.
- Outline: 5–8 chương, ID `^CH\d{2}$`, tổng `target_seconds` 900–1500 s (15–25 phút), thứ tự chương
  khớp storyboard, claim của mỗi cảnh phải nằm trong `claim_ids` của chương chứa cảnh.
- Clip: 3–6 clip, ID `^CL\d{2}$`, mỗi clip 30–90 s (900–2700 frame ở 30 fps).
- Clip không có trường văn bản nào ngoài `title` (nhãn nội bộ, không render).
- Clip chứa claim có `caveat_claim_ids` thì phải chứa mọi claim giới hạn đó; vi phạm → chặn duyệt
  Cổng 1 và chặn render clip.
- Không bịa nguồn/số liệu; fixture test dùng `synthetic_test_record: true`.
- Dùng `pathlib.Path`; lệnh chạy được trong PowerShell; không commit render/cache/report agy.
- Baseline trước M8.2: 992 passed, 3 skipped (Python); vitest + tsc sạch.

## Phân vai (bắt buộc từ M8.2)

| Việc | Ai |
|---|---|
| Viết code + test theo brief | agy |
| Chạy `python tools/agy_check.py` / `corepack pnpm --dir video test` / `... typecheck` | agy (chỉ 3 lệnh này) |
| Đọc diff, tự chạy lại kiểm tra, gửi yêu cầu sửa (`agy -c`) | Claude |
| `python tools/export_schemas.py` (Task 1, 2) | Claude, lúc review |
| Chèn dòng README bằng Python (utf-8) | Claude, lúc commit (agy không chạy được Python tùy ý) |
| `git add <paths>` + commit | Claude |

## Quy tắc chung cho agy

Áp dụng cho MỌI task. Đọc hết trước khi code.

1. Chỉ làm đúng task được giao. Chỉ sửa/tạo file liệt kê ở mục **Files** của task.
2. KHÔNG sửa `README.md`, `schemas/*.json`, `.gitignore`. KHÔNG chạy git. KHÔNG đổi kỳ vọng của test
   có sẵn, trừ chỗ task ghi rõ "Sửa test cũ".
3. Chỉ chạy được 3 lệnh, gõ đúng nguyên văn:
   - `python tools/agy_check.py` (ruff + toàn bộ pytest, tự đặt `PYTHONPATH=src`)
   - `corepack pnpm --dir video test`
   - `corepack pnpm --dir video typecheck`
4. TDD: viết test trước → chạy kiểm tra, thấy test mới FAIL đúng lý do → viết code → chạy lại đến khi
   dòng cuối là `AGY_CHECK: PASS`.
5. Code dán trong task là bản chuẩn. Được sửa lỗi cú pháp/import/lint hiển nhiên; mọi thay đổi khác
   phải ghi ở mục "Lệch khỏi plan" trong report.
6. Không bịa nguồn, DOI, PMID, số liệu y khoa. Chỉ dùng dữ liệu fixture có sẵn trong task.
7. UTF-8 cho mọi file; giữ tiếng Việt có dấu.
8. Kẹt (test cũ fail không rõ lý do, thiếu API) → dừng, ghi vào report, không đoán.
9. Khi xong, ghi report tại `.agy-reports/m8-2-task-<N>.md` theo mẫu:

```markdown
# M8.2 Task <N> — báo cáo agy
## File đã sửa/tạo
- <path>: <một dòng mô tả>
## Lệnh đã chạy (lần cuối)
- `python tools/agy_check.py` → <dòng cuối nguyên văn, ví dụ "AGY_CHECK: PASS">; pytest: <N passed, M skipped>
- (Task 5) `corepack pnpm --dir video test` → <kết quả>; `corepack pnpm --dir video typecheck` → <kết quả>
## Lệch khỏi plan
- <không có> hoặc <mô tả + lý do>
## Câu hỏi mở
- <không có> hoặc <câu hỏi>
```

Chỉ ghi kết quả của lệnh thực sự đã chạy. Không ghi "đã sửa X" nếu không có diff tương ứng.

## Lệnh giao việc (Claude chạy từ worktree)

```bash
agy -p "Đọc docs/superpowers/plans/2026-09-30-m8-2-outline-clip-plan.md: mục 'Quy tắc chung cho agy' và 'Task <N>'. Chỉ làm Task <N>. Xong thì ghi báo cáo vào .agy-reports/m8-2-task-<N>.md đúng mẫu." --mode accept-edits --model gemini-3.1-pro-high --print-timeout 0s
```

Vòng sửa:

```bash
agy -c -p "Review Task <N> chưa đạt: <danh sách lỗi, mỗi lỗi có file:dòng và cách sửa>. Sửa, chạy lại python tools/agy_check.py, cập nhật .agy-reports/m8-2-task-<N>.md." --mode accept-edits --model gemini-3.1-pro-high --print-timeout 0s
```

## Checklist review của Claude (mỗi task)

- [ ] `git status --short` + `git diff` — chỉ file trong mục **Files**; không có file lạ.
- [ ] Đối chiếu diff với code/test trong task và Global Constraints; không tin report agy.
- [ ] Tự chạy `python tools/agy_check.py` → `AGY_CHECK: PASS`; số test ≥ baseline + test mới.
- [ ] Task có `video/`: tự chạy `corepack pnpm --dir video test` và `... typecheck`.
- [ ] Task 1, 2: `python tools/export_schemas.py`; `git diff --stat schemas` chỉ đúng file dự kiến.
- [ ] Chèn dòng README, `git add <paths>` (không `-a`), commit.

Chèn dòng README (sau dòng `| M8.2 ...` cuối cùng; dán dòng của task vào `ROW`):

```bash
python - <<'PY'
from pathlib import Path
ROW = "<dán dòng README của task>"
path = Path("README.md")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
last = max(i for i, line in enumerate(lines) if line.startswith("| M8.2"))
lines.insert(last + 1, ROW + "\n")
path.write_text("".join(lines), encoding="utf-8")
PY
```

## File map

| File | Trách nhiệm |
|---|---|
| `src/healthvideo/domain/outline.py` (mới) | `Outline`, `OutlineChapter`, `validate_outline` |
| `src/healthvideo/domain/clip_plan.py` (mới) | `ClipPlan`, `ClipSpec`, `resolve_clip_scenes`, `validate_clip_plan` |
| `src/healthvideo/domain/evidence.py` | `EvidenceClaim.caveat_claim_ids` |
| `src/healthvideo/workflows/long_form.py` (mới) | nạp + kiểm outline/clip-plan; dựng và render clip |
| `src/healthvideo/workflows/gate_review.py` | Cổng 1 hash + kiểm outline/clip-plan; Cổng 2 hash clip |
| `src/healthvideo/workflows/review_html.py` | gói duyệt y khoa hiện dàn ý + clip; gói duyệt video hiện clip |
| `src/healthvideo/workflows/produce.py` | render clip trong nhánh `youtube_long`; manifest `clips` |
| `tools/export_schemas.py` | thêm `outline.schema.json`, `clip-plan.schema.json` |
| `tests/helpers.py` | `create_long_form_project_fixture` |
| `video/src/Root.tsx` | composition `VerticalClip` cho Studio |

---

### Task 1: Outline model + kiểm tra với storyboard

**Files:**
- Create: `src/healthvideo/domain/outline.py`
- Create: `tests/domain/test_outline.py`
- Modify: `tools/export_schemas.py` (thêm import + 1 dòng trong `SCHEMAS`)
- Modify: `tests/contracts/test_schemas.py` (thêm 1 dòng trong danh sách parametrize)

**Interfaces:**
- Consumes: `Storyboard`, `Scene` (`src/healthvideo/domain/storyboard.py`, có `chapter_id`, `format_profile` từ M8.1).
- Produces: `Outline(schema_version="1.0", title: str, chapters: tuple[OutlineChapter, ...])`;
  `OutlineChapter(id, title, goal, claim_ids: tuple[str, ...], target_seconds: int)`;
  `validate_outline(outline: Outline, storyboard: Storyboard, claim_ids: Set[str]) -> None` (ném `ValueError`).

- [ ] **Step 1: Viết test FAIL** — `tests/domain/test_outline.py`:

```python
import pytest
from pydantic import ValidationError

from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard

CHAPTERS = ("CH01", "CH02", "CH03", "CH04", "CH05")


def _chapters(ids: tuple[str, ...] = CHAPTERS, seconds: int = 240) -> list[dict]:
    return [
        {
            "id": chapter,
            "title": f"Chương {chapter}",
            "goal": "Giải thích một ý chính",
            "claim_ids": ["C01"] if chapter == "CH01" else [],
            "target_seconds": seconds,
        }
        for chapter in ids
    ]


def _outline(chapters: list[dict] | None = None) -> Outline:
    return Outline.model_validate(
        {"title": "Muối và huyết áp", "chapters": chapters or _chapters()}
    )


def _board(claims: dict[str, str] | None = None) -> Storyboard:
    claims = {"S01": "C01"} if claims is None else claims
    scenes = tuple(
        Scene(
            id=f"S{index:02d}", start_frame=(index - 1) * 900, duration_frames=900,
            narration="Nội dung", visual="whiteboard", chapter_id=chapter,
            claim_id=claims.get(f"S{index:02d}"),
        )
        for index, chapter in enumerate(CHAPTERS, start=1)
    )
    return Storyboard(title="PYH", scenes=scenes, format_profile="youtube_long")


def test_valid_outline_matches_storyboard() -> None:
    validate_outline(_outline(), _board(), {"C01"})


def test_outline_needs_five_to_eight_chapters() -> None:
    with pytest.raises(ValidationError, match="at least 5"):
        _outline(_chapters(CHAPTERS[:4], seconds=300))
    with pytest.raises(ValidationError, match="at most 8"):
        _outline(_chapters(tuple(f"CH{i:02d}" for i in range(1, 10)), seconds=120))


def test_outline_target_must_be_15_to_25_minutes() -> None:
    with pytest.raises(ValidationError, match="outline target 500 s"):
        _outline(_chapters(seconds=100))
    with pytest.raises(ValidationError, match="outline target 1600 s"):
        _outline(_chapters(seconds=320))


def test_outline_chapter_ids_unique() -> None:
    chapters = _chapters()
    chapters[1]["id"] = "CH01"
    with pytest.raises(ValidationError, match="unique"):
        _outline(chapters)


def test_outline_rejects_free_text_fields() -> None:
    chapters = _chapters()
    chapters[0]["narration"] = "Lời mới"
    with pytest.raises(ValidationError):
        _outline(chapters)


def test_outline_order_must_match_storyboard() -> None:
    chapters = _chapters()
    chapters[0], chapters[1] = chapters[1], chapters[0]
    with pytest.raises(ValueError, match="do not match storyboard"):
        validate_outline(_outline(chapters), _board(), {"C01"})


def test_outline_claim_must_exist_in_ledger() -> None:
    with pytest.raises(ValueError, match="CH01: unknown claim C01"):
        validate_outline(_outline(), _board(), set())


def test_scene_claim_must_be_planned_in_its_chapter() -> None:
    with pytest.raises(ValueError, match="Scene S02: claim C01 is not planned in chapter CH02"):
        validate_outline(_outline(), _board({"S01": "C01", "S02": "C01"}), {"C01"})


def test_outline_requires_youtube_long_storyboard() -> None:
    board = Storyboard(
        title="PYH",
        scenes=(Scene(id="S01", start_frame=0, duration_frames=1350, narration="N", visual="whiteboard"),),
    )
    with pytest.raises(ValueError, match="requires a youtube_long storyboard"):
        validate_outline(_outline(), board, {"C01"})
```

- [ ] **Step 2: Chạy** `python tools/agy_check.py` → FAIL: `No module named 'healthvideo.domain.outline'`.

- [ ] **Step 3: Code** — `src/healthvideo/domain/outline.py`:

```python
"""Long-form chapter plan (script/outline.yaml) and its check against the storyboard."""

from collections.abc import Set
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.storyboard import Storyboard

MIN_TARGET_SECONDS = 15 * 60
MAX_TARGET_SECONDS = 25 * 60


class OutlineChapter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CH\d{2}$")
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = ()
    target_seconds: int = Field(gt=0)


class Outline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1)
    chapters: tuple[OutlineChapter, ...] = Field(min_length=5, max_length=8)

    @model_validator(mode="after")
    def _check_chapters(self) -> "Outline":
        ids = [chapter.id for chapter in self.chapters]
        if len(ids) != len(set(ids)):
            raise ValueError("outline chapter IDs must be unique")
        total = sum(chapter.target_seconds for chapter in self.chapters)
        if not MIN_TARGET_SECONDS <= total <= MAX_TARGET_SECONDS:
            raise ValueError(
                f"outline target {total} s must be between "
                f"{MIN_TARGET_SECONDS} and {MAX_TARGET_SECONDS} s"
            )
        return self


def validate_outline(outline: Outline, storyboard: Storyboard, claim_ids: Set[str]) -> None:
    """Chapters appear in storyboard order; every scene claim is planned in its chapter."""
    if storyboard.format_profile != "youtube_long":
        raise ValueError("outline requires a youtube_long storyboard")
    order: list[str] = []
    for scene in storyboard.scenes:
        if scene.chapter_id is not None and (not order or order[-1] != scene.chapter_id):
            order.append(scene.chapter_id)
    planned = [chapter.id for chapter in outline.chapters]
    if order != planned:
        raise ValueError(f"outline chapters {planned} do not match storyboard {order}")
    for chapter in outline.chapters:
        for claim_id in chapter.claim_ids:
            if claim_id not in claim_ids:
                raise ValueError(f"{chapter.id}: unknown claim {claim_id}")
    by_id = {chapter.id: chapter for chapter in outline.chapters}
    for scene in storyboard.scenes:
        if scene.claim_id and scene.claim_id not in by_id[scene.chapter_id].claim_ids:
            raise ValueError(
                f"Scene {scene.id}: claim {scene.claim_id} is not planned "
                f"in chapter {scene.chapter_id}"
            )
```

`tools/export_schemas.py`: thêm `from healthvideo.domain.outline import Outline` (giữ thứ tự import
alphabet) và dòng `"outline.schema.json": Outline,` cuối dict `SCHEMAS`.

`tests/contracts/test_schemas.py`: thêm `("outline.schema.json", True),` cuối danh sách parametrize.

- [ ] **Step 4: Chạy** `python tools/agy_check.py` → `AGY_CHECK: PASS`.
- [ ] **Step 5: Report** `.agy-reports/m8-2-task-1.md`.

**Claude (review + commit):** `python tools/export_schemas.py` → chỉ thêm `schemas/outline.schema.json`.

README row:

```text
| M8.2 Task 1 outline | outline.yaml 5–8 chương, tổng 15–25 phút, thứ tự khớp storyboard, claim của cảnh phải thuộc chương | complete | pytest; Ruff; contracts | `feat: add long-form outline model` |
```

```bash
git add src/healthvideo/domain/outline.py tests/domain/test_outline.py tools/export_schemas.py tests/contracts/test_schemas.py schemas/outline.schema.json README.md
git commit -m "feat: add long-form outline model"
```

---

### Task 2: Clip plan + validator an toàn nội dung

**Files:**
- Modify: `src/healthvideo/domain/evidence.py` (class `EvidenceClaim`, ngay sau `chart_data`)
- Create: `src/healthvideo/domain/clip_plan.py`
- Create: `tests/domain/test_clip_plan.py`
- Modify: `tools/export_schemas.py`, `tests/contracts/test_schemas.py` (thêm `clip-plan.schema.json`)

**Interfaces:**
- Consumes: `Storyboard`, `Scene` (M8.1), `EvidenceClaim`.
- Produces: `EvidenceClaim.caveat_claim_ids: list[str]`; `ClipSpec(id, title, first_scene_id,
  last_scene_id, hook_scene_id: str | None, outro_scene_id: str | None)`;
  `ClipPlan(schema_version="1.0", clips: tuple[ClipSpec, ...])`;
  `resolve_clip_scenes(clip: ClipSpec, storyboard: Storyboard) -> tuple[Scene, ...]` (thứ tự: hook, dải, outro);
  `validate_clip_plan(plan: ClipPlan, storyboard: Storyboard, claims: Mapping[str, EvidenceClaim]) -> dict[str, tuple[Scene, ...]]`
  (khóa = clip ID, theo thứ tự trong plan).

- [ ] **Step 1: Viết test FAIL** — `tests/domain/test_clip_plan.py`:

```python
import pytest
from pydantic import ValidationError

from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.storyboard import Scene, Storyboard

LAYOUT = (("S01", "CH01", 900, "C01"), ("S02", "CH02", 900, "C02"), ("S03", "CH03", 900, None),
          ("S04", "CH04", 900, None), ("S05", "CH05", 900, None), ("S06", "CH05", 600, None))


def _board(profile: str = "youtube_long") -> Storyboard:
    scenes, start = [], 0
    for scene_id, chapter, frames, claim in LAYOUT:
        scenes.append(Scene(
            id=scene_id, start_frame=start, duration_frames=frames, narration=f"Lời {scene_id}",
            visual="whiteboard", claim_id=claim,
            chapter_id=chapter if profile == "youtube_long" else None,
        ))
        start += frames
    return Storyboard(title="PYH", scenes=tuple(scenes), format_profile=profile)


def _claim(claim_id: str, caveats: list[str]) -> EvidenceClaim:
    return EvidenceClaim(
        id=claim_id, text_public="Câu công chúng", text_technical="Mệnh đề kỹ thuật",
        type="evidence", sources=["R01"], caveat_claim_ids=caveats,
    )


CLAIMS = {"C01": _claim("C01", ["C02"]), "C02": _claim("C02", [])}


def _clip(clip_id: str, first: str, last: str, **extra: str) -> dict:
    return {"id": clip_id, "title": f"Clip {clip_id}", "first_scene_id": first,
            "last_scene_id": last, **extra}


def _plan(*clips: dict) -> ClipPlan:
    if not clips:
        clips = (_clip("CL01", "S01", "S02"), _clip("CL02", "S03", "S04"),
                 _clip("CL03", "S05", "S06"))
    return ClipPlan.model_validate({"clips": list(clips)})


def _with(first: dict) -> ClipPlan:
    return _plan(first, _clip("CL02", "S03", "S04"), _clip("CL03", "S05", "S06"))


def test_valid_plan_resolves_scenes_in_order() -> None:
    resolved = validate_clip_plan(_plan(), _board(), CLAIMS)
    assert [scene.id for scene in resolved["CL01"]] == ["S01", "S02"]
    assert list(resolved) == ["CL01", "CL02", "CL03"]


def test_hook_and_outro_wrap_the_range() -> None:
    plan = _with(_clip("CL01", "S03", "S03", hook_scene_id="S02", outro_scene_id="S04"))
    resolved = validate_clip_plan(plan, _board(), CLAIMS)
    assert [scene.id for scene in resolved["CL01"]] == ["S02", "S03", "S04"]


def test_claim_without_its_caveat_is_blocked() -> None:
    plan = _with(_clip("CL01", "S01", "S01", outro_scene_id="S03"))
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02 in the clip"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_hook_claim_also_needs_its_caveat() -> None:
    plan = _with(_clip("CL01", "S03", "S04", hook_scene_id="S01"))
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_claim_must_be_in_ledger() -> None:
    with pytest.raises(ValueError, match="CL01: claim C01 is not in the ledger"):
        validate_clip_plan(_plan(), _board(), {})


def test_caveat_must_be_in_ledger() -> None:
    with pytest.raises(ValueError, match="CL01: caveat C02 of claim C01 is not in the ledger"):
        validate_clip_plan(_plan(), _board(), {"C01": CLAIMS["C01"]})


@pytest.mark.parametrize(("first", "last", "frames"), [("S06", "S06", 600), ("S01", "S04", 3600)])
def test_clip_must_last_30_to_90_seconds(first: str, last: str, frames: int) -> None:
    plan = _with(_clip("CL01", first, last))
    with pytest.raises(ValueError, match=f"CL01: duration {frames} frames"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_unknown_scene() -> None:
    with pytest.raises(ValueError, match="CL01: unknown scene S99"):
        validate_clip_plan(_with(_clip("CL01", "S01", "S99")), _board(), CLAIMS)


def test_reversed_range() -> None:
    with pytest.raises(ValueError, match="CL01: first scene must not come after last scene"):
        validate_clip_plan(_with(_clip("CL01", "S02", "S01")), _board(), CLAIMS)


def test_hook_inside_range() -> None:
    plan = _with(_clip("CL01", "S01", "S02", hook_scene_id="S02"))
    with pytest.raises(ValueError, match="CL01: scene S02 is already inside the clip range"):
        validate_clip_plan(plan, _board(), CLAIMS)


def test_plan_needs_three_to_six_clips() -> None:
    with pytest.raises(ValidationError):
        _plan(_clip("CL01", "S01", "S02"), _clip("CL02", "S03", "S04"))
    with pytest.raises(ValidationError):
        _plan(*(_clip(f"CL{i:02d}", "S03", "S04") for i in range(1, 8)))


def test_clip_ids_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        _plan(_clip("CL01", "S01", "S02"), _clip("CL01", "S03", "S04"), _clip("CL03", "S05", "S06"))


def test_clip_cannot_carry_new_wording() -> None:
    with pytest.raises(ValidationError):
        _with(_clip("CL01", "S01", "S02", narration="Câu mới chưa duyệt"))


def test_clip_plan_requires_youtube_long_storyboard() -> None:
    with pytest.raises(ValueError, match="requires a youtube_long storyboard"):
        validate_clip_plan(_plan(), _board("vertical_clip"), CLAIMS)


def test_legacy_claim_has_no_caveats() -> None:
    claim = EvidenceClaim(id="C09", text_public="a", text_technical="b", type="evidence")
    assert claim.caveat_claim_ids == []
```

- [ ] **Step 2: Chạy** `python tools/agy_check.py` → FAIL: `No module named 'healthvideo.domain.clip_plan'`.

- [ ] **Step 3: Code**

`src/healthvideo/domain/evidence.py`, trong `class EvidenceClaim`, ngay sau dòng `chart_data: ...`:

```python
    # Doctor-owned: claims stating the limits/exceptions of this claim. A vertical
    # clip that shows this claim must also show every caveat claim (spec §4.2).
    caveat_claim_ids: list[str] = Field(default_factory=list)
```

`src/healthvideo/domain/clip_plan.py`:

```python
"""Vertical clip plan (script/clip-plan.yaml): clips cut from the approved long-form script.

A clip only points at existing storyboard scenes, so it cannot carry new wording;
``extra="forbid"`` keeps free text, and therefore new claims, out of the plan.
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.storyboard import Scene, Storyboard

FPS = 30
CLIP_MIN_FRAMES = 30 * FPS
CLIP_MAX_FRAMES = 90 * FPS


class ClipSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^CL\d{2}$")
    title: str = Field(min_length=1, max_length=100)  # internal label, never rendered
    first_scene_id: str
    last_scene_id: str
    hook_scene_id: str | None = None
    outro_scene_id: str | None = None


class ClipPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    clips: tuple[ClipSpec, ...] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ClipPlan":
        ids = [clip.id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("clip IDs must be unique")
        return self


def resolve_clip_scenes(clip: ClipSpec, storyboard: Storyboard) -> tuple[Scene, ...]:
    """Return hook + contiguous range + outro scenes, in that order."""
    index = {scene.id: position for position, scene in enumerate(storyboard.scenes)}
    wanted = (clip.first_scene_id, clip.last_scene_id, clip.hook_scene_id, clip.outro_scene_id)
    for scene_id in wanted:
        if scene_id is not None and scene_id not in index:
            raise ValueError(f"{clip.id}: unknown scene {scene_id}")
    first, last = index[clip.first_scene_id], index[clip.last_scene_id]
    if first > last:
        raise ValueError(f"{clip.id}: first scene must not come after last scene")
    for scene_id in (clip.hook_scene_id, clip.outro_scene_id):
        if scene_id is not None and first <= index[scene_id] <= last:
            raise ValueError(f"{clip.id}: scene {scene_id} is already inside the clip range")
    hook = [storyboard.scenes[index[clip.hook_scene_id]]] if clip.hook_scene_id else []
    outro = [storyboard.scenes[index[clip.outro_scene_id]]] if clip.outro_scene_id else []
    return tuple(hook + list(storyboard.scenes[first : last + 1]) + outro)


def validate_clip_plan(
    plan: ClipPlan, storyboard: Storyboard, claims: Mapping[str, EvidenceClaim]
) -> dict[str, tuple[Scene, ...]]:
    """Block clips that run too short/long, cite unknown claims, or drop a caveat."""
    if storyboard.format_profile != "youtube_long":
        raise ValueError("clip plan requires a youtube_long storyboard")
    resolved: dict[str, tuple[Scene, ...]] = {}
    for clip in plan.clips:
        scenes = resolve_clip_scenes(clip, storyboard)
        frames = sum(scene.duration_frames for scene in scenes)
        if not CLIP_MIN_FRAMES <= frames <= CLIP_MAX_FRAMES:
            raise ValueError(
                f"{clip.id}: duration {frames} frames must be between "
                f"{CLIP_MIN_FRAMES} and {CLIP_MAX_FRAMES}"
            )
        present = {scene.claim_id for scene in scenes if scene.claim_id}
        for claim_id in sorted(present):
            claim = claims.get(claim_id)
            if claim is None:
                raise ValueError(f"{clip.id}: claim {claim_id} is not in the ledger")
            for caveat_id in claim.caveat_claim_ids:
                if caveat_id not in claims:
                    raise ValueError(
                        f"{clip.id}: caveat {caveat_id} of claim {claim_id} is not in the ledger"
                    )
                if caveat_id not in present:
                    raise ValueError(
                        f"{clip.id}: claim {claim_id} requires caveat {caveat_id} in the clip"
                    )
        resolved[clip.id] = scenes
    return resolved
```

`tools/export_schemas.py`: thêm `from healthvideo.domain.clip_plan import ClipPlan` + dòng
`"clip-plan.schema.json": ClipPlan,`. `tests/contracts/test_schemas.py`: thêm `("clip-plan.schema.json", True),`.

- [ ] **Step 4: Chạy** `python tools/agy_check.py` → `AGY_CHECK: PASS`.
- [ ] **Step 5: Report** `.agy-reports/m8-2-task-2.md`.

**Claude:** `python tools/export_schemas.py` → đổi đúng `schemas/evidence.schema.json` (thêm
`caveat_claim_ids`) và thêm `schemas/clip-plan.schema.json`.

README row:

```text
| M8.2 Task 2 clip plan | clip-plan.yaml 3–6 clip 30–90 s chỉ tham chiếu cảnh có sẵn (không lời mới); ledger caveat_claim_ids; clip thiếu câu giới hạn bị chặn | complete | pytest; Ruff; contracts | `feat: add clip plan with caveat safety check` |
```

```bash
git add src/healthvideo/domain/evidence.py src/healthvideo/domain/clip_plan.py tests/domain/test_clip_plan.py tools/export_schemas.py tests/contracts/test_schemas.py schemas/evidence.schema.json schemas/clip-plan.schema.json README.md
git commit -m "feat: add clip plan with caveat safety check"
```

---

### Task 3: Outline + clip-plan vào gói Cổng 1

**Files:**
- Create: `src/healthvideo/workflows/long_form.py`
- Modify: `src/healthvideo/workflows/gate_review.py` (`medical_reviewed_paths` ~dòng 65; `approve_gate` ngay sau `validate_hook_outro(...)` ~dòng 173)
- Modify: `src/healthvideo/workflows/review_html.py` (`render_medical_packet`)
- Modify: `tests/helpers.py` (thêm `create_long_form_project_fixture` ngay sau `create_v2_project_fixture`)
- Sửa test cũ: `tests/workflows/test_produce_long_form.py` (`_long_form_project` + 1 assert)
- Create: `tests/workflows/test_gate_long_form.py`

**Interfaces:**
- Consumes: `Outline`, `validate_outline` (Task 1); `ClipPlan`, `validate_clip_plan` (Task 2).
- Produces: `OUTLINE_ARTIFACT = "script/outline.yaml"`, `CLIP_PLAN_ARTIFACT = "script/clip-plan.yaml"`;
  `load_clip_scenes(revision_root: Path, storyboard: Storyboard) -> dict[str, tuple[Scene, ...]]`;
  `tests.helpers.create_long_form_project_fixture(root: Path) -> Path` (project ở
  `awaiting_medical_review`, 6 cảnh S01–S06, 5 chương, 3 clip CL01–CL03, C01 có caveat C02).

- [ ] **Step 1: Fixture** — thêm vào `tests/helpers.py` ngay sau `create_v2_project_fixture`
  (`read_yaml`, `write_yaml_atomic`, `WorkflowState` đã được import trong file):

```python
def create_long_form_project_fixture(root: Path) -> Path:
    """youtube_long v2 project awaiting medical review: 6 scenes, 5 chapters, 3 clips.

    Claim C01 (scene S01) carries caveat C02 (scene S02): a clip showing S01 must show S02.
    """
    project_dir = create_v2_project_fixture(root, state=WorkflowState.AWAITING_MEDICAL_REVIEW)
    revision_root = project_dir / "revisions" / "001"

    ledger_path = revision_root / "evidence" / "ledger.yaml"
    ledger = read_yaml(ledger_path)
    ledger["claims"][0]["caveat_claim_ids"] = ["C02"]
    ledger["claims"].append(
        {
            "id": "C02",
            "text_public": "Mức giảm khác nhau giữa từng người.",
            "text_technical": "Đáp ứng huyết áp với giảm natri không đồng nhất.",
            "type": "evidence",
            "sources": ["R01"],
            "synthetic_test_record": True,
        }
    )
    write_yaml_atomic(ledger_path, ledger)

    texts = (
        "Ăn mặn có thể làm huyết áp tăng.",
        "Mức giảm khác nhau giữa từng người.",
        "Muối ẩn trong nhiều món chế biến sẵn.",
        "Đọc nhãn giúp biết lượng muối.",
        "Nêm nhạt dần để vị giác quen.",
        "Tóm tắt các ý chính của video.",
    )
    claims = {0: "C01", 1: "C02"}
    lines = []
    for index, text in enumerate(texts):
        line = {"id": f"L{index + 1:02d}", "text": text, "delivery": {"intent": "explain"}}
        if index in claims:
            line.update({"claim_id": claims[index], "source_marker": "[1]"})
        lines.append(line)
    script_path = revision_root / "script" / "script.yaml"
    script = read_yaml(script_path)
    script["lines"] = lines
    write_yaml_atomic(script_path, script)

    board_path = revision_root / "storyboard" / "storyboard.yaml"
    board = read_yaml(board_path)
    first = board["scenes"][0]
    first.update({"duration_frames": 900, "chapter_id": "CH01"})
    scenes = [first]
    chapters = ("CH01", "CH02", "CH03", "CH04", "CH05", "CH05")
    frames = (900, 900, 900, 900, 900, 600)
    start = 900
    for index in range(1, 6):
        scene = {
            "id": f"S{index + 1:02d}",
            "start_frame": start,
            "duration_frames": frames[index],
            "narration": texts[index],
            "visual": "whiteboard",
            "chapter_id": chapters[index],
        }
        if index in claims:
            scene.update({"claim_id": claims[index], "source_marker": "[1]"})
        scenes.append(scene)
        start += frames[index]
    board.update({"format_profile": "youtube_long", "scenes": scenes})
    write_yaml_atomic(board_path, board)

    write_yaml_atomic(
        revision_root / "script" / "outline.yaml",
        {
            "schema_version": "1.0",
            "title": "Ăn mặn và tăng huyết áp",
            "chapters": [
                {
                    "id": f"CH{number:02d}",
                    "title": f"Chương {number}",
                    "goal": "Giải thích một ý chính",
                    "claim_ids": {1: ["C01"], 2: ["C02"]}.get(number, []),
                    "target_seconds": 240,
                }
                for number in range(1, 6)
            ],
        },
    )
    write_yaml_atomic(
        revision_root / "script" / "clip-plan.yaml",
        {
            "schema_version": "1.0",
            "clips": [
                {"id": "CL01", "title": "Muối và huyết áp", "first_scene_id": "S01", "last_scene_id": "S02"},
                {"id": "CL02", "title": "Muối ẩn", "first_scene_id": "S03", "last_scene_id": "S04"},
                {"id": "CL03", "title": "Nêm nhạt dần", "first_scene_id": "S05", "last_scene_id": "S06"},
            ],
        },
    )
    return project_dir
```

- [ ] **Step 2: Test FAIL** — `tests/workflows/test_gate_long_form.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.storage.files import read_yaml, write_yaml_atomic
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate, medical_reviewed_paths
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_medical_packet
from tests.helpers import create_long_form_project_fixture, create_v2_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _revision(project_dir: Path) -> Path:
    return project_dir / "revisions" / "001"


def test_medical_gate_binds_outline_and_clip_plan(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    record = approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert {"script/outline.yaml", "script/clip-plan.yaml"} <= record.artifact_hashes.keys()
    assert read_yaml(project_dir / "project.yaml")["state"] == "medically_approved"


def test_medical_gate_requires_clip_plan(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    (_revision(project_dir) / "script" / "clip-plan.yaml").unlink()
    with pytest.raises(FileNotFoundError, match="youtube_long needs script/clip-plan.yaml"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert read_yaml(project_dir / "project.yaml")["state"] == "awaiting_medical_review"


def test_medical_gate_blocks_clip_missing_caveat(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    path = _revision(project_dir) / "script" / "clip-plan.yaml"
    plan = read_yaml(path)
    plan["clips"][0].update({"last_scene_id": "S01", "outro_scene_id": "S03"})
    write_yaml_atomic(path, plan)
    with pytest.raises(ValueError, match="CL01: claim C01 requires caveat C02"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    assert not (_revision(project_dir) / "reviews" / "medical-approval.yaml").exists()


def test_medical_gate_blocks_outline_mismatch(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    path = _revision(project_dir) / "script" / "outline.yaml"
    outline = read_yaml(path)
    outline["chapters"][0]["claim_ids"] = []
    write_yaml_atomic(path, outline)
    with pytest.raises(ValueError, match="Scene S01: claim C01 is not planned in chapter CH01"):
        approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)


def test_editing_clip_plan_after_approval_blocks_production(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    path = _revision(project_dir) / "script" / "clip-plan.yaml"
    plan = read_yaml(path)
    plan["clips"][1]["title"] = "Đổi sau khi duyệt"
    write_yaml_atomic(path, plan)
    with pytest.raises(ValueError, match="current medical approval"):
        produce_project(project_dir, SilentTTS(), lambda argv: 0)


def test_vertical_project_gate_paths_unchanged(tmp_path: Path) -> None:
    project_dir = create_v2_project_fixture(tmp_path)
    paths = medical_reviewed_paths(_revision(project_dir))
    assert "script/outline.yaml" not in paths and "script/clip-plan.yaml" not in paths


def test_medical_packet_shows_outline_and_clips(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    html = render_medical_packet(_revision(project_dir))
    assert "Dàn ý chương" in html and "CH05" in html
    assert "Clip dọc 9:16" in html and "CL01" in html and "S01, S02" in html
```

- [ ] **Step 3: Chạy** `python tools/agy_check.py` → FAIL (thiếu `youtube_long needs ...`, thiếu hash, thiếu HTML).

- [ ] **Step 4: Code**

`src/healthvideo/workflows/long_form.py`:

```python
"""Long-form Gate 1 plans: script/outline.yaml and script/clip-plan.yaml."""

from pathlib import Path

from healthvideo.domain.clip_plan import ClipPlan, validate_clip_plan
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.outline import Outline, validate_outline
from healthvideo.domain.storyboard import Scene, Storyboard
from healthvideo.storage.files import read_yaml

OUTLINE_ARTIFACT = "script/outline.yaml"
CLIP_PLAN_ARTIFACT = "script/clip-plan.yaml"


def load_clip_scenes(revision_root: Path, storyboard: Storyboard) -> dict[str, tuple[Scene, ...]]:
    """Validate outline + clip plan against storyboard and ledger; return each clip's scenes."""
    for name in (OUTLINE_ARTIFACT, CLIP_PLAN_ARTIFACT):
        if not (revision_root / name).is_file():
            raise FileNotFoundError(f"youtube_long needs {name}")
    ledger = read_yaml(revision_root / "evidence" / "ledger.yaml")
    claims = {
        claim.id: claim
        for claim in (EvidenceClaim.model_validate(item) for item in ledger.get("claims", []))
    }
    outline = Outline.model_validate(read_yaml(revision_root / OUTLINE_ARTIFACT))
    validate_outline(outline, storyboard, claims.keys())
    plan = ClipPlan.model_validate(read_yaml(revision_root / CLIP_PLAN_ARTIFACT))
    return validate_clip_plan(plan, storyboard, claims)
```

`src/healthvideo/workflows/gate_review.py`:
- import: `from healthvideo.workflows.long_form import CLIP_PLAN_ARTIFACT, OUTLINE_ARTIFACT, load_clip_scenes`
- trong `medical_reviewed_paths`, ngay sau khi tạo dict `paths` (trước `manifest_path = ...`):

```python
    storyboard_path = paths["storyboard/storyboard.yaml"]
    if (
        storyboard_path.is_file()
        and read_yaml(storyboard_path).get("format_profile") == "youtube_long"
    ):
        for name in (OUTLINE_ARTIFACT, CLIP_PLAN_ARTIFACT):
            paths[name] = revision_root / name
```

- trong `approve_gate`, ngay sau dòng `validate_hook_outro(script, storyboard, require_brand=True)`:

```python
        if storyboard.format_profile == "youtube_long":
            load_clip_scenes(revision_root, storyboard)
```

`src/healthvideo/workflows/review_html.py`:
- import: `from healthvideo.domain.outline import Outline` và
  `from healthvideo.workflows.long_form import OUTLINE_ARTIFACT, load_clip_scenes`
- thêm hàm ngay trước `def render_medical_packet`:

```python
def _render_long_form_section(revision_root: Path, storyboard: Storyboard) -> str:
    if storyboard.format_profile != "youtube_long":
        return ""
    outline = Outline.model_validate(read_yaml(revision_root / OUTLINE_ARTIFACT))
    chapter_rows = "".join(
        f"<tr><td>{escape(chapter.id)}</td><td>{escape(chapter.title)}</td>"
        f"<td>{escape(chapter.goal)}</td><td>{escape(', '.join(chapter.claim_ids))}</td>"
        f"<td>{chapter.target_seconds}</td></tr>"
        for chapter in outline.chapters
    )
    clip_rows = "".join(
        f"<tr><td>{escape(clip_id)}</td>"
        f"<td>{escape(', '.join(scene.id for scene in scenes))}</td>"
        f"<td>{escape(' '.join(scene.narration for scene in scenes))}</td>"
        f"<td>{escape(', '.join(sorted({s.claim_id for s in scenes if s.claim_id})))}</td></tr>"
        for clip_id, scenes in load_clip_scenes(revision_root, storyboard).items()
    )
    return (
        '<section><h2>Dàn ý chương</h2><table border="1"><thead><tr>'
        "<th>Chương</th><th>Tiêu đề</th><th>Mục tiêu</th><th>Claim</th><th>Giây dự kiến</th>"
        f"</tr></thead><tbody>{chapter_rows}</tbody></table></section>"
        '<section><h2>Clip dọc 9:16 cắt từ kịch bản</h2><table border="1"><thead><tr>'
        "<th>Clip</th><th>Cảnh</th><th>Lời thoại</th><th>Claim</th>"
        f"</tr></thead><tbody>{clip_rows}</tbody></table></section>"
    )
```

- trong `render_medical_packet`, ở biểu thức `return`, thêm
  `+ _render_long_form_section(revision_root, storyboard)` ngay trước `+ "</body></html>"`.

Sửa test cũ `tests/workflows/test_produce_long_form.py`:
- import thêm `create_long_form_project_fixture` từ `tests.helpers`; bỏ import không còn dùng
  (`create_v2_project_fixture`, `write_yaml_atomic`, … — ruff sẽ báo).
- thay thân `_long_form_project` bằng:

```python
def _long_form_project(tmp_path: Path) -> Path:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer="BS Nguyễn Văn An", now=REVIEWED_AT)
    return project_dir
```

- đổi `"--frames=0-1799" in calls[0]` thành `"--frames=0-899" in calls[0]` (chương CH01 giờ là S01, 900 frame).

- [ ] **Step 5: Chạy** `python tools/agy_check.py` → `AGY_CHECK: PASS`.
- [ ] **Step 6: Report** `.agy-reports/m8-2-task-3.md`.

**Claude:** README row:

```text
| M8.2 Task 3 Cổng 1 long-form | youtube_long bắt buộc outline.yaml + clip-plan.yaml; Cổng 1 hash và kiểm cả hai; gói duyệt y khoa hiện dàn ý và clip; sửa sau duyệt chặn produce | complete | pytest; Ruff | `feat: gate long-form outline and clip plan at medical review` |
```

```bash
git add src/healthvideo/workflows/long_form.py src/healthvideo/workflows/gate_review.py src/healthvideo/workflows/review_html.py tests/helpers.py tests/workflows/test_produce_long_form.py tests/workflows/test_gate_long_form.py README.md
git commit -m "feat: gate long-form outline and clip plan at medical review"
```

---

### Task 4: Render clip 9:16 trong produce + clip vào Cổng 2

**Files:**
- Modify: `src/healthvideo/workflows/long_form.py` (thêm `clip_render_input`, `render_clips`)
- Modify: `src/healthvideo/workflows/produce.py` (`_produce_v2`, `_v2_run_is_valid`)
- Modify: `src/healthvideo/workflows/gate_review.py` (`video_reviewed_paths`)
- Modify: `src/healthvideo/workflows/review_html.py` (`render_video_packet`)
- Sửa test cũ: `tests/workflows/test_produce_long_form.py` (1 assert)
- Create: `tests/workflows/test_clips_render.py`

**Interfaces:**
- Consumes: `load_clip_scenes`, `CLIP_PLAN_ARTIFACT` (Task 3); `build_render_input`, `audio_timing_qa`
  (`render/input.py`); `build_render_argv` (`render/remotion.py`).
- Produces: `clip_render_input(storyboard: Storyboard, scenes: Sequence[Scene], audio_file: str) -> RenderInput`;
  `render_clips(clip_scenes, storyboard, staging_dir, *, synthesize: Callable[[str, Path], int], runner) -> dict[str, str]`;
  render manifest có khóa `"clips": {"CL01": "clips/CL01.mp4", ...}` khi `youtube_long`;
  Cổng 2 hash thêm `renders/clips/<id>.mp4`.

Thiết kế: mỗi clip đọc lại lời thoại của chính các cảnh đó bằng TTS (không cắt WAV dài → không cắt
ngang câu). Render clip **trước** các chương, để lệnh cuối vẫn là FFmpeg concat (giữ test CLI M8.1).

- [ ] **Step 1: Test FAIL** — `tests/workflows/test_clips_render.py`:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from healthvideo.domain.gate_review import GateKind
from healthvideo.domain.storyboard import Storyboard
from healthvideo.storage.files import read_yaml
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.gate_review import approve_gate
from healthvideo.workflows.long_form import clip_render_input
from healthvideo.workflows.produce import produce_project
from healthvideo.workflows.review_html import render_video_packet
from tests.helpers import create_long_form_project_fixture

REVIEWED_AT = datetime(2026, 9, 30, 9, 0, tzinfo=UTC)
REVIEWER = "BS Nguyễn Văn An"


def _runner(calls: list[list[str]]):
    def run(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--output") + 1]) if "--output" in argv else Path(argv[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp4")
        return 0
    return run


def _produced(tmp_path: Path) -> tuple[Path, list[list[str]]]:
    project_dir = create_long_form_project_fixture(tmp_path)
    approve_gate(project_dir, GateKind.MEDICAL, reviewer=REVIEWER, now=REVIEWED_AT)
    calls: list[list[str]] = []
    produce_project(project_dir, SilentTTS(), _runner(calls))
    return project_dir, calls


def test_clip_render_input_is_vertical_and_retimed(tmp_path: Path) -> None:
    project_dir = create_long_form_project_fixture(tmp_path)
    board = Storyboard.model_validate(
        read_yaml(project_dir / "revisions/001/storyboard/storyboard.yaml")
    )
    result = clip_render_input(board, board.scenes[2:4], "audio/clips/CL02.wav")
    assert (result.format_profile, result.width, result.height) == ("vertical_clip", 1080, 1920)
    assert [(s.id, s.start_frame, s.chapter_id) for s in result.scenes] == [
        ("S03", 0, None), ("S04", 900, None)
    ]
    assert [s.narration for s in result.scenes] == [s.narration for s in board.scenes[2:4]]


def test_produce_renders_each_clip_vertical(tmp_path: Path) -> None:
    project_dir, calls = _produced(tmp_path)
    renders = project_dir / "revisions" / "001" / "renders"
    manifest = json.loads((renders / "render-manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"] == {
        "CL01": "clips/CL01.mp4", "CL02": "clips/CL02.mp4", "CL03": "clips/CL03.mp4"
    }
    clip_input = json.loads(
        (renders / "clips" / "CL01.render-input.json").read_text(encoding="utf-8")
    )
    assert (clip_input["width"], clip_input["height"]) == (1080, 1920)
    assert [scene["id"] for scene in clip_input["scenes"]] == ["S01", "S02"]
    assert (renders / "audio" / "clips" / "CL01.wav").is_file()
    assert all((renders / relative).is_file() for relative in manifest["clips"].values())
    assert calls[-1][0] == "ffmpeg"
    clip_calls = [c for c in calls if c[0] != "ffmpeg" and not any(a.startswith("--frames") for a in c)]
    assert len(clip_calls) == 3


def test_video_gate_binds_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    record = approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)
    assert {f"renders/clips/CL0{n}.mp4" for n in (1, 2, 3)} <= record.artifact_hashes.keys()


def test_video_gate_refuses_missing_clip(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    (project_dir / "revisions/001/renders/clips/CL02.mp4").unlink()
    with pytest.raises(FileNotFoundError, match="renders/clips/CL02.mp4"):
        approve_gate(project_dir, GateKind.VIDEO, reviewer=REVIEWER, now=REVIEWED_AT)


def test_video_packet_lists_clips(tmp_path: Path) -> None:
    project_dir, _ = _produced(tmp_path)
    html = render_video_packet(project_dir / "revisions" / "001")
    assert "../renders/clips/CL01.mp4" in html
```

- [ ] **Step 2: Chạy** `python tools/agy_check.py` → FAIL (`cannot import name 'clip_render_input'`).

- [ ] **Step 3: Code**

`src/healthvideo/workflows/long_form.py` — thêm import (gộp vào khối import đầu file) và hai hàm:

```python
import json
from collections.abc import Callable, Mapping, Sequence

from healthvideo.render.input import RenderInput, audio_timing_qa, build_render_input
from healthvideo.render.remotion import build_render_argv


def clip_render_input(
    storyboard: Storyboard, scenes: Sequence[Scene], audio_file: str
) -> RenderInput:
    """Re-time the clip's approved scenes from frame 0 as a 9:16 render (re-laid out, not cropped)."""
    retimed: list[Scene] = []
    start = 0
    for scene in scenes:
        retimed.append(scene.model_copy(update={"start_frame": start, "chapter_id": None}))
        start += scene.duration_frames
    board = Storyboard(
        title=storyboard.title,
        scenes=tuple(retimed),
        visual_budget_profile=storyboard.visual_budget_profile,
        format_profile="vertical_clip",
    )
    return build_render_input(board, audio_file, duration_policy="v2")


def render_clips(
    clip_scenes: Mapping[str, Sequence[Scene]],
    storyboard: Storyboard,
    staging_dir: Path,
    *,
    synthesize: Callable[[str, Path], int],
    runner: Callable[[list[str]], int],
) -> dict[str, str]:
    """Voice and render each approved clip; return clip ID -> mp4 path relative to the run."""
    # ponytail: clips re-render with every long-form render; cache per clip if it gets slow.
    outputs: dict[str, str] = {}
    for clip_id, scenes in clip_scenes.items():
        audio = f"audio/clips/{clip_id}.wav"
        duration_ms = synthesize(" ".join(scene.narration for scene in scenes), staging_dir / audio)
        audio_timing_qa(duration_ms, sum(scene.duration_frames for scene in scenes))
        render_input = clip_render_input(storyboard, scenes, audio)
        input_path = staging_dir / "clips" / f"{clip_id}.render-input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            json.dumps(render_input.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        output = staging_dir / "clips" / f"{clip_id}.mp4"
        if runner(build_render_argv(input_path, output, staging_dir)) != 0 or not output.is_file():
            raise RuntimeError(f"Clip {clip_id} render failed")
        outputs[clip_id] = f"clips/{clip_id}.mp4"
    return outputs
```

`src/healthvideo/workflows/produce.py`:
- import: `from healthvideo.workflows.long_form import CLIP_PLAN_ARTIFACT, load_clip_scenes, render_clips`
- trong `_produce_v2`, dict truyền vào `canonical_json_hash(...)` để tính `input_hash`: thêm mục cuối

```python
            **(
                {"clip_plan": read_yaml(layout.artifact_root / CLIP_PLAN_ARTIFACT)}
                if storyboard.format_profile == "youtube_long"
                else {}
            ),
```

- trong khối `try`, thay hai dòng:

```python
        chapter_parts: tuple[str, ...] = ()
        if render_input.format_profile == "youtube_long":
            chapter_parts = render_long_form(
```

  bằng:

```python
        chapter_parts: tuple[str, ...] = ()
        clip_outputs: dict[str, str] = {}
        if render_input.format_profile == "youtube_long":

            def synthesize_clip(text: str, path: Path) -> int:
                tts.synthesize(
                    TTSRequest(
                        text=apply_pronunciation(text, pronunciation),
                        language=script.language,
                    ),
                    path,
                )
                return inspect_wav(
                    path, require_signal=getattr(tts, "require_signal", False)
                ).duration_ms

            clip_outputs = render_clips(
                load_clip_scenes(layout.artifact_root, storyboard),
                storyboard,
                staging_dir,
                synthesize=synthesize_clip,
                runner=runner,
            )
            chapter_parts = render_long_form(
```

  (các đối số còn lại của `render_long_form(...)` giữ nguyên.)
- trong dict ghi `V2_RENDER_MANIFEST_NAME`, ngay sau dòng `chapter_parts`, thêm
  `**({"clips": clip_outputs} if clip_outputs else {}),`
- trong `_v2_run_is_valid`, ngay trước `return all(` cuối hàm:

```python
    if not all(
        (run_dir / relative).is_file() for relative in manifest.get("clips", {}).values()
    ):
        return False
```

`src/healthvideo/workflows/gate_review.py` — thay toàn bộ `video_reviewed_paths`:

```python
def video_reviewed_paths(revision_root: Path) -> dict[str, Path]:
    """Name the artifacts the video gate covers: render manifest, MP4 and every clip."""
    renders = revision_root / "renders"
    paths = {
        "renders/render-manifest.json": renders / "render-manifest.json",
        "renders/video.mp4": renders / "video.mp4",
    }
    manifest_path = renders / "render-manifest.json"
    if manifest_path.is_file():
        clips = json.loads(manifest_path.read_text(encoding="utf-8")).get("clips", {})
        for relative in clips.values():
            paths[f"renders/{relative}"] = renders / relative
    return paths
```

`src/healthvideo/workflows/review_html.py`, trong `render_video_packet`, trước `return`:

```python
    clip_videos = "".join(
        f"<h2>Clip {escape(clip_id)}</h2>"
        f'<video controls src="../renders/{escape(relative)}"></video>'
        for clip_id, relative in sorted(manifest.get("clips", {}).items())
    )
```

  và chèn `+ clip_videos` ngay sau chuỗi `'<video controls src="../renders/video.mp4"></video>'`.

Sửa test cũ `tests/workflows/test_produce_long_form.py`: đổi
`assert "--frames=0-899" in calls[0] and "--muted" in calls[0]` thành
`assert any("--frames=0-899" in call and "--muted" in call for call in calls)`
(lệnh đầu giờ là render clip).

- [ ] **Step 4: Chạy** `python tools/agy_check.py` → `AGY_CHECK: PASS`.
- [ ] **Step 5: Report** `.agy-reports/m8-2-task-4.md`.

**Claude (thêm):** nếu có project youtube_long thật trong `projects/`, render 1 clip thật và
`ffprobe` xác nhận 1080×1920 + có audio; không có thì ghi "smoke thật: chưa có project mẫu".

README row:

```text
| M8.2 Task 4 clip render | produce youtube_long đọc lại + render từng clip 9:16 từ cảnh đã duyệt (không crop), manifest clips, Cổng 2 hash clip, gói duyệt video hiện clip | complete | pytest; Ruff; smoke <kết quả> | `feat: render vertical clips and bind them to video review` |
```

```bash
git add src/healthvideo/workflows/long_form.py src/healthvideo/workflows/produce.py src/healthvideo/workflows/gate_review.py src/healthvideo/workflows/review_html.py tests/workflows/test_produce_long_form.py tests/workflows/test_clips_render.py README.md
git commit -m "feat: render vertical clips and bind them to video review"
```

---

### Task 5: Composition `VerticalClip` cho Remotion Studio

**Files:**
- Modify: `video/src/Root.tsx`
- Modify: `video/src/Root.test.ts`

**Interfaces:**
- Consumes: `metadataFromProps`, `defaultProps` (M8.1, `video/src/Root.tsx`).
- Produces: `export const verticalClipDefaults: RenderInput`; composition id `VerticalClip`
  (1080×1920, mặc định 900 frame, kích thước/độ dài lấy từ props). Render từ Python vẫn dùng
  `HealthVideo` (đã tự lấy kích thước từ props); `VerticalClip` để xem/sửa trong Studio (spec §6.1).

- [ ] **Step 1: Test FAIL** — sửa import đầu `video/src/Root.test.ts` thành
  `import {metadataFromProps, verticalClipDefaults} from './Root';` và thêm vào cuối file:

```ts
describe('vertical clip', () => {
  it('defaults to a 30 s 9:16 clip', () => {
    expect(metadataFromProps(verticalClipDefaults))
      .toEqual({durationInFrames: 900, width: 1080, height: 1920});
  });

  it('accepts a Python clip render input (re-timed, no chapter)', () => {
    const clip = {title: 'T', audio_file: 'audio/clips/CL01.wav', format_profile: 'vertical_clip',
      width: 1080, height: 1920, scenes: [
        {id: 'S01', start_frame: 0, duration_frames: 900, narration: 'A', visual: 'whiteboard'},
        {id: 'S02', start_frame: 900, duration_frames: 600, narration: 'B', visual: 'whiteboard'},
      ]};
    expect(metadataFromProps(clip)).toEqual({durationInFrames: 1500, width: 1080, height: 1920});
  });
});
```

- [ ] **Step 2: Chạy** `corepack pnpm --dir video test` → FAIL (`verticalClipDefaults` không tồn tại).

- [ ] **Step 3: Code** — `video/src/Root.tsx`, ngay sau `longFormDefaults`:

```tsx
export const verticalClipDefaults: RenderInput = {
  ...defaultProps,
  audio_file: 'audio/clips/CL01.wav',
  scenes: [{...defaultProps.scenes[0], duration_frames: 900}],
};
```

  và trong `RemotionRoot`, ngay sau composition `LongForm`:

```tsx
    <Composition
      id="VerticalClip"
      component={HealthVideo}
      defaultProps={verticalClipDefaults}
      durationInFrames={900}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={({props}) => metadataFromProps(props)}
    />
```

- [ ] **Step 4: Chạy** `corepack pnpm --dir video test` và `corepack pnpm --dir video typecheck` → cả hai sạch;
  `python tools/agy_check.py` → `AGY_CHECK: PASS` (renderer identity đổi, test Python vẫn phải qua).
- [ ] **Step 5: Report** `.agy-reports/m8-2-task-5.md`.

**Claude (thêm):** `corepack pnpm --dir video exec remotion compositions src/index.ts` liệt kê
`HealthVideo`, `LongForm`, `VerticalClip`.

README row:

```text
| M8.2 Task 5 VerticalClip | Composition VerticalClip 1080×1920 cho Remotion Studio; nhận render input clip từ Python | complete | vitest; tsc; remotion compositions | `feat: add VerticalClip composition for Studio` |
```

```bash
git add video/src/Root.tsx video/src/Root.test.ts README.md
git commit -m "feat: add VerticalClip composition for Studio"
```

---

## Sau M8.2

- Claude chạy toàn bộ: `python tools/agy_check.py`, `corepack pnpm --dir video test`, `... typecheck`.
- Review toàn nhánh theo spec §4.1–4.2 và §11 → sửa qua agy nếu cần → đổi dòng "M8.2 plan" trong
  README sang `complete`.
- Người dùng tự tạo PR (như M8.1).

## Để sau (không làm ở M8.2)

- Kiểm tra hook mở đầu ≤ 30 s và chương kết (tóm tắt + giới hạn + hành động): cần quy ước đánh dấu
  cảnh; làm cùng bước viết draft long-form.
- Cache riêng từng clip (hiện render lại cùng video dài).
- Visual regression 1 frame cho `VerticalClip` (bố cục dọc đã có test ở `HealthVideo.test.tsx`).
- Đưa clip vào gói đăng `publish/tiktok/<clip-id>/` — M8.6.
