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
- `HEALTHVIDEO_TTS_PYTHON`, `HEALTHVIDEO_MUSIC_PYTHON`, `HEALTHVIDEO_FLUX_PYTHON`: đường dẫn `python.exe` ghi đè các venv tương ứng trong `cache/`.

Kiểm tra môi trường bất kỳ lúc nào bằng:

```powershell
.venv\Scripts\healthvideo.exe doctor
```

## Bốn giai đoạn

| Giai đoạn | Làm gì | Công cụ |
| --- | --- | --- |
| 1. Chủ đề và kịch bản | Tìm tín hiệu/hiểu lầm tạo thẻ chủ đề để bác sĩ chọn vào hàng đợi; tự động tìm và sàng lọc y văn, tổng hợp ledger, lập bản đồ cơ chế (`explainer.yaml`), viết script, storyboard, dàn ý chương, kế hoạch clip rồi dừng ở cổng `awaiting_medical_review` | YouTube Data API, Google Trends, Reddit, PubMed, Europe PMC, agent CLI (`codex`/`agy`), skill `humanizer` |
| 2. Hình, giọng, nhạc | Dùng lại hoặc vẽ mới component SVG giải phẫu/cơ chế có chú thích; sinh ảnh minh họa bối cảnh không nhãn; tổng hợp giọng đọc từng dòng kèm căn thời gian có hash; sinh nhạc nền không lời và trộn ducking dưới giọng đọc | Thư viện SVG (`video/src/anatomy/`), FLUX.2 [klein] 4B, VieNeu TTS (`Thái Sơn`) + faster-whisper, ACE-Step 1.5 + FFmpeg |
| 3. Dựng video | Render video dài 16:9 theo chương (có cache), dựng 1–6 clip dọc 9:16 từ cảnh đã duyệt (không thêm lời mới), phụ đề tiếng Việt, mascot, thẻ cuối; chạy QA tiếng-hình, layer, font và xuất contact sheet rồi dừng ở cổng `awaiting_video_review` | Remotion 4, FFmpeg, bộ kiểm QA Python |
| 4. Đóng gói đa kênh | Soạn tiêu đề/mô tả/tag/thumbnail YouTube, caption TikTok/Shorts/Reels, bài Facebook và YouTube Community ngay trong `producing` để duyệt chung ở cổng video; sau khi duyệt video chỉ đóng băng vào `publish/` để bác sĩ tự đăng (`published_manual`) | `healthvideo step posts-check`, `healthvideo package` |

## Vận hành hằng ngày

Đặt mã PIN duyệt lần đầu (chỉ chạy trực tiếp trong terminal của bác sĩ; băm scrypt lưu tại `~/.healthvideo/approver-pin.json` ngoài repo):

```powershell
.venv\Scripts\healthvideo.exe review set-pin
```

Luồng vận hành chuẩn:

1. `healthvideo topic discover --query "<từ khóa>"` — tìm tín hiệu thật và lưu thẻ gợi ý vào `topics/discovered/<ngày>.yaml`.
2. `healthvideo topic add --slug <slug> --title "<tiêu đề>" --question "<câu hỏi>" [--note "<ghi chú>"]` — đưa chủ đề vào hàng đợi `topics/queue.yaml`.
3. `healthvideo run` — chạy tự động hàng đợi qua các bước Python và agent (`codex`/`agy`) cho tới khi chạm cổng duyệt.
4. `healthvideo status` — xem bảng trạng thái toàn bộ hàng đợi, cổng đang chờ và lệnh mở gói duyệt (hoặc `healthvideo status <project>` cho một dự án).
5. `healthvideo review open <project> --gate medical|video` — xuất gói HTML duyệt cổng y khoa hoặc cổng video.
6. Duyệt hoặc từ chối tại cổng:
   - `healthvideo review approve <project> --gate medical|video --reviewer "<tên bác sĩ>" [--note "<ghi chú>"]` (bác sĩ gõ tay mã PIN trực tiếp trong terminal TTY).
   - `healthvideo review reject <project> --gate medical|video --reviewer "<tên bác sĩ>" --reason "<lý do>" --resume-to <trạng_thái>` (từ chối để lần `run` tiếp theo tự sửa theo ghi chú).
7. Chạy lại `healthvideo run` sau khi duyệt cổng y khoa (hoặc sau khi `reject`) để hoàn tất sản xuất và tiến tới cổng duyệt video.
8. `healthvideo package <project>` — sau khi duyệt cổng video, đóng băng toàn bộ video, clip, nguồn và bài đăng vào `revisions/<rev>/publish/` để bác sĩ tự đăng.

## Lệnh

Bộ lệnh công khai của `healthvideo` (xem chi tiết bằng `--help`):

- `healthvideo topic discover` — tìm tín hiệu chủ đề từ YouTube, Google Trends, Reddit và đếm bài PubMed.
- `healthvideo topic add` — thêm một thẻ chủ đề mới vào hàng đợi `topics/queue.yaml` (chặn trùng slug).
- `healthvideo topic list` — liệt kê các chủ đề trong hàng đợi cùng trạng thái dự án.
- `healthvideo run` — chạy hàng đợi tự động tới cổng duyệt tiếp theo (`--once` để chạy tối đa một bước).
- `healthvideo status [project_dir]` — xem bảng tiến độ toàn hàng đợi hoặc chi tiết bước kế tiếp của một project (`--json`).
- `healthvideo review open <project_dir> --gate medical|video` — in gói duyệt HTML ra stdout (chỉ đọc).
- `healthvideo review approve <project_dir> --gate medical|video --reviewer <tên> [--note <ghi_chú>]` — duyệt cổng bằng PIN gõ tay trong TTY.
- `healthvideo review reject <project_dir> --gate medical|video --reviewer <tên> --reason <lý_do> --resume-to <trạng_thái> [--yes]` — từ chối cổng kèm lý do và trạng thái nối lại.
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

- [Spec tái cấu trúc xưởng video (2026-10-22)](docs/superpowers/specs/2026-10-22-video-factory-restructure-design.md)
- [Kế hoạch triển khai tái cấu trúc xưởng video (2026-10-22)](docs/superpowers/plans/2026-10-22-video-factory-restructure.md)
- [Spec nội dung explain-first (2026-10-18)](docs/superpowers/specs/2026-10-18-explain-first-content-design.md)
- [Lưu trữ tài liệu cũ (`docs/archive/`)](docs/archive/) — gồm các spec/plan lịch sử và [`docs/archive/README-2026-10.md`](docs/archive/README-2026-10.md) (ghi chú: `projects/do-huyet-ap-khong-trieu-chung` là bản thử cũ theo profile `legacy`, không chuyển đổi).

## Tiến độ nhiệm vụ

| Task | Deliverable | Status | Tests | Commit |
| --- | --- | --- | --- | --- |
| Xưởng P7 Task 7.1: chạy thật A–Z | Bản thử "Gan nhiễm mỡ hình thành thế nào?" (TEST, không đăng): research → draft → cổng y khoa → posts → VieNeu + ACE-Step → render 16:9 10:30 + 2 clip 9:16 + thumbnail → cổng video → `package`. Lộ và sửa: phụ đề/bố cục/thẻ nguồn giả (4d6be93), vòng qua cổng y khoa (18f8bcc), phụ đề kéo giãn (e343b44), `posts.md` còn `[claim:…]`, `blocked.txt` cũ không xóa. Còn: một hình giải phẫu cho cả video, cận cảnh cắt mép, chưa có minh họa FLUX trong video | complete | pytest 1258 passed, 1 skipped; Ruff; 3 lần render + 4 vòng cổng duyệt | `fix: clean paste-ready posts and stale block notes; record P7 pilot` |
| Xưởng P7: phụ đề không kéo giãn | `captionFontSize` thu nhỏ cỡ chữ khi dòng quá dài (ước lượng 0,6em/ký tự) thay cho `textLength` ép giãn glyph bằng bề ngang tối đa | complete | vitest 148; typecheck | `fix: shrink long caption rows instead of stretching glyphs` |
| Xưởng: đọc toàn văn nguồn | `step fulltext` lấy toàn văn OA từ Europe PMC (kèm giấy phép) hoặc PDF bác sĩ tự tải vào `cache/fulltext/inbox/` (tên `<PMID>.pdf`), cache ngoài Git; `step fulltext-search` trả đoạn kèm locator; claim có `support` (trích ≤25 từ, kiểm khớp nguyên văn khi ghi ledger và khi mở gói duyệt, không khi nạp); gói duyệt y khoa hiện trích dẫn; crop ảnh chỉ khi CC BY/BY-SA; thêm `pypdf` | complete | pytest 1257 passed, 1 skipped; Ruff; chạy thật trên bản sao gan-nhiem-mo-test | `feat: read open-access and user-supplied full text for evidence` |
| Xưởng P7 chốt cổng y khoa khi sửa sản xuất | `step resume --gate video --to production_in_progress` từ chối khi tệp đã duyệt y khoa (storyboard, assets, script, ledger…) bị đổi; prompt `revise_production` chỉ cho sửa component SVG, còn lại báo bác sĩ `review reopen --gate medical` | complete | pytest full; Ruff; test_resume_to_production_refuses_after_medical_reviewed_storyboard_edit | `fix: block production resume after medical-reviewed edits` |
| Xưởng P7 sửa renderer | Phụ đề mọi cảnh có lời; tế bào gan lấp ≥75% khung, ô cơ chế lớn hơn, camera đổi khung theo scene, QA chặn >4 cảnh cơ chế liền cùng hình; visual `source_card` dựng từ ledger (khớp chính xác) thay thẻ nguồn giả, `evidence_highlight` chỉ cho crop thật có giấy phép; whiteboard dùng `on_screen_text` ≤90 ký tự, nét vẽ dưới chữ; nối minh họa FLUX vào cảnh whiteboard | complete | pytest 1233 passed, 1 skipped; vitest 147; typecheck; Ruff; still Remotion 4 cảnh | `fix: renderer layout, source cards and captions from P7 pilot` |
| Thư viện giải phẫu: `HepaticCell` | Component SVG tế bào gan (agent vẽ khi chạy thử gan nhiễm mỡ): nguồn mỡ, tín hiệu insulin, tế bào gan, giọt mỡ trong tế bào, dùng năng lượng, tổn thương/miễn dịch, tế bào hình sao, chất nền ngoại bào; đăng ký trong `library.json` + `registry.ts`; còn "new" cho tới khi qua cổng video | complete (chờ cổng video soát y khoa) | vitest 121; typecheck; pytest anatomy 72 | `feat: add hepatic cell anatomy component` |
| Xưởng P7 sửa lỗi lần 1 | Lộ ra khi chạy thử gan nhiễm mỡ: subject giải phẫu Python/TS đọc từ `video/src/anatomy/library.json` (đăng ký component mới chỉ sửa trong `anatomy/`); `run_queue` chụp snapshot git + SHA-1 trước/sau bước agent nên chỉ báo code agent vừa đổi; `doctor` đọc `HEALTHVIDEO_TTS_PYTHON` | complete | pytest 1212 passed, 1 skipped; vitest 121; typecheck; Ruff | `fix: single anatomy registry, per-step code changes, TTS env in doctor` |
| Xưởng P6 Task 6.1 (thumbnail) | Khối `thumbnail` trong `posts.yaml` (headline ≤60 ký tự, số liệu phải trỏ claim, dấu `[claim:…]` không vẽ lên ảnh); nền FLUX + composition Remotion `Thumbnail` 1280×720 (brand, logo, tiếng Việt đủ dấu); render trong `produce`, cache theo hash, ghi license ledger; hash cổng video gồm `posts/thumbnail.png`; gói duyệt hiện ảnh; `package` chép ảnh đã duyệt; schema `posts` | complete | pytest 1205 passed, 1 skipped; vitest 116; typecheck; Ruff; ảnh mẫu thật kiểm bằng mắt | `feat: render YouTube thumbnail from FLUX background and Remotion still` |
| Xưởng P1 Task 1.3 | README mới 123 dòng (mục đích kênh, cài đặt, 4 giai đoạn, vận hành, lệnh, quy tắc an toàn); README cũ lưu `docs/archive/README-2026-10.md`; 31 spec/plan cũ + runbook M7 chuyển vào `docs/archive/`; `CLAUDE.md`/`AGENTS.md` trỏ spec + plan 2026-10-22; bảng theo dõi trong plan cập nhật | complete | pytest 1197 passed, 1 skipped; Ruff | `docs: archive old specs and rewrite README for the factory` |
| Xưởng P4 Task 4.1 | Minh họa FLUX.2 klein 4B (venv `cache/flux-venv`, CPU offload): loại asset `illustration` (`prompt`, `seed`), chặn nhãn/chú thích trên ảnh AI, `produce` sinh ảnh còn thiếu + ghi license ledger Apache-2.0 (hash cổng y khoa giữ nguyên), cache theo hash + sidecar, doctor cảnh báo trọng số không phải 4B; spike RTX 3060: nạp ≈97 s, ≈30–116 s/ảnh, VRAM đỉnh ≈9,8 GB | complete | pytest 1197 passed, 1 skipped; Ruff | `feat: generate unlabeled illustrations with FLUX.2 klein 4B` |
| Xưởng P6 Task 6.1+6.2 | Bước agent `posts` chạy trước `produce` khi `posts/posts.yaml` thiếu/sai; `step posts-check`; cổng video từ chối nếu bài đăng thiếu/lỗi, hash cổng video gồm `posts.yaml`, claim hợp lệ = claim trong ledger khớp hash duyệt y khoa; gói duyệt video có mục "Bài đăng"; `package` chép bài đăng đã duyệt + `posts.md`, từ chối nếu sửa sau duyệt; tên chương có số không bị coi là số liệu | complete | pytest 1173 passed, 1 skipped; Ruff | `feat: draft multi-channel posts before video review` |
| Xưởng P4 Task 4.2 | Nhạc nền ACE-Step 1.5 (turbo 2B + LM 1.7B, venv `cache/music-venv`): 30 s nhạc không lời lặp dưới giọng, ducking FFmpeg `sidechaincompress`, giữ `narration-voice.wav` cho ASR/QA, cache theo hash, ghi license ledger MIT trong `renders/`, `mood` tùy chọn ở outline/chương, `produce --no-music`, doctor kiểm venv; spike RTX 3060: VRAM đỉnh ≈8,2 GB, ≈120 s sinh/30 s nhạc | complete | pytest 1161 passed, 1 skipped; Ruff | `feat: add ACE-Step background music with ducking` |
| Cấu hình pytest | `testpaths = ["tests"]` để pytest không thu thập mã bên thứ ba trong `cache/` (vd. `cache/ace-step-src`) | complete | pytest 1142 passed, 1 skipped | `chore: limit pytest collection to tests/` |
| Xưởng P3 Task 3.5 (CLI) | `healthvideo run [--once]` gọi `run_queue` với phụ thuộc thật (`factory_deps`: tạo project + chọn thẻ từ hàng đợi, đọc trạng thái, ghi chú từ chối mới nhất, `git status` tìm code đổi); sản xuất dùng VieNeu "Thái Sơn" (venv qua `HEALTHVIDEO_TTS_PYTHON`); mã thoát 3 khi cả hai agent hết quota; CLI nạp `.env` (UTF-8 BOM, bỏ khóa chứa PIN, không ghi đè biến có sẵn) | complete | pytest 1142 passed, 1 skipped; Ruff | `feat: wire healthvideo run to the topic queue` |
| Xưởng P2 Task 2.8 (+ CLI 3.1/3.2/5.1) | CLI công khai: `topic discover/add/list`, `run` (tạm), `status`, `review open/approve/reject/reopen/set-pin`, `preview`, `produce`, `package`, `doctor`; lệnh còn lại vào nhóm ẩn `step`; `review approve` bắt buộc TTY + PIN, xóa alias `review medical/video`; `topic discover` (YouTube/Trends/Reddit + `PubMedClient.count`); `/pyh` 36 dòng; prompt khớp lệnh `step` | complete | pytest 1131 passed, 1 skipped; Ruff | `refactor: shrink CLI to the factory command surface` |
| Xưởng P3 Task 3.5 (lõi) | `run_queue` + `RunDeps`/`RunReport`: tạo project, gọi agent hoặc bước Python theo `next_step`, dừng ở cổng, chạy lại đúng bước khi bị cắt, chặn chủ đề khi agent không đổi trạng thái/vượt 20 bước, dừng hẳn khi cả hai agent hết quota, ghi `topics/code-review.yaml` — chưa nối CLI `run` | complete (lõi) | 9 test run_queue; pytest toàn bộ xanh; Ruff | `feat: add run_queue core with injected dependencies` |
| Xưởng P2 Task 2.7 | Bỏ task: visual budget là QA tỷ lệ hình, license ledger là sổ giấy phép có hash — giữ cả hai; ghi chú trong plan | dropped | — | `docs: drop task 2.7 from factory plan` |
| Xưởng P2 Task 2.5+2.6 | Gỡ Veo/AI clip (`video_ai/`, `ai_clips`, `AiClipScene`, loại asset/scene AI) và `tts-benchmark`; giữ TTS, visual budget, license ledger | complete | pytest 1105 passed, 1 skipped; vitest 113; typecheck; Ruff | `refactor: remove Veo AI clips and TTS benchmark` |
| Xưởng P6 Task 6.1 (model) | `domain/posts.py`: `PostSet` (2–3 tiêu đề YouTube, mô tả, tag ≤500 ký tự, caption TikTok/Shorts/Reels mỗi clip, bài Facebook, Community); `validate_posts` chặn câu có số liệu thiếu `[claim:…]`, claim chưa duyệt y khoa, mô tả thiếu chương/nguồn — chưa nối produce | complete (model) | 7 passed; Ruff | `feat: add multi-channel post model and claim check` |
| Xưởng P4 Task 4.3 | `video/src/anatomy/library.json` là nguồn duy nhất; `registry.ts` chọn component; `approved.json` + `anatomy_library.library_status` đánh dấu component mới/đã sửa; contact sheet có mục riêng cho component chưa duyệt (chưa nối ghi duyệt vào cổng video) | complete | pytest 1203 passed; vitest 115; typecheck; Ruff | `feat: track anatomy library approval in video review` |
| Xưởng P2 Task 2.3+2.4 | `topic_selected → research_in_progress` trực tiếp; gỡ orientation, author brief, second-model review, browser login (5 trạng thái, 14 file); nhiều truy vấn chuyển sang `evidence search --query …` | complete | pytest 1197 passed (nhánh), 1203 sau gộp; Ruff | `refactor: fold orientation into research and drop brief and second-model gates` (dòng README đi kèm commit 4.3) |
| Xưởng P2 Task 2.2 | Gỡ project v1 (`domain/project.py`, `domain/review.py`), `project new`/`migrate`, mọi profile/duration `legacy`; `content_profile` chỉ còn `explain_first_v1`; fixture golden chuyển sang explain-first; `review medical/video` gọi cổng v2 | complete | pytest 1292 passed, 1 skipped; Ruff; vitest 112; typecheck | `refactor: drop v1 projects, migrate and legacy profile` |
| Xưởng P5 Task 5.1 (module) | `discovery/`: YouTube Data API (cần `YOUTUBE_API_KEY`), Google Trends RSS VN, Reddit search; `collect` ghi `SourceFailure` thay vì nuốt lỗi; thẻ chủ đề không có số liệu thì `heat=None`; ghi `topics/discovered/<ngày>.yaml` — chưa nối CLI | complete (module) | 16 passed; Ruff | `feat: add free-source topic discovery modules` |
| Xưởng P3 Task 3.6 | 4 prompt cố định (`research`, `draft`, `revise_medical`, `revise_production`) + `render_prompt`, `HARD_RULES` (không bịa, không approve/set-pin, không commit, chỉ sửa project + SVG mới, không đăng) | complete | 43 passed; Ruff | `feat: add fixed agent prompts for factory steps` |
| Xưởng P2 Task 2.1 | Gỡ lease, backup/restore, security-audit, doctor filesystem probe (`doctor --project`), `busy`/writer khỏi operator status; xóa 18 file (≈2.800 dòng), schema lease/backup; `/pyh` + AGENTS.md bỏ M7 | complete | pytest 1384 passed, 1 skipped; Ruff | `refactor: remove multi-writer lease, backup and security audit` |
| Xưởng P3 Task 3.1+3.2 (module) | `approver_pin` (scrypt + salt, ghi nguyên tử, đổi PIN cần PIN cũ, file hỏng → không xác minh); hàng đợi `topics/queue.yaml` (`QueueEntry`, chặn slug trùng hàng đợi/project) — chưa nối CLI | complete (module) | 19 passed; Ruff | `feat: add approver PIN and topic queue modules` |
| Xưởng P3 Task 3.3+3.4 | `runner.next_step` (trạng thái → bước kế, hai cổng → None); `agents.py` gọi Codex/agy, log UTF-8, lọc biến môi trường chứa PIN, chuyển agent chỉ khi hết quota, `AllAgentsExhausted` | complete | 33 passed (test_agents, test_runner); Ruff | `feat: add runner step map and agent quota failover` |
| Xưởng video: kế hoạch triển khai | 8 giai đoạn P0–P7, 25 task; theo dõi ở đầu file plan | approved | self-review | `docs: add video factory implementation plan` |
| Xưởng video: spec tái cấu trúc | Cắt gọt tại chỗ, 4 giai đoạn, hàng đợi `run` Codex/agy, PIN chống tự duyệt, Claude chỉ rà code | approved | builder check; `git diff --check` | `docs: add video factory restructure design` |
| Video gate: sync, chart, motion, captions | TTS từng dòng, timing production có hash, WAV khớp scene và clip tái dùng audio; QA chặn lệch/đuôi im lặng; chart lớn, cơ chế chuyển động xuyên cảnh, phụ đề đủ dấu tiếng Việt | complete | pytest 1416 passed, 3 skipped; vitest passed; typecheck; Ruff; chưa render lại pilot | `feat: sync narration timing and polish mechanism visuals` |

Lịch sử trước 2026-10-23: docs/archive/README-2026-10.md
