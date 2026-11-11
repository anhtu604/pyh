# Đánh giá toàn dự án và kế hoạch hoàn thiện (2026-11-11)

Đánh giá trên `master` tại `7ad3cc4`. Kế hoạch này thay phần "Việc tiếp theo" của
`docs/HANDOFF.md` (viết 2026-10-27, đã cũ).

## 1. Kết luận

Xưởng đã đủ chức năng để làm một video từ chủ đề tới gói đăng. Sản phẩm thì chưa có:
sau hai tháng và khoảng 300 commit, chưa video thật nào qua cổng duyệt video. Việc còn
lại không phải là thêm tính năng cho xưởng mà là đưa video gout qua hết đường ống, rồi
lặp lại với chủ đề thứ hai mà không cần Claude sửa tay.

## 2. Hiện trạng đã kiểm

| Hạng mục | Kết quả |
| --- | --- |
| Test Python (`pytest -q`) | 1800 đạt, 1 bỏ qua |
| Ruff (`src tests tools`) | sạch |
| Test video (Vitest) | 251 đạt, 32 file |
| Typecheck video (`tsc --noEmit`) | sạch |
| `healthvideo doctor` | 2 mục FAIL: `pnpm`, `elevenlabs` |
| Quy mô | 22.199 dòng Python nguồn, 26.456 dòng test, 8.789 dòng TypeScript |
| `gan-nhiem-mo-test` | `packaged` (bản thử, không đăng) |
| `gout-tinh-the-urat` | `needs_medical_revision`, bước kế `revise_medical` |
| Xưởng nền | không chạy (PID trong `topics/.xuong.lock` đã chết) |
| Credit vibi | 98.123 còn lại; gout dùng 29.215 ký tự mỗi lần đọc trọn bài |

## 3. Vấn đề, xếp theo mức ảnh hưởng

### 3.1 Gout kẹt vì lỗi bố cục chỉ lộ ra sau cổng y khoa

Ngày 2026-11-07 bước `produce` của gout hỏng liên tiếp, mỗi lần một lỗi khác:

1. `chart_crop=2485/9858 frames outside 15-25%` (25,2%)
2. `Scene S02: beat at 10.0 outside timed scene`
3. `Scene S03: front-loaded entrances all within first 15%` (rồi S23)
4. `CL02: duration 1243 frames must be between 1800 and 5400`

Cả bốn đều phụ thuộc thời lượng giọng đọc thật, mà thời lượng chỉ có sau khi bác sĩ đã
duyệt y khoa. Mỗi lần hỏng, bác sĩ phải mở lại cổng bằng PIN để agent sửa storyboard, rồi
duyệt lại. `21f41af` đã tự dời chữ vào cảnh cho lỗi số 3; ba lỗi còn lại vẫn theo kiểu cũ.
Chủ đề nào cũng sẽ gặp lại chuỗi này.

### 3.2 Chưa có video chuẩn

Nhận xét của bác sĩ ngày 2026-10-24 (phát âm "gout"/"urat", ảnh mở đầu không liên quan,
hình đứng lâu, giọng đều) đã được sửa ở mức code, nhưng chưa có bản dựng mới nào để bác sĩ
xem lại. Còn hai câu hỏi chờ bác sĩ: "u-rát" đọc đúng chưa, và chọn `speech-2.8-hd` hay
turbo. Yêu cầu đổi hình tinh thể ở cảnh S07 (gửi qua chat 2026-11-08) đang xếp hàng.

### 3.3 Dữ liệu chưa được sao lưu

- `master` đi trước `origin/main` 88 commit, chưa push. Toàn bộ công việc từ 2026-10-22
  chỉ nằm trên một ổ đĩa.
- `profiles/doctor-feedback.yaml` (hồ sơ chỉ-thêm của bác sĩ) có 32 dòng chưa commit;
  `profiles/factory-standards.yaml` chưa được Git theo dõi.

### 3.4 Môi trường dựng video đang hỏng

Node trên máy là 26.13.0, không có Corepack đi kèm, và `pnpm` không có trên `PATH`.
`doctor` báo `Cannot launch pnpm safely`. Bước render gọi `pnpm`, nên lần `produce` tới sẽ
hỏng ở đây. (Lần dựng thành công gần nhất là 2026-11-07.)

### 3.5 Rác vận hành

- 12 worktree, 12 nhánh chưa merge. Các nhánh `factory/*` và `feat/dashboard-app` đã vào
  `master` bằng squash-merge nên Git vẫn coi là chưa merge. `feat/m8-3-voicestudio` và
  `feat/script-voice` là hướng đã bỏ.
- Gốc repo có `New Recording.m4a`, `api-docs.zip`, thư mục `.remotion/` chưa ignore,
  thư mục thừa `.worktrees/preventive-health-video-mvp`.
- `topics/code-review.yaml` liệt kê các thư mục skill, không phải việc cần xem.

### 3.6 Tài liệu lệch với code

- `CLAUDE.md` chỉ agent đọc spec 2026-10-22; spec hiện hành là
  `2026-11-08-factory-company-design.md`.
- `docs/HANDOFF.md` vẫn mô tả khóa nghiệm thu 4 giai đoạn đã bỏ ngày 2026-11-07.
- Kế hoạch `2026-11-08-factory-company.md` chưa đánh dấu ô nào dù đã merge; Task 7
  (nghiệm thu trong trình duyệt) mới làm một phần.

### 3.7 Code không còn dùng

`workflows/factory_trials.py` (655 dòng, khu nghiệm thu đã ẩn), `tts/elevenlabs.py`
(bác sĩ đã từ chối giọng này), `tts/asr.py` (không module nào import), 17 trong 30 skill ở
`.agents/skills/`. `jev/` và `video_ai/` đã gỡ khỏi Git, chỉ còn thư mục `__pycache__` ở
checkout chính. Không chặn việc gì, nhưng agent vẫn phải đọc và test vẫn phải chạy.

### 3.8 Đổi hướng quá nhiều

Sáu lần đổi thiết kế trong hai tháng (MVP dọc → video dài → explain-first → tái cấu trúc
xưởng → nghiệm thu 4 giai đoạn → bỏ nghiệm thu → xưởng-công ty). Mỗi lần đều có lý do,
nhưng cộng lại thì xưởng lớn dần còn số video vẫn là không.

## 4. Kế hoạch

Bản chi tiết từng việc (file, người làm, tiêu chí xong) nằm ở `CLAUDE.md` mục 5; trạng thái
nằm ở `docs/progress.yaml`. Dưới đây là bản tóm tắt lúc đánh giá.

Nguyên tắc: từ giờ tới khi gout được bác sĩ duyệt video, không thêm tính năng xưởng. Chỉ
sửa thứ mà gout đang vấp. Hai cổng duyệt và đăng tay giữ nguyên.

### Giai đoạn 0 — Giữ an toàn dữ liệu và môi trường

| # | Việc | Xong khi |
| --- | --- | --- |
| 0.1 | Commit `profiles/doctor-feedback.yaml` và `profiles/factory-standards.yaml` | `git status` không còn hai file này |
| 0.2 | Push `master` lên `origin/main` (cần người dùng đồng ý) | `git rev-list --count origin/main..master` = 0 |
| 0.3 | Cài `pnpm` 11 (`npm i -g pnpm@11`, cần người dùng đồng ý) | `healthvideo doctor` báo `OK pnpm` |
| 0.4 | Thêm `.remotion/` vào `.gitignore`; chuyển `New Recording.m4a`, `api-docs.zip` ra khỏi gốc repo | `git status` sạch |
| 0.5 | Khởi động lại `healthvideo app` để chạy code sau merge | trang chủ hiện đủ 5 mục của xưởng-công ty |

### Giai đoạn 1 — Chặn lỗi bố cục trước cổng y khoa

Mục tiêu: storyboard đã qua `submit-medical` thì `produce` không được hỏng vì thời lượng.

| # | Việc | Xong khi |
| --- | --- | --- |
| 1.1 | Ước lượng thời lượng từng dòng từ số ký tự, hiệu chỉnh bằng receipt TTS đã có (`audio/tts-usage.json` + WAV trong cache) | sai số trên gout ≤ 10% mỗi cảnh |
| 1.2 | `step submit-medical` chạy đúng các bộ kiểm của `produce` (ngân sách hình, beat trong cảnh, nhịp chữ, thời lượng clip) trên thời lượng ước lượng, với biên hẹp hơn (ví dụ `chart_crop` 16–24%) | bốn lỗi ở mục 3.1 đều bị bắt trước cổng trong test |
| 1.3 | Sau TTS thật, lệch nhỏ ở trường thuần trình bày (thời điểm beat, thời điểm chữ vào) thì tự kẹp vào cảnh thay vì chặn; lệch ở thứ bác sĩ đã duyệt (cảnh nào thuộc clip nào, lời đọc) vẫn chặn | test: cùng storyboard, TTS dài hơn ước lượng 8% vẫn dựng xong |

Không tổng hợp giọng thật trước cổng: một lần đọc trọn gout tốn khoảng 30% credit vibi
còn lại, và bác sĩ từ chối kịch bản thì mất trắng.

### Giai đoạn 2 — Video gout chuẩn

| # | Việc | Ai | Xong khi |
| --- | --- | --- | --- |
| 2.1 | Một vòng `revise_medical` gộp: tỷ lệ biểu đồ, beat S02, clip CL02, hình kim ở S07 | agent | qua kiểm ở 1.2 |
| 2.2 | Duyệt cổng y khoa | bác sĩ, một lần PIN | `medical_approved` |
| 2.3 | `produce` dùng lại cache TTS theo dòng; agent duyệt sản phẩm xem trước | xưởng | tới `awaiting_video_review` mà không mở lại cổng |
| 2.4 | Bác sĩ xem, trả lời hai câu còn treo ("u-rát", hd hay turbo), góp ý qua tab Ý kiến hoặc chat | bác sĩ | duyệt cổng video |
| 2.5 | Ghi những gì bác sĩ chấp nhận thành kiểm tự động (từ điển phát âm, nhịp hình, lint văn phong) | Claude | chủ đề sau tự đạt các điểm này |
| 2.6 | Đóng gói, bác sĩ đăng tay | bác sĩ | `published_manual` |

Nếu sau hai vòng góp ý mà bác sĩ vẫn chưa ưng một hạng mục (giọng hoặc hình), dừng lại
và bàn riêng hạng mục đó; không tiếp tục vá lẻ.

### Giai đoạn 3 — Dọn

| # | Việc | Ghi chú |
| --- | --- | --- |
| 3.1 | Xóa worktree và nhánh đã vào `master` | cần người dùng xác nhận danh sách trước khi xóa |
| 3.2 | Xóa `factory_trials.py`, `tts/elevenlabs.py`, `tts/asr.py`, skill thừa cùng test của chúng | chạy song song với P1 vì chỉ xóa; mỗi mục một commit để dễ hoàn lại |
| 3.3 | `CLAUDE.md` trỏ đúng spec 2026-11-08; viết lại `docs/HANDOFF.md`; chuyển bảng tiến độ cũ trong README vào `docs/archive/` | |
| 3.4 | Xóa `topics/code-review.yaml` nếu không bước nào đọc nó | kiểm bằng grep trước |

### Giai đoạn 4 — Chủ đề thứ hai, rồi mới mở rộng

| # | Việc | Xong khi |
| --- | --- | --- |
| 4.1 | Bác sĩ chọn một chủ đề thật trong app | có trong `topics/queue.yaml` |
| 4.2 | Xưởng chạy A–Z; Claude chỉ quan sát, ghi lại mọi chỗ phải can thiệp | bác sĩ chỉ làm: thêm chủ đề, hai lần PIN, góp ý |
| 4.3 | Sửa các chỗ đã ghi ở 4.2 | chủ đề thứ ba không cần can thiệp |
| 4.4 | Cài trên checkout sạch bằng `install/install.ps1`; thử `/pyh` trong Claude Code và Antigravity | `doctor` toàn OK |

## 5. Thế nào là hoàn thiện

1. Video gout được bác sĩ duyệt và đăng.
2. Một chủ đề thật đi từ hàng đợi tới `packaged` mà không ai sửa tay ngoài bác sĩ.
3. Cài mới trên checkout sạch, `doctor` không có FAIL nào ở mục bắt buộc.
4. `master` đã push, còn một worktree, tài liệu khớp code.

## 6. Kết quả kiểm khi viết kế hoạch

Chạy trên checkout chính, `master` tại `7ad3cc4`, ngày 2026-11-11:

- `pytest -q`: 1800 đạt, 1 bỏ qua, 242 giây. Ở lần chạy đầu,
  `test_factory_trials.py::test_stages_2_to_4_keep_offline_path_without_calling_agent[3]`
  hỏng vì Chrome của Remotion không kết nối kịp trong 25 giây khi máy đang chạy Vitest
  song song; chạy lại riêng file đó và chạy lại cả bộ đều đạt. Test này dựng Remotion thật
  nên nhạy với tải máy; nó thuộc code sẽ xóa ở việc 3.2.
- `ruff check src tests tools`: sạch.
- Vitest: 251 đạt (32 file). `tsc --noEmit`: sạch. Chạy bằng binary trong
  `video/node_modules/.bin` vì `pnpm`/`corepack` không có trên `PATH`.
- `resolve_pnpm_argv(['--version'])` ném `Cannot launch pnpm safely`, tức đường dựng sản
  xuất (`cli.py`, `factory_deps.py`, `dashboard.py`) hiện không gọi được Remotion. Khu thử
  trong `factory_trials.py` gọi thẳng `remotion-cli.js` bằng `node` nên không bị ảnh hưởng.
