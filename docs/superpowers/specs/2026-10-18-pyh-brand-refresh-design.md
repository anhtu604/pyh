# Làm mới nhận diện PYH: logo, mascot chibi, màu, font, thẻ cuối

**Ngày:** 18-10-2026
**Trạng thái:** Đã duyệt và triển khai (18-10-2026)
**Kế thừa:** M6.3 (`2026-09-13-pyh-brand-mascot-m6-3-design.md`), explain-first §12–§13
(`2026-10-18-explain-first-content-design.md`)

## 1. Vấn đề đã xác nhận

Render thử `render_pyh_logo` và `render_mascot` ra `.tmp/brand-now/` cho thấy:

- **Logo bị cắt.** Chữ `H` chạm mép phải `viewBox` (path kết thúc ở x=760 = chiều rộng),
  không có lề. Monogram chỉ là wordmark thu nhỏ, bị cắt mất `H`, không phải dấu vuông.
- **Bản một màu hỏng.** Dấu kiểm và dấu cộng cùng màu navy với nét chữ nên biến mất.
- **`P` đọc như `D`.** Bụng chữ cao gần hết thân, lỗ bong bóng quá nhỏ.
- **Mascot tạm trông như logo.** Thân navy, đường may `H`, huy hiệu `P`, dấu kiểm vàng.
  Mascot thật là **bác sĩ chibi đại diện cho người dùng**; người dùng chưa có file ảnh
  (xác nhận 18-10-2026).
- Video dùng `Arial`, không có font tiếng Việt riêng. Token `night` (#0A1C2E) chỉ có trong
  `video/src/anatomy/palette.ts`, chưa có trong brand profile.

## 2. Logo

Vẽ lại theo **bảng nhận diện cũ người dùng đã duyệt** (ảnh gửi 18-10-2026, bản làm việc
`.tmp/brand-board/board.webp`, không commit), chỉ đổi thứ tự chữ thành P–Y–H. Bản phác
hình học tự vẽ trước đó bị người dùng loại vì xấu và sai thiết kế.

- **`P` = bong bóng giải thích.** Thân thẳng + bụng bo tròn cao khoảng 2/3 chữ; lỗ bên
  trong là bong bóng thoại có đuôi nhọn chéo xuống trái, đủ lớn để đọc ở chiều cao 32 px.
- **`Y` = dấu kiểm vàng trên thân navy.** Hai nhánh trên của `Y` chính là dấu kiểm (nhánh
  trái ngắn, nhánh phải dài), nét bo tròn, màu `yellow`; thân dưới là khối `navy`.
- **`H` có dấu cộng kín đáo.** Thanh ngang của `H` nhô lên và xuống ở giữa thành dấu cộng,
  **cùng màu** với `H` (teal), nên bản một màu vẫn đọc được.
- **Lề an toàn.** Mọi hình (kể cả nửa bề dày nét) nằm cách mép `viewBox` ít nhất 40 đơn vị.
  Bản ngang `0 0 730 280`.
- **Biến thể** (`LogoVariant`):
  - `horizontal`: navy / yellow / teal trên nền trong suốt.
  - `monogram`: dấu vuông riêng `0 0 320 320`, ô navy bo góc, `P` off_white, dấu kiểm
    vàng nằm trong lỗ bong bóng. Dùng cho avatar kênh, watermark.
  - `one_color`: toàn navy; dấu kiểm vẫn tách khỏi thân `Y` nhờ hình dạng.
  - `reverse` **(mới)**: `P` và thân `Y` off_white, dấu kiểm yellow, `H` teal, dùng trên nền
    `night`. Nền vẫn trong suốt; người dùng đặt lên nền tối.
- Logo chỉ dùng lệnh path tuyệt đối `M L H V Q Z` để test đọc được tọa độ và kiểm tra lề.

### 2.1. Chốt thứ tự chữ: PYH

Bảng nhận diện cũ của người dùng vẽ logo đọc thành `PHY` (P–H–Y). Người dùng chốt ngày
18-10-2026: tên chuẩn là **PYH** theo Protect Your Health, logo đọc P–Y–H. Giữ các ý từ bảng
cũ (P bong bóng, H teal có dấu cộng, nhánh Y thành dấu kiểm vàng) nhưng sắp lại thứ tự.

Thống nhất: xóa alias `render_phy_logo` vì không còn nơi gọi ngoài test; fixture test
`assets/phy.svg` đổi thành `assets/pyh.svg`. Giữ nguyên: test đọc revision cũ có asset
`phy-*` (tương thích dữ liệu đã lưu) và tên commit lịch sử trong README.

## 3. Màu

Giữ năm token M6.3, thêm `night`:

| Token | Giá trị | Dùng cho |
| --- | --- | --- |
| `navy` | `#12304A` | chữ, nét chính |
| `teal` | `#18A6A6` | mảng hỗ trợ; **không** làm chữ nhỏ trên off_white (tương phản ~2,7:1) |
| `yellow` | `#F4B942` | dấu kiểm, từ khóa nhấn mạnh; không làm mảng nền lớn |
| `off_white` | `#F7F4EC` | nền sáng, chữ trên nền tối |
| `charcoal` | `#263238` | chữ phụ |
| `night` | `#0A1C2E` | **mới**: nền thẻ cuối, cảnh tối, nền logo `reverse` |

`profiles/brand.vi.yaml` và `BrandColors` thêm `night` (bắt buộc). `video/src/anatomy/palette.ts`
vẫn là bản sao phía TypeScript; một test Python so khớp `brand` trong `palette.ts` với YAML
để hai bên không lệch.

## 4. Font tiếng Việt

- **Be Vietnam Pro** (SIL Open Font License 1.1), thiết kế riêng cho dấu tiếng Việt.
- Lưu hai file `woff2` (SemiBold 600 cho phụ đề/thân chữ, ExtraBold 800 cho tiêu đề/CTA)
  cùng `OFL.txt` trong `video/public/fonts/`. Lấy từ repo chính thức `google/fonts`. OFL cho
  phép phân phối lại nên được commit; render không tải mạng.
- Nạp bằng `FontFace` + `staticFile` + `delayRender/continueRender` trong một module
  `video/src/fonts.ts` xuất hằng `FONT_FAMILY` (kèm fallback `Arial, sans-serif`). Mọi chỗ
  đang ghi `'Arial, sans-serif'` chuyển sang hằng này. Không thêm dependency mới.

## 5. Mascot bác sĩ chibi

### 5.1. Khe artwork

Người dùng chưa có file. Pipeline chuẩn bị sẵn khe để khi có ảnh chỉ cần thả file và khai báo:

```yaml
# profiles/brand.vi.yaml
mascot:
  poses: [welcome, explain, caution]
  artwork:            # tùy chọn; vắng mặt => dùng placeholder SVG
    welcome: {path: assets/brand/mascot/welcome.png, sha256: "<64 hex>"}
    explain: {path: assets/brand/mascot/explain.png, sha256: "<64 hex>"}
    caution: {path: assets/brand/mascot/caution.png, sha256: "<64 hex>"}
```

Khi có `artwork`, lúc nạp profile phải kiểm (chỉ dùng stdlib): đủ ba pose; đường dẫn POSIX
tương đối trong repo; file tồn tại; SHA-256 khớp; là PNG RGBA (có kênh alpha); cả ba cùng
kích thước, cạnh ngắn ít nhất 768 px. Sai một điều là từ chối với thông báo rõ.

Một hàm duy nhất `mascot_asset(brand, pose) -> (bytes, suffix)` trả PNG nếu có artwork,
ngược lại trả SVG placeholder. Cả hai nơi đăng ký mascot (`create_mascot_reaction_asset`,
`_register_clip_mascot`) đi qua hàm này; đường dẫn asset lấy đuôi `.png` hoặc `.svg` theo
kết quả. Mọi kiểm tra đuôi/kind ở manifest, preflight và Zod phải nhận `.png` cho
`mascot_reaction`.

### 5.2. Yêu cầu với ảnh (gửi người vẽ)

Nhân vật theo bảng nhận diện cũ người dùng đã duyệt:

- Chibi tỉ lệ 2–2,5 đầu, nam, mũm mĩm, tóc đen ngắn, kính tròn (giống người dùng); giữ
  **nguyên khuôn mặt, trang phục, tỷ lệ** ở cả ba pose.
- Áo khoác navy viền teal, sọc teal tạo chữ thập trên ngực, huy hiệu `P` trắng, dấu kiểm
  vàng ở tay áo; áo thun trắng bên trong, quần navy, sneaker trắng.
- Phong cách phẳng: mảng màu đặc, viền gọn, không gradient/glow/bóng mờ.
- **Không** áo blouse, ống nghe, tư thế khám, kê đơn; ngoài huy hiệu `P`, **không** chữ, số
  hay claim trong ảnh.
- Canvas vuông 1024×1024, nền trong suốt; nhân vật đứng, chân cách đáy khoảng 5%, đầu cách
  đỉnh khoảng 8%; thân **hướng sang phải người xem**.
- `welcome`: vẫy tay, tay kia đút túi. `explain`: chỉ tay sang phải về vùng nội dung,
  miệng cười. `caution`: hai bàn tay giơ ra, nháy mắt.
- Quyền: tranh do người dùng tự vẽ hoặc đặt vẽ/tự tạo và có quyền dùng. Code chỉ ghi
  `creator` và `license` khai báo trong profile; code không kết luận quyền pháp lý.

### 5.3. Placeholder

Rig SVG hiện tại giữ nguyên hình (huy hiệu `P`, sọc, dấu kiểm vàng khớp với nhân vật thật),
chỉ đổi `aria-label` thành `PYH guide placeholder <pose>`. Khi render bằng
placeholder, gói duyệt video (cổng 2) hiển thị một dòng cảnh báo "mascot đang dùng hình tạm".
Cảnh báo không chặn render.

### 5.4. Mascot mang chú thích y khoa

Ranh giới M6.3 giữ nguyên: `mascot_reaction` không chữ, số, claim; chú thích y khoa là
`mascot_medical_annotation` và qua cổng duyệt y khoa. Khi đã có artwork PNG, SVG không được
nhúng raster, nên `create_mascot_annotation_asset` từ chối với hướng dẫn: dùng asset
`medical_text` (bong bóng chú thích) đặt cạnh `mascot_reaction`. Khi chưa có artwork, hành vi
cũ giữ nguyên.

### 5.5. Quy tắc dùng trong video explain-first

Giữ bảng nhịp/pose của explain-first §13 (mở `welcome`, cơ chế `explain`, giới hạn
`caution`, thẻ cuối `welcome`; cảnh báo khi mascot có mặt trên 35% frame). Bổ sung:

- Mascot cao tối đa 30% chiều cao khung ở 16:9, 24% ở 9:16 (thẻ cuối được phép lớn hơn).
- Ảnh luôn hướng phải; nếu tâm hộp mascot nằm ở nửa phải khung thì renderer lật ngang
  (`scaleX(-1)`) để mascot nhìn vào nội dung.
- Không che phụ đề, source marker, cơ quan đang hoạt họa; 9:16 tránh cột nút bên phải.
- Đĩa tròn `off_white` sau mascot (đã có trong `MascotGuide`) giữ nguyên để mascot nổi trên
  nền tối lẫn nền sáng.

## 6. Thẻ cuối clip

Giữ bố cục Task 7 (nền `night`, chữ CTA off_white, chữ `YouTube` màu vàng, mascot `welcome`
trên đĩa off_white) và thêm:

- CTA dùng `FONT_FAMILY` weight 800.
- Logo `reverse` bản ngang nhỏ ở cuối nhóm: cao 64 px ở 9:16, 48 px ở 16:9, cách mascot
  32 px, nằm trong vùng an toàn.
- Logo là asset render-owned, đăng ký giống mascot (`clips/cta/logo.svg`, kind `flourish`,
  `semantic: false`); `youtube_cta` thêm trường `logo_path` (Pydantic + Zod), mặc định
  `clips/cta/logo.svg` để input cũ vẫn parse.

## 7. Ngoài phạm vi

- Vẽ mascot thật (chờ người dùng cung cấp ảnh).
- Intro/outro, câu signature (M6.4), thumbnail, avatar/banner kênh.
- Rig mascot nhiều khớp, lip-sync, mascot dạng video.

## 8. Phối hợp với explain-first Task 7

Task 7 đã commit (`9408a3b`), `video/src` sạch. Triển khai một đợt, trong đó phần Python
(profile, logo, `mascot_asset`, đăng ký logo thẻ cuối, cảnh báo cổng 2) làm trước, phần
`video/src` (font, Zod `logo_path` và `.png`, logo trên thẻ cuối, lật/giới hạn mascot) sau.

## 9. Kiểm thử và nghiệm thu

- Python: logo lặp đúng byte; mọi tọa độ (cộng nửa nét) nằm trong lề 40; bốn biến thể đúng
  màu; profile thiếu `night` hoặc artwork sai hash/không phải PNG RGBA/lệch kích thước bị từ
  chối; `mascot_asset` trả PNG khi có artwork và SVG khi không có; placeholder có
  `aria-label` chứa `placeholder`; không còn `render_phy_logo`; annotation bị chặn khi có artwork; test
  đồng bộ `palette.ts`; input cũ không có `logo_path` vẫn parse.
- Video: Zod nhận `logo_path` và `.png`; thẻ cuối có logo; mascot lật khi ở nửa phải; font
  dùng `FONT_FAMILY`.
- Claude tự xem: logo bốn biến thể, ba pose placeholder, một khung cơ chế 16:9 và 9:16, thẻ
  cuối 9:16 và ảnh duyệt bố cục 16:9 (CTA trong schema chỉ dành cho `vertical_clip`; still ra `.tmp/brand-review/`).
- `python -m pytest -q`, `python -m ruff check src tests tools`, schema export không có diff
  ngoài dự kiến, `pnpm --dir video test`, `pnpm --dir video typecheck`, `git diff --check`.
- README thêm dòng tiến độ trong cùng commit.

## 10. Thiết kế lại toàn bộ (18-10-2026, thay §2 và §5.2–§5.3)

Người dùng loại cả logo hình học tự vẽ lẫn bảng nhận diện cũ, yêu cầu thiết kế mới hoàn toàn.
Phần này **thay thế** §2 (logo) và §5.2–§5.3 (yêu cầu ảnh, placeholder); các mục khác giữ
nguyên.

### 10.1. Logo "lời giải thích đã kiểm chứng"

- **Biểu tượng:** bong bóng thoại vuông bo góc màu `teal`, đuôi nhọn chéo xuống trái, bên
  trong là dấu kiểm `yellow` nét bo tròn. Không còn ghép hình vào từng chữ P/Y/H.
- **Wordmark:** chữ `PYH` lấy outline từ font Be Vietnam Pro ExtraBold (OFL), màu `navy`;
  dòng phụ `PROTECT YOUR HEALTH` cũng lấy outline từ font đó, chữ hoa, giãn chữ nhẹ, màu
  `charcoal`. Path outline được tính sẵn bằng một script trong `tools/`, rồi lưu thành hằng
  số trong generator; lúc chạy không đọc file font.
- **Biến thể:** `horizontal` (biểu tượng + PYH + dòng phụ); `monogram` (ô vuông `navy` bo góc
  chứa biểu tượng, làm avatar kênh); `one_color` (toàn `navy`, dấu kiểm khoét rỗng trong
  bong bóng); `reverse` (chữ `off_white`, biểu tượng giữ màu, dùng trên nền `night`).
- Bản phác đã duyệt: `.tmp/logo-lab/lab.py`.

### 10.2. Mascot (concept B đã duyệt)

- Nhân vật mới do AI tạo (Gamma, 18-10-2026), người dùng chọn concept B: nam trẻ, tóc đen ngắn,
  kính tròn, dáng tròn, áo bomber `teal` tay `navy`, huy hiệu bong bóng thoại vàng trên ngực,
  áo thun trắng, quần navy, giày sneaker kem. Phong cách phẳng, không gradient.
- Ba pose lấy từ sheet concept: `welcome` vẫy tay; `explain` chỉ sang phải; `caution` hai bàn
  tay mở, nét mặt lưỡng lự.
- Theo quyết định của người dùng, bỏ điều cấm "sinh mascot bằng model" của M6.3 **cho mascot**.
  Các ranh giới khác giữ nguyên: không áo blouse, không ống nghe, không chữ hay claim y khoa.
- Ảnh gốc `.tmp/mascot-lab/concept-b.jpg` không commit. Chỉ commit ba PNG RGBA đã tách nền
  trong `assets/brand/mascot/`, khai báo trong `mascot.artwork` với SHA-256. `creator`/`license`
  ghi rõ nguồn: ảnh tạo bằng AI theo yêu cầu của PYH.
- Placeholder SVG chỉ còn là đường dự phòng khi thiếu artwork.

## 11. Mascot kiểu người dẫn (18-10-2026, thay §5.5 và phần mascot của §6)

Tham khảo kênh Vui Vẻ (YouTube `83yfLZpp2U4`, `lzPkXdsqogc`), người dùng đã duyệt cả ba hướng.

### 11.1. Viền nướng sẵn vào PNG

- Bỏ đĩa tròn `off_white` sau mascot ở mọi nơi (`MascotGuide`, thẻ cuối).
- Mỗi pose có hai lớp viền tính trên kênh alpha: viền trong màu `night`, dày khoảng 1,6% chiều
  cao nhân vật; viền ngoài `off_white` mảnh hơn (khoảng một nửa viền trong) kiểu sticker.
  Đặt trên nền sáng hay tối thì nhân vật đều tách khỏi nền. Không dùng CSS/SVG filter.
- Script `tools/build_mascot_artwork.py` (Pillow, xác định) đọc ảnh gốc chưa viền ở
  `assets/brand/mascot/source/<pose>.png`, rồi ghi `assets/brand/mascot/<pose>.png`. Ảnh được
  cắt sát theo nhân vật cộng viền và một lề nhỏ, ba pose cùng kích thước canvas. Không bắt buộc
  canvas vuông; cạnh ngắn vẫn ≥ 768. Cập nhật SHA-256 trong profile.

### 11.2. Vị trí người dẫn, cắt ở cạnh dưới

- Mascot đứng ở một bên khung, đối diện vùng nội dung, bị cắt ngang đùi: chỉ thấy khoảng 65%
  phía trên của nhân vật.
- **16:9:** đường cắt là cạnh dưới khung. Phần nhìn thấy cao khoảng 38% chiều cao khung.
- **9:16:** đường cắt là mép trên của dải phụ đề (dải đáy dành cho phụ đề và giao diện
  TikTok). Phần nhìn thấy cao khoảng 30% chiều cao khung, nằm ngoài cột nút bên phải.
- Ảnh luôn hướng phải. Đứng ở nửa phải khung thì lật ngang để nhìn vào nội dung (đã có).
- Chuyển động: spring trồi lên từ đường cắt, nhấp nhô nhẹ; không để lộ khoảng trống dưới
  đường cắt.
- Giới hạn 30%/24% của §5.5 được thay bằng các mức trên. Vẫn không che phụ đề, source marker
  hay vật thể đang hoạt họa chính.

### 11.3. Nền sáng cho cảnh có mascot

- Cảnh cơ chế (`MechanismScene` và các cảnh dùng nó) có mascot thì dùng nền `off_white`;
  không có mascot thì giữ nền `night`. Chữ và nét trên cảnh phải đủ tương phản với nền sáng.
- Thẻ cuối giữ nền `night`. Mascot `welcome` toàn thân, không đĩa tròn, cao khoảng 30% khung
  9:16; viền off_white giúp nhân vật nổi trên nền tối.

### 11.4. Để sau

Thêm biểu cảm (ngạc nhiên, suy nghĩ, đắc ý) từ cùng nhân vật B bằng AI. Việc này chưa làm
trong đợt này.
