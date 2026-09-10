# Thiết kế workflow khép kín A–Z cho Protect Your Health

**Ngày:** 09-09-2026

**Trạng thái:** Đã duyệt thiết kế trong trao đổi; chờ duyệt bản đặc tả trước khi lập implementation plan

**Phạm vi:** Một video tiếng Việt 9:16, 45–90 giây, faceless, evidence-based, chạy được trên nhiều máy

**Quan hệ tài liệu:** Thay thế §5, §7–§11, §14 và §15 của bản thiết kế
07-09-2026. Khi hai bản lặp lại con số hoặc quyết định, bản 09-09-2026 chi phối.

## 1. Bối cảnh

MVP hiện tại đã chứng minh vertical slice từ artifact y khoa chuẩn bị sẵn đến
render, hai cổng duyệt và gói xuất bản. Nó chưa tự tìm chủ đề, thu thập y văn, viết
kịch bản, tạo giọng đọc thật hoặc dựng asset nâng cao. Bản thiết kế này định nghĩa
đường nâng cấp MVP thành workflow vận hành từ ý tưởng đến gói đăng TikTok.

Hệ thống hỗ trợ bác sĩ, không tự phát ngôn thay bác sĩ. AI giúp tìm, sắp xếp, phản
biện và diễn đạt. Bác sĩ sở hữu lập trường, duyệt bằng chứng và kịch bản trước sản
xuất, rồi duyệt video trước đăng. Việc đăng vẫn do con người thực hiện.

## 2. Mục tiêu và giới hạn

### Mục tiêu

- Sản xuất khoảng năm video mỗi tuần; video thường cần 25–35 phút thao tác của bác sĩ.
- Nhận cả chủ đề nhập tay và chủ đề phát hiện từ xu hướng.
- Truy vết từ câu tìm kiếm đến claim, cảnh, lời thoại và gói đăng.
- Giữ cách nghĩ và cách nói thật của bác sĩ; không bịa trải nghiệm, cảm xúc, quan điểm.
- Tận dụng Codex, Claude Code, Gemini/NotebookLM và Veo qua subscription hiện có.
- Local-first, cache theo stage, chạy lại và chuyển máy không cần lịch sử chat.

### Ngoài phạm vi

- Không tự động đăng hoặc tương tác thay bác sĩ trên TikTok.
- Không chẩn đoán hay tư vấn cá nhân hóa cho người xem.
- Không dùng LLM làm nguồn y khoa hoặc suy ra kết quả ngoài nguồn đã kiểm tra.
- Không đặt CogVideo hay mô hình video nặng vào critical path của RTX 3060 12 GB.
- Không đưa cookie, secret, toàn văn có bản quyền, audio, cache hoặc render vào Git.
- Chưa sản xuất tiếng Anh trong milestone này.

### Tiêu chí thành công

1. Một lệnh bắt đầu hoặc tiếp tục một video và luôn chỉ ra bước kế tiếp.
2. Mọi claim quan trọng có nguồn đã xác minh, certainty, giới hạn và applicability;
   opinion được gắn nhãn riêng.
3. Production bị chặn nếu medical approval thiếu/stale; package bị chặn nếu video
   approval thiếu/stale.
4. Sửa một artifact chỉ chạy lại các stage phụ thuộc.
5. Video thường không cần Claude; chủ đề rủi ro cao dừng ở handoff ngắn có cấu trúc.
6. TTS local, render và package không tiêu thụ token LLM.
7. Máy thứ hai tiếp tục từ artifact hợp lệ và tái tạo phần dẫn xuất còn thiếu.

## 3. Các quyết định đã khóa

| Vấn đề | Quyết định |
| --- | --- |
| Điểm vào | Có cả discovery và chủ đề nhập tay |
| Điều phối | Codex/Claude Code gọi CLI xác định; không phụ thuộc API LLM |
| Đơn vị chạy | Một video mỗi project, độc lập và resume được |
| Kiến trúc | Pipeline artifact có schema, hash, manifest và state machine |
| TTS | VieNeu local mặc định sau benchmark; ElevenLabs fallback tùy chọn |
| Scopus | Không tự động hóa UI; chỉ dùng sau khi quyền subscription được xác nhận |
| Review | HTML tĩnh để đọc/nghe/xem; quyết định ghi qua CLI có hash |
| UX | Slash command cho tác nhân, deterministic CLI ở lớp dưới |
| Hình ảnh | Whiteboard chính, chart/ảnh y văn tạo nhịp, Veo khoảng tối đa 10% |
| Xuất bản | Package tự động, đăng thủ công |

## 4. Kiến trúc

```text
Codex/Claude command
        │
        v
healthvideo workflow ──> state graph ──> stage manifests ──> immutable revision
        │                     │
        ├─ trends/browser     ├─ medical approval gate
        ├─ evidence           └─ video approval gate
        ├─ editorial
        ├─ TTS/visuals
        ├─ Remotion/FFmpeg
        └─ QA/package ──> bác sĩ đăng thủ công
```

Python sở hữu state, schema, provenance, cache, provider adapter và workflow.
TypeScript/Remotion sở hữu timeline 9:16. FFmpeg chuẩn hóa media. HTML review là
artifact tĩnh, mở không cần server. YAML/JSON trong project là nguồn sự thật;
SQLite cục bộ chỉ là index/cache tái tạo được.

Slash command không chứa business logic. `/healthvideo resume huyet-ap` dịch thành
`healthvideo workflow resume <project>` rồi đọc kết quả có cấu trúc.

## 5. Workflow A–Z

| Bước | Stage | Hành động | Artifact bắt buộc | Điều kiện đi tiếp |
| --- | --- | --- | --- | --- |
| A | discover/input | Quét xu hướng hoặc nhận chủ đề | `topic/card.yaml` | Có câu hỏi công chúng rõ |
| B | triage | Chấm lợi ích, độ nóng, evidence readiness, harm risk | `topic/score.yaml` | Bác sĩ chọn/xếp hàng |
| C | author brief | Hỏi tối đa ba câu về động cơ, lập trường, hành động | `author/brief.yaml` | Không suy đoán lập trường |
| D | question | Chuyển thành câu hỏi có cấu trúc/PICO khi phù hợp | `evidence/question.yaml` | Có search concepts |
| E | search | Tìm guideline, review, nghiên cứu gốc | `search-log.yaml`, `candidates.jsonl` | Query có provenance |
| F | verify | Khử trùng lặp, kiểm DOI/PMID, dữ liệu, retraction | `included-sources.yaml`, `excluded-sources.yaml` | Source dùng được đã xác minh |
| G | synthesize | Tạo claim ledger, uncertainty, applicability | `evidence/ledger.yaml` | Claim đủ hoặc reject topic |
| H | draft | Viết lời thoại từ brief và ledger | `script/script.yaml` | Script QA không lỗi chặn |
| I | storyboard | Gắn cảnh/marker/nhịp; dựng chart, crop và asset semantic | `storyboard/storyboard.yaml`, `assets/asset-manifest.yaml` | Claim và byte semantic truy vết được |
| J | preflight | Kiểm schema, claim–citation, semantic asset, ngôn ngữ, thời lượng | `reviews/preflight.json` | Không lỗi Critical/Important |
| K | medical review | HTML để bác sĩ duyệt evidence+script+storyboard | `reviews/medical-*.yaml` | Approval hash hiện hành |
| L | assets | TTS cuối, caption timing, asset trang trí và Veo tùy chọn; chép nguyên byte semantic đã duyệt | `audio/`, `assets/`, manifests | Asset QA và semantic hash đạt |
| M | render | Kết hợp bằng Remotion và FFmpeg | `renders/<hash>/video.mp4` | Publish run nguyên tử |
| N | video QA | Kiểm codec, audio, subtitle, marker, license | `reviews/video-qa.json` | Không lỗi chặn |
| O | video review | HTML để bác sĩ xem và duyệt | `reviews/video-*.yaml` | Approval hash hiện hành |
| P | package | Video, caption, nguồn, thumbnail, manifest | `publish/` | Package tự xác minh |
| Q | publish | Bác sĩ đăng và ghi URL/giờ | `publish/receipt.yaml` | Không chặn video kế tiếp |
| R | learn | Ghi diff lời/nhịp/phát âm đã duyệt | `voice-learning/*.yaml` | Chỉ học revision đã duyệt |

Lệnh chính:

```text
healthvideo workflow start --topic "..."
healthvideo workflow discover
healthvideo workflow resume <project>
healthvideo workflow status <project>
healthvideo workflow explain <project>
healthvideo workflow retry <project> --stage <name>
healthvideo review open <project> --gate medical|video
healthvideo review approve <project> --gate medical|video --reviewer "..."
healthvideo revision create <project> --reason "..."
healthvideo package verify <project>
healthvideo publish record <project> --url <url> --posted-at <rfc3339>
```

`publish record` chỉ chạy ở `packaged`, kiểm URL và thời điểm có múi giờ, ghi nguyên
tử `publish/receipt.yaml`, rồi chuyển `packaged -> published_manual`. Nó không gọi
API TikTok và không tự đăng video.

## 6. State machine

```text
idea -> topic_selected -> author_brief_ready -> research_in_progress
     -> evidence_ready -> draft_ready -> awaiting_medical_review
     -> medically_approved -> production_in_progress -> awaiting_video_review
     -> video_approved -> packaged -> published_manual
```

Side states:

```text
awaiting_browser_login     awaiting_second_model_review
needs_medical_revision    needs_production_revision
blocked                   topic_rejected
```

Transition v2 là graph có precondition, không dùng `ORDER` tuyến tính. Đường chính
cho phép đúng các cạnh đã vẽ ở trên, cộng cạnh phục hồi
`production_in_progress -> medically_approved` khi run chưa publish và staging đã
được xác minh là không dùng được. Precondition của mỗi cạnh gồm state nguồn, revision
đang active, stage input hash hiện hành và artifact bắt buộc đã validate. Các cạnh
vào/ra side state là:

| Side state | Cạnh vào hợp lệ | Cạnh ra hợp lệ |
| --- | --- | --- |
| `awaiting_browser_login` | `idea`, `research_in_progress` | `resume_state` đã ghi (`idea` hoặc `research_in_progress`) |
| `awaiting_second_model_review` | `evidence_ready`, `draft_ready` | `resume_state`; hoặc `needs_medical_revision` khi reviewer yêu cầu sửa |
| `needs_medical_revision` | `awaiting_medical_review` khi reject; mọi state từ `medically_approved` đến `packaged` khi semantic input stale; `awaiting_second_model_review` | `research_in_progress` nếu đổi evidence; `draft_ready` nếu đổi script/storyboard; sau sửa phải đi lại `awaiting_medical_review` |
| `needs_production_revision` | `production_in_progress` khi asset/QA lỗi; `awaiting_video_review` khi reject; `video_approved` hoặc `packaged` khi video input stale | `production_in_progress` nếu chỉ sửa production; `draft_ready` nếu phát hiện lỗi semantic và sau đó phải qua medical gate |
| `blocked` | mọi state chưa kết thúc khi conflict/invariant không tự phục hồi | đúng `resume_state` sau lệnh resolve xác minh nguyên nhân đã hết |
| `topic_rejected` | `research_in_progress`, `evidence_ready` | `topic_selected` qua revision mới nếu bác sĩ mở lại chủ đề |

`resume_state`, `reason_code` và `entered_at` là trường bắt buộc của side-state
record, trừ `topic_rejected` là trạng thái kết thúc có lý do riêng. Graph validator
từ chối mọi cạnh không nằm trong bảng.

Artifact được ghi vào staging, validate và promote nguyên tử trước khi state ổn định
đổi. Dry-run vẫn phải qua gate phù hợp.

## 7. Revision, hash và invalidation

Mỗi project có revision bất biến `revisions/001`, `revisions/002`, ...;
`project.yaml.active_revision` chọn revision hiện hành. Không dùng symlink trên
Windows. Sửa nội dung đã duyệt tạo revision mới, không ghi đè lịch sử.

Stage manifest chứa `stage`, `status`, `input_hash`, `output_hash`, `tool_version`,
`agent`, `model`, timestamps và ước lượng token. Không có “state đúng” nếu hash sai.

`assets/asset-manifest.yaml` phân loại từng asset bằng `semantic: true|false`.
Editorial/storyboard agent đặt cờ lần đầu ở bước I. Policy xác định bắt buộc
`semantic: true` cho `evidence_highlight`, chart mang số liệu/claim, medical diagram,
text/marker y khoa và mọi asset mà thay đổi có thể đổi cách hiểu. Chỉ background,
texture, flourish và transition thuần trang trí mới được `false`. Preflight ở bước J
kiểm policy; bác sĩ nhìn và xác nhận phân loại trong medical packet ở bước K. Bác sĩ
có thể nâng `false -> true`; hạ `true -> false` cần reason và phải qua lại preflight.

Mọi asset `semantic: true` phải có file hoàn chỉnh và SHA-256 trước bước K. Bước L
chỉ chép đúng byte đã duyệt vào render run; nếu thiếu hoặc hash lệch, production dừng
và medical approval stale. Asset `semantic: false` có thể được tạo sau gate.

Medical gate hash canonical ledger, script, storyboard, asset manifest và byte của
mọi asset `semantic: true`. Với project v1 chưa có manifest, mọi asset
`evidence_highlight` hiện được code tìm qua `referenced_evidence_assets()` mặc định
là semantic và tiếp tục nằm trong hash.

Quy tắc invalidation:

- Đổi claim/source: làm lại ledger, script, storyboard, medical review và production.
- Đổi lập trường/lời thoại: làm lại script, storyboard, medical review, TTS, render.
- Đổi nội dung màn hình, marker hoặc crop y văn: medical approval stale.
- Đổi asset có `semantic: true`: medical approval stale. Đổi asset `semantic: false`
  chỉ làm render và video approval stale.
- Chỉ đổi âm lượng/timing animation: render và video review lại.
- Chỉ các JSON Pointer sau trong publish metadata được đổi mà không làm medical gate
  stale: `/posting/platform`, `/posting/account_handle`, `/posting/scheduled_at`,
  `/posting/visibility`, `/posting/allow_comments`, `/posting/allow_duet`,
  `/posting/allow_stitch`, `/tracking/campaign_id`. Ngoài allowlist này, thay đổi làm
  medical approval stale. `caption.txt`, hashtag, disclaimer, source list,
  `thumbnail_text` và pinned comment là semantic, phải sinh xác định từ artifact đã
  duyệt; sửa tay cũng làm medical approval stale.

Final manifest ràng buộc revision, ledger, script, storyboard, audio, render và hai
approval.

## 8. Discovery và triage

`workflow discover` tạo topic inbox từ TikTok Creative Center, Google Trends,
YouTube, RSS/guideline, medical news và saved search. Browser collector dùng profile
riêng theo máy, có giám sát, rate limit và snapshot. Nó không vượt CAPTCHA, đăng
nhập hoặc điều khoản nền tảng. UI đổi thì collector dừng, không bịa dữ liệu.

Topic card chứa câu đang được hỏi, khán giả, tín hiệu nguồn, thời điểm, URL, tính
mới, preventive value, evidence readiness, clarity, harm risk, production cost và
expiry. Điểm chỉ xếp hạng; bác sĩ chọn. Chủ đề nhập tay bỏ discovery nhưng vẫn qua
triage. Chủ đề thiếu bằng chứng trở thành video về sự bất định hoặc `topic_rejected`.

## 9. Evidence pipeline

Thứ tự ưu tiên:

1. Guideline hiện hành của cơ quan hoặc hội chuyên môn phù hợp.
2. Systematic review/meta-analysis có phương pháp phù hợp.
3. Nghiên cứu gốc then chốt hoặc mới công bố.
4. Nguồn cơ chế/nền chỉ để giải thích, không thay evidence về kết cục.

PubMed E-utilities, Europe PMC REST và Crossref REST dùng cho search/metadata công
khai. Client ghi tool/email nhận diện, cache, rate limit, retry/backoff và checksum.
Scopus không nằm trong collector tự động; quyết định riêng nằm ở §17.

```text
evidence/
  question.yaml
  search-log.yaml
  candidates.jsonl
  included-sources.yaml
  excluded-sources.yaml
  ledger.yaml
  source-cache/        # local/ignored; chỉ nội dung được phép
```

Source chỉ được dùng khi metadata và identifier khớp. Số liệu quan trọng phải chỉ
ra section/table/figure/page hoặc đoạn abstract được phép. Hệ thống kiểm retraction,
expression of concern, thiết kế, quần thể, cỡ mẫu, effect, CI, thời gian theo dõi và
conflict of interest. Nó không biến abstract thành claim cần full text.

Claim tách `evidence`, `interpretation`, `professional_opinion`; ghi bằng chứng ủng
hộ/mâu thuẫn, certainty và applicability cho công chúng Việt Nam. Nguồn không đủ thì
pipeline không lấp chỗ trống bằng kiến thức model.

## 10. Giọng tác giả và kịch bản

Hệ thống hỏi tối đa ba câu: vì sao bác sĩ muốn nói; bác sĩ đồng ý/phản đối điều gì;
người xem nên hiểu/làm gì. Câu trả lời là text hoặc ghi âm thô. Hệ thống trích lập
trường, lý do, cảm xúc, mối lo của khán giả, câu muốn giữ và claim cần kiểm; không tự
gán trải nghiệm nghề nghiệp hay cảm xúc.

```text
vấn đề công chúng đang nghe -> câu chuyển tự nhiên -> quan điểm rõ
-> 2–3 căn cứ mạnh nhất -> ý nghĩa -> giới hạn/ngoại lệ -> hành động an toàn
```

Khi nhắc nghiên cứu, lời thoại theo nhịp: dẫn vào; ai/ở đâu nghiên cứu trên nhóm nào;
kết quả; ý nghĩa và giới hạn. Tác giả, nơi, cỡ mẫu và số liệu chỉ xuất hiện nếu đã có
trong ledger và giúp hiểu sức nặng bằng chứng.

Mỗi beat có intent, pace, pause, emphasis và emotional color. QA bắt câu dài, thuật
ngữ chưa giải thích, chuyển ý thiếu lý do, hook phóng đại, sáo ngữ AI, kết luận tuyệt
đối và đoạn đọc nguồn quá dày. Chỉ diff của revision đã duyệt mới được dùng để cập
nhật `profiles/author-voice.vi.yaml`.

## 11. Phân vai AI và token

**Codex** là operator mặc định: đọc state, gọi CLI, tạo packet, ledger bản đầu,
script/storyboard, chạy QA, render và package. Mỗi stage chỉ nhận context cần thiết.

**Claude Code** phản biện có điều kiện cho vaccine, thuốc, thai kỳ, trẻ em, ung thư,
bằng chứng mâu thuẫn, conflict of interest hoặc nguy cơ gây hại. Pipeline ghi
`handoffs/claude-review.xml`, chuyển `awaiting_second_model_review` và đưa đúng
prompt. Claude trả `review-response.yaml` gồm lỗi, mức độ và patch, không viết lại
toàn bộ hồ sơ.

**Gemini/NotebookLM** đối chiếu tập tài liệu đã chọn, thử cách giải thích và Video
Overview tham khảo. Kết quả không tự vào ledger. Subscription UI không được giả định
là API tự động.

**Veo** chỉ tạo minh họa/chuyển cảnh ngắn. Không dùng làm bằng chứng, giải phẫu chính
xác hoặc hướng dẫn hành vi rủi ro. Hết quota thì dùng SVG/stock/chart, không chặn.

| Tác vụ | Token mục tiêu |
| --- | ---: |
| Chọn topic | 1.000–2.000 |
| Evidence packet | 6.000–10.000 |
| Script + storyboard | 3.000–5.000 |
| Patch | dưới 2.000 |
| Claude review khi cần | 4.000–7.000 |
| TTS/render/package | 0 |

Giảm token bằng packet theo stage, metadata/trích đoạn thay toàn văn, cache canonical,
prompt ổn định, delta patch, chỉ 2–3 nguồn mạnh trong thoại, không gửi binary/log dài
và dùng rule giọng đã duyệt thay lịch sử chat.

## 12. TTS và âm thanh

```text
synthesize(lines, voice_profile, language, delivery) -> audio + timings + manifest
```

Benchmark mù cùng 10–15 câu khó giữa VieNeu local và ElevenLabs: tên thuốc, số, viết
tắt, tiếng Anh chen tiếng Việt, cảm xúc và câu dài. Chấm phát âm, tự nhiên, kiểm soát
nhịp, ổn định, thời gian, chi phí và quyền sử dụng.

VieNeu local là mặc định sau khi model/version/license cụ thể vượt benchmark trên
RTX 3060. Không khóa tên model vì upstream thay đổi nhanh. ElevenLabs là fallback
khi bác sĩ cấu hình key; secret ở ngoài Git. Voice clone chỉ bật sau đồng ý, hồ sơ
quyền và đánh giá lạm dụng; ban đầu dùng giọng tổng hợp chung.

Từ điển phát âm có version. ASR back-check so transcript với text; bác sĩ vẫn nghe
duyệt tên, thuốc, số và viết tắt. Cache theo câu; FFmpeg chuẩn hóa loudness, sample
rate và khoảng lặng.

## 13. Visual và render

- 65–75% whiteboard/SVG 2D.
- 15–25% chart, infographic hoặc crop y văn.
- Không quá 10% clip AI/Veo nếu bác sĩ không chủ động đổi.

Thứ tự asset: SVG template; icon/stock có license; chart từ dữ liệu đã xác minh;
crop bài báo hợp pháp; Veo. Mọi asset ghi source, license, sha256, người tạo, revision.

Chart nêu mẫu số, đơn vị, trục và CI; animation không phóng đại tỷ lệ. Crop y văn
lưu tọa độ/chuỗi đối chiếu, bôi vàng đúng câu hoặc số và đồng bộ marker `[n]`. Không
đưa full text có bản quyền hay thông tin đăng nhập vào package/Git.

Remotion nhận `render-input.json` bất biến. FFmpeg chuẩn hóa H.264/AAC, 1080×1920,
30 fps và loudness. Production dùng staging + atomic promotion; crash không đổi
state. OpenMontage/VoiceStudio chỉ là tham khảo hoặc adapter thử nghiệm, không fork
vào core và không cài binary chưa xác minh.

## 14. Hai gói review

Medical HTML hiển thị từng claim theo chuỗi: câu công chúng; mệnh đề kỹ thuật; nguồn,
thiết kế và quần thể; số liệu/vị trí; giới hạn/certainty/applicability; quan điểm bác
sĩ; cảnh/marker. Packet có bản nghe thử, script, storyboard và diff revision.

Video HTML nhúng MP4, timeline, transcript, nguồn, asset license, QA và diff. HTML
không tự ký. CLI yêu cầu reviewer/quyết định/xác nhận; medical gate hash ledger,
script, storyboard, `asset-manifest.yaml` và byte của mọi asset `semantic: true`;
video gate hash MP4 và render input. Reject tạo revision hoặc side state phù hợp,
giữ review cũ làm audit trail. Đây là quyết định mở rộng có tương thích: code v1 đã
hash ba YAML và mọi asset `evidence_highlight`; M1 định nghĩa manifest/invalidation,
M2 tích hợp chúng vào review packet và gate.

## 15. Repo và contract

Master hiện có cây xương sống sau; module mới phải mở rộng, không thay thế nó:

```text
src/healthvideo/
  cli.py
  assets.py
  process.py
  domain/          # ProjectState và Pydantic domain models
  storage/         # atomic writes, canonical_json_hash, file hashes
  workflows/       # create, doctor, review, produce, package
  render/          # render input, Remotion bridge, run identity
  tts/             # provider protocol và SilentTTS
  qa/              # script QA hiện có
```

Module M1–M7 nằm cạnh hoặc trong module cũ như sau:

```text
src/healthvideo/
  domain/          # thêm graph/state v2, revision, topic, asset manifest
  storage/         # thêm lease, stage manifest; giữ API v1
  workflows/       # thêm graph.py, resume.py, migrate.py, review_packets.py
  render/ tts/ qa/ # mở rộng adapter và QA, không tạo namespace trùng
  trends/          # module mới
  browser/         # module mới cho nguồn được phép, không gồm Scopus UI automation
  evidence/        # module mới; domain model vẫn ở domain/
  editorial/       # module mới
  agents/          # module mới cho packet/handoff
  visuals/         # module mới; assets.py là compatibility facade trong migration
skills/preventive-health-video/
  SKILL.md discover.md research.md script.md production.md review.md
projects/YYYY/MM/<slug>/
  project.yaml workflow.yaml
  revisions/001/
    topic/ author/ evidence/ script/ storyboard/
    handoffs/ reviews/ audio/ assets/ renders/ publish/
```

Logic review và package tiếp tục ở `workflows/review.py` và
`workflows/package.py`; không tạo package `review/` hoặc `package/` cạnh chúng.

Artifact có JSON Schema/Pydantic model và `schema_version`. YAML dành cho review;
JSONL cho candidate lớn; JSON cho machine contract. Đường dẫn nội bộ dùng
`pathlib.Path`; path trong artifact dùng POSIX relative path.

## 16. Migration từ MVP

Schema v2 không phá project phẳng hiện tại. State mapping là:

| State v1 | State v2 sau migrate |
| --- | --- |
| `idea` | `idea` |
| `evidence_in_progress` | `research_in_progress` |
| `evidence_ready` | `evidence_ready` |
| `awaiting_medical_review` | `awaiting_medical_review` |
| `script_approved` | `medically_approved` |
| `producing` | `production_in_progress` |
| `rendered` | `awaiting_video_review` |
| `awaiting_video_review` | `awaiting_video_review` |
| `approved_to_publish` | `video_approved` |
| `published` | `published_manual` |

V2 bỏ `rendered`: đây chỉ là state trung gian mà `produce_project()` hiện đi qua
trong bộ nhớ trước `awaiting_video_review`, không phải điểm duyệt hữu ích. Bản v2
đổi production thành `medically_approved -> production_in_progress ->
awaiting_video_review`. Lệnh ghi `production_in_progress` cùng stage-run manifest
trước công việc; sau atomic promotion nó đi thẳng tới `awaiting_video_review`.
Nếu crash, resume kiểm staging: run hợp lệ thì promote và đi tiếp; run không hợp lệ
thì dọn staging và chuyển `production_in_progress -> medically_approved` để retry;
asset/QA cần sửa thì chuyển `needs_production_revision`.

Transition v2 dùng graph và precondition ở §6. `transition()` tuyến tính cùng `ORDER`
được giữ cho reader/workflow v1 trong giai đoạn tương thích; project v2 gọi graph
transition mới. Không thêm side state vào `ORDER`.

Quy trình migrate:

1. Reader nhận v1 phẳng và v2 revisioned; writer mới chỉ ghi v2.
2. `healthvideo project migrate <path> --dry-run` liệt kê file, hash và đích.
3. Migrate thật copy v1 vào staging `revisions/001`, validate, rồi cập nhật
   `project.yaml` nguyên tử; lưu report và không xóa v1.
4. Golden v1/v2 chạy song song đến khi gate, render, package tương đương về nghĩa.

Approval v1 chỉ chuyển khi tập artifact có hash tương đương. Nếu không chứng minh
được, project quay về gate phù hợp thay vì tự ký lại.

## 17. Quyết định Scopus

Đã rà soát [Elsevier website terms](https://www.elsevier.com/legal/elsevier-website-terms-and-conditions)
ngày **10-09-2026**. Điều khoản chung cấm systematic retrieval, automated
downloading/scraping và hạn chế đưa Content vào công cụ AI nếu subscription hoặc
văn bản ủy quyền không cho phép. Hậu quả có thể là vi phạm tài khoản, nên đây không
phải rủi ro vận hành được chấp nhận.

Phạm vi mặc định:

- Không scripted click, browser automation, scraping, bulk download hoặc truyền
  nội dung Scopus cho AI.
- Bác sĩ có thể tự tìm và đọc Scopus ngoài pipeline theo quyền tài khoản; repo không
  nhập export/nội dung Scopus cho đến khi tổ chức hoặc Elsevier xác nhận quyền bằng
  văn bản.
- Nếu có xác nhận, chỉ dùng chức năng export chính thức và trường metadata được phép;
  adapter deterministic import file, lưu căn cứ quyền và không lưu cookie/full text.
- Nếu không có xác nhận, PubMed, Europe PMC, Crossref, guideline chính thức và trang
  publisher là đường production. Scopus chỉ là kiểm tra thủ công ngoài hệ thống và
  việc thiếu Scopus không chặn workflow.

Quyết định này thay mọi mô tả cũ về profile trình duyệt Scopus có giám sát.

## 18. Multi-machine, tiến trình, secret và dữ liệu

Git đồng bộ code, schema, evidence metadata, script, storyboard và review. Git LFS
hoặc NAS/Syncthing có thể đồng bộ asset hợp pháp; render, model, cache và secret mặc
định local. Doctor kiểm toolchain/profile; resume tái tạo index từ manifest.

Lease file có host ID, process ID, process-start fingerprint, timestamp, TTL và
revision; nó ngăn cả hai máy lẫn hai tiến trình trên cùng máy ghi một revision.
Lock acquisition dùng create-exclusive/atomic primitive, không phải “kiểm rồi ghi”.
Lease hết hạn không tự xóa; recovery xác nhận PID/start fingerprint nếu cùng host và
kiểm staging/manifest trước khi nhận quyền. Merge conflict trong artifact chuyển
`blocked`, không tự chọn bản.

Key nằm trong environment/secret store. Browser profile ở ngoài repo và mỗi máy tự
đăng nhập. Log redact token, cookie, query nhạy cảm và path chứa thông tin tài khoản.

## 19. Lỗi và phục hồi

Mỗi lỗi hiển thị: **What failed; Why; What was preserved; Exact next command**.

- Mất mạng/rate limit: giữ response hợp lệ, backoff và resume cursor.
- Nguồn browser được phép hết session/CAPTCHA: `awaiting_browser_login`; không vượt xác thực.
- DOI/PMID không khớp: cách ly candidate, không cho vào ledger.
- Handoff thiếu: giữ packet, chờ response đúng schema.
- VieNeu lỗi: retry theo câu; chỉ đề nghị ElevenLabs nếu đã cấu hình.
- Veo hết quota: dùng asset xác định thay thế.
- Render crash: dọn staging an toàn, giữ state trước production.
- QA fail: tạo report/side state, không mở gate.
- Approval stale: nêu artifact/hash đổi và gate cần duyệt lại.
- Máy khác thiếu cache: tái tạo stage dẫn xuất; không làm lại research đã đủ.

## 20. Kiểm thử và acceptance

- Unit: graph, hash, invalidation, scoring, dedupe, citation, redaction.
- Contract: schema, handoff, provider response và unknown fields.
- Browser: recorded fixture, selector failure, login state; CI không dùng web thật.
- Evidence: fixture tổng hợp, identifier giả được gắn rõ.
- Agent eval: nguồn bịa, overclaim, opinion giả, văn máy và delta sai.
- TTS: cache câu, pronunciation, ASR mismatch, fallback.
- Visual: chart scale, safe zone, marker, highlight, license inventory.
- Recovery: network, crash, damaged cache, stale approval, lease.
- E2E: golden v1/v2 offline; Windows smoke có audio test và render dọc.

Acceptance: một project nhập tay và một project discovery đi tới package; project
rủi ro cao dừng đúng ở Claude handoff; đổi claim làm stale medical approval; đổi
volume chỉ làm stale video approval; resume máy hai chỉ tái tạo phần thiếu; package
không chứa secret, cookie, full text hoặc asset không rõ license.

## 21. Roadmap M1–M7 và chi phí

Roadmap Giai đoạn 0–5 ở bản 07-09-2026 hết hiệu lực. Roadmap duy nhất cho phần việc
chưa triển khai là M1–M7 dưới đây.

| Milestone | Deliverable | Chi phí ngoài subscription |
| --- | --- | --- |
| M1 | Workflow kernel: graph v2, revision, stage/semantic-asset manifest, invalidation, migrate | 0 |
| M2 | Medical/video HTML, gate dùng semantic manifest, reject/revise UX | 0 |
| M3 | Trend + PubMed/Europe PMC/Crossref; Scopus theo §17 | 0 |
| M4 | Agent packet, risk routing, Codex/Claude/Gemini contract | 0 API |
| M5 | VieNeu benchmark/adapter, pronunciation, ASR, Eleven fallback | 0 local; Eleven tùy chọn |
| M6 | Chart, SVG, paper highlight, Veo adapter, license ledger | trong quota Gemini/Veo |
| M7 | E2E, multi-process/multi-machine, backup, security, hướng dẫn | 0 ngoài lưu trữ tùy chọn |

i5-13500, RTX 3060 12 GB và RAM 32 GB là máy production chính cho local TTS, ASR,
SVG/chart và Remotion. Video diffusion local là thí nghiệm ngoài critical path.
Mỗi giai đoạn giữ MVP cũ chạy được và có commit/review riêng.

## 22. Rủi ro đã chấp nhận

- UI TikTok/Google có thể đổi; collector có giám sát và fixture chỉ giảm chi
  phí bảo trì, không loại bỏ nó.
- Subscription không có automation API ổn định; handoff cần một thao tác mở model
  khác khi risk routing yêu cầu.
- TTS tiếng Việt cần benchmark thực; adapter tránh khóa provider.
- Mục tiêu 25–35 phút không áp cho chủ đề nguy cơ cao hoặc evidence mâu thuẫn.

## 23. Nguồn kỹ thuật và giấy phép kiểm chứng

- [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [Europe PMC REST](https://europepmc.org/RestfulWebService)
- [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [TikTok Creative Center](https://ads.tiktok.com/help/article/creative-center?lang=en)
- [Google Trends](https://trends.google.com/trends/)
- [Remotion](https://github.com/remotion-dev/remotion)
- [VieNeu-TTS source](https://github.com/pnnbao97/VieNeu-TTS) và
  [source LICENSE](https://github.com/pnnbao97/VieNeu-TTS/blob/main/LICENSE)
- [VieNeu-TTS v3 Turbo model package](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo)
- [ElevenLabs TTS](https://elevenlabs.io/docs/overview/capabilities/text-to-speech)
- [NotebookLM Video Overview](https://support.google.com/notebooklm/answer/16246230)
- [Google Veo](https://ai.google.dev/gemini-api/docs/veo)
- [VoiceStudio](https://github.com/debpalash/VoiceStudio)
- [OpenMontage](https://github.com/calesthio/OpenMontage)
- [Elsevier website terms](https://www.elsevier.com/legal/elsevier-website-terms-and-conditions)

Các nguồn kỹ thuật được kiểm tra ngày **09-09-2026**; VieNeu và Elsevier được kiểm
tra lại ngày **10-09-2026**. NCBI/Crossref client phải nhận diện tool, cache,
rate-limit và backoff. TikTok/Google Trends chỉ là tín hiệu quan tâm, không phải
bằng chứng y khoa. Remotion cần kiểm lại
license nếu quy mô tổ chức thay đổi. Repo VieNeu đúng là `pnnbao97/VieNeu-TTS`;
README gọi **VieNeu-TTS v3 Turbo** là bản open-source mới nhất và **v4** là dịch vụ
proprietary. File LICENSE của source repo và model card của
`pnnbao-ump/VieNeu-TTS-v3-Turbo` đều ghi **Apache License 2.0** ngày kiểm tra. M5 vẫn
phải ghim revision, ghi dependency/voice asset cụ thể và kiểm từng giấy phép trước
khi dùng thương mại. Chỉ tin repo OpenMontage của `calesthio`.

## 24. Điều kiện chuyển sang implementation plan

Bác sĩ duyệt bản đặc tả này. Implementation plan sau đó chia theo M1–M7,
ghi file ownership, test RED/GREEN, migration checkpoint, review checkpoint và lệnh
kiểm chứng. Không bắt đầu code workflow v2 trước bước duyệt đó.
