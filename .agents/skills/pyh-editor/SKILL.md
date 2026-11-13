---
name: pyh-editor
description: Hướng dẫn chỉnh sửa SVG và motion Remotion đúng kiến trúc repo video/ cho Thợ dựng (revise_production, revise_product).
---

# Thợ dựng xưởng PYH

## Ghi đè skill `remotion-best-practices` & `motion-design`
- Xưởng chạy tự động không giao diện trên Windows: **tuyệt đối không** chạy `npx remotion studio` hay `npx remotion render` (làm treo pipe); Python sẽ tự dựng lại video sau khi bạn sửa xong.
- Không tìm `timeline.json` hay `src/lib.ts` của `motion-design`. Kiến trúc thật nằm trong `video/src/anatomy/` (khai báo `FOCUS_REGIONS`, `LABELS`, `CUE_ACTIONS`, đăng ký ở `library.json` và `registry.ts`) cùng 14 thẻ chuyển động và bảng màu trong `docs/reference/motion-vocabulary.md` (nền kem ấm `#F7F4EC`/`#FFFDF7`, chữ `#12304A`, nhấn `#18A6A6`/`#F4B942`, cảnh báo viêm `#D8574B`).

## Cách làm việc khi sửa SVG
1. Đọc contact sheet / `reviews/visual-review.yaml` hoặc nhận xét lỗi để xác định đúng nhãn bị cắt, chồng lấn hoặc sai tỷ lệ khung.
2. Giữ sơ đồ phẳng tiếng Việt dùng font `Be Vietnam Pro`, tối đa 6 nhãn có leader line rõ hướng, chừa biên an toàn tối thiểu ~60px quanh mép khung và phía trên vùng phụ đề.
3. Mọi chuyển động phải tính thuần từ `frame` với đường cong giảm tốc mượt (không `linear` khi dừng, không `Math.random()` hay `Date`).
4. Sau khi sửa component trong `video/src/anatomy/`, cập nhật và chạy unit test của component đó để xác nhận.
