# Bước: Sửa theo góp ý cổng y khoa (`revise_medical`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
- Ghi chú từ chối cổng y khoa: `{reject_note}`

## Việc cần làm
1. Đọc kỹ ghi chú từ chối `{reject_note}` và file `*-rejected.yaml` hoặc `*-reopened.yaml` mới nhất trong thư mục `reviews/medical/` của revision hiện hành để xác định toàn bộ điểm bị bác sĩ yêu cầu sửa.
2. Bạn là biên kịch viral: sửa đúng những chỗ bị chỉ ra trong `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml` hoặc `clip-plan.yaml`, bám `revisions/<rev>/evidence/expert-brief.md` và ledger. Không tự tìm nguồn, không thêm hay sửa claim, ledger, `explainer.yaml`, `expert-brief.md`: chỗ nào cần chuyên gia y học, ghi câu hỏi vào `revisions/<rev>/script/questions.yaml` (`questions: [{id: Q1, line: N03, ask: "..."}]`), chạy `healthvideo step resume {project} --gate medical --to research_in_progress` rồi dừng; chuyên gia sẽ bổ sung và xưởng chuyển lại cho bạn. Nếu sửa lời thoại, chạy lại skill `humanizer` trên phần lời thoại.
3. Không tranh luận với ghi chú của bác sĩ và không thêm trải nghiệm bác sĩ ngoài `{doctor_note}` hay `{reject_note}`. Nếu ghi chú yêu cầu khẳng định điều không có bằng chứng xác minh, ghi rõ vào `{project}/blocked-reason.md` và dừng ngay.
4. Trước khi nộp, chạy `healthvideo step resume {project} --gate medical --to draft_ready` (cần chuyên gia thì làm như mục 2 và dừng). Khi đã sửa xong và khớp bằng chứng, chạy `healthvideo step draft {project} --script <script.yaml> --storyboard <storyboard.yaml> --assets <asset-manifest.yaml>` tới khi hết lỗi rồi dừng. KHÔNG tự nộp cổng y khoa: xưởng sẽ cho Kiểm duyệt kịch bản chấm bản sửa trước, đạt thì xưởng tự nộp.

## Lệnh được dùng
- `healthvideo step resume {project} --gate medical --to <draft_ready|research_in_progress>`
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo status {project}`

## Đầu ra
- Các file `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml`, `clip-plan.yaml` đã cập nhật trong revision hiện hành (hoặc `script/questions.yaml` khi cần chuyên gia, hoặc `{project}/blocked-reason.md` nếu thiếu bằng chứng)

## Xong khi
- Trạng thái đích của project là `draft_ready` và `healthvideo step draft` không còn lỗi, kiểm tra bằng `healthvideo status {project}` (hoặc `research_in_progress` sau khi đã ghi câu hỏi cho chuyên gia, hoặc đã ghi `{project}/blocked-reason.md` và dừng).

## Đường dẫn revision hiện hành
Đọc `active_revision` từ `{project}/project.yaml`; `<rev>` là giá trị đó.
- `revisions/<rev>/script/script.yaml`, `revisions/<rev>/script/outline.yaml`, `revisions/<rev>/script/clip-plan.yaml`
- `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`
- `revisions/<rev>/evidence/ledger.yaml`, `revisions/<rev>/explainer/explainer.yaml`
