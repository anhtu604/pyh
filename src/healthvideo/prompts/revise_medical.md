# Bước: Sửa theo góp ý cổng y khoa (`revise_medical`)

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
- Ghi chú từ chối cổng y khoa: `{reject_note}`

## Việc cần làm
1. Đọc kỹ ghi chú từ chối `{reject_note}` và file `*-rejected.yaml` mới nhất trong thư mục `reviews/medical/` của revision hiện hành để xác định toàn bộ điểm bị bác sĩ yêu cầu sửa.
2. Sửa đúng những chỗ bị chỉ ra trong hồ sơ bằng chứng, `explainer.yaml`, `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml` hoặc `clip-plan.yaml`. Nếu cần bổ sung hoặc thay nguồn bằng chứng, dùng lại các lệnh của bước `research` (`evidence-search`, `evidence-screen`, `build-ledger`). Nếu sửa lời thoại, chạy lại skill `humanizer` trên phần lời thoại.
3. Không tranh luận với ghi chú của bác sĩ và không thêm trải nghiệm bác sĩ ngoài `{doctor_note}` hay `{reject_note}`. Nếu ghi chú yêu cầu khẳng định điều không có bằng chứng xác minh, ghi rõ vào `{project}/blocked-reason.md` và dừng ngay.
4. Khi đã sửa xong và khớp bằng chứng, chạy `healthvideo step draft {project} --script <script.yaml> --storyboard <storyboard.yaml> --assets <asset-manifest.yaml}` tới khi hết lỗi, rồi nộp lại cổng y khoa bằng `healthvideo step submit-medical {project}`.

## Lệnh được dùng
- `healthvideo step evidence-search {project} --query "<q>"`
- `healthvideo step evidence-screen {project}`
- `healthvideo step build-ledger {project}`
- `healthvideo step draft {project} --script <path> --storyboard <path> --assets <path>`
- `healthvideo step submit-medical {project}`
- `healthvideo status {project}`

## Đầu ra
- Các file `explainer.yaml`, ledger, `script.yaml`, `storyboard.yaml`, `asset-manifest.yaml`, `outline.yaml`, `clip-plan.yaml` đã cập nhật trong revision hiện hành (hoặc `{project}/blocked-reason.md` nếu thiếu bằng chứng)
- Hồ sơ trình duyệt y khoa mới sau khi chạy `submit-medical`

## Xong khi
- Trạng thái đích của project đạt `awaiting_medical_review`, kiểm tra bằng lệnh `healthvideo status {project}` (hoặc đã ghi `{project}/blocked-reason.md` và dừng).
