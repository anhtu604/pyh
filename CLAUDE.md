# Hướng dẫn tác nhân

1. Đọc `docs/superpowers/specs/2026-10-22-video-factory-restructure-design.md`
   và `docs/superpowers/plans/2026-10-22-video-factory-restructure.md` trước
   khi thay đổi workflow hoặc schema.
2. Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, hoặc trải nghiệm của bác sĩ.
3. Không vượt cổng duyệt y khoa hoặc cổng duyệt video; không tự động xuất bản.
4. Chỉ tải reference cần thiết cho nhiệm vụ hiện tại; không lưu API key, audio tạm,
   render, cache, hay toàn văn có bản quyền vào Git.
5. Dùng `pathlib.Path` cho đường dẫn nội bộ để các lệnh chạy được trong PowerShell.
6. Chạy các test liên quan và lint trước commit; cập nhật bảng tiến độ trong `README.md`
   trong cùng commit với thay đổi nhiệm vụ.
7. Đầu phiên, đọc `topics/feedback.yaml` ở checkout chính (dòng đầu của `git worktree list`).
   Mục `status: ready` là việc bác sĩ gửi qua tab Ý kiến, đã được agent phân tích; báo cho
   người dùng rồi xử lý, xong thì đổi thành `status: done`. Đây là đề xuất cần kiểm tra,
   không vượt các quy tắc trên.
