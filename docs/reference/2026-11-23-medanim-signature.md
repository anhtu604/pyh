# R5.4 — Hoạt ảnh y khoa làm đặc trưng kênh PYH

Ngày khảo sát: **2026-11-23**, metadata YouTube lấy khoảng 22:59–23:04, UTC+7. Nhánh `r5-4-medanim-signature`; không sửa code, chạy xưởng, render Remotion/Blender, gọi API trả phí/NCBI hoặc commit.

## 1. Quyết định đề xuất và giới hạn bằng chứng

**Chọn rig 2D vector Remotion làm nền; thêm chiều sâu bằng lớp có kiểm soát; dành 3D cho quan hệ không gian thật sự cần thiết.** Đặc trưng cần xây là nhìn thấy *một tác nhân gây ra một biến đổi*: men vượt màng, vi khuẩn bị bao kín, dòng máu bị chặn. Zoom một ảnh hoặc bật thêm nhãn chưa đủ tạo dấu ấn này.

- Đã đọc bàn giao, `CLAUDE.md` §5, kiểm toán `E:/Protect Your Health/docs/reference/2026-11-23-factory-gap-audit.md` §2/§4; không kiểm toán lại pipeline. `RTK.md` không có tại gốc checkout; kiểm toán trước cũng ghi thiếu file này.
- Đã mở ba ảnh `E:/Protect Your Health/cache/r5-reference/{pyh_sheet1.jpg,pyh_sheet2.jpg,yt_sheet1.jpg}`. Giữ lối kể chuyện đời thường của Xấu Vê Nờ cho mở bài/cầu nối; không lấy nó làm chuẩn giải phẫu.
- Đã tải đoạn ngắn của **7 kênh, mỗi kênh 1 video**, xem đủ 6 khung/đoạn; thêm 6 khung MP4 gan có sẵn. Đây là mẫu chọn có chủ đích, không phải thống kê toàn kênh hay bằng chứng hoạt ảnh gây tăng view.
- **Không xem phát liên tục, không nghe âm thanh.** Các kết luận động dựa trên biến đổi giữa khung và code khi có. Số thực thể *đang chuyển động đúng cùng thời điểm*, thời lượng đầy đủ một trường đoạn và nhạc/SFX: **không đo được** từ cách quan sát này. Bảng dưới ghi rõ phần thay thế quan sát được, không biến ước đếm thành phép đo đồng thời.
- Thời gian làm/render/token/chi phí sản xuất tương lai chưa benchmark trên RTX 3060 12GB; các con số §5 là **dự toán công hoặc trần ngân sách thử nghiệm**, không phải kết quả đo.

## 2. Chuẩn mẫu đã xem thật

### 2.1. Cách lấy và đọc bằng chứng

Gốc tư liệu `C = E:/pyh-r5-4/cache/r5-medanim/`. Mỗi thư mục kênh có `selected.json` chứa metadata trực tiếp, `window.json`, `probe.json`, `evidence.json`, log tải và `scenes.log`. Chỉ dùng view từ `selected.json`, không trộn số đếm trang TED hay kết quả tìm kiếm cũ.

Lệnh tương đương đã dùng: `yt-dlp -f "bv*[height<=480]+ba/b[height<=480]" --download-sections "*START-END"`; khi luồng HTTPS lỗi, dùng HLS `-f 230`. FFprobe kiểm tra có luồng video; không coi exit 0 của yt-dlp là tải thành công (mẫu Nucleus cũ từng ra file rỗng).

FFmpeg trích tại **t=0,3,6,9,12,15 giây của file tải** bằng `-ss t -frames:v 1`; phát hiện cảnh bằng `select='gt(scene,0.25)',showinfo`. `contact.jpg` chỉ ghép lại 6 JPG, không dựng hoạt ảnh mới. `key_01.jpg`…`key_06.jpg` là bộ khung cuối cùng đã xem.

Tải theo section có thể mang preroll/keyframe; cửa sổ nguồn dưới đây là **cửa sổ yêu cầu**, không cam kết source time chính xác từng frame. Đặc biệt Nucleus `gerd.webm` dài container 23s, video start_time 1,646s; không suy ra shot 18s từ tham số tải. Ký hiệu “15s lấy mẫu” chỉ khoảng từ khung đầu đến khung cuối, không chứng minh không có chớp/cắt giữa hai mẫu.

Đã yêu cầu phụ đề bằng yt-dlp; HTTP 429 làm thiếu một phần. Có VTT tiếng Anh: Kurzgesagt, Osmosis, TED-Ed và **`nucleus/gerd.en.vtt`**. Armando, Zack, HayHo: chưa lấy được phụ đề. Không chép lời thoại. Không dùng VTT video xơ vữa đã loại để mô tả video GERD.

### 2.2. Danh mục — view tại thời điểm lấy metadata, ngày là ngày đăng YouTube

| ID / kênh, phong cách | Video, link gốc | View | Ngày đăng | Cửa sổ yêu cầu; nguồn cuối; độ phân giải |
|---|---|---:|---|---|
| N / Nucleus Medical Media — 3D y khoa | [What Causes GERD?](https://www.youtube.com/watch?v=zh-9RaSCMxQ) | 17.681.389 | 2022-04-05 | 00:35–00:53; `nucleus/gerd.webm`; 854×480 |
| Z / Zack D. Films — 3D dọc | [How Mouth Breathing Can Change Your Face](https://www.youtube.com/watch?v=2ll9ClpJ3x8) | 10.370.082 | 2026-11-22 | 00:03–00:21; `zack/sample.mp4`; 240×426 |
| O / Osmosis from Elsevier — 2D minh họa/viết dần | [Inflammation](https://www.youtube.com/watch?v=1BpV6p8pXDg) | 285.737 | 2025-02-11 | 00:50–01:08; `osmosis/sample.mp4`; 854×480 |
| K / Kurzgesagt — vector phẳng | [The Immune System Explained I – Bacteria Infection](https://www.youtube.com/watch?v=zQGOcOUBi6s) | 54.683.731 | 2014-07-01 | 01:52–02:10; `kurzgesagt/mechanism.mp4`; 854×480 |
| T / TED-Ed, animator Cinematic — 2D nhân vật/lớp | [How do vaccines work?](https://www.youtube.com/watch?v=rb7TVW77ZCs) | 3.571.168 | 2015-01-12 | 00:45–01:03; `teded/sample.mp4`; 854×480 |
| A / Armando Hasudungan — vẽ tay thật | [Part I – Inflammation](https://www.youtube.com/watch?v=cdCh4_Ckor0) | 1.063.233 | 2013-05-01 | 05:30–05:48; `armando/mechanism.mp4`; 640×360 |
| V / HayHo — tiếng Việt, ảnh thật + minh họa 3D | [Hệ miễn dịch hoạt động bảo vệ cơ thể như thế nào?](https://www.youtube.com/watch?v=jEd-MtgdMf0) | 511.198 | 2020-09-27 | 01:30–01:48; `viet/hls.mp4`; 640×360 |

Nguồn sơ cấp cho nhận diện tác giả: các link YouTube trong bảng; [TED-Ed ghi credit animation](https://ed.ted.com/lessons/how-do-vaccines-work-kelwalin-dhanasarnsombut/digdeeper). HayHo là ví dụ bản địa về cách dẫn bằng cơ thể/triệu chứng; **chưa xác minh họ tự sản xuất hay có quyền đối với từng cảnh 3D**. Zack là chuẩn nhịp/camera, chưa được dùng làm nguồn chứng minh kết luận lâm sàng về phát triển hàm.

### 2.3. Số đo và quan sát hình

Quy ước: chữ đếm theo đơn vị cách trắng, bỏ watermark/credit. “Nhóm biến đổi” là vật thể/cấu trúc thấy thay đổi giữa mẫu, **không phải số vật thể chuyển động đồng thời**. Hạt nhiều không đếm thành con số chính xác khi không theo dõi được danh tính.

| Mẫu | Khoảng hoạt ảnh quan sát | Nhóm biến đổi nhìn thấy; số đồng thời | Chữ/nhãn trên khung cụ thể | Dẫn mắt, màu, chuyển cảnh |
|---|---|---|---|---|
| N | Cả 6 mẫu trong khoảng 15s là cùng mặt cắt thực quản–dạ dày; độ dài trường đoạn đầy đủ: không đo được | 1 khối thức ăn đổi vị trí/hình dạng; camera đổi cỡ cảnh. Đồng thời: không đo được | `key_04`: 1 nhãn, 3 đơn vị “Gastroesophageal reflux (GER)” | Cắt bỏ thành trước để thấy lòng ống; mô hồng trên nền xanh tối, thức ăn vàng; đối tượng lớn, nhãn góc, camera giữ liên hệ cơ quan |
| Z | 6/6 mẫu là 3D trong khoảng 15s; shot riêng không đo được | Mặt → lưỡi/hàm → đường thở; mũi tên lực. Đồng thời: không đo được | `key_06`: 2 đơn vị phụ đề; không có bảng nhãn giải phẫu | Camera xuyên mặt vào mặt cắt, rồi đổi góc; da/xương gần thật, nền cyan; đặt cơ chế trong một người cụ thể |
| O | 6/6 mẫu thuộc một bảng 2D trong khoảng 15s; chuyển động sinh học của hình vi khuẩn không thấy rõ | Chữ tăng dần; hình chính gần như giữ nguyên. Đồng thời: không đo được | `key_06`: ≥25 đơn vị, nhiều dòng; không tính nét chữ dở | Nền trắng, chữ đỏ nâu, vi khuẩn vàng; vẽ/viết thêm thay vì biến đổi vật thể. Có ích cho học chuyên môn, không phải đích “wow” PYH |
| K | 6/6 mẫu là hoạt ảnh trong khoảng 15s; ít nhất 3 bố cục khác nhau; độ dài từng shot không đo được | Đại thực bào, nhiều vi khuẩn, túi/màng và hạt; hình bao kín rồi mục tiêu biến dạng. Đồng thời: không đo được | `key_05`: khoảng 7 đơn vị ở tiêu đề/bong bóng/nhãn; `key_01`: 1 nhãn thước | Nhân hóa vi khuẩn, đổi từ ngoài vào trong tế bào rồi trở lại mô; vòng đỏ/vàng, vi khuẩn xanh mint; dùng màu để giữ danh tính xuyên tầng |
| T | Hoạt ảnh có ở cả 6 mẫu/15s, chuyển từ vi mô sang người và danh sách triệu chứng | 4 biểu tượng xanh cyan thấy đổi vị trí giữa `key_01–02`; sau đó mặt/tay và dấu kiểm đổi trạng thái. Đồng thời: không đo được | `key_03`: 7 đơn vị, gồm tiêu đề 3 + 4 mục một từ | Màu mận/đỏ trong mô, chuyển xanh nền khi về người; gắn cơ chế với biểu hiện đời thường; cuối đoạn có lớp chồng hình |
| A | 6/6 mẫu là quay bảng vẽ trong khoảng 15s; không thấy tế bào tự biến dạng giữa mẫu | 1 bàn tay/cây bút; camera/khung giấy đổi vị trí; sinh vật vẽ đứng yên. Đồng thời: không đo được | `key_03`: ≥10 cụm nhãn; tổng chữ không đo được vì chữ tay nhỏ | Vẽ bản đồ mô–mạch, tô đỏ mạch và xanh mạch bạch huyết; mũi tên nối quan hệ; giữ định hướng tốt nhưng tải chữ lớn |
| V | `key_01–03,05` là ảnh người; `key_04,06` là mặt cắt 3D mũi/dạ dày; độ dài liên tục từng đoạn 3D: không đo được | Ảnh/camera/hiệu ứng hạt thay đổi; chuyển động cơ chế trong từng đoạn 3D không đo được | `key_04`: 1 nhãn “DỊCH NHẦY”, 2 đơn vị; `key_06`: không thấy nhãn chính | Từ bộ phận quen thuộc → mặt cắt bên trong; mô hồng, dịch vàng/xanh; ghép ảnh thật và cơ chế dễ vào đề, phong cách chưa đồng nhất |

**Scene detect không thay người đọc cảnh:** với ngưỡng 0,25, log phát hiện T tại t≈4,880 và 16,934s; A tại 4,400/16,640/17,200s; V tại 11,111/13,146s. N/K/O/Z có 0 điểm vượt ngưỡng trong lần dò; không có nghĩa không chuyển shot (Z/K đổi bố cục rất rõ). Đây là mốc ứng viên của file cục bộ, không phải source time hay thống kê nhịp cắt cả video.

**Nhạc/SFX:** cả 7 mẫu **không đo được/không được nghe đánh giá**. FFprobe chỉ chứng minh luồng âm thanh có/không, không chứng minh có nhạc hay loại SFX. A/O/V bản dùng trích hình là luồng video không âm thanh; K/T/Z/N có audio. Không suy diễn cảm giác âm nhạc từ contact sheet hoặc view.

### 2.4. Đường dẫn khung đã xem

Mỗi hàng dưới liệt kê đủ 6 file, đều dưới `E:/pyh-r5-4/cache/r5-medanim/`; không đưa vào Git.

| Thư mục | Các khung JPG cuối cùng | Tương ứng t trong file |
|---|---|---|
| `nucleus/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `zack/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `osmosis/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `kurzgesagt/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `teded/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `armando/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `viet/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 0,3,6,9,12,15s |
| `pyh/` | `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` | 2,10,18,26,30,38s của MP4 gan |

Các thư mục còn có `contact.jpg` ghép lại chính các JPG trên. Ví dụ đường dẫn đầy đủ: `E:/pyh-r5-4/cache/r5-medanim/kurzgesagt/key_05.jpg`.

## 3. Ma trận lĩnh vực × cách thể hiện

“Mẫu tốt nhất” dưới đây nghĩa là phù hợp nhất **trong các đoạn đã quan sát**. Không có mẫu trực tiếp thì ghi thiếu; không suy rộng một đoạn miễn dịch thành đã khảo sát mô phôi/pharmacology. Độ khó là dự toán làm rig dùng lại, không mức độ khó của kiến thức y khoa.

| Lĩnh vực | Mẫu/điểm học | Kỹ thuật ưu tiên | Khó; điểm cần giữ đúng |
|---|---|---|---|
| Giải phẫu | N: mặt cắt còn ngữ cảnh cơ quan; Z: camera xuyên tầng | 3D Blender cho xoay/cắt lớp; vector cho sơ đồ đơn giản | Cao với 3D; liên tục vị trí, bên trái/phải, tỷ lệ tương đối |
| Sinh lý | N: vật chất đi qua lòng ống; Z: hình liên hệ đường thở | Vector theo đường dẫn; 2.5D nhiều lớp cho thành ống co giãn | Vừa; chiều dòng, ranh giới khoang, chức năng van |
| Sinh lý bệnh | K: tác nhân vào → bị nuốt → biến đổi; N cho bối cảnh GERD | Vector có trạng thái, mask và biến dạng; 3D khi cần không gian | Vừa–cao; tác nhân phải gây đúng hậu quả, không chỉ đổi màu |
| Giải phẫu bệnh | Chưa có mẫu mô bệnh học thật trong 7 đoạn; N chỉ gợi cách cắt lớp | Ảnh mô học thật được cấp phép + khoanh vùng; vector đối chiếu bình thường/bệnh | Cao; phải ghi loại nhuộm/thang đo khi có, không giả ảnh AI là mô bệnh học |
| Mô phôi | Chưa có đoạn phôi phát triển được xem; K chỉ gợi cách giữ danh tính qua biến dạng | Vector morph cho quá trình; 2.5D/3D cho gấp/di chuyển mô; ảnh mô học thật có phép | Cao; trình tự thời gian, nguồn gốc tế bào, vị trí lớp mầm |
| Vi sinh | K: khác biệt tác nhân/đại thực bào bằng hình và màu | Vector vi khuẩn phân đôi, virus bám–vào–tháo vỏ; lớp parallax để tạo chiều sâu | Vừa; không gộp vi khuẩn/virus thành một cơ chế |
| Miễn dịch | K tốt nhất cho hành động; T tốt cho nối cơ chế với người | Rig tế bào/túi/kháng thể có hành động, không lạm dụng nhân hóa | Vừa–cao; receptor/ligand, trong–ngoài màng và nhánh đáp ứng |
| Dược lý | Chưa có đoạn thuốc–đích được xem; mượn nguyên tắc giữ danh tính của K | Vector ligand–receptor, enzyme–substrate, đường nồng độ có nguồn | Vừa–cao; chọn lọc/đối kháng khác nhau; không vẽ “thuốc quét sạch” tùy tiện |

2.5D chỉ tạo chiều sâu/camera khi hình đã chia lớp; một ảnh FLUX được pan/zoom không thay thế được dòng chảy, phagocytosis hay morph mô. AI video không được chọn trong ma trận vì chưa có cấu hình local 12GB đã xác nhận hoặc chi phí dịch vụ đủ rõ trong khảo sát này.

## 4. Thư viện hiện có — giữ nền, thay cách diễn hành

Đã đọc `library/medanim/*/animation.yaml`, timeline `video/src/medanim/{liverEnzymeLeak,alveolarGasExchange,atheroscleroticPlaqueRupture,macrophagePhagocytosis}.ts`, kiểm phần chuyển động trong component `MedAnim*.tsx`, `ScientificHepaticArtwork.tsx`, catalog domain/workflows. Đã mở 7 preview PNG và PNG tiểu thùy Servier; đọc XML SVG màng thực bào/phế nang để kiểm hình là asset riêng, không coi ảnh minh họa vốn có là rig biến dạng.

MP4 có sẵn được đọc: `E:/Protect Your Health/cache/medanim/liver-enzyme-leak/liver-enzyme-leak-r2-16x9.mp4`; FFprobe xác nhận 1920×1080. Khung tại §2.4. Không tìm được MP4 riêng tương ứng ba hoạt ảnh còn lại trong lượt tìm theo tên tại `cache/` và MP4 ở `projects/`; không khẳng định toàn ổ đĩa không có. Preview/code không chứng minh chuyển động cuối cùng đã đạt.

Đánh giá bằng mô tả thay cho điểm số “đúng” giả định: đúng y khoa chưa được tái thẩm định y văn trong nhiệm vụ này. `medical_audit.passed` trong YAML cũng không đồng nghĩa đã qua cổng bác sĩ hiện hành.

| Hoạt ảnh | Đẹp/đọc rõ từ PNG và MP4 sẵn | Động theo code; so mẫu | Đúng: giới hạn cần giữ | Giữ / bỏ hoặc thay |
|---|---|---|---|---|
| `liver-enzyme-leak` | Hình gan/tiểu thùy/tế bào có nguồn rõ; preview B4 có nhiều khung chú giải cạnh nhau, phần trái mờ chiếm diện tích; MP4 cho thấy tiến triển khác bản slide sản phẩm | Có tuyến máu/mật, 20 dot enzyme trong khai báo, mask màng/ty thể, enzyme vào xoang; gần nguyên tắc “vật vượt ranh giới” của K nhưng ít liền mạch hơn | Phân biệt men tăng và chức năng gan; không biến m-AST thành thước đo nặng/nhẹ phổ quát. Preview ghi rõ mô hình gan chuột thiếu máu | Giữ asset/tuyến dòng/định vị/cấu hình dọc; thay hộp giải thích bằng diễn hành một khoang lớn; không tái dùng nguyên tế bào cho mọi câu về gan |
| `alveolar-gas-exchange` | B3 phân khoang rõ, chữ lớn; B4 lại có hình toàn cảnh bên trái + sơ đồ bên phải + nhiều câu lặp; nhãn song ngữ chiếm chỗ | Code có 5 hồng cầu, 6 hạt O₂, 5 hạt CO₂; dịch kẽ dày lên và đổi đích hạt; đây là chuyển động cơ chế thật, không chỉ ảnh tĩnh | Icon tế bào phế nang lặp dễ khiến người xem hiểu toàn mặt trao đổi gồm tế bào dày giống nhau; cần duyệt hình type I/type II và cách đơn giản hóa phù | Giữ phân khoang/chiều O₂–CO₂; thống nhất phong cách icon, bỏ ảnh đối chiếu dư và nhãn Latin khi không phục vụ người xem |
| `atherosclerotic-plaque-rupture` | Mảng/bao xơ nhìn ra được; foam cell, collagen, tiểu cầu nhiều phong cách; hình collagen xoắn dễ gây hiểu sai tỷ lệ; vòng focus lớn che nhiều chi tiết | Có LDL xuyên lớp, monocyte di chuyển, foam cell xuất hiện, mask vỡ bao, tiểu cầu/fibrin kết tập; 4 beat 8s + credit 3s theo timeline | Không mặc định mọi hẹp đều nứt vỡ hoặc mọi huyết khối đều bít hoàn toàn; preview B4 chưa tự chứng minh lòng mạch đã bị bít như lời | Giữ chuỗi nhân quả/asset có phép; thay crossfade monocyte→foam bằng tăng lipid trong cùng tế bào; cho dòng máu giảm/ngừng nhìn thấy được khi mô tả tắc |
| `macrophage-phagocytosis` | B2 tách hai hình lớn nhưng cùng vi khuẩn không theo được xuyên hai hình; B4 có thêm thẻ chu trình tạo lặp ý; Latin/ROS/enzym dồn chữ | Code có vi khuẩn dịch vào, đường actin vẽ dần, vòng seal và mask phân giải; chưa phải màng gốc thực sự ôm và khép liên tục như kỳ vọng từ K | YAML còn `opsonin-receptor-vs-direct-prr` cần bác sĩ xác nhận đơn giản hóa; không mô tả PRR trực tiếp như mọi kiểu thực bào | Giữ chuỗi nhận diện→bao→hợp nhất→tiêu; thay hai sơ đồ bằng một tế bào/vi khuẩn liên tục, bỏ thẻ chu trình lặp, làm rõ màng túi kín |

Preview đã mở: `library/medanim/alveolar-gas-exchange/previews/{b3,b4}.png`; `atherosclerotic-plaque-rupture/previews/{b2,b4}.png`; `macrophage-phagocytosis/previews/{b2,b4}.png`; `liver-enzyme-leak/previews/b4-mild.png`; thêm PNG tiểu thùy và các khung MP4 gan. Không suy diễn các preview chưa mở.

**Phân biệt hai đường hình gan:** `ScientificHepaticArtwork.tsx` dùng chung ảnh tế bào cho nhiều subject, có hồng cầu/dot/đường xơ nhưng phần ảnh nền vẫn nguyên. Không đồng nhất component này với composition thư viện `MedAnimLiverEnzymeLeak`. Kiểm toán trước đã chỉ ra sản phẩm bị bảng/hộp chiếm thời lượng; bốn composition standalone có chi tiết động hơn, song vẫn cần giảm UI quanh hình.

Catalog hiện chỉ nhận anatomy/physiology/pathophysiology/pathology/microbiology; immunology, embryology, pharmacology chưa là category riêng. Ba mục ngoài gan khai báo `portrait: null`; gan có geometry riêng 9:16. Đây là khoảng thiếu quan sát được, không phải đề nghị sửa schema trong phiên này. Workflow lọc bản duyệt theo hash; không bật lại hay duyệt thay bác sĩ.

## 5. Ba phương án sản xuất trên RTX 3060 12GB

### 5.1. So sánh để chọn

Mốc dự toán dưới đây giả định clip cơ chế 15–25s, 3–4 hành động, đã có brief y khoa/asset hợp lệ; “công” gồm kiểm hình và một vòng sửa thông thường, chưa gồm chờ bác sĩ. Một ngày công = 8 giờ. Trần token dùng để giới hạn thử nghiệm, không phải token đã tiêu hay cam kết chất lượng.

| Phương án | Chất lượng đích và khung đối chiếu | Công dự toán cho hoạt ảnh mới | Render trên máy này | Token/tiền; ai làm | Rủi ro y khoa/giấy phép |
|---|---|---|---|---|---|
| **A. Rig vector 2D Remotion**: tế bào/màng/túi, dòng máu, hạt, vi khuẩn, virus, kháng thể; state/action có tham số | Hướng tới hành động rõ như K `key_04–05`, phân khoang như preview phế nang; không hứa đạt toàn bộ mỹ thuật Kurzgesagt | Bộ rig nền 3–5 ngày; một clip mới 4–8h, biến thể sau khi rig ổn 1–3h | **Không đo được**; mục tiêu nghiệm thu thử sau này ≤2 phút/clip 20s 1080p30. Remotion còn phụ thuộc CPU/SVG/font, không suy từ GPU | `gemini-4-neon-medium` dựng hình/TS; `gpt-6.1-sol` dự phòng khi lỗi lặp. Trần thử 2 lượt, tổng ≤20k input + 8k output/clip. Không API hình/video; tiền CLI theo gói hiện có, điện chưa đo | Thấp–vừa nếu trạng thái/đường đi cố định; hình asset không tự đúng cơ chế. Tự vẽ hoặc PD/CC0/CC BY được ghi công từng file |
| **B. Clip 3D Blender dựng sẵn**: xoay, cắt lớp, đường đi qua cơ quan, xuất clip tái dùng | Học mặt cắt N `key_03–06`, xuyên tầng Z `key_02–04`; không hứa đạt da/tóc/ánh sáng chất lượng studio | Chuẩn scene/ánh sáng/camera 3–7 ngày; clip mới 1–3 ngày nếu model sạch sẵn; model tự tạo có thể vượt dự toán | **Không đo được**; ưu tiên Eevee, 1080p30, ít vật liệu/texture. Trần thử sau này ≤15 phút/20s; Cycles chưa có ngân sách đo | Neon viết script Blender theo template + người biết 3D kiểm. Sol chỉ xử lý script khó; trần 2 lượt ≤30k input + 12k output. Local không phí render cloud; công người cao hơn A | Sai cắt lớp/đường đi/tỷ lệ; atlas không có sẵn rig sinh lý bệnh. Z-Anatomy/BodyParts3D không đi qua allowlist hiện hành; chọn model tự tạo/CC0/CC BY hoặc giữ trạng thái chưa bật |
| **C. FLUX.2 klein 4B + 2.5D + lớp vector cơ chế** | Chất liệu/chiều sâu và cầu nối người→cơ thể như T `key_02–03`, V `key_04`; chỉ tương đồng bố cục, không khẳng định mẫu dùng AI/parallax | Chuẩn style/lớp 1–2 ngày; clip mới 4–8h gồm chọn ảnh, tách lớp, vá vùng khuất; biến thể 2–4h | Sinh ảnh + compositing: **không đo được**. Chỉ chạy riêng GPU, dùng đường offload hiện có; không lấy quảng cáo model làm thời gian RTX 3060 | Neon làm brief/kiểm lớp, local FLUX sinh ảnh, vector Remotion điều khiển cơ chế. Trần 2 candidate, 2 lượt agent ≤16k input + 6k output. Điện/khấu hao/công tách lớp chưa định giá | Cao nếu ảnh AI tự quyết cấu trúc; chỉ dùng nền/bối cảnh hoặc hình y khoa được kiểm từng cấu trúc. Đúng variant klein 4B Apache-2.0; không suy giấy phép cho mọi FLUX |

Tên model trên là đề xuất phân công theo `CLAUDE.md`, **không gọi model/agent trong khảo sát này**. Bác sĩ kiểm ý nghĩa sinh học; reviewer hình kiểm pixel/định vị; không dùng model mạnh hơn mặc định để bù một brief hành động thiếu rõ. Giá token theo gói CLI thực dùng chưa có hóa đơn/bảng giá đã xác minh: **không đo được**, không quy đổi USD giả.

### 5.2. Giấy phép và điều kiện thực thi

- A: [Servier hiện công bố CC BY 4.0](https://smart.servier.com/); bản Bioicons lưu trong thư viện có asset ghi CC BY 3.0, phải giữ đúng provenance của bản tải, không đổi nhãn hàng loạt. [Reactome quy định Icon Library/illustration CC BY 4.0](https://reactome.org/license). Với NIAID/DBCLS/Bioicons kiểm trang và metadata **từng asset**, không suy toàn kho cùng giấy phép; báo cáo không tái xác minh toàn bộ asset hiện có.
- B: [License.txt chính thức Z-Anatomy](https://github.com/Z-Anatomy/Models-of-human-anatomy/blob/master/License.txt) ghi CC BY-SA 4.0, nguồn BodyParts3D BY-SA 2.1 Japan; còn ghi tai trong NC-SA và kidney NC. Vì vậy không nhập gói nguyên trạng vào allowlist hiện có (PD/CC0/BY3/BY4). Không gộp giấy phép phần mềm Blender với giấy phép model.
- Tài liệu `z-anatomy-license-check.md` nêu rủi ro SA, nhưng không nên coi “toàn bộ mọi video có một đoạn render đều tự động mang SA” là kết luận đã xác lập: phạm vi adaptation/collection tùy trường hợp. [FAQ chính thức Creative Commons](https://creativecommons.org/faq/#when-is-my-use-considered-an-adaptation) là căn cứ phân biệt; dù vậy chính sách PYH đang chặn SA nên B dùng Z-Anatomy vẫn **chưa sẵn sàng**.
- C: code `src/healthvideo/visuals/flux.py` chốt `black-forest-labs/FLUX.2-klein-4B`, kiểm variant/weights; [model card chính thức ghi Apache-2.0](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B). Model license không chứng nhận cấu trúc y khoa hay đảm bảo mọi hình đầu ra không vướng quyền khác.
- Không đề xuất AI video như phương án thứ tư: chưa xác nhận pipeline local 12GB/giấy phép/chi phí trong nhiệm vụ này. Video/khuôn hình của kênh mẫu chỉ là tư liệu xem nội bộ, không được coi là tài sản mở để cắt ghép vào PYH. [Nucleus phân biệt quyền YouTube và giấy phép NMAL](https://nmal.nucleusmedical.media/atherosclerosis-in-coronary-artery-cross-section/faq).

### 5.3. Cách làm A để tạo dấu ấn thay vì thêm một bộ slide

1. Mỗi brief xác định **một câu hỏi, tác nhân, khoang, hành động, kết quả**, kèm điều giản lược phải báo bác sĩ. Ví dụ “men ở trong tế bào → màng tăng tính thấm/tổn thương → men vào máu”; không mặc định phải vẽ lỗ rách lớn cho mọi tổn thương.
2. Rig có anchor và lớp thật: membrane/cytosol/nucleus/vesicle/receptor/particle; action bám–vào–bao–khép–hợp nhất–thoát–phân giải; màu/danh tính theo cùng thực thể qua các shot. Hồng cầu chạy nền không thay thế hành động trọng tâm.
3. Đề xuất mục tiêu thiết kế cho một clip: 3–4 beat, mỗi beat 3–6s, có một biến đổi hoàn chỉnh nhìn thấy; 1–2 nhãn cần thiết cùng lúc, câu giải thích chuyển về lời đọc. Đây là **chuẩn đề xuất**, không phải trung bình đã đo của bảy kênh.
4. Tạo bố cục riêng 16:9/9:16 ngay từ rig: giữ tác nhân, đường đi và nhãn trong khung; không crop cơ chế ngang thành clip dọc. Học cấu hình portrait gan, bổ sung cho ba rig còn thiếu ở một brief triển khai khác.
5. Mẫu nghiệm thu sau này phải xem MP4 liên tục và nghe âm thanh, kiểm tắt tiếng còn hiểu hành động, rồi đối chiếu nhãn/lời. Đo wall time/token/candidate thật trước khi nâng dự toán thành SLA. Phiên này không thực hiện bước dựng/duyệt đó.

## 6. Thư viện ưu tiên — 26 hoạt ảnh lõi

Thứ tự là **ước tính biên tập về tần suất tái dùng**, không phải số lần tìm kiếm hay analytics kênh đã đo. Ưu tiên chủ đề tim mạch/chuyển hóa/hô hấp/gan–thận, phù hợp bối cảnh bệnh không lây nhiễm tại Việt Nam theo [WHO Việt Nam](https://www.who.int/vietnam/news/detail/15-12-2025-viet-nam-unites-to-tackle-top-causes-of-disease-and-death); bổ sung nhiễm trùng theo [ưu tiên WHO Việt Nam](https://www.who.int/vietnam/our-work/managing-communicable-and-noncommunicable-diseases). Thứ hạng cụ thể là đề xuất của người lập báo cáo, không suy từ gánh nặng bệnh thành tần suất dùng chính xác.

| Ưu tiên | Lõi: hành động bắt buộc nhìn thấy | Tái dùng cho chủ đề | Rig/kỹ thuật; khó |
|---:|---|---|---|
| 1 | Viêm: tổn thương → tín hiệu → bạch cầu rời mạch | Nhiễm trùng, da, khớp, gan, đường thở | Mạch+tế bào+hạt; vừa |
| 2 | Co/giãn tiểu động mạch → đổi lòng mạch và dòng | Huyết áp, muối, stress, thuốc | Thành mạch biến dạng; vừa |
| 3 | LDL lưu giữ dưới nội mô → tế bào bọt → mảng | Mỡ máu, tim mạch, đột quỵ | Nâng rig xơ vữa có sẵn; vừa |
| 4 | Bao xơ vỡ → tiểu cầu/fibrin → dòng bị cản | Nhồi máu, đột quỵ, thuốc chống huyết khối | Tách biến thể rig xơ vữa; vừa–cao |
| 5 | Insulin gắn receptor → tăng đưa glucose vào tế bào | Đái tháo đường, vận động, kháng insulin | Receptor+transporter; vừa |
| 6 | Mỡ tích trong tế bào gan → biến đổi cấu trúc | Gan nhiễm mỡ, béo phì, chuyển hóa | Cell+giọt lipid; vừa |
| 7 | Men rời tế bào tổn thương → theo máu ra xét nghiệm | Men gan, rượu, thuốc/thảo dược | Nâng rig gan có sẵn; vừa |
| 8 | Thông khí + O₂/CO₂ qua hàng rào máu–khí | Hút thuốc, viêm phổi, COPD, vận động | Nâng rig phế nang; vừa |
| 9 | Hàng rào lọc cầu thận giữ tế bào/protein, cho dịch lọc qua | Bệnh thận, đái tháo đường, huyết áp | Mạch+màng lọc; cao |
| 10 | Ống thận tái hấp thu nước/điện giải | Mất nước, muối, lợi tiểu | Lòng ống+transporter; cao |
| 11 | Nhung mao hấp thu dưỡng chất qua tế bào vào dòng vận chuyển | Ăn uống, đường huyết, thiếu chất | Màng+đường đi riêng từng chất; vừa |
| 12 | Acid/dịch dạ dày qua vùng nối khi hàng rào chống trào ngược suy | Trào ngược, ăn đêm, ợ nóng | 2D thành ống/2.5D; vừa |
| 13 | Đại thực bào bao kín → túi hợp nhất → mục tiêu phân giải | Nhiễm trùng, vaccine, viêm | Nâng rig thực bào; vừa–cao |
| 14 | Virus bám–vào–tháo vỏ–nhân bản trong tế bào | Cúm, viêm gan, vaccine | Cell+virus, biến thể theo virus; cao |
| 15 | Vi khuẩn tăng trưởng và phân đôi | Vệ sinh, ngộ độc thực phẩm, kháng sinh | Vector morph; vừa |
| 16 | Thuốc/ligand vào đích: kích hoạt hoặc chặn | Thuốc huyết áp, dị ứng, hen | Receptor theo đích; vừa |
| 17 | Đường thở co thắt + nhầy → hẹp lòng và cản khí | Hen, COPD, dị ứng | Thành ống+dịch+luồng; vừa |
| 18 | Tổn thương kéo dài → lắng collagen, mô biến dạng | Xơ gan, phổi, thận | Sợi+matrix+morph; cao |
| 19 | Kháng thể gắn đúng kháng nguyên → trung hòa/đánh dấu | Vaccine, miễn dịch, xét nghiệm | Antibody rig+target; vừa |
| 20 | Điện thế chạy dọc neuron → synapse truyền tín hiệu | Giấc ngủ, đau, stress, thuốc | Axon+synapse+vesicle; cao |
| 21 | Tín hiệu đau từ mô tổn thương → tủy/đường dẫn truyền | Đau đầu, cơ xương khớp, thuốc giảm đau | Đường thần kinh, sơ đồ đa tầng; cao |
| 22 | Tinh thể urat xuất hiện → đáp ứng viêm tại khớp | Gout, acid uric, ăn uống | Hạt+tế bào, không giả định nồng độ cụ thể; vừa |
| 23 | Cân bằng tạo xương–hủy xương làm đổi bè xương | Loãng xương, vận động, tuổi cao | 2D morph/3D chọn lọc; cao |
| 24 | Tế bào tăng sinh bất thường → xâm lấn ranh giới mô | Tầm soát, ung thư, hút thuốc | Cell+matrix, ảnh mô có phép khi cần; cao |
| 25 | Xuyên mạch/tăng tính thấm → dịch thoát, có thể tái hấp thu | Phù, suy tim, sốt xuất huyết | Mạch+dòng dịch; cao, cơ chế từng bệnh khác nhau |
| 26 | Biểu mô nhiều lớp/nhung mao và quá trình đổi cấu trúc mô | Ruột, da, mô học; nền mở rộng mô phôi | Vector lớp + ảnh mô hợp phép; cao; chưa làm phôi toàn bộ |

Không dựng đủ 26 ngay. Giai đoạn đầu nên hoàn thiện **1,3,4,7,8,13**, tận dụng bốn composition hiện có và hai rig bổ trợ; sau đó thêm **2,5,9,11,14,19**. Các lõi dùng chung thực thể nhưng phải có hành động riêng, tránh biến thư viện thành 26 biến thể của một hình tế bào.

## 7. Kết luận lựa chọn và phần còn chưa đo

**A là hướng chính**, vì tận dụng được asset có provenance, điều khiển được nhân quả và tái dùng state/action với chi phí sửa thấp hơn model 3D mới. C chỉ bổ trợ bối cảnh/chiều sâu; B triển khai chọn lọc bằng asset đủ quyền, không mở khóa Z-Anatomy trong khảo sát này. Học K về danh tính và biến đổi, N/Z về định hướng không gian, T/V về cầu nối đời sống; tránh sao chép bảng chữ của O/A vào phần “wow”.

Bằng chứng hiện có đủ để chọn hướng và xác định hạng mục sửa, **chưa đủ để tuyên bố đạt chất lượng kênh mẫu, thời gian render/token, số thực thể chuyển động đồng thời hay nhạc/SFX**. Những mục đó ghi “không đo được”; không dùng số dự toán làm nghiệm thu. Báo cáo và khung chỉ phục vụ quyết định; các cổng duyệt hiện hành giữ nguyên.
