# Protect Your Health — xưởng video y khoa

Protect Your Health (PYH) là xưởng sản xuất video y khoa giải thích bản chất bệnh và các hiểu lầm thường gặp theo chiều sâu hàn lâm (giải phẫu → sinh lý → sinh lý bệnh → giải phẫu bệnh). Kênh áp dụng cấu trúc `explain-first` (giải thích cơ chế trước, dẫn chứng kiểm chứng sau) và bắt buộc đối chiếu y văn cho mọi số liệu/khuyến cáo. Mỗi chủ đề xuất ra 1 video dài YouTube 16:9, bộ clip dọc 9:16 (TikTok, YouTube Shorts, Facebook Reels) cắt từ kịch bản đã duyệt và bộ bài đăng đa kênh. Xưởng vận hành theo mô hình **Company 2.0 (16 vai nhân sự)** qua agent CLI (`omniroute`, `codex`, `agy`), luôn dừng ở **hai cổng duyệt bằng PIN của bác sĩ** (y khoa và video) và không tự ý đăng khi chưa đủ phê duyệt còn hiệu lực.

## Cài đặt

Trên Windows 11 / PowerShell 5.1 (cần Python ≥ 3.11, Node.js ≥ 22, pnpm ≥ 11 hoặc Corepack, FFmpeg ≥ 8 trên `PATH`), chạy từ thư mục gốc repo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install/install.ps1
```

Bộ cài tạo/dùng lại `.venv`, cài dependency Python và `video/`, đồng thời tùy chọn cài `cache/tts-venv` (`vieneu==3.6.4` làm TTS dự phòng offline; thêm `-SkipTts` nếu chỉ dùng Vibi MiniMax). Các môi trường AI dùng chung đặt ngoài Git trong `cache/`:

- `cache/whisper-venv` + `cache/models/whisper-large-v3`: `faster-whisper` (`large-v3`) căn thời gian từng từ và kiểm tra phát âm (`pronunciation-qa.json`).
- `cache/music-venv` + `cache/models/ace-step-1.5`: ACE-Step 1.5 sinh nhạc nền không lời theo tâm trạng chương.
- `cache/flux-venv` + `cache/models/flux2-klein-4b`: FLUX.2 [klein] 4B (Apache-2.0) sinh ảnh minh họa bối cảnh không nhãn.
- `cache/tts-venv` *(tùy chọn)*: VieNeu ONNX local dự phòng khi cài không dùng `-SkipTts`.

Khai báo biến môi trường local trong `.env` (không commit `.env`, CLI tự lọc bỏ mọi khóa chứa `PIN`; xem `.env.example`):

- `VIBI_API_KEY`: khóa API Vibi MiniMax (`profiles/voice.yaml`, giọng nhân bản của bác sĩ).
- `YOUTUBE_API_KEY`: khóa YouTube Data API cho bước tìm tín hiệu chủ đề.
- `NCBI_EMAIL`, `NCBI_API_KEY`, `ELSEVIER_API_KEY`, `ELSEVIER_INSTTOKEN`: khóa tùy chọn cho tra cứu y văn (`healthvideo evidence`).
- `HEALTHVIDEO_TTS_PYTHON`, `HEALTHVIDEO_MUSIC_PYTHON`, `HEALTHVIDEO_FLUX_PYTHON`, `HEALTHVIDEO_WHISPER_PYTHON`: đường dẫn ghi đè venv trong `cache/`.

Kiểm tra nhanh toàn bộ toolchain bất kỳ lúc nào:

```powershell
.venv\Scripts\healthvideo.exe doctor
```

## Bốn giai đoạn và kiến trúc 16 vai

| Giai đoạn | Luồng xử lý chính | Công cụ & chuẩn áp dụng |
| --- | --- | --- |
| 1. Chủ đề & Kịch bản | Săn tín hiệu/chấm rubric (`researcher`), tra cứu y văn & lập `explainer.yaml` (`medical_expert`), viết kịch bản (`writer`), thiết kế phân cảnh & style (`storyboard_director`), chuẩn hóa phát âm (`voice_director`), kiểm định Trạm 07 tối đa 3 chu kỳ/6 vòng (`script_critic`) trước khi dừng ở `awaiting_medical_review` | Google Sheet, YouTube/Trends/Reddit, Europe PMC/Elsevier, Company 2.0 (`profiles/company.yaml`), bộ 3 style `scale_zoom` / `iso_infographic` / `whiteboard` |
| 2. Hình, Giọng, Nhạc | Lắp ghép/vẽ mới SVG giải phẫu theo bảng màu thực thể & duyệt ảnh FLUX bối cảnh (`art_director`); tổng hợp giọng đọc qua **Vibi MiniMax** + từ điển `profiles/pronunciation.vi.yaml`; căn lời từng từ với `faster-whisper`; sinh nhạc nền ACE-Step 1.5 và trộn ducking | `video/src/anatomy/`, `library/medanim/`, FLUX.2 [klein] 4B, Vibi MiniMax (`speech-2.8-hd`), `faster-whisper`, ACE-Step 1.5, FFmpeg |
| 3. Dựng & Kiểm định | Dựng video dài 16:9 (**không cháy cứng phụ đề**) và các clip dọc 9:16 (phụ đề **highlight theo từ** trong vùng an toàn); xuất `motion-report.json` ở Trạm 09 bắt đoạn giữ tĩnh > 6s; Trạm 12 (`product_critic`) chấm độc lập trước cổng `awaiting_video_review`; thợ dựng (`editor`) sửa khi cần | Remotion 4, FFmpeg/FFprobe, bộ kiểm layout/safe-zone/Vitest |
| 4. Đóng gói & Kênh | Soạn bài đăng đa kênh (`copywriter`), lập kế hoạch clip (`shorts_producer`), đóng gói vào `revisions/<rev>/publish/` kèm file phụ đề rời `subtitles.vi.srt` cho video dài; bác sĩ đăng tay hoặc xác nhận đăng qua kết nối kênh đã cấp quyền sau khi qua đủ 2 cổng PIN | `healthvideo package`, `subtitles.vi.srt`, tab **Kênh** (YouTube OAuth / TikTok Autotok DPAPI) |

Trong suốt quá trình chạy, **Trưởng nhóm Điều phối** (`coordinator` / `coordinator_senior`) phân loại phản hồi từ khung chat duy nhất, **Kỹ sư sửa lỗi** (`repair_engineer` + `repair_service`) tự động chẩn đoán/sửa sự cố kỹ thuật có nghiệm thu độc lập, hệ thống tự phát hiện render cũ (`render_is_stale`) khi đầu vào thay đổi và đẩy câu hỏi khó lên hàng đợi để bác sĩ quyết định trên app.

## Vận hành hằng ngày

1. **Lần đầu:** chạy `healthvideo review set-pin`, rồi mở app điều khiển `healthvideo app` (hoặc lối tắt Desktop **Xưởng video**). Server mặc định chạy ở `127.0.0.1:8765` và tự né sang `8766–8775` nếu cổng đang bận (lưu trạng thái tại `cache/dashboard-server.json`).
2. **Theo dõi & điều phối:** trên app gồm các mục **Tổng quan**, **Tiến độ**, **Sơ đồ xưởng**, **Kho đề tài**, **Thư viện hoạt cảnh** và **Kênh** (cùng khu vận hành **Nhật ký & Hệ thống**, **Hàng đợi**, **Thư viện**). Bấm **Bật xưởng** (hoặc `healthvideo xuong --background`). Mọi góp ý về sản phẩm hoặc xưởng gửi trực tiếp qua khung chat **Nhắn điều phối viên** (`feedback_analyst` sẽ tách thành việc cụ thể).
3. **Duyệt hai cổng PIN:** xem kịch bản, đối chiếu claim/y văn, xem video/giọng và bấm **Quyết định · PIN** ngay trên app, hoặc chạy `healthvideo duyet` trong terminal TTY (chọn **A** duyệt / **R** từ chối / **B** bỏ qua, nhập PIN). PIN chỉ kiểm tra cục bộ, không bao giờ lưu hay truyền cho agent.
4. **Đóng gói & đăng kênh:** sau khi qua cả hai cổng PIN, sản phẩm đóng băng vào `revisions/<rev>/publish/` (kèm `subtitles.vi.srt` cho bản 16:9). Bác sĩ có thể tự đăng từ `publish/` hoặc xác nhận đăng qua tài khoản đã kết nối ở tab **Kênh** với kênh đích và quyền hiển thị được chọn rõ ràng.

Dùng `healthvideo status` để xem tiến độ từng chủ đề (`PYH-xxx`), trạng thái tạm dừng/chờ bác sĩ; `healthvideo xuong --stop` để dừng xưởng nền (chu kỳ mặc định 120s, log xoay vòng tại `topics/logs/xuong.log`).

## Lệnh chính

- `healthvideo app [--port 8765] [--no-browser] [--install-shortcut]` — mở bảng điều khiển local (tự né cổng `8765–8775` nếu bận).
- `healthvideo topic discover|add|list|sync-sheet|discover-ai` — tìm tín hiệu, đồng bộ Google Sheet và thêm chủ đề vào `topics/queue.yaml`.
- `healthvideo xuong [--background|--once|--stop] [--interval 120]` — chạy xưởng tự hành liên tục và tự đóng gói gói đã duyệt.
- `healthvideo duyet` / `healthvideo status [project_dir]` — duyệt lần lượt các gói chờ PIN hoặc xem bảng trạng thái hàng đợi.
- `healthvideo review open|approve|reject|reopen|set-pin` — thao tác đọc gói duyệt, duyệt/từ chối/mở lại cổng bằng PIN TTY và đặt PIN.
- `healthvideo preview|produce|package <project_dir>` — xem trước Remotion Studio, chạy dựng giọng/nhạc/video thủ công và đóng gói `publish/`.
- `healthvideo channel sync-sheet|import-csv|analyze|create-sheet` — đồng bộ và phân tích số liệu hiệu quả kênh.
- `healthvideo doctor` — kiểm tra toolchain, GPU, model local và số dư Vibi. *(Nhóm lệnh `healthvideo step ...` ẩn dành riêng cho agent).*

## Quy tắc an toàn

- Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu hoặc trải nghiệm lâm sàng của bác sĩ.
- Agent không bao giờ tự duyệt cổng y khoa hoặc cổng video; mọi phê duyệt bắt buộc có mã PIN do bác sĩ nhập tay qua app hoặc TTY, và biến môi trường chứa `PIN` luôn bị lọc khỏi tiến trình con.
- Không tự ý đăng bài: chỉ được chuẩn bị/xác nhận đăng đúng gói đã qua **cả hai cổng còn hiệu lực**, đúng hash manifest, với tài khoản và quyền hiển thị được chọn rõ; không tự đăng lại khi chưa rõ kết quả.
- Ảnh sinh bởi FLUX.2 [klein] 4B tuyệt đối không mang chữ hay nhãn giải phẫu; mọi hình giải phẫu/cơ chế có chú thích phải dùng SVG trong `video/src/anatomy/` hoặc `library/medanim/`.
- Mọi câu có số liệu/liều lượng trong kịch bản và `posts/posts.yaml` phải gắn `[claim:<id>]` trỏ tới claim đã được duyệt ở cổng y khoa.

## Tài liệu tham khảo

- [Đối chiếu chuẩn MXH & Tối ưu lõi công nghệ (2026-11-22)](docs/reference/2026-11-22-exemplar-and-stack-optimization.md)
- [Bộ style hình ảnh và chuẩn hình y khoa (2026-11-21)](docs/superpowers/specs/2026-11-21-visual-style-set-design.md)
- [Chuẩn phong cách A — Mascot dẫn chuyện (2026-11-17)](docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md)
- [Kết nối kênh và đăng nội dung đã duyệt (2026-11-15)](docs/superpowers/specs/2026-11-15-channel-connection-publishing-design.md)
- [Spec xưởng-công ty (2026-11-08)](docs/superpowers/specs/2026-11-08-factory-company-design.md) và [Kiểm toán skill & chi phí agent (2026-11-17)](docs/reference/agent-skill-audit-2026-11-17.md)
- [Lưu trữ tài liệu cũ (`docs/archive/`)](docs/archive/)

## Tiến độ nhiệm vụ

Tiến độ chi tiết theo từng phase xem tại [`docs/progress.yaml`](docs/progress.yaml) (hiển thị trực tiếp ở tab **Tiến độ** trong app).
