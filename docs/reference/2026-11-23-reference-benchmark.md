# R5.1 — Benchmark video bằng bằng chứng thực tế

Ngày khảo sát: 23/11/2026. Không commit; không thay code, workflow, schema hoặc `projects/`.

## Kết luận dùng ngay

PYH nên chuyển từ bố cục phiếu giảng sang một nhân vật đang gặp vấn đề, rồi dùng hình để giải quyết từng câu hỏi. Trong mẫu Xấu Vê Nờ nhiều view, nhịp đổi hình được dò có trung vị 2,22–2,73 giây, nhưng chuyển động thường chỉ là pan/zoom hình tĩnh. Chưa có bằng chứng rằng phải làm hoạt hình phức tạp hay dùng AI mới đạt hình thức này.

Đây là benchmark quan sát có giới hạn, không phải nghiên cứu chứng minh nguyên nhân tăng view. Đã tải và xem khung của 23 video: 5 mẫu Xấu Vê Nờ, 5 kênh đối chiếu × 2 video, 1 video kiểm tra thêm, 3 kênh Shorts × 2 video và 1 mẫu TikTok. Có mẫu lệch thể loại được ghi rõ; không gộp tất cả thành “hoạt hình phẳng thành công”.

## Phương pháp và giới hạn kiểm chứng

- Nguồn định lượng: `video.info.json`, VTT và MP4 trong từng thư mục cache; số liệu gốc, SHA-256, timestamps, số token và lý do thiếu nằm trong [metrics.json](../../cache/r5-reference/metrics.json). View là snapshot khi tải, không phải analytics của chủ kênh.
- Lệnh media: `yt-dlp --no-cache-dir --write-info-json -f "bv*[height<=480]+ba/b[height<=480]" --merge-output-format mp4 -o "cache/r5-reference/<id>/video.%(ext)s" URL`. YouTube tải được ở 360–480p, Shorts cao 426px; TikTok là bản gốc có sẵn 576×1024.
- Đã yêu cầu `--write-auto-subs --sub-langs vi,en --skip-download`; tách tải media khỏi phụ đề sau lỗi HTTP 429. Không coi `--ignore-errors` exit 0 là tải phụ đề thành công: kiểm file thực tế và nội dung.
- FFmpeg dùng `select='gt(scene,0.3)',showinfo`; lưu thời điểm được chọn và trích `scene_sheet.jpg`. Lấy thêm 1 khung/5 giây vào `sample_sheet.jpg`; video ≤10 phút được xem thêm `tail_sheet.jpg` đến hết. Video dài xem 0–300 giây và hai cửa sổ giữa 60 giây, ghi chính xác trong JSON/bảng dưới.
- `-t` đầu ra có thể để bộ lọc xử lý quá cửa sổ trước khi dừng; tính toán đã lọc `start < timestamp < end`. Không nối khoảng qua phần video không lấy mẫu. Mean/phân vị chỉ dùng khoảng hoàn chỉnh giữa hai cut, loại khoảng chạm biên. Các cut sát nhau trong một transition vẫn được giữ trong số thô.
- Đây là **khoảng đổi hình mà ngưỡng 0,3 phát hiện**, không phải nhãn cảnh ngữ nghĩa. Bộ dò bỏ sót nền trắng/đen và chuyển động nội cảnh; ít cut có thể làm mean sai lệch mạnh. K1 có đúng một khoảng 0,067 giây từ transition, tuyệt đối không diễn giải là cảnh dài 0,067 giây.
- Tốc độ lời: bỏ timestamp/tag VTT, khử lặp rolling-caption bằng phần đuôi/đầu token trùng nhau, bỏ `[music]`, `[âm nhạc]`, ký hiệu người nói; số token chia **toàn bộ thời lượng MP4**, kể cả quảng cáo/im lặng. JSON còn lưu tốc độ theo span phụ đề. Tiếng Việt là tiếng/âm tiết tách khoảng trắng, tiếng Anh là từ; không so ngang hai ngôn ngữ. Đây là proxy phụ đề, chưa kiểm bằng nghe từng từ.
- Chữ hình: ước đếm bằng mắt trên đúng 6 `key_*.jpg`, lưu từng số và thời điểm; bỏ logo/watermark và chữ chép lời, giữ nhãn/CTA/số. Mẫu thiên về mở đầu nên không đại diện census toàn phim; chữ quá nhỏ ghi null, không thay bằng 0. Chỉ tiêu này là ước đếm thủ công, không phải OCR chính xác.
- Đã xem thêm chuỗi khung 10/10,5/11 và 20/20,5/21 giây để phân biệt pan/zoom với cử động lớp/nhân vật. Riêng 3 Shorts bổ sung cuối dùng lưới 5 giây và key frames, chưa có chuỗi 0,5 giây.
- **Âm nhạc/SFX: không đo được cho mọi video** vì phiên không có đầu vào nghe âm thanh trực tiếp. Track audio đã tải; nhãn music/singing trong phụ đề chỉ là dấu hiệu, không chứng minh loại nhạc, cách mix hoặc SFX. Không có kết luận nghe giả lập.
- H1: phụ đề en nhận lời Việt thành câu tiếng Anh vô nghĩa; vi bị 429, loại WPM. S1 không có track phụ đề. Z1/Z2 vi/en bị 429 kể cả thử lại en. D0 không có URL bài gốc/phụ đề rời. Không lấy tốc độ của mẫu khác điền vào.

## Kênh được chọn và bằng chứng thành công

Subscriber ưu tiên snapshot tab kênh, không dùng trường lỗi của từng watch page. Tần suất là `(4−1)×7 / số ngày giữa 4 upload gần nhất` trên tab videos; đó là cửa sổ quan sát, không phải cam kết lịch đăng. Các ngày và ID gần nhất có trong `channels/*/recent.json`.

| Kênh | Subscriber quan sát | Upload gần nhất: cửa sổ / nhịp tuần | Lý do chọn và phạm vi áp dụng |
|---|---:|---|---|
| [AsapSCIENCE](https://www.youtube.com/channel/UCC552Sd-3nyi_tk2BudLUzA) | 10,800,000 | 20261001–20261112 / 0.50 | A1/A2: 1,51 triệu/8,40 triệu; người thật + bảng vẽ/overlay. Chỉ học minh họa một cơ chế và phụ đề, không phải mẫu art phẳng. |
| [MinuteEarth](https://www.youtube.com/channel/UCeiYXex_fwgYDonaTcSIk6w) | 3,340,000 | 20261015–20261113 / 0.72 | M1/M2: 208 nghìn/1,80 triệu, Shorts 2D thật, hợp để học sơ đồ tiến triển; nhịp dưới đây là video ngang, không suy ra lịch Shorts. |
| [KIẾN THỨC THÚ VỊ Official](https://www.youtube.com/channel/UCfUbRhr13XdumUFsFg9iMfA) | 2,740,000 | 20261119–20261123 / 5.25 | K1/K2 đạt 1,69 triệu/960 nghìn, whiteboard infographic Việt. Là đối chứng nhiều chữ vẫn có view; không dùng làm đích mỹ thuật PYH. |
| [Soi Sáng](https://www.youtube.com/channel/UChQtq0f3T1peK2w4olNyWYw) | 4,150,000 | 20261122–20261123 / 21.00 | S1 đạt 4,74 triệu view, có nhân vật dẫn hành trình tiêu hóa; S2 8,73 triệu nhưng chủ yếu stock, chỉ đối chiếu hook/typography. |
| [Xấu Vê Nờ](https://www.youtube.com/channel/UCmHY3OS_0BG4T6ZiYrwr60A) | 2,250 | 20261107–20261112 / 4.20 | X1–X3 đứng đầu tab videos trả về; đối chứng X4 ít view. X0 là mẫu bác sĩ, có bất nhất danh mục cần giữ riêng. |
| [Life Noggin](https://www.youtube.com/channel/UCpJmBQ8iNHXeQ7jQWDyGe3A) | 3,120,000 | 20251117–20260317 / 0.17 | L1/L2 đạt 2,83 triệu/1,32 triệu; nhân vật hình học lặp, giải phẫu giản lược. Thành công lịch sử, upload gần đây không còn đều. |
| [TED-Ed](https://www.youtube.com/channel/UCsooa4yRKGN_zEE8iknghZA) | 23,000,000 | 20261110–20261119 / 2.33 | T1/T2 đều gần hoặc trên 7 triệu, có tình huống mở rồi giải thích bằng hình; 2D rõ, không dùng ký ức về kênh. |
| [Hi Pencil Studio](https://www.youtube.com/channel/UCvoQ2QzfwzoYU4OV8bPcDhw) | 1,200,000 | 20250604–20250619 / 1.40 | H1/H2 đạt 3,92 triệu/515 nghìn, nội dung cơ thể/giấc mơ; pha rối và 2D, hướng trẻ em. Học nhân cách hóa, không sao giọng trẻ em. |
| [Zack D. Films](https://www.youtube.com/@zackdfilms/shorts) | 29.800.000 (watch page, chưa đối chiếu tab kênh) | Chưa đo nhịp đăng | Z1/Z2 đạt 10,37/31,67 triệu; 3D giải phẫu, chỉ học framing/chuỗi nhân quả, không gộp vào art 2D. |
Năm kênh đối chiếu chính là Soi Sáng, KIẾN THỨC THÚ VỊ, Hi Pencil Studio, TED-Ed, Life Noggin. Ba kênh Việt có độ tương đồng không hoàn toàn: Soi Sáng thay đổi phong cách theo video; Hi Pencil pha rối; whiteboard K1/K2 gần bài giảng hơn mẫu bác sĩ. Vì vậy tập tham chiếu art phẳng trưởng thành thuần nhất vẫn chưa đủ 4–5 kênh; không lấp khoảng trống bằng gán sai thể loại.

Danh sách Xấu Vê Nờ tải lại bằng `--flat-playlist` chứa X1/X2/X3 đứng đầu, nhưng **không có X0**. Watch metadata X0 vẫn ghi Xấu Vê Nờ, subscriber 225 trong khi tab kênh và X1–X4 là 2.250. Do đó 437.588 view của X0 được giữ như snapshot mẫu bác sĩ, chưa xác minh nó là outlier của cùng tập upload. Chưa thể kết luận kênh tăng trưởng nhờ video đó.

## Danh sách video đã xem khung

Mọi dòng được truy xuất ngày **23/11/2026**. Ngày trong bảng là ngày upload theo YouTube; ID là khóa nối metrics, nhận xét và thư mục khung. “Nhiều view” là mẫu liên quan tìm được, không tuyên bố top toàn kênh ngoại trừ X1–X3 trong danh sách trả về.

| Mã | Video / ID / link | Kênh | View snapshot | Ngày upload | Thời lượng giây |
|---|---|---|---:|---|---:|
| X0 | [Tại Sao Con Người Phải Giả Vờ Ngủ Thì Mới Có Thể Ngủ Thật?](https://www.youtube.com/watch?v=fafGZ46MgQs) `fafGZ46MgQs` | Xấu Vê Nờ | 437,588 | 2026-10-01 | 1085.854 |
| X1 | [Người Tiền Sử Đã Làm Gì Khi Mưa Suốt Cả Tuần?](https://www.youtube.com/watch?v=AGobTMyC2l4) `AGobTMyC2l4` | Xấu Vê Nờ | 67,059 | 2026-10-24 | 1043.294 |
| X2 | [Người Tiền Sử Thực Sự Làm Gì Suốt Cả Ngày?](https://www.youtube.com/watch?v=pVewKAEhZU4) `pVewKAEhZU4` | Xấu Vê Nờ | 38,847 | 2026-10-26 | 1030.714 |
| X3 | [Người Tiền Sử Dựng Nơi Trú Ẩn Thời Kỷ Băng Hà Như Nào?](https://www.youtube.com/watch?v=JnEdUcLhDjY) `JnEdUcLhDjY` | Xấu Vê Nờ | 24,596 | 2026-10-06 | 1161.334 |
| X4 | [Vì Sao Hạm Đội Mông Cổ Chìm Ở Con Sông Lội Qua Được?](https://www.youtube.com/watch?v=8FeccSWHnkc) `8FeccSWHnkc` | Xấu Vê Nờ | 560 | 2026-11-12 | 511.554 |
| S1 | [Cơ Thể Người Ký Sự](https://www.youtube.com/watch?v=DsnplT0xVbE) `DsnplT0xVbE` | Soi Sáng | 4,738,720 | 2019-10-18 | 571.874 |
| S2 | [Cách để Đốt nhiều Mỡ Hơn Khi Ngủ](https://www.youtube.com/watch?v=mra27LEwpS8) `mra27LEwpS8` | Soi Sáng | 8,732,918 | 2020-04-06 | 458.214 |
| K1 | [Toàn bộ kiến thức về Sức khỏe bạn nên xem](https://www.youtube.com/watch?v=YsfozkETBc0) `YsfozkETBc0` | KIẾN THỨC THÚ VỊ Official | 1,690,258 | 2024-04-17 | 5533.014 |
| K2 | [Những Sự thật thú vị về Máu mà bạn chưa biết](https://www.youtube.com/watch?v=YzWbQQDyeS0) `YzWbQQDyeS0` | KIẾN THỨC THÚ VỊ Official | 960,137 | 2020-04-03 | 307.554 |
| K3 | [Đã tìm ra 1 cách chữa ung thư di căn (Nobel Y học 2024)](https://www.youtube.com/watch?v=PIvqjhSj_zo) `PIvqjhSj_zo` | KIẾN THỨC THÚ VỊ Official | 142,769 | 2026-07-10 | 699.614 |
| H1 | [Điều Chưa Biết Về Cơ Thể Mình / Điều Chúng Mình Chưa Biết / Hi Pencil Studio](https://www.youtube.com/watch?v=ECYh0eNgeFo) `ECYh0eNgeFo` | Hi Pencil Studio | 3,920,768 | 2015-09-07 | 537.054 |
| H2 | [Giấc Mơ Của Bé / Điều Chúng Mình Chưa Biết / Hi Pencil Studio](https://www.youtube.com/watch?v=AM-p8XZ-59c) `AM-p8XZ-59c` | Hi Pencil Studio | 515,582 | 2015-10-12 | 630.354 |
| T1 | [The benefits of a good night's sleep - Shai Marcu](https://www.youtube.com/watch?v=gedoSfZvBgE) `gedoSfZvBgE` | TED-Ed | 7,512,847 | 2015-01-05 | 344.614 |
| T2 | [What causes insomnia? - Dan Kwartler](https://www.youtube.com/watch?v=j5Sl8LyI7k8) `j5Sl8LyI7k8` | TED-Ed | 6,973,718 | 2018-06-14 | 311.154 |
| L1 | [Top 5 Body Parts You Can Live Without](https://www.youtube.com/watch?v=0R8XqyHGIaI) `0R8XqyHGIaI` | Life Noggin | 2,826,431 | 2016-02-08 | 170.594 |
| L2 | [What Happens When Organs Grow Outside Your Body?](https://www.youtube.com/watch?v=eVd0ZCpYqkc) `eVd0ZCpYqkc` | Life Noggin | 1,317,914 | 2018-08-16 | 203.614 |
| D0 | Mẫu chuyển nhượng esports @500giangaf (file bác sĩ cung cấp; thiếu URL bài) `500giangaf` | @500giangaf | không đo được | không đo được | 110.912 |
| M1 | [What's The Fewest People That Could Repopulate Earth?](https://www.youtube.com/watch?v=u8zr-9CUgzg) `u8zr-9CUgzg` | MinuteEarth | 208,321 | 2026-10-02 | 133.554 |
| M2 | [You are not genetically related to all your ancestors.](https://www.youtube.com/watch?v=Zm2hTKevX_E) `Zm2hTKevX_E` | MinuteEarth | 1,802,515 | 2025-08-31 | 50.174 |
| A1 | [The call is coming from inside the house](https://www.youtube.com/watch?v=FCaTFLdtsco) `FCaTFLdtsco` | AsapSCIENCE | 1,576,755 | 2026-05-04 | 66.854 |
| A2 | [Why you hate the sound of your own voice #shorts](https://www.youtube.com/watch?v=1Xk8ldFZhFM) `1Xk8ldFZhFM` | AsapSCIENCE | 8,403,276 | 2022-03-23 | 56.134 |
| Z1 | [How Mouth Breathing Can Change Your Face 😬](https://www.youtube.com/watch?v=2ll9ClpJ3x8) `2ll9ClpJ3x8` | Zack D. Films | 10,370,081 | 2026-11-22 | 32.334 |
| Z2 | [What If Humans Had Hummingbird Hearts 🤔](https://www.youtube.com/watch?v=ob4_mDwWkM0) `ob4_mDwWkM0` | Zack D. Films | 31,670,286 | 2026-11-07 | 37.314 |
## Bảng số đo

Đơn vị mean/Pxx: giây; `cut/n` = số cut nội cửa sổ/số khoảng hoàn chỉnh dùng tính. Dấu †: dưới 5 khoảng, không đại diện thời lượng cảnh. `NĐ` = không đo được, lý do ở phương pháp và JSON. “Chữ” là token ước đếm/khung trên 6 key frames. Cột lời ghi rõ vi/en. Tất cả con số ở đây được đọc từ JSON, không nhập ước lượng nhịp bằng cảm giác.

| Mã | Giây đã dò | cut/n | Mean | P25 | P50 | P75 | P90 | Token lời/phút | Chữ/khung |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| X0 | 420.000 | 173/170 | 2.42 | 1.51 | 2.22 | 3.12 | 4.04 | 254.7 vi | 0.00 |
| X1 | 420.000 | 166/163 | 2.51 | 1.68 | 2.37 | 2.98 | 3.80 | 278.3 vi | 0.00 |
| X2 | 420.000 | 145/142 | 2.89 | 1.94 | 2.73 | 3.62 | 4.67 | 279.6 vi | 0.00 |
| X3 | 420.000 | 122/119 | 3.44 | 1.83 | 2.63 | 3.68 | 7.21 | 255.0 vi | 1.00 |
| X4 | 511.554 | 75/74 | 6.45 | 2.73 | 3.67 | 5.74 | 9.54 | 236.7 vi | 0.00 |
| S1 | 571.874 | 30/29 | 18.59 | 0.23 | 7.27 | 25.87 | 49.83 | NĐ | 0.50 |
| S2 | 458.214 | 21/20 | 18.70 | 0.23 | 4.47 | 31.66 | 49.67 | 224.4 vi | 0.67 |
| K1 | 420.000 | 3/1 | 0.07† | 0.07† | 0.07† | 0.07† | 0.07† | 227.3 vi | 17.17 |
| K2 | 307.554 | 2/1 | 34.45† | 34.45† | 34.45† | 34.45† | 34.45† | 228.8 vi | 5.33 |
| K3 | 420.000 | 14/11 | 23.63 | 4.20 | 17.00 | 39.72 | 49.57 | 220.1 vi | NĐ |
| H1 | 537.054 | 87/86 | 6.14 | 1.04 | 3.52 | 8.73 | 16.64 | NĐ | 0.17 |
| H2 | 420.000 | 43/41 | 6.28 | 0.92 | 1.60 | 4.00 | 11.48 | 120.0 vi | 1.00 |
| T1 | 344.614 | 2/1 | 9.97† | 9.97† | 9.97† | 9.97† | 9.97† | 142.1 en | 3.33 |
| T2 | 311.154 | 18/17 | 16.00 | 5.05 | 8.26 | 17.18 | 46.42 | 136.1 en | 0.17 |
| L1 | 170.594 | 5/4 | 5.04† | 3.61† | 4.60† | 6.03† | 7.23† | 202.9 en | 1.00 |
| L2 | 203.614 | 2/1 | 15.33† | 15.33† | 15.33† | 15.33† | 15.33† | 195.4 en | 0.00 |
| D0 | 110.912 | 1/0 | NĐ | NĐ | NĐ | NĐ | NĐ | NĐ | 3.67 |
| M1 | 133.554 | 4/3 | 22.42† | 11.77† | 13.38† | 28.54† | 37.64† | 178.4 en | NĐ |
| M2 | 50.174 | 0/0 | NĐ | NĐ | NĐ | NĐ | NĐ | 210.5 en | NĐ |
| A1 | 66.854 | 1/0 | NĐ | NĐ | NĐ | NĐ | NĐ | 163.3 en | 2.67 |
| A2 | 56.134 | 0/0 | NĐ | NĐ | NĐ | NĐ | NĐ | 214.8 en | 9.33 |
| Z1 | 32.334 | 0/0 | NĐ | NĐ | NĐ | NĐ | NĐ | NĐ | 0.00 |
| Z2 | 37.314 | 3/2 | 11.81† | 6.44† | 11.81† | 17.18† | 20.41† | NĐ | 0.00 |
Cửa sổ dài (giây): X0 0–300/489–549/760–820; X1 0–300/469–529/730–790; X2 0–300/464–524/721–781; X3 0–300/523–583/813–873; K1 0–300/2490–2550/3873–3933; K3 0–300/315–375/490–550; H2 0–300/347–407/504–564. Các video khác dò hết. K1 chỉ có một khoảng hoàn chỉnh dù có 3 cut vì nằm ở các cửa sổ rời nhau.

Không lấy trung bình chung 23 video: ngôn ngữ, độ dài, quảng cáo, nền hình và độ nhạy bộ dò khác nhau. Chữ 0 ở X0/X1/X2/X4 chỉ đúng 6 key frames; lưới đầy đủ vẫn có nhãn/CTA tại thời điểm khác. K1 17,17 cũng chỉ là trung bình 6 mẫu, trong đó một bảng khoảng 60 token.

## Đọc từng video: hook, cấu trúc, hình và chuyển động

Các sơ đồ dưới đây là bản đồ biên tập từ phụ đề và các đoạn hình đã xem, không phải shotlog từng giây. Mốc phút chỉ định vị phần nội dung. Không trích lời dài; nội dung y khoa trong mẫu chưa được thẩm định bởi báo cáo này.
**X0.** 30 giây: người nằm giường nhưng đầu nghĩ chuyện cũ; hình bong bóng suy nghĩ biến điều vô hình thành hành động. Mở tình huống → áp lực ngủ/cảnh giác → tổ tiên và an toàn → trạng thái chớm ngủ → ánh sáng/điện thoại → suy nghĩ rời rạc → quay lại câu hỏi đầu. Ẩn dụ não họp, châm biếm chuyện tự ép ngủ; cuối chốt bằng việc buông cảnh giác, không thấy CTA đăng ký trong phần phụ đề cuối. Người đầu tròn, áo xanh, phòng ngủ xanh đêm; xen icon não và sơ đồ. 10–10,5 giây chủ yếu zoom cùng hình; 11 giây đổi hình. Không có bằng chứng xác định ảnh AI.
**X1.** 30 giây: đói, dấu thú, chuẩn bị lao rồi mưa phá kế hoạch; tương phản mong muốn–trở ngại. Chuỗi nơi trú/thú dữ → giữ lửa → sửa đá/khâu da/làm chỗ nằm → hoạt động cộng đồng → kiếm ăn sau mưa → chốt ngày ở nhà vẫn chuẩn bị tương lai. Các câu hỏi nối từng vấn đề sống còn; hài qua so sánh sinh hoạt hiện đại. Nhân vật đầu tròn áo da, nâu đất/xám mưa, hang và bếp lặp làm điểm neo. Hai chuỗi 0,5 giây cho thấy crop/zoom nhẹ trên ảnh gần tĩnh; thời tiết là dấu hiệu hành động. Không thấy CTA lời ở kết.
**X2.** 30 giây: báo thức/điện thoại và người hiện đại thức dậy, sau đó lật sang ngày sống tiền sử. Đặt nghi vấn bận rộn → chứng cứ xương/thể trạng → kiếm ăn và thời gian lao động → thủ công/âm nhạc → chuyện bên lửa → nghĩa vụ khi làm nông → hỏi lại thời gian sống khác thời gian làm việc thế nào. Sơ đồ so sánh hai thời đại là ẩn dụ chính; hài bằng điện thoại và công việc bàn giấy. Trời xanh, đất nâu, người que lặp; chủ yếu pan/zoom/cắt ảnh, không thấy rig tay chân rõ ở 10–11 giây. Cuối không thấy CTA lời.
**X3.** 30 giây: hoàng hôn, gió lạnh, người cuộn mình; lời đặt hạn 40 phút trước tối. Vị trí/mái đá → dựng khung/vách → dấu tích nền → nhà xương voi → nghi vấn cách lợp → nhiên liệu/bếp → sàn cách lạnh → bố trí cộng đồng → chốt ý “bên trong”. Câu hỏi công trình lớn được lợp thế nào giữ khoảng trống giải thích; hài nhẹ hơn X1/X2. Nâu da, trắng băng, xanh nhạt; có nhà/xương và mặt cắt nền, không phải hình tế bào cố định. Pan/zoom và lớp gió; nút Subscribe xuất hiện ngay từ mở đầu nhưng không suy ra hiệu quả.
**X4.** 30 giây: đưa người xem thành lính trên thuyền vừa mắc lại khi nước rút, hình thuyền lớn/cọc xuất hiện. Mở kết quả → quay về chiến dịch/lương thực → dựng bẫy thủy triều → trận đánh → hậu quả → dấu cọc khảo cổ. Ví von bữa tiệc đã dọn sạch và trò ảo thuật cũ tạo hài; câu hỏi vì sao mắc bẫy được trả bằng mặt cắt thuyền–cọc. Nhân vật chibi mặc giáp, bản đồ/biểu đồ nước; cắt, zoom và thuyền di chuyển qua bố cục. Kết phụ đề còn có câu mang dạng ghi chú đếm từ/tốc độ; chưa nghe xác minh có lọt vào voice. Hook và hoạt hình vẫn hiện diện dù chỉ 560 view.
**S1.** 30 giây: logo bóng đèn, viên tròn tím trong trái cây rồi nhân vật chuẩn bị ăn. Qua hình đã xem toàn thời lượng: miệng/răng → thực quản như đường trượt → dạ dày → ruột non và tuyến phụ → ruột già/vi sinh → ruột thừa → tín hiệu đi vệ sinh → hành vi nhân vật → logo. Nhân cách hóa viên thức ăn/cơ quan, tuyến tiêu hóa thành chuyến đi; bảng màu hồng/đỏ/xanh rất bão hòa, nhãn thường ngắn. Nhân vật và lớp hình cử động độc lập, có wipe/zoom. Không có phụ đề nên không xác nhận được lời hook, câu đùa, câu hỏi mở hay CTA lời.
**S2.** 30 giây: logo rồi ham muốn giảm cân khi không vận động; montage người ăn/ngủ và dấu hỏi. Sau đó là danh sách hành động liên tiếp (nước, nhiệt độ, ngủ, cà phê, đồ ăn, tập luyện...) → hỏi người xem chia sẻ mẹo → gợi video khác. Vàng/đen, thẻ chữ lớn, stock quay người thật xen vài sơ đồ; zoom/blur/đồ thị. Hài nằm ở ví dụ lười và hóa đơn điện. Đây **không phải** mẫu hoạt hình phẳng xuyên suốt; view cao không đủ để nhận làm chuẩn hình hay tin các mẹo sức khỏe.
**K1.** 30 giây: cà phê quen thuộc, hỏi lợi/hại rồi hứa tóm tắt; tách title và ảnh xuất hiện dần. Toàn bài là tuyển tập nhiều chủ đề thực phẩm/đồ uống, không một đường truyện duy nhất; các phần lặp mô thức lợi–hại–lưu ý. Khung giữa được xem có bưởi/hàu và chất chống oxy hóa; phụ đề cuối quay về rủi ro nước ngọt, không thấy CTA lời rõ ở cuối. Hài/nhớ bằng ví von đời thường. Whiteboard bàn tay vẽ, clipart và chữ tích lũy; không dùng làm mẫu art đích vì một khung đã khoảng 60 token.
**K2.** 30 giây: mở như chuyện tình cảm rồi chuyển nghĩa sang tim/máu; người buồn và hệ tuần hoàn được vẽ dần. Lượng máu/độ dài mạch → tim bơm → vận chuyển/bảo vệ/nhiệt độ → các thành phần máu → CTA hiến máu và kết. Xe tải là ẩn dụ vận chuyển; tim vỡ tạo hài và nối hook. Trắng xám, đen/đỏ, hình giải phẫu + clipart; bàn tay reveal và camera lia trên bảng. Chữ tăng dần, cuối thu nhỏ tổng bảng. Cùng có view cao nhưng gần phong cách giảng bài: học ẩn dụ xe, không học gom mọi chữ lên một khung.
**K3.** 30 giây đầu thực tế là quảng cáo vay, sau đó nhân vật khoa học mới xuất hiện. ADN/protein → hai nhà nghiên cứu/con giun → lin-4/microRNA → đối chiếu dữ liệu → let-7 → liên hệ ứng dụng → chốt giá trị tò mò → quảng cáo máy hút bụi/CTA mua. Câu hỏi vì sao một gen tạo protein khác nhau là động cơ; hài về soi giun và công nhân tế bào. Whiteboard vẽ dần, hình tài liệu nhỏ, clipart và icon nhà máy. Dùng làm kiểm tra chống chọn nhầm hook: tên video có sức khỏe không có nghĩa 30 giây đầu phục vụ lời hứa sức khỏe.
**H1.** 30 giây là montage nhận diện chương trình/rối/động vật; câu chuyện cơ thể bắt đầu sau mở màn. Hình toàn phim: đối thoại rối ở lớp → trẻ/cha mẹ và ngáp → phổi nhân cách hóa → chảy mũi/hắt hơi → da/lông → bộ não/cảm giác → lạnh/rùng mình → rối kết. Không đủ phụ đề đáng tin để gán lời hook, câu hỏi mở, câu chốt/CTA cụ thể. Các cơ quan có gương mặt, gia đình và trường học là bối cảnh; pastel, nét mềm, xen rối quay thật. Có cử động nhân vật và chuyển góc, không phải chuỗi slide. Chỉ là mẫu kể cho trẻ em, không mẫu tông giọng PYH.
**H2.** 30 giây cũng là montage; sau đó rối ngái ngủ ở lớp mở phần kể. Ngủ và não sửa chữa → thời lượng ngủ theo tuổi → giấc mơ/hình ảnh đẹp-xấu → bạn ngủ gật bị trêu → thiếu ngủ → câu hỏi trắc nghiệm, mời xem HTV7 → endcard đăng ký kéo dài. Não như người điều khiển phòng máy là ẩn dụ dễ thấy; hài bằng dán mắt để ngủ trong lớp. Màu pastel, rối lặp và hoạt hình trẻ; cử động thật/2D, đổi cảnh/wipe. Token/phút toàn video thấp một phần vì intro, nhạc và endcard; không lấy 120 làm tốc độ voice PYH.
**T1.** 30 giây: 4 giờ sáng, thi và biểu diễn piano đang tới, bàn tay chuyển giữa sách và đàn; đặt lựa chọn tiếp tục học hay ngủ. Phá hiểu lầm ngủ là phí giờ → não/ký ức → phân biệt trí nhớ → giai đoạn ngủ và củng cố → trở lại kết quả học/đàn → credit, link bài học/CTA tham gia. Hình não biến thành mạng và kho biểu tượng; xanh ngọc, vàng, đỏ trên xám; chuyển hình bằng morph/lớp, tay và đồng hồ cử động. Không cần nhân vật dẫn có mặt ở mọi cảnh. Không thấy câu đùa riêng nổi bật trong phụ đề đã rà.
**T2.** 30 giây: người nằm trên giường với những việc khiến mất ngủ; phòng/ngày đêm và nét mặt thay đổi. Mất ngủ thoáng qua → vòng stress/giường → kích hoạt cơ thể/tiêu hao → mạn tính → phá liên kết hành vi → đồng hồ sinh học → phân biệt một vấn đề nhịp ngủ khác → thói quen/CTA tìm hiểu thêm. Pin não, quan tài và con mèo tạo ẩn dụ/hài; một nhân vật lặp, nâu/xanh đêm/paper texture. Chuỗi 20–21 giây thấy nhân vật thực sự ngồi dậy trong cùng phòng, 10–11 giây icon vào bong bóng. Dò .3 bỏ nhiều chuyển hình nhỏ.
**L1.** 30 giây: cá voi và bộ phận thoái hóa, chuyển sang răng khôn, chọc chuyện niềng răng. Mỗi phần một ví dụ (răng, ruột thừa, đuôi, núm vú, mí mắt) → chuyển qua video tim → hẹn video mới/CTA xem tiếp. Bác sĩ cầm tiền và người dẫn hình học tạo hài; nền magenta/xanh/vàng, nhãn 1–2 từ, cơ quan giản lược. Cơ chế kể là danh sách, không cuộc phiêu lưu; vẫn nối bằng một nhân vật và joke. 10–11 giây ít đổi, 20–21 giây có đổi tỷ lệ/răng; ít cut ngưỡng lớn không có nghĩa cả phút không đổi nội dung.
**L2.** 30 giây: người dẫn bước vào tình huống phòng thí nghiệm và câu hỏi cơ quan ngoài cơ thể. Khuyết tật thành bụng → chức năng cơ quan/xương sườn → não/màng và dịch bảo vệ → người dẫn vui đùa → hỏi người xem muốn chủ đề nào/Subscribe, xem tiếp. Mô hình giải phẫu dạng hình học, bối cảnh lab/nhà/sân; cyan, xanh nhạt, magenta. Nhân vật trắng và nhà khoa học lặp; pan theo bối cảnh, reveal cơ quan, cử động tay/chân. Nhãn ngắn và hình cắt lớp chịu phần giải thích.
**D0.** 30 giây: sơ đồ các đội, chân dung Zeus/Doran, nhãn chia tay rồi xoáy nghi vấn tin đồn; chỉ xác nhận hook bằng chữ đốt sẵn và hình. Sau các chuyển nhượng, cú ngắt khoảng giữa quay lại vòng đội/cầu thủ → so sánh cân và lựa chọn đường trên → hỏi khán giả chọn ai. Nền tối sao, sơ đồ ở trên/giữa, phụ đề phía dưới; màu vàng/đỏ/xanh mã hóa trạng thái, nối đường và viền chọn. 10–11 giây bố cục giữ, caption thay; 20–21 giây chữ reveal. Không có bằng chứng view/subscriber hoặc thành công của kênh; là mẫu bác sĩ thích, không mẫu sức khỏe.
**M1.** 30 giây: tình huống nhân loại phải tái lập và máy gắp như ẩn dụ vốn gen ít/nhiều. Giảm dần các kịch bản quy mô quần thể → chọn lọc có kế hoạch → phôi đông lạnh → trở lại Trái Đất và joke tránh bom. Bố cục dọc vẽ tay, hình người dẫn ở góc dưới, sơ đồ nhóm/đường nối ở giữa; tím/trắng, số nổi bật. Không có phụ đề đốt sẵn nhấn từng từ ở lưới đã xem. Máy gắp thay lượng viên trong khung 10–21 giây. 133,554 giây: ví dụ Shorts có thể trên một phút; không suy ra PYH nên kéo dài như vậy.
**M2.** 30 giây: phả hệ nhìn trực tiếp và nghịch lý không nhận gen từ mọi tổ tiên. Đặt nghịch lý → kẹo của bố/mẹ như việc lấy mẫu gen → đường gen chồng lên phả hệ → một số nhánh không truyền DNA → thu ra nhiều thế hệ. Màu đen/trắng, đỏ/xanh phân nguồn; nét người que lặp, reveal đường và chuyển quy mô. Lưới hình không thể hiện đúng kẹo như lời kể ở mọi nhịp, nên không khẳng định hình–voice khớp từng câu. Cuối chốt nghịch lý, không thấy CTA lời.
**A1.** 30 giây: hỏi về giọng nói của chính người xem; người biểu diễn bên đàn và bảng nguyên âm/sóng. Nối nguyên âm → cao độ → âm S → ngoại lệ cá nhân → đồ thị/không quy giản testosterone → câu chốt hài. Người thật là neo cố định, bảng che vùng giữa, caption trắng viền đen có từ nhấn màu; không phải hoạt hình phẳng. 10–11 giây thay title bằng bảng là một thay đổi ý dù detector chỉ bắt 1 cut toàn clip. Phụ đề ghi cả music/singing nhưng chưa nghe nên không kết luận mix nhạc.
**A2.** 30 giây: tiêu đề hỏi vì sao ghét nghe giọng thu âm, người cầm bảng tai/ốc tai. Đường truyền qua không khí → thêm rung xương khi tự nói → bản ghi thiếu đường xương → cảm giác lạ. Có hình vẽ thật trên bảng, nhãn xanh/tím, người chỉ vào sơ đồ; title đỏ ở trên là 9 token cố định. Ít phụ đề chép lời trong mẫu hình; không thấy CTA lời hay joke tách riêng, kết ở cảm giác khó chịu. Đầu–cuối cùng một góc máy vẫn có tiến trình cơ chế; 0 cut không phải 0 chuyển động.
**Z1.** 30 giây gần như toàn bài: mặt/luồng khí → cắt lớp lưỡi → hàm/hộp sọ → khuôn mặt → răng. Cơ chế được gợi bằng mũi tên áp lực và thay hình giải phẫu, nền cyan, nhân vật áo đỏ; caption trắng 2–4 từ theo cụm, không thấy karaoke từng từ chắc chắn. Khung 10–11 giây lưỡi/luồng khí và caption đổi dù detector 0 cut. Không có phụ đề rời đáng tin để đo tốc độ hoặc dựng toàn bộ câu chuyện lời; không xác nhận tính đúng y khoa của quan hệ được kể.
**Z2.** 30 giây: chim ruồi → tim người đập nhanh → người chạy → mạch máu và nhu cầu cơ thể. Cuối chuyển từ khả năng tưởng tượng sang hệ quả và người ăn uống; áo vàng, nền cyan/tím, giải phẫu 3D màu mạnh, camera xuyên cơ thể. Phụ đề đốt sẵn theo cụm 2–4 từ; không có CTA nhìn thấy ở kết. Thiếu track phụ đề nên không đo WPM, không gán câu đùa hoặc lời chốt chính xác. Đây là mẫu nhịp hình/cutaway, không mẫu chi phí của pipeline 2D.
## So sánh thắng–thua trong Xấu Vê Nờ

X1/X2/X3 có 67.059/38.847/24.596 view, X4 có 560. X1–X3 cùng người que, vấn đề sinh tồn/dời sống, ít chữ; X4 vẫn có tình huống nhập vai và nhân vật nhưng chuyển sang lịch sử quân sự, thêm bản đồ/thủy triều và nhãn. Vì vậy “có nhân vật/hook” là chưa đủ để phân biệt thắng–thua.

Trong đoạn đã đo, X1/X2/X3 có median cut 2,37/2,73/2,63 giây và P90 3,80/4,67/7,21; X4 median 3,67, P90 9,54. Nhịp X4 chậm hơn theo bộ dò, song chưa biết retention/CTR/impression/thumbnail, nguồn phân phối hay cơ cấu người xem; ngày đăng cũng khác. Đây là giả thuyết thử nhịp và chọn vấn đề gần người xem, không kết luận nhân quả.

X0 mạnh ở nghịch lý rất đời thường, phòng ngủ lặp nhưng câu chuyện tiến từ khó ngủ sang cơ chế rồi trở lại người nằm giường. Không dùng tỷ lệ 437.588/560 để quy công cho mỹ thuật vì danh tính tập upload đang bất nhất.

## Ước tính sản xuất và chi phí

Các khoảng dưới là **dự toán của người phân tích cho PYH**, không phải dữ liệu hậu trường của kênh; chưa biết họ dùng phần mềm, AI, ê-kíp hoặc ngân sách nào. Mỗi video ở trên được ánh xạ theo họ hình dưới đây. Công tính 150.000 đồng/giờ là giả định để so phương án, chưa gồm nghiên cứu y khoa/duyệt, bản quyền, thuê giọng, máy và API. API chưa đo: không đưa giá giả.

| Họ / video áp dụng | Cách dựng hợp lý theo hình đã xem | Quy mô giả định | Công và tiền công giả định |
|---|---|---|---|
| X0–X4 | Bộ nhân vật/pose và bối cảnh đồng nhất, ảnh tĩnh + pan/zoom/cut; có thể vẽ hoặc tạo ảnh rồi chỉnh. Không chứng minh AI | 1 phim 15 phút; thử 120 bố cục có biến thể/reuse | 32–56 giờ; 4,8–8,4 triệu |
| S1, T1/T2, L1/L2, M1/M2 | Vector nhiều lớp; nhân vật/cơ quan dùng lại, animate reveal/transform/morph; cần sửa tay | 5 phút ngang hoặc 60 giây dọc | Ngang 24–48 giờ (3,6–7,2 triệu); dọc 6–12 giờ (0,9–1,8 triệu) |
| K1–K3 | Whiteboard/template bàn tay, clipart/nhãn; cần xóa bảng đúng lúc, không tích lũy vô hạn | 10 phút nội dung gốc, không tính ghép lại tuyển tập 92 phút | 16–32 giờ; 2,4–4,8 triệu |
| S2 | Tìm/licence stock, typography và montage | 8 phút | 12–24 giờ; 1,8–3,6 triệu + licence chưa đo |
| H1/H2 | Rối quay thật + hoạt hình 2D; không thể thay toàn bộ bằng template pan/zoom mà giữ cùng diễn xuất | 1 tập khoảng 10 phút | Không đo được công/chi phí đáng tin vì thiếu lịch quay, asset và ê-kíp |
| D0 | Card chân dung/logo, đường nối, vòng trạng thái và cân; keyframe vị trí/viền/chữ | 60–110 giây từ template sẵn | 4–8 giờ; 0,6–1,2 triệu, cộng quyền ảnh chưa đo |
| A1/A2 | Người thật quay dọc + bảng vẽ/overlay/caption | 1 clip 60 giây sau khi đã có script | 3–6 giờ; 0,45–0,9 triệu |
| Z1/Z2 | Rig/model 3D, giải phẫu/camera/collision và compositing | 1 clip 30–40 giây | Không đo được công/chi phí từ hình; không dùng làm dự toán 2D |

## Chuẩn đề xuất cho PYH

Đây là **mục tiêu thử nghiệm biên tập**, không phải chuẩn phổ quát hay điều kiện thay cổng duyệt. Mỗi hàng có video gốc để đối chiếu. Chưa đủ bằng chứng đặt chuẩn nhạc/SFX, retention hoặc chi phí GPU.

| Chiều | 16:9, 10–25 phút | 9:16 | Căn cứ đã đo/xem |
|---|---|---|---|
| Hook | Trong 30 giây có 1 người, 1 vấn đề, 1 câu hỏi còn treo; chưa đưa bảng nguồn | Trong 5 giây lộ vật/người và điều bất ngờ; 30 giây phải đang trả lời | X0/X1/X3 mở cảnh đời/sinh tồn; T2 nằm giường; M2 lộ phả hệ từ khung 0; Z1 lộ người từ khung 0 |
| Nhịp đổi hình | Thử median 2,5–3,5 giây, P90 ≤8 giây với phong cách ảnh/cut; cho phép cảnh cơ chế dài khi có tiến triển nội cảnh | Không áp median hard-cut cho mọi mẫu; 0 cut ở M2/A2/Z1 vẫn có tiến triển. Kiểm bằng chuỗi 5 giây: mỗi bước có thay đổi quan hệ/hành động | X1–X3 median 2,37–2,73, P90 3,80–7,21; X4 3,67/9,54; M2/A2/Z1 detector 0 |
| Lời Việt | Thử 240–270 tiếng/phút toàn đoạn có lời; ghi riêng tốc độ toàn video và span nói. Đọc chậm hơn ở cơ chế khó nếu hình cần thời gian | Chưa đủ mẫu dọc **tiếng Việt sức khỏe** có VTT để đặt WPM; không quy đổi 178–215 từ Anh thành tiếng Việt | X0/X3 khoảng 255, X1/X2 khoảng 278–280 toàn video; M1/M2/A2 khoảng 178/210/215 từ Anh |
| Chữ ngoài caption | Đích thử trung bình ≤6 token trên 6 mẫu phân bố đều; một nhãn một nhiệm vụ, không dồn title/nguồn/bảng song song | Đích thử ≤8 token sơ đồ mỗi thời điểm; title cố định phải được tính vào tải chữ | X0–X2 0, S1 0,50, T1 3,33, L1 1,00; D0 3,67; A2 9,33 là đối chứng title chiếm tải chữ |
| Nhân vật/bối cảnh | Một người có mục tiêu quay lại ở ít nhất đầu–giữa–cuối; đổi pose/đạo cụ theo trạng thái, không chỉ làm mascot góc | Một nhân vật hoặc một sơ đồ neo; mỗi đoạn bổ sung một quan hệ | X0 phòng ngủ, X1 hang/bếp, T2 người mất ngủ; M2 phả hệ, D0 vòng đội. Số lần “3” là đề xuất kiểm thử, chưa phải tần suất census |
| Cơ chế | Bắt đầu bằng ẩn dụ gần đời rồi chuyển sang hình cơ quan cần thiết; thể hiện nguyên nhân → thay đổi → hệ quả | Một đường nhân quả chính; từng bước dùng mũi tên/highlight hoặc đổi hình | S1 thức ăn thành chuyến đi; K2 xe chở hàng; T2 pin; A2 hai đường truyền; Z1 mũi tên/cắt lớp |
| Chuyển động | Ảnh + pan/zoom đủ để thử phong cách X; chỉ animate bộ phận khi giúp hiểu thay đổi | Ưu tiên vùng chú ý ổn định và reveal tiến trình; không cần mỗi nhịp đều có hard-cut | X1/X2 chuỗi 0,5 giây gần tĩnh; T2 thực sự ngồi dậy; D0 giữ bố cục, đổi chữ/viền |
| Vùng chữ dọc | Không áp dụng | Tách nhãn sơ đồ khỏi caption; thử caption tối đa 2 dòng, cụm 2–4 từ, xem trên điện thoại; vị trí tránh che vật chính. Chưa đo được safe-area pixel chung | D0 caption phía dưới sơ đồ; Z1/Z2 cụm trắng 2–4 từ; A1 caption ở ngực/đầu bảng. “2 dòng” là ràng buộc thiết kế thử, chưa là số trung bình mẫu |
| Kết/CTA | Trả câu hỏi mở trước khi mời xem tiếp; chỉ 1 hành động phù hợp nội dung PYH | Kết bằng kết quả/đối chiếu trước–sau hoặc 1 câu hỏi cụ thể | X0 trở lại câu hỏi ngủ; T1 kết quả học/đàn; K2 hiến máu; D0 hỏi chọn đường trên. Số “1” là đề xuất giảm phân tán |
| Nguồn trên hình | Để nguồn đầy đủ ở mô tả/gói duyệt; trong phim chỉ nhãn nguồn ngắn khi nó giúp quyết định, không lấy khung thẻ bài báo thay câu chuyện | Tương tự, không co cả thẻ bài báo vào màn hình dọc | So sánh key T1/T2/L1 với `pyh_sheet2.jpg`; không hàm ý giảm chuẩn bằng chứng y khoa |

Để nghiệm thu đích thử, lấy 6 khung phân bố đều trong video PYH mới (khác mẫu thuận tiện thiên mở đầu hiện tại), đếm chữ lại, kiểm 30 giây đầu và diễn tiến 5 giây/lần; đối chiếu với X1/T2/S1/M2. Không triển khai pipeline trong brief này.

## Những gì PYH đang làm ngược

Đã xem cả `pyh_sheet1.jpg` và `pyh_sheet2.jpg`; đây là lưới không có timestamp nên **không đo được** tốc độ cảnh, WPM hoặc thời lượng lặp của PYH từ hai file đó.

| Quan sát trực tiếp ở PYH | Đối chiếu mẫu thực tế | Hướng sửa hình/cách kể đề xuất |
|---|---|---|
| Tế bào gai lặp trong nhiều ô; thay nhãn/chấm nhưng người xem vẫn ở cùng bố cục bảng | X0 vẫn lặp phòng ngủ nhưng thay người/hành động/điều lo; S1 đi qua từng cơ quan | Dùng một người nhận phiếu xét nghiệm và gặp quyết định; tế bào chỉ xuất hiện ở đoạn cần giải thích |
| Chia nhiều khung viền: title trên, hình trái, bảng phải, dải mạch phía dưới, nguồn nhỏ | T2 thường một người + một hình giải thích; L1 một cơ quan + nhãn | Mỗi khung một quan hệ chính; chuyển câu tiếp theo sang bố cục mới thay vì cộng thêm hàng |
| Thẻ tiêu đề nghiên cứu tiếng Anh chiếm nguyên cảnh; chữ diễn giải nhỏ | X1/T2 tạo vấn đề bằng hành động, không mở bằng tên nghiên cứu | Chuyển kết quả liên quan thành lựa chọn/hệ quả bằng hình; giữ nguồn truy vết ở mô tả và gói duyệt |
| Có mascot bác sĩ góc dưới và vài hình người, nhưng phần lớn ô là cơ quan/bảng | T2 nhân vật thật sự đứng/ngồi dậy; X1 đối mặt với mưa, lạnh, lửa | Cho nhân vật làm việc, chần chừ, đổi quyết định; không chỉ đứng cạnh bảng |
| Các ô chứa lượng chữ khó đọc khi thu xuống điện thoại | X0–X2 sáu key frames không cần chữ; T1 vẫn truyền cơ chế bằng mạng/đàn/biểu tượng | Kiểm lại bản 480p/mobile; bỏ chữ không cần để hiểu cảnh, không chỉ tăng cỡ chữ trong cùng bảng |
| Tông kem/xanh nhạt và vùng trống giống phiếu chuyên môn | X0 dùng xanh đêm cho trải nghiệm ngủ; S1 dùng màu đi theo cơ quan/trạng thái | Cho màu báo trạng thái và điểm chú ý. Không đổi toàn bộ sang màu bão hòa chỉ vì S1 nhiều view |

Hai lưới PYH vẫn có mầm câu chuyện: người cầm phiếu, hộp thuốc, cảnh buổi khám và vào viện. Vấn đề quan sát được là các cảnh đó chưa làm trục cho phần lớn hình đang thấy; không kết luận rằng video hoàn toàn không có nhân vật hoặc không có nội dung hữu ích.

## Chỉ mục khung tiêu biểu và dữ liệu kiểm toán

Gốc tuyệt đối: `E:\pyh-r5-1\cache\r5-reference\`. Mỗi dòng dưới liệt kê đủ 6 file tiêu biểu (không quá 6/video). Click thư mục qua key_01; các thời điểm chính xác nằm trong `on_screen_text.frames` của metrics. `sample_sheet.jpg`, `tail_sheet.jpg`, `scene_sheet.jpg`, `motion_sheet.jpg` là lưới hỗ trợ, không thêm file `key_*`.

| Mã | Thư mục và sáu file khung |
|---|---|
| X0 | [fafGZ46MgQs](../../cache/r5-reference/fafGZ46MgQs/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| X1 | [AGobTMyC2l4](../../cache/r5-reference/AGobTMyC2l4/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| X2 | [pVewKAEhZU4](../../cache/r5-reference/pVewKAEhZU4/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| X3 | [JnEdUcLhDjY](../../cache/r5-reference/JnEdUcLhDjY/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| X4 | [8FeccSWHnkc](../../cache/r5-reference/8FeccSWHnkc/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| S1 | [DsnplT0xVbE](../../cache/r5-reference/DsnplT0xVbE/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| S2 | [mra27LEwpS8](../../cache/r5-reference/mra27LEwpS8/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| K1 | [YsfozkETBc0](../../cache/r5-reference/YsfozkETBc0/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| K2 | [YzWbQQDyeS0](../../cache/r5-reference/YzWbQQDyeS0/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| K3 | [PIvqjhSj_zo](../../cache/r5-reference/PIvqjhSj_zo/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| H1 | [ECYh0eNgeFo](../../cache/r5-reference/ECYh0eNgeFo/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| H2 | [AM-p8XZ-59c](../../cache/r5-reference/AM-p8XZ-59c/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| T1 | [gedoSfZvBgE](../../cache/r5-reference/gedoSfZvBgE/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| T2 | [j5Sl8LyI7k8](../../cache/r5-reference/j5Sl8LyI7k8/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| L1 | [0R8XqyHGIaI](../../cache/r5-reference/0R8XqyHGIaI/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| L2 | [eVd0ZCpYqkc](../../cache/r5-reference/eVd0ZCpYqkc/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| D0 | [500giangaf](../../cache/r5-reference/500giangaf/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| M1 | [u8zr-9CUgzg](../../cache/r5-reference/u8zr-9CUgzg/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| M2 | [Zm2hTKevX_E](../../cache/r5-reference/Zm2hTKevX_E/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| A1 | [FCaTFLdtsco](../../cache/r5-reference/FCaTFLdtsco/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| A2 | [1Xk8ldFZhFM](../../cache/r5-reference/1Xk8ldFZhFM/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| Z1 | [2ll9ClpJ3x8](../../cache/r5-reference/2ll9ClpJ3x8/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
| Z2 | [ob4_mDwWkM0](../../cache/r5-reference/ob4_mDwWkM0/key_01.jpg): `key_01.jpg`, `key_02.jpg`, `key_03.jpg`, `key_04.jpg`, `key_05.jpg`, `key_06.jpg` |
Lưới đầu vào bác sĩ: [PYH 1](../../cache/r5-reference/pyh_sheet1.jpg), [PYH 2](../../cache/r5-reference/pyh_sheet2.jpg), [Xấu Vê Nờ 1](../../cache/r5-reference/yt_sheet1.jpg), [Xấu Vê Nờ 2](../../cache/r5-reference/yt_sheet2.jpg), [TikTok 1](../../cache/r5-reference/lc_sheet1.jpg), [TikTok 2](../../cache/r5-reference/lc_sheet2.jpg). `yt_head.md` chỉ dùng kiểm chéo hook X0; WPM dùng VTT gốc đã tải lại và khử lặp.

Phần chưa đủ bằng chứng: âm nhạc/SFX thực nghe; WPM S1/H1/D0/Z1/Z2; view và URL bài D0; danh tính tập upload X0; tỷ lệ giữ chân/CTR/chi phí hậu trường; tập 4–5 kênh Việt trưởng thành thuần hoạt hình phẳng; tốc độ lời dọc sức khỏe tiếng Việt. Những mục này không được đánh dấu đã hoàn thành chỉ vì đã có bảng số đo.
