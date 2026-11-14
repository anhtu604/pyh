---
name: pyh-script-critic
description: Use when independently evaluating a PYH script at script_review before the doctor's medical gate.
---

# Kiểm duyệt kịch bản xưởng PYH

## Đầu vào
- Đọc prompt `script_review.md`, doctor_note/reject_note và `active_revision`
  từ `{project}/project.yaml`; đọc toàn bộ `revisions/<rev>/script/script.yaml`.
- Đối chiếu `evidence/ledger.yaml`, `evidence/expert-brief.md`,
  `reviews/style-lint.json` cùng revision, không chấm dựa bản cũ.
- Đọc `script/outline.yaml`: `title` giữ lời hứa, `chapters[].goal` giữ
  tiến triển/payoff/CTA; khán giả/intent/câu hỏi ở expert brief. Đối chiếu
  script thực trả được gì, không phụ thuộc scratch của writer.
- Đọc `profiles/doctor-feedback.yaml` mục `slug: chung`; chuẩn mới tại
  `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`
  ưu tiên về funnel/CTA, không ép hài, ẩn dụ hay cú twist khi không hợp.

## Phán đoán công việc
- Đúng y khoa chưa đủ hay: người xem nào, lời hứa gì, điều mới nào,
  phần nào trả lời được lời hứa, CTA có hợp ý định không? Ánh xạ vào sáu key sẵn.
- `giong_nguoi_that`: nói được thành tiếng, rõ với audience; không đọc nguồn,
  phương pháp, năm/cơ quan hay ngôn ngữ quản trị bằng chứng vào lời đọc.
- `nhip_cau`: nhịp câu và chuỗi phát hiện/hệ quả dẫn tới payoff, không giậm chân,
  không lặp khuôn nêu ý → rào lại → đi khám. Hook phải được nội dung trả lời.
- `khong_lap_y`: mỗi đoạn thêm ý; chỉ rõ đoạn định nghĩa/danh sách có thể cắt
  mà không mất đáp án, không bắt nhắc lại ý khó chỉ vì skill ngoài khuyên vậy.
- `hinh_anh`: ví dụ/hình dung giúp hiểu điểm đáng nghe; không thưởng ẩn dụ
  khó hiểu hay trừ điểm chỉ vì không nhân hóa khi không cần.
- `ca_tinh`: góc nhìn sắc và ấm, không sáo rỗng/giật gân; không ép đùa hoặc twist.
  Không châm biếm người bệnh, không tự bịa retention hay bảo đảm viral.
- `dung_yeu_cau`: audience, intent, promise, payoff, CTA và ghi chú bác sĩ khớp;
  không nói quá brief/ledger, giữ câu kết chuẩn chưa được thay.
- TOFU gợi khám phá; MOFU gỡ hiểu lầm/cân lựa chọn; BOFU thực hành, khám khi cần,
  tin/theo dõi kênh. Một tầng chính, có thể chạm tầng khác có chủ đích;
  không đòi đủ ba tầng hay bắt CTA thuốc/khám ở mọi video.

## Đầu ra
- Chỉ ghi `revisions/<rev>/reviews/script-review.yaml`, không sửa script.
- Giữ `scores` sáu key trên, `summary`, `issues`, `checked`, `decisions`;
  điểm 1–10 theo prompt; mỗi tiêu chí dưới 7 phải có issue tương ứng.
- Issue có `line` thật, `criterion`, `problem`, `fix`; nêu phản ví dụ cụ thể:
  trích chỗ hứa rồi chỉ đoạn chưa trả lời, gợi cách cắt/nối bằng claim hiện có.
- `decisions` đúng loại điểm khó và schema prompt, một `keep: true`,
  tối đa một `recommended: true`; không đưa lỗi biên tập thường thành câu hỏi cổng.
  `copy-editing` chỉ giúp soi lỗi, không thêm testimonial hay bằng chứng marketing.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Báo cáo đủ điểm, nhận xét kiểm chứng được; `checked` chỉ ghi điều đã kiểm.
- Thiếu brief/ledger hoặc không đọc được file: báo thiếu, không tự suy ra claim;
  lỗi công cụ ghi đúng lỗi. Không đổi workflow, duyệt cổng hay tự sửa để chấm đạt.
