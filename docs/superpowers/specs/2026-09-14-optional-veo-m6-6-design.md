# M6.6 — Veo tùy chọn với provenance và duyệt y khoa

**Ngày:** 14-09-2026  
**Trạng thái:** Thiết kế đã được người dùng duyệt; chờ review plan trước implementation

## 1. Mục tiêu và ranh giới

M6.6 cho phép operator chủ động tạo một clip minh họa ngắn bằng Veo trước cổng
duyệt y khoa, đăng ký đúng bytes vào asset manifest và license ledger, gắn clip
vào đúng một scene `ai_clip`, rồi dùng pipeline M6.5 hiện có để duyệt, render và
đóng gói. Veo là tùy chọn: dự án không có AI clip, dự án legacy và v1 tiếp tục
chạy như hiện tại.

Generation không nằm trong `produce`. Production chỉ đọc asset đã khai báo và
đã được medical approval bao phủ; không tạo request Veo, không poll operation,
không đọc credential và không sửa storyboard/manifest. Không thêm workflow state,
cổng duyệt, TTS hoặc hành vi đăng tự động.

Clip chỉ phục vụ truyền thông giáo dục sức khỏe công cộng, không dùng Veo để chẩn
đoán, tư vấn cá nhân, ra quyết định lâm sàng hoặc thay thế nhân viên y tế.

## 2. Baseline nhà cung cấp đã xác minh

Baseline được kiểm tra ngày 14-09-2026 từ tài liệu chính thức:

- model GA mặc định: `veo-3.1-fast-generate-001`;
- khung dọc `9:16`, MP4, 24 fps, 720p hoặc 1080p, thời lượng 4/6/8 giây;
- M6.6 yêu cầu 1080p để khớp composition 1080×1920;
- API là long-running operation; adapter che giấu HTTP, polling và base64;
- khi không đặt `storageUri`, output có thể được trả dưới dạng bytes/base64;
- Veo 3.0 đã ngừng ngày 30-06-2026; model M6.6 phải là cấu hình tường minh để
  việc đổi model sau này không âm thầm thay provenance;
- quota và giá được coi là dữ liệu vận hành có thể đổi, không hard-code thành
  lời hứa chi phí trong domain hoặc package.

Nguồn chính thức:

- <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate>
- <https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation>
- <https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing>
- <https://cloud.google.com/terms/service-terms>
- <https://support.tiktok.com/en/using-tiktok/creating-videos/ai-generated-content>

Nếu model hoặc response contract thay đổi, live adapter phải fail closed và cần
thay spec/test trước khi chấp nhận shape mới.

## 3. Kích hoạt và command authoring

Lệnh mới có dạng:

```text
healthvideo ai-clip generate <project> --scene-id <id> --prompt <text> \
  --duration-seconds 4|6|8 --allow-live-generation \
  --google-project <id> --location <location> \
  --source <text> --creator <text> --license <text> --rights-basis <text> \
  [--requested-seed <int>]
```

`--allow-live-generation` là consent bắt buộc cho request thật. Credential tồn
tại, project/location tồn tại hoặc chọn provider không được coi là consent. Thiếu
cờ phải dừng trước khi lấy token hoặc truy cập mạng. Command chỉ chạy trên revision
v2 ở trạng thái authoring trước medical approval, không có medical approval hiện
hành và storyboard bật `visual_budget_profile=m6_5_v1`.

Output path do workflow xác định từ scene, dưới `assets/ai-clips/`; scene ID phải
an toàn khi dùng làm tên file. Không nhận absolute path, không ghi đè asset khác,
không thay clip đã thuộc scene khác và không sửa revision đã duyệt. Prompt được
lưu nguyên văn để review; không đưa credential, access token, Google project ID
hoặc raw HTTP response vào artifact có thể commit.

CLI tạo short-lived access token bằng một argv `gcloud auth print-access-token`
không qua shell. Token chỉ nằm trong bộ nhớ và không vào log, manifest, intent,
cache hoặc exception. Provider/project/location được đưa vào request runtime;
provenance có provider/model nhưng không lưu cloud project ID.

## 4. Provider và transport

Domain dùng interface hẹp:

```text
VeoTransport.generate(VeoRequest) -> VeoResult
```

`VeoRequest` chỉ chứa các trường ổn định: prompt, model, aspect ratio `9:16`,
resolution `1080p`, duration 4/6/8, sample count 1 và `requested_seed` tùy chọn.
`request_sha256` là SHA-256 của canonical JSON các trường này theo convention của
repo; không hash auth header, URL có project ID, thứ tự JSON do HTTP client tạo
hoặc dữ liệu polling không ổn định.

Live `GoogleVeoTransport` sở hữu endpoint Vertex AI, authorization header, submit,
polling có timeout, response validation, error mapping và base64 decode. Domain và
workflow không phụ thuộc tên operation hay response JSON của Google. HTTP lỗi,
timeout, operation thất bại, nhiều output, output rỗng, base64 sai hoặc MIME khác
`video/mp4` đều fail closed.

CI chỉ dùng fake transport được inject trực tiếp. Fake thực thi cùng interface và
trả fixture MP4 tối thiểu đã theo dõi; test không cần network, gcloud, credential,
quota hoặc model. Không có fallback tự động từ live sang fake.

## 5. Contract asset và provenance

`AssetKind` thêm `AI_CLIP`; `VisualAssetRef.role` và
`AssetRecord.storyboard_role` thêm `ai_clip`. `AssetRecord` thêm trường tùy chọn
`ai_provenance`; trường này bắt buộc đúng khi `kind=ai_clip` và bị cấm với mọi kind
khác.

`AIClipProvenance` là model đóng, bất biến, gồm:

- `schema_version=1.0`;
- `provider=google_vertex_ai`;
- model chính xác;
- prompt nguyên văn;
- `requested_seed` tùy chọn, chỉ diễn tả seed đã yêu cầu, không hứa tái lập;
- thời điểm generation có timezone;
- `request_sha256` của canonical request;
- `output_sha256`, bắt buộc bằng `AssetRecord.sha256`;
- MIME/container `video/mp4`/`mp4`;
- width/height 1080×1920;
- source fps 24;
- `duration_ms` thuộc đúng `{4000, 6000, 8000}` và source frame count tương ứng
  96/144/192.

AI clip có thể `semantic=true` hoặc `semantic=false`. Clip decorative bắt buộc có
`classification_reason` không rỗng và không được mang claim/source marker. Clip
semantic phải được bind vào scene có `claim_id` và `source_marker`; script line
tương ứng phải có cùng binding, và citation resolver hiện có phải truy được claim
đến evidence record thật. `source` trong asset/rights là nguồn tạo hoặc nguồn
quyền; nó không thay thế nguồn bằng chứng y khoa.

Mọi AI clip bắt buộc `rights_required=true` và có đúng một license-ledger entry
khớp path, source, creator, license, revision và SHA. `rights_basis` là chuỗi do
operator cung cấp trong ledger; code chỉ kiểm tra có/khớp, không suy diễn quyền từ
Google, model, điều khoản dịch vụ hoặc việc file được tạo thành công.

## 6. Ownership và toàn vẹn liên artifact

Một scene `visual=ai_clip` của profile M6.5 phải:

- dài đúng 120, 180 hoặc 240 composition frame ở 30 fps;
- có đúng một `VisualAssetRef(role=ai_clip)`;
- tham chiếu đúng một manifest record `kind=ai_clip`,
  `storyboard_role=ai_clip`;
- thỏa quy tắc semantic/decorative ở §5;
- có bytes tồn tại, hash và media probe khớp provenance.

Ngược lại, record có `storyboard_role=ai_clip` phải được tham chiếu đúng một lần
bởi đúng một scene `ai_clip`. Không glob `assets/*.mp4`, không stage clip chưa bind
và không dùng whiteboard fallback.

`validate_asset_manifest()` giữ hành vi decorative legacy. Resolver thêm ngoại lệ
có chủ đích: mọi AI clip được tham chiếu, kể cả decorative, đều phải kiểm tra bytes.
`medical_reviewed_paths()` thêm mọi referenced AI clip vào hash set bên cạnh
storyboard, manifest và license ledger. Vì vậy đổi prompt/provenance, classification,
claim/rationale, rights hoặc MP4 sau duyệt đều làm approval stale.

## 7. Duration và media probing

Veo output giữ nguyên 24 fps. Composition vẫn 30 fps:

| Veo duration | Source frames @24 fps | Scene frames @30 fps |
| ---: | ---: | ---: |
| 4 s | 96 | 120 |
| 6 s | 144 | 180 |
| 8 s | 192 | 240 |

Authoring probe kiểm tra MP4, video stream duy nhất, 1080×1920, 24 fps và đúng
duration/frame count đã yêu cầu. Sai contract bị từ chối; không trim, loop, pad,
đổi playback rate hoặc âm thầm normalize. Container có audio stream vẫn có thể
được lưu để giữ nguyên provider output, nhưng Remotion luôn render clip muted;
narration được duyệt vẫn là nguồn audio duy nhất của composition.

## 8. Transaction authoring và recovery

Generation ghi response vào file tạm ngoài declared output path. Workflow decode,
probe, hash và dựng desired manifest/license-ledger/storyboard trước promotion.
Sau đó ghi `workflow/pending-ai-clip-generation.yaml` chứa canonical old/desired
payload và hash, scene/path, request hash, rights identity và staged-byte hash.

Recovery chỉ chấp nhận các trạng thái đã ghi. Thứ tự promotion là:

1. promote validated MP4 tới path cuối;
2. ghi manifest và license ledger desired;
3. ghi storyboard desired;
4. xóa intent và staging.

Retry cùng request/scene/rights hội tụ mà không gọi lại provider khi staged hoặc
promoted bytes còn xác minh được. Storyboard-first, bytes khác hash, edit không
liên quan, rights/provenance drift, target khác hoặc state đã qua medical review
đều fail closed. Gate và production chạy recovery trước validation; pending intent
không recover được thì revision không thể được duyệt hoặc render.

Nếu generation thất bại trước khi có validated bytes, không tạo intent, không đổi
artifact/state và chỉ dọn file tạm do lần gọi hiện tại sở hữu. Không để MP4 chưa
khai báo ở path trông như production-ready.

## 9. Production và Remotion

Sau khi recovery và medical approval hiện hành được xác nhận, production dùng
resolver chung để đưa clip path/hash vào `asset_hashes` và production input hash.
`_copy_v2_assets()` chỉ copy exact approved bytes và xác minh hash sau copy. Bỏ
lỗi M6.5 “unsupported until M6.6” chỉ sau khi contract, gate, staging và renderer
đều hoạt động.

Zod yêu cầu role/ownership của scene AI giống Python. `HealthVideo` dispatch tới
`AiClipScene`, dùng media component của Remotion với `staticFile(asset.path)`,
`muted`, không loop và không playback-rate override. Clip asset không đi qua lớp
`VisualAsset` dùng cho ảnh, nên được render đúng một lần. Caption và source marker
giữ safe area hiện có.

Zero-AI M6.5 phải giữ render-input và cache behavior hiện tại. Legacy/v1 không bị
buộc có AI provenance hoặc duration 4/6/8 giây.

## 10. Package và disclosure

Khi approved storyboard có ít nhất một AI clip, package thêm
`ai-disclosure.json` vào payload và hash nó trong `manifest.json`. File được sinh
từ snapshot đã được medical/video approval bao phủ, gồm schema version,
`contains_ai=true`, danh sách scene/path/provider/model/classification và hướng
dẫn operator bật nhãn AI-generated content khi nền tảng yêu cầu. Nó không chứa
prompt đầy đủ, credential hoặc cloud project ID.

Không có AI clip thì file không tồn tại và package giữ contract cũ. Guidance chỉ
hỗ trợ bước đăng thủ công, không gọi TikTok, không tự bật nhãn và không tuyên bố
đã đáp ứng mọi yêu cầu của nền tảng.

## 11. Refusal cases và tiêu chí chấp nhận

- Thiếu opt-in dừng trước token/network.
- Provider hoặc media response sai contract không tạo asset đã khai báo.
- AI provenance thiếu/thừa/sai kind, output hash khác manifest hoặc rights thiếu
  đều bị từ chối.
- Semantic clip thiếu claim/marker/citation và decorative clip thiếu rationale
  hoặc mang claim đều bị từ chối trước medical approval.
- Clip thiếu, sửa bytes hoặc sửa metadata/rights/storyboard làm approval stale.
- Scene duration khác 120/180/240 hoặc media khác 4/6/8 giây bị từ chối.
- `produce` không bao giờ gọi provider; preflight lỗi tạo zero TTS/render calls và
  không đổi state.
- Remotion render declared clip đúng một lần, muted, đúng scene duration.
- Package có disclosure đúng khi có AI và không có khi zero-AI; vẫn manual-only.
- Legacy v1/v2, M6.4 exact duration, M6.5 budget/QA/cache, hai gate và manual
  publishing giữ nguyên.
- Full Python, Ruff, schema export/diff, video tests/typecheck và
  `git diff --check` phải qua trước khi đánh dấu M6.6 complete.
