# Thiết kế nhận diện PHY và mascot M6.3

**Ngày:** 13-09-2026  
**Trạng thái:** Chờ duyệt đặc tả  
**Phạm vi:** M6.3 — nhận diện nền, SVG whiteboard và mascot rig cố định

## 1. Mục tiêu

M6.3 tạo một ngôn ngữ hình ảnh riêng cho Protect Your Health (PHY). Trụ cột
thương hiệu là **y khoa đáng tin**. Tính cách thương hiệu là một bác sĩ gần gũi,
giải thích kiến thức khó bằng ngôn ngữ dễ hiểu nhưng vẫn chỉn chu và có căn cứ.

Lát này phải tạo được logo chữ PHY, bộ màu, SVG whiteboard và mascot đồng nhất,
xác định và dùng được trong Remotion. Uy tín của PHY đến từ nguồn và quy trình
kiểm chứng, không đến từ việc mascot giả lập hoạt động khám bệnh.

## 2. Phạm vi và ranh giới

### Trong phạm vi

- Mở rộng `profiles/brand.vi.yaml` với token nhận diện PHY được kiểm tra bằng
  model cố định.
- Sinh logo chữ PHY và mascot từ SVG xác định, không phụ thuộc model tạo ảnh.
- Cung cấp ba tư thế mascot: `welcome`, `explain`, `caution`.
- Sinh SVG whiteboard từ một tập template cố định và dữ liệu do operator nhập.
- Khai báo asset mascot/whiteboard trong manifest của revision trước khi
  Remotion sử dụng.
- Phân biệt mascot trang trí với mascot mang nội dung y khoa.
- Cho storyboard tham chiếu asset đã khai báo mà không phá fixture v1 hoặc v2
  hiện có.

### Ngoài phạm vi

- Intro, outro, câu signature và thời lượng signature; M6.4 xử lý phần này.
- Kiểm tra tỷ lệ visual toàn video; M6.5 xử lý phần này.
- Veo, video AI, chuyển động rig phức tạp hoặc sinh mascot bằng model.
- Áo blouse, ống nghe, tư thế khám, chẩn đoán, kê đơn hoặc tư vấn cá nhân hóa.
- Tự tạo nội dung y khoa, số liệu, nguồn, quyền sử dụng hoặc lời của bác sĩ.
- Thay đổi hai cổng duyệt hoặc cơ chế đăng thủ công.

Ảnh concept tạo trong quá trình thiết kế chỉ là tham khảo. Nó không phải asset
production, không được chép vào Git và không quyết định byte SVG cuối cùng.

## 3. Hệ nhận diện

### 3.1. Logo “Dấu kiểm chứng”

Logo là wordmark hình học viết đúng `PHY`:

- `P` gợi một bong bóng giải thích bằng khoảng âm đơn giản;
- `H` chứa dấu cộng kín đáo trong cấu trúc nét;
- nhánh trên của `Y` kết thúc thành dấu kiểm màu vàng.

Logo phải đọc rõ là `PHY` ở kích thước nhỏ. Dấu cộng không được trở thành biểu
tượng bệnh viện độc lập. Logo không dùng tim–điện tâm đồ, khiên, caduceus hoặc
DNA. Generator cung cấp bản ngang, monogram vuông và bản một màu từ cùng token.

### 3.2. Màu và nét

Brand profile lưu các màu sau dưới tên ngữ nghĩa:

| Token | Giá trị | Vai trò |
| --- | --- | --- |
| `navy` | `#12304A` | màu chính, nét và chữ |
| `teal` | `#18A6A6` | màu hỗ trợ, giải thích |
| `yellow` | `#F4B942` | dấu kiểm và điểm nhấn hiếm |
| `off_white` | `#F7F4EC` | nền |
| `charcoal` | `#263238` | chữ phụ |

SVG dùng mảng phẳng, đầu nét bo tròn và không dùng gradient, glow, filter,
external reference, script hoặc font nhúng. Màu vàng không được dùng làm mảng
nền lớn vì nó biểu thị điểm cần chú ý hoặc đã kiểm chứng.

### 3.3. Mascot

Mascot là bác sĩ–người hướng dẫn nam, tóc ngắn gọn, thân hình tròn vừa phải,
khuôn mặt thân thiện và kính tròn hơi bất đối xứng. Nhân vật mặc áo khoác chuyên
môn navy–teal, không mặc blouse. Ba chi tiết nối mascot với logo:

- huy hiệu hình `P`;
- đường may áo tạo cấu trúc `H`;
- dấu `Y-check` vàng nhỏ.

Ba pose có silhouette riêng nhưng dùng chung đầu, thân, kính, bảng màu và tỷ lệ.
`welcome` chào trung tính; `explain` chỉ về vùng nội dung; `caution` giơ tay nhắc
cẩn trọng. Không pose nào mô phỏng khám hoặc đưa chỉ định điều trị.

## 4. Kiến trúc

M6.3 chia thành năm đơn vị độc lập:

1. **Brand model** đọc và kiểm tra token từ `profiles/brand.vi.yaml`. Mọi
   generator nhận model này thay vì chép mã màu rải rác.
2. **Logo generator** tạo các biến thể SVG xác định từ brand model.
3. **Whiteboard generator** nhận tên template và dữ liệu hiển thị đã được cung
   cấp. Template chỉ bố trí hình; nó không suy luận nội dung y khoa.
4. **Mascot generator** nhận pose và annotation tùy chọn, rồi tạo SVG từ rig cố
   định.
5. **Asset registration và renderer** ghi asset vào revision một cách nguyên tử,
   thêm tham chiếu cảnh và chỉ render đường dẫn đã có trong manifest.

Generator là hàm thuần: cùng brand profile và cùng payload phải tạo đúng cùng
byte UTF-8. SVG sắp xếp attribute ổn định, dùng số nguyên khi có thể và kết thúc
bằng một newline.

## 5. Contract dữ liệu và policy

`AssetKind` thêm hai loại đã được đặc tả A–Z quy định:

- `mascot_reaction`: bắt buộc `semantic: false`;
- `mascot_medical_annotation`: bắt buộc `semantic: true`.

Whiteboard mang sơ đồ, chữ, số hoặc marker y khoa dùng loại semantic hiện có
`medical_diagram` hoặc `medical_text`. Whiteboard thuần trang trí dùng một loại
decorative hiện có phù hợp. Workflow không được hạ một nội dung y khoa thành
decorative để né medical hash.

Mỗi cảnh có thể thêm danh sách `visual_assets`. Mỗi tham chiếu gồm đường dẫn
POSIX tương đối và vai trò `whiteboard` hoặc `mascot`. Tham chiếu mascot có pose
`welcome`, `explain` hoặc `caution`. Các trường đều là optional để fixture v1 và
v2 cũ vẫn parse và render như trước.

Mọi đường dẫn trong `visual_assets` phải:

- nằm trong revision;
- xuất hiện đúng một lần trong asset manifest;
- trỏ đến file có thật và đúng SHA-256;
- có kind phù hợp với vai trò;
- có phân loại semantic phù hợp với nội dung.

`mascot_reaction` không được chứa annotation, claim ID, source marker, số liệu
hoặc nội dung y khoa. Nếu mascot mang bất kỳ thành phần nào trong số đó, workflow
phải đăng ký nó là `mascot_medical_annotation` và đưa byte vào medical gate.

Logo và mascot do dự án tự tạo dùng license nội bộ được khai báo rõ trong brand
profile. Code kiểm tra chuỗi license và creator có thật; code không tự kết luận
quyền pháp lý. Asset đưa vào revision vẫn có source, creator, license, revision
và SHA-256 như các asset khác.

## 6. Luồng tạo và sử dụng asset

1. Operator chọn template hoặc pose, nhập đúng nội dung cần hiển thị và chỉ định
   semantic classification.
2. Workflow đọc revision v2 đang ở giai đoạn trước medical approval và từ chối
   revision đã được duyệt.
3. Workflow kiểm tra brand profile, scene, claim/source mapping khi asset mang
   nội dung y khoa, manifest hiện tại và quyền sử dụng.
4. Generator tạo SVG trong staging. Workflow tính SHA-256 từ chính byte staged.
5. Workflow ghi ý định tham chiếu vào storyboard trước, rồi promotion thư mục
   asset gồm SVG, manifest và rights ledger. Trong cửa sổ crash, medical gate từ
   chối tham chiếu thiếu asset; lần chạy lại hoàn tất promotion từ cùng input.
   Workflow không coi trạng thái trung gian là thành công.
6. Medical gate kiểm tra hai chiều giữa storyboard và manifest, rồi hash mọi
   asset semantic. Mascot reaction không thay đổi medical hash.
7. Production preflight chỉ chuyển asset đã khai báo và đúng hash vào render run.
8. Remotion dùng `staticFile(path)` để render asset. Cảnh không có
   `visual_assets` tiếp tục dùng nét whiteboard legacy hiện tại.

Không bước nào thay đổi state chỉ vì tạo asset. Hai cổng duyệt và invalidation
hiện có giữ nguyên.

## 7. Renderer

Remotion thêm component nhỏ cho SVG asset và bố cục mascot. Asset whiteboard nằm
trong safe area của cảnh; mascot đặt ở phần dưới hoặc cạnh vùng giải thích, không
che source marker hay phụ đề. `explain` quay về phía vùng nội dung; `caution`
không dùng màu đỏ toàn cảnh hoặc animation gây báo động quá mức.

Animation chỉ dùng transform và opacity xác định theo frame. Không đọc thời gian
hệ thống, random hoặc tài nguyên mạng. Renderer không dựng lại SVG từ dữ liệu y
khoa; nó chỉ hiển thị byte đã khai báo và đã qua preflight.

## 8. Xử lý lỗi và khả năng chạy lại

Workflow từ chối trước khi ghi nếu gặp một trong các lỗi sau:

- brand profile thiếu token hoặc có màu sai định dạng;
- template, pose, asset name hoặc đường dẫn không hợp lệ;
- annotation y khoa thiếu claim/source/marker hợp lệ;
- mascot reaction chứa nội dung semantic;
- đường dẫn trùng, manifest/rights ledger lệch hoặc asset cũ khác provenance;
- revision sai state hoặc đã có medical approval.

Nếu process dừng giữa các bước ghi, lần chạy sau phải phát hiện staging/promotion
dở, phục hồi trạng thái nhất quán và hội tụ về cùng byte/hash. Workflow không ghi
đè một asset cùng tên nhưng khác nội dung hoặc provenance.

## 9. Kiểm thử và tiêu chí hoàn tất

### Python

- Brand model nhận profile chuẩn và từ chối token thiếu, màu sai, pose lạ.
- Logo, từng pose mascot và từng template whiteboard lặp lại đúng byte/hash.
- SVG không chứa script, filter, external URL, embedded raster hoặc font nhúng.
- `mascot_reaction` chỉ nhận `semantic: false`; annotation luôn semantic.
- Workflow từ chối annotation không có claim/source/marker hợp lệ.
- Manifest, rights ledger và storyboard nhất quán sau success, crash và retry.
- Medical gate hash riêng byte annotation semantic. Nó không hash riêng byte
  mascot reaction; production preflight vẫn từ chối reaction có byte lệch hash
  đã khai báo. Thay storyboard hoặc manifest sau approval vẫn làm approval stale.
- Fixture v1 và v2 hiện có vẫn parse; schema export không có diff ngoài thay đổi
  đã chủ ý.

### TypeScript/Remotion

- Zod chấp nhận scene legacy và scene có `visual_assets` hợp lệ.
- Renderer dùng đúng asset đã khai báo, pose và safe-area layout.
- Mascot không che source marker hoặc subtitle ở các frame đại diện.
- Test cấm fallback sang đường dẫn asset không có trong render input.
- Video tests và typecheck đều qua.

### Kiểm tra cuối

- Toàn bộ `python -m pytest -q` qua.
- `python -m ruff check src tests tools` qua.
- Schema export rồi diff chỉ chứa thay đổi dự kiến.
- `pnpm --dir video test` và `pnpm --dir video typecheck` qua.
- `git diff --check` qua.
- README ghi M6.3 hoàn tất trong cùng commit implementation.

## 10. Quyết định giữ lại cho M6.4

M6.3 định nghĩa logo, palette và DNA mascot để M6.4 có đầu vào ổn định. M6.4 mới
quyết định cách logo xuất hiện trong intro/outro, thời lượng 2–3 giây, chuyển động
signature và câu thoại được bác sĩ cung cấp. M6.3 không tự tạo slogan hoặc thoại.
