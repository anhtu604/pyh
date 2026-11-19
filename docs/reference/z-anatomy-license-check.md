# Kiểm tra giấy phép Z-Anatomy 3D

Ngày kiểm tra: 2026-11-19.

## 1. Nguồn chính thức đã kiểm chứng

- Trang chủ WebGL chính thức: `https://www.z-anatomy.com/` (bản build WebGL `2026.1.0-webgl`).
- Tổ chức GitHub chính thức: `https://github.com/Z-Anatomy`
  - Repo mô hình giải phẫu người: `https://github.com/Z-Anatomy/Models-of-human-anatomy` (`Readme.md`, `License.txt`).
  - Các repo liên quan: `Models-of-veterinary-anatomy`, `Unity-app_Z-Anatomy`, `Blender-addons` (mã add-on Blender mang giấy phép `GPL-3.0`).

## 2. Giấy phép chính thức và nguồn kế thừa

Theo tệp `License.txt` và `Readme.md` trong `Z-Anatomy/Models-of-human-anatomy`:

1. **Giấy phép chính của Z-Anatomy:** Toàn bộ nội dung, cơ sở dữ liệu và mô hình 3D do Z-Anatomy chia sẻ được phát hành dưới giấy phép **Creative Commons Attribution-ShareAlike 4.0 International (`CC BY-SA 4.0`)** (`http://creativecommons.org/licenses/by-sa/4.0/`).
2. **Mô hình nền gốc (`BodyParts3D`):** Phần lớn lưới 3D nền được phái sinh từ **BodyParts3D** (Database Center for Life Science — DBCLS), mang giấy phép **`CC BY-SA 2.1 Japan`**.
3. **Định nghĩa mô tả giải phẫu:** Lấy từ **Wikipedia**, mang giấy phép **`CC BY-SA 3.0`**.
4. **Một số mô hình thành phần tích hợp/tham chiếu riêng trong `License.txt`:**
   - *Cranial Nerves and Foramina* (University of Dundee, CAHID): **`CC BY 4.0`**.
   - *Anatomy of the Inner Ear* (University of Dundee School of Medicine): **`CC BY-NC-SA 4.0`** (**Phi thương mại — NC** + ShareAlike).
   - *Kidney* (Lissie Cowley): **`CC BY-NC 4.0`** (**Phi thương mại — NC**).

## 3. Hệ quả của copyleft `CC BY-SA 4.0` (và thành phần `NC`) đối với video kênh PYH

### 3.1. Điều khoản ShareAlike (`SA`) khi dựng video / hoạt cảnh
- Bản thân `CC BY-SA 4.0` **cho phép sử dụng thương mại** (vd. kênh YouTube bật kiếm tiền), **NHƯNG** đi kèm điều kiện **copyleft (ShareAlike)**:
  - Nếu dùng mô hình 3D Z-Anatomy để quay/render trực tiếp, cắt ghép, tô nhấn, gắn nhãn, chuyển động hoặc biên tập thành **tác phẩm phái sinh (Adapted Material)**, **toàn bộ tác phẩm phái sinh đó (video / hoạt cảnh đã kết xuất)** phải được phân phối lại dưới **chính giấy phép `CC BY-SA 4.0`** (hoặc giấy phép tương thích theo Creative Commons).
  - Hệ quả thực tế: bất kỳ bên thứ ba nào cũng có quyền tải, chia sẻ lại và chỉnh sửa lại video của kênh (kể cả cho mục đích thương mại) chỉ cần ghi công; đồng thời kênh **không được** áp thêm điều khoản hạn chế pháp lý hoặc DRM/quyền sở hữu riêng lên phần sản phẩm phái sinh đó.
  - Ngay cả khi sử dụng ảnh chụp màn hình tĩnh hoặc đoạn render ngắn xen kẽ trong video dài, ranh giới pháp lý giữa *Adapted Material* (bị lây ShareAlike sang cả video) và *Collection* (tuyển tập các tác phẩm tách biệt) trong dựng phim chuyển động/compositing rất dễ gây tranh chấp và rủi ro pháp lý cho kênh.

### 3.2. Thành phần `CC BY-NC` / `CC BY-NC-SA` bên trong gói Z-Anatomy
- Do một số mô hình bộ phận trong Z-Anatomy (như tai trong `CC BY-NC-SA 4.0` và thận `CC BY-NC 4.0`) có điều khoản **NonCommercial (`NC`)**, mọi hoạt động xuất bản trên kênh có bật quảng cáo, tài trợ, hoặc mang tính thương mại đều **vi phạm điều khoản NC** nếu sử dụng các phần mô hình đó.

### 3.3. Yêu cầu ghi công nhiều tầng
- `License.txt` yêu cầu ghi công đầy đủ cả `BodyParts3D - The Database Center for Life Science - CC-BY-SA 2.1 Japan`, `Z-Anatomy - The libre 3D atlas of anatomy - CC-BY-SA 4.0`, các tác giả thành phần liên quan, link giấy phép và nêu rõ thay đổi nếu có chỉnh sửa.

## 4. Kết luận và trạng thái trong xưởng PYH

- **Trạng thái 3D Z-Anatomy: CHƯA BẬT (tạm khóa).**
- **Lý do:**
  1. `CC BY-SA 4.0` là giấy phép copyleft lan truyền (*ShareAlike*), không phù hợp với chính sách kho hình mở mặc định của PYH (`Public Domain`, `CC0`, `CC BY 3.0`, `CC BY 4.0` — cấm `CC BY-SA`, `NC`, `ND` tại `src/healthvideo/domain/medanim_library.py`).
  2. Gói Z-Anatomy còn chứa thành phần `CC BY-NC 4.0` và `CC BY-NC-SA 4.0` xung đột với kênh có thể thương mại hóa/kiếm tiền trên YouTube/TikTok.
- **Khuyến nghị chờ bác sĩ quyết định:**
  - Tiếp tục sử dụng tài nguyên 2D vector chuẩn khoa học (`NIAID NIH BioArt` Public Domain / `CC BY 4.0`, `Reactome` `CC BY 4.0`, `Servier Medical Art` `CC BY 4.0`, `DBCLS` `CC BY 4.0`, `Bioicons` lọc bỏ `CC BY-SA`).
  - Chỉ mở khóa Z-Anatomy 3D nếu bác sĩ quyết định chấp nhận phát hành công khai các video dùng Z-Anatomy theo giấy phép `CC BY-SA 4.0` **và** loại bỏ hoàn toàn các thành phần con mang nhãn `NC` (hoặc tìm nguồn 3D `CC0` / `Public Domain` / `CC BY 4.0` thuần túy thay thế).
