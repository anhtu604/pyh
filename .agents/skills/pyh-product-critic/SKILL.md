---
name: pyh-product-critic
description: Quy trình kiểm định sản phẩm cuối qua contact sheet, timing, QA và bài đăng cho Kiểm định sản phẩm (product_review).
---

# Kiểm định sản phẩm xưởng PYH

## Ghi đè từ `character-animation-qa`
- Không mở Playwright/trình duyệt và không chạy script ngoài; lấy khung hình bằng `healthvideo step review-frames`, đọc `index.json` rồi mở xem trực tiếp toàn bộ contact sheet.

## Quy trình đối chiếu 4 nguồn
1. **Contact sheet ↔ `renders/scene-timing.json` & `storyboard.yaml`**: kiểm cảnh mở đầu có chuyển động ngay không; phát hiện đoạn giữ một hình đứng yên quá 6 giây (`nhip_dung`); đối chiếu hình giải phẫu/biểu đồ có khớp đúng câu đang đọc không (`hinh_khop_loi`); kiểm nhãn tiếng Việt và phụ đề có chồng lấn, tràn mép hay quá nhỏ không (`hinh_ro`).
2. **`reviews/video-qa.json` & `profiles/pronunciation.vi.yaml`**: kiểm tra lỗi kỹ thuật tự động và rà mọi thuật ngữ tiếng Anh/Latin/viết tắt trong `script.yaml` xem đã có phiên âm trong `pronunciation.vi.yaml` chưa (`am_thanh_phu_de`).
3. **Mở và kết (`mo_ket`)**: kiểm hook khung đầu cuốn hút và thẻ nhận diện/câu kết cuối video rõ ràng.
4. **`posts/posts.yaml` (`bai_dang`)**: đối chiếu tiêu đề, chương, nguồn, caption clip dọc và `thumbnail` có khớp nội dung đã duyệt và tránh hứa hẹn quá đà không.

## Phân loại `fixable` chính xác
- `fixable: true`: chỉ khi sửa trọn vẹn được trong `video/src/anatomy/` hoặc `posts/posts.yaml`.
- `fixable: false`: khi gốc lỗi nằm ở lời đọc, thứ tự/thời lượng cảnh, ảnh FLUX hoặc `profiles/pronunciation.vi.yaml` (để bác sĩ xem và quyết định mở lại cổng).
