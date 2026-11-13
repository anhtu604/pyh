---
name: pyh-feedback-analyst
description: Quy trình truy vết gốc lỗi và phân loại việc san_pham / xuong / chuan_kenh cho Phân tích ý kiến (feedback_inbox).
---

# Phân tích ý kiến xưởng PYH

## Cách làm việc
1. **Định vị nhanh trong kho mã**: khi cần xác định vị trí code liên quan tới lỗi bác sĩ nêu, hỏi đồ thị trước bằng `graphify query "<từ khóa>" --graph "graphify-out/graph.json" --budget 1500` (nếu có file đồ thị) thay vì đọc dò nhiều file.
2. **Ánh xạ triệu chứng → `kind` và `target` chuẩn**:
   - Lỗi nội dung hoặc hình riêng của một chủ đề → `san_pham` (trỏ file trong `projects/<slug>/revisions/<rev>/` hoặc component giải phẫu riêng của chủ đề).
   - Lỗi có tính lặp lại từ prompt, bộ kiểm hay giao diện → `xuong` (vd: `src/healthvideo/domain/script_style.py`, `domain/visual_budget.py`, `render/beats.py`, `profiles/pronunciation.vi.yaml`, `src/healthvideo/prompts/*.md`); nếu bác sĩ nêu qua một project cụ thể, tách rõ việc sửa sản phẩm đó và việc chặn gốc ở xưởng.
   - Quy tắc biên tập/thẩm mỹ lâu dài cho mọi video mới (sau khi đã kiểm `profiles/doctor-feedback.yaml` để không trùng) → `chuan_kenh`.
3. **Định nghĩa `done_when` kiểm chứng được**: nêu dấu hiệu đo được rõ ràng (test chạy đạt, rule lint mới bắt được trường hợp lỗi, trường hoặc quy tắc xuất hiện đúng chỗ), tránh tiêu chí chung chung khó nghiệm thu.
