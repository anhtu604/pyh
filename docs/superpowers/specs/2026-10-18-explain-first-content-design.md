# Thiết kế tái cấu trúc nội dung: giải thích trực quan trước, bằng chứng sau

**Ngày:** 18-10-2026
**Trạng thái:** approved 18-10-2026; plan `docs/superpowers/plans/2026-10-18-explain-first-content.md`.
**Kế thừa:** bản 07-09-2026 (§3, §8, §9, §10), bản 09-09-2026 (state graph, hai cổng
duyệt) và bản 20-09-2026 (orientation). Tài liệu này chỉ mô tả phần thay đổi.
**Thay thế:** khung 6 nhịp §9.2 và tỷ lệ hình ảnh §10 bản 07-09-2026 khi hai bên mâu thuẫn.
Lộ trình M8 (video dài, clip, VoiceStudio, script-voice) tạm dừng; không phải đầu vào
của thiết kế này.

## 1. Vấn đề

Hệ thống hiện tối ưu cho việc *dẫn chứng*: claim ledger là trung tâm, kịch bản đi theo
lập luận "vấn đề → lập trường → bằng chứng". Kết quả là video giống bản tóm tắt bài báo.
Người xem phổ thông thiếu nền để hiểu vì sao bằng chứng quan trọng: họ chưa thấy cơ quan
đó trông thế nào, bình thường hoạt động ra sao và hỏng ở đâu.

## 2. Mục tiêu

1. Mỗi video **giải thích cơ chế bằng hoạt họa trước**, theo chuỗi
   giải phẫu → sinh lý → sinh lý bệnh → giải phẫu bệnh, rồi mới đưa bằng chứng.
2. Bằng chứng ngắn, đúng trọng tâm: trả lời "vậy làm gì thì có ích, chắc chắn đến đâu".
3. Tìm và sàng lọc bài báo **nhanh gọn**: vài nguồn mạnh nhất, không phải tổng quan hệ thống.
4. Giữ nguyên: không bịa nguồn/số liệu, author-owned voice, hai cổng duyệt, không tự đăng.

## 3. Mạch nội dung mới (explain-first arc)

| # | Nhịp | Câu hỏi người xem | Hình ảnh chủ đạo | Tỷ trọng thời lượng |
|---|---|---|---|---|
| 1 | Mở | "Chuyện này liên quan gì đến tôi?" | tình huống đời thường | 5–10% |
| 2 | Giải phẫu | "Bộ phận đó nằm đâu, trông thế nào?" | cơ quan hoạt họa, zoom từ cơ thể vào | 10–15% |
| 3 | Sinh lý | "Bình thường nó làm việc ra sao?" | dòng chảy, tín hiệu, chu trình chuyển động | 15–20% |
| 4 | Sinh lý bệnh | "Hỏng ở khâu nào, vì sao?" | cùng cảnh đó nhưng có lỗi, so sánh bình thường/bệnh | 20–25% |
| 5 | Giải phẫu bệnh / hậu quả | "Lâu dần cơ thể thay đổi gì?" | mô/cơ quan biến đổi theo thời gian | 10–15% |
| 6 | Bằng chứng | "Làm gì thì có ích, chắc đến đâu?" | biểu đồ, trích đoạn nghiên cứu | 15–20% |
| 7 | Hành động + giới hạn | "Tôi nên làm gì, ai không áp dụng?" | checklist ngắn, outro | 5–10% |

Quy tắc:

- Nhịp 2–5 dùng **một bộ hình nhất quán**: cùng cơ quan, cùng màu, cùng góc nhìn, để
  người xem thấy "đây là cái mình vừa xem, giờ nó hỏng". Đây là điểm khác biệt chính.
- Không phải chủ đề nào cũng cần đủ 4 tầng. Bắt buộc tối thiểu: **một tầng "bình thường"**
  (2 hoặc 3) và **một tầng "bệnh"** (4 hoặc 5). Bỏ tầng nào phải ghi lý do trong explainer.
- Mỗi thuật ngữ chỉ xuất hiện sau khi đã có hình minh họa; tối đa 3 thuật ngữ mới mỗi video
  ngắn, 2 thuật ngữ mới mỗi chương video dài.
- Mỗi tầng có **một ẩn dụ đời thường** (ví dụ ống nước, công an, đồn) do AI đề xuất, bác sĩ
  chọn hoặc sửa. Ẩn dụ không được làm sai cơ chế; giới hạn của ẩn dụ phải ghi lại.
- Giọng tác giả, lập trường và trải nghiệm vẫn do bác sĩ cung cấp (§9.1 bản 07-09 giữ nguyên).
- Mạch áp dụng cho mọi độ dài: video ngắn gộp nhịp, video dài lặp nhịp 2–6 ở cấp chương.

## 4. Artifact mới: `explainer.yaml`

Đặt tại `revisions/<rev>/explainer/explainer.yaml`, tạo trong `research_in_progress`,
song song với claim ledger. Đây là "bản đồ cơ chế" mà kịch bản và storyboard dựa vào.

```yaml
schema_version: "1.0"
topic_question: "Vì sao huyết áp cao mà không thấy gì?"
organ_system: cardiovascular
layers:
  - id: L1
    layer: anatomy            # anatomy | physiology | pathophysiology | pathology
    concept: "Động mạch có thành cơ đàn hồi"
    plain_explanation: "Mạch máu lớn giống ống cao su dày, co giãn theo mỗi nhịp tim."
    analogy: {text: "ống tưới vườn", limits: "mạch máu tự co chủ động, ống thì không"}
    terms_introduced: ["động mạch"]
    visual:
      kind: anatomy_animation # anatomy_animation | process_animation | comparison | timelapse
      subject: artery_cross_section
      motion: "thành mạch giãn ra theo nhịp tim"
      reuse_of: null           # id lớp trước nếu dùng lại cùng hình, để giữ nhất quán
    claim_ids: [M01]
  - id: L3
    layer: pathophysiology
    concept: "Áp lực cao kéo dài làm thành mạch dày và cứng"
    visual: {kind: comparison, subject: artery_cross_section, reuse_of: L1,
             motion: "bên trái bình thường, bên phải thành dày, lòng hẹp"}
    claim_ids: [M03]
skipped_layers:
  - layer: pathology
    reason: "Video ngắn; hậu quả trình bày gộp ở nhịp hành động."
```

Ví dụ trên chỉ minh họa cấu trúc; nội dung y khoa thật phải lấy từ nguồn đã xác minh.

Validator bắt buộc: thứ tự tầng không đi ngược (bệnh trước bình thường), đạt mức tối thiểu
ở §3, `reuse_of` trỏ tới lớp tồn tại, mọi `claim_ids` có trong ledger, mọi thuật ngữ
trong lời thoại đã được giới thiệu ở một lớp có hình.

## 5. Claim cơ chế

Thêm `type: mechanism` vào claim ledger, cạnh `evidence | interpretation | professional_opinion`.

- Nguồn hợp lệ cho claim cơ chế: sách giáo khoa y khoa, StatPearls/NCBI Bookshelf,
  review cơ chế, guideline. Đây là "nguồn nền" theo §8 bản 07-09; nay chính thức có nhãn riêng.
- Claim cơ chế **không cần** PICO, effect size hay mức chắc chắn GRADE-lite; vẫn cần nguồn
  xác minh được hoặc nhãn `professional_opinion` nếu là kiến thức bác sĩ tự xác nhận.
- Claim cơ chế không được dùng để khẳng định hiệu quả can thiệp ("vì cơ chế vậy nên thuốc X
  có ích" là claim `evidence`, phải có bằng chứng kết cục).
- Cổng duyệt 1 hiển thị claim cơ chế thành nhóm riêng, kèm mô tả hình dự kiến, để bác sĩ
  duyệt **độ đúng giải phẫu** trước khi dựng.

## 6. Tìm và sàng lọc bài báo nhanh

Mục tiêu là "đủ để nói đúng", không phải tổng quan hệ thống. Ngân sách mặc định mỗi video:

| Nhóm | Số nguồn | Ưu tiên |
|---|---|---|
| Guideline hiện hành | 1–2 | VN/WHO/hội chuyên ngành |
| SR/meta-analysis | 1–3 | mới nhất, đúng câu hỏi |
| Nghiên cứu gốc | 0–2 | chỉ khi là nghiên cứu then chốt hoặc mới |
| Nguồn cơ chế | 1–3 | sách giáo khoa, StatPearls |

Quy trình (tái dùng orientation và evidence workflow hiện có, không thêm state):

1. **Truy vấn hẹp**: PubMed/Europe PMC với bộ lọc loại bài (guideline, SR, MA, RCT) và
   10 năm gần nhất; tối đa 50–100 kết quả mỗi câu hỏi.
2. **Sàng lọc tiêu đề/abstract** qua interface `Screener` trả về
   `include | exclude | unsure` + lý do ngắn + xác suất (nếu có):
   - `dual_llm` (mặc định): hai lượt đánh giá độc lập theo tiêu chí ghi sẵn; bất đồng
     hoặc `unsure` → lượt thứ ba xem cả hai lý do (theo nguyên tắc reviewer độc lập của Cochrane).
   - `jev` (khi có API key TypeSafe): chấm xác suất, chỉ bài lưng chừng chuyển sang LLM.
   - Kết quả sàng lọc là **gợi ý**: không tự thêm nguồn vào ledger; nguồn vào ledger
     vẫn qua validator hiện có (DOI/PMID xác minh, không bịa).
3. **Bảng sàng lọc** `screening.csv` (id, tiêu đề, năm, loại bài, quyết định, lý do,
   reviewer) để bác sĩ lướt trong 2–3 phút và sửa quyết định.
4. Chỉ trích số liệu từ nguồn đã được chọn; số liệu trong lời thoại vẫn phải khớp ledger.

**LatteReview:** không đưa vào dependency. Giấy phép PolyForm Noncommercial không phù hợp
nếu kênh kiếm tiền. Chỉ tham khảo thiết kế (reviewer kép + người phân xử). Nếu sau này có
giấy phép thương mại, có thể thay `dual_llm` bằng adapter LatteReview mà không đổi artifact.

**Jev:** runtime Jev đã gỡ (commit `72deb95`); spec 2026-09-21 chỉ còn là lịch sử. Adapter
`jev` mới chỉ phục vụ sàng lọc, nhận key qua biến môi trường, test bằng fake transport,
không gọi mạng trong test. Triển khai khi người dùng cung cấp API.

## 7. Hình ảnh và hoạt họa

- Storyboard thêm các `visual` mới: `anatomy_animation`, `process_animation`, `comparison`,
  `timelapse`, ánh xạ 1–1 với `explainer.layers[].visual.kind`.
- **Thư viện cơ quan** trong `video/src/anatomy/`: component Remotion SVG điều khiển hoàn toàn
  bằng frame (không dùng thư viện chạy theo đồng hồ thực). Mỗi cơ quan có trạng thái
  `normal | diseased` và tham số mức độ, để nhịp 4–5 tái dùng đúng hình nhịp 2–3.
  Bắt đầu với hệ tim mạch (mạch máu, tim) vì là chủ đề thí điểm; cơ quan khác thêm theo chủ đề.
- **Phong cách:** chọn 1 phong cách chủ đạo (đề xuất: 2D phẳng kiểu Kurzgesagt hoặc bảng
  trắng). Kho `.refs/animasyon-stil-katalogu` chỉ để xem; không chép file vì repo không có
  giấy phép. Tự vẽ lại theo nguyên tắc chung.
- **Tỷ lệ hình ảnh mới** (thay §10 bản 07-09): hoạt họa cơ chế 55–70%, biểu đồ và trích đoạn
  bằng chứng 15–25%, chữ/checklist/outro 10–15%, AI clip ≤ 5%. Visual budget kiểm tra theo tỷ lệ này.
- **Tự xem frame (review-loop):** công cụ `healthvideo review frames <slug>` render bản nháp
  độ phân giải thấp, lấy frame tại mỗi mốc cảnh (+9 frame cho cảnh đã ổn định), ghép contact
  sheet 4×2 bằng Pillow. Agent xem, sửa, lặp. Contact sheet các cảnh cơ chế được đưa vào gói
  cổng duyệt 2 để bác sĩ kiểm độ đúng giải phẫu. Đây là QA bổ sung, không thay cổng duyệt.

## 8. Thay đổi workflow và tương thích

- **Không thêm main state.** `research_in_progress → evidence_ready` nay yêu cầu cả claim
  ledger hợp lệ **và** `explainer.yaml` hợp lệ. Orientation (bản 20-09) giữ nguyên.
- `script.yaml`: mỗi dòng thêm `arc_beat` (1–7 theo §3) và `explainer_layer_id` (nếu có).
  Lint kiểm tra thứ tự nhịp, tỷ trọng thời lượng (cảnh báo, không chặn) và thuật ngữ chưa giới thiệu.
- Project cũ (v1, và v2 đã qua `evidence_ready`) không bị ảnh hưởng: trường mới tùy chọn,
  `format_profile` cũ giữ nguyên hành vi. Project mới mặc định `explain_first_v1`.
- Schema đổi có version và test; JSON schema xuất lại bằng `tools/export_schemas.py`.

## 9. Kế hoạch triển khai (để lập plan chi tiết sau khi duyệt)

| Giai đoạn | Nội dung | Kiểm chứng |
|---|---|---|
| P1 | Model + schema `explainer`, claim `mechanism`, `arc_beat` trong script | unit test validator, schema export không lỗi |
| P2 | Nối explainer vào `evidence_ready`, gói cổng 1 hiển thị nhóm cơ chế | test chuyển trạng thái, project cũ không đổi |
| P3 | `Screener` + `dual_llm` + `screening.csv`; adapter `jev` khi có key | test với fake provider, không gọi mạng |
| P4 | Thư viện cơ quan tim mạch + 4 visual kind mới trong Remotion | vitest, typecheck, contact sheet |
| P5 | `review frames` (contact sheet) + tỷ lệ visual budget mới | test lấy frame và tile ảnh |
| P6 | Thí điểm end-to-end với `do-huyet-ap-khong-trieu-chung` | bác sĩ duyệt qua cả hai cổng |

P1–P3 (Python) và P4 (TypeScript) độc lập nên Codex có thể làm song song trong hai worktree.

## 10. Tiêu chí chấp nhận

1. Một project mới không vào được `evidence_ready` khi thiếu explainer hoặc explainer sai thứ tự/thiếu tầng tối thiểu.
2. Claim `mechanism` không có nguồn xác minh hoặc nhãn ý kiến chuyên môn bị từ chối; claim hiệu quả dựa trên cơ chế bị từ chối.
3. Sàng lọc không thể đưa nguồn vào ledger nếu chưa qua validator; test không gọi mạng.
4. Cảnh nhịp 4–5 tái dùng component của nhịp 2–3 (`reuse_of`) và render được trạng thái bệnh.
5. Video thí điểm: ≥ 55% thời lượng là hoạt họa cơ chế, bác sĩ thao tác ≤ 30 phút ngoài phần duyệt.
6. Toàn bộ test Python, vitest, typecheck và ruff qua; hai cổng duyệt và không tự đăng giữ nguyên.

## 11. Quyết định đã chốt (18-10-2026)

1. **Định dạng thí điểm:** 3–5 phút, 16:9 (1920×1080). Tái dùng format profile
   `youtube_long` và render theo chương đã làm xong trên nhánh `feat/m8-1-long-form`
   (merge vào `master` ở Task 0 của plan); không mở lại phần còn lại của M8.
2. **Phong cách hoạt họa:** 2D phẳng kiểu Kurzgesagt — hình khối đơn giản, màu bão hòa
   trên nền tối, bóng đổ mềm, không viền đen. Tự vẽ, không chép từ kho tham khảo.
3. **Sàng lọc mặc định:** `dual_llm`; `jev` bổ sung khi người dùng cung cấp API.
