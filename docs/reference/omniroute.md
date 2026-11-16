# OmniRoute cho agent PYH

`healthvideo xuong --background`, nút bật xưởng trong app và lệnh chạy xưởng trực tiếp
đều kiểm tra OmniRoute trước khi nhận việc. Nếu chưa chạy, xưởng gọi
`omniroute serve --port 20128 --no-open --no-tray` trong tiến trình nền ẩn và chờ
`/api/health`. Dùng lại dịch vụ đang hoạt động, không mở thêm cửa sổ hay dashboard.
Dừng xưởng không tắt OmniRoute vì ứng dụng khác cũng có thể đang dùng dịch vụ này.

Cấu hình tại `profiles/omniroute.yaml`. Khóa inference riêng của xưởng nằm ở
`~/.codex/pyh/omniroute-key`, ngoài repository. Không đưa khóa lên Git hoặc chép token
của tài khoản provider vào cấu hình xưởng. Log khởi động: `cache/omniroute.log`.

Đường `cli: omniroute` dùng Codex CLI làm vòng agent có công cụ, kết nối Responses API
của OmniRoute. Không sửa cấu hình Codex/Claude toàn máy. Khóa chỉ được truyền vào
tiến trình con qua biến môi trường riêng và được che trong log trả về.

Ngày 2026-11-15 đã gọi thật thành công `codex/gpt-6.1-sol`. Một số mục AGY được
`/v1/models` liệt kê nhưng bị live catalog từ chối; chưa bật chúng cho xưởng.
Mỗi model mới phải thử thực tế trước khi thêm vào chuỗi. Không dùng alias `auto/*`
vì cần biết chính xác model của maker để chọn critic độc lập.

Cập nhật 2026-11-16: cả 16 vai ưu tiên OmniRoute bằng tên model cụ thể;
không còn Claude trong tier hoặc override. Không dùng Orchestrator tự chọn model.
Codex trực tiếp nằm cuối chuỗi để dự phòng. Model không tồn tại hoặc không hỗ trợ được
chuyển sang mục tiếp theo ngay và chỉ nghỉ riêng model lỗi trong 10 phút. Quota của đường OmniRoute được ghi riêng
với CLI trực tiếp, còn tính độc lập maker/critic so sánh provider và model thật.
Đổi đường kết nối không cho phép model tự chấm sản phẩm của mình.

OmniRoute có thể phân phối giữa các kết nối được bật trong dashboard providers.
Nhiều đường dùng cùng tài khoản vẫn có thể chung hạn mức; không đảm bảo hết lỗi 429.
Chuỗi CLI trực tiếp và thời gian nghỉ quota hiện hành vẫn được giữ làm dự phòng.

## Kiểm tra trực tiếp ngày 2026-11-16

Đọc catalog `/v1/models` có xác thực và `omniroute providers list --json`.
Các kết nối đang bật: 2 Codex, 2 AGY, 2 Antigravity và 1 DeepSeek, ngoài Claude.
AGY và Antigravity dùng cùng hai tài khoản, không cộng thành bốn hạn mức độc lập.
Muse đang tắt và hết hạn. Không coi các provider chỉ xuất hiện trong catalog là đã kết nối.

Phép thử Responses API yêu cầu model gọi một function với đối số xác định,
không chỉ trả lời văn bản. Thời gian dưới đây là từng lượt ngắn, không phải benchmark
chất lượng hay dự báo thời gian xử lý cả dự án.

| Model | Function call | Nhận ảnh thử | Dùng trong xưởng |
| --- | --- | --- | --- |
| `codex/gpt-6.1-sol` | Đạt, 3,7 giây | Trả lời sai màu ô thử (orange thay vì red) | Viết, phân cảnh, sửa kỹ thuật, điều phối chuyên sâu |
| `codex/gpt-6.1-terra` | Đạt, 1,9 giây | Đạt, nhận đúng ô đỏ | Y khoa, kiểm duyệt kịch bản/sản phẩm, dự phòng |
| `codex/gpt-6-luna` | Đạt, 1,9 giây | Chưa kiểm | Chat nhanh, trinh sát, bài đăng, phân loại ý kiến |
| `agy/gemini-4-hydrogen-medium` | Đạt, 2,3 giây | Đạt, nhận đúng ô đỏ | Nghiên cứu kênh, đạo diễn hình/giọng, Shorts, dự phòng |
| `agy/gemini-3.8-flash-medium` | Đạt, 21 giây | Đạt, nhận đúng ô đỏ | Dự phòng việc nhẹ và các vai cần xem ảnh |
| `antigravity/gemini-3.8-flash-medium` | Đạt, 5,3 giây | Đạt, nhận đúng ô đỏ | Chưa dùng: đọc được file nhưng chưa trả lời cuối khi hết 65 giây |
| `ds-web/deepseek-v4-pro` | Đạt, 2,2 giây | Chưa kiểm | Chưa bật: lượt agent CLI reconnect và hết 65 giây |
| `ds-web/deepseek-v4-flash` | Đạt, 1,9 giây | Chưa kiểm | Chưa bật: lượt agent CLI reconnect và hết 40 giây |
| `agy/gemini-4-carbon-medium` | Hết 40 giây chưa có kết quả | Chưa kiểm | Chưa bật |
| `agy/gemini-4-argon-medium` | Hết 40 giây chưa có kết quả | Chưa kiểm | Chưa bật |

Chỉ dùng đường AGY đã hoàn tất vòng agent thật cho Flash; không
thêm cả hai tên AGY/Antigravity của cùng model vào chuỗi để giả tăng số model độc lập.
Đường Hydrogen đã chạy thành công vòng agent Codex CLI thật: đọc file bằng công cụ,
nhận kết quả và trả lời đúng (19,7 giây). Terra (16,1 giây) và Luna (20 giây) cũng
hoàn tất cùng phép thử. Sol đã có lượt agent sửa sản phẩm thật hoàn tất trên PYH-003.
Flash qua AGY hoàn tất phép thử đọc file và trả lời trong 23,2 giây.
Các lượt thử đọc file chạy trong thư mục tạm, không sửa file dự án.

DeepSeek trả SSE function-call đúng ở phép thử ngắn nhưng chưa chạy được cùng
payload/toolset thật của Codex CLI (lượt đo có khoảng 470 KB, gồm namespace tools).
Chưa xác định nguyên nhân cuối cùng; không đưa vào chuỗi tự động chỉ dựa vào catalog
hoặc phép thử API ngắn. Schema nhận cả `ds-web` và `deepseek-web`, chuẩn hóa cùng
identity để tránh dùng alias vượt điều kiện độc lập khi bổ sung sau này.

Critic khởi đầu bằng Terra, còn writer/storyboard/editor khởi đầu bằng Sol.
Runtime tiếp tục loại model thực sự đã làm sản phẩm khỏi toàn bộ chuỗi critic,
kể cả khi đổi giữa CLI trực tiếp và OmniRoute. Các vai cần xem ảnh chỉ dùng các model
đã qua phép thử ảnh trong đợt này. Hai cổng bác sĩ và PIN không đổi.
