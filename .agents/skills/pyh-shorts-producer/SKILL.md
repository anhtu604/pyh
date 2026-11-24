---
name: pyh-shorts-producer
description: Use when PYH shorts_plan designs standalone or extracted 9:16 vertical Shorts/Reels/TikTok plans (45-90s hooks, loop bridges, safe zones) in posts/shorts-plan.yaml.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Script/claim và cảnh ứng viên, nội dung cổng y khoa bao phủ, plan hiện có.
output: Cut range, hook/payoff/caveat duy nhất gửi storyboard_director trước khóa; posts/shorts-plan.yaml đúng schema.
done_when: Clip đứng độc lập, lời nằm trong script đã qua cổng; giữ caveat, kiểm bố cục dọc có phụ đề.
missing_data_to: writer/medical_expert nếu cần lời mới qua cổng y khoa; coordinator mở lại đúng luồng nếu plan đã khóa; copywriter chỉ đóng gói.
```


# Nhà sản xuất Shorts & Reels PYH (`shorts_producer`)

## Đầu vào
- Đọc `project.yaml` lấy `active_revision`; đọc `revisions/<rev>/script/script.yaml`, `script/outline.yaml`, `storyboard/storyboard.yaml`, `script/clip-plan.yaml` (nếu có), `evidence/ledger.yaml`, `reviews/medical-approval.yaml`, và `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` (mục 4 & 6, Trạm 15).
- Đọc `topics/channel-insights.yaml` (nếu có) để nắm mẫu hook 0–2 giây đầu và điểm giữ chân hiệu quả của kênh.

## Phán đoán công việc
- Khi có nhiều đoạn ứng viên, dùng tiêu chí từ [OpenMontage Clip Factory](https://github.com/OpenMontageInc/OpenMontage/blob/main/pipeline_defs/clip-factory.yaml). Đọc mỗi đoạn như một video độc lập. Loại đoạn bắt đầu hoặc kết thúc giữa câu, cần cảnh trước mới hiểu, hoặc thiếu điều kiện áp dụng và cảnh báo y khoa. Trong số đoạn còn lại, ưu tiên đoạn vào ý sớm và trả lời trọn câu mở đầu.
- Thiết kế từ 1–4 kịch bản clip dọc 9:16 (`target_seconds` **45–90 giây**, khuyến nghị **60–90 giây** khi ánh xạ sang `clip-plan.yaml`) theo **Chuẩn phong cách PYH — Hướng A (9:16)**, có thể đứng độc lập hoàn chỉnh cho YouTube Shorts, TikTok và Facebook Reels:
  - **Hook 0–2 giây đầu (`hook_text`, `hook_window_seconds <= 2.0`)**: nêu ngay câu hỏi gắt hoặc hiểu lầm đời thường có trong nội dung đã duyệt y khoa trong 2 giây đầu; KHÔNG giật tít hứa chữa khỏi, KHÔNG phóng đại.
  - **Mascot 9:16 (`mascot_max_width_percent <= 28`)**: mascot có sẵn chỉ ở câu chốt, vắng giải phẫu cận; khi có, chiếm tối đa **28% chiều rộng** khung hình 9:16, không che sơ đồ cơ chế hay phụ đề.
  - **Phụ đề giữa dưới & An toàn hiển thị 9:16 (`subtitle_position: bottom_center`, `safe_zone_checked: true`)**: phụ đề đặt ở **giữa dưới** (1–2 dòng, `<= 24` ký tự/dòng, highlight theo từ/cụm nếu có timing Whisper); phụ đề và nhãn chính tránh 15% đỉnh, 22% đáy (mô tả/caption) và cột nút phải (`~100–120px` trên khung 1080×1920).
  - **Cấu trúc giữ chân & Loop**: chọn đúng dải `start_scene_id`..`end_scene_id` (hoặc toàn bộ bài nếu dự án vốn là Shorts ngắn), thiết kế `loop_bridge` nối mượt cuối clip về câu mở đầu khi phù hợp.
  - **Caveat y khoa**: mọi clip đều giữ đủ điều kiện áp dụng/giới hạn an toàn (`safety_caveat`), không cắt bỏ phần cảnh báo quan trọng chỉ để câu view.
- Không tự sửa kịch bản gốc đã duyệt y khoa; không tự xuất bản. Kế hoạch chỉ là đề xuất đến khi ánh xạ vào `clip-plan.yaml` và QA file xuất thực tế; không nhận hook/loop đã được render khi chưa có output thực.

## Đầu ra & Lệnh
- Ghi file tạm YAML bằng Python `encoding="utf-8"` đúng schema `ShortsPlan` rồi xác nhận bằng:
  `healthvideo step shorts-plan {project} --file <tmp_shorts_plan.yaml>`
- Xong khi lệnh thoát mã `0` và `revisions/<rev>/posts/shorts-plan.yaml` hợp lệ.

## Quyền sở hữu R5 và thiếu dữ liệu
- shorts_producer là chủ sở hữu duy nhất cut range/hook/payoff/caveat trước khóa; gửi range và line/claim IDs cho storyboard_director hiện thực clip-plan/layout 9:16. Copywriter chỉ đóng gói title/caption, không tạo kịch bản clip cạnh tranh.
- Lời clip, hook/payoff/caveat phải nằm trong script đã qua cổng y khoa; không viết voiceover mới từ ledger rồi coi là đã duyệt. Trước cổng chỉ chọn ứng viên từ script để đưa cả range vào gói duyệt; chưa nhận đã qua cổng. Thiếu đoạn tự đứng vững trả writer/medical_expert bổ sung qua cổng, không cắt mất caveat.
- Không crop mù video ngang. 16:9 không phụ đề cháy chữ; 9:16 giữ phụ đề/highlight đúng timing. Không FLUX cơ chế hay tự vẽ cơ thể/cơ quan thay hình có phép; mascot chỉ câu chốt, vắng khung giải phẫu cận.
- Thiếu range/claim/approval hoặc plan đã khóa cần đổi: báo coordinator mở lại đúng luồng. Validator cũ ép subject/range ngược nội dung thì báo lỗi, không đổi cơ quan để đủ quota. Không ghi đè clip-plan đã khóa; schema ShortsPlan có caption chỉ là nhãn biên tập, caption xuất bản do copywriter sở hữu.
