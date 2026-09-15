# Protect Your Health

## Bắt đầu với `/pyh`

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install/install.ps1
# Trong Codex hoặc Claude Code:
# /pyh tìm chủ đề                  # xem/tạo topic card trong inbox cục bộ
# /pyh chọn chủ đề                 # chọn card; tạo project v2 nếu chưa có
# /pyh chốt brief                  # xem và xác nhận brief riêng trước nghiên cứu
# /pyh tiếp tục                    # nghiên cứu, soạn và dừng tại cổng duyệt y khoa
```

Yêu cầu `/pyh làm video ... về <chủ đề>` cũng tạo/chọn topic card rồi dừng để bác sĩ xác nhận brief. Mở packet bằng `healthvideo review open <project> --gate medical`; bác sĩ duyệt rõ ràng bằng lệnh `healthvideo review approve` với tên người duyệt. Sau khi `/pyh tiếp tục` dựng video, mở packet `--gate video` và duyệt lần hai. `/pyh tạo gói đăng` tạo `revisions/<active_revision>/publish/` để đăng thủ công. Dùng `/pyh trạng thái` để xem bước tiếp theo. Discovery trực tuyến có giám sát và TTS thật chưa thuộc acceptance offline hiện tại.

Với chủ đề rủi ro cao cần phản biện bổ sung, `healthvideo agent review-request <project> --reason <code>` tạo gói XML cục bộ để gửi thủ công; `healthvideo agent review-complete <project> --file <response.yaml>` chỉ nhận phản hồi gắn đúng request và revision. Bước này không gọi mô hình, không thay thế hai cổng duyệt của bác sĩ.

## Mục tiêu

Xây dựng luồng có thể kiểm tra để biến hồ sơ và luận điểm đã được bác sĩ duyệt
thành video y tế dự phòng tiếng Việt dọc 1080 × 1920.

## Trạng thái hiện tại

MVP đã hoàn thành: project scaffold, claim ledger, author-owned script,
read-aloud QA, Remotion vertical preview, production cache, hai cổng duyệt của
bác sĩ, gói xuất bản, Windows installer và environment doctor. Thiết kế workflow
khép kín A–Z đã được duyệt tại `8a2b9a7`. M1 workflow kernel đã hoàn tất trên
nhánh triển khai: contract/layout v2, state graph, revision và stage bất biến,
semantic asset manifest, invalidation xác định và migration v1→v2 không phá dữ
liệu. M2 review gate và M3 topic/evidence đã hoàn tất. MVP v1 vẫn là đường
chạy tương thích ổn định; `/pyh` vận hành project v2 qua hai cổng duyệt.
PYH.1–6 đã hoàn tất và được kiểm tra end-to-end offline. M4.1 đã thêm gói
phản biện mô hình thứ hai để gửi/nhận thủ công, không thay thế duyệt của bác sĩ.
M5.1–M5.2 đã thêm từ điển phát âm tiếng Việt được ràng buộc với medical gate,
adapter TTS dạng lệnh cục bộ, kiểm tra WAV trước render và harness benchmark
offline. M5.2 ở commit `1376663` trên nhánh `codex/m1-workflow-kernel`;
525 test Python, 12 test video, Ruff và video typecheck đã qua ở M5.2.

M5.3 đã xác minh môi trường và giấy phép ứng viên (VieNeu-TTS v3 Turbo,
`vieneu==3.6.4`, model card Apache-2.0 cho phép audio thương mại từ preset voice),
thêm wrapper cục bộ `tools/tts/vieneu_synth.py`, lệnh `healthvideo tts-benchmark`
với tiêu chí đo khách quan và đã chạy benchmark thật trên máy này (xem
`docs/superpowers/plans/2026-09-13-tts-m5-3-vieneu-benchmark.md`). Kết luận đo
được: 13/13 case tổng hợp thành công, tốc độ đọc 2,7–4,8 từ/s; bài ~50 s đạt RTF
0,55 (fp32) / 0,46 (int8) trên CPU; câu lẻ trượt RTF ≤ 1,0 vì mỗi lần gọi nạp
model ~8 s. M5.4 thêm ASR back-check (faster-whisper, MIT) với WER khách quan, chuẩn hóa
loudness bằng FFmpeg (`NormalizedTTS`) và `produce --tts vieneu --voice <preset>`;
đã chạy thật: 10/13 case WER ≤ 0,2 và một video golden v2 dựng xong bằng VieNeu
(82 s, −16,7 LUFS) dừng ở `awaiting_video_review`. M5 hoàn tất phần kỹ thuật
tại `c4a500c` (548 test Python, 12 test video, Ruff, typecheck). Hai việc M5 còn
chờ con người: bác sĩ nghe 13 WAV benchmark để chọn preset voice chính thức và bổ
sung từ điển phát âm cho tên thuốc; ElevenLabs fallback chỉ làm khi có key.
Không đưa audio/model/cache, credential hoặc bản render tạm vào Git; không vượt
hai cổng duyệt hoặc tự đăng.

M6 bắt đầu theo [kế hoạch visual](docs/superpowers/plans/2026-09-13-visuals-m6.md).
M6.1 chỉ tạo chart SVG tĩnh từ `chart_data` dạng `count_of_total` được ghi rõ
trong claim của `evidence/ledger.yaml`: số đếm nguyên, mẫu số, đơn vị, nhãn,
source ID và CI tùy chọn. API Python `create_evidence_chart` chỉ nhận project v2
chưa duyệt y khoa; nó kiểm nguồn thuộc claim, đăng ký `data_chart` với
`semantic: true`, hash bytes trong `assets/asset-manifest.yaml` và ghi
`assets/license-ledger.yaml` từ license/căn cứ quyền do operator nhập tường
minh. Code không suy đoán giấy phép, không tạo số liệu, không đổi state; medical
gate hash cả asset và license ledger. Chưa nối chart vào Remotion hoặc CLI.

M6.2 cung cấp API Python `create_evidence_highlight_asset` cho project v2 trước
cổng duyệt y khoa. Operator chuẩn bị ảnh trang PNG/JPEG **ngoài project**, ghi
`source_id`, số trang, câu trích nguyên văn, marker và hình chữ nhật chuẩn hóa
trong storyboard, rồi khai tường minh license, căn cứ quyền dùng và creator.
API kiểm source–claim–marker, crop vùng nhỏ quanh hình chữ nhật bằng Pillow
12.3.0 ([PyPI](https://pypi.org/project/pillow/), MIT-CMU), chỉ lưu PNG crop;
không đưa trang đầy đủ/PDF/full text hay đường dẫn máy vào project. Metadata
crop giữ tọa độ trang gốc và kích thước pixel của ảnh cắt; renderer đặt ảnh
theo `contain` và vẽ overlay trong cùng hộp nên không lệch trên crop vuông hoặc
ngang. Asset semantic, hash và rights ledger được medical gate ràng buộc;
retry sau lỗi promotion hội tụ an toàn. Không OCR hoặc xác nhận tự động
quote có thật trong ảnh. PDF rasterization, mascot, signature, visual budget và
Veo vẫn ở lát sau. Không đổi hai cổng duyệt hoặc đăng thủ công.

M6.3 hoàn tất theo đặc tả nhận diện PYH đã duyệt. Brand profile khóa
bảng màu xác định (navy, teal, vàng, trắng ngà, charcoal), ba pose mascot
`welcome`/`explain`/`caution`, logo hình học PYH không phụ thuộc font và bốn
template whiteboard hữu hạn. SVG lặp byte, không script/filter/external raster;
generator chỉ bố trí giá trị operator cung cấp. Mascot tóc ngắn, dáng đầy đặn,
đeo kính và mặc áo khoác chuyên nghiệp navy–teal; không áo blouse, ống nghe hay
hành vi khám/chẩn đoán/kê đơn. Intro, outro và chuyển động signature vẫn thuộc
M6.4.

Checkpoint B thêm `mascot_reaction` chỉ trang trí và
`mascot_medical_annotation` luôn semantic. Scene v2 có thể khai báo
`visual_assets`; resolver kiểm đường dẫn, loại asset và SHA-256 cho cả asset
trang trí trước medical gate và production. Workflow đăng ký ghi intent trước,
promotion nguyên tử và retry hội tụ; annotation/whiteboard semantic bắt buộc
claim–source–marker hợp lệ. Remotion chỉ render asset đã khai báo qua
`staticFile`, stage đúng byte và đưa hash cả asset trang trí vào cache identity.
Scene cũ không có trường này vẫn giữ fallback hiện tại. M6.4 đã hoàn tất.
M6.5 complete (acceptance và C2C review DONE): storyboard `m6_5_v1`
cưỡng chế ngân sách visual theo frame ở medical gate và production, QA ghi report
tái tính được, chart dùng SVG `DATA_CHART` đã bind. M6.6 complete sau acceptance
toàn bộ và C2C review DONE cho cả sáu lát: Veo chỉ
chạy khi operator opt-in trước medical gate; production chỉ stage đúng bytes AI
clip đã được medical approval bao phủ, không gọi provider; Remotion render clip
muted; gói đăng thủ công có `ai-disclosure.json` khi có AI. Hai cổng duyệt và
đăng thủ công giữ nguyên.

## Milestone

MVP complete: vertical slice từ author brief, evidence, kịch bản và storyboard
đến TTS giả lập, render, hai cổng duyệt, gói xuất bản và kiểm tra Windows.

M1 complete: kernel workflow v2 và migration sibling v1→v2 đã vượt acceptance
offline; migration không sửa nguồn, không overwrite đích và không tự duyệt gate.

M2 complete: review gate v2 cho cả y khoa và video đã hoàn thành (approve,
reject audit trail lặp lại được, resume, static HTML review packet, CLI adapter
và `.gitignore` cho HTML). Không đổi hành vi của v1 (`review medical`/`review video`).
Toàn bộ 407 tests pass offline trên Windows/PowerShell (11-09-2026). Các commit:
M2.1 (`38321a6`), M2.2 (`78fe1fb`), M2.3 (`3ffcae8`), M2.4 (`10ba3da`), M2.5 (`feat: expose v2 review gate approve, reject, open and resume`).
Gói review HTML giữ đúng giới hạn model hiện tại (chưa model hóa population, certainty,
applicability, per-claim doctor notes — hoãn sang M3).

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
| A–Z workflow design | Đặc tả pipeline khép kín, migration v1→v2, phân vai AI, token budget và roadmap M1–M7 | approved | state/review/produce: 41 passed; Ruff; spec consistency; source/license verification; `git diff --check` | `8a2b9a7` |
| M1 implementation plan | Plan chi tiết graph v2, revision/stage/asset manifest, invalidation và migration không phá v1 | approved; ownership audited | path ownership matrix; document consistency; `git diff --check` | `docs: plan workflow kernel M1`; `docs: lock M1 fixture path contracts`; `docs: audit M1 path ownership` |
| M1.1 | Contract project v2 và dual-golden checkpoint | complete | Baseline 10-09-2026: 124 passed; `python -m pytest -q` (132 passed); `python -m ruff check src tests tools`; dual-golden + schema (18 passed) | `feat: add parallel v2 project contract` |
| M1.2 | Main-path graph v2 có precondition | complete | `python -m pytest -q --basetemp=.task2-fix2-pytest` (149 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: add preconditioned v2 state graph` |
| M1.3 | Side-state graph v2 và đường resume/reject cho `awaiting_browser_login`, `awaiting_second_model_review`, `needs_medical_revision`, `needs_production_revision`, `blocked`, `topic_rejected`. Lối ra `needs_production_revision -> draft_ready` đọc reason class `semantic_issue` tại thời điểm thoát (lỗi semantic được phát hiện khi đang ở side state), không đọc lý do đã ghi lúc vào. `blocked` chỉ nhận nguồn là main state chưa kết thúc: `ProjectManifestV2` chỉ có một ô `side_state`, nên lồng side state trong side state sẽ ghi đè `resume_state` và mất đích resume — mở rộng cần đổi schema, hoãn sang M2. | complete | `python -m pytest tests/domain/test_state_graph.py -q` (85 passed); `python -m pytest tests/e2e/test_golden_project.py tests/e2e/test_golden_workflow_versions.py -q` (21 passed); `python -m pytest -q` (219 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: add v2 side-state transitions`; `fix: read side-exit reason class at exit time` |
| M1.4 | Stage manifest bất biến (`StageManifest`: `stage`, `status`, `input_hash`, `output_hash`, `tool_version`, `agent`, `model`, `started_at`, `completed_at`, `estimated_input_tokens`, `estimated_output_tokens`) và storage append-only. `write_yaml_once` mở file exclusive (`"x"`), fsync rồi từ chối mọi lần ghi thứ hai bằng `FileExistsError` mà không đổi byte đã có. Record nằm tại `workflow/stages/<stage>/<started-at>-<input-hash-prefix>.yaml` với timestamp UTC không dấu `:` để chạy trên Windows. Complete bắt buộc `output_hash` + `completed_at`; trạng thái khác cấm `output_hash`; `completed_at` không được sớm hơn `started_at`. | complete | `python -m pytest tests/domain/test_stage.py tests/storage/test_immutable.py tests/storage/test_stages.py tests/contracts/test_schemas.py tests/e2e/test_golden_workflow_versions.py -v` (46 passed); `python -m pytest -q` (251 passed); `python -m ruff check src tests tools`; `git diff --check`; `python tools/export_schemas.py` | `feat: add immutable stage manifests` |
| M1.5 | Revision workflow bất biến và lệnh `healthvideo revision create <project> --reason "..."`. `RevisionRecord` (`schema_version`, `revision`, `parent_revision`, `reason`, `created_at`) là model bất biến, ID revision đúng 3 chữ số, `reason` không được rỗng/toàn khoảng trắng, `created_at` bắt buộc có múi giờ. `create_revision` copy đúng sáu thư mục `topic/`, `author/`, `evidence/`, `script/`, `storyboard/`, `assets/` từ active revision sang staging `revisions/.<mới>-stage-<uuid>` (không copy `handoffs/`, `reviews/`, `audio/`, `renders/`, `publish/`), ghi `workflow.yaml` bằng `write_yaml_once`, đối chiếu byte mọi file đã copy, rồi promote một lần bằng `promote_directory_once` (primitive mới trong `storage/immutable.py`, cạnh `write_yaml_once`, sẽ dùng lại cho migration ở Task 9) — không bao giờ ghi đè revision đích. Chỉ sau khi promote thành công `project.yaml.active_revision` mới được ghi nguyên tử; mọi lỗi trước đó (copy hỏng, đối chiếu byte lệch, đích đã tồn tại) chỉ xóa đúng thư mục staging vừa tạo và giữ nguyên `project.yaml` cùng revision cha. Project schema `1.0` bị từ chối với thông báo yêu cầu `project migrate`. | complete | `python -m pytest tests/domain/test_revision.py tests/storage/test_revisions.py tests/storage/test_immutable.py tests/test_cli.py tests/e2e/test_golden_workflow_versions.py -v` (48 passed); `python -m pytest -q` (279 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: create immutable workflow revisions` |
| M1.6 | Semantic asset manifest và policy phân loại §7. `AssetKind` (`evidence_highlight`, `data_chart`, `medical_diagram`, `medical_text`, `background`, `texture`, `flourish`, `transition`); `evidence_highlight`, chart mang số liệu/claim, medical diagram và medical text luôn `semantic=true` — `AssetRecord` (bất biến) từ chối `semantic=false` cho bốn kind này bằng `ValidationError`; chỉ `background`/`texture`/`flourish`/`transition` mới được `false`. `AssetManifest` (bất biến) từ chối duplicate `path`. `validate_asset_manifest` buộc mọi path POSIX tương đối, không `..`, không absolute, nằm trong revision root, rồi khớp SHA-256 byte cho mọi asset `semantic=true` trước khi đủ điều kiện vào medical gate; lệch hoặc mất file raise `AssetIntegrityError` riêng biệt. `validate_reclassification` so hai manifest, từ chối hạ một asset từ `semantic=true` xuống `false` nếu thiếu `classification_reason`. Fixture golden Task 1 (`assets/evidence-r01.svg`, `evidence_highlight`, `semantic: true`) load + validate giữ nguyên byte trước/sau. Trong lúc làm việc phát hiện typo SHA-256 65 ký tự trong chính fixture đó (khác byte thật của file); leo thang lên controller thay vì tự sửa fixture, được xác nhận và sửa ở `2462ed9` (ngoài diff Task 6). | complete | `python -m pytest tests/domain/test_asset_manifest.py tests/contracts/test_schemas.py tests/e2e/test_golden_workflow_versions.py -v` (53 passed); `python -m pytest -q` (315 passed); `python -m ruff check src tests tools`; `git diff --exit-code -- tests/fixtures/golden-project-v2`; `git diff --check`; `python tools/export_schemas.py` | `feat: classify semantic workflow assets` |
| M1.7 | Invalidation engine xác định, thuần dữ liệu (`src/healthvideo/domain/invalidation.py`), không đụng filesystem và không tự gọi state graph. `InvalidationLevel` (`IntEnum`) `none < package < video < medical`. `ArtifactChange(path, json_pointers)` và `InvalidationDecision(level, target_state, reason_codes)` đều là dataclass bất biến (`frozen=True`). `evaluate_invalidation(changes, asset_manifest)` phân loại từng change độc lập rồi lấy mức cao nhất (không phải match đầu/cuối) làm quyết định chung; `reason_codes` chỉ giữ lý do của các change đạt đúng mức cao nhất đó. Thứ tự phân loại: (1) path khớp asset trong `AssetManifest` → `semantic=true` là `medical`, `semantic=false` là `video`; (2) đúng `publish/metadata.yaml` → chỉ `package` khi *mọi* JSON pointer nằm trong allowlist đúng 8 phần tử `/posting/platform`, `/posting/account_handle`, `/posting/scheduled_at`, `/posting/visibility`, `/posting/allow_comments`, `/posting/allow_duet`, `/posting/allow_stitch`, `/tracking/campaign_id` — pointer rỗng, pointer lạ (vd. caption/hashtag/disclaimer/source list/thumbnail text/pinned comment) hoặc trộn lẫn allowlist với pointer lạ đều trả `medical`; (3) tiền tố thư mục đã biết — `evidence/`, `script/`, `storyboard/` → `medical`; `audio/`, `timing/`, `renders/` → `video`; (4) path không nhận diện được (kể cả path rỗng) fail-closed về `medical`, không bao giờ hạ xuống `none`/`package` một cách âm thầm. `target_state` là `needs_medical_revision`/`needs_production_revision` ở hai mức nặng, `None` ở `none`/`package` (không đổi gate). Không có change nào → `none`, `target_state=None`, `reason_codes` rỗng. Dual-golden mới xác nhận engine chỉ đọc `asset-manifest.yaml` của golden v2, fail-closed đúng cho path lạ, và không đổi byte của cả hai fixture — golden v1 không có khái niệm asset manifest nên chưa bao giờ bị áp policy v2 này. Review Task 7 thêm một test độc lập chốt đúng 8 phần tử allowlist bằng literal set (không đọc lại từ hằng số production), vì test parametrize cũ tự tham chiếu hằng số nên sẽ không phát hiện một drift âm thầm trong `PUBLISH_METADATA_PACKAGE_ALLOWLIST`. | complete | `python -m pytest tests/domain/test_invalidation.py tests/e2e/test_golden_workflow_versions.py -v` (47 passed); `python -m pytest -q` (356 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: evaluate deterministic gate invalidation`; `test: pin the publish-metadata package allowlist independent of the constant` |
| M1.8 | Migration planner v1→v2 thuần read-only. `plan_migration` validate đúng schema v1, ánh xạ đủ 10 state (loại `rendered` về `awaiting_video_review`), khóa đúng tám path nguồn/đích của contract, hash YAML/JSON theo canonical JSON và asset theo byte SHA-256. Topic card và semantic asset manifest được dựng trong bộ nhớ để lập plan, chưa ghi filesystem; approval chỉ mang nhãn `retain_candidate`, chưa được coi là giữ hợp lệ trước equivalence Task 9. Đích mặc định là sibling `<source>-v2`; đích tồn tại chỉ được báo `destination_conflict=true`, planner không ghi đè, không tạo staging và không sửa byte project nguồn. Nguồn schema v2 bị từ chối. | complete | `python -m pytest tests/workflows/test_migrate_plan.py tests/e2e/test_golden_workflow_versions.py -v` (22 passed); `python -m pytest -q` (371 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: plan non-destructive project migration` |
| M1.9 | Migration transaction v1→v2 không phá dữ liệu: dựng sibling staging `.<destination>.migrate-<uuid>`, canonicalize YAML, copy asset/render đúng byte, tạo topic + semantic asset manifest, validate Pydantic/layout/hash asset và mọi output trong plan rồi promote một lần bằng `promote_directory_once`; không có in-place/overwrite. Copy, validation hoặc promotion lỗi đều dọn đúng staging của migration, giữ source byte-identical và không để destination bán phần; chạy lần hai fail bằng `FileExistsError`. Approval equivalence đối chiếu cả binding nguồn hiện hành và hash artifact tại revision đích: medical không chứng minh được → `awaiting_medical_review`; medical đúng + render hỏng → `medically_approved`; medical đúng + render hợp lệ nhưng video chưa đúng → `awaiting_video_review`; cả hai gate đúng → tối đa `video_approved` (không tự giữ `published_manual` khi thiếu receipt). Chỉ review record chứng minh tương đương mới được copy vào `revisions/001/reviews/`; không tự ký lại approval. | complete | `python -m pytest tests/workflows/test_migrate_execute.py tests/e2e/test_golden_workflow_versions.py -v` (21 passed); `python -m pytest -q` (384 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: migrate v1 projects atomically` |
| M1.10 | CLI `healthvideo project migrate <project> [--dry-run]`. Dry-run in source, sibling destination, state map, approval disposition, conflict và từng path/hash mà không ghi filesystem. Execute inject timezone-aware time + UUID, gọi transaction Task 9 và in destination; lỗi nguồn/đích/validation/integrity trả exit 1 có thông báo. Không có `--in-place`, `--force`, overwrite hay auto approval. Acceptance xác nhận golden v1 cũ và v2/migrated chạy song song, schema export deterministic; review packet/gate-native v2 được hoãn đúng sang M2. | complete | CLI migrate/revision (5 passed); dual-golden E2E (27 passed); `python -m pytest -q` (387 passed); `python -m ruff check src tests tools`; `python tools/export_schemas.py`; `git diff --exit-code -- schemas`; `git diff --check` | `feat: expose safe project migration` |
| M2.1 | Domain model gate review v2 (`GateKind`, `GateApprovalRecord`, `GateRejectionRecord`). Bắt buộc `reviewer` không rỗng, `reviewed_at` có múi giờ, `artifact_hashes` không rỗng; `GateRejectionRecord` bắt buộc `reason` không rỗng và lưu `resume_state`. | complete | Baseline 11-09-2026: 387 passed; `tests/domain/test_gate_review.py` (4 passed); `python -m pytest -q` (391 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: add v2 gate review records` |
| M2.2 | Medical gate v2 (`approve_gate`, `reject_gate`, `resume_gate`). Khớp artifact hash (`medical_reviewed_paths` hash ledger, script, storyboard, asset-manifest và byte asset `semantic=true`), bắt buộc `validate_asset_manifest` trước khi approve. Ghi `reviews/medical-approval.yaml` một lần mỗi revision (`write_yaml_once`), từ chối ký lại; reject ghi audit trail timestamp và chuyển `needs_medical_revision`, resume đưa về `draft_ready`. Dual-golden copy xác nhận không sửa fixture tracked. | complete | `tests/workflows/test_gate_review.py` (5 passed); `tests/e2e/test_golden_workflow_versions.py` (10 passed); `python -m pytest -q` (397 passed); `python -m ruff check src tests tools`; `git diff --exit-code -- tests/fixtures`; `git diff --check` | `feat: add v2 medical gate approve, reject and resume` |
| M2.3 | Video gate v2 (`approve_gate`, `reject_gate`, `resume_gate` với `GateKind.VIDEO`). Hash `renders/render-manifest.json` và `renders/video.mp4`; reject cho phép quay lại `production_in_progress` hoặc `draft_ready` (yêu cầu reason class `semantic_issue`). Chạy trên synthetic render fixture; chưa có pipeline production v2 thật (M6). | complete | `tests/workflows/test_gate_review.py` (8 passed); `tests/e2e/test_golden_workflow_versions.py` (10 passed); `python -m pytest -q` (400 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: wire the v2 video gate onto the same approve/reject/resume core` |
| M2.4 | Render static review packet HTML (`render_medical_packet`, `render_video_packet`). Hàm thuần + `html.escape`, không thêm dependency runtime (không Jinja2/web framework), không tự mở trình duyệt, không tự ký. Medical packet chỉ hiển thị field hiện có trong model (`text_public`, `text_technical`, `sources`), có ghi chú rõ các field spec §14 chưa có trong hệ thống (population, certainty, applicability, quan điểm bác sĩ theo claim). Video packet nhúng thẻ video trỏ path tương đối `../renders/video.mp4` và dump manifest/QA. | complete | `tests/workflows/test_review_html.py` (3 passed); `python -m pytest -q` (403 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: render static medical and video review packets` |
| M2.5 | CLI review gate v2 (`review approve`, `review reject`, `review open`, `review resume` với flag `--gate medical|video`), `.gitignore` cho packet HTML và acceptance M2 offline. Lệnh v1 (`review medical`, `review video`) giữ nguyên không đổi. Reject yêu cầu gõ `REJECT` xác nhận (hoặc `--yes`); approve yêu cầu gõ `APPROVE` (hoặc `--yes`). `review open` ghi HTML bằng `write_text_atomic` và in đường dẫn, không tự mở trình duyệt. | complete | `tests/test_cli.py` (4 passed); `tests/workflows/test_gate_review.py` (8 passed); `tests/workflows/test_review_html.py` (3 passed); dual-golden E2E (10 passed); `python -m pytest -q` (407 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: expose v2 review gate approve, reject, open and resume` |
| M3.1 | Domain model topic discovery & triage scoring (`TopicSignal`, `TopicScores`, `TopicCard`, `calculate_triage_rank`). Điểm triage chuẩn hoá 0.0–1.0 ưu tiên giá trị phòng bệnh, tính sẵn sàng của bằng chứng và độ rõ ràng của câu hỏi công chúng. Tương thích ngược hoàn toàn với fixture card migration v2. | complete | `tests/domain/test_topic.py` (4 passed); `python -m pytest -q` (411 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: add topic discovery and triage domain models` |
| M3.2 | Topic inbox và selection workflow (`list_topics`, `create_topic`, `reject_topic`, `select_topic`). Lưu trữ inbox tại `topics/*.yaml`, hỗ trợ lọc theo status và sắp xếp theo điểm triage. `select_topic` ghi `revisions/<id>/topic/card.yaml` và chuyển trạng thái `idea -> topic_selected` với context input hash hợp lệ. | complete | `tests/workflows/test_topic.py` (3 passed); `python -m pytest -q` (414 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: manage topic inbox and select topics into projects` |
| M3.3 | Mở rộng domain model bằng chứng (`EvidenceClaim`, `SourceRecord`, `EvidenceQuestion`, `SearchLogRecord`, `CandidateSource`, `SourceSelection`). Bổ sung các trường hoãn từ M2 (`certainty`, `population`, `applicability`, `evidence_direction`, `doctor_notes`, `pmcid`, `journal`, `retraction_status`, `conflict_of_interest`, `key_findings`). Bảo toàn 100% tương thích ngược với ledger fixture v1 và v2. | complete | `tests/domain/test_evidence.py` (5 passed); `tests/contracts/test_schemas.py` (13 passed); `python -m pytest -q` (419 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: extend evidence models with certainty population and search artifacts` |
| M3.4 | Client tìm kiếm y văn (`PubMedClient`, `EuropePMCClient`, `CrossrefClient`, `check_scopus_policy`, `get_cached_response`, `store_cached_response`). Sử dụng `urllib.request` thuần không thêm dependency, hỗ trợ injectable transport để test offline 100%. Thực thi nghiêm ngặt quyết định loại trừ Scopus theo §17 (chặn tự động, yêu cầu tìm kiếm ngoài hệ thống). | complete | `tests/evidence/test_clients.py` (5 passed); `python -m pytest -q` (424 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: add medical literature search clients for pubmed europepmc crossref` |
| M3.5 | Workflow tổng hợp bằng chứng (`record_question`, `search_literature`, `record_source_selections`, `build_evidence_ledger`, `reject_topic_for_lack_of_evidence`). Quản lý artifact PICO `question.yaml`, `search-log.yaml`, `candidates.jsonl`, tách sàng lọc `included-sources.yaml`/`excluded-sources.yaml`, kiểm tra rút bài (retraction check) trước khi tạo `ledger.yaml` và chuyển trạng thái `research_in_progress -> evidence_ready` hoặc `topic_rejected`. | complete | `tests/workflows/test_evidence.py` (5 passed); `python -m pytest -q` (429 passed); `python -m ruff check src tests tools`; `git diff --check` | `feat: synthesize evidence ledger and manage literature search workflow` |
| M3.6 | Tích hợp review packet HTML, schema contracts, CLI topic & evidence và acceptance M3. Bổ sung hiển thị `certainty` và `population` vào medical packet; export `topic-card.schema.json`; bổ sung CLI `healthvideo topic list|create|select|reject` và `healthvideo evidence search|ingest|build-ledger`. Bỏ qua cache y văn `source-cache/` trong `.gitignore`. Xác nhận toàn bộ 435 tests vượt qua, giữ nguyên 0-byte diff fixtures v1/v2 và tính bất biến offline. | complete | `tests/test_cli.py` (4 passed); `tests/workflows/test_review_html.py` (4 passed); `tests/contracts/test_schemas.py` (14 passed); dual-golden E2E (28 passed); `python -m pytest -q` (435 passed); `python -m ruff check src tests tools`; `git diff --exit-code -- tests/fixtures`; `git diff --check` | `feat: wire topic and evidence CLI and complete M3 discovery pipeline` |
| PYH.1 | Tạo project schema v2 bằng sibling staging và xác nhận author brief qua cạnh `topic_selected -> author_brief_ready` có hash/artifact guard sẵn có. Giữ nguyên `AuthorBrief`, creator v1 và graph v2; brief nháp không đổi state. | complete | `python -m pytest tests/workflows/test_create_project_v2.py tests/workflows/test_author.py tests/workflows/test_create_project.py tests/domain/test_state_graph.py -v` | `feat: create and confirm pyh workflow v2 projects` |
| PYH.2 | Chiếu read-only state/layout v1/v2 đã validate thành action `/pyh`, gồm main path, side state, migration v1 và status tái lập; không ghi `STATUS.md`, approval hoặc workflow state. | complete | `python -m pytest tests/workflows/test_operator.py tests/storage/test_project_layout.py tests/domain/test_state_graph.py -v` | `feat: project workflow state into pyh actions` |
| PYH.3 | Mở rộng `produce_project` và `package_project` qua compatibility boundary: v2 dùng active revision, gate record M2, cache render hiện có và atomic package promotion; v1 giữ nguyên đường chạy. | complete | `python -m pytest tests/workflows/test_produce.py tests/workflows/test_package.py tests/e2e/test_golden_project.py tests/e2e/test_golden_workflow_versions.py tests/workflows/test_gate_review.py -v` (65 passed); `python -m ruff check src tests tools` | `feat: produce and package approved v2 projects` |
| PYH.4 | Chứng minh lifecycle offline từ chọn topic, brief, evidence đến package qua hai cổng duyệt; xác nhận invalidation y khoa/video. | complete | `python -m pytest tests/e2e tests/workflows/test_gate_review.py tests/domain/test_invalidation.py -q` (79 passed); `python -m ruff check src tests tools` | `test: prove pyh lifecycle across both review gates` |
| PYH.5 | Thêm CLI `operator new/status/select/brief` cho v2 và một skill `/pyh` chuẩn dùng chung với Claude Code; giữ nguyên lệnh v1 và các cổng duyệt hiện có. | complete | `python -m pytest tests/test_cli.py tests/contracts/test_pyh_skill.py tests/workflows/test_operator.py -q` (51 passed); `python -m ruff check src tests tools` | `feat: expose shared pyh operator workflow` |
| PYH.6 | Quick Start `/pyh` và acceptance toàn hệ thống, giữ v1, không thêm auto-publishing. | complete | `python -m pytest -q` (475 passed); Ruff; schema export/diff; video test (12 passed)/typecheck; operator smoke | `docs: complete pyh operator milestone` |
| PYH review | Làm rõ hai đường bắt đầu topic và ý định duyệt trong skill chuẩn; Quick Start tách chọn topic khỏi xác nhận brief. | complete | Contract/CLI/operator/E2E; full Python/Ruff/schema/video gates | `docs: clarify pyh entry and doctor approval boundaries` |
| M4.1 | Gói phản biện mô hình thứ hai thủ công, bất biến, gắn response với request/revision/source hashes; nhánh blocking về medical revision, nhánh sạch trở lại state trước đó. | complete | Domain/workflow/CLI/schema/skill contracts; full Python/Ruff/schema/video gates | `feat: add bound manual second-model review handoff` |
| M5.1 | Từ điển phát âm tiếng Việt có phiên bản cho production v2: thay thế literal chỉ trong yêu cầu TTS, profile được medical gate hash/duyệt; cache, render manifest và video gate ràng buộc kết quả; v1 giữ nguyên. Profile mặc định rỗng, chưa có benchmark VieNeu, ASR hay ElevenLabs. | complete | `python -m pytest -q`; Ruff; schema export; video test/typecheck | `feat: bind versioned pronunciation to v2 production` |
| M5.2 | Adapter lệnh TTS cục bộ cấu hình rõ ràng, kiểm tra cấu trúc/tín hiệu WAV, nhận diện voice/runtime trong cache v2 và harness benchmark offline không chấm điểm chủ quan. Chưa chọn model hay chạy benchmark thật. | complete; C2C review DONE | `python -m pytest -q` (525 passed); Ruff; video test (12 passed)/typecheck; `git diff --check` | `1376663` |
| M5 handoff | Đồng bộ báo cáo tiến độ, giới hạn còn mở và đầu vào M5.3 để tiếp tục từ HEAD hiện tại. | complete | README review; `git diff --check` | `docs: hand off pyh M5 progress` |
| M5.3 | Xác minh môi trường (RTX 3060, Python 3.11, ffmpeg 8.1.1) và nguồn/giấy phép VieNeu-TTS v3 Turbo (`vieneu==3.6.4`, HF revision `8b7e9cf`, Apache-2.0); wrapper `tools/tts/vieneu_synth.py`; `evaluate_benchmark` với ngưỡng khách quan; lệnh `healthvideo tts-benchmark`; bộ 13 case; benchmark thật fp32/int8 ghi trong plan. Voice chính thức, ASR, ElevenLabs và `produce --tts vieneu` chưa làm. | complete | `python -m pytest -q` (532 passed); `ruff check src tests tools`; `git diff --check`; benchmark thật 2×13 case | `feat: benchmark VieNeu-TTS with objective gates` |
| M5.4 | ASR back-check `CommandASR` + `word_error_rate` (faster-whisper 1.2.1, MIT; wrapper `tools/tts/whisper_transcribe.py`); `NormalizedTTS` FFmpeg loudnorm; `tts-benchmark --asr-*`/`--max-wer`; `produce --tts vieneu --voice`; sửa `build_render_argv` dùng đường dẫn tuyệt đối. Chạy thật: WER 13 case (10/13 ≤ 0,2), produce golden v2 bằng VieNeu đến `awaiting_video_review`. Voice chính thức và ElevenLabs chưa làm. | complete | `python -m pytest -q` (548 passed); `ruff check src tests tools`; `git diff --check`; benchmark + produce thật | `feat: add ASR back-check and loudnorm to VieNeu production` |
| M5 handoff 2 | Chốt M5: kỹ thuật xong tại `c4a500c`; còn chờ bác sĩ chọn voice và bổ sung từ điển tên thuốc; ElevenLabs chờ key. M6 bắt đầu từ HEAD này. | complete | README review; `git diff --check` | `docs: hand off M5 completion` |
| M6.1 | Chart SVG count-of-total xác định từ datum explicit trong evidence ledger; asset semantic hash và license/right ledger cùng revision, medical gate ràng buộc bytes/metadata; không đổi v1/state. Các visual/render khác theo plan M6. | complete; C2C review DONE | `python -m pytest -q` (585 passed); Ruff; schema export; video test (12 passed)/typecheck; `git diff --check` | `feat: register evidence-bound charts and asset rights` |
| M6.2 | Crop paper highlight từ ảnh trang PNG/JPEG cục bộ ngoài project; source/page/marker/quote/tọa độ gốc, kích thước pixel crop, quyền dùng explicit, semantic hash/medical gate; renderer `contain` và remap overlay trên crop; retry crash-safe. Không PDF/OCR/full page. | complete; C2C review DONE | `python -m pytest -q` (599 passed); Ruff; schema export/diff; video test (16 passed)/typecheck; `git diff --check` | `feat: add provenance-safe paper highlights` |
| M6.3 | Nhận diện PYH xác định: logo/palette, mascot phi lâm sàng ba pose và bốn whiteboard template; asset khai báo, phân loại decorative/semantic, rights/hash, retry crash-safe, medical/production preflight và Remotion `staticFile`; giữ fallback cũ. Không intro/outro, budget hay Veo. | complete; C2C review iteration 3 DONE | `python -m pytest -q` (642 passed); Ruff; schema export/diff; video test (21 passed)/typecheck; compatibility (55 passed); `git diff --check` | `feat: add the PHY visual identity and mascot` (tên commit lịch sử trước khi sửa typo) |
| M6.3 naming correction | Tên và hình học chuẩn là Protect Your Health (PYH): wordmark P–Y–H, ARIA/mascot/whiteboard/outro/Remotion và asset mới dùng `PYH`/`pyh-*`; giữ `render_phy_logo` làm alias và tiếp tục đọc revision cũ nguyên trạng. | Complete; C2C review iteration 2 DONE | `python -m pytest -q` (799 passed); Ruff; video test (30 passed)/typecheck; `git diff --check` | `fix: correct visual identity to PYH`; `test: isolate legacy PHY compatibility` |
| M6.4 design | Đặc tả hook ở frame 0 không intro; câu kết pin trong script và storyboard trước duyệt; brand asset khai báo; v2 không giới hạn tổng thời lượng, audio phải khớp timeline; v1 giữ nguyên. Đã triển khai qua sáu lát M6.4. | Complete; C2C implementation review iteration 2 DONE | C2C planning/spec review; 22 contract tests; Ruff; `git diff --check` | `docs: design M6.4 hook and reviewed outro` |
| M6.4 plan | Kế hoạch triển khai sáu lát: contract, authoring/gate, logo khai báo, timing/audio QA, Remotion, tích hợp/acceptance. Đã triển khai đủ sáu lát. | Complete; C2C implementation review iteration 2 DONE | 22 contract tests; Ruff; plan/spec self-review; `git diff --check` | `docs: plan M6.4 hook and outro implementation` |
| M6.4 contract | Profile `hook_outro_v1`, câu kết cố định, scene–line binding và yêu cầu logo ở cổng duyệt; dữ liệu legacy giữ mặc định riêng. | Complete; included in C2C implementation review iteration 2 DONE | 24 domain/contract tests; schema export; Ruff; `git diff --check` | `feat: define M6.4 script storyboard contract` |
| M6.4 authoring/gate | Lệnh `outro author` ghi script và storyboard có intent phục hồi; cổng duyệt y khoa từ chối intent dở hoặc thiếu logo, kiểm tra hook–claim–marker–source; packet hiển thị hook/outro. | Complete; included in C2C implementation review iteration 2 DONE | 63 workflow/CLI tests; Ruff; `git diff --check` | `feat: author reviewed PHY outro before medical gate` |
| M6.4 logo | Logo PYH decorative được khai báo `FLOURISH`/`brand`, có hash và rights ledger; cổng duyệt kiểm tra role/kind/file và đưa bytes logo vào hash duyệt. | Complete; included in C2C implementation review iteration 2 DONE | 83 domain/workflow tests; schema export; Ruff; `git diff --check` | `feat: register declared PHY logo for outro` (tên commit lịch sử trước khi sửa typo) |
| M6.4 timing | V2 dùng thời lượng storyboard theo nội dung; WAV thực đo phải vừa timeline trước render, QA lưu thời lượng audio, composition và đoạn hình cuối không tiếng; V1 giữ 45–90 giây. | Complete; included in C2C implementation review iteration 2 DONE | 69 render/produce/e2e tests; Ruff; `git diff --check` | `feat: match v2 video duration to reviewed audio timeline` |
| M6.4 Remotion | Composition lấy đúng frame cuối storyboard; frame đầu là hook, scene cuối dùng logo/mascot đã khai báo và caption trong vùng an toàn. | Complete; included in C2C implementation review iteration 2 DONE | 24 video tests; TypeScript typecheck; `git diff --check` | `feat: render hook-first PHY outro at exact duration` |
| M6.4 integration | E2E xác nhận hook ở frame 0, outro cuối với logo khai báo, QA WAV, hai cổng duyệt thủ công và caption từ hook; packet nêu nguồn gốc logo. | Complete; C2C implementation review iteration 2 DONE | 662 Python tests; Ruff; schema export không đổi; 24 video tests; typecheck; `git diff --check` | `feat: complete reviewed M6.4 hook and outro workflow` |
| M6.4 retry QA | Cache M6.4 nhận QA thời lượng đã chuyển sang `reviews`, kiểm tra lại số đo WAV và frame cuối, phục hồi được khi trạng thái dự án chưa cập nhật; retry không gọi lại TTS/render. | Complete; C2C implementation review iteration 2 DONE | 663 Python tests; Ruff; schema export không đổi; 24 video tests; typecheck; `git diff --check` | `fix: reuse promoted M6.4 timing QA on retry` |
| M6.5 design | Ngân sách visual tính theo frame storyboard đã duyệt; ba nhóm loại trừ nhau, override nằm trong medical hash; chart dùng SVG khai báo, AI production chờ M6.6. | Complete; C2C review DONE | Spec/plan review; Ruff; `git diff --check` | `docs: clarify M6.5 chart binding contract` |
| M6.5 plan | Năm lát test-first cho contract, medical packet, chart render, production QA và E2E; lát sáu acceptance/C2C. | Complete; Task 1–6 triển khai, acceptance passed; C2C review DONE | Plan/spec consistency; Ruff; `git diff --check` | `docs: plan M6.5 visual budget implementation` |
| M6.5 Task 1 | Contract domain/schema opt-in `m6_5_v1`, phân nhóm scene theo frame, biên số nguyên, override có rationale và feasibility; legacy mặc định không bị cưỡng chế. | Complete; included in C2C review DONE | 43 focused + 29 render regression tests; schema export/diff; Ruff; `git diff --check` | `feat: define deterministic M6.5 visual budgets` |
| M6.5 Task 2 | Medical gate cưỡng chế cùng visual-budget validator trước khi ghi approval; packet hiển thị frame/basis point/bound/override đã escape, vẫn chỉ có một cổng medical. | Complete; included in C2C review DONE | Gate/packet/domain/produce regression tests; Ruff; `git diff --check` | `feat: bind M6.5 budget to medical review` |
| M6.5 Task 3 | Bind chart M6.1 có intent/recovery manifest-first, ownership/hash/rights hai chiều; render đúng SVG khai báo qua Remotion và giữ legacy fallback. | Complete; included in C2C review DONE | 136 Python tests; 29 video tests; schema export/diff; Ruff; typecheck; `git diff --check` | `feat: render declared M6.1 chart assets` |
| M6.5 Task 4 | Production tính lại visual budget sau medical approval, trước TTS/render; `ai_clip` dừng với lỗi chờ M6.6; `video-qa.json` ghi đủ report cạnh timing M6.4; cache staged/promoted so canonical JSON với report tái tính nên thiếu, sửa field, thêm field hoặc đổi kiểu đều bị từ chối; retry/recovery không gọi lại TTS/render. | Complete; included in C2C review DONE | 46 produce tests; 60 render/gate/e2e-version tests; 91 review/package/CLI/e2e tests; Ruff; `git diff --check` | `feat: record recomputable M6.5 visual QA` |
| M6.5 Task 5 | Video packet tái tính report từ storyboard đã duyệt và báo QA production khớp/không khớp/thiếu; E2E zero-AI 75% whiteboard/outro và 25% crop/chart DATA_CHART đã bind: hook frame 0, không intro, outro pin, logo khai báo, 60 s theo nội dung, một lần TTS, hai cổng thủ công, package thủ công; legacy không đổi. | Complete; included in C2C review DONE | 173 packet/e2e/CLI/produce/gate/render tests; 29 video tests; typecheck; Ruff; `git diff --check` | `feat: integrate reviewed M6.5 visual budgets` |
| M6.5 Task 6 | Acceptance toàn bộ M6.5: không có audio/render/cache/model/credential/ảnh nguồn trong các commit M6.5; AI clip production vẫn chặn tới M6.6; hai cổng và đăng thủ công giữ nguyên. M6.5 complete sau C2C DONE. | Complete; C2C review DONE | `python -m pytest -q` (733 passed); `ruff check src tests tools`; `tools/export_schemas.py` không đổi schema; video test (29 passed)/typecheck; `git diff --check` | `docs: record M6.5 acceptance` |
| M6.6 design | Veo 3.1 Fast opt-in trước medical gate; AI clip có provenance/hash/rights typed, ownership một scene, duration 4/6/8 s và mọi bytes được medical hash; production không gọi provider; Remotion muted; disclosure chỉ phục vụ đăng thủ công. | Complete; C2C review DONE | Official Veo/Vertex/terms/TikTok review; live workspace C2C PLAN; `git diff --check` | `docs: design M6.6 optional Veo workflow`; `docs: resolve M6.6 review findings` |
| M6.6 plan | Sáu lát test-first: contract asset, provider/authoring recovery, medical binding, production/Remotion, disclosure E2E và acceptance/C2C. | Complete; implementation and C2C review DONE | Plan/spec consistency; schema and compatibility matrix | `docs: design M6.6 optional Veo workflow`; `docs: resolve M6.6 review findings` |
| M6.6 Task 1 | Contract `AI_CLIP` và provenance typed; role/ownership một scene; duration M6.5 đúng 120/180/240 frame; semantic/decorative policy; rights bắt buộc; referenced decorative clip vẫn kiểm byte/hash; legacy giữ nguyên. | Complete; C2C review iteration 2 DONE | 102 focused tests; 94 nearest regressions; deterministic schema export; Ruff; `git diff --check` | `feat: define reviewed AI clip assets`; `fix: expose AI clip media validator` |
| M6.6 Task 2 | Veo transport inject token/HTTP, request hash canonical và lỗi đã khử bí mật; ffprobe argv kiểm đúng MP4 dọc 24 fps 4/6/8 s; authoring pre-medical ghi bytes/manifest/quyền/storyboard theo intent R0–R4, retry cùng identity không gọi provider; CLI bắt buộc opt-in trước live boundary. | Complete; C2C review iteration 2 DONE | 66 provider/workflow/CLI tests; 122 Task 1 regressions; Ruff; `git diff --check` | `feat: author optional Veo clips safely`; `fix: use Veo fetch operation contract` |
| M6.6 Task 3 | Medical gate phục hồi intent AI hợp lệ, kiểm ownership/citation/quyền và đưa mọi AI clip kể cả decorative vào review hash; packet hiển thị classification, provider/model/duration/hash prefix/quyền (đã escape) mà không lộ prompt hoặc runtime secret. Review độc lập bổ sung test từ chối ledger thiếu/lệch, citation tới nguồn không tồn tại, decorative mang claim, và stale khi sửa prompt/classification/quyền/binding. | Complete; C2C review iteration 2 DONE | 60 gate/packet/authoring tests (mutation check: bỏ citation AI làm 2 test fail); Ruff; `git diff --check` | `feat: bind AI clips to medical review`; `test: cover AI clip medical gate refusals` |
| M6.6 Task 4 | Production chạy recovery AI rồi kiểm approval hash (bytes/provenance/quyền), resolver role/ownership và duration scene khớp provenance trước TTS/render; bỏ lỗi "unsupported until M6.6"; stage đúng bytes đã duyệt, hash vào render manifest/cache; không gọi provider. Render input/Zod: `ai_clip` chỉ nằm trong scene `ai_clip`, tối đa một, đúng một ở `m6_5_v1`, 120/180/240 frame. `AiClipScene` dùng `OffthreadVideo` muted qua `staticFile` một lần, không loop/trim/playback rate; overlay ảnh bỏ qua `ai_clip`. Zero-AI và legacy giữ nguyên. | Complete; C2C review iteration 1 DONE | 86 focused Python tests; 33 video tests; typecheck | `feat: render approved AI clips` |
| M6.6 Task 5 | Package v2 sinh `ai-disclosure.json` (schema 1.0, `contains_ai`, scene/path/provider/model/classification, hướng dẫn bật nhãn AI khi đăng thủ công) từ storyboard và asset manifest đã được medical approval hash, không chứa prompt/project/token, và đưa hash vào `manifest.json`; zero-AI giữ đúng payload cũ, không có file. E2E AI: fake transport + bytes dưới `tmp_path` → medical gate → production không gọi provider, stage đúng clip, hook frame 0, không intro, outro/logo pin, 63 s @30 fps, budget 1260/450/180 → video gate → package; đúng hai approval, state dừng ở `packaged`, không đăng. Review iteration 1 bổ sung exact payload cho v1 và assertion E2E rằng renderer AI dùng một `OffthreadVideo` muted, không loop/trim/rate/volume. | Complete; C2C review iteration 2 DONE | 37 focused package/review/E2E tests; Ruff; `git diff --check` | `feat: package AI disclosure guidance`; `test: strengthen M6.6 package compatibility` |
| M6.6 Task 6 | Acceptance M6.6: rà toàn bộ commit M6.6 không có media/model/cache/credential hay Google project ID thật; media được track chỉ là icon skill Remotion có trước M6.6. Không test nào gọi provider thật; CLI/Veo test inject token/HTTP giả. `produce`/`package`/`render` không import `video_ai` hay gọi generation. `GateKind` chỉ có `medical`/`video`; package dừng ở `packaged`, `published_manual` vẫn là bước thủ công. MP4 AI dưới `projects/**/assets/ai-clips/` và `workflow/staged-ai-clips/` đã có test `git check-ignore`. | Complete; C2C review iteration 1 DONE — M6.6 complete | `python -m pytest -q` (831 passed); `python -m ruff check src tests tools`; `python tools/export_schemas.py` hai lần không diff; `corepack pnpm --dir video test` (33 passed); `corepack pnpm --dir video typecheck`; `git diff --check` | `docs: record M6.6 acceptance`; `docs: refresh M6.6 acceptance review status` |
| M7 design | Lease single-writer trên shared filesystem đã probe; backup/restore bất biến và fail-closed; subprocess E2E; audit bảo mật offline; runbook vận hành. Giữ nguyên v1/v2, đúng hai cổng và đăng thủ công. | Proposed; awaiting C2C review | Spec self-review; `git diff --check` | pending |
| M7 plan | Sáu lát test-first: lease/storage, toàn bộ CLI mutation, backup/restore, process E2E, security/doctor/runbook và acceptance/C2C. | Proposed; implementation not started | Plan/spec consistency; `git diff --check` | pending |
| M7.1 | Lease project schema 1.0 độc lập, acquire bằng exclusive create, heartbeat/release theo token, recovery stale phân biệt cùng/khác host và chống PID reuse; atomic text write dùng temp duy nhất cùng thư mục; runtime lease bị Git ignore. Chưa bọc CLI mutation — thuộc M7.2. | Complete; awaiting inclusion in final M7 C2C review | 50 focused lease/storage/schema/gitignore tests; deterministic schema export; Ruff; `git diff --check` | `feat: add project write leases` |
| M7.2 | Toàn bộ lệnh CLI ghi vào project được bọc lease single-writer; dry-run giữ read-only. Operator status, mở packet và lease inspect vẫn hoạt động khi bận; recovery stale cùng host kiểm PID/start fingerprint, khác host bắt buộc cờ explicit và giữ bản ghi stale. Subprocess contention/failure dùng pipe barrier, không sleep. | Complete; awaiting inclusion in final M7 C2C review | 89 focused lease/CLI/operator/skill/subprocess tests chạy hai lần; toàn bộ Python 861 passed; Ruff; `git diff --check` | `feat: serialize project mutations` |
| M7.3 | Snapshot thư mục bất biến với `backup-manifest.json` schema 1.0 độc lập (path POSIX chuẩn đã sort, size, SHA-256; không hash chính nó). `healthvideo backup create <project> <backup-root> --id <id>` giữ lease ghi, loại `.healthvideo`/cache/model/credential/`.env`/pending cache/`source-documents`, nhưng giữ recovery journal và `staged-ai-clips`; từ chối link/reparse point và artifact có thẩm quyền tham chiếu path bị cấm; staging cạnh đích, hash lại rồi mới promote. `healthvideo backup restore <snapshot> <new-project-dir>` chỉ ghi đích mới: kiểm manifest đóng, entry bị cấm, thiếu/thừa/sửa bytes, layout v1/v2, cấu trúc approval và artifact được approval ràng buộc, rồi copy staging, xác minh lần hai và promote. Approval stale nguyên vẹn vẫn stale; không resign, migrate, đổi state hay publish. | Complete; awaiting inclusion in final M7 C2C review | 94 focused backup/CLI/schema/inventory tests (1 symlink test skipped khi Windows thiếu quyền symlink); mutation check journal/validation làm test fail; schema export hai lần deterministic; toàn bộ Python 893 passed, 1 skipped; Ruff; `git diff --check` | `feat: add verified project backup restore` |

## Kiến trúc

Python CLI điều phối artifact YAML/JSON theo schema. Domain thuần Python tách
khỏi TTS và renderer; Remotion nhận `render-input.json` bất biến.

## Lệnh kỹ thuật và tương thích v1

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

# M1: xem plan không ghi dữ liệu, rồi migrate sang sibling `<project>-v2`.
& .venv\Scripts\healthvideo.exe project migrate projects/2026/09/muoi-va-huyet-ap --dry-run
& .venv\Scripts\healthvideo.exe project migrate projects/2026/09/muoi-va-huyet-ap

# M2: mở gói HTML review, duyệt cổng y khoa/video hoặc từ chối và nối lại.
& .venv\Scripts\healthvideo.exe review open projects/2026/09/muoi-va-huyet-ap-v2 --gate medical
& .venv\Scripts\healthvideo.exe review approve projects/2026/09/muoi-va-huyet-ap-v2 --gate medical --reviewer "BS An" --yes

# M3: quản lý chủ đề và tìm kiếm bằng chứng y khoa.
& .venv\Scripts\healthvideo.exe topic create --title "Ăn mặn và huyết áp" --question "Ăn mặn có làm tăng huyết áp không?" --slug an-man-va-huyet-ap
& .venv\Scripts\healthvideo.exe topic list
& .venv\Scripts\healthvideo.exe topic select projects/2026/09/muoi-va-huyet-ap-v2 --slug an-man-va-huyet-ap
& .venv\Scripts\healthvideo.exe evidence search projects/2026/09/muoi-va-huyet-ap-v2 --query "sodium blood pressure"
& .venv\Scripts\healthvideo.exe evidence build-ledger projects/2026/09/muoi-va-huyet-ap-v2
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

Project v2 có AI clip đã duyệt được thêm `ai-disclosure.json` (scene, path,
provider, model, classification và hướng dẫn bật nhãn AI-generated content khi đăng
thủ công), sinh từ storyboard và asset manifest đã được medical approval hash và có
trong `payload_sha256`. File không chứa prompt, token hay cloud project ID; không
có AI clip thì không có file. Hướng dẫn không tự bật nhãn hay gọi nền tảng.

## Kiểm thử gần nhất

Ngày chạy acceptance M6.6 cục bộ: **15-09-2026** trên `codex/m1-workflow-kernel`.
`python -m pytest -q` (831 passed); `python -m ruff check src tests tools`;
`python tools/export_schemas.py` hai lần không đổi schema; `corepack pnpm --dir video
test` (33 passed) và `typecheck`; `git diff --check`. Không gọi Veo/provider thật;
M6.6 complete; Task 3/5 C2C DONE ở iteration 2, Task 4/6 DONE ở iteration 1.

Ngày chạy M2 gần nhất: **11-09-2026**. `python -m pytest -q` (407 passed);
`python -m ruff check src tests tools`; `git diff --check`. Golden v1 giữ nguyên 100%
hành vi; dual-golden test xác nhận cổng v2 chạy hoàn toàn offline không sửa fixture.

Ngày chạy MVP ban đầu: **08-09-2026**. `python -m pytest -v` (124 passed);
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

M5.2 thêm `CommandTTS` cho lệnh TTS cục bộ do operator cung cấp qua Python.
Lệnh nhận file văn bản UTF-8 và ghi WAV qua các tham số `{input}`, `{output}`;
không chạy qua shell. Ví dụ cấu hình dùng `CommandTTS(executable="local-tts",
arguments=("--input", "{input}", "--output", "{output}"),
model_id="candidate", voice_id="generic", runtime_id="revision")` sau khi đã
xác minh riêng lệnh, model và quyền sử dụng trên máy. Các
định danh provider/model/voice/runtime chỉ nhận alias công khai dài tối đa 128 ký tự,
bắt đầu bằng chữ hoặc số ASCII, các ký tự còn lại là chữ, số, dấu `.`, `_`, `-`.
`run_benchmark` nhận các
`BenchmarkCase` tiếng Việt và provider được cấp, ghi WAV vào thư mục output cục
bộ (nên đặt dưới `cache/`); record chỉ chứa thời gian, trạng thái và kiểm tra
WAV khách quan, không suy ra chất lượng giọng. Không commit audio, model hay
credential. `produce` hiện vẫn chỉ chọn `silent`; ElevenLabs và ASR chưa được
kích hoạt trong workflow.

M5.3 nối VieNeu-TTS v3 Turbo qua `CommandTTS` mà không thêm adapter mới: môi
trường riêng `cache/tts-venv` (`uv venv --python 3.11 cache/tts-venv` rồi
`uv pip install --python cache/tts-venv/Scripts/python.exe vieneu==3.6.4`,
ONNX/CPU, không torch), wrapper `tools/tts/vieneu_synth.py --input {input}
--output {output} [--voice Adam] [--precision fp32|int8]` ghi PCM16 48 kHz mono.
Lệnh `healthvideo tts-benchmark <cases.yaml> --output cache/<dir> --command <exe>
--arg ... --model-id ... --voice-id ...` chạy `tests/fixtures/tts-benchmark-cases.yaml`
(12 câu khó + 1 bài ghép 185 từ), ghi `benchmark.json` và trả exit 1 nếu có case
trượt ngưỡng khách quan: WAV PCM16 24/48 kHz có tín hiệu, RTF ≤ `--max-rtf`
(mặc định 1,0), tốc độ đọc 1,5–5,0 từ/s. Lệnh này không chấm phát âm hay độ tự
nhiên; kết quả đo thật và cách đọc ghi trong plan M5.3. Lần đầu chạy wrapper sẽ
tải model từ Hugging Face vào cache người dùng, ngoài Git.

M5.4: `tts-benchmark` nhận thêm `--asr-command <exe> --asr-arg ... --asr-model-id
... --max-wer 0.2`; `tools/tts/whisper_transcribe.py` (faster-whisper trong cùng
`cache/tts-venv`, `uv pip install --python cache/tts-venv/Scripts/python.exe
faster-whisper==1.2.1`) ghi transcript JSON; record thêm `transcript`, `wer`.
WER là lỗi gộp TTS+ASR và chưa quy đổi số–chữ, chỉ dùng để khoanh câu cần bác sĩ
nghe. `healthvideo produce <project> --tts vieneu --voice <preset> [--precision
fp32|int8] [--tts-python <python của tts-venv>]` dựng `NormalizedTTS(CommandTTS)`:
VieNeu tổng hợp rồi FFmpeg `loudnorm I=-16 TP=-1.5 LRA=11` về 48 kHz mono PCM16;
`runtime_id` trong manifest/cache mang hậu tố `-loudnorm`. `--voice` bắt buộc và
do bác sĩ chọn; `--tts silent` giữ nguyên. Mọi lần tổng hợp lại vẫn dừng ở cổng
duyệt video.

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
- [Thiết kế workflow khép kín A–Z](docs/superpowers/specs/2026-09-09-closed-loop-healthvideo-workflow-design.md)
