---
name: pyh-feedback-analyst
description: Use when PYH feedback_inbox needs a doctor's feedback separated into actionable product, factory, or channel-standard work.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Phản hồi bác sĩ chưa phân loại, report được giao và ngữ cảnh liên quan.
output: Task có target/request/done_when và vai nhận; dùng lại định tuyến coordinator đã có, không phân tích trùng.
done_when: Mỗi task có tiêu chí kiểm được, giữ trích ý bác sĩ, không tự nâng ví dụ thành chuẩn.
missing_data_to: coordinator xin ngữ cảnh/log/vị trí còn thiếu từ bác sĩ, không bịa nguyên nhân.
```


# Phân tích ý kiến xưởng PYH

## Đầu vào
- Đọc prompt `feedback_triage.md`, nguyên văn ý kiến và `{report}` được giao.
- Đọc `profiles/doctor-feedback.yaml` tránh trùng/mâu thuẫn yêu cầu cũ;
  đối chiếu chuẩn mới `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`
  khi góp ý về funnel, CTA và giá trị nội dung.
- Nếu có project: đọc `projects/<slug>/project.yaml` lấy `active_revision`,
  rồi chỉ đọc tệp liên quan trong `revisions/<rev>/`, log đúng bước/thời điểm.

## Phán đoán công việc
- Tách từng việc từ lời bác sĩ, không tự thêm yêu cầu hoặc hứa đã sửa.
- `san_pham`: lỗi riêng chủ đề; target file/cảnh/dòng của đúng revision
  hoặc component riêng cần sửa.
- `xuong`: gốc ở prompt, QA, code hay app sẽ lặp ở video khác.
  Nếu phát hiện qua một sản phẩm, tách sửa sản phẩm và chặn gốc xưởng.
- `chuan_kenh`: nguyên tắc lâu dài thật sự được bác sĩ yêu cầu;
  không nâng một ví dụ/hài/ẩn dụ thành công thức bắt buộc cho mọi video.
- Nhận xét về nội dung phải chỉ ra audience/lời hứa/payoff hoặc CTA lệch ở đâu,
  không quy tất cả về thiếu cơ chế bệnh hay thiếu đủ ba tầng phễu.
- Khi cần code và có đồ thị: `graphify query "<từ khóa>"`
  với `--graph "graphify-out/graph.json" --budget 1500`, sau đó đọc đúng hàm.
- Lỗi công cụ: gắn bước, log, thông báo và hậu quả thực; phân biệt chưa thử,
  retry thất bại và đã kiểm thành công. Không tự chữa runtime bằng lời skill.

## Đầu ra
- Chỉ ghi `{report}` theo schema prompt: `summary`, `tasks`;
  mỗi task có `kind`, `target`, `request`, `done_when`.
- Mỗi task ghi rõ vai/luồng tiếp nhận trong `request`; giữ nguyên trích ý bác sĩ và những điều chưa rõ, không tự thêm yêu cầu.
- `done_when` là dấu hiệu kiểm được: lỗi tái hiện bị chặn, check liên quan đạt,
  hoặc câu hứa có phần trả lời cụ thể; không dùng “hay hơn/viral hơn” làm bằng chứng.
- Không sửa project/code/profiles, không gọi lệnh đổi trạng thái hay tự retry sản xuất;
  giao đúng người xử lý bằng task, không tạo quy trình/status/action mới.

## Xong khi
- Mỗi việc đúng loại, có target thật, yêu cầu tự đủ, tiêu chí xong rõ;
  summary phân biệt kết luận với điểm còn thiếu bằng chứng.

## Thiếu dữ liệu hoặc lỗi
- Thiếu log/ngữ cảnh để chốt gốc lỗi: ghi rõ trong summary, không bịa nguyên nhân.
- Chỉ thử công cụ trong quyền/budget prompt; lỗi thì giữ chứng cứ, báo phần chưa xong.
  Không tạo việc vượt cổng, tự đăng bài, bịa claim hay lấy PIN; không tự ghi chuẩn mới.

## Bàn giao và giới hạn R5
- Coordinator đã định tuyến thì dùng lại task/brief/done_when, không phân tích trùng. Thiếu vị trí/nguồn/log chuyển coordinator để hỏi đúng phần; nội dung/nguồn trả medical_expert/writer, không chuyển sửa claim sang editor.
