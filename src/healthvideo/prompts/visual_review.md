# Kiểm trực quan sau bản render ứng viên
Project: {project}
Chủ đề: {title}. Câu hỏi: {question}
Ghi chú bác sĩ: {doctor_note}

Mục tiêu: xem thật mọi ảnh ứng viên và contact sheet trước khi Python dựng bản cuối.
Đọc project.yaml để xác định revision; chỉ ghi trong revision này.
Đọc `reviews/visual/candidates.yaml`, storyboard và lời thoại đã duyệt.
Dùng công cụ xem ảnh để mở TỪNG candidate và MỌI `contact_sheets[].path` trong index.
Không suy đoán nội dung ảnh từ tên file hay prompt. Ghi trung thực những gì đã xem.
Kiểm ảnh có đúng bộ phận/bệnh trong lời thoại; không có chữ AI, vật thể lạ hoặc ẩn dụ khó hiểu.
Kiểm contact sheet: chữ có dải riêng, không đè ảnh, nhãn đọc được và không bị cắt.
Không sửa script, storyboard, manifest, candidate index, ảnh hoặc approval.

Ghi `reviews/visual-review.yaml`:
```yaml
candidate_index_sha256: "sha256 của candidates.yaml vừa đọc"
inspected_images: ["đường dẫn tương đối mọi ảnh đã mở, gồm contact sheet"]
scenes:
  - scene: S01
    decision: select # hoặc reject
    selected: reviews/visual/asset-00/round-0/candidate-2.png # null nếu reject
    reason: "Nêu bộ phận nhìn thấy và liên hệ trực tiếp với lời thoại"
    layout_issues: [] # mô tả vấn đề thật nhìn thấy, nếu có
    new_prompt: null # reject: prompt mới cụ thể bằng tiếng Anh, no text
```
Mỗi cảnh trong index cần đúng một quyết định; cảnh dùng chung ảnh phải chọn giống nhau.
Nếu cả ba ảnh sai chủ đề: reject và prompt mới; không chọn ảnh sai cho xong.
Python sẽ sinh lại tối đa hai vòng; sau đó dùng SVG tổng quan đúng chủ đề.
Không tự chạy lại GPU, không đổi trạng thái workflow; Python sẽ áp dụng báo cáo và dựng lại.
Các vấn đề bố cục vẫn phải ghi để bác sĩ xem; không tự duyệt cổng y khoa hay video.
Xong khi báo cáo chứa đầy đủ quyết định và danh sách ảnh đã thực sự xem.
