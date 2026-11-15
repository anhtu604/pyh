# Thiết kế PYH Company 2.0 — Công ty Truyền thông Y học Tự động hóa & Chạy Song song

**Ngày**: 2026-11-15  
**Phạm vi**: Nâng cấp Xưởng video Protect Your Health thành mô hình công ty truyền thông hoàn chỉnh với Trưởng nhóm Điều phối biết phân việc, Chuyên viên Nghiên cứu & Phân tích Kênh (`researcher`) nối Google Sheet + phân tích hiệu quả video đã đăng, 4 vai chuyên sâu mới, và động cơ thực thi song song có kiểm soát GPU/hủy tác vụ treo.

---

## 1. Bất biến an toàn (Không thay đổi)
1. **Hai cổng duyệt của bác sĩ** (`AWAITING_MEDICAL_REVIEW`, `AWAITING_VIDEO_REVIEW`) và **chống tự xuất bản**: không agent hay API nào được phép vượt cổng, chạm PIN hoặc sửa hồ sơ approval.
2. **Chống bịa nguồn & số liệu**: mọi khẳng định y khoa phải trỏ `claim` thật trong `evidence/ledger.yaml`; mọi số liệu kênh phải lấy từ dữ liệu thật (`KET_QUA_KENH`, CSV YouTube/TikTok hoặc form nhập thật trên Dashboard).
3. **Giới hạn model**: không bao giờ khai báo model chứa `opus` hay `astra` trong `profiles/company.yaml`; critic không bao giờ chạy trên cùng `(cli, model)` vừa tạo ra bản nháp/bản dựng cần chấm (kể cả khi failover).

---

## 2. Cơ cấu Nhân sự 15 Vai (Company 2.0 Roster)

### Khối Điều hành & Chiến lược
- `coordinator` (**Trưởng nhóm Điều phối**, `tier: medium`, `steps: [chat]`): Nhận chỉ thị từ bác sĩ, đọc trạng thái toàn công ty / hàng đợi / Tủ đề xuất / Kết quả kênh, phân rã thành danh sách `assignments` giao đúng vai nhân viên hoặc hủy tác vụ treo (`cancel_job`). Tự thực thi ngay các việc an toàn; chỉ giữ xác nhận 1-click khi mở lại dự án đã qua cổng duyệt.
- `coordinator_senior` (**Điều phối viên trưởng · Chuyên sâu**, `tier: hard`, `steps: [chat_deep]`): Xử lý các câu hỏi điều tra nhiều file/revision/log khi `coordinator` đặt `escalate: true`.
- `researcher` (**Chuyên viên Nghiên cứu & Phân tích Kênh**, `tier: medium`, `steps: [topic_research, channel_analytics]`):
  1. Đồng bộ Google Sheet tham khảo của bác sĩ (`1e-WrbZP062LSlNTF8rmpYuHYECgXI10n6HUtiOBfOXg`: `TRANH_CAI_MXH`, `Y_HOC_MOI`, `Trang tính1`), chấm điểm chuẩn 100 điểm theo tab `THANG_DIEM` (Hạng A `>= 80`, B `65–79`, C `< 65`) và lưu hồ sơ `topics/inbox/<slug>.dossier.yaml`.
  2. Chủ động săn đề tài sức khỏe Việt Nam mới theo chỉ thị (`discover_topics_with_agent`).
  3. Phân tích hiệu quả video đã đăng từ tab `KET_QUA_KENH` (nếu Sheet có quyền đọc tab này hoặc qua Sheet cấu hình riêng), CSV YouTube Studio/TikTok Analytics, hoặc form nhập link trên Dashboard -> xuất `topics/channel-insights.yaml` và cập nhật `#channel`.
- `scout` (**Trinh sát Tín hiệu Nhanh**, `tier: bulk`, `steps: [scout]`): Quét nhanh tín hiệu mạng xã hội/xu hướng khi cần.

### Khối Tiền kỳ Y khoa & Kịch bản
- `medical_expert` (**Chuyên gia y học**, `tier: hard`, `steps: [research]`): Kiểm chứng PubMed/PMC/Elsevier, xây `evidence/ledger.yaml`, `explainer/explainer.yaml`, `evidence/expert-brief.md` và trả lời `script/questions.yaml`.
- `writer` (**Biên kịch viral**, `tier: hard`, `steps: [draft, revise_medical]`): Viết lời thoại đời thường `script/script.yaml`, `script/outline.yaml` (hỗ trợ cả `youtube_long` 10–25p và `flexible_v1` cho Shorts/video ngắn), tận dụng thêm `topic/dossier.yaml` nếu xuất phát từ Tủ đề xuất.
- `storyboard_director` (**Đạo diễn Phân cảnh & Đồ họa**, `tier: medium`, `steps: [storyboard_design]`): Tách công việc phân cảnh, `assets/asset-manifest.yaml`, `script/clip-plan.yaml`, visual budget `16–24%`, FLUX prompt và component SVG `video/src/anatomy/` khỏi `writer`.
- `voice_director` (**Đạo diễn Giọng đọc & Phiên âm**, `tier: bulk`, `steps: [voice_prep]`): Chuẩn hóa phiên âm thuật ngữ y khoa và nhịp đọc trong `script/voice-prep.yaml` trước khi tốn credit Vibi TTS.
- `script_critic` (**Kiểm duyệt kịch bản**, `tier: hard`, `steps: [script_review]`): Đánh giá độc lập (`agy / gemini-4-carbon-medium`), khác `(cli, model)` với cả `writer` và `storyboard_director`.

### Khối Sản xuất, Hậu kỳ & Đóng gói Tăng trưởng
- `art_director` (**Đạo diễn hình**, `tier: medium`, `steps: [visual_review]`): Duyệt contact sheet / ảnh FLUX trước dựng.
- `editor` (**Thợ dựng**, `tier: medium`, `steps: [revise_production, revise_product]`): Sửa hình ảnh/nhịp dựng/Remotion khi có góp ý sản xuất hoặc góp ý từ bác sĩ.
- `copywriter` (**Chiến lược Đóng gói & Bài đăng**, `tier: bulk`, `steps: [posts]`): Viết 2–3 phương án tiêu đề, mô tả, mốc chương, thumbnail headline ≤ 5 từ khớp `channel-insights.yaml` và lời hứa mở đầu.
- `shorts_producer` (**Nhà sản xuất Shorts & Reels**, `tier: medium`, `steps: [shorts_plan]`): Thiết kế kế hoạch 9:16 45–90s (`posts/shorts-plan.yaml`) từ video dài hoặc Shorts độc lập, kiểm soát hook 3s đầu, vòng lặp và vùng an toàn phụ đề.
- `product_critic` (**Kiểm định sản phẩm**, `tier: hard`, `steps: [product_review]`): Kiểm tra độc lập video hoàn chỉnh + `posts.yaml` trên `claude / claude-sonnet-5-5` (khác `editor`).
- `feedback_analyst` (**Phân tích ý kiến**, `tier: bulk`, `steps: [feedback_inbox]`): Phân loại góp ý bác sĩ thành việc sửa sản phẩm, sửa xưởng hoặc chuẩn chung.

---

## 3. Lưu ý Quyền Google Sheet (`1e-WrbZP062LSlNTF8rmpYuHYECgXI10n6HUtiOBfOXg`)
- Tài khoản `anhtu604.hmu@gmail.com` hiện có quyền đọc trên bảng tính tham khảo của bác sĩ (lệnh `gsheets mutate add-sheet` trả 403 Forbidden).
- Vì vậy:
  - Các tab đề tài (`TRANH_CAI_MXH`, `Y_HOC_MOI`, `Trang tính1`) được đọc tự động theo chế độ Read-Only.
  - Dữ liệu hiệu quả kênh hỗ trợ đồng bộ 3 đường: đọc tab `KET_QUA_KENH` từ Google Sheet cấu hình (hoặc Sheet riêng do bác sĩ tạo bằng nút trên App), nhập CSV từ YouTube Studio / TikTok Analytics, và nhập/cập nhật từng video ngay trên App.

---

## 4. Kiến trúc Thực thi Song song & Điều khiển Tác vụ Treo
1. **Đa chủ đề (`max_parallel_topics = 3`)**: Khi xưởng chạy vòng lặp, tối đa 3 chủ đề độc lập chạy đồng thời trên thread pool với lock riêng theo `slug`.
2. **Song song nội bộ chủ đề (`parallel_branches = True`)**:
   - Trước cổng Y khoa (`DRAFT_READY`): `storyboard_design` và `voice_prep` chạy song song sau khi `script.yaml` sẵn sàng, sau đó mới vào `script_review`.
   - Sau cổng Y khoa (`MEDICALLY_APPROVED` / `PRODUCTION_IN_PROGRESS`): `posts` (`copywriter`) và `shorts_plan` (`shorts_producer`) chạy song song với nhánh `produce`.
3. **Bảo vệ RTX 3060 VRAM (`gpu_mutex`)**: Mọi lượt `produce` chạy qua khóa `cache/gpu-mutex.lock` đảm bảo chỉ tối đa 1 tác vụ GPU nặng chạy tại một thời điểm trong khi các agent CLI khác vẫn làm việc song song bình thường.
4. **Hủy tác vụ treo (`cancel_running_job`)**: Mỗi lần gọi CLI ghi nhận PID tiến trình con + OS creation token trong `.job-<job_id>.json`. Khi bác sĩ bấm hủy trên UI hoặc ra lệnh cho Leader, hệ thống chỉ chấm dứt cây tiến trình con đã xác minh danh tính, tuyệt đối không làm sập App hay Factory.
