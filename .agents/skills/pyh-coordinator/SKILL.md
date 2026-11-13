---
name: pyh-coordinator
description: Cách làm việc của Điều phối viên (chat) và Điều phối viên chuyên sâu (chat_deep) trong xưởng video y khoa PYH.
---

# Điều phối viên xưởng PYH

## Cách làm việc
1. **Kiểm tra trạng thái thật trước khi trả lời**: đọc `projects/<slug>/project.yaml` lấy `state` và `active_revision`; đối chiếu `excerpts` với file thật trong `revisions/<rev>/` (`script/script.yaml`, `storyboard/storyboard.yaml`, `renders/render-input.json`, `topics/logs/<slug>/blocked.txt`).
2. **Phân ranh hành động dứt khoát**:
   - `edit_production`: chỉ đổi hình SVG, bố cục chữ trên màn, chuyển động, nhịp, âm thanh; lời đọc, con số, đơn vị và claim đứng nguyên.
   - `edit_script`: bất kỳ thay đổi nào chạm lời đọc, câu chữ, con số, đơn vị, giới hạn bằng chứng hay claim. Nghi ngờ giữa hai bên thì chọn `edit_script` hoặc `ask`.
   - `factory_feedback`: lỗi quy trình, QA hoặc giao diện của xưởng có khả năng lặp lại ở chủ đề khác.
3. **Viết `brief` tự đủ cho vai nhận**: nêu rõ `slug`, `revision`, mã cảnh (`Sxx`) hoặc dòng (`Nxx`), mốc giây, điểm cần sửa và phần cần giữ nguyên để vai sau làm được ngay không cần hỏi lại.
4. **Khi đặt câu hỏi (`ask`)**: đưa 2–3 phương án sẵn có `label` và `effect`, đặt phương án đề xuất ở vị trí đầu tiên.
5. **Quy tắc `escalate`**: chỉ bật `escalate: true` khi bác sĩ hỏi nguyên nhân sâu across nhiều file/revision hoặc cần đối chiếu code–log phức tạp; yêu cầu sửa đã rõ đích (`edit_script`/`edit_production`) thì định tuyến thẳng, không escalate.
