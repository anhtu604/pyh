# M7: vận hành project và phục hồi an toàn

Chạy trong thư mục repo sau khi cài bằng `install/install.ps1`. Thay các giá trị
trong dấu `<...>` bằng đường dẫn/tên thật; dấu ngoặc kép giữ đường dẫn có khoảng
trắng hoạt động trong PowerShell. Lệnh `& .venv\Scripts\healthvideo.exe` dùng
executable của môi trường repo. Không lưu credential vào project hoặc Git.

## 1. Kiểm tra filesystem trước khi chia sẻ một project

```powershell
& .venv\Scripts\healthvideo.exe doctor --project "<project>"
& .venv\Scripts\healthvideo.exe security-audit "<project>"
```

`doctor` phải báo `OK exclusive_create` và `OK atomic_rename`. Hai probe tạo
file tạm duy nhất ngay trong project và chỉ dọn file còn đúng marker của chúng.
Nếu một probe FAIL, không cho hai writer cùng dùng project đó. Probe kiểm hành vi
quan sát được tại thời điểm chạy; nó không chứng minh độ bền sau sự cố của mọi
filesystem mạng. Dùng một thư mục project chung trên filesystem đáp ứng probe;
hai Git clone hoặc Syncthing không tạo thành một lease chung.

## 2. Đọc trạng thái và owner khi project busy

```powershell
& .venv\Scripts\healthvideo.exe operator status "<project>" --json
& .venv\Scripts\healthvideo.exe lease inspect "<project>"
```

Khi writer đang hoạt động, chỉ đọc trạng thái/packet. `lease inspect` cho host,
PID, operation và heartbeat; TTL quá hạn chỉ là tín hiệu cần điều tra, không cấp
quyền lấy lease. Các lệnh ghi tự heartbeat và release khi kết thúc bình thường;
không có lệnh ép release. Sau khi writer kết thúc, chạy `lease inspect` để thấy
`Writer: idle`.

## 3. Phục hồi lease stale

### same-host

Xác nhận tiến trình giữ lease đã dừng. Lệnh dưới đây chỉ phục hồi khi cặp PID và
process-start fingerprint ghi trong lease không còn khớp owner sống; record cũ
được giữ trong `.healthvideo/stale-leases/`.

```powershell
& .venv\Scripts\healthvideo.exe lease recover "<project>"
& .venv\Scripts\healthvideo.exe lease inspect "<project>"
```

### foreign-host

Liên hệ operator của máy kia và xác nhận tiến trình đã dừng, project không còn
writer nào. Chỉ sau đó mới dùng cờ tường minh; TTL một mình không đủ. Nếu không
xác minh được, giữ project read-only và không chạy recovery.

```powershell
& .venv\Scripts\healthvideo.exe lease recover "<project>" --allow-foreign-host
& .venv\Scripts\healthvideo.exe lease inspect "<project>"
```

## 4. Tạo và kiểm backup

```powershell
& .venv\Scripts\healthvideo.exe backup create "<project>" "<backup-root>" --id "<backup-id>"
& .venv\Scripts\healthvideo.exe backup restore "<snapshot>" "<new-project-dir>"
& .venv\Scripts\healthvideo.exe operator status "<new-project-dir>" --json
& .venv\Scripts\healthvideo.exe security-audit "<new-project-dir>"
```

`<snapshot>` là thư mục `<backup-root>/<backup-id>` vừa tạo. Snapshot có
`backup-manifest.json` với path, size và SHA-256. `restore` xác minh manifest,
toàn bộ bytes, layout và binding approval rồi chỉ promote vào **đích mới chưa
tồn tại**. Nó không sửa source, tự migrate, ký lại approval, render hoặc đăng.
Một approval stale vẫn stale sau restore. Giữ snapshot gốc để phục hồi tiếp;
đừng thay thế project đang hoạt động bằng thư mục vừa restore khi chưa kiểm tra.

## 5. Audit trước commit

```powershell
& .venv\Scripts\healthvideo.exe security-audit "<project>"
git status --short
git diff --check
git ls-files
```

Đọc danh sách file tracked/untracked và từ chối commit credential, audio/video,
render, cache, model weights, ảnh trang nguồn hoặc toàn văn có bản quyền. Audit
project chỉ báo rule/path tương đối, không in giá trị secret; nó không thay thế
việc rà staged diff. Gói cuối dừng ở `packaged`. Cổng `medical` và `video` vẫn
do bác sĩ quyết định; **không tự động xuất bản**.

## Khi có lỗi

| Tình huống | Dữ liệu được giữ | Bước an toàn tiếp theo |
| --- | --- | --- |
| `doctor --project` FAIL | Project không đổi; file probe lạ có thể còn nếu cleanup thất bại. | Kiểm tra file `.healthvideo-doctor-*` theo owner, chuyển sang filesystem đáp ứng yêu cầu rồi chạy lại `doctor --project`. Không xóa file không thuộc probe. |
| Project busy | State và artifact chưa bị lệnh bị từ chối thay đổi. | Chạy `operator status` và `lease inspect`; chờ writer xong. |
| same-host lease stale | Record cũ được lưu khi phục hồi thành công. | Xác minh owner đã chết, chạy `lease recover` không cờ foreign-host, rồi `lease inspect`. |
| foreign-host lease stale | Lease vẫn chặn ghi cho tới khi phục hồi tường minh. | Xác minh máy kia đã dừng; nếu không xác minh được, tiếp tục read-only. |
| Backup lỗi/busy | Project nguồn không bị sửa; snapshot hợp lệ không được ghi đè. Staging lỗi có thể còn để chẩn đoán. | Chạy `lease inspect`, sửa nguyên nhân, tạo backup ID mới. |
| Restore lỗi | Snapshot nguyên vẹn; destination hợp lệ không bị ghi đè. Staging lỗi có thể còn. | Kiểm `backup-manifest.json` và thông báo lỗi, dùng destination mới sau khi sửa nguyên nhân. |
| `security-audit` FAIL | Audit chỉ đọc, không sửa project. | Sửa rule được báo, rà Git và chạy audit lại trước commit. |
