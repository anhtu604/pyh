# R5.3 — Chuẩn chất lượng PYH: giải thích sâu, hình diễn hành

Ngày 2026-11-24 · Trạng thái: dự thảo để bác sĩ chốt các ngưỡng đề xuất ở §10.
Phạm vi phiên này: chỉ viết spec và kế hoạch; không thay code/cấu hình, không commit, không gọi Vibi/FLUX, không bật xưởng.

## 1. Căn cứ, hiệu lực và giới hạn bằng chứng

- Giữ mô hình công ty, hai cổng PIN, phân quyền, chat mở lại đúng luồng của `docs/superpowers/specs/2026-11-08-factory-company-design.md:19`, `:238`; giữ phễu và nguồn thật của `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md:28`.
- Thay các hướng cũ mâu thuẫn về độ sâu, hình, model và hạn ngạch bằng quyết định bác sĩ trong brief R5.3 ngày 24/11. Không mặc nhiên coi những chi tiết triển khai bên dưới đã được bác sĩ duyệt.
- Đọc quy tắc và bàn giao trước khi khảo sát. `CLAUDE.md:123` cấm tách dashboard/produce/CLI, gộp ba agent chấm, bỏ legacy và thêm framework app; R5.3 tuân thủ. Không sửa tiến độ hay file append-only trong phiên tài liệu này.
- Đường dẫn tương đối là checkout `E:/pyh-r5-3`; ký hiệu **P** trong dẫn chứng là `E:/pyh-r5-5`, chỉ đọc. Dẫn `P/video/...:dòng` là code bản thử, không phải code xưởng.
- Nghiên cứu nền: `docs/reference/2026-11-23-factory-gap-audit.md:9`, `:125`, `:141`; `docs/reference/2026-11-23-reference-benchmark.md:155`; `docs/reference/2026-11-23-medanim-signature.md:78`, `:138`; giới hạn benchmark model tại `docs/reference/agent-model-evaluation.md:122`.
- Bản lời chọn hướng là `P/cache/r5-proto/script-v3-deep.md:3`, `:20`, `:40`. Duyệt hướng chương 1 v6 không phải duyệt y khoa toàn bộ video hoặc cho phép chạy xưởng. Nguồn y khoa trong bản thử chưa được tái thẩm định trong nhiệm vụ tài liệu này.
- `P/cache/r5-proto/REPORT.md:1` hiện bắt đầu ở vòng 3/v4 rồi ghi vòng 4–5/v5–v6 (`:78`, `:118`); không có mục riêng vòng 1–2 trong file đã đọc. `script-v2-story.md` không tồn tại ở đường dẫn brief; chỉ biết bản cũ qua REPORT `:8`. Không phục dựng hay gán lời cũ là đã đọc. `RTK.md` và đồ thị `graphify-out/graph.json` không có trong checkout; đã thử truy vấn, dùng đọc file trực tiếp.

## 2. Quyết định nội dung đã chốt

1. Giải thích theo chuẩn y khoa, tường tận bản chất: cơ quan → giải phẫu/cấp máu → đơn vị mô → tế bào → cấu tạo/chức năng/sinh lý → cơ chế bệnh hoặc ý nghĩa xét nghiệm → hành động. Không nhảy từ tên xét nghiệm sang lời khuyên. Tầng không liên quan phải có lý do, không bịa chi tiết để đủ tầng.
2. Một video phục vụ ba lớp: người thường lấy được đáp án; nội dung giải thích sâu nhất trong phạm vi câu hỏi và bằng chứng; bác sĩ trẻ/sinh viên y có lớp tham khảo và cập nhật. Không đánh đổi chiều sâu lấy nhịp cắt nhanh.
3. Hook nêu 2–4 câu hỏi cốt lõi. Mỗi khối sâu có một câu chốt in đậm trong bản lời, nối về câu hỏi. Có đoạn “cập nhật chuyên môn” nêu phạm vi, thời điểm nguồn và mức chắc chắn; kết trả lại từng câu hỏi đúng thứ tự/ID. Mẫu cấu trúc ở `P/cache/r5-proto/script-v3-deep.md:8`, `:35`, `:38`; không sao chép các mệnh đề y khoa chưa kiểm vào chủ đề mới.
4. Mỗi video có một tầng chính TOFU/MOFU/BOFU. TOFU có điều bất ngờ có nguồn trong 30 giây đầu; phần sâu luôn nối về điều người xem muốn biết. BOFU là hành động sức khỏe có căn cứ, điều mang/kể khi đi khám; không bán hàng. Không ép mọi video đủ ba tầng.
5. Giọng kể nói với “bạn”, cảnh và ẩn dụ đời thường, câu ngắn như hướng tham khảo Xấu Vê Nờ “giả vờ ngủ”; giữ giới hạn của ẩn dụ. Nhịp mục tiêu khoảng 265 âm tiết/phút, Vibi speed 1,18; đoạn khó có thể chậm hơn theo hình. Không đọc nguyên metadata nghiên cứu vào lời; phần cập nhật có thể gọi tên hướng dẫn khi tên đó giúp hiểu khác biệt chuyên môn.
6. Mỗi câu y khoa, kể cả câu chốt/cập nhật, phải ánh xạ claim và locator đã đọc. Một câu gồm nhiều mệnh đề phải đủ nguồn cho từng mệnh đề. Abstract chỉ đỡ được nội dung thực có trong abstract; không suy thành đã đọc toàn văn. Thiếu nguồn trả về chuyên gia, không để writer tự bổ sung.
7. Hoạt ảnh y khoa là đặc trưng xuyên chủ đề: giải phẫu, sinh lý, sinh lý bệnh, giải phẫu bệnh, mô phôi, vi sinh. Không bắt mỗi video chứa cả sáu lĩnh vực. Ảnh mô thật phải có provenance; sơ đồ giản lược phải ghi giới hạn trong gói duyệt.

## 3. Tiêu chí đạt và cách đo

Các số có nhãn **ĐX** là đề xuất thử nghiệm, chưa phải kết quả v6 hay bảo đảm retention. Các quyết định bác sĩ ở §2 và cấm sai y khoa/nguồn/giấy phép không được bù bằng điểm mỹ thuật.

| Tiêu chí | Ngưỡng và phép kiểm | Bản chất/căn cứ |
|---|---|---|
| Câu hỏi và đáp án | 2–4 ID ở hook; cuối trả đủ 100%, không đổi câu hỏi giữa chừng; critic chỉ dòng hỏi/đáp | Đã chốt; mẫu bản lời sâu có ba câu |
| Khối sâu | 100% khối có câu chốt, câu hỏi được phục vụ và nguồn; có ≥1 khối cập nhật chuyên môn | Đã chốt về cấu trúc; “khối” là đơn vị ý, không phải mọi scene |
| Nguồn y khoa | 100% mệnh đề y khoa có claim + locator phù hợp; không còn câu hỏi nguồn chưa giải quyết trước cổng y khoa | Đã chốt; kiểm ý nghĩa bằng người chấm, không chỉ đếm ID |
| Hook/phễu | Tầng chính ghi rõ; TOFU có bất ngờ có nguồn ở ≤30s theo WAV thật | Đã chốt; thời gian ước lượng trước cổng, xác nhận lại sau TTS |
| Thẻ chữ/bảng/cây chữ | **ĐX ≤15%** toàn thời lượng MP4, tính hợp các khoảng xuất hiện, không cộng trùng overlay | Giảm mạnh so với 53,56% bảng/nguồn mà R5.2 ghi nhận (`factory-gap-audit.md:44`); v6 chưa có phép đo tỷ lệ tương đương |
| Một lần giữ bảng/thẻ lớn | **ĐX ≤6s** liên tục; credit cuối được chia trang; câu chốt ≤8 đơn vị cách trắng | V6 có phiếu ngắn ≤6s theo REPORT `:137`; mốc 15% là lựa chọn biên tập, không suy từ 6s |
| Nhịp kể chuyện | **ĐX trung vị shot 2,5–3,5s**, P90 ≤8s; báo riêng theo nhóm | V4 28 shot, trung vị 2,767s/P90 3,800s (REPORT `:14`); benchmark R5.1 `:162` |
| Nhịp cơ chế | **ĐX trung vị shot 8–20s**, mỗi đoạn 3–6s có bước nhân quả mới; shot >20s cần lý do và ≥3 bước nhìn thấy | Cho phép theo dõi cơ chế liền mạch; chưa đo trung vị shot cơ chế v6. R5.4 `medanim-signature.md:142` chỉ đề xuất beat 3–6s |
| Nhãn và tải chữ | **ĐX ≤2 nhãn cơ chế cùng lúc**, mỗi nhãn ≤3 đơn vị cách trắng; thuật ngữ cần dài ghi ngoại lệ. Thanh tầng tính riêng, chỉ một thanh | Giảm chữ; không ép tên y khoa thành sai nghĩa. Câu chốt không đồng thời với bảng |
| Tính liên tục | 100% chuyển tầng có vùng đích/anchor, giữ bên cơ thể, màu/danh tính thực thể và chiều dòng; thanh “Cơ thể → … → Enzyme” hiện tầng đang xem | Đã chốt; kiểm chuyển tiếp trước–giữa–sau, không chỉ ảnh đầu/cuối |
| Hình và nhân vật | 0 FLUX trong cơ chế; 0 cơ quan/cơ thể tự vẽ thay hình có phép sẵn; không tạo nhân vật mới; mascot ở câu chốt, vắng trong giải phẫu cận | Đã chốt; vector chỉ diễn hành/phân khoang dựa trên hình khoa học |
| Định dạng | 16:9 không cháy phụ đề lời đọc; 9:16 có phụ đề, nhãn/đường đi còn trong khung, không crop mù từ ngang | Đã chốt; giữ caption rời và word timing phục vụ tiếp cận/QA |
| Âm thanh và kỹ thuật | Đúng voice ID đã ghim, không cắt lời, giải mã toàn MP4 không lỗi, nhãn khớp lời; phải nghe đoạn thuật ngữ/đoạn ASR lệch | Không dùng tỷ lệ ASR làm chứng nhận phát âm |

**Quy ước đo bắt buộc:** shot là khoảng có một bố cục/cỡ cảnh/điểm nhìn chính; beat là thay đổi có nghĩa trong shot. Đổi nhãn, hồng cầu chạy nền hay từng từ caption không tự tạo shot hoặc hoàn thành beat nhân quả. Median/P90 tính theo số shot bằng nearest-rank cho P90; ghi số shot và các khoảng frame gốc. Nhóm không có shot ghi N/A, không ghi 0 hay đạt giả.

Tỷ lệ chữ dùng mẫu số toàn MP4 kể cả outro/credit. Tử số gồm thẻ câu hỏi/câu chốt, worksheet, source card, bảng phiếu xét nghiệm và cây chữ, kể cả khi phủ trên ảnh; credit tính vào tử số. Không tính nhãn ngắn chỉ cấu trúc và thanh tầng vào tỷ lệ này nhưng vẫn kiểm đọc rõ/che hình. Đạo cụ phiếu không được miễn chỉ vì đặt trên bàn. Thống kê riêng “thẻ chiếm khung” để đối chiếu R5.2, vì baseline cũ đo cả scene còn chuẩn mới đo khoảng xuất hiện.

QA xuất frame đã retime và danh sách khoảng vào `renders/quality-report.json` (đề xuất mới); tự động tính hợp khoảng, median, P90, nguồn asset, caption policy. Critic kiểm thực MP4 tại mọi chuyển tầng, mọi câu chốt và các đoạn 5s lấy đều; kiểm 6 khung phân bố đều ở 720p. Contact sheet không đủ xác nhận diễn hành, nghe hay tính đúng y khoa.

## 4. Các đường hiện hành phải thay hoặc giữ

| Điểm đã đọc trực tiếp | Quyết định cho R5 mới; legacy giữ nguyên |
|---|---|
| `src/healthvideo/domain/visual_budget.py:73`, `:91`, `:96` có profile và tỷ lệ cũ, gồm cơ chế 55–70%, chart/crop 15–25% | Bỏ các hạn ngạch này khỏi chuẩn R5; không đặt hạn ngạch tối thiểu cho source card hay tối đa cho giải thích sâu |
| `src/healthvideo/workflows/draft.py:39`, `:52`, `:142`; `src/healthvideo/workflows/produce.py:840` kiểm budget cả trước cổng và sau WAV | Thay phép kiểm theo profile bằng §3, cùng một bộ hàm; không xóa kiểm trước cổng hoặc bỏ QA cache |
| `video/src/components/AuthoredPanels.tsx:8`, `:18`, `:32`, `:58` biến tab thành hàng/cột và co chữ tới 1px | R5 cấm suy layout từ tab; tab là dữ liệu lỗi trước cổng. Phiếu thật dùng component có cột khai báo; không co chữ để nhét đủ bảng |
| `video/src/scenes/MechanismScene.tsx:125`, `:163`; `video/src/scenes/WhiteboardScene.tsx:70`; `video/src/HealthVideo.tsx:26` định tuyến theo panelRows | R5 định tuyến theo shot/component đã khai báo, không cho bảng ngầm lấn chuỗi zoom; giữ đường cũ cho revision cũ |
| `tests/domain/test_visual_budget.py:74`, `:93`; `video/src/scenes/AuthoredPanels.test.tsx:31`, `:69` bảo vệ tỷ lệ/bảng hiện hành | Giữ thành kiểm legacy; thêm case R5 không cần chart, không tạo worksheet từ tab, vượt trần chữ bị chặn. Không xóa test an toàn đơn vị/nguồn/timing |
| `src/healthvideo/domain/storyboard.py:550` ép ≥4 subject ngang và chặn >4 scene cùng subject | R5 đánh giá tiến triển hành động/tầng; không đổi cơ quan vô cớ để đủ quota. Legacy vẫn kiểm như cũ |
| `src/healthvideo/render/beats.py:47`, `:76` đếm từ caption vào đồng hồ 6s; `src/healthvideo/render/input.py:57` gọi QA; `tests/render/test_beats.py:23`, `:32` kiểm khoảng 6s và bốn subject | R5 chỉ đếm sự kiện thực hiện trên hình; không dùng từ không hiện ở 16:9. Giữ kiểm beat trong cảnh và thứ tự timing; chuyển test ép subject sang legacy, thêm test tiến triển cơ chế R5 |
| `video/src/components/Captions.tsx:8`, `:88`; `video/src/components/StyleCaptions.tsx:62` đã trả null cho ngang; `video/src/scenes/SpokenVisuals.test.tsx:44` đã kiểm ngang/dọc | Yêu cầu “bỏ phụ đề 16:9” đã có ở lớp chung: giữ và kiểm thêm component mới/đường trực tiếp, không mô tả là còn bật toàn xưởng |
| `profiles/voice.yaml:3`–`:9` là Vibi speech-2.8-hd, ID `c081d39a-4922-4c88-9615-78bb240337cd`, speed 1.0 | Giữ đúng voice ID Anh Tu; R5 ghim speed 1.18; không gọi giọng cũ đã xóa hay tự fallback sang giọng khác |
| `src/healthvideo/workflows/product_review.py:70`, `:530`; `src/healthvideo/workflows/script_review.py:26` có trần 4/2; `src/healthvideo/workflows/visual_review.py:32` có trần tái sinh 2 | Chuẩn R5 dùng budget bền vững ở §8, không chỉ giảm hằng số rồi cho reset chu kỳ lách trần |

## 5. Hợp đồng dữ liệu và tương thích — thiết kế đề xuất

Không thêm trạng thái xưởng, không viết lại ledger/script/approval cũ. Đây là phần mở rộng schema có chủ đích so với phạm vi “không đổi schema” năm 08/11 và 14/11, cần triển khai/test trước sử dụng.

- Thêm `quality_profile: r5_v1` **tùy chọn, mặc định không serialize khi vắng** trên storyboard/render-input mới; ghim cùng chuẩn trong `workflow/standards.yaml`. Vắng trường = nguyên hành vi legacy; không đổi default `explain_first_v1` của project cũ (`src/healthvideo/domain/storyboard.py:520`, `src/healthvideo/render/input.py:51`).
- Thêm `r5_contract` tùy chọn trên storyboard: `questions[{id,text,hook_line_id,answer_line_ids}]`, `blocks[{id,line_ids,question_ids,takeaway_line_id,professional_update}]`. ID phải có thật, mọi khối gắn câu hỏi, ít nhất một khối cập nhật. Câu chốt in đậm được thể hiện trong bản duyệt từ ID; không chèn dấu Markdown vào lời TTS.
- Thêm `shots` tùy chọn trên Scene: `{id,kind,tier,component,asset_paths,question_ids,start,end,actions,text_windows}`. `kind` = story/mechanism/recap/credit; `tier` là tầng phóng to hoặc null; `start/end` là anchor từ/cụm thuộc line hoặc ranh đầu/cuối scene; `actions` có actor, compartment, change, outcome; `text_windows` có loại thẻ/bảng/nhãn và anchor riêng. Không cho text kiểu bảng qua tab.
- `component` là ID registry cho phép, không phải mã JS agent gửi vào renderer. `asset_paths` phải trỏ manifest; nhãn/số lấy từ claim, không nhúng giá trị lâm sàng mặc định vào component. Không cho agent tùy ý ghi component path để thực thi code.
- Lưu lựa chọn biên tập ở expert brief/outline như trước; contract chỉ ánh xạ kiểm chứng, không tạo nguồn nội dung thứ hai. Phát hiện lệch lời/ID phải chặn, không tự sửa script để khớp hình.
- Trước cổng dùng timing ước lượng; sau WAV resolve lại anchor thành interval frame không âm, liên tục, không chồng shot, không rơi ngoài scene; text overlay có thể chồng nhưng tử số tính hợp. Thiếu/ambiguous anchor phải báo lỗi, không dùng tỷ lệ phần trăm để đoán câu quan trọng.
- `retime_storyboard` hiện chia scene theo nhóm line (`src/healthvideo/render/timing.py:128`); giữ API đó và resolve shot sau retime/alignment. `build_render_input` hiện truyền scene (`src/healthvideo/render/input.py:120`); mở rộng serializer Python/TS đồng bộ, không lấy `chapter1DeepData.ts` làm dữ liệu sản xuất.
- Cổng y khoa đang hash script/storyboard/manifest/standards/license và asset semantic (`src/healthvideo/workflows/gate_review.py:158`). R5 đưa hình cơ chế, contract, source/licensing snapshot vào đúng revision và hash; hình có nội dung y khoa phải semantic. Không tham chiếu thư viện mutable lúc render.
- Manifest/cache R5 phải bao gồm profile, resolved shot/text intervals, voice ID/speed/lexicon, asset SHA và renderer identity; thay một đầu vào phải invalid cache tương ứng. Giữ byte/hash mặc định legacy; không sửa approval đã cấp. Đổi lời/claim/hình y khoa đã khóa phải đi đường mở lại và bác sĩ duyệt lại.

## 6. Hợp đồng vai, quyền sở hữu và model đề xuất

Đối chiếu đủ 16 vai trong `profiles/company.yaml:25`–`:233`; **không tạo vai thứ 17**, không gộp script_review/visual_review/product_review. Thư viện là trách nhiệm của đạo diễn phân cảnh phối hợp chuyên gia và công cụ xác định, không thêm agent duyệt thay bác sĩ.

Ký hiệu model: **N** = agy `gemini-4-neon-medium`; **S** = codex `gpt-6.1-sol`; **O** = orchestrator-neon khi cần suy luận mạnh. O là tuyến bác sĩ yêu cầu, phải kiểm ID khả dụng trước cấu hình, không tự đoán tên CLI. Không Carbon high, Opus/astra trong cả chuỗi chính và fallback. Chưa có phép đo đối chứng Neon trên toàn bộ vai nên đây là phân công thử nghiệm, không xếp hạng năng lực.

| Vai / vị trí cấu hình hiện tại | Đầu vào → đầu ra; thay đổi hợp đồng | Model và lý do |
|---|---|---|
| researcher (`company.yaml:54`) | Tín hiệu/kênh → dossier có khán giả, tầng chính, 2–4 câu hỏi ứng viên; không làm research y khoa thay expert | N: tác vụ giới hạn, ưu tiên nhanh |
| scout (`:70`) | Đề/dossier/queue → kiểm trùng, tính khả thi; giữ một brief, không viết lại định hướng | N: kiểm hữu hạn |
| medical_expert (`:78`) | Brief/questions → records/claims/ledger/expert brief/explainer; thêm nguồn nền giải phẫu/sinh lý như StatPearls qua Europe PMC, và nguồn cập nhật riêng | N; O chỉ khi nguồn mâu thuẫn/thiếu cơ chế sau một lượt có câu hỏi cụ thể; không dùng model để bù thiếu nguồn |
| writer (`:91`) | Ledger/brief → script/outline/questions: mạch §2, câu chốt, cập nhật, hỏi–đáp; thiếu claim trả expert | S: giữ chuyên trách lời Việt; không giao SVG/FLUX hay bảng để vượt validator |
| script_critic (`:136`) | Toàn script/ledger/brief → báo cáo sáu tiêu chí hiện có, kiểm từng mệnh đề và hợp đồng §2; không tự cấp phê duyệt y khoa | N khác writer; O khi tranh chấp chuyên môn cụ thể. Bác sĩ giữ cổng PIN |
| storyboard_director (`:107`) | Script đã viết/explainer/library → storyboard + manifest + contract/shot plan, chọn tầng và hình có phép, câu chốt/mascot; nhận cut range từ shorts | N: nhìn hình/Remotion; O một lần nếu không giải được không gian. Không đổi script |
| Trách nhiệm medanim (thuộc storyboard_director) | Brief cơ chế và hình allowlist → assets.yaml + asset SHA/provenance + rig/action, giới hạn giản lược; expert kiểm cấu trúc | N làm hình, công cụ Python kiểm quyền/hash; không tự mở nguồn tải khác |
| voice_director (`:123`) | Script/profile/lexicon → voice-prep gắn hash, cách đọc tên/số; speed 1.18, thuật ngữ khó có mốc nghe kiểm | N: chuẩn hóa hữu hạn; không thay nghĩa lời |
| art_director (`:149`) | Asset/contact sheet và chuyển tầng mẫu → visual-review chọn/reject, chỉ lỗi pixel/giải phẫu/quyền/đọc rõ; không chấm âm thanh bằng ảnh | S: độc lập người làm hình N; cần kiểm khả năng đọc pixel thực trước áp dụng, không nhận đã xem nếu không có ảnh |
| editor (`:161`) | Issue có path/dải dòng, timing đã khóa → sửa component chung được giao và test; Python dựng lại; không đổi script/claim/shot plan khóa | N: TS/Remotion; lỗi Python có bất biến giao repair_engineer S theo brief riêng |
| product_critic (`:177`) | MP4 thật, chất lượng, bài đăng, nguồn → product review có timestamp và issue ID; kiểm trả câu hỏi, nhịp hai nhóm, chữ, lời–hình, tiếng đọc | S khác editor N; failover phải vẫn độc lập, không được dùng maker session |
| shorts_producer (`:199`) | Script/claim + ứng viên cảnh → một chủ sở hữu cut range/hook/payoff/caveat 9:16, chuyển range cho storyboard trước khóa; lời mới phải duyệt y khoa | N: thiết kế điểm chạm TOFU; không chỉ crop video ngang |
| copywriter (`:190`) | Nội dung đã duyệt + clip range → title/thumbnail/posts/caption xuất bản; giữ hook/đáp án trong chính clip, không tạo kịch bản clip cạnh tranh | N: đóng gói giới hạn; nguồn đầy đủ ở mô tả |
| coordinator (`:26`) | Chat/state → định tuyến và brief đủ phạm vi, nguồn/ID lỗi; không tự bật lại xưởng hay duyệt | N: phản hồi nhanh |
| coordinator_senior (`:40`) | Log + issue + chẩn đoán trước → một nguyên nhân có bằng chứng, brief sửa/acceptance; lỗi nội dung trả đúng vai | S: Python/bất biến; O cho phân tích khó hữu hạn, không mở vòng chẩn đoán vô tận |
| feedback_analyst (`:214`) | Phản hồi chưa phân loại → task có done_when; coordinator đã định tuyến thì dùng lại, không phân tích trùng | N: phân loại |
| repair_engineer (`:221`) | Brief kỹ thuật có allowlist file → bản sửa/test/log nghiệm thu; không sửa claim/approval để làm xanh | S: cổng/hash/timing/retry/storage |

**Gỡ hợp đồng mâu thuẫn cùng đợt:** bỏ chỉ dẫn giữ chart 16–24% và buộc dùng source_card để diễn giải ledger (`.agents/skills/pyh-storyboard-director/SKILL.md:25`, `:28`); giữ nguyên metadata nguồn trong gói duyệt, không buộc hiện nguyên thẻ trong phim. Không để writer tạo khung hình tối thiểu chỉ để qua validator (`.agents/skills/pyh-writer/SKILL.md:60`).

Đồng bộ skill/prompt editor về quyền sửa hẹp, thay “chỉ SVG trong anatomy” bằng đúng component R5 được giao (`.agents/skills/pyh-editor/SKILL.md:8`, `:42`); không cho quyền sửa storyboard/voice khóa từ prompt rộng hơn. Hợp nhất quyền sở hữu hook/range vào shorts_producer, copywriter chỉ viết caption xuất bản (hai hợp đồng hiện ở `.agents/skills/pyh-shorts-producer/SKILL.md:18`, `.agents/skills/pyh-copywriter/SKILL.md:25`). Không gộp agent chấm. Loại yêu cầu mascot ở mọi đầu chương nếu nó chen vào giải phẫu cận (`.agents/skills/pyh-storyboard-director/SKILL.md:32`); chuẩn R5 gắn mascot vào câu chốt. Phụ đề dọc giữ policy riêng, không dùng luật “phụ đề tĩnh” của art-director để xóa highlight dọc đang được phép (`.agents/skills/pyh-art-director/SKILL.md:35`, `.agents/skills/pyh-shorts-producer/SKILL.md:17`).

## 7. Thư viện và đưa bản thử vào xưởng

### 7.1 Hình có giấy phép

Cấu trúc đề xuất: `library/medanim/<chủ-đề>/assets.yaml`, `assets/<file>`, `animation.yaml` (cơ chế/nguồn/giới hạn), `previews/`, lịch sử duyệt bất biến. assets.yaml là catalog hình; animation.yaml tham chiếu tập asset dùng, không chép hai bản metadata độc lập. Loader phải kiểm chúng nhất quán. Thư viện hiện kiểm SHA từ assets/public ở `src/healthvideo/workflows/medanim_library.py:70`; asset model hiện có source_page/original_url/author/license/SHA (`src/healthvideo/domain/medanim_library.py:246`).

1. Expert xác định cấu trúc cần thấy; đạo diễn tìm trong thư viện trước. Chỉ tải từ Servier Medical Art, NIAID BioArt, DBCLS, Reactome đã được cho phép; kiểm license từng file. Không tự mở rộng sang Bioicons hay atlas khác cho lượt tải mới. Asset cũ không bị đổi giấy phép hồi tố.
2. Lưu trang nguồn, URL gốc, tác giả, license + URL license/bằng chứng PD, ngày lấy, SHA-256, vai trò/cấu trúc nhìn thấy, thay đổi/crop đã làm. Ví dụ provenance thực ở `P/library/medanim/liver-anatomy/assets.yaml:6`, `:14`. Thiếu quyền hoặc URL redirect ra ngoài allowlist thì giữ thiếu asset và báo, không tự tải nguồn khác.
3. Downloader chỉ HTTPS, kiểm hostname chính xác ở mọi redirect, loại URL nội bộ/private, chặn traversal/symlink và file quá lớn (ĐX 5 MB/file); không đọc key/cookie. Cấm tải rồi gắn nhãn “mở” theo tên kho. Chính sách license nội bộ hiện chỉ nhận PD/CC0/BY3/BY4 và chặn SA/NC/ND (`src/healthvideo/domain/medanim_library.py:30`, `:51`); giữ nguyên.
4. Dùng ảnh thật có phép cho cơ thể/cơ quan; vector để highlight, mask/cắt lớp có căn cứ, đường máu, hạt, màng và biến đổi sinh học. Không tự vẽ cơ quan thay ảnh có sẵn. Thiếu lớp giải phẫu: ghi giới hạn, hỏi chuyên gia/bác sĩ; không để vector giả thành ảnh mô thật.
5. Chép đúng asset dùng vào revision, ghi license-ledger và hash; chuẩn hình có phép không thay cổng y khoa. Nếu thư viện đã có duyệt theo hash thì giữ luồng đó, không tái dùng approval cho rig/asset đã đổi.
6. Credit cuối phim sinh từ tập asset thực dùng: tác giả/kho, tên hình, license, ghi thay đổi; URL đầy đủ và mapping từng hình ở mô tả/gói duyệt. Credit chia trang đủ đọc, ĐX 6–10s tổng, vẫn tính vào 15%. Không bê nguyên credit chứa cả asset chỉ tải mà chưa dùng từ bản thử (REPORT `:116`).

### 7.2 Thành phần lấy, sửa và bỏ

| Code bản thử đã đọc | Đưa vào dùng chung | Điều bắt buộc thay |
|---|---|---|
| `P/video/src/proto/Chapter1ZoomChain.tsx:24`, `:240`, `:430`, `:656`, `:930` | Chuỗi zoom có anchor cơ thể→cơ quan→mô→tế bào; asset giải phẫu giữ nguyên provenance | Tách nội dung gan khỏi điều khiển camera; geometry theo tầng, không crossfade hai tỷ lệ rồi gọi là zoom |
| `P/video/src/proto/Chapter1Shared.tsx:434` | ScaleBreadcrumb → ScaleChain dùng danh sách tầng đầu vào | Bỏ mảng tầng gan hardcode; layout dọc rút gọn vẫn biết đang ở đâu |
| `P/video/src/proto/Chapter1Shared.tsx:134`, `:34` | TakeawayCard và MascotCorner | Nhận anchor/pose đã ghim; thẻ tính vào ngân sách chữ; không tạo thêm nhân vật |
| `P/video/src/proto/LiverLeakSignature.tsx:38`, `:289`; `P/video/src/proto/Chapter1Deep.tsx:35` | Rig men vào máu với customClock/customLabels | Chuyển clock sang dữ liệu resolved; kiểm nghĩa của tổn thương màng, không dùng cho mọi bệnh; không dựng cơ quan mới bằng tay |
| `P/video/src/proto/Chapter1Shared.tsx:206` | VnLabSheet → phiếu VN có tên/kết quả/khoảng tham chiếu/đơn vị/H | Bỏ ALT/AST hardcode; số chỉ từ claim/ca được phép, không bịa người bệnh |
| `P/video/src/proto/Chapter1Clinical.tsx:614`, `:628` | ReferenceDistribution: đường cong minh họa, vùng/marker/nhóm người nhận từ dữ liệu | Không mặc định mọi xét nghiệm phân bố chuẩn; ghi “minh họa”, không lấy tọa độ Gaussian làm dữ liệu nghiên cứu |
| `P/video/src/proto/Chapter1Clinical.tsx:1242` | CreditCard sinh từ used assets | Không giữ danh sách nguồn/tác giả hardcode; không dồn chữ nhỏ như bản mẫu |
| `P/video/src/proto/chapter1DeepData.ts:1`; `P/tools/proto/build_v5_data.py:25`, `:88` | Học cách neo lời và build frame data | Không chép file sinh có 15 dòng cố định, fallback first-token/phần trăm hoặc timing thủ công sang xưởng |
| `P/tools/proto/render_v6.cjs:7`, `:32`, `:100`; `P/tools/proto/qa_v6.py:14`, `:131` | Học bundle, ghi metrics, kiểm giải mã/contact sheet | Dùng render/QA xưởng, bỏ đường dẫn checkout/cache và copy asset ngầm; không gọi script proto trong production |
| `P/video/src/proto/StorySceneV4.tsx:4`, `:11`; `P/video/src/proto/StorySceneR2.tsx:50`, `:69` và cảnh FLUX cũ | Không nhập các scene kể chuyện cũ vào runtime R5 | Không tạo dependency storyV4Data, nền FLUX nhà thuốc/xưởng. Bối cảnh mới dùng tài sản thực có phép và đồ vật/vector đúng VN; giữ lịch sử prototype |

Không chép cả Chapter1Deep thành template mọi video. Dùng registry chung qua HealthVideo; Python vẫn sở hữu TTS, timing, render, cache và cổng. `P/tools/proto/voice_v5.py:17`, `:55` tái dùng cache dòng và speed 1.18, nhưng hardcode checkout tại `:20`; chỉ lấy nguyên tắc, không mang script gọi API thử vào workflow.

## 8. Ngăn vòng chấm–sửa lặp

ĐX cho mỗi revision R5: script ≤2 lần chấm (đầu + một lần sửa), hình ≤3 lần chấm (đầu + hai lần sửa), sản phẩm ≤3 lần chấm (đầu + hai lần sửa). Cùng issue còn mở hai lần liên tiếp thì dừng sớm, gom thành một brief. Chỉ review diff/ảnh hưởng quanh chỗ đổi sau vòng đầu; phát hiện an toàn mới vẫn phải báo.

Budget lưu bền vững theo revision + stage, issue_id và fingerprint nguyên nhân; rerender/hash thay đổi, restart, reset submitted hay failover **không** làm mới quota chất lượng. Quota/tool transient dùng budget kỹ thuật riêng nhưng không được tạo review mới vô hạn. ĐX tối đa hai chẩn đoán kỹ thuật cùng fingerprint, mỗi chẩn đoán một lần sửa và một lần xác minh; hết thì báo chủ sở hữu và bằng chứng.

Chỉ thay đổi nội dung/phạm vi mới do bác sĩ yêu cầu rõ, đi luồng revision hiện hành, mới có budget revision mới; không tự tạo revision để xóa đếm. Không tự báo đạt khi hết vòng. Lỗi nguồn/giải phẫu/an toàn phải xử lý trước cổng; thẻ hỏi quyết định không phải approval và không cho bỏ cổng. R5.2 ghi 24 vòng sản phẩm hỏng và 60 lần repair_diagnose (`factory-gap-audit.md:11`, `:148`): mục đích là chặn tích lũy tương tự, không tuyên bố đã sửa runtime hiện nay.

## 9. Thời gian, ký tự và chi phí

Số đo đã lưu: v5/v6 cùng 9.331 frame, 311,033s video; render 978,736/968,573s (`P/cache/r5-proto/render-v5-metrics.json`, `render-v6-metrics.json`; REPORT `:81`, `:83`, `:126`). Vibi v5 gửi 5.812 ký tự, WAV 307,005s, không gọi lại (REPORT `:82`); khác số 5.659 ký tự bản lời dự tính (`script-v3-deep.md:53`). Như vậy mốc “5 phút mất 15–16 phút” trong brief là xấp xỉ; log bản cuối gần 16,1 phút cho 5:11 video, tỷ số render/video khoảng 3,11–3,15.

| Lời/video đích | Ký tự Vibi ngoại suy từ 5.812/307,005s lời | Render ngoại suy từ 968,573–978,736/311,033s video |
|---|---:|---:|
| 10 phút | ~11.400 | ~31–32 phút |
| 15 phút | ~17.000 | ~47–48 phút |
| 25 phút | ~28.400 | ~78–79 phút |

Hai cột có mẫu số khác nhau; là dự toán tuyến tính cùng độ phức tạp, không gồm tìm nguồn, soạn bài, align/Whisper, clip dọc, QA/sửa hay chờ bác sĩ. ĐX dự phòng ký tự 20% cho lần đọc lại có chỉ định: ~13.700–34.100 ký tự/10–25 phút; báo thực dùng riêng. Không suy tiền từ credit hay bảng token cũ; chưa có đơn giá/hóa đơn thực đọc trong phiên này. Không tuyên bố tiết kiệm tiền/Neon nhanh hơn bao nhiêu.

Giảm thời gian theo thứ tự: dùng cache WAV theo voice/speed/text/lexicon; dùng cache chương theo input+renderer+asset hash; một bundle tái dùng; chỉ render chương đổi; preview ngắn/720p để kiểm vị trí trước bản đủ; giảm blur/filter/SVG dư; đo concurrency 2/4/6 trên cùng clip khi được phép, không mặc định tăng là nhanh. Xưởng đã có active bundle và cache chương (`src/healthvideo/workflows/produce.py:910`, `:930`); bản thử dùng concurrency 4 (`P/tools/proto/render_v6.cjs:106`). Giữ bản cuối 1080p30 và QA đầu ra; tối ưu không được cắt bước duyệt/nguồn.

## 10. Rủi ro và năm quyết định còn cần bác sĩ chốt

- Nguồn nền chỉ có abstract không đủ xác nhận mọi chi tiết sâu; expert phải thu hẹp câu hoặc xin nguồn bổ sung. Không coi bản lời được thích là mọi số/khẳng định đã được duyệt cho video mới.
- Hình có phép vẫn có thể bị định vị sai; v6 từng bỏ nhãn thận vì asset không vẽ thận (REPORT `:130`); kiểm đối chiếu cấu trúc thực hiện trên pixel, không theo tên file.
- V6 còn giới hạn lớp LSEC theo REPORT `:145`; asset thiếu không được lấp bằng hình tự chế chưa kiểm. Thư viện ban đầu ưu tiên một chuỗi gan rồi cơ chế phù hợp chủ đề, không dựng đồng loạt 26 rig.
- Độ sâu và nhịp cắt dễ xung đột; trường hợp ngoại lệ phải có timestamp/lý do/tiến triển nhìn thấy, không lấy median làm lý do lược bỏ thông tin an toàn. Chưa có dữ liệu chứng minh retention hay năng lực bác sĩ trẻ sau xem.

| Quyết định | Phương án đề xuất trước; lựa chọn khác | Hệ quả |
|---|---|---|
| D1. Trần chữ | **≤15%, mỗi thẻ/bảng ≤6s**; hoặc ≤20%, cùng giới hạn từng lần | 15% chống slide mạnh hơn; cả hai tính cả phiếu và credit |
| D2. Nhịp hai nhóm | **Kể 2,5–3,5s; cơ chế 8–20s, beat 3–6s, ngoại lệ có lý do**; hoặc chỉ dùng nhịp làm cảnh báo | Chọn bộ ngưỡng cứng thử nghiệm hay advisory; không đổi yêu cầu cơ chế liền mạch |
| D3. Cập nhật khi thiếu nguồn mới phù hợp | **Chỉ rõ nguồn mới nhất tìm được/ngày tìm, nói chưa có cập nhật đủ chắc**; hoặc hoãn chủ đề tới khi bổ sung được nguồn | Không bịa “nghiên cứu mới”, không gọi hướng dẫn cũ là phát hiện mới |
| D4. Hết budget review | **Dừng và trình brief cho bác sĩ chọn hướng, không tự reset**; hoặc bác sĩ cho một đợt bổ sung hữu hạn có phạm vi/đếm riêng | Cả hai không cho lỗi y khoa vượt cổng, không coi hỏi ý kiến là xin PIN |
| D5. Pilot nghiệm thu sau triển khai | **Một chủ đề thật 10–15 phút, ưu tiên chuỗi gan tái dùng**; hoặc một chủ đề mới 15–25 phút | Chỉ làm sau khi bác sĩ cho phép bật lại xưởng, đủ hai cổng; không tự đăng |

Kế hoạch đi kèm: `docs/superpowers/plans/2026-11-24-r5-quality-standards.md`. Chốt spec không đồng nghĩa cho phép chạy pilot; năm lựa chọn này không mở lại các quyết định đã chốt ở §2.
