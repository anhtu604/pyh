# Protect Your Health

## Mục tiêu

Xây dựng luồng có thể kiểm tra để biến hồ sơ và luận điểm đã được bác sĩ duyệt
thành video y tế dự phòng tiếng Việt dọc 1080 × 1920.

## Trạng thái hiện tại

MVP đã hoàn thành: project scaffold, claim ledger, author-owned script,
read-aloud QA, Remotion vertical preview, production cache, hai cổng duyệt của
bác sĩ, gói xuất bản, Windows installer và environment doctor. Plan tiếp theo:
`evidence-ingestion`.

## Milestone

MVP complete: vertical slice từ author brief, evidence, kịch bản và storyboard
đến TTS giả lập, render, hai cổng duyệt, gói xuất bản và kiểm tra Windows.

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
| 8 | Hai cổng duyệt có hash và audit trail | complete | `python -m pytest tests/workflows/test_review.py tests/workflows/test_produce.py tests/storage -v` (35 passed); `python -m pytest -v` (83 passed); `python -m ruff check src tests tools`; `pnpm --dir video test` (11 passed); `pnpm --dir video typecheck` | `feat: enforce doctor review gates`; `fix: bind the medical gate to the storyboard` |
| 9 | Gói xuất bản và golden end-to-end test | complete | `python -m pytest tests/e2e/test_golden_project.py -v` (15 passed); `python -m pytest -v` (99 passed); `python -m ruff check src tests tools`; `pnpm --dir video test` (11 passed); `pnpm --dir video typecheck` | `feat: package reviewed videos for publishing`; `fix: harden publication package integrity` |
| 10 | Installer Windows và environment doctor | complete | `python -m pytest -v` (106 passed); `ruff`; video test/typecheck; `install/doctor.ps1` | `feat: add Windows installer and diagnostics` |
| Final review | Approval, asset, package và Windows render hardening | complete | `python -m pytest -v` (122 passed); Ruff; video test (12 passed)/typecheck; real Windows golden render 1080 × 1920, 30 fps, 45.056 s | `fix: close final production integrity gaps` |
| Security closure | Loại bỏ Windows batch-shell boundary cho pnpm | complete | `python -m pytest -v` (124 passed); Ruff; video test (12 passed)/typecheck; doctor; real Windows golden render 1080 × 1920, 30 fps, 45.056 s | `fix: remove Windows batch-shell launcher` |

## Kiến trúc

Python CLI điều phối artifact YAML/JSON theo schema. Domain thuần Python tách
khỏi TTS và renderer; Remotion nhận `render-input.json` bất biến.

## Quick start

```powershell
# Cài lại an toàn được: chỉ tạo/cập nhật .venv và dependencies trong repo.
powershell -NoProfile -ExecutionPolicy Bypass -File install/install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File install/doctor.ps1
& .venv\Scripts\healthvideo.exe version
& .venv\Scripts\healthvideo.exe project new muoi-va-huyet-ap --title "Ăn mặn và tăng huyết áp"
# Bác sĩ viết evidence/ledger.yaml, script/script.yaml, storyboard/storyboard.yaml
# theo mẫu tests/fixtures/golden-project, rồi đặt state=awaiting_medical_review
# trong project.yaml (MVP chưa có lệnh intake cho các bước này).
& .venv\Scripts\healthvideo.exe review medical projects/2026/09/muoi-va-huyet-ap --reviewer "BS An" --note "Đã đối chiếu số liệu"
& .venv\Scripts\healthvideo.exe produce projects/2026/09/muoi-va-huyet-ap --tts silent
& .venv\Scripts\healthvideo.exe review video projects/2026/09/muoi-va-huyet-ap --reviewer "BS An"
& .venv\Scripts\healthvideo.exe package projects/2026/09/muoi-va-huyet-ap
& .venv\Scripts\healthvideo.exe status projects/2026/09/muoi-va-huyet-ap
```

Smoke test fixture golden độc lập (không thay thế render của dự án thật, không tạo
artifact và không đổi state):

```powershell
& .venv\Scripts\healthvideo.exe produce tests/fixtures/golden-project --tts silent --dry-run
```

`healthvideo doctor` yêu cầu Python >=3.11, Node >=22, pnpm >=11, FFmpeg >=8 và
Arial hoặc Noto Sans. Doctor và production dùng chung resolver: ưu tiên executable
`pnpm`; trên Windows, nếu PATH chỉ có shim `.cmd`, resolver gọi `pnpm.cjs` hoặc
`corepack.js` trực tiếp bằng `node.exe` và không đi qua `cmd.exe`. Batch launcher
khác bị từ chối với lỗi rõ ràng; CUDA chỉ là cảnh báo tùy chọn. Lần kiểm tra Windows
gần nhất (08-09-2026) phát hiện Python 3.14.3, Node 24.14.0, pnpm 12.3.4 và
FFmpeg 8.1.1.

Artifact nằm trong thư mục dự án: `evidence/`, `script/`, `storyboard/` là đầu vào
do bác sĩ sở hữu; `reviews/` giữ audit trail của hai cổng duyệt;
`renders/<input_hash>/` giữ WAV, `render-input.json`, MP4 và manifest của một lần
sản xuất; `publish/` là gói cuối cùng để đăng thủ công. Chỉ `evidence/`, `script/`,
`storyboard/`, `project.yaml`, `author-brief.yaml` và `reviews/` nên vào Git;
`audio/`, `renders/` và `publish/` đã được `.gitignore` bỏ qua.

## Workflow

Author brief → evidence ledger → script + storyboard → medical review → production
→ video review → publication package. Cả hai cổng duyệt của bác sĩ là bắt buộc;
storyboard phải tồn tại trước khi duyệt y khoa.
`produce` chỉ nhận dự án ở `script_approved` khi có `ReviewRecord` y khoa hiện hành,
kể cả với `--dry-run` hoặc cache hit; state YAML đơn lẻ không mở cổng. Nếu dự án đã ở
`awaiting_video_review`, nó chỉ trả lại video cache khi hash đầu vào vẫn khớp.

## Cổng duyệt và audit trail

`healthvideo review medical` chỉ chạy ở `awaiting_medical_review`, gắn hash của
`evidence/ledger.yaml`, `script/script.yaml`, `storyboard/storyboard.yaml` và byte
của mọi ảnh `evidence_highlight` rồi chuyển `script_approved`; đường dẫn asset phải
là POSIX tương đối, nằm trong dự án và trỏ tới file có thật. Storyboard nằm trong
cổng vì nó quyết định nội dung và dấu trích dẫn hiện trên màn hình.
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
`package` dùng lại `ensure_approval_current` cho cổng video.

## Gói xuất bản

`healthvideo package <project>` chỉ chạy khi dự án ở `approved_to_publish` **và**
cả `ReviewRecord` y khoa (ledger, script, storyboard) lẫn video (`render-input.json`,
MP4) còn hiệu lực. Thiếu bản ghi nào cũng bị từ chối như bản ghi đã cũ, vì gói này đi
ra ngoài nên mọi lần duyệt phải truy vết được. Lệnh không gọi API đăng bài và không
đổi state, nên đóng gói lại nhiều lần vẫn an toàn.

`publish/` gồm bốn payload được tự kiểm tra và manifest của chúng:

- `video.mp4` — bản sao `shutil.copy2` của MP4 đã duyệt trong run đang hoạt động.
- `render-input.json` — render contract đúng bản đã được duyệt video.
- `caption.txt` — hook ngắn lấy từ câu đầu kịch bản, disclaimer thông tin chung và
  danh sách `[n]` kèm nguồn.
- `sources.md` — nguồn đầy đủ theo từng dấu `[n]`: tiêu đề, tác giả, năm, thiết kế
  nghiên cứu, cỡ mẫu, DOI/PMID/URL.
- `manifest.json` — `payload_sha256` của bốn payload trên (không hash chính
  manifest), cùng `approval_bindings` riêng cho hai gate với canonical
  `approval_sha256` và hash artifact mà mỗi gate đã ký.

Mỗi dấu `[n]` hiện trong `render-input.json` đã duyệt phải khớp claim và nguồn trong
script/ledger; nếu không, `package` từ chối thay vì phát hành một trích dẫn không có
nguồn. Câu
`professional_opinion` không mang `source_marker` nên không bao giờ xuất hiện trong
danh sách nguồn. Gói được dựng trong thư mục staging cạnh `publish/` rồi publish
bằng một lần đổi tên thư mục; trước promotion, MP4 và canonical `render-input.json`
trong staging phải khớp chính xác video approval. Caption và sources chỉ sinh từ
snapshot ledger/script/storyboard đã đối chiếu với medical approval, nên sửa file
đồng thời trong lúc copy không thể đưa byte hoặc nội dung chưa duyệt vào gói.

## Kiểm thử gần nhất

Ngày chạy gần nhất: **08-09-2026**. `python -m pytest -v` (124 passed);
`python -m ruff check src tests tools`; `pnpm --dir video test` (12 passed);
`pnpm --dir video typecheck`; `install/doctor.ps1`. Golden project
(`tests/fixtures/golden-project`) chạy hết luồng từ duyệt y khoa, sản xuất, duyệt
video đến `package` offline với TTS im lặng và renderer giả lập; hai cổng duyệt,
audit trail và test approval stale (`status` báo `approval_stale=true`, `produce`
và `package` từ chối chạy) đều PASS, không cần TTY, mạng hay GPU. Ngoài test giả,
CLI Windows đã render thật golden project bằng silent TTS qua
`node.exe` + Corepack entrypoint, không qua `cmd.exe`: MP4 H.264 1080 × 1920,
30 fps, 45.056 giây. Regression test chạy thật bảo toàn nguyên văn đối số chứa
`&`, `%`, `!`, `^`, khoảng trắng và Unicode. Bộ dev ghim
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
và dữ liệu bắt buộc cho `evidence_highlight` trước render. Whiteboard và chart
đều hiển thị `source_marker` nhất quán ở góc trên bên phải. Mỗi dự án mới lưu
`author-brief.yaml` ở thư mục gốc dự án. `install/install.ps1` tạo hoặc dùng lại
`.venv`, cài dependency Python/video trong repo rồi chạy doctor; nó không sửa PATH,
cài driver hay ghi secret. `SilentTTS` chỉ ghi WAV im lặng, xác định
(mono PCM 16-bit, 24 kHz), phục vụ test và smoke render — chưa phải giọng đọc để
đăng: `publish/video.mp4` dựng bằng `--tts silent` là video câm, chỉ dùng để kiểm
tra luồng chứ chưa đăng được. Chưa có intake nguồn hay TTS thực; đăng video vẫn là
thao tác thủ công của con người từ thư mục `publish/`. CUDA không bắt buộc cho MVP;
GPU acceleration và Linux installer thuộc các plan tiếp theo.

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
storyboard, profile giọng tác giả, provider và SHA-256 byte của từng evidence asset
thành input hash. Thay asset làm approval cũ stale và tạo cache identity mới. Một lần render hợp lệ
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
