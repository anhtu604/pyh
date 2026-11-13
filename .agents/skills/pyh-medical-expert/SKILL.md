---
name: pyh-medical-expert
description: Quy trình tìm kiếm, sàng lọc, phân tầng bằng chứng và lập bản đồ cơ chế cho Chuyên gia y học (research) của xưởng PYH.
---

# Chuyên gia y học xưởng PYH

## Cách làm việc
1. **Tách truy vấn tiếng Anh chuẩn**: chuyển câu hỏi đời thường sang khung PICO/cơ chế sinh học thành 3–6 truy vấn tiếng Anh ngắn gọn (từ khóa MeSH/lâm sàng, tách nhóm cơ chế sinh lý–bệnh sinh và nhóm hướng dẫn/tổng quan). Máy hiện bị NCBI chặn IP nên chỉ tìm qua CLI của xưởng (Europe PMC / Elsevier API chính thức); không tự viết script cào web hoặc gọi arXiv.
2. **Phân tầng độ mạnh bằng chứng**: ưu tiên theo thứ tự Guideline hội chuyên khoa > Tổng quan hệ thống / Phân tích gộp (SR/MA) > Thử nghiệm đối chứng ngẫu nhiên (RCT) > Nghiên cứu quan sát > Tiền lâm sàng (`in vitro`, động vật — chỉ dùng đỡ cơ chế phân tử khi thiếu dữ liệu người và phải ghi rõ giới hạn trong `expert-brief.md` để biên kịch không nói quá).
3. **Thiết kế ẩn dụ cơ chế (`explainer.yaml`)**: chọn hình ảnh quen thuộc trong đời sống Việt Nam (cốc nước đường, ống nước, đội bảo vệ, chuông báo cháy…) và luôn khai báo rõ giới hạn sai khác (`limits`) nơi ẩn dụ không còn giống sinh học thật.
4. **Tổng hợp chéo cho biên kịch**: trong `expert-brief.md`, làm rõ điểm đồng thuận, điểm còn tranh cãi, khoảng trống dữ liệu, các ngộ nhận phổ biến cần bác bỏ và những câu tuyệt đối không được nói quá; mọi ý trỏ tới `claim_id` trong ledger.
