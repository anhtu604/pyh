# Bàn giao — 2026-10-27 (Claude Code → Antigravity)

Đọc `AGENTS.md` trước. File này chỉ ghi **trạng thái hiện tại và việc còn dở**.

## Cập nhật 2026-11-07
Đã bỏ khóa nghiệm thu 4 giai đoạn: xưởng chuyển sang sản xuất, bác sĩ nghiệm thu trên sản phẩm thật qua hai cổng và tab **Ý kiến**. Các mục nói "chờ đủ 4 chuẩn" bên dưới không còn áp dụng.

## Mục tiêu hiện tại
Theo thiết kế **hoàn thiện xưởng trước, sản xuất sau** (`docs/superpowers/specs/2026-10-25-factory-first-stage-acceptance-design.md`, trạng thái: đã duyệt): hoàn thiện công cụ xưởng và trình bác sĩ nghiệm thu từng giai đoạn 1 → 4 ngay trong `healthvideo app` bằng mẫu `TEST` phi y khoa trước khi mở chạy sản xuất A–Z. Dự án **gout** (`projects/gout-tinh-the-urat`) được giữ nguyên, **chờ sau khi bác sĩ chấp nhận đủ 4 chuẩn giai đoạn** mới mở vòng sửa sản phẩm.

## Đã xong
- **Nền trước đó (`master`, tới `99ffece` + app dashboard)**:
  - `baccb32` Hình cơ chế có nhãn tiếng Việt, `beats` theo từ khóa, QA nhịp hình ≤ 6 s, whiteboard tách dải chữ/ảnh, FLUX 3 ứng viên + bước agent `visual_review`.
  - `d913c25` Văn phong tự nhiên (`prompts/draft.md`, `prompts/style_examples.vi.md`, lint `domain/script_style.py`), từ điển + QA phát âm, `produce --tts` mặc định `silent`.
  - `43a4e88` Giọng nhân bản của bác sĩ qua `tts/vibi.py` (`VibiTTS`, `vibi_minimax`, `speech-2.8-hd`).
  - `99ffece` Lý do `review reopen` tới agent `revise_medical`; `agy` headless chạy được công cụ shell; `healthvideo app` xem sản phẩm, góp ý từng dòng và quyết định cổng bằng PIN.
- **4 gói hoàn thiện xưởng + tích hợp (nhánh `factory/integration`)**:
  1. **Gói A — Cache TTS trả phí + giới hạn retry sản xuất**: `_synthesize_cached_line` dùng lại audio đã kiểm SHA-256 + `inspect_wav` cho cả `vibi_minimax` và ElevenLabs (không nhân đôi `audio/tts-usage.json`); phân loại WAV nhà cung cấp hỏng/im lặng thành `RuntimeError` đã làm sạch; `workflows/production_retry.py` dừng ngay lỗi xác định (`ValueError`) tới khi đổi fingerprint đầu vào, và giới hạn lỗi tạm thời (`OSError`/`RuntimeError`) tối đa 3 lần mỗi fingerprint với backoff 120 s → 600 s.
  2. **Gói B — Khu thử + tiêu chuẩn có phiên bản + nghiệm thu 4 giai đoạn**: `workflows/factory_trials.py` cô lập mẫu thử ngoại tuyến dưới `cache/factory-test/` (không chạm `projects/` hay `topics/queue.yaml`, không gọi dịch vụ trả phí); `workflows/factory_standards.py` lưu nháp/chấp nhận chuẩn theo thứ tự giai đoạn 1 → 4 bằng PIN bác sĩ, đóng băng snapshot `revisions/<rev>/workflow/standards.yaml` cho project mới và chặn **Bật xưởng** khi chưa đủ 4 chuẩn; `runner.py` nối `prompt_block(root, slug=entry.slug)` để dùng đúng snapshot chuẩn của project và chỉ lấy góp ý `chung` + đúng `slug`.
  3. **Gói C — Vận hành chủ đề, khôi phục lỗi và thư viện ảnh có nguồn trong app**: `workflows/dashboard_operations.py` + `workflows/asset_library.py` thêm tab **Hàng đợi** (thêm chủ đề, xem bước kế + ước tính cache + `retry_after`, cho phép thử lại khi đã sửa đầu vào, mở lại cổng y khoa bằng PIN giữ lịch sử superseded) và tab **Thư viện** (lọc/tìm FLUX, SVG, contact sheet, thumbnail, ảnh nhập; chọn file raster tại máy chủ qua ID một lần, kiểm provenance/giấy phép/hash và gắn vào cảnh `whiteboard`).
  4. **Gói D (+ sửa `UrateDeposition` ở Gói E) — Hình giải phẫu có khối**: nâng 5 component gout (`UrateFluid`, `UrateCrystalCloseUp`, `InflammationSignal`, `UrateDeposition`, `GoutFootOverview`) lên đồ họa phẳng 4 tông có khối (`shade.ts`, `palette.ts`), dịch khớp trong `UrateDeposition` ôm sát đường cong màng hoạt dịch không còn mép cắt thẳng.
- **Kiểm chứng Muse AI bằng tài khoản người dùng**: `status: needs_login` (chưa kiểm trên phiên đăng nhập của người dùng; tác nhân không tự đăng nhập hay lưu cookie/token). Đường tích hợp đang dùng: sinh ảnh bằng FLUX hiện có hoặc người dùng/agent xuất file raster từ Muse rồi nhập qua mục **Nhập ảnh có nguồn** trong tab **Thư viện** của app (kèm nguồn, prompt, giấy phép, URL và SHA-256).

## Đang chặn (gout — bảo lưu tới sau khi đủ 4 chuẩn xưởng)
- Dự án `projects/gout-tinh-the-urat` đang dừng ở bước `produce` do `visual budget failed: chart_crop=2494/9866 frames outside 15-25%` (≈25,3% > 25% sau khi có timing TTS thật).
- Theo quyết định thứ tự xưởng trước: **chưa sửa storyboard gout, chưa chạy lại TTS/render cho gout** cho tới khi bác sĩ nghiệm thu xong 4 giai đoạn của xưởng. Lựa chọn giữ `chart_crop` 15–25% và mở lại cổng y khoa để chỉnh storyboard vẫn được bảo lưu cho vòng sản phẩm gout sau.

## Tài liệu tham chiếu
- Spec & kế hoạch nghiệm thu xưởng: `docs/superpowers/specs/2026-10-25-factory-first-stage-acceptance-design.md`, `docs/superpowers/plans/2026-10-25-factory-first-stage-acceptance.md`.
- Ghi nhận kiểm chứng Muse AI: `docs/reference/muse-integration-findings.md` (`status: needs_login`).
- Hướng dẫn nghiệm thu xưởng trong app: `docs/factory-acceptance-guide.md`.
- Kịch bản mẫu bác sĩ đã duyệt văn phong ("ok làm đi"): `cache/review/gout-kich-ban-v2.md` (21 dòng, claim M01–M08, mục ⚑ giữ như đã viết, danh sách 6 ý mở rộng để đạt ~10 phút).
- Nghe thử giọng nhân bản: `cache/voice-test/clone/index.html` (hd vs turbo). Whisper nghe "u-rát" thành "u-zát" (có thể do giọng Bắc) — **chờ bác sĩ xác nhận**, và chờ chọn hd/turbo.
- API vibi: `docs/reference/vibi-api/` (header `xi-api-key` + **bắt buộc** `User-Agent`; TTS bất đồng bộ: POST → poll `/v1/history/{id}` → tải `result.audio_url`).

## Việc tiếp theo
1. **Bác sĩ nghiệm thu giai đoạn 1 trong app (`healthvideo app` / lối tắt Desktop "Xưởng video")**: mở mục **Nghiệm thu xưởng**, tạo và chạy mẫu `TEST` giai đoạn 1 (`1 · Chủ đề → kịch bản`), xem kịch bản/bằng chứng mẫu, ghi chuẩn nháp và bấm **Chấp nhận chuẩn** bằng PIN.
2. Sau khi có phản hồi hoặc chấp nhận giai đoạn 1, lần lượt nghiệm thu và chốt chuẩn giai đoạn **2 → 3 → 4** trong app.
3. Khi đủ **4 chuẩn đã chấp nhận**, nút **Bật xưởng** trong app mới mở cho sản xuất A–Z.
4. **Vòng sản phẩm gout (sau khi đủ 4 chuẩn)**: trình bác sĩ xử lý `chart_crop` (mở lại cổng y khoa trong tab Hàng đợi hoặc điều chỉnh theo quyết định bác sĩ), chạy lại `produce` tận dụng cache TTS theo dòng và duyệt cổng video trong app.
5. Kiểm chứng Muse AI trên trình duyệt nếu bác sĩ đã đăng nhập sẵn phiên Muse (`status` hiện tại: `needs_login`, không chặn nghiệm thu xưởng).

## Ý tưởng chưa làm (2026-10-25, tham khảo Muse AI / VanTrong08 AI Studio)
Chỉ là tư vấn, **chưa có code hay quyết định nào được chốt**. Không làm trước khi bác sĩ duyệt gout.

**Dùng Muse AI (tài khoản của người dùng) cho:**
- Ảnh tham chiếu giữ nhân vật/mascot nhất quán; ảnh minh họa không chú thích (bối cảnh, ẩn dụ, thumbnail), tạo hàng loạt.
- Tùy chọn: ảnh→video 5–8 s làm b-roll phá cảnh hình đứng lâu. **Cần bác sĩ đồng ý mở lại video AI** (spec §2, §4.2 đang loại Veo/AI clip).
- Không dùng cho hình giải phẫu/cơ chế/số liệu (giữ SVG + Remotion). Không để tool tự ghép video cuối; không dùng tab "Codex AI" của tool.
- Cách tích hợp tối thiểu: lấy prompt từ `clip_plan`/`asset_manifest` → tạo tay trên Muse → lưu vào `projects/<slug>/assets/muse/` (không commit) → ghi nguồn "Muse AI", ngày, prompt, giấy phép trong asset manifest → đưa vào contact sheet cổng video. Chưa viết code gọi tool.
- Cần kiểm: điều khoản Muse về dùng thương mại trên kênh kiếm tiền; VanTrong08 là app bên thứ ba, đừng đưa API key/tài khoản vào repo.
- Thử trước trên gout (ảnh mở đầu không liên quan bác sĩ đã chê).

**Học từ giao diện VanTrong08 cho `healthvideo app`** (`workflows/dashboard.html`, `dashboard.py`):
1. Tab **Thư viện** dạng lưới thumbnail theo project: nhãn loại, tên file, prompt, kích thước, giờ tạo, nút Mở file/Thư mục, lọc loại + project, tìm theo prompt (gom ảnh FLUX 3 ứng viên, hình SVG, contact sheet, thumbnail). Ưu tiên cao nhất.
2. Thanh trạng thái trên cùng: xưởng chạy/dừng, agent hiện tại (Codex/agy), quota, credit vibi.
3. Chia tab ngang (~4–5, không phải 10): Tổng quan, Hàng đợi, Duyệt, Thư viện, Cài đặt.
4. Tab Ảnh tham chiếu (mascot, bảng nhân vật, palette) và trang Hướng dẫn ngắn trong app.
5. Sheet nhân vật nhiều tư thế trên nền trắng để giữ nhất quán giữa các video.
- Không học: proxy, kích hoạt key, tạo hàng loạt không qua cổng duyệt.
- Khi làm: worktree/nhánh riêng, test, một dòng trong bảng tiến độ README (xem quy tắc dưới).

## Quy tắc bắt buộc (ngoài AGENTS.md)
- **PIN chỉ bác sĩ gõ, trong TTY của mình hoặc trong app cục bộ** (`healthvideo app`, máy chủ chỉ nghe 127.0.0.1, kiểm PIN bằng `verify_pin`, không lưu/không log). Agent không bao giờ nhận PIN qua chat/tham số/biến môi trường/file, không tự duyệt cổng, không xuất bản.
- Góp ý của bác sĩ là chuẩn lâu dài: không xóa/sửa mục cũ trong `profiles/doctor-feedback.yaml` (chỉ thêm). Chuẩn giai đoạn đã chấp nhận lưu append-only tại `profiles/factory-standards.yaml`; góp ý riêng chỉ áp dụng cho đúng `slug`, ghi chú `chung` áp dụng toàn kênh.
- Không in/chép API key. `.env` chứa `VIBI_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_*` — không commit.
- NCBI đang chặn IP người dùng → dùng Europe PMC, **không** tìm cách lách. Toàn văn có bản quyền không vào Git.
- Không chép code/prompt/SFX từ bộ trả phí `AI V1.1/`.
- Bác sĩ muốn **thao tác tay tối thiểu** và **không muốn dùng PowerShell**: mọi thao tác qua app (bấm đúp "Xưởng video" trên Desktop).
- Mỗi việc: worktree/nhánh riêng → test (`PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`, `ruff check src tests`, `corepack pnpm --dir video test`, `corepack pnpm --dir video typecheck`) → squash-merge vào `master` kèm một dòng trong bảng tiến độ README.
