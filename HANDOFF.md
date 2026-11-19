# HANDOFF — 2026-11-19 (R3 xong, chờ bác sĩ xem)

Đọc `CLAUDE.md` mục 1 và 3 trước. Tiến độ sống ở `docs/progress.yaml`. Báo cáo nghiệm thu R3: `docs/reports/2026-11-19-r3-acceptance-report.md`.

## Quyết định của bác sĩ còn hiệu lực

- **2026-11-17: dừng tạo video thật** tới khi bác sĩ cho bật lại. Xưởng đang **dừng** (`healthvideo status` báo "Xưởng nền: không chạy"). Không bật lại khi chưa được phép.
- Phong cách A bắt buộc (spec `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`); phụ đề tĩnh theo trang; zoom y khoa bằng kính lúp; hình y khoa chỉ từ kho có giấy phép (Public Domain, CC0, CC BY 3.0, CC BY 4.0; cấm CC BY-SA/NC/ND).
- Push GitHub cần bác sĩ đồng ý mỗi lần. Chưa push gì.
- Đừng chạy pytest cùng lúc Vitest/Remotion.

## Đã xong (commit trên master, chưa push)

- R3.1, R3.2, R3.3 (Style A, trạm 09–15, bản dọc 9:16), R3.4 (telemetry, Ollama tắt mặc định, cache voice_prep), R3.5 (vai trò, shorts-plan nối clip-plan, skill gọn). Chi tiết và số liệu kiểm: báo cáo nghiệm thu.
- Thư viện hoạt cảnh y khoa `library/medanim/` có 4 mục (men gan, trao đổi khí phế nang, đại thực bào, vỡ mảng xơ vữa), tất cả `pending`: **bác sĩ chưa duyệt**, chưa có `doctor-approval.yaml`.

## Việc cần bác sĩ quyết

1. Duyệt (hoặc từ chối) từng hoạt cảnh trong tab "Thư viện hoạt cảnh" bằng PIN.
2. Có bật định tuyến Ollama không (cần tạo `profiles/local-llm.yaml`; mới đo `qwen2.5:3b`, chưa đo `qwen3:4b`).
3. Z-Anatomy 3D đang khóa (CC BY-SA 4.0 và có phần NC), xem `docs/reference/z-anatomy-license-check.md`.
4. Mở lại xưởng khi nào; sau đó dừng rồi bật một lần để nạp code mới.

## Tồn đọng

- Chưa commit: `projects/`, `topics/*.yaml`, `uv.lock` (dữ liệu chạy; hỏi bác sĩ ignore hay commit).
- Lỗ hổng y khoa ghi trong `open_issues` của từng `animation.yaml` (ví dụ nội mô xoang có cửa sổ của men gan còn chặn nghiệm thu cuối).
- Test flaky đã biết: `tests/storage/test_files.py::test_atomic_writers_use_unique_owned_temporary_files` đôi khi WinError 5 trên Windows.

## Cách giao việc

- Mỗi việc: sửa `docs/progress.yaml` ở checkout chính, brief tự đủ, đọc toàn bộ diff, gom lỗi vào một vòng sửa; `git add` từng đường dẫn, không `-A`, không commit `cache/`.
- Không bịa nguồn hay số liệu; NCBI bị chặn nên dùng Europe PMC; không lưu key, render, cache vào Git.
