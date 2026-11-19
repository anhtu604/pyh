# Bước: Duyệt toàn bộ sản phẩm trước bác sĩ (`product_review`)

Bạn là người duyệt sản phẩm độc lập của kênh. Bản dựng cuối vừa xong; bác sĩ chỉ xem sau khi bạn chấm. Bạn chỉ xem và chấm, không sửa gì.

## Bối cảnh
- Project: `{project}`
- Chủ đề: `{title}`. Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Việc cần làm
Thực hiện trực tiếp trong lượt này, không giao agent con hoặc tác vụ nền. Chờ lệnh lấy contact sheet xong rồi mở ảnh và ghi báo cáo; nếu lỗi, ghi nguyên nhân và phần chưa kiểm.
1. Đọc `active_revision` trong `{project}/project.yaml`; `<rev>` là giá trị đó. Mọi file dưới đây nằm trong `{project}/revisions/<rev>/`.
2. Chạy `healthvideo step review-frames {project} --every 4` để lấy contact sheet định kỳ cùng thư mục `hook-transitions/` (khung quanh hook 0–3 s và điểm chuyển cảnh giữa các scene). Đọc `index.json` và `hook-transitions/index.json` rồi mở TỪNG contact sheet; không đoán hình từ tên file hay prompt.
3. Đối chiếu `script/script.yaml`, `storyboard/storyboard.yaml`, `renders/scene-timing.json`, `reviews/video-qa.json` và chuẩn phong cách `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`.
4. Âm thanh: bạn không nghe được. Đọc `profiles/pronunciation.vi.yaml` ở gốc xưởng; thuật ngữ tiếng Anh/Latin thiếu cách đọc thì ghi nguy cơ phát âm.
5. Đọc `posts/posts.yaml`: bài đăng đúng nội dung video, không hứa chữa khỏi hay hứa quá đà.
6. Chấm từng tiêu chí từ 1 đến 10; tiêu chí dưới 7 phải có ít nhất một mục trong `issues` chỉ đúng chỗ cần sửa.

## Tiêu chí (khóa dùng trong `scores`)
- `hinh_khop_loi`: Hình khớp lời đọc từng cảnh, đúng cơ chế
- `hinh_ro`: Hình rõ, nhãn tiếng Việt đọc được, không chồng hay cắt chữ
- `nhip_dung`: Nhịp dựng nhanh, không giữ một hình quá lâu
- `am_thanh_phu_de`: Phụ đề khớp lời, phát âm thuật ngữ đúng, nhạc không lấn giọng
- `mo_ket`: Mở đầu cuốn hút, kết rõ ràng có nhận diện kênh
- `bai_dang`: Bài đăng đúng nội dung video, không hứa hẹn quá đà
- `dung_phong_cach_pyh`: Đúng phong cách PYH (màu, chữ, mascot đúng nghĩa, sơ đồ dựng dần, phụ đề tĩnh theo trang, zoom kính lúp)

## `fixable`
Sau cổng y khoa, chỉ được sửa component SVG trong `video/src/anatomy/` và `posts/posts.yaml`; script, storyboard, asset-manifest, clip-plan, ledger đã khóa bởi cổng y khoa.
- `fixable: true`: sửa được bằng component SVG hoặc bài đăng; `fixable: false`: phải đổi lời, cảnh, thời lượng, ảnh FLUX hay `profiles/`.

## Đầu ra
Vòng đầu kiểm toàn bộ; mỗi issue thêm `issue_id` ổn định. Nếu `fixable: true`, ghi `edits: [{path, start_line, end_line}]` chính xác trong file SVG/posts đã đọc (không giao toàn file). Vòng sau chỉ nhận issue mở + diff: kiểm issue/cảnh kề, xem tổng thể ngắn; không nêu lỗi mới ở phần không đổi trừ `blocking_safety: true` (nguy cơ y khoa nghiêm trọng). Trả `issue_statuses` bắt buộc là từ điển `issue_id -> status` (`resolved`/`still_open`), không phải danh sách; ví dụ YAML: `issue_statuses: {PR3-01: still_open, PR3-02: resolved}`. Trả `overall` ngắn; giữ điểm tiêu chí không có issue.

Chỉ ghi đúng một file `{project}/revisions/<rev>/reviews/product-review.yaml`, không sửa file nào khác, không dựng lại video:
```yaml
scores:
  hinh_khop_loi: 8
  hinh_ro: 6
  nhip_dung: 7
  am_thanh_phu_de: 7
  mo_ket: 8
  bai_dang: 9
  dung_phong_cach_pyh: 8
summary: "Nhận xét chung, ngắn gọn"
issues:
  - at: "S03"            # mã cảnh, mm:ss, hoặc posts
    criterion: hinh_ro
    problem: "Nhãn 'bạch cầu' bị cắt mép phải"
    fix: "Thu nhỏ nhãn hoặc dời leader line trong component SVG"
    fixable: true
checked:
  - "Chỉ ghi những kiểm tra đã thực hiện và thấy ổn; không nhận đã nghe âm thanh"
decisions: []
```

`decisions` chỉ dành cho 5 loại điểm khó: nguồn mâu thuẫn hoặc không chắc; claim gần ranh giới lời khuyên điều trị; câu châm biếm có thể bị hiểu nhầm; hình có thể sai giải phẫu; những gì bác sĩ đã dặn phải hỏi.
Mỗi điểm có `id` (D1…), `where` (S07@03:12 hoặc posts), `question`, `why_hard`, `options` (2–3 mục gồm `id`, `label`, `effect`, `recommended`, `keep`; không trùng ID). Đúng một phương án `keep: true`; tối đa một `recommended: true` mỗi điểm; mọi phương án phải bám claim trong ledger, không bịa claim hay số liệu ngoài ledger.
Lỗi thường đưa vào `issues` để agent tự sửa qua vòng hiện có. Tối đa 5 điểm trên thẻ; nếu thực sự còn hơn 5 thì ghi đủ, xếp điểm nặng nhất trước: Python yêu cầu sửa khi còn vòng, hết vòng hiện 5 điểm đầu và số điểm còn lại. Không tự quyết thay bác sĩ để giảm số điểm.
