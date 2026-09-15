# M7 — Hardening vận hành và phục hồi

**Ngày:** 15-09-2026  
**Trạng thái:** Đề xuất; chờ C2C review độc lập trước implementation

## 1. Mục tiêu và ranh giới

M7 làm cứng workflow `/pyh` đã hoàn tất M1–M6.6 để hai tiến trình không cùng
ghi một project, backup/restore giữ nguyên bytes và trạng thái duyệt, kiểm thử E2E
chạy qua ranh giới tiến trình, và operator có lệnh audit cùng runbook phục hồi.
M7 không thay đổi nội dung y khoa, provider, TTS, Remotion, hai cổng duyệt hoặc
bước đăng thủ công.

Ranh giới đồng thời được hỗ trợ là nhiều CLI/operator cùng truy cập **một thư mục
project trên shared filesystem**. Filesystem đó phải vượt probe exclusive-create
và atomic same-directory rename. Git clone, worktree riêng, Syncthing hoặc hệ thống
đồng bộ eventual-consistency không phải distributed lock và không được quảng bá
như một cấu hình multi-machine an toàn.

## 2. Lease ghi

Mỗi project có tối đa một lease runtime tại `.healthvideo/write-lease.yaml`. File
này bị loại khỏi Git và backup, không thêm trường vào `project.yaml`, và không đổi
schema project v1/v2. Lease schema `1.0` là model đóng, gồm:

- `lease_id`: token ngẫu nhiên duy nhất;
- `host_id`, `pid`, `process_start_fingerprint`: danh tính owner;
- `operation`, `active_revision`: phạm vi chẩn đoán;
- `acquired_at`, `heartbeat_at`, `ttl_seconds`: thời gian UTC có timezone và TTL
  bị chặn trong một khoảng hữu hạn được test.

Acquire dùng exclusive create (`O_CREAT | O_EXCL`, tương đương mode `x`). Heartbeat
và release chỉ thành công khi `lease_id` còn khớp; tiến trình không bao giờ xóa lease
của owner khác. Mọi command CLI có thể sửa project phải acquire lease trước lần đọc
được dùng để quyết định mutation và giữ lease đến khi mutation hoặc recovery kết
thúc. `status`, audit read-only và mở packet được phép đọc khi bận; `backup` cũng
lấy lease vì cần snapshot nhất quán.

TTL chỉ báo lease đáng nghi, không tự cấp quyền cướp lease. Recovery cùng host chỉ
được phép sau khi chứng minh cặp PID + process-start fingerprint không còn sống.
Lease hết hạn của host khác vẫn chặn và yêu cầu operator chạy recovery tường minh;
record cũ phải được bảo tồn trong `.healthvideo/stale-leases/` trước khi cấp lease
mới. Lỗi contention trả kết quả busy/read-only và không đổi workflow state.

## 3. Ghi file và thư mục an toàn

`write_text_atomic()` chuyển từ tên `.tmp` cố định sang temp duy nhất trong cùng
thư mục đích, flush + fsync file, `os.replace`, rồi fsync thư mục khi nền tảng hỗ
trợ. Chỉ temp do invocation hiện tại tạo mới được dọn. Promotion thư mục giữ cơ chế
backup phục hồi hiện có nhưng mọi caller mutation nằm sau lease.

Lease cung cấp ownership giữa các writer hợp tác qua CLI; atomic replace cung cấp
all-or-nothing cho từng file. M7 không tuyên bố bảo vệ trước chương trình ngoài
workflow tự sửa bytes hoặc filesystem vi phạm semantics đã probe.

## 4. Backup bất biến

`healthvideo backup create <project> <backup-root>` tạo một thư mục snapshot mới,
không ghi đè. Backup giữ các bytes có thẩm quyền và audit được của project, gồm
`project.yaml`, revision artifacts, approvals, asset đã duyệt, render/package đã
có và manifest tương ứng. Nó loại:

- `.healthvideo/`, temp/superseded runtime, pending cache và lock/lease;
- credential, `.env`, token, model weights và cache provider;
- audio/render/cache tạm chưa trở thành artifact được manifest hóa;
- `source-documents/`, source cache, ảnh nguyên trang và toàn văn có bản quyền.

Nếu một file nằm trong vùng bị cấm nhưng được artifact có thẩm quyền tham chiếu,
backup fail closed thay vì âm thầm tạo snapshot không đầy đủ. Policy này không xóa
file nguồn khỏi project; nó chỉ từ chối đưa file đó vào backup M7.

Snapshot chứa `backup-manifest.json` schema `1.0` với backup id, project schema,
slug, active revision, thời điểm inject được, và danh sách path POSIX tương đối đã
sort gồm size + SHA-256. Manifest không hash chính nó. Tạo snapshot trong staging
cạnh đích, xác minh lại mọi entry, rồi promote bằng rename; lỗi để lại staging có
tên chẩn đoán nhưng không tạo snapshot hợp lệ.

## 5. Restore fail-closed

`healthvideo backup restore <snapshot> <new-project-dir>` chỉ nhận destination chưa
tồn tại. Trước khi tạo destination, nó parse manifest đóng và kiểm tra toàn bộ cây:

- cấm absolute path, drive-qualified path, `..`, path trùng/case-collision và ký
  tự không portable;
- cấm symlink, junction/reparse point và mọi entry ngoài manifest;
- kiểm size/hash của tất cả entry, không thiếu và không thừa;
- parse project layout v1/v2 và xác minh approval/artifact bindings hiện hành bằng
  validator sẵn có, không làm mới approval.

Restore copy vào staging cạnh destination, xác minh lần hai rồi atomic-promote. Nó
không resign, migrate, produce, package, render, đổi state hay publish. Project ở
`packaged` vẫn ở `packaged`; approval stale trước backup vẫn stale sau restore.
Failure giữ nguyên snapshot, không để destination bán phần, và nêu staging nào cần
operator xử lý nếu cleanup an toàn không thể hoàn tất.

## 6. Security audit và doctor filesystem

`healthvideo security-audit <project>` là kiểm tra offline, deterministic, trả mã
khác 0 khi vi phạm. Audit kiểm:

- artifact runtime/media/cache/model/credential nằm ở path có nguy cơ được commit;
- token, cloud project id hoặc raw provider response trong artifact typed;
- symlink/reparse point và path thoát root;
- `GateKind` vẫn đúng `medical | video`, không có gate thứ ba;
- package kết thúc ở `packaged`, không có publish API/automation trong production;
- backup inclusion/exclusion và approval bindings nhất quán.

Audit dùng rule cụ thể của repo, không phụ thuộc secret scanner tổng quát hoặc mạng.
Output chỉ nêu rule, path tương đối đã sanitize, lý do và lệnh tiếp theo; không in
nội dung credential. `doctor` thêm probe disposable cho exclusive create và atomic
same-directory rename tại filesystem chứa project. Probe luôn dọn bytes do chính nó
tạo và từ chối bật multi-writer khi semantics không xác nhận được.

## 7. E2E qua ranh giới tiến trình

Acceptance dùng subprocess thật và synchronization bằng barrier/event/file descriptor,
không dựa vào sleep timing. Một golden v2 offline đi từ authoring qua medical gate,
production, video gate, package; một writer thứ hai phải bị từ chối mà không mutate.
Test kill holder, recovery cùng host, lease hết hạn host khác, backup khi writer bận,
restore snapshot và chạy validators trên project mới.

Toàn bộ test dùng fake transport/TTS/render dưới `tmp_path`; không gọi mạng, browser,
GPU, provider thật hoặc publish. Matrix giữ project v1 45–90 giây, v2 hook frame 0,
outro/logo PYH, duration theo nội dung, AI clip muted và đúng hai approval.

## 8. Runbook vận hành

`docs/operations/m7-hardening-runbook.md` phải mô tả bằng command thật: doctor,
status khi busy, nhận diện owner, heartbeat/release bình thường, recovery same-host,
foreign-host escalation, tạo/kiểm backup, restore sang đích mới, security audit và
artifact audit trước commit. Mỗi lỗi nêu rõ điều gì xảy ra, dữ liệu nào được giữ,
và command an toàn tiếp theo. Runbook không chứa credential, đường dẫn cá nhân hoặc
hướng dẫn vượt hai cổng duyệt.

## 9. Tương thích và bất biến

- ProjectManifest v1/v2 không đổi chỉ để chứa lease hay backup metadata.
- Lease và backup là standalone schema; schema export phải deterministic.
- `blocked`/`lock_conflict` hiện có đủ cho báo cáo; contention không tạo state mới.
- `GateKind` chỉ có `medical` và `video`; approval không được tự sinh hoặc refresh.
- `published_manual` chỉ do người vận hành ghi nhận sau thao tác bên ngoài; M7 không
  thêm client đăng bài.
- Không migration v1→v2 trong backup/restore.

## 10. Rủi ro và cách giảm

- **Network filesystem không đúng POSIX/Windows semantics:** probe và fail closed.
- **Clock skew:** TTL không đủ để steal; cần chứng minh owner chết hoặc recovery
  foreign-host tường minh.
- **PID reuse:** so cả PID và process-start fingerprint.
- **Crash giữa heartbeat/release:** mọi mutation kiểm token ownership; stale record
  được bảo tồn.
- **Snapshot thay đổi giữa copy:** giữ lease suốt backup và hash lại trước promote.
- **Path/symlink attack:** snapshot dạng directory có manifest, cấm link và xác minh
  trước lẫn sau copy; không extract archive.
- **Bỏ sót CLI mutation:** lập inventory command và test contract bao phủ từng entry.
- **Flaky concurrency test:** dùng synchronization xác định thay vì sleep.

## 11. Ngoài phạm vi

Không thêm database/Redis/coordinator/object store, distributed consensus, daemon,
scheduler, queue, tự merge conflict, tự steal theo thời gian, mã hóa/key management
cho backup, PHI, provider/TTS/render mới, migration v1→v2, live network test, hai máy
vật lý trong CI, cổng duyệt thứ ba hoặc tự đăng mạng xã hội.

## 12. Tiêu chí chấp nhận thiết kế

- Lease semantics khớp §18 của thiết kế vòng kín và nói rõ shared-filesystem boundary.
- Backup/restore có policy inclusion, exclusion, manifest, path và crash safety.
- Sáu lát implementation bao phủ lease, CLI, backup, E2E, audit/runbook và closeout.
- v1/v2, hai cổng và đăng thủ công được giữ nguyên.
- README ghi M7 design/plan là proposed, chưa ghi implementation complete.
- `git diff --check` qua và C2C review trả `DONE` trước khi bắt đầu implementation.
