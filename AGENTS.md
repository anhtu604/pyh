# Hướng dẫn tác nhân

1. Đọc `docs/superpowers/specs/2026-11-08-factory-company-design.md` trước khi thay đổi
   workflow hoặc schema. Kế hoạch và phân việc hiện hành nằm ở `CLAUDE.md` mục 5.
2. Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, hoặc trải nghiệm của bác sĩ.
3. Không vượt cổng duyệt y khoa hoặc cổng duyệt video. Theo yêu cầu bác sĩ 2026-11-15,
   được kết nối YouTube/TikTok và đăng đúng gói đã qua cả hai cổng còn hiệu lực,
   với tài khoản/quyền hiển thị được chọn rõ; không đăng lại khi chưa rõ kết quả.
4. Chỉ tải reference cần thiết cho nhiệm vụ hiện tại; không lưu API key, audio tạm,
   render, cache, hay toàn văn có bản quyền vào Git.
5. Dùng `pathlib.Path` cho đường dẫn nội bộ để các lệnh chạy được trong PowerShell.
6. Chạy các test liên quan và lint trước commit; không tự commit trừ khi brief yêu cầu;
   tiến độ do Claude ghi ở `docs/progress.yaml`.
7. Chỉ sửa các file brief nêu tên; cần đụng file khác thì dừng và báo lại.
8. Đang có bàn giao: đọc `docs/handoff-codex.md` trước tiên.
