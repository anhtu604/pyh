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
2. Ở bước này chỉ được sửa component SVG trong `video/src/anatomy/` (kèm test). `storyboard.yaml`, `asset-manifest.yaml`, `clip-plan.yaml`, script, ledger và explainer đều nằm trong hash cổng y khoa: **không sửa** ở bước này.
3. Nếu góp ý cần sửa bất kỳ tệp nào thuộc cổng y khoa, dừng, không sửa gì, ghi rõ trong báo cáo: "Cần bác sĩ chạy `review reopen --gate medical --changed <tệp> --resume-to draft_ready`" và liệt kê tệp + thay đổi dự kiến. Sau khi bác sĩ mở cổng, bước `draft` sẽ sửa và nộp lại.
4. Nếu chỉ sửa component SVG, chạy `healthvideo step resume {project} --gate video --to production_in_progress`; lệnh này tự từ chối nếu tệp đã duyệt y khoa bị đổi.
5. Khi sửa SVG: giữ phong cách sơ đồ tiếng Việt có leader line/mũi tên; tối đa 6 nhãn không chồng/cắt. Đọc `reviews/visual-review.yaml` và contact sheet để sửa lỗi nhìn thấy. Nếu cần đổi beat/subject/prompt FLUX, áp dụng mục 3 vì các trường này thuộc storyboard/manifest đã duyệt; không sửa lách cổng.

## Lệnh được dùng
- `healthvideo step resume {project} --gate video --to production_in_progress`
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo step submit-medical {project}`
- `healthvideo status {project}`

## Đầu ra
- Component SVG kèm test trong `video/src/anatomy/` đã sửa, hoặc báo cáo nêu tệp cần bác sĩ mở lại cổng y khoa
- Trạng thái project được chuyển về sản xuất (chỉ khi không đụng tệp thuộc cổng y khoa)

## Xong khi
- Trạng thái đạt `production_in_progress`, hoặc báo cáo đã nêu rõ tệp cần bác sĩ mở lại cổng y khoa; kiểm tra bằng `healthvideo status {project}`.

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/explainer/explainer.yaml`
