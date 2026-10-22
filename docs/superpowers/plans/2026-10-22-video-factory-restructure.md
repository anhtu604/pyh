# Xưởng video PYH — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cắt gọt `healthvideo` thành xưởng video một người vận hành: 4 giai đoạn, hàng đợi chủ đề chạy tự động tới hai cổng duyệt của bác sĩ.

**Architecture:** Giữ lõi (bằng chứng, hai cổng, revision/invalidation, TTS VieNeu, Remotion). Xóa phần đa người dùng/legacy/nhánh phụ theo từng lát, test xanh sau mỗi lát. Thêm `healthvideo run`: Python tự chạy bước cố định, gọi Codex/agy cho bước viết/phán đoán, tự đổi agent khi hết quota, dừng ở cổng. Lệnh duyệt cổng đòi PIN gõ tay.

**Tech Stack:** Python ≥3.11, Typer, Pydantic 2, PyYAML, pytest, Ruff; Remotion 4 + Vitest (pnpm); VieNeu TTS; FLUX.2 [klein] 4B; ACE-Step 1.5; Codex CLI; Antigravity `agy`.

**Spec:** `docs/superpowers/specs/2026-10-22-video-factory-restructure-design.md`

## Theo dõi tiến độ

| Giai đoạn | Nội dung | Task | Trạng thái |
|---|---|---|---|
| P0 | Hoàn tất việc dở (A/V sync) | 0.1 | ☐ |
| P1 | Dọn rác + tài liệu | 1.1–1.3 | ☐ |
| P2 | Cắt code | 2.1–2.8 | ☐ |
| P3 | Hàng đợi, `run`, PIN | 3.1–3.6 | ☐ |
| P4 | Giai đoạn 2 mới: FLUX, nhạc, thư viện SVG | 4.1–4.3 | ☐ |
| P5 | Giai đoạn 1 mới: tìm chủ đề | 5.1 | ☐ |
| P6 | Giai đoạn 4 mới: bài đăng đa kênh | 6.1–6.2 | ☐ |
| P7 | Chạy thật một chủ đề A–Z | 7.1 | ☐ |

Cập nhật cột "Trạng thái" và bảng tiến độ trong `README.md` trong cùng commit của mỗi task.

## Global Constraints

- Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, trải nghiệm bác sĩ.
- Không vượt cổng duyệt y khoa/video; không tự động xuất bản.
- Không lưu API key, audio tạm, render, cache, toàn văn có bản quyền vào Git.
- Dùng `pathlib.Path` cho đường dẫn nội bộ; lệnh phải chạy trong PowerShell 5.1.
- Mỗi commit: test liên quan + Ruff xanh, kèm một dòng bảng tiến độ `README.md`; `git add <paths>`, không `-a`.
- Lệnh kiểm chung (gọi là **CHECK** bên dưới):
  `rtk proxy .venv\Scripts\python -m pytest -q` (PYTHONPATH=src), `.venv\Scripts\ruff check src tests`,
  và khi đụng `video/`: `corepack pnpm --dir video test`, `corepack pnpm --dir video typecheck`.
- GPU RTX 3060 12 GB: mô hình local (VieNeu, FLUX, ACE-Step) chạy tuần tự.
- Chỉ dùng mô hình/công cụ có giấy phép cho dùng thương mại: FLUX.2 [klein] **4B** (Apache-2.0), không dùng 9B/dev.
- `agy` luôn chạy `--model gemini-4-argon-medium`.
- Executor (Codex/agy) không commit; Claude rà diff rồi commit.

## Quyết định của kế hoạch (bổ sung spec)

- **Giữ tên trạng thái hiện có** thay vì đổi tên theo sơ đồ spec §5 (tránh churn dữ liệu và test): `topic_selected`≙queued, `research_in_progress`≙researching, `production_in_progress`≙producing. Giữ hai trạng thái sửa `needs_medical_revision` / `needs_production_revision` vì chúng định tuyến khác nhau. Xóa: `orientation_research_in_progress`, `awaiting_editorial_direction`, `author_brief_ready`, `awaiting_browser_login`, `awaiting_second_model_review`.
- **Code do agent viết trong `run`** không được commit và không tách nhánh: `run` ghi danh sách file code thay đổi (ngoài `projects/`) vào `topics/code-review.yaml` để Claude rà theo lô. (Spec §6 nói "nhánh riêng"; bản này đơn giản hơn. Nâng cấp lên worktree theo chủ đề nếu hai chủ đề cùng sửa code đụng nhau.)
- **PIN**: lưu băm scrypt ở `Path.home() / ".healthvideo" / "approver-pin.json"`; `review approve` và `review set-pin` chỉ chạy khi `sys.stdin.isatty()` và đọc PIN bằng `getpass`. Không có cờ hay biến môi trường nào truyền PIN.

## Review Focus

1. Agent bị cắt giữa bước (hết quota, tắt máy) → chạy lại `run` phải làm lại đúng bước đó, không nhảy trạng thái, không nhân đôi file. (Task 3.3, 3.5)
2. Cả Codex và agy đều hết quota → `run` dừng, in rõ "cả hai agent hết quota", trạng thái chủ đề không đổi. (Task 3.4)
3. `review approve` chạy không có TTY (từ agent/script) hoặc chưa đặt PIN → từ chối, không ghi record. (Task 3.1)
4. Thẻ hàng đợi trùng slug với project đã có → không ghi đè, báo lỗi. (Task 3.2)
5. Bài đăng có số liệu không trỏ tới claim đã duyệt y khoa → chặn trước cổng video. (Task 6.1)

---

## P0 — Hoàn tất việc dở

### Task 0.1: Rà và commit bản sửa A/V sync/chart/motion/phụ đề

**Files:** 25 file đang sửa trong working tree + `src/healthvideo/render/timing.py`, `tests/render/test_timing.py`, `video/src/scenes/MechanismScene.motion.test.tsx` (chưa track).

- [ ] **Step 1:** Claude rà diff (`git diff`, file mới) so với dòng README "Video gate: sync, chart, motion, captions".
- [ ] **Step 2:** Chạy CHECK đủ cả phần video. Expected: pytest 1416 passed, 3 skipped; vitest 112 passed; typecheck sạch.
- [ ] **Step 3:** Commit `feat: sync narration timing and polish mechanism visuals` với các path cụ thể; cập nhật dòng README thành `complete`.

---

## P1 — Dọn rác + tài liệu

### Task 1.1: Dọn gốc repo

**Files:** Delete (không track/không thuộc dự án): `VoiceStudio-Electron-0.5.6-win-x64.exe`, `New Recording.m4a`, `.codex-tmp/`, `sample/`. Modify: `.gitignore`, `tests/test_gitignore.py`.

- [ ] **Step 1: Test** — trong `tests/test_gitignore.py` thêm `test_remotion_cache_is_ignored`: `git check-ignore .remotion/x` trả mã 0.
- [ ] **Step 2:** Chạy test, expected FAIL.
- [ ] **Step 3:** Thêm `.remotion/` vào `.gitignore`. Hỏi người dùng trước khi xóa `.worktrees/` (có thể còn worktree đang dùng: kiểm `git worktree list`); chỉ xóa worktree đã merge bằng `git worktree remove`.
- [ ] **Step 4:** CHECK xanh. Commit `chore: clean repo root and ignore remotion cache`.

### Task 1.2: Gom skill

**Files:** `.agents/skills/*`, `skills-lock.json`, `.claude/commands/`.

- [ ] **Step 1:** Lập danh sách skill được tham chiếu bởi `pyh`, prompt giai đoạn (P3) hoặc tài liệu vận hành: giữ `pyh`, `humanizer`, `remotion-*`, `motion-design`, `svg-character-animation`, `character-animation-qa`, `visual-style`, `video-understand`. Mọi skill khác (caveman*, cavecrew, migration, safe-refactor, surgical-patch…) chưa track → xóa khỏi `.agents/skills/`, gỡ khỏi `skills-lock.json`.
- [ ] **Step 2:** `healthvideo doctor` vẫn báo skill `pyh` OK; CHECK xanh. Commit `chore: keep only skills the factory uses`.

### Task 1.3: Lưu trữ tài liệu, README mới

**Files:** Move `docs/superpowers/specs/*` và `docs/superpowers/plans/*` (trừ hai file 2026-10-22 và `2026-10-18-explain-first-content-design.md`) → `docs/archive/`; move `docs/operations/m7-hardening-runbook.md` → `docs/archive/`. Rewrite `README.md`. Modify `CLAUDE.md`, `AGENTS.md`, `tests/` tham chiếu đường dẫn tài liệu cũ (`grep -rn "docs/superpowers\|m7-hardening" tests`).

- [ ] **Step 1:** Sửa test tham chiếu tài liệu (vd. `test_m7_runbook`) — xóa test đó cùng runbook (thuộc phần cắt P2.1) hoặc trỏ sang archive.
- [ ] **Step 2:** README mới ≤ 200 dòng: mục đích kênh, cài đặt (`install/install.ps1`), 4 giai đoạn, CLI đích (spec §7), cách duyệt cổng, bảng tiến độ **chỉ** cho kế hoạch này (bảng cũ chuyển vào `docs/archive/README-progress-2026-10.md`).
- [ ] **Step 3:** `CLAUDE.md` mục 1 và `AGENTS.md` mục 1 trỏ tới spec + plan 2026-10-22 thay cho 2026-09-07; `AGENTS.md` bỏ mục 7 (runbook M7) khi P2.1 xong — làm luôn ở đây và ghi chú.
- [ ] **Step 4:** CHECK xanh. Commit `docs: archive old specs and rewrite README for the factory`.

---

## P2 — Cắt code

Quy trình chung cho mỗi task P2: (1) thêm/sửa test khẳng định lệnh/trạng thái đã biến mất; (2) xóa module + test riêng của nó; (3) sửa chỗ import còn lại; (4) CHECK xanh; (5) commit `refactor: remove <phần>`. Không đổi hành vi của phần giữ lại; test e2e golden workflow phải vẫn qua sau khi bỏ bước đã cắt khỏi kịch bản test.

### Task 2.1: Bỏ lease, backup, security-audit, M7 doctor probes

**Files:** Delete `src/healthvideo/storage/lease.py`, `domain/lease.py`, `storage/backup.py`, `domain/backup.py`, `workflows/backup.py`, `security.py`, `workflows/operations.py` (nếu chỉ phục vụ lease), test tương ứng (`tests/test_security.py`, tests lease/backup). Modify `cli.py` (bỏ nhóm `lease`, `backup`, `security-audit`), `commands/operator.py`, `workflows/operator.py`, `workflows/doctor.py` (bỏ filesystem probe, giữ kiểm FFmpeg/Node/VieNeu/skill).

- [ ] **Test:** `tests/test_cli.py::test_removed_commands_absent` — parametrize `["lease","backup","security-audit"]`; `CliRunner().invoke(app, [cmd, "--help"])` có `exit_code != 0`.
- [ ] Xóa, sửa import, CHECK, commit `refactor: remove multi-writer lease, backup and security audit`.

### Task 2.2: Bỏ project v1, `migrate`, profile `legacy`

**Files:** Delete `domain/project.py`, `workflows/create_project.py`, `workflows/migrate.py`, `storage/project_layout.py` nhánh v1, test v1/migrate. Modify `cli.py`, `qa/script.py`, `workflows/{operator,package,produce,review}.py` để chỉ dùng `ProjectV2`/`transition_v2`; bỏ giá trị `legacy` của `content_profile` (mặc định explain-first) trong `domain/project_v2.py`, `domain/{script,storyboard,hook_outro}.py`, `render/input.py`, `workflows/{hook_outro,review_html}.py`.

**Interfaces:** Produces — mọi workflow nhận `ProjectV2`; `content_profile` chỉ còn một giá trị (xóa trường nếu không còn nơi đọc).

- [ ] **Test:** `test_removed_commands_absent` thêm `"migrate"`, `("project","create")`; test mới `tests/domain/test_project_v2.py::test_legacy_profile_rejected` (tải manifest `content_profile: legacy` → `ValidationError`) nếu trường còn tồn tại.
- [ ] Project thí điểm `projects/do-huyet-ap-khong-trieu-chung` (`content_profile: legacy`) không được chuyển đổi; ghi chú trong README rằng nó là bản thử cũ.
- [ ] CHECK, commit `refactor: drop v1 projects, migrate and legacy profile`.

### Task 2.3: Gộp orientation vào nghiên cứu, bỏ editorial direction / author brief

**Files:** Delete `workflows/orientation.py`, `domain/orientation.py`, `workflows/author.py`, `domain/author.py`, `tests/test_orientation_cli.py`, test orientation/author. Modify `domain/project_v2.py` (xóa 3 trạng thái), `domain/state_graph.py` (`topic_selected → research_in_progress` trực tiếp), `commands/operator.py` (bỏ `orientation*`, `brief`), `workflows/operator.py`, `workflows/evidence.py`, `domain/evidence.py` (bỏ tham chiếu orientation), `workflows/create_project_v2.py`.

- [ ] **Test:** `tests/domain/test_state_graph.py::test_topic_selected_goes_straight_to_research` — `transition_v2(project ở topic_selected, RESEARCH_IN_PROGRESS)` thành công; `WorkflowState` không còn 3 giá trị đã xóa.
- [ ] Giữ nguyên tìm PubMed/Europe PMC nhiều truy vấn tiếng Anh (`--query`) — chuyển cờ này sang `evidence search` nếu đang chỉ có ở orientation.
- [ ] CHECK, commit `refactor: fold orientation into research and drop author brief gate`.

### Task 2.4: Bỏ second-model review và browser login

**Files:** Delete `workflows/agent_review.py`, `domain/agent_review.py`, test. Modify `cli.py` (bỏ nhóm `agent`), `domain/project_v2.py`, `domain/state_graph.py` (xóa `AWAITING_SECOND_MODEL_REVIEW`, `AWAITING_BROWSER_LOGIN`).

- [ ] **Test:** `test_removed_commands_absent` thêm `"agent"`; enum không còn hai giá trị.
- [ ] CHECK, commit `refactor: remove second-model review and browser login states`.

### Task 2.5: Bỏ Veo / AI clip

**Files:** Delete `src/healthvideo/video_ai/`, `workflows/ai_clips.py`, `domain/ai_clip.py`, `tests/video_ai/`, `video/src/scenes/AiClipScene.tsx(+test)`. Modify `cli.py`, `domain/asset_manifest.py` (bỏ loại asset AI clip), `workflows/{gate_review,produce}.py`, `video/src/types.ts`, `video/src/HealthVideo.tsx`.

- [ ] **Test:** `test_removed_commands_absent` thêm lệnh Veo; `tests/contracts` không còn scene kind `ai_clip` (cập nhật schema export `tools/export_schemas.py`).
- [ ] CHECK (cả video), commit `refactor: remove Veo AI clip scenes`.

### Task 2.6: Bỏ `tts-benchmark`

**Files:** Delete `tts/benchmark.py`, test. Modify `cli.py`.

- [ ] Test `test_removed_commands_absent` thêm `"tts-benchmark"`. CHECK, commit `refactor: remove TTS benchmark`.

### Task 2.7: Thay visual budget + license ledger bằng trường giấy phép trong asset manifest

**Files:** Delete `domain/visual_budget.py`, `domain/license_ledger.py`, test. Modify `domain/asset_manifest.py`, `domain/storyboard.py`, `render/input.py`, `workflows/{draft,gate_review,produce,review_html,long_form,visual_assets}.py`.

**Interfaces:** Produces — mỗi `AssetEntry` có `license: str` (SPDX hoặc `"own"`/`"generated:flux2-klein-4b"`) và `source: str`; validator từ chối asset thiếu `license`. Gói duyệt video liệt kê giấy phép từng asset.

- [ ] **Test:** `tests/domain/test_asset_manifest.py::test_asset_requires_license` (thiếu `license` → `ValidationError`); `test_review_packet_lists_asset_licenses` trong `tests/workflows/test_gate_review.py`.
- [ ] Nếu gỡ visual budget làm hỏng kiểm tra tỷ lệ cảnh của explain-first (frame budget §T6), giữ phần frame budget explain-first, chỉ xóa phần ngân sách chi phí.
- [ ] CHECK (cả video), commit `refactor: replace visual budget and license ledger with asset license field`.

### Task 2.8: CLI đích + `/pyh` mới

**Files:** Modify `cli.py`, `commands/operator.py` (gộp vào nhóm ẩn `step`), `.agents/skills/pyh/SKILL.md`, `.claude/commands/pyh.md`, `install/`.

**Interfaces:** Produces — lệnh công khai: `topic discover|add|list`, `run`, `status [project]`, `review open|approve|reject|reopen|set-pin`, `preview`, `produce`, `package`, `doctor`. Lệnh nội bộ cho agent dưới `healthvideo step …` (`hidden=True`): `evidence-search`, `evidence-screen`, `build-ledger`, `draft`, `submit-medical`, `resume`.

- [ ] **Test:** `tests/test_cli.py::test_public_command_surface` — tập lệnh hiển thị trong `--help` đúng bằng danh sách trên (`topic discover` và `run` có thể là stub "chưa có" tới P3/P5, trả mã 2).
- [ ] `/pyh` SKILL.md ≤ 40 dòng: dùng `status`, `run`, `review`; giữ nguyên quy tắc không tự duyệt, không suy đoán reviewer, không tự xuất bản.
- [ ] CHECK, commit `refactor: shrink CLI to the factory command surface`.

---

## P3 — Hàng đợi, `run`, PIN

### Task 3.1: PIN cho lệnh duyệt

**Files:** Create `src/healthvideo/approver_pin.py`, `tests/test_approver_pin.py`. Modify `cli.py` (`review approve`, thêm `review set-pin`).

**Interfaces:** Produces —
`pin_path() -> Path` (= `Path.home() / ".healthvideo" / "approver-pin.json"`);
`set_pin(pin: str, *, old_pin: str | None, path: Path | None = None) -> None` (lỗi `PinError` nếu đã có PIN và `old_pin` sai; PIN ≥ 6 ký tự);
`verify_pin(pin: str, *, path: Path | None = None) -> bool` (False nếu chưa đặt);
băm `hashlib.scrypt(n=2**14, r=8, p=1)` + salt 16 byte, so sánh `hmac.compare_digest`.

- [ ] **Tests:** `test_verify_after_set`, `test_wrong_pin_rejected`, `test_reset_requires_old_pin`, `test_short_pin_rejected`, `test_verify_without_pin_file_is_false`; CLI: `test_approve_refuses_without_tty` (CliRunner không có TTY → exit ≠ 0, không có file approval mới), `test_approve_refuses_when_no_pin_set`, `test_approve_with_correct_pin_writes_record` (monkeypatch `sys.stdin.isatty`→True, `getpass.getpass`→PIN).
- [ ] Bỏ cờ `--yes` khỏi `review approve` (vẫn giữ cho `reject`). `reject` không cần PIN.
- [ ] CHECK, commit `feat: require interactive PIN for gate approval`.

### Task 3.2: Hàng đợi chủ đề

**Files:** Create `src/healthvideo/domain/queue.py`, `src/healthvideo/storage/queue.py`, tests. Modify `cli.py` (`topic add`, `topic list`).

**Interfaces:** Produces —
`QueueEntry(BaseModel, frozen)`: `slug: str` (regex `^[a-z0-9-]{3,80}$`), `title: str`, `question: str`, `doctor_note: str | None = None`, `added: date`;
`load_queue(root: Path) -> list[QueueEntry]` (file `root / "topics" / "queue.yaml"`, thiếu file → `[]`);
`add_to_queue(root: Path, entry: QueueEntry) -> None` (ghi nguyên tử; `QueueError` nếu slug đã có trong hàng đợi **hoặc** `root/"projects"/slug` đã tồn tại).

- [ ] **Tests:** `test_add_then_load_roundtrip`, `test_duplicate_slug_rejected`, `test_existing_project_slug_rejected`, `test_missing_queue_file_is_empty`, `test_bad_slug_rejected`.
- [ ] `topic add --slug --title --question [--note]`; `topic list` in bảng slug/title/trạng thái project (hoặc "chưa bắt đầu").
- [ ] CHECK, commit `feat: add topic queue`.

### Task 3.3: Chọn bước kế tiếp (thuần)

**Files:** Create `src/healthvideo/workflows/runner.py`, `tests/workflows/test_runner.py`.

**Interfaces:** Produces —
`StepKind = Literal["create", "research", "draft", "produce", "revise_medical", "revise_production"]`;
`next_step(state: WorkflowState | None) -> StepKind | None`: `None`(chưa có project)→`"create"`; `topic_selected`,`research_in_progress`→`"research"`; `evidence_ready`,`draft_ready`→`"draft"`; `medically_approved`,`production_in_progress`→`"produce"`; `needs_medical_revision`→`"revise_medical"`; `needs_production_revision`→`"revise_production"`; mọi trạng thái khác (hai cổng, `video_approved`, `packaged`, `published_manual`, `blocked`, `topic_rejected`) → `None`.
`AGENT_STEPS = frozenset({"research", "draft", "revise_medical", "revise_production"})`.

- [ ] **Tests:** parametrize toàn bộ `WorkflowState` + `None` → giá trị trên; `test_gates_never_have_a_step`.
- [ ] CHECK, commit `feat: map workflow state to next factory step`.

### Task 3.4: Gọi agent với chuyển đổi khi hết quota

**Files:** Create `src/healthvideo/agents.py`, `tests/test_agents.py`.

**Interfaces:** Produces —
`AgentCli(name: str, argv: tuple[str, ...], prompt_via_stdin: bool)`;
`DEFAULT_AGENTS = (AgentCli("codex", ("codex","exec","--dangerously-bypass-approvals-and-sandbox","-"), True), AgentCli("agy", ("agy","-p","{prompt}","--mode","accept-edits","--print-timeout","0s","--model","gemini-4-argon-medium"), False))`;
`AgentResult(agent: str, ok: bool, quota_exhausted: bool, log_path: Path)`;
`invoke(agent: AgentCli, prompt: str, *, cwd: Path, log_dir: Path, runner=subprocess.run) -> AgentResult` (ghi stdout+stderr vào log; `quota_exhausted` khi output khớp `QUOTA_PATTERNS` không phân biệt hoa thường);
`invoke_with_failover(agents: Sequence[AgentCli], prompt: str, *, cwd: Path, log_dir: Path, runner=subprocess.run) -> AgentResult` (thử lần lượt; chỉ chuyển agent khi `quota_exhausted`; tất cả hết → `AllAgentsExhausted`).
`QUOTA_PATTERNS`: executor xác định từ log thật của Codex và agy khi hết quota; khởi đầu `("usage limit", "rate limit", "quota", "resource_exhausted", "429")`.

- [ ] **Tests** (fake `runner`): `test_quota_switches_to_next_agent`, `test_non_quota_failure_does_not_switch` (trả `ok=False` của agent đầu), `test_all_exhausted_raises`, `test_prompt_sent_via_stdin_for_codex`, `test_prompt_substituted_for_agy`, `test_env_has_no_pin_material` (env truyền cho subprocess không chứa khóa nào có "PIN").
- [ ] CHECK, commit `feat: invoke codex/agy with quota failover`.

### Task 3.5: Lệnh `run` và `status` tổng

**Files:** Modify `src/healthvideo/workflows/runner.py`, `cli.py`. Create `src/healthvideo/prompts/{research,draft,revise_medical,revise_production}.md` (nội dung ở Task 3.6). Test `tests/workflows/test_runner.py`, `tests/test_cli.py`.

**Interfaces:** Consumes `next_step`, `invoke_with_failover`, `load_queue`. Produces —
`RunReport(advanced: list[str], at_gate: list[str], blocked: list[str], code_changes: list[Path])`;
`run_queue(root: Path, *, agents: Sequence[AgentCli] = DEFAULT_AGENTS, once: bool = False, python_steps: Mapping[StepKind, Callable[[Path], None]] | None = None) -> RunReport`.
Vòng lặp: với mỗi thẻ theo thứ tự, lặp `next_step` → `"create"`: tạo project v2 + chọn thẻ (dùng `create_project_v2`, `topic select`); bước agent: render prompt từ `prompts/<step>.md` với `{project}`, `{slug}`, `{title}`, `{question}`, `{doctor_note}`, `{reject_note}` rồi `invoke_with_failover`; `"produce"`: gọi `produce` Python. Sau mỗi bước đọc lại trạng thái; nếu không đổi sau bước agent `ok` → đánh `blocked` cho thẻ (ghi lý do), sang thẻ kế. `once=True`: dừng sau một bước. `AllAgentsExhausted` → dừng toàn bộ, in thông báo.
Sau mỗi bước agent: `git status --porcelain` ngoài `projects/`/`topics/` → nối vào `topics/code-review.yaml` (path, slug, thời gian).
`healthvideo status` không đối số: bảng mọi thẻ — slug, trạng thái, bước kế/cổng đang chờ, đường dẫn gói duyệt (`review open` sẽ mở).

- [ ] **Tests:** `test_run_stops_at_medical_gate` (fake agent đưa project tới `awaiting_medical_review` → `at_gate` chứa slug, không gọi thêm agent), `test_run_rerun_resumes_same_step` (agent lần đầu "bị cắt" không đổi file → lần chạy sau gọi lại đúng prompt `research`), `test_unchanged_state_marks_blocked`, `test_all_exhausted_stops_run_and_keeps_state`, `test_code_changes_recorded`, `test_run_never_invokes_approve` (fake runner ghi mọi argv; không argv nào chứa `approve`), `test_status_table_lists_all_queue_entries`.
- [ ] CHECK, commit `feat: run the topic queue up to the review gates`.

### Task 3.6: Prompt cố định cho từng bước agent

**Files:** `src/healthvideo/prompts/*.md`, test `tests/test_prompts.py`.

- [ ] Mỗi prompt ≤ 60 dòng, gồm: mục tiêu bước, lệnh `healthvideo step …` được dùng, file đầu ra, quy tắc cứng (không bịa nguồn/số liệu/trải nghiệm bác sĩ; không gọi `review approve`; không commit; không sửa file ngoài project trừ component SVG mới trong `video/src/anatomy/` kèm test), điều kiện xong (trạng thái đích). `draft.md` dẫn spec explain-first §1–§15 và yêu cầu dùng skill `humanizer` cho lời thoại; `revise_*.md` đọc ghi chú từ chối mới nhất.
- [ ] **Tests:** `test_every_agent_step_has_prompt` (mỗi phần tử `AGENT_STEPS` có file), `test_prompts_forbid_approval_and_fabrication` (mỗi prompt chứa các câu quy tắc cứng cố định, định nghĩa thành hằng `HARD_RULES` trong `runner.py` và chèn khi render).
- [ ] CHECK, commit `feat: add fixed agent prompts for factory steps`.

---

## P4 — Giai đoạn 2 mới

Mỗi task P4 bắt đầu bằng một spike (không commit) trên máy RTX 3060 để đo VRAM/thời gian; kết quả spike ghi vào mô tả commit.

### Task 4.1: Minh họa FLUX.2 [klein] 4B

**Files:** Create `src/healthvideo/visuals/flux.py`, `tools/flux/` (script chạy trong venv riêng như `tools/tts/`), test. Modify `domain/asset_manifest.py` (loại asset `illustration` + `prompt`), `workflows/produce.py`.

**Interfaces:** `generate_illustration(prompt: str, *, out: Path, width: int, height: int, seed: int, runner=…) -> Path`; asset ghi `license="generated:flux2-klein-4b"`; cache theo hash(prompt, seed, size).
- [ ] **Tests:** `test_illustration_cached_by_hash`, `test_illustration_asset_rejects_text_labels` (storyboard cảnh có `labels`/chú thích dùng asset `illustration` → lỗi lint: ảnh AI không mang nhãn giải phẫu), fake runner.
- [ ] Doctor kiểm venv FLUX + trọng số 4B (không phải 9B/dev).
- [ ] CHECK, commit `feat: generate unlabeled illustrations with FLUX.2 klein 4B`.

### Task 4.2: Nhạc nền ACE-Step 1.5

- [ ] **Step 0 (chặn):** xác minh giấy phép **trọng số** ACE-Step 1.5 cho dùng thương mại. Không đạt → báo người dùng kèm 2 phương án (thư viện nhạc miễn phí bản quyền có giấy phép rõ / không nhạc), dừng task.
**Files:** Create `src/healthvideo/audio/music.py`, `tools/music/`, test. Modify `render/` (mix), `workflows/produce.py`.
**Interfaces:** `generate_music(mood: str, *, seconds: float, out: Path, seed: int, runner=…) -> Path`; `mix_with_ducking(narration: Path, music: Path, *, out: Path, music_db: float = -20.0, duck_db: float = -12.0) -> Path` (FFmpeg `sidechaincompress`).
- [ ] **Tests:** `test_music_cached_by_hash`, `test_mix_keeps_narration_duration`, `test_music_disabled_flag` (`produce --no-music` không gọi ACE-Step); QA hiện có (lệch tiếng-hình) vẫn qua.
- [ ] CHECK, commit `feat: add ACE-Step background music with ducking`.

### Task 4.3: Thư viện SVG mở rộng được

**Files:** Create `video/src/anatomy/registry.ts` (+test), `src/healthvideo/visuals/anatomy_library.py` (+test). Modify `workflows/review_frames.py`.
**Interfaces:** `registry.ts` export `ANATOMY_COMPONENTS: Record<string, {component, layers: string[], approvedIn: string | null}>`; Python `library_status(repo: Path) -> dict[str, Literal["approved","new","modified"]]` (so hash file component với `video/src/anatomy/approved.json` ghi `{name: {sha256, project, revision}}`); khi cổng video duyệt, ghi hash các component dùng trong video vào `approved.json`.
- [ ] **Tests:** `test_new_component_flagged`, `test_modified_component_flagged`, `test_review_frames_includes_new_and_modified_components` (contact sheet có mục riêng), Vitest `registry.test.ts` (mọi component có `layers` khớp bộ kiểm layer).
- [ ] Ghi quy ước vào `video/src/anatomy/README.md` (≤ 30 dòng): palette brand, lớp nhãn, test bắt buộc.
- [ ] CHECK (cả video), commit `feat: track anatomy library approval in video review`.

---

## P5 — Giai đoạn 1 mới

### Task 5.1: `topic discover`

**Files:** Create `src/healthvideo/discovery/{youtube,trends,reddit,cards}.py`, tests với fixture HTTP ghi sẵn. Modify `cli.py`.
**Interfaces:** mỗi nguồn: `fetch_signals(query: str, *, client) -> list[Signal]`; `Signal(source: Literal["youtube","trends","reddit","pubmed"], url: str, text: str, metric: float | None, fetched: datetime)`. `build_cards(signals, *, pubmed_counts) -> list[TopicCard]`; `TopicCard` gồm `title`, `question`, `misconceptions: list[Signal]` (chỉ từ tín hiệu thật), `heat: float | None` (None nếu không có số liệu → không được gắn nhãn "hot"), `layers: list[str]`. Ghi ra `topics/discovered/<date>.yaml`; người dùng chọn rồi `topic add`.
Khóa API (YouTube Data API) đọc từ `.env`; thiếu khóa → bỏ nguồn đó, ghi rõ trong output, không lỗi toàn bộ.
- [ ] **Tests:** `test_card_without_metric_has_no_heat`, `test_misconceptions_only_from_signals`, `test_missing_youtube_key_skips_source`, `test_provider_error_reported_not_swallowed`.
- [ ] Không dùng ScrapeCreators. `local-deep-research` không tích hợp ở bước này.
- [ ] CHECK, commit `feat: discover topic cards from free sources`.

---

## P6 — Giai đoạn 4 mới

### Task 6.1: Bản nháp bài đăng + thumbnail trong `production_in_progress`

**Files:** Create `src/healthvideo/domain/posts.py`, `src/healthvideo/workflows/posts.py`, `src/healthvideo/prompts/posts.md`, tests. Modify `workflows/produce.py`, `workflows/review_html.py` (gói duyệt video hiện bài đăng + thumbnail), `workflows/runner.py` (bước agent `"posts"` sau render, trước `awaiting_video_review`).
**Interfaces:** `PostSet(BaseModel)`: `youtube_titles: list[str]` (2–3), `youtube_description: str`, `youtube_tags: list[str]`, `clip_captions: dict[str, ClipCaptions]` (`tiktok`, `shorts`, `reels`), `facebook_post: str`, `youtube_community: str`, `claim_refs: list[str]`; `validate_posts(posts: PostSet, ledger) -> list[str]` — mọi chữ số trong văn bản phải nằm trong câu có `[claim:<id>]` trỏ tới claim đã duyệt; mô tả YouTube có chương + nguồn lấy từ outline/ledger. Thumbnail: ảnh FLUX (Task 4.1) + chữ do Remotion still dựng.
- [ ] **Tests:** `test_number_without_claim_ref_blocks`, `test_claim_ref_must_be_medically_approved`, `test_description_has_chapters_and_sources`, `test_video_packet_contains_posts_and_thumbnail`, `test_title_count_bounds`.
- [ ] CHECK (cả video nếu đụng still), commit `feat: draft multi-channel posts before video review`.

### Task 6.2: Đóng băng bài đăng khi đóng gói

**Files:** Modify `workflows/package.py`, `domain/gate_review.py` (hash cổng video gồm posts + thumbnail).
- [ ] **Tests:** `test_package_copies_approved_posts_unchanged`, `test_post_edit_after_video_approval_blocks_package` (dùng invalidation có sẵn).
- [ ] CHECK, commit `feat: freeze approved posts into publish package`.

---

## P7 — Chạy thật

### Task 7.1: Một chủ đề từ đầu đến cuối

- [ ] `healthvideo topic add` một chủ đề thử (ghi rõ TEST, không đăng).
- [ ] `healthvideo run` tới cổng y khoa; người dùng duyệt bằng PIN; `run` tới cổng video; người dùng duyệt; `healthvideo package`.
- [ ] Ghi kết quả (thời gian mỗi bước, số lần đổi agent, lỗi gặp) vào dòng README; mở follow-up cho lỗi tìm thấy. Không commit render/audio.

---

## Thứ tự và song song

P0 → P1 → P2 → P3 tuần tự (P2 đụng cùng `cli.py`, `project_v2.py`, `state_graph.py`). Sau P3: P4.1/P4.2 và P5 có thể chạy song song (file khác nhau); P4.3 sau P4.1; P6 sau P4.1; P7 cuối.
