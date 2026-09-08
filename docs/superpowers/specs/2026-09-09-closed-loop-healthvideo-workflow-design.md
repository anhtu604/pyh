# Thiết kế workflow khép kín A–Z cho Protect Your Health

**Ngày:** 09-09-2026

**Trạng thái:** Đã duyệt thiết kế trong trao đổi; chờ duyệt bản đặc tả trước khi lập implementation plan

**Phạm vi:** Một video tiếng Việt 9:16, 45–90 giây, faceless, evidence-based, chạy được trên nhiều máy

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
| Scopus | Profile trình duyệt riêng, đã đăng nhập, thao tác có giám sát |
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
| I | storyboard | Gắn cảnh, marker, chart, asset, nhịp | `storyboard/storyboard.yaml` | Claim màn hình truy vết được |
| J | preflight | Kiểm schema, claim–citation, ngôn ngữ, thời lượng | `reviews/preflight.json` | Không lỗi Critical/Important |
| K | medical review | HTML để bác sĩ duyệt evidence+script+storyboard | `reviews/medical-*.yaml` | Approval hash hiện hành |
| L | assets | TTS, caption, SVG, chart, crop y văn, Veo tùy chọn | `audio/`, `assets/`, manifests | Asset QA đạt |
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
```

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

Mọi transition có precondition, output schema và recovery command. Artifact được
ghi vào staging, validate và promote nguyên tử trước khi state đổi. Dry-run vẫn
phải qua gate phù hợp.

## 7. Revision, hash và invalidation

Mỗi project có revision bất biến `revisions/001`, `revisions/002`, ...;
`project.yaml.active_revision` chọn revision hiện hành. Không dùng symlink trên
Windows. Sửa nội dung đã duyệt tạo revision mới, không ghi đè lịch sử.

Stage manifest chứa `stage`, `status`, `input_hash`, `output_hash`, `tool_version`,
`agent`, `model`, timestamps và ước lượng token. Không có “state đúng” nếu hash sai.

Quy tắc invalidation:

- Đổi claim/source: làm lại ledger, script, storyboard, medical review và production.
- Đổi lập trường/lời thoại: làm lại script, storyboard, medical review, TTS, render.
- Đổi nội dung màn hình, marker hoặc crop y văn: medical approval stale.
- Đổi asset trang trí không đổi nghĩa: giữ medical approval; render và video review lại.
- Chỉ đổi âm lượng/timing animation: render và video review lại.
- Đổi caption đăng trong phạm vi metadata cho phép: package hash đổi; gate giữ nguyên.

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
Scopus mở bằng profile riêng đã đăng nhập để tìm, xem cited-by và kiểm tra phạm vi;
cookie không vào repo. UI automation là đường có giám sát vì có thể thay đổi và chịu
điều khoản tài khoản của bác sĩ.

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
script, storyboard và evidence asset; video gate hash MP4 và render input. Reject
tạo revision hoặc side state phù hợp, giữ review cũ làm audit trail.

## 15. Repo và contract

```text
src/healthvideo/
  workflow/ trends/ browser/ evidence/ editorial/ agents/
  review/ tts/ visuals/ render/ qa/ package/
skills/preventive-health-video/
  SKILL.md discover.md research.md script.md production.md review.md
projects/YYYY/MM/<slug>/
  project.yaml workflow.yaml
  revisions/001/
    topic/ author/ evidence/ script/ storyboard/
    handoffs/ reviews/ audio/ assets/ renders/ publish/
```

Artifact có JSON Schema/Pydantic model và `schema_version`. YAML dành cho review;
JSONL cho candidate lớn; JSON cho machine contract. Đường dẫn nội bộ dùng
`pathlib.Path`; path trong artifact dùng POSIX relative path.

## 16. Migration từ MVP

Schema v2 không phá project phẳng hiện tại:

1. Reader nhận v1 phẳng và v2 revisioned; writer mới chỉ ghi v2.
2. `healthvideo project migrate <path> --dry-run` liệt kê file, hash và đích.
3. Migrate thật copy v1 vào staging `revisions/001`, validate, rồi cập nhật
   `project.yaml` nguyên tử; lưu report và không xóa v1.
4. Golden v1/v2 chạy song song đến khi gate, render, package tương đương về nghĩa.

Approval v1 chỉ chuyển khi tập artifact có hash tương đương. Nếu không chứng minh
được, project quay về gate phù hợp thay vì tự ký lại.

## 17. Multi-machine, secret và dữ liệu

Git đồng bộ code, schema, evidence metadata, script, storyboard và review. Git LFS
hoặc NAS/Syncthing có thể đồng bộ asset hợp pháp; render, model, cache và secret mặc
định local. Doctor kiểm toolchain/profile; resume tái tạo index từ manifest.

Lease file có host, PID, timestamp và TTL ngăn hai máy ghi cùng revision. Lease hết
hạn không tự xóa; recovery kiểm staging/manifest trước khi nhận quyền. Merge conflict
trong artifact chuyển `blocked`, không tự chọn bản.

Key nằm trong environment/secret store. Browser profile ở ngoài repo và mỗi máy tự
đăng nhập. Log redact token, cookie, query nhạy cảm và path chứa thông tin tài khoản.

## 18. Lỗi và phục hồi

Mỗi lỗi hiển thị: **What failed; Why; What was preserved; Exact next command**.

- Mất mạng/rate limit: giữ response hợp lệ, backoff và resume cursor.
- Scopus hết session/CAPTCHA: `awaiting_browser_login`; không vượt xác thực.
- DOI/PMID không khớp: cách ly candidate, không cho vào ledger.
- Handoff thiếu: giữ packet, chờ response đúng schema.
- VieNeu lỗi: retry theo câu; chỉ đề nghị ElevenLabs nếu đã cấu hình.
- Veo hết quota: dùng asset xác định thay thế.
- Render crash: dọn staging an toàn, giữ state trước production.
- QA fail: tạo report/side state, không mở gate.
- Approval stale: nêu artifact/hash đổi và gate cần duyệt lại.
- Máy khác thiếu cache: tái tạo stage dẫn xuất; không làm lại research đã đủ.

## 19. Kiểm thử và acceptance

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

## 20. Roadmap và chi phí

| Giai đoạn | Deliverable | Chi phí ngoài subscription |
| --- | --- | --- |
| 1 | Workflow kernel: state v2, revision, manifest, invalidation, migrate | 0 |
| 2 | Medical/video HTML, reject/revise UX | 0 |
| 3 | Trend + PubMed/Europe PMC/Crossref + Scopus supervised | 0; dùng Scopus hiện có |
| 4 | Agent packet, risk routing, Codex/Claude/Gemini contract | 0 API |
| 5 | VieNeu benchmark/adapter, pronunciation, ASR, Eleven fallback | 0 local; Eleven tùy chọn |
| 6 | Chart, SVG, paper highlight, Veo adapter, license ledger | trong quota Gemini/Veo |
| 7 | E2E, multi-machine, backup, security và hướng dẫn | 0 ngoài lưu trữ tùy chọn |

i5-13500, RTX 3060 12 GB và RAM 32 GB là máy production chính cho local TTS, ASR,
SVG/chart và Remotion. Video diffusion local là thí nghiệm ngoài critical path.
Mỗi giai đoạn giữ MVP cũ chạy được và có commit/review riêng.

## 21. Rủi ro đã chấp nhận

- UI TikTok/Scopus/Google có thể đổi; collector có giám sát và fixture chỉ giảm chi
  phí bảo trì, không loại bỏ nó.
- Subscription không có automation API ổn định; handoff cần một thao tác mở model
  khác khi risk routing yêu cầu.
- TTS tiếng Việt cần benchmark thực; adapter tránh khóa provider.
- Mục tiêu 25–35 phút không áp cho chủ đề nguy cơ cao hoặc evidence mâu thuẫn.

## 22. Nguồn kỹ thuật kiểm chứng ngày 09-09-2026

- [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [Europe PMC REST](https://europepmc.org/RestfulWebService)
- [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [TikTok Creative Center](https://ads.tiktok.com/help/article/creative-center?lang=en)
- [Google Trends](https://trends.google.com/trends/)
- [Remotion](https://github.com/remotion-dev/remotion)
- [VieNeu-TTS](https://github.com/pnnbao97/VieNeu-TTS)
- [ElevenLabs TTS](https://elevenlabs.io/docs/overview/capabilities/text-to-speech)
- [NotebookLM Video Overview](https://support.google.com/notebooklm/answer/16246230)
- [Google Veo](https://ai.google.dev/gemini-api/docs/veo)
- [VoiceStudio](https://github.com/debpalash/VoiceStudio)
- [OpenMontage](https://github.com/calesthio/OpenMontage)

NCBI/Crossref client phải nhận diện tool, cache, rate-limit và backoff. TikTok/Google
Trends chỉ là tín hiệu quan tâm, không phải bằng chứng y khoa. Remotion cần kiểm lại
license nếu quy mô tổ chức thay đổi. VieNeu v3 Turbo là bản open-source mới nhất tại
thời điểm kiểm tra; v4 là proprietary. Chỉ tin repo OpenMontage của `calesthio`.

## 23. Điều kiện chuyển sang implementation plan

Bác sĩ duyệt bản đặc tả này. Implementation plan sau đó chia theo bảy giai đoạn,
ghi file ownership, test RED/GREEN, migration checkpoint, review checkpoint và lệnh
kiểm chứng. Không bắt đầu code workflow v2 trước bước duyệt đó.
