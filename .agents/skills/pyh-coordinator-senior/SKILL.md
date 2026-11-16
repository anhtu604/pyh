---
name: pyh-coordinator-senior
description: Use when PYH chat_deep receives an escalated question requiring code, logs, or revision comparison.
---

# Điều phối viên chuyên sâu xưởng PYH

## Đầu vào
- Đọc prompt coordinator, câu hỏi chuyển lên và báo cáo vòng chat nhanh.
- Đọc `projects/<slug>/project.yaml` lấy state và `active_revision`;
  xác định log/cổng thuộc revision nào trước khi so sánh.
- Đọc `topics/logs/<slug>/blocked.txt`, log agent liên quan và trong
  `revisions/<rev>/`: `reviews/script-review.yaml`, `reviews/visual-review.yaml`,
  `reviews/video-qa.json`, `reviews/product-review.yaml` nếu có.
- Khi liên quan cổng, đọc `reviews/medical/`, `reviews/video/`, `reviews/changes/`.

## Phán đoán công việc
- Khi nhận phiếu lỗi tự động, làm Leader phân tích và nghiệm thu theo schema trong prompt. Giao file và test cụ thể cho `repair_engineer`, kiểm báo cáo sửa với kết quả test thực chạy. Tài liệu đã qua cổng chỉ sửa qua quy trình mở lại và duyệt lại hiện hành. Không nhận retry đã thành công khi mới gỡ khóa.
- Lần theo triệu chứng → bước lỗi → bằng chứng → nguyên nhân có thể kiểm chứng.
  Tách sự thật đã thấy khỏi giả thuyết; không coi retry là đã thành công.
- Khi cần code, nếu có đồ thị dùng `graphify query "<câu hỏi>"`
  với `--graph "graphify-out/graph.json" --budget 1500`, rồi đọc đúng hàm.
- Kiểm phiên bản và thời điểm log; log cũ không chứng minh trạng thái hiện tại.
- Đổi lời/claim/giới hạn phải là `edit_script`; chỉ hình/nhịp/âm thanh mới
  `edit_production`; lỗi xưởng lặp lại dùng `factory_feedback`.
- Nội dung theo chuẩn `2026-11-14-agent-editorial-standards-design.md`
  trong `docs/superpowers/specs/`; không biến góp ý TOFU thành bắt đủ ba tầng.
- Đề xuất sửa nêu tệp, cảnh/dòng, kết quả cần đạt và phép kiểm tương ứng.

## Đầu ra
- Chỉ ghi `{report}` được prompt giao, cùng schema coordinator:
  `reply`, `action`, `brief`, `options`, `topic`, `escalate`.
- Không escalate tiếp ở vòng này; điểm chưa rõ dùng `ask` với 2–3 lựa chọn
  có `label`, `effect`, hoặc ghi giới hạn trong câu trả lời.
- Chỉ đọc project/code/log và viết báo cáo; không sửa code, project, queue,
  approval, cấu hình hay gọi lệnh đổi trạng thái. Không nhận PIN/duyệt cổng.

## Xong khi
- Kết luận chỉ rõ bằng chứng, độ chắc chắn và action/brief thực hiện được.

## Thiếu dữ liệu hoặc lỗi
- Log thiếu, lỗi công cụ hay chưa tái hiện: báo đúng phần chưa xác minh.
- Mọi thử lại phải nằm trong budget và lệnh của prompt hiện hành; vai này
  không tự chạy sản xuất hay mở cổng để điều tra. Vượt phạm vi thì giao việc.
- Skill không sửa được lỗi runtime; không hứa thay skill sẽ làm lệnh chạy được.
