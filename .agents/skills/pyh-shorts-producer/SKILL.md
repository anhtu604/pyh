---
name: pyh-shorts-producer
description: Use when PYH shorts_plan designs standalone or extracted 9:16 vertical Shorts/Reels/TikTok plans (45-90s hooks, loop bridges, safe zones) in posts/shorts-plan.yaml.
---

# Nhà sản xuất Shorts & Reels PYH (`shorts_producer`)

## Đầu vào
- Đọc `project.yaml` lấy `active_revision`; đọc `revisions/<rev>/script/script.yaml`, `script/outline.yaml`, `storyboard/storyboard.yaml`, `script/clip-plan.yaml` (nếu có), `evidence/ledger.yaml`, `reviews/medical-approval.yaml`, và `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` (mục 4 & 6, Trạm 15).
- Đọc `topics/channel-insights.yaml` (nếu có) để nắm mẫu hook 0–2 giây đầu và điểm giữ chân hiệu quả của kênh.

## Phán đoán công việc
- Khi có nhiều đoạn ứng viên, dùng tiêu chí từ [OpenMontage Clip Factory](https://github.com/OpenMontageInc/OpenMontage/blob/main/pipeline_defs/clip-factory.yaml). Đọc mỗi đoạn như một video độc lập. Loại đoạn bắt đầu hoặc kết thúc giữa câu, cần cảnh trước mới hiểu, hoặc thiếu điều kiện áp dụng và cảnh báo y khoa. Trong số đoạn còn lại, ưu tiên đoạn vào ý sớm và trả lời trọn câu mở đầu.
- Thiết kế từ 1–4 kịch bản clip dọc 9:16 (`target_seconds` **45–90 giây**) theo **Chuẩn phong cách PYH — Hướng A (9:16)**, có thể đứng độc lập hoàn chỉnh cho YouTube Shorts, TikTok và Facebook Reels:
  - **Hook 0–2 giây đầu (`hook_text`, `hook_window_seconds <= 2.0`)**: nêu ngay câu hỏi gắt hoặc hiểu lầm đời thường có trong nội dung đã duyệt y khoa trong 2 giây đầu; KHÔNG giật tít hứa chữa khỏi, KHÔNG phóng đại.
  - **Mascot 9:16 (`mascot_max_width_percent <= 28`)**: mascot nhỏ gọn, chiếm tối đa **28% chiều rộng** khung hình 9:16, không che sơ đồ cơ chế hay phụ đề.
  - **Phụ đề giữa dưới & An toàn hiển thị 9:16 (`subtitle_position: bottom_center`, `safe_zone_checked: true`)**: phụ đề tĩnh theo trang đặt ở **giữa dưới** (1–2 dòng, `<= 24` ký tự/dòng, không tô sáng từng chữ); phụ đề và nhãn chính tránh 15% đỉnh và 22% đáy (khu vực nút Like/Share/Caption của TikTok/Reels/Shorts).
  - **Cấu trúc giữ chân & Loop**: chọn đúng dải `start_scene_id`..`end_scene_id` (hoặc toàn bộ bài nếu dự án vốn là Shorts ngắn), thiết kế `loop_bridge` nối mượt cuối clip về câu mở đầu khi phù hợp.
  - **Caveat y khoa**: mọi clip đều giữ đủ điều kiện áp dụng/giới hạn an toàn (`safety_caveat`), không cắt bỏ phần cảnh báo quan trọng chỉ để câu view.
- Không tự sửa kịch bản gốc đã duyệt y khoa; không tự xuất bản.

## Đầu ra & Lệnh
- Ghi file tạm YAML theo schema `ShortsPlan` rồi xác nhận bằng:
  `healthvideo step shorts-plan {project} --file <tmp_shorts_plan.yaml>`
- Xong khi lệnh thoát mã `0` và `revisions/<rev>/posts/shorts-plan.yaml` hợp lệ.
