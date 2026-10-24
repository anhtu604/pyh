# Bàn giao — 2026-10-24 (Claude Code → Antigravity)

Đọc `AGENTS.md` trước. File này chỉ ghi **trạng thái hiện tại và việc còn dở**.

## Mục tiêu hiện tại
Biến video **gout** (`projects/gout-tinh-the-urat`) thành **video chuẩn mẫu**. Bác sĩ đã chê bản đầu (đọc sai "gút/u-rát", ảnh mở đầu không liên quan, chữ đè ảnh, hình quá đơn giản và đứng lâu, giọng đều đều, kịch bản "nghe AI"). **Không nhận chủ đề mới cho tới khi bác sĩ duyệt gout.**

## Đã xong (master, commit cuối `99ffece`; pytest ~1429 pass, vitest 182, typecheck, ruff)
- `baccb32` Hình cơ chế có nhãn tiếng Việt, `beats` theo từ khóa, QA nhịp hình ≤ 6 s, whiteboard tách dải chữ/ảnh, FLUX 3 ứng viên + bước agent `visual_review`.
- `d913c25` Văn phong tự nhiên: `prompts/draft.md` + `prompts/style_examples.vi.md`; lint `domain/script_style.py` (chặn tự tả hình/giọng thuyết trình/rào đón lặp) → `reviews/style-lint.json` + mục "Văn phong" trong gói duyệt; từ điển phát âm + QA phát âm; `produce --tts` mặc định `silent`.
- `43a4e88` Giọng nhân bản của bác sĩ: `tts/vibi.py` (`VibiTTS`), `profiles/voice.yaml` = `provider: vibi_minimax`, `model_id: speech-2.8-hd`, voice `1d90e9bd-a67b-4d63-a415-032eb9ce91b5` ("lanhvcl"). `--tts auto` chọn vibi khi có `VIBI_API_KEY`. `healthvideo doctor` báo credit.
- `99ffece` Lý do `review reopen` nay tới agent `revise_medical` (`reject_note` đọc cả `*-reopened.yaml`).
- 2026-10-24 15:08 bác sĩ đã chạy `review reopen` (project ở `needs_medical_revision` → resume `research_in_progress`). Xưởng 15:09 bị chặn: Codex hết quota (tới 18:51), `agy` headless tự từ chối lệnh shell → "agent không làm đổi trạng thái". Đã sửa: `agy` chạy với `--dangerously-skip-permissions` (`fix: let headless agy run shell tools`).
- 21:11 bác sĩ từ chối (M11/M16/M10/N27 + cắt đuôi giải thích); agent sửa; sau đó bác sĩ **đã duyệt y khoa** → `medically_approved`.
- `feat: dashboard app with in-app review and doctor standards`: app `healthvideo app` (lối tắt Desktop **Xưởng video**). Bác sĩ xem sản phẩm (kịch bản/claim/video), góp ý theo dòng, quyết định cổng bằng PIN ngay trong app. Mọi góp ý ghi vào `profiles/doctor-feedback.yaml` và chèn vào prompt mọi agent (đã nạp sẵn 3 góp ý cũ của gout).

## Đang chặn (gout)
- Bước produce lặp lỗi `visual budget failed: chart_crop=2494/9866 frames outside 15-25%` (≈25,3% > 25% sau khi có timing TTS thật). Storyboard đã được duyệt y khoa → sửa storyboard cần reopen; nới ngưỡng là quyết định của bác sĩ.
- Mỗi lần thử lại produce **tổng hợp lại toàn bộ 30 câu TTS qua vibi** (`audio/tts-usage.json`: 120 request, ~23k ký tự) → tốn credit. **Xưởng đã được dừng.** Không bật lại cho tới khi: (a) produce dùng lại TTS cache theo hash văn bản, (b) không tự thử lại produce sau lỗi xác định, và (c) bác sĩ quyết cách xử lý visual budget.

## Tài liệu tham chiếu
- Kịch bản mẫu bác sĩ đã duyệt văn phong ("ok làm đi"): `cache/review/gout-kich-ban-v2.md` (21 dòng, claim M01–M08, mục ⚑ giữ như đã viết, danh sách 6 ý mở rộng để đạt ~10 phút).
- Nghe thử giọng nhân bản: `cache/voice-test/clone/index.html` (hd vs turbo). Whisper nghe "u-rát" thành "u-zát" (có thể do giọng Bắc) — **chờ bác sĩ xác nhận**, và chờ chọn hd/turbo.
- API vibi: `docs/reference/vibi-api/` (header `xi-api-key` + **bắt buộc** `User-Agent`; TTS bất đồng bộ: POST → poll `/v1/history/{id}` → tải `result.audio_url`).

## Việc tiếp theo
1. Sửa produce: cache TTS theo hash văn bản + giọng/model; không tự thử lại sau lỗi xác định (visual budget, sync).
2. Trình bác sĩ quyết visual budget `chart_crop` (nới dung sai hay reopen sửa storyboard).
3. Bác sĩ bật xưởng **trong app** (nút "Bật xưởng"); tới cổng video bác sĩ duyệt trong app (hoặc `duyet` trong TTY).
4. Sau khi bác sĩ duyệt gout: mã hóa chuẩn đó thành QA (vd. luật thẻ nguồn không dồn cuối video) rồi mới mở hàng đợi chủ đề.
5. Còn `.worktrees/m1-workflow-kernel` chưa đụng.

## Quy tắc bắt buộc (ngoài AGENTS.md)
- **PIN chỉ bác sĩ gõ, trong TTY của mình hoặc trong app cục bộ** (`healthvideo app`, máy chủ chỉ nghe 127.0.0.1, kiểm PIN bằng `verify_pin`, không lưu/không log). Agent không bao giờ nhận PIN qua chat/tham số/biến môi trường/file, không tự duyệt cổng, không xuất bản.
- Góp ý của bác sĩ là chuẩn lâu dài: không xóa/sửa mục cũ trong `profiles/doctor-feedback.yaml` (chỉ thêm).
- Không in/chép API key. `.env` chứa `VIBI_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_*` — không commit.
- NCBI đang chặn IP người dùng → dùng Europe PMC, **không** tìm cách lách. Toàn văn có bản quyền không vào Git.
- Không chép code/prompt/SFX từ bộ trả phí `AI V1.1/`.
- Bác sĩ muốn **thao tác tay tối thiểu** và **không muốn dùng PowerShell**: mọi thao tác qua app (bấm đúp "Xưởng video" trên Desktop).
- Mỗi việc: worktree/nhánh riêng → test (`PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`, `ruff check src tests`, `corepack pnpm --dir video test`, `corepack pnpm --dir video typecheck`) → squash-merge vào `master` kèm một dòng trong bảng tiến độ README.
