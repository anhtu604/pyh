# HANDOFF — 2026-11-18 (Claude dev lead → phiên kế tiếp)

Đọc `CLAUDE.md` mục 1 và 3 trước. Tiến độ sống ở `docs/progress.yaml` (tab Tiến độ trong app). Bác sĩ thao tác qua app; đừng đưa lệnh nhiều tham số cho bác sĩ.

## Quyết định của bác sĩ còn hiệu lực

- **2026-11-17: dừng tạo video thật** tới khi dây chuyền hoàn thiện (R3); chỉ test nhẹ. Xưởng đã **dừng** (`xuong --stop`); không bật lại khi chưa được phép. PYH-003 kẹt Trạm 07 sau 3 chu kỳ (claim 6); PYH-002 chờ duyệt y khoa; PYH-001/004 tạm dừng.
- **Sửa/duyệt từng phần:** người viết chỉ sửa điểm bị nêu, người duyệt chỉ kiểm lại điểm đó rồi xem tổng thể ngắn; không làm lại từ đầu (đã làm ở R3.1).
- **Phong cách A "Mascot dẫn chuyện"** áp triệt để cho trạm 09–15 (09 Máy dựng, 10 Đạo diễn hình, 11 Thợ dựng, 12 Kiểm định, 13 Cổng video, 14 Đóng gói, 15 Shorts). Lõi Remotion/HyperFrames. Tham khảo: OpenMontage (AGPL, không vendoring), kaomei stickman B5, lemo-opuscar (docs CC BY-NC: chỉ lấy ý), MoneyPrinterTurbo (chỉ tham khảo).
- **Hình y khoa phải chuẩn khoa học** (giải phẫu, sinh lý, mô phôi, sinh lý bệnh, giải phẫu bệnh, vi sinh), đủ để bác sĩ khác đánh giá cao. **Agent không tự vẽ cấu trúc y khoa**: ghép từ kho có giấy phép (Servier CC BY 4.0; NIAID kiểm từng hình; Reactome CC BY 4.0; Wikimedia Commons CC0/CC BY), ghi `manifest.yaml`, credit cuối video. Màu mô theo thực tế, không theo màu thương hiệu.
- **Phụ đề tĩnh theo trang**: không gạch chân hay nhảy theo từng chữ; mỗi trang ≥4 từ; vàng tối đa 1 cụm/trang. Zoom y khoa bằng **kính lúp**, không cross-fade giả zoom (spec mục 3b, 4).
- Giảm thời gian/token; được dùng model nhẹ qua **Ollama** chỉ khi máy đủ tài nguyên (RTX 3060, RAM 32 GB; Ollama đã cài, chưa có model). Không dùng local cho y khoa hay chấm kịch bản.
- Push GitHub cần bác sĩ đồng ý mỗi lần. Chưa push gì.

## Đã xong và merge vào master (chưa push)

- R2.0–R2.5: hội tụ Trạm 07, thư viện giải phẫu đọc live, dashboard gọn + tab Tiến độ, mascot, OpenMontage tùy chọn, sửa Trạm 12, sửa Repair mồ côi (`aabefac`).
- **R3.1 `10400f0`**: sửa/duyệt từng phần (`workflows/scoped_review.py`, `rework.py`, 7 skill; issue_id cố định, `dropped_issues`, kẹt 2 vòng → bác sĩ). 2178 test đạt.
- **R3.2 `9ce796c`**: báo cáo `docs/reference/agent-skill-audit-2026-11-17.md` (thời gian, token, skill, Ollama, phong cách).
- Chuẩn phong cách: `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`.
- Xưởng **chưa** khởi động lại sau `aabefac` và R3.1: khi bác sĩ cho chạy lại, dừng rồi bật một lần để nạp code (`.venv\Scripts\python.exe -c "from healthvideo.cli import app; app()" xuong --root "E:\Protect Your Health" --stop` rồi `--background`).

## Đang dở: R3.3 hoạt cảnh y khoa mẫu "tế bào gan tổn thương → ALT/AST vào máu"

- Worktree `E:\pyh-r3-3`, nhánh `feat/r3-3-style-a`, **chưa commit**. `video/node_modules` là **junction** tới checkout chính: trước khi `git worktree remove` phải chạy `cmd /c rmdir E:\pyh-r3-3\video\node_modules` (xem memory `worktree-junction-hazard`).
- Code mới: `video/src/medanim/`, `components/MascotHost.tsx`, `StyleCaptions.tsx`, `captionPaging.ts`, `mascotMotion.ts`, `style/assets/`; sửa `Root.tsx`, `Captions.tsx`.
- Dữ liệu: `cache/medanim/liver-enzyme-leak/` (`script.yaml` 6 bước có PMID/DOI thật, `assets/manifest.yaml`, `review-r1.md`, `liver-enzyme-leak-r1-16x9.mp4` 53 s, ảnh khung). `cache/` đã ignore.
- Bản r1 bác sĩ nói **chưa đạt**. Góp ý đã gom thành brief vòng 2 (6 mục): bỏ gạch chân phụ đề; zoom → kính lúp; bỏ ghi chú "chưa có hình nội mô…" khỏi khung hình; hình ≥60% khung; thay nội mô tự vẽ bằng hình thật có giấy phép hoặc ghi `open_issues`; thể hiện màng/ty thể tổn thương tự nhiên hơn.
- Codex đã bắt đầu vòng 2 (StyleCaptions 12 test đạt) rồi bị ngắt. **Kiểm `git status` trong worktree, chạy `cd E:\pyh-r3-3\video; .\node_modules\.bin\vitest run; .\node_modules\.bin\tsc --noEmit`, xem lại khung hình trước khi tin.** Thiếu thì giao lại cùng 6 mục.
- Lỗ hổng y khoa còn mở: nội mô xoang có cửa sổ (chưa có hình có giấy phép), nhánh động mạch gan hợp xoang, màng tổn thương còn thô. Hai mức tổn thương: nhẹ → men bào tương; nặng/hoại tử → AST ty thể (nguồn Kamiike 1989, gan chuột thiếu máu: ghi rõ minh họa cơ chế).
- Còn worktree của agy: `C:/Users/anhtu/.gemini/antigravity-cli/worktrees/0d82942c-b0cf-4cbc-adfe-5a918919d215/swarm-zoom-02db4bbf` (nhánh `swarm-zoom-02db4bbf`, commit 1fa4006). Kiểm `git -C <path> status`; trống thì gỡ (gỡ junction trước nếu có).
- Sau khi bác sĩ duyệt: bản dọc 9:16, giọng đọc thật (TTS tốn credit: hỏi bác sĩ), rồi nối chuẩn vào trạm 09–15.

## Việc kế tiếp, theo thứ tự

1. Hoàn tất hoạt cảnh mẫu → bác sĩ duyệt → squash-merge `feat/r3-3-style-a` (`git add` từng đường dẫn, không `-A`, không commit `cache/`).
2. **R3.3b: nối chuẩn A vào trạm 09–15** (codex): ghim file chuẩn vào revision (sha256); mã lỗi `style_*` ở trạm 10; tiêu chí "Đúng phong cách PYH" ở trạm 12 (contact sheet + đoạn quanh hook/chuyển cảnh); thumbnail trạm 14; bản 9:16 trạm 15; storyboard phải có `mascot_pose` ở hook, đầu chương, outro. Căn cứ: mục 6 của spec và mục 5 báo cáo R3.2.
3. **Thư viện hoạt cảnh y khoa dùng lại**: kịch bản cơ chế từng bước + nguồn Europe PMC + hình có giấy phép → agent y khoa đối chiếu → bác sĩ duyệt một lần → vào thư viện. Cần mô hình dữ liệu và chỗ duyệt trong app. Làm thêm 2–3 hoạt cảnh khác loại (sinh lý, vi sinh, giải phẫu bệnh) để thử độ tổng quát. 3D (Z-Anatomy) chỉ sau khi xác minh giấy phép.
4. **R3.4 giảm thời gian/token**: (a) ghi usage/time theo attempt và trạm Python; (b) Ollama: benchmark model ~4B cho phân loại góp ý/tóm tắt, định tuyến theo VRAM/RAM thực, fallback OmniRoute, allowlist chỉ vai nhẹ; (c) giảm payload voice/critic, tái dùng cache.
5. **Vai trò/phân quyền** (đề xuất 1 và 4 của audit): quyền sở hữu script/hình/clip, bước shorts-plan chưa nối output thật, rút skill (bỏ SLR khỏi researcher…). Cần bác sĩ xem báo cáo R3.2 trước khi đổi.
6. Khi R3 xong: bật lại xưởng (stop/start), chạy PYH-003 với luật mới; nếu Trạm 07 vẫn kẹt, bác sĩ gửi hướng dẫn qua thẻ "Việc của bác sĩ".
7. R2.5 OpenMontage: chưa dùng cho video thật (thiếu anatomy, mascot, 9:16, phụ đề dòng); xét lại sau chuẩn A.

## Tồn đọng

- Chưa commit: `projects/`, `topics/*.yaml`, `uv.lock` (dữ liệu chạy; hỏi bác sĩ ignore hay commit).
- Test flaky: `tests/storage/test_files.py::test_atomic_writers_use_unique_owned_temporary_files` đôi khi WinError 5 trên Windows (khi còn tiến trình mồ côi).
- Đừng chạy pytest cùng lúc Vitest (một test dựng Remotion quá giờ).

## Cách giao việc

- Mỗi việc: sửa `docs/progress.yaml` ở checkout chính (`chore: progress`), worktree và nhánh riêng, brief tự đủ ở scratchpad, đọc toàn bộ diff, gom mọi lỗi vào một vòng sửa, squash-merge.
- **agy** (giao diện, Remotion, việc cần nhìn ảnh): tên model đổi theo ngày. Khi lỗi "invalid model selection", đọc danh sách trong lỗi (2026-11-17: `"Claude Opus 4.6 (Thinking)"`, `"Claude Sonnet 4.6 (Thinking)"`, `Gemini 3.8 Flash (High/Medium/Low)`, GPT-OSS 120B). Hạn mức agy hay cạn (429, reset sau vài giờ): khi đó giao codex.
- **codex**: `Get-Content -Raw brief.md | codex exec -m gpt-6.1-sol --dangerously-bypass-approvals-and-sandbox -`.
- Không bịa nguồn hay số liệu; NCBI bị chặn nên dùng Europe PMC; không lưu key, render, cache vào Git.
