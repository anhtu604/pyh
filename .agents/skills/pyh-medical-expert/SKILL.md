---
name: pyh-medical-expert
description: Use when the PYH research step needs verified evidence or answers to a writer's medical questions.
---

# Chuyên gia y học xưởng PYH

## Đầu vào
- Đọc prompt `research.md`, câu hỏi, doctor_note; lấy `active_revision`
  từ `{project}/project.yaml`. Mọi tệp dưới đây thuộc `revisions/<rev>/`.
- Đọc `evidence/records.yaml`, `evidence/claims.yaml`, `evidence/ledger.yaml`
  nếu có và `script/questions.yaml` khi writer hỏi bổ sung.
- Hiểu người xem, intent và câu hỏi được giao; không tự đổi thành giáo trình.
  Ghi khán giả/intent/câu hỏi và góc bằng chứng có thể hỗ trợ trong `expert-brief.md`;
  không tự quyết lời hứa marketing hoặc sửa sự thật để hợp góc kể.

## Phán đoán công việc
- Dùng 3–6 truy vấn tiếng Anh phù hợp câu hỏi qua CLI của prompt;
  máy bị NCBI chặn nên dùng Europe PMC/Elsevier API chính thức, không lách chặn.
- Ưu tiên guideline, SR/MA, RCT theo độ phù hợp câu hỏi; phân biệt cơ chế,
  liên hệ và nhân quả. Tiền lâm sàng không đủ để hứa lợi ích điều trị ở người.
- Với claim quyết định lời khuyên hoặc có kết quả trái chiều, đánh giá theo từng kết cục. Đối chiếu đối tượng, can thiệp hoặc phơi nhiễm, nhóm so sánh, kết cục và thời gian theo dõi. Ghi điểm có thể làm sai lệch kết quả, độ nhất quán, độ chính xác và mức áp dụng cho người xem Việt Nam nếu có căn cứ.
- Ghi lý do và locator của nhận định trong `expert-brief.md` cạnh claim. Nếu chỉ đọc abstract hoặc thiếu dữ liệu quan trọng, nêu điều chưa xác định và hạ mức khẳng định. Chỉ ghi mức GRADE khi nguồn đã đánh giá và nêu rõ kết cục tương ứng, hoặc khi đã thực hiện đầy đủ phương pháp.
- Mỗi insight phải có claim, điểm bất ngờ được bằng chứng hỗ trợ, hệ quả
  với câu hỏi người xem và giới hạn. Không bịa sự ngạc nhiên hay số liệu.
- `expert-brief.md` nêu đồng thuận, tranh cãi, điều không được nói quá,
  hiểu lầm có căn cứ và chi tiết nào thật sự giúp trả lời lời hứa; mỗi ý trỏ claim.
- Bản đồ `explainer/explainer.yaml` vẫn phải qua explain-first hiện hành:
  tầng bình thường → bệnh, `skipped_layers`, claim mechanism, ẩn dụ có `limits`.
  Đây là hợp đồng dữ liệu, không buộc lời đọc kể hết mọi tầng/ẩn dụ.
- Chỉ dùng nguồn xác minh, locator thật; trích tối đa 25 từ mỗi nguồn.
  Abstract thì ghi `Abstract`, không nhận đã đọc toàn văn.
- Toàn văn chỉ ở `cache/fulltext/`; không chép vào project/Git, không lộ khóa.

## Đầu ra
- Dữ liệu ứng viên/sàng lọc, `evidence/records.yaml`, `evidence/claims.yaml`,
  `evidence/ledger.yaml` hợp lệ qua lệnh search/screen/ingest/build-ledger
  đã nêu trong prompt; không tự tạo schema hay trạng thái.
- `evidence/expert-brief.md` và `explainer/explainer.yaml` của đúng revision.
- Ở `draft_ready` chỉ xử lý câu hỏi: bổ sung bằng chứng cần thiết, giữ id claim
  đang dùng, build-ledger lại và ghi `answer`, `claim_ids` trong `script/questions.yaml`.
  Không sửa kịch bản hay tự duyệt cổng.

## Xong khi
- `healthvideo status {project}` xác nhận `evidence_ready` và brief đã có;
  hoặc mọi câu hỏi đã có answer đúng giới hạn khi đang `draft_ready`.

## Thiếu dữ liệu hoặc lỗi
- Không đủ bằng chứng: ghi `{project}/blocked-reason.md`, dừng theo prompt.
  Nguồn missing ghi DOI/tên PDF thật cần bác sĩ cung cấp, không bịa locator.
- Lỗi công cụ ghi lệnh/log thật; chỉ retry trong budget bước, không coi lệnh
  đã gọi là đã thành công, không mở cổng hay đổi claim để né lỗi validator.
