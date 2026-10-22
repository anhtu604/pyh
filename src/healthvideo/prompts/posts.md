# Bước: Soạn bài đăng đa kênh (`posts`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Việc cần làm
1. Đọc `script.yaml`, `outline.yaml`, `clip-plan.yaml` **đã duyệt y khoa** và `evidence/ledger.yaml` của revision hiện hành để viết `revisions/<rev>/posts/posts.yaml` theo schema `PostSet` (`youtube_titles` gồm 2–3 phương án, `youtube_description`, `youtube_tags`, `clip_captions` cho từng clip với `tiktok`/`shorts`/`reels`, `facebook_post`, `youtube_community`).
2. Giữ đúng giọng kênh như kịch bản (người thường kể chuyện dễ hiểu, dí dỏm vừa phải); không thêm khẳng định y khoa mới ngoài các claim đã duyệt và không thêm quan điểm hay trải nghiệm cá nhân của bác sĩ ngoài `{doctor_note}`.
3. Mọi câu có chữ số (trừ mốc giờ đầu dòng chương trong `youtube_description`) bắt buộc phải gắn `[claim:<id>]` trỏ tới `claim_id` đã duyệt y khoa trong `evidence/ledger.yaml`.
4. Trong `youtube_description`, ghi đầy đủ mốc giờ chương kèm đúng tiêu đề chương từ `outline.yaml` và danh sách nguồn tham khảo dùng đúng nhãn nguồn (`title` của từng bản ghi trong `evidence/ledger.yaml`).
5. Chạy `healthvideo step posts-check {project}` và sửa `revisions/<rev>/posts/posts.yaml` cho tới khi không còn lỗi.

## Lệnh được dùng
- `healthvideo step posts-check {project}`
- `healthvideo status {project}`

## Đầu ra
- `revisions/<rev>/posts/posts.yaml` hợp lệ theo `PostSet` và vượt qua `posts-check`

## Xong khi
- Lệnh `healthvideo step posts-check {project}` không còn báo lỗi (mã thoát `0`).

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/posts/posts.yaml`
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/reviews/medical-approval.yaml`
