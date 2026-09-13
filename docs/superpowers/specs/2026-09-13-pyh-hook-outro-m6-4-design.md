# M6.4 — Mở bằng hook, kết bằng lời cảm ơn đã duyệt

**Ngày:** 13-09-2026
**Trạng thái:** Thiết kế đã được người dùng chấp thuận; chờ duyệt bản viết trước implementation.

## 1. Quyết định và phạm vi

Video v2 mở ngay tại frame 0 bằng cảnh nội dung và dòng thoại đầu tiên. Dòng này
có thể đặt câu hỏi gây tranh luận hoặc diễn đạt mạnh để giữ người xem; mọi mệnh đề
y khoa trong hook vẫn phải gắn claim, source marker và đi qua cổng duyệt y khoa như
các dòng khác. Không có intro scene, logo lead-in im lặng hay ngoại lệ kiểm duyệt
cho hook. Logo/mascot có thể xuất hiện như asset đã khai báo trên cảnh nội dung,
nhưng không chiếm thời gian trước hook.

Video v2 kết bằng một dòng script và một cảnh storyboard thật. Lời kết do người
dùng chọn là:

> Nếu mình có gì sai sót, hoặc bạn có bất kỳ câu hỏi nào, hãy để lại phản hồi
> dưới phần bình luận nhé. Cảm ơn bạn đã xem video.

Dòng kết được author trước cổng duyệt y khoa. M6.4 pin chính xác câu trên;
không hỗ trợ biến thể lời kết trong lát này. Nó không nằm trong brand profile,
không được renderer tự chèn và không được tổng hợp thành audio thứ hai. Thời lượng
cảnh kết theo nhịp đọc đã author; không ấn định 2–3 giây. Video v2 không có giới
hạn cứng 45–90 giây: composition kết thúc đúng frame cuối storyboard.

Thiết kế này thay thế quy tắc intro bắt buộc, outro 2–3 giây và thoại signature
trong `profiles/brand.vi.yaml` ở bản A–Z §13; thay thế row M6.4 của plan M6;
thay thế giới hạn tổng 45–90 giây của v2. Các mục này tiếp tục mô tả lịch sử
hoặc v1, không còn là quy tắc cho video v2 sau M6.4. Khung 1080×1920/30 fps,
hai cổng duyệt, đăng thủ công và dữ liệu v1 giữ nguyên. M6.5 visual budgets và
M6.6 Veo nằm ngoài phạm vi.

## 2. Lựa chọn kiến trúc

Chọn **authored script + storyboard** làm nguồn sự thật duy nhất cho thoại và
timeline. Phương án chèn outro trong Remotion hoặc lấy lời thoại từ brand profile
được loại vì medical review, TTS, cache và timing sẽ nhìn thấy các bản khác nhau.
Phương án một template bắt buộc với thời lượng cố định cũng bị loại: câu kết dài
hơn thời gian 2–3 giây và video không còn giới hạn tổng thời lượng.

Luồng v2:

```text
author hook + nội dung + outro trong script
    → author cảnh liên tiếp trong storyboard
    → validate liên kết và asset
    → duyệt y khoa (script/storyboard/manifest)
    → TTS một lần từ toàn bộ script
    → so thời lượng WAV thật với frame cuối
    → Remotion render đúng timeline
    → duyệt video → chuẩn bị gói đăng thủ công
```

Không có bước tự chèn hoặc sửa storyboard sau cổng duyệt. Khi tác giả đổi câu
kết, timing hoặc asset, duyệt y khoa cũ hết hiệu lực theo revision/hash hiện có.

## 3. Contract script và storyboard

Thêm `Script.format_profile` tùy chọn với giá trị `legacy` (mặc định khi file
cũ thiếu trường) hoặc `hook_outro_v1`. Đường authoring M6.4 cho dự án v2 mới
ghi `hook_outro_v1` vào script; production đọc trường này để chọn validator.
Không suy ra profile từ sự có mặt của outro. Script v2 cũ không có marker vẫn
chạy theo contract legacy; không tự nâng cấp hoặc tự chèn câu kết. Marker đã
ghi phải được giữ khi sửa revision và nằm trong medical hash của script.

Thêm trường tùy chọn, tương thích ngược `ScriptLine.purpose` với giá trị
`content` (mặc định) hoặc `outro`. Một script M6.4 có đúng một dòng `outro`, ở
cuối danh sách. Dòng kết có text đúng bản author trong revision, không mang
`claim_id` hoặc `source_marker`; validator `hook_outro_v1` yêu cầu text khớp
chính xác câu đã pin ở §1. Thay câu kết là thay đổi thiết kế riêng, không phải
chỉnh sửa tự do trong M6.4.

Thêm `Scene.script_line_id` tùy chọn và loại cảnh `brand_outro` cho v2 M6.4.
Mọi cảnh có thoại do M6.4 author tham chiếu ID dòng script; mỗi dòng thoại ánh
xạ đúng một cảnh theo đúng thứ tự, không có dòng/cảnh thoại mồ côi. Cảnh cuối
`brand_outro` tham chiếu dòng `purpose=outro`; `narration` phải khớp chính xác
text của dòng đó, không có claim/marker hay evidence highlight. Cảnh này bắt
đầu ngay sau cảnh nội dung cuối và có `duration_frames > 0`. Cảnh đầu bắt đầu
ở frame 0 và tham chiếu dòng đầu, tức hook. Không suy đoán ý nghĩa y khoa bằng
NLP: tác giả phải khai báo claim/source binding theo contract hiện có; validator
và cổng duyệt kiểm tra chúng như mọi cảnh nội dung.

Để bảo toàn fixture và dự án cũ, các trường mới là tùy chọn khi parse. Validator
nghiêm ngặt áp dụng khi `format_profile=hook_outro_v1`, kể cả nếu script bị
xóa mất outro; không thể rơi về legacy bằng cách xóa dòng kết. v2 legacy không
outro vẫn đọc và chạy được. v1 không phải đổi schema hay hành vi.

## 4. Brand asset và renderer

Logo PHY SVG tạo xác định từ M6.3 được đăng ký như một `AssetRecord` decorative,
`semantic=false`, với role mới `brand`; không giả làm `whiteboard`. Scene ref
có `role=brand`. Mascot tùy chọn là `mascot_reaction` decorative ở một trong
ba pose M6.3. Asset có chữ, số hoặc annotation y khoa không được phân loại là
decorative; nó phải theo đường semantic và claim/source binding hiện có.

Workflow đăng ký asset theo kiểu intent-first, promotion an toàn khi retry của
M6.3. Resolver và medical gate kiểm tra hai chiều giữa scene ref và manifest
record do M6.4 sở hữu. Production xác minh path tương đối, bytes và SHA-256,
stage đúng asset đã khai báo và đưa hash cả asset decorative vào render cache.
Không nhúng SVG tự sinh trực tiếp trong renderer, không dùng URL/network.

`OutroScene` chỉ bố trí asset đã khai báo và caption/narration từ storyboard.
Chuyển động chỉ phụ thuộc frame: opacity, translate hoặc scale xác định; không
random, clock, network, slogan ẩn hay thoại phát sinh. Logo/mascot không che
caption. Asset ở cảnh nội dung không che marker, chart hoặc crop. Scene không
chứa trường M6.4 giữ cách render cũ.

## 5. Timing và audio

Với v2, `build_render_input()` vẫn yêu cầu ít nhất một scene, scene đầu ở frame
0, các scene liên tiếp không chồng lấp, mỗi duration dương, media path tương đối
hợp lệ. Nó không áp giới hạn 1.350–2.700 frame. Total frame là end frame của
scene cuối. Đường v1 tiếp tục kiểm tra 45–90 giây; API phải phân biệt version
hoặc policy tường minh thay vì vô tình nới v1. Schema/render input vẫn 30 fps.

Remotion `durationFromScenes()` trả đúng end frame cuối cho input v2, không
`max(1350, ...)`. `Composition.defaultProps` có thể giữ duration preview hữu
hạn, nhưng `calculateMetadata` phải trả duration thật của storyboard khi render.
Không có Sequence outro ngoài storyboard.

Production tổng hợp một WAV từ toàn bộ `script.lines`, gồm câu kết đúng một lần.
Sau TTS, đọc `audio_duration_ms` từ WAV thực tế và đặt `F` là end frame cuối.
Tại 30 fps, dừng trước render nếu `30 * audio_duration_ms > 1000 * (F + 1)`;
vế `+1` chỉ cho dung sai tối đa một frame khi đổi millisecond sang frame.
Không cắt/pad WAV, auto-retime cảnh hoặc sửa storyboard sau duyệt. Ghi ba
trường quan sát xác định vào `video-qa.json` của v2:
`audio_duration_ms`, `composition_duration_ms = ceil(1000 * F / 30)` và
`trailing_visual_ms = max(0, composition_duration_ms - audio_duration_ms)`.
Chúng không phải lệnh kéo dài audio hoặc thay timeline; người duyệt video nhìn
thấy khoảng hình không còn tiếng ở cuối.

## 6. Cổng duyệt, lỗi và khả năng chạy lại

Medical packet hiển thị hook, câu kết, scene cuối, timeline và brand refs.
Medical gate hash script, storyboard, manifest và semantic bytes theo contract
hiện có; thay đổi text/timing/ref làm approval stale. Decorative bytes được
resolver/preflight xác minh theo hash manifest và đưa vào cache identity.
Không tạo cổng duyệt thứ ba. Video gate duyệt output thực tế. Package chỉ lấy
hook từ dòng đầu, không lấy outro làm caption hook/title; citations vẫn đến từ
claim/source marker thật. Không tự đăng.

Authoring thất bại khi thiếu/nhân đôi outro, outro không cuối, mapping ID sai,
asset không khai báo/không đúng role, hoặc dữ liệu semantic giả làm decorative.
Production thất bại có thông báo khi WAV vượt timeline; nó không promote render
hay đổi state. Retry trên cùng input phải hội tụ; xung đột file/hash phải dừng
thay vì ghi đè artifact khác.

## 7. Kiểm chứng

- Domain/schema: thiếu `format_profile` mặc định legacy và không tự nâng cấp;
  `hook_outro_v1` thiếu outro bị từ chối; default `purpose=content` đọc dữ liệu
  cũ; một outro cuối với câu pin chính xác hợp lệ; khác câu, không cuối, nhân
  đôi, claim hoặc marker trên outro bị từ chối; mapping ID, text và thứ tự
  scene–line phải khớp; hook ở frame 0.
- Render timing: v2 20 giây và 140 giây đều hợp lệ; gap/overlap/zero duration
  vẫn bị chặn; v1 20/140 giây vẫn bị chặn; Python và Remotion cho cùng end frame.
- Asset/gate: logo và mascot ref được render một lần, quyền/hash/role và reverse
  manifest được xác minh; đổi text, timing hoặc ref sau duyệt làm gate stale;
  semantic annotation không thể đi đường decorative.
- Audio/production: TTS input kết bằng đúng câu kết một lần; so sánh độ dài
  bằng công thức `30*A > 1000*(F+1)`, gồm test tại biên; WAV vượt timeline dừng
  trước render, WAV phù hợp đi tiếp; ba trường audio/timeline/tail ở
  `video-qa.json` đúng công thức; không mutate storyboard post-gate; cache đổi
  khi text/timing/logo bytes đổi.
- Renderer/package: frame đầu là hook chứ không phải intro; chuyển động outro
  xác định, caption không bị che; caption upload dùng hook, citations không chứa
  nguồn giả; scene legacy và fixture v1/v2 vẫn tương thích.

Chạy test liên quan, full Python suite, Ruff, schema export/diff, video test,
TypeScript typecheck và `git diff --check` trước commit implementation. README
phải cập nhật tiến độ trong cùng commit nhiệm vụ.
