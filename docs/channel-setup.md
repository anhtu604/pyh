# Kết nối YouTube và TikTok

Xưởng dùng quyền OAuth của chủ kênh để đồng bộ số liệu qua API. YouTube dùng
OAuth để gửi video. TikTok có thêm cách gửi video bằng phiên trình duyệt.
Chỉ nhập khóa trong mục **Kết quả kênh** của app.

## YouTube — thiết lập trước

1. Mở [Google Cloud Console](https://console.cloud.google.com/), tạo project cho
   xưởng. Bật **YouTube Data API v3** và **YouTube Analytics API** trong API Library.
2. Trong Google Auth Platform, cấu hình tên ứng dụng và email hỗ trợ. Nếu dùng
   chế độ Testing, thêm email Google quản lý kênh vào danh sách Test users.
3. Tạo OAuth client loại **Desktop app**, tải JSON cấu hình client.
4. Mở app xưởng → **Kết quả kênh → YouTube → Thiết lập**, nhập JSON vừa tải, lưu.
5. Bấm **Kết nối**, đăng nhập Google, chọn đúng kênh và cấp các quyền đọc/upload.
   Sau khi trình duyệt chuyển về callback, quay lại xưởng kiểm tra tên kênh.
6. Bấm **Đồng bộ từ kênh**. Chưa có video thì vẫn kết nối được, nhưng Researcher
   chưa có dữ liệu để phân tích. Chỉ số API không cung cấp sẽ hiện trống.

Đường callback khi app dùng cổng mặc định:
`http://127.0.0.1:8765/api/channel/oauth/youtube/callback`.
Client desktop hỗ trợ loopback; không chọn nhầm client loại web.

Quyền được xin: `youtube.readonly`, `youtube.upload`, `yt-analytics.readonly`.
Việc bật API và cấp quyền đọc riêng không mặc nhiên cấp quyền đăng.
Token có thể hết hạn/bị thu hồi; khi app yêu cầu, kết nối lại đúng tài khoản.

[Hướng dẫn OAuth chính thức](https://developers.google.com/youtube/data/guides/authentication),
[hướng dẫn client desktop và upload](https://developers.google.com/youtube/data/guides/uploading_a_video).

## TikTok qua trình duyệt

1. Mở **Kết quả kênh → TikTok**. Nếu thấy **Cài công cụ đăng nhập**, bấm cài một lần.
2. Bấm **Đăng nhập TikTok bằng trình duyệt**. Kiểm tra đúng tài khoản trong cửa
   sổ Chrome vừa mở, hoàn tất đăng nhập rồi quay lại xưởng.
3. Khi gửi clip đã duyệt, chọn quyền hiển thị và kiểm tra kết quả trên TikTok.
   Trạng thái chờ xác minh nghĩa là xưởng chưa có xác nhận bài đã xuất hiện.

Đường này dùng Autotok và không cần app Developer. Phiên trình duyệt chỉ hỗ trợ
gửi clip. Để đồng bộ số liệu tự động, dùng OAuth.

## TikTok qua API chính thức

1. Đăng nhập [TikTok for Developers](https://developers.tiktok.com/), tạo app.
   Chọn nền tảng **Desktop**, thêm **Login Kit**, **Display API** và **Content Posting API**.
2. Đăng ký redirect URI chính xác:
   `http://127.0.0.1:8765/api/channel/oauth/tiktok/callback`.
   Nếu đổi cổng app xưởng, sửa redirect trong cấu hình TikTok tương ứng.
3. Xin quyền `user.info.basic`, `video.list`, `video.publish`; bật Direct Post.
   Nhập Client key và Client secret vào thẻ thiết lập TikTok trong xưởng.
4. Bấm **Kết nối**, đăng nhập tài khoản TikTok cần dùng và cấp quyền.
   Kiểm tra tên tài khoản sau callback, rồi đồng bộ video.

**Giới hạn thực tế:** ứng dụng chưa audit chỉ đăng riêng tư (`SELF_ONLY`). TikTok
không chấp nhận tiện ích chỉ dùng để đăng lên tài khoản của chính cá nhân/đội
nội bộ trong tiêu chí duyệt Direct Post. Vì thế tạo app/sandbox chưa bảo đảm được
đăng công khai cho xưởng này; cần phương án ứng dụng được TikTok chấp thuận.
Nếu không đủ điều kiện, dùng gói xuất đã duyệt để đăng qua TikTok Studio.

[Desktop Login Kit](https://developers.tiktok.com/docs/en/login-kit-desktop),
[Direct Post prerequisites](https://developers.tiktok.com/docs/en/content-posting-api-get-started),
[điều kiện sử dụng và audit](https://developers.tiktok.com/docs/en/content-sharing-guidelines).

## Quy trình đăng

Sau khi nội dung mới qua cả cổng y khoa và cổng video, xưởng đóng gói. Chọn
project/clip đã duyệt, xem đúng kênh đích và nội dung, chọn quyền hiển thị rồi
gửi đăng. TikTok cần xác nhận sử dụng nhạc cho từng bài. Trạng thái “đang xử lý”
khác với “đã đăng”; lỗi mạng chưa rõ kết quả phải đối soát trước khi gửi lại.

Các pilot cũ đang được lưu trữ; không có nội dung đang chờ đăng. Đợt kết nối này
không tự khôi phục pilot hay tự tạo approval.
