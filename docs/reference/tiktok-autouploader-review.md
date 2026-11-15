# Đánh giá TiktokAutoUploader cho xưởng

2026-11-15. Repo bác sĩ gửi:
https://github.com/makiisthenes/TiktokAutoUploader

Đọc source tại commit `0bcbbdcff3600fbc09a47b9be107d1d3fd49b260`, package
`autotok` 2.1.0. Chỉ clone vào cache để review; chưa cài/chạy code, đăng nhập hoặc đăng bài.

## Phù hợp phần nào

Đây là backend upload qua phiên đăng nhập và API web TikTok. Không cần ứng dụng
Direct Post OAuth cho lượt đăng của backend này; các hạn chế audit Direct Post
đã nêu áp dụng đường API chính thức, không phải mô tả cơ chế của Autotok.
README hiện tại có Python SDK/CLI/MCP. Chỉ tích hợp phía sau lớp kiểm cổng/hash
và chống trùng của xưởng; không đưa công cụ upload MCP trực tiếp cho agent.

## Chưa thể coi là thay thế kết nối kênh

- Alias do người dùng tự đặt; đăng nhập chờ cookie, `check_session()` chỉ kiểm
  upload auth. Không có API trả danh tính tài khoản thật hay analytics trong
  phần source được xem. Không gắn nhãn “kênh đã kết nối/phân tích được” chỉ từ alias.
- `AccountStore` mặc định ghi cookie và proxy vào JSON; `chmod(0600)` không
  thay thế DPAPI trên Windows. Khi tích hợp cần store mã hóa ngoài Git.
- UploadResult.video_id lấy từ bộ lưu trữ; publish chỉ kiểm `status_code == 0`.
  Phải gọi trạng thái đó là đã tiếp nhận/chờ xác minh, chưa khẳng định bài đã lên kênh.
- Có PublishUncertainError hữu ích nhưng lỗi HTTP sau bước gửi đăng cũng cần
  đối soát. Không tự retry upload khi không biết kết quả.
- Lỗi mạng có thể chứa URL với msToken/signature. Adapter phải thay bằng lỗi
  đã làm sạch; không ghi raw stdout/exception ra dashboard hoặc log agent.
- CLI mặc định public và bật bình luận; không dùng mặc định cho gói bác sĩ duyệt.
- Browserbase/Steel/proxy là tùy chọn; lượt đầu chỉ dùng trình duyệt local.

## Điều kiện tích hợp

Pin dependency, tách môi trường, store DPAPI, xác minh tài khoản độc lập,
chuyển đúng byte/caption đã duyệt, visibility rõ ràng, lưu ý định trước gửi,
không retry mù và xác nhận bài thật. Chưa có đăng nhập TikTok hoặc clip mới
đã duyệt để kiểm thử thực tế. Chưa coi thư viện này được nghiệm thu trong xưởng.

Source tham chiếu tại commit trên: `autotok/accounts.py` (lưu phiên),
`auth.py` (login), `uploader.py` (check_session, _transfer, _publish),
`web/scheduler/worker.py` (tránh retry khi không rõ kết quả), `pyproject.toml`
(dependencies, AGPL-3.0-only). Không sao chép source vào xưởng.
