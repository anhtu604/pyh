# Kế hoạch chuẩn hóa skill và model

**Mục tiêu:** Hoàn tất bộ hướng dẫn có thể review và kiểm hành vi trước khi làm video mới.
**Thiết kế:** `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`.
**Phạm vi:** Brief ở `E:/Protect Your Health/cache/dev-lead/agent-standards-brief.md`.
**Ràng buộc:** không đổi schema/cổng/hash/timing, không Opus/astra, không chạy pilot,
không sửa thay đổi sẵn trong doctor-feedback, không push. Tiến độ ở progress.yaml.

## 1. Dừng pilot

Dừng worker và tác vụ chờ cũ. Lưu hai project, queue, log riêng vào cache có ignore.
Queue rỗng và `healthvideo status` không còn project/worker; không xóa dữ liệu.

## 2. Kiểm baseline và sửa hợp đồng

Dev lead chuẩn bị spec, brief, worktree; người sửa skill sở hữu đúng 11 SKILL.md.
Baseline TOFU phải cho thấy ảnh hưởng của công thức phễu cũ trước khi sửa.
Chuẩn hóa đầu vào/đầu ra/xong khi/thiếu dữ liệu, không tạo field hoặc trạng thái giả.
Dev lead sở hữu các prompt draft, revise_medical, research, script_review, posts
để hướng dẫn có hiệu lực cùng skill và giữ format string của runner.

## 3. Phân model

Kiểm `agy models`, cache model Codex và CLI Claude. Chạy hai ứng viên trên cùng
packet ngắn, ghi thời gian/exit code và đầu ra. Hạn chạy hữu hạn; lỗi chạy không
được ghi thành điểm chất lượng. Ghi giới hạn mẫu nhỏ và các vai chưa đo.
Cấu hình company.yaml không đổi role/step/schema, đầu chuỗi critic khác maker.

## 4. Kiểm hành vi và tích hợp

Reviewer độc lập chạy các tình huống TOFU/MOFU/BOFU, claim thiếu, đòi hứa chữa khỏi,
bài đúng nhưng buồn tẻ; đọc đầy đủ diff, trả một vòng sửa nếu cần.
Dev lead chạy pytest company, runner prompt, script-review và bộ kiểm liên quan;
Ruff toàn src/tests/tools, kiểm YAML/frontmatter và `git diff --check`.
Nếu sửa Python ngoài các prompt Markdown cần brief bổ sung, test hành vi riêng.
Commit từng đường dẫn đã review, squash vào master; cập nhật progress/handoff/CLAUDE.
Không đổi worker đang tắt thành chạy. Kết thúc bằng trạng thái kiểm chứng được,
không đánh dấu việc sửa phục hồi lỗi hoặc schema là đã xong.
