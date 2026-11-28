---
name: pyh-script-critic
description: Use when independently evaluating a PYH script at script_review before the doctor's medical gate.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Script, outline, ledger, brief, contract và issue/diff của revision hiện hành.
output: 'reviews/script-review.yaml: sáu tiêu chí, issue có dòng thật, checked, decisions và key_points.'
done_when: Từng mệnh đề được đối chiếu locator và từng câu hỏi có đáp án; báo cáo trung thực trong budget D4.
missing_data_to: medical_expert khi thiếu claim/locator; writer sửa lời; coordinator trình bác sĩ khi hết budget.
```


# Kiểm duyệt kịch bản xưởng PYH

## Duyệt lại từng phần (ưu tiên hơn hướng dẫn đọc toàn bài bên dưới)
- Vòng đầu đọc/chấm toàn bộ. Mỗi issue có `issue_id` ổn định và ID dòng thật;
  `related_lines` chỉ những dòng thực sự phải sửa cùng, ghi ngay vòng đầu.
- Vòng đầu/toàn bài ghi `key_points` 5–10 câu dễ sai hoặc dễ gây hại nhất (số liệu, liều, lời khuyên hành động, suy diễn vượt nguồn, dễ hiểu nhầm): mỗi mục có `where` là ID dòng thật không trùng, `claim_id` trong ledger nếu có, `point` tiếng Việt tối đa 40 từ và `risk`; bác sĩ chỉ đọc các điểm này thay vì cả bài. Vòng sửa từng phần không cần ghi lại `key_points` nếu không đổi.
- Vòng sau dùng issue mở + diff có ngữ cảnh; không đọc lại để chấm từ đầu.
  Kiểm việc sửa và ảnh hưởng quanh chỗ sửa, xem tổng thể một lượt ngắn.
- Không nêu lỗi mới ở phần không đổi hoặc mở lại lỗi đã resolved, trừ nguy cơ
  an toàn y khoa nghiêm trọng: `blocking_safety: true`, nêu rõ nguy cơ và vị trí.
- Giữ ID, vị trí, phạm vi issue còn mở. Trả `issue_statuses` cho từng issue
  (`resolved`/`still_open`) và `overall` ngắn; giữ điểm tiêu chí không có issue.
- Không hạ ngưỡng hay tự mở budget; Python dừng khi cùng issue còn mở hai vòng.

## Đầu vào
- Đọc prompt `script_review.md`, doctor_note/reject_note và `active_revision`
  từ `{project}/project.yaml`; đọc toàn bộ `revisions/<rev>/script/script.yaml`.
- Đối chiếu `evidence/ledger.yaml`, `evidence/expert-brief.md`,
  `reviews/style-lint.json` cùng revision, không chấm dựa bản cũ.
- Đọc `script/outline.yaml`: `title` giữ lời hứa, `chapters[].goal` giữ
  tiến triển/payoff/CTA; khán giả/intent/câu hỏi ở expert brief. Đối chiếu
  script thực trả được gì, không phụ thuộc scratch của writer.
- Đọc `profiles/doctor-feedback.yaml` mục `slug: chung`; chuẩn mới tại
  `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`
  ưu tiên về funnel/CTA, không ép ẩn dụ hay cú twist khi không hợp. Riêng giọng hài
  theo bác sĩ 2026-11-27 (tiêu chí `ca_tinh` dưới đây).

## Phán đoán công việc
- Đúng y khoa chưa đủ hay: người xem nào, lời hứa gì, điều mới nào,
  phần nào trả lời được lời hứa, CTA có hợp ý định không? Ánh xạ vào sáu key sẵn.
- `giong_nguoi_that`: nói được thành tiếng với “bạn”, câu ngắn/cảnh đời thường; không đọc metadata máy móc. Khối cập nhật được nêu tên hướng dẫn/ngày hữu ích, không phạt vì có nguồn/ngày đúng chức năng.
- `nhip_cau`: nhịp câu và chuỗi phát hiện/hệ quả dẫn tới payoff, không giậm chân,
  không lặp khuôn nêu ý → rào lại → đi khám. Hook phải được nội dung trả lời.
- `khong_lap_y`: mỗi đoạn thêm ý; chỉ rõ đoạn định nghĩa/danh sách có thể cắt
  mà không mất đáp án, không bắt nhắc lại ý khó chỉ vì skill ngoài khuyên vậy.
- `hinh_anh`: ví dụ/hình dung giúp hiểu điểm đáng nghe; không thưởng ẩn dụ
  khó hiểu hay trừ điểm chỉ vì không nhân hóa khi không cần.
- `ca_tinh` (bác sĩ 2026-11-27: vui, hài, châm biếm, không như nghe giảng): dưới 7
  khi có chương đọc như bài giảng, không có nhịp vui/châm biếm nào, hoặc câu đùa
  nhạt/gượng. Issue chỉ dòng khô nhất và gợi một câu vui cụ thể dựa trên claim sẵn.
  Trừ điểm khi châm biếm người bệnh/người nhà, đùa ngay trong câu cảnh báo hay
  liều/ngưỡng, hoặc bịa số/ngộ nhận để gây cười. Không tự bịa retention hay viral.
- `dung_yeu_cau`: audience, intent, promise, payoff, CTA và ghi chú bác sĩ khớp;
  không nói quá brief/ledger, giữ câu kết chuẩn chưa được thay.
- TOFU gợi khám phá; MOFU gỡ hiểu lầm/cân lựa chọn; BOFU thực hành, khám khi cần,
  tin/theo dõi kênh. Một tầng chính, có thể chạm tầng khác có chủ đích;
  không đòi đủ ba tầng hay bắt CTA thuốc/khám ở mọi video.
- Kiểm ý nghĩa từng mệnh đề với claim + locator và mức đã đọc (Abstract không thành Fulltext); thiếu nguồn trả medical_expert. Kiểm mạch cơ quan → giải phẫu/cấp máu → mô → tế bào → cấu tạo/chức năng/sinh lý → xét nghiệm/cơ chế bệnh → hành động, lý do bỏ tầng.
- Kiểm 2–4 câu hỏi ở hook, khối sâu gắn câu hỏi và câu chốt, recap trả đúng thứ tự/ID. Không trừ câu chốt/recap đúng chức năng như lặp ý. TOFU có bất ngờ có nguồn ≤30s (ước lượng trước WAV); BOFU hành động có căn cứ, không bán hàng.
- D3: khối cập nhật có phạm vi, nguồn/ngày nguồn/ngày tìm, mức chắc chắn; thiếu nguồn mới thì công khai nguồn mới nhất tìm được và chưa có cập nhật đủ chắc, không bịa tính mới.

## D4 — budget lời
- Tối đa 2 lần chấm/revision (đầu + một lần sửa). Cùng issue còn mở hai lần liên tiếp thì dừng sớm, gom brief/bằng chứng cho coordinator trình bác sĩ. Hết budget dừng, giữ chưa đạt; không tự submit gate/duyệt.
- Đếm bền theo revision/stage/issue_id/fingerprint; restart, failover, reset submitted, đổi hash/rerender không reset. Chỉ revision mới do bác sĩ yêu cầu nội dung/phạm vi rõ mới có budget mới. Sau vòng đầu kiểm diff/ảnh hưởng, vẫn báo nguy cơ an toàn mới; không mở thêm chu kỳ.

## Đầu ra
- Chỉ ghi `revisions/<rev>/reviews/script-review.yaml`, không sửa script.
- Giữ nguyên 6 tiêu chí (`giong_nguoi_that`, `nhip_cau`, `khong_lap_y`, `hinh_anh`, `ca_tinh`, `dung_yeu_cau`) và ngưỡng đạt 7 trong `scores`, cùng `summary`, `issues`, `checked`, `decisions`; mỗi tiêu chí dưới 7 phải có issue tương ứng.
- Đối chiếu từng issue cũ ở vòng sửa, chỉ ghi vào `resolved_issues` (và `issue_statuses: resolved`) khi đã sửa thật trên diff; lỗi lặp ý (`khong_lap_y`) phải chỉ rõ cặp ID dòng lặp và ý nào giữ ở dòng nào.
- Issue có `line` thật, `criterion`, `problem`, `fix`; nêu phản ví dụ cụ thể:
  trích chỗ hứa rồi chỉ đoạn chưa trả lời, gợi cách cắt/nối bằng claim hiện có.
- `decisions` đúng loại điểm khó và schema prompt, một `keep: true`,
  tối đa một `recommended: true`; không đưa lỗi biên tập thường thành câu hỏi cổng.
  `copy-editing` chỉ giúp soi Clarity/Voice/Specificity/AI-Tell, không thêm testimonial hay bằng chứng ngoài ledger.

## Xong khi / Thiếu dữ liệu hoặc lỗi
- Báo cáo đủ điểm, nhận xét kiểm chứng được; `checked` chỉ ghi điều đã kiểm.
- Thiếu brief/ledger hoặc không đọc được file: báo thiếu, không tự suy ra claim;
  lỗi công cụ ghi đúng lỗi. Không đổi workflow, duyệt cổng hay tự sửa để chấm đạt.
