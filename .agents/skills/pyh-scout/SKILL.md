---
name: pyh-scout
description: Use when selecting or checking a new Vietnamese health topic before it enters the PYH queue.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Đề và dossier đã có, brief bác sĩ, queue và dự án để kiểm trùng.
output: Một brief kiểm trùng/khả thi giữ nguyên định hướng được giao.
done_when: Phân biệt câu hỏi mới với trùng đề; nêu căn cứ và giới hạn khả thi.
missing_data_to: researcher bổ sung dossier; coordinator quyết phạm vi; medical_expert kiểm bằng chứng.
```


# Trinh sát chủ đề xưởng PYH

## Đầu vào
- Chỉ kiểm đề đã có khi có caller/brief trực tiếp giao: kiểm trùng, đối tượng người xem (`audience`), câu hỏi trung lập; việc săn đề (`discover`) và chấm điểm `THANG_DIEM` do `researcher` thực hiện.
- Đọc brief về người xem, câu hỏi, mục tiêu kênh và giới hạn chủ đề.
- Kiểm trùng bằng `healthvideo topic list`, `topics/queue.yaml`, `projects/`;
  nếu nối tiếp video cũ, đọc revision hiện hành từ `project.yaml` rồi xem
  `script/outline.yaml` để phân biệt câu hỏi mới với đổi tên câu hỏi cũ.

## Phán đoán công việc
- Chọn nhu cầu người xem + điểm đáng nghe, không chỉ chọn một tên bệnh/cơ chế.
- Nói được: ai sẽ quan tâm, đang tự hỏi gì, xem xong hiểu thêm điều gì,
  góc nào có thể làm họ bất ngờ và bằng chứng nào cần chuyên gia kiểm.
- Theo `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`,
  chọn một tầng chính: TOFU gợi khám phá/góc nhìn bất ngờ; MOFU gỡ hiểu lầm,
  cân lựa chọn; BOFU thực hành sức khỏe, khám khi cần, tin và theo dõi kênh.
- Không bán hàng; không ép một video đi đủ ba tầng hay phải có nỗi đau bệnh nhân.
- Có thể chọn thói quen, điều tưởng quen, câu hỏi đời sống hoặc cơ chế;
  cơ chế chỉ đáng làm khi giúp trả lời nhu cầu đã nêu.
- Dùng tư duy searchable/shareable của `content-strategy`; bỏ phễu
  pricing/demo/buy, backlink và lịch bán hàng. Không hứa viral hay chữa khỏi.
- Tín hiệu tìm kiếm không tự chứng minh hiểu lầm phổ biến hoặc nhu cầu lớn.
  Không có dữ liệu demand thì gọi đó là giả thuyết để kiểm, không gọi đang hot.

## Đầu ra
- Theo đúng định dạng brief/lệnh đang giao; không tự tạo schema hàng đợi mới.
- Đề xuất gồm câu hỏi trung lập, người xem, intent chính, lời hứa/góc đáng nghe,
  căn cứ demand hoặc nhãn giả thuyết và điểm cần chuyên gia xác minh.
- Chỉ ghi file/hàng đợi khi nhiệm vụ cho phép; đề xuất không đồng nghĩa đã enqueue.
  Không tự tạo revision hay xuất bản.

## Xong khi
- Chủ đề không trùng, lời hứa có thể trả lời và căn cứ/giả thuyết được tách rõ;
  brief đủ để chuyên gia nghiên cứu và writer không tự đoán nhu cầu người xem.

## Thiếu dữ liệu hoặc lỗi
- Báo nguồn discover lỗi từ `failures`; không bịa xu hướng để lấp chỗ trống.
- Chưa có bằng chứng y khoa chỉ đề xuất câu hỏi, không khẳng định đáp án.
- Lỗi lệnh ghi thông báo thật; chỉ thử lại trong budget nhiệm vụ, không chạy xưởng.

## Bàn giao và giới hạn R5
- Giữ một brief từ researcher có 2–4 câu hỏi ứng viên và tầng chính; chỉ kiểm trùng/khả thi, không viết lại định hướng. Thiếu dossier trả researcher/coordinator, nguồn nền/cập nhật trả medical_expert qua Europe PMC, không NCBI.
