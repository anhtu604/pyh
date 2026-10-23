# Bước: Soạn kịch bản và storyboard (`draft`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
- Yêu cầu sửa nội dung từ lần từ chối trước (nếu có): `{reject_note}`. Sửa đầy đủ các điểm này trước khi nộp lại cổng y khoa.
- Nếu đang ở revision mới, cập nhật `revision` của asset manifest và license ledger sang revision hiện hành khi tái dùng đúng byte ảnh; giữ nguyên nguồn, giấy phép và SHA-256, không bịa quyền sử dụng.

## Việc cần làm
1. Soạn `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml` (video dài 16:9 thời lượng 10–25 phút, chia 4–8 chương) và `clip-plan.yaml` (1–6 clip dọc 9:16, 60–180 giây mỗi clip, chỉ cắt từ cảnh có sẵn trong storyboard kèm đủ câu giới hạn caveat, không viết lời mới) theo mạch 7 nhịp explain-first (`docs/superpowers/specs/2026-10-18-explain-first-content-design.md` §1–§15): Mở → Giải phẫu → Sinh lý → Sinh lý bệnh → Giải phẫu bệnh → Bằng chứng → Hành động + giới hạn.
2. Giữ giọng người thường kể chuyện, hài hước kiểu châm biếm niềm tin sai hoặc thói quen phổ biến chứ không châm biếm người; có hook trong 3 giây đầu; câu đùa chứa số liệu hay nhận định y khoa vẫn phải trỏ tới claim trong ledger. Viết xong lời thoại thì chạy skill `humanizer` trên toàn bộ lời thoại để khử mùi văn AI.
3. Cảnh giải phẫu/cơ chế dùng component SVG trong `video/src/anatomy/` (tái dùng hình giữa tầng bình thường và tầng bệnh qua `reuse_of`). Nếu thiếu, thêm `<Name>.tsx` + `<Name>.test.tsx`, một mục trong `library.json` và một dòng ánh xạ component trong `registry.ts` (kèm import); tất cả nằm trong `video/src/anatomy/`, không cần sửa schema hay file ngoài thư mục này. Đọc README của thư viện và ghi component mới trong báo cáo. Ảnh minh họa AI không được mang nhãn giải phẫu hay số liệu; mọi asset phải có trường `license` và `source`.
4. Chạy `healthvideo step draft {project} --script <script.yaml> --storyboard <storyboard.yaml> --assets <asset-manifest.yaml>`; sửa cho tới khi hết lỗi kiểm tra; sau đó chạy `healthvideo step submit-medical {project}`.
5. Không thêm quan điểm, lập trường hay trải nghiệm cá nhân của bác sĩ ngoài nội dung đã ghi trong `{doctor_note}`.
6. Luân phiên `process_animation` / `comparison` / `timelapse` / `whiteboard`; không quá 4 cảnh cơ chế liên tiếp cùng `anatomy.subject` và cùng `visual`. Video `youtube_long` có ≥ 6 cảnh cơ chế phải dùng ≥ 2 subject. Gan đã có `liver_organ` (LiverOrgan), `liver_lobule` (LiverLobule), `hepatic_cell_and_tissue_lipid_balance` (HepaticCell): luân phiên cơ quan ↔ tiểu thùy ↔ tế bào theo tầng giải phẫu → sinh lý → sinh lý bệnh. Camera tự chọn khung từ scene ID; đổi khung không thay cho đổi nội dung.
7. Diễn giải bằng chứng dùng `visual: source_card`, `claim_id`, `source_marker` và `source_card`: `source_id`, `title`, `journal`, `year`, `pmid`, `doi`, `interpretation`. Chép nguyên metadata từ record trong ledger; `interpretation` bằng `claim.text_public`, nguồn thuộc `claim.sources` (có thể dùng `SourceCard.from_ledger`). Thẻ được React dựng bằng font brand, không cần asset nguồn giả; tính vào ngân sách `chart_crop`.
8. Cấm tự sinh SVG/PNG giả làm ảnh chụp nguồn. `evidence_highlight` chỉ dành cho crop PNG/JPEG thật, có `source_id`, `page`, đủ metadata crop, asset semantic `evidence_highlight` với `rights_required: true` và bản ghi khớp trong `assets/license-ledger.yaml`. Chưa có crop và quyền sử dụng thì dùng thẻ nguồn.
9. Mỗi cảnh `whiteboard` phải có `on_screen_text` (≤ 90 ký tự) hoặc `visual_assets` role `whiteboard`; `brand_outro` được miễn. Chữ lớn chỉ tóm ý, không chép cả narration. Chữ có số liệu phải gắn `claim_id` và `source_marker` hợp lệ như lời đọc. Phụ đề tự dựng từ narration; không nhúng chữ lặp vào ảnh.
10. Video dài phải có ít nhất 2 cảnh whiteboard dùng minh họa FLUX (hook và một cảnh mở chương); máy không có GPU có thể bỏ và ghi rõ lý do (QA chỉ cảnh báo). Ảnh không chữ, không nhãn giải phẫu: khai báo asset `kind: illustration`, `semantic: false`, `rights_required: false`, `path: assets/illustrations/<name>.png`, `source: generated:flux2-klein-4b`, `license: Apache-2.0`, `creator`, `revision`, `prompt`, `seed`, `storyboard_role: whiteboard`; scene tham chiếu `visual_assets` với `role: whiteboard`. Produce sinh ảnh từ recipe đã duyệt, trước TTS; không dùng ảnh AI làm bằng chứng hay sơ đồ có nhãn.

SFX (tùy chọn): mỗi cảnh tối đa 2 mục `sfx: [{{id: tick, at: start, volume: 0.2}}]`; chọn id từ `assets/sfx/catalog.yaml` (chỉ CC0).
`at` là `start`, giây trong cảnh hoặc từ khóa lời đọc; volume 0.15–0.4. Dùng nhẹ, tránh âm báo động/giật gân.
Mặc định có `whoosh-soft` mở chương và `chime-soft` vào `source_card`; đặt `sfx_defaults: false` ở storyboard để tắt.

## Lệnh được dùng
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo step submit-medical {project}`
- `healthvideo status {project}`

## Đầu ra
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`
- Gói chờ duyệt cổng y khoa từ `revisions/<rev>/reviews/` qua `healthvideo review open {project} --gate medical` (và component SVG mới kèm test trong `video/src/anatomy/` nếu có)

## Xong khi
- Trạng thái đích của project đạt `awaiting_medical_review`, kiểm tra bằng lệnh `healthvideo status {project}`.

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/explainer/explainer.yaml`
