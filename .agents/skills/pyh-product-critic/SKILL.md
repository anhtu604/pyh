---
name: pyh-product-critic
description: Use when PYH product_review independently evaluates the final video and posts before the doctor's video gate.
---

# Kiểm định sản phẩm xưởng PYH

## Duyệt lại từng phần (ưu tiên hơn việc đọc toàn bộ bên dưới)
- Vòng đầu kiểm toàn bộ, mỗi issue có `issue_id` ổn định, `at` thật.
  Lỗi sửa được phải có `edits` gồm path tương đối repo, start_line/end_line chính xác.
- Vòng sau chỉ nhận issue mở + diff nguồn; lấy contact sheet hiện hành, kiểm cảnh
  có issue và ngữ cảnh kề, xem tổng thể ngắn. Không suy diễn hình từ source diff.
- Giữ điểm tiêu chí không có issue, ID/vị trí/edits lỗi còn mở. Trả `issue_statuses`
  (`resolved`/`still_open`) cho từng ID và `overall` ngắn. Không mở lại lỗi resolved.
- Chỉ nêu lỗi mới ở phần không đổi khi có nguy cơ y khoa nghiêm trọng,
  ghi `blocking_safety: true` cùng lý do. Không hạ ngưỡng hoặc vượt cổng.

## Đầu vào
- Tự thực hiện lượt kiểm định, chờ các lệnh hoàn tất trước khi ghi báo cáo. Không mở tác vụ nền hay giao agent con cho bước này.
- Đọc prompt `product_review.md`, lấy `active_revision` từ `{project}/project.yaml`.
  Mọi sản phẩm dưới đây thuộc `revisions/<rev>/`.
- Chạy `healthvideo step review-frames {project} --every 4` theo prompt;
  đọc `index.json` và `hook-transitions/index.json` trong thư mục lệnh trả về,
  mở từng contact sheet định kỳ lẫn khung quanh hook (0–3 s) và chuyển cảnh giữa các scene.
- Đối chiếu `script/script.yaml`, `storyboard/storyboard.yaml`,
  `renders/scene-timing.json`, `reviews/video-qa.json`, `posts/posts.yaml` và chuẩn phong cách
  `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`.
- Đọc `profiles/pronunciation.vi.yaml`; không mở Playwright/trình duyệt
  hay chạy script ngoài theo `character-animation-qa`.

## Phán đoán công việc
- `hinh_khop_loi`: hình/nhãn/cơ chế đúng câu ở đúng cảnh và thời điểm.
- `hinh_ro`: đọc được trên khung nhỏ, không chồng/cắt, đủ khoảng thở.
- `nhip_dung`: điểm nhấn đến đúng câu và giúp hiểu, không đòi hiệu ứng máy móc;
  đoạn giữ hình lâu là dấu hiệu cần xem trong ngữ cảnh, không tiêu chí duy nhất.
  Giữ QA/timing hiện hành, không tự bỏ giới hạn 6 giây bằng cách chấm điểm.
- `am_thanh_phu_de`: dựa QA và từ điển; thuật ngữ thiếu phiên âm là nguy cơ,
  không khẳng định đã nghe sai. Contact sheet chỉ xác nhận hình;
  không nhận đã nghe giọng/nhạc hoặc kiểm được toàn bộ chuyển động giữa khung lấy mẫu.
- `mo_ket`: hook và payoff khớp lời hứa; kết nhận diện rõ, CTA theo intent chính.
  TOFU khám phá, MOFU cân hiểu/lựa chọn, BOFU thực hành/khám khi cần/theo dõi;
  không yêu cầu mọi video có đủ ba tầng hay nhắc thuốc.
- `bai_dang`: title/thumbnail/caption hứa đúng phần video trả lời, không hù dọa,
  clickbait, hứa chữa khỏi hoặc thêm claim chưa duyệt.
- `dung_phong_cach_pyh`: chấm theo spec `2026-11-17-pyh-style-a-mascot-host.md` trên contact sheet
  định kỳ + `hook-transitions/` (hook 0–3 s và chuyển cảnh): màu `off_white/navy/teal/yellow/night`
  ≤ 3 màu nổi không đỏ báo động; chữ Be Vietnam Pro đọc rõ 720p; mascot đúng 9 tư thế và đúng nghĩa;
  sơ đồ dựng dần từng beat và zoom kính lúp (không cross-fade chồng mờ); 16:9 không cháy cứng phụ đề;
  9:16 giữ phụ đề trong vùng an toàn (tránh 15% đỉnh, 22% đáy, cột nút phải) và không đè nhãn/mascot/nguồn.
  Kiểm contact sheet clip xuất thực để xác nhận bố cục 9:16, không nhận `safe_zone_checked: true` là bằng chứng.

## Đầu ra
- Chỉ ghi `revisions/<rev>/reviews/product-review.yaml`, không sửa/render.
- Giữ đủ bảy key `scores` trên (gồm `dung_phong_cach_pyh`), `summary`, `issues`, `checked`, `decisions`;
  điểm 1–10, dưới 7 phải có issue với `at`, `criterion`, `problem`, `fix`, `fixable`.
- `fixable: true` chỉ nếu sửa trọn bằng SVG trong `video/src/anatomy/`
  hoặc `posts/posts.yaml`; phải đổi lời/cảnh/thời lượng/FLUX/profiles là false.
- `decisions` đúng loại và schema prompt: một `keep: true`, tối đa một
  `recommended: true`, mọi phương án bám ledger; lỗi thường ở `issues`.
- `checked` chỉ ghi phép kiểm đã thực hiện; trong `summary` tách rõ quan sát từ contact sheet,
  dữ liệu QA (`video-qa.json`/`pronunciation-qa.json`) và nhận định chưa nghe âm thanh.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Báo cáo đủ bảy tiêu chí với vị trí và hướng sửa cụ thể, không tự duyệt cổng.
- Thiếu contact sheet/QA/timing: chỉ rõ phần chưa kiểm, không chấm như đã xem đủ.
  Lỗi công cụ ghi log thật, retry đúng budget prompt; không sửa trạng thái/hash
  hoặc giả bước lấy khung hình lỗi đã thành công.
