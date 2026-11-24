# Bước: Sửa theo người duyệt sản phẩm (`revise_product`)

## Bối cảnh
- Project: `{project}`
- Chủ đề: `{title}`. Câu hỏi chính: `{question}`
- Ghi chú bác sĩ: `{doctor_note}`

## Nhận xét cần sửa
{reject_note}

## Việc cần làm (cùng phạm vi skill pyh-editor)
1. Đọc active_revision, issue_id, ghi chú bác sĩ và reviews/visual-review.yaml hoặc vòng cuối reviews/product-review-log.yaml; mở ảnh tham chiếu và timing hiện hành.
2. Chỉ sửa component R5 hoặc posts đúng path/component và dải dòng edits được giao, trong quyền HARD_RULES hiện hành; giữ nguyên từng byte ngoài dải, kể cả cùng file. Thiếu path/start_line/end_line thì trả coordinator, không tự suy quyền từ mã cảnh. Ngữ cảnh kề chỉ để kiểm ảnh hưởng.
3. Khóa script, ledger/evidence, explainer, outline, storyboard/shot plan, manifest/license-ledger, clip-plan, voice-prep, shorts-plan và profiles; không sửa dù lỗi beat/nhịp/phát âm. Cần file khóa trả coordinator để giao đúng writer/medical_expert/storyboard_director/voice_director/shorts_producer qua mở lại và duyệt lại. Lỗi Python có bất biến trả repair_engineer bằng brief riêng.
4. Đọc docs/reference/image-prompting.md chỉ để đối chiếu quyền nguồn; không sinh FLUX cơ chế, không tự vẽ cơ thể/cơ quan thay hình có phép. Mascot có sẵn chỉ câu chốt, vắng giải phẫu cận. 16:9 không phụ đề cháy chữ; 9:16 giữ phụ đề/highlight đúng timing.
5. Kỷ luật thợ dựng theo spec phong cách 2026-11-17 mục 5: chỉ sửa lỗi đã giao, không thêm motion/bounce để “cho sinh động”. Giữ anchor/chuyển tầng/timing đã khóa, không cross-fade giả zoom. R5 tối đa 2 nhãn cơ chế đồng thời, mỗi nhãn ≤3 đơn vị cách trắng, thuật ngữ dài ghi ngoại lệ.
6. Test component liên quan và posts-check nếu được giao posts phải đạt trong budget; báo file/dải dòng, lệnh/kết quả thật. Không tự render/TTS/nhạc, mở Studio, đổi hash/approval hoặc tự chấm đạt. Python dựng lại và critic độc lập chấm. Cùng issue mở hai lần hoặc hết budget thì dừng trình bác sĩ, không lặp dựng lại bản không đổi.

## Đầu ra và đích trả
Chỉ component/posts đúng edits kèm test liên quan, hoặc brief nêu file khóa/thiếu dữ liệu cho coordinator. Không tạo báo cáo/schema mới. Ghi UTF-8 sạch dấu.

## Xong khi
Các mục trong quyền đã sửa và test liên quan đạt, posts-check đạt nếu đổi posts; phần ngoài quyền trả coordinator có chứng cứ. Không tự đổi trạng thái; Python dựng và product_critic chấm lại trong D4 tối đa 3 lần, không reset budget.

Quyền agent xưởng hiện tại vẫn theo HARD_RULES: chỉ ghi trong project được giao; ngoại lệ duy nhất là thêm SVG mới trong video/src/anatomy/ kèm test. Hợp đồng R5 không cấp quyền sửa component/thư viện dùng chung ngoài phạm vi đó; trả coordinator để lập brief kỹ thuật riêng. Nối hợp đồng R5 vào runner thuộc R5.3.9, gate theo quality_profile: r5_v1; không tự bật hành vi tương lai hoặc đổi revision legacy.
