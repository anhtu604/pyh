# Hướng dẫn nghiệm thu xưởng theo giai đoạn trong app

Tài liệu này tóm tắt cách bác sĩ nghiệm thu 4 giai đoạn của xưởng và vận hành hằng ngày ngay trong `healthvideo app` (lối tắt Desktop **Xưởng video**), không cần dùng PowerShell.

## 1. Nghiệm thu 4 giai đoạn (1 → 4)

1. Mở **Xưởng video** trên Desktop (hoặc chạy `.venv\Scripts\healthvideo.exe app`).
2. Tại khung **Nghiệm thu xưởng (TEST · ngoại tuyến)** ở đầu trang:
   - Chọn giai đoạn **1 · Chủ đề → kịch bản**, bấm **Tạo mẫu TEST**, sau đó bấm **Chạy mẫu ngoại tuyến · 0 yêu cầu trả phí**.
   - Xem kịch bản mẫu từng dòng và tệp bằng chứng ngay trên trang.
   - Nhập nội dung quy định/góp ý vào ô **Góp ý / chuẩn nháp cho mẫu này**, bấm **Lưu nháp góp ý**.
   - Nhập **PIN bác sĩ** và bấm **Chấp nhận chuẩn v1**.
3. Lặp lại theo đúng thứ tự cho giai đoạn **2 · Hình → giọng**, **3 · Dựng → QA**, **4 · Bài đăng → đóng gói**.
4. Mọi thao tác trong khu `TEST` chỉ ghi vào `cache/factory-test/` và `profiles/factory-standards.yaml`, không chạy hàng đợi thật và không tốn credit dịch vụ trả phí.
5. Khi cả 4 giai đoạn đều có chuẩn đã chấp nhận, nút **Bật xưởng** trên thanh đầu trang mới được mở khóa; các dự án sản xuất mới sẽ tự đóng băng bản chụp chuẩn tại `revisions/<rev>/workflow/standards.yaml`.

## 2. Quản lý hàng đợi, khôi phục lỗi và thư viện ảnh

- **Tab Hàng đợi**:
  - **Thêm chủ đề**: nhập tên, mã chủ đề (`slug`), câu hỏi và ghi chú bác sĩ để thêm vào `topics/queue.yaml`.
  - **Xử lý dự án**: chọn dự án để xem revision, bước kế tiếp, số dòng kịch bản, số file cache TTS hiện có và trạng thái khóa retry (`reason` hoặc `retry_after` khi đang chờ backoff).
  - **Cho phép thử lại**: xóa khóa giữ sau khi đã sửa đầu vào hợp lệ (không tự bật worker thứ hai).
  - **Mở lại cổng y khoa**: yêu cầu tích xác nhận, nhập tên bác sĩ, lý do, danh sách tệp cần sửa và **PIN bác sĩ**; bản duyệt cũ được lưu thành `*-superseded-approval.yaml`.
- **Tab Thư viện**:
  - Lọc/tìm kiếm tài nguyên theo dự án, loại (`imported`, `flux`, `svg`, `contact_sheet`, `thumbnail`) hoặc từ khóa prompt.
  - **Nhập ảnh có nguồn**: bấm **Chọn file trên máy**, điền nguồn (vd. `Muse AI`), prompt, giấy phép, URL điều khoản rồi nhập vào thư viện và gắn vào cảnh `whiteboard` (chỉ khi dự án chưa khóa bởi duyệt y khoa hoặc đã mở lại cổng).

## 3. Giới hạn đã biết

- Kiểm chứng trực tiếp tài khoản Muse AI đang ở trạng thái `needs_login` (`docs/reference/muse-integration-findings.md`); trước mắt dùng FLUX local và nhập file raster thủ công qua tab **Thư viện**.
- Dự án cũ (như `gout-tinh-the-urat`) tạo trước khi có snapshot chuẩn vẫn đọc và xem bình thường; chỉ dự án tạo mới sau khi đủ 4 chuẩn mới gắn cứng `workflow/standards.yaml`.
