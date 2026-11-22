# Bộ style hình ảnh và chuẩn hình y khoa (thiết kế)

Ngày 2026-11-21. Bác sĩ chọn: bộ ba style **Scale Zoom**, **Isometric Infographic**, **Whiteboard**
(mỗi video một style chính), giữ mascot làm nhân vật hướng dẫn nhỏ, chuẩn hóa hình y khoa, và
làm Trạm 09 (Máy dựng) kiểm được những lỗi đang lọt: hình giữ lâu, chữ chồng, bôi vàng che chữ,
hình sơ sài. PYH-003 dùng Scale Zoom. Bổ sung cho (không thay) `2026-11-17-pyh-style-a-mascot-host.md`:
bản này đổi **phần hình minh họa**; nhận diện kênh, mascot, màu thương hiệu, cổng duyệt giữ nguyên.

## 1. Nguồn tham khảo và bản quyền

Ngữ pháp hình mượn từ `github.com/lemomo-ai/lemo-opuscar` (thư mục `styles/flat-space-explainer`
tức Scale Zoom, `iso-infographic`, `whiteboard`; đọc ngày 2026-11-21). Đó là hướng dẫn dựng
canvas/WebGL; ta **không chạy repo**, chỉ dựng lại bằng Remotion/SVG. STYLE.md thuộc CC BY-NC 4.0:
theo LICENSE của repo, bác sĩ và người làm việc cùng được đọc và làm theo để làm phim của mình
(kể cả thương mại), nhưng **không chép nguyên văn hay phân phối lại** tài liệu đó. Vì vậy tài liệu
này chỉ viết lại bằng lời của ta, không sao chép STYLE.md vào repo. Đây là cách đọc văn bản
giấy phép, không phải tư vấn pháp lý; nếu kênh có mô hình thương mại đặc biệt thì hỏi tác giả.

## 2. Ba style và khi nào dùng

| Style | Dùng khi | Ngữ pháp hình (ta dựng lại) |
| --- | --- | --- |
| `scale_zoom` | Cơ chế đi từ cơ quan → tế bào → phân tử (men gan thoát ra, viêm, tổn thương do thuốc) | Hình phẳng một bậc đổ bóng, không viền; camera zoom theo thang log xuống từng tầng, không xoay; mỗi màn hình **một** nhãn chính; vòng sáng hai lớp; nền `night #0A1C2E` hoặc `off_white` theo chương |
| `iso_infographic` | Giải phẫu, mặt cắt cơ quan, đếm số liệu, so sánh cấu trúc | Hình đẳng cự 30°, mỗi mặt ba tông phẳng, 5–7 màu trên nền sáng; mặt cắt lột lớp; vẽ đường đi trước khi vật chuyển động; nhãn dạng ghim + đường dẫn dọc + gạch ngang |
| `whiteboard` | Quy trình, nguyên nhân–hệ quả, việc nên làm, đọc phiếu xét nghiệm | Nét mực viết dần theo từng thuật ngữ đúng lúc lời đọc nhắc (0,3–0,8 s mỗi thuật ngữ), tối đa 3 màu + 1 màu nhấn; camera trượt trên một bảng |

Quy tắc chọn: biên kịch/agent storyboard ghi `visual_style` ở đầu `storyboard.yaml` (một giá trị
cho cả video). Trong video `scale_zoom`/`iso_infographic`, cảnh `whiteboard` dùng cho quy trình, nguyên nhân–hệ quả, việc nên làm, đọc phiếu; tổng thời lượng bị giới hạn bởi ngân sách hình (whiteboard_svg 10–15%). `visual_style` nằm trong hash cổng
y khoa (vì nằm trong `storyboard.yaml`), nên đổi style của video đã duyệt phải mở lại cổng y khoa.
Quyết định bác sĩ 2026-11-21: bỏ giới hạn whiteboard trong một chương; PYH-003 giữ whiteboard ở cả CH06 và CH07.

Màu thương hiệu giữ nguyên (`off_white`, `navy`, `teal`, `yellow`, `night`); ba style chỉ đổi cách
dựng hình, không đổi bảng màu kênh. Tối đa 3 màu nổi trên một khung như Style A.

## 3. Mascot

Giữ làm nhân vật hướng dẫn nhỏ: hook, đầu chương, câu chốt, outro; không chiếm cảnh chính và
không xuất hiện trong khung dữ liệu dày. Tư thế và quy tắc đổi tư thế như Style A mục 2.

## 4. Chuẩn hình y khoa (dùng chung cho cả ba style)

1. **Mỗi hình có một câu "người xem học được gì"** (`anatomy.motion` hoặc trường mới
   `visual_takeaway`), nằm trong storyboard nên được bác sĩ duyệt ở cổng y khoa. Hình không thể
   viết được câu này là hình vô nghĩa và bị loại ở Trạm 07.
2. **Thư viện chủ thể có id chuẩn** (`liver_organ`, `hepatocyte_sinusoid_unit`...), mỗi chủ thể
   ghi nguồn gốc và giấy phép; bản vẽ giải phẫu do người/code vẽ, không dùng ảnh AI có nhãn
   (đã là luật của `assets.py`).
3. **Mã hóa màu theo loại thực thể**, giữ cố định giữa các video: mô gan bình thường, tế bào
   tổn thương, enzym (ALT/AST), thuốc/chế phẩm, dòng máu, mạch mật, mốc cảnh báo. Mỗi loại một
   màu trong bảng thương hiệu; bảng đặt ở `profiles/` do bác sĩ duyệt, không để từng cảnh tự chọn.
4. **Ngữ pháp nhãn:** tiếng Việt, thuật ngữ La-tinh/viết tắt trong ngoặc nếu cần; ghim + đường
   dẫn; tối đa 6 nhãn mỗi khung, một nhãn chính tại một thời điểm; không chồng, không cắt.
5. **Trạng thái:** `normal`/`diseased` và mức nặng (`severity`) chỉ đổi khi lời đọc nói tới;
   không ánh xạ kết quả xét nghiệm sang tổn thương nếu bằng chứng không nói vậy.
6. **Thang tỷ lệ:** khi zoom qua nhiều tầng, hiện thanh tỷ lệ hoặc nhãn tầng (cơ quan, tế bào,
   phân tử); không để người xem mất định hướng.
7. **Bàn tay và người:** FLUX vẽ tay sai; hình có tay phải kiểm bắt buộc.

## 5. Trạm 09 (Máy dựng) phải kiểm được những gì

Hiện Trạm 09 chỉ ghim chuẩn và từ chối storyboard thiếu `mascot_pose`. Bổ sung kiểm **khách quan**,
chạy trên video đã dựng, ghi vào `reviews/motion-report.json` làm bằng chứng cho Trạm 12 (người
chấm chỉ nhìn ảnh mẫu nên không chứng minh được chuyển động):

- Chuỗi độ khác biệt giữa các khung (lấy mẫu mỗi 0,5 s); báo mọi đoạn **giữ gần như tĩnh > 6 s**
  (trừ cảnh dữ liệu được khai báo).
- Mỗi cảnh cơ chế có ≥ 1 thay đổi hình có nghĩa mỗi 6 s, đối chiếu với `beats`.
- Hộp chữ không chồng nhau và không bị che (kiểm bbox từ props, bổ sung kiểm ảnh).
- Nét nhấn (gạch/vòng vàng) không che quá 25% chiều cao dòng chữ.
- Chỉ dùng component thuộc style đã ghim; từ chối `visual` không thuộc style đó.
- Phụ đề: 16:9 không cháy cứng (xuất `.srt`), 9:16 giữ như chuẩn.

## 6. Kế hoạch theo giai đoạn

| Giai đoạn | Việc | Ai |
| --- | --- | --- |
| S1 | Thiết kế này + bảng màu thực thể y khoa (`profiles/`), bác sĩ duyệt | Claude |
| S2 | Trường `visual_style`, `visual_takeaway` ở schema storyboard + kiểm + test | codex |
| S3 | Bộ cảnh `scale_zoom` (log-zoom nhiều tầng, nhãn đơn, thanh tỷ lệ) | agy |
| S4 | Trạm 09: `motion-report.json` và các kiểm ở mục 5, nối vào Trạm 12 | codex |
| S5 | Chuẩn hóa thư viện giải phẫu (bảng màu thực thể, nhãn, id) | agy |
| S6 | Bộ cảnh `iso_infographic`, nâng `whiteboard` lên ngữ pháp mới | agy |
| S7 | Viết lại storyboard PYH-003 theo `scale_zoom`, mở lại cổng y khoa, dựng, duyệt | xưởng |

S2–S4 trước vì chúng sửa gốc lỗi (máy dựng không bắt được). S6 làm sau khi PYH-003 qua S7.

## 7. Không làm

Không chạy hay vendoring repo lemo-opuscar; không dùng ảnh vi thể thật (style Microscope bị loại
khỏi bộ ba vì tốn kiểm giấy phép từng ảnh); không đổi nhận diện kênh; không bỏ cổng y khoa
khi đổi style; không đụng PIN.
