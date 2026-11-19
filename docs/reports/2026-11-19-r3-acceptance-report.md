# Báo cáo nghiệm thu R3 — 2026-11-19

Người kiểm: verifier (độc lập với các tác giả). Mọi số liệu dưới đây lấy từ lệnh chạy trong phiên nghiệm thu trên `E:\Protect Your Health` (`master`).

## 1. Kết quả kiểm

| Hạng mục | Kết quả |
|---|---|
| `pnpm --dir video typecheck` | exit 0 |
| `pnpm --dir video test` | 43 file, 358 test đạt (không có file `video/` đổi sau lần chạy này) |
| `ruff check src tests tools` | All checks passed (exit 0) |
| `pytest -q --tb=short` (đầy đủ, sau khi sửa) | **2253 passed, 2 skipped, 0 failed** |
| `git diff --check` | exit 0 (chỉ cảnh báo LF/CRLF) |
| `git status --short tests/fixtures` | trống |
| `git worktree list` | 2 dòng: `master` và worktree `protect_your_health_handoff` |
| Xưởng | dừng (`healthvideo status`: "Xưởng nền: không chạy"; PID cũ 5260 không còn chạy) |
| `projects/` | 4 thư mục dự án còn nguyên; `healthvideo status` liệt kê đủ 4 |
| `library/medanim/` | 0 file `.mp4`, 0 `doctor-approval.yaml` |
| 4 hoạt cảnh | `MedAnimEntry` hợp lệ, SHA-256 khớp file thật (thư viện và public), giấy phép đều thuộc Public Domain/CC0/CC BY 3.0/CC BY 4.0, `medical_audit.passed: true`, trạng thái `pending` |
| `frame_slop_lint` | 39 khung dựng thật (4 hoạt cảnh, kể cả bản dọc men gan): **0 lỗi** |
| Ảnh preview | đã mở trực tiếp 21/21 ảnh trong `library/medanim/*/previews/`: không ghi chú nội bộ, phụ đề tĩnh, kính lúp, credit đủ |

Hai lần chạy pytest đầu có 3 test lỗi: `test_pyh_skill` (SKILL.md 42 dòng > 40; đã rút còn 39 dòng bởi r35-roles) và 2 test schema (schemas lệch sau `mascot_pose`; medanim chạy `tools.export_schemas`, đổi 5 file `schemas/*.json`). Lần chạy lại đạt toàn bộ.

## 2. Chưa kiểm được (nói thẳng)

- **Europe PMC**: máy này không kết nối được `www.ebi.ac.uk` trong phiên nghiệm thu (curl quá thời gian, `europepmc.org` trả 403; 1 PMID thử đạt trước khi mạng treo). Tôi **chưa đối chiếu độc lập** được 20 PMID và các trích dẫn ở 3 hoạt cảnh mới. Phần này dựa vào `medical_audit` của tác giả và cần kiểm lại khi có mạng. Với men gan, kết quả Kamiike 1989 đã kiểm ở vòng R2 trước đó.
- **Thời gian/token R3.4**: benchmark chỉ đo `qwen2.5:3b` (6 mẫu, 6/6 đạt schema, 123,8 tok/s). `qwen3:4b` không kéo được, chưa đo; chưa đánh giá chất lượng ngữ nghĩa so với cloud.
- 2 test pytest bị bỏ qua (skipped) chưa liệt kê tên.
- Chưa chạy xưởng thật với luật mới R3.5.

## 3. Việc để bác sĩ quyết

1. Duyệt từng hoạt cảnh (4 mục đang `pending`, chưa có `doctor-approval.yaml`). Mục men gan còn `open_issues` chặn nghiệm thu cuối: nội mô xoang có cửa sổ.
2. Bật định tuyến Ollama hay không (cần `profiles/local-llm.yaml`).
3. Z-Anatomy 3D giữ khóa: CC BY-SA 4.0 và có phần NC (`docs/reference/z-anatomy-license-check.md`).
4. Khi nào mở lại xưởng.
5. `projects/`, `topics/*.yaml`, `uv.lock` chưa commit: ignore hay commit.
