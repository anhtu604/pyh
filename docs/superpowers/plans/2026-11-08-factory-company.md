# Xưởng-công ty: kế hoạch triển khai

> **Cho agent thực thi:** mỗi task được giao cho một CLI theo cột "Người làm"; Claude (phiên điều phối) review từng task
> trước task sau, rồi review cả nhánh. Bước dùng checkbox (`- [ ]`).

**Goal:** Xưởng chạy như công ty: bậc model + vai + skill, chuyển model khi hết token, thẻ quyết định ở hai cổng,
chat Điều phối viên, dashboard tổng quan + trang xem sản phẩm.

**Architecture:** Cấu hình `profiles/company.yaml` quyết định vai → bậc → chuỗi (cli, model); `agents.py` gọi CLI với
model theo lần gọi và ghi activity/quota. Agent duyệt ghi thêm `checked`/`decisions`; dashboard dựng thẻ và gọi
`approve_gate`/`reject_gate` có sẵn. Chat lưu JSONL, Điều phối viên trả YAML, Python thực hiện action qua
`request_change`.

**Tech Stack:** Python 3.12, pydantic v2, pytest, ruff; dashboard `ThreadingHTTPServer` + HTML/JS thuần (không build).

**Spec:** `docs/superpowers/specs/2026-11-08-factory-company-design.md` (đọc kèm).

## Global Constraints

- Không có đường nào cho agent/chat gọi `approve_gate`, đặt PIN, ghi file approval; PIN không lưu/log/chuyển cho agent.
- `HARD_RULES` giữ nguyên, luôn là khối cuối của prompt.
- Mở lại từ chat: bấm xác nhận, **không PIN**, kể cả khi bỏ hiệu lực duyệt y khoa.
- Tối đa 5 điểm khó mỗi thẻ; mỗi điểm có đúng một phương án `keep: true`.
- Model nghỉ mặc định +5 giờ khi CLI không in giờ reset.
- Đường dẫn bằng `pathlib.Path`; chạy được trong PowerShell; CLI gọi qua `prepare_subprocess_argv` + `child_env`.
- Không thêm dependency Python/JS mới.
- Test: `.venv\Scripts\python -m pytest -q`; lint: `.venv\Scripts\python -m ruff check src tests`.
- Mỗi commit cập nhật bảng tiến độ trong `README.md` (quy tắc 6 của `CLAUDE.md`).
- Không commit `cache/`, `projects/`, `topics/`, `.superpowers/`.

## Review Focus

1. Điều phối viên trả YAML hỏng / sai schema → tin chat `status: failed` kèm lỗi đọc được, không đổi trạng thái dự án (Task 5).
2. Yêu cầu đổi số liệu bị xếp `edit_production` → Python hạ thành `edit_script` (Task 5).
3. Mọi mục trong chuỗi hết quota → chỉ dự án đó chờ model, dự án khác chạy tiếp; trạng thái nghỉ còn sau khi tắt/bật xưởng (Task 2).
4. Log duyệt cũ không có `checked`/`decisions`/`submitted` vẫn đọc được, thẻ hiện "không có điểm khó" (Task 4).
5. Thẻ có lựa chọn không-keep nhưng PIN sai → không đổi gì, `PinLimiter` vẫn đếm (Task 4).

---

## Phân việc

| Task | Nội dung | Độ khó | Người làm (CLI · model) |
|---|---|---|---|
| 1 | Bảng vai + bậc model | trung bình | codex · gpt-6.1-sol |
| 2 | Model theo lần gọi, quota nghỉ, activity, runner không dừng cả hàng | khó | codex · gpt-6-astra |
| 3 | Gán skill có sẵn + nạp vào prompt | dễ (đã cài skill) | gộp vào gói 4–5 |
| 4 | Thẻ quyết định (backend + prompt) | khó | agy · claude-opus-5-5-high |
| 5 | `request_change` + chat Điều phối viên (backend) | khó | agy · claude-opus-5-5-high |
| 6 | Dashboard mới (API + giao diện) | trung bình | agy · gemini-4-argon-high |

Cập nhật 2026-11-08: Claude CLI gần hết token, astra tốn token → Task 1–2 chạy Codex `gpt-6.1-sol`; phần còn lại sang agy.
| 7 | Nghiệm thu | — | Claude (phiên này) |

Chạy tuần tự (các task chạm chung `agents.py`, `runner.py`, `dashboard.py`). Hết quota thì chuyển sang mục kế tiếp của
bậc trong spec 5.1.

---

### Task 1: Bảng vai và bậc model

**Files:**
- Create: `profiles/company.yaml`, `src/healthvideo/company.py`
- Test: `tests/test_company.py`

**Interfaces:**
- Produces:
  - `ModelSlot(BaseModel)`: `cli: Literal['claude','codex','agy']`, `model: str` (frozen, hashable).
  - `Role(BaseModel)`: `id: str`, `name: str`, `skill: str | None`, `steps: list[str]`, `tier: Literal['hard','medium','bulk']`, `models: list[ModelSlot] | None`.
  - `Company(BaseModel)`: `tiers: dict[str, list[ModelSlot]]`, `roles: dict[str, Role]`; method `chain(role_id: str) -> list[ModelSlot]` (= `role.models` hoặc `tiers[role.tier]`), `role_for_step(step: str) -> Role`.
  - `load_company(path: Path = COMPANY_PATH) -> Company` (`COMPANY_PATH = REPO_ROOT / 'profiles/company.yaml'`), kiểm hợp lệ, lỗi → `ValueError` tiếng Việt.
- Nội dung `company.yaml`: đúng bảng bậc và bảng vai ở spec 5.1 (id vai: coordinator, scout, researcher, writer, script_critic, art_director, editor, product_critic, copywriter, feedback_analyst). `skill` = `.agents/skills/pyh-<id>/SKILL.md`.

- [ ] **Step 1: Viết test**

```python
def test_every_agent_step_has_exactly_one_role(): ...      # mọi runner.AGENT_STEPS
def test_critic_first_slot_differs_from_maker(): ...      # script_critic vs writer, product_critic vs editor
def test_chain_uses_override_then_tier(): ...             # script_critic.chain()[0] == ModelSlot(cli='codex', model='gpt-6-astra'); writer.chain() == tiers['hard']
def test_duplicate_step_rejected(tmp_path): ...           # ValueError
def test_unknown_cli_rejected(tmp_path): ...              # ValueError
def test_bulk_roles_never_start_on_hard_tier(): ...       # copywriter, scout chain()[0] thuộc tiers['bulk']
```

- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_company.py -q` → FAIL (module chưa có).
- [ ] **Step 3:** Viết `company.py` + `company.yaml`.
- [ ] **Step 4:** Chạy lại → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: add company roles and model tiers`.

### Task 2: Model theo lần gọi, quota nghỉ, activity, runner không dừng cả hàng

**Files:**
- Modify: `src/healthvideo/agents.py`, `src/healthvideo/workflows/runner.py`, `src/healthvideo/workflows/factory_deps.py`, `src/healthvideo/workflows/feedback_inbox.py`, `src/healthvideo/workflows/factory.py` (chỉ chỗ xử lý `report.exhausted`)
- Test: `tests/test_agents.py`, test runner hiện có trong `tests/workflows/`

**Interfaces:**
- Consumes: `ModelSlot`, `Company.chain`, `Company.role_for_step` (Task 1).
- Produces:
  - `argv_for(slot: ModelSlot) -> tuple[AgentCli, list[str]]`: claude `--model <m>` (giữ allowlist hiện có), codex chèn `-m <m>` trước `-`, agy thay giá trị `--model`.
  - `QuotaBook(path: Path = REPO_ROOT/'cache/agent-quota.yaml')`: `resting(slot, now) -> bool`, `rest(slot, until: datetime, reason: str)`, `earliest_return(slots, now) -> datetime | None`, `snapshot(now) -> list[dict]`.
  - `parse_reset(output: str, now: datetime) -> datetime | None` (nhận "try again at HH:MM", "resets in N hours/minutes"; không nhận → `None` → dùng `now + 5h`). Nếu output có "account"/"plan" + quota → nghỉ mọi slot cùng cli.
  - `invoke_with_failover(slots: Sequence[ModelSlot], prompt, *, cwd, log_dir, role: str, slug: str, step: str, runner=subprocess.run, now=lambda: datetime.now().astimezone(), quota: QuotaBook | None = None, activity: Path | None = None) -> AgentResult`. Bỏ qua slot đang nghỉ; ghi `topics/logs/activity.jsonl` dòng `{at, role, cli, model, slug, step, event: start|end|quota, ok}`. Hết chuỗi → `AllAgentsExhausted(earliest_return)`.
  - `AgentResult` thêm `model: str`.
  - `RunDeps.step_agents` bị thay bằng `RunDeps.company: Company`; `run_queue(root, deps, *, once=False, max_steps_per_topic=20)` (bỏ tham số `agents`).
  - Khi `AllAgentsExhausted`: ghi `topics/logs/<slug>/waiting-model.txt` (giờ trở lại), **chuyển sang topic kế tiếp**; `RunReport.waiting_model: list[str]` thay `exhausted`. Đầu mỗi topic: có `waiting-model.txt` mà chưa tới giờ → bỏ qua; tới giờ → xoá file, chạy tiếp.
  - `factory.py`: vòng lặp ngủ tới `min(interval, earliest waiting)` thay vì ngủ dài khi `exhausted`.
  - `feedback_inbox.analyze` dùng `company.chain('feedback_analyst')`.

- [ ] **Step 1: Viết test**

```python
def test_argv_for_each_cli_injects_model(): ...           # codex argv chứa ['-m','gpt-6-astra'] trước '-'; agy '--model' theo slot; claude '--model' theo slot
def test_resting_slot_is_skipped(tmp_path): ...           # slot 1 đang nghỉ → runner fake chỉ được gọi với slot 2
def test_quota_rests_slot_default_five_hours(tmp_path): ...  # output 'usage limit' không giờ → resting_until == now+5h
def test_parse_reset_reads_cli_hint(): ...                 # 'try again at 21:30' → hôm nay 21:30 (hoặc mai nếu đã qua)
def test_account_quota_rests_all_slots_of_cli(tmp_path): ...
def test_activity_lines_written(tmp_path): ...            # start + end, có role/model/slug/step
def test_exhausted_topic_waits_others_continue(tmp_path): ...  # 2 topic; topic A hết chuỗi → A trong waiting_model, B vẫn advanced
def test_waiting_topic_resumes_after_return(tmp_path): ...
def test_runner_uses_role_chain_for_step(tmp_path): ...   # step 'script_review' → slots == company.chain('script_critic')
```

- [ ] **Step 2:** Chạy test → FAIL.
- [ ] **Step 3:** Cài đặt như Interfaces; sửa mọi chỗ gọi cũ (`grep -rn "invoke_with_failover\|step_agents\|DEFAULT_AGENTS\|exhausted" src tests`).
- [ ] **Step 4:** `.venv\Scripts\python -m pytest -q` toàn bộ → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: per-call models, quota rest and activity log`.

### Task 3: Skill từng vai

**Đã làm (Claude, 2026-11-08):** cài 7 skill công khai vào `.agents/skills/` + `skills-lock.json`, rà nội dung; bảng gán ở spec 5.3. Phần còn lại là code, gộp vào gói Task 4–5.

**Files:**
- Modify: `profiles/company.yaml` + `src/healthvideo/company.py` (`Role.skill: str | None` → `Role.skills: list[str] = []`, tên thư mục skill trong `.agents/skills/`, theo bảng spec 5.3), `src/healthvideo/workflows/runner.py` (`render_prompt`), `src/healthvideo/workflows/feedback_inbox.py` (`_prompt`)
- Test: `tests/test_prompts.py`, `tests/test_company.py`

**Interfaces:**
- Consumes: `load_company`, `Role.skills`.
- Produces: `role_skill_block(role_id: str) -> str`: rỗng nếu vai không có skill; ngược lại `## Skill của vai: <name>` + danh sách `- .agents/skills/<x>/SKILL.md` + đúng câu "Đọc các skill trên trước khi làm; chỉ áp dụng phần hợp với kênh sức khoẻ tiếng Việt. Khi skill mâu thuẫn với prompt bước hoặc quy tắc cứng, prompt bước và quy tắc cứng thắng." `render_prompt` chèn khối này ngay trước `## Quy tắc cứng`.

- [ ] **Step 1: Viết test**

```python
def test_every_role_skill_exists(): ...                    # mọi tên trong Role.skills có .agents/skills/<x>/SKILL.md thật
def test_role_skill_before_hard_rules(): ...              # render_prompt('draft', ...) chứa 'Skill của vai: Biên kịch' và 'youtube-scriptwriting', index < index('## Quy tắc cứng'); prompt kết thúc bằng khối quy tắc cứng
def test_role_without_skills_has_no_block(): ...          # vai coordinator → role_skill_block == ''
```

- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Sửa `company.py`/`company.yaml`/`render_prompt`.
- [ ] **Step 4:** Toàn bộ test → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: give each factory role its own skill`.

### Task 4: Thẻ quyết định

**Files:**
- Create: `src/healthvideo/workflows/decision_card.py`
- Modify: `src/healthvideo/workflows/script_review.py`, `src/healthvideo/workflows/product_review.py`, `src/healthvideo/prompts/script_review.md`, `src/healthvideo/prompts/product_review.md`, `src/healthvideo/workflows/dashboard.py` (`decide`, route), `src/healthvideo/workflows/draft.py` (gọi `script_review.mark_submitted` khi nộp y khoa)
- Test: `tests/workflows/test_decision_card.py`, `tests/workflows/test_script_review.py`, `tests/workflows/test_dashboard.py`

**Interfaces:**
- Produces:
  - Trong cả hai report: `checked: list[str] = []`, `decisions: list[Decision] = []`.
    `Decision`: `id: str` (D1…), `where: str`, `question`, `why_hard`, `options: list[DecisionOption]` (2–3).
    `DecisionOption`: `id: str`, `label`, `effect`, `recommended: bool = False`, `keep: bool = False`.
    Kiểm: đúng một `keep`, tối đa một `recommended`, `id` không trùng; script: `where` là id dòng có thật.
  - `script_review`: log có `submitted` như product_review; `_cycle`; `mark_submitted(artifact_root)`; `next_script_action` đếm vòng trong chu kỳ; >5 decisions mà còn vòng → coi như chưa đạt (`draft`).
  - `decision_card.card(project_dir: Path) -> dict | None`: `{gate, revision, title, checked, decisions (≤5, khuyến nghị chọn sẵn), more: int, followup: str | None}`. `followup` = "Đã sửa theo D1=b…" khi lần nộp trước của cổng này bị gửi sửa từ thẻ.
  - `decision_card.compose(card: dict, choices: dict[str, str], other: str) -> tuple[Literal['approve','send_fix'], str]` → lý do/ghi chú dạng `D1 (N14) → b: <label>`.
  - `dashboard.decide` nhận thêm `choices`, `other`; action `card`: dùng `compose`; `approve` → `approve_gate(note=...)`; `send_fix` → `reject_gate(resume_state=` `DRAFT_READY` cho y khoa; `PRODUCTION_IN_PROGRESS` cho video`)`. PIN kiểm trước mọi thay đổi.
  - Route: `GET /api/projects/<slug>/card` → `card()`.
  - Prompt: hai prompt duyệt thêm phần "Đầu ra" cho `checked` và `decisions`, nêu đúng 5 loại điểm khó ở spec 5.4, cấm số liệu ngoài ledger.

- [ ] **Step 1: Viết test**

```python
def test_old_logs_without_new_fields_still_load(tmp_path): ...    # Review Focus 4
def test_decision_needs_exactly_one_keep(tmp_path): ...
def test_script_where_must_be_real_line(tmp_path): ...
def test_resubmission_starts_new_review_cycle(tmp_path): ...       # sau mark_submitted, next_script_action == 'script_review'
def test_card_caps_five_and_counts_more(tmp_path): ...
def test_compose_all_keep_approves(): ...                           # ('approve', ...)
def test_compose_non_keep_sends_fix_with_choices(): ...            # ('send_fix', 'D1 (N14) → b: ...')
def test_card_decide_wrong_pin_changes_nothing(tmp_path): ...      # Review Focus 5: state + files không đổi, limiter đếm 1
def test_card_send_fix_rejects_to_draft(tmp_path): ...
```

- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Toàn bộ test → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: decision cards at both gates`.

### Task 5: `request_change` và chat Điều phối viên (backend)

**Files:**
- Create: `src/healthvideo/workflows/change_request.py`, `src/healthvideo/workflows/chat.py`, `src/healthvideo/prompts/coordinator.md`
- Modify: `src/healthvideo/workflows/factory_deps.py` (`reject_note`), `src/healthvideo/workflows/runner.py` (áp dụng yêu cầu chờ giữa hai bước + tin "đã xong"), `src/healthvideo/workflows/dashboard_operations.py` (routes), `src/healthvideo/workflows/feedback_inbox.py` (`add_ready`)
- Test: `tests/workflows/test_change_request.py`, `tests/workflows/test_chat.py`

**Interfaces:**
- Consumes: `invoke_with_failover`, `Company.chain('coordinator')` (Task 2), `add_to_queue`, `transition_v2`.
- Produces:
  - `change_request.request_change(project_dir: Path, kind: Literal['edit_production','edit_script'], brief: str, context: dict, *, now: datetime) -> dict`: ghi `revisions/<rev>/reviews/changes/<ts>-requested.yaml` `{at, by: 'doctor-chat', kind, brief, context, applied: false}`; chuyển trạng thái đúng bảng ở spec 5.5 (dùng `transition_v2`; `edit_script` sau duyệt y khoa → `NEEDS_MEDICAL_REVISION` với `reason_code='chat_change'`, `resume_state=DRAFT_READY`; ở `DRAFT_READY` → `script_review.mark_submitted` để vòng duyệt chạy lại). Trạng thái không hợp lệ → `ValueError` tiếng Việt.
  - `change_request.pending_note(project_dir) -> str | None` (brief chưa xử lý mới nhất, kèm ngữ cảnh `S07 @ 03:12`); `mark_applied(project_dir)`.
  - `factory_deps.reject_note` nối `pending_note`.
  - `chat.CoordinatorReply`: `reply: str`, `action: Literal['none','ask','edit_production','edit_script','queue_topic','factory_feedback','status']`, `brief: str = ''`, `options: list[dict] = []`, `topic: dict | None` (cho queue_topic: slug/title/question). Validator: brief bắt buộc trừ none/ask/status; ask cần 2–3 options.
  - `chat.post(root: Path, slug: str | None, text: str, context: dict) -> dict` (ghi tin bác sĩ, `status: pending`, khởi luồng nền; một Điều phối viên chạy mỗi lúc cho cả app).
  - `chat.run_coordinator(root, message_id, *, invoke=invoke_with_failover) -> dict` → ghi tin coordinator; YAML hỏng → tin bác sĩ `status: failed`, `error` (Review Focus 1).
  - `chat.guard(reply: CoordinatorReply) -> CoordinatorReply`: `edit_production` có brief nhắc id dòng (`N\d+`), "claim", "số liệu", chữ số kèm đơn vị y khoa (mg, mmol, %) → đổi thành `edit_script` (Review Focus 2).
  - `chat.confirm(root, slug, message_id) -> dict`: bác sĩ bấm xác nhận → nếu dự án có `RUNNING_MARKER` → ghi `status: queued`; ngược lại gọi `request_change`. `queue_topic` → `add_to_queue`; `factory_feedback` → `feedback_inbox.add_ready(root, project, text)` (mục `status: ready`, không chạy analyst).
  - Runner: đầu mỗi vòng của một topic, áp dụng tin `queued` của dự án đó (gọi `request_change`); khi trạng thái đi tiếp sau bước có `pending_note` → `mark_applied` + ghi tin coordinator "Đã sửa …, xem lại" kèm `context`.
  - Lưu: `projects/<slug>/chat.jsonl`, `topics/chat.jsonl`; dòng `{id, at, who, text, context, action, status, error?}`.
  - Routes: `GET /api/chat?slug=` (100 tin cuối), `POST /api/chat` `{slug, text, context}`, `POST /api/chat/confirm` `{slug, id}`.
  - `coordinator.md`: vai, bảng action, luật "không chắc → edit_script hoặc ask", chỉ ghi đúng file báo cáo được chỉ định.

- [ ] **Step 1: Viết test**

```python
def test_production_change_enters_needs_production_revision(tmp_path): ...
def test_script_change_after_medical_approval_reopens_without_pin(tmp_path): ...
def test_script_change_at_draft_ready_restarts_review(tmp_path): ...
def test_invalid_state_raises(tmp_path): ...                          # vd. IDEA
def test_reject_note_includes_pending_brief(tmp_path): ...
def test_guard_downgrades_number_change(): ...                       # brief 'đổi 6 mg/dL thành 5' → edit_script
def test_bad_yaml_marks_message_failed_state_unchanged(tmp_path): ...
def test_confirm_while_agent_running_queues(tmp_path): ...
def test_runner_applies_queued_change_between_steps(tmp_path): ...
def test_factory_feedback_written_ready(tmp_path): ...
def test_chat_never_approves(tmp_path): ...                          # mọi action: không có file approval mới
```

- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Toàn bộ test → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: coordinator chat and change requests`.

### Task 6: Dashboard mới

**Files:**
- Modify: `src/healthvideo/workflows/dashboard.html` (có thể tách `dashboard.js`/`dashboard.css` cạnh nó, phục vụ qua route tĩnh), `src/healthvideo/workflows/dashboard.py`, `src/healthvideo/workflows/dashboard_operations.py`
- Test: `tests/workflows/test_dashboard.py`

**Interfaces:**
- Consumes: `QuotaBook.snapshot`, activity.jsonl (Task 2), `decision_card.card` + `decide` action `card` (Task 4), chat routes (Task 5), `snapshot()`, `media_file()` có sẵn.
- Produces (API mới):
  - `GET /api/overview` → `{tiles: {running, waiting_doctor, done_7d, done_30d, avg_days_topic_to_video, models_resting}, decisions: [{slug, title, gate, count}], projects: [{slug, title, stage_index, state, preview_url|null, status_line}], resting: [...], channel: {connected: false}}`.
  - `GET /api/activity?limit=10` → dòng activity mới nhất + việc đang chạy (start chưa có end).
  - `GET /api/projects/<slug>/timeline` → `[{scene, start_s, end_s, open_change: bool}]` từ render input của bản dựng mới nhất (thiếu → `[]`).
  - `POST /api/studio` → chạy Remotion Studio một lần (`resolve_pnpm_argv(['--dir','video','exec','remotion','studio'])`, stdout/stderr ghi `cache/studio.log`), trả `{url}`.
- Giao diện (giữ thứ tự spec 5.6): ô số liệu → dải "Cần bạn quyết" → thẻ dự án → "Công ty đang làm gì" → "Kết quả kênh: chưa kết nối"; chức năng cũ vào menu "Quản trị". Trang dự án: tab Nguồn / Kịch bản / Storyboard / Video / Nhật ký; Video = `<video>` + dải cảnh bấm-để-tua + nút "Mở Remotion Studio"; thẻ quyết định như spec 5.4 (khuyến nghị chọn sẵn, nút đổi nhãn Duyệt ↔ Gửi sửa theo lựa chọn, một ô PIN). Chat cố định bên phải, gửi kèm `{slug, revision, view, scene, time_s}`; tin `ask` hiện nút; tin cần mở lại hiện nút "Mở lại để sửa?" gọi `/api/chat/confirm`; poll 3 giây khi có tin `pending`. Tab "Ý kiến" bỏ (đã gộp vào chat). Chạy được ở 1366×768.

- [ ] **Step 1: Viết test**

```python
def test_overview_shape(tmp_path): ...                 # đủ khoá; channel.connected is False
def test_activity_running_job_listed(tmp_path): ...
def test_timeline_from_render_input(tmp_path): ...
def test_timeline_missing_render_is_empty(tmp_path): ...
def test_html_has_sections_in_order(): ...             # id tiles < decisions < projects < activity < channel trong dashboard.html
def test_feedback_tab_removed(): ...
```

- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3:** Cài đặt API + giao diện.
- [ ] **Step 4:** Toàn bộ test → PASS; ruff sạch.
- [ ] **Step 5:** Commit `feat: company dashboard, product viewer and chat UI`.

### Task 7: Nghiệm thu (Claude)

- [ ] Review cả nhánh so với spec (mục 3 phản mục tiêu, Global Constraints).
- [ ] `.venv\Scripts\python -m pytest -q` + ruff toàn bộ → PASS.
- [ ] Chạy app thật trong trình duyệt nội bộ: trang chủ đủ 5 mục; trang gout phát video + tua theo cảnh; gửi tin chat "đổi hình S07 sang dạng kim" → Điều phối viên trả `edit_production` + nút xác nhận; thẻ quyết định hiển thị với dữ liệu giả lập; quota giả lập → model hiện "nghỉ".
- [ ] Cập nhật README (bảng tiến độ), merge vào master khi người dùng đồng ý.
