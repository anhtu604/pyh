# M6.5 — Ngân sách visual theo timeline đã duyệt

**Ngày:** 14-09-2026  
**Trạng thái:** Bản thiết kế chờ review trước implementation

## 1. Mục tiêu và phạm vi

M6.5 đo và cưỡng chế tỷ lệ visual trên timeline storyboard v2 đã duyệt. Chính
sách mặc định là 65–75% whiteboard/SVG, 15–25% chart hoặc crop y văn và tối đa
10% AI clip. Tỷ lệ là ràng buộc authoring có thể kiểm tra, không phải chỉ số ước
lượng sau render.

Lát này cũng nối SVG chart đã khai báo của M6.1 vào scene `chart`. M6.2 crop,
M6.3 SVG/mascot/logo và M6.4 hook/outro tiếp tục dùng contract hiện có. Không
thêm Veo, provider video, network, dữ liệu y khoa, giấy phép suy đoán, cổng duyệt
thứ ba hoặc hành vi đăng tự động.

Khung hình giữ 1080×1920, 30 fps. V2 tiếp tục kết thúc ở frame cuối storyboard;
v1 giữ giới hạn 45–90 giây và toàn bộ hành vi cũ.

## 2. Kích hoạt và tương thích

`Storyboard` có trường cộng thêm `visual_budget_profile`:

- `legacy` là mặc định khi trường vắng mặt;
- `m6_5_v1` bật kiểm tra nghiêm ngặt.

Không suy ra profile từ `Script.format_profile`, outro, chart hoặc asset. Vì vậy
mọi file v1 và v2 hiện có tiếp tục parse và chạy như trước. Đường authoring hoặc
fixture M6.5 phải ghi `m6_5_v1` tường minh.

`visual_budget_override` là tùy chọn và chỉ hợp lệ với `m6_5_v1`. Override nằm
trong `storyboard.yaml`, gồm rationale không rỗng và min/max phần trăm nguyên cho
đúng ba nhóm. Nó thay giới hạn mặc định nhưng không tắt việc phân loại hay tính
toán. Mỗi bound nằm trong 0–100, min không vượt max và phải tồn tại ít nhất một
phân bổ tổng 100 thỏa cả ba khoảng:

```text
sum(min_i) <= 100 <= sum(max_i)
```

Không có `skip_validation`, nhóm thứ tư hoặc override ở sidecar. Vì storyboard
nằm trong medical hash, đổi policy, bound hoặc rationale sau duyệt làm approval
hết hiệu lực theo cơ chế hiện có.

## 3. Phân loại scene

Mẫu số là tổng frame của timeline liên tiếp, bằng end frame của scene cuối. Mỗi
scene thuộc đúng một nhóm theo `Scene.visual` chính:

| Nhóm | `Scene.visual` |
| --- | --- |
| `whiteboard_svg` | `whiteboard`, `brand_outro` |
| `chart_crop` | `chart`, `evidence_highlight` |
| `ai_clip` | `ai_clip` |

Logo, mascot, medical text, SVG trang trí và mọi `visual_assets` phủ trên scene
không được cộng thêm frame. Chúng kế thừa nhóm của visual chính, tránh đếm kép.
Do đó mascot và outro của M6.3–M6.4 nằm trong ngân sách whiteboard/SVG; mascot
trên chart không làm tăng nhóm whiteboard.

Mọi visual hiện hành được partition đúng một lần. Giá trị mới trong tương lai
phải fail closed cho profile `m6_5_v1` cho đến khi mapping được cập nhật.

## 4. Số học và report

Gọi `T` là tổng frame, `F[c]` là tổng `duration_frames` của nhóm `c`. Validator
dùng số nguyên, không dựa vào phần trăm đã làm tròn:

```text
min[c] * T <= 100 * F[c] <= max[c] * T
```

Giới hạn mặc định, tính inclusive:

| Nhóm | Min | Max |
| --- | ---: | ---: |
| `whiteboard_svg` | 65 | 75 |
| `chart_crop` | 15 | 25 |
| `ai_clip` | 0 | 10 |

Ba điều kiện áp dụng đồng thời. AI bằng 0 hợp lệ, nhưng tổng tỷ lệ vẫn phải thỏa
cả khoảng whiteboard và chart/crop; hệ thống không tự tạo scene hoặc retime để
làm policy đạt.

Hàm domain thuần trả report bất biến gồm profile, `override_active`, `total_frames`,
frame theo nhóm, basis points chỉ để hiển thị, effective bounds và `passed`.
Basis points dùng phép chia nguyên xác định; quyết định pass luôn dùng phép nhân
chéo ở trên.

## 5. Chart đã khai báo

Scene `chart` của M6.5 phải tham chiếu đúng một asset role `chart`. Manifest record
tương ứng phải có `kind=DATA_CHART`, `semantic=true`, `storyboard_role=chart`,
bytes/hash hợp lệ và rights ledger hợp lệ theo M6.1. Thiếu ref, trùng ref, sai kind,
sai owner, thiếu bytes hoặc hash lệch đều bị từ chối trước medical approval và
trước production.

Remotion chỉ hiển thị SVG đã khai báo qua `staticFile`. Nó không tính lại số liệu,
đổi trục, tạo chart hoặc suy diễn nguồn/quyền. Chart render đúng một lần và giữ
marker/caption trong vùng an toàn.

`VisualAssetRef.role` và `AssetRecord.storyboard_role` được mở rộng cộng thêm
`chart`; các role M6.3–M6.4 không đổi.

## 6. AI clip chưa hỗ trợ production

Pure validator vẫn phân loại `ai_clip` để kiểm tra contract và override. Tuy nhiên
M6.5 chưa có clip asset/provider đã khai báo. Production của storyboard
`m6_5_v1` chứa `ai_clip` phải dừng trước TTS và Remotion với lỗi chỉ rõ cần M6.6.
Không gọi generic whiteboard fallback và không báo rằng đã render AI footage.

Video M6.5 với 0% AI là đường production được hỗ trợ đầy đủ.

## 7. Gate, production và QA

Medical gate chạy cùng pure visual-budget validator trước khi ghi approval, sau
khi kiểm tra storyboard/manifest hiện có. Packet y khoa hiển thị profile, frame,
tỷ lệ, bound hiệu lực và rationale override. Đây vẫn là cổng pre-production duy
nhất; override được bác sĩ chấp thuận thông qua chính medical gate.

Production xác minh approval hiện hành rồi tính lại cùng report trước TTS/render.
Nếu fail hoặc có AI clip, nó không tạo WAV/MP4, không đổi state và không tự sửa
storyboard.

`video-qa.json` v2 được mở rộng bằng `visual_budget` chứa toàn bộ report xác định.
M6.4 timing QA vẫn cùng file và không đổi. QA được tạo trong staging hiện có rồi
promotion/recovery như các artifact production khác.

Cache validation không tin JSON tự nhất quán. Nó tính lại budget từ storyboard
đã duyệt hoặc canonical `render-input.json`, so sánh toàn bộ report, input hash và
artifact hiện có. QA đã promote ở `reviews/video-qa.json` và QA staged ở
`renders/video-qa.json` được xử lý theo cùng nguyên tắc retry của M6.4. Crash không
được làm project tiến state hoặc khiến cache chưa xác minh được chấp nhận.

Video packet hiển thị visual-budget QA của render thực. Video gate vẫn yêu cầu
thao tác duyệt riêng và hash output hiện có. Package vẫn chỉ chuẩn bị gói đăng thủ
công; không thay caption, source hoặc publish flow.

## 8. Lỗi và tính nguyên tử

- Timeline gap/overlap/zero duration tiếp tục bị contract render chặn.
- Storyboard ngoài budget bị từ chối với nhóm, frame, bound và tỷ lệ liên quan.
- Override thiếu rationale, bound sai hoặc infeasible bị từ chối khi parse.
- Chart ref/manifest/bytes/rights sai bị từ chối trước gate và production.
- AI clip bị từ chối trước thao tác tốn kém.
- Không tự retime, chuyển nhóm, thêm chart/crop hoặc nới bound.
- Đăng ký chart tiếp tục intent/staging/promotion của visual asset workflow.
- Ghi storyboard dùng atomic write; production dùng staging và promotion hiện có.

## 9. Tiêu chí chấp nhận

- Boundary 65/75, 15/25 và 0/10 pass; lệch một frame tại boundary fail chính xác
  mà không phụ thuộc float.
- Tổng frame ba nhóm bằng tổng timeline, không đếm kép asset phủ.
- Legacy v1/v2 không có marker giữ nguyên dữ liệu và hành vi.
- Override hợp lệ thay bound; thay override sau duyệt làm medical approval stale.
- Scene chart chỉ render SVG `DATA_CHART` đã khai báo, có provenance và rights.
- M6.5 có AI clip fail trước TTS/render; 0% AI chạy được.
- Medical packet và video packet hiển thị report/rationale, không tự duyệt.
- Production ghi report đúng vào QA, retry dùng cache không gọi lại TTS/render,
  QA giả hoặc stale bị từ chối.
- Hook frame 0, outro đã duyệt, exact v2 duration, 1080×1920/30 fps, hai gate và
  manual publishing giữ nguyên.
- Full Python, Ruff, schema export/diff, video tests, typecheck và
  `git diff --check` đều qua trước khi đánh dấu complete.
