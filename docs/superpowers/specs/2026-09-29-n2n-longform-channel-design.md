# Thiết kế nâng cấp M8: dây chuyền n2n video dài YouTube, clip TikTok và kế hoạch kênh

**Ngày:** 29-09-2026
**Trạng thái:** proposed; chờ người dùng duyệt spec.
**Kế thừa:** bản 07-09-2026 (§1–§4, §8–§13, §16–§17), bản 09-09-2026 (state graph,
hai cổng duyệt, roadmap M1–M7) và bản 20-09-2026 (orientation). Tài liệu này chỉ mô tả
phần thay đổi; mọi quy tắc bằng chứng, author-owned voice và hai cổng duyệt giữ nguyên.

## 1. Mục tiêu

Nâng hệ thống từ "video TikTok 45–90 giây" lên dây chuyền end-to-end (n2n) có:

1. Video YouTube dài **15–25 phút, 16:9, chuyên sâu** là sản phẩm chính.
2. **Clip TikTok/Shorts 9:16** cắt ra từ cùng kịch bản đã duyệt, không viết nội dung mới.
3. **Bảng theo dõi 10 bước** có dấu ĐẠT + thời điểm, giống video mẫu trong `sample/`.
4. **Xem và sửa trực quan**: Remotion Studio cho toàn bộ video, HyperFrames Studio cho
   đồ họa chèn.
5. **Kế hoạch kênh** dựng từ 7 prompt trong `sample/1–4.jpg`, lưu thành artifact có
   schema, nối vào topic inbox.
6. Chạy tốt trên **Antigravity** (IDE) và **Claude Code** (CLI) với cùng một workflow.

## 2. Quyết định đã chốt (29-09-2026)

| Chủ đề | Quyết định |
|---|---|
| Renderer | Giữ Remotion (`video/`, 4.0.522) làm renderer duy nhất cho video cuối |
| Sửa trực quan | Remotion Studio cho timeline; HyperFrames (Apache-2.0) cho đồ họa chèn |
| Giọng đọc | VoiceStudio chạy local trên RTX 3060 12 GB, qua ranh giới dịch vụ (AGPL) |
| Bàn giao | Render MP4 16:9 + clip 9:16 → cổng duyệt video → gói đăng; không xuất CapCut |
| Định dạng | YouTube dài 15–25 phút chuyên sâu |
| Không dùng | printfilm (nền tảng phim ngắn/lead-gen, không khớp mục tiêu) |
| Để sau | srt-whiteboard-animation (một style đồ họa), video-use (chỉ khi có cảnh quay thật) |

## 3. Quy trình 10 bước

Mười bước là **lớp hiển thị** trên state graph hiện có, không thay state graph.
Bước 4–8 là checkpoint con trong `production_in_progress`; không thêm main state mới.

| # | Bước | Nguồn trạng thái | Cổng người | Đầu ra chính |
|---|---|---|---|---|
| 1 | Đề tài & định vị | `topic_selected` → orientation → `author_brief_ready` | xác nhận brief | `topic/card.yaml`, `author-brief.yaml` |
| 2 | Tra nguồn | `research_in_progress` → `evidence_ready` | — | claim ledger đã xác minh |
| 3 | Kịch bản | `draft_ready` → `awaiting_medical_review` | **Cổng 1: duyệt y khoa** | `outline.yaml`, `script.yaml`, `storyboard.yaml`, `clip-plan.yaml` |
| 4 | Giọng đọc | checkpoint `voice` | nghe thử | audio từng chương + word timestamps |
| 5 | Tư liệu | checkpoint `sources_media` | — | asset có license ledger |
| 6 | Đồ họa | checkpoint `graphics` | — | whiteboard, biểu đồ, clip HyperFrames |
| 7 | Chọn hình | checkpoint `selection` | — | asset gán cho từng cảnh, visual budget đạt |
| 8 | Nhịp dựng | checkpoint `pacing` | xem trong Studio | timing QA đạt, preview |
| 9 | Bàn giao | `awaiting_video_review` → `video_approved` → `packaged` | **Cổng 2: duyệt video** | `long.mp4`, `clips/*.mp4` |
| 10 | SEO & Thumbnail | trong `packaged` | chọn thumbnail | tiêu đề, mô tả, chapters, thumbnail |

### 3.1. Bảng ĐẠT

`healthvideo operator board <project>` in bảng 10 dòng: `✓ ĐẠT <ISO timestamp>`,
`▶ đang chạy`, `✗ lỗi: <mã>` hoặc `· chưa tới`. Dữ liệu lấy từ state, checkpoint
manifest và review record; bảng chỉ đọc, không tạo approval. Có thêm `--html` để ghi
`board.html` cạnh `review_html` hiện có.

## 4. Định dạng: format profile

Thay hằng số cứng (`MAX_DURATION_FRAMES = 90 * FPS`, `1080×1920`) bằng profile:

| Profile | Kích thước | Thời lượng | Dùng cho |
|---|---|---|---|
| `youtube_long` | 1920×1080 | 15–25 phút | video chính |
| `vertical_clip` | 1080×1920 | 30–90 giây | TikTok, Shorts, Reels |

Project v2 cũ mặc định `vertical_clip`, nên hành vi cũ và test cũ giữ nguyên.

### 4.1. Video dài theo chương

- `outline.yaml` chia 5–8 chương; mỗi chương có mục tiêu, claim ID và thời lượng dự kiến.
- Khung 6 nhịp (§9.2 bản 07-09) áp dụng ở cấp chương; có thêm mở đầu (hook ≤ 30 giây,
  không phóng đại) và kết (tóm tắt + giới hạn + hành động).
- Tốc độ đọc khoảng 130–160 từ/phút, nên 20 phút ≈ 2.600–3.200 từ.
- Render theo chương rồi ghép bằng FFmpeg. Cache theo hash chương: sửa một chương chỉ
  render lại chương đó. 25 phút ở 30 fps là 45.000 frame; render lần đầu được tính bằng
  giờ, sẽ đo thực tế trong plan.
- Chapter timestamps sinh từ timeline thật để dùng cho mô tả YouTube.

### 4.2. Clip dọc từ video dài

- `clip-plan.yaml` liệt kê 3–6 đoạn. Mỗi đoạn tham chiếu một dải cảnh liên tục của
  kịch bản đã duyệt, cộng hook/outro ngắn lấy từ câu đã có trong script.
- Clip được **dựng lại bố cục 9:16** từ storyboard, không crop khung 16:9.
- Validator an toàn nội dung: nếu clip chứa claim có giới hạn/ngoại lệ gắn kèm trong
  ledger thì clip phải chứa câu giới hạn đó. Clip không được thêm claim mới. Vi phạm
  thì chặn render clip.
- `clip-plan.yaml` nằm trong gói Cổng 1, nên bác sĩ duyệt luôn việc cắt đoạn. Mỗi clip
  render xong được đưa vào Cổng 2 cùng video dài.

## 5. Giọng đọc: VoiceStudio

- VoiceStudio cài và chạy như ứng dụng riêng; repo không vendor mã AGPL.
- Adapter `VoiceStudioTTS` gọi API local qua `127.0.0.1`, theo protocol TTS hiện có
  (`synthesize → audio + word_timestamps + metadata`). Nếu API không có timestamps
  thì dùng faster-whisper căn lại, như hiện tại.
- Tổng hợp theo chương/câu để có thể tiếp tục khi bị gián đoạn; cache theo hash câu.
- `healthvideo doctor` kiểm tra VoiceStudio đang chạy, model đã tải, GPU có sẵn.
- Clone giọng bác sĩ **không** bật mặc định; nếu làm sau thì cần văn bản đồng ý lưu
  trong project.
- Chưa xác minh được VoiceStudio hỗ trợ tiếng Việt tốt đến đâu. Plan phải có bước
  benchmark nghe mù với VieNeu-TTS (bản 09-09 §23) trước khi khóa provider.

## 6. Sửa trực quan

### 6.1. Remotion Studio (toàn video)

- `pnpm --dir video studio` mở composition `LongForm` và `VerticalClip` với input props
  của project đang chọn.
- Props có zod schema, nên Studio chỉnh được các tham số hiển thị: vị trí chữ, màu, nhịp
  animation, thời điểm vào/ra cảnh.
- Chỉnh trong Studio **không** sửa lời thoại, claim hay số liệu. Thay đổi được ghi ngược
  vào `storyboard.yaml` qua lệnh `healthvideo storyboard apply-props` và đi qua
  invalidation policy hiện có: thay đổi hình ảnh → rerender; thay đổi ngữ nghĩa → quay
  về Cổng 1.

### 6.2. HyperFrames (đồ họa chèn)

- Dùng cho title card, lower-third, biểu đồ động phức tạp, thumbnail frame và intro kênh.
- Mỗi đồ họa là một composition HTML trong `graphics/<id>/`, render ra MP4/PNG và vào
  asset manifest với license `self-made`. Remotion chỉ nhúng file đã render.
- Số liệu trong biểu đồ HyperFrames chỉ đọc từ file dữ liệu sinh từ ledger; lint kiểm
  tra không có số viết tay.
- Cài skill HyperFrames bằng `npx hyperframes skills update` (bộ core) cho cả Claude
  Code và Antigravity.

**Lý do không dùng HyperFrames làm renderer chính:** hai renderer cho cùng một video sẽ
nhân đôi timeline, test và cache. Remotion đã có 11 test hình ảnh và contract Python→TS.

## 7. SEO, thumbnail và gói đăng

- Sinh 3 tiêu đề, mô tả có chapters và nguồn đầy đủ, tag và 3 phương án thumbnail
  (frame HyperFrames + chữ ngắn). Bác sĩ chọn trong gói đăng.
- Tiêu đề và thumbnail qua cùng kiểm tra "không phóng đại" như hook: không hứa chữa
  khỏi, không tuyệt đối hóa, không mâu thuẫn ledger.
- Gói `publish/` tách `youtube/` và `tiktok/<clip-id>/`, mỗi phần có checklist đăng
  thủ công. **Không tự động đăng.**

## 8. Kế hoạch kênh

Bảy prompt mẫu trở thành 7 artifact trong `channel/`, mỗi artifact do một phiên agent
tạo từ template prompt trong `channel/prompts/`:

| # | Artifact | Nội dung |
|---|---|---|
| 1 | `plan.yaml` | định vị, trụ cột nội dung, lịch tuần |
| 2 | `niche.yaml` | chân dung người xem, khác biệt, 100 ý tưởng xếp hạng → topic cards |
| 3 | `hook-thumbnail.yaml` | quy tắc hook/tiêu đề/thumbnail đã lọc theo an toàn y khoa |
| 4 | `growth.yaml` | tần suất, thử nghiệm A/B tiêu đề/thumbnail, vòng đời video |
| 5 | `production.yaml` | ánh xạ 10 bước và checklist QA |
| 6 | `monetization.yaml` | các nguồn thu theo giai đoạn kênh, kèm ràng buộc xung đột lợi ích |
| 7 | `analytics/` | import CSV xuất tay từ YouTube Studio → báo cáo tuần/tháng |

Ràng buộc:

- Mọi nhận định thị trường (lượng tìm kiếm, CPM, đối thủ) là **giả thuyết** có ngày và
  nguồn, hoặc ghi `unverified`. Không bịa số liệu.
- Ý tưởng video trong `niche.yaml` chỉ thành topic card; vẫn phải qua orientation.
- Monetization không được đưa sản phẩm/tài trợ vào nội dung y khoa khi chưa khai báo xung
  đột lợi ích trong brief; tài trợ bị chặn ở chủ đề thuốc/thực phẩm chức năng trừ khi bác
  sĩ ghi rõ ngoại lệ.
- Analytics chỉ đọc file người dùng xuất; không gọi YouTube API ở M8.

## 9. Antigravity và Claude Code

- Một nguồn sự thật: CLI `healthvideo` + skill `/pyh`. Adapter mỏng cho từng agent:
  - Claude Code: `.claude/skills/` (đang có).
  - Antigravity: file rule và workflow trỏ về cùng skill và AGENTS.md.
- Chưa xác minh quy ước thư mục của Antigravity (rule, workflow, skill). Task đầu của
  plan là đọc tài liệu Antigravity hiện hành rồi mới tạo file; không đoán tên thư mục.
- Mọi lệnh chạy được trong PowerShell (`pathlib.Path`), không yêu cầu bash.
- Smoke test: cùng một project mẫu chạy đến `awaiting_medical_review` từ cả hai agent.

## 10. Thời gian bác sĩ (ước tính, cần đo lại)

| Hoạt động | Phút/video dài |
|---|---:|
| Chọn đề tài, xác nhận brief | 10–15 |
| Duyệt nguồn, claim, outline, script, clip-plan | 45–75 |
| Nghe thử giọng | 10–20 |
| Xem video dài + clip, ghi patch | 30–40 |
| Chọn tiêu đề/thumbnail, duyệt gói | 5–10 |
| **Tổng** | **100–160** |

Máy: TTS khoảng 10–20 phút; render lần đầu vài giờ, rerender một chương vài phút (sẽ đo).

## 11. Kiểm thử

- Unit: format profile, outline/chương, clip-plan validator (claim mới, giới hạn thiếu),
  board 10 bước, apply-props invalidation.
- Contract: schema `outline`, `clip-plan`, `channel/*`, render input 16:9.
- Visual regression: 1 frame mỗi composition `LongForm`, `VerticalClip`.
- Integration: VoiceStudio adapter với server giả; skip nếu không có server thật.
- E2E: project mẫu ~3 phút (profile test rút gọn) từ brief đến `packaged`, có 2 clip.
- Hồi quy: toàn bộ 973 test hiện có vẫn qua; project cũ mặc định `vertical_clip`.

## 12. Roadmap M8

| Mốc | Nội dung | Ước tính |
|---|---|---|
| M8.1 | Format profile + composition `LongForm` + render theo chương | 2–3 ngày |
| M8.2 | Outline + clip-plan + validator + composition `VerticalClip` | 2 ngày |
| M8.3 | VoiceStudio adapter + benchmark tiếng Việt | 1–2 ngày |
| M8.4 | Board 10 bước (CLI + HTML) | 0,5 ngày |
| M8.5 | Remotion Studio props + apply-props; HyperFrames graphics | 2 ngày |
| M8.6 | SEO/thumbnail + gói đăng YouTube/TikTok | 1 ngày |
| M8.7 | Kênh: 7 artifact + prompt template + import analytics | 1–2 ngày |
| M8.8 | Adapter Antigravity + smoke test hai agent | 0,5–1 ngày |

## 13. Rủi ro

| Rủi ro | Kiểm soát |
|---|---|
| Clip cắt mất ngữ cảnh, gây hiểu sai | Validator giới hạn bắt buộc; clip-plan qua Cổng 1; clip qua Cổng 2 |
| Render dài, hỏng giữa chừng | Render theo chương, cache hash, tiếp tục từ chương lỗi |
| VoiceStudio đọc tiếng Việt kém | Benchmark mù trước khi khóa; giữ adapter VieNeu/command |
| AGPL | Chỉ gọi qua HTTP local; không copy mã |
| Giấy phép Remotion | Miễn phí cho cá nhân/công ty ≤ 3 người; rà lại khi mở rộng đội |
| Tiêu đề/thumbnail câu view | Kiểm tra phóng đại; bác sĩ chọn |
| Quy ước Antigravity thay đổi | Adapter mỏng, logic nằm ở CLI |

## 14. Câu hỏi mở (không chặn M8.1)

1. Nhịp đăng: 1 video dài/tuần + 3–5 clip, hay 2 video dài/tháng?
2. Tên kênh, nhận diện 16:9 (logo, intro ≤ 5 giây)?
3. Có dùng lại mascot M6.3 trong video dài không?

## 15. Điều kiện chuyển sang plan

Người dùng duyệt spec này hoặc yêu cầu sửa. Sau đó viết
`docs/superpowers/plans/2026-09-29-n2n-longform-channel.md` theo task nhỏ, có file,
test và lệnh xác minh.
