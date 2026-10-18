# Plan: explain-first content (giải thích trực quan trước, bằng chứng sau)

**Spec:** `docs/superpowers/specs/2026-10-18-explain-first-content-design.md` (approved 18-10-2026)
**Vai trò:** Claude là tech lead (viết brief, review diff, chạy test, commit). Codex CLI làm
toàn bộ code. Mỗi task = một brief độc lập; Codex không commit; Claude commit sau khi nghiệm thu.

## Quy tắc chung cho mọi task (đưa nguyên văn vào brief)

- TDD: viết test fail trước, rồi code tối thiểu cho test qua.
- Dùng `pathlib.Path`; chạy được trên Windows PowerShell.
- Không bịa nguồn/DOI/PMID/số liệu trong fixture: dùng ID giả rõ ràng (`R-TEST-01`) và
  nội dung minh họa không mang tính khẳng định y khoa thật.
- Không đụng hai cổng duyệt, không thêm đường tự đăng, không gọi mạng trong test.
- Trường mới phải tùy chọn hoặc có default để project cũ và fixture cũ không đổi hành vi.
- Đổi model Pydantic → chạy `python tools/export_schemas.py` và commit schema sinh ra.
- Kiểm chứng trước khi báo xong: `python -m pytest -q`, `python -m ruff check src tests tools`,
  `git diff --check`; task có TypeScript thêm `corepack pnpm --dir video test` và
  `corepack pnpm --dir video typecheck`.
- Thêm một dòng vào bảng "Tiến độ nhiệm vụ" trong `README.md` (cột: Task, Deliverable,
  Status, Tests, Commit) với commit message dự kiến.
- Báo cáo vào `.tmp/codex-report-<task>.md`: file đã đổi, quyết định thiết kế, lệnh test và kết quả.

## Task 0 — Nền 16:9 (Claude làm, không giao Codex)

Merge `feat/m8-1-long-form` (`d433d96`, đã review xong, merge-tree sạch) vào `master`.
Profile `youtube_long` cho phép 1920×1080, 60 giây–25 phút → đủ cho 3–5 phút; render
theo chương có sẵn. Chạy full test sau merge. Không merge các nhánh M8 khác.

## Task 1 — Explainer: model, schema, validator (spec §4)

- `src/healthvideo/domain/explainer.py`: `Explainer`, `ExplainerLayer`, `LayerVisual`,
  `Analogy`, `SkippedLayer`. `layer ∈ {anatomy, physiology, pathophysiology, pathology}`,
  `visual.kind ∈ {anatomy_animation, process_animation, comparison, timelapse}`.
- Validator (thuần, không I/O): id duy nhất; thứ tự tầng không đi ngược; tối thiểu một tầng
  bình thường (anatomy/physiology) và một tầng bệnh (pathophysiology/pathology); tầng thiếu
  phải nằm trong `skipped_layers` kèm `reason` không rỗng; `reuse_of` trỏ tới lớp đứng trước;
  hàm riêng `validate_claim_refs(explainer, claim_ids)` báo claim id không tồn tại.
- Đọc/ghi YAML tại `revisions/<rev>/explainer/explainer.yaml` theo helper lưu trữ nguyên tử hiện có.
- Test: `tests/domain/test_explainer.py` phủ từng luật trên + một explainer hợp lệ đầy đủ.

## Task 2 — Claim `mechanism` (spec §5)

- Thêm `"mechanism"` vào Literal loại claim trong `src/healthvideo/domain/evidence.py`.
- Luật: claim `mechanism` bắt buộc có ≥1 nguồn đã xác minh **hoặc** đánh dấu là ý kiến chuyên
  môn (theo cơ chế hiện có); không bắt buộc PICO/effect/certainty.
- Thêm cờ nhẹ: claim `mechanism` có `text_public` chứa ý hiệu quả can thiệp (từ khóa
  "giảm nguy cơ", "hiệu quả", "nên dùng", "có ích") → lỗi validator, gợi ý đổi sang `evidence`.
  Danh sách từ khóa là hằng số; ghi `# ponytail:` về giới hạn heuristic.
- Gói review cổng 1 (HTML hiện có): claim `mechanism` hiển thị thành nhóm riêng
  "Cơ chế — cần kiểm độ đúng giải phẫu", kèm `visual.motion` của lớp explainer tham chiếu nếu có.
- Test: domain evidence + review HTML snapshot/contains.

## Task 3 — Script `arc_beat` + lint (spec §3, §8)

- `ScriptLine` thêm `arc_beat: int | None` (1–7) và `explainer_layer_id: str | None`.
- `script.format_profile` thêm `"explain_first_v1"`.
- Lint (trong `qa/`, cùng chỗ với lint script hiện có): với `explain_first_v1` — nhịp không đi
  lùi (cho phép lặp nhịp 2–6 khi bắt đầu chương mới, đánh dấu bằng dòng có `arc_beat` 2 sau 6);
  mọi dòng có `explainer_layer_id` hợp lệ; cảnh báo (không chặn) khi tỷ trọng ước lượng theo số
  từ lệch khỏi khoảng spec §3; lỗi khi lời thoại dùng thuật ngữ trong `terms_introduced` của lớp
  chưa xuất hiện trước đó.
- Test: `tests/qa/` cho từng luật; script cũ (`legacy`, `hook_outro_v1`) không bị lint mới.

## Task 4 — Nối explainer vào `evidence_ready` (spec §8)

- Project v2 thêm `content_profile: Literal["legacy", "explain_first_v1"] = "legacy"`; project
  tạo mới qua `create_project_v2` mặc định `explain_first_v1`. Project cũ đọc lên là `legacy`.
- Với `explain_first_v1`: chuyển `research_in_progress → evidence_ready` yêu cầu thêm explainer
  hợp lệ (Task 1) và mọi `claim_ids` của explainer tồn tại trong ledger. Thiếu → lỗi rõ ràng,
  state không đổi. `legacy` giữ nguyên hành vi.
- Operator/CLI: thông báo bước tiếp theo nhắc tạo explainer khi thiếu.
- Test: chuyển state cho cả hai profile; fixture v1/v2 cũ không đổi byte.

## Task 5 — Sàng lọc nhanh `Screener` + `dual_llm` (spec §6)

- `src/healthvideo/evidence/screening.py`: `ScreeningDecision` (`include|exclude|unsure`,
  `reason`, `probability: float|None`, `reviewer`), protocol `Judge.judge(record, criteria)`.
- `dual_llm`: hai lượt judge độc lập (không thấy kết quả nhau); khác nhau hoặc có `unsure`
  → lượt thứ ba nhận cả hai lý do. Kết quả cuối + từng lượt ghi vào `screening.csv`
  (id, title, year, pub_type, decision, reason, reviewer_1, reviewer_2, arbiter).
- `CommandJudge`: chạy lệnh trong env `HEALTHVIDEO_SCREEN_CMD` (ví dụ `claude -p` hoặc
  `codex exec`), gửi prompt qua stdin, đọc JSON từ stdout; lỗi/JSON sai → `unsure` + lý do, không crash.
  Không lưu key; không gọi mạng trong test (dùng fake judge).
- CLI: `healthvideo evidence screen <project> --criteria <yaml> --input <candidates.jsonl>` ghi
  `screening.csv` vào thư mục research của revision. Kết quả chỉ là gợi ý: **không** thêm nguồn
  vào ledger.
- Test: đồng thuận, bất đồng → arbiter, judge lỗi, CSV đúng cột, ledger không đổi.

## Task 6 — Storyboard visual kinds mới (Python)

- Storyboard `visual` Literal thêm `anatomy_animation`, `process_animation`, `comparison`,
  `timelapse`; scene thêm `explainer_layer_id` và `anatomy: {subject, state: normal|diseased,
  severity: 0–1, motion}` (bắt buộc khi visual thuộc 4 kind mới).
- Render input truyền các trường mới sang Remotion; visual budget có profile `explain_first_v1`
  theo tỷ lệ spec §7 (cơ chế 55–70%, bằng chứng 15–25%, chữ/outro 10–15%, AI ≤5%).
- Test: schema, render input, visual budget.

## Task 7 — Thư viện cơ quan + scene Remotion (TypeScript)

- `video/src/anatomy/`: `palette.ts` (Kurzgesagt-like: nền xanh đậm, màu bão hòa, không viền
  đen, bóng mềm), `ArterySection.tsx` (mặt cắt động mạch: thành mạch, lòng mạch, dòng hồng cầu;
  `state`, `severity` điều khiển độ dày thành và lòng hẹp), `Heart.tsx` (tim bơm theo nhịp).
  Chuyển động **chỉ** từ `useCurrentFrame()`/`interpolate`/`spring`; không dùng thư viện chạy
  theo đồng hồ thực.
- Scenes: `AnatomyScene`, `ProcessScene`, `ComparisonScene` (hai trạng thái cạnh nhau),
  `TimelapseScene` (severity tăng theo frame). Dùng layout 16:9 từ Task 0.
- Đọc skill `motion-design`, `remotion-markup` trước khi viết.
- Test vitest: render từng scene ở vài frame, severity đổi hình học, typecheck.

## Task 8 — `healthvideo review frames` (contact sheet, spec §7)

- Render bản nháp `--scale=0.5` qua runner Remotion hiện có, lấy frame tại `start_frame + 9`
  mỗi cảnh (kẹp trong thời lượng) bằng FFmpeg, ghép sheet 4×2 có nhãn thời gian bằng Pillow,
  ghi vào thư mục render bị gitignore. Cờ `--from/--to/--every` để lấy mẫu dày.
- Gói cổng duyệt 2 đính kèm sheet các cảnh 4 kind cơ chế.
- Test: tính mốc frame, tile ảnh (ảnh giả), không render thật trong unit test.

## Task 9 — Thí điểm (người dùng + Claude, không giao Codex)

`do-huyet-ap-khong-trieu-chung`: orientation → brief do bác sĩ xác nhận → ledger + explainer
→ script → cổng 1 → produce 3–5 phút 16:9 → review frames → cổng 2. Đo tiêu chí spec §10.

## Thứ tự và song song

```text
T0 → T1 → T2 → T3 → T4 → T5
          └──────────→ T6 → T7 → T8 → T9
```

T7 (TypeScript, `video/`) chỉ phụ thuộc T6 (contract props). T5 độc lập với T6–T8.
Mỗi lúc tối đa hai Codex chạy song song, trên hai worktree khác nhau, không chung file.
