# Preventive Health Video MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo một vertical slice chạy được từ hồ sơ video, `author brief`, kịch bản có nhịp nói và storyboard đến TTS giả lập, render Remotion 9:16, hai cổng bác sĩ duyệt và gói xuất bản.

**Architecture:** Python CLI là nguồn điều phối và lưu artifact YAML/JSON theo schema; các hàm domain không phụ thuộc CLI hoặc renderer. Remotion nhận một `render-input.json` bất biến và dựng video bằng component nhỏ. Mọi bước ghi manifest có hash để chạy lại an toàn; MVP chưa gọi LLM, PubMed, Scopus hoặc TTS thương mại.

**Tech Stack:** Python 3.11+, Pydantic 2.13.5, Typer 0.27.2, PyYAML 6.0.3, pytest 9.1.1, Ruff 0.16.6; Node.js 22+, pnpm 11.19.0, TypeScript 7.0.2, React 19.2.8, Remotion 4.0.522, Zod 4.5.4, Vitest 5.0.0; FFmpeg 8+.

**Spec:** `docs/superpowers/specs/2026-09-07-preventive-health-video-system-design.md`

## Global Constraints

- Đầu ra chính là video tiếng Việt 1080 × 1920, 30 fps, dài 45–90 giây.
- AI chỉ chấp bút từ ý kiến của bác sĩ; MVP không tự sinh lập trường, trải nghiệm hoặc cảm xúc.
- Luận điểm y khoa phải mang `claim_id`; ý kiến cá nhân dùng `professional_opinion` và không giả làm bằng chứng.
- Cổng duyệt y khoa phải hoàn tất trước sản xuất; cổng duyệt video phải hoàn tất trước đóng gói.
- Video chỉ hiện `[1]`, `[2]`; nguồn đầy đủ nằm trong artifact và caption.
- Git không lưu API key, cache, model, toàn văn có bản quyền, audio tạm hoặc render.
- Mọi lệnh phải chạy được trong PowerShell; đường dẫn nội bộ dùng `pathlib.Path`.
- Test không cần mạng, tài khoản AI, Scopus hoặc GPU.
- `README.md` là bảng tiến độ duy nhất; mỗi task cập nhật trạng thái, test đã chạy và commit trong cùng commit với mã.

---

## File map

| Khu vực | Trách nhiệm |
|---|---|
| `src/healthvideo/domain/` | Model, state machine và quy tắc thuần Python |
| `src/healthvideo/storage/` | Đọc/ghi YAML/JSON nguyên tử và hash artifact |
| `src/healthvideo/workflows/` | Use case tạo dự án, duyệt, sản xuất và đóng gói |
| `src/healthvideo/tts/` | Protocol TTS và provider giả lập xác định |
| `src/healthvideo/render/` | Chuyển domain model thành input Remotion và gọi renderer |
| `src/healthvideo/qa/` | Kiểm tra giọng nói, claim, thời lượng và gói xuất |
| `video/src/` | Composition, scene và component hình ảnh |
| `schemas/` | JSON Schema xuất từ Pydantic, dùng giữa Python và TypeScript |
| `profiles/` | Brand, giọng tác giả và policy bằng chứng |
| `tests/` | Unit, contract và end-to-end tests |

---

### Task 1: Bootstrap repo và CLI có thể kiểm thử

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `CLAUDE.md`
- Create: `src/healthvideo/__init__.py`
- Create: `src/healthvideo/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: Không.
- Produces: console command `healthvideo`; hằng `healthvideo.__version__`.

- [ ] **Step 1: Viết test CLI thất bại**

```python
# tests/test_cli.py
from typer.testing import CliRunner

from healthvideo import __version__
from healthvideo.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/test_cli.py -v`

Expected: FAIL vì chưa có package `healthvideo`.

- [ ] **Step 3: Tạo package và cấu hình dependency**

`pyproject.toml` phải khai báo `requires-python = ">=3.11"`, package layout `src`, command `healthvideo = "healthvideo.cli:app"`, runtime dependencies `pydantic==2.13.5`, `typer==0.27.2`, `PyYAML==6.0.3`; dev dependencies `pytest==9.1.1`, `ruff==0.16.6`.

```python
# src/healthvideo/__init__.py
__version__ = "0.1.0"
```

```python
# src/healthvideo/cli.py
import typer

from healthvideo import __version__

app = typer.Typer(no_args_is_help=True)


@app.command()
def version() -> None:
    """In phiên bản healthvideo."""
    typer.echo(__version__)
```

`.gitignore` phải loại `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `cache/`, `projects/**/audio/`, `projects/**/renders/` và `projects/**/source-documents/`. Không ignore metadata, script, storyboard hoặc review.

`AGENTS.md` và `CLAUDE.md` cùng yêu cầu: đọc spec và plan; không bịa nguồn; không vượt cổng duyệt; chỉ tải reference cần thiết; chạy test liên quan trước commit. Mỗi file dưới 100 dòng.

`README.md` phải có các phần: `Mục tiêu`, `Trạng thái hiện tại`, `Milestone`, `Tiến độ nhiệm vụ`, `Kiến trúc`, `Quick start`, `Workflow`, `Kiểm thử gần nhất`, `Quyết định`, `Giới hạn hiện tại` và `Tài liệu`. Bảng tiến độ ban đầu liệt kê Task 1–10 với trạng thái `planned`; khi hoàn tất Task 1, đổi Task 1 thành `complete`. Mỗi hàng có cột `Task`, `Deliverable`, `Status`, `Tests`, `Commit`. Dùng đúng ba giá trị trạng thái: `planned`, `in_progress`, `complete`.

- [ ] **Step 4: Cài editable package và chạy test/lint**

Run: `python -m pip install -e ".[dev]"`

Run: `python -m pytest tests/test_cli.py -v`

Run: `python -m ruff check src tests`

Expected: tất cả PASS, Ruff không báo lỗi.

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml README.md AGENTS.md CLAUDE.md src/healthvideo tests/test_cli.py
git commit -m "chore: bootstrap healthvideo CLI"
```

---

### Task 2: Domain model, state machine và storage nguyên tử

**Files:**
- Create: `src/healthvideo/domain/__init__.py`
- Create: `src/healthvideo/domain/project.py`
- Create: `src/healthvideo/storage/__init__.py`
- Create: `src/healthvideo/storage/files.py`
- Create: `tests/domain/test_project.py`
- Create: `tests/storage/test_files.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Pydantic.
- Produces: `ProjectState`, `ProjectManifest`, `transition(manifest, target)`, `read_yaml(path)`, `write_yaml_atomic(path, data)`, `sha256_file(path)`.

- [ ] **Step 1: Viết test state machine và storage thất bại**

```python
# tests/domain/test_project.py
import pytest

from healthvideo.domain.project import ProjectManifest, ProjectState, transition


def test_state_machine_accepts_only_next_state() -> None:
    project = ProjectManifest(slug="muoi-va-huyet-ap")
    changed = transition(project, ProjectState.EVIDENCE_IN_PROGRESS)
    assert changed.state is ProjectState.EVIDENCE_IN_PROGRESS
    with pytest.raises(ValueError, match="Invalid transition"):
        transition(changed, ProjectState.RENDERED)
```

```python
# tests/storage/test_files.py
from healthvideo.storage.files import read_yaml, sha256_file, write_yaml_atomic


def test_yaml_round_trip_and_hash(tmp_path) -> None:
    path = tmp_path / "project.yaml"
    write_yaml_atomic(path, {"slug": "muoi-va-huyet-ap", "state": "idea"})
    assert read_yaml(path)["state"] == "idea"
    assert len(sha256_file(path)) == 64
    assert not (tmp_path / "project.yaml.tmp").exists()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/domain/test_project.py tests/storage/test_files.py -v`

Expected: FAIL vì các module chưa tồn tại.

- [ ] **Step 3: Cài state machine tối thiểu**

```python
# src/healthvideo/domain/project.py
from enum import StrEnum

from pydantic import BaseModel, Field


class ProjectState(StrEnum):
    IDEA = "idea"
    EVIDENCE_IN_PROGRESS = "evidence_in_progress"
    EVIDENCE_READY = "evidence_ready"
    AWAITING_MEDICAL_REVIEW = "awaiting_medical_review"
    SCRIPT_APPROVED = "script_approved"
    PRODUCING = "producing"
    RENDERED = "rendered"
    AWAITING_VIDEO_REVIEW = "awaiting_video_review"
    APPROVED_TO_PUBLISH = "approved_to_publish"
    PUBLISHED = "published"


ORDER = list(ProjectState)


class ProjectManifest(BaseModel):
    schema_version: str = "1.0"
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    language: str = "vi"
    state: ProjectState = ProjectState.IDEA
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


def transition(project: ProjectManifest, target: ProjectState) -> ProjectManifest:
    current_index = ORDER.index(project.state)
    if current_index + 1 >= len(ORDER) or ORDER[current_index + 1] is not target:
        raise ValueError(f"Invalid transition: {project.state} -> {target}")
    return project.model_copy(update={"state": target})
```

`write_yaml_atomic` phải tạo thư mục cha, ghi UTF-8 vào file cùng thư mục có hậu tố `.tmp`, flush và `os.fsync`, rồi gọi `os.replace`. `sha256_file` đọc từng block 64 KiB. `read_yaml` trả về dictionary và từ chối root không phải mapping.

- [ ] **Step 4: Chạy test và lint**

Run: `python -m pytest tests/domain/test_project.py tests/storage/test_files.py -v`

Run: `python -m ruff check src tests`

Expected: PASS.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 2 thành `complete`, ghi hai lệnh pytest đã PASS và commit mới vào hàng Task 2; đặt `Trạng thái hiện tại` là “Project state và storage nguyên tử đã hoạt động”.

```bash
git add src/healthvideo/domain src/healthvideo/storage tests/domain tests/storage README.md
git commit -m "feat: add project state and atomic storage"
```

---

### Task 3: Project scaffold và author-owned voice

**Files:**
- Create: `src/healthvideo/domain/author.py`
- Create: `src/healthvideo/workflows/__init__.py`
- Create: `src/healthvideo/workflows/create_project.py`
- Create: `profiles/author-voice.vi.yaml`
- Create: `profiles/brand.vi.yaml`
- Create: `profiles/evidence-policy.yaml`
- Modify: `src/healthvideo/cli.py`
- Test: `tests/workflows/test_create_project.py`
- Test: `tests/test_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `ProjectManifest`, `write_yaml_atomic`.
- Produces: `AuthorBrief`, `create_project(root, slug, title) -> Path`; CLI `healthvideo project new`.

- [ ] **Step 1: Viết test scaffold thất bại**

```python
# tests/workflows/test_create_project.py
from healthvideo.storage.files import read_yaml
from healthvideo.workflows.create_project import create_project


def test_create_project_writes_author_brief_and_manifest(tmp_path) -> None:
    project_dir = create_project(tmp_path, "muoi-va-huyet-ap", "Ăn mặn và tăng huyết áp")
    assert read_yaml(project_dir / "project.yaml")["state"] == "idea"
    brief = read_yaml(project_dir / "author-brief.yaml")
    assert brief["title"] == "Ăn mặn và tăng huyết áp"
    assert brief["personal_position"] == ""
    assert (project_dir / "script").is_dir()
    assert (project_dir / "reviews").is_dir()
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/workflows/test_create_project.py -v`

Expected: FAIL vì workflow chưa tồn tại.

- [ ] **Step 3: Tạo model và workflow**

```python
# src/healthvideo/domain/author.py
from pydantic import BaseModel, Field


class AuthorBrief(BaseModel):
    schema_version: str = "1.0"
    title: str
    why_speak: str = ""
    personal_position: str = ""
    desired_audience_action: str = ""
    emotion: str = "điềm tĩnh, thẳng thắn"
    phrases_to_keep: list[str] = Field(default_factory=list)
```

`create_project` phải từ chối slug đã tồn tại, tạo các thư mục `trend`, `evidence`, `script`, `storyboard`, `handoffs`, `audio`, `assets`, `renders`, `reviews`, `voice-learning`, `publish`, rồi ghi `project.yaml` và `author-brief.yaml`. CLI nhận `--root`, mặc định `projects/YYYY/MM` theo giờ địa phương.

`author-voice.vi.yaml` phải chứa `pronouns: {self: "tôi", audience: "bạn"}`, `directness: clear_and_calm`, danh sách từ tránh gồm “hãy cùng tìm hiểu”, “bí mật”, “sốc”, “100%”, và quy tắc không bịa trải nghiệm cá nhân. Brand profile đặt 1080 × 1920, 30 fps, nền trắng ngà, chữ than, vàng làm màu highlight. Evidence policy bắt buộc `claim_id` cho câu bằng chứng.

- [ ] **Step 4: Chạy test CLI và workflow**

Run: `python -m pytest tests/workflows/test_create_project.py tests/test_cli.py -v`

Expected: PASS; chạy lệnh hai lần với cùng slug phải báo rõ dự án đã tồn tại và không ghi đè.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 3 thành `complete`, ghi test workflow/CLI đã PASS và mô tả ngắn vị trí `author-brief.yaml`.

```bash
git add src/healthvideo profiles tests/workflows tests/test_cli.py README.md
git commit -m "feat: scaffold projects from doctor briefs"
```

---

### Task 4: Claim ledger, human script và read-aloud QA

**Files:**
- Create: `src/healthvideo/domain/evidence.py`
- Create: `src/healthvideo/domain/script.py`
- Create: `src/healthvideo/qa/__init__.py`
- Create: `src/healthvideo/qa/script.py`
- Create: `schemas/evidence.schema.json`
- Create: `schemas/author-brief.schema.json`
- Create: `schemas/script.schema.json`
- Create: `tools/export_schemas.py`
- Test: `tests/domain/test_script.py`
- Test: `tests/qa/test_script_qa.py`
- Test: `tests/contracts/test_schemas.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `AuthorBrief`.
- Produces: `EvidenceClaim`, `SourceRecord`, `Delivery`, `ScriptLine`, `Script`; `review_script(script, claims, forbidden_phrases) -> list[QAIssue]`.

- [ ] **Step 1: Viết test domain và QA thất bại**

```python
# tests/qa/test_script_qa.py
from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Delivery, Script, ScriptLine
from healthvideo.qa.script import review_script


def test_qa_rejects_unmapped_claim_and_machine_phrase() -> None:
    script = Script(title="Muối", lines=[ScriptLine(
        id="L01",
        text="Hãy cùng tìm hiểu: ăn mặn chắc chắn gây bệnh [1].",
        claim_id="C99",
        source_marker="[1]",
        delivery=Delivery(intent="problem"),
    )])
    issues = review_script(script, [EvidenceClaim(
        id="C01", text_public="Giảm muối giúp hạ huyết áp", text_technical="Reduced sodium lowers BP",
        type="evidence", sources=["R01"],
    )], ["hãy cùng tìm hiểu"])
    assert {issue.code for issue in issues} == {"forbidden_phrase", "unknown_claim"}
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/domain/test_script.py tests/qa/test_script_qa.py -v`

Expected: FAIL vì model và QA chưa tồn tại.

- [ ] **Step 3: Cài model và quy tắc QA**

`EvidenceClaim.type` dùng `Literal["evidence", "interpretation", "professional_opinion"]`; `SourceRecord` chứa `id`, `title`, `authors`, `year`, `study_design`, `sample_size`, `doi`, `pmid`, `url`. `Delivery` chứa `intent`, `pace` mặc định `normal`, `pause_before_ms`, `pause_after_ms`, `emphasis_words`, `emotional_color`. `ScriptLine` chứa `id`, `text`, `claim_id`, `source_marker`, `delivery`; `Script` chứa `title`, `language="vi"`, `lines`.

```python
# src/healthvideo/qa/script.py
from pydantic import BaseModel

from healthvideo.domain.evidence import EvidenceClaim
from healthvideo.domain.script import Script


class QAIssue(BaseModel):
    code: str
    line_id: str
    message: str


def review_script(
    script: Script,
    claims: list[EvidenceClaim],
    forbidden_phrases: list[str],
) -> list[QAIssue]:
    known = {claim.id for claim in claims}
    issues: list[QAIssue] = []
    for line in script.lines:
        lowered = line.text.casefold()
        for phrase in forbidden_phrases:
            if phrase.casefold() in lowered:
                issues.append(QAIssue(code="forbidden_phrase", line_id=line.id, message=phrase))
        if line.claim_id and line.claim_id not in known:
            issues.append(QAIssue(code="unknown_claim", line_id=line.id, message=line.claim_id))
        if len(line.text.split()) > 32:
            issues.append(QAIssue(code="long_spoken_sentence", line_id=line.id, message="over 32 words"))
    return issues
```

`tools/export_schemas.py` phải gọi `model_json_schema()` và ghi JSON UTF-8 có sort key. Contract test chạy exporter vào `tmp_path`, đọc từng schema và xác nhận `$defs` cùng `schema_version` tồn tại. Commit cả schema đã xuất để TypeScript dùng mà không chạy Python.

- [ ] **Step 4: Chạy domain, QA và contract tests**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/domain/test_script.py tests/qa/test_script_qa.py tests/contracts/test_schemas.py -v`

Expected: PASS; lần chạy exporter thứ hai không tạo Git diff.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 4 thành `complete`, ghi các rule QA đã có và kết quả domain/QA/contract tests.

```bash
git add src/healthvideo/domain src/healthvideo/qa schemas tools tests/domain tests/qa tests/contracts README.md
git commit -m "feat: validate evidence-linked human scripts"
```

---

### Task 5: Storyboard, evidence highlight và render contract

**Files:**
- Create: `src/healthvideo/domain/storyboard.py`
- Create: `src/healthvideo/render/__init__.py`
- Create: `src/healthvideo/render/input.py`
- Create: `schemas/storyboard.schema.json`
- Create: `schemas/render-input.schema.json`
- Modify: `tools/export_schemas.py`
- Test: `tests/render/test_input.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Script`, claim/source dictionaries, media paths.
- Produces: `Storyboard`, `Scene`, `EvidenceHighlight`, `RenderInput`, `build_render_input(...) -> RenderInput`.

- [ ] **Step 1: Viết test render contract thất bại**

```python
# tests/render/test_input.py
from healthvideo.domain.storyboard import EvidenceHighlight, Scene, Storyboard
from healthvideo.render.input import build_render_input


def test_highlight_requires_source_marker_and_quote() -> None:
    board = Storyboard(title="Muối", scenes=[Scene(
        id="S01", start_frame=0, duration_frames=150, narration="Một nghiên cứu...",
        source_marker="[1]", visual="evidence_highlight",
        evidence_highlight=EvidenceHighlight(
            image="assets/paper-r01.png", quote="giảm huyết áp tâm thu", x=0.12, y=0.42, width=0.64, height=0.08,
        ),
    )])
    result = build_render_input(board, audio_file="audio/narration.wav")
    assert result.width == 1080
    assert result.height == 1920
    assert result.scenes[0].evidence_highlight.quote == "giảm huyết áp tâm thu"
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/render/test_input.py -v`

Expected: FAIL vì storyboard chưa tồn tại.

- [ ] **Step 3: Cài contract bất biến**

`Scene` phải kiểm tra `start_frame >= 0`, `duration_frames > 0`, `visual` thuộc `whiteboard|chart|evidence_highlight|ai_clip`. Tọa độ highlight nằm trong `[0,1]`; `x + width <= 1`, `y + height <= 1`. Cảnh `evidence_highlight` bắt buộc có `source_marker`, `quote` và ảnh. `RenderInput` đặt `width=1080`, `height=1920`, `fps=30`, nhận `audio_file` và danh sách scene. Model dùng `frozen=True` để renderer không sửa dữ liệu.

`build_render_input` kiểm tra scene nối tiếp, không chồng, tổng frame trong 45–90 giây và mọi đường dẫn là đường dẫn tương đối POSIX; nếu sai, ném `ValueError` có scene ID.

- [ ] **Step 4: Xuất schema và chạy test**

Run: `python tools/export_schemas.py`

Run: `python -m pytest tests/render/test_input.py tests/contracts/test_schemas.py -v`

Expected: PASS.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 5 thành `complete`, ghi contract 1080 × 1920, 30 fps, 45–90 giây và test đã PASS.

```bash
git add src/healthvideo/domain/storyboard.py src/healthvideo/render schemas tools/export_schemas.py tests/render tests/contracts README.md
git commit -m "feat: define storyboard render contract"
```

---

### Task 6: Remotion composition 9:16 và visual regression cơ bản

**Files:**
- Create: `pnpm-workspace.yaml`
- Create: `video/package.json`
- Create: `video/tsconfig.json`
- Create: `video/src/index.ts`
- Create: `video/src/Root.tsx`
- Create: `video/src/types.ts`
- Create: `video/src/HealthVideo.tsx`
- Create: `video/src/scenes/WhiteboardScene.tsx`
- Create: `video/src/scenes/EvidenceHighlightScene.tsx`
- Create: `video/src/components/Captions.tsx`
- Create: `video/src/timing.test.ts`
- Modify: `README.md`

**Interfaces:**
- Consumes: `RenderInput` JSON từ Task 5.
- Produces: Remotion composition ID `HealthVideo`; command `pnpm --dir video render --props projects/sample/render-input.json --output projects/sample/renders/video.mp4`.

- [ ] **Step 1: Viết timing test thất bại**

```typescript
// video/src/timing.test.ts
import {describe, expect, it} from 'vitest';
import {activeSceneIndex} from './HealthVideo';

describe('activeSceneIndex', () => {
  it('selects the scene that owns the current frame', () => {
    const scenes = [
      {id: 'S01', start_frame: 0, duration_frames: 90},
      {id: 'S02', start_frame: 90, duration_frames: 60},
    ];
    expect(activeSceneIndex(scenes, 0)).toBe(0);
    expect(activeSceneIndex(scenes, 89)).toBe(0);
    expect(activeSceneIndex(scenes, 90)).toBe(1);
  });
});
```

- [ ] **Step 2: Cài Node dependencies và xác nhận test thất bại**

`video/package.json` khóa `remotion`, `@remotion/cli`, `@remotion/renderer` ở `4.0.522`; `react` và `react-dom` ở `19.2.8`; `zod` ở `4.5.4`; dev dependencies `typescript==7.0.2`, `vitest==5.0.0`, `@types/react==19.2.18`. Scripts gồm `test`, `typecheck`, `render`.

Run: `pnpm install`

Run: `pnpm --dir video test`

Expected: FAIL vì `HealthVideo` chưa tồn tại.

- [ ] **Step 3: Tạo composition và scene**

```typescript
// video/src/HealthVideo.tsx
import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import type {RenderInput, SceneTiming} from './types';

export const activeSceneIndex = (scenes: SceneTiming[], frame: number): number =>
  scenes.findIndex((scene) => frame >= scene.start_frame && frame < scene.start_frame + scene.duration_frames);

export const HealthVideo: React.FC<RenderInput> = ({audio_file, scenes}) => (
  <AbsoluteFill style={{backgroundColor: '#FFFDF7', color: '#202124'}}>
    <Audio src={staticFile(audio_file)} />
    {scenes.map((scene) => (
      <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
        {scene.visual === 'evidence_highlight'
          ? <EvidenceHighlightScene scene={scene} />
          : <WhiteboardScene scene={scene} />}
      </Sequence>
    ))}
  </AbsoluteFill>
);
```

`EvidenceHighlightScene` dùng `interpolate` để tăng chiều rộng lớp vàng từ 0 đến `width` trong 18 frame, đặt theo tọa độ chuẩn hóa, render ảnh bằng `Img`, quote và `[n]`. `WhiteboardScene` vẽ đường SVG bằng `strokeDashoffset`. `Captions` giới hạn hai dòng và highlight từ đang đọc. `Root.tsx` tính `durationInFrames` từ scene cuối, đăng ký composition 1080 × 1920, 30 fps.

- [ ] **Step 4: Chạy test, typecheck và render frame mẫu**

Run: `pnpm --dir video test`

Run: `pnpm --dir video typecheck`

Run: `pnpm --dir video exec remotion still src/index.ts HealthVideo tests/fixtures/render-input.json tests/artifacts/frame-001.png --frame=120`

Expected: test/typecheck PASS; PNG 1080 × 1920 có nền trắng ngà, chữ than và highlight vàng.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 6 thành `complete`; nhúng đường dẫn đến frame mẫu, ghi test/typecheck và lệnh render still đã chạy.

```bash
git add pnpm-workspace.yaml pnpm-lock.yaml video tests/fixtures/render-input.json README.md
git commit -m "feat: render vertical whiteboard scenes"
```

---

### Task 7: TTS giả lập, manifest cache và render workflow

**Files:**
- Create: `src/healthvideo/tts/__init__.py`
- Create: `src/healthvideo/tts/base.py`
- Create: `src/healthvideo/tts/silent.py`
- Create: `src/healthvideo/render/remotion.py`
- Create: `src/healthvideo/workflows/produce.py`
- Create: `tests/__init__.py`
- Create: `tests/helpers.py`
- Modify: `src/healthvideo/cli.py`
- Test: `tests/tts/test_silent.py`
- Test: `tests/workflows/test_produce.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: approved project, `Script`, `Storyboard`.
- Produces: `TTSProvider.synthesize(request, output) -> TTSResult`; `SilentTTS`; `produce_project(project_dir, tts, runner) -> Path`; CLI `healthvideo produce`.

- [ ] **Step 1: Viết test TTS và cache thất bại**

```python
# tests/tts/test_silent.py
import wave

from healthvideo.tts.base import TTSRequest
from healthvideo.tts.silent import SilentTTS


def test_silent_tts_writes_deterministic_wav(tmp_path) -> None:
    output = tmp_path / "narration.wav"
    result = SilentTTS().synthesize(TTSRequest(text="Xin chào bạn", language="vi"), output)
    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1
    assert result.duration_ms > 0
    assert result.provider == "silent"
```

```python
# tests/workflows/test_produce.py
from healthvideo.tts.silent import SilentTTS
from healthvideo.workflows.produce import produce_project
from tests.helpers import create_project_fixture


def test_produce_reuses_matching_artifact_hash(tmp_path) -> None:
    project_dir = create_project_fixture(tmp_path, state="script_approved")
    calls: list[list[str]] = []

    def fake_runner(argv: list[str]) -> int:
        calls.append(argv)
        output = project_dir / "renders" / "video.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"synthetic-mp4")
        return 0

    first = produce_project(project_dir, SilentTTS(), fake_runner)
    second = produce_project(project_dir, SilentTTS(), fake_runner)
    assert first == second
    assert len(calls) == 1
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/tts/test_silent.py tests/workflows/test_produce.py -v`

Expected: FAIL vì protocol và workflow chưa tồn tại.

- [ ] **Step 3: Cài provider và workflow**

`TTSRequest` chứa `text`, `language`, `speed=1.0`, delivery beats; `TTSResult` chứa `provider`, `audio_file`, `duration_ms`, `word_timestamps`. `SilentTTS` dùng thư viện `wave`, mono PCM 16-bit 24 kHz; thời lượng bằng `max(1000, round(word_count / 2.7 * 1000))`. Nó tạo silence, không phát tone.

`produce_project` chỉ nhận trạng thái `script_approved`; tính SHA-256 trên canonical JSON của script, storyboard, profile và tên provider. Nếu manifest có cùng hash và output tồn tại, trả output không gọi runner. Nếu khác, tạo WAV, `render-input.json`, gọi runner bằng argv list, kiểm tra exit code và file MP4, rồi chuyển trạng thái qua `producing` đến `rendered` và `awaiting_video_review`. Không dùng `shell=True`.

`tests/helpers.py` cung cấp `create_project_fixture(root: Path, state: str) -> Path`. Helper tạo đủ `project.yaml`, `author-brief.yaml`, một claim synthetic, script sáu câu, storyboard sáu cảnh liên tiếp tổng 1.350 frame và các thư mục workflow; mọi task sau dùng helper này thay vì fixture ẩn.

- [ ] **Step 4: Chạy test và CLI dry run**

Run: `python -m pytest tests/tts/test_silent.py tests/workflows/test_produce.py -v`

Run: `healthvideo produce tests/fixtures/golden-project --tts silent --dry-run`

Expected: PASS; dry run in lệnh Remotion nhưng không tạo MP4 và không đổi trạng thái.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 7 thành `complete`, ghi rõ TTS hiện là silence dành cho test và cache render đã được xác minh.

```bash
git add src/healthvideo/tts src/healthvideo/render src/healthvideo/workflows/produce.py src/healthvideo/cli.py tests/tts tests/workflows README.md
git commit -m "feat: add cached production workflow"
```

---

### Task 8: Hai cổng duyệt có hash và audit trail

**Files:**
- Create: `src/healthvideo/domain/review.py`
- Create: `src/healthvideo/workflows/review.py`
- Modify: `src/healthvideo/cli.py`
- Test: `tests/workflows/test_review.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: project state, artifact paths, reviewer name and decision.
- Produces: `ReviewRecord`; `approve_medical(...)`; `approve_video(...)`; CLI `healthvideo review medical|video`.

- [ ] **Step 1: Viết test gate thất bại**

```python
# tests/workflows/test_review.py
import pytest

from healthvideo.workflows.review import approve_medical, approve_video
from tests.helpers import create_project_fixture


def test_medical_approval_binds_script_and_evidence_hash(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="awaiting_medical_review")
    record = approve_medical(project, reviewer="BS An", note="Đã đối chiếu số liệu")
    assert set(record.artifact_hashes) == {"evidence", "script"}
    assert record.decision == "approved"


def test_video_cannot_be_approved_before_render(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="awaiting_medical_review")
    with pytest.raises(ValueError, match="awaiting_video_review"):
        approve_video(project, reviewer="BS An", note="")
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/workflows/test_review.py -v`

Expected: FAIL vì review workflow chưa tồn tại.

- [ ] **Step 3: Cài review record và lệnh duyệt**

`ReviewRecord` chứa UUID, `kind`, `decision`, `reviewer`, timezone-aware `reviewed_at`, `artifact_hashes`, `note`. Medical review chỉ chạy ở `awaiting_medical_review`, hash `evidence/ledger.yaml` và `script/script.yaml`, ghi đường dẫn Python `reviews / f"medical-{record.id}.yaml"`, rồi chuyển `script_approved`. Video review chỉ chạy ở `awaiting_video_review`, hash MP4 và `render-input.json`, ghi `reviews / f"video-{record.id}.yaml"`, rồi chuyển `approved_to_publish`.

Nếu artifact đổi sau duyệt, lệnh `status` báo `approval_stale=true`; `produce` và `package` từ chối chạy. CLI bắt buộc `--reviewer`, nhận `--note`, và yêu cầu gõ `APPROVE` trên terminal trừ khi có `--yes`.

- [ ] **Step 4: Chạy test review và state machine**

Run: `python -m pytest tests/workflows/test_review.py tests/domain/test_project.py -v`

Expected: PASS.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 8 thành `complete`, ghi hai gate đã được cưỡng chế và test approval stale đã PASS.

```bash
git add src/healthvideo/domain/review.py src/healthvideo/workflows/review.py src/healthvideo/cli.py tests/workflows/test_review.py README.md
git commit -m "feat: enforce doctor review gates"
```

---

### Task 9: Gói xuất bản và golden end-to-end test

**Files:**
- Create: `src/healthvideo/workflows/package.py`
- Create: `tests/fixtures/golden-project/project.yaml`
- Create: `tests/fixtures/golden-project/author-brief.yaml`
- Create: `tests/fixtures/golden-project/evidence/ledger.yaml`
- Create: `tests/fixtures/golden-project/script/script.yaml`
- Create: `tests/fixtures/golden-project/storyboard/storyboard.yaml`
- Create: `tests/e2e/test_golden_project.py`
- Modify: `src/healthvideo/cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: project ở `approved_to_publish`, video review còn hiệu lực.
- Produces: `publish/video.mp4`, `publish/caption.txt`, `publish/sources.md`, `publish/manifest.json`; CLI `healthvideo package`.

- [ ] **Step 1: Viết end-to-end test thất bại**

```python
# tests/e2e/test_golden_project.py
from healthvideo.workflows.package import package_project
from tests.helpers import create_project_fixture


def test_package_contains_video_caption_sources_and_manifest(tmp_path) -> None:
    project = create_project_fixture(tmp_path, state="approved_to_publish")
    output = package_project(project)
    assert (output / "video.mp4").exists()
    assert "[1]" in (output / "caption.txt").read_text(encoding="utf-8")
    assert "R01" in (output / "sources.md").read_text(encoding="utf-8")
    assert '"approval_stale": false' in (output / "manifest.json").read_text(encoding="utf-8")
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/e2e/test_golden_project.py -v`

Expected: FAIL vì packaging workflow chưa tồn tại.

- [ ] **Step 3: Cài packaging và fixture tiếng Việt**

`package_project` kiểm tra state, review hash và sự tồn tại của MP4; tạo thư mục tạm, copy bằng `shutil.copy2`, sinh caption gồm hook ngắn, disclaimer thông tin chung và danh sách `[n]`; sinh `sources.md` với tiêu đề, tác giả, năm, DOI/PMID/URL; sinh manifest gồm SHA-256 của bốn file; đổi tên thư mục tạm sang `publish` bằng thao tác nguyên tử khi cùng volume. Hàm không gọi API đăng bài.

Golden fixture dùng chủ đề muối và huyết áp, một claim bằng chứng, một câu `professional_opinion`, sáu scene dài tổng cộng 45 giây, một evidence highlight và một biểu đồ đơn giản. Dữ liệu nghiên cứu trong fixture phải được gắn nhãn `synthetic_test_record: true` để không bị hiểu là bằng chứng thật.

README hướng dẫn chuỗi lệnh local từ `project new` đến `package`, giải thích hai gate, vị trí artifact và giới hạn của silent TTS.

- [ ] **Step 4: Chạy toàn bộ test và lint**

Run: `python -m pytest -v`

Run: `python -m ruff check src tests tools`

Run: `pnpm --dir video test`

Run: `pnpm --dir video typecheck`

Expected: tất cả PASS; `git status --short` chỉ hiện file đầu ra đã được ignore.

- [ ] **Step 5: Cập nhật README và commit**

Đổi Task 9 thành `complete`, cập nhật `Quick start`, ghi kết quả full test và bốn file của gói xuất bản.

```bash
git add src/healthvideo/workflows/package.py src/healthvideo/cli.py tests/fixtures tests/e2e README.md
git commit -m "feat: package reviewed videos for publishing"
```

---

### Task 10: Installer Windows và environment doctor

**Files:**
- Create: `install/install.ps1`
- Create: `install/doctor.ps1`
- Create: `src/healthvideo/workflows/doctor.py`
- Modify: `src/healthvideo/cli.py`
- Test: `tests/workflows/test_doctor.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: PATH và phiên bản runtime.
- Produces: `check_environment(run) -> list[CheckResult]`; CLI `healthvideo doctor`; scripts cài đặt PowerShell idempotent.

- [ ] **Step 1: Viết test doctor thất bại**

```python
# tests/workflows/test_doctor.py
from healthvideo.workflows.doctor import check_environment


def test_doctor_reports_missing_ffmpeg() -> None:
    def fake_run(argv: list[str]) -> tuple[int, str]:
        return (1, "not found") if argv[0] == "ffmpeg" else (0, "24.14.0")

    results = check_environment(fake_run)
    ffmpeg = next(item for item in results if item.name == "ffmpeg")
    assert ffmpeg.ok is False
    assert "FFmpeg 8" in ffmpeg.remedy
```

- [ ] **Step 2: Chạy test để xác nhận thất bại**

Run: `python -m pytest tests/workflows/test_doctor.py -v`

Expected: FAIL vì doctor workflow chưa tồn tại.

- [ ] **Step 3: Cài doctor và installer**

`check_environment` kiểm tra Python >=3.11, Node >=22, pnpm >=11, FFmpeg >=8, font `Arial` hoặc `Noto Sans`, và CUDA chỉ ở mức cảnh báo. Mỗi `CheckResult` có `name`, `ok`, `detected`, `required`, `remedy`. CLI trả exit code 1 nếu thiếu dependency bắt buộc.

`install/install.ps1` dùng `$ErrorActionPreference = 'Stop'`, xác nhận đang ở repo bằng `pyproject.toml`, tạo `.venv`, chạy `.venv\Scripts\python -m pip install -e ".[dev]"`, `pnpm install --frozen-lockfile`, rồi `.venv\Scripts\healthvideo doctor`. Script không tự cài driver, không sửa PATH hệ thống và không ghi secret. `doctor.ps1` chỉ gọi CLI trong venv.

- [ ] **Step 4: Chạy kiểm thử và smoke test sạch**

Run: `python -m pytest tests/workflows/test_doctor.py -v`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File install/doctor.ps1`

Expected: test PASS; máy hiện tại báo Python 3.14.3, Node 24.14.0, pnpm 11.19.0 và FFmpeg 8.1.1 đạt yêu cầu.

- [ ] **Step 5: Kiểm tra cuối, cập nhật README và commit**

Run: `python -m pytest -v`

Run: `python -m ruff check src tests tools`

Run: `pnpm --dir video test && pnpm --dir video typecheck`

Run: `git diff --check`

Expected: tất cả PASS.

Đổi Task 10 và milestone MVP thành `complete`; ghi phiên bản runtime đã phát hiện, bốn lệnh kiểm tra cuối, ngày chạy và tóm tắt giới hạn còn lại. `Trạng thái hiện tại` phải chỉ tới plan tiếp theo `evidence-ingestion`.

```bash
git add install src/healthvideo/workflows/doctor.py src/healthvideo/cli.py tests/workflows/test_doctor.py README.md
git commit -m "feat: add Windows installer and diagnostics"
```

---

## MVP exit criteria

- Tạo được dự án mới và thu `author brief` mà không cần LLM.
- Kịch bản lưu được nhịp, khoảng dừng, từ nhấn, claim ID và source marker.
- QA phát hiện cụm từ máy móc, claim lạ, câu nói quá dài và approval hết hiệu lực.
- Render được một video 1080 × 1920 có whiteboard, subtitle và bôi vàng bằng chứng.
- Có silent TTS xác định để test; kiến trúc sẵn sàng thay bằng VieNeu-TTS hoặc ElevenLabs.
- Không thể sản xuất trước duyệt y khoa hoặc đóng gói trước duyệt video.
- Lần chạy lại không gọi renderer khi hash đầu vào không đổi.
- Cài và kiểm tra được trên máy Windows hiện tại; toàn bộ test chạy không cần mạng.

## Các plan tiếp theo sau MVP

1. `evidence-ingestion`: PubMed, Europe PMC, Scopus intake, DOI/PMID validation và claim ledger có provenance.
2. `ai-editorial-routing`: gói context Codex/Claude, risk routing, delta patch và token ledger.
3. `tts-providers`: benchmark mù VieNeu-TTS, VoiceStudio, ElevenLabs; từ điển phát âm và ASR back-check.
4. `trend-discovery`: inbox TikTok/Google Trends/YouTube/RSS, deduplication và lịch năm video/tuần.
5. `advanced-visuals`: biểu đồ động, PDF crop/highlight kiểm chứng, Veo adapter và license inventory.
6. `multi-machine-hardening`: Linux installer, Syncthing/NAS guide, backup, recovery và security review.
