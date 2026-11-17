---
name: pyh-storyboard-director
description: Use when PYH storyboard_design designs storyboard.yaml, asset-manifest.yaml, clip-plan.yaml, FLUX prompts, and video/src/anatomy SVG components from an authored script.yaml.
---

# Đạo diễn Phân cảnh & Đồ họa PYH (`storyboard_director`)

## Sửa sau validator
- Chỉ sửa ID cảnh/trường được lỗi chỉ ra, giữ nguyên từng chữ ở phần đã đạt.
  Không thiết kế lại toàn bộ storyboard hay thay script/timing để tránh lỗi.
- Kiểm toàn bộ bất biến schema/hash/timing vẫn bắt buộc. Nếu lỗi toàn cục
  chưa xác định phạm vi, báo cần xác định vị trí trước, không tự nhận toàn bài.

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

## Mascot thương hiệu theo nhịp cảnh
- Hook dùng `welcome`, `surprised` hoặc `thinking` theo lời mở; đính chính niềm tin sai dùng `myth_bust`; cảnh báo dấu hiệu nguy hiểm dùng `caution`; tóm ý/chuyển chương dùng `point_up` hoặc `explain`; kết + CTA và `brand_outro` dùng `thumbs_up` hoặc `welcome`, giữ logo thương hiệu.
- Gợi ý 4–8 lần cho video dài, ≤1 lần mỗi clip dọc; điều chỉnh theo nội dung, không ép đủ số. CTA clip tự thêm đã có mascot `welcome`, nên ưu tiên không thêm mascot trong các cảnh cắt khi CTA này đủ nhận diện.
- Không che vùng giải phẫu, biểu đồ, phụ đề hay thẻ nguồn; kiểm cả 16:9 và 9:16. Bỏ mascot ở cảnh cơ chế chính nếu làm rối. Mascot chỉ phản ứng, không nói claim y khoa mới; không chữ/số trên ảnh, `blank_board` chỉ là khung trống. Chữ riêng bằng Remotion vẫn phải tuân thủ claim/nguồn hiện hành.
- Đọc `profiles/brand.vi.yaml`: chọn `mascot.artwork[pose].path`, kiểm SHA-256 khớp `mascot.artwork[pose].sha256`, chép nguyên PNG vào revision, ví dụ `assets/brand/welcome.png`. Không sửa brand/ảnh hay tự sinh lại mascot. Chỉ khai báo tham chiếu không tự chép ảnh hoặc tạo manifest.
- Scene ghi `visual_assets: [{path: assets/brand/welcome.png, role: mascot, pose: welcome}]`; không dùng `asset_id`. Path tương đối POSIX từ gốc revision, phải trùng path trong manifest.
- Manifest: `path: assets/brand/welcome.png`, `kind: mascot_reaction`, `semantic: false`, `storyboard_role: mascot`, `sha256` đúng byte/brand, `source: repository:assets/brand/mascot/welcome.png`, `creator` và `license` chép nguyên `brand.assets`, `revision` hiện hành, `rights_required: false` (artwork nội bộ có provenance, không phải crop nguồn cần xin quyền). Không bịa giấy phép.
- Khi dùng Python helper có sẵn `workflows.visual_assets.create_mascot_reaction_asset(project_dir, scene_id=..., asset_name=..., pose=MascotPose.WELCOME)`: helper dùng alias `assets/<asset_name>.png`, tự gắn scene ref, manifest và license-ledger (`source: built_in:pyh-mascot`, `rights_required: true`, entry có `rights_basis`, license/creator từ brand và SHA thực). Chỉ dùng ở draft trước duyệt; không sửa dữ liệu đã khóa. Hai cách đăng ký đều cần validate lại bằng CLI.
- Kiểm `reviews/style-lint.json`: `mascot_missing` nhắc video dài chưa có mascot; `mascot_dense_scene` nhắc mascot cùng anatomy/chart/nguồn. Đây là cảnh báo `warn`, không xác nhận ảnh chồng nhau và không chặn bước; đạo diễn phải xem bố cục thực tế. Gói đã duyệt muốn đổi mascot phải đi luồng mở lại cổng hiện hành và bác sĩ duyệt lại, không chỉnh trực tiếp revision khóa.

## Đầu ra & Lệnh
- Ghi `revisions/<rev>/storyboard/storyboard.yaml`, `revisions/<rev>/assets/asset-manifest.yaml`, và `revisions/<rev>/script/clip-plan.yaml` (nếu là `youtube_long`).
- Chạy `healthvideo step storyboard {project} --storyboard <path> --assets <path> [--clip-plan <path>]` tới khi thoát mã `0`.
