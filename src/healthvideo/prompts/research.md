# Bước: Nghiên cứu bằng chứng và cơ chế (`research`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Việc cần làm
1. Đặt 3–6 truy vấn **tiếng Anh** cho PubMed/Europe PMC từ câu hỏi chính `{question}`; chạy `healthvideo step evidence-search {project} --query "<q>"` (lặp cờ `--query` cho các truy vấn).
2. Chạy `healthvideo step evidence-screen {project}` để sàng lọc ứng viên, rồi chạy `healthvideo step build-ledger {project}` để dựng sổ cái bằng chứng; chỉ giữ vài nguồn mạnh nhất, ưu tiên hướng dẫn lâm sàng (guideline), tổng quan hệ thống (SR/MA), và RCT.
3. Viết `explainer.yaml` trong thư mục `explainer/` của revision hiện hành theo spec explain-first (`docs/superpowers/specs/2026-10-18-explain-first-content-design.md` §4):
   - Bắt buộc tối thiểu một tầng "bình thường" (`anatomy` hoặc `physiology`) và một tầng "bệnh" (`pathophysiology` hoặc `pathology`), đúng thứ tự từ bình thường sang bệnh; bỏ tầng nào phải ghi trong `skipped_layers`.
   - Mỗi tầng có một ẩn dụ đời thường kèm giới hạn của ẩn dụ, ví dụ: `analogy: {text: "ống tưới vườn", limits: "mạch máu tự co chủ động, ống thì không"}`.
   - Mọi khẳng định cơ chế phải trỏ tới `claim_ids` thuộc loại `mechanism` có nguồn xác minh trong ledger.
4. Nếu không đủ bằng chứng xác minh để trả lời câu hỏi `{question}`, dừng ngay và ghi rõ lý do vào `{project}/blocked-reason.md` — **không** viết nội dung suy đoán.

## Lệnh được dùng
- `healthvideo step evidence-search {project} --query "<q>"`
- `healthvideo step evidence-screen {project}`
- `healthvideo step build-ledger {project}`
- `healthvideo status {project}`

## Đầu ra
- Dữ liệu ứng viên và bảng sàng lọc trong `revisions/<rev>/evidence/`
- Sổ cái bằng chứng và claim ledger hợp lệ trong `revisions/<rev>/evidence/`
- Bản đồ cơ chế `revisions/<rev>/explainer/explainer.yaml` hợp lệ (hoặc `{project}/blocked-reason.md` nếu thiếu bằng chứng)

## Xong khi
- Trạng thái đích của project đạt `evidence_ready`, kiểm tra bằng lệnh `healthvideo status {project}` (hoặc đã ghi `{project}/blocked-reason.md` và dừng).
