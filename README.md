# Protect Your Health

## Mục tiêu

Xây dựng luồng có thể kiểm tra để biến hồ sơ và luận điểm đã được bác sĩ duyệt
thành video y tế dự phòng tiếng Việt dọc 1080 × 1920.

## Trạng thái hiện tại

Project scaffold, claim ledger, author-owned script, read-aloud QA, Remotion
vertical preview, production cache và hai cổng duyệt của bác sĩ đã hoạt động.

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
| 7 | TTS giả lập, manifest cache và render workflow | complete | `python -m pytest` (61 passed); `ruff check src tests tools`; `pnpm --dir video test` (11 passed); `pnpm --dir video typecheck` | `feat: add cached production workflow`; `fix: make production failures transactional`; `fix: publish production runs atomically`; `fix: converge production publish over a damaged run` |
| 8 | Hai cổng duyệt có hash và audit trail | complete | `python -m pytest tests/workflows/test_review.py tests/domain/test_project.py -v` (14 passed); `python -m pytest` (79 passed); `python -m ruff check src tests tools`; `pnpm --dir video test` (11 passed); `pnpm --dir video typecheck` | `feat: enforce doctor review gates` |
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
healthvideo review medical projects/2026/09/muoi-va-huyet-ap --reviewer "BS An" --note "Đã đối chiếu số liệu"
healthvideo review video projects/2026/09/muoi-va-huyet-ap --reviewer "BS An"
healthvideo status projects/2026/09/muoi-va-huyet-ap
```

## Workflow

Author brief → evidence ledger → medical review → script/storyboard → production
→ video review → publication package. Cả hai cổng duyệt của bác sĩ là bắt buộc.
`produce` chỉ nhận dự án ở `script_approved`; nếu dự án đã ở
`awaiting_video_review`, nó chỉ trả lại video cache khi hash đầu vào vẫn khớp.

## Cổng duyệt và audit trail

`healthvideo review medical` chỉ chạy ở `awaiting_medical_review`, gắn hash của
`evidence/ledger.yaml` và `script/script.yaml` rồi chuyển `script_approved`.
`healthvideo review video` chỉ chạy ở `awaiting_video_review`, gắn hash của MP4 và
`render-input.json` trong run đang hoạt động rồi chuyển `approved_to_publish`.
Mỗi lần duyệt ghi một `ReviewRecord` bất biến (`reviews/medical-<uuid>.yaml`,
`reviews/video-<uuid>.yaml`) gồm người duyệt, thời điểm có múi giờ, quyết định,
ghi chú và hash artifact. Cả hai lệnh bắt buộc `--reviewer`, nhận `--note`, và
yêu cầu gõ `APPROVE` trên terminal trừ khi có `--yes`; xác nhận chỉ nằm ở lớp CLI
nên `approve_medical`/`approve_video` vẫn thuần và test được offline.

Tài liệu YAML/JSON được hash theo nghĩa (canonical JSON), MP4 hash theo byte, nên
định dạng lại file không làm mất hiệu lực duyệt còn sửa nội dung thì có.
Khi artifact đã duyệt đổi hoặc biến mất, `healthvideo status` báo
`approval_stale=true` và `produce` từ chối chạy với lỗi `medical approval is stale`;
`package` (Task 9) dùng lại `ensure_approval_current` cho cổng video.

## Kiểm thử gần nhất

`python -m pytest` (79 passed); `python -m ruff check src tests tools`;
`pnpm --dir video test` (11 passed); `pnpm --dir video typecheck`. Hai cổng duyệt,
audit trail và test approval stale (`status` báo `approval_stale=true`, `produce`
từ chối chạy) đều PASS offline, không cần TTY. Bộ dev ghim `jsonschema==4.26.0`
để kiểm tra các contract JSON Schema đã xuất.

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
đăng. Chưa có intake nguồn, TTS thực, packaging hay installer.

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
pnpm --dir video render --props ../projects/sample/renders/<input_hash>/render-input.json --output ../projects/sample/renders/<input_hash>/video.mp4
```

## Production cache

`healthvideo produce <project> --tts silent` kết hợp canonical JSON của script,
storyboard, profile giọng tác giả và provider thành SHA-256. Một lần render hợp lệ
được publish nguyên khối ở `renders/<input_hash>/` (WAV, `render-input.json`, MP4,
manifest); `project.yaml.artifact_hashes.production` chọn run đang hoạt động. Khi
run đang hoạt động cùng khớp hash, lệnh tái sử dụng MP4 và không gọi Remotion.
`--dry-run` chỉ in argv Remotion; không tạo WAV/MP4/input/manifest và không đổi state.
Dry-run chỉ hợp lệ ở `script_approved`, hoặc ở `awaiting_video_review` với cache
chính xác. Khi render thật, run được tạo trong staging sibling rồi đổi tên thư mục
nguyên tử sau khi renderer trả kết quả hợp lệ; lỗi TTS/render giữ nguyên state
`script_approved` để có thể chạy lại. Nếu một run đã publish nhưng không còn đủ
artifact, lần chạy sau publish đè lên nó và hội tụ về trạng thái đúng. Fixture golden tạo WAV im lặng trong test/smoke
setup, không lưu audio đã sinh vào Git.

## Tài liệu

- [Thiết kế hệ thống](docs/superpowers/specs/2026-09-07-preventive-health-video-system-design.md)
- [Kế hoạch MVP](docs/superpowers/plans/2026-09-07-preventive-health-video-mvp.md)
