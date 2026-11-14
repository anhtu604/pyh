# Xưởng phục hồi lỗi và nhân viên có hoạt cảnh theo trạng thái thật

Ngày 2026-11-14. Tiếp nối chuẩn agent/model, theo yêu cầu bác sĩ hoàn thiện xưởng
và cho agent hoạt cảnh lúc làm việc, nghỉ phải khác. Không khôi phục pilot.

## Quyết định triển khai

Giữ dashboard isometric hiện có, cải thiện trạng thái và hoạt cảnh trong cùng UI.
Không thay framework, thêm dependency, tách dashboard hay thay cơ chế cổng duyệt.
Đây là lựa chọn kỹ thuật của dev lead theo nhiệm vụ được giao.
Chỉ thêm chuyển động trang trí sẽ giữ false-busy hiện tại; chỉ sửa runtime sẽ chưa
đáp ứng nhu cầu nhìn trạng thái. Vì vậy sửa hai phần đồng bộ, với file sở hữu riêng.

## Nguyên nhân đã kiểm từ code/log

- agents.invoke gọi subprocess.run không deadline; log chỉ có sau khi kết thúc.
- Failover chủ yếu nhận quota/overload, nhiều lỗi kết nối chưa được xử lý thống nhất.
- Agent lỗi có blocked.txt nhưng tick sau vẫn gọi cùng bước, chưa có cap bền vững.
- Exception agent có thể thoát vòng queue trước các chủ đề khác.
- Produce có retry 3 lần/backoff 120/600 và hold validation hiện hữu; cần giữ.
- Render/nhạc/Whisper/contact sheet/local TTS còn subprocess không có deadline.
- Scene máy dựng suy busy từ project.state, activity orphan có thể busy lâu,
  băng chuyền luôn chạy và poll thay innerHTML reset hoạt cảnh mỗi ba giây.
- Xưởng tắt vẫn có chat thật từ dashboard: không thể gate mọi agent theo cờ factory.

Chưa có log xác định CL01 cũ do GPU/OOM; không coi giả thuyết đó là root cause.

## Runtime

### Subprocess hữu hạn

process.run_bounded nhận timeout bắt buộc, trả CompletedProcess như subprocess.run.
Khi timeout, dọn tree do mình tạo, giữ stdout/stderr một phần, raise TimeoutExpired;
không chỉ giết launcher rồi để Node/Chrome/GPU/agent tiếp tục ghi file.
Windows nhận diện process bằng PID + creation token; POSIX dùng process group/session.
Thời hạn production đủ thực tế, có constants và test dùng giới hạn ngắn.
Không thêm retry HTTP Vibi vì provider đã có timeout/retry.

### Agent và queue

AgentResult bổ sung failure_kind mặc định None, giữ caller cũ. Timeout/network/
overload rõ là transient; missing executable/permission là configuration; lỗi
không rõ không được giả làm transient. Quota giữ đường nghỉ/chuyển model riêng.
Mỗi attempt phải có start/end với job_id và process_token, kể cả exception.
Marker giữ hai dòng tương thích cũ và metadata JSON dòng ba nếu cần.

Retry agent riêng với budget produce, theo slug/step/fingerprint đầu vào thật.
Transient tối đa ba attempt với backoff 120/600 qua tick và restart. Validation,
artifact/state-invalid và configuration hold đến khi input thay đổi; không lấy
log/output do chính attempt tạo làm lý do reset budget. Record lỗi fail closed.
Thành công dọn retry. Một chủ đề lỗi không làm mất lượt chủ đề sau.

Factory chờ đúng deadline, không lặp thông báo lỗi không đổi. Chỉ gate thật mời
bác sĩ duyệt; lỗi công cụ chỉ báo lỗi/bước/log và hướng xử lý. Không mở lại cổng,
đổi claim/storyboard hay bỏ QA để vượt lỗi. Sản phẩm, TTS cache và approval hợp lệ giữ nguyên.

### Tín hiệu dựng thật

Khi produce thực sự chạy, runner ghi topics/logs/<slug>/.production-running gồm
pid, process_token, started_at; dọn trong finally. Dashboard xác minh identity để
bật máy dựng, không suy từ trạng thái nội dung.

## UI: chuyển động giải thích công việc

Mode Operate, giữ bảng màu/font và không gian isometric. Nhân viên vẫn ở trạm,
dụng cụ/pose giúp nhận ra công việc. Nhãn chữ luôn nói rõ trạng thái, không dựa
chỉ vào màu hoặc chuyển động.

| Trạng thái | Hình/nhãn | Chuyển động |
| --- | --- | --- |
| Đang làm có chứng cứ | Tay làm việc với dụng cụ theo vai | Viết/gõ, đọc/đối chiếu, so ảnh, timeline, checklist... |
| Nghỉ | Tay rời bàn/ngả nghỉ, dụng cụ ngừng | Không chạy chuyển động công việc |
| Chờ bác sĩ | Hồ sơ chờ tại cổng, nhãn chờ duyệt | Yên, không giả agent xử lý tiếp |
| Chờ model/retry | Lý do và thời điểm thử lại khi có | Pose chờ, không gõ/phân tích giả |
| Lỗi | Ký hiệu và thông báo cụ thể | Dừng công việc, không ăn mừng hay loop làm việc |
| Mất kết nối/chưa xác minh | Nhãn chưa xác minh | Dừng motion công việc cũ |

Không tin orphan start không identity, PID chết hay đã tái sử dụng. Chat thật có
thể làm khi pipeline dừng. Job start/end phải ghép theo job_id khi có; không để
job cùng role kết thúc nhầm job khác. API thêm dữ liệu hiển thị, giữ keys cũ.
Không gán chờ model cho mọi vai chỉ vì một model dự phòng đang nghỉ.

Poll không thay scene khi signature/state không đổi; giữ focus/popover/animation.
Băng chuyền chỉ chạy khi có execution thật. Pause loop khi tab ẩn hoặc scene
offscreen; nút bật/tắt hoạt cảnh nhớ lựa chọn. prefers-reduced-motion dùng pose
tĩnh phân biệt được. Giữ keyboard, màn hình hẹp và không có tràn ngang.

## Phạm vi, kiểm chứng và giới hạn

Brief cache/dev-lead/factory-reliability-animation-brief.md chia ownership A:
process/agent/callers; B: runner/retry/factory; C: dashboard/tests UI; lead: docs/review.
Mỗi sửa file ngoài danh sách phải báo trước. Worker không commit; lead kiểm và squash.
Không push, không bật xưởng, không API/TTS/nhạc/render/pilot thật để test.

Kiểm RED/GREEN: deadline/partial log/descendant cleanup, retry qua tick/restart,
hold validation/corrupt-record, queue isolation và không mời duyệt vì tool error.
HTTP/UI: stopped pipeline và live chat, missing/dead/recycled PID, concurrent job,
máy dựng theo marker, offline và motion preferences. Kiểm browser desktop/mobile/
reduced-motion bằng fixture mô phỏng riêng, ghi rõ fixture, không dữ liệu production.
Chạy regression liên quan, toàn pytest sau khi hợp nhất, Ruff, diff-check.

Không sửa schema nội dung explain-first/thời lượng hay tách writer/dựng trong
đợt này: đó là phần còn lại của R1.4 cần thiết kế và kiểm cổng riêng. Không tuyên bố
hết mọi lỗi sản xuất chỉ vì unit/UI pass.
