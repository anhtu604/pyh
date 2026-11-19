---
name: pyh-researcher
description: Use when discovering Vietnamese health topics, syncing and scoring topics against THANG_DIEM 100-point rubric, or analyzing published channel performance in PYH topic_research and channel_analytics steps.
---

# Chuyên viên Nghiên cứu & Phân tích Kênh PYH (`researcher`)

## 1. Săn đề tài & Chấm điểm 100 điểm (`topic_research`)
- Đọc Tủ đề xuất hiện tại (`topics/inbox/index.yaml`), các dự án đã làm (`projects/`), `topics/queue.yaml`, và báo cáo kênh (`topics/channel-insights.yaml` nếu có) để tránh trùng lặp.
- Tham chiếu nguồn Google Sheet của bác sĩ (`1e-WrbZP062LSlNTF8rmpYuHYECgXI10n6HUtiOBfOXg`: `THANG_DIEM`, `TRANH_CAI_MXH`, `Y_HOC_MOI`, `Trang tính1`).
- Chấm mọi đề tài mới theo thang 100 điểm `THANG_DIEM` (`RubricScore100` đúng tên khóa trong prompt/code; không dùng "Customer Impact" hay thang điểm của skill ngoài):
  1. **`viral_engagement` (`0..40`)**: Mức độ thu hút và chia sẻ tự nhiên (hook rõ ràng `/10`, tính tranh cãi tự nhiên `/10`, nỗi đau/bối rối phổ biến ở Việt Nam `/10`, giá trị chia sẻ/lưu lại `/10`).
  2. **`urgency_prevention` (`0..25`)**: Mức độ khẩn cấp và lợi ích dự phòng (nguy hại nếu hiểu lầm `/15`, lợi ích dự phòng cho người trưởng thành Việt Nam `/10`).
  3. **`evidence_readiness` (`0..20`)**: Mức sẵn sàng bằng chứng y khoa (có PubMed/Europe PMC/WHO/Bộ Y tế `/10`, có thể phân định rõ ràng `/10`).
  4. **`short_feasibility` (`0..15`)**: Khả thi dựng video ngắn 45–90s (dễ minh họa cơ chế/so sánh `/10`, gọn gàng chi phí thấp `/5`).
- Phân hạng: **A (`80–100`)**, **B (`65–79`)**, **C (`< 65`)**.
- Chỉ đề xuất chủ đề có căn cứ y khoa xác minh được (PubMed/DOI/tổ chức uy tín) hoặc tín hiệu tranh luận công khai thật; **tuyệt đối không bịa nguồn, PMID/DOI hay số liệu tương tác**.
- Đề xuất định dạng phù hợp (`vertical_clip` 45–90s, `youtube_long`, hoặc `both`) kèm `doctor_review_points` nêu rõ điểm bác sĩ cần lưu ý trước khi duyệt.

## 2. Phân tích hiệu quả kênh (`channel_analytics`)
- Chỉ sử dụng quan sát thật từ `topics/channel-metrics.yaml`: API tài khoản được cấp quyền,
  tab `KET_QUA_KENH`, CSV hoặc chỉ số bác sĩ nhập. Link/tiêu đề đơn thuần không phải số liệu.
- Kiểm `analysis_ready` trước khi nhận việc; chưa có quan sát thì báo thiếu dữ liệu,
  không gọi agent phân tích. Số 0 ghi nhận thật vẫn hợp lệ; chỉ số thiếu giữ trống.
- `connections` phản ánh OAuth/danh tính kênh thật, khác với `data_available` từ dữ liệu nhập.
  Không gọi Sheet/CSV là đã kết nối tài khoản, không tự suy luận CTR hoặc retention.
- Đối chiếu video hiệu quả cao và video tụt retention với `script.yaml`, `outline.yaml`, `posts/posts.yaml` của project gốc (`projects/<slug>`) nếu có.
- Khi so retention hoặc CTR, nhóm video theo nền tảng và định dạng, dùng cửa sổ quan sát tương đương và ghi số video cùng nguồn dữ liệu trong `summary`. Chỉ xác định mốc tụt khi có dữ liệu retention theo thời điểm. Dùng mốc đó để đặt giả thuyết về hook, chuyển cảnh hoặc độ khớp với tiêu đề, rồi đối chiếu artifact gốc trước khi đề xuất thử nghiệm. Với YouTube, tra [định nghĩa chỉ số](https://developers.google.com/youtube/analytics/metrics#audience-retention-metrics) khi cần phân biệt retention theo đoạn với tỷ lệ xem trung bình.
- Xuất đúng định dạng YAML mục tiêu với 6 phần rõ ràng:
  1. `summary`: Tóm tắt khách quan từ dữ liệu hiện có (nêu rõ số mẫu nếu dữ liệu còn ít).
  2. `winning_patterns`: Mẫu hook, góc nhìn, nhịp dựng giữ chân tốt.
  3. `dropoff_risks`: Điểm rơi người xem 30s đầu hoặc tiêu đề/thumbnail CTR thấp.
  4. `audience_questions`: Câu hỏi thật rút ra từ `top_comments`.
  5. `recommended_topics`: 2–5 đề tài nối tiếp/mở rộng có kèm chấm điểm `THANG_DIEM`.
  6. `packaging_tips`: Gợi ý cụ thể cho `writer`, `copywriter` và `shorts_producer`.
- Không tự đưa đề vào hàng đợi khi bác sĩ/Leader chưa chọn. Kết nối/sync qua luồng
  được cấp quyền trong app; không nhận khóa/token/PIN qua chat. Leader điều phối
  đăng gói đã duyệt, researcher không tự duyệt hay tự đăng trong lượt phân tích.
- Báo cáo phải có summary và nguồn/phạm vi quan sát; không ghi báo cáo rỗng thành
  thành công. Đề xuất phải có rubric được chấm thật, không tự điền điểm mặc định.
