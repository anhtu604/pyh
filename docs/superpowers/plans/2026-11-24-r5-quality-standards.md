# R5.3 — Kế hoạch đưa chuẩn chất lượng vào xưởng

> **Cho người thực hiện:** dùng skill `superpowers:executing-plans`, triển khai từng việc và kiểm trước khi chuyển tiếp. Đây là kế hoạch tương lai, không phải lệnh thực thi trong phiên viết tài liệu.

**Mục tiêu:** video giải thích sâu theo câu hỏi người xem, hình y khoa có phép và diễn hành rõ, giảm bảng chữ và vòng sửa tích lũy.
**Kiến trúc:** mở rộng tùy chọn `quality_profile: r5_v1`, giữ legacy và hai cổng PIN. Python giữ nguồn/hash/timing/retry; Remotion hiển thị shot đã resolve qua registry dùng chung.
**Công nghệ:** Python/Pydantic/pytest/Ruff; Remotion/React/TypeScript/Zod/Vitest; không thêm framework/dependency app.
**Spec:** [2026-11-24-r5-quality-standards-design.md](../specs/2026-11-24-r5-quality-standards-design.md).

## Ràng buộc và trình tự nghiệm thu

- Phiên R5.3 hiện tại chỉ tạo hai tài liệu, không commit hay sửa bất cứ file thực thi nào. Các đường dẫn dưới đây là allowlist **đề xuất cho brief triển khai sau**, không phải quyền sửa hiện tại. Cần thêm file ngoài brief của một việc thì dừng báo lead.
- Không Vibi/FLUX/render thật hoặc bật xưởng trước R5.3.11 và lệnh cho phép riêng của bác sĩ. Dùng fixture, mock, markup và timing giả rõ ràng cho kiểm offline; không nhận chúng là nghiệm thu video thật.
- Không Opus/astra/Carbon high; agy mặc định `gemini-4-neon-medium`. `orchestrator-neon` chỉ tăng cường hữu hạn, xác nhận ID CLI trước cấu hình. Codex dùng `gpt-6.1-sol` cho Python có bất biến. Không gọi agent/model trong phiên tài liệu.
- Không tách `dashboard.html`, `dashboard.py`, `produce.py`, `cli.py`; không gộp ba agent chấm; không bỏ legacy (quy tắc `CLAUDE.md:123`).
- Không sửa/xóa mục cũ của `profiles/doctor-feedback.yaml`, `profiles/factory-standards.yaml`; mọi thêm chuẩn có phiên bản và ghim revision. Tiến độ do lead cập nhật sau trong phạm vi được giao, không tạo sổ tiến độ mới trong kế hoạch này.
- Ngưỡng đề xuất D1–D4 phải được chốt trước khi bật chuẩn mới mặc định. Trong lúc chưa chốt chỉ kiểm fixture với giá trị dự thảo; không áp lên project sống. Chốt D5/pilot là việc riêng, không suy từ chốt ngưỡng.

## Lệnh kiểm chuẩn (K)

Chép đúng cách gọi từ `CLAUDE.md:89`–`:98`; các mã K dưới đây là lệnh thật, không phải lời báo đã chạy:

```powershell
# K-P: Python toàn bộ trong worktree, Python của checkout chính
$env:PYTHONPATH='src'; & 'E:\Protect Your Health\.venv\Scripts\python.exe' -m pytest -q
# K-L: lint Python
& 'E:\Protect Your Health\.venv\Scripts\python.exe' -m ruff check src tests tools
# K-V và K-T: chạy ở checkout chính sau khi lead đưa đúng thay đổi cần kiểm sang đó
video\node_modules\.bin\vitest run
video\node_modules\.bin\tsc --noEmit
# Nếu lead xác nhận đã hoàn tất việc 0.3 theo CLAUDE, K-V có thể dùng:
pnpm --dir video test
# K-D: trong worktree
git diff --check
```

Không chạy pytest cùng Vitest. Không mặc nhiên dùng video test ở checkout chính chưa có diff triển khai để xác nhận worktree. Lead chọn đưa diff sang môi trường kiểm riêng hoặc dùng đường node_modules checkout chính với root video worktree; ghi rõ root code thực được kiểm. Lệnh Python chọn lọc: giữ cùng interpreter/PYTHONPATH như K-P, thêm các đường test được nêu từng việc trước `-q`. Mỗi việc Python chạy test chọn lọc + K-L + K-D; mỗi việc TS chạy K-V + K-T + K-D. Cuối tích hợp chạy toàn bộ theo thứ tự.

## Trọng điểm review

| Điều kiện dễ sót | Hành vi phải giữ | Việc sở hữu test |
|---|---|---|
| Revision cũ thiếu mọi trường R5 | Đọc/serialize và hash không đổi; approval/cache cũ vẫn kiểm đúng | .1, .8 |
| WAV dài/ngắn hơn ước lượng, anchor lặp hoặc mất | Resolve đúng hoặc chặn rõ; không đoán tỷ lệ, không cắt lời | .3, .8 |
| Hai overlay chữ chồng nhau; caption ngang không hiện | Tính hợp interval, không cộng trùng; từ không hiện không tính nhịp | .3, .7 |
| URL nguồn đúng nhưng redirect ra ngoài; ảnh thiếu quyền/SHA | Chặn trước ghi asset, không tự tải nguồn thay thế | .2 |
| Restart/rerender/reset cycle/đổi model | Không xóa quota chất lượng hoặc phá độc lập maker/critic | .4, .9 |

## Bản đồ file và phụ thuộc

File mới trong kế hoạch đều ghi “tạo”; còn lại là đích sửa dự kiến, không phải khẳng định chúng đã có chức năng R5. Điểm code hiện hành đối chiếu ở spec §4, §5, §7; mỗi brief phải mang theo spec và đúng allowlist của việc đó.

Đường găng: `.1 → .3 → .7 → .8 → .10 → .11`. Nhánh hình: `.1 + .2 → .5 → .6 → .7`. Nhánh hợp đồng: `.1 → .4`; `.3 + .4 → .9`. `.8 + .9` phải xong trước `.10`.

- `.2` và `.4` có thể song song sau khi giao diện .1 được cố định: khác file. `.3` và `.5` song song sau .1/.2; `.5` chỉ tạo component TS riêng, không sửa types/HealthVideo.
- `.6` sau .5; `.7` sau .3/.6 vì cần cùng shape shot và component. `.8` và `.9` chạy song song nếu khóa quyền file đúng như dưới.
- Không ai sửa file do người khác đang giữ. Đặc biệt `.4` giữ toàn bộ skill/prompt và company/voice; `.9` chỉ sửa runtime/test Python. `.1` giữ schema chung; `.3` không sửa lại storyboard/types, `.8` chỉ bổ sung tích hợp produce/render input sau bàn giao .1.
- Trước mỗi nhánh triển khai lead viết brief file cụ thể, tiêu chí và lệnh kiểm; không tự gộp task vào một lần sửa lớn. Không tự commit trong brief nhân viên.

## R5.3.1 — Hợp đồng R5 và tương thích legacy

**Người làm:** codex; chưa thay workflow đang chạy. Căn cứ hiện trạng: `src/healthvideo/domain/storyboard.py:337`, `:512`, `src/healthvideo/render/input.py:45`, `video/src/types.ts:323`.
**File sửa:** `src/healthvideo/domain/storyboard.py`, `src/healthvideo/domain/visual_budget.py`, `src/healthvideo/render/input.py`, `video/src/types.ts`, `src/healthvideo/workflows/factory_standards.py`.
**File tạo:** `src/healthvideo/domain/quality_standards.py`, `tests/domain/test_quality_standards.py`.
**Test sửa:** `tests/domain/test_storyboard.py`, `tests/domain/test_visual_budget.py`, `tests/render/test_input.py`, `video/src/types.test.ts`.
**Giao diện bàn giao:** `R5Contract`, `R5Shot`, `ResolvedR5Shot`, `QualityReport` (model Python/Zod đồng dạng); trường/enum theo spec §5, `quality_profile` vắng không phát sinh key. Thêm `validate_r5_contract(board: Storyboard, script: Script) -> None`; không kiểm nội dung y khoa bằng keyword.

- [ ] Test contract: 2–4 câu hỏi, ID thật, đáp đủ ID, block có question/takeaway/update; từ chối component không thuộc registry ID, shot thiếu ranh giới và trường lạ trong dữ liệu R5.
- [ ] Thêm schema tùy chọn; thiếu profile giữ serialize/hash fixture cũ. Chuẩn R5 không ép chart/4 subject; test cũ vẫn kiểm tỷ lệ và variety cho legacy.
- [ ] Mở pinning chuẩn R5 có phiên bản; không đổi snapshot revision đã ghim. Chưa ghi mục mới vào file append-only ở việc này.
- [ ] Kiểm: K-P chọn `tests/domain/test_quality_standards.py tests/domain/test_storyboard.py tests/domain/test_visual_budget.py tests/render/test_input.py`, K-L, K-V, K-T, K-D. Xong khi Python/TS round-trip cùng payload, case legacy không khác byte/hash kỳ vọng.

## R5.3.2 — Catalog hình có phép và tải có kiểm soát

**Người làm:** codex (quyền/path/hash); agy chỉ đọc và kiểm hình sau khi có lượt tải được phép riêng. Không tải mạng trong kiểm offline.
**File sửa:** `src/healthvideo/domain/medanim_library.py`, `src/healthvideo/workflows/medanim_library.py`, `library/medanim/liver-enzyme-leak/animation.yaml`.
**File tạo:** `src/healthvideo/visuals/medanim_assets.py`, `library/medanim/liver-enzyme-leak/assets.yaml`, `tests/visuals/test_medanim_assets.py`.
**Test sửa:** `tests/workflows/test_medanim_library.py`.
**Giao diện:** `load_asset_catalog(path: Path) -> tuple[MedAnimAsset, ...]`; `validate_download_url(url: str) -> None`; `fetch_licensed_asset(record: MedAnimAsset, destination: Path) -> Path`, HTTP client được inject/mock, kiểm mọi redirect. Ngưỡng đề xuất 5 MB/file; source page/download host phải thuộc allowlist xác nhận theo từng kho, không wildcard tên miền tùy ý.

- [ ] Viết fixture nguồn Servier/NIAID/DBCLS/Reactome và case giấy phép rỗng/SA/NC/ND, sai SHA, traversal/symlink, redirect ngoài allowlist/private IP, quá kích thước; tất cả lỗi phải chặn.
- [ ] Trích provenance đang có sang assets.yaml không đổi asset bytes/giấy phép; animation.yaml tham chiếu ID và loader đối chiếu, giữ đọc entry cũ. Không tải thêm Bioicons/atlas khác, không đổi giấy phép asset cũ.
- [ ] Tạo used-asset list cho credit và revision snapshot; thêm ngày lấy/biến đổi/chứng cứ license có thật hoặc ghi thiếu, không bịa ngày tải cũ. Hash kiểm lại khi chép.
- [ ] Kiểm: K-P chọn `tests/visuals/test_medanim_assets.py tests/workflows/test_medanim_library.py`, K-L/K-D. Xong khi case thiếu provenance không được chọn render; catalog cũ đọc được. Pilot mới được nhập bộ liver-anatomy qua brief riêng có file cụ thể.

## R5.3.3 — Resolve shot và đo chất lượng bằng frame

**Người làm:** codex. Căn cứ: `src/healthvideo/render/timing.py:128`, `src/healthvideo/render/beats.py:47`, `:76`.
**File tạo:** `src/healthvideo/render/quality.py`, `tests/render/test_quality.py`.
**File sửa:** `src/healthvideo/render/beats.py`, `src/healthvideo/workflows/draft.py`; test `tests/render/test_beats.py`, `tests/workflows/test_draft.py`.
**Giao diện:** `resolve_r5_shots(board: Storyboard) -> Storyboard` nhận word alignment đã gắn hoặc timing ước lượng gắn cờ; `measure_r5_quality(board: Storyboard) -> QualityReport`; `validate_r5_quality(report: QualityReport, *, estimated: bool) -> None`. Report có source intervals, numerator/denominator frames, count/median/P90 từng nhóm và trạng thái chưa kiểm thủ công.

- [ ] Test 1000 frame có text [0,100), [50,150) cho hợp 150 frame; đúng 15% đạt, 151 frame không đạt với dự thảo D1. Bảng phiếu/credit/overlay đều tính, nhãn/thanh tầng báo riêng.
- [ ] Test nhóm story/mechanism riêng; median/P90 nearest-rank đúng danh sách shot; nhóm rỗng N/A. Thêm case 25s cơ chế có ≥3 bước và lý do; chuyển động nền không đủ thay đổi nhân quả.
- [ ] Test anchor thiếu/lặp/ngoài scene, shot gap/overlap, WAV ±10%, chuỗi nhiều scene cùng line. Không dùng first-token hay fallback phần trăm trong bản aligned.
- [ ] Với R5, QA nhịp chỉ dùng action/shot thực hiện; words/caption 16:9 không làm mới đồng hồ. Pre-gate gom lỗi một lượt, chưa tổng hợp giọng thật. Cùng hàm đo dùng lại sau TTS.
- [ ] Kiểm: K-P chọn `tests/render/test_quality.py tests/render/test_beats.py tests/workflows/test_draft.py`, K-L/K-D. Xong khi lỗi mang scene/shot/frame/đích nhận sửa, không đổi lời/script/hash khi resolve runtime.

## R5.3.4 — Hợp đồng vai, model, lời và điểm chạm TOFU

**Người làm:** codex soạn hợp đồng/cấu hình; agy Neon kiểm ví dụ hình offline theo brief sau. Không gọi model để benchmark trong việc viết cấu hình.
**File sửa:** `profiles/company.yaml`, `profiles/voice.yaml`; các `SKILL.md` dưới `.agents/skills/`: `pyh-researcher`, `pyh-scout`, `pyh-medical-expert`, `pyh-writer`, `pyh-script-critic`, `pyh-storyboard-director`, `pyh-voice-director`, `pyh-art-director`, `pyh-editor`, `pyh-product-critic`, `pyh-shorts-producer`, `pyh-copywriter`, `pyh-coordinator`, `pyh-coordinator-senior`, `pyh-feedback-analyst`, `pyh-repair-engineer`.
**Prompt sửa (trong `src/healthvideo/prompts/`):** `research.md`, `draft.md`, `revise_medical.md`, `script_review.md`, `storyboard_design.md`, `voice_prep.md`, `visual_review.md`, `revise_production.md`, `revise_product.md`, `product_review.md`, `shorts_plan.md`, `posts.md`.
**Test sửa:** `tests/test_company.py`, `tests/test_prompts.py`.

- [ ] Đồng bộ spec §2/§6 vào skill và prompt: nguồn giải phẫu/sinh lý qua Europe PMC, question→block→takeaway→recap, cập nhật có ngày/giới hạn, không writer làm khung bảng để qua validator.
- [ ] Xóa quota chart/source_card và hợp đồng ép mascot vào giải phẫu cận; mở quyền editor đúng component/dải dòng được giao, không cho sửa storyboard/voice/manifest khóa. Giữ ba khâu chấm độc lập.
- [ ] Giao shorts_producer sở hữu cut range/hook/payoff/caveat trước khóa; storyboard hiện thực 9:16, copywriter chỉ đóng gói caption/title. Lời clip mới phải được medical gate bao phủ, không đổi lời sau duyệt. Giữ khác biệt phụ đề ngang/dọc.
- [ ] Cấu hình theo bảng spec §6; kiểm ID Neon/O trước khi ghi, fallback không quay sang model cấm hoặc maker đã dùng. Giữ voice ID Anh Tu, speed 1.18; thiếu voice không dùng giọng thay.
- [ ] Test tình huống thiếu claim/abstract-only, TOFU không bán hàng, cập nhật không có nguồn mới, editor vượt quyền, fallback hết model độc lập. Kiểm nội dung bằng packet fixture và review tay, không chỉ grep đủ keyword.
- [ ] Kiểm: K-P chọn `tests/test_company.py tests/test_prompts.py`, K-L/K-D. Xong khi cả 16 vai có input/output/done_when/đích trả thiếu dữ liệu và prompt không ghi đè ngược skill mới.

## R5.3.5 — Bộ component zoom, thanh tầng, câu chốt và phiếu VN

**Người làm:** agy Neon. Input: giao diện .1, catalog .2, code nguồn P chỉ đọc theo spec §7.2.
**File tạo trong `video/src/components/r5/`:** `ScaleChain.tsx`, `ZoomChain.tsx`, `TakeawayCard.tsx`, `VnLabSheet.tsx`, `ReferenceDistribution.tsx`, `CreditCard.tsx`, `R5Components.test.tsx`.
**Giao diện:** component nhận `ResolvedR5Shot`, layout, danh sách asset revision và giá trị/nhãn đã có claim; ZoomChain nhận from/to anchor; CreditCard nhận used assets. Không sửa file chung types/HealthVideo ở việc này.

- [ ] Viết test markup/geometry hai layout: bên cơ thể, anchor nối tầng, ≥1 vùng định vị; thẻ/mascot không che vùng giải phẫu cận, nhãn không chồng caption dọc.
- [ ] Trích điều khiển từ Chapter1ZoomChain/Shared; bỏ đường dẫn P/cache, mảng tầng gan cố định và số ALT/AST/ngưỡng hardcode. Phiếu có bốn cột và H, dữ liệu trống dùng dấu —, không tự tạo ca bệnh.
- [ ] Đường cong nhận dữ liệu và nhãn “minh họa”; không tuyên bố mọi chỉ số Gaussian. Credit chỉ chứa asset thực dùng, chia trang trong ngân sách chữ.
- [ ] Kiểm K-V/K-T/K-D; không render thật. Xong khi component không import `proto/`, không gọi API, frame thuần xác định và cùng props cho cùng markup/geometry.

## R5.3.6 — Rig đặc trưng men vào máu

**Người làm:** agy Neon; chuyên gia/bác sĩ kiểm nghĩa giản lược trong gói duyệt sau, không thêm cổng thay thế.
**File tạo:** `video/src/medanim/R5LiverLeakSignature.tsx`, `video/src/medanim/R5LiverLeakSignature.test.tsx`.
**Input/output:** từ `P/video/src/proto/LiverLeakSignature.tsx:38`, `P/video/src/proto/Chapter1Deep.tsx:35` → rig nhận clock/labels resolved và asset revision, không tự quyết thời điểm bằng %.

- [ ] Kiểm trạng thái trước–trong–sau: men trong tế bào → đổi màng theo mô tả có nguồn → men trong máu/ống nghiệm; giữ thực thể qua các mốc, không coi rung nền là cơ chế.
- [ ] Bỏ hardcode cache/đường tải, nhãn/claim lâm sàng và camera chỉ hợp 16:9; cấu hình portrait có đường đi đầy đủ. Không tự vẽ cơ thể/cơ quan khi đã có asset có phép.
- [ ] Kiểm K-V/K-T/K-D. Xong khi rig đọc được cùng resolved action interface .1/.3, không phụ thuộc Chapter1DeepData/StorySceneR2/V4 và không import cảnh FLUX.

## R5.3.7 — Renderer R5, bỏ tab→bảng và bảo vệ caption policy

**Người làm:** agy Neon. Căn cứ đường hiện hành: `video/src/scenes/MechanismScene.tsx:163`, `video/src/scenes/WhiteboardScene.tsx:70`, `video/src/components/Captions.tsx:88`.
**File tạo:** `video/src/scenes/R5ShotScene.tsx`, `video/src/scenes/R5ShotScene.test.tsx`.
**File sửa:** `video/src/HealthVideo.tsx`, `video/src/components/AuthoredPanels.tsx`, `video/src/scenes/MechanismScene.tsx`, `video/src/scenes/WhiteboardScene.tsx`.
**Test sửa:** `video/src/HealthVideo.test.tsx`, `video/src/scenes/AuthoredPanels.test.tsx`, `video/src/scenes/SpokenVisuals.test.tsx`.

- [ ] Định tuyến R5 theo registry component .5/.6; shot là một điểm nhìn chính, transition dùng anchor. Legacy không đổi renderer.
- [ ] Với R5 từ chối tab layout ngầm, không tự chuyển cơ chế sang worksheet; phiếu phải khai báo VnLabSheet. Giữ test bảng cũ ở nhóm legacy, không bỏ kiểm đơn vị/nguồn.
- [ ] Test tất cả kind/component R5 ở 16:9 không có caption/band lời; 9:16 có phụ đề, kể cả wrapper và khi có mascot. Không xóa word timing hoặc caption file rời.
- [ ] Kiểm K-V/K-T/K-D. Xong khi chọn profile rõ, component lạ fail closed, markup khác nhau đúng hai định dạng và không mang scene FLUX cũ vào renderer mới.

## R5.3.8 — Tích hợp sản xuất, cache, nguồn và cổng

**Người làm:** codex. Điểm tích hợp đã đọc: `src/healthvideo/workflows/produce.py:764`, `:840`, `:910`; `src/healthvideo/workflows/gate_review.py:158`.
**File sửa:** `src/healthvideo/workflows/produce.py`, `src/healthvideo/render/input.py`, `src/healthvideo/workflows/long_form.py`, `src/healthvideo/workflows/gate_review.py`.
**Test sửa:** `tests/workflows/test_produce.py`, `tests/workflows/test_produce_long_form.py`, `tests/workflows/test_gate_review.py`, `tests/render/test_input.py`.

- [ ] Gắn resolve/measure .3 sau retime/alignment, ghi quality-report và input/renderer hash; dùng cùng validator pre-gate. Runtime không sửa contract lời/claim đã khóa.
- [ ] Snapshot asset/license/catalog dùng vào revision, hình cơ chế semantic có hash cổng; đổi source/asset/contract làm approval stale đúng luồng. Test source thay byte, mất license, thay profile, không tự mở cổng hay ghi approval.
- [ ] Cache khóa theo voice ID/speed/lexicon, resolved shots/text windows, profile/assets/renderer; speed đổi chỉ dùng WAV phù hợp; chương không đổi tái dùng cache. Test fixture hai chương chỉ đổi một chương.
- [ ] Test legacy không phát sinh key/hashes mới, WAV ±10% không cắt lời, anchor hỏng dừng trước render, report interval chồng tính đúng. Mock TTS/render, không gọi voice_v5.py/render_v6.cjs.
- [ ] Kiểm K-P chọn `tests/workflows/test_produce.py tests/workflows/test_produce_long_form.py tests/workflows/test_gate_review.py tests/render/test_input.py`, K-L/K-D. Xong khi không có đường bypass PIN và cache không làm cổng nhận artifact cũ.

## R5.3.9 — Budget review và chẩn đoán tồn tại qua restart

**Người làm:** codex. Căn cứ: `src/healthvideo/workflows/product_review.py:70`, `:530`; `src/healthvideo/workflows/script_review.py:26`; `src/healthvideo/workflows/visual_review.py:32`.
**File tạo:** `src/healthvideo/workflows/review_budget.py`, `tests/workflows/test_review_budget.py`.
**File sửa:** `src/healthvideo/workflows/script_review.py`, `src/healthvideo/workflows/visual_review.py`, `src/healthvideo/workflows/product_review.py`, `src/healthvideo/workflows/scoped_review.py`, `src/healthvideo/workflows/repair_service.py`.
**Test sửa:** `tests/workflows/test_script_review.py`, `tests/workflows/test_visual_review.py`, `tests/workflows/test_product_review.py`, `tests/workflows/test_scoped_review.py`, `tests/workflows/test_repair_service.py`.
**Giao diện:** `consume_review_budget(revision: Path, stage: str, event_id: str) -> int` ghi bền vững/idempotent; `review_budget_status(revision: Path, stage: str) -> dict` chỉ đọc. Dùng atomic write/lock theo mẫu repo, không sửa lịch sử review cũ.

- [ ] Test script 2/hình 3/sản phẩm 3 lần chấm tối đa; cùng issue hai lần dừng sớm; event_id lặp không tăng hai lần, hai process không vượt trần.
- [ ] Test restart/reset submitted/rerender hash mới/failover/cùng fingerprint không reset; hai chẩn đoán cùng nguyên nhân là trần kỹ thuật. Chỉ revision mới hợp lệ theo yêu cầu bác sĩ mới có budget mới.
- [ ] Hết budget trả brief đúng vai + chứng cứ, giữ chưa đạt và không tự submit gate; lỗi an toàn không được đổi thành issue không chặn. Giữ độc lập maker/critic cả fallback; phần này không sửa company của .4.
- [ ] Kiểm K-P chọn các test của việc này, K-L/K-D. Xong khi mô phỏng chuỗi reset 24 lần vẫn không tạo 24 lượt chấm hoặc 60 lần chẩn đoán, log vẫn giải thích được từng lần tiêu budget.

## R5.3.10 — Chốt chuẩn, kiểm tích hợp offline và bàn giao

**Người làm:** codex kiểm bất biến; agy Neon kiểm shape/markup hai layout. Chỉ sau .4/.7/.8/.9 đạt.
**File sửa:** `tests/workflows/test_explain_first.py`, `tests/workflows/test_gate_long_form.py`, `tests/workflows/test_clips_render.py`; **tạo** `tests/e2e/test_r5_quality_offline.py`.
**File cấu hình:** `profiles/factory-standards.yaml` chỉ thêm mục R5 đã được bác sĩ chốt; không sửa/xóa mục cũ. Không chạm dashboard/progress trong brief này.

- [ ] Fixture tổng hợp có nhiều khối, 2–4 câu hỏi, một cập nhật, một đoạn zoom, phiếu VN, credit và clip dọc; claim chỉ là fixture có đánh dấu, không nhập nguồn y khoa giả vào thư viện thật.
- [ ] Test luồng nghiên cứu→lời→phân cảnh→estimated QA→hai cổng giả lập qua helper test hợp lệ→produce mock→review→package; test thiếu PIN/approval/hash stale phải bị chặn. Không dùng file approval viết tay ở dự án sống.
- [ ] Đối chiếu D1–D4 với spec; chỉ thêm chuẩn mới sau xác nhận. Revision mới ghim đúng chuẩn; legacy snapshot không bị cập nhật hồi tố. Nếu bác sĩ chọn ngưỡng khác thì cập nhật fixture/code trong brief bổ sung đúng file, không sửa ngầm spec đã chốt.
- [ ] Chạy K-P toàn bộ → K-L → K-V → K-T → K-D tuần tự; ghi root/command/exit/output thật. Review toàn diff và phạm vi, xác nhận không cache/audio/key/render vào Git. Chưa commit nếu brief chưa giao.
- [ ] Xong khi báo rõ “offline đạt, chưa nghiệm thu video thật”, mọi mục spec có test hoặc checklist người xem/nghe; chuẩn đã có đường rollback bằng không chọn R5 ở revision mới, không sửa project khóa.

## R5.3.11 — Một chủ đề thật từ đầu đến cuối, sau khi bác sĩ cho phép bật lại xưởng

**Người làm:** lead điều phối; agy Neon xử lý hình/Remotion; codex xử lý lỗi Python theo brief hữu hạn; bác sĩ duyệt hai cổng PIN.
**Phụ thuộc bắt buộc:** .10 đạt, D5 được chọn, bác sĩ cho phép bật lại xưởng rõ ràng. Chưa có các điều kiện đó thì dừng ở bàn giao .10, không tự làm pilot.
**File dữ liệu được tạo qua CLI/app:** `projects/<slug>/project.yaml` và revision mới `evidence/`, `script/`, `explainer/`, `storyboard/`, `assets/`, `workflow/`, `reviews/`, `audio/`, `renders/`, `posts/`, `publish/`; runtime queue/log theo CLI, không commit artifact tạm.
**File thư viện (nếu chọn gan):** `library/medanim/liver-anatomy/assets.yaml`, `library/medanim/liver-anatomy/assets/niaid-human-anatomy-519.png`, `servier-digestive-system.png`, `servier-liver-gallbladder.png`, `servier-liver-lobule.png`, `servier-bile-secretion.png` trong cùng thư mục assets. Lead chốt allowlist riêng trước nhập từ P, kiểm license/SHA, không copy toàn cache. Chủ đề khác cần brief asset có tên cụ thể trước làm.

- [ ] Tạo dự án mới theo chủ đề bác sĩ chọn, đủ nghiên cứu Europe PMC và nguồn nền/cập nhật; đi toàn bộ vai, không dùng hướng duyệt v6 thay duyệt kịch bản mới. Kiểm estimated report rồi bác sĩ duyệt y khoa bằng PIN trong app.
- [ ] Dựng Vibi Anh Tu 1.18, 16:9 và clip dọc bằng pipeline mới; ghi ký tự gửi/cache hit, wall time từng bước, render/video ratio, model thực chạy và coverage token. Chỉ gọi API/tải theo quyền pilot đã cấp, không FLUX cơ chế.
- [ ] Kiểm K-P/K-L/K-V/K-T/K-D trước nhận bản sửa code; QA video giải mã toàn MP4, nghe thuật ngữ/ASR lệch, xem mọi chuyển tầng/câu chốt ở 720p và clip dọc trên điện thoại; đo đủ §3 theo frame thật.
- [ ] Bác sĩ xem video và tự trả lời 2–4 câu hỏi; nhận xét riêng độ sâu/chuyên môn và cảm giác slide. Budget hết thì xử lý theo D4, không dựng bản không đổi để thử vận may. Đổi lời/claim phải quay lại cổng y khoa.
- [ ] Qua product review rồi bác sĩ duyệt cổng video bằng PIN; đóng gói đúng revision/hash. Xong khi một chủ đề đi hết hai cổng, đủ video/clip/posts/credit/nguồn và báo số đo thật so với ngưỡng đã chốt. Không tự đăng; xuất bản cần tài khoản/quyền hiển thị và yêu cầu rõ theo quy tắc hiện hành.

Nếu pilot chưa đạt mỹ thuật nhưng kiểm offline đạt, ghi rõ hai kết quả khác nhau; không kết luận “xưởng đã đạt chuẩn mới”. Không sửa spec để hợp thức hóa kết quả đo.
