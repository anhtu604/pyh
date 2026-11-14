# Phân model agent — ghi nhận 2026-11-14

Đợt này không chạy video pilot. Phân công dưới đây là cấu hình làm việc có thể
điều chỉnh, không phải bảng xếp hạng năng lực tổng quát.

## Model khả dụng và cách gọi

`agy models` ngày 2026-11-14 trả về Carbon medium/high, Hydrogen medium,
orchestrator và các mức khác. Cache model Codex có `gpt-6.1-sol`;
CLI Claude Code có trên máy. Có tên trong danh sách không chứng minh hết quota
hay khả năng tốt ở mọi vai. Không dùng Opus/astra theo yêu cầu bác sĩ trước.

Với việc hữu hạn có đầu vào/đầu ra rõ, gọi Carbon trực tiếp; giữ điều phối nhiều
bước ở workflow của xưởng. Chưa có phép đo đối chứng chứng minh gọi trực tiếp
nhanh hơn orchestrator, nên không tuyên bố mức tiết kiệm.

| Vai | Model đầu chuỗi | Căn cứ và mức chắc chắn |
| --- | --- | --- |
| Điều phối chat | Hydrogen medium | Giữ phân công nhẹ hiện có; kiểm định tuyến bằng hợp đồng, chưa đo lại độ trễ |
| Điều phối chuyên sâu | Sol | Đọc code/log và tổng hợp; giữ cấu hình hiện có, chưa có benchmark riêng |
| Scout | Hydrogen medium | Tạo ứng viên nhanh, phải ghi giả thuyết khi thiếu tín hiệu; chưa kiểm chất lượng chọn đề |
| Chuyên gia y học | Carbon high | Phân công cho việc đọc/đối chiếu phức tạp; chưa benchmark y văn, phải qua kiểm claim |
| Biên kịch | Sol | Mẫu mở bài bên dưới; cần thêm đề và bài dài trước kết luận chất lượng |
| Kiểm duyệt kịch bản | Carbon medium | Khác nhà cung cấp đầu chuỗi writer; đã bắt lỗi trong một bài cố tình sai, chưa phải bộ đánh giá đầy đủ |
| Đạo diễn hình | Carbon medium | Nhiệm vụ ảnh có phạm vi rõ; chưa chạy bộ ảnh sai giải phẫu/bố cục |
| Thợ dựng | Carbon medium | Giữ phân công agy, gọi trực tiếp; chưa benchmark sửa Remotion |
| Kiểm định sản phẩm | Sonnet | Giữ đầu chuỗi khác thợ dựng; chưa kiểm nghe/xem bản dựng thật |
| Viết bài đăng | Hydrogen medium | Ràng buộc từ bài đã duyệt, kiểm title/thumbnail/claim; chưa so chất lượng tiêu đề |
| Phân tích ý kiến | Hydrogen medium | Phân loại/viết brief; chưa chạy bộ tình huống định tuyến riêng |

Chuỗi dự phòng trong company.yaml giữ chuyển model khi hết quota. Validator
hiện chỉ kiểm độc lập của đầu chuỗi người làm/người chấm; sau failover có thể
trùng model. Chưa tuyên bố đã bảo đảm độc lập mọi lần chạy; cần kiểm ở runtime
trong đợt phục hồi lỗi, không tự nới cổng duyệt.

## Mẫu mở bài: cùng đề, cùng dữ kiện, một lần mỗi ứng viên

Đề: viết hai hướng mở cho người thấy khỏe nên chưa quan tâm huyết áp, mỗi hướng
có title, lời mở 60–90 từ, outline bốn nhịp, CTA và giá trị nhận thêm.
Chỉ cấp ba dữ kiện từ
[WHO — Hypertension](https://www.who.int/news-room/fact-sheets/detail/hypertension):
nhiều người không có triệu chứng; đo giúp nhận biết; không điều trị có thể dẫn
đến bệnh tim, thận và đột quỵ. Không số, liều, bệnh nhân hay trải nghiệm bác sĩ.
Packet này dùng để thử lời viết, không phải ledger hay sản phẩm đã duyệt.

| Ứng viên | Cách gọi | Thời gian quan sát | Kết quả |
| --- | --- | --- | --- |
| Sol | Codex exec, reasoning medium, read-only | 45,43 giây | Exit 0, đủ hai hướng; góc tự phân biệt cảm giác/thông tin và góc hỏi thăm người thân |
| Carbon medium | agy, plan mode, không dùng tool theo brief | 124,70 giây | Exit 0, đủ hai hướng; có thêm diễn giải về tâm lý người bận rộn và title so sánh “nhất” ngoài packet |

Codex stderr có lỗi refresh danh sách model do timeout nhưng lệnh vẫn hoàn tất
exit 0; không tính lỗi đó thành lỗi kịch bản. reasoning medium khớp cấu hình
Codex trên máy lúc đo; company.yaml hiện không khóa reasoning riêng từng vai.
Hai CLI dùng mode khác nhau, mạng/cache và một lần đo có thể ảnh hưởng thời gian.

Nhận xét của dev lead: giữ Sol làm ứng viên writer chính vì đầu ra bám packet
và có hai góc chia sẻ khác nhau. Cả hai vẫn có câu khái quát và cần biên tập;
không chấm “hay” chỉ vì có hook hay đủ số mục. Với Carbon, suy luận tâm lý cần
được viết thành tình huống giả định hoặc có căn cứ, không biến thành sự thật.
Chưa chấm mù, chưa thử nhiều đề/ngôn ngữ/độ dài; không suy rộng tỷ lệ thời gian
hoặc kết luận Sol luôn hay hơn Carbon.

Prompt, stdout/stderr và kết quả gốc giữ tại
`E:/Protect Your Health/cache/dev-lead/model-benchmark/` (không commit).

## Kiểm critic trên model cấu hình và review bộ hướng dẫn

Gọi Carbon medium qua agy plan mode với skill critic mới và bốn dòng giả lập:
mở kiểu giáo trình, định nghĩa chưa có claim, lặp lại định nghĩa, lời hứa không
bao giờ đột quỵ để bán gói tư vấn. Chỉ cấp hai claim về không triệu chứng và đo
để nhận biết. Model hoàn tất exit 0 trong 131,83 giây, trả YAML đúng sáu tiêu chí,
bảy issue gắn đúng dòng, `dung_yeu_cau: 1`. Nó bắt lời hứa vô căn cứ, CTA bán hàng,
ý lặp; không đòi hài hay đủ ba tầng; ghi rõ artifact còn thiếu và không nhận đã
kiểm những file không được cung cấp. Đã parse YAML và kiểm schema báo cáo.
Đây là tình huống lỗi rõ, đã nêu giới hạn dữ kiện; chưa chứng minh critic tự
phát hiện được mọi lỗi tinh vi trong bài dài.

Reviewer độc lập (Sol medium) áp dụng skill mới trên năm nhóm tình huống:
TOFU, MOFU, BOFU thiếu claim/yêu cầu hứa tuyệt đối, bài giáo trình/CTA sai,
và phân biệt contact sheet với kiểm âm thanh/quyền sửa. Đầu ra mô phỏng cho
thấy giữ được intent và ranh quyền. Vòng review đã sửa mất brief khi bàn giao,
hứa fallback SVG không thật và nhánh thiếu bằng chứng mơ hồ; sau sửa PASS phạm vi
skill/prompt/config. Đây không phải đánh giá thay cho tất cả model sản xuất.

## Điều kiện nâng đánh giá trước khi bật sản xuất

- Dùng cùng gói đầu vào và skill mới; nhiều đề ở cả TOFU/MOFU/BOFU, có bài thiếu
  claim và yêu cầu sai. Đảo tên người viết khi chấm, bác sĩ chọn đoạn muốn nghe.
- Tách điểm đúng nguồn, đúng yêu cầu, giọng kể, tiến triển/payoff, CTA, chi phí
  và độ trễ; bịa claim không được bù bằng điểm văn hay.
- Kiểm riêng từng loại việc: truy nguồn cho chuyên gia, lỗi cố ý cho critic,
  ảnh thật cho vai nhìn ảnh, component/test cho thợ dựng, log cho điều phối.
- Thử hết quota/lỗi công cụ với retry hữu hạn, không dùng sinh TTS/render làm
  benchmark viết. Đo thật trên CLI cấu hình chạy, không coi subagent mô phỏng
  là kiểm định toàn bộ model sản xuất.

Hướng dẫn biên tập tham khảo
[YouTube Help — audience retention](https://support.google.com/youtube/answer/9314415?hl=en):
mở bài khớp title/thumbnail và đánh giá chỗ người xem bỏ qua. Kênh chưa có số liệu
để bảo đảm retention, CTR hay “viral”; các ngưỡng thời gian trong skill chỉ là
hướng thiết kế hoặc giới hạn runtime.
