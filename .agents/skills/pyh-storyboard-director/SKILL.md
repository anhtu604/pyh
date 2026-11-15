---
name: pyh-storyboard-director
description: Use when PYH storyboard_design designs storyboard.yaml, asset-manifest.yaml, clip-plan.yaml, FLUX prompts, and video/src/anatomy SVG components from an authored script.yaml.
---

# Đạo diễn Phân cảnh & Đồ họa PYH (`storyboard_director`)

## Đầu vào
- Đọc `project.yaml` lấy `active_revision`; làm việc trong `revisions/<rev>/`.
- Đọc `script/script.yaml`, `script/outline.yaml`, `explainer/explainer.yaml`, `evidence/ledger.yaml`, và `docs/reference/image-prompting.md`, `docs/reference/motion-vocabulary.md`.
- Nếu có góp ý từ `reviews/script-review-log.yaml` liên quan phân cảnh/nhịp hình, sửa dứt điểm.

## Phán đoán công việc
- Khi cảnh cần điểm nhấn, tham khảo [thư viện Video Shotcraft](https://vincentwei1021.github.io/video-shotcraft/). Dùng `marker-underline-title` để gạch chân từ khóa sau khi chữ đã xuất hiện, hoặc lấy cách dẫn mắt từ `spotlight-sweep-moves` để làm nổi đúng vùng giải phẫu. Dùng thành phần và trường storyboard sẵn có theo quyền của bước.
- Đặt điểm nhấn theo câu đang đọc. Kiểm bố cục ngang và 9:16 để chữ tiếng Việt, phụ đề và chú thích nguồn đều đọc được. Giữ nguyên trục, đơn vị và tỷ lệ khi dùng hiệu ứng trên biểu đồ. Bỏ hiệu ứng nếu làm khó hiểu hình hoặc lời.
- Tách gánh nặng thị giác khỏi `writer`: biến từng dòng lời thoại `script.yaml` thành chuỗi cảnh sinh động, dễ hiểu kiểu Osmosis/Armando Hasudungan.
- **Mở đầu động**: Cảnh hook đầu tiên BẮT BUỘC có chuyển động (`Scene.motion`, `anatomy` có `CUE_ACTIONS`, hoặc `kinetic_term`/`stat_gauge`) — không mở bằng ảnh tĩnh đứng yên.
- **Ngân sách hình ảnh**: giữ tỷ lệ `chart_crop` (`source_card` / `stat_gauge` / `evidence_highlight`) trong `16–24%`, thay đổi hình/nhịp mỗi `<= 6` giây, dùng `>= 4` subject cho video dài (`>= 2` cho clip dọc), không lặp >4 cảnh cơ chế cùng subject + visual liên tiếp.
- **Thành phần SVG**: ưu tiên các component đã đăng ký trong `video/src/anatomy/library.json` (`FOCUS_REGIONS`, `LABELS`, `CUE_ACTIONS`). Nếu cần component mới, tạo `.tsx` + test trong `video/src/anatomy/`, tối đa 6 nhãn tiếng Việt không chồng/cắt.
- **Ảnh FLUX**: `kind: illustration`, `semantic: false`, `rights_required: false`, prompt phẳng sạch tiếng Anh, KHÔNG chữ/số/nhãn trong ảnh; `on_screen_text` chứa số liệu phải gắn `claim_id` và `source_marker` khớp ledger.
- **Cấm giả nguồn**: không tạo SVG/PNG giả chụp tài liệu nghiên cứu; diễn giải ledger luôn dùng `source_card` lấy nguyên metadata từ `evidence/ledger.yaml`.
- Giữ nguyên `script/script.yaml` (không đổi lời đọc hay claim của biên kịch).

## Đầu ra & Lệnh
- Ghi `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`, và `revisions/<rev>/script/clip-plan.yaml` (nếu là `youtube_long`).
- Chạy `healthvideo step storyboard {project} --storyboard <path> --assets <path> [--clip-plan <path>]` tới khi thoát mã `0`.
