---
name: pyh-editor
description: Use when PYH revise_production or revise_product needs permitted SVG or post corrections.
---

# Thợ dựng xưởng PYH

## Sửa từng phần
- Chỉ xử lý issue mở. `revise_product` chỉ sửa đúng path và dải dòng `edits`
  được critic giao, giữ nguyên từng byte bên ngoài, kể cả phần khác trong cùng file.
- Ngữ cảnh/cảnh kề chỉ để kiểm ảnh hưởng, không tự mở rộng phạm vi. Giữ timing,
  hash và cổng. Nếu cần đổi file khóa, trả lại mục vượt quyền theo đường hiện hành.
- Python khôi phục và trả lại một lần khi sửa ngoài phạm vi; cùng issue còn mở
  hai vòng thì chờ bác sĩ hướng dẫn, không tự lặp hay chấm đạt.

## Đầu vào
- Đọc prompt bước và `active_revision` từ `{project}/project.yaml`.
- Trong `revisions/<rev>/`, đọc `reviews/visual-review.yaml`, contact sheet,
  góp ý cổng video hoặc vòng cuối `reviews/product-review-log.yaml` theo bước.
- Đối chiếu `script/script.yaml`, `storyboard/storyboard.yaml`,
  `renders/scene-timing.json`; đọc `docs/reference/motion-vocabulary.md`
  và thư viện `video/src/anatomy/` cho component cần sửa.

## Phán đoán công việc
- Kỷ luật thợ dựng (`docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md` mục 5 & 6):
  chỉ sửa đúng lỗi bị nêu; tuyệt đối không tự thêm hiệu ứng, chuyển động, bounce hay mẫu motion
  ngoài bộ động tác nhận diện ở mục 5 (dựng sơ đồ dần, vòng nhấn teal, gạch chân vàng,
  thẻ thuật ngữ, thẻ nguồn; tối đa 2 mẫu `video/src/motion` khác trong một chương) để "cho sinh động".
  Zoom y khoa dùng kính lúp mục 3b, không cross-fade chồng mờ giả zoom.
- Sửa hình giúp hiểu đúng câu đang đọc: chủ thể, nhãn, mũi tên, thứ tự nhấn;
  không chỉ thêm hiệu ứng đều mỗi 6 giây rồi coi chất lượng đã đạt.
- Giữ giới hạn timing/beat hiện hành; không đổi storyboard đã khóa để né lỗi.
- Sơ đồ phẳng tiếng Việt, font `Be Vietnam Pro`, tối đa 6 nhãn,
  leader line rõ hướng; chừa biên khoảng 60px và vùng phụ đề.
- Motion thuần từ `frame`, giảm tốc khi dừng; không `Math.random()` hay `Date`.
  Dùng `FOCUS_REGIONS`, `LABELS`, `CUE_ACTIONS`, registry thật của repo;
  không tìm `timeline.json` hay `src/lib.ts` từ skill motion ngoài.
- Không mở Studio/chạy `npx remotion render`, không tự dựng TTS/nhạc/video;
  xưởng Windows headless để Python dựng lại, tránh treo pipe.

## Đầu ra
- `revise_production`: chỉ component SVG trong `video/src/anatomy/` kèm test.
  Nếu chỉ sửa hợp lệ, resume về `production_in_progress` đúng lệnh prompt.
- `revise_product`: component SVG kèm test và/hoặc
  `revisions/<rev>/posts/posts.yaml`; sửa posts thì chạy `posts-check` đến exit 0.
- Không sửa script, storyboard, manifest, clip-plan, ledger, explainer hay profiles;
  các file này đã khóa, kể cả lỗi beat/subject/prompt FLUX/phát âm.
- Không tạo báo cáo/schema mới; báo kết quả và mục ngoài quyền theo prompt.

## Xong khi
- Mục sửa được đã sửa, test component liên quan đạt; posts-check đạt nếu đổi posts.
  `revise_production` kiểm status đúng đích hoặc đã báo file cần mở cổng;
  `revise_product` không tự đổi trạng thái. Python dựng và critic chấm lại.

## Thiếu dữ liệu hoặc lỗi
- Cần sửa file khóa / lỗi ngoài quyền (`script`, `storyboard`, `manifest`, `clip-plan`, `ledger`, `explainer`, `profiles`, prompt FLUX, phát âm): trả rõ file/cảnh và vai cần nhận cho Leader; `revise_production` giữ `blocked` hoặc mở cổng theo quy trình hiện hành, `revise_product` để lại mục đó cho bác sĩ quyết — tuyệt đối không lặp dựng lại bản không đổi.
- Công cụ lỗi: báo lệnh/log và phần chưa xong; chỉ retry trong budget bước,
  không sửa claim/hash/approval để vượt lỗi, không giả render đã thành công.
