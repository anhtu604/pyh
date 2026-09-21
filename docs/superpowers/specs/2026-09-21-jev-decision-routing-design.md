# Thiết kế Jev cho định tuyến quyết định có kiểm soát

**Ngày:** 21-09-2026
**Trạng thái:** Chờ bác sĩ duyệt đặc tả trước khi lập kế hoạch triển khai

## 1. Mục tiêu

Tích hợp Jev của TypeSafe như một lớp ra quyết định có cấu trúc cho các thao tác
phân loại, chấm điểm và cảnh báo trong Protect Your Health. Jev giúp Codex ưu
tiên việc cần xem, nhưng không xác nhận tính đúng y khoa, không viết nội dung và
không tự đổi trạng thái dự án.

Hệ thống vẫn giữ nguyên thứ tự: tìm và kiểm định kiến thức, trình bày các góc
nhìn, nhận ý kiến riêng của bác sĩ, rồi mới tạo brief và đi qua hai cổng duyệt.

## 2. Phạm vi

Ba use case đầu tiên dùng output Jev ở dạng *advisory*:

1. **Topic triage.** Đọc topic card đã có để đề xuất độ ưu tiên và các yếu tố
   rủi ro cần người vận hành xem lại.
2. **Claim triage.** Đọc metadata và claim đã có nguồn để đánh dấu claim cần
   kiểm định thêm, thiếu citation hoặc có ngôn ngữ tuyệt đối. Jev không đánh giá
   sự thật của claim.
3. **Second-model routing.** Đề xuất có nên tạo gói phản biện mô hình thứ hai
   theo policy. Người vận hành vẫn phải chủ động chạy `agent review-request`.

Jev không được dùng cho tìm y văn, trích xuất số liệu từ toàn văn, tạo nguồn,
viết/sửa claim, viết script, chọn lập trường của bác sĩ, duyệt medical/video,
sản xuất, đóng gói hoặc đăng video.

## 3. Kiến trúc và ranh giới

```text
topic card / source-bound claim metadata / review context
                         |
                         v
                 Jev decision adapter
                         |
                         v
          versioned advisory decision record
                         |
             +-----------+-----------+
             |                       |
      operator sees suggestion   manual workflow command
```

Adapter là ranh giới duy nhất gọi TypeSafe SDK. Domain và workflow nhận một
protocol nội bộ, nên unit test thay bằng fake transport và không gọi mạng. Mỗi
use case trả về một record bất biến gồm loại quyết định, lựa chọn đã chuẩn hóa,
confidence, model identifier, input hash, thời điểm và lý do ngắn đã lọc.

Record advisory không sửa `TopicScores`, claim ledger, author brief, project
state, review record hay stage record. Một lệnh mutating hiện có mới có thể đổi
state; Jev không được gọi trong lệnh đó để tạo transition ngầm.

## 4. An toàn dữ liệu và secret

Key dùng biến môi trường `TYPESAFE_API_KEY`. Khi người vận hành chọn dùng tệp
secret cục bộ, loader chỉ tìm `Path(os.environ["LOCALAPPDATA"]) /
"ProtectYourHealth" / "typesafe.env"`; tệp này nằm ngoài repository, không
được log, copy vào artifact, backup hay Git. Biến môi trường do tiến trình nhận
được ưu tiên hơn tệp cục bộ.

Request chỉ chứa trường tối thiểu: topic card, claim metadata, source ID/loại
nguồn/certainty và policy routing. Không gửi API key, dữ liệu bệnh nhân, toàn
văn có bản quyền, file audio/video, raw research cache, author profile hoặc
phản hồi cổng duyệt.

Artifact không lưu raw provider response, prompt đầy đủ hay trường có tên
`token`. Chỉ lưu lựa chọn chuẩn hóa, confidence, model identifier, input hash
và lý do đã giới hạn độ dài. Security audit và backup policy phải tiếp tục từ
chối credential, response thô và dữ liệu bị cấm.

## 5. Hành vi fail-closed

Jev là opt-in. Nếu thiếu key, SDK/HTTP lỗi, response không đúng schema, model
không xác định, confidence dưới ngưỡng policy hoặc input vượt giới hạn, adapter
trả một advisory `manual_review_required`; workflow giữ nguyên byte và trạng
thái dự án. Không có retry ngầm trong mutation và không có fallback sang mô
hình sinh văn bản.

Ngưỡng mặc định là `0.90` cho nhãn “đủ tin cậy để hiển thị như một gợi ý mạnh”.
Dù đạt ngưỡng, output vẫn chỉ là gợi ý. Mọi ngưỡng và policy phải hiển thị trong
record để người vận hành hiểu giới hạn của kết quả.

## 6. Tích hợp theo use case

### Topic triage

Jev nhận topic card và policy công khai. Output là một band ưu tiên đề xuất,
các risk flag đã chuẩn hóa và `manual_review_required`. UI/CLI hiển thị output
cạnh điểm triage hiện có, không ghi đè điểm gốc và không tự chọn/reject topic.

### Claim triage

Jev chỉ chạy sau khi pipeline đã có claim và source metadata. Output là các
cờ kiểm tra như `citation_check`, `absolute_language_check`,
`population_applicability_check` hoặc `manual_review_required`. Cờ này không
chứng minh claim đúng hay sai, và không cho phép chuyển sang medical gate.

### Second-model routing

Jev nhận risk context tối thiểu và trả `not_recommended`, `consider_review` hoặc
`manual_review_required`. `consider_review` chỉ hiển thị lý do và lệnh tiếp
theo. Nó không tạo gói XML, không gọi Claude/ChatGPT và không chuyển trạng thái
sang `awaiting_second_model_review`.

## 7. Thành phần dự kiến

| Thành phần | Trách nhiệm |
| --- | --- |
| `healthvideo/jev/config.py` | Resolve key hiện diện an toàn, config và giới hạn input. |
| `healthvideo/jev/client.py` | Adapter TypeSafe SDK, protocol nội bộ và validate response. |
| `healthvideo/domain/jev_decision.py` | Model record, enum outcome và invariants thuần dữ liệu. |
| `healthvideo/workflows/jev_triage.py` | Xây input tối thiểu, gọi protocol, tạo advisory record. |
| CLI `healthvideo jev ...` | Chạy explicit check/triage và chỉ in hoặc ghi advisory artifact. |
| tests | Fake transport, validation, redaction, failure và non-transition tests. |

Vị trí artifact chi tiết sẽ theo layout revision hiện hữu trong plan. Artifact
phải versioned, write-once và gắn `input_hash`; không trở thành nguồn thẩm quyền
thay cho topic card, evidence ledger hoặc review record.

## 8. Khả năng tương thích và vận hành

Không có key hoặc không gọi lệnh Jev thì mọi project v1/v2 hoạt động đúng như
trước. Không migration schema, không đổi GateKind, không thêm provider network
vào `produce`, `package` hoặc render.

`healthvideo jev check` là lệnh explicit duy nhất có thể kiểm tra provider sống;
nó chỉ xác nhận cấu hình và danh sách model tối thiểu, không in secret. Test CI
không gọi endpoint thật. Trước vận hành multi-writer hoặc backup, operator vẫn
chạy `healthvideo doctor --project <project>` và `healthvideo security-audit
<project>` theo M7 runbook.

## 9. Tiêu chí chấp nhận

- Thiếu/lỗi key, timeout, malformed response và confidence thấp đều không đổi
  project state, không ghi partial artifact và dẫn về manual review.
- Raw response, secret, patient data và full text không xuất hiện trong request
  fixture, artifact, log, backup hay Git.
- Ba use case chỉ tạo đề xuất được schema-validate; không có path nào tự chọn
  topic, sửa ledger, gửi phản biện, ký gate, sản xuất hay xuất bản.
- Unit/contract tests dùng fake transport; CLI health check chỉ chạy mạng khi
  người vận hành gọi rõ ràng.
- Full regression giữ nguyên hai medical/video gate và `packaged` là điểm dừng
  trước đăng thủ công.

## 10. Quyết định đã chốt

- Jev là decision engine có cấu trúc, không là tác nhân y khoa hay content model.
- Triển khai theo adapter opt-in, record advisory và manual action rõ ràng.
- `0.90` chỉ phân biệt gợi ý mạnh với manual review, không cấp quyền tự động.
- Secret ở environment hoặc local app-data ngoài repo; không commit `.env`.
- Kế hoạch triển khai phải dùng test-first và kiểm thử đầy đủ đường fail-closed.
