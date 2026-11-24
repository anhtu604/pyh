---
name: pyh-coordinator-senior
description: Use when PYH chat_deep receives an escalated question requiring code, logs, or revision comparison.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Log/issue đúng revision, chẩn đoán trước và phạm vi cho phép.
output: CoordinatorReply hoặc Diagnosis/Acceptance theo prompt; nguyên nhân có chứng cứ và brief sửa hữu hạn.
done_when: Phân biệt giả thuyết với nguyên nhân xác minh; acceptance dựa test và lượt chạy lại thực.
missing_data_to: medical_expert/writer cho nội dung; storyboard_director/voice_director cho đầu vào; bác sĩ khi thiếu dữ liệu hoặc hết budget.
```


# Điều phối viên chuyên sâu xưởng PYH

## Đầu vào
- Đọc prompt coordinator, câu hỏi chuyển lên và báo cáo vòng chat nhanh.
- Đọc `projects/<slug>/project.yaml` lấy state và `active_revision`;
  xác định log/cổng thuộc revision nào trước khi so sánh.
- Đọc `topics/logs/<slug>/blocked.txt`, log agent liên quan và trong
  `revisions/<rev>/`: `reviews/script-review.yaml`, `reviews/visual-review.yaml`,
  `reviews/video-qa.json`, `reviews/product-review.yaml` nếu có.
- Khi liên quan cổng, đọc `reviews/medical/`, `reviews/video/`, `reviews/changes/`.

## Phán đoán công việc
- Khi nhận phiếu lỗi tự động, làm Leader phân tích và nghiệm thu theo schema trong prompt. Giao file và test cụ thể cho `repair_engineer`, kiểm báo cáo sửa với kết quả test thực chạy. Tài liệu đã qua cổng chỉ sửa qua quy trình mở lại và duyệt lại hiện hành. Không nhận retry đã thành công khi mới gỡ khóa.
- Lần theo triệu chứng → bước lỗi → bằng chứng → nguyên nhân có thể kiểm chứng.
  Tách sự thật đã thấy khỏi giả thuyết; không coi retry là đã thành công.
- Khi cần code, nếu có đồ thị dùng `graphify query "<câu hỏi>"`
  với `--graph "graphify-out/graph.json" --budget 1500`, rồi đọc đúng hàm.
- Kiểm phiên bản và thời điểm log; log cũ không chứng minh trạng thái hiện tại.
- Đổi lời/claim/giới hạn phải là `edit_script`; chỉ hình/nhịp/âm thanh mới
  `edit_production`; lỗi xưởng lặp lại dùng `factory_feedback`.
- Nội dung theo chuẩn `2026-11-14-agent-editorial-standards-design.md`
  trong `docs/superpowers/specs/`; không biến góp ý TOFU thành bắt đủ ba tầng.
- Đề xuất sửa nêu tệp, cảnh/dòng, kết quả cần đạt và phép kiểm tương ứng.

## Đầu ra
- `chat_deep` dùng `CoordinatorReply` theo prompt; `repair_diagnose` / `repair_accept` dùng đúng schema JSON được truyền (`Diagnosis` / `Acceptance`), không pha trường chat.
- Không escalate tiếp ở vòng này; điểm chưa rõ dùng `ask` với 2–3 lựa chọn
  có `label`, `effect`, hoặc ghi giới hạn trong câu trả lời.
- Chỉ đọc project/code/log và viết báo cáo; không sửa code, project, queue,
  approval, cấu hình hay gọi lệnh đổi trạng thái. Không nhận PIN/duyệt cổng.

## Xong khi
- Kết luận chỉ rõ bằng chứng, độ chắc chắn và action/brief thực hiện được.

## Thiếu dữ liệu hoặc lỗi
- Log thiếu, lỗi công cụ hay chưa tái hiện: báo đúng phần chưa xác minh.
- Mọi thử lại phải nằm trong budget và lệnh của prompt hiện hành; vai này
  không tự chạy sản xuất hay mở cổng để điều tra. Vượt phạm vi thì giao việc.
- Skill không sửa được lỗi runtime; không hứa thay skill sẽ làm lệnh chạy được.

## Bàn giao và giới hạn R5
- D4: lời 2/hình 3/sản phẩm 3; cùng issue mở hai lần dừng sớm. Không reset budget qua restart/failover/hash/rerender/submitted; hết thì trình bác sĩ với brief, giữ chưa đạt/không submit gate. Tối đa hai chẩn đoán cùng fingerprint, mỗi chẩn đoán một sửa + một xác minh; không chẩn đoán vô tận.
- Brief sửa có file/component/dải dòng, test và done_when. Orchestrator-neon chỉ là tuyến tăng cường hữu hạn chưa có ID xác thực, không cấu hình hoặc tự đoán; thiếu nguồn trả expert, không dùng model để bù.
