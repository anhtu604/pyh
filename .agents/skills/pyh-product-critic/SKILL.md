---
name: pyh-product-critic
description: Use when PYH product_review independently evaluates the final video and posts before the doctor's video gate.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: MP4 thực, quality report/timing, script/ledger/contract, posts và clip xuất thực.
output: 'reviews/product-review.yaml: bảy tiêu chí, timestamp/issue_id/edits và checked trung thực.'
done_when: Xem diễn hành/chuyển tầng và nghe phần cần kiểm khi có công cụ; báo thiếu nếu chưa xem/nghe, D4 tối đa ba lần.
missing_data_to: editor chỉ sửa component/dải dòng; medical_expert/writer xử lý nội dung; coordinator/bác sĩ khi thiếu MP4/âm thanh hoặc hết budget.
```


# Kiểm định sản phẩm xưởng PYH

## Duyệt lại từng phần (ưu tiên hơn việc đọc toàn bộ bên dưới)
- Vòng đầu kiểm toàn bộ, mỗi issue có `issue_id` ổn định, `at` thật.
  Lỗi sửa được phải có `edits` gồm path tương đối repo, start_line/end_line chính xác.
- Vòng sau chỉ nhận issue mở + diff nguồn; lấy contact sheet hiện hành, kiểm cảnh
  có issue và ngữ cảnh kề, xem tổng thể ngắn. Không suy diễn hình từ source diff.
- Giữ điểm tiêu chí không có issue, ID/vị trí/edits lỗi còn mở. Trả `issue_statuses`
  (`resolved`/`still_open`) cho từng ID và `overall` ngắn. Không mở lại lỗi resolved.
- Chỉ nêu lỗi mới ở phần không đổi khi có nguy cơ y khoa nghiêm trọng,
  ghi `blocking_safety: true` cùng lý do. Không hạ ngưỡng hoặc vượt cổng.

## Đầu vào
- Tự thực hiện lượt kiểm định, chờ các lệnh hoàn tất trước khi ghi báo cáo. Không mở tác vụ nền hay giao agent con cho bước này.
- Đọc prompt `product_review.md`, lấy `active_revision` từ `{project}/project.yaml`.
  Mọi sản phẩm dưới đây thuộc `revisions/<rev>/`.
- Chạy `healthvideo step review-frames {project} --every 4` theo prompt;
  đọc `index.json` và `hook-transitions/index.json` trong thư mục lệnh trả về,
  mở từng contact sheet định kỳ lẫn khung quanh hook (0–3 s) và chuyển cảnh giữa các scene.
- Đối chiếu `script/script.yaml`, `storyboard/storyboard.yaml`,
  `renders/scene-timing.json`, `reviews/video-qa.json`, `posts/posts.yaml` và chuẩn phong cách
  `docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md`.
- Đọc `profiles/pronunciation.vi.yaml`; không mở Playwright/trình duyệt
  hay chạy script ngoài theo `character-animation-qa`.

## Phán đoán công việc
- `hinh_khop_loi`: hình/nhãn/cơ chế đúng câu ở đúng cảnh và thời điểm.
- `hinh_ro`: đọc được trên khung nhỏ, không chồng/cắt, đủ khoảng thở.
- `nhip_dung`: điểm nhấn đến đúng câu và giúp hiểu, không đòi hiệu ứng máy móc;
  đoạn giữ hình lâu là dấu hiệu cần xem trong ngữ cảnh, không tiêu chí duy nhất.
  R5 dùng D2: story median 2,5–3,5s/P90 ≤8s; mechanism median 8–20s, bước nhân quả mỗi 3–6s; shot >20s cần lý do và ≥3 bước. Không áp trần shot 6s cũ lên cơ chế R5.
- `am_thanh_phu_de`: dựa QA và từ điển; thuật ngữ thiếu phiên âm là nguy cơ,
  không khẳng định đã nghe sai. Contact sheet chỉ xác nhận hình;
  không nhận đã nghe giọng/nhạc hoặc kiểm được toàn bộ chuyển động giữa khung lấy mẫu.
- `mo_ket`: hook và payoff khớp lời hứa; kết nhận diện rõ, CTA theo intent chính.
  TOFU khám phá, MOFU cân hiểu/lựa chọn, BOFU thực hành/khám khi cần/theo dõi;
  không yêu cầu mọi video có đủ ba tầng hay nhắc thuốc.
- `bai_dang`: title/thumbnail/caption hứa đúng phần video trả lời, không hù dọa,
  clickbait, hứa chữa khỏi hoặc thêm claim chưa duyệt.
- `dung_phong_cach_pyh`: chấm theo spec `2026-11-17-pyh-style-a-mascot-host.md` trên contact sheet
  định kỳ + `hook-transitions/` (hook 0–3 s và chuyển cảnh): màu `off_white/navy/teal/yellow/night`
  ≤ 3 màu nổi không đỏ báo động; chữ Be Vietnam Pro đọc rõ 720p; mascot đúng 9 tư thế và đúng nghĩa;
  sơ đồ dựng dần từng beat và zoom kính lúp (không cross-fade chồng mờ); 16:9 không cháy cứng phụ đề;
  9:16 giữ phụ đề trong vùng an toàn (tránh 15% đỉnh, 22% đáy, cột nút phải) và không đè nhãn/mascot/nguồn.
  Kiểm contact sheet clip xuất thực để xác nhận bố cục 9:16, không nhận `safe_zone_checked: true` là bằng chứng.

## Đầu ra
- Chỉ ghi `revisions/<rev>/reviews/product-review.yaml`, không sửa/render.
- Giữ đủ bảy key `scores` trên (gồm `dung_phong_cach_pyh`), `summary`, `issues`, `checked`, `decisions`;
  điểm 1–10, dưới 7 phải có issue với `at`, `criterion`, `problem`, `fix`, `fixable`.
- `fixable: true` chỉ nếu sửa trọn bằng component R5 hoặc posts đúng path/dải dòng `edits` và trong quyền HARD_RULES hiện hành. Component dùng chung ngoài project cần sửa thì false, trả coordinator lập brief kỹ thuật riêng; không suy quyền sửa từ fixable. Cần đổi script/storyboard/manifest/clip-plan/voice-prep/shot plan/shorts-plan/nguồn/profiles khóa thì false và trả coordinator; không coi mọi lỗi hình/âm thanh đều sửa được. `blocking_safety` dành cho nguy cơ an toàn có bằng chứng.
- `decisions` đúng loại và schema prompt: một `keep: true`, tối đa một
  `recommended: true`, mọi phương án bám ledger; lỗi thường ở `issues`.
- `checked` chỉ ghi phép kiểm đã thực hiện; trong `summary` tách rõ quan sát từ contact sheet,
  dữ liệu QA (`video-qa.json`/`pronunciation-qa.json`) và phần chưa nghe/xem. Phải xem MP4 diễn hành tại mọi chuyển tầng/câu chốt và mẫu 5s lấy đều, kiểm 6 khung phân bố đều ở 720p; nghe đoạn thuật ngữ/ASR lệch khi có công cụ. Thiếu công cụ/audio thì báo chưa kiểm cho coordinator/bác sĩ, không kết luận đạt âm thanh từ tỷ lệ ASR hay ảnh.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Báo cáo đủ bảy tiêu chí với vị trí và hướng sửa cụ thể, không tự duyệt cổng.
- Thiếu contact sheet/QA/timing: chỉ rõ phần chưa kiểm, không chấm như đã xem đủ.
  Lỗi công cụ ghi log thật, retry đúng budget prompt; không sửa trạng thái/hash
  hoặc giả bước lấy khung hình lỗi đã thành công.

## R5 — hợp đồng và D4 sản phẩm
- Kiểm MP4 thực trả đúng 2–4 câu hỏi theo thứ tự/ID, khối sâu/câu chốt/cập nhật có nguồn/ngày/giới hạn D3; TOFU bất ngờ có nguồn ≤30s theo WAV, BOFU hành động có căn cứ, không bán hàng. Không dùng đếm từ khóa để chứng nhận đúng y khoa.
- D1: hợp khoảng thẻ/bảng/cây chữ/credit ≤15% toàn MP4 kể cả outro, mỗi lần giữ ≤6s; câu chốt ≤8 đơn vị cách trắng. Quality report cần frame intervals, median/P90 từng nhóm story/mechanism, nhóm trống N/A. Đổi nhãn/hạt nền/caption không tạo shot/beat nhân quả. Kiểm hình có phép/provenance, không FLUX cơ chế; mascot chỉ ở câu chốt, vắng giải phẫu cận.
- D4 tối đa 3 lần chấm/revision (đầu + hai lần sửa); cùng issue còn mở hai lần liên tiếp dừng sớm. Hết budget dừng, giữ chưa đạt, trình brief/bằng chứng qua coordinator cho bác sĩ, không tự submit gate.
- Budget bền revision/stage/issue_id/fingerprint, không reset khi restart/failover/reset submitted/đổi hash/rerender. Chỉ revision mới do bác sĩ yêu cầu rõ nội dung/phạm vi mới có budget mới; không tự tạo revision. Sau vòng đầu kiểm diff/ảnh hưởng, vẫn báo nguy cơ an toàn mới. Giữ độc lập editor cả model fallback/session; không gộp ba khâu chấm.
