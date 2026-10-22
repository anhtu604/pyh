# Bước: Sửa theo góp ý cổng video (`revise_production`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
- Ghi chú từ chối cổng video: `{reject_note}`

## Việc cần làm
1. Đọc kỹ ghi chú từ chối `{reject_note}` và file `*-rejected.yaml` mới nhất trong thư mục `reviews/video/` của revision hiện hành để xác định các lỗi hình ảnh, hoạt họa, nhịp dựng, phụ đề hoặc âm thanh cần chỉnh.
2. Sửa `storyboard.yaml`, `asset-manifest.yaml`, `clip-plan.yaml` hoặc component SVG trong `video/src/anatomy/` (kèm test) theo đúng ghi chú từ chối. Giữ nguyên quy tắc ảnh minh họa AI không mang nhãn giải phẫu hay số liệu, và mỗi asset đều có `license` hợp lệ.
3. Nếu phải sửa lời thoại, claim, explainer hoặc clip-plan đã duyệt, dừng và yêu cầu bác sĩ mở lại cổng y khoa bằng `review reopen`; không sửa trước khi mở cổng. Sau khi mở, dùng quy trình `revise_medical` để nộp lại.
4. Nếu chỉ sửa hình ảnh/storyboard/component mà không đụng nội dung y khoa đã duyệt, chạy `healthvideo step resume {project} --gate video --to production_in_progress` để đưa project quay lại giai đoạn sản xuất.

## Lệnh được dùng
- `healthvideo step resume {project} --gate video --to production_in_progress`
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo step submit-medical {project}`
- `healthvideo status {project}`

## Đầu ra
- `storyboard.yaml`, `asset-manifest.yaml`, `clip-plan.yaml` hoặc component SVG kèm test trong `video/src/anatomy/` đã sửa theo góp ý
- Trạng thái project được chuyển về sản xuất (hoặc mở lại cổng y khoa nếu sửa nội dung y khoa)

## Xong khi
- Trạng thái đích của project đạt `production_in_progress` (hoặc `awaiting_medical_review` nếu có thay đổi lời thoại/claim/explainer), kiểm tra bằng lệnh `healthvideo status {project}`.

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/explainer/explainer.yaml`
