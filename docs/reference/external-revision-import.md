# Nhập revision dựng ngoài (IMP-1)

`healthvideo import-revision <slug> --from <dir> --reason "lý do"`
(`--root` chọn gốc xưởng). API dùng chung:
`healthvideo.workflows.external_revision.import_revision(project_dir, source, reason=...)`.
Không nhập vào project thật trong đợt phát triển này.

## Hồ sơ nhập

```text
script/script.yaml                 # Script: title, lines [{id, text, delivery, claim_id, purpose}]
evidence/ledger.yaml               # claims: EvidenceClaim[], records: SourceRecord[]
renders/video.mp4                  # 16:9, có stream tiếng, 600–1500 giây
renders/clips/CL01.mp4 ...          # 1–6 clip 9:16, có stream tiếng, biên ClipPlan hiện có
posts/posts.yaml                   # PostSet; caption khớp toàn bộ clip; mô tả chứa tên nguồn
posts/thumbnail.png                # tùy chọn, luôn hash nếu có
profiles/pronunciation.vi.yaml     # tùy chọn; thiếu thì chụp từ điển xưởng hiện tại
```

`text` là lời hiển thị; `delivery` là lời đọc theo quy tắc ScriptLine hiện có
(không được đổi nghĩa bằng lời đọc). Các dòng không có claim, như outro/câu dẫn,
vẫn được critic kiểm. Claim phải có nguồn tồn tại; không tự gán nguồn. Trường
`support` nếu có vẫn qua kiểm trích đoạn/cache hiện có. Sai schema báo tên file,
trường và lỗi gốc bằng thông báo tiếng Việt.

Nếu khai `PostSet.thumbnail`, vẫn cần đủ `thumbnail.png`,
`thumbnail-background.png`, `license-ledger.yaml` như cổng video hiện tại.
Thumbnail nhập sẵn có thể chỉ là `posts/thumbnail.png`, không khai spec sinh hình.
Không nhận symlink/junction hoặc tệp có tên chứa `approval`. Không nhận hồ sơ còn
`evidence/unresolved-claims.yaml`. Không sao chép reviews/audio/publish từ nguồn.

## Revision, hash và cổng

Tạo N+1 bằng `storage.revisions.create_revision`, với callback chuẩn bị staging và
chuyển manifest. Giữ nguyên N; `workflow.yaml` ghi parent/reason/time. Chỉ đổi
`active_revision` sau kiểm staging và rename. Lỗi sao chép/ghi manifest sẽ dọn staging
hoặc revision vừa tạo. Khóa giao dịch dùng cơ chế revision_lock hiện có; file khóa
được giữ lại có chủ đích theo cơ chế đó.

`workflow/external.yaml` chứa `production_mode: external`, được hash ở cả hai cổng.
Cổng y khoa hash script, ledger, dấu external, từ điển toàn xưởng và bản chụp từ điển
trong revision. Luồng thường/legacy giữ nguyên danh sách hash. Hồ sơ external vào
`awaiting_medical_review`; factory chạy critic Trạm 07 trên lời nhập trước khi hiện
cổng PIN. Điểm không đạt/thiếu bản chấm hợp lệ vẫn bị chặn; không ghi bản chấm thay agent.

`approve_gate` external yêu cầu PIN bác sĩ (app/TTY chuyển PIN đang xác thực, không
lưu PIN); bỏ riêng các kiểm dựa trên storyboard/visual budget/brand asset.
Vẫn kiểm schema, ledger/support, posts, từ điển, hash và critic. Gói HTML y khoa
hiện từng dòng hiển thị/lời đọc cùng bảng claim/nguồn, không tạo storyboard giả.

Sau PIN y khoa, `produce_external` dùng ffprobe kiểm media và ghi manifest/QA kỹ thuật;
không gọi TTS, Remotion, storyboard, ảnh hoặc clip maker. QA không khẳng định đã nghe,
đọc hình hay chấm đúng nội dung. Critic Trạm 12 kiểm video/clip/posts hiện hành; sau khi
đạt mới gọi `submit_video`. Cổng video kiểm lại medical hash, media hash, inventory
clip, QA, posts, critic và PIN. Bác sĩ vẫn cần xem/nghe.

Sau PIN video, nhánh `package_project` external kiểm hai bản duyệt còn hiệu lực,
kiểm lại byte payload, đóng gói video + clip + posts + thumbnail (nếu có) và ghi
`publish/manifest.json` đúng bindings/payload_sha256 để publisher/auto_publish hiện có
dùng được. Thay lời/ledger/từ điển hoặc byte video/clip sau duyệt sẽ chặn luồng.
Hồ sơ external bị từ chối hoặc cần sửa được giữ lại để sửa nguồn và nhập revision mới;
factory không tự giao agent dựng lại.

## Adapter PYH-003

`python tools/build_pyh003_import.py <thư mục đích mới>`; mặc định
`cache/pyh003-import`, nguồn `E:/pyh-003/cache/pyh003` (chỉ đọc).
Không gọi mạng, không gọi import-revision, không đụng project thật.

Adapter đọc script-full-lines.json/script-full.md, sources-full.md,
research-ledger.json và evidence-rev001/ledger.yaml. Nguồn và ánh xạ claim → dòng
chỉ lấy từ bảng đã có. Mỗi dòng có một claim tổng hợp giữ toàn bộ claim thành phần,
locator và giới hạn trong text_technical. Không suy ánh xạ từ từ khóa. Nếu thiếu
ánh xạ/nguồn, ghi import-report.json cùng unresolved-claims.yaml và trả exit 1;
import-revision từ chối hồ sơ đó.

Sao chép pyh003-full.mp4, short-bo-gan.mp4 → CL01, short-di-kham.mp4 → CL02,
thumb-a.png → posts/thumbnail.png. Posts là bản nháp từ tiêu đề topic/tên nguồn,
có ghi rõ để bác sĩ xem ở cổng video. Không tự gắn trạng thái đã duyệt.

Chạy thử ngày 25/11/2026 tại thư mục tạm `pyh003-import-imp1-20261125`
(chạy lại adapter cuối tại `pyh003-import-imp1-final-20261125`):
42 dòng, 41 claim theo dòng, 33 claim gốc, 18 nguồn; schema đạt;
`missing_support: []`. Đây là kiểm schema/ánh xạ có sẵn, không phải nghiệm thu
bằng chứng hay xác nhận lời khớp audio. Còn cần hai critic thật và hai PIN bác sĩ.

Kiểm ffprobe trên bản sao tạm: video 1920×1080, có tiếng, 790,85 giây, đạt.
CL01 1080×1920 dài 41,53 giây; CL02 1080×1920 dài 39,27 giây, đều có stream tiếng
nhưng **không đạt biên 60–180 giây của ClipPlan**. Nhánh sản xuất chặn nguyên trạng,
không tự kéo dài clip hay nới QA. Cần làm lại clip ở nguồn cho đúng biên trước khi
gói này có thể đi hết quy trình đăng. Kết quả chi tiết ở `media-check.json` trong
thư mục tạm, không thuộc Git.

## File thay đổi và điểm nối

| File:dòng | Lý do |
|---|---|
| `src/healthvideo/workflows/external_revision.py:45` | Kiểm schema/nguồn, nhập nguyên tử qua dịch vụ revision, ffprobe, ràng buộc QA và media. |
| `src/healthvideo/storage/revisions.py:27` | Callback staging/activation để dùng lại tạo N+1; rollback khi ghi manifest lỗi; bảo toàn workflow.yaml. |
| `src/healthvideo/domain/state_graph.py:393` | Riêng external được nộp y khoa bằng script/ledger/dấu external; không thêm đường duyệt. |
| `src/healthvideo/cli.py:912` | Lệnh import-revision; chuyển PIN đã nhập TTY vào approve_gate external. |
| `src/healthvideo/workflows/gate_review.py:324` | Bộ đường dẫn hash external và kiểm schema/PIN/media trước duyệt; giữ posts, critic và QA hiện có. |
| `src/healthvideo/workflows/produce.py:438` | Rẽ sang ffprobe, không gọi TTS/renderer; submit_video kiểm media external hiện hành. |
| `src/healthvideo/workflows/runner.py:1641` | Chỉ gọi critic lời/sản phẩm cho external; không gọi maker; critic không đạt vẫn chặn. |
| `src/healthvideo/workflows/product_review.py:271` | Kiểm độ mới external bằng hash/QA, tránh coi video cũ hơn ngày nhập/PIN là phải dựng lại. |
| `src/healthvideo/workflows/review_html.py:201` | Gói HTML lời/nguồn và video/clip/posts external không cần storyboard. |
| `src/healthvideo/workflows/dashboard.py:2807` | Chuyển PIN đã xác thực của bác sĩ vào nhánh external; dashboard vốn đã đọc script/ledger độc lập storyboard. |
| `src/healthvideo/workflows/package.py:237` | Đóng gói external bằng hai approval binding hiện có; kiểm hash byte trước/sau sao chép. |
| `tools/build_pyh003_import.py:18` | Adapter offline PYH-003; báo thiếu ánh xạ, không suy hoặc gán nguồn. |
| `tests/workflows/test_external_revision.py:43` | Kiểm revision 002, rollback, hash/PIN/critic/QA, chặn sửa byte, runner không gọi maker và gói đăng. |
| `tests/test_cli.py:685` | Cập nhật tập lệnh công khai với import-revision. |
| `docs/reference/external-revision-import.md:1` | Hợp đồng hồ sơ nhập, cách vận hành, điểm nối và kết quả kiểm PYH-003. |

Mẫu WAV có sẵn ở checkout chính được sao chép chỉ đọc sang
`cache/voice-ref/anh-tu-ref.wav` của worktree để test Voice Studio thật chạy được.
Cache này đã được `git check-ignore` xác nhận, không đưa audio vào Git.

## Kiểm chứng cuối

- Toàn bộ `python -m pytest -q`: **3170 passed, 3 skipped**, 398,33 giây.
- Nhóm `tests/workflows/test_external_revision.py` sau bổ sung các trường hợp YAML lỗi:
  **22 passed**; có kiểm preview publisher YouTube/TikTok trên tài khoản giả, không upload.
- `ruff check src tests tools`: đạt. `git diff --check`: đạt.
- Không chạy Vitest song song, không commit, không nhập revision hoặc duyệt/đăng project thật.
- Adapter cuối tạo hồ sơ trong `%TEMP%/pyh003-import-imp1-final-20261125`;
  schema đạt, không có claim thiếu ánh xạ nguồn. Hai clip thật vẫn bị chặn vì dưới 60 giây.
