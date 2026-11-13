---
name: pyh-scout
description: Cách chọn và kiểm tra chủ đề cho kênh y khoa tiếng Việt trước khi đưa vào hàng đợi xưởng PYH.
---

# Trinh sát chủ đề xưởng PYH

## Chắt lọc từ `content-strategy`
- Chỉ áp dụng tư duy **searchable** (câu hỏi người bệnh hay tìm kiếm) + **shareable** (hiểu lầm phổ biến có cú lật nhận thức khi giải thích cơ chế) và bảng chấm điểm ưu tiên.
- **Bỏ qua** các phần SaaS/marketing trong `content-strategy` (phễu `pricing/demo/buy`, chiến dịch backlink blog, lịch bán hàng).

## Cách làm việc
1. **Kiểm tra trùng lặp trước**: chạy `healthvideo topic list`, đọc `topics/queue.yaml` và thư mục `projects/` để tránh trùng `slug` hoặc lặp lại câu hỏi đã làm.
2. **Dò tín hiệu trung thực**: khi dùng `healthvideo topic discover --query "<truy vấn>"`, đọc `topics/discovered/<YYYY-MM-DD>.yaml`, báo rõ nguồn nào có tín hiệu và nguồn nào lỗi (`failures`); tuyệt đối không gắn nhãn "đang nóng" khi không có dữ liệu nhiệt.
3. **Tiêu chí lọc chủ đề phù hợp xưởng**:
   - Xuất phát từ triệu chứng, thói quen hoặc câu hỏi đời thường người Việt hay gặp.
   - Giải thích được theo mạch cơ chế bình thường → bệnh lý và có guideline hoặc tổng quan hệ thống trên Europe PMC / PubMed.
   - Đặt câu hỏi trung lập, không hứa chữa khỏi hay thay thế chẩn đoán cá nhân.
