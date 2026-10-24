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

## Tài liệu tham chiếu
- Kịch bản mẫu bác sĩ đã duyệt văn phong ("ok làm đi"): `cache/review/gout-kich-ban-v2.md` (21 dòng, claim M01–M08, mục ⚑ giữ như đã viết, danh sách 6 ý mở rộng để đạt ~10 phút).
- Nghe thử giọng nhân bản: `cache/voice-test/clone/index.html` (hd vs turbo). Whisper nghe "u-rát" thành "u-zát" (có thể do giọng Bắc) — **chờ bác sĩ xác nhận**, và chờ chọn hd/turbo.
- API vibi: `docs/reference/vibi-api/` (header `xi-api-key` + **bắt buộc** `User-Agent`; TTS bất đồng bộ: POST → poll `/v1/history/{id}` → tải `result.audio_url`).

## Việc tiếp theo
1. ~~Bác sĩ chạy `review reopen`~~ (đã xong 15:08). **Bác sĩ chỉ cần bật lại xưởng** từ cửa sổ PowerShell của mình:
   ```
   .\.venv\Scripts\healthvideo.exe xuong --background
   ```
   Xưởng nền phải do bác sĩ bật từ cửa sổ của mình (bật từ shell của agent sẽ chết khi phiên agent kết thúc).
2. Theo dõi `topics/logs/xuong.log`; nếu dừng thì đọc `projects/gout-tinh-the-urat/blocked-reason.md` / `blocked.txt`.
3. Tới cổng y khoa → bác sĩ chạy `.\.venv\Scripts\healthvideo.exe duyet` (một phím + PIN). Tới cổng video cũng vậy.
4. Sau khi bác sĩ duyệt gout: mã hóa chuẩn đó thành QA (vd. luật thẻ nguồn không dồn cuối video) rồi mới mở hàng đợi chủ đề.
5. ~~Việc nhỏ treo~~: đã chuyển `api-docs/` → `docs/reference/vibi-api/` và dọn `.claude/worktrees/` (giữ các nhánh git). Còn `.worktrees/m1-workflow-kernel` chưa đụng.

## Quy tắc bắt buộc (ngoài AGENTS.md)
- **PIN chỉ bác sĩ gõ trong TTY của mình.** Agent không bao giờ nhận PIN qua chat/tham số/biến môi trường/file, không tự duyệt cổng, không xuất bản.
- Không in/chép API key. `.env` chứa `VIBI_API_KEY`, `ELEVENLABS_API_KEY`, `TELEGRAM_*` — không commit.
- NCBI đang chặn IP người dùng → dùng Europe PMC, **không** tìm cách lách. Toàn văn có bản quyền không vào Git.
- Không chép code/prompt/SFX từ bộ trả phí `AI V1.1/`.
- Bác sĩ muốn **thao tác tay tối thiểu**: chỉ đưa `duyet`/`xuong`, không đưa chuỗi lệnh dài trừ khi bắt buộc (như lệnh reopen ở trên); kiểm tra `--help` trước khi đưa lệnh.
- Mỗi việc: worktree/nhánh riêng → test (`PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`, `ruff check src tests`, `corepack pnpm --dir video test`, `corepack pnpm --dir video typecheck`) → squash-merge vào `master` kèm một dòng trong bảng tiến độ README.
