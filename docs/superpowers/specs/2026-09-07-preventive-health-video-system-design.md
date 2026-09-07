# Thiết kế hệ thống sản xuất video y học dự phòng

**Ngày:** 07-09-2026

**Trạng thái:** Chờ bác sĩ duyệt trước khi lập kế hoạch triển khai
**Tên làm việc:** Protect Your Health

## 1. Mục tiêu

Xây một repo có thể cài trên nhiều máy và điều khiển bằng Codex hoặc Claude Code để sản xuất khoảng năm video TikTok tiếng Việt mỗi tuần. Mỗi video dài 45–90 giây, khung dọc 9:16, không lộ mặt, chủ yếu dùng nét vẽ whiteboard/2D. Hệ thống phải giảm thời gian thao tác của bác sĩ xuống khoảng 30 phút mỗi video mà vẫn bảo toàn truy xuất nguồn, mức độ chắc chắn và quan điểm chuyên môn.

Sản phẩm không phải “máy viết nội dung tự động”. Nó là một dây chuyền có kiểm soát: phát hiện chủ đề, lập hồ sơ bằng chứng, viết kịch bản, dựng hình, đọc thoại, render và kiểm tra. Bác sĩ giữ quyền quyết định tại hai cổng bắt buộc:

1. Duyệt bằng chứng và kịch bản trước sản xuất.
2. Duyệt video hoàn chỉnh trước đăng.

## 2. Phạm vi và tiêu chí thành công

### Trong phạm vi

- Phát hiện chủ đề y khoa đang được bàn luận, hiểu sai hoặc mới công bố.
- Tìm, khử trùng lặp, lưu và đánh giá nguồn từ PubMed, Europe PMC, Scopus và guideline chính thống.
- Tách rõ bằng chứng, diễn giải và quan điểm cá nhân của bác sĩ.
- Sinh kịch bản tiếng Việt dễ hiểu, storyboard theo cảnh và danh sách claim–citation.
- Tạo TTS, phụ đề, whiteboard/SVG, biểu đồ động, ảnh nghiên cứu và đoạn AI/Veo ngắn.
- Render video dọc bằng một quy trình tái lập, có cache và tiếp tục từ checkpoint.
- Chạy từ Codex hoặc Claude Code trên Windows; có đường mở rộng cho Linux/macOS.
- Xuất gói đăng gồm video, caption, tài liệu nguồn và checklist duyệt.

### Ngoài phạm vi bản đầu

- Tự động đăng TikTok.
- Chẩn đoán hoặc tư vấn cá nhân hóa cho người xem.
- Thay bác sĩ đánh giá tính áp dụng lâm sàng.
- Tự huấn luyện mô hình video hoặc LLM lớn trên máy RTX 3060.
- Đồng bộ file render và model nặng bằng Git.
- Sản xuất tiếng Anh trước khi quy trình tiếng Việt ổn định.

### Chỉ số chấp nhận

- Một video thông thường cần không quá 30 phút thao tác của bác sĩ sau giai đoạn làm quen.
- 100% luận điểm y khoa quan trọng ánh xạ đến ít nhất một nguồn đã xác minh hoặc được đánh dấu rõ là ý kiến chuyên môn.
- Không có DOI/PMID do mô hình tự bịa; mã định danh phải được kiểm tra bằng dịch vụ nguồn.
- Kịch bản giữ được lập trường, cách nói và nhịp lập luận của bác sĩ; người duyệt không cảm thấy mình đang đọc lời của một “người dẫn AI” chung chung.
- Có thể chạy lại một bước mà không làm lại các bước đầu nếu đầu vào không đổi.
- Cùng một `project.yaml` và cùng phiên bản mã tạo ra kết quả có thể truy vết trên máy khác.

## 3. Nguyên tắc thiết kế

1. **Evidence-first:** lập claim ledger trước khi viết lời thoại.
2. **Human-in-the-loop:** trạng thái dự án chặn sản xuất và xuất bản khi thiếu chữ ký duyệt.
3. **Local-first:** dùng mã xác định, cache và GPU cục bộ cho việc lặp lại; gọi AI khi cần suy luận hoặc sáng tạo.
4. **Skill-first:** `AGENTS.md` và `CLAUDE.md` chỉ định tuyến; hướng dẫn chi tiết nằm trong skill và được tải theo nhu cầu.
5. **Provider-agnostic:** TTS, LLM và video AI dùng adapter; thay nhà cung cấp mà không đổi hồ sơ dự án.
6. **Artifact-over-chat:** mọi kết quả quan trọng nằm trong file có schema, không phụ thuộc lịch sử hội thoại.
7. **Least-context:** mỗi tác vụ chỉ nhận trường và nguồn cần thiết; phản biện trả về delta thay vì viết lại toàn bộ.
8. **Safe publishing:** hệ thống chuẩn bị gói đăng nhưng không tự đăng.
9. **Author-owned voice:** AI giúp bác sĩ nói rõ điều mình nghĩ; AI không tự tạo một nhân vật bác sĩ thay cho tác giả.

## 4. Kiến trúc tổng thể

```text
Nguồn xu hướng ──> Topic inbox ──> Evidence pipeline ──> Claim ledger
                                              │              │
                                              └──────> Cổng duyệt 1
                                                               │
                              Script + storyboard <────────────┘
                                        │
                     ┌──────────────────┼──────────────────┐
                     │                  │                  │
                  TTS/audio       SVG + charts       AI/Veo clips
                     └──────────────────┼──────────────────┘
                                        │
                              Remotion + FFmpeg render
                                        │
                                 QA + Cổng duyệt 2
                                        │
                              Gói đăng, không auto-post
```

Python điều phối nghiên cứu, schema, provider và workflow. TypeScript/Remotion dựng cảnh theo timeline; FFmpeg chuẩn hóa media và mã hóa đầu ra. SQLite hoặc DuckDB lưu chỉ mục cache và provenance cục bộ; YAML/JSON trong thư mục dự án là nguồn sự thật có thể review bằng Git.

## 5. Vòng đời dự án

Trạng thái hợp lệ:

```text
idea
  -> evidence_in_progress
  -> evidence_ready
  -> awaiting_medical_review
  -> script_approved
  -> producing
  -> rendered
  -> awaiting_video_review
  -> approved_to_publish
  -> published
```

Mỗi lệnh kiểm tra trạng thái đầu vào, tạo đầu ra vào file tạm, xác minh schema rồi mới đổi tên nguyên tử. Một manifest lưu hash đầu vào, phiên bản tool, provider, model và thời điểm chạy. Nếu hash không đổi, hệ thống dùng cache. Nếu một bước lỗi, trạng thái không tiến và log ghi cách chạy lại.

Các lệnh dự kiến:

```text
healthvideo topic discover
healthvideo project new <slug>
healthvideo evidence collect <slug>
healthvideo evidence validate <slug>
healthvideo script draft <slug>
healthvideo review medical <slug>
healthvideo produce <slug>
healthvideo render <slug>
healthvideo review video <slug>
healthvideo package <slug>
healthvideo status <slug>
```

## 6. Phân công Codex, ChatGPT, Claude và Gemini

### Codex: tác nhân vận hành chính

Codex đọc trạng thái repo, gọi script, quản lý file, sửa mã, chạy test và điều phối một video từ đầu đến cuối. Codex cũng tạo claim ledger bản đầu, kịch bản mặc định, storyboard, scene Remotion và báo cáo QA. Đây là đường chạy chuẩn cho video rủi ro thấp hoặc vừa.

### ChatGPT: bàn biên tập theo lô

Một phiên ChatGPT mỗi tuần gom chủ đề, xếp ưu tiên và nghiên cứu sâu các câu hỏi khó. Không mở một cuộc trò chuyện riêng cho từng video thông thường. Đầu ra phải được lưu thành topic cards hoặc research brief có cấu trúc để Codex dùng lại.

### Claude: phản biện y khoa và biên tập có điều kiện

Claude không chạy toàn bộ pipeline. Hệ thống gọi Claude khi chủ đề có tranh cãi, bằng chứng mâu thuẫn hoặc nguy cơ cao: vaccine, thuốc, thai kỳ, trẻ em, ung thư, xung đột lợi ích hoặc khuyến nghị có thể gây hại. Claude nhận một gói XML ngắn gồm câu hỏi, claim ledger, trích đoạn nguồn cần thiết, đối tượng và kịch bản. Claude trả về YAML gồm lỗi, mức nghiêm trọng và patch đề xuất; không trả lại toàn bộ hồ sơ.

### Gemini, NotebookLM và Veo

Gemini/NotebookLM hỗ trợ đối chiếu tài liệu đã chọn, tìm cách giải thích dễ hiểu và thử Video Overview. Chúng không thay thế bảng bằng chứng chuẩn. Veo chỉ tạo đoạn chuyển cảnh hoặc minh họa khó dựng, thường dưới 10% thời lượng.

### Ngân sách context theo video

| Tác vụ | Mục tiêu context |
|---|---:|
| Topic card | 1.500–2.500 token |
| Evidence packet | 8.000–15.000 token |
| Claude review khi cần | 6.000–10.000 token |
| Viết kịch bản | 3.000–5.000 token |
| Storyboard | 2.000–4.000 token |
| Sửa một cảnh | dưới 2.000 token |
| Render, validate, cache | 0 token LLM |

Video thường dùng một phiên Codex, không cần Claude hoặc phiên ChatGPT riêng. Video rủi ro cao dùng thêm một lượt Claude và tối đa một lượt patch ngắn. Prompt cố định đặt trước, dữ liệu động đặt sau để tận dụng prompt caching khi nền tảng hỗ trợ.

## 7. Phát hiện và chọn chủ đề

Nguồn đầu vào gồm TikTok Creative Center theo thao tác có giám sát, Google Trends, YouTube, RSS từ tạp chí/guideline, PubMed saved search và topic do bác sĩ nhập. Không phụ thuộc scraping dễ vỡ làm đường chính.

Mỗi topic card chứa:

- câu hỏi công chúng đang hỏi;
- phát biểu gây tranh cãi hoặc hiểu nhầm;
- nhóm khán giả và nguy cơ gây hại;
- tính mới, mức quan tâm và độ phù hợp với y học dự phòng;
- khả năng có bằng chứng đủ mạnh;
- góc nhìn sơ bộ của bác sĩ;
- hạn sử dụng của chủ đề.

Điểm ưu tiên kết hợp `public_interest`, `preventive_value`, `evidence_readiness`, `clarity` và trừ `harm_risk`, `production_cost`. Bác sĩ chọn lịch năm video từ một bảng gợi ý theo tuần.

## 8. Pipeline bằng chứng

### Thứ tự nguồn

1. Guideline hiện hành của tổ chức chuyên môn hoặc cơ quan y tế.
2. Systematic review/meta-analysis có phương pháp phù hợp.
3. Nghiên cứu gốc then chốt hoặc mới công bố.
4. Nguồn nền để giải thích cơ chế; không dùng thay cho bằng chứng kết cục.

PubMed E-utilities và Europe PMC cung cấp metadata mở. Scopus dùng tài khoản của bác sĩ cho tìm kiếm, cited-by và kiểm tra phạm vi. Hệ thống lưu metadata hợp pháp, ghi nguồn truy cập và không đưa toàn văn có bản quyền vào Git.

### Claim ledger

Mỗi claim có:

```yaml
id: C01
text_public: "Câu nói dành cho công chúng"
text_technical: "Mệnh đề kỹ thuật có thể kiểm chứng"
type: evidence | interpretation | professional_opinion
direction: supportive | mixed | contradictory
population: "P"
intervention_or_exposure: "I/E"
comparator: "C"
outcome: "O"
effect: {measure: RR, value: 0.82, ci95: [0.74, 0.91]}
certainty: high | moderate | low | very_low | not_graded
applicability: "Khả năng áp dụng cho công chúng Việt Nam"
sources: [R01, R02]
review_status: pending | approved | revise | rejected
```

Validator kiểm tra nguồn tồn tại, DOI/PMID khớp metadata, con số trong lời thoại khớp ledger và mọi `[n]` ánh xạ đến tài liệu. GRADE-lite chỉ dùng nhãn mô tả nội bộ; không tuyên bố đã thực hiện GRADE đầy đủ khi chưa có đánh giá chính thức.

Kịch bản phải nói rõ bất định. Khi guideline khác nhau, video nêu phạm vi đồng thuận, điểm bất đồng và lý do bác sĩ chọn quan điểm. Ý kiến cá nhân không được khoác nhãn “bằng chứng”.

## 9. Giọng tác giả, kịch bản và storyboard

### 9.1. AI là người chấp bút, bác sĩ là người nói

Mỗi video bắt đầu bằng một `author brief`, không bắt đầu bằng prompt “hãy viết một video viral”. Bác sĩ có thể nhập vài dòng, trả lời ba câu ngắn hoặc gửi ghi âm thô:

- Điều gì trong chủ đề này khiến tôi muốn lên tiếng?
- Tôi thực sự đồng ý hoặc phản đối điều gì?
- Sau khi xem xong, tôi muốn người nghe hiểu hoặc làm gì?

Hệ thống chép lời nếu cần rồi tách `personal_position`, `reasoning`, `emotion`, `audience_concern` và những câu chữ bác sĩ muốn giữ nguyên. AI được phép sắp xếp và làm rõ; AI không được tự thêm trải nghiệm cá nhân, cảm xúc, câu chuyện nghề nghiệp hoặc lập trường mà bác sĩ chưa cung cấp.

`profiles/author-voice.vi.yaml` lưu những đặc điểm ổn định: cách xưng hô, mức trực diện, từ thường dùng, từ tránh dùng, độ dài câu, kiểu ví dụ và mức hài hước. Sau mỗi lần bác sĩ sửa, hệ thống lưu diff giữa bản AI và bản được duyệt vào `voice-learning/`. Chỉ các bản đã duyệt mới được dùng làm few-shot cho video sau. Repo không huấn luyện mô hình từ giọng tác giả trong bản đầu.

### 9.2. Mạch lập luận tự nhiên

Kịch bản phải giống một bác sĩ đang giải thích điều mình quan tâm, không giống bản tóm tắt bài báo. Khung mặc định cho 45–90 giây là:

1. **Vấn đề:** trình bày điều công chúng đang nghe hoặc đang lo; không kết luận vội.
2. **Câu hỏi chuyển:** tạo một nhịp suy nghĩ tự nhiên, chẳng hạn “Nhưng sự thật có hoàn toàn như vậy không?”
3. **Lập trường:** dùng ngôi thứ nhất khi phù hợp, chẳng hạn “Quan điểm của tôi là…”.
4. **Lập luận và bằng chứng:** đưa hai hoặc ba căn cứ mạnh nhất theo một chuỗi nguyên nhân–kết quả dễ theo dõi.
5. **Giới hạn:** nói rõ bằng chứng chưa trả lời điều gì, ngoại lệ nào quan trọng và nhóm nào không áp dụng.
6. **Hành động:** chốt một việc cụ thể, an toàn mà người xem có thể cân nhắc.

Đây là khung logic, không phải mẫu câu bắt buộc. Hệ thống phải biến đổi cách mở, chuyển ý và kết để các video không lặp giọng. Nó tránh các dấu hiệu “văn AI”: hook phóng đại, liệt kê máy móc, sáo ngữ như “hãy cùng tìm hiểu”, quá nhiều câu hỏi tu từ, kết luận tuyệt đối và nhắc nguồn như đang đọc danh mục tài liệu.

### 9.3. Đưa nghiên cứu vào lời nói

Nguồn được kể như một phần của lập luận. Tùy điều quan trọng nhất, câu nói có thể nêu nhóm tác giả, nơi thực hiện hoặc tạp chí, thiết kế nghiên cứu, cỡ mẫu, thời gian theo dõi và kết quả chính. Ví dụ về cấu trúc, không phải câu mẫu dùng lặp lại:

> “Một nhóm nghiên cứu tại … đã theo dõi … người trong … năm. Họ thấy rằng … [1].”

Kịch bản ưu tiên thông tin giúp khán giả đánh giá bằng chứng: đây là thử nghiệm hay quan sát, nghiên cứu trên ai, hiệu quả lớn đến đâu và còn bất định gì. Tên tác giả hoặc cơ sở chỉ xuất hiện khi tăng độ tin cậy hoặc giúp nhận diện nghiên cứu; không dùng uy tín thay cho chất lượng phương pháp. Tất cả tên riêng, cỡ mẫu, thời gian và con số phải lấy trực tiếp từ evidence ledger đã xác minh.

Mỗi đoạn bằng chứng đi theo nhịp: **dẫn vào → nghiên cứu đã làm gì → tìm thấy gì → kết quả đó có nghĩa gì với người xem**. Nhờ vậy, ký hiệu `[1]` hỗ trợ câu chuyện thay vì ngắt câu chuyện.

### 9.4. Nhịp nói và kiểm tra đọc thành tiếng

Mỗi câu thoại có metadata `intent`, `pace`, `pause_before`, `pause_after`, `emphasis_words` và `emotional_color`. Storyboard dùng cùng beat để phối hợp nét vẽ, chữ, biểu đồ và khoảng lặng. TTS adapter chuyển metadata sang SSML hoặc điều khiển prosody nếu provider hỗ trợ; nếu không, renderer dùng dấu câu, khoảng lặng và cắt audio.

Trước cổng duyệt thứ nhất, hệ thống bắt buộc chạy bản nghe thử. Bác sĩ có thể đánh dấu “không phải cách tôi nói”, sửa một câu hoặc thu lại câu đó. Bộ kiểm tra phát hiện câu quá dài, ba câu cùng nhịp liên tiếp, chuyển ý thiếu lý do, thuật ngữ chưa giải thích và đoạn đọc nguồn quá dày. Kiểm tra tự động chỉ gợi ý; tai nghe và quyền sửa của bác sĩ quyết định độ tự nhiên.

### 9.5. Dữ liệu storyboard

Mỗi cảnh chứa thời lượng, lời thoại, metadata diễn đạt, chữ trên màn hình, hành động hình ảnh, claim ID, source marker và loại asset. Bộ kiểm tra ước lượng tốc độ đọc tiếng Việt, độ dài subtitle, vùng an toàn TikTok, mật độ thuật ngữ, số claim và tổng thời lượng. Khi bác sĩ sửa, pipeline chỉ tái tạo audio và các cảnh có hash thay đổi.

## 10. Hình ảnh, biểu đồ và âm thanh

Phong cách mặc định:

- 70–80% whiteboard/2D từ SVG và thư viện biểu tượng có giấy phép rõ.
- 15–20% biểu đồ động từ dữ liệu đã kiểm tra.
- Không quá 10% ảnh/video AI, trừ khi bác sĩ chủ động đổi tỷ lệ.

Remotion là renderer chính vì timeline nằm trong mã, dễ test và tạo biểu đồ động. FFmpeg xử lý âm lượng, codec, cắt ghép và thumbnail. OpenMontage là nguồn tham khảo cho schema, checkpoint và quy trình render; không fork toàn bộ vì phạm vi quá lớn.

Biểu đồ chỉ đọc dữ liệu trong evidence ledger hoặc file dữ liệu riêng. Trục, mẫu số, đơn vị và khoảng tin cậy bắt buộc hiện rõ. Animation không được thay đổi tỷ lệ để phóng đại hiệu ứng.

Khi lời thoại nhắc một nghiên cứu, hệ thống có thể đưa ảnh trang đầu, abstract, bảng hoặc biểu đồ đã được phép sử dụng lên màn hình. Một nét bút vàng động bôi đúng câu hoặc con số đang được đọc; khung hình đồng thời hiện ký hiệu `[n]`. Đoạn trích phải ngắn, đúng nguyên văn, lấy từ bản người dùng được quyền truy cập và lưu tọa độ hoặc chuỗi đối chiếu để kiểm tra. Video không dùng ảnh bài báo như bằng chứng trang trí, không bôi một câu tách khỏi ngữ cảnh và không làm lộ thông tin tài khoản thư viện.

TTS dùng interface chung:

```text
synthesize(text, voice, language, speed) -> audio + word_timestamps + metadata
```

Ưu tiên benchmark mù ba lựa chọn: VieNeu-TTS local, VoiceStudio chạy như dịch vụ local và ElevenLabs nếu mua. VieNeu-TTS 0.5B có giấy phép Apache 2.0 phù hợp hơn bản 0.3B CC BY-NC khi kênh có thể kiếm tiền. Whisper/faster-whisper căn phụ đề và kiểm tra sai từ; bác sĩ nghe duyệt tên thuốc, số liệu và từ viết tắt.

CogVideo chỉ là provider thử nghiệm. RTX 3060 12 GB đủ cho TTS, ASR, Remotion và một số pipeline video nhỏ/quantized, nhưng không nên đặt CogVideo vào đường sản xuất bắt buộc. NotebookLM Video Overview phù hợp làm bản nháp ý tưởng, không phải renderer cuối vì khả năng kiểm soát cảnh, thời lượng và provenance còn hạn chế.

## 11. Cấu trúc repo dự kiến

```text
protect-your-health/
├─ AGENTS.md
├─ CLAUDE.md
├─ README.md
├─ install/
│  ├─ install.ps1
│  ├─ install.sh
│  └─ doctor.ps1
├─ skills/preventive-health-video/
│  ├─ SKILL.md
│  ├─ references/
│  └─ scripts/
├─ src/healthvideo/
│  ├─ cli.py
│  ├─ workflow.py
│  ├─ trends/
│  ├─ evidence/
│  ├─ scripting/
│  ├─ tts/
│  ├─ assets/
│  ├─ charts/
│  ├─ captions/
│  └─ qa/
├─ video/src/
│  ├─ compositions/
│  ├─ scenes/
│  ├─ charts/
│  └─ brand/
├─ schemas/
│  ├─ topic.schema.json
│  ├─ evidence.schema.json
│  ├─ author-brief.schema.json
│  ├─ script.schema.json
│  ├─ storyboard.schema.json
│  └─ project.schema.json
├─ profiles/
│  ├─ brand.vi.yaml
│  ├─ author-voice.vi.yaml
│  ├─ evidence-policy.yaml
│  └─ providers.example.yaml
├─ projects/YYYY/MM/topic-slug/
│  ├─ project.yaml
│  ├─ trend/
│  ├─ evidence/
│  ├─ author-brief.yaml
│  ├─ script/
│  ├─ storyboard/
│  ├─ handoffs/
│  ├─ audio/
│  ├─ assets/
│  ├─ renders/
│  ├─ reviews/
│  ├─ voice-learning/
│  └─ publish/
├─ cache/                 # gitignored
├─ tests/
└─ tools/
```

`AGENTS.md` và `CLAUDE.md` giữ trong khoảng 50–100 dòng, cùng trỏ đến một workflow và schema. Chúng chỉ khác cú pháp gọi tool hoặc quy ước riêng của tác nhân. Tài liệu dài nằm trong `skills/.../references/` và chỉ được nạp cho bước liên quan.

## 12. Cài nhiều máy, đồng bộ và bí mật

Git lưu mã, schema, profile, metadata, kịch bản và review. Git LFS chỉ dùng cho asset nhỏ cần phiên bản hóa. Renders, model, cache, toàn văn bài báo và audio nháp nằm ngoài Git; người dùng có thể đồng bộ chúng bằng Syncthing, NAS hoặc ổ dùng chung.

Installer kiểm tra Python, Node, pnpm, FFmpeg, font tiếng Việt, CUDA và dung lượng; sau đó tạo virtual environment, cài dependency khóa phiên bản và chạy smoke test. `healthvideo doctor` báo khác biệt giữa các máy.

API key nằm trong `.env` cục bộ hoặc secret manager, không nằm trong prompt, log hay commit. Hồ sơ bệnh nhân không thuộc phạm vi hệ thống. Mọi asset lưu giấy phép, nguồn và điều kiện sử dụng trong metadata. Dependency AGPL như VoiceStudio chạy qua ranh giới dịch vụ; trước khi phân phối thương mại cần rà soát nghĩa vụ giấy phép.

## 13. Kiểm thử và bảo đảm chất lượng

- Unit test cho state machine, hash/cache, DOI/PMID validation, citation mapping, timing và provider adapters.
- Contract test cho mọi JSON Schema và YAML handoff.
- Golden test cho một dự án mẫu tiếng Việt, gồm claim ledger, storyboard và frame đại diện.
- Visual regression cho bố cục 9:16, vùng an toàn, subtitle và biểu đồ.
- Audio QA cho clipping, loudness, khoảng lặng, tốc độ và phát âm từ nhạy cảm.
- Read-aloud QA cho nhịp câu, chuyển ý, từ nhấn và các dấu hiệu văn phong máy móc; so sánh với bản bác sĩ sửa gần nhất.
- Evidence-highlight QA xác nhận đoạn bôi vàng khớp nguyên văn, đúng claim và đúng ký hiệu nguồn.
- Failure test: mất mạng, provider timeout, thiếu asset, schema sai, TTS lỗi giữa chừng và render bị ngắt.
- Manual checklist ở hai cổng duyệt; tên người duyệt, thời gian, hash artifact và ghi chú phải được lưu.

Không dùng snapshot hình ảnh để xác nhận tính đúng của số liệu. QA hình thức và QA y khoa là hai lớp độc lập.

## 14. Thời gian thao tác mục tiêu

| Hoạt động của bác sĩ | Phút/video |
|---|---:|
| Chọn chủ đề và góc tiếp cận | 3–5 |
| Duyệt nguồn, claim và quan điểm | 8–12 |
| Sửa và duyệt kịch bản | 5–7 |
| Xem bản render, ghi patch | 5–7 |
| Duyệt caption và gói đăng | 1–2 |
| **Tổng** | **22–33** |

Mục tiêu 30 phút khả thi với chủ đề thường sau khi có template và voice ổn định. Chủ đề rủi ro cao được phép vượt mục tiêu; độ an toàn quan trọng hơn tốc độ.

## 15. Roadmap và chi phí

### Giai đoạn 0 — đặc tả và mẫu chuẩn, 2–3 ngày

Chốt schema, policy bằng chứng, brand profile, một topic mẫu và tiêu chí benchmark TTS.

### Giai đoạn 1 — video engine MVP, 1–2 tuần

Dựng project CLI, storyboard schema, Remotion templates, SVG/biểu đồ, TTS adapter, subtitle, render và cổng duyệt video. Kết thúc giai đoạn này có thể sản xuất thủ công có hỗ trợ.

### Giai đoạn 2 — evidence pipeline, 1–2 tuần

Thêm PubMed/Europe PMC/Scopus intake, claim ledger, kiểm tra định danh, citation markers, gói phản biện Claude và cổng duyệt y khoa.

### Giai đoạn 3 — trend và lịch biên tập, 1 tuần

Thêm inbox đa nguồn, scoring, deduplication và kế hoạch năm video mỗi tuần.

### Giai đoạn 4 — provider và chất lượng, 1 tuần

Benchmark TTS, tích hợp Gemini/NotebookLM/Veo tùy chọn, audio QA, visual regression và cache tinh hơn.

### Giai đoạn 5 — đa máy và hardening, 1 tuần

Hoàn thiện installer, environment doctor, backup/sync guide, security review, license inventory và recovery test.

Tổng thời gian dự kiến 5–7 tuần; có thể bắt đầu đăng sau giai đoạn 1 bằng quy trình nghiên cứu thủ công. Chi phí tăng thêm của MVP là 0 USD nếu dùng các gói hiện có và TTS local. ElevenLabs là tùy chọn sau benchmark; mức gói và giá phải kiểm tra lại tại thời điểm mua. Veo dùng hạn mức Gemini hiện có, không dùng mặc định cho mọi video.

## 16. Rủi ro và biện pháp kiểm soát

| Rủi ro | Kiểm soát |
|---|---|
| AI bịa nguồn hoặc số liệu | Chỉ nhận ID đã xác minh; claim–citation validator; cổng bác sĩ duyệt |
| Quan điểm quá mạnh so với bằng chứng | Lưu certainty, applicability, contradiction; Claude review có điều kiện |
| Tốn quota vì chuyền toàn bộ context | Artifact nhỏ theo schema; routing theo rủi ro; delta patch; cache |
| Scraper mạng xã hội hỏng | Nhập thủ công có cấu trúc là đường dự phòng; không phụ thuộc một nguồn |
| Giọng Việt đọc sai | Từ điển phát âm; ASR back-check; bác sĩ nghe duyệt |
| Video AI sai giải phẫu | Chỉ dùng cảnh trang trí hoặc qua duyệt; ưu tiên SVG kiểm soát được |
| Khác môi trường giữa máy | Lockfile, installer, `doctor`, manifest phiên bản |
| Vi phạm bản quyền hoặc giấy phép | Metadata asset; không commit toàn văn; rà soát AGPL/NC trước thương mại hóa |

## 17. Quyết định đã chốt

- Tiếng Việt trước; kiến trúc i18n để thêm tiếng Anh sau.
- Tỷ lệ hình chủ đạo là whiteboard/2D, xen biểu đồ động và cảnh AI ngắn.
- AI chấp bút từ `author brief`; giọng điệu và lập trường thuộc về bác sĩ, không dùng nhân vật dẫn chuyện chung chung.
- Lời thoại có nhịp, khoảng dừng và từ nhấn; cảnh nghiên cứu có thể bôi vàng đúng đoạn đang được giải thích.
- Video chỉ hiện ký hiệu `[1]`, `[2]`; caption và evidence record chứa liên kết đầy đủ.
- Codex là tác nhân chính; Claude phản biện có điều kiện; ChatGPT làm kế hoạch theo lô.
- TTS là adapter và được chọn bằng benchmark mù, không khóa sớm vào ElevenLabs.
- Hai cổng duyệt của bác sĩ là bắt buộc; không tự động đăng.
- Máy đích chính: Intel i5-13500, RTX 3060 12 GB, RAM 32 GB.

## 18. Câu hỏi hoãn đến kế hoạch triển khai

Các lựa chọn sau không chặn kiến trúc, nhưng cần chốt trong giai đoạn 0:

- Tên kênh, bảng màu, font, logo và giọng xưng hô.
- Giọng thật clone hay giọng tổng hợp riêng; điều kiện đồng ý khi clone giọng.
- Mức ngưỡng nào bắt buộc gọi Claude review.
- Cách dùng Scopus trên từng máy trong giới hạn giấy phép tài khoản.
- Syncthing, NAS hay thư mục cloud cho asset nặng.
- Bộ ba chủ đề dùng làm golden tests.

## 19. Tài liệu và repo tham khảo

- [OpenAI — Using GPT-5.5](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5)
- [OpenAI — ChatGPT use cases](https://learn.chatgpt.com/use-cases)
- [Anthropic — Prompt templates and variables](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables)
- [Anthropic — Claude Code với gói Pro/Max](https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)
- [NCBI — E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)
- [Europe PMC — REST API](https://europepmc.org/RestfulWebService)
- [Remotion](https://github.com/remotion-dev/remotion)
- [OpenMontage](https://github.com/calesthio/OpenMontage)
- [VoiceStudio](https://github.com/debpalash/VoiceStudio)
- [CogVideo](https://github.com/zai-org/CogVideo)
- [ECC](https://github.com/affaan-m/ECC)
- [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI)
- [VieNeu-TTS](https://github.com/pnnbao-ump/VieNeu-TTS)
- [Google NotebookLM — Video Overviews](https://blog.google/technology/google-labs/notebooklm-video-overviews/)

## 20. Điều kiện chuyển sang kế hoạch triển khai

Bác sĩ duyệt tài liệu này hoặc yêu cầu sửa. Sau khi duyệt, bước kế tiếp là viết kế hoạch triển khai theo task nhỏ, chỉ rõ file, test, lệnh xác minh và checkpoint. Việc viết mã bắt đầu sau khi kế hoạch đó được duyệt.
