---
name: pyh-copywriter
description: Quy trình viết tiêu đề, mô tả, caption clip ngắn, bài cộng đồng và prompt nền thumbnail cho Viết bài đăng (posts).
---

# Viết bài đăng xưởng PYH

## Chắt lọc từ `social`
- Chỉ áp dụng kỹ thuật viết hook mở đầu, tách nội dung thành caption độc lập cho clip ngắn và bộ lọc *No AI Tells* (tránh broetry mỗi câu một dòng, "Không phải X mà là Y", rải emoji đầu dòng, câu mồi tương tác rỗng).
- **Bỏ qua** toàn bộ phần kết nối MCP đặt lịch tự động (Typefully/Buffer/Marky) và quy trình bình luận/nhắn tin B2B.

## Cách làm việc cho `posts.yaml`
1. **`youtube_titles`**: kết hợp 1 tiêu đề bám từ khóa người bệnh hay tìm và 1–2 tiêu đề đánh vào hiểu lầm đời thường trong bài; gợi tò mò đúng cơ chế đã duyệt, không giật tít dọa dẫm hay hứa chữa khỏi.
2. **`clip_captions` (`tiktok`/`shorts`/`reels`)**: mỗi clip phải tự đứng vững cho người chưa xem video dài, mở bằng câu chạm vấn đề ngay dòng đầu và giữ nguyên ý giới hạn an toàn (caveat) của clip đó.
3. **`facebook_post` & `youtube_community`**: giọng chia sẻ gần gũi, dễ hiểu cho người đọc phổ thông; kết bằng câu hỏi gợi suy ngẫm hoặc nhắc lưu thông tin mang đi khám.
4. **`thumbnail`**: `headline` ngắn gọn đọc rõ trên điện thoại; `background_prompt` tả minh họa phẳng 2D theo phong cách kênh, đặt chủ thể lệch phải để chừa khoảng thoáng bên trái cho Remotion vẽ chữ/logo, tuyệt đối không mô tả chữ, số hay ký hiệu chữ trong ảnh nền.
