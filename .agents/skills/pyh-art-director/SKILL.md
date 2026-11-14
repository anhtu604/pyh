---
name: pyh-art-director
description: Use when PYH visual_review must inspect generated image candidates and contact sheets.
---

# Đạo diễn hình xưởng PYH

## Đầu vào
- Đọc prompt `visual_review.md`, `active_revision` trong `{project}/project.yaml`.
  Dùng `revisions/<rev>/reviews/visual/candidates.yaml`, storyboard và lời đã duyệt.
- Mở trực tiếp từng candidate và mọi `contact_sheets[].path` trong index bằng
  công cụ xem ảnh; không đoán nội dung từ tên file, seed hay prompt.
- Đọc `docs/reference/image-prompting.md` khi cần viết prompt thay thế.

## Phán đoán công việc
- Hình phải giúp hiểu đúng câu: đúng cơ quan, bên, vị trí và biểu hiện;
  không biến minh họa trang trí thành bằng chứng hay suy diễn chẩn đoán.
- Kiểm phong cách vector y khoa phẳng 2D nền kem, không bóng nhựa 3D;
  loại chữ/số AI, vật thể lạ, đạo cụ ánh sáng thừa và ẩn dụ khó hiểu.
- Kiểm chữ/nhãn/phụ đề có dải riêng, đọc ở kích thước nhỏ,
  không che chủ thể/tổn thương, chồng nhau hay cắt mép.
- Đối chiếu contact sheet với nhịp câu và điều cần nhấn; hiệu ứng đều theo
  khoảng thời gian không tự chứng minh hình có ích hoặc video hấp dẫn.
- Chỉ ảnh/contact sheet không chứng minh đã nghe âm thanh hoặc xem mọi khung.
- Cảnh dùng chung asset chọn cùng ứng viên; không chọn sai để xong bước.
- Cả ba seed lỗi thì reject, viết `new_prompt` tiếng Anh: cỡ cảnh/góc nhìn,
  tỉ lệ chủ thể, mép cắt rõ; một chủ thể, biểu hiện nhìn thấy nếu phù hợp;
  tả hiệu ứng ánh sáng thay vì gọi nguồn sáng, phong cách phẳng matte, `no text`.

## Đầu ra
- Chỉ ghi `revisions/<rev>/reviews/visual-review.yaml`:
  `candidate_index_sha256` đúng file vừa đọc, `inspected_images` chỉ ảnh đã mở,
  `scenes` đủ từng cảnh với `scene`, `decision`, `selected`, `reason`,
  `layout_issues`, `new_prompt` đúng schema prompt.
- `reason` nêu thứ thật thấy và liên hệ lời thoại; layout lỗi vẫn phải ghi.
- Không sửa script/storyboard/manifest/index/ảnh/approval, không tự chạy GPU.
  Python áp dụng báo cáo, sinh lại trong budget tối đa hai vòng. Chỉ fallback SVG
  khi có mapping/component phù hợp; `_fallback_subject` hiện chỉ có gout/urat.
  Ngoài mapping, báo rõ cần SVG đúng chủ đề; không hứa fallback luôn chạy
  và không chọn ảnh sai để tránh lỗi runtime.

## Xong khi
- Mọi cảnh có quyết định và danh sách ảnh đã xem trung thực, không tự duyệt cổng.

## Thiếu dữ liệu hoặc lỗi
- Không mở được ảnh/index thì ghi rõ ảnh nào chưa kiểm, không nhận đã xem đủ.
- Lỗi công cụ ghi log/thông báo thật, chỉ thử trong budget prompt;
  không sửa index/hash hay đổi lời/claim để hợp thức ảnh sai.
