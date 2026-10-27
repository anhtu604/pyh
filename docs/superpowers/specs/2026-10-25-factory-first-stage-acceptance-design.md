# Hoàn thiện xưởng trước, sản xuất sau

Ngày: 2026-10-25. Trạng thái: đã duyệt (bác sĩ đã duyệt trong chat ngày 2026-10-25).

## 1. Ý định và quyết định của người dùng

Tách hai việc: (1) hoàn thiện công cụ xưởng, (2) tạo và điều chỉnh sản phẩm.
Hoàn thiện xưởng trước; nghiệm thu từng giai đoạn qua app. Sau khi thử và chấp
nhận tiêu chuẩn của một giai đoạn, xưởng dùng tiêu chuẩn đó cho sản xuất A–Z.
Không yêu cầu bác sĩ dùng PowerShell. Thiết kế gọn, tận dụng hệ thống hiện có.
Người dùng dùng trực tiếp muse.ai và cho biết có tài khoản với một tỷ token;
đây là thông tin do người dùng cung cấp, chưa kiểm chứng hạn mức/dịch vụ.

Quyết định mới thay thứ tự cũ trong HANDOFF: chưa tiếp tục sửa storyboard gout,
chưa tạo audio/render cho gout. Lựa chọn giữ chart_crop 15–25% vẫn được bảo lưu
cho vòng sửa sản phẩm sau. Không tự bật xưởng hay tiếp tục hàng đợi thật.

## 2. Hiện trạng đã kiểm tra

- Có pipeline nghiên cứu, ledger, script, storyboard, SVG/FLUX, TTS, alignment,
  Remotion dài/dọc, posts, package; hai cổng duyệt và invalidation đã tồn tại.
- App HTML/Python có start/stop, tiến độ, agent/log, xem script/claim/video,
  góp ý, lịch sử và duyệt/từ chối bằng PIN. Chưa có thao tác nhập/chọn chủ đề,
  thư viện tài nguyên, nhập tài nguyên Muse, mở lại và xử lý bước lỗi qua app.
- Góp ý bác sĩ được nối vào profiles/doctor-feedback.yaml và prompt, nhưng
  chưa phân biệt đủ tiêu chuẩn đã nghiệm thu với góp ý chỉ dành cho một dự án.
- Cache từng câu của produce chỉ áp dụng ElevenLabs trên master, bỏ qua Vibi;
  factory gọi lại bước lỗi ở chu kỳ sau. Nhánh codex/gout-production-cache có
  bản sửa dở, chưa commit/merge. Review phát hiện cần phân biệt ValueError do
  audio nhà cung cấp hỏng với lỗi kiểm tra đầu vào xác định. Phải sửa trước dùng.
- Một lượt pytest trên bản sửa trung gian: 1467 pass, 1 skip. Có chỉnh sửa sau
  lượt đó chưa chạy lại; chưa có nghiệm thu giao diện hay kiểm chứng Muse.
- Ý tưởng Muse/Thư viện nằm trong HANDOFF chưa commit ở E:/Protect Your Health,
  không có trong bản HANDOFF của worktree. Cần đồng bộ tài liệu, giữ ý gốc.

## 3. Phạm vi gọn do tác nhân đề xuất

Giữ Python + HTML hiện có và Remotion; không viết lại frontend, không dựng
nền tảng plugin, không thêm hệ thống tài khoản, dashboard token hoặc kho cloud.
Bổ sung chức năng vào app bằng các khối nhỏ, tái dùng CLI/workflow đã có.

### 3.1 Điều khiển trọn quy trình qua app

Có thể nhập chủ đề/câu hỏi và ghi chú; xem hàng đợi; theo dõi giai đoạn; xem
sản phẩm trung gian; góp ý; dừng/tiếp tục; nhận lý do bị chặn và thử lại khi đã
sửa. Trước khi thử lại phải thấy bước nào chạy và phần nào dùng lại cache.
Mở lại nội dung đã duyệt phải gọi workflow invalidation hiện có, bảo toàn lịch
sử. Không ghi đè approval hoặc tự coi góp ý là quyết định duyệt.

Giữ hai cổng y khoa/video và PIN ở máy bác sĩ. Không thêm cổng nội dung thứ ba.
Phê duyệt tiêu chuẩn xưởng là việc cấu hình công cụ, không duyệt một video thật.
Trong khu vực thử xưởng, quyết định thử không được bật worker hàng đợi thật;
không tái dùng trực tiếp hành vi decide hiện tại đang tự bật factory.

### 3.2 Chạy lại không lặp chi phí ngoài ý muốn

Cache từng câu theo request thực tế, provider, model, voice, settings và xử lý
chuẩn hóa; kiểm hash và WAV trước dùng lại. Giữ cache khi bước sau thất bại.
Lỗi dữ liệu/QA xác định dừng chờ sửa; lỗi mạng/dịch vụ chỉ thử lại có giới hạn.
Không lặp vô hạn ở chu kỳ factory. Thông báo không in key hoặc thông tin bí mật.
App hiển thị lỗi, tác vụ đang chờ và số yêu cầu TTS thực tế; chưa cần dự đoán tiền
khi không có biểu phí tin cậy. Không coi token Muse tương đương credit Vibi.

### 3.3 Thư viện tài nguyên và Muse

Một danh sách có preview, loại, dự án, prompt/nguồn nếu có, kích thước, trạng
thái chọn và nút mở file. Gom ảnh FLUX, SVG, thumbnail, contact sheet và tài
nguyên nhập từ Muse. Dùng lại asset manifest, hash và cơ chế giấy phép sẵn có.
Ảnh dùng lại phải giữ nguồn và liên kết tới nơi sử dụng; tài nguyên thử xưởng
ở khu thử riêng, không tự chuyển sang sản phẩm.

Muse là công cụ phụ trợ tạo ảnh minh họa không nhãn, ảnh tham chiếu, thumbnail.
SVG/Remotion vẫn dựng hình y khoa có nhãn và video cuối. AI clip chưa thuộc
phạm vi này vì spec hiện loại AI video; không ngầm mở lại bằng thiết kế này.

Bước đầu sau khi duyệt thiết kế là kiểm chứng nhỏ: xem tài khoản Muse đã đăng
nhập bằng trình duyệt, xác nhận công cụ tạo ảnh thực có, xuất được file, điều
khoản dùng thương mại, giới hạn và cách lấy file. Không mặc định có API tạo ảnh
hay tài khoản token cho phép tự động hóa. Ưu tiên agent thao tác trình duyệt
hiện có nếu được hỗ trợ; bác sĩ chỉ cần can thiệp khi đăng nhập/ủy quyền.
Nếu không đáp ứng được, báo rõ giới hạn; dùng FLUX hiện có và nhập file qua app,
không để Muse chặn nghiệm thu các phần khác. Chưa xây connector công khai.
Chọn/import một file chưa có nghĩa file đã qua cổng duyệt y khoa/video.

### 3.4 Tiêu chuẩn sau nghiệm thu

Giữ nguyên lịch sử góp ý cũ. Góp ý thử nghiệm là nháp; chỉ nút chấp nhận rõ ràng
của bác sĩ trong app mới tạo phiên bản tiêu chuẩn đã nghiệm thu cho giai đoạn.
Ghi nội dung, phạm vi áp dụng, phiên bản và bằng chứng thử; không tự biến mọi
góp ý riêng của gout thành luật toàn kênh. Khi phát hiện góp ý riêng đang được
áp dụng toàn cục, giữ lịch sử và tạo quyết định phạm vi mới, không xóa mục cũ.

Tiêu chuẩn gồm prompt/hướng dẫn cho việc cần phán đoán và QA cho điều kiện đo
được. Tác nhân không tự tuyên bố các yêu cầu chủ quan đã kiểm bằng máy.
Sản phẩm mới ghi phiên bản tiêu chuẩn đã dùng. Sửa chuẩn không tự sửa sản phẩm
cũ; vòng thay đổi nội dung vẫn đi qua cổng hiện có. Chưa làm trình soạn luật.

## 4. Nghiệm thu từng giai đoạn

Trước hết kiểm thử nền vận hành và app: lỗi, cache, tiếp tục, dữ liệu cũ và PIN.
Sau đó lần lượt trình bác sĩ nghiệm thu bốn giai đoạn, không làm cả A–Z rồi
mới hỏi. Giai đoạn sau được phát triển và kiểm thử kỹ thuật, nhưng chưa chốt
chuẩn vận hành của nó trước khi nhận phản hồi của giai đoạn trước.

| Giai đoạn | Bằng chứng cần xem qua app | Điều kiện chấp nhận |
|---|---|---|
| 1. Chủ đề → kịch bản | Thẻ chủ đề, nguồn/claim, lời thoại, storyboard | Đủ dữ liệu, truy nguồn được, góp ý tới đúng chỗ và bản sửa phản ánh góp ý |
| 2. Hình → giọng → nhạc | Preview hình, câu giọng, lựa chọn tài nguyên, trạng thái/cache | Chọn và dùng lại đúng tài nguyên; không gọi lại TTS đã có; nhãn và quyền sử dụng rõ |
| 3. Dựng → QA | Mẫu dài/dọc ngắn, phụ đề, timing, contact sheet và lý do QA | Tiếng/hình khớp, xem/tua được, lỗi chặn rõ, sửa đúng bước |
| 4. Bài đăng → đóng gói | Tiêu đề, mô tả, thumbnail, caption, thư mục xuất | Gói đúng nội dung đã duyệt, không sinh lại sau duyệt, không đăng tự động |

Kiểm thử phần mềm dùng fixture có sẵn hoặc dữ liệu phi y khoa, không bịa nghiên
cứu/nguồn và không phát sinh API trả phí. Nghiệm thu giai đoạn dùng dự án thử
riêng được đánh dấu TEST trong app, không lấy gout hay chủ đề mới vào hàng đợi
thật. Mẫu hình/giọng/clip ngắn là mẫu kiểm công cụ, không phải sản phẩm kênh.
Trước mỗi thử có dịch vụ thật, hiển thị tác vụ và hạn mức yêu cầu; không chạy
hàng loạt. Mức đề xuất: một ảnh Muse và một câu TTS ngắn khi cần kiểm kết nối;
đây là giới hạn của tác nhân đề xuất, không phải hạn mức người dùng đã xác nhận.

Sau khi các giai đoạn được chấp nhận: cho phép chạy sản phẩm A–Z theo chuẩn;
bắt đầu vòng sản phẩm gout sau, bác sĩ xem và yêu cầu sửa qua app. Hai cổng
vẫn bắt buộc; không coi việc nghiệm thu xưởng là approval cho nội dung thật.

## 5. Không làm và dấu hiệu thất bại

Không tự xuất bản; không nhận PIN trong chat/file/env; không commit key,
audio, render, cache hay toàn văn có bản quyền. Không sửa gout để chứng minh
xưởng đã xong. Không làm người dùng phải quay về terminal cho thao tác thường
ngày. Không thay QA bằng chỉ dẫn prompt rồi gọi là đã kiểm. Không mặc định
Muse có API hoặc token đồng nghĩa với quyền tạo ảnh/video không giới hạn.

## 6. Phần để người lập kế hoạch quyết định

Chia task và chọn file/hàm/schema tối thiểu; cách trình bày chức năng trong app;
định dạng lưu phiên bản chuẩn và báo cáo nghiệm thu; cơ chế giới hạn retry;
fixture và kiểm thử tích hợp UI; cách di chuyển bản sửa dở và tài liệu chưa
commit mà không mất dữ liệu. Phải đưa kết quả kiểm chứng Muse vào quyết định
triển khai, chỉ chọn đường tích hợp đã chứng minh. Chưa triển khai sản phẩm mã
trước khi bác sĩ duyệt toàn bộ thiết kế này; sau duyệt mới viết kế hoạch chi tiết.

## 7. Quyết định cập nhật 2026-10-27

- **Mẫu giai đoạn 1 (Chủ đề → kịch bản)** chạy agent thật (`research` → `draft`) theo chủ đề bác sĩ nhập ngay bên trong thư mục trial cô lập (`cache/factory-test/<trial_id>/project/`), chỉ để nghiệm thu chuẩn giai đoạn 1, không thêm vào `topics/`, không tạo approval, không chạy produce/render và không xuất bản.
- **Giai đoạn 2–4** giữ nguyên mẫu ngoại tuyến cố định để kiểm khung.
