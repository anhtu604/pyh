# Các bước hoàn thiện M7

Áp dụng trong worktree `codex/m1-workflow-kernel`. Giữ nguyên project v1/v2,
hai cổng duyệt thủ công và trạng thái `packaged`; không tự xuất bản. Kế hoạch
chi tiết gốc: `2026-09-15-m7-hardening.md`, Task 5–6.

| Bước | Kết quả kiểm tra được | Điều kiện hoàn thành |
| --- | --- | --- |
| B1 — Security audit offline | `healthvideo security-audit <project>` trả finding đã khử dữ liệu nhạy cảm, mã thoát khác 0 khi có lỗi; phát hiện link, binding backup hỏng, trường credential và media/secret ở path Git có thể theo dõi. | Test audit/CLI đỏ rồi xanh; Ruff, toàn bộ Python, `git diff --check`; README và commit cùng thay đổi. |
| B2 — Filesystem doctor | Probe exclusive-create và atomic same-directory rename trên filesystem của project, dọn đúng file thử; từ chối tuyên bố single-writer khi probe thất bại. | Test success/failure/cleanup/PowerShell path; CLI doctor và tests qua. |
| B3 — Runbook và hợp đồng vận hành | Runbook lệnh thật cho doctor, status/lease, backup/restore/audit; bảng lỗi và bước phục hồi; cập nhật `AGENTS.md` và `/pyh` trong ranh giới M7. | Test từng command trong runbook tồn tại, kiểm không vượt hai gate, focused/full test và lint qua. |
| B4 — Acceptance và C2C | Chạy full Python/video/typecheck/schema/E2E nhiều lần, audit v1/v2, kiểm commit không có media/model/cache/credential, review C2C đến DONE. | Worktree sạch; README ghi số đo thật và M7 complete chỉ khi toàn bộ cổng đạt. |

B1 chỉ là lát đầu của Task 5, không thay thế B2–B4 hoặc review độc lập.
