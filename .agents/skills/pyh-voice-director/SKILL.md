---
name: pyh-voice-director
description: Use when PYH voice_prep reviews script.yaml before TTS synthesis to standardize Vietnamese medical pronunciations and delivery pacing in script/voice-prep.yaml.
---

# Đạo diễn Giọng đọc & Phiên âm PYH (`voice_director`)

## Đầu vào
- Ưu tiên kiểm đường nhanh Python `try_auto_voice_prep` trước khi suy luận: nếu 100% thuật ngữ ứng viên đã có trong từ điển chuẩn `profiles/pronunciation.vi.yaml` (không `needs_doctor_review: true`) hoặc khớp cache hợp lệ, tự động tạo/tái dùng `script/voice-prep.yaml` với 0 token.
- Khi còn từ lạ hoặc mục đang `needs_doctor_review: true`, chỉ nhận payload delta (`new_terms`, `needs_doctor_review_terms`, `changed_lines`) + `script_hash` + `profiles/pronunciation.vi.yaml`; đọc `project.yaml` lấy `active_revision` và `script/script.yaml` nếu cần đối chiếu.
- Giữ và tái dùng cache theo nội dung cần phát âm + hash từ điển (`voice-prep-cache.yaml`) để không dịch lại toàn bộ kịch bản không đổi.

## Phán đoán công việc
- Quét từng dòng `text` và `delivery` trong phần cần kiểm tra để phát hiện từ và ký hiệu dễ bị bộ TTS tiếng Việt đọc sai hoặc ngắt gượng. Khi dữ liệu tác vụ xác nhận bộ TTS thực tế (Vibi hoặc VieNeu), dùng kết quả nghe thử của đúng bộ đó nếu có:
  - Từ viết tắt tiếng Anh / y khoa (`HDL`, `LDL`, `HbA1c`, `CT`, `MRI`, `NSAID`, `BMI`, `RNA`, `DNA`).
  - Tên hoạt chất, acid, enzym, vi sinh vật hoặc đơn vị (`uric`, `purin`, `allopurinol`, `mg/dL`, `mmol/L`, `mmHg`, `IU`).
  - Con số ghép ký hiệu có thể đọc nhầm (`30–60 phút`, `< 7%`, `140/90`).
- Số liệu, liều lượng hoặc đơn vị y khoa không rõ cách đọc an toàn thì ghi chú chuyển chuyên gia y học xác nhận, tuyệt đối không tự đoán hay làm tròn số.
- Chỉ thêm các mục CHƯA có trong `profiles/pronunciation.vi.yaml` (hoặc cần cách đọc phù hợp cho riêng bài này). Dùng gạch nối tách âm tiết nhẹ nhàng khi cần (ví dụ `u-ríc`), viết thuần tiếng Việt dễ đọc tự nhiên.
- Không sửa lời thoại gốc `script/script.yaml`, không đổi số liệu y khoa hay claim.
- Nếu có chỗ khó đọc cần lưu ý bác sĩ hoặc `editor` về sau, ghi ngắn gọn ở `pacing_notes`.
- Nếu chưa có mẫu âm thanh, ghi cách đọc là phương án cần kiểm trong QA. Khi có mẫu, đối chiếu tên thuốc, đơn vị, dấu bất đẳng thức, khoảng số và nhịp ngắt với nguyên văn. Chỉ ghi đã nghe những mục thực sự có mẫu để nghe.

## Đầu ra & Lệnh
- Ghi file tạm YAML bằng Python `encoding="utf-8"` (không mất dấu thành `?`) đúng schema `VoicePrepSheet` (`schema_version: "1.0"`, `pronunciations`, `pacing_notes`, `notes`) rồi chạy:
  `healthvideo step voice-prep {project} --file <tmp_voice_prep.yaml>`
- Xong khi lệnh trả mã thoát `0` và `revisions/<rev>/script/voice-prep.yaml` hợp lệ khớp hash kịch bản hiện hành.
