# Kế hoạch phục hồi lỗi xưởng và hoạt cảnh nhân viên

**Goal:** Xử lý lỗi có deadline/budget hữu hạn, UI biểu diễn đúng việc đang chạy/nghỉ.
**Architecture:** Giữ workflow/schema/cổng; helper subprocess dùng chung, retry
sidecar theo input, backend xác minh process identity và UI SVG/CSS có state.
**Tech Stack:** Python/Pydantic/YAML, stdlib HTTP, SVG/CSS/JS hiện có; không dependency mới.
**Spec:** docs/superpowers/specs/2026-11-14-factory-reliability-animation-design.md.
**Ownership/files:** brief E:/Protect Your Health/cache/dev-lead/factory-reliability-animation-brief.md.
**Constraints:** không pilot/API trả phí/TTS/render thật, không bật xưởng, không push,
không đụng approval/hash/doctor-feedback; worker không commit. Tiến độ checkout chính.

## A. Subprocess và agent hữu hạn

1. Test fail timeout/partial output/cleanup và terminal event/marker.
2. Cung cấp run_bounded, process_token, is_same_process đúng spec, không nuốt ngắt.
3. AgentResult failure_kind tương thích cũ, transient failover hữu hạn, quota giữ nguyên.
4. Áp deadline cho render, nhạc, align, contact sheet, local TTS với log đúng bước.
5. Test helper thực bằng Python sleeper/descendant tạm, callers bằng fake runners;
   Ruff và kiểm diff. Không production thật.

## B. Queue/retry bền vững

1. Test fail repeated tick/restart, invalid state/artifact, exception làm mất topic sau.
2. Sidecar agent-retry tách produce, fingerprint input tiêu thụ ổn định, cap/backoff/hold.
3. Production execution marker trong mọi đường produce, finally dọn.
4. Factory wake deadline, dedupe và lời thông báo gate đúng nghĩa.
5. Giữ các regression produce retry, cache và approval; test + Ruff + đọc diff.

## C. Hoạt cảnh có chứng cứ

1. Test fail các false-busy và missing/dead/recycled PID, live chat khi factory tắt.
2. Backend role state + production marker; API additive, không suy máy chạy từ state dự án.
3. SVG pose/action theo role; idle/wait/error khác working; text/aria rõ.
4. Giữ scene khi poll không đổi; offline/hidden/offscreen/toggle/reduced-motion dừng loop.
5. Test HTTP/HTML contract và lead kiểm browser desktop/mobile/reduced-motion.

## Review và tích hợp

Lead đọc diff đầy đủ, kiểm hợp đồng chung A/B/C; reviewer độc lập kiểm invariants,
input không xác minh và UI không giả thực thi. Gửi cùng worker sửa một vòng gộp.
Sau test mục tiêu, chạy toàn pytest và Ruff; xác minh không có worker/pilot chạy.
Commit từng path đúng brief, squash về master, progress/handoff cập nhật bằng bằng chứng.
Ghi rõ phần nội dung cứng/chất lượng model chưa xử lý thay vì đánh dấu toàn xưởng xong.
