# Kiểm trực quan sau bản render ứng viên
Project: {project}
Chủ đề: {title}. Câu hỏi: {question}
Ghi chú bác sĩ: {doctor_note}

Mục tiêu: xem thật mọi ảnh ứng viên và contact sheet trước khi Python dựng bản cuối.
Đọc project.yaml để xác định revision; chỉ ghi trong revision này.
Đọc `reviews/visual/candidates.yaml`, storyboard, lời thoại đã duyệt và chuẩn phong cách `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` (mục 1–3b).
Dùng công cụ xem ảnh để mở TỪNG candidate và MỌI `contact_sheets[].path` trong index.
Không suy đoán nội dung ảnh từ tên file hay prompt. Ghi trung thực những gì đã xem.
Kiểm từng ảnh/FLUX theo mục 1: nền `off_white #F7F4EC`, nét/chữ `navy #12304A` phẳng 2D matte, nhấn `teal #18A6A6` / `yellow #F4B942`, tối đa 3 màu nổi, không đỏ báo động, không gradient/bóng đổ/grain/chữ AI trong minh họa; hình khoa học có phép giữ màu giải phẫu khi cần; FLUX chỉ cho cảnh đời sống (không dùng FLUX cho hình y khoa).
Kiểm bắt buộc bàn tay ở mọi ảnh/FLUX có bàn tay: đếm ngón trên từng bàn tay (đúng 5 ngón mỗi tay, ngón cái đúng chỗ, độ dài ngón hợp lý, không dính/chồng, tay không quá to dính vào tờ giấy/đồ vật), cổ tay/cẳng tay liền mạch. Sai thì ghi `style_hands` vào `style_issues` và `reject`; không chọn ảnh tay sai "cho xong". Nếu cả ba ứng viên tay sai: `reject` và `new_prompt` phải đổi bố cục để KHÔNG có tay (đặt vật lên bàn, không thấy tay — `no hands in frame`) hoặc tay ở xa/bị che một phần (`hands partially out of frame / hidden`).
Kiểm bắt buộc bản quyền và thương hiệu ở MỌI ảnh (kể cả khi prompt và provenance trông vô hại): soi logo, nhãn/nhãn hiệu trên chai lọ thuốc hoặc bao bì, chữ thương hiệu, khuôn mặt người thật dễ nhận ra, nhân vật hoạt hình/phim có bản quyền. Nếu thấy bất kỳ dấu hiệu nào, ghi `style_rights` kèm mô tả rõ thấy gì vào `style_issues` và `reject` (không được `select`); `new_prompt` phải đổi bố cục để loại bỏ hoàn toàn (chai lọ nhãn trống `blank unbranded label`, bỏ vật có nhãn, tránh khuôn mặt người thật).
Kiểm và chọn tư thế mascot theo bảng 9 tư thế mục 2 (`welcome`, `explain`, `point_up`, `thinking`, `surprised`, `caution`, `myth_bust`, `blank_board`, `thumbs_up`) khớp đúng ý lời đọc.
Kiểm contact sheet: video dài 16:9 không có phụ đề cháy cứng (không trừ điểm vì thiếu phụ đề); 9:16 giữ phụ đề, cho highlight từ/cụm khi có timing và không đè ảnh/nhãn/mascot, nhãn đọc được ở 720p, không bị cắt; zoom y khoa dùng kính lúp mục 3b (không cross-fade chồng mờ).
Không sửa script, storyboard, manifest, candidate index, ảnh hoặc approval.

Ghi `reviews/visual-review.yaml`:
Tuân thủ quy tắc ghi tệp UTF-8 chung: dùng Write/Edit/apply_patch hoặc tệp Python UTF-8 chạy trực tiếp. Cấm Set-Content/Out-File/redirect và here-string chứa tiếng Việt pipe vào Python; `encoding='utf-8'` ở đầu ra không cứu được dữ liệu đã hỏng trong pipe.
```yaml
candidate_index_sha256: "sha256 của candidates.yaml vừa đọc"
inspected_images: ["đường dẫn tương đối mọi ảnh đã mở, gồm contact sheet"]
scenes:
  - scene: S01
    decision: select # hoặc reject
    selected: reviews/visual/asset-00/round-0/candidate-2.png # null nếu reject
    mascot_pose: explain # tư thế mascot mục 2 (tùy chọn nếu cảnh có mascot)
    reason: "Nêu bộ phận nhìn thấy và liên hệ trực tiếp với lời thoại"
    layout_issues: [] # mô tả vấn đề bố cục nhìn thấy, nếu có
    style_issues: [] # mã lệch phong cách: style_palette, style_typography, style_mascot_pose, style_stroke, style_medical_art, style_caption, style_zoom, style_hands, style_rights (kèm ": mô tả" nếu cần)
    new_prompt: null # reject: prompt mới cụ thể bằng tiếng Anh, no text
```
Chỉ quyết định các asset chưa có `selected` hoặc `fallback`; vòng sau chỉ mở ảnh mới của asset còn chờ và contact sheet làm ngữ cảnh. Cảnh đã chọn giữ nguyên, không chấm lại. Báo cáo có thể chỉ gồm cảnh còn chờ; Python giữ quyết định cũ. Không nêu lỗi mới ở cảnh không đổi, trừ an toàn y khoa nghiêm trọng ghi `blocking_safety: true` và lý do, dừng chờ bác sĩ. Cảnh dùng chung ảnh phải chọn giống nhau.
Nếu cả ba ảnh sai chủ đề: reject và prompt mới; không chọn ảnh sai cho xong.
D4 hình tối đa 3 lần chấm/revision (đầu + hai lần sửa). Cùng issue mở hai lần dừng sớm; hết vòng dừng, giữ chưa đạt và trình brief/bằng chứng qua coordinator cho bác sĩ, không tự submit gate. Thiếu hình/mapping/quyền trả storyboard_director/medical_expert, không tự vẽ cơ quan fallback hoặc chọn ảnh sai.
Không tự chạy lại GPU, không đổi trạng thái workflow; Python sẽ áp dụng báo cáo và dựng lại.
Các vấn đề bố cục vẫn phải ghi để bác sĩ xem; không tự duyệt cổng y khoa hay video.
Xong khi báo cáo chứa đầy đủ quyết định và danh sách ảnh đã thực sự xem.

R5: cơ chế dùng Servier/NIAID/DBCLS/Reactome có phép + vector Remotion, không FLUX, không tự vẽ cơ thể/cơ quan thay hình có sẵn. Mascot có sẵn chỉ câu chốt, vắng giải phẫu cận. Kiểm pixel thực, cấu trúc/quyền/SHA/chuyển tầng có anchor; không chấm âm thanh bằng ảnh. Thiếu ảnh hoặc công cụ xem thì báo coordinator, không nhận đã xem.
Budget bền revision/stage/issue_id/fingerprint qua restart/failover/hash/rerender/reset submitted; không tự tạo revision để reset, chỉ bác sĩ yêu cầu nội dung/phạm vi mới rõ mới có budget mới. Độc lập storyboard_director cả fallback/session, không gộp ba khâu chấm; sau vòng đầu kiểm diff/ảnh hưởng, vẫn báo nguy cơ an toàn mới.

Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.
