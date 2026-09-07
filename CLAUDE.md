# Hướng dẫn tác nhân

1. Đọc `docs/superpowers/specs/2026-09-07-preventive-health-video-system-design.md`
   và `docs/superpowers/plans/2026-09-07-preventive-health-video-mvp.md` trước
   khi thay đổi workflow hoặc schema.
2. Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, hoặc trải nghiệm của bác sĩ.
3. Không vượt cổng duyệt y khoa hoặc cổng duyệt video; không tự động xuất bản.
4. Chỉ tải reference cần thiết cho nhiệm vụ hiện tại; không lưu API key, audio tạm,
   render, cache, hay toàn văn có bản quyền vào Git.
5. Dùng `pathlib.Path` cho đường dẫn nội bộ để các lệnh chạy được trong PowerShell.
6. Chạy các test liên quan và lint trước commit; cập nhật bảng tiến độ trong `README.md`
   trong cùng commit với thay đổi nhiệm vụ.
