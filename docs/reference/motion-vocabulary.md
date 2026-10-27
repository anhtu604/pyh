# Từ vựng chuyển động y khoa (`video-shotcraft`)

Tài liệu này định nghĩa 14 mẫu chuyển động Remotion trong `video/src/motion/` để tạo nhịp hình nhanh, có nhãn rõ ràng ("labeled fast-paced visuals") cho video giải thích y khoa mà không làm rối thông tin lâm sàng.

## 1. Bảng 14 thẻ chuyển động (Dùng khi / Không dùng khi / Thời lượng)

### Nhấn mạnh thuật ngữ (`typography`)
- `marker-underline-title`: **Dùng khi** cần gạch dạ quang dưới đúng 1 cụm từ khóa y khoa trọng tâm trong câu mở đầu hoặc kết luận đoạn / **Không dùng khi** câu có nhiều hơn 1 thuật ngữ mới hoặc đang chiếu bảng số liệu dày / **Thời lượng**: 90 frame (3,0 giây @ 30fps).
- `lead-word-zoom-assemble`: **Dùng khi** giới thiệu thuật ngữ bệnh học cốt lõi (từ đầu phóng to `2.3x` rồi lùi về ghép cả cụm + định nghĩa ngắn) / **Không dùng khi** cụm thuật ngữ quá 6 từ hoặc cảnh dưới 2,5 giây / **Thời lượng**: 84 frame (2,8 giây @ 30fps).
- `outline-word-fill`: **Dùng khi** đóng đinh một khái niệm cơ chế (chữ viền rỗng bơm màu đặc từ dưới lên kèm thẻ giải thích ngắn) / **Không dùng khi** nền cảnh bên dưới đã có sơ đồ giải phẫu nhiều chi tiết / **Thời lượng**: 120 frame (4,0 giây @ 30fps).
- `title-demote-to-label`: **Dùng khi** mở đầu phần/chương bằng tiêu đề lớn rồi thu nhỏ (`scale 0.42`) lên góc trên làm nhãn giữ ngữ cảnh cho sơ đồ bên dưới / **Không dùng khi** cảnh chỉ kéo dài dưới 3 giây hoặc không có nội dung chính xuất hiện sau pha thu nhỏ / **Thời lượng**: 132 frame (4,4 giây @ 30fps).

### Số liệu lâm sàng (`data` — dùng qua visual `stat_gauge`)
- `chart-live-moves`: **Dùng khi** trình bày đường biểu diễn nồng độ/nguy cơ có nhịp thở nhẹ và con số đếm nhảy theo thời gian thực / **Không dùng khi** chỉ nêu định tính không có số liệu thuộc `claim_id` trong ledger / **Thời lượng**: 138 frame (4,6 giây @ 30fps).
- `gauge-readout-moves`: **Dùng khi** nhấn mạnh một ngưỡng sinh lý hoặc xét nghiệm đơn lẻ (vd: `6,8 mg/dL` ngưỡng bão hòa urat) trên vòng cung đo / **Không dùng khi** cần so sánh nhiều nhóm nghiên cứu cùng lúc / **Thời lượng**: 138 frame (4,6 giây @ 30fps).
- `timeline-travel`: **Dùng khi** mô tả diễn tiến bệnh học theo mốc giờ/ngày/giai đoạn có camera lướt ngang qua các trạm / **Không dùng khi** các ý không có trật tự thời gian hoặc tiến triển nhân quả / **Thời lượng**: 144 frame (4,8 giây @ 30fps).
- `before-after-slider-scrub`: **Dùng khi** đặt 2 trạng thái trước–sau có đủ hai bộ nhãn/chỉ số truyền tường minh cho component `BeforeAfterSliderScrub` (không dùng làm `StatGauge.variant` vì `stat_gauge` chỉ giữ một `value` đơn) / **Không dùng khi** hai vế không cùng đơn vị đo hoặc chưa có bằng chứng đối chiếu / **Thời lượng**: 132 frame (4,4 giây @ 30fps).

### Soi bằng chứng (`effects`)
- `scan-bracket-sweep`: **Dùng khi** khóa khung `[ ]` 4 góc vào đúng vùng trích dẫn hoặc kết luận nghiên cứu để dẫn mắt bác sĩ và người xem / **Không dùng khi** cảnh không có câu khẳng định hay vùng thông tin cụ thể cần khoanh / **Thời lượng**: 138 frame (4,6 giây @ 30fps).
- `scanline-annotate-focus`: **Dùng khi** tia quét dọc đi qua điểm mấu chốt và bật nhãn chú thích y khoa ngắn gọn ngay tại mốc giao cắt / **Không dùng khi** đã có nhiều hơn 3 nhãn giải phẫu đang mở trên màn hình / **Thời lượng**: 126 frame (4,2 giây @ 30fps).
- `spotlight-sweep-moves`: **Dùng khi** cần làm dịu vùng ngoại vi và gom sáng vào đúng 1 tổn thương hoặc thông điệp cảnh báo an toàn / **Không dùng khi** người xem cần quan sát toàn bộ sơ đồ so sánh hai bên cùng lúc / **Thời lượng**: 138 frame (4,6 giây @ 30fps).

### Chuyển cảnh & Nhịp máy quay (`transition` / `camera`)
- `circle-match-iris`: **Dùng khi** chuyển từ góc nhìn tổng quan cơ quan sang cận cảnh mô/tế bào qua vòng iris đồng tâm / **Không dùng khi** hai cảnh liên tiếp vẫn cùng một tầng giải thích và cùng góc máy / **Thời lượng**: 126 frame (4,2 giây @ 30fps; pha iris đầu cảnh ~34 frame).
- `wipe-transitions`: **Dùng khi** sang chương mới hoặc chuyển từ cơ chế bệnh sinh sang hướng dẫn xử trí dự phòng / **Không dùng khi** đang ở giữa một chuỗi giải thích cơ chế liên tục / **Thời lượng**: 132 frame (4,4 giây @ 30fps).
- `crash-zoom-punch`: **Dùng khi** tạo cú nhấn thị giác nhanh vào con số hoặc điểm bùng phát viêm quan trọng ở đầu cảnh mới / **Không dùng khi** dùng lặp lại liên tiếp gây mỏi mắt hoặc dùng cho cảnh kết luận nhẹ nhàng / **Thời lượng**: 126 frame (4,2 giây @ 30fps).

---

## 2. Cách khai báo trong `storyboard.yaml`

1. **Overlay lên bất kỳ cảnh nào qua trường tùy chọn `motion`** (cảnh không khai báo giữ nguyên hành vi cũ):
   ```yaml
   motion:
     emphasis: marker-underline-title   # 1 trong 7 thẻ typography/effects
     emphasis_text: "tăng acid uric máu" # BẮT BUỘC là cụm từ có mặt trong narration của cảnh
     transition_in: circle-match-iris   # tùy chọn: circle-match-iris | wipe-transitions | crash-zoom-punch
   ```
2. **Hai loại `visual` độc lập mới**:
   - `visual: stat_gauge`: bắt buộc có `claim_id` hợp lệ trong `evidence/ledger.yaml` và trường `stat_gauge: {value, unit, label, max_value?, variant?}` (`variant`: `gauge-readout-moves` | `chart-live-moves` | `timeline-travel`). Xếp vào nhóm ngân sách `chart_crop`.
   - `visual: kinetic_term`: định nghĩa nhanh thuật ngữ qua `kinetic_term: {term, definition, variant?}` (`variant`: `lead-word-zoom-assemble` | `outline-word-fill` | `marker-underline-title` | `title-demote-to-label`). Xếp vào nhóm ngân sách `whiteboard_svg`.

---

## 3. 10 quy tắc thẩm mỹ cho video giải thích y khoa (chắt lọc từ `aesthetic-rules.md`)

1. **Mỗi cảnh chỉ nhấn mạnh 1 cụm thuật ngữ**: `motion.emphasis_text` chỉ khoanh đúng 1 khái niệm trọng tâm khớp lời đọc; gạch chân cả câu tương đương với không nhấn mạnh gì.
2. **Không chồng 2 hiệu ứng nhấn mạnh trên cùng một cảnh**: mỗi cảnh tối đa 1 `motion.emphasis`; không vừa quét tia sáng vừa phóng chữ rỗng trên cùng một khung.
3. **Giới hạn chuyển cảnh mạnh tối đa 2–3 lần/phút**: chỉ gắn `transition_in` (`circle-match-iris`, `wipe-transitions`, `crash-zoom-punch`) ở ranh giới chuyển tầng giải phẫu hoặc chuyển chương; phần lớn cảnh dùng cắt thẳng (hard cut) gọn.
4. **Chữ chính xuất hiện trong ≤ 10 frame đầu**: khi cảnh mở ra, tiêu đề hoặc chỉ số phải đọc được ngay trong 6–10 frame đầu, tránh màn hình trống chờ lời đọc.
5. **Mọi đường cong chuyển động phải có giảm tốc (easing/spring)**: cấm nội suy tuyến tính (`linear`) cho vị trí và tỉ lệ phóng; dùng giảm tốc mượt hoặc lò xo tắt dần không nảy quá đà (`no bounce` khi kết thúc).
6. **Sau khi vào chỗ vẫn duy trì chuyển động vi mô (micro-motion)**: biểu đồ, kim đo, hoặc khung ngắm sau pha vào phải có nhịp thở rất nhẹ (`1.0 -> 1.006`) hoặc con số đếm mượt để khung hình không bị "đông cứng như ảnh chụp".
7. **Tối đa 3 cấp cỡ chữ trên một khung hình**: nhãn phụ/đơn vị, nội dung giải thích, và chỉ số/thuật ngữ chính phải phân tầng rõ (chênh nhau ít nhất `1.4x`), dùng thống nhất font `Be Vietnam Pro` hiển thị đầy đủ dấu tiếng Việt.
8. **Số liệu trên `stat_gauge` luôn gắn liền nguồn bằng chứng**: mọi con số lâm sàng hiển thị lớn phải đi kèm `claim_id` có thật trong ledger và hiển thị `source_marker` rõ ràng.
9. **Tương phản màu trung thành với bảng màu y khoa của xưởng**: chỉ dùng nền kem ấm (`#F7F4EC` / `#FFFDF7`), chữ xanh đậm/than (`#12304A` / `#202124`), điểm nhấn xanh cổ vịt (`#18A6A6`), vàng hổ phách (`#F4B942`) và đỏ san hô (`#D8574B`) cho cảnh báo viêm/nguy cơ.
10. **Giữ vùng an toàn cho phụ đề giọng đọc**: mọi nhãn chuyển động và hộp chú thích phải nằm gọn phía trên vùng phụ đề (`Captions`), không che khuất chữ đang đọc hoặc hình giải phẫu chính.

---

## 4. Ghi công bản quyền (Attribution)

Các thành phần trong `video/src/motion/` được chuyển thể (port) và viết lại theo phong cách y khoa từ dự án **video-shotcraft** của **Wei Yihao** (`Copyright 2026 Wei Yihao`), phát hành theo giấy phép **Apache License 2.0** (xem thêm tệp `NOTICE` ở thư mục gốc của kho mã).
