# Thư viện SVG giải phẫu (`video/src/anatomy/`)

Quy ước mở rộng và duyệt component giải phẫu:

1. **File component**: Tạo `<Name>.tsx` xuất component phẳng (flat SVG, không gradient/filter) dùng đúng bảng màu `palette.ts` (`brand`, `anatomyColors`) và nhận `OrganProps`.
2. **Nhãn chữ**: Không nướng chữ hay nhãn giải phẫu vào SVG; mọi chữ/chú thích do scene bên ngoài vẽ để giữ kiểm soát bố cục 16:9 và 9:16.
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
