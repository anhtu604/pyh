# Chuẩn agent và biên tập lấy người xem làm điểm xuất phát

Ngày 2026-11-14. Yêu cầu trực tiếp mới của bác sĩ thay ưu tiên phải hoàn tất gout
trước trong CLAUDE.md và handoff cũ. Dev lead: codex.

## Mục tiêu và quyết định của bác sĩ

- Dừng các video pilot; hoàn thiện xưởng trước khi làm video mới.
- Bắt đầu bằng chuẩn hóa skill từng agent và chọn model theo đúng công việc.
- Video chia sẻ điều hay, thú vị mà người khác muốn nghe; có cách nhìn, sự giải thích
  hoặc giá trị thực hành, không đọc lại kiến thức tra mạng được.
- TOFU/MOFU/BOFU là tầng nhu cầu khán giả. BOFU đã được bác sĩ xác nhận:
  thực hành sức khỏe, đi khám khi cần và tin theo dõi kênh; không phải bán sản phẩm.
- Giữ nguồn thật, giới hạn bằng chứng, hai cổng PIN và quyền duyệt của bác sĩ.

## Cách triển khai do dev lead chọn

1. Chỉ thêm lời dặn “viết hấp dẫn” vào writer: ít thay đổi nhưng scout, chuyên gia,
   critic và bài đăng vẫn tối ưu cho đầu ra cũ; không chọn.
2. Đồng bộ hợp đồng các vai, prompt và phân model trong cấu trúc xưởng hiện có:
   chọn cho đợt này. Kiểm bằng tình huống áp lực và mẫu đầu ra, không làm video pilot.
3. Đổi toàn bộ workflow/schema, tách biên kịch khỏi storyboard/code dựng ngay:
   hướng cần xem tiếp, chưa làm trong đợt skill/model vì có bất biến cổng và timing.

Đây là quyết định triển khai của dev lead trong phạm vi bác sĩ giao, không ghi nhận
là bác sĩ đã duyệt chi tiết kỹ thuật hay một sản phẩm y khoa.

## Hợp đồng nội dung

Trước khi viết, xác định trong ghi chú làm việc (không thêm khóa vào YAML có schema):
người xem cụ thể; tầng chính; câu hỏi họ thật sự muốn trả lời; hiểu lầm/khoảng trống;
góc kể; lời hứa một câu; điều thay đổi ở người xem sau khi xem; một hành động phù hợp.
Khi bàn giao nghiên cứu, giữ định hướng trong `expert-brief.md` hiện có;
ở bước viết, dùng `title` và trường `goal` của các chương trong outline để lưu
lời hứa, tiến triển/payoff và CTA. Scratch chỉ dùng thử hook/câu, không phải nơi
duy nhất giữ quyết định biên tập. Các vai sau đọc brief và nội dung thực tế; không tự đoán mục tiêu bán hàng.

| Tầng chính | Người xem đang cần | Video phải trả được |
| --- | --- | --- |
| TOFU | Chưa chủ động tìm hiểu, nhưng nhận ra chuyện liên quan mình | Một câu hỏi đáng tò mò, cách nhìn mới, lý do đáng chia sẻ |
| MOFU | Đã quan tâm, đang bối rối hoặc có niềm tin sai | Lời giải thích, phân biệt hay cân nhắc giúp họ hiểu rõ hơn |
| BOFU | Đã hiểu, cần biết bước tiếp theo | Một hành động sức khỏe có căn cứ, điều cần hỏi khi đi khám, hoặc bước theo dõi kênh có ích |

Một video có thể phục vụ hơn một tầng nhưng không bắt buộc ba phần theo phễu.
Không ép mọi video mở bằng đau đớn, hài trong ba giây, một ẩn dụ duy nhất, một cú twist,
hay kết bằng nhắc thuốc/đi khám. Dùng khi phù hợp người xem và bằng chứng.
Câu kết nhận diện hiện có vẫn giữ cho tới khi bác sĩ thay riêng.

“Mới” là giá trị diễn giải: nối hai điều người xem chưa nối, làm rõ một nghịch lý,
giúp cân nhắc hay hành động; không phải tự tạo phát hiện y khoa mới.
Mở bài xác nhận đúng lời hứa tiêu đề, đưa giá trị sớm. Thân bài có tiến triển
tình huống → câu hỏi → phát hiện có căn cứ → hệ quả. Chọn cấu trúc theo đề tài,
không biến mạch này thành khuôn lời đọc cố định.
Loại đoạn chỉ đọc định nghĩa, liệt kê hay nhắc lại mà không giúp trả lời câu hỏi.
Không giữ thông tin an toàn cần thiết đến cuối để câu giờ; không bịa số liệu, bệnh nhân,
trải nghiệm bác sĩ, tín hiệu xu hướng hoặc hiệu quả giữ chân.

## Hợp đồng từng vai

| Vai | Đầu vào và phán đoán chính | Đầu ra/ranh giới |
| --- | --- | --- |
| Điều phối | Trạng thái, yêu cầu, bằng chứng đang có | Định tuyến và brief đủ đích; không tự duyệt hay hứa đã sửa |
| Điều phối chuyên sâu | Chuỗi log và kết quả kiểm | Nguyên nhân có chứng cứ, phân biệt giả thuyết; không sửa ngoài quyền |
| Scout | Nhu cầu người xem, tín hiệu tìm được | Câu hỏi, tầng chính, góc đáng nghe; thiếu demand ghi là giả thuyết |
| Chuyên gia y học | Câu hỏi/hiểu lầm cần giải | Ledger + expert brief với phát hiện có ích, độ chắc chắn, điều không được suy diễn |
| Biên kịch | Brief khán giả, ledger, expert brief | Câu chuyện trả lời lời hứa; không đọc lại expert brief như giáo trình |
| Kiểm duyệt kịch bản | Cùng lời hứa và toàn bộ script | Chỉ rõ nơi người xem mất lý do nghe; đúng y khoa chưa đủ để đạt |
| Đạo diễn hình | Lời/cảnh và ảnh ứng viên | Hình giải thích điều khó, đúng giải phẫu, không trang trí che mất nội dung |
| Thợ dựng | Brief sửa, timing, QA | Sửa đúng phạm vi hình/âm, không tự đổi lời đọc hay claim |
| Kiểm định sản phẩm | Bản dựng, QA, khung hình, bài đăng | Phân biệt đã xem/đã nghe/suy đoán; không dùng contact sheet để xác nhận âm thanh |
| Viết bài đăng | Kịch bản đã duyệt | Tiêu đề/thumbnail/CTA trả đúng lời hứa, không bịa nội dung để tăng click |
| Phân tích ý kiến | Phản hồi và log liên quan | Phân loại gốc sản phẩm/xưởng/chuẩn kênh, điều kiện hoàn tất kiểm được |

Mỗi skill phải nói rõ đầu vào, cách phán đoán, đầu ra, xong khi nào và thiếu dữ liệu
thì trả về đâu. Không thêm skill marketing lớn chỉ để tăng số lượng.
Giữ tên file, trường schema, sáu tiêu chí script critic và quyền sửa hiện hành.

## Model và kiểm chứng

Chỉ cấu hình model có trong CLI hiện tại; không Opus/astra theo yêu cầu trước.
Ưu tiên model gọi trực tiếp cho việc hữu hạn; không mặc định dùng orchestrator
cho mọi vai. Vai làm và vai chấm có đầu chuỗi khác nhau. Giữ fallback khi hết quota.
Một mẫu ngắn chỉ kiểm khả năng theo brief, giọng Việt và độ trễ; không chứng minh
khả năng viết video dài, tìm y văn, đọc ảnh hay sửa code. Chi tiết trong
`docs/reference/agent-model-evaluation.md`.

## Bằng chứng baseline và kiểm sau sửa

Baseline độc lập dùng skill cũ cho đề bài video TOFU: agent vẫn chia TOFU–MOFU–BOFU,
kết bằng câu nhắc dùng thuốc và hỏi bác sĩ. Agent chỉ ra nguyên tắc 1, 9 là nguồn ép.
Đó là lỗi khớp mục đích người xem; không phải lỗi thiếu một model đắt tiền hơn.

Kiểm sau sửa: cùng tình huống TOFU; thêm MOFU, BOFU, thiếu claim, đề bài đòi hứa
chữa khỏi, và kiểm reviewer biết chặn bài đủ đúng nhưng thiếu giá trị người xem.
Đánh giá bằng đầu ra thật, không chỉ tìm keyword trong skill.
Chạy test company, render prompt, script-review và lint. Không TTS/nhạc/render.

## Giới hạn và việc tiếp theo

- Schema/workflow explain-first vẫn kiểm bản đồ bình thường → bệnh, bảy nhịp và
  video dài 10–25 phút. Giữ hợp lệ nhưng không bắt người xem nghe tên bảy mục.
  Chưa tuyên bố xưởng đã hỗ trợ mọi kiểu nội dung TOFU/MOFU/BOFU.
- Writer vẫn phải xuất storyboard/asset và đôi khi code SVG. Tách chuyên môn
  kể chuyện khỏi hiện thực kỹ thuật là việc workflow tiếp theo.
- Skill không khắc phục crash, mất kết nối, treo CLI, thiếu timeout hoặc lỗi timing.
  Cần một việc riêng: lỗi phân loại được, log đủ, retry hữu hạn theo loại lỗi,
  giữ approval/cache hợp lệ, hết khả năng thì báo đích danh việc cần người xử lý.
- Hai pilot, queue cũ và log riêng lưu ở `cache/pilot-archive/2026-11-14/`.
  Xưởng dừng; không tự bật lại để thử bộ hướng dẫn này.

## Nguồn phương pháp

[YouTube Help — key moments for audience retention](https://support.google.com/youtube/answer/9314415?hl=en):
đối chiếu mở bài với lời hứa tiêu đề/thumbnail, xem đoạn rơi người xem, đưa phần
hấp dẫn lên sớm. Đây là phương pháp đánh giá; chưa có dữ liệu retention của kênh.
Không dùng quy tắc ba giây hay nhịp sáu giây như bảo đảm hiệu quả.
