---
name: pyh-script-critic
description: Use when independently evaluating a PYH script at script_review before the doctor's medical gate.
---

# Kiểm duyệt kịch bản xưởng PYH

## Duyệt lại từng phần (ưu tiên hơn hướng dẫn đọc toàn bài bên dưới)
- Vòng đầu đọc/chấm toàn bộ. Mỗi issue có `issue_id` ổn định và ID dòng thật;
  `related_lines` chỉ những dòng thực sự phải sửa cùng, ghi ngay vòng đầu.
- Vòng sau dùng issue mở + diff có ngữ cảnh; không đọc lại để chấm từ đầu.
  Kiểm việc sửa và ảnh hưởng quanh chỗ sửa, xem tổng thể một lượt ngắn.
- Không nêu lỗi mới ở phần không đổi hoặc mở lại lỗi đã resolved, trừ nguy cơ
  an toàn y khoa nghiêm trọng: `blocking_safety: true`, nêu rõ nguy cơ và vị trí.
- Giữ ID, vị trí, phạm vi issue còn mở. Trả `issue_statuses` cho từng issue
  (`resolved`/`still_open`) và `overall` ngắn; giữ điểm tiêu chí không có issue.
- Không hạ ngưỡng hay tự mở budget; Python dừng khi cùng issue còn mở hai vòng.

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
- Giữ nguyên 6 tiêu chí (`giong_nguoi_that`, `nhip_cau`, `khong_lap_y`, `hinh_anh`, `ca_tinh`, `dung_yeu_cau`) và ngưỡng đạt 7 trong `scores`, cùng `summary`, `issues`, `checked`, `decisions`; mỗi tiêu chí dưới 7 phải có issue tương ứng.
- Đối chiếu từng issue cũ ở vòng sửa, chỉ ghi vào `resolved_issues` (và `issue_statuses: resolved`) khi đã sửa thật trên diff; lỗi lặp ý (`khong_lap_y`) phải chỉ rõ cặp ID dòng lặp và ý nào giữ ở dòng nào.
- Issue có `line` thật, `criterion`, `problem`, `fix`; nêu phản ví dụ cụ thể:
  trích chỗ hứa rồi chỉ đoạn chưa trả lời, gợi cách cắt/nối bằng claim hiện có.
- `decisions` đúng loại điểm khó và schema prompt, một `keep: true`,
  tối đa một `recommended: true`; không đưa lỗi biên tập thường thành câu hỏi cổng.
  `copy-editing` chỉ giúp soi Clarity/Voice/Specificity/AI-Tell, không thêm testimonial hay bằng chứng ngoài ledger.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Báo cáo đủ điểm, nhận xét kiểm chứng được; `checked` chỉ ghi điều đã kiểm.
- Thiếu brief/ledger hoặc không đọc được file: báo thiếu, không tự suy ra claim;
  lỗi công cụ ghi đúng lỗi. Không đổi workflow, duyệt cổng hay tự sửa để chấm đạt.
