# Bàn giao cho codex (2026-11-14, từ Claude)

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
