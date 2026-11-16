# Bàn giao cho codex (2026-11-14, từ Claude)

## Cập nhật Antigravity Swarm (2026-11-15 — nối tiếp bàn giao 18:52 UTC+7)

- **7 điểm rà `repair_service` & 16 vai Company 2.0 + rà `gate_for_project` + vá deadlock + nối CLI:** đã hoàn tất toàn bộ 7 điểm rà `repair_service` (PID/token, `_maintenance` giữ lock & `recover_interrupted_repairs()` kể cả khi gián đoạn lúc `phase: diagnosing`, khóa cứng `_IGNORED_SNAPSHOT_DIRS` / `_restore_workspace` không chạm `projects/`/`topics/`/`docs/`/runtime `profiles/`, `_verify_retry_validated`, nhánh `delegate` giữ cổng, cooldown quota/timeout, `stop_background()`), cập nhật 16 vai (`company.yaml`, `dashboard.html`, `tests/test_company.py`, `tests/workflows/test_dashboard.py`), đồng bộ `factory.gate_for_project` / `require_passed_review` Trạm 07/12 trên `cli.py` & `telegram_bot.py`, vá deadlock `_maker_slots_for_critic` trong `src/healthvideo/workflows/runner.py`, nối `repair_service.ensure_background` / `stop_background` vào `cli.xuong` và chạy smoke subprocess cô lập thành công.
- **Vá 3 bug phát hiện thêm trong đợt xử lý cuối:**
  - `video/src/anatomy/IntestinalVitaminCAbsorption.tsx`: bổ sung `<g data-layer="intestinal-absorption">...</g>` khớp `library.json`.
  - `src/healthvideo/agents.py`: mở rộng `QUOTA_PATTERNS`, `_RESET_AT`/`parse_reset`, `_ACCOUNT` bắt thông báo kiểu `"You've hit your weekly limit · resets 5pm (Asia/Ho_Chi_Minh)"` (+ regression tests ở `tests/test_agents.py`).
  - `src/healthvideo/workflows/storyboard_design.py` & `src/healthvideo/workflows/draft.py`: `shutil.rmtree(staging, ignore_errors=True)` trong `finally:` để `[WinError 32]` Windows không che mất `ValueError` validation (+ test `PermissionError` ở `tests/workflows/test_draft.py`).
- **Đồng bộ Trạm 07/12 cho toàn bộ 26 file test còn tồn:** xử lý dứt điểm từ **84 failed, 12 errors** -> **0**; bổ sung `submit_medical_review_fixture` & `submit_video_fixture` trong `tests/helpers.py`, sửa typo `submission == "medical_review"` ở `tests/workflows/test_explain_first.py`; không sửa `tests/fixtures/*`, không nới bất kỳ cổng duyệt nào.
- **Nghiệm thu cuối cùng toàn hệ thống:** `.venv/Scripts/python.exe -m pytest -q --tb=short` đạt **2030 passed, 1 skipped, 0 failed, 0 errors** (`318.66s`); `.venv/Scripts/python.exe -m ruff check src tests tools` đạt; `git diff --check` exit 0; `git status --short tests/fixtures` rỗng; `pnpm --dir video typecheck` exit 0; `pnpm --dir video test` đạt **36/36 files, 270/270 tests**.
- **Trạng thái xưởng sống (không ngắt `PID 48216`):** `thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi` đang chạy active ở `production_in_progress` (đã có `video.mp4`, `video-qa.json`, `pronunciation-qa.json` cảnh báo 210 khác biệt phiên âm/Whisper để bác sĩ quyết định ở cổng video + PIN, active markers `.agent-running`, `.chat-step-running`, `.job-badbcb46eb594f369c4c2bc78767fa86.json`). 4 topic còn lại (`an-gao-lut-...`, `hoc-xuong-ca-...`, `men-gan-tang-va-thuoc-bo-gan`, `uong-1-vien-c-sui-...`) vẫn ở `draft_ready` với `blocked.txt` cũ từ trước khi vá; khi `PID 48216` rảnh cần `healthvideo xuong --stop` rồi `healthvideo xuong --background` từ shell thường để nạp mã mới. Chưa tự commit hay push; giữ nguyên các thay đổi của phiên khác.

## Bàn giao Codex ngày 2026-11-15 lúc 18:52 UTC+7 — tạm dừng theo yêu cầu bác sĩ

### Mục tiêu và yêu cầu mới nhất

Bác sĩ muốn xưởng tự nhận lỗi, tìm nguyên nhân, sửa và thử lại. Leader chịu trách nhiệm phân tích, giao việc và nghiệm thu. Có thêm một agent Kỹ sư sửa lỗi chạy độc lập. Chỉ đưa bác sĩ duyệt y khoa khi trạm 07 đạt với kịch bản hiện hành. Cổng video cần cả trạm 07 và 12 đạt với dữ liệu hiện hành. Bác sĩ yêu cầu tạm dừng triển khai và bàn giao tại thời điểm này.

### Đã chạy và kiểm chứng trong phiên này

- Scheduler trong `src/healthvideo/workflows/runner.py` đã thay vòng chờ cả batch bằng theo dõi future và kiểm tra thay đổi hàng đợi mỗi giây khi còn tác vụ đang chạy. Nhận được dự án vừa duyệt, vừa gỡ retry hoặc mới thêm trong lúc dự án khác còn chạy. Không giao trùng cùng slug. Khóa GPU hiện hành vẫn được dùng. Có 3 test hồi quy trong `tests/workflows/test_parallel_company.py`.
- Đã sửa `script_review.py`, `product_review.py`, `draft.py`, `produce.py`, `gate_review.py` và thêm `factory.gate_for_project`. Hết vòng sửa mà điểm chưa đạt sẽ báo lỗi tại xưởng. Không tự nộp sang bác sĩ. Cả API duyệt và dashboard kiểm kết quả critic cùng hash hiện hành. Đã sửa fixture synthetic để ghi rõ kết quả critic trong tests.
- Bộ kiểm liên quan scheduler, critic, gate và dashboard đạt **191 test**, Ruff sạch trước khi bắt đầu phần agent sửa lỗi mới. Đã nạp phần này vào xưởng thật, PID **48216**. Đã quan sát trạm 9 dựng dự án men gan đồng thời agent làm hóc xương cá và C sủi.
- FLUX trước đó sập `memory allocation ... failed`, exit `3221226505`. `tools/flux/generate.py` đã chuyển Qwen sang `device_map="auto"`, pipeline dùng `enable_sequential_cpu_offload()`. Tạo thật PNG 384×256 thành công tại `cache/flux-memory-smoke.png`. Chưa nghiệm thu video men gan cuối cùng.
- Studio đã trả HTTP 200 tại `http://127.0.0.1:3000`. `dashboard.py` chờ HTTP sẵn sàng trước khi trả URL và dùng lại Studio đang chạy. Lỗi ban đầu do mở tab trước khi build xong khoảng 35 giây. Bộ dashboard + FLUX trước đợt sửa critic đạt 86 test.
- `cli.py` lệnh `step build-ledger` đã ưu tiên `claims.yaml` + `records.yaml` hiện hành trước ledger cũ. Nguyên nhân hóc xương cá thiếu E06 là bản tổng hợp cũ được ưu tiên đọc lại. 65 test CLI đạt ở lần sửa này.
- Validator outro chấp nhận câu kết mới trong doctor-feedback và câu cũ để đọc revision cũ. Đã khởi động lại app và xưởng để nạp mã. Tab dashboard cũ có thể báo `forbidden` sau restart vì token phiên đổi. Cần Ctrl+F5 và mở lại gói duyệt.
- Medical expert đã được bác sĩ chọn chỉ `agy / gemini-4-carbon-medium`, một model trong override của `profiles/company.yaml`.

### Agent sửa lỗi mới đang làm dở — chưa kích hoạt

- `profiles/company.yaml` thêm `repair_engineer`, tên Kỹ sư sửa lỗi, tier medium, skill `pyh-repair-engineer`, step `repair`.
- Mới tạo `.agents/skills/pyh-repair-engineer/SKILL.md`. Đã bổ sung trách nhiệm phân tích lỗi và nghiệm thu vào `.agents/skills/pyh-coordinator/SKILL.md` và `pyh-coordinator-senior/SKILL.md`.
- Mới tạo `src/healthvideo/workflows/repair_service.py`. Prototype chạy process riêng, dùng singleton kernel lock qua `factory.FactoryLock(root / 'cache/repair-worker')`. Quét lỗi dự án khi xưởng đang chạy. Leader chuyên sâu tạo `Diagnosis`, engineer sửa file kỹ thuật được giao, Python chạy pytest và Ruff, Leader ghi `Acceptance`, rồi gỡ retry. Giới hạn 2 lượt sửa cho mỗi revision. Log tại `topics/logs/repair/<slug>/<attempt>/`, trạng thái tại `topics/logs/<slug>/leader-repair.yaml`.
- Prototype chỉ cho sửa file hiện có dưới `src/`, `tools/`, `video/`, với pytest hiện có do Leader chỉ định. Lỗi cần đổi dữ kiện y khoa, hồ sơ đã duyệt, cấu hình tài khoản hoặc thiếu dữ kiện được giữ lại và ghi vai cần tiếp nhận. Chưa có nhánh tự giao lại writer/medical_expert cho các trường hợp đó.
- Prototype chờ toàn xưởng rảnh trước khi sửa code dùng chung, dừng xưởng, sửa/test/nghiệm thu, khôi phục nội dung file khai báo nếu lỗi, rồi bật lại xưởng. Leader có thể chẩn đoán trong lúc dự án khác chạy. Chưa kiểm chứng sửa lỗi thật hoặc crash recovery.
- Dashboard thêm `repair_engineer` vào `WS_COUNTER_BASE`. Chưa nạp phần giao diện mới này vào app đang chạy.
- `tests/workflows/test_repair_service.py` có 7 trường hợp mới, đều đạt trong lần chạy chung với tests company. Tổng kết lần chạy **28 passed, 2 failed**. Hai test fail là `tests/test_company.py::test_role_skills_follow_spec_table` và `::test_split_script_roles_have_new_names`, vì kỳ vọng vẫn là 15 vai, thiếu vai mới. Chưa sửa hai kỳ vọng khi bác sĩ yêu cầu tạm dừng.
- Ruff của repair service, CLI và test mới đã đạt. Chưa chạy toàn suite sau khi thêm vai thứ 16.
- **Chưa gọi `ensure_background()` trên repo thật. Đã gỡ hook tự bật service khỏi CLI trước bàn giao để phần chưa nghiệm thu không tự chạy khi ai khởi động lại xưởng.** Khi tiếp tục cần hoàn thiện, kiểm thử và chủ động nối service vào lifecycle xưởng.

### Điểm cần rà trước khi bật agent sửa lỗi

1. `_active()` đang dùng sự tồn tại marker, cần đối chiếu PID/process token để marker cũ không giữ worker mãi. Cần test công việc đang chạy thật và marker mồ côi.
2. `_maintenance()` đã giữ xưởng dừng tới hết kiểm thử và Leader nghiệm thu, rồi mới bật lại. Cần cơ chế phục hồi bền vững nếu process repair chết giữa lúc sửa. Hiện backup file ở RAM và việc resume nằm trong `finally`. Cần chống một app khác bật xưởng trong lúc maintenance.
3. Kiểm việc engineer chỉ sửa đúng file Leader giao và bảo toàn mọi thay đổi đang có. Hiện phạm vi được chỉ dẫn bằng prompt, Python chỉ kiểm đường dẫn được giao và rollback các file đó khi test/acceptance fail. Chưa có phát hiện thay đổi ngoài phạm vi hoặc file mới do agent tạo.
4. `retry_requested` hiện được đổi sang `validated` khi không còn blocked và project không active. Cần bằng chứng lượt thử lại thực sự đã chạy và validator đạt trước khi Leader kết luận đã phục hồi. Không được nhận chỉ gỡ khóa là đã sửa xong.
5. Sau `hold` hiện giữ `needs_attention`. Cần thiết kế đường Leader giao đúng writer/medical_expert/editor khi lỗi nằm ở nội dung, với cổng hiện hành. Không cho chuyên viên kỹ thuật sửa claim hoặc tự tạo báo cáo critic để đạt.
6. Cần kiểm quota/timeout, trạng thái service sau crash và lịch nghỉ giữa hai lượt lỗi. Chưa có smoke thật của chuỗi Leader → engineer → test → Leader nghiệm thu → thử lại.
7. `gate_for_project` lọc dashboard và thông báo. Cần rà các đường CLI/Telegram mở gói duyệt để bảo đảm cùng quy tắc trạm 07/12. Không tự sửa hoặc thu hồi approval bác sĩ đã cấp trước yêu cầu mới.

### Trạng thái máy lúc bàn giao

- API dashboard `127.0.0.1:8765` trả trạng thái xưởng running, PID 48216.
- Có marker production thật của `thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi`. Không có marker agent trong lần kiểm lúc 18:52. Đây là ảnh chụp trạng thái, cần kiểm lại khi tiếp tục.
- Bác sĩ tạm dừng phần triển khai. Phiên này giữ tác vụ dựng đang chạy để bàn giao, không ngắt render.
- Có nhiều thay đổi từ phiên/nhân viên khác trong workspace, gồm anatomy, doctor-feedback và topics/code-review. Không revert hoặc commit gộp chúng. Phiên này chưa tự commit/push.

### Bước tiếp theo khi bác sĩ yêu cầu tiếp tục

1. Đọc đoạn bàn giao này, AGENTS.md, spec company, rồi kiểm status và log mới. Phân biệt lỗi cũ trong `blocked-reason.md` với log lỗi hiện tại.
2. Rà prototype `repair_service.py` theo các điểm trên, cập nhật tests company cho 16 vai và thêm test phục hồi khi service chết, nghiệm thu sau retry, scope file, singleton và quota.
3. Chạy `.venv/Scripts/python.exe -m pytest tests/workflows/test_repair_service.py tests/test_company.py -q`, Ruff, rồi các test scheduler/critic/gate/dashboard liên quan. Bộ 191 test trước đó không chứng minh prototype mới đã nghiệm thu.
4. Sau khi đạt mới nối `ensure_background(root)` vào lifecycle CLI/xưởng, bật service và quan sát một lỗi fixture trong môi trường cô lập. Chỉ sau đó cho xử lý lỗi dự án thật.
5. Kiểm toàn trình video men gan và test render liên quan trước kết luận trạm 9 đã hoàn tất. Bác sĩ vẫn tự duyệt bằng PIN.

### Nơi lấy bằng chứng

- Trạng thái hiện hành qua `.venv/Scripts/healthvideo.exe status` và API dashboard.
- `topics/logs/<slug>/blocked.txt`, `agent-retry.yaml`, `production-retry.yaml` cùng log CLI mới nhất, kể cả `parallel-*`.
- `cache/flux-memory-smoke.log`, `cache/studio.log`.
- Không có observation ID claude-mem mới được tạo trong phiên này. Dùng file và log thật làm nguồn khi tiếp tục.

## Trạng thái mới nhất ngày 2026-11-15

- Đã hoàn tất đóng gói & tích hợp **PYH Company 2.0 + Channel Connections** trên checkout chính `master` (cùng 1 worktree `E:/Protect Your Health`, 1 nhánh `* master`; đã sao lưu báo cáo và gắn tag `archive/*` cho 14 nhánh chưa gộp trước khi dọn 20 worktree phụ và 41 nhánh cũ). Đạt **35/38 `done`** trên [docs/progress.yaml](progress.yaml); còn **3/38 `doing`** (`CH.3`, `4.2`, `4.3`) đang vận hành tự động về cổng duyệt của bác sĩ.
- **Bảo mật `.gitignore`:** đã khóa `client_secret*.json`, `topics/logs/`, `topics/*.log`, `topics/.*.lock`, `topics/chat.jsonl`, `topics/channel-publications/`, `topics/channel-metrics.yaml`, `topics/discovered/`, `topics/inbox/`.
- **Kết nối kênh (`CH.2`):** YouTube `Protect Your Health` OAuth (`can_sync=True, can_publish=True`) đồng bộ thật sạch (0 video); TikTok phiên trình duyệt Autotok DPAPI `connected` (`can_publish=True`, không analytics theo spec bổ sung `2026-11-15`).
- **Độc lập Maker/Critic, Benchmark & Bền bỉ Agent (`R1.5` & `4.3`):** đã sửa `src/healthvideo/agents.py` để `exclude_slots` không rơi về `list(slots)` khi hết ứng viên critic, và phân loại CLI thoát khác 0 kèm log rỗng 0 byte thành `transient` (cho phép failover/thử lại có giới hạn thay vì khóa `agent_error`); đã chạy 7 lượt CLI thật tại `cache/dev-lead/model-benchmark/2026-11-15/` và ghi vào `docs/reference/agent-model-evaluation.md`.
- **Giọng đọc, Smoke dựng thật & Cài đặt sạch (`R1.8` & `4.4`):** giữ `speech-2.8-hd`, đã duyệt toàn bộ 9 mục `profiles/pronunciation.vi.yaml` v3; thử Vibi TTS (110 ký tự, 6,84s WAV) + Whisper alignment; chạy thật `PYH_REAL_RENDER_SMOKE=1` `tests/e2e/test_real_production_smoke.py` đạt `1 passed` (83,41s); đã clone sạch nhánh `master` vào `%TEMP%` và chạy `install/install.ps1 -SkipTts` đạt exit `0` (`"HealthVideo installation complete."`, `pyh_skill` và `pyh_claude_command` đều `OK`).
- **UX & Kiểm thử (`3.6`):** nút `#pv-general` ("Nhắn điều phối viên") mở khung chat `#chat-panel` và focus `#chat-input` duy nhất. Toàn suite Python đạt **1.990 passed, 1 skipped** (cộng thêm 1 smoke Remotion thật pass khi bật `PYH_REAL_RENDER_SMOKE=1`), Ruff sạch, Vitest đạt **32 files / 251 tests**, `tsc --noEmit` sạch, `git diff --check` sạch.
- **Đang chờ ở Bước P4 & CH.3 (`4.2`, `4.3`, `CH.3`):** xưởng nền (`PID 40508`) đang chạy 5 chủ đề thật trong `topics/queue.yaml` (gồm `men-gan-tang-va-thuoc-bo-gan`) hướng tới cổng duyệt y khoa bằng PIN và bước đăng kênh sau khi bác sĩ duyệt đủ 2 cổng.

## Cập nhật dev lead 2026-11-15 — kết nối kênh

- Bác sĩ đã lưu cấu hình YouTube nhưng chưa cấp quyền; TikTok chưa configured.
  Sửa UX: Kết nối → hiện liên kết Mở trang cấp quyền Google/TikTok thay vì
  window.open sau await (có thể bị chặn popup); hướng dẫn đăng nhập/cấp quyền rõ.
  13 test UI đạt, Ruff sạch; HTML cập nhật tại checkout chính không restart server.
- Bác sĩ yêu cầu kiểm tiến độ và kết nối **YouTube + TikTok** để đăng trên kênh.
  Chưa có developer/OAuth apps; hướng dẫn: `docs/channel-setup.md` và thẻ thiết lập
  trong app. Không có tài khoản thật đã kết nối hoặc bài đăng thật được nghiệm thu.
- Spec mới: `docs/superpowers/specs/2026-11-15-channel-connection-publishing-design.md`.
  Yêu cầu mới cho phép đăng gói được cấp quyền sau cả hai cổng; không cấp quyền
  agent duyệt cổng/PIN. TikTok private-only khi chưa audit; công cụ chỉ dùng nội bộ
  không đủ tiêu chí Direct Post audit. Không hứa đăng công khai trước khi đủ điều kiện.
- Researcher chỉ phân tích quan sát thực tế, tách dữ liệu nhập và OAuth. Có 0 video
  số liệu tại thời điểm kiểm; không khôi phục pilot, không bật xưởng.
- Có adapter OAuth desktop/DPAPI, sync API, publisher kiểm hash/cổng, chống trùng
  và đối soát; chat chuẩn bị preview, gửi đăng qua app với kênh/nội dung/hiển thị rõ.
- AGY CLI giao diện không phản hồi gần 10 phút, đã dừng; Sol dự phòng hoàn tất.
  UI desktop/mobile kiểm qua Chrome, không overflow/lỗi JS, 12 test UI đạt.
- Kiểm toàn bộ Company 2.0 + kết nối: **1.986 test đạt, 1 bỏ qua**, Ruff/diff sạch.
  Đã nạp 24 file theo scope vào app chính, kiểm thêm 85 test tại checkout chính;
  dashboard khởi động lại, HTTP 200; xưởng vẫn dừng, 0 project, hai kênh chưa cấp quyền. Thay đổi Company 2.0 và kết nối còn chưa commit/push; không nhầm với
  bản runtime/hoạt cảnh `8c9fa8f` đã tích hợp trước đó.
- Chưa xong xưởng: benchmark từng vai R1.5, smoke dựng GPU/giọng R1.8 và kiểm
  toàn trình một video mới sau khi được phép làm pilot. Không dùng test offline
  để coi những việc đó đã nghiệm thu. Publisher chưa tự upload thumbnail YouTube.
- Bác sĩ gửi TiktokAutoUploader trong lúc làm. Đã review `autotok` 2.1.0 tại
  `0bcbbdcff3600fbc09a47b9be107d1d3fd49b260`, chưa cài/chạy. Đây là đường API web
  qua session, khác Direct Post OAuth. Chưa có xác minh account thật/analytics,
  cookie JSON và “published” mới là acceptance. Xem
  `docs/reference/tiktok-autouploader-review.md` trước khi tích hợp adapter.

## Đổi ưu tiên theo yêu cầu bác sĩ 2026-11-14 — đọc trước phần lịch sử

- Bác sĩ dừng toàn bộ pilot để hoàn thiện xưởng, bắt đầu skill từng vai và model.
- Xưởng đã dừng, tiến trình chờ khởi động lại cũ đã hết hạn, queue rỗng. Hai
  project và log riêng giữ tại `cache/pilot-archive/2026-11-14/`; không xóa dữ liệu,
  không tự phục hồi pilot/đòi duyệt gout hoặc bật xưởng.
- Chuẩn nội dung: một người xem, một tầng chính TOFU/MOFU/BOFU, một lời hứa có
  giá trị diễn giải/thực hành. BOFU bác sĩ chọn: thực hành sức khỏe, khám khi cần,
  tin theo dõi kênh, không bán hàng. Không ép đủ ba tầng hoặc đọc lại giáo trình.
- Spec: `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`.
  Model/mẫu thử: `docs/reference/agent-model-evaluation.md`. Tiến độ hiện hành: R1.
- Vòng chuẩn hóa đầu đã sửa 11 skill, đồng bộ prompt và phân model trực tiếp.
  117 test liên quan đạt, Ruff sạch; review độc lập PASS phạm vi skill/prompt/config.
  Writer Sol và critic Carbon medium đã có mẫu thử ngắn; các vai khác chưa được
  kiểm năng lực toàn diện. Không coi đã nghiệm thu xưởng hoặc video.
- Skill/model là bước đầu, chưa khắc phục runtime treo/lỗi là dừng. Tiếp theo:
  retry/log/timeout có giới hạn, giữ cổng/cache; xem lại explain-first và thời lượng,
  tách yêu cầu kỹ thuật dựng khỏi công việc kể chuyện.

**Phần bên dưới là lịch sử trước khi đổi ưu tiên, không phải lệnh tiếp tục gout.**

Claude hết token; codex làm **dev lead** thay, theo `CLAUDE.md` mục 1, 3, 5 (chỗ ghi
"Claude" nay là codex). Tiến độ vẫn ghi ở `docs/progress.yaml`, commit `chore: progress`.
Push cần bác sĩ đồng ý (master đang đi trước `origin/main` vài commit).

## Gout đang ở đâu

- 11:10 bác sĩ duyệt cổng y khoa. Dựng hỏng 3 lần: 12:01 mất kết nối vibi; 12:28 ACE-Step
  (nhạc nền) sập `exit 3221225477`; 12:53 **`Clip CL01 render failed`**
  (`workflows/long_form.py:174`). Nguồn: `topics/logs/xuong.log`,
  `topics/logs/gout-tinh-the-urat/production-retry.yaml`.
- 13:35 bác sĩ bấm mở lại cổng; writer (codex) đang `revise_medical`. Bác sĩ sẽ phải
  duyệt lại. Đã dặn bác sĩ: lần sau dựng hỏng thì báo, đừng mở cổng.
- Lỗi CL01 chưa rõ nguyên nhân vì xưởng nền bỏ stdout của Remotion. Commit `25a7d32` cho
  `factory_deps._run_render_argv` ghi log dựng hỏng vào `topics/logs/render/*.log`.
- Một tác vụ nền của phiên Claude chờ gout về `awaiting_medical_review` và hết việc chạy,
  rồi `healthvideo xuong --stop` + `--background` để nạp `25a7d32`. Nếu phiên Claude đã
  đóng thì tác vụ đó chết theo: kiểm `topics/.xuong.lock` (`started_at` phải sau commit
  25a7d32); nếu xưởng còn chạy code cũ thì khởi động lại lúc gout chờ ở cổng, không giết
  agent đang chạy.

## Việc tiếp theo

1. Sau khi bác sĩ duyệt lại, theo dõi `produce`. Nếu CL01 hỏng tiếp: đọc
   `topics/logs/render/` và sửa gốc (ứng viên: Chrome/GPU hết bộ nhớ khi chạy cùng ACE-Step,
   hoặc dữ liệu clip mới sau khi kịch bản dài ra). Có test tái hiện trước khi sửa.
2. ACE-Step sập là lỗi truy cập bộ nhớ; nếu lặp lại, cân nhắc dọn GPU trước bước nhạc hoặc
   dựng không nhạc. Hỏi bác sĩ trước khi bỏ nhạc.
3. QA phát âm của bản dựng cũ (`renders/video-qa.json`) báo 71 lỗi chặn; xem lại khi có bản
   dựng mới. Câu treo cho bác sĩ ở 2.4: "u-rát", `speech-2.8-hd` hay turbo, hình kim S07.
4. Sau gout: 2.5, 2.6, 2.7, rồi 3.2 (agy làm ở `.claude/worktrees/p3-elevenlabs`, chưa rõ
   trạng thái), 3.5, 3.6, P4.

## Đã chốt trong phiên này (đừng làm lại)

- Phân model ở `profiles/company.yaml` (d856e99): vai nhẹ dùng `gemini-4-hydrogen-medium`;
  y khoa, kiểm duyệt, đạo diễn hình, thợ dựng dùng `gemini-pro-orchestrator`; writer dùng
  codex `gpt-6.1-sol`; không Opus, không astra. Kiểm duyệt kịch bản tối đa 2 vòng.
- Điều phối viên chat nhanh, tự `escalate` sang `coordinator_senior` khi khó.
- 10 nguyên tắc viết của bác sĩ: `profiles/doctor-feedback.yaml` mục `slug: chung`,
  tóm trong `.agents/skills/pyh-writer/SKILL.md`.
- Contact sheet FFmpeg đã gom 50 điều kiện mỗi nhóm (9b8f4ab).
