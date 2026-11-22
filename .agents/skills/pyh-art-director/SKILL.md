---
name: pyh-art-director
description: Use when PYH visual_review must inspect generated image candidates and contact sheets.
---

# Đạo diễn hình xưởng PYH

## Vòng duyệt lại
- Chỉ xem/chọn lại asset chưa có selected/fallback; mở ảnh mới và contact sheet
  làm ngữ cảnh. Giữ nguyên quyết định cảnh đã chọn; không yêu cầu sinh lại phần đạt.
- Báo cáo chỉ cần các cảnh còn chờ; Python giữ quyết định đã chọn.
- Không nêu lỗi mới ở cảnh không đổi, trừ an toàn y khoa nghiêm trọng:
  ghi `blocking_safety: true`, lý do và dừng chờ bác sĩ.

## Đầu vào
- Đọc prompt `visual_review.md`, `active_revision` trong `{project}/project.yaml`.
  Dùng `revisions/<rev>/reviews/visual/candidates.yaml`, storyboard và lời đã duyệt.
- Mở trực tiếp từng candidate và mọi `contact_sheets[].path` trong index bằng
  công cụ xem ảnh; không đoán nội dung từ tên file, seed hay prompt.
- Đọc `docs/reference/image-prompting.md` khi cần viết prompt thay thế.

## Phán đoán công việc
- Đối chiếu chuẩn phong cách PYH đã ghim (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`, mục 1–3b) cho cả SVG và FLUX ở 16:9/9:16 khi có mẫu; thiếu mẫu ghi rõ chưa kiểm:
  - Kiểm ảnh/FLUX theo mục 1: nền `off_white #F7F4EC`, nét/chữ `navy #12304A` 6 px phẳng 2D matte,
    nhấn `teal #18A6A6`, chốt `yellow #F4B942`, tối đa 3 màu nổi, không đỏ báo động, không gradient,
    không bóng đổ/nhựa 3D, không grain, không ảnh stock, loại chữ/số AI và vật thể lạ.
  - FLUX chỉ cho cảnh đời sống; không dùng FLUX cho hình giải phẫu/y khoa (mục 3).
  - Chọn/kiểm tư thế mascot theo đúng 9 tư thế mục 2: `welcome`, `explain`, `point_up`,
    `thinking`, `surprised`, `caution`, `myth_bust`, `blank_board`, `thumbs_up`; mỗi tư thế khớp ý lời đọc.
  - Báo mọi lệch phong cách bằng mã lỗi chuẩn `style_*` trong `style_issues`:
    `style_palette`, `style_typography`, `style_mascot_pose`, `style_stroke`,
    `style_medical_art`, `style_caption`, `style_zoom`.
- Hình phải giúp hiểu đúng câu: đúng cơ quan, bên, vị trí và biểu hiện;
  không biến minh họa trang trí thành bằng chứng hay suy diễn chẩn đoán.
- Kiểm chữ/nhãn/phụ đề có dải riêng, đọc ở kích thước nhỏ (720p),
  không che chủ thể/tổn thương, chồng nhau hay cắt mép; phụ đề tĩnh theo trang, không highlight từng chữ.
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
  `scenes` đủ từng cảnh với `scene`, `decision`, `selected`, `mascot_pose` (khi có mascot),
  `reason`, `layout_issues`, `style_issues` (dùng mã `style_*`), `new_prompt` đúng schema prompt.
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
