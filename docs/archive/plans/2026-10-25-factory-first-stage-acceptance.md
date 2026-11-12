# Factory-first staged acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện xưởng gọn, điều khiển và nghiệm thu từng giai đoạn qua app; sau đó sản xuất A–Z theo chuẩn đã chấp nhận.

**Architecture:** Giữ Python/HTML, Remotion và hai cổng hiện có. Tách khu thử dưới `cache/factory-test/`; app tái dùng workflow thay vì tạo pipeline mới. Tiêu chuẩn có phiên bản, tài nguyên Muse nhập như ảnh có sẵn với provenance; không xây API/connector khi chưa chứng minh khả năng.

**Tech Stack:** Python ≥3.11, pathlib, Pydantic hiện có, PyYAML, HTML/JavaScript thuần, pytest, Ruff, Remotion/React, Vitest, FFmpeg; Windows/PowerShell. Không thêm framework frontend hay database.

**Spec:** `docs/superpowers/specs/2026-10-25-factory-first-stage-acceptance-design.md` — người dùng duyệt ngày 2026-10-25.

## Global Constraints

- Không yêu cầu bác sĩ dùng PowerShell. Thiết kế gọn, tận dụng hệ thống hiện có.
- Không tự bật xưởng hay tiếp tục hàng đợi thật.
- Chưa tiếp tục sửa storyboard gout, chưa tạo audio/render cho gout.
- Giữ hai cổng y khoa/video và PIN ở máy bác sĩ. Không thêm cổng nội dung thứ ba.
- Kiểm thử phần mềm dùng fixture có sẵn hoặc dữ liệu phi y khoa, không bịa nghiên cứu/nguồn và không phát sinh API trả phí.
- Không tự xuất bản; không nhận PIN trong chat/file/env; không commit key, audio, render, cache hay toàn văn có bản quyền.
- AI clip chưa thuộc phạm vi này vì spec hiện loại AI video.
- Góp ý thử nghiệm là nháp; chỉ nút chấp nhận rõ ràng của bác sĩ trong app mới tạo phiên bản tiêu chuẩn đã nghiệm thu cho giai đoạn.
- Mỗi task cập nhật README trong cùng commit, review trước merge; giữ mọi thay đổi người dùng đang có. Không squash/merge vào master trước khi task đã qua kiểm tra.

## Review Focus

1. App đang mở dự án thật nhưng chuyển sang thử: mọi start/retry/accept phải ở đúng root, không gọi worker sản xuất (Task 4, 8).
2. Browser cũ gửi lại quyết định sau khi thay revision/mẫu/chuẩn: từ chối ghi chuẩn hoặc quyết định nhầm bản (Task 5, 8).
3. Dịch vụ trả audio lỗi tạm thời hoặc hết credit: không coi audio hỏng là QA nội dung, không lặp chi phí vô hạn (Task 2, 3).
4. Đường dẫn ảnh ngoài thư mục, SVG có script, ảnh không có provenance/giấy phép: từ chối import/dùng, không phát sinh script khi preview (Task 7).
5. Mẫu thử lỗi hoặc bác sĩ không chấp nhận: giữ chuẩn cũ và giới hạn giai đoạn, không tự mở chạy A–Z (Task 5, 8, 9).

## Quy ước thực thi và kiểm tra

Thực hiện trong worktree `codex/gout-production-cache` hiện có. Không reset/stash hay đưa bốn file sửa dở vào commit tài liệu. Dùng Python/venv và node_modules ở checkout gốc nếu chưa có trong worktree; luôn đặt PYTHONPATH tới `src` của worktree, cwd là worktree. Không copy `.env` hay venv vào Git.

PowerShell (định nghĩa lại biến trong mỗi phiên lệnh):

```powershell
$pyhPython = 'E:/Protect Your Health/.venv/Scripts/python.exe'
$pyhRuff = 'E:/Protect Your Health/.venv/Scripts/ruff.exe'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& $pyhPython -m pytest -q <test paths>
& $pyhRuff check src tests
git diff --check
```

Mỗi task: viết test hành vi → thấy FAIL đúng lý do → sửa tối thiểu → test liên quan PASS → Ruff/diff check → review → cập nhật README và commit chỉ file task. Với task chỉ tài liệu/spike không viết test phản chiếu nội dung tài liệu. CHECK-ALL cuối: `pytest -q` (0 failed), `ruff check src tests`, `corepack pnpm --dir video test`, `corepack pnpm --dir video typecheck`, `git diff --check`. Cài dependency đúng lockfile nếu thiếu; không đổi phiên bản để qua test.

## Bản đồ file và trách nhiệm

| Vùng | File chính | Trách nhiệm |
|---|---|---|
| Độ tin cậy | `workflows/produce.py`, `workflows/runner.py`, mới `workflows/production_retry.py`; `tts/{vibi,elevenlabs,normalize}.py` | Cache, phân loại và giới hạn retry |
| Khu thử | mới `workflows/factory_trials.py`, `tests/fixtures/factory-trials/` | Root riêng, mẫu và bằng chứng thử |
| Tiêu chuẩn | mới `workflows/factory_standards.py`; `workflows/standards.py` | Nháp, bản được chấp nhận, phạm vi và snapshot |
| App | `workflows/dashboard.py`, `workflows/dashboard.html`; mới `workflows/dashboard_operations.py` | Routing mỏng; thao tác dự án; UI và nghiệm thu |
| Thư viện | mới `workflows/asset_library.py`; `workflows/review_frames.py` | Danh sách/import/binding tài nguyên |
| Hợp đồng sản xuất | `workflows/{runner,factory_deps,create_project_v2,gate_review,package}.py` | Gắn chuẩn, đúng gate và đóng băng |
| Kiểm thử | `tests/workflows/test_*`, mới `tests/ui/test_factory_app.py` | Python hợp đồng và browser thật |

Không thêm field vào ProjectManifestV2 cho chế độ TEST; chế độ được quyết định từ root server riêng. Không đổi schema AssetRecord chỉ để nhập ảnh Muse: dùng `kind=background`, `semantic=false`, SHA-256 bắt buộc, `storyboard_role=whiteboard` và nguồn/giấy phép thật. Metadata prompt/ngày/import nằm ở chỉ mục thư viện; không giả ảnh Muse là recipe FLUX.

### Task 1: Chốt baseline, đồng bộ handoff và kiểm chứng đường Muse

**Files:** Modify `docs/HANDOFF.md`, spec đã duyệt, `README.md`; Create `docs/reference/muse-integration-findings.md`.
**Interfaces:** Produces tài liệu kết quả `status: verified|unavailable|needs_login`, ngày, URL tài liệu chính thức, công cụ ảnh thực có, cách tải, điều kiện dùng thương mại, giới hạn đã biết/chưa biết và đường tích hợp chọn. Không lưu cookie/token hoặc thông tin tài khoản.

- [ ] Đổi trạng thái spec thành đã duyệt; cập nhật HANDOFF theo thứ tự xưởng trước, giữ lịch sử và phần Muse ở bản `E:/Protect Your Health/docs/HANDOFF.md` chưa commit. Không ghi đè phần thêm của người dùng khi merge tài liệu.
- [ ] Chạy baseline CHECK-ALL trên bản đang có; báo riêng lỗi sẵn có và hai finding review chưa xong. Ghi SHA và file đang bẩn.
- [ ] Dùng browser tool xem phiên Muse có sẵn; đọc skill computer-use nếu dùng UI. Chỉ kiểm chứng tính năng/đường xuất/quyền sử dụng; không đăng nhập thay người dùng. Nếu cần mẫu sau khi đã hiển thị phạm vi thử, tối đa 1 ảnh phi y khoa, không AI clip; giữ trong `cache/factory-test/`. Không chạy batch.
- [ ] Chọn đường đơn giản đã chứng minh: agent dùng browser rồi import file, hoặc FLUX + import file. Không có tài khoản/khả năng chưa chứng minh thì ghi `needs_login/unavailable`, không chặn task còn lại. API connector công khai không thuộc kế hoạch.
- [ ] Review và commit tài liệu riêng: `docs: align factory-first scope and record Muse integration findings`.

### Task 2: Cache TTS trả phí và lỗi audio nhà cung cấp

**Files:** Modify `src/healthvideo/workflows/produce.py`, `src/healthvideo/tts/{vibi,elevenlabs,normalize}.py`; Test `tests/workflows/test_voice_production.py`, `tests/tts/{test_vibi,test_elevenlabs,test_normalize}.py`.
**Interfaces:** Giữ `_synthesize_cached_line(tts, request, output, *, cache_dir) -> None`; key là full TTSRequest + `provider_identity(tts)`, gồm normalization. Lỗi audio mới sinh không hợp lệ chuyển thành lỗi provider `RuntimeError` đã làm sạch; lỗi request sai speed/tag vẫn là `ValueError`. Cache hit không tạo usage request mới.

- [ ] Bổ sung test tái hiện với fake Vibi opener: audio silent/unreadable phải là lỗi retryable provider, không cache; lỗi speed/tag vẫn xác định. Giữ test nhánh hiện có: thất bại render rồi chạy lại không gọi TTS; đổi text/language/speed/voice/model/runtime thì miss; hash/WAV hỏng thì tạo lại; có normalized wrapper.
- [ ] Chạy `pytest -q tests/workflows/test_voice_production.py tests/tts/test_vibi.py tests/tts/test_normalize.py` và ghi FAIL đúng trước sửa.
- [ ] Hoàn thiện bản sửa đang dở; thêm Vibi vào cache/usage promotion; bắt riêng lỗi WAV mới ở adapter/wrapper để tránh biến lỗi tạm thời thành hold nội dung. Giữ receipt ghi nguyên tử, không cache kết quả chưa kiểm.
- [ ] Chạy các test trên cộng `tests/tts/test_elevenlabs.py tests/workflows/test_produce.py`; PASS, Ruff/diff check và review.
- [ ] README + commit: `fix: reuse paid TTS lines and classify invalid provider audio`.

### Task 3: Lỗi xác định dừng, lỗi tạm thời thử lại hữu hạn

**Files:** Create `src/healthvideo/workflows/production_retry.py`, `tests/workflows/test_production_retry.py`; Modify `workflows/{runner,factory}.py`, `tests/workflows/test_run_queue.py`, `tests/test_factory_operator.py`.
**Interfaces:** `production_fingerprint(root: Path, project_dir: Path, state: WorkflowState) -> str`; `retry_status(root, project_dir, state) -> dict`; `record_failure(root, project_dir, state, error: Exception) -> None`; `clear_retry(root, slug: str) -> None`. Store `topics/logs/<slug>/production-retry.yaml`: fingerprint, kind (`validation|transient`), attempts, sanitized reason, `retry_after` UTC. `retry_status` trả `allowed`, `kind`, `attempts`, `reason`, `retry_after`; không phát sinh network.

- [ ] Test: cùng ValueError chạy 3 chu kỳ chỉ gọi produce 1 lần; sửa storyboard/asset bytes/visual-review/voice/code thì được thử lại; OSError/provider RuntimeError chỉ được tối đa 3 lần tự động cho một fingerprint, backoff 120s rồi 600s; đến lần 3 giữ chặn qua restart. Dùng clock inject hoặc monkeypatch, không ngủ thật.
- [ ] Chạy `pytest -q tests/workflows/test_production_retry.py tests/workflows/test_run_queue.py` thấy FAIL cho giới hạn/khôi phục sau sửa.
- [ ] Chuyển phần fingerprint/hold dở khỏi runner vào module riêng; dùng nguồn code thực đang import nếu root dữ liệu khác worktree. Bọc cả produce sau visual_review. Khi thành công xóa retry record; không xóa block note do nguyên nhân khác.
- [ ] Chạy test trên + `tests/test_factory_operator.py`; PASS, review. Không coi file hold YAML lỗi là được tự do gọi paid service: báo lỗi cần khôi phục record.
- [ ] README + commit: `fix: bound production retries and resume after input repairs`.

### Task 4: Khu thử xưởng tách khỏi sản xuất

**Files:** Create `src/healthvideo/workflows/factory_trials.py`, `tests/workflows/test_factory_trials.py`, `tests/fixtures/factory-trials/README.md`; Modify `workflows/dashboard.py`, `tests/workflows/test_dashboard.py`.
**Interfaces:** `trial_root(root: Path) -> Path` = `root/cache/factory-test`; `create_trial(root: Path, stage: int) -> dict` tạo ID ngẫu nhiên dưới root này; `trial_bundle(root: Path, trial_id: str) -> dict`; `run_trial(root, trial_id, *, real_service: bool=False) -> dict`. Trial record: id, stage 1–4, status, input_hash, outputs (relative path/hash), events. Offline runner mặc định; không đưa trial vào `topics/queue.yaml` của production.

- [ ] Test `test_trial_never_starts_production_worker`: monkeypatch factory.start_background/paid providers fail nếu bị gọi; create/run stage 1–4 chỉ ghi root thử. Test slug/path traversal, khởi động lại đọc được record, output hash mismatch báo stale, real_service mặc định False và có quota 1 mẫu.
- [ ] Chạy `pytest -q tests/workflows/test_factory_trials.py tests/workflows/test_dashboard.py`, thấy FAIL API/module mới.
- [ ] Tạo storage và runner nhỏ, tái dùng đọc/ghi atomic. Trước mắt mẫu phi y khoa/static đủ kiểm app; không dùng script tự dựng approval thật. Tách `/api/trials/*` khỏi `/api/project/*`; mọi quyết định thử không gọi `decide` đang tự bật production.
- [ ] Chạy test PASS và đọc lại toàn bộ file thay đổi để xác nhận không có gọi `run_queue` với production root. Review.
- [ ] README + commit: `feat: isolate factory trials from production projects`.

### Task 5: Tiêu chuẩn được chấp nhận và phiên bản sản xuất

**Files:** Create `src/healthvideo/workflows/factory_standards.py`, `tests/workflows/test_factory_standards.py`; Modify `workflows/{standards,runner,create_project_v2,gate_review,package}.py`, `tests/test_prompts.py`, test tạo project/gate/package hiện có.
**Interfaces:** `save_standard_draft(root, stage: int, text: str, trial_id: str) -> dict`; `accept_standard(root, stage, *, trial_id: str, expected_input_hash: str, expected_version: int, reviewer: str, now: datetime) -> dict`; `accepted_standards(root) -> dict[int, dict]`; `pin_standards(root, project_dir) -> Path`. Accepted history append-only ở `profiles/factory-standards.yaml`, drafts ở trial root; record gồm id, stage, version tăng dần trong stage, text, reviewer, accepted_at, trial_id, evidence_hash, scope=`channel`. Snapshot `revisions/<rev>/workflow/standards.yaml` bất biến khi tạo project sản xuất mới, đủ 4 giai đoạn đã chấp nhận.

- [ ] Test code: `assert accepted_standards(root) == {}` sau lưu nháp; accept cùng expected hash/version một lần tạo đúng v1, gửi lại/stale hoặc mẫu failed bị từ chối; stage 2 không accept trước stage 1. Sửa chuẩn tạo v2, không sửa snapshot project đã có. Không tạo approval y khoa/video hay bật worker.
- [ ] Chạy `pytest -q tests/workflows/test_factory_standards.py tests/test_prompts.py` thấy FAIL.
- [ ] Implement storage/validation và snapshot; thêm snapshot vào hashes hai gate/package nếu có. Dự án cũ thiếu snapshot vẫn đọc được, không tự backfill hoặc sửa gout. Project mới chỉ được vào sản xuất thật khi đủ bốn chuẩn accepted.
- [ ] `standards.prompt_block(root, *, slug: str | None = None) -> str`: chuẩn accepted toàn kênh + góp ý đúng slug + ghi chú `chung`; không tự đưa góp ý slug khác thành luật. Giữ byte/history cũ; ghi quyết định scope mới cho việc chuyển đổi. Test gout feedback không đi vào chủ đề khác; test package giữ nguyên snapshot và edit snapshot sau duyệt bị chặn. PASS và review.
- [ ] README + commit: `feat: version accepted factory standards and pin production runs`.

### Task 6: Điều khiển chủ đề và xử lý lỗi trong app

**Files:** Create `src/healthvideo/workflows/dashboard_operations.py`, `tests/workflows/test_dashboard_operations.py`; Modify `workflows/{dashboard.py,dashboard.html}`, `tests/workflows/test_dashboard.py`.
**Interfaces:** `add_topic(root: Path, body: dict) -> dict` tái dùng QueueEntry/add_to_queue; `project_operations(root, slug: str) -> dict` trả next_step, gate/revision, retry_status, cache counts; `retry_project(root, slug, *, expected_revision: str) -> dict` clear giới hạn retry chỉ khi input hợp lệ/worker không trùng, không tự đổi approval; `reopen_project(root, slug, *, expected_revision, reviewer, reason, changed: list[str]) -> dict` gọi reopen_gate hiện có tới draft_ready. Mở lại yêu cầu bác sĩ xác nhận trên app, không lấy danh tính suy đoán.

- [ ] Test duplicate/invalid topic không tạo file ngoài queue; POST thiếu token/foreign Host bị chặn; retry stale revision bị chặn; reopen lưu superseded record và đúng invalidation; retry giữ nguyên medical gate khi file đã duyệt bị sửa.
- [ ] Chạy `pytest -q tests/workflows/test_dashboard_operations.py tests/workflows/test_dashboard.py` thấy FAIL.
- [ ] Thêm API `/api/topics/add`, `/api/project/<slug>/operations|retry|reopen` với GET/POST đúng loại; UI đơn giản: nhập chủ đề, xem hàng đợi, lỗi và nút xử lý. Trước start/retry hiển thị bước, số dòng có cache, số yêu cầu dự kiến tối đa; không hứa hit khi chưa kiểm hash/provider. Start cần đủ chuẩn mới, không tự bật vì chỉ mở app.
- [ ] PASS test trên + `tests/test_run_cli.py tests/workflows/test_run_queue.py`; kiểm tra app thao tác thật với fixture offline. Review.
- [ ] README + commit: `feat: manage topics and production recovery in the app`.

### Task 7: Thư viện ảnh, provenance và đường nhập Muse

**Files:** Create `src/healthvideo/workflows/asset_library.py`, `tests/workflows/test_asset_library.py`; Modify `workflows/{dashboard.py,dashboard.html,review_frames.py}`, `tests/workflows/test_review_frames.py`; `.gitignore` nếu cần ignore thư mục import.
**Interfaces:** `list_assets(root: Path, *, slug: str | None = None, kind: str | None = None, query: str = '') -> list[dict]`; `import_image(project_dir: Path, source: Path, *, origin: str, prompt: str, license: str, source_url: str, now: datetime) -> dict`; `bind_image(project_dir, asset_id: str, scene_id: str, *, expected_revision: str) -> None`. Chỉ mục local `assets/library.yaml`, bytes `assets/imported/<sha256>.png`, metadata origin/date/prompt/license/source_url, width/height/hash và used_in. Convert bằng Pillow chỉ raster input PNG/JPEG/WebP, không dùng image editing AI để sửa ảnh ở task này.

- [ ] Test filter/search/gom FLUX/SVG/contact sheet/thumbnail; import image kiểm decode thật, thiếu license/source/prompt không được gắn dùng; filename traversal không thoát root; SVG import bị từ chối (SVG nội bộ preview raster hoặc route không chạy script); trùng hash giữ provenance không ghi đè. Ảnh TEST không bind vào production.
- [ ] Chạy `pytest -q tests/workflows/test_asset_library.py tests/workflows/test_review_frames.py` thấy FAIL.
- [ ] Implement danh sách + copy ảnh chọn qua file picker local phía máy chủ; trả opaque selection ID dùng một lần, POST chỉ nhận ID này (không cho HTTP client tự gửi đường dẫn để đọc file bất kỳ); Muse browser do agent xuất file theo kết quả Task 1 rồi cùng đường import, không hardcode API giả. Ảnh imported dùng existing AssetRecord background và LicenseLedger có hash, giữ provenance sidecar; FLUX recipes giữ nguyên.
- [ ] Bind kiểm current medical approval: thay storyboard/manifest đã duyệt phải reopen trước, không tự bypass. Thêm imported images vào contact sheet và hashes reviewed asset hiện có. Test preview qua `/media` không có quyền đọc ngoài thư mục được phép; ảnh `assets/imported` vào gitignore. PASS và review.
- [ ] README + commit: `feat: browse and import traceable illustration assets`.

### Task 8: Màn nghiệm thu bốn giai đoạn và chốt chuẩn

**Files:** Modify `workflows/{factory_trials.py,factory_standards.py,dashboard.py,dashboard.html}`, test tương ứng; Create `tests/ui/test_factory_app.py`, `tools/factory_trial_samples.py`.
**Interfaces:** GET `/api/trials`, POST `/api/trials/create|run|standard-draft|accept`, GET `/api/trials/<id>/bundle`. `accept` gồm trial_id, stage, expected_input_hash, expected_version, reviewer, text đã xem. Không có field approval y khoa/video, không nhận PIN hoặc key ở trial record. Nút accept tiêu chuẩn là quyết định cấu hình đã tách từ cổng sản phẩm.

- [ ] Test trình duyệt (Playwright nếu runtime có; thêm đúng dev dependency nếu thiếu): nhập chủ đề TEST, xem mẫu stage 1, góp ý/lưu nháp/reload vẫn còn, chấp nhận v1; stage 2 chỉ mở accept sau stage 1; hai tab gửi stale hash/version không ghi nhầm. Mọi nút thử không gọi production start. Python test API kiểm cùng hợp đồng.
- [ ] Chạy `pytest -q tests/ui/test_factory_app.py tests/workflows/test_factory_trials.py tests/workflows/test_factory_standards.py tests/workflows/test_dashboard.py`, thấy FAIL hành vi chưa có.
- [ ] Implement khu Nghiệm thu xưởng trong app, giữ layout hiện có; trình bày một giai đoạn tại một thời điểm, kết quả/bằng chứng/góp ý/chuẩn nháp/Chấp nhận. Mẫu stage 1: fixture nguồn thật đã lưu + script liên kết hoặc phi y khoa không nguồn; stage 2: ảnh và WAV fixture; stage 3: clip Remotion phi y khoa 5–10s dài/dọc, không API; stage 4: bộ caption/thumbnail mẫu + file hash. `tools/factory_trial_samples.py` có `build_samples(root: Path) -> dict[int, list[Path]]`, không tạo approval giả cho project thật.
- [ ] Kiểm thử UI thực tế với app mở đúng trial root; submit failed mẫu/stale version/reject không đổi chuẩn cũ. Media tua được; feedback hiển thị lại đúng đối tượng. Dùng ảnh chụp/mẫu local làm bằng chứng; không commit render. PASS và review.
- [ ] README + commit: `feat: accept factory stages and retain review evidence in the app`.

### Task 9: Kiểm chứng toàn xưởng và bàn giao nghiệm thu giai đoạn 1

**Files:** Modify `README.md`, `docs/HANDOFF.md`; Create `docs/factory-acceptance-guide.md`; sửa lỗi phát hiện ở file task sở hữu với regression test trước sửa.
**Interfaces:** Báo cáo nghiệm thu trong `cache/factory-test/verification.json`: SHA, test command/results, sandbox root, stages technical-ready, accepted_versions thực tế và known limitations. Chỉ khi bác sĩ đã accept đủ 4 stage mới cho mở production; báo cáo technical-ready không thay quyết định bác sĩ.

- [ ] Test end-to-end offline: restart app vẫn giữ trial/chuẩn; legacy project đọc được không mutate; production queue/project/gout hashes trước/sau giống nhau; start chưa đủ chuẩn bị từ chối; snapshot chuẩn mới không ảnh hưởng product cũ; không network trả phí hoặc tự đăng bài.
- [ ] Chạy CHECK-ALL và test UI; kết quả phải 0 failed, ghi số pass/skip có lý do. Rà branch toàn bộ trước merge; sửa mọi issue quan trọng rồi chạy lại test bị ảnh hưởng.
- [ ] Kiểm shortcut Desktop trỏ tới code đã kiểm, không trỏ worktree sắp bị dọn; chỉ cập nhật sau tích hợp bản đã kiểm vào master. Không đổi key, không auto start worker. Giữ dữ liệu E:/Protect Your Health; merge HANDOFF có phần Muse của người dùng.
- [ ] Commit/squash-merge theo quy tắc repo, cập nhật hướng dẫn thao tác app và known limitations. Không archive worktree khi còn file dở chưa được bảo toàn. Đưa bác sĩ xem nghiệm thu stage 1; chưa đòi chấp nhận stage 2–4 cùng lúc.
- [ ] Dừng ở nghiệm thu giai đoạn 1 nếu cần phản hồi; ghi work_state. Sau mỗi phản hồi sửa đúng task/giai đoạn và kiểm lại, chốt phiên bản khi bác sĩ bấm chấp nhận. Chỉ sau đủ bốn chuẩn mới chuyển sang công việc sản phẩm gout.

## Thứ tự, điểm dừng và tiêu chí xong

Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. Muse needs_login/unavailable không chặn Task 2–9; ghi khả năng chưa có và dùng import/FLUX. Không song song sửa dashboard/runner vì dùng chung file và hợp đồng.

Bàn giao kỹ thuật đầu tiên: app đủ chức năng thử và stage 1 technical-ready, người dùng chưa cần duyệt toàn bộ xưởng một lần. Các mẫu stage sau có thể kiểm kỹ thuật trước, nhưng chốt chuẩn và chỉnh theo góp ý theo thứ tự 1→2→3→4. Xưởng hoàn thành khi bác sĩ chấp nhận cả bốn giai đoạn, mọi check pass, app dùng bản tích hợp và production chỉ dùng chuẩn đã chốt. Tạo sản phẩm là việc kế tiếp, không nằm trong task triển khai này.

## Tự rà kế hoạch

- Spec §1–2: Task 1 và baseline/giữ dữ liệu; §3.1: Task 4/6/8; §3.2: Task 2/3; §3.3: Task 1/7; §3.4: Task 5/8; §4: Task 8/9; §5: constraints + test cách ly; §6: interfaces/file map trên.
- Mọi Review Focus đều có test task sở hữu. Không giả định có API Muse, không thêm loại AI video, không mở production bằng acceptance giả.
- Chuẩn mới chỉ snapshot ở project mới; approval hashes bao gồm snapshot nếu có, legacy projects không backfill. Trial accept không gọi product decide.
- Native execution được đề xuất vì task nối tiếp và cùng sửa app/runner; giữ một lượt review độc lập cho toàn branch trước tích hợp.
