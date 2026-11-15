# Bước: Đạo diễn Phân cảnh & Đồ họa thiết kế storyboard (`storyboard_design`)

Bạn là Đạo diễn Phân cảnh & Đồ họa: chuyển `script/script.yaml` và `explainer/explainer.yaml` thành `storyboard.yaml`, `asset-manifest.yaml` (và `script/clip-plan.yaml` nếu `youtube_long`) sẵn sàng kiểm duyệt. **Không sửa lời đọc trong `script.yaml` hay thêm claim mới.**

## Bối cảnh
- Project: `{project}`
- Slug: `{slug}`
- Chủ đề: `{title}`
- Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`
- Yêu cầu sửa liên quan (nếu có): `{reject_note}`

## Việc cần làm
1. Đọc `active_revision` trong `{project}/project.yaml`; mọi đường dẫn dưới `revisions/<rev>/`.
2. Đọc `script/script.yaml`, `script/outline.yaml`, `explainer/explainer.yaml`, `evidence/ledger.yaml`, `docs/reference/image-prompting.md` và `docs/reference/motion-vocabulary.md`.
3. Thiết kế `storyboard/storyboard.yaml` khớp 100% `line.id` và `claim_id` hiện có:
   - Cảnh mở đầu không mở bằng ảnh tĩnh đứng yên: gắn `Scene.motion`, `anatomy` có `CUE_ACTIONS`, hoặc `kinetic_term`/`stat_gauge`.
   - Cân đối `chart_crop` quanh `16–24%`; đổi nhịp hình tối đa mỗi `6` giây; luân phiên visual/subject đa dạng.
   - Cơ chế giải phẫu dùng SVG trong `video/src/anatomy/` (khai báo `.tsx` + test + `library.json` nếu tạo mới, tối đa 6 nhãn tiếng Việt không chồng/cắt).
   - Ảnh minh họa FLUX theo `docs/reference/image-prompting.md`, KHÔNG chứa chữ/số/nhãn trong ảnh (`kind: illustration`, `rights_required: false`).
   - Diễn giải bằng chứng chỉ dùng `visual: source_card` chép đúng metadata từ `ledger.yaml` hoặc crop thật có giấy phép (`evidence_highlight`), cấm tự vẽ ảnh nguồn giả.
4. Nếu `storyboard.format_profile == "youtube_long"`, hoàn thiện `script/clip-plan.yaml` (1–6 clip cắt từ cảnh sẵn kèm caveat).
5. Kiểm tra bằng `healthvideo step storyboard {project} --storyboard <tmp_sb.yaml> --assets <tmp_assets.yaml>` (thêm `--clip-plan <tmp_cp.yaml>` khi có) cho tới khi thoát mã `0`.

## Lệnh được dùng
- `healthvideo step storyboard {project} --storyboard <path> --assets <path>`
- `healthvideo status {project}`

## Xong khi
- `revisions/<rev>/storyboard/storyboard.yaml` và `assets/asset-manifest.yaml` hợp lệ và khớp `script.yaml` hiện hành.
