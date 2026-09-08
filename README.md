# Protect Your Health

## Mục tiêu

Xây dựng luồng có thể kiểm tra để biến hồ sơ và luận điểm đã được bác sĩ duyệt
thành video y tế dự phòng tiếng Việt dọc 1080 × 1920.

## Trạng thái hiện tại

Project scaffold, claim ledger, author-owned script, read-aloud QA, Remotion
vertical preview và production cache đã hoạt động.

## Milestone

MVP hoàn thành vertical slice từ author brief, evidence, kịch bản và storyboard
đến TTS giả lập, render, hai cổng duyệt và gói xuất bản.

## Tiến độ nhiệm vụ

| Task | Deliverable | Status | Tests | Commit |
| --- | --- | --- | --- | --- |
| 1 | Bootstrap repo và CLI có thể kiểm thử | complete | `pytest tests/test_cli.py`; `ruff check src tests` | `chore: bootstrap healthvideo CLI` |
| 2 | Domain model, state machine và storage nguyên tử | complete | `python -m pytest tests/domain/test_project.py -v`; `python -m pytest tests/storage/test_files.py -v`; `python -m ruff check src tests` | `feat: add project state and atomic storage` |
| 3 | Project scaffold và author-owned voice | complete | `python -m pytest tests/workflows/test_create_project.py tests/test_cli.py -v` | `feat: scaffold projects from doctor briefs` |
| 4 | Claim ledger, human script và read-aloud QA | complete | `python tools/export_schemas.py`; `python -m pytest tests/domain/test_script.py tests/qa/test_script_qa.py tests/contracts/test_schemas.py -v` | `feat: validate evidence-linked human scripts` |
| 5 | Storyboard, evidence highlight và render contract | complete | `python tools/export_schemas.py`; `python -m pytest tests/render/test_input.py tests/contracts/test_schemas.py -v` | `feat: define storyboard render contract` |
| 6 | Remotion composition 9:16 và visual regression cơ bản | complete | `pnpm --dir video test` (11 passed); `pnpm --dir video typecheck`; still 1080 × 1920 | `feat: render vertical whiteboard scenes` |
| 7 | TTS giả lập, manifest cache và render workflow | complete | `python -m pytest tests/tts/test_silent.py tests/workflows/test_produce.py -v`; `python -m ruff check src tests` | `feat: add cached production workflow` |
| 8 | Hai cổng duyệt có hash và audit trail | planned | — | — |
| 9 | Gói xuất bản và golden end-to-end test | planned | — | — |
| 10 | Installer Windows và environment doctor | planned | — | — |

## Kiến trúc

Python CLI điều phối artifact YAML/JSON theo schema. Domain thuần Python tách
khỏi TTS và renderer; Remotion nhận `render-input.json` bất biến.

## Quick start

```powershell
python -m pip install -e ".[dev]"
healthvideo version
healthvideo project new muoi-va-huyet-ap --title "Ăn mặn và tăng huyết áp"
healthvideo produce tests/fixtures/golden-project --tts silent --dry-run
```

## Workflow

Author brief → evidence ledger → medical review → script/storyboard → production
→ video review → publication package. Cả hai cổng duyệt của bác sĩ là bắt buộc.
`produce` chỉ nhận dự án ở `script_approved`; nếu dự án đã ở
`awaiting_video_review`, nó chỉ trả lại video cache khi hash đầu vào vẫn khớp.

## Kiểm thử gần nhất

`python -m pytest tests/tts/test_silent.py tests/workflows/test_produce.py -v`
(7 passed); silent TTS, cache manifest và state gate đều chạy offline. Bộ dev ghim
`jsonschema==4.26.0` để kiểm tra các contract JSON Schema đã xuất.

## Quyết định

Tiếng Việt trước; AI chỉ chấp bút từ ý kiến bác sĩ; mọi claim y khoa cần định
danh và nguồn đã xác minh; không tự động đăng video. Read-aloud QA gắn cờ câu
vượt 32 từ, claim không có trong ledger và cụm từ máy móc bị cấm.

## Giới hạn hiện tại

Đã có domain model, schema JSON, storyboard, render input bất biến, composition
`HealthVideo` và cache render SHA-256. Render contract cố định khung hình dọc 1080 × 1920 ở 30 fps;
storyboard phải có cảnh liên tiếp, không chồng lấp và tổng thời lượng 45–90 giây.
Composition dùng tối thiểu 1.350 frame, render whiteboard/subtitle hoặc ảnh bằng
chứng với bôi vàng; Zod kiểm tra điều kiện `x + width <= 1`, `y + height <= 1`
và dữ liệu bắt buộc cho `evidence_highlight` trước render. Mỗi dự án mới lưu
`author-brief.yaml` ở thư mục gốc dự án. `SilentTTS` chỉ ghi WAV im lặng, xác định
(mono PCM 16-bit, 24 kHz), phục vụ test và smoke render — chưa phải giọng đọc để
đăng. Chưa có intake nguồn, TTS thực, review, packaging hay installer.

## Remotion preview

Frame kiểm tra gần nhất: [frame-001.png](tests/artifacts/frame-001.png) (1080 ×
1920, nền trắng ngà, chữ than, bôi vàng). Đã chạy:

```powershell
pnpm --dir video test
pnpm --dir video typecheck
pnpm --dir video exec remotion still src/index.ts HealthVideo ../tests/artifacts/frame-001.png --props=../tests/fixtures/render-input.json --frame=120 --overwrite
```

Ở Remotion `4.0.522`, JSON props phải truyền bằng `--props`; tham số vị trí thứ
ba là đường dẫn PNG output. Render video dùng composition `HealthVideo`:

```powershell
pnpm --dir video render --props ../projects/sample/render-input.json --output ../projects/sample/renders/video.mp4
```

## Production cache

`healthvideo produce <project> --tts silent` kết hợp canonical JSON của script,
storyboard, profile giọng tác giả và provider thành SHA-256. Khi `renders/manifest.json`
và `renders/video.mp4` cùng khớp hash, lệnh tái sử dụng video và không gọi Remotion.
`--dry-run` chỉ in argv Remotion; không tạo WAV/MP4/input/manifest và không đổi state.
Fixture golden có WAV im lặng tổng hợp để Remotion smoke test không cần mạng.

## Tài liệu

- [Thiết kế hệ thống](docs/superpowers/specs/2026-09-07-preventive-health-video-system-design.md)
- [Kế hoạch MVP](docs/superpowers/plans/2026-09-07-preventive-health-video-mvp.md)
