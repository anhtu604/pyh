# HANDOFF — 2026-11-19 (R3 + Pháp y log & Vá lỗi dừng xưởng xong, chờ bác sĩ xem)

Đọc `CLAUDE.md` mục 1 và 3 trước. Tiến độ sống ở `docs/progress.yaml`. Báo cáo nghiệm thu R3: `docs/reports/2026-11-19-r3-acceptance-report.md`. Báo cáo pháp y log & vá lỗi dừng xưởng: `docs/reports/2026-11-19-factory-log-audit-and-fixes.md`.

## Quyết định của bác sĩ còn hiệu lực

- **Xưởng đang dừng** (`healthvideo status` báo `Xưởng nền: không chạy`; `PID 13064` đã chết và `.xuong.lock` mồ côi đã dọn). Không bật lại khi chưa được bác sĩ cho phép; khi bật lại nhớ dừng/khởi động lại một lần để nạp code mới.
- Phong cách A bắt buộc cho dự án mới (spec `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`); 4 dự án cũ trước Chuẩn A (`style_a_active == False`) dùng 6 tiêu chí gốc ở Trạm 12, không bị chặn bởi `dung_phong_cach_pyh`.
- Push GitHub cần bác sĩ đồng ý mỗi lần. Chưa push gì.
- Đừng chạy `pytest` cùng lúc Vitest/Remotion.

## Đã xong (commit trên master, chưa push)

- R3.1–R3.6: Style A (trạm 09–15, 9:16), thư viện 4 hoạt cảnh `library/medanim/` (còn `pending`, chưa có `doctor-approval.yaml`), telemetry + Ollama tắt mặc định (`qwen2.5:3b` benchmark; `qwen3:4b` chưa đo), thống nhất vai trò R3.5, ScopusProvider + kiểm chéo PubMed (`60e1744`).
- **R3.7 (Pháp y log & vá lỗi dừng xưởng):** sửa tự thoát kép `repair_service` + `factory`, retry `WinError 5/32` ở `write_text_atomic`/`agents`, `PYTHONUTF8=1` cho subprocess, `restore_locked_illustrations` khôi phục ảnh khóa `sha256` ở `produce`/`visual_review`, đồng bộ `shorts_plan` 1800..2700f + fallback an toàn, `gpu_mutex` reentrant + batch FFmpeg `<=50` frame, Trạm 12 tương thích dự án cũ, xóa mù lỗi `runner`/`storyboard_design`/`script_review`. Đã dọn `blocked.txt`, `production-retry.yaml`, `repair_failed` trên `thay-men-gan-...`; giữ nguyên `paused.yaml` ở 3 dự án kia và giữ nguyên toàn vẹn `medical-approval.yaml` (9/9 hash).

## Việc cần bác sĩ quyết

1. Cho phép bật lại `xuong` để chạy tiếp `thay-men-gan-...` (`medically_approved -> produce`, lưu ý `CL01` 2486f gần ngưỡng 90s nếu TTS chậm) và quyết định có bỏ `paused.yaml` cho `hoc-xuong-ca-...` (`medically_approved`), `an-gao-lut-...`, `uong-1-vien-c-sui-...` hay không.
2. Duyệt (hoặc từ chối) 4 hoạt cảnh `pending` trong tab "Thư viện hoạt cảnh" bằng PIN (`liver-enzyme-leak` còn `open_issues` nội mô xoang có cửa sổ).
3. Quyết định bật định tuyến Ollama (`profiles/local-llm.yaml`), Z-Anatomy 3D (`CC BY-SA 4.0` + phần `NC`), và dán `ELSEVIER_API_KEY` vào `.env` nếu dùng Scopus.

## Tồn đọng

- Chưa commit (dữ liệu vận hành / ngoài phạm vi): `projects/`, `topics/*.yaml`, `uv.lock`, cùng thay đổi runtime `profiles/doctor-feedback.yaml` từ lượt duyệt y khoa 2026-11-19.
- Test opt-in skip khi không đặt biến môi trường: `tests/e2e/test_real_production_smoke.py:27` và `tests/render/test_openmontage.py:230`. (Test `tests/storage/test_files.py` đã hết flaky: chạy 5/5 lần liên tiếp đều 10/10 pass.)

## Cách giao việc

- Mỗi việc: sửa `docs/progress.yaml` ở checkout chính, brief tự đủ, đọc toàn bộ diff, gom lỗi vào một vòng sửa; `git add` từng đường dẫn, không `-A`, không commit `cache/`.
- Không bịa nguồn hay số liệu; không lưu key, render, cache vào Git.
