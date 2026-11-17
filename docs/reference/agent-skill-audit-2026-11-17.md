# R3.2 — Kiểm toán skill, bàn giao và chi phí agent

Ngày kiểm: 17/11/2026. Chỉ đọc hệ thống và tạo báo cáo; mọi thay đổi dưới đây là **đề xuất**, chưa triển khai.

## Phạm vi và cách đọc số liệu

| Mục | Bằng chứng / giới hạn |
|---|---|
| Hợp đồng hiện hành | `profiles/company.yaml`, 29 file `.agents/skills/*/SKILL.md`, 16 file `src/healthvideo/prompts/*.md`, `workflows/runner.py` và các validator/bộ tiêu thụ liên quan. `prompts/` ở gốc không tồn tại. |
| Quy định | Đã đọc `docs/handoff-codex.md`, mục 1 `CLAUDE.md`, spec công ty 08/11. `RTK.md` không tồn tại trong worktree. Không đọc/in `.env`. |
| So sánh checkout | HEAD hai checkout đều `5711eeb`; nội dung văn bản company, runner, script_review, các SKILL và prompt đã đối chiếu giống nhau (khác newline ở một số file). Không suy ra đó là phiên bản đã chạy trong mọi log cũ. |
| Dữ liệu thật | Checkout chính `E:/Protect Your Health`: 4 thư mục project hiện hữu; `topics/logs/activity.jsonl` có 456 sự kiện, lịch sử từ 08/11 đến 16/11; `xuong.log` có thông báo đến 17/11. Review chỉ lấy `revisions/001/reviews/`, loại thư mục staging `.001.*` để tránh đếm bản sao. |
| Thời gian | Ghép start/end cùng slug, role, step, CLI, model, job_id; với bản ghi cũ thiếu job_id dùng FIFO trong cùng nhóm. Tổng thời gian agent gồm cả lượt lỗi, không gồm start thiếu end. Độ chính xác timestamp: giây. `ok=true` chỉ là agent trả thành công, không chứng minh sản phẩm qua validator/critic. |
| Token | Chỉ nhận footer cuối file khớp `tokens used\n<số>` và kết thúc file; bỏ các số bị trích lại giữa log. Ghép tên file UTC với start cách dưới 2 giây, cùng slug/CLI; nhánh `parallel-*` thêm điều kiện step. Không cộng log repair chứa bản sao log khác vào tổng production. Đây là tổng CLI tự báo từng lượt, **không phải hóa đơn**, chưa tách input/output/cache/reasoning. |
| Skill được dùng | Cấu hình gán skill ≠ đã đọc ≠ làm đúng. Khối `role_skill_block()` chỉ đưa đường dẫn và yêu cầu đọc; chưa có biên nhận/hash chứng minh agent đã nạp. Dấu lệnh đọc trong log là bằng chứng mạnh hơn cấu hình nhưng vẫn không chứng minh áp dụng đúng. |

**Kết luận chính:** nút thắt là vòng sửa và hợp đồng bàn giao. Men gan có 20 báo cáo Trạm 07, một bản cũ từng đạt; bản hiện hành chưa đạt. Bước phiên âm nhẹ nhưng có 3.291.195 token CLI quan sát được. Chưa có mẫu hoàn tất A–Z trong 4 project để tính thời gian một video đạt hai cổng.

## 1. Sơ đồ công ty và điều kiện qua trạm

Luồng thực trong runner: tạo project → research → draft → kiểm câu hỏi cho expert → storyboard/voice (có thể song song) → Trạm 07 ↔ draft → nộp y khoa → **bác sĩ duyệt** → posts/shorts/produce (có thể song song; visual_review khi có ứng viên) → Trạm 12 ↔ editor/dựng lại → nộp video → **bác sĩ duyệt** → đóng gói. Nhánh chat, nghiên cứu kênh, phản hồi và sửa lỗi chạy ngoài chuỗi chính. Trong vòng rewrite, runner hoãn storyboard/voice đến lúc cần nộp để giảm làm lại.

Model trong bảng là **mục đầu tiên** của chuỗi hiện hành, không khẳng định model đó đã làm tất cả log. `OR` = OmniRoute. Fallback đầy đủ theo `company.yaml`; cấu hình hiện nay khác mô tả Carbon trong `CLAUDE.md` và spec 08/11.

| Vai — model đầu | Nhận gì, từ ai | Trả gì, cho ai | Điều kiện qua / trách nhiệm |
|---|---|---|---|
| coordinator — OR Luna | Chat bác sĩ + company_summary | CoordinatorReply/assignments → Python dispatch | Đúng schema, action và phạm vi; publish chỉ chuẩn bị preview, kiểm cả hai cổng và xác nhận trong app. |
| coordinator_senior — OR Sol | Escalation từ coordinator; phiếu lỗi từ repair service | Báo cáo chat hoặc Diagnosis/Acceptance → Python/engineer | Đúng schema được giao; nghiệm thu sửa kỹ thuật và lượt retry thực, không nhận gỡ khóa là thành công. |
| researcher — OR Hydrogen medium | Query/Sheet/metrics từ Leader | Dossier/rubric → Inbox; insights → writer/copywriter/shorts | Chấm rubric code, nguồn thật; analytics chỉ khi analysis_ready; không tự enqueue. |
| scout — OR Luna (bulk) | Brief chọn đề/kiểm trùng | Đề xuất → người chọn/queue khi được giao | Có trong roster nhưng chưa tìm thấy đường gọi role scout trong Python; discover thực đi researcher. |
| medical_expert — OR Terra | Queue/câu hỏi writer | Records, claims, ledger, explainer, expert brief/answers → writer | evidence_ready + brief; hoặc trả hết câu hỏi khi draft_ready. Không viết script/duyệt cổng. |
| writer — OR Sol | Brief/ledger, ghi chú bác sĩ, issues critic | Script + outline + storyboard/assets/clip-plan ban đầu → director/critic | step draft đạt, draft_ready; thiếu bằng chứng hỏi expert, không tự bổ sung claim. |
| storyboard_director — OR Sol | Script/outline/explainer từ writer/expert | Storyboard, manifest, clip-plan, SVG → validator/production | step storyboard exit 0, khớp script; không đổi lời. |
| voice_director — OR Hydrogen medium | Script + từ điển chung | voice-prep.yaml → TTS/Python | Đúng schema và script_hash; không sửa script hoặc tự nhận đã nghe TTS. |
| script_critic — OR Terra | Toàn script/brief/ledger/outline + issues cũ | script-review.yaml → Python/writer | Sáu điểm đều ≥7, ≤5 decisions; report đúng hash. 2 lượt/chu kỳ, tối đa 3 chu kỳ hiện hành; hết thì chặn chờ hướng dẫn, không vượt y khoa. |
| art_director — OR Hydrogen medium | Candidate index, ảnh và contact sheet từ Python | visual-review.yaml → Python chọn/sinh lại | Đủ cảnh, hash index đúng, khai ảnh đã mở; tối đa hai vòng sinh lại theo hợp đồng, fallback chỉ khi có mapping. |
| editor — OR Sol | Góp ý video/Trạm 12 | SVG + test, hoặc posts khi revise_product → Python dựng lại | Chỉ sửa file được phép; không đổi tài liệu khóa. Lỗi cần đổi storyboard/lời phải qua luồng mở lại cổng. |
| product_critic — OR Terra | Bản dựng, contact sheet, timing, QA, posts | product-review.yaml → Python/editor | Sáu điểm ≥7, ≤5 decisions và đúng render hash; tối đa 3 review trong chu kỳ. Lỗi không fixable phải chuyển xử lý, không đưa bản trượt lên cổng. |
| copywriter — OR Luna (bulk) | Script/outline/clip-plan đã duyệt + ledger | posts.yaml → validator/product critic | posts-check exit 0, tiêu đề/thumbnail trả đúng lời hứa; không publish. |
| shorts_producer — OR Hydrogen medium | Nội dung đã duyệt + clip-plan + insights | posts/shorts-plan.yaml → readiness/dashboard | 1–4 clip, target 45–90s, cảnh tồn tại, claim ref hợp lệ, safe_zone_checked=true; chưa chứng minh renderer thực hiện kế hoạch. |
| feedback_analyst — OR Luna (bulk) | Ý kiến bác sĩ từ inbox/Leader | summary/tasks → dev lead/luồng sửa | kind/target/request/done_when kiểm được; chỉ phân tích, không sửa code/profiles. |
| repair_engineer — OR Sol | Diagnosis có file/test từ Leader | Báo cáo sửa + kết quả test → Leader/Python | Đúng phạm vi, test/lint và Acceptance; giữ cổng/claim, retry thực đạt mới coi phục hồi. |
| Python + bác sĩ | Artifact từng vai | State, render, hash, approval, package → trạm sau | Python thực thi/kiểm bất biến; bác sĩ là người quyết hai cổng. Không gán nhiệm vụ này cho LLM. |

### Khoảng hở, trùng việc và vòng chưa hội tụ

| Mức | Bằng chứng | Hệ quả và đề xuất |
|---|---|---|
| P0 | `draft.md` mục 1/3/6 yêu cầu writer thiết kế storyboard/assets/SVG; director lại thiết kế cùng bộ file. | Hai chủ sở hữu hình, làm lại sau sửa lời. Chỉ định director chịu trách nhiệm thiết kế hình; writer chỉ giữ đồng bộ tối thiểu mà step draft hiện buộc có. Đổi phần bắt buộc cần sửa hợp đồng code/test, không chỉ xóa câu trong skill. |
| P0 | `shorts_plan.py` lưu kế hoạch 45–90s; `produce.py`/render dùng `script/clip-plan.yaml`; tìm toàn `src/healthvideo` chưa thấy renderer đọc `posts/shorts-plan.yaml`. Clip-plan cũ 1–6 clip, 60–180s. | Có người lập kế hoạch nhưng thiếu người chuyển thành output. Quyết một hợp đồng clip và một bước ánh xạ có kiểm duration/caveat, thực thi hook/loop/safe-zone rồi QA file xuất. Hiện safe_zone_checked chỉ là boolean tự khai. |
| P0 | Product critic chấm âm thanh từ QA/từ điển; skill nói rõ không nghe. Editor không được sửa từ điển/voice-prep/asset khóa. | Chưa có agent chịu trách nhiệm nghe đối chiếu và sửa phát âm trọn vòng. Giao QA âm thanh về voice director với quyền đề xuất; thay dữ liệu khóa qua mở lại/duyệt lại hiện hành. Bác sĩ vẫn quyết điểm chưa xác minh. |
| P1 | scout được cấu hình nhưng discover gọi researcher; cả hai có content-strategy. | Vai trùng ở ý tưởng, scout chưa có đường thực thi đã xác minh. Chọn researcher sở hữu discover/chấm; scout chỉ kiểm đầu vào nếu thực sự nối workflow, nếu không bỏ khỏi roster vận hành. |
| P1 | visual_review chủ yếu xét candidate; motion-design chỉ gán editor lúc sửa; visual-style không có file phong cách PYH riêng. | Thiếu người nghiệm thu style toàn chuỗi trước khóa y khoa. Giao director giữ style, art director kiểm cả cảnh SVG/FLUX theo cùng mẫu; editor chỉ thi hành sửa. |

**Ca Trạm 07 men gan (ví dụ người dùng gọi PYH-003):** log hiện hữu dùng slug, chưa tìm được định danh PYH-003 để xác nhận ánh xạ; số dưới đây gắn đúng slug men gan, không mặc định mã đó.

| Chỉ dấu | Quan sát |
|---|---|
| Lịch sử | 20 report, vòng 2 từng đạt; 18 vòng tiếp theo đều trượt. `submitted: 14`, `cycles: 3`, `cycle_start: 18`: chu kỳ hiện tại sau mốc submitted có 6 review, không phải 20 vòng trong cùng một budget. |
| Xu hướng 6 vòng cuối (15→20) | Nhịp câu: 6→6→6→5→6→7; không lặp ý: 6→6→7→7→7→7; đúng yêu cầu: 7→7→8→5→6→6. Sửa nhịp tiến bộ nhưng mức khẳng định vẫn kẹt. |
| Lỗi cuối | N31 hứa chắc các bước khám cho mọi người thay vì tùy bệnh cảnh; critic yêu cầu diễn đạt có điều kiện theo brief. Report 17/19/20 có dấu `?` thay ký tự tiếng Việt: dữ liệu đã mất ký tự, không chỉ lỗi hiển thị terminal. |
| Chặn thật | `xuong.log` 16/11 23:19 và 17/11 21:55 ghi hết 3 chu kỳ/6 vòng, tiêu chí đúng yêu cầu 6. Cơ chế hiện tại có trần; chưa chứng minh vòng vô hạn. Lịch sử dài gồm các lần nộp/reset và phiên bản code cũ. |
| Gốc khả dĩ | Ràng buộc thời lượng/explain-first dễ sinh lặp; feedback sửa nhịp có thể làm mạnh câu; lỗi chuyển dòng khó theo dõi bằng (line, criterion). Đây là giả thuyết từ hợp đồng/lịch sử, chưa phải thí nghiệm nhân quả. |
| Sửa nên làm | Sau hai vòng không cải thiện, Leader phân loại lỗi biên tập/y khoa/hợp đồng và giao đúng vai; giữ trần, không hạ điểm. Lưu claim/issue identity, đối chiếu before/after; bác sĩ hướng dẫn qua chat khi đã chạm trần. Giữ lỗi đang mở, chỉ đóng có chứng cứ. |

## 2. Kiểm toán từng skill và dòng sửa đề xuất

`Đọc` = có dấu lệnh đọc đường dẫn SKILL trong log mẫu; `Gán/chạy` = role có start, chưa chứng minh đã đọc skill; `Gán/chưa thấy` = có cấu hình, chưa có lượt role tương ứng trong activity; `Ngoài roster` = không gán vào 16 vai. Độ dài là số dòng thực đo, không quy đổi thành token. “Dài” đánh giá theo phạm vi công việc, không theo một trần token đã đo.

Mọi dòng trong cột cuối là sửa dự kiến, **không áp dụng trong đợt audit**. Vị trí dùng tên mục/câu hiện hữu để tránh lệ thuộc số dòng khi file đổi.

| Skill — dòng | Dùng thực / độ dài | Mâu thuẫn, thừa/thiếu | Dòng sửa cụ thể đề xuất |
|---|---|---|---|
| pyh — 40 | Ngoài roster; có tham chiếu trong log | Hướng dẫn vận hành cho người dùng dễ bị worker nạp thêm; chứa cả set-pin/xuong. | Sau tiêu đề thêm: “Agent chạy một bước chỉ đọc prompt bước và skill vai; phần vận hành dưới đây dành cho phiên điều hành.” |
| pyh-coordinator — 39 | Gán/chạy | Schema tóm tắt thiếu platform/privacy/clip/job so với prompt; skill nói đăng nhưng chưa nhấn preview rõ như prompt. | Đầu ra đổi thành “Theo CoordinatorReply hiện hành và prompt; publish_video chỉ tạo preview chờ xác nhận trong app.” |
| pyh-coordinator-senior — 45 | Gán/chạy | Nói luôn cùng schema coordinator, trong repair service lại nhận Diagnosis/Acceptance. | Đầu ra thay bằng “chat_deep dùng CoordinatorReply; repair_diagnose/repair_accept dùng đúng schema JSON được truyền, không pha trường chat.” |
| pyh-researcher — 40 | Gán/chưa thấy | Đang chấm nhóm 40/25/20/15 theo nhãn khác code; code yêu cầu viral_engagement/urgency_prevention/evidence_readiness/short_feasibility. | Thay bốn dòng rubric bằng tên, nghĩa và miền điểm đúng prompt/code; không ghi “customer impact” của skill ngoài. |
| pyh-scout — 45 | Gán/chưa thấy | Chưa có caller; trùng researcher. | Nhiệm vụ ghi “Chỉ kiểm đề đã có: trùng, audience, câu hỏi; discover/chấm điểm do researcher.” Chỉ giữ nếu nối được caller. |
| pyh-medical-expert — 52 | Đọc | Gọn, chuyên biệt; thiếu biên nhận phạm vi đọc cho claim chính. | Đầu ra thêm “Với mỗi claim quyết định lời khuyên, ghi mức đã đọc và phần chưa xác minh trong brief; không tự gán GRADE.” |
| pyh-writer — 76 | Đọc | Tốt ở giới hạn claim; lặp prompt và còn sở hữu cả hình; văn “câu kết chuẩn cũ” dễ lệch feedback mới. | Đầu ra đổi “writer sở hữu script/outline; storyboard/assets tối thiểu theo validator, director hoàn thiện”; câu kết đổi thành “mục slug: chung hiện hành, không mặc định bản cũ”. |
| pyh-storyboard-director — 36 | Đọc; ít dòng nhưng 6.278 byte | Thiếu file style chung; phần mascot dài, hai cách rights_required khác nhau theo helper. | Thêm “Nạp style PYH đã pin; đánh giá 3 cảnh đại diện cả hai tỷ lệ”; chuyển hai hướng dẫn mascot sang reference, chọn một đường đăng ký chính đã test. |
| pyh-voice-director — 24 | Đọc; tải công việc thực lớn | Scope quét hẹp nhưng bị chạy nhiều và ngữ cảnh lớn; số/đơn vị có rủi ro y khoa. | Đầu vào thêm “Chỉ nhận dòng thay đổi + hash + từ điển; giữ cache theo nội dung phát âm; số/đơn vị không rõ thì chuyển chuyên gia, không đoán.” |
| pyh-script-critic — 52 | Đọc | Thiếu nhắc resolved_issues trong skill dù prompt/code có; quy tắc vòng sửa nằm nhiều nơi. | Đầu ra thêm “Đối chiếu từng issue cũ, ghi resolved_issues chỉ khi sửa thật; lỗi lặp chỉ rõ cặp dòng và ý giữ.” Không đổi sáu tiêu chí/ngưỡng. |
| pyh-art-director — 48 | Gán/chạy | Có giới hạn xem ảnh trung thực; không sở hữu style cả video, fallback hẹp gout/urat. | Phán đoán thêm “Đối chiếu style đã pin, cả SVG và FLUX ở 16:9/9:16 khi có mẫu; thiếu mẫu ghi chưa kiểm.” Không hứa fallback ngoài mapping. |
| pyh-editor — 46 | Đọc | Khá rõ quyền; “để bác sĩ quyết” chưa chỉ rõ đường bàn giao khi Trạm 12 đang chặn. | Lỗi ngoài quyền thêm “Trả file/cảnh và vai cần nhận cho Leader; giữ blocked, không lặp dựng bản không đổi.” |
| pyh-product-critic — 48 | Gán/chạy; đường dẫn có trong log | Không nghe âm thanh nhưng có điểm âm thanh; không có bằng chứng safe-zone từ clip đã xuất. | Đầu ra thêm “Tách quan sát/QA/nhận định chưa nghe trong summary; kiểm contact sheet clip xuất thực, không nhận boolean là bằng chứng.” |
| pyh-copywriter — 49 | Gán/chạy | Đã chặn publish và claim mới tốt; posts còn phụ thuộc clip-plan cũ. | Đầu vào thêm “Dùng danh sách clip thực sẽ xuất sau khi hợp đồng clip thống nhất; id/caption khớp manifest cuối.” |
| pyh-shorts-producer — 24 | Gán/chạy | 45–90s khác clip-plan/render 60–180s; safe-zone tự khai. | Đầu ra thêm “Kế hoạch chỉ là đề xuất đến khi ánh xạ vào clip-plan và QA file xuất; không nhận hook/loop đã được render.” |
| pyh-feedback-analyst — 46 | Gán/chưa thấy | Gọn; chia loại tốt nhưng không tự thực hiện task. | Đầu ra thêm “Mỗi task ghi người/luồng tiếp nhận trong request; giữ nguyên trích ý bác sĩ và điều chưa rõ.” |
| pyh-repair-engineer — 23 | Gán/chạy | Gọn, giữ scope/cổng; thiếu ranh giới chống đọc lại toàn lịch sử. | Thực hiện thêm “Chỉ đọc log lỗi và hàm được giao; thêm ngữ cảnh khi có giả thuyết cần kiểm, không nạp toàn thư mục log.” |
| content-strategy — 444 | Gán researcher/scout, chưa thấy lượt | Quá rộng cho chọn chủ đề; pricing/demo/buy, backlink, lịch 60/30/10 và rubric 40/30/20/10 không phải rubric PYH. | Khối skill của vai chỉ dẫn đọc “Searchable vs Shareable” và ideation; thêm “Bỏ Buyer Stage/Scoring Template/Calendar; dùng rubric PYH.” |
| systematic-literature-review — 235 | Gán researcher, chưa thấy lượt | arXiv-only, lệnh /mnt/skills, bắt buộc task/subagent và báo cáo APA, sai việc săn đề/analytics; medical_expert không được gán skill này. | Bỏ khỏi `researcher.skills`; chỉ dùng theo nhu cầu tổng quan riêng với công cụ đúng môi trường, không dùng để nghiên cứu y khoa của xưởng. |
| youtube-scriptwriting — 144 | Gán writer; có tham chiếu log | Checkpoint tương tác, tự research, “Restate complex ideas twice” và Binge Loop gây lặp/hứa video mới; wrapper đã loại một phần. | Tại khối PYH chỉ định “Đọc hook/through-line/payoff; bỏ research, lặp ý và Binge Loop; không dừng hỏi duyệt checkpoint trong bước batch.” |
| short-form-video — 155 | Gán writer/shorts; có tham chiếu log | Ép payoff cuối, loop và render Short ngoài pipeline; sai với caveat sớm và clip cắt đã khóa. | Thêm điều kiện “Không trì hoãn cảnh báo an toàn; không tạo composition hay tự render; hook/loop chỉ trong quyền clip đã duyệt.” Chỉ nạp cho tác vụ clip. |
| scripting-and-storyboarding — 105 | Gán director; có tham chiếu log | Bắt đọc skill idea/brand không có trong danh mục 29; thiên quay thật/WoopSocial. | Khối PYH thay prerequisites bằng script/outline, brand.vi.yaml, style đã pin; chỉ lấy bảng audio–visual và intent từng shot, bỏ lịch quay/publish. |
| visual-style — 122 | Gán director; có tham chiếu log | Có phương pháp tạo/áp style, chưa có `visual-style.md` PYH để áp; connector tổng quát. | Đầu Apply thêm nhánh PYH “Đọc style đã duyệt từ đường dẫn được pin; ánh xạ sang brand/storyboard/motion hiện có, không tự thêm schema/connector.” |
| motion-design — 93 | Đọc trong editor | `timeline.json`, `src/lib.ts`, `npm run sfx`, review-loop không phải hợp đồng PYH; pyh-editor đã phủ định. | Thay mục 1 bằng ánh xạ scene-timing/beats/FOCUS_REGIONS/CUE_ACTIONS; bỏ npm run sfx; workflow chỉ Python dựng lại. Phần easing/typography chỉ đọc khi sửa hình. |
| remotion-best-practices — 109 | Đọc trong editor | Bắt mở Studio trước sửa, ưu tiên preview; trái bước headless cấm mở Studio/render. | Trong khối PYH ghi “Bỏ Open preview/New project/Render; chỉ đọc markup và API của component được giao.” Không nạp cây references mặc định. |
| character-animation-qa — 43 | Gán product critic; có tham chiếu log | Playwright preview/browser trái prompt chỉ review-frames; không phải mọi cảnh đều là character. | Thêm nhánh PYH dùng review-frames/index, schema và FFprobe QA có sẵn; bỏ Playwright; không nhận đã xem chuyển động liên tục từ frame mẫu. |
| social — 457 | Gán copywriter/shorts; không thấy đường dẫn trong log đã tìm | Quá dài, có MCP scheduling/publish, B2B/LinkedIn và engagement không cần cho posts. | Khối vai chỉ nạp hooks/standalone captions/no-AI-tells; loại Publishing/Scheduling/Engagement; dùng PostSet/ShortsPlan làm đầu ra duy nhất. |
| copy-editing — 491 | Gán critic/copywriter; có tham chiếu log | Dài nhất; bảy sweep marketing có proof/testimonial/claim mạnh hơn, không hợp ledger đóng. | Chỉ nạp clarity/voice/flow/concreteness; thêm “Không bổ sung proof/testimonial, không sửa mức chắc chắn; lỗi claim chuyển expert/writer.” |
| video-understand — 94 | Ngoài roster; chưa thấy log đọc | Có thể giúp kiểm video thủ công, nhưng trùng extraction/Whisper của Python; tự chạy dễ tốn GPU và sinh ASR khác. | Ghi “Công cụ điều tra theo yêu cầu; không là prerequisite product_review, không tự chạy lại Whisper nếu đã có QA phù hợp.” Giữ tùy chọn, chưa cần xóa. |

**Thiếu cần bổ sung:** một reference phong cách PYH có ví dụ đạt/trượt; hợp đồng ánh xạ clip; quy trình nghe đối chiếu âm thanh; biên nhận skill/hash và giới hạn context từng role. Ưu tiên reference ngắn trong wrapper hiện có, chưa cần tăng số vai/skill. Không có số token dành riêng cho việc đọc từng skill: **chưa đo**. Bốn skill tổng quát content-strategy/copy-editing/social/SLR dài 235–491 dòng; cần đọc theo mục thay vì gọi tất cả là cần thiết.

## 3. Thời gian, token và số vòng thực tế

Ký hiệu project: **G** gạo lứt; **X** hóc xương cá; **M** men gan; **C** C sủi. Slug đầy đủ nằm ở bảng trạng thái dưới đây. Cột mỗi ô là **số lượt ghép được / tổng giây**, kể cả lỗi. `—` = không có cặp start/end quan sát được, không phải 0 giây thực thi.

| Bước | G | X | M | C |
|---|---:|---:|---:|---:|
| research | 2 / 1.613 | 3 / 2.921 | 5 / 1.580 | 1 / 1.511 |
| draft | 3 / 3.580 | 6 / 3.215 | 25 / 11.639 | 10 / 7.499 |
| storyboard_design | 1 / 286 | 4 / 571 | 5 / 1.595 | 2 / 725 |
| voice_prep | 3 / 225 | 2 / 186 | 16 / 2.588 | 3 / 259 |
| script_review (07) | 2 / 912 | 2 / 1.412 | 21 / 2.330 | 3 / 1.965 |
| revise_medical | 1 / 1.082 | — | 1 / 217 | — |
| posts | — | — | 1 / 170 | — |
| shorts_plan | — | — | 1 / 346 | — |
| visual_review | — | — | 2 / 1.285 | — |
| product_review (12) | — | — | 15 / 8.365 | — |
| revise_product | — | — | 6 / 7.723 | — |
| revise_production | — | — | 5 / 2.337 | — |
| repair_diagnose | — | — | 11 / 2.449 | — |
| repair | — | — | 1 / 79 | — |
| **Tổng agent** | **12 / 7.698** | **17 / 8.305** | **115 / 42.703** | **19 / 11.959** |

Create/submit-medical/submit-video/produce/package và chờ người duyệt chưa có telemetry start/end chuẩn theo trạm: **chưa đo**. Không lấy mtime file hoặc khoảng cách log agent làm thời gian render. Audio TTS men gan ghi 13.008 ký tự, không phải token LLM; QA bản dựng còn lại ghi 767.634 ms (khoảng 12 phút 48 giây), không phải thời gian sản xuất.

| Project / trạng thái snapshot | Khoảng quan sát agent (UTC+7) | Tổng agent / khoảng lịch | Vòng review artifact / tình trạng |
|---|---|---|---|
| G: `an-gao-lut-muoi-me-de-bo-doi-ung-thu-tu-chua-lanh-hay-tu-day` — draft_ready | 15/11 13:07:23–19:30:02 | 2:08:18 / 6:22:39; 1 start thiếu end | 07: 2 report, 0 đạt; submitted=2 là dấu lịch sử, không chứng minh gate hiện hành hợp lệ. |
| X: `hoc-xuong-ca-nuot-ngay-nam-com-to-cach-chua-meo-hay-tu-day-x` — awaiting_medical_review | 15/11 13:16:29–20:59:06 | 2:18:25 / 7:42:37; 1 start thiếu end | 07: 1 report đạt; có 2 lượt gọi critic nhưng chỉ 1 báo cáo được ghi. |
| M: `thay-men-gan-tang-lien-voi-mua-thuoc-bo-gan-mat-gan-uong-coi` — draft_ready, còn hash production cũ | 15/11 14:12:07–16/11 23:18:58 | 11:51:43 / 33:06:51; 2 start thiếu end | 07: 20 report/1 từng đạt; 12: 3 report/0 đạt. 25 draft là lượt gọi, không phải 25 chu kỳ. |
| C: `uong-1-vien-c-sui-moi-ngay-tang-de-khang-hay-tu-nuoi-soi-can` — draft_ready | 15/11 13:53:35–21:00:19 | 3:19:19 / 7:06:44; không thiếu end | 07: 3 report/1 từng đạt; bản đạt cũ không đủ chứng minh bản hiện hành đạt. |

Khoảng lịch ở trên chỉ từ sự kiện đầu đến cuối quan sát được, chứa thời gian chờ và ngắt quãng. Tổng agent là tổng tài nguyên thời gian của nhiều nhánh, có thể chồng nhau; không dùng nó làm thời gian trôi A–Z. Activity còn slug gout/men-gan-tang-va-thuoc-bo-gan không có thư mục project tương ứng trong `projects/` hiện tại; không đủ artifact để tái dựng video hoàn tất. **Tổng thời gian một video hoàn tất hai cổng: chưa đo.**

### Token CLI quan sát được — số tổng / số log có footer

| Bước | G | X | M | C |
|---|---:|---:|---:|---:|
| research | chưa đo | chưa đo | 154.393 / 4 | chưa đo |
| draft | 155.368 / 1 | 296.293 / 3 | 3.682.674 / 23 | 463.961 / 4 |
| storyboard_design | 131.144 / 1 | 122.318 / 1 | 634.731 / 5 | 236.884 / 2 |
| voice_prep | chưa đo | chưa đo | 3.291.195 / 13 | chưa đo |
| script_review | chưa đo | chưa đo | 835.947 / 18 | chưa đo |
| revise_medical | chưa đo | — | 81.821 / 1 | — |
| product_review | — | — | 201.837 / 2 | — |
| revise_product | — | — | 162.535 / 2 | — |
| revise_production | — | — | 263.663 / 4 | — |
| **Tổng phần đo được** | **286.512 / 2** | **418.611 / 4** | **9.308.796 / 72** | **700.845 / 6** |

Posts/shorts/visual review và repair chưa có tổng usage đủ chắc để quy vào bảng; **chưa đo**. Các số token là phần quan sát được, không phải toàn bộ dự án và không dùng để so chất lượng model. Footer chỉ có ở một phần log; lượt timeout có thể tốn token mà không có footer. Voice chiếm khoảng 35,4% phần token men gan đo được; draft khoảng 39,6%. Tổng thời gian agent lớn nhất cả bốn project đều ở draft; riêng men gan tiếp theo là product_review và revise_product. Chưa tách thời gian đọc tool/log khỏi thời gian model.

| Chỗ nên ghi telemetry | Trường đề xuất / phép kiểm |
|---|---|
| `agents.invoke`/`invoke_with_failover` | Một record mỗi attempt: run_id/job_id, slug/revision, role/step, provider/model, log_path, timestamps + monotonic duration, outcome/failure_kind, parent/retry/review_cycle. Giữ raw usage có nguồn; thiếu để null + usage_available=false. |
| Adapter OmniRoute/CLI | input/output/cached/reasoning theo provider, đơn vị, source; không cộng lại trường bao hàm nhau. Nếu chỉ có footer, ghi cli_total riêng. Không suy usage từ độ dài file. |
| Runner/Python/GPU | Start/end cả trạm produce, TTS, FLUX, render, QA, package và thời gian chờ lock/model/doctor riêng; gắn artifact hashes. |
| Nạp skill | Tên/hash skill + mục đã yêu cầu đọc, prompt hash, context/token nếu provider cung cấp; không log secret/PIN/toàn văn. Có thể đưa đoạn chuẩn ngắn trực tiếp để không phụ thuộc tự giác đọc. |
| Giảm làm lại | Cache voice theo nội dung cần phát âm/dictionary/provider; vẫn stamp đúng script_hash ở hợp đồng đầu ra. Chỉ tái dùng nếu chứng minh đầu vào liên quan không đổi; không bỏ hash gate. |

## 4. Vai nhẹ có thể thử Ollama

GPU đo chỉ đọc bằng `nvidia-smi`: RTX 3060, **12.288 MiB tổng**, 9.152 MiB rảnh tại lúc kiểm; RAM 32 GB theo brief, RAM khả dụng và hiệu năng local **chưa đo**. Không cài hay tải model trong đợt này.

Ứng viên thử đầu: `qwen3:4b-instruct` Q4_K_M, gói khoảng 2,5 GB theo [thư viện Ollama](https://ollama.com/library/qwen3:4b-instruct). Dung lượng gói không phải VRAM đỉnh: còn KV cache/runtime/context. Bắt đầu context 4K cho payload đã thu hẹp; tốc độ, độ đúng tiếng Việt và tỷ lệ phải fallback **chưa đo**, chưa kết luận thay được model cloud.

| Công việc / vai | Mức phù hợp thử local | Rủi ro và cách giới hạn |
|---|---|---|
| feedback_analyst: tách ý thành task | Cao | Có thể phân loại sai thay đổi y khoa; chỉ tạo đề xuất schema, giữ nguyên lời bác sĩ, Python/Leader kiểm trước dispatch. |
| coordinator: báo trạng thái, tóm tắt job | Cao cho read-only | Không cho local tự chọn publish/cancel/reopen; action có tác động chuyển OmniRoute. |
| copywriter: tags/caption từ câu đã duyệt | Vừa | Có thể làm mạnh claim hoặc mất caveat; giới hạn biên tập chữ, posts-check + kiểm định hiện hành. Không giao sáng tác lời khuyên. |
| researcher/scout: khử trùng, phân loại metadata | Cao cho tiền xử lý | Dùng Python cho exact dedupe, local chỉ gợi ý trùng ngữ nghĩa; không giao xác minh nguồn/đáp án y khoa hay rubric cần phán đoán bằng chứng. |
| Tóm tắt log kỹ thuật | Vừa | Chỉ log đã lọc với id; không cấp quyền sửa code, không nhận tóm tắt là chẩn đoán/nghiệm thu. |
| voice_director | Thấp cho toàn vai | Chỉ có thể thử phát hiện token chưa có trong từ điển; tên thuốc, số/đơn vị, cách đọc và quyết định QA giữ tuyến hiện hành. |
| Y khoa, viết/sửa nội dung y khoa, chấm kịch bản | Không đề xuất local | Giữ OmniRoute và cổng hiện hành; không dùng local làm fallback cho các vai này. |
| Art/product critic, storyboard, editor, repair | Chưa nên thay | Cần thị giác hoặc nhiều bất biến; chưa có benchmark phù hợp, text 4B không chứng minh năng lực xem ảnh. |

**Cơ chế “đủ tài nguyên mới local, thiếu về OmniRoute” (đề xuất):** allowlist nhiệm vụ nhẹ → kiểm model đã cài/health → lấy GPU mutex hiện có → đo VRAM/RAM khả dụng → so hồ sơ peak đã benchmark của đúng model/quant/context cộng phần dự phòng → chạy một request hữu hạn → validate schema/ngữ nghĩa → giải phóng model/khóa. Bất kỳ thiếu model, thiếu bộ nhớ, context tràn, OOM, timeout hoặc validation fail thì bỏ kết quả local và gọi chuỗi OmniRoute hiện có một lần theo retry budget; không vòng qua lại vô hạn, không tự tải model lúc production.

Trước khi có peak đo thật, local chỉ chạy benchmark cô lập; chưa mở routing sản xuất. Đặt dự phòng ban đầu 2 GiB VRAM và 8 GiB RAM là **ngưỡng thử đề xuất**, phải hiệu chỉnh bằng đo; không dùng số free chụp một lần làm bảo đảm. Khi FLUX/Whisper/TTS local cần GPU thì bỏ local LLM, tránh giữ model resident tranh bộ nhớ. Không tự chấp nhận CPU offload chậm làm fallback ngầm.

Ollama có `num_ctx`, `keep_alive: 0` để unload, `ollama ps` để thấy CPU/GPU; xem [FAQ chính thức](https://docs.ollama.com/faq). API `/api/ps` có `size_vram`/context ([tài liệu](https://docs.ollama.com/api/ps)); API generate trả `prompt_eval_count`, `eval_count`, load/total duration ([tài liệu](https://docs.ollama.com/api/generate)). Đây là dữ liệu nên ghi để so local/cloud; không suy tốc độ từ cấu hình GPU.

## 5. Những gì đang quyết định phong cách video

Đây là kiểm toán hợp đồng và review có sẵn; chưa xem/nghe trực tiếp toàn video trong phiên này. Nhận định “đơn giản/lặp” được hậu thuẫn bởi review men gan, không phải điểm mỹ thuật độc lập mới.

| Nơi quyết định hình | Đã có | Thiếu để nhất quán / đề xuất |
|---|---|---|
| `profiles/brand.vi.yaml` | Navy/teal/yellow/off-white, mascot 9 pose có SHA/provenance | Palette/mascot chưa là ngữ pháp hình: cần quy tắc nét, độ lớn chữ/nhãn, khoảng trống, camera, mức trừu tượng dùng chung ngang/dọc. |
| draft prompt + pyh-writer | Kiểu Osmosis/Armando, SVG giải phẫu, ≥4 subject, đổi hình ≤6s, chart 16–24% mục tiêu | Tên kênh tham khảo và quota không tạo phong cách riêng; chuyển quyết định hình cho director và cho ví dụ PYH cụ thể đạt/trượt. |
| storyboard prompt + pyh-storyboard-director | Chọn shot, subject, motion, SVG/FLUX, mascot và safe layout | Thiếu bản thiết kế style được pin theo revision; phải chỉ rõ mỗi nhịp làm người xem hiểu thêm gì, không chỉ đổi camera/asset để đủ nhịp. |
| visual-style | Hướng dẫn tạo/extract/apply style | Không tìm thấy file `visual-style.md` PYH. Tạo bản phong cách có 3 cảnh mẫu (đời sống, cơ chế, bằng chứng), hai tỷ lệ, sau khi bác sĩ chọn phong cách. |
| image-prompting.md + pyh-art-director | Phẳng 2D matte, nền kem, nét navy, no text; mở từng ảnh/candidate | Cần golden reference chung cho FLUX và SVG, cùng rubric kiểm phong cách; art director hiện không được thiết kế lại shot đã khóa. |
| motion-vocabulary.md + component/render | 14 mẫu chuyển động có điều kiện dùng/không dùng, timing; anatomy registry/labels/cues | Đã có thư viện, cần chọn bộ động tác nhận diện nhỏ và dùng theo ngữ nghĩa; kiểm montage cả chương để tránh lặp, không dùng đủ cả 14 cho có. |
| motion-design + remotion-best-practices → editor | Easing, type, pure-frame; wrapper giữ headless | Chỉ đến lúc sửa sản phẩm mới nạp; đưa quy tắc motion thích hợp vào giai đoạn director trước cổng. Loại timeline/Studio không hợp repo. |
| product critic + QA | Điểm khớp lời, rõ, nhịp; contact sheet định kỳ | Lấy mẫu 4s bỏ lỡ motion ngắn; cần đoạn xem ngắn quanh hook/chuyển cảnh/điểm cơ chế và clip dọc, ghi rõ khả năng thực xem/nghe. |

Review men gan Trạm 12 có 3 vòng đều trượt: điểm nhịp 5→5→3, âm thanh/phụ đề 4→4→3; vòng cuối ghi hình lặp, chữ nhỏ/cắt và hình không khớp lời. Điều này cho thấy “có nhiều loại visual/motion” chưa bảo đảm đầu ra. Nên thử một đoạn mẫu có lời thật và scene timing thật trước khi khóa toàn bộ phong cách; nghiệm thu cả dễ hiểu, đọc được và nhận diện thương hiệu. Không tăng hiệu ứng để thay cho sửa bố cục/nội dung hình.

## 6. Top 5 việc nên làm

| Ưu tiên | Việc cụ thể | Tiêu chí xong |
|---|---|---|
| 1 — P0 | Thống nhất chủ sở hữu script/hình/clip; nối shorts-plan với output hoặc bỏ bước thừa; chốt cách xử lý lỗi ngoài quyền editor và QA âm thanh. | Một clip xuất thật khớp duration/hook/caveat/safe-zone; mỗi lỗi có vai nhận, cổng/hash vẫn được kiểm. Không còn kế hoạch tồn tại chỉ để readiness đạt. |
| 2 — P0 | Làm vòng 07/12 hội tụ: gộp lỗi có identity, kiểm before/after, chuyển đúng expert khi mức khẳng định kẹt; giữ trần và chờ hướng dẫn khi hết. | Ca men gan được xử lý đúng lỗi cuối và chấm độc lập trên hash mới; log chứng minh sửa tiến bộ hoặc dừng có người tiếp nhận, không reset budget vô căn cứ. |
| 3 — P1 | Ghi usage/time theo attempt và trạm Python; giảm payload phiên âm/critic, tái dùng cache hợp lệ. | Có báo cáo A–Z phân biệt active/wait/GPU/doctor; usage thiếu ghi null; voice không nạp lại toàn lịch sử khi chỉ cần quét thuật ngữ. |
| 4 — P1 | Rút skill tổng quát theo bảng; bỏ SLR khỏi researcher, làm rõ scout và schema senior; tạo style PYH có mẫu đạt/trượt trước cổng. | Mỗi vai có đầu vào/đầu ra/quyền rõ, không mở Studio/arXiv/subagent ngoài tác vụ; mẫu ngang/dọc được nghiệm thu theo style đã pin. |
| 5 — P2 | Benchmark local 4B cho phân loại feedback/tóm tắt trạng thái; routing theo bộ nhớ thực và fallback OmniRoute. | Có peak VRAM/RAM, latency, usage, tỷ lệ lỗi schema/chuyển tuyến và so sánh chất lượng trên cùng bộ ca; chỉ bật allowlist khi đạt, không đưa y khoa/chấm kịch bản sang local. |

### Mốc nguồn để kiểm lại

| Kết luận | File/hàm hoặc log mẫu |
|---|---|
| Thứ tự và quyền | `src/healthvideo/workflows/runner.py`: render_prompt, _build_step_prompt, AGENT_STEPS và chọn bước; `company.py`: role_skill_block, CRITIC_OF; `profiles/company.yaml`. |
| Vòng chấm | `workflows/script_review.py`: next_script_action, revision_notes, record_review; `product_review.py`: next_product_action, require_passed_review. |
| Khoảng hở clip/rubric | `workflows/shorts_plan.py`: save_shorts_plan; `produce.py` + render clip-plan; `researcher.py`: discover_topics_with_agent/rubric; prompt shorts_plan và draft. |
| Số thời gian | Checkout chính `topics/logs/activity.jsonl`; `topics/logs/xuong.log` các dòng 375, 381, 384, 387, 390. |
| Review/history | Mỗi slug ở trên: `revisions/001/reviews/script-review-log.yaml`; men gan thêm `product-review-log.yaml`, `video-qa.json`, `audio/tts-usage.json`. |
| Footer/đọc skill | Log men gan `20261116T161756243580-omniroute.log` (45.657 token); `20261116T034540730279-omniroute.log` (122.812); voice `20261116T101502374494-omniroute.log` có lệnh đọc skill; writer gạo lứt `20261115T071332891209-codex.log`; editor men gan `20261116T045213661885-omniroute.log`. |

Không thay workflow/schema, chạy sản xuất, sửa approval, cài model, cập nhật progress hoặc commit trong đợt audit này.
