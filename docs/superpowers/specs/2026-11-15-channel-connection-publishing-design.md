# Kết nối kênh và đăng nội dung đã duyệt

Ngày: 2026-11-15. Bổ sung Company 2.0 theo yêu cầu trực tiếp của bác sĩ:
kiểm tiến độ, kết nối **YouTube và TikTok**, cho agent đăng bài trên kênh.
Bác sĩ chưa có ứng dụng OAuth, cần hướng dẫn thiết lập.

## Quyết định và phạm vi

- Yêu cầu mới thay giới hạn “không tự xuất bản” của thiết kế cũ, chỉ với nội dung
  đã qua **cả hai cổng**, còn hiệu lực, đúng revision và đúng byte được duyệt.
  Không cấp cho agent quyền duyệt, nhận PIN hay sửa approval.
- Không khôi phục pilot, không bật xưởng, không tự tạo nội dung để thử đăng.
- Kết nối tài khoản là OAuth có danh tính kênh được API xác nhận, hoặc phiên
  trình duyệt TikTok đã đăng nhập và kiểm upload-auth thật cùng UID từ cookie
  của lần đăng nhập đó. Hiển thị rõ phương thức và nguồn danh tính, không biến
  alias người dùng tự đặt thành handle đã xác minh. Sheet/CSV/form là dữ liệu
  nhập, không chứng minh tài khoản đã kết nối.
- Researcher chỉ nhận việc phân tích khi có quan sát chỉ số thật. Link/tiêu đề
  đơn thuần không phải quan sát; số 0 được ghi nhận thật vẫn là dữ liệu hợp lệ.
  Thiếu CTR/retention thì để trống và nêu giới hạn; không suy diễn thành 0.
- Báo cáo thiếu/rỗng/sai schema không được coi là phân tích xong. Không tự điền
  điểm đề tài khi agent chưa chấm.

## Kết nối

- Ứng dụng desktop OAuth, callback loopback của dashboard cho từng nền tảng.
- State ngẫu nhiên, một lần, có thời hạn; PKCE theo đúng quy tắc mỗi nền tảng.
- Client secret, access/refresh token, state và verifier lưu ngoài repository,
  theo namespace checkout; Windows dùng DPAPI. Không đưa vào chat, log, prompt,
  localStorage hay API status. Đổi tài khoản phải hiện rõ danh tính mới.
- Google: đọc danh sách video/số liệu và upload với quyền cần thiết. TikTok:
  Login Kit desktop, Display API `video.list`, Content Posting `video.publish`.
- Đồng bộ dùng phân trang có giới hạn và timeout; không gọi mạng khi chỉ xem
  overview. Thiếu quyền/token hết hạn phải hiện đúng trạng thái, không giả kết nối.

## Đăng và đối soát

- Chỉ nhận slug/clip đã đóng gói, không nhận đường dẫn file tùy ý.
- Kiểm lại approval hiện hành, manifest gói, hash video/clip và bài đăng trước
  khi gọi API. Chỉ chọn tiêu đề/caption đã duyệt; quyền hiển thị chọn rõ ràng.
- Xem trước có kênh đích, nội dung và quyền hiển thị. TikTok lấy creator info mới
  nhất và yêu cầu đồng ý dùng nhạc cho từng lượt đăng.
- Khóa lượt đăng và lưu ý định trước thao tác mạng. Khóa chống trùng gắn tài khoản,
  revision, nền tảng và hash nội dung. Mất phản hồi không tự đăng lại.
- YouTube thành công khi API trả video ID. TikTok nhận file/publish ID mới là
  đang xử lý; chỉ báo hoàn tất khi API trạng thái xác nhận.
- Không sửa workflow state hoặc approval chỉ vì API đã nhận file.

## Giới hạn nền tảng đã xác minh

TikTok giới hạn ứng dụng chưa audit ở `SELF_ONLY`; hướng dẫn Direct Post còn
không chấp nhận tiện ích chỉ dành cho các tài khoản nội bộ của chính đội dùng.
Do đó không coi đăng công khai TikTok là đã sẵn sàng khi mới có adapter hoặc
sandbox. Không tìm cách vượt duyệt ứng dụng. YouTube và TikTok đều cần bác sĩ
đăng nhập, chọn đúng kênh và cấp quyền thật trước khi có thể chạy trực tiếp.

Nguồn chính thức:

- [YouTube authorization](https://developers.google.com/youtube/data/guides/authentication)
- [YouTube upload](https://developers.google.com/youtube/data/guides/uploading_a_video)
- [TikTok Desktop Login](https://developers.tiktok.com/docs/en/login-kit-desktop)
- [TikTok Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post)
- [TikTok content sharing guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)

## Nghiệm thu

Test offline chặn phân tích khi chưa có quan sát, phân biệt nhập dữ liệu/OAuth,
state replay/expiry, thiếu quyền/refresh, thiếu hoặc cũ hai approval, hash thay đổi,
traversal, trùng/đăng không rõ kết quả, TikTok pending. Test không gọi mạng thật.
Đăng thật chưa được nghiệm thu khi chưa có OAuth và sản phẩm mới đã duyệt.

File được giao: channel_connections.py + test, channel_analytics.py/chat.py/
coordinator.md + test, channel_publishing.py/dashboard_operations.py + test,
dashboard.html + tests/ui/test_channel_setup.py. Dev lead cập nhật spec này,
hướng dẫn setup, AGENTS.md/CLAUDE.md, skill pyh/coordinator/researcher và progress.

## Bổ sung hoàn thiện sau khi bác sĩ chưa tạo được TikTok Developer app

- YouTube đã OAuth thật và sync thành công. Kênh chưa sản xuất video nên số
  video bằng 0 là bình thường, không phải lỗi kết nối hoặc điều kiện dừng xưởng.
- Đăng nhập TikTok local bằng Autotok tại commit đã review. Cài môi trường riêng
  bên ngoài Git; chỉ trình duyệt Chrome local, không proxy/cloud hoặc AccountStore
  JSON mặc định. Bác sĩ bấm đăng nhập rồi tự nhập thông tin/quét QR trong trình duyệt.
- Phiên/UA lưu DPAPI, truyền cho helper qua stdin. Không API nào nhận cookie từ
  chat/browser form, không ghi raw stderr/exception có token. Process có deadline,
  dọn cây con đã xác minh danh tính. Không thay OAuth đang dùng nếu login mới hỏng.
- Browser mode có quyền gửi bài, không có analytics. Researcher chỉ dùng dữ liệu
  nhập hoặc API được cấp quyền; không suy diễn số liệu từ login hoặc video ID lưu trữ.
- Public/private được chọn rõ theo phương thức. Giới hạn audit SELF_ONLY áp dụng
  Direct Post OAuth; không dùng nó để mô tả sai đường API web của Autotok.
- Upstream status_code=0/video_id lưu trữ là `pending_verification`. Không tự nâng
  lên posted hoặc đăng lại; phải xác minh bài thật độc lập. Hai cổng/hash/đúng kênh
  và snapshot bất biến vẫn áp dụng khi gọi backend trình duyệt.
- YouTube gửi thumbnail có hash được cổng video duyệt. Lưu video ID trước lượt
  gửi ảnh; ảnh hỏng thì hiện riêng lỗi thumbnail, không đăng lại video.
