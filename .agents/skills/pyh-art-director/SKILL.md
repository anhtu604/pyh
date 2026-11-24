---
name: pyh-art-director
description: Use when PYH visual_review must inspect generated image candidates and contact sheets.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Asset/index/contact sheet và mẫu chuyển tầng có thể mở, script/manifest/nguồn cùng revision.
output: reviews/visual-review.yaml có inspected_images, quyết định và lỗi pixel/giải phẫu/quyền/đọc rõ.
done_when: Ảnh thực đã mở và phần chưa kiểm được ghi đúng; D4 không vượt ba lần chấm.
missing_data_to: storyboard_director sửa hình; medical_expert xác minh giải phẫu; coordinator/bác sĩ khi thiếu ảnh/quyền hoặc hết budget.
```


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
    không bóng đổ/nhựa 3D, không grain; loại chữ/số AI và vật thể lạ. Hình khoa học có phép giữ màu giải phẫu khi cần, không reject chỉ vì khác palette minh họa.
  - FLUX chỉ cho cảnh đời sống; không dùng FLUX cho hình giải phẫu/y khoa (mục 3).
  - Chọn/kiểm tư thế mascot theo đúng 9 tư thế mục 2: `welcome`, `explain`, `point_up`,
    `thinking`, `surprised`, `caution`, `myth_bust`, `blank_board`, `thumbs_up`; mỗi tư thế khớp ý lời đọc.
  - Báo mọi lệch phong cách bằng mã lỗi chuẩn `style_*` trong `style_issues`:
    `style_palette`, `style_typography`, `style_mascot_pose`, `style_stroke`,
    `style_medical_art`, `style_caption`, `style_zoom`.
- Hình phải giúp hiểu đúng câu: đúng cơ quan, bên, vị trí và biểu hiện;
  không biến minh họa trang trí thành bằng chứng hay suy diễn chẩn đoán.
- Kiểm chữ/nhãn/phụ đề có dải riêng, đọc ở kích thước nhỏ (720p),
  không che chủ thể/tổn thương, chồng nhau hay cắt mép; 16:9 không phụ đề cháy chữ, 9:16 giữ phụ đề, cho highlight từ/cụm khi có timing.
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
  Python áp dụng báo cáo trong budget D4; không dùng fallback tự vẽ cơ quan thay asset có phép. Thiếu mapping/asset đúng chủ đề trả storyboard_director và coordinator, không chọn ảnh sai để xong.

## D4 — budget hình
- Tối đa 3 lần chấm/revision (đầu + hai lần sửa); cùng issue còn mở hai lần liên tiếp dừng sớm. Hết budget dừng, giữ chưa đạt và trình brief/bằng chứng qua coordinator cho bác sĩ; không tự submit gate.
- Revision/stage/issue_id/fingerprint giữ đếm bền qua restart/failover/đổi hash/rerender/reset submitted; không tự tạo revision để reset. Chỉ bác sĩ yêu cầu rõ nội dung/phạm vi mới đi revision mới. Sau vòng đầu kiểm diff/ảnh hưởng, vẫn báo nguy cơ an toàn mới.
- Độc lập storyboard_director cả fallback và session; chỉ ghi đã xem khi mở pixel thật. Kiểm cấu trúc/quyền/SHA, chuyển tầng mẫu có anchor, mascot có sẵn chỉ ở câu chốt và vắng trong giải phẫu cận; cơ chế dùng Servier/NIAID/DBCLS/Reactome có phép + vector Remotion, không FLUX. Không chấm âm thanh bằng ảnh.

## Xong khi
- Mọi cảnh có quyết định và danh sách ảnh đã xem trung thực, không tự duyệt cổng.

## Thiếu dữ liệu hoặc lỗi
- Không mở được ảnh/index thì ghi rõ ảnh nào chưa kiểm, không nhận đã xem đủ.
- Lỗi công cụ ghi log/thông báo thật, chỉ thử trong budget prompt;
  không sửa index/hash hay đổi lời/claim để hợp thức ảnh sai.
