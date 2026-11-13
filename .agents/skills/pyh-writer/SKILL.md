---
name: pyh-writer
description: Quy tắc viết và sửa kịch bản cho Biên kịch viral (draft, revise_medical) theo 10 nguyên tắc của bác sĩ và chuẩn bố cục xưởng PYH.
---

# Biên kịch viral xưởng PYH

## 10 nguyên tắc viết kịch bản của bác sĩ (bắt buộc)
Trước khi viết hoặc sửa, đọc mục `slug: chung` mới nhất (ngày `2026-11-12`) trong `profiles/doctor-feedback.yaml`. Tóm tắt 10 nguyên tắc phải bám:
1. **Cấu trúc phễu TOFU – MOFU – BOFU**: TOFU mở bằng nỗi đau thật của người bệnh và câu người xung quanh hay hỏi, pha chút hài đời thường trong 3 giây đầu; MOFU giải thích cơ chế; BOFU kết bằng việc người xem làm được ngay.
2. **Một ẩn dụ xuyên suốt & nhân hóa cơ chế**: giữ một ẩn dụ đời thường xuyên suốt (như cốc nước đường) và nhân hóa cơ chế (đội bảo vệ, chuông báo cháy, dân phòng dập lửa…); giữ mạch kể tới cuối bài, không để lời đọc thành sách giáo khoa.
3. **Thuật ngữ chuyên môn để trên màn hình**: tên phân tử, cytokine, tên cơ chế chỉ hiện chữ nhỏ trên màn hình (`on_screen_text`, `LABELS`, `kinetic_term`), lời đọc dùng tiếng Việt đời thường; cấm từ dịch sát tiếng Anh (như "chết theo chương trình").
4. **Mỗi dòng thêm một ý mới**: không có dòng tóm tắt lại 2–3 dòng trước, không hai dòng cùng một ý (cắt/gộp thẳng tay khi biên tập lại).
5. **Không đọc nguồn trong lời thoại**: cấm đọc tên nguồn, phương pháp nghiên cứu (`in vitro`…), năm xuất bản hay tên cơ quan vào lời đọc; nguồn để trên `source_card`/chữ nhỏ màn hình và phần mô tả/bình luận ghim (bằng chứng vẫn đủ trong ledger). Ở nhịp bằng chứng, kể tác động thực tế lên người bệnh, không đọc mục lục tài liệu.
6. **Cú bẻ lái phá hiểu lầm**: giữ ít nhất một cú bẻ lái phá ngộ nhận phổ biến ở giữa video dựa trên `expert-brief.md`.
7. **Nối ý từ hệ quả, bỏ rào đón**: khái niệm mới phải nối từ hệ quả của ý trước, không đưa vào đột ngột; câu chữ gãy gọn, cắt đuôi rào đón học thuật.
8. **Callback mở đầu**: gần cuối quay lại câu hỏi mở đầu, kết luận cân bằng, không đổ hết tội cho một nguyên nhân.
9. **BOFU có lực đẩy**: một câu người xem nên hỏi bác sĩ khi đi khám, một lời kêu gọi cụ thể (lưu video, bình luận chỉ số của mình), nhắc dùng thuốc phải có bác sĩ khám — không kết bằng câu miễn trừ khô cứng.
10. **Câu kết cố định của kênh**: dùng nguyên văn câu kết chuẩn ở mục `slug: chung` trong `profiles/doctor-feedback.yaml`.

## Điều chỉnh skill đi kèm & phòng lỗi dựng
- **`youtube-scriptwriting`**: bỏ qua bước tự tìm nguồn mới (thiếu ý ghi `script/questions.yaml`) và thay mẫu kết "Binge Loop mở vấn đề mới" bằng nguyên tắc 8–10 ở trên.
- **`short-form-video`**: áp dụng nhịp hook–giữ chân cho `clip-plan.yaml` (cắt từ cảnh có sẵn 60–180 giây kèm đủ caveat); không tự tạo project Remotion riêng hay chạy `npx remotion render`.
- **Cân bố cục trước khi chạy `step draft`**: giữ tỷ lệ `chart_crop` an toàn quanh 16–24% (tránh sát mép 15% và 25%), đặt `beats` nằm gọn trong thời lượng ước tính của lời thoại, tách ý `whiteboard` bằng dấu `;` để không dồn đầu cảnh, và đảm bảo mỗi clip dọc ước tính đủ 60–180 giây.
