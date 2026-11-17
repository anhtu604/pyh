# Chuẩn phong cách PYH — Hướng A "Mascot dẫn chuyện"

Bác sĩ chọn ngày 2026-11-17. Bắt buộc cho trạm 09–15; storyboard (trạm trước cổng 08) phải
viết theo đúng ngữ pháp này để trạm 09–15 không phải đoán.

Nguồn tham khảo (chỉ lấy quy tắc, không chép tài sản):

- Nhân vật dẫn chuyện: kaomei `directing-stickman-videos`, chế độ B5 Character Explainer.
- Cảnh cơ chế: OpenMontage `minimalist-diagram` / `clean-professional` (AGPL-3.0, không vendoring code).
- Phụ đề sáng theo từng chữ: MoneyPrinterTurbo (MIT).
- Lõi dựng: Remotion; HyperFrames registry chỉ làm tham khảo chuyển cảnh và thẻ chữ.

## 1. Nhận diện

| Mục | Quy tắc |
| --- | --- |
| Màu | Nền `off_white #F7F4EC`. Nét và chữ `navy #12304A`. Nhấn `teal #18A6A6`. Cảnh báo/điểm chốt `yellow #F4B942`. Cảnh tối duy nhất là nền outro/hook kịch tính `night #0A1C2E`. **Tối đa 3 màu nổi trên một khung** (không tính nền). Không đỏ báo động. |
| Chữ | Be Vietnam Pro: 800 cho tiêu đề/nhãn chính, 600 cho nội dung. 16:9: nhãn ≥ 44 px, tiêu đề ≥ 72 px. 9:16: nhãn ≥ 52 px. Đọc rõ ở 720p; tương phản ≥ 4.5:1. |
| Nét hình | Phẳng 2D, matte, nét navy đều 6 px ở 1080p, góc bo; không gradient, không bóng đổ, không grain, không ảnh stock. |
| Bố cục | Lưới 12 cột; mascot chiếm một phía (trái hoặc phải, giữ nguyên trong một chương), sơ đồ phía còn lại. Vùng an toàn và hộp phụ đề theo `video/src/layout.ts`. |

## 2. Mascot dẫn chuyện

- Mascot là người dẫn, không phải trang trí. Xuất hiện ở hook, đầu mỗi chương, mỗi lần đổi ý
  chính, câu chốt và outro. Không xuất hiện trong khung chỉ có dữ liệu dày (biểu đồ, thẻ nguồn)
  trừ khi nhỏ ở góc và đang chỉ vào điểm chính.
- 9 tư thế trong `profiles/brand.vi.yaml` gắn với nghĩa:
  `welcome` mở video/chương · `explain` giải thích cơ chế · `point_up` chỉ vào điểm/nhãn ·
  `thinking` đặt câu hỏi · `surprised` sự thật bất ngờ · `caution` cảnh báo/khi nào đi khám ·
  `myth_bust` bác bỏ hiểu lầm · `blank_board` mở bảng sơ đồ · `thumbs_up` việc nên làm/kết.
- Cử động (Remotion, xác định theo frame): vào cảnh trượt + nảy nhẹ 12 frame; thở/bob 2 px chu
  kỳ 2 s khi đang nói; đổi tư thế bằng cross-fade 6 frame đúng beat lời đọc; hướng nhìn/tay chỉ
  về phía sơ đồ. Không xoay, không lắc đầu liên tục, không hiệu ứng cartoon quá đà.
- Một tư thế giữ ≥ 2 s; đổi tư thế chỉ khi ý đổi.

## 3. Cảnh cơ chế (sơ đồ)

- Sơ đồ dựng dần theo lời: mỗi beat thêm đúng một phần tử (cơ quan, mũi tên, nhãn). Không hiện
  cả sơ đồ rồi đọc.
- Mũi tên teal vẽ dần (stroke draw 10–16 frame); nhãn navy fade-up 0.95→1.0 trong 12 frame.
- Phần tử đang nói được nhấn bằng vòng teal hoặc gạch chân vàng; phần còn lại giảm 40% độ đậm.
- Ưu tiên SVG giải phẫu trong `video/src/anatomy`; FLUX chỉ cho cảnh đời sống, cùng nét/màu ở mục 1.

## 4. Phụ đề

- 16:9: tối đa 2 dòng, ≤ 42 ký tự/dòng, chia theo ý. 9:16: 1–2 dòng, ≤ 24 ký tự/dòng.
- Chữ đang đọc sáng teal (word highlight theo timing TTS), chữ khác navy trên dải off_white 90%.
- Thuật ngữ y khoa đã gắn nhãn trên sơ đồ được tô vàng trong phụ đề lần đầu xuất hiện.
- Không đè thẻ nguồn, không đè mascot, không đè nhãn sơ đồ (`safeZones.test.tsx`).

## 5. Nhịp

- Giữ cảnh 2.5–12 s; có thay đổi hình (beat) ít nhất mỗi 6 s.
- Chuyển cảnh: fade/slide-left 0.4 s, ease-in-out, không bounce ở chuyển cảnh, ≥ 2 s giữa hai chuyển cảnh.
- Hook 0–8 s: mascot `surprised` hoặc `thinking` + một câu hỏi lớn + một hình cụ thể. Không logo intro dài.
- Bộ động tác nhận diện chỉ gồm: dựng sơ đồ dần, vòng nhấn teal, gạch chân vàng, thẻ thuật ngữ,
  thẻ nguồn. 14 mẫu trong `video/src/motion` chỉ dùng khi đúng nghĩa, tối đa 2 mẫu khác trong
  một chương.

## 6. Nghĩa vụ từng trạm

| Trạm | Phải làm |
| --- | --- |
| 09 Máy dựng | Ghim file chuẩn này (đường dẫn + sha256) vào revision như `workflow/standards.yaml`; dựng bằng component theo chuẩn; từ chối storyboard thiếu `mascot_pose` ở hook/đầu chương/outro. |
| 10 Đạo diễn hình | Kiểm từng ảnh/FLUX theo mục 1; chọn tư thế mascot theo bảng mục 2; báo lệch phong cách bằng mã lỗi `style_*`. |
| 11 Thợ dựng | Chỉ sửa lỗi bị nêu; không thêm hiệu ứng ngoài mục 5 để "cho sinh động". |
| 12 Kiểm định sản phẩm | Chấm thêm tiêu chí "Đúng phong cách PYH" (màu, chữ, mascot đúng nghĩa, sơ đồ dựng dần, phụ đề) trên contact sheet + đoạn quanh hook và chuyển cảnh. |
| 13 Cổng video | Bác sĩ xem; app hiện điểm phong cách của trạm 12. |
| 14 Đóng gói & bài đăng | Thumbnail: mascot (tư thế khớp tiêu đề) + ≤ 4 chữ Be Vietnam Pro 800 + một hình cơ chế; nền off_white hoặc night. |
| 15 Shorts & Reels | Cùng chuẩn ở 9:16: mascot nhỏ hơn (≤ 28% chiều rộng), phụ đề giữa dưới, hook 0–2 s. |

## 6b. Bổ sung từ lemo-opuscar (chỉ lấy ý tưởng, không chép tài liệu: docs CC BY-NC)

- **Hook trong 3 s đầu** (siết mục 5): câu hỏi/sự thật bất ngờ phải có trước giây thứ 3.
- **Theo dòng chảy:** cảnh cơ chế tô teal dọc đường đi (máu, thuốc, men qua gan) theo đúng thứ tự lời đọc.
- **Nhãn mọc từ bộ phận** bằng đường dẫn (leader line) navy; chỉ một nhãn chính sáng tại một thời điểm.
- **Bỏ một lớp:** khi giải thích vì sao hỏng, cho tắt một phần tử để thấy hệ thống đổi ra sao (chỉ khi nguồn y khoa nói vậy).
- **Khoảng lặng:** 0.5–1 s đứng hình/không nhạc trước câu chốt; tối đa 2 lần mỗi chương.
- **Chủ thể ≥ 60% khung** ở cảnh cơ chế (mascot thu nhỏ về góc).
- Cảnh cơ chế được phép chuyển cảnh "bên trong vật thể" (zoom vào tế bào → cảnh tiếp) thay cho fade.
- Không mô phỏng "vật lý thật" cho cơ thể nếu không có nguồn; không dùng phong cách gây hoang mang (thriller, X-ray, game show).

## 7. Nghiệm thu chuẩn

Trước khi xưởng làm video thật: một clip mẫu 10–15 s (16:9 và 9:16) từ một câu lời đọc của
PYH-003, có hook, một cảnh cơ chế dựng dần, phụ đề sáng từng chữ, mascot đổi 2 tư thế. Bác sĩ
xem trong app và duyệt; ảnh khung đạt được lưu làm golden reference cho trạm 10 và 12.
