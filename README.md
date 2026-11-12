# Protect Your Health — xưởng video y khoa

Protect Your Health (PYH) là xưởng sản xuất video y khoa giải thích bản chất bệnh và các tranh cãi thường gặp bằng mô phỏng trực quan theo chiều sâu hàn lâm (giải phẫu → sinh lý → sinh lý bệnh → giải phẫu bệnh). Kênh đi theo cấu trúc giải thích cơ chế trước, đưa bằng chứng có nguồn kiểm chứng sau (`explain-first`), và bắt buộc dẫn chứng y văn khi bảo vệ một quan điểm. Mỗi chủ đề trong hàng đợi xuất ra 1 video dài YouTube 16:9 (10–25 phút), 1–6 clip dọc 9:16 (TikTok, YouTube Shorts, Facebook Reels) cắt từ kịch bản đã duyệt và bộ bài đăng đa kênh soạn sẵn. Quy trình chạy tự động qua agent CLI (`codex` và Antigravity `agy`) nhưng luôn dừng ở **hai cổng duyệt của bác sĩ** (y khoa và video) và **không tự động đăng bài**.

## Cài đặt

Trên Windows 11 / PowerShell 5.1 (cần Python ≥3.11, Node.js ≥22, pnpm ≥11 hoặc Corepack, FFmpeg ≥8 trên `PATH`), chạy một lệnh từ thư mục gốc repo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install/install.ps1
```

Bộ cài tạo/dùng lại `.venv`, cài gói Python cùng dependency `video/`, cài môi trường TTS mặc định (thêm `-SkipTts` nếu muốn bỏ qua TTS) rồi chạy `doctor`. Các môi trường ảo mô hình dùng chung đặt trong `cache/` (nằm ngoài Git):

- `cache/tts-venv`: Python 3.11 với `vieneu==3.6.4` (giọng đọc kênh `Thái Sơn`) và `faster-whisper` cho kiểm tra ASR.
- `cache/music-venv`: ACE-Step 1.5 sinh nhạc nền không lời theo tâm trạng chương (trọng số tại `cache/models/ace-step-1.5`).
- `cache/flux-venv`: FLUX.2 [klein] 4B (Apache-2.0) sinh ảnh minh họa bối cảnh không nhãn.

Các biến môi trường tùy chọn đặt trong file `.env` ở gốc repo (chỉ khai báo trong máy local, không commit `.env` vào Git; CLI tự nạp và lọc bỏ mọi khóa chứa `PIN`):

- `YOUTUBE_API_KEY`: khóa YouTube Data API cho bước tìm chủ đề.
- `NCBI_EMAIL`, `NCBI_API_KEY`: email liên hệ và khóa API tùy chọn khi tìm kiếm PubMed/NCBI.
- `ELSEVIER_API_KEY`, `ELSEVIER_INSTTOKEN`: khóa Elsevier API chính thức (tùy chọn) cho `healthvideo evidence elsevier-search` / `elsevier-abstract`; khóa chỉ đi trong header, không ghi log, toàn văn không lưu vào repo. Xem `.env.example`.
- `HEALTHVIDEO_TTS_PYTHON`, `HEALTHVIDEO_MUSIC_PYTHON`, `HEALTHVIDEO_FLUX_PYTHON`: đường dẫn `python.exe` ghi đè các venv tương ứng trong `cache/`.

Kiểm tra môi trường bất kỳ lúc nào bằng:

```powershell
.venv\Scripts\healthvideo.exe doctor
```

## Bốn giai đoạn

| Giai đoạn | Làm gì | Công cụ |
| --- | --- | --- |
| 1. Chủ đề và kịch bản | Tìm tín hiệu/hiểu lầm tạo thẻ chủ đề để bác sĩ chọn vào hàng đợi; tự động tìm và sàng lọc y văn, tổng hợp ledger, lập bản đồ cơ chế (`explainer.yaml`), viết script, storyboard, dàn ý chương, kế hoạch clip; agent biên tập viên chấm kịch bản theo 6 tiêu chí, chưa đạt thì agent viết sửa (tối đa 3 lần chấm), rồi dừng ở cổng `awaiting_medical_review` | YouTube Data API, Google Trends, Reddit, PubMed, Europe PMC, agent CLI (`codex`/`agy`), skill `humanizer` |
| 2. Hình, giọng, nhạc | Dùng lại hoặc vẽ mới component SVG giải phẫu/cơ chế có chú thích; sinh ảnh minh họa bối cảnh không nhãn; tổng hợp giọng đọc từng dòng kèm căn thời gian có hash; sinh nhạc nền không lời và trộn ducking dưới giọng đọc | Thư viện SVG (`video/src/anatomy/`), FLUX.2 [klein] 4B, VieNeu TTS (`Thái Sơn`) + faster-whisper, ACE-Step 1.5 + FFmpeg |
| 3. Dựng video | Render video dài 16:9 theo chương (có cache), dựng 1–6 clip dọc 9:16 từ cảnh đã duyệt (không thêm lời mới), phụ đề tiếng Việt, mascot, thẻ cuối; chạy QA tiếng-hình, layer, font và xuất contact sheet rồi dừng ở cổng `awaiting_video_review` | Remotion 4, FFmpeg, bộ kiểm QA Python |
| 4. Đóng gói đa kênh | Soạn tiêu đề/mô tả/tag/thumbnail YouTube, caption TikTok/Shorts/Reels, bài Facebook và YouTube Community ngay trong `producing` để duyệt chung ở cổng video; sau khi duyệt video chỉ đóng băng vào `publish/` để bác sĩ tự đăng (`published_manual`) | `healthvideo step posts-check`, `healthvideo package` |

## Vận hành hằng ngày

1. Lần đầu: bác sĩ chạy `healthvideo review set-pin`, rồi mở app điều khiển `healthvideo app` (hoặc bấm đúp lối tắt Desktop **Xưởng video**). Bấm **Bật xưởng** (hoặc `healthvideo xuong --background`). Bác sĩ nghiệm thu ngay trên sản phẩm thật ở hai cổng duyệt; ý kiến về sản phẩm hay xưởng gõ ở tab **Ý kiến**, agent độc lập phân tích thành việc rồi ghi vào `topics/feedback.yaml` cho Claude xử lý.
2. Thêm chủ đề và xử lý lỗi: ngay trong tab **Hàng đợi** của `healthvideo app` (thêm chủ đề, xem bước kế tiếp + ước tính cache + `retry_after`, cho phép thử lại khi đã sửa đầu vào, mở lại cổng y khoa bằng PIN) và tab **Thư viện** (lọc/xem ảnh, nhập ảnh có nguồn như Muse AI và gắn vào cảnh `whiteboard`); hoặc qua CLI `healthvideo topic discover --query "<từ khóa>"`, `healthvideo topic add --slug <slug> --title "<tiêu đề>" --question "<câu hỏi>" [--note "<ghi chú>"]`.
3. Khi có thông báo: xem sản phẩm (kịch bản, claim + câu trích, video/giọng), góp ý từng dòng và bấm **Quyết định · PIN** ngay trong `healthvideo app`, hoặc chạy `healthvideo duyet` trong terminal TTY (chọn **A** duyệt / **R** từ chối / **B** bỏ qua, nhập PIN). Tên bác sĩ lưu ngoài repo tại `~/.healthvideo/operator.yaml`; PIN chỉ kiểm tra cục bộ, không lưu.
4. Xưởng tự chạy tiếp và đóng gói sau khi duyệt video. Lấy `revisions/<rev>/publish/` để đăng tay.

`healthvideo status` cho biết PID xưởng và số project chờ bác sĩ. Dùng `healthvideo xuong --stop` để dừng, `healthvideo xuong` để chạy trong terminal (Ctrl+C dừng), hoặc `healthvideo xuong --once` để chạy một vòng. Chu kỳ mặc định 120 giây, đổi bằng `--interval`; hết quota cả hai agent thì chờ ít nhất 30 phút rồi thử lại. Log xoay vòng tại `topics/logs/xuong.log`. Các lệnh xưởng và duyệt nhận `--root` nếu chạy ngoài gốc repo.

## Lệnh

Bộ lệnh công khai của `healthvideo` (xem chi tiết bằng `--help`):

- `healthvideo app [--port 8765] [--no-browser] [--install-shortcut]` — mở bảng điều khiển local (`127.0.0.1`) để quản lý hàng đợi/thử lại/mở lại cổng, duyệt thư viện ảnh, gửi ý kiến và quyết định hai cổng bằng PIN.
- `healthvideo topic discover` — tìm tín hiệu chủ đề từ YouTube, Google Trends, Reddit và đếm bài PubMed.
- `healthvideo topic add` — thêm một thẻ chủ đề mới vào hàng đợi `topics/queue.yaml` (chặn trùng slug).
- `healthvideo topic list` — liệt kê các chủ đề trong hàng đợi cùng trạng thái dự án.
- `healthvideo duyet` — mở lần lượt gói chờ bác sĩ theo hàng đợi rồi các project khác; chọn A/R/B và nhập PIN.
- `healthvideo xuong [--background|--once|--stop] [--interval 120]` — chạy xưởng liên tục, thông báo thay đổi và tự đóng gói video đã duyệt.
- `healthvideo run` — chạy hàng đợi tự động tới cổng duyệt tiếp theo (`--once` để chạy tối đa một bước).
- `healthvideo status [project_dir]` — xem bảng tiến độ toàn hàng đợi hoặc chi tiết bước kế tiếp của một project (`--json`).
- `healthvideo review open <project_dir> --gate medical|video` — in gói duyệt HTML ra stdout (chỉ đọc).
- `healthvideo review approve <project_dir> --gate medical|video --reviewer <tên> [--note <ghi_chú>]` — duyệt cổng bằng PIN gõ tay trong TTY.
- `healthvideo review reject <project_dir> --gate medical|video --reviewer <tên> --reason <lý_do> --resume-to <trạng_thái> [--yes]` — từ chối cổng kèm lý do và trạng thái nối lại; PIN vẫn bắt buộc, `--yes` chỉ bỏ xác nhận chữ.
- `healthvideo review reopen <project_dir> --gate medical|video --reviewer <tên> --reason <lý_do> --changed <path> --resume-to <trạng_thái> [--yes]` — mở lại cổng khi cần sửa artifact đã duyệt.
- `healthvideo review set-pin` — đặt hoặc đổi mã PIN duyệt của bác sĩ trong terminal TTY.
- `healthvideo preview <project_dir> [--port <cổng>] [--print-only]` — mở Remotion Studio xem trước bản render hiện hành.
- `healthvideo produce <project_dir>` — chạy tay bước tổng hợp giọng, nhạc và render video (giai đoạn 2–3).
- `healthvideo package <project_dir>` — đóng băng gói đăng bài đa kênh vào `publish/` sau khi qua cổng video (giai đoạn 4).
- `healthvideo doctor` — kiểm tra cấu hình và dependency của toolchain local.

Ngoài ra, nhóm lệnh ẩn `healthvideo step ...` (`hidden=True`) dành riêng cho agent gọi trong các bước tự động (`new`, `select`, `evidence-search`, `evidence-screen`, `evidence-ingest`, `build-ledger`, `draft`, `lint`, `outro-author`, `submit-medical`, `posts-check`, `review-frames`, `resume`, `revision-create`, `version`).

## Quy tắc an toàn

- Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, hoặc trải nghiệm lâm sàng của bác sĩ.
- Agent không bao giờ tự duyệt cổng y khoa hoặc cổng video; `review approve` bắt buộc TTY + mã PIN do bác sĩ gõ tay, và tiến trình gọi agent luôn lọc bỏ mọi biến môi trường chứa `PIN`.
- Không tự động xuất bản lên bất kỳ nền tảng nào; việc đăng bài từ `publish/` luôn do bác sĩ thực hiện thủ công.
- Ảnh minh họa do AI sinh (FLUX.2 [klein] 4B) tuyệt đối không mang nhãn giải phẫu hay số liệu; mọi hình giải phẫu/cơ chế có chú thích phải là component SVG trong `video/src/anatomy/` có kiểm tra layer và contact sheet.
- Mọi câu có số liệu trong bài đăng đa kênh (`posts/posts.yaml`) phải gắn `[claim:<id>]` trỏ tới claim đã được duyệt ở cổng y khoa.

## Tài liệu

- [Spec xưởng-công ty (2026-11-08)](docs/superpowers/specs/2026-11-08-factory-company-design.md) và [Đánh giá và kế hoạch hoàn thiện (2026-11-11)](docs/superpowers/plans/2026-11-11-completion-plan.md)
- [Spec hoàn thiện xưởng trước, nghiệm thu từng giai đoạn (2026-10-25)](docs/superpowers/specs/2026-10-25-factory-first-stage-acceptance-design.md)
- [Ghi nhận kiểm chứng tích hợp Muse AI](docs/reference/muse-integration-findings.md)
- [Spec tái cấu trúc xưởng video (2026-10-22)](docs/superpowers/specs/2026-10-22-video-factory-restructure-design.md)
- [Spec nội dung explain-first (2026-10-18)](docs/superpowers/specs/2026-10-18-explain-first-content-design.md)
- [Lưu trữ tài liệu cũ (`docs/archive/`)](docs/archive/) — gồm các spec/plan lịch sử, [`docs/archive/README-2026-11.md`](docs/archive/README-2026-11.md) và [`docs/archive/README-2026-10.md`](docs/archive/README-2026-10.md) (ghi chú: `projects/do-huyet-ap-khong-trieu-chung` là bản thử cũ theo profile `legacy`, không chuyển đổi).

## Tiến độ nhiệm vụ

Tiến độ xem ở [`docs/progress.yaml`](docs/progress.yaml) (app hiển thị ở mục "Tiến độ hoàn thiện xưởng").
