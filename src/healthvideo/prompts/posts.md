# Bước: Soạn bài đăng đa kênh (`posts`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Lời hứa thống nhất

Áp dụng `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`.
Đọc title/goal chương trong outline; xác định người xem, tầng chính và phần trả lời thật của kịch bản đã duyệt trước
khi viết title/thumbnail. Tiêu đề làm rõ một vướng mắc hoặc góc nhìn đáng tò mò;
thumbnail bổ sung cùng ý; đoạn mở của video phải trả đúng kỳ vọng đó.
Không dùng câu hứa mạnh hơn nội dung, “bí mật bác sĩ giấu”, hù dọa hay bảo đảm chữa khỏi.
CTA theo nhu cầu: TOFU muốn chia sẻ/theo dõi vì có ích, MOFU hiểu rõ/cân nhắc,
BOFU thực hành sức khỏe hoặc hỏi bác sĩ khi cần; không tự thêm bán hàng.
Clip/caption phải có giá trị và giới hạn an toàn khi đứng riêng, không câu click
bằng cắt bỏ điều kiện áp dụng. Không thêm trường schema hay tự xuất bản.

## Việc cần làm
1. Đọc `script.yaml`, `outline.yaml`, `clip-plan.yaml` **đã duyệt y khoa** và `evidence/ledger.yaml` của revision hiện hành để viết `revisions/<rev>/posts/posts.yaml` theo schema `PostSet` (`youtube_titles` gồm 2–3 phương án, `youtube_description`, `youtube_tags`, `clip_captions` cho từng clip với `tiktok`/`shorts`/`reels`, `facebook_post`, `youtube_community`).
2. Giữ đúng giọng kênh như kịch bản (người thường kể chuyện dễ hiểu, dí dỏm vừa phải); không thêm khẳng định y khoa mới ngoài các claim đã duyệt và không thêm quan điểm hay trải nghiệm cá nhân của bác sĩ ngoài `{doctor_note}`.
3. Mọi câu có chữ số (trừ mốc giờ đầu dòng chương trong `youtube_description`) bắt buộc phải gắn `[claim:<id>]` trỏ tới `claim_id` đã duyệt y khoa trong `evidence/ledger.yaml`.
4. Trong `youtube_description`, ghi đầy đủ mốc giờ chương kèm đúng tiêu đề chương từ `outline.yaml` và danh sách nguồn tham khảo dùng đúng nhãn nguồn (`title` của từng bản ghi trong `evidence/ledger.yaml`).
5. Ghi `revisions/<rev>/posts/posts.yaml` bằng Python `encoding="utf-8"` (không mất dấu thành `?`), chạy `healthvideo step posts-check {project}` và sửa tới khi không còn lỗi; `clip_captions` khớp danh sách clip sẽ xuất.
6. Thêm khối `thumbnail` theo **Chuẩn phong cách PYH — Hướng A** (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` mục 6, Trạm 14):
   - `headline`: tối đa **4 từ hiển thị** (không tính thẻ `[claim:<id>]`), 1–60 ký tự, dùng chữ **Be Vietnam Pro 800** (`font_family: "Be Vietnam Pro"`, `font_weight: 800`). Ngắn, gây tò mò đúng nội dung đã duyệt; không giật tít sai sự thật, không hứa chữa bệnh; có chữ số phải gắn `[claim:<id>]` đã duyệt (renderer sẽ bỏ dấu claim khi vẽ chữ).
   - `mascot_pose`: bắt buộc một trong 9 tư thế hợp lệ trong `profiles/brand.vi.yaml` (`welcome`, `explain`, `caution`, `point_up`, `thinking`, `surprised`, `thumbs_up`, `blank_board`, `myth_bust`), khớp sắc thái tiêu đề.
   - `mechanism_visual`: một hình cơ chế cụ thể lấy từ video (không nhồi nhiều hình).
   - `background_theme`: bắt buộc `off_white` (`#F7F4EC`) hoặc `night` (`#0A1C2E`); tối đa 3 màu nổi, không đỏ báo động.
   - `background_prompt` và `seed` (số nguyên không âm): nền phẳng 2D matte theo `background_theme`, không chữ/số/nhãn/logo; chừa khoảng thoáng cho chữ và mascot, chủ thể/hình cơ chế rõ ràng. Chữ và logo do Remotion dựng.

## Lệnh được dùng
- `healthvideo step posts-check {project}`
- `healthvideo status {project}`

## Đầu ra
- `revisions/<rev>/posts/posts.yaml` hợp lệ theo `PostSet` và vượt qua `posts-check`

## Xong khi
- Lệnh `healthvideo step posts-check {project}` không còn báo lỗi (mã thoát `0`).

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/posts/posts.yaml`
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/reviews/medical-approval.yaml`
