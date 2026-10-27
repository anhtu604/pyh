# Kết quả kiểm chứng tích hợp Muse AI

- `status`: `needs_login`
- Ngày ghi nhận: `2026-10-27`
- URL tham chiếu: `https://muse.ai/` (chưa kiểm phiên đăng nhập thực tế của người dùng trong môi trường ngoại tuyến)

## 1. Phạm vi và nguyên tắc

- Theo ràng buộc vận hành, tác nhân **không tự đăng nhập**, không nhận mật khẩu/cookie/token và không kết nối mạng trong lượt tích hợp ngoại tuyến.
- Vì chưa có phiên trình duyệt đã đăng nhập sẵn để xác minh công cụ tạo ảnh, cách xuất file và điều khoản thương mại trực tiếp trên tài khoản người dùng, trạng thái được ghi nhận là `needs_login`.

## 2. Giới hạn đã biết và chưa biết

- **Đã biết**:
  - Spec hiện hành loại bỏ AI video clip; mọi hình giải phẫu/cơ chế có nhãn và số liệu vẫn do component SVG + Remotion đảm nhiệm.
  - Ảnh minh họa nhập từ bên ngoài chỉ được dùng cho vai trò nền không nhãn (`kind=background`, `semantic=false`, `storyboard_role=whiteboard`) kèm SHA-256, nguồn, prompt và giấy phép trong `LicenseLedger` + contact sheet.
- **Chưa biết (cần phiên đăng nhập của người dùng để xác nhận)**:
  - Tên model/công cụ tạo ảnh cụ thể trong gói tài khoản Muse của người dùng và hạn mức thực tế.
  - Điều khoản cấp phép thương mại chi tiết của tệp xuất từ tài khoản đó.

## 3. Đường tích hợp đã chọn

- Không xây dựng connector/API tự động tới Muse khi chưa chứng minh khả năng.
- Dùng đường **FLUX.2 [klein] 4B sẵn có + nhập file raster qua tab Thư viện của `healthvideo app`** (`/api/library/select` + `/api/library/import` + `/api/library/bind`), bảo toàn đầy đủ provenance (`origin`, `prompt`, `license`, `source_url`, `sha256`) và kiểm tra cổng duyệt y khoa/video.
