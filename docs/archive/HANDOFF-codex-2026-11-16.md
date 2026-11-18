# Handoff từ Codex sang Claude

> Ngày 16/11/2026 · Workspace `E:/Protect Your Health`
> Bác sĩ yêu cầu bàn giao lại cho Claude và ghi rõ việc xưởng lỗi liên tục. Đọc `AGENTS.md`, `docs/handoff-codex.md` và mục 5 `CLAUDE.md`.

## Mục tiêu

Xưởng phải tự tiếp tục xử lý tới khi có sản phẩm hoặc cần bác sĩ quyết định. Khi lỗi, Leader nhận ca và giao đúng vai; khi Trạm 07 không đạt, chuyển nhận xét tới Writer và chấm độc lập bản mới. Ưu tiên PYH-003 (video men gan). **Đưa mascot thương hiệu vào các dự án video** bằng bộ hình sẵn có và dùng theo nội dung cảnh. Bác sĩ cũng muốn chuyển bước dựng sang OpenMontage và giữ dashboard dễ theo dõi.

## Tình trạng lúc bàn giao

- PYH-003: `projects/thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi/`, revision `001`, `draft_ready`. Lần kiểm cuối có marker hoạt động, không có `blocked.txt`, critic vòng **15 chưa đạt**. Không có bản video mới được nghiệm thu. Worker xưởng PID 4420, Repair PID 11028 tại thời điểm kiểm; đo lại khi tiếp nhận.
- Dashboard tại `http://127.0.0.1:8765/` trả HTTP 200 với giao diện mới. Trang Tổng quan đã bỏ mục Tiến độ hoàn thiện xưởng; Sơ đồ xưởng, Kho đề tài và Kênh ở tab riêng. JavaScript qua kiểm tra cú pháp; chưa xác nhận giao diện trực tiếp qua Chrome.
- Mascot dùng chung còn ở `assets/brand/mascot/` (welcome, explain, caution, thinking, v.v.). Storyboard PYH-003 hiện không tham chiếu asset vai `mascot`; `brand_outro` chỉ gắn logo. Các nhân vật của dashboard 3D vẫn nằm trong tab Sơ đồ xưởng. Đây là hai thành phần khác nhau.
- OpenMontage lấy từ repo `https://github.com/calesthio/OpenMontage`, commit `2e003e65fa99a0f329478a2c1cdcf26bc481933a`. Hai kiểm thử đầu cuối HyperFrames đạt trên Windows. Đoạn mẫu 8 giây 1920×1080 đã xuất ở `C:/Users/anhtu/AppData/Local/Temp/pyh-openmontage-f56b90c762434b16843025b91905c259/pyh003-preview/PYH-003-openmontage-layout-preview.mp4`. Đây là mẫu không lời, chưa nối vào xưởng hoặc kiểm đồng bộ phụ đề, chưa chuyển renderer chính.

## Chuỗi lỗi tái diễn cần xử lý

1. **Trạm 12 không đạt chất lượng hình.** Bản dựng cũ lặp sơ đồ tế bào gan, có ảnh chưa đúng lời, ô vàng là `source_marker` do renderer vẽ, phụ đề/thẻ nguồn chồng nhau. FLUX chỉ tạo một số ảnh nên đổi model ảnh không xử lý được nguyên nhân lặp. Đã sửa storyboard cho S06 (gan/cơ), S31 (bước đi khám), S34 (dấu hiệu/hành động) ở các lượt draft; chưa nghiệm thu trên render mới. Mã nội bộ và thẻ nguồn vẫn cần xử lý ở renderer.
2. **`revise_production: đầu ra hoặc trạng thái chưa hợp lệ` lặp nhiều lần.** Leader giao Editor một brief có câu “chỉ chẩn đoán”. Agent trả báo cáo, xưởng lại chờ tạo phẩm hoặc đổi trạng thái. Brief cũ tiếp tục có hiệu lực ngay cả sau khi mở lại cổng y khoa. Đã mở lại cổng bằng luồng hiện có, lưu duyệt cũ vào lịch sử, thay brief thành yêu cầu thực thi và nối về `draft_ready`.
3. **`storyboard_design: đầu ra hoặc trạng thái chưa hợp lệ`.** CLI mới chấp nhận storyboard, worker sống lâu lại từ chối. Repair tái hiện bằng cách mô phỏng thư viện anatomy cũ thiếu `alt_ast_tissue_distribution` của S06. `validate_anatomy_subjects` trong `src/healthvideo/domain/storyboard.py` dùng snapshot lúc import; việc snapshot của PID cũ là suy luận có bằng chứng. Restart xưởng giúp qua bước, chưa có bản vá tận gốc cho snapshot. Một vòng Repair còn lỗi vì Leader điền lệnh shell vào danh sách `tests` vốn chỉ nhận đường dẫn pytest hiện có. Lượt sau engineer lại trả chẩn đoán thay vì sửa.
4. **`PermissionError: [WinError 32] … .agent-running` khi `script_review`.** Windows khóa marker lúc dọn. Marker sót làm Repair nhìn PID cha còn sống và tưởng agent còn chạy trong khi PID con đã thoát. Đã dọn marker mồ côi sau khi xác minh PID, sau đó vá `agents.py` retry xóa khi WinError 32/33, giữ kết quả agent; `repair_service.py` dùng định danh PID con khi có job khớp. Các bản vá đã nạp sau restart.
5. **`chấm kịch bản lỗi: Trạm 07 chưa đạt sau các vòng sửa; cần xử lý nhận xét trước khi nộp bác sĩ.`** Đây là lỗi lặp gần nhất. `next_script_action` trả draft trong hạn nhưng ném lỗi khi đủ `MAX_REVIEWS`. Leader có thể giao Writer, nhưng từng đánh dấu validated khi chỉ có hoạt động mới và schema hợp lệ; đã vá yêu cầu critic đạt đối với các ca giao nội dung. Giới hạn Repair trước đây theo revision, đã đổi sang lý do lỗi + trạng thái, giữ trần cho lỗi lặp. Khi hết lượt nó vẫn cần người điều phối, hiện chưa có luồng trả Writer bền vững sau khi hết lượt và chưa hiển thị rõ ai đang xử lý / cần bác sĩ làm gì. Codex từng tạo phiếu sửa và gỡ chặn thủ công theo critic vòng 12 rồi vòng 14. Vòng 14 vướng giọng báo cáo, nhịp chậm và lặp ý (N17/N23/N30/N42–N46); đọc vòng 15 hoặc bản mới hơn trên đúng hash hiện hành trước khi làm tiếp.

## Điểm vào và phần việc còn lại

1. Đọc `topics/logs/<slug>/blocked.txt`, `leader-repair.yaml`, marker `.job-*.json`, log agent mới nhất và `revisions/001/reviews/script-review-log.yaml`. Đối chiếu critic với hash hiện hành. Nếu có job đang sống, quan sát đầu ra trước khi chạy trùng hoặc restart.
2. Ưu tiên luồng Trạm 07 → Writer → Critic. `src/healthvideo/workflows/runner.py` chọn bước qua `next_script_action` và dùng `change_request.pending_note` cho phiếu thực thi; `script_review.py` giữ lịch sử và ngân sách. `repair_service.py` điều phối và xác nhận kết quả. Khi lỗi lặp, giao brief khả thi dựa trên vòng mới nhất, đổi cách sửa hoặc làm rõ việc cần bác sĩ quyết định; đừng chỉ gỡ `blocked.txt` để chạy lại nguyên bản. Phần thay đổi `runner.py` và test tương ứng để tự trả Writer sau khi hết lượt chưa được Codex triển khai.
3. Đưa mascot vào dự án bằng asset manifest và tham chiếu storyboard phù hợp. Kiểm cả bản ngang/dọc, phụ đề và vùng giải phẫu. Với revision đã duyệt, thực hiện qua workflow mở lại cổng; không sửa trực tiếp tạo phẩm đang khóa. Dùng pose có ích như mở đầu, giải thích, cảnh báo hoặc kết, giữ trọng tâm cảnh y khoa.
4. Nối OpenMontage từ `src/healthvideo/workflows/produce.py` ở ranh giới render, giữ audio timing, nguồn/quyền sử dụng, QA, hash render và các cổng. Bản mẫu chỉ chứng minh runtime. Giữ mẫu PYH-003 tách khỏi output duyệt cho tới khi test đầy đủ. Phạm vi Codex đề xuất nhưng chưa được duyệt cụ thể: `produce.py`, mới `src/healthvideo/render/openmontage.py` và `tests/render/test_openmontage.py`.
5. Các thay đổi đáng chú ý: `src/healthvideo/agents.py`, `tests/test_agents.py`, `src/healthvideo/workflows/repair_service.py`, `tests/workflows/test_repair_service.py`, `src/healthvideo/workflows/dashboard.html`. Bộ agents + Repair gần nhất: **84 test đạt**, Ruff sạch. Nhiều thay đổi có từ trước trong worktree; xem diff trước khi sửa. Không commit/push trong lượt bàn giao.

## Ràng buộc

- Không hạ ngưỡng critic, chế approval/PIN, bỏ cổng y khoa/video hoặc tự đăng. Bác sĩ muốn chuỗi tác vụ tiếp tục cho đến khi cần họ quyết định hoặc có sản phẩm, với người phụ trách rõ ràng.
- Bác sĩ muốn tận dụng model OmniRoute hiện có, trừ Claude trong cấu hình worker của xưởng. Claude là người nhận bàn giao phiên này. Codex Sol/Terra/Luna và Gemini Hydrogen/Flash qua AGY từng chạy được tool loop; DeepSeek Web chạy probe API nhưng timeout trong quy trình xưởng.
- Chỉ sửa file đúng phạm vi brief theo AGENTS.md. Giữ thay đổi của người khác và toàn bộ hồ sơ critic; không commit cache, render, audio tạm hoặc API key.
