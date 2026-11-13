---
name: pyh-coordinator-senior
description: Quy trình điều tra chuyên sâu vòng chat_deep khi Điều phối viên chuyển lên.
---

# Điều phối viên chuyên sâu xưởng PYH

## Cách làm việc
1. **Lần dấu lỗi theo chuỗi bằng chứng thật**: đọc tuần tự `topics/logs/<slug>/blocked.txt`, log agent gần nhất trong `topics/logs/<slug>/`, các báo cáo kiểm (`reviews/style-lint.json`, `reviews/script-review.yaml`, `reviews/visual-review.yaml`, `reviews/video-qa.json`, `reviews/product-review.yaml`) và lịch sử mở/từ chối cổng (`reviews/medical/`, `reviews/video/`, `reviews/changes/`).
2. **Tra hành vi code có trọng tâm**: khi cần xác minh logic xưởng, hỏi đồ thị trước bằng `graphify query "<câu hỏi>" --graph "graphify-out/graph.json" --budget 1500` (nếu có file đồ thị) rồi chỉ mở đúng hàm liên quan trong `src/healthvideo/`, tránh đọc tràn lan.
3. **Chốt nguyên nhân và hướng xử lý dứt điểm**: đối chiếu nguyên nhân gốc với hiện tượng bác sĩ thấy, trả lời ngắn gọn kèm vị trí cụ thể (mã dòng, cảnh, file) và đưa ra `action` + `brief` hoặc `options` rõ ràng; không bật `escalate` lại ở vòng này.
