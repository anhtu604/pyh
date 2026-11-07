# Bước: Sửa theo người duyệt sản phẩm (`revise_product`)

## Bối cảnh
- Project: `{project}`
- Chủ đề: `{title}`. Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Nhận xét cần sửa
{reject_note}

## Việc cần làm
1. Đọc `active_revision` trong `{project}/project.yaml`; `<rev>` là giá trị đó. Nhận xét đầy đủ ở `{project}/revisions/<rev>/reviews/product-review-log.yaml` (vòng cuối).
2. Chỉ sửa đúng các mục trong nhận xét, và chỉ ở hai chỗ được phép:
   - component SVG trong `video/src/anatomy/`, kèm test, giữ sơ đồ tiếng Việt có leader line, tối đa 6 nhãn không chồng hay cắt;
   - `{project}/revisions/<rev>/posts/posts.yaml`; sửa xong chạy `healthvideo step posts-check {project}` cho tới khi mã thoát `0`.
3. Không sửa script, storyboard, asset-manifest, clip-plan, ledger hay explainer: chúng đã khóa bởi cổng y khoa. Mục nào cần sửa các file đó thì bỏ qua; bác sĩ sẽ thấy trong điểm chấm.
4. Không dựng video, không đổi trạng thái project. Python dựng lại ngay sau bước này và người duyệt sẽ chấm lại.

## Xong khi
- Mọi mục sửa được đã sửa; test component SVG đã sửa chạy qua.
