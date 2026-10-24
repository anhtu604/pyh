# Thư viện SVG giải phẫu (`video/src/anatomy/`)

Quy ước mở rộng và duyệt component giải phẫu:

1. **File component**: Tạo `<Name>.tsx` xuất component phẳng (flat SVG, không gradient/filter) dùng đúng bảng màu `palette.ts` (`brand`, `anatomyColors`) và nhận `OrganProps`.
2. **Nhãn SVG v2**: Cho phép thuật ngữ giải phẫu/sinh lý tiếng Việt cố định trong code, không chứa số liệu hoặc diễn giải chưa được duyệt. Dùng font brand `Be Vietnam Pro`, nền/viền tương phản, leader line tới cấu trúc tương ứng; mũi tên riêng chỉ quá trình. Ảnh AI FLUX vẫn tuyệt đối không có chữ.
   - Tối đa 6 nhãn hiện cùng lúc; hộp nhãn không chồng nhau, không vượt viewBox. `visibleLabels` do beat điều khiển, mặc định ẩn. Camera chỉ biến đổi hình giải phẫu; scene đặt nhãn trên overlay cố định và biến đổi đầu leader line theo camera.
   - Mỗi component khai báo `FOCUS_REGIONS` (`id → {left, top, width, height}` theo tọa độ viewBox) và `LABELS` (`id → {text, region, x, y, width, height, anchor: [x,y]}`). Component cũ chưa có nhãn dùng object rỗng. Đồng bộ với `focus_regions`/`labels` trong `library.json` và các registry `ANATOMY_FOCUS_REGIONS`/`ANATOMY_LABELS`.
   - Dùng `DiagramAnnotations` trong `annotations.tsx` để dựng nhãn, và `ProcessArrow` để chỉ hướng; không nhầm mũi tên sơ đồ với thang đo/tốc độ sinh học.
   **Độ phủ**: Mọi component phải dùng viewBox vuông và nội dung chính (kể cả nhánh mũi tên) lấp ít nhất 75% chiều rộng lẫn chiều cao. Xuất hằng `CONTENT_BOX` bao toàn bộ nội dung vẽ ở các trạng thái/frame, nằm trong viewBox; đăng ký hằng trong `ANATOMY_CONTENT_BOXES`. Test chung `anatomy.test.tsx` kiểm tra độ phủ và viewBox cho tất cả component; test riêng kiểm hằng theo hình học thực tế. Không thêm hình vô nghĩa để tăng bbox.
3. **Đăng ký trong thư viện** (không cần sửa file ngoài `video/src/anatomy/`):
   - `video/src/anatomy/library.json`: thêm `<subject>: {"file": "<Name>.tsx", "layers": [...]}` (nguồn sự thật duy nhất).
   - `video/src/anatomy/registry.ts`: ánh xạ `<subject>` → component trong `ANATOMY_COMPONENTS`.
   - Python và TypeScript tự lấy subject từ key trong `library.json`; không duy trì danh sách riêng.
4. **Kiểm thử bắt buộc**:
   - Thêm `<Name>.test.tsx` ngay trong `video/src/anatomy/` để kiểm tra hình học, chuyển động theo `state`/`severity` và các nhóm/layer SVG.
   - `video/src/anatomy/registry.test.ts` và `tests/visuals/test_anatomy_library.py` tự động kiểm tra đồng bộ giữa `library.json`, `registry.ts`, `types.ts` và `storyboard.py`.
5. **Theo dõi duyệt y khoa**:
   - Trạng thái component (`new`, `modified`, `approved`) được tính bằng SHA-256 của file `.tsx` đối chiếu với `video/src/anatomy/approved.json`.
   - Mọi component có trạng thái `new` hoặc `modified` đang dùng trong video luôn được liệt kê thành mục riêng khi dựng contact sheet (`review_frames.py`) để bác sĩ soát kỹ trước khi duyệt cổng video.
6. **Căn chuyển động theo lời nói**: Mỗi component xuất `CUE_ACTIONS` (mảng rỗng khi chưa hỗ trợ). `anatomy.cues` gắn `word` trong narration với một `action` hợp lệ; production thêm `start_frame` cục bộ từ alignment. Scene chuyển thành `cueProgress: Record<string, number>` trong khoảng 0–1 và component điều khiển riêng từng hành động. Thiếu mốc căn chữ thì giữ chuyển động liên tục cũ.
   - `UrateFluid`: `seed`, `grow`, `deposit`; `InflammationSignal`: `engulf`, `alarm`, `recruit`; `HepaticCell`: `fat`, `inflame`, `fibrose`. Không coi tiến độ minh họa là diễn tiến bệnh hay thang điểm lâm sàng.

## Góc nhìn gout v2 và lời thoại đã duyệt

- `UrateFluid`: N03–N08 (urat hòa tan và ô dịch), N10–N13 (mầm/hạt rắn), N20 (lắng đọng khác cơn viêm). Mặt cắt có năm nhãn giải phẫu và ô phóng đại; không phải ảnh mô học.
- `UrateCrystalCloseUp`: N10–N13, N21, N23: hòa tan, mầm, lớn lên, dạng kim; không vẽ kim khâu đâm mô. Không tự đảo quá trình bệnh hay mô phỏng điều trị.
- `InflammationSignal`: N05/N09/N14 (trạng thái yên), N15/N24 (báo động tế bào, có điều kiện chuẩn bị), N16/N19/N25 (huy động bạch cầu), N17–N18 (viêm cấp). Các thuật ngữ NLRP3/IL-1β là nhãn cấu trúc cơ chế; không thêm lời khẳng định lâm sàng.
- `UrateDeposition`: N14/N20/N26: lắng đọng tách biệt với cơn viêm có triệu chứng. Góc bề mặt sụn và màng hoạt dịch, không tự bật viêm.
- `GoutFootOverview`: hình tổng quan vị trí khớp theo yêu cầu hình ảnh, có thể hỗ trợ ngữ cảnh N01/N02/N17, **nhưng lời thoại revision 001 không nêu ngón cái/MTP1**. Không tự gắn component này vào revision đã duyệt; cần bác sĩ duyệt riêng vị trí và dấu đỏ/sưng/nóng trước khi sử dụng. Không dùng hình để chẩn đoán mọi khớp đau là gout.
- Không thêm `UricAcidBalance`: lời thoại revision 001 không nhắc thận hay cân bằng tạo/thải urat.

Kiểm thử `annotations.test.tsx` kiểm mọi hộp nhãn và focus, registry đồng bộ, số nhãn cùng lúc; các file gout test kiểm cue độc lập, hình học và trạng thái bình thường/bệnh. Mọi component mới/sửa vẫn đi qua cổng video, không tự cập nhật `approved.json`.
