# Protect Your Health

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
liệu. M2–M7 được giữ ở mức deliverable để tránh lỗi thời. MVP v1 vẫn là đường
chạy tương thích ổn định; review experience v2 thuộc M2.

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

# M1: xem plan không ghi dữ liệu, rồi migrate sang sibling `<project>-v2`.
& .venv\Scripts\healthvideo.exe project migrate projects/2026/09/muoi-va-huyet-ap --dry-run
& .venv\Scripts\healthvideo.exe project migrate projects/2026/09/muoi-va-huyet-ap

# M2: mở gói HTML review, duyệt cổng y khoa/video hoặc từ chối và nối lại.
& .venv\Scripts\healthvideo.exe review open projects/2026/09/muoi-va-huyet-ap-v2 --gate medical
& .venv\Scripts\healthvideo.exe review approve projects/2026/09/muoi-va-huyet-ap-v2 --gate medical --reviewer "BS An" --yes
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
