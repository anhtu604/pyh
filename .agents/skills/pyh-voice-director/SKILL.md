---
name: pyh-voice-director
description: Use when PYH voice_prep reviews script.yaml before TTS synthesis to standardize Vietnamese medical pronunciations and delivery pacing in script/voice-prep.yaml.
---

## Hợp đồng R5.3.4
Áp dụng spec `2026-11-24-r5-quality-standards-design.md` §2/§3/§6/§8 cho R5; không sửa hồi tố revision/approval đã khóa. Prompt bước thực hiện cùng phạm vi, không mở rộng quyền.
Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.

```yaml
input: Script_hash, voice profile, lexicon/cache và payload từ mới hoặc dòng thay đổi.
output: script/voice-prep.yaml có hash đúng, cách đọc và pacing_notes/mốc cần nghe kiểm.
done_when: Sheet hợp lệ, đúng Anh Tu speed 1.18; chỉ nhận đã nghe khi có mẫu thực.
missing_data_to: medical_expert/bác sĩ xác nhận thuật ngữ; coordinator nhận lỗi thiếu voice, không chọn giọng thay.
```


# Đạo diễn Giọng đọc & Phiên âm PYH (`voice_director`)

## Đầu vào
- Ưu tiên kiểm đường nhanh Python `try_auto_voice_prep` trước khi suy luận: nếu 100% thuật ngữ ứng viên đã có trong từ điển chuẩn `profiles/pronunciation.vi.yaml` (không `needs_doctor_review: true`) hoặc khớp cache hợp lệ, tự động tạo/tái dùng `script/voice-prep.yaml` với 0 token.
- Khi còn từ lạ hoặc mục đang `needs_doctor_review: true`, chỉ nhận payload delta (`new_terms`, `needs_doctor_review_terms`, `changed_lines`) + `script_hash` + `profiles/pronunciation.vi.yaml`; đọc `project.yaml` lấy `active_revision` và `script/script.yaml` nếu cần đối chiếu.
- Giữ và tái dùng cache theo nội dung cần phát âm + hash từ điển (`voice-prep-cache.yaml`) để không dịch lại toàn bộ kịch bản không đổi.

## Phán đoán công việc
- Giữ voice_id Anh Tu `c081d39a-4922-4c88-9615-78bb240337cd`, speed 1.18 (~265 âm tiết/phút mục tiêu); đoạn khó ghi pacing_notes để đồng bộ hình. Thiếu voice thì báo lỗi cho coordinator, không dùng giọng thay. Không sửa profile hay lời để né lỗi.
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

## Thiếu dữ liệu hoặc lỗi
- Chuyển từ/đơn vị chưa rõ kèm line ID cho medical_expert/bác sĩ; thiếu profile/voice/cache hợp lệ báo coordinator. Không nhận đã nghe khi chưa có audio mẫu, không gọi TTS để tự thử ngoài nhiệm vụ.
