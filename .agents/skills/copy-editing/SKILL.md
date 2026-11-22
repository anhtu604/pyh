---
name: copy-editing
description: Edit, review, or improve existing Vietnamese health scripts and channel copy for clarity, natural spoken voice, specificity, and zero AI tells.
metadata:
  version: 2.2.1
---

# Copy Editing (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- **Không** bổ sung proof/testimonial, case study khách hàng, bảo đảm kết quả hay tăng mức khẳng định y khoa ngoài `evidence/ledger.yaml` đã duyệt.
- **Bỏ** các pass SaaS/sales landing page (Sweep 4 Prove It / Sweep 7 Zero Risk / Expert Panel Scoring). Nếu phát hiện claim thiếu căn cứ hoặc khẳng định quá mức, trả về cho `medical_expert` / `writer` xử lý.
- Với vòng sửa từng phần (`revise_product` / `revise_medical` / `draft`), chỉ sửa đúng dòng/phạm vi được giao.

## Focused Editing Passes

### Clarity
- Ensure every sentence has one clear idea and reads cleanly on first listen.
- Cut buried points, ambiguous pronoun references, and unexplained jargon.
- Replace abstract phrasing with concrete everyday mechanisms.

### Voice and Tone
- Read aloud mentally: keep natural Vietnamese spoken rhythm, alternating short and medium sentences.
- Remove textbook/lecturing stiffness and sudden shifts between casual and corporate wording.
- Preserve the channel's warm, grounded, empathetic tone; never mock patients.

### Specificity
- Prefer concrete mechanisms, exact conditions, and real scope over vague intensifiers ("rất tốt", "tối ưu", "hiệu quả vượt trội").
- Keep numbers and clinical limits strictly tied to approved `[claim:<id>]` entries—never invent numbers to sound specific.

## Quick-Pass Word & Sentence Checks

- Cut weak fillers (`thực sự`, `về cơ bản`, `cực kỳ`, `một cách tối ưu`) when they add no meaning.
- Prefer active, direct Vietnamese phrasing; keep one topic per paragraph and ≤ 32 words per spoken sentence.

### AI-Tell Check

Remove patterns that make Vietnamese scripts or posts sound generated:
- **Contrast reveals**: "Không phải X, mà là Y" / "It's not X, it's Y" — state Y directly with its reason.
- **Negation lists**: "Không X, không Y, không Z" — state what actually happens.
- **Trailing pile-ons**: a complete claim followed by tacked-on summary clauses — end the sentence cleanly.
- **Self-answered rhetorical filler**: "Kết quả là gì? ..." / "Điều thú vị là:" — go straight to the point.
- **Stock clickbait phrases**: "bí mật ít ai biết", "hãy cùng tìm hiểu", "trong thế giới hiện đại ngày nay".
