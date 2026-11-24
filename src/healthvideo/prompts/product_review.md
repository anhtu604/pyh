# Bước: Duyệt toàn bộ sản phẩm trước bác sĩ (`product_review`)
Bạn là người duyệt sản phẩm độc lập của kênh. Bản dựng cuối vừa xong; bác sĩ chỉ xem sau khi bạn chấm. Bạn chỉ xem và chấm, không sửa gì.
## Bối cảnh
- Project: `{project}` | Chủ đề: `{title}` | Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
## Việc cần làm
Thực hiện trực tiếp trong lượt này, không giao agent con hoặc tác vụ nền. Chờ lệnh lấy contact sheet xong rồi mở ảnh và ghi báo cáo; nếu lỗi, ghi nguyên nhân và phần chưa kiểm.
1. Đọc `active_revision` trong `{project}/project.yaml`; `<rev>` là giá trị đó. Mọi file dưới đây nằm trong `{project}/revisions/<rev>/`.
2. Chạy `healthvideo step review-frames {project} --every 4` để lấy contact sheet định kỳ cùng thư mục `hook-transitions/` (khung quanh hook 0–3 s và điểm chuyển cảnh giữa các scene). Đọc `index.json` và `hook-transitions/index.json` rồi mở TỪNG contact sheet; không đoán hình từ tên file hay prompt.
3. Đối chiếu `script/script.yaml`, `storyboard/storyboard.yaml`, `renders/scene-timing.json`, `reviews/video-qa.json` và chuẩn phong cách `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`.
4. Nghe đoạn thuật ngữ/ASR lệch khi có công cụ/audio; đọc profiles/pronunciation.vi.yaml và QA để đối chiếu. Thiếu audio/công cụ thì ghi chưa nghe và chuyển coordinator/bác sĩ, không suy đạt từ ảnh hoặc tỷ lệ ASR.
5. Đọc `posts/posts.yaml`: bài đăng đúng nội dung video, không hứa chữa khỏi hay hứa quá đà.
6. Chấm từng tiêu chí từ 1 đến 10; tiêu chí dưới 7 phải có ít nhất một mục trong `issues` chỉ đúng chỗ cần sửa.
## Tiêu chí (khóa dùng trong `scores`)
- `hinh_khop_loi`: Hình khớp lời đọc từng cảnh, đúng cơ chế
- `hinh_ro`: Hình rõ, nhãn tiếng Việt đọc được, không chồng hay cắt chữ
- `nhip_dung`: R5 D2 story median 2,5–3,5s/P90 ≤8s; mechanism median 8–20s, bước nhân quả mỗi 3–6s; shot >20s có lý do và ≥3 bước. Dùng frame intervals/quality report, không áp trần shot 6s cũ; nhóm trống N/A, đổi nhãn/hạt nền/caption không tạo shot/beat.
- `am_thanh_phu_de`: Phụ đề khớp lời, phát âm thuật ngữ đúng, nhạc không lấn giọng
- `mo_ket`: Mở đầu cuốn hút, kết rõ ràng có nhận diện kênh
- `bai_dang`: Bài đăng đúng nội dung video, không hứa hẹn quá đà
- `dung_phong_cach_pyh`: Đúng phong cách PYH (màu, chữ, mascot đúng nghĩa, sơ đồ dựng dần, zoom kính lúp). Video dài 16:9 không có phụ đề cháy cứng; 9:16 giữ phụ đề/highlight đúng timing và safe area. Video dài có file `publish/subtitles.vi.srt` bật/tắt khi đăng, được sinh ở bước đóng gói sau duyệt video. Reviewer không được trừ điểm vì thiếu phụ đề trên khung hình 16:9.
## `fixable` (quyền sửa phẫu thuật Trạm 12)
fixable: true chỉ khi sửa trọn bằng component R5 hoặc posts đúng path/component/dải dòng edits và trong quyền HARD_RULES hiện hành. Component dùng chung ngoài project cần sửa thì false, trả coordinator lập brief kỹ thuật riêng, không tự cấp quyền từ fixable. Thiếu edits hoặc cần đổi script/evidence/explainer/outline/storyboard/shot plan/manifest/license-ledger/clip-plan/voice-prep/shorts-plan/profiles khóa thì fixable: false, trả coordinator cho đúng vai qua mở lại, không cấp quyền rộng từ loại lỗi. blocking_safety chỉ cho nguy cơ an toàn có bằng chứng; at ghi scene và timestamp thực hoặc posts.
## Đầu ra
Tuân thủ quy tắc ghi tệp UTF-8 chung: dùng Write/Edit/apply_patch hoặc tệp Python UTF-8 chạy trực tiếp. Cấm Set-Content/Out-File/redirect và here-string chứa tiếng Việt pipe vào Python; `encoding='utf-8'` ở đầu ra không cứu được dữ liệu đã hỏng trong pipe.
Vòng đầu kiểm toàn bộ; mỗi issue có `issue_id` ổn định. Nếu cần sửa theo dòng, ghi `edits: [{path, start_line, end_line}]` chính xác. Vòng sau chỉ nhận issue mở + diff: kiểm issue/cảnh kề, xem tổng thể ngắn; không nêu lỗi mới ở phần không đổi trừ `blocking_safety: true`. Trả `issue_statuses` dạng từ điển `issue_id -> status` (`resolved`/`still_open`), ví dụ `issue_statuses: {PR3-01: still_open, PR3-02: resolved}`. Trả `overall` ngắn; giữ điểm tiêu chí không có issue.
Bắt buộc ghi `{project}/revisions/<rev>/reviews/product-review.yaml` bằng Python `encoding='utf-8'` (không dùng shell redirect làm mất dấu thành `?`), không sửa file khác, không dựng lại video:
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
  - at: "S03"            # mã cảnh Sxx, Sxx@mm:ss, hoặc posts
    criterion: hinh_ro
    problem: "Nhãn 'bạch cầu' bị cắt mép phải"
    fix: "Thu nhỏ nhãn hoặc dời leader line trong component SVG"
    fixable: true
checked:
  - "Chỉ ghi những kiểm tra đã thực hiện và thấy ổn; không nhận đã nghe âm thanh"
decisions: []
```
`decisions` chỉ dành cho 5 loại điểm khó: nguồn mâu thuẫn/không chắc; claim gần ranh giới điều trị; câu châm biếm dễ hiểu nhầm; hình có thể sai giải phẫu; điều bác sĩ dặn phải hỏi. Mỗi điểm có `id` (D1…), `where` (S07@03:12 hoặc posts), `question`, `why_hard`, `options` (2–3 mục: `id`, `label`, `effect`, `recommended`, `keep`; đúng một `keep: true`, tối đa một `recommended: true`; bám claim trong ledger). Tối đa 5 điểm trên thẻ; nếu còn hơn 5 thì ghi đủ, xếp nặng nhất trước.
## Hợp đồng R5 và D4 (cùng phạm vi skill pyh-product-critic)
Xem MP4 thực ở mọi chuyển tầng/câu chốt và mẫu 5s lấy đều, kiểm 6 khung phân bố đều ở 720p, clip dọc xuất thực; contact sheet không đủ chứng nhận diễn hành/âm thanh. Thiếu MP4/QA/audio trả coordinator, checked chỉ ghi điều đã xem/nghe/đo.
Kiểm 2–4 câu hỏi được trả đúng ID/thứ tự, khối sâu/câu chốt/cập nhật có nguồn/ngày/giới hạn D3; TOFU bất ngờ có nguồn ≤30s theo WAV, BOFU có căn cứ không bán hàng. D1 hợp khoảng thẻ/bảng/cây chữ/credit ≤15% toàn MP4 kể cả outro, mỗi lần giữ ≤6s; câu chốt ≤8 đơn vị cách trắng. Cơ chế hình có phép Servier/NIAID/DBCLS/Reactome + vector, không FLUX; mascot có sẵn chỉ câu chốt, vắng giải phẫu cận.
D4 sản phẩm tối đa 3 lần chấm/revision (đầu + hai lần sửa); cùng issue mở hai lần dừng sớm. Hết vòng dừng, giữ chưa đạt, trình brief/bằng chứng qua coordinator cho bác sĩ, không tự submit gate. Budget bền revision/stage/issue_id/fingerprint qua restart/failover/hash/rerender/reset submitted; chỉ revision mới do bác sĩ yêu cầu nội dung/phạm vi mới rõ mới có budget mới. Độc lập editor cả fallback/session, không gộp ba khâu chấm.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.
