# R5.2 — Kiểm toán khoảng cách xưởng ↔ sản phẩm mẫu

Ngày kiểm: 2026-11-23. Chỉ đọc, không chạy xưởng/render/API, không commit. Code: nhánh `r5-2-factory-gap-audit`, HEAD `07533cc`; dữ liệu sống được đọc đến sự kiện `2026-11-23T20:10:30+07:00`. Đây là kiểm toán sản phẩm và hợp đồng sản xuất, không thẩm định lại các kết luận y khoa.

## 1. Phạm vi, quy ước và kết luận chính

- Đường dẫn code tương đối tính từ `E:/pyh-r5-2/`. `D` = `E:/Protect Your Health/`; `P3` = `D/projects/thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi/revisions/001/`; `L3` = `D/topics/logs/thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi/`. Những đường dẫn viết tắt này đều là địa chỉ bằng chứng, không phải file trong checkout kiểm toán.
- Đã mở trực tiếp đủ 7 ảnh: `D/cache/r5-reference/{pyh_sheet1.jpg,pyh_sheet2.jpg,yt_sheet1.jpg,yt_sheet2.jpg,lc_sheet1.jpg,lc_sheet2.jpg,xuong-phim-2.5d-editor.webp}`; đã đọc `yt_head.md`. Contact sheet chứng minh bố cục ở khung lấy mẫu, không chứng minh mọi khung/chuyển động/âm thanh. Không có timestamp lấy mẫu trong các JPG nên chưa đo được chính xác nhịp cắt 3–5 giây của mẫu YouTube.
- **Nguyên nhân chính của cảm giác slide là hợp đồng hình + cách renderer diễn giải dữ liệu:** ngân sách buộc cơ chế chiếm 55–70%, bằng chứng 15–25%; `entrances` có tab được chuyển thành phiếu/bảng. Trong bản dựng đo được, 10 cảnh bảng và 7 thẻ nguồn chiếm 246,43/460,07 giây = **53,56%**. Nguồn: `src/healthvideo/domain/visual_budget.py:96`, `video/src/components/AuthoredPanels.tsx:8`, `video/src/scenes/MechanismScene.tsx:163`, `P3/renders/render-input.json`.
- **Không thể quy hết cho writer thiếu chỉ dẫn kể chuyện:** skill hiện hành đã cấm đọc tên nguồn và yêu cầu cắt đoạn định nghĩa/danh sách; kịch bản hiện tại có ẩn dụ, tình huống và 0 câu đọc tên nghiên cứu. Khoảng cách còn lại là mật độ thông tin, đoạn lời dài và không có hợp đồng shot theo câu. Nguồn: `.agents/skills/pyh-writer/SKILL.md:43`, `:52`, `src/healthvideo/domain/storyboard.py:337`, `P3/script/script.yaml` (đo tại §3).
- **Chi phí lớn nằm ở vòng sửa/kiểm/khôi phục tích lũy**, chưa có bằng chứng đổi model mạnh hơn sẽ giải quyết: activity ghi 269 lượt bắt đầu, 265 kết thúc; log sản phẩm lưu 24 vòng, tất cả chưa đạt. Nguồn: `D/topics/logs/activity.jsonl` lọc slug P3; `P3/reviews/product-review-log.yaml`.
- Dữ liệu hiện hành đã qua nhiều lượt sửa; không coi nó là nguyên trạng lần sinh đầu hoặc đồng nhất hash với JPG tham chiếu. SHA-256 byte đầu 16 ký tự: script `d97c7a8d6c254939`, storyboard `48a9abee42a743ff`, render-input `7368b72029351002`. Code checkout chưa được chứng minh trùng toàn bộ code đã nạp ở từng lượt lịch sử. `RTK.md` được AGENTS dẫn nhưng không tồn tại tại gốc checkout; không suy diễn nội dung.

## 2. Vì sao thành slide: truy vết và số đo

### 2.1. Chuỗi dữ liệu thực tế

1. **Expert → script:** bản đồ explain-first dùng tầng anatomy/physiology/pathophysiology/pathology, cần ít nhất 2 tầng và có cả bình thường lẫn bệnh. Visual của tầng chỉ có 4 loại cơ chế. Khi scene trỏ tầng, draft kiểm loại visual phải khớp. Đây là lực kéo về bài giải thích cơ quan trước tình huống, dù prompt nói không phải đọc hết bản đồ. Nguồn: `src/healthvideo/domain/explainer.py:8`, `:23`, `:55`, `:63`; `src/healthvideo/workflows/draft.py:114`; `src/healthvideo/prompts/research.md:21`; `P3/explainer/explainer.yaml` (2 tầng, đều dùng `hepatocyte_sinusoid_unit`).
2. **Script → storyboard:** P3 có 31 đoạn `line`, 31 scene, mỗi scene trỏ đúng một line khác nhau; narration khớp nguyên văn script ở cả 31/31 cảnh. Một `line` ở đây là đoạn nhiều câu, không phải một câu nói. `S01` chứa 5 câu nhưng chỉ một visual và một subject. Schema cho phép nhiều scene cùng line; thực tế tác giả chưa khai thác. Nguồn: `P3/script/script.yaml:7`, `P3/storyboard/storyboard.yaml:6`; `src/healthvideo/render/timing.py:140` (chia thời lượng cho nhóm scene cùng line).
3. **Storyboard → render-input:** `retime_storyboard` thay start/duration theo WAV; `apply_alignment` gắn timing từ; `build_render_input` chuyển nguyên scene/style, không sáng tác thêm shot. Do đó chỉnh timing không tự tạo bối cảnh mới. Nguồn: `src/healthvideo/workflows/produce.py:764`, `:843`; `src/healthvideo/render/timing.py:128`; `src/healthvideo/render/input.py:118`.
4. **Render-input → Remotion:** `HealthVideo` chọn component bằng `scene.visual`, toàn video dài dùng nền sáng. Với cơ chế `scale_zoom`, không có bảng thì vào `ScaleZoomStage`; có hàng 3 cột thì sang `SplitClinicalWorksheetStage`. Whiteboard có bảng + ảnh cũng đi cùng stage này. Nguồn: `video/src/HealthVideo.tsx:43`, `:60`; `video/src/scenes/MechanismScene.tsx:125`, `:163`; `video/src/scenes/WhiteboardScene.tsx:70`.
5. **Bảng là hành vi code cụ thể:** `panelRows` nhận tab làm dấu phân cột; 2 cột thành heading/detail, 3 cột thành worksheet. Stage ngang dành hộp hình 960px và hộp phiếu 824px, bảng có 3 cột con; cảm giác “hai cột” là hai vùng lớn hình/phiếu. Các hàng xuất hiện dần rồi tích lũy, không thay toàn cảnh theo câu. Nguồn: `video/src/components/AuthoredPanels.tsx:8`, `:18`, `:53`; `video/src/medanim/SplitClinicalWorksheetStage.tsx:44`, `:53`, `:209`.
6. **Chữ nhỏ được chấp nhận bằng co chữ:** worksheet có vòng giảm font xuống tới 1px để chứa nội dung; thẻ nguồn tự co tới hệ số 0,3, vẫn hiện title, journal/year, PMID/DOI. Tại stage split, title ngang 28px, takeaway 18px; artwork có nhãn compact 10–14px. Chuyển hình 1080p xuống 720p làm các cỡ 18/28px còn 12/18,7px trước các phép scale khác. Đây là cơ chế gây khó đọc, không phải lỗi chỉ do font tiếng Việt. Nguồn: `video/src/components/AuthoredPanels.tsx:57`; `video/src/scenes/SourceCardScene.tsx:164`, `:243`; `video/src/medanim/SplitClinicalWorksheetStage.tsx:90`; `video/src/medanim/ScientificHepaticArtwork.tsx:416`, `:453`.

### 2.2. Các luật khuyến khích đầu ra này

- Storyboard chỉ có một `visual_style` toàn video, chọn trong `scale_zoom`, `iso_infographic`, `whiteboard`; không có style kể chuyện nhân vật. `scale_zoom` vẫn cho whiteboard nhưng whiteboard/outro bị ngân sách explain-first giới hạn. Không phải schema bắt buộc mọi cảnh là tế bào. Nguồn: `src/healthvideo/domain/storyboard.py:14`, `:18`, `:517`; `src/healthvideo/prompts/storyboard_design.md:32`; `P3/storyboard/storyboard.yaml:3`.
- Skill đạo diễn yêu cầu chart/crop 16–24%, >=4 subject, đổi nhịp <=6s, dùng SVG cho cơ chế, source_card cho diễn giải ledger. Code budget thực tế cho chart/crop 15–25%; “đủ subject” và “đổi focus” có thể đạt mà vẫn chỉ lặp lá gan/tế bào. Nguồn: `.agents/skills/pyh-storyboard-director/SKILL.md:25`, `:28`; `src/healthvideo/domain/visual_budget.py:96`; `src/healthvideo/domain/storyboard.py:550`.
- Prompt phân cảnh cho `scale_zoom` khi đi từ cơ quan → tế bào → phân tử; chỉ cho FLUX cảnh đời sống, không hình y khoa; bắt mascot ở hook/đầu chương/outro. Skill writer đẩy nguồn ra source_card/chữ nhỏ/posts. Các lựa chọn này hợp an toàn nhưng cộng dồn thành sơ đồ + nhãn + nguồn + mascot, không hình thành nhân vật trải qua chuyện. Nguồn: `src/healthvideo/prompts/storyboard_design.md:19`, `:23`, `:24`, `:32`; `.agents/skills/pyh-writer/SKILL.md:52`.
- `beats` hiện chỉ hợp lệ khi scene có anatomy; focus/labels/action phải thuộc registry cơ quan. `on_screen_text` tối đa 90 ký tự nhưng `entrances` và metadata source_card làm tăng chữ ngoài giới hạn này. Schema thiếu shot size, background/character ID và đường diễn hành động theo câu. Nguồn: `src/healthvideo/domain/storyboard.py:348`, `:352`, `:443`, `:456`.
- Editor bị yêu cầu chỉ sửa issue và không thêm motion ngoài từ vựng nhận diện; hữu ích để chống sửa vô hạn nhưng không đủ quyền sáng tạo để đổi một trường đoạn slide thành chuyện. Nguồn: `.agents/skills/pyh-editor/SKILL.md:25`; `src/healthvideo/prompts/revise_product.md:13`, `:20`.

### 2.3. Đếm P3 revision 001

Nguồn cho toàn bộ bảng: `P3/storyboard/storyboard.yaml`, `P3/renders/render-input.json` (fps 30), `P3/assets/asset-manifest.yaml`. Đếm duration bằng `duration_frames/30`; không lấy mtime làm thời gian chạy. SB = storyboard dự kiến, RI = render-input đã retime.

| Chỉ số | Kết quả |
|---|---|
| Scene / tổng thời lượng | 31; SB 478,13s; RI 460,07s (7:40,07), `youtube_cta: null` |
| Duration/scene RI | Trung bình 14,84s; trung vị 13,97s; min 6,27s; max 25,57s; 31/31 scene dài hơn 6s |
| Loại scene: số / giây RI | anatomy 9/152,20; process 7/92,47; comparison 2/17,43; timelapse 2/40,10; source_card 7/98,87; whiteboard 3/48,17; outro 1/10,83 |
| Nhóm ngân sách RI | mechanism 65,69%; chart/crop 21,49%; whiteboard + outro 12,82% — nằm trong ngân sách explain-first |
| Lặp subject | 20 scene cơ chế, 6 subject; hepatocyte 7 và liver_organ 7 = 14/20; các subject còn lại 2,2,1,1 |
| Bảng/nguồn | 10 scene 3 cột: S02,S03,S08,S19,S23,S42,S46,S40,S32,S35; 147,57s. 7 source_card: S17,S28,S24,S30,S45,S38,S41; 98,87s. Hai nhóm không trùng; 17/31 scene, 53,56% thời lượng |
| Beat / mascot | 88 beat; 8 scene gắn asset mascot. Beat có thể chỉ đổi nhãn/focus, không tương đương 88 hình mới |
| FLUX khác nhau thực dùng | 5 path/5 SHA trong manifest, tham chiếu tại 6 scene; `clinic-preparation.png` dùng 2 lần. Thư mục illustrations có 6 PNG khác SHA, nhưng 1 PNG ngoài 5 asset manifest không được tính vào hình đã dùng |
| Candidate lưu lại | 27 PNG candidate trong `P3/reviews/visual/`; 10 file `review-01..10.yaml`. Không coi 27 PNG là 27 lời gọi GPU: có cache và nhiều vòng duyệt |

**Chữ/cảnh:** bảng dưới đếm đơn vị cách trắng (tiếng Việt không tương đương từ ngôn ngữ học). `T` = `on_screen_text`; `E` = tổng chữ trong entrances; `N` = title nguồn. T/E có thể trùng nội dung, không cộng máy móc. E có thể xuất hiện lần lượt. Đây là đo dữ liệu chữ authored, chưa phải OCR hay số chữ đồng thời của mỗi frame; nhãn hardcode, journal/DOI, takeaway và caption còn nằm ngoài T. Không có dữ liệu đếm pixel đầy đủ từng frame.

| Scene | RI giây | T / E / N | Scene | RI giây | T / E / N |
|---|---:|---:|---|---:|---:|
| S01 | 22,30 | 10/10/0 | S02 | 13,13 | 11/31/0 |
| S03 | 20,13 | 7/38/0 | S04 | 23,23 | 10/10/0 |
| S06 | 19,47 | 12/12/0 | S08 | 22,90 | 8/40/0 |
| S11 | 10,93 | 15/15/0 | S12 | 17,70 | 16/16/0 |
| S17 | 14,10 | 18/18/27 | S18 | 10,83 | 14/14/0 |
| S19 | 17,87 | 15/37/0 | S20 | 25,57 | 12/84/0 |
| S23 | 14,53 | 9/30/0 | S28 | 9,87 | 19/19/7 |
| S24 | 24,03 | 13/71/15 | S30 | 16,43 | 10/72/11 |
| S27 | 7,33 | 6/6/0 | S42 | 13,80 | 11/34/0 |
| S43 | 6,50 | 11/11/0 | S45 | 13,40 | 11/11/9 |
| S46 | 13,97 | 14/39/0 | S37 | 18,83 | 10/10/0 |
| S40 | 13,57 | 17/31/0 | S31 | 16,67 | 13/13/0 |
| S38 | 6,27 | 10/17/9 | S39 | 10,77 | 11/11/0 |
| S41 | 14,77 | 20/20/9 | S32 | 8,67 | 12/27/0 |
| S34 | 12,67 | 11/11/0 | S35 | 9,00 | 11/23/0 |
| S36 | 10,83 | 11/11/0 | — | — | — |

Chỉ T đã có 378 đơn vị (6–20/cảnh). S17 còn title nguồn 27 từ tiếng Anh và interpretation 98 đơn vị; renderer chia interpretation thành câu hoặc dùng AuthoredStep, nên 98 không phải số chữ hiện cùng lúc. S20 có E=84, lớn hơn nhiều T=12: giới hạn T 90 ký tự không bảo vệ được tải chữ thực. Nguồn: `P3/renders/render-input.json`, `video/src/scenes/SourceCardScene.tsx:180`, `video/src/components/AuthoredPanels.tsx:18`.

## 3. Kịch bản: có tiến bộ nhưng chưa thành chuyện

**Hook 30 giây đầu:** N01/S01 kéo từ 0–22,30s: nhắc ALT/AST → giải thích men thoát khỏi tế bào → mỉa tên “mát gan” → cảnh báo thảo dược → câu hỏi. Từ 22,30–30s đã sang N02/S02, nhắc không tự bỏ thuốc kê đơn. Như vậy mở đầu chuyển nhanh từ vấn đề quen sang hai nhánh tư vấn; chưa để người xem đi qua một hành động và kết quả. Mẫu YouTube dành khoảng 0–31s cho cùng một người nằm giả ngủ nhưng đầu vẫn nghĩ, rồi mới đẩy nghịch lý. Nguồn: `P3/script/script.yaml:7`, `P3/renders/render-input.json` (S01,S02); `D/cache/r5-reference/yt_head.md` [00:00]–[00:31].

**Phương pháp tỷ lệ:** tách câu ở `. ! ?` theo sau là khoảng trắng; một người kiểm mã hóa nội dung, không phải thước đo chất lượng chuẩn hóa. S = tình huống cụ thể/diễn hành/ẩn dụ; B = hỏi dẫn, cầu nối, CTA; F = giải thích, dữ kiện, liệt kê hoặc chỉ dẫn còn lại. “Bạn” đơn thuần không được tính là kể chuyện. Nguồn đầu vào: `P3/script/script.yaml`; transcript tự động `yt_head.md` được khử phần lặp bằng nối suffix/prefix token dài nhất; không đếm 151 segment như 151 câu.

- **Toàn P3:** 31 đoạn, 1.682 đơn vị cách trắng, 93 câu; S=15 (16,13%), F=64 (68,82%), B=14 (15,05%). S gồm N01.3,N02.2,N03.4,N04.1,N04.4,N04.5,N17.1,N17.2,N19.2,N20.1,N20.2,N42.1,N37.4,N40.2,N40.3 (số sau dấu chấm là thứ tự câu trong đoạn). B gồm 9 câu hỏi còn lại, N27.1,N43.1 và 3 câu N36; F là phần bù. Các trường hợp “công cụ”/phiếu giả định được tính rộng cho P3, không chỉ truyện hoàn chỉnh.
- **Cùng cửa sổ ~150s:** 8 đoạn đầu P3 kết thúc ở 149,80s: 32 câu, S=6 (18,75%), F=24 (75%), B=2 (6,25%). Mẫu 0–150s khử lặp cho 41 đơn vị kết câu hoàn chỉnh và 1 đoạn cuối dở; bỏ đoạn dở: S=31 (75,61%), F=8 (19,51%), B=2 (4,88%). Phép tách không xử lý riêng dấu câu bên trong ngoặc kép nên đây là tỷ lệ theo quy tắc đã nêu, không tỷ lệ câu ngữ pháp tuyệt đối.
- Để tái kiểm mẫu: 41 câu đầy đủ sau khử lặp, đánh số từ “Hãy tưởng tượng cảnh này.”; S=1–18,20–24,28,29,32,36–38,40,41; B=19,25; F=26,27,30,31,33–35,39. Các ẩn dụ nổi bật là họp trong đầu, tắt máy/công tắc, chuyển giao quyền lực, bình nước; không kiểm định tính đúng y khoa của video mẫu.
- **Đọc tên nghiên cứu: 0/93 câu hiện tại.** Đọc trực tiếp và rà `nghiên cứu`, `tổng quan`, PMID/DOI, AASLD, năm 20xx không thấy câu đọc nguồn; silymarin/statin là tên hoạt chất/nhóm thuốc, không tên nghiên cứu. Tên nghiên cứu tiếng Anh hiện trên source_card, ví dụ S17; không được kết luận lời đọc có lỗi này từ ảnh. Nguồn: `P3/script/script.yaml`; `P3/storyboard/storyboard.yaml:507`.
- N04 đã có ẩn dụ dụng cụ/xưởng; N20 dựng cảnh uống hết hộp rồi thở phào vì ALT bình thường; N37 có quên tên hộp. Tuy vậy hình vẫn chủ yếu cơ quan/phiếu, không thể hiện đầy đủ hành động, cảm xúc và hậu quả mà lời gợi ra. Nguồn: `P3/script/script.yaml:54`, `:176`; `P3/storyboard/storyboard.yaml`; `D/cache/r5-reference/pyh_sheet1.jpg`, `pyh_sheet2.jpg`.

**Lực kéo về văn giáo trình nằm ở đâu:** writer và script_critic hiện đã chống giọng giáo trình, không ép ẩn dụ, chấm nhịp/hình dung; medical_expert còn ghi rõ bản đồ không buộc kể mọi tầng. Vì vậy không có cơ sở nói ba skill này chỉ quan tâm an toàn. Nhưng chúng cùng phải phục vụ bản đồ explain-first, từng claim/ngoại lệ và outline; prompt/skill writer vẫn ghi 10–25 phút, 4–8 chương, trong khi runtime `youtube_long` thực tế chấp nhận 1–25 phút. Đây là mâu thuẫn có thể khuyến khích kéo dài/đủ mục và cần dọn, không được cáo buộc nó đã trực tiếp tạo từng câu dở. Nguồn: `.agents/skills/pyh-writer/SKILL.md:45`, `:63`; `.agents/skills/pyh-script-critic/SKILL.md:32`; `.agents/skills/pyh-medical-expert/SKILL.md:28`; `src/healthvideo/prompts/draft.md:20`; `src/healthvideo/domain/format_profile.py:22`.

Thiếu tiêu chí nghiệm thu “mỗi câu có hình hành động gì”, thời gian chờ câu hỏi được trả lời, độ mới về ý sau mỗi đoạn, và số cảnh chỉ đọc bảng. Sáu điểm critic hiện có đủ nơi để nhận xét nhưng chưa định nghĩa các phép kiểm này. Nguồn: `.agents/skills/pyh-script-critic/SKILL.md:34`, `:52`; `src/healthvideo/prompts/script_review.md:29`; các số đo ở §2–3.

## 4. Pipeline hình và khoảng cách với Xưởng Phim 2.5D

| Nhu cầu mẫu | Năng lực hiện tại / khoảng thiếu có bằng chứng |
|---|---|
| Mỗi câu một hình mới | Có thể chia nhiều scene cùng line và retime theo nhóm; hiện 31 đoạn →31 scene, không có sentence/shot contract bắt buộc. Cần shot/subshot theo câu hoặc mệnh đề có hành động, không chỉ tăng focus. `src/healthvideo/render/timing.py:140`; `P3/renders/render-input.json` |
| Nhân vật nhất quán | Brand có mascot tái dùng 9 pose, schema asset chỉ path/role/pose; chưa có actor ID/character sheet/đồ mặc/hướng nhìn xuyên cảnh. Mascot phản ứng ở góc không thay vai người xem đang hành động. `src/healthvideo/domain/storyboard.py:203`; `.agents/skills/pyh-storyboard-director/SKILL.md:31` |
| Ảnh tham chiếu FLUX | **Đã có ở tầng thấp:** `MAX_REFS=2`, hash có refs, CLI truyền `--ref`, generator đưa `image=ref_images`. **Chưa nối thành hợp đồng sản xuất:** `generate_candidates` chỉ nhận prompt/dimensions/seed; đường produce cũng gọi không refs. Không thể nói hoàn toàn thiếu image-reference, nhưng đường candidate hiện chưa giữ danh tính nhân vật bằng ref. `src/healthvideo/visuals/flux.py:16`, `:21`, `:85`, `:135`; `tools/flux/generate.py:96`; `src/healthvideo/workflows/produce.py:373` |
| Bối cảnh đời thường tái dùng | 5 ảnh manifest của P3 là phiếu/đơn/bao bì/chuẩn bị khám/vào viện; prompt riêng từng ảnh, có chừa nửa phải cho overlay. Chưa có trường background_id/prop placement trong Scene; khó tái dùng phòng ngủ, nhà bếp, bàn làm việc như mẫu. `P3/assets/asset-manifest.yaml:9`, `:30`, `:79`; `src/healthvideo/domain/storyboard.py:337` |
| Chuyển động 2D nhân vật | Remotion có frame, camera, cue và beat, nên làm được về kỹ thuật; registry hiện hướng vào cơ quan, chưa có skeleton/actor-action/đường đi/x-y-z theo shot trong schema. Đổi scale/camera hoặc reveal chữ không tạo ra động tác nhân vật. `video/src/scenes/MechanismScene.tsx:30`, `:61`; `src/healthvideo/domain/storyboard.py:193`, `:443` |
| Thư viện medanim | Có catalog chỉ trả animation đã duyệt, hữu ích cho cơ chế tái dùng, không đồng nghĩa thư viện người/bối cảnh/đạo cụ đời thường. P3 vẫn trỏ anatomy subjects, không actor. `src/healthvideo/workflows/medanim_library.py:343`; `src/healthvideo/domain/medanim_library.py:326`; `P3/storyboard/storyboard.yaml` |
| Clip dọc kiểu lc | Mẫu có đồ thị trung tâm, card/icon thay trạng thái và từ khóa màu; không phải yêu cầu nhiều tranh mới như mẫu YouTube. PYH có word timing/motion nhưng art-director yêu cầu subtitle tĩnh, shorts prompt lại cho highlight từ/cụm. Cần một hợp đồng riêng cho dọc, không áp nguyên stage ngang chia phiếu. `.agents/skills/pyh-art-director/SKILL.md:35`; `src/healthvideo/prompts/shorts_plan.md:19`; `D/cache/r5-reference/lc_sheet1.jpg`, `lc_sheet2.jpg` |

Ảnh `xuong-phim-2.5d-editor.webp` cho thấy 10 cảnh/60 câu, thoại có nhãn WIDE/CLOSEUP/TWO_SHOT/INSERT, thư viện bối cảnh, actor có tọa độ/kích thước/lớp, timeline Cảnh–Thoại–Âm thanh và nút MP4/CapCut. Đây là tham chiếu cấu trúc nhìn thấy, chưa xác minh phần mềm thực xuất được gì. Khoảng thiếu cốt lõi của PYH là **ngữ pháp dựng cảnh**: một môi trường tái dùng, một diễn viên có danh tính, nhiều shot thoại trong cùng cảnh, track độc lập. Không cần xây editor UI/CapCut trước khi có được ngữ pháp này. Nguồn đối chiếu: ảnh trên; `src/healthvideo/domain/storyboard.py:337`, `:203`; `video/src/HealthVideo.tsx:52`.

## 5. Agent và hợp đồng: đủ vai nhưng mục tiêu còn lệch

Có **16 vai** trong `profiles/company.yaml:25`; `tiers` chỉ là chuỗi mặc định, `roles.*.models` ghi đè ở nhiều vai. Skill được chèn dưới dạng chỉ dẫn đọc; prompt bước/quy tắc cứng thắng skill (`src/healthvideo/company.py:21`, `:176`; `src/healthvideo/workflows/runner.py:264`). Bảng sau bao quát đầu vào, đầu ra, tiêu chí và điểm thiếu; `S/<tên>` viết tắt `.agents/skills/<tên>/SKILL.md`.

| Vai / bước | Đầu vào → đầu ra, tiêu chí chính; khoảng thiếu | Hợp đồng skill + prompt/code |
|---|---|---|
| coordinator / chat | Tin bác sĩ + company_summary → CoordinatorReply/assignments; đúng quyền/định tuyến. Chất lượng sản phẩm phụ thuộc brief chuyển giao | `S/pyh-coordinator:10`, `:37`; `src/healthvideo/prompts/coordinator.md:1` |
| coordinator_senior / chat_deep, repair_diagnose | Chat/log/state → reply hoặc Diagnosis/Acceptance; nguyên nhân có chứng cứ, test. Dễ lặp chẩn đoán lỗi nội dung | `S/pyh-coordinator-senior:8`, `:18`, `:31`; `src/healthvideo/workflows/repair_service.py:645` |
| researcher / topic_research, channel_analytics | Sheet/tín hiệu/metrics → dossier/rubric100, ChannelInsights; có viral40, urgency25, evidence20, feasibility15, không bịa retention. Có tiêu chí khán giả nhưng chưa là nghiệm thu từng shot | `S/pyh-researcher:8`, `:20`; prompt nhúng `src/healthvideo/workflows/researcher.py:491`, `src/healthvideo/workflows/channel_analytics.py:484` |
| scout / scout | Đề đã giao + queue → kiểm trùng/audience/câu hỏi; chỉ kiểm đề, không discover/chấm thay researcher. Có thể bỏ lần gọi riêng | `S/pyh-scout:8`, `:30`; `profiles/company.yaml:70` |
| medical_expert / research | Câu hỏi + bằng chứng + questions → records/claims/ledger/brief/explainer; support/locator/giới hạn. Không sở hữu cấu trúc câu chuyện | `S/pyh-medical-expert:8`, `:35`; `src/healthvideo/prompts/research.md:14`, `:24` |
| writer / draft, revise_medical | Brief/ledger/feedback → script/outline/questions; audience/promise/payoff, tự nhiên, không thêm claim. Còn chỉ dẫn 10–25 phút và khung tối thiểu để qua validator | `S/pyh-writer:19`, `:59`; `src/healthvideo/prompts/draft.md:14`, `:20`; `src/healthvideo/prompts/revise_medical.md:1` |
| storyboard_director / storyboard_design | Script/explainer → storyboard/manifest/clip-plan, SVG; đúng hash/budget/pose/beat. Chưa giao actor/background/shot/storyboard prototype cho người xem | `S/pyh-storyboard-director:14`, `:41`; `src/healthvideo/prompts/storyboard_design.md:18` |
| voice_director / voice_prep | Script/voice lexicon → VoicePrepSheet, script hash; đúng đọc tên/số/đơn vị. Không thể tự nhận đã nghe khi chưa có audio | `S/pyh-voice-director:8`, `:18`, `:24`; `src/healthvideo/prompts/voice_prep.md:1` |
| script_critic / script_review | Script/outline/brief/ledger → review 6 điểm, mỗi điểm >=7; hình dung/nhịp/cá tính có thật, không chỉ safety. Thiếu tiêu chí shot và tải thông tin định lượng | `S/pyh-script-critic:19`, `:31`, `:50`; `src/healthvideo/prompts/script_review.md:29` |
| art_director / visual_review | Candidates + sheet + lời → chọn/reject/prompt mới; đúng màu/tay/quyền/nhãn/khớp lời. Quyết định giữ ảnh không đồng nghĩa duyệt được mạch chuyện | `S/pyh-art-director:15`, `:22`, `:45`; `src/healthvideo/prompts/visual_review.md:8` |
| editor / revise_production, revise_product | Review + sheet + timing → sửa phần được giao; test/check qua. Skill và prompt đang khác phạm vi quyền, xem bên dưới | `S/pyh-editor:16`, `:41`; `src/healthvideo/prompts/revise_product.md:13`; `src/healthvideo/prompts/revise_production.md:1` |
| product_critic / product_review | Video sheet/QA/timing/posts → review 7 điểm >=7; gồm nhịp, mở-kết, độ rõ. Không nghe được audio; không thể bảo đảm âm thanh hay bằng điểm ASR | `S/pyh-product-critic:18`, `:31`, `:52`; `src/healthvideo/prompts/product_review.md:12`, `:14`, `:18` |
| copywriter / posts | Script/outline/clip/ledger → PostSet/thumbnail; lời hứa khớp payoff, posts-check. Bị giao lại CTA/caption cùng shorts producer | `S/pyh-copywriter:8`, `:17`, `:32`; `src/healthvideo/prompts/posts.md:1` |
| shorts_producer / shorts_plan | Đầu vào đã duyệt + scene ranges → 1–4 ShortsPlan; hook<=2s, caveat/safe-zone/45–90s ở skill, 60–90s ở prompt. Khó đổi hook nếu chỉ được chọn đoạn dài đã khóa | `S/pyh-shorts-producer:8`, `:14`; `src/healthvideo/prompts/shorts_plan.md:18`, `:20` |
| feedback_analyst / feedback_inbox | Feedback + project/log → summary/tasks(kind,target,request,done_when); đúng luồng/scope, không tự sửa. Chồng phần phân loại với coordinator | `S/pyh-feedback-analyst:8`, `:16`, `:31`; `src/healthvideo/prompts/feedback_triage.md:1` |
| repair_engineer / repair | Diagnosis/log/scope → code fix + test/lint + report; không thay y khoa/cổng. Không nên là cơ chế xử lý lỗi hình/ngữ điệu vốn là nội dung | `S/pyh-repair-engineer:15`, `:20`, `:29`; prompt schema nhúng `src/healthvideo/workflows/repair_service.py:645` |

**Mâu thuẫn/chồng chéo cần dọn trước khi thêm vai:**

1. Editor skill cấm sửa storyboard/manifest/clip/voice; prompt revise_product cho phép các file này với khóa metadata. Prompt thắng theo company, nhưng agent phải tự giải xung đột mỗi lượt. Nguồn: `.agents/skills/pyh-editor/SKILL.md:42`, `:46`; `src/healthvideo/prompts/revise_product.md:15`; `src/healthvideo/company.py:21`.
2. Art-director yêu cầu subtitle tĩnh, không highlight từng chữ; shorts skill/prompt cho highlight nếu có Whisper. Writer skill nói 10–25 phút, runtime chỉ tối thiểu 1 phút. Nguồn: `.agents/skills/pyh-art-director/SKILL.md:35`; `.agents/skills/pyh-shorts-producer/SKILL.md:17`; `src/healthvideo/prompts/shorts_plan.md:19`; `src/healthvideo/domain/format_profile.py:22`.
3. Storyboard_director làm clip-plan, shorts_producer làm shorts-plan có range/hook/caption, copywriter làm clip captions; cả ba phụ thuộc cùng đoạn đã khóa. Cần một người sở hữu cut range + hook, copywriter chỉ đóng gói. Nguồn: `.agents/skills/pyh-storyboard-director/SKILL.md:42`; `.agents/skills/pyh-shorts-producer/SKILL.md:18`; `.agents/skills/pyh-copywriter/SKILL.md:34`.
4. Chấm khán giả không hoàn toàn thiếu: script có nhịp/cá tính/payoff, product có nhịp/mở-kết; thiếu **ngưỡng cụ thể bám mẫu** và xem animatic trước GPU. Art duyệt ảnh và product duyệt cuối có phần trùng bố cục/phong cách, trong khi lỗi kể chuyện chỉ lộ rõ sau dựng. Nguồn: `src/healthvideo/prompts/product_review.md:18`; `.agents/skills/pyh-art-director/SKILL.md:33`; §2–3.
5. Vòng sau “không nêu lỗi mới ở phần không đổi” giúp dừng soi lại vô tận, nhưng có nguy cơ giữ nguyên điểm nếu vòng đầu bỏ sót chất lượng tổng thể. Round23 script hiện ghi giữ điểm khi không còn issue/diff; đây là bằng chứng giới hạn cơ chế, không bằng chứng critic cố ý bỏ qua. Nguồn: `.agents/skills/pyh-script-critic/SKILL.md:8`; `P3/reviews/script-review-log.yaml` round23.

## 6. Model, token, thời gian và vòng sửa thật

### 6.1. Cách đo và giới hạn

- Activity: lọc đúng slug; đếm event start/end, thất bại là end `ok:false` (lỗi gọi agent, không phải số review không đạt). Ghép theo job_id khi có, nếu log cũ thì cặp gần nhất cùng role/step/cli/model; lấy `duration_s`, thiếu thì hiệu ISO timestamp. Tổng là thời gian các lượt cộng dồn, có thể chồng nhau; không phải đường găng hay giờ lao động bác sĩ. `D/topics/logs/activity.jsonl` có 770 dòng; P3 540 dòng, 4 start chưa ghép end.
- Token trong activity chỉ 149/265 end P3 có `usage_available`; tất cả thiếu trường input/output riêng. Bảng ghi tổng `cli_total_tokens` được quan sát và số lượt có usage, **không coi phần thiếu là 0**. Terminal CLI ghi `tokens used` là token toàn phiên, không quy đổi tiền/token mới/billing. Nguồn parser: `src/healthvideo/telemetry.py:40`, `:173`; writer activity: `src/healthvideo/agents.py:568`.
- Rà thêm terminal footer của `*.log` trong thư mục slug (kể cả thư mục con): P3 có 154 log, tổng 24.734.147 token; hóc xương 4 log/418.611; C sủi 6 log/700.845. Đây là quần thể khác bảng activity, có lượt không có activity usage; **không cộng hai tổng**, không gán token log thiếu role bằng phỏng đoán. Input/output riêng cho ba dự án: **không có dữ liệu xác nhận**. Ví dụ footer `L3/20261123T130824823466-omniroute.log`: 49.382 token; `L3/20261119T193535094211-omniroute.log`: 115.891.

### 6.2. PYH-003: từng vai/bước, từ 15/11 đến 23/11

Nguồn toàn bảng: `D/topics/logs/activity.jsonl`, slug P3. Cột “model chạy” là lịch sử, không phải config hiện tại; Sol/Terra/Luna là các ID `gpt-6.1-sol`/`gpt-6.1-terra`/`gpt-6-luna`, Hydrogen/Carbon là ID Gemini tương ứng. Giây làm tròn từ tổng đã ghép; “—” = không có dữ liệu usage.

| Vai / bước | Start / end / lỗi gọi | Tổng giây | Token quan sát / end có usage | Model chạy chính và biến thể |
|---|---:|---:|---:|---|
| coordinator / coordinator | 10/10/0 | 388 | 473.618 /10 | Luna 10 |
| coordinator_senior / repair_diagnose 60, chat senior 1 | 61/60/5 | 10.807 | 3.804.594 /49 | Sol OmniRoute57 + trực tiếp1; Carbon3 |
| medical_expert / research | 5/5/0 | 1.580 | — /0 | Terra4, Carbon1 |
| writer / draft26, revise_medical9 | 35/35/1 | 14.343 | 1.149.664 /9 | Sol OmniRoute32 + trực tiếp1, Carbon1, Sonnet1 |
| storyboard_director / storyboard_design | 6/6/0 | 1.958 | 131.188 /1 | Sol OmniRoute5 + trực tiếp1 |
| voice_director / voice_prep | 17/17/2 | 2.681 | 272.666 /1 | Hydrogen15, Luna1, Terra1 |
| script_critic / script_review | 24/24/1 | 2.439 | 129.946 /3 | Terra22, Carbon2 |
| art_director / visual_review | 14/14/0 | 4.354 | 7.157.678 /12 | Hydrogen12, Carbon2 |
| editor / revise_product31, revise_production7 | 38/37/5 | 15.843 | 2.775.386 /26 | Sol33, Terra1, Orchestrator4 |
| product_critic / product_review | 40/39/12 | 12.063 | 1.887.499 /24 | Terra25, Sol5, Carbon4, Sonnet2, Orchestrator2, Argon-orchestrator2 |
| copywriter / posts | 1/1/0 | 170 | — /0 | Hydrogen1 |
| shorts_producer / shorts_plan | 9/8/1 | 934 | 1.921.324 /6 | Hydrogen7, Carbon1, Terra1 |
| repair_engineer / repair | 9/9/0 | 972 | 329.988 /8 | Sol9 |
| researcher, scout, feedback_analyst | 0 start trong activity của slug | — | không có dữ liệu | Không suy ra vai chưa từng chạy ngoài phạm vi log |

Tổng token activity quan sát **20.033.551**; art_director chiếm 35,73% số token đã ghi, nhưng coverage không đồng đều nên chưa kết luận chi phí thật chiếm 35,73%. Editor và writer đứng đầu thời gian cộng dồn (~4,40h và ~3,98h), sau đó product critic ~3,35h, senior ~3,00h. Đây là bằng chứng nên giảm số vòng và lượng ngữ cảnh trước khi tăng model. Nguồn: cùng activity và bảng trên.

### 6.3. Hai dự án đối chứng, không lấy thiếu log làm số 0

`H` = `hoc-xuong-ca-nuot-ngay-nam-com-to-cach-chua-meo-hay-tu-day-x`; `C` = `uong-1-vien-c-sui-moi-ngay-tang-de-khang-hay-tu-nuoi-soi-can`. Nguồn: `D/topics/logs/activity.jsonl`, `D/projects/<H|C>/revisions/001/`; giây ghép timestamp vì log cũ thiếu duration_s.

| Project / vai | Start/end/lỗi | Giây | Model lịch sử |
|---|---:|---:|---|
| H / medical_expert | 4/3/1 | 2.921 | Carbon high1, medium3 |
| H / writer | 6/6/3 | 3.215 | Sol3, Carbon2, Sonnet1 |
| H / script_critic | 2/2/1 | 1.412 | Carbon medium2 |
| H / storyboard_director | 4/4/1 | 571 | Sonnet3, Sol1 |
| H / voice_director | 2/2/0 | 186 | Hydrogen2 |
| C / medical_expert | 1/1/0 | 1.511 | Carbon medium1 |
| C / writer | 10/10/5 | 7.499 | Sol4, Carbon3, Sonnet3 |
| C / script_critic | 3/3/0 | 1.965 | Carbon medium3 |
| C / storyboard_director | 2/2/0 | 725 | Sol2 |
| C / voice_director | 3/3/0 | 259 | Hydrogen3 |

H có script/storyboard 44/44; C 25/25. H lưu 1 script-review round, C lưu 3 round (submitted=1). Activity của H có 1 research start thiếu end. Hai project không có `audio/tts-usage.json` và không xuất hiện trong station telemetry đang giữ; thời gian/calls FLUX, TTS, render và các vai còn lại: **không có dữ liệu**, không được suy từ test. Nguồn: các đường dẫn trên; `D/topics/logs/station-telemetry.jsonl` (476 dòng, tất cả slug P3).

### 6.4. GPU, render, TTS và thất bại sản phẩm P3

Nguồn bảng: `D/topics/logs/station-telemetry.jsonl`, từ 19/11 15:33:53 đến 23/11 20:08:22 UTC+7. Ghép span_id; tất cả start có end, wait_s ghi 0. Trạm con nằm trong produce nên **không cộng produce với trạm con**. Một span có thể cache-hit hoặc bao gồm retry/clip/chapter; không phải số lần inference hay số MP4 mới.

| Trạm | Start/end | End lỗi | Tổng giây | Trung vị / max giây |
|---|---:|---:|---:|---:|
| produce | 61/61 | 33 | 15.724,39 | 128,72 / 1.995,86 |
| FLUX | 49/49 | 3 | 2.929,36 | 0,41 / 1.886,71 |
| TTS | 42/42 | 10 | 2.057,68 | 0,45 / 1.044,27 |
| Remotion/render | 30/30 | 6 | 9.123,30 | 282,74 / 646,39 |
| QA | 56/56 | 0 | 582,09 | 2,89 / 114,25 |

- Render chiếm ~58,02% tổng span produce ở cùng cửa sổ (tỷ lệ thời lượng trạm, không sử dụng GPU); lớn nhất trong các trạm con đã đo. FLUX/TTS trung vị dưới 1s cho thấy không thể dùng số span để báo số lần sinh mới. Nguồn: bảng telemetry; cơ chế cache ảnh `src/healthvideo/visuals/flux.py:117`.
- TTS receipt tích lũy: **110 request, 31.582 Unicode character**, tất cả `speech-2.8-hd`, 89 text_sha256 khác nhau; không có token/billed credits hay duration từng request. Nguồn: `P3/audio/tts-usage.json` (`count_basis` ghi rõ submitted characters, phải đối chiếu subscription để biết credits).
- Script-review log: 23 round, 19 chưa đạt/4 đạt; product-review: 24 round, 24 chưa đạt (submitted=22). Số round không bằng số calls: một lần gọi có thể lỗi, chẩn đoán không phải review, chu kỳ gửi lại có thể reset. Nguồn: `P3/reviews/{script-review-log.yaml,product-review-log.yaml}`.
- Round24 product ghi nhịp=5, rõ hình=6, âm thanh/phụ đề=5; motion còn S30 12s/giới hạn10s, S37 17,5s/giới hạn6s; 62 cờ phát âm tự động, reviewer chưa nghe nên không kết luận đọc sai. Điểm khớp lời/phong cách=7 không chứng minh đạt mẫu kể chuyện. Nguồn: `P3/reviews/product-review-log.yaml`, round24; `L3/20261123T130824823466-omniroute.log`.
- Log render giữ lại một lỗi CL01: Chrome kết nối quá hạn **25.000ms**, exit1; không lấy timestamp tên file trừ mtime để suy toàn thời gian render. Nguồn: `D/topics/logs/render/20261119T211622249902.log`.
- Run/cache kiểm bổ sung: `D/projects/<slug P3>/renders-cache/` có 113 entry, ví dụ các MP4 chapter hash; không gọi đây là 113 lượt render. Repair giữ 33 `*/diagnosis.yaml`: delegate17, repair12, hold4; activity senior có 60 repair_diagnose start nên số phiếu lưu khác số lượt gọi. Phiếu33 mô tả bundle lồng vào public-dir và chưa nhận đã chạy lại nghiệm thu; không tái hiện trong cuộc kiểm toán này. Nguồn: `D/topics/logs/repair/<slug P3>/{1..33}/diagnosis.yaml`.

## 7. Đề xuất ưu tiên — chưa triển khai

Các ngưỡng dưới đây là **mục tiêu thử nghiệm đề xuất**, không số đã đo trên sản phẩm mẫu và không thay hai cổng bác sĩ. Tác động/chi phí là nhận định kỹ thuật dựa trên §2–6, chưa có benchmark tiền.

| Ưu tiên | Thay đổi và thứ nên bỏ | Tác động / chi phí, cách nghiệm thu |
|---|---|---|
| P0 | Bỏ quota bắt buộc 15–25% chart/source và 55–70% cơ chế đối với video kể chuyện; bỏ yêu cầu >=4 subject khi chỉ cần một cơ chế. Bằng chứng vẫn giữ ledger/nguồn posts/marker | Cao / thấp–vừa; chặn lực kéo trực tiếp tại `domain/visual_budget.py:96`, `domain/storyboard.py:550`. Nghiệm thu storyboard không cần chèn cơ quan/nguồn chỉ để đủ quota |
| P0 | Bỏ nguồn full-screen mặc định và auto-route tab→worksheet khỏi luồng kể chuyện; giữ component bảng/SourceCard như lựa chọn giải thích dữ liệu có chủ đích | Cao / vừa; prototype 60–90s có 0 bảng toàn khung, 0 title nghiên cứu tiếng Anh toàn khung, chữ nhấn mục tiêu <=6 đơn vị/shot ngoài phụ đề. So ảnh mẫu §1 và renderer §2 |
| P0 | Giao writer + storyboard_director chung một AV beat plan: câu hỏi → hành động → phát hiện; mỗi shot có câu/mệnh đề, actor, bối cảnh, hành động nhìn thấy, ý mới. Giữ quyền claim riêng cho y khoa | Cao / vừa; thử nhịp 3–5s có lý do theo câu, đo shot chứ không đếm zoom. Nghiệm thu animatic đoạn mở trước sinh cả video; khoảng thiếu `storyboard.py:337`, số đo §2–3 |
| P0 | Dọn xung đột skill/prompt về quyền editor, phụ đề, thời lượng; bỏ boilerplate 10–25 phút nếu bài trả lời xong sớm | Cao / thấp; một bảng quyền và một profile định dạng dùng chung; rà các cặp dẫn tại §5 trước thử model |
| P1 | Tạo thư viện nhỏ actor/pose/props/background, nối FLUX refs vào manifest/candidate, tái dùng nền; không sinh lại toàn hình cho mọi câu | Cao / vừa–cao; đoạn thử giữ cùng danh tính qua >=6 shot, có wide/closeup/insert và 2 bối cảnh; refs tầng thấp đã có (§4), chưa cần editor UI |
| P1 | Gộp quyền sở hữu clip-plan/shorts-plan vào shorts_producer; copywriter nhận cut đã chốt. Bỏ scout agent riêng nếu chỉ kiểm trùng/schema; gộp phân loại feedback đơn giản vào coordinator | Vừa / thấp–vừa; giảm lần gọi mà vẫn giữ rubric, caveat và quyền duyệt. Hợp đồng chồng tại §5; 9 shorts starts của P3 (§6) |
| P1 | Giữ một critic độc lập sau mỗi mốc sản phẩm thay đổi; bỏ full reread ảnh/log đã có hash. Sửa cache/diff và chỉ đưa issue mở + artefact liên quan | Cao / vừa; đo lại số call/token trên cùng packet, giảm so baseline §6; vẫn kiểm toàn bộ bất biến gate/hash/timing bằng code |
| P1 | Ngừng đưa lỗi thẩm mỹ/nhịp đã xác định vào senior để chẩn đoán lại; chuyển thẳng owner. Bỏ vòng “diagnose” khi cùng incident/input hash không đổi | Cao / vừa; giữ một phiếu có owner/done_when, đo retries cùng fingerprint; baseline 60 diagnosis starts, 33 phiếu lưu (§6) |
| P2 | Dọc dùng profile diagram/card tiến triển + keyword caption; không ép storyboard nhân vật ngang sang 9:16 hoặc bê nguyên phiếu đôi | Vừa / vừa; xem độc lập trên khung 1080×1920 và preview 720p, so lc sheets; chốt dứt điểm mâu thuẫn caption §5 |

### Phân model đề xuất cho đủ 16 vai

Chỉ dùng ID đã có trong config/tài liệu local; không gọi catalog/API để thử trong kiểm toán. `O:` = OmniRoute; model dự phòng không được làm critic nếu đã làm maker thực tế. Đề xuất thay ưu tiên công việc/ngữ cảnh trước khi đổi tier. Nguồn hiện trạng: `profiles/company.yaml:5`–`:234`; bằng chứng khả năng giới hạn: `docs/reference/omniroute.md:44` (chỉ function call/ô màu), `docs/reference/agent-model-evaluation.md:112` (mẫu nhỏ, không đánh giá dài).

| Vai | Đầu chuỗi hiện tại | Đề xuất | Lý do / điều kiện |
|---|---|---|---|
| coordinator | O:Luna | Giữ O:Luna | 10 lượt chat ~388s; định tuyến hữu hạn, chuyển sâu khi cần (§6) |
| coordinator_senior | O:Sol | Giữ O:Sol, chỉ incident mới/phức tạp | Việc code/log khó; cắt 60 lượt diagnosis lặp đáng ưu tiên hơn hạ model |
| researcher | O:Hydrogen | Giữ O:Hydrogen; sync/scoring thuần code | Đã có rubric; chưa có benchmark chất lượng chọn đề của bộ hiện tại |
| scout | O:Luna (bulk) | Bỏ call thường lệ; O:Luna khi phải phán đoán audience | Trùng lặp tên/queue nên code kiểm; không cần model mạnh |
| medical_expert | O:Terra | Giữ O:Terra; O:Sol đối chiếu trường hợp khó | Safety/nguồn cần năng lực, nhưng chưa có benchmark để tuyên bố Terra yếu hoặc Sol tốt hơn |
| writer | O:Sol | Giữ O:Sol với packet gọn + AV plan | Đã có mẫu viết; 35 starts chủ yếu phản ánh vòng sửa, không chứng minh thiếu năng lực model |
| storyboard_director | O:Sol | Giữ O:Sol cho shot plan; O:Terra kiểm ảnh độc lập | Trọng tâm thay ngữ pháp kể chuyện; không giao pixel QA cho Sol chỉ dựa tên model |
| voice_director | O:Hydrogen | Code/lexicon trước, O:Hydrogen chỉ tên/cách ngắt mới | Giảm 17 lần gọi đầy đủ; chưa đủ bằng chứng cho O:Luna xử lý tiếng Việt y khoa tốt hơn |
| script_critic | O:Terra | Giữ O:Terra độc lập writer | Đưa rubric tải thông tin/câu chuyện + ví dụ sai; không thưởng đủ metadata |
| art_director | O:Hydrogen | Giữ O:Hydrogen, chỉ ảnh mới; O:Terra dự phòng | 7,16M token đã ghi/12 lượt là chỗ ưu tiên giảm ảnh/ngữ cảnh; chưa có A/B cho thấy cần model mạnh hơn |
| editor | O:Sol | Giữ O:Sol cho code; sửa dữ liệu đơn giản bằng patch có kiểm | 15.843s tích lũy; scope/renderer mới là nút thắt, không thêm agent motion riêng |
| product_critic | O:Terra | Giữ O:Terra độc lập; QA kỹ thuật bằng code | 12/39 end lỗi gọi; phải tách API/runtime lỗi với phán đoán. Âm thanh vẫn cần người nghe |
| copywriter | O:Luna (bulk) | Giữ O:Luna | Packet đã duyệt, đầu ra hữu hạn; 1 lượt lịch sử Hydrogen chưa đủ so sánh chất lượng |
| shorts_producer | O:Hydrogen | O:Terra cho cut/caveat; metadata lặp dùng code | Tác vụ hiện vượt “điền form”: 9 starts, 1,92M token/6 end có usage. Đây là giả thuyết thử A/B, không kết luận Hydrogen yếu |
| feedback_analyst | O:Luna (bulk) | Gộp vào coordinator; O:Luna chỉ feedback dài nhiều việc | Giảm chuyển tay cho phân loại trùng, senior chỉ điều tra sâu |
| repair_engineer | O:Sol | Giữ O:Sol theo file/test cụ thể | Python/Remotion có hash/gate; 9 end không lỗi gọi nhưng phải nghiệm thu bằng test/retry thật |

Không chọn lại Carbon/Orchestrator/DeepSeek chỉ vì bảng benchmark cũ hoặc catalog: tài liệu 16/11 ghi Carbon timeout, DeepSeek chưa qua payload/toolset thật; tài liệu 14–15/11 là các mẫu nhỏ có Carbon và cấu hình khác. Không kết luận model nào “quá yếu” từ sản phẩm chịu hợp đồng sai; vai đang **dùng công suất quá mức cho phạm vi công việc** là senior/ảnh/voice lặp, bằng chứng là số vòng và token ở §6. Nguồn: `docs/reference/omniroute.md:52`, `:65`; `docs/reference/agent-model-evaluation.md:17`, `:112`.

### Những việc giữ lại và điều chưa biết

- Giữ xác minh nguồn/claim, provenance, QA timing, độc lập maker/critic, hai cổng bác sĩ. Đề xuất bỏ bớt quota/role/call/component mặc định không bao gồm bỏ cổng. Cơ sở: `src/healthvideo/company.py:21`; `docs/reference/omniroute.md:71`; `AGENTS.md` quy tắc 2–3.
- Chưa biết tiền thực trả, input/output/cached token riêng, latency riêng từng HTTP/tool call, inference FLUX thật mỗi ảnh, thời gian người làm/đợi bác sĩ, retention/CTR của sản phẩm và nhịp cắt chính xác mẫu. Ghi **không có dữ liệu**; không nội suy từ giá model hoặc mtime. Nguồn giới hạn: activity/telemetry/tts receipt và JPG đã nêu tại §1, §6.
- Nghiệm thu thay đổi sau này cần cùng một brief, packet, đoạn thử và rubric, so cả hình thực + người nghe; báo median latency/token/calls, tỷ lệ issue tái mở, mức hiểu đúng và đánh giá giữ xem. Đây là thiết kế thử đề xuất, chưa chạy và chưa có kết quả.
