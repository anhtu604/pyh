---
name: pyh-copywriter
description: Use when the PYH posts step needs titles, descriptions, clip captions, community copy, or thumbnail text.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Nội dung đã duyệt, clip range/hook/payoff/caveat của shorts_producer và nguồn.
output: 'posts/posts.yaml: title/thumbnail/mô tả/caption xuất bản, không có kịch bản clip cạnh tranh.'
done_when: posts-check đạt và lời hứa được chính video/clip trả lời, giữ nguồn và caveat.
missing_data_to: shorts_producer nếu thiếu range/hook/payoff/caveat; medical_expert/writer nếu thiếu nguồn/nội dung; coordinator nếu thiếu approval.
```


# Viết bài đăng xưởng PYH

## Đầu vào
- Đọc prompt `posts.md`, doctor_note; lấy `active_revision` từ `{project}/project.yaml`.
- Đọc `revisions/<rev>/script/script.yaml`, `script/outline.yaml`,
  `script/clip-plan.yaml` đã duyệt, `evidence/ledger.yaml`,
  `reviews/medical-approval.yaml` cùng revision, và `topics/channel-insights.yaml` (nếu có) để tối ưu tiêu đề A/B & chữ thumbnail theo dữ liệu kênh thật.
- Xác định audience/intent từ `evidence/expert-brief.md` nếu cần; đọc `title`
  và `chapters[].goal` trong outline để giữ lời hứa, tiến triển/payoff/CTA
  đã chốt; đối chiếu script thực có, không phụ thuộc scratch của writer.

## Phán đoán công việc
- Title, thumbnail và mở video cùng một lời hứa; nội dung phải trả được nó.
  Tò mò từ góc nhìn thật, không giấu đáp án để hứa bí mật hay hù người đang khỏe.
- `youtube_titles`: 2–3 phương án, từ khóa tự nhiên và góc đáng nghe có căn cứ;
  không bắt mọi tiêu đề phải có bệnh/triệu chứng hay một ngộ nhận tự bịa.
- CTA theo tầng chính: TOFU gợi khám phá/quan sát/theo dõi;
  MOFU gợi cân hiểu/lựa chọn; BOFU thực hành sức khỏe, khám khi cần,
  tin và theo dõi kênh. Không bán hàng, không nhồi CTA khám/thuốc vào mọi bài.
- Caption từng clip tự đứng vững, chỉ hứa điều có trong chính clip,
  giữ caveat; không lấy kết luận video dài nếu clip thiếu phần hỗ trợ.
- Không thêm claim, số liệu, quan điểm hay trải nghiệm cá nhân bác sĩ ngoài đầu vào.
  Dùng giọng chia sẻ, không cam kết viral/chữa khỏi hay mồi tương tác rỗng.
- `social` chỉ hỗ trợ hook/caption và soi văn AI; bỏ MCP đặt lịch,
  bình luận/nhắn tin B2B, không tự publish.

## Đầu ra
- Chỉ ghi `revisions/<rev>/posts/posts.yaml` bằng Python `encoding="utf-8"` (không mất dấu thành `?`) theo `PostSet`:
  `youtube_titles`, `youtube_description`, `youtube_tags`, `clip_captions`
  (`tiktok`, `shorts`, `reels` từng clip, khớp đúng danh sách clip thực xuất trong `clip-plan.yaml`), `facebook_post`, `youtube_community`, `thumbnail`.
- Chương đúng giờ/tên từ outline, nguồn đúng title record trong ledger;
  câu có chữ số gắn `[claim:<id>]` trừ mốc giờ đầu dòng chương như prompt.
- Thumbnail theo **Chuẩn phong cách PYH — Hướng A** (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` mục 6, Trạm 14):
  - `headline`: tối đa **4 từ hiển thị** (sau khi bỏ `[claim:<id>]`), chữ **Be Vietnam Pro 800** (`font_family: "Be Vietnam Pro"`, `font_weight: 800`).
  - `mascot_pose`: bắt buộc một trong 9 tư thế hợp lệ trong `profiles/brand.vi.yaml`, khớp tiêu đề.
  - `mechanism_visual`: một hình cơ chế rõ ràng từ video.
  - `background_theme`: `off_white` hoặc `night` (tối đa 3 màu nổi, không đỏ báo động).
  - `background_prompt` và `seed` nguyên không âm: nền phẳng 2D matte, chủ thể bên phải, thoáng trái, không chữ/số/nhãn/logo; renderer vẽ chữ/logo, không bịa ảnh nguồn.

## Xong khi
- `healthvideo step posts-check {project}` exit 0 và lời hứa khớp payoff;
  đúng schema chưa đủ nếu tiêu đề vẫn hứa điều video không có.

## Thiếu dữ liệu hoặc lỗi
- Thiếu approval/script/clip hay thông tin nguồn thì báo phần thiếu, không đoán.
- Lỗi posts-check: sửa trong phạm vi và budget bước; ghi lỗi thật khi chưa xong,
  không đổi script/ledger/approval để bài đăng vượt kiểm, không tự đổi trạng thái.

## Điểm chạm TOFU R5
- Chỉ đóng gói title/thumbnail/caption từ nội dung và range/hook/payoff/caveat do shorts_producer sở hữu. Không đổi range, viết lại hook/payoff/caveat trong lời clip hoặc tạo kịch bản clip cạnh tranh. Thiếu clip tự trả lời lời hứa thì trả shorts_producer, không dùng caption cứu một clip thiếu đáp án.
- TOFU lấy điều bất ngờ có nguồn thực trong 30 giây đầu; nguồn đầy đủ ở mô tả. BOFU hành động sức khỏe có căn cứ, không bán hàng. Thiếu nguồn/ngày cập nhật trả medical_expert/writer; không gọi nguồn cũ là phát hiện mới (D3).
