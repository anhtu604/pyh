# Bước: Soạn kịch bản và storyboard (`draft`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Việc cần làm
1. Soạn `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml` (video dài 16:9 thời lượng 10–25 phút, chia 4–8 chương) và `clip-plan.yaml` (1–6 clip dọc 9:16, 60–180 giây mỗi clip, chỉ cắt từ cảnh có sẵn trong storyboard kèm đủ câu giới hạn caveat, không viết lời mới) theo mạch 7 nhịp explain-first (`docs/superpowers/specs/2026-10-18-explain-first-content-design.md` §1–§15): Mở → Giải phẫu → Sinh lý → Sinh lý bệnh → Giải phẫu bệnh → Bằng chứng → Hành động + giới hạn.
2. Giữ giọng người thường kể chuyện, hài hước kiểu châm biếm niềm tin sai hoặc thói quen phổ biến chứ không châm biếm người; có hook trong 3 giây đầu; câu đùa chứa số liệu hay nhận định y khoa vẫn phải trỏ tới claim trong ledger. Viết xong lời thoại thì chạy skill `humanizer` trên toàn bộ lời thoại để khử mùi văn AI.
3. Cảnh giải phẫu/cơ chế dùng component SVG trong `video/src/anatomy/` (tái dùng hình giữa tầng bình thường và tầng bệnh qua `reuse_of`); nếu thiếu thì thêm component SVG mới kèm test trong `video/src/anatomy/` (ghi rõ trong báo cáo). Ảnh minh họa AI không được mang nhãn giải phẫu hay số liệu; mọi asset phải có trường `license` và `source`.
4. Chạy `healthvideo step draft {project} --script <script.yaml> --storyboard <storyboard.yaml> --assets <asset-manifest.yaml>`; sửa cho tới khi hết lỗi kiểm tra; sau đó chạy `healthvideo step submit-medical {project}`.
5. Không thêm quan điểm, lập trường hay trải nghiệm cá nhân của bác sĩ ngoài nội dung đã ghi trong `{doctor_note}`.

## Lệnh được dùng
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo step submit-medical {project}`
- `healthvideo status {project}`

## Đầu ra
- `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml`, `clip-plan.yaml` trong `revisions/<rev>/draft/`
- Gói chờ duyệt cổng y khoa trong `revisions/<rev>/reviews/medical/` (và component SVG mới kèm test trong `video/src/anatomy/` nếu có)

## Xong khi
- Trạng thái đích của project đạt `awaiting_medical_review`, kiểm tra bằng lệnh `healthvideo status {project}`.
