# Bước: Sửa theo người duyệt sản phẩm (`revise_product`)

## Bối cảnh
- Project: `{project}`
- Chủ đề: `{title}`. Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Nhận xét cần sửa
{reject_note}

## Việc cần làm
1. Đọc `active_revision` trong `{project}/project.yaml`; `<rev>` là giá trị đó. Nhận xét đầy đủ ở `{project}/revisions/<rev>/reviews/product-review-log.yaml` (vòng cuối).
2. Chỉ sửa phẫu thuật đúng các lỗi `fixable: true` trong phạm vi được phép:
   - `video/src/anatomy/*`, `video/src/components/*`, `video/src/scenes/*` (theo `edits` nếu có, hoặc component anatomy của cảnh bị gắn cờ / component hiển thị & outro: `OutroScene.tsx`, `YouTubeEndCard.tsx`, `VisualAsset.tsx`, `logoContrast.ts`), kèm test; giữ sơ đồ tiếng Việt có leader line, tối đa 6 nhãn không chồng/cắt;
   - `storyboard/storyboard.yaml`: CHỈ sửa các cảnh `Sxx` thuộc danh sách được phép (nhịp, beat, entrances, visual, anatomy, on_screen_text, mascot_pose); giữ nguyên từng chữ cảnh khác và metadata; tuyệt đối không đổi `id`, `script_line_id`, `narration`, `claim_id`, `chapter_id`, `source_marker`, `source_card`, `evidence_highlight`;
   - `assets/asset-manifest.yaml` & `script/clip-plan.yaml`: chỉ sửa/thêm asset `semantic: false` cho cảnh được phép; không xóa hay đổi sha256 asset `semantic: true` hoặc `storyboard_role == 'brand'`;
   - `script/voice-prep.yaml`: chỉ sửa khi có issue âm thanh/phát âm, giữ `script_hash` khớp `script/script.yaml`;
   - `{project}/revisions/<rev>/posts/posts.yaml` (chạy `healthvideo step posts-check {project}` tới mã thoát `0`) & `posts/shorts-plan.yaml`.
3. Khóa cứng tuyệt đối y khoa: KHÔNG sửa `script/script.yaml`, `evidence/*`, `explainer/*`, `assets/license-ledger.yaml`, `script/outline.yaml`.
4. Kỷ luật thợ dựng (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` mục 5): tuyệt đối không tự thêm hiệu ứng, chuyển động hay mẫu motion ngoài bộ động tác nhận diện (dựng sơ đồ dần, vòng nhấn teal, gạch chân vàng, thẻ thuật ngữ, thẻ nguồn; tối đa 2 mẫu khác trong một chương) để "cho sinh động"; không bounce ở chuyển cảnh, zoom y khoa dùng kính lúp mục 3b (không cross-fade chồng mờ).
5. Bắt buộc ghi mọi file YAML bằng Python với `encoding='utf-8'` để không mất dấu tiếng Việt thành `'?'`.
6. Không dựng video, không đổi trạng thái project. Python dựng lại ngay sau bước này và người duyệt sẽ chấm lại.

## Xong khi
- Mọi mục `fixable: true` đã sửa đúng phạm vi; test component đã sửa (nếu có) chạy qua.
