# Xưởng PYH như một công ty: dashboard, chat điều phối, thẻ quyết định, phân vai agent

Ngày: 2026-11-08. Bổ sung cho `2026-10-22-video-factory-restructure-design.md` và
`2026-10-25-factory-first-stage-acceptance-design.md`; không thay hai spec đó.

## 1. Ý định và lý do

Bác sĩ thấy xưởng hiện tại "vẫn hơi đơn giản" và tốn thời gian ở cổng duyệt.
Ba việc làm mất thời gian nhất:

- phải đọc lại cả gói duyệt dù agent đã kiểm phần lớn;
- muốn sửa một chỗ trong video phải nhắn qua phiên Claude Code thay vì làm ngay trên app;
- không thấy toàn cảnh: dự án nào đang ở đâu, ai đang làm, sản phẩm trông ra sao.

Mục tiêu là xưởng vận hành như một công ty: mỗi việc giao cho một vai (agent có skill riêng),
chạy ngầm qua CLI (`claude`, `codex`, `agy`), model chọn theo độ khó. Bác sĩ chỉ
xem sản phẩm, chat để sửa, và quyết **những điểm khó**.

## 2. Quyết định của người dùng

1. **Không vượt cổng, nhưng thiết kế lại cổng.** Hai cổng (y khoa, video) vẫn còn, vẫn cần PIN,
   agent không bao giờ tự duyệt. Bác sĩ "chỉ quyết những điểm khó thôi".
2. Kịch bản viết theo **văn phong châm biếm của bác sĩ**, sau đó **qua một agent duyệt**.
3. **Chat trực tiếp để sửa**: xem video chưa ưng chỗ nào thì chat vào đó yêu cầu sửa; có một
   **người điều phối chính** nhận lệnh.
4. **Trang chủ là dashboard trực quan**, theo dõi sản phẩm và tiến độ tổng quát.
5. Sản phẩm **xem trực quan ngay trên app** (như HyperFrames/Remotion).
6. **Mỗi nhiệm vụ một agent, agent có skill riêng**: tìm skill bằng `/find-skills`, dựng lại bằng
   `/reverse-engineer-anything`.
7. **Model theo độ khó**: việc nhiều mà dễ dùng model nhanh/rẻ, việc trung bình dùng model làm việc
   chính, việc khó dùng model mạnh nhất. Tên model người dùng đưa chỉ là ví dụ; xưởng tự chọn trong
   toàn bộ model có trên máy. **Hết token thì chuyển model.**
8. **Sau này** nối YouTube/TikTok để agent phân tích kết quả, điều chỉnh hướng làm cho viral hơn.
   Không thuộc đợt này.

## 3. Mục tiêu, không làm, phản mục tiêu

**Mục tiêu đợt này**
- G1. Bảng bậc model + bảng vai (vai → skill → bậc) trong một file cấu hình; bộ chạy dùng nó thay `STEP_AGENTS`.
- G2. Chuyển model khi hết token, nhớ model đang "nghỉ" tới giờ reset.
- G3. Mỗi vai có skill riêng trong repo, được nạp vào prompt của bước do vai đó làm.
- G4. Thẻ quyết định thay gói duyệt dài ở cả hai cổng.
- G5. Chat Điều phối viên trên app, gắn ngữ cảnh dự án/cảnh/mốc thời gian, tự xếp loại và giao việc.
- G6. Trang chủ dashboard mới + trang xem sản phẩm có trình xem video và dải cảnh.

**Không làm đợt này**
- Nối API YouTube/TikTok, agent phân tích xu hướng (giai đoạn 2). Chỉ chừa một ô "Kết quả kênh — chưa kết nối".
- Đổi đồ thị trạng thái `WorkflowState`, đổi định dạng ledger/script/render input.
- Tự đăng bài.

**Phản mục tiêu (làm xong mà dính một điều dưới đây là hỏng)**
- Bất kỳ đường nào cho agent hoặc chat tự duyệt cổng, đặt PIN, ghi file approval.
- Chat sửa claim y khoa mà không quay lại khâu kịch bản và cổng y khoa.
- Thẻ quyết định dài như gói duyệt cũ, hoặc hỏi bác sĩ những thứ agent đã kiểm ổn.
- Việc dễ (caption, bài đăng, quét chủ đề) chạy model bậc khó; hoặc hết token làm dự án bị `blocked`.
- Agent chấm điểm trùng agent/phiên làm ra sản phẩm.

## 4. Ràng buộc

- Toàn bộ quy tắc trong `CLAUDE.md` giữ nguyên (không bịa nguồn, không vượt cổng, không lưu
  key/render/cache vào Git, `pathlib.Path`, test + lint trước commit, cập nhật bảng tiến độ README).
- `HARD_RULES` trong `runner.py` giữ nguyên và vẫn nối cuối mọi prompt bước.
- Dashboard vẫn là server Python localhost (`dashboard.py`, `ThreadingHTTPServer`), PIN không bao giờ
  lưu, log hay chuyển cho agent.
- Windows + PowerShell; mọi CLI gọi qua `prepare_subprocess_argv`/`child_env` như hiện tại.

## 5. Thiết kế

### 5.1 Bậc model và bảng vai: `profiles/company.yaml`

Một file, đọc bằng pydantic (`extra='forbid'`). Hai phần: **bậc** (chuỗi model theo thứ tự thử)
và **vai** (bước nào, skill nào, bậc nào; được ghi đè chuỗi riêng khi cần).

Model có trên máy (tra ngày 2026-11-08: `~/.codex/models_cache.json`, `agy models`, `claude --model`):

| Bậc | Dùng cho | Chuỗi mặc định (*Claude chọn*) |
|---|---|---|
| `hard` | nghiên cứu, viết kịch bản, chấm kịch bản/sản phẩm | claude `claude-opus-5-5` → codex `gpt-6-astra` → agy `claude-opus-5-5-high` → codex `gpt-6.1-sol` |
| `medium` | điều phối, dựng video, đạo diễn hình, phân tích ý kiến | claude `claude-sonnet-5-5` → codex `gpt-6.1-sol` → agy `gemini-4-argon-medium` → codex `gpt-6.1-terra` |
| `bulk` | việc nhiều mà dễ: bài đăng, quét chủ đề, tóm tắt log | claude `claude-haiku-5-5` → codex `gpt-6-luna` → agy `gemini-3.8-flash-medium` → codex `gpt-6.1-terra` |

```yaml
tiers:
  hard:   [{cli: claude, model: claude-opus-5-5}, {cli: codex, model: gpt-6-astra}, ...]
  medium: [...]
  bulk:   [...]
roles:
  writer:
    name: Biên kịch
    skill: .agents/skills/pyh-writer/SKILL.md
    steps: [draft, revise_medical]
    tier: hard
  script_critic:
    name: Kiểm duyệt kịch bản
    steps: [script_review]
    tier: hard
    models:   # ghi đè: bắt đầu từ nhà cung cấp khác với biên kịch
      - {cli: codex, model: gpt-6-astra}
      - {cli: agy, model: claude-opus-5-5-high}
      - {cli: claude, model: claude-opus-5-5}
```

Bảng vai khởi đầu (*Claude chọn*):

| Vai (id) | Bước / việc | Bậc | Ghi đè |
|---|---|---|---|
| Điều phối viên (`coordinator`) | chat | medium | |
| Trinh sát chủ đề (`scout`) | đề xuất chủ đề vào hàng đợi | bulk | |
| Nhà nghiên cứu (`researcher`) | `research` | hard | |
| Biên kịch (`writer`) | `draft`, `revise_medical` | hard | |
| Kiểm duyệt kịch bản (`script_critic`) | `script_review` | hard | bắt đầu từ codex `gpt-6-astra` |
| Đạo diễn hình (`art_director`) | `visual_review` | medium | bắt đầu từ agy `gemini-4-argon-high` (nhìn ảnh tốt) |
| Thợ dựng (`editor`) | `revise_production`, `revise_product`, sửa cảnh từ chat | medium | bắt đầu từ agy `gemini-4-argon-medium` (quen repo video) |
| Kiểm định sản phẩm (`product_critic`) | `product_review` | hard | |
| Viết bài đăng (`copywriter`) | `posts` | bulk | |
| Phân tích ý kiến (`feedback_analyst`) | `feedback_inbox` | medium | |

Quy tắc kiểm khi nạp file (test):
- mỗi `AGENT_STEPS` có đúng một vai;
- vai chấm (`script_critic`, `product_critic`) không được có mục đầu tiên trùng (cli, model) đầu tiên
  của vai làm ra sản phẩm nó chấm (`writer`, `editor`). Phiên CLI luôn mới, nên trùng ở mục dự phòng được phép;
- mọi `cli` thuộc {claude, codex, agy}.

`AgentCli` đổi thành nhận model lúc gọi: cờ model của từng CLI (`claude --model`, `codex -m`,
`agy --model`) được chèn từ mục trong chuỗi, thay vì cố định trong `agents.py`. `STEP_AGENTS`
và `DEFAULT_AGENTS` bị thay bằng tra bảng vai. Đổi model chỉ cần sửa file này (hoặc bảo Điều phối viên
qua chat, nó ghi qua `factory_feedback` để Claude sửa, không tự sửa).

### 5.2 Hết token: chuyển và cho model "nghỉ"

- Giữ `invoke_with_failover` và `QUOTA_PATTERNS`. Khi một mục (cli, model) dính quota, ghi vào
  `cache/agent-quota.yaml`: `{cli, model, resting_until, reason}`. `resting_until` lấy từ thông điệp
  lỗi nếu CLI có in giờ reset; không có thì mặc định +5 giờ (*Claude chọn; builder chỉnh được*).
  Quota tính theo tài khoản CLI, nên dính quota ở một model của `codex` thì chỉ model đó nghỉ, trừ khi
  thông điệp nói rõ cả tài khoản hết lượt; khi đó mọi mục cùng `cli` nghỉ.
- Lần gọi sau bỏ qua mục đang nghỉ. Hết cả chuỗi thì chỉ việc đó tạm dừng (không `blocked`), dashboard
  hiện "chờ model", và xưởng thử lại khi mục sớm nhất hết nghỉ. Dự án và bậc khác vẫn chạy tiếp: `run_queue`
  không còn dừng cả hàng đợi khi một chuỗi hết (*Claude chọn*; thay hành vi hiện tại của `AllAgentsExhausted`).
- `invoke_with_failover` nhận thêm `role`, `slug`, `step` để ghi activity và quota.
- Dashboard hiện danh sách model đang nghỉ và giờ trở lại.

### 5.3 Skill của từng vai

- **Không tự viết skill** (*người dùng đổi ý 2026-11-08*): dùng skill công khai có sẵn, tìm bằng `/find-skills`
  (skills.sh / GitHub), cài bằng `npx skills add <owner/repo> -s <skill> --copy -a codex claude-code` vào
  `.agents/skills/` (ghi trong `skills-lock.json`), cộng với skill đã có trong repo. Mỗi vai có danh sách
  `skills` (0–3 đường dẫn).
- Gán ban đầu (đã cài và rà nội dung 2026-11-08):

  | Vai | Skill |
  |---|---|
  | coordinator | — |
  | scout | `content-strategy` (coreyhaines31/marketingskills, 173K lượt cài) |
  | researcher | `systematic-literature-review` (bytedance/deer-flow) |
  | writer | `youtube-scriptwriting` (cdeistopened/skill-stack), `short-form-video` (iart-ai/tiktok-video-skills) |
  | script_critic | `copy-editing` (coreyhaines31/marketingskills) |
  | art_director | `scripting-and-storyboarding` (social-media-skills/skills), `visual-style` |
  | editor | `remotion-best-practices`, `motion-design` |
  | product_critic | `video-understand`, `character-animation-qa` |
  | copywriter | `social` (coreyhaines31/marketingskills) |
  | feedback_analyst | — |

- Skill công khai dài (100–500 dòng) và viết cho tiếng Anh/marketing, nên **không chép vào prompt**:
  `render_prompt` thêm khối `## Skill của vai: <tên>` liệt kê đường dẫn SKILL.md, dặn agent đọc trước khi làm,
  áp dụng phần hợp với kênh sức khoẻ tiếng Việt, và khi skill mâu thuẫn với prompt bước hay quy tắc cứng thì
  prompt bước và quy tắc cứng thắng. Khối này nằm trước "Quy tắc cứng"; test kiểm quy tắc cứng luôn nằm cuối.
- Skill bên ngoài là dữ liệu không tin cậy: trước khi gán, Claude rà nội dung (script, lệnh mạng, chỉ dẫn
  lạ). Cập nhật skill (`npx skills update`) cũng phải rà lại trước khi commit.

### 5.4 Thẻ quyết định (cổng y khoa và cổng video)

**Agent duyệt ghi thêm "điểm khó".** `script-review.yaml` và báo cáo `product_review` có thêm
(ví dụ minh hoạ, không phải số liệu thật):

```yaml
checked:            # những gì agent đã kiểm và thấy ổn, mỗi mục một dòng
  - "28/28 claim khớp ledger"
  - "Không còn dấu hiệu văn AI (style-lint sạch)"
decisions:          # chỉ điều agent không được phép hoặc không đủ chắc để tự quyết
  - id: D1
    where: N14        # id dòng kịch bản, hoặc S07@03:12 với video
    question: "Hai nguồn trong ledger nêu ngưỡng khác nhau; câu này nói theo nguồn nào?"
    why_hard: "Ledger có 2 claim mâu thuẫn ở nhóm bệnh nhân đặc biệt"
    options:
      - {id: a, label: "Nói ngưỡng chung", effect: "Câu ngắn, bỏ ngoại lệ", recommended: true}
      - {id: b, label: "Nói ngưỡng chung + ngoại lệ", effect: "Thêm 1 câu, chính xác hơn"}
      - {id: c, label: "Giữ nguyên câu hiện tại", effect: "Không đổi gì", keep: true}
```

Mỗi phương án trỏ tới claim có trong ledger; agent không được đưa số liệu không có trong ledger vào phương án.
`decisions` chỉ dành cho: nguồn mâu thuẫn hoặc không chắc, claim gần ranh giới lời khuyên điều trị,
câu châm biếm có thể bị hiểu nhầm, hình có thể sai giải phẫu, và những gì bác sĩ đã dặn phải hỏi.
Mọi thứ khác agent tự sửa qua vòng sửa hiện có (`next_script_action`, `next_product_action`) trước khi
lên cổng. Mỗi điểm luôn có một phương án `keep: true`. Tối đa 5 điểm mỗi thẻ: nhiều hơn thì coi như chưa đạt, quay
lại vòng sửa; nếu đã hết số vòng (`MAX_REVIEWS`) thì vẫn lên thẻ, 5 điểm nặng nhất đứng đầu, kèm một dòng "còn N
điểm nhỏ hơn, xem chi tiết".

**Đếm vòng theo từng lần nộp.** `script_review` đếm vòng theo từng chu kỳ nộp, giống `product_review`
(`submitted`). Sau mỗi lần cổng gửi sửa hoặc chat yêu cầu sửa, vòng mới bắt đầu, nên agent duyệt luôn kiểm lại
bản đã sửa trước khi lên thẻ.

**Thẻ trên app.** Mỗi thẻ có:
- tiêu đề + nút xem sản phẩm (kịch bản hoặc video, mở đúng `where`);
- dòng "Agent đã kiểm" (thu gọn, bấm để mở `checked`);
- từng điểm khó: câu hỏi, lý do khó, các phương án có `effect`, phương án khuyến nghị chọn sẵn;
- ô "ý khác" tự do;
- một ô PIN và một nút.

**Luồng (*Claude chọn*):**
- Mọi điểm chọn phương án `keep`, ô "ý khác" trống (hoặc thẻ không có điểm khó) → nút là **Duyệt** → PIN →
  gọi `approve_gate` như hiện tại; lựa chọn được ghi kèm vào file approval.
- Có điểm chọn phương án không `keep`, hoặc có "ý khác" → nút là **Gửi sửa theo lựa chọn** → PIN → gọi
  đường reject/reopen hiện có với `reason` dựng từ các lựa chọn. Vai biên kịch (hoặc thợ dựng) sửa,
  agent duyệt kiểm lại, thẻ quay về chỉ còn "Đã sửa theo D1=b · agent kiểm ✓" → Duyệt + PIN.
- Gói duyệt cũ (`review_html.py`) vẫn mở được từ thẻ ("xem chi tiết") nhưng không còn là đường chính.

### 5.5 Chat Điều phối viên

**Giao diện.** Ô chat cố định bên phải mọi trang. Trên trang dự án, mỗi tin tự kèm ngữ cảnh
`{slug, revision, view: video|script|evidence|storyboard, scene, time_s}` lấy từ trình xem đang mở.

**Lưu trữ.** `projects/<slug>/chat.jsonl` cho chat trong dự án; `topics/chat.jsonl` cho chat chung.
Mỗi dòng: `{id, at (ISO 8601 có múi giờ, vd. 2026-11-08T17:05:00+07:00), who: doctor|coordinator,
text, context, action?, status: pending|done|failed}`.

**Điều phối viên.** Mỗi tin của bác sĩ chạy vai `coordinator` qua CLI, trong một luồng nền (giống cách
`feedback_inbox` đang chạy; một Điều phối viên chạy mỗi lúc cho cả app, tin khác xếp hàng). Đầu vào: tin nhắn, ngữ cảnh, trạng thái
dự án, 20 tin gần nhất, trích đoạn liên quan (dòng kịch bản / cảnh trong render input). Đầu ra bắt buộc là
YAML, được kiểm bằng pydantic:

```yaml
reply: "Câu trả lời ngắn cho bác sĩ"
action: none | ask | edit_production | edit_script | queue_topic | factory_feedback | status
brief: "Mô tả việc cho vai nhận, đủ để làm không cần hỏi lại"   # bắt buộc trừ none/ask/status
options: [...]   # chỉ khi action=ask: 2–3 phương án, mỗi cái có label + effect
```

Python, không phải agent, thực hiện `action`:
- `edit_production`: sửa hình, chữ trên màn, nhịp, âm thanh, không đụng lời đọc hay claim. Mở lại dự án về
  khâu dựng qua đường reopen hiện có (`RESUME_TARGETS`), `reason` = `brief` + ngữ cảnh cảnh/mốc. Vai thợ dựng
  làm. Video lại qua `product_review` rồi lên cổng video bằng thẻ.
- `edit_script`: đụng lời đọc hoặc claim. Mở lại về `DRAFT_READY` với `brief` → biên kịch sửa → kiểm duyệt
  → cổng y khoa bằng thẻ. Không có đường tắt.
- `queue_topic`: thêm vào `topics/queue.yaml` bằng hàm hàng đợi hiện có.
- `factory_feedback`: góp ý về chính xưởng; ghi `brief` thẳng vào `topics/feedback.yaml` thành mục
  `status: ready` (không chạy lại agent phân tích, Điều phối viên đã phân tích). Tab "Ý kiến" cũ gộp vào chat.
- `status` / `none`: chỉ trả lời.
- `ask`: hiện phương án thành nút bấm trong chat; bấm = gửi tin trả lời.

**Yêu cầu sửa (code mới, chưa có sẵn).** Đường reopen hiện có (`reject_gate`, `reopen_project`) chỉ chạy ở
cổng và cần danh sách file đã đổi, nên không dùng được cho chat. Thêm một hàm `request_change(project, kind,
brief, context)`:
- ghi `revisions/<rev>/reviews/changes/<ts>-requested.yaml` (`{at, by: doctor-chat, kind, brief, context}`);
- chuyển trạng thái trong đồ thị hiện có (`state_graph.py`):
  - `edit_production` ở `PRODUCTION_IN_PROGRESS` / `AWAITING_VIDEO_REVIEW` / `VIDEO_APPROVED` / `PACKAGED` →
    `NEEDS_PRODUCTION_REVISION`;
  - `edit_script` trước cổng y khoa (research, `EVIDENCE_READY`, `DRAFT_READY`): giữ trạng thái, chỉ gắn `brief`;
    nếu ở `DRAFT_READY` thì xoá kết quả script review của lần này để vòng biên kịch → kiểm duyệt chạy lại;
  - `edit_script` ở `AWAITING_MEDICAL_REVIEW` hoặc sau khi đã duyệt y khoa → `NEEDS_MEDICAL_REVISION`
    (bỏ hiệu lực duyệt y khoa, như reopen hiện tại);
- `reject_note` trong `factory_deps.py` đọc thêm yêu cầu sửa mới nhất chưa xử lý, để `brief` tới được biên kịch/thợ dựng.

Chat hiện nút xác nhận "Mở lại để sửa?" trước khi Python gọi `request_change`. **Không cần PIN**, kể cả khi
việc này bỏ hiệu lực duyệt y khoa (*quyết định của người dùng 2026-11-08*): mở lại chỉ huỷ duyệt, không duyệt gì,
và bản sửa vẫn phải qua cổng có PIN.
**Xưởng đang chạy:** yêu cầu được xếp hàng (`status: pending`); runner kiểm yêu cầu đang chờ của dự án trước khi
chọn bước kế tiếp và áp dụng nó giữa hai bước, không bao giờ trong lúc một agent đang làm dự án đó (*Claude chọn*).
Nếu Điều phối viên không chắc
một yêu cầu là sửa hình hay sửa lời/claim, nó phải chọn `edit_script` hoặc `ask`. Test: yêu cầu đổi số liệu
không bao giờ ra `edit_production` (Python kiểm thêm: `edit_production` có `brief` nhắc tới id dòng kịch bản
hoặc claim thì đổi thành `edit_script`). Điều phối viên chỉ đọc file và ghi báo cáo đầu ra, không sửa project.

Khi việc giao xong (trạng thái dự án đi tiếp), runner ghi một tin `coordinator` vào chat: "Đã sửa S07,
xem lại" kèm link tới đúng cảnh/mốc.

### 5.6 Trang chủ dashboard

Từ trên xuống:
1. **Ô số liệu**: dự án đang chạy; chờ bác sĩ quyết; video xong 7/30 ngày; thời gian trung bình
   chủ đề → video; số model đang nghỉ.
2. **Dải "Cần bạn quyết"**: mỗi thẻ quyết định một chip, bấm mở thẻ.
3. **Thẻ dự án**: ảnh xem trước (thumbnail render nếu có, không thì khung storyboard, không thì icon
   khâu), tên, thanh 7 khâu, trạng thái chữ ("đang dựng S07 · Thợ dựng · gemini-4-argon-medium").
4. **"Công ty đang làm gì"**: mỗi việc đang chạy và 10 việc gần nhất: vai, cli/model, dự án, bước,
   thời lượng, kết quả. Nguồn: file mới `topics/logs/activity.jsonl`, do `invoke_with_failover` ghi một
   dòng lúc bắt đầu và một dòng lúc kết thúc (`{at, role, cli, model, slug, step, event: start|end|quota, ok}`).
5. **Kết quả kênh**: ô trống "Chưa kết nối YouTube/TikTok" (giai đoạn 2).
6. Các chức năng đang có (bật/tắt xưởng, hàng đợi, tiêu chuẩn, thử nghiệm, log) chuyển vào menu/trang
   phụ, không mất.

### 5.7 Trang xem sản phẩm

- Tab theo khâu: **Nguồn** (ledger), **Kịch bản** (dòng + điểm của agent duyệt), **Storyboard** (khung
  hình đã có từ `review_frames`), **Video**, **Nhật ký** (activity + chat của dự án).
- **Video**: thẻ `<video>` phát MP4 render mới nhất, server hỗ trợ HTTP Range để tua. Bên dưới là dải
  cảnh lấy thời điểm từ render input; bấm cảnh để tua tới đó. Cảnh có yêu cầu sửa đang mở được tô màu.
  Thời điểm và cảnh đang phát được đưa vào ngữ cảnh chat.
- **Xem trước khi render xong** (*Claude chọn*): nút "Mở Remotion Studio" chạy studio của `video/` một lần
  (qua `resolve_pnpm_argv`, output ghi ra file log vì Remotion treo pipe trên Windows), rồi mở trong tab mới.
  Không đóng gói `@remotion/player` vào dashboard; dashboard giữ dạng HTML/JS thuần, không có bước build.

## 6. Thứ tự thực hiện (đề xuất)

1. Bậc model + bảng vai + model theo lần gọi + cho model nghỉ (5.1, 5.2). Nền cho mọi thứ khác.
2. Nhật ký activity (5.6 mục 4). Nhỏ, làm sớm để thấy các bước sau chạy ra sao.
3. Skill từng vai (5.3).
4. Thẻ quyết định: schema reviewer, prompt, luồng duyệt/gửi sửa (5.4).
5. Chat Điều phối viên: backend + action (5.5).
6. Dashboard mới: trang chủ, trang sản phẩm, thẻ, chat UI (5.6, 5.7).
7. Nghiệm thu: test, lint, chạy app thật với một dự án có sẵn (gout): chat sửa một cảnh, một
   thẻ quyết định có điểm khó, và giả lập hết quota.

## 7. Quyết định của Claude (người dùng chưa xác nhận)

- Ba bậc model, chuỗi mặc định, phân vai và ghi đè trong 5.1.
- Thời gian nghỉ mặc định +5 giờ khi CLI không in giờ reset.
- Luồng thẻ: chọn phương án làm đổi nội dung thì gửi sửa, rồi duyệt lại bằng thẻ ngắn; tối đa 5 điểm/thẻ.
- Chat không chắc thì đi đường kịch bản; mở lại dự án cần bấm xác nhận.
- Trình xem dùng MP4 + dải cảnh + nút Remotion Studio, không đóng gói Remotion Player vào dashboard.
- Gộp tab "Ý kiến" vào chat; `factory_feedback` ghi thẳng mục `ready`, không phân tích lại.
- Hàm mới `request_change` thay vì mượn đường reopen ở cổng; yêu cầu sửa xếp hàng khi xưởng đang chạy, áp dụng giữa hai bước.
- Hết chuỗi model chỉ dừng việc đó, không dừng cả hàng đợi.
- `script_review` đếm vòng theo từng lần nộp.

## 8. Để lại cho builder

- Cấu trúc file trong dashboard (tách `dashboard.html` thành vài file JS/CSS tĩnh hay giữ một file).
- Cách chèn cờ model cho từng CLI và cách đọc giờ reset từ thông điệp lỗi.
- Bố cục và màu chi tiết, miễn giữ thứ tự mục ở 5.6 và chạy được trên màn hình laptop.
- Cách tính "thời gian trung bình chủ đề → video" từ dữ liệu sẵn có.
