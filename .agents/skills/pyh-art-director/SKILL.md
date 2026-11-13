---
name: pyh-art-director
description: Quy trình kiểm tra ảnh ứng viên FLUX, contact sheet và viết lại prompt tiếng Anh cho Đạo diễn hình (visual_review).
---

# Đạo diễn hình xưởng PYH

## Cách làm việc
1. **Soi từng ảnh ứng viên (`candidate-*.png`)**: đối chiếu trực tiếp với lời thoại cảnh tương ứng — kiểm đúng vị trí giải phẫu (đúng cơ quan/khớp, đúng bên, đúng biểu hiện lâm sàng), giữ đồng nhất phong cách vector y khoa phẳng 2D nền kem ấm (không bóng nhựa 3D, không ảnh chụp gắt), loại ngay ảnh có chữ/số/ký tự giả do AI vẽ, đạo cụ ánh sáng thừa hoặc ẩn dụ khó hiểu.
2. **Soi `contact_sheets`**: kiểm tra vùng chữ (`on_screen_text`, phụ đề, nhãn) tách dải rõ ràng khỏi chủ thể minh họa, đọc tốt ở kích thước nhỏ, không đè lên vùng tổn thương chính và không bị cắt sát mép khung.
3. **Viết `new_prompt` tiếng Anh khi cả 3 seed đều lỗi** (theo `docs/reference/image-prompting.md`):
   - Câu đầu định lượng rõ cỡ cảnh, góc máy, tỉ lệ chủ thể và mép cắt.
   - Chỉ tả hiệu ứng ánh sáng trên bề mặt chủ thể; không gọi tên cửa sổ, bóng đèn hay nguồn sáng.
   - Giữ đúng 1 chủ thể, ngoại hóa triệu chứng qua tư thế cơ thể nhìn thấy được.
   - Chốt bằng câu nhắc lại mép cắt + cụm phong cách phẳng matte + `no text`.
4. **Đồng bộ lựa chọn**: các cảnh dùng chung một asset phải chọn cùng một ảnh ứng viên.
