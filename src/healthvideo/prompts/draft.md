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
3. Phong cách: sơ đồ y khoa có chú thích tiếng Việt, kiểu Osmosis/Armando Hasudungan. Cảnh cơ chế dùng SVG trong `video/src/anatomy/`; nhãn thuật ngữ cố định từ `LABELS`, có leader line và mũi tên quá trình, tối đa 6 nhãn không chồng/cắt. Nếu thiếu component, thêm `.tsx` + test, đăng ký `library.json`/`registry.ts`, khai báo `FOCUS_REGIONS`, `LABELS`, `CUE_ACTIONS`; đọc README thư viện. Chỉ minh họa nội dung lời thoại đã duyệt; mọi asset có `license`, `source`. FLUX không chứa chữ/nhãn/số liệu.
4. Chạy `healthvideo step draft {project} --script <script.yaml> --storyboard <storyboard.yaml> --assets <asset-manifest.yaml>`; sửa cho tới khi hết lỗi kiểm tra; sau đó chạy `healthvideo step submit-medical {project}`.
5. Không thêm quan điểm, lập trường hay trải nghiệm cá nhân của bác sĩ ngoài nội dung đã ghi trong `{doctor_note}`.
6. Luân phiên `process_animation` / `comparison` / `timelapse` / `whiteboard`; không quá 4 cảnh cơ chế liên tiếp cùng subject và visual. Video dài dùng ≥ 4 subject, clip dọc ≥ 2 subject. Chọn góc nhìn cơ quan ↔ mặt cắt ↔ tế bào ↔ tinh thể theo đúng lời thoại. Đổi camera không thay đổi nội dung; không giữ hình không đổi quá 6 giây.
7. Diễn giải bằng chứng dùng `visual: source_card`, `claim_id`, `source_marker` và `source_card`: `source_id`, `title`, `journal`, `year`, `pmid`, `doi`, `interpretation`. Chép nguyên metadata từ record trong ledger; `interpretation` bằng `claim.text_public`, nguồn thuộc `claim.sources` (có thể dùng `SourceCard.from_ledger`). Thẻ được React dựng bằng font brand, không cần asset nguồn giả; tính vào ngân sách `chart_crop`.
8. Cấm tự sinh SVG/PNG giả làm ảnh chụp nguồn. `evidence_highlight` chỉ dành cho crop PNG/JPEG thật, có `source_id`, `page`, đủ metadata crop, asset semantic `evidence_highlight` với `rights_required: true` và bản ghi khớp trong `assets/license-ledger.yaml`. Chưa có crop và quyền sử dụng thì dùng thẻ nguồn.
9. Mỗi cảnh `whiteboard` phải có `on_screen_text` (≤ 90 ký tự) hoặc `visual_assets` role `whiteboard`; `brand_outro` được miễn. Chữ lớn chỉ tóm ý, không chép cả narration. Chữ có số liệu phải gắn `claim_id` và `source_marker` hợp lệ như lời đọc. Phụ đề tự dựng từ narration; không nhúng chữ lặp vào ảnh.
10. Video dài có ít nhất 2 whiteboard minh họa FLUX (hook, mở chương); thiếu GPU thì ghi rõ. Prompt mô tả trực tiếp chủ đề, ví dụ "flat medical illustration of a swollen red big toe joint, no text"; cấm vật thể ẩn dụ khó hiểu. Asset: `kind: illustration`, `semantic: false`, `rights_required: false`, `path: assets/illustrations/<name>.png`, `source: generated:flux2-klein-4b`, `license: Apache-2.0`, `creator`, `revision`, `prompt`, `seed`, `storyboard_role: whiteboard`; scene role `whiteboard`. Produce sinh 3 seed để visual_review chọn; ảnh và chữ có dải riêng, không đè nhau; ảnh AI không làm bằng chứng.
11. Mỗi cảnh cơ chế có `beats: [{at: "từ khóa", focus: "FOCUS_REGION hoặc null", labels: ["id trong LABELS"], action: "CUE_ACTION hoặc null"}]`; `at` dùng số khi là giây. Cảnh > 12 giây có ≥ 2 beat; khoảng giữa thay đổi hình ≤ 6 giây. Whisper căn từ khóa; camera ease 0.8 giây, nhãn bật/tắt theo beat. Có thể thêm `anatomy.cues: [{word: "từ khóa", action: "CUE_ACTION"}]`. Whiteboard tách ý bằng dấu chấm phẩy để trải entrance; không dồn thay đổi đầu cảnh.
12. Nhịp nhấn và thẻ chuyển động (`docs/reference/motion-vocabulary.md`): mỗi cảnh có thể gắn `motion: {{emphasis?: <tên thẻ>, emphasis_text?: "cụm từ có trong narration", transition_in?: <tên chuyển cảnh>}}` (nhấn mạnh tối đa 1 cụm/cảnh, không chồng hiệu ứng). Có thể dùng `visual: stat_gauge` (`stat_gauge: {{value, unit, label, max_value?, variant?}}`, bắt buộc gắn `claim_id` thuộc ledger, nhóm `chart_crop`) cho con số lâm sàng hoặc `visual: kinetic_term` (`kinetic_term: {{term, definition, variant?}}`, nhóm `whiteboard_svg`) cho thuật ngữ cốt lõi.
SFX (tùy chọn): mỗi cảnh tối đa 2 mục `sfx: [{{id: tick, at: start, volume: 0.2}}]`; chọn id từ `assets/sfx/catalog.yaml` (chỉ CC0).
`at` là `start`, giây trong cảnh hoặc từ khóa lời đọc; volume 0.15–0.4. Dùng nhẹ, tránh âm báo động/giật gân.
Mặc định có `whoosh-soft` mở chương và `chime-soft` vào `source_card`; đặt `sfx_defaults: false` ở storyboard để tắt.

## Giọng văn và cách đọc
- Nói như người thật kể cho bạn bè, xưng "mình", gọi người xem là "bạn"; câu ngắn, câu dài xen nhau; có từ đệm tự nhiên ("có điều", "mà", "thôi", "đấy", "nhé") nhưng không lạm dụng.
- Xéo xắt nhẹ với **hiểu lầm**, không bao giờ với người bệnh. Nội dung y khoa và giới hạn bằng chứng giữ nguyên chuẩn mực.
- **Không** tự bình luận về hình ("màn hình", "ô vuông", "chấm", "ký hiệu", "hình mô phỏng", "màu xanh là…"): hình tự nói, lời chỉ kể chuyện.
- Giới hạn bằng chứng (thí nghiệm ngoài cơ thể, động vật…) gom vào 1–2 câu ở chương nguồn, không rải khắp nơi.
- Không giọng thuyết trình: không "Video này…", "Ta sẽ xem…", "Hãy cùng…", "khám phá", "hành trình", "Điều cần giữ lại là…", "Câu ngắn để nhớ là…".
- Không ẩn dụ rồi tự giải thích rằng đó chỉ là ẩn dụ. Xem 2 cặp ví dụ "Bản cũ → Bản mới" trong `src/healthvideo/prompts/style_examples.vi.md`.
- Mỗi dòng có `delivery` là nguyên văn `text` kèm 1–3 thẻ từ `allowed_tags` trong `profiles/voice.yaml` (ví dụ `[curious]`, `[sarcastic]`, `[pause]`) đặt đúng chỗ, không lạm dụng. Bỏ thẻ phải trùng `text`; phụ đề luôn dùng `text`. Nhịp bằng chứng/giới hạn nên dùng sắc thái tò mò hoặc ngắt nghỉ, không châm biếm.

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
