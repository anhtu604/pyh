# Xưởng video PYH: tái cấu trúc dự án

Ngày: 2026-10-22 · Trạng thái: bản thảo chờ người dùng duyệt

## 1. Mục đích và lý do

Dự án `healthvideo` lớn dần qua nhiều phiên (≈15k dòng Python, ≈21k dòng test,
46 lệnh CLI, 24 trạng thái workflow, 30 spec/plan, README 101 KB). Nhiều phần
được xây cho kịch bản nhiều người cùng ghi một project, chuyển đổi v1→v2, hay
các nhánh phụ không còn dùng. Người dùng thấy dự án quá cồng kềnh.

Mục tiêu mới: biến repo thành **xưởng sản xuất video A–Z cho kênh của người
dùng**, một người vận hành, chạy liên tục qua agent CLI (Codex, Antigravity
`agy`), chỉ dừng ở hai cổng duyệt của bác sĩ.

Nội dung kênh (người dùng chốt):

- Chia sẻ kiến thức y khoa hay và làm rõ tranh cãi bằng góc nhìn y khoa thực thụ.
- **Bỏ trọng tâm "phòng bệnh".** Trọng tâm là **mô phỏng trực quan** để người
  xem hiểu bản chất một bệnh/vấn đề y khoa qua kiến thức hàn lâm: giải phẫu,
  sinh lý, giải phẫu bệnh, sinh lý bệnh, mô phôi, nội/ngoại/sản/nhi…
- Khi bảo vệ một quan điểm, phải đưa bằng chứng có nguồn.
- Giữ nguyên hướng giọng/nội dung "explain-first" đã có
  (`docs/superpowers/specs/2026-10-18-explain-first-content-design.md` §1–§15:
  giải thích trước, bằng chứng sau; cân bằng kiến thức, hấp dẫn, hài hước).

Người dùng muốn **ít phải ra quyết định**; khi cần, agent đề xuất phương án để
chọn.

## 2. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu**

1. Cắt gọt tại chỗ (người dùng chọn): giữ lõi đang chạy tốt, xóa phần thừa,
   không viết lại từ đầu.
2. Tổ chức lại quanh **4 giai đoạn** (mục 5) và một **hàng đợi chủ đề** chạy
   tự động tới cổng duyệt.
3. Mỗi chủ đề xuất ra: 1 video dài YouTube 16:9, 1–6 clip 9:16
   (TikTok/Shorts/Reels), và bài đăng đa kênh soạn sẵn trong gói đăng bài.
4. Thư viện hình mô phỏng y khoa mở rộng được qua từng chủ đề.
5. CLI còn khoảng 10–12 lệnh; README ngắn, tài liệu cũ vào lưu trữ.

**Không làm**

- Podcast (người dùng bỏ; không dùng podcastfy).
- Tự động đăng bài lên bất kỳ nền tảng nào.
- Avatar/người thật AI, video AI sinh cảnh (Veo).
- Đa người dùng, đa máy, khóa ghi, backup/restore, chuyển đổi v1.

**Phản mục tiêu** (dù chạy được vẫn là thất bại)

- Video có số liệu, nguồn, hoặc kết quả nghiên cứu bịa; hoặc bịa trải nghiệm
  của bác sĩ.
- Hình giải phẫu/cơ chế sai y khoa lọt qua cổng.
- Agent tự duyệt cổng y khoa hoặc cổng video, hoặc tự đăng bài.
- Cắt gọt làm hỏng đường đi đang chạy: render dài theo chương, clip 9:16, TTS
  VieNeu, căn thời gian theo dòng, hai cổng duyệt, gói đăng bài.
- Thay hệ thống này bằng một hệ thống khác cũng cồng kềnh như vậy.

## 3. Ràng buộc

- Quy tắc repo trong `CLAUDE.md`/`AGENTS.md` giữ nguyên: không bịa; không vượt
  cổng; không tự xuất bản; không lưu API key/audio tạm/render/cache/toàn văn có
  bản quyền vào Git; dùng `pathlib.Path`; chạy test + lint trước commit; cập nhật
  bảng tiến độ README trong cùng commit.
- Máy: Windows 11, PowerShell 5.1, Python ≥3.11, Node/pnpm, **RTX 3060 12 GB**.
  Các mô hình local chạy **tuần tự**, không đồng thời.
- Người duyệt hai cổng: người dùng (bác sĩ). Approval chỉ tạo khi người dùng
  gửi quyết định tường minh kèm tên người duyệt; agent không tự tạo.
- **Chống tự duyệt** (người dùng chọn): `review approve` đòi **mã PIN** do người
  dùng đặt, lưu ngoài repo (ví dụ trong thư mục cấu hình người dùng), không nằm
  trong `.env` hay biến môi trường mà `run` truyền cho agent. `run` không cho
  agent gọi `review approve`. Từ chối (`reject`) không cần PIN.
- Agent thực thi: Codex CLI và `agy` (Antigravity) thay phiên khi một bên hết
  token. `agy` chạy ở mức effort **medium** (cao hơn sẽ thiếu token).
  Claude điều phối, rà soát, giao việc.
- Giọng đọc: VieNeu `Thái Sơn` (người dùng đã chọn qua nghe mù).
- Chỉ dùng công cụ có giấy phép cho phép dùng trên kênh có kiếm tiền.

## 4. Hiện trạng: giữ, cắt, thêm

### 4.1 Giữ (lõi chạy tốt)

| Phần | Vị trí chính |
|---|---|
| Tìm bằng chứng PubMed + Europe PMC, sàng lọc, ledger, claim gắn nguồn | `evidence/`, `workflows/evidence.py`, `workflows/screening.py`, `workflows/citations.py`, `domain/evidence.py` |
| Explainer cơ chế, claim `mechanism`, lint kịch bản explain-first | `domain/explainer.py`, `qa/script.py`, `workflows/draft.py` |
| Script, storyboard, asset manifest, outline, clip plan | `domain/script.py`, `storyboard.py`, `asset_manifest.py`, `outline.py`, `clip_plan.py` |
| Hai cổng duyệt, revision, invalidation (sửa sau duyệt → mở lại cổng) | `domain/gate_review.py`, `invalidation.py`, `revision.py`, `workflows/gate_review.py`, `review.py`, `review_html.py`, `review_frames.py` |
| TTS VieNeu, chuẩn hóa, phát âm, ASR kiểm, căn thời gian theo dòng | `tts/` (trừ `benchmark.py`), `render/timing.py` |
| Render Remotion: dài 16:9 theo chương + cache, clip 9:16, phụ đề, mascot, thẻ cuối, font | `render/`, `workflows/produce.py`, `long_form.py`, `video/src/` |
| Brand (logo, mascot, palette), hook/outro | `domain/brand.py`, `visuals/`, `assets/brand/`, `domain/hook_outro.py` |
| Gói đăng bài thủ công | `workflows/package.py` |
| Xem trước Remotion Studio, bộ cài một lệnh, skill `/pyh` | `cli.py preview`, `install/`, `.agents/skills/pyh/` |

### 4.2 Cắt

| Phần | Lý do |
|---|---|
| Khóa ghi (lease), `lease inspect/recover`, backup/restore, `security-audit`, M7 runbook, doctor filesystem probe | Chỉ cần khi nhiều writer/nhiều máy |
| Project v1, `migrate`, `create_project.py`, `domain/project.py`, profile `legacy` | Không còn project v1 cần giữ |
| Orientation riêng + chờ "editorial direction" + xác nhận author brief nhiều bước | Gộp vào giai đoạn 1 (mục 5.1); bác sĩ góp ý ở cổng y khoa |
| Second-model review (`agent review-request/complete`), `awaiting_second_model_review` | Không dùng; hai cổng của bác sĩ là đủ |
| `awaiting_browser_login` | Không dùng trình duyệt đăng nhập trong pipeline |
| Veo / AI clip (`video_ai/`, `workflows/ai_clips.py`, `domain/ai_clip.py`, `AiClipScene`) | Ngoài phạm vi; FLUX thay phần minh họa |
| `tts-benchmark` | Đã chốt giọng |
| Visual budget, license ledger riêng | Thay bằng một trường giấy phép trong asset manifest (builder quyết chi tiết) |
| Rác ở gốc: `VoiceStudio-Electron-0.5.6-win-x64.exe` (204 MB), `New Recording.m4a`, `.codex-tmp/`, `.worktrees/` cũ, `.remotion/`, `sample/` | Không thuộc dự án; `.remotion/` thêm vào `.gitignore` |
| Khoảng 50 skill trong `.agents/skills/` | Chỉ giữ skill workflow này thực sự gọi (`pyh`, nhóm remotion, humanizer…); builder lập danh sách |
| 30 spec/plan cũ, README 101 KB | Chuyển vào `docs/archive/`; README mới ngắn |

### 4.3 Thêm

1. Hàng đợi chủ đề + bộ chạy agent tự đổi Codex/agy (mục 6).
2. Giai đoạn 1: tìm chủ đề/tranh cãi từ nguồn miễn phí.
3. Thư viện hình mô phỏng SVG mở rộng dần + minh họa FLUX.2 klein 4B.
4. Nhạc nền ACE-Step 1.5.
5. Bài đăng đa kênh + thumbnail trong gói đăng bài.

## 5. Bốn giai đoạn

Trạng thái workflow rút gọn (24 → khoảng 12):

```
queued → researching → draft_ready → awaiting_medical_review → medically_approved
       → producing → awaiting_video_review → video_approved → packaged → published_manual
nhánh: needs_revision · blocked · rejected
```

`producing` gồm cả giai đoạn 2, 3 **và bản nháp giai đoạn 4** (bài đăng,
thumbnail), để gói duyệt video chứa đủ mọi thứ sẽ đăng. `packaged` chỉ đóng băng
gói đã duyệt vào `publish/`.

Hai cổng `awaiting_medical_review` và `awaiting_video_review` là nơi duy nhất
pipeline dừng chờ người. Mọi chỗ khác agent tự đi tiếp.

### 5.1 Giai đoạn 1: Chủ đề và kịch bản

- **Tìm chủ đề** (người dùng chọn "miễn phí trước, trả phí sau"):
  YouTube Data API (tìm kiếm + bình luận video tiếng Việt), Google Trends,
  Reddit, và PubMed để thấy chủ đề có đủ bằng chứng. Mỗi gợi ý thành một
  **thẻ chủ đề** có: câu hỏi chính, tranh cãi/hiểu lầm phổ biến (kèm link nguồn
  thật đã thấy), độ hot ước lượng, lớp kiến thức sẽ giải thích (giải phẫu, sinh
  lý…). Không ghi "đang hot" nếu không có dữ liệu chứng minh.
- `local-deep-research` (LearningCircuit) là **tùy chọn** để đọc nền rộng;
  không thay ledger PubMed/Europe PMC.
- ScrapeCreators (trả phí) để sau: chỉ thêm khi người dùng yêu cầu soi sâu
  TikTok/Facebook.
- Người dùng **duyệt nhanh danh sách thẻ** rồi thả vào hàng đợi (đây không phải
  cổng y khoa; chỉ là chọn chủ đề). Người dùng cũng có thể tự thêm thẻ.
- **Nghiên cứu** (tự động): tìm bằng chứng → sàng lọc → ledger → explainer cơ
  chế. Gộp orientation cũ vào bước này.
- **Kịch bản** (tự động): script + storyboard + outline + clip plan theo
  explain-first, giọng người thường, châm biếm niềm tin chứ không châm biếm
  người; qua skill `humanizer`. Không có góc nhìn/trải nghiệm bác sĩ nào nếu
  người dùng chưa ghi trong thẻ.
- Kết thúc: `awaiting_medical_review` → người dùng duyệt hoặc từ chối kèm lý do.

### 5.2 Giai đoạn 2: Hình, giọng, nhạc

- **Hình mô phỏng có chú thích** (giải phẫu, mô học, cơ chế bệnh): component
  SVG phẳng chuyển động trong `video/src/anatomy/` theo palette brand. Mỗi chủ đề,
  agent dùng lại component có sẵn; nếu thiếu thì vẽ thêm component mới và đưa
  vào thư viện. Component mới phải có test layer/khung hình và luôn xuất hiện
  trong gói duyệt video (contact sheet) để bác sĩ soát đúng y khoa.
- **Minh họa không chú thích** (bối cảnh, ẩn dụ, thumbnail): FLUX.2 [klein] 4B
  chạy local (Apache-2.0, ~8 GB VRAM). Không dùng các bản 9B/dev (giấy phép
  phi thương mại). Ảnh AI **không bao giờ** mang nhãn giải phẫu hay số liệu.
- **Giọng**: VieNeu Thái Sơn, TTS từng dòng, căn thời gian có hash (đã có).
- **Nhạc nền**: ACE-Step 1.5 local tạo nhạc không lời theo tâm trạng chương,
  ducking dưới giọng đọc. Builder phải xác minh giấy phép **trọng số mô hình**
  (không chỉ mã nguồn MIT) cho phép dùng thương mại trước khi bật mặc định.

### 5.3 Giai đoạn 3: Dựng video

- Remotion (đã có): video dài 16:9 theo chương + cache, clip 9:16 từ cảnh đã
  duyệt (không crop, không lời mới), phụ đề tiếng Việt đủ dấu, mascot, thẻ cuối.
- QA tự động trước cổng video: lệch tiếng-hình, đuôi im lặng, layer y khoa, font.
- Kết thúc: `awaiting_video_review` → người dùng duyệt hoặc từ chối.
- Không dùng short-video-factory (AGPL, ghép footage có sẵn) và
  AI-Youtube-Shorts-Generator (clip đã cắt từ kịch bản duyệt, an toàn hơn).

### 5.4 Giai đoạn 4: Đóng gói đa kênh

- Bản nháp tạo trong `producing` và nằm trong gói duyệt video; sau
  `video_approved` chỉ đóng băng, không sinh lại. Gói `publish/` hiện có, thêm:
  - YouTube: tiêu đề (2–3 phương án), mô tả có chương + nguồn, tag, thumbnail.
  - Mỗi clip: caption TikTok, YouTube Shorts, Facebook Reels.
  - Bài Facebook dạng văn bản, bài YouTube Community.
- Tất cả sinh từ nội dung đã duyệt; không thêm claim mới. Một claim có số liệu
  trong bài đăng phải trỏ tới claim đã qua cổng y khoa.
- Người dùng tự đăng; đánh dấu `published_manual` khi xong.
- Không dùng social-media-agent (LangGraph, nhắm X/LinkedIn, nặng).

## 6. Hàng đợi và bộ chạy liên tục

- `topics/queue.yaml` (hoặc thư mục tương đương) liệt kê chủ đề theo thứ tự.
- Lệnh `healthvideo run`:
  1. Duyệt hàng đợi, chọn chủ đề tiếp theo **không** đang chờ cổng.
  2. Giao bước kế tiếp cho agent CLI hiện hành (Codex trước, hoặc theo cấu hình)
     với một prompt cố định cho giai đoạn đó.
  3. Nếu agent báo hết token/quota, chuyển sang agent còn lại và chạy lại bước đó.
     Nếu cả hai hết, dừng và báo.
  4. Khi chủ đề tới cổng, ghi lại và chuyển sang chủ đề kế.
  5. Dừng khi hàng đợi không còn việc tự động.
- `healthvideo status` (không đối số) in bảng toàn bộ chủ đề: giai đoạn, cổng
  đang chờ, đường dẫn gói duyệt. Người dùng duyệt theo lô từ bảng này.
- Mỗi bước phải chạy lại được an toàn (idempotent) vì agent có thể bị cắt giữa
  chừng.

**Phân việc Python / agent.** Python tự chạy mọi bước cố định: tìm PubMed/Europe
PMC, TTS, FLUX, ACE-Step, render Remotion, QA, đóng gói. Các mô hình GPU chạy lần
lượt do Python điều phối. Agent (Codex/agy) chỉ được gọi cho bước cần viết hoặc
phán đoán: chọn truy vấn tìm kiếm, sàng lọc, explainer, script/storyboard/outline/
clip plan, bài đăng, component SVG mới, sửa theo ghi chú từ chối. Mỗi lần gọi
agent là một bước nhỏ có đầu ra file xác định, để chạy lại được.

**Sau khi bị từ chối.** `run` coi `needs_revision` là việc tự động: agent sửa
theo ghi chú của bác sĩ rồi nộp lại cổng đó. Nếu sửa sau từ chối video đụng tới
nội dung đã duyệt y khoa (script, claim, explainer), logic invalidation có sẵn mở
lại cổng y khoa.

**Vai trò Claude** (người dùng chọn "chỉ rà code"). Nội dung (kịch bản, hình,
bài đăng) đi thẳng tới cổng của bác sĩ. Code mới hoặc sửa code repo (component
SVG trong `video/src/anatomy/`, sửa pipeline) do agent viết kèm test, chạy
test + lint, **không tự commit**: `run` để thay đổi trên một nhánh riêng và ghi
vào danh sách chờ rà. Claude rà và commit theo lô. Chủ đề dùng component mới vẫn
đi tới cổng video trên nhánh đó; component chỉ vào nhánh chính sau khi Claude
rà.

**Component đã duyệt.** Component SVG đã qua cổng video ở một chủ đề được tin
dùng lại cho chủ đề sau; component mới hoặc vừa sửa luôn có trong contact sheet
của gói duyệt video.

## 7. CLI đích (khoảng 12 lệnh)

```
healthvideo topic discover | add | list      # giai đoạn 1: tìm và quản lý thẻ
healthvideo run                              # chạy hàng đợi tới cổng
healthvideo status [project]                 # bảng tổng / chi tiết một chủ đề
healthvideo review open|approve|reject|reopen <project> --gate medical|video
healthvideo preview <project>                # Remotion Studio
healthvideo produce <project>                # chạy tay giai đoạn 2–3 nếu cần
healthvideo package <project>                # chạy tay giai đoạn 4 nếu cần
healthvideo doctor                           # kiểm cài đặt (FFmpeg, Node, VieNeu, GPU)
```

Các lệnh con evidence/draft nội bộ có thể giữ dưới một nhóm ẩn cho agent gọi;
builder quyết định.

Skill `/pyh` viết lại ngắn theo CLI mới, giữ nguyên quy tắc duyệt cổng.

## 8. Thứ tự thực hiện (đề xuất)

0. **Hoàn tất việc dở**: rà soát và commit bản sửa A/V sync/chart/motion/phụ đề
   đang chưa commit (25 file) trước khi cắt gì.
1. **Dọn rác + tài liệu**: xóa file rác ở gốc, `.gitignore`, gom skill, chuyển
   spec/plan cũ vào `docs/archive/`, README mới ngắn, cập nhật `CLAUDE.md` /
   `AGENTS.md` trỏ tới spec này thay cho spec 2026-09-07.
2. **Cắt code**: xóa các phần ở 4.2 cùng test của chúng; rút gọn state graph.
   Toàn bộ test còn lại phải xanh sau mỗi lát cắt.
3. **Hàng đợi + `run`** với Codex/agy luân phiên.
4. **Giai đoạn 2 mới**: FLUX.2 klein, ACE-Step, quy ước mở rộng thư viện SVG.
5. **Giai đoạn 1 mới**: `topic discover` từ nguồn miễn phí.
6. **Giai đoạn 4 mới**: bài đăng đa kênh + thumbnail.
7. **Chạy thật** một chủ đề từ đầu đến cuối qua `healthvideo run` (chủ đề thử,
   không đăng).

Bước 1–2 có thể giao agent khác chạy song song với nhau nếu không đụng cùng file.

## 9. Quyết định của Claude (người dùng chưa xác nhận)

- Bỏ bước xác nhận author brief riêng; quan điểm bác sĩ chỉ đến từ thẻ chủ đề
  hoặc ghi chú ở cổng y khoa.
- Project thí điểm `do-huyet-ap-khong-trieu-chung` là bản thử: không chuyển đổi,
  sẽ chạy lại theo luồng mới nếu cần.
- Giữ tên gói Python `healthvideo` và lệnh `/pyh`.
- Chọn chủ đề từ danh sách gợi ý là một bước duyệt nhẹ của người dùng, không
  phải cổng.
- Nhạc nền bật mặc định nếu giấy phép ACE-Step đạt.
- Python chạy bước cố định, agent chỉ làm bước viết/phán đoán (mục 6).
- `needs_revision` được `run` tự sửa và nộp lại; sửa đụng nội dung y khoa mở
  lại cổng y khoa.
- Bài đăng và thumbnail làm trước cổng video, nằm trong gói duyệt video.
- Component SVG đã duyệt được dùng lại; mới/sửa thì luôn hiện để duyệt.

## 10. Để lại cho builder

- Cấu trúc file/hàm cụ thể, schema hàng đợi, cách phát hiện "hết token" của từng
  agent CLI.
- Prompt cố định cho từng giai đoạn.
- Danh sách skill giữ lại trong `.agents/skills/`.
- Cách gom lệnh nội bộ evidence/draft.
- Cách ducking nhạc và mức âm lượng.
- Cách lấy dữ liệu Google Trends/YouTube/Reddit (API key nào, lưu ở `.env`).
