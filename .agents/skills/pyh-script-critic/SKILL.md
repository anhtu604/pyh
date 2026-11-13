---
name: pyh-script-critic
description: Chuẩn chấm kịch bản cho Kiểm duyệt kịch bản (script_review) đối chiếu theo 10 nguyên tắc của bác sĩ và expert-brief.md.
---

# Kiểm duyệt kịch bản xưởng PYH

## Chấm theo 10 nguyên tắc của bác sĩ (bắt buộc)
Đọc mục `slug: chung` mới nhất (ngày `2026-11-12`) trong `profiles/doctor-feedback.yaml` để soi lỗi nhất quán với người viết, ánh xạ vào 6 tiêu chí chấm:
- **`giong_nguoi_that` & `hinh_anh`** (Nguyên tắc 2, 3, 5): soi nửa sau có bị "sách giáo khoa hóa" không; thuật ngữ phân tử/cơ chế hay từ dịch sát tiếng Anh có lọt vào lời thoại thay vì đặt trên màn hình không; có dòng nào đọc tên nguồn, phương pháp nghiên cứu (`in vitro`), năm xuất bản hay tên cơ quan trong lời đọc không (có thì bắt buộc ghi `issues` yêu cầu bỏ khỏi lời nói, đưa lên màn hình/mô tả).
- **`khong_lap_y`** (Nguyên tắc 4): bắt mọi dòng chỉ tóm tắt lại 2–3 dòng trước hoặc hai dòng liền nhau trùng ý; chỉ rõ dòng cần cắt hoặc gộp trong `fix`.
- **`nhip_cau` & `ca_tinh`** (Nguyên tắc 1, 6, 7, 8): kiểm hook 3 giây đầu có chạm nỗi đau + câu phán xét đời thường + nét hài nhẹ không; có cú bẻ lái phá hiểu lầm giữa bài không; chuyển ý có nối từ hệ quả thay vì đột ngột và có đuôi rào đón học thuật không; gần cuối có callback cân bằng về câu hỏi mở đầu không.
- **`dung_yeu_cau`** (Nguyên tắc 9, 10 + `expert-brief.md`): kiểm BOFU có câu hỏi đi khám + CTA cụ thể + nhắc dùng thuốc phải có bác sĩ khám chưa; có câu kết cố định của kênh chưa; có dòng nào nói quá mức bằng chứng trong `expert-brief.md` không.

## Điều chỉnh từ `copy-editing`
- Dùng *Seven Sweeps* và *AI-Tell Check* để phát hiện lỗi và viết hướng dẫn sửa vào `issues`; **không sửa trực tiếp `script.yaml`**.
- Bỏ qua các loại bằng chứng marketing trong `copy-editing` (testimonial, logo khách hàng, cam kết hoàn tiền); mọi gợi ý trong `fix` và `decisions` chỉ được dựa trên claim có trong `ledger.yaml` và `expert-brief.md`.
