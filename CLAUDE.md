# Hướng dẫn tác nhân

Agent đang chạy **một bước của xưởng** (prompt có mục "Quy tắc cứng"): chỉ áp dụng mục 1
dưới đây và làm đúng bước được giao, bỏ qua các mục còn lại.

## 1. Quy tắc cứng

1. Không bịa nguồn, DOI, PMID, số liệu, kết quả nghiên cứu, hoặc trải nghiệm của bác sĩ.
2. Không vượt cổng duyệt y khoa hoặc cổng duyệt video; không tự động xuất bản. PIN chỉ bác
   sĩ gõ trong app hoặc TTY của mình; agent không nhận PIN qua chat, tham số, biến môi
   trường hay file.
3. Không lưu API key, audio tạm, render, cache hay toàn văn có bản quyền vào Git. Không in
   nội dung `.env`.
4. Dùng `pathlib.Path` cho đường dẫn nội bộ.
5. Chạy test liên quan và lint trước commit.
6. `profiles/doctor-feedback.yaml` và `profiles/factory-standards.yaml` chỉ thêm, không
   sửa hay xóa mục cũ.
7. NCBI đang chặn IP máy này: dùng Europe PMC, không tìm cách lách.

## 2. Dự án là gì, đang ở đâu (2026-11-11)

Xưởng làm video y khoa tiếng Việt: mỗi chủ đề ra 1 video YouTube 16:9 dài 10–25 phút, 1–6
clip dọc 9:16 và bộ bài đăng. Xưởng chạy tự động bằng agent CLI, dừng ở hai cổng duyệt của
bác sĩ, bác sĩ tự đăng. Cách dùng: `README.md`. Thiết kế hiện hành:
`docs/superpowers/specs/2026-11-08-factory-company-design.md` (đọc trước khi đổi workflow
hoặc schema). Bản đánh giá đầy đủ: `docs/superpowers/plans/2026-11-11-completion-plan.md`.

Xưởng đã đủ chức năng nhưng chưa video thật nào qua cổng duyệt video. Từ giờ tới khi video
gout được duyệt: **không thêm tính năng xưởng**, chỉ sửa thứ gout đang vấp và xóa thứ thừa.

Số liệu kiểm ngày 2026-11-11 trên `master` `7ad3cc4`: pytest 1800 đạt, 1 bỏ qua; Ruff sạch;
Vitest 251 đạt; `tsc` sạch. `gout-tinh-the-urat` ở `needs_medical_revision`;
`gan-nhiem-mo-test` đã `packaged` (bản thử). Xưởng nền không chạy.

## 3. Vai trò và cách làm việc

Claude là **dev lead**: lập brief, giao việc, đọc diff, chạy test, commit. Claude không tự
viết code tính năng; chỉ tự sửa khi thay đổi dưới khoảng 30 dòng hoặc là tài liệu/cấu hình.
Hai nhân viên:

| Nhân viên | Model | Giao việc gì |
| --- | --- | --- |
| `agy` | `gemini-4-carbon-high` | Giao diện app (`dashboard.html`), Remotion/TypeScript, xóa code hàng loạt, việc cần nhìn ảnh hay khung hình |
| `agy` | `gemini-4-carbon-medium` | Tài liệu, sửa nhỏ, việc lặp |
| `codex` | `gpt-6.1-sol` | Dự phòng khi Carbon làm sai hai vòng liền (bác sĩ 2026-11-12: dùng model vừa phải, không dùng Opus hay astra) |
| `codex` | `gpt-6.1-sol` | Python có bất biến cần giữ: cổng duyệt, hash, timing, retry, storage |

`gemini-4-carbon` có từ 2026-11-11, đã thử chạy headless được. Việc đầu tiên giao cho nó
phải đọc diff kỹ hơn thường lệ. Trong xưởng, `profiles/company.yaml` đã dùng
`gemini-4-carbon-medium` đầu bậc `medium` và `gemini-4-carbon-high` cho vai Đạo diễn hình;
vai `editor` còn `gemini-4-argon-medium`. Nếu Carbon cho kết quả kém Argon ở một vai, đổi
lại đúng dòng đó. Không dùng `gpt-6-astra` (tốn token).

Lệnh giao việc (chạy từ PowerShell, trong worktree của việc đó, chạy nền):

```powershell
agy -p "Đọc và làm đúng theo file <đường dẫn brief.md>" --model gemini-4-carbon-high --mode accept-edits --print-timeout 0s
agy -c -p "<yêu cầu sửa>" --model gemini-4-carbon-high --mode accept-edits --print-timeout 0s
Get-Content -Raw <brief.md> | codex exec -m gpt-6.1-sol --dangerously-bypass-approvals-and-sandbox -
```

Quy trình mỗi việc:

1. Sửa `docs/progress.yaml` **ở checkout chính** (`E:\Protect Your Health`): việc đó thành
   `status: doing`, ghi `owner` và `note` một câu đang làm gì, đổi `updated`. Commit thẳng
   lên `master` với message `chore: progress`. App đọc file này nên bác sĩ thấy ngay.
2. Tạo worktree và nhánh riêng. Viết brief tự đủ: file cần sửa, tiêu chí xong, lệnh test,
   "không commit", "không đụng file ngoài danh sách". Lưu brief ở scratchpad.
3. Hai nhân viên không bao giờ sửa cùng một file cùng lúc. P1 (codex) và P3 (agy) chạy
   song song được vì khác file.
4. Nhân viên xong: Claude đọc toàn bộ diff, chạy test. Sai thì gửi lại cho đúng nhân viên
   đó, gom mọi lỗi vào một vòng sửa. Không tự vá.
5. Đạt: commit (`git add` từng đường dẫn, không `-A`), squash-merge vào `master`, sửa
   `docs/progress.yaml` thành `done`. Push cần bác sĩ đồng ý mỗi lần.

Lệnh kiểm (trong worktree dùng Python của checkout chính):

```powershell
$env:PYTHONPATH='src'; & 'E:\Protect Your Health\.venv\Scripts\python.exe' -m pytest -q
& 'E:\Protect Your Health\.venv\Scripts\python.exe' -m ruff check src tests tools
```

Test video chạy ở checkout chính: `video\node_modules\.bin\vitest run` và
`video\node_modules\.bin\tsc --noEmit` (sau việc 0.3 thì dùng `pnpm --dir video test`).
Đừng chạy pytest cùng lúc với Vitest: một test dựng Remotion thật sẽ quá giờ.

Với bác sĩ: không đưa lệnh PowerShell nhiều tham số, mọi thao tác qua app. Khi cần bác sĩ
quyết, đưa 2–3 phương án trả lời sẵn, phương án đề xuất đứng đầu. Đầu phiên đọc
`topics/feedback.yaml` ở checkout chính: mục `status: ready` là việc bác sĩ gửi qua tab Ý
kiến; báo cho bác sĩ, xử lý, rồi đổi thành `status: done`.

Worktree mới của Claude Code được cắt từ `origin/main`. Nếu `master` chưa push thì worktree
sẽ thiếu code mới: chạy `git merge --ff-only master` ngay đầu phiên.

## 4. Kết cấu: chỗ chưa hợp lý

Đo ngày 2026-11-11: 22.199 dòng Python, 26.456 dòng test, 8.789 dòng TypeScript.

| # | Vấn đề | Xử lý |
| --- | --- | --- |
| K1 | Bộ kiểm bố cục phụ thuộc thời lượng giọng thật chỉ chạy sau cổng y khoa; gout hỏng `produce` liên tiếp ngày 2026-11-07, mỗi lần bác sĩ phải mở lại cổng | P1 |
| K2 | Khu nghiệm thu 4 giai đoạn đã bỏ từ 2026-11-07 nhưng còn nguyên: `factory_trials.py` (655 dòng), `factory_standards.py`, tab "Nghiệm thu chuẩn", khoảng 175 dòng trong `dashboard.html`, một test dựng Remotion thật hay quá giờ | Việc 3.1 |
| K3 | `tts/elevenlabs.py` còn dù bác sĩ đã từ chối giọng này; `tts/asr.py` không module nào trong `src` import | Việc 3.2 |
| K4 | `.agents/skills/` có 30 skill (3,2 MB); `profiles/company.yaml` chỉ dùng 12, cộng `pyh` | Việc 3.3 |
| K5 | Tiến độ ghi ở ba nơi: bảng 85 dòng trong `README.md`, `docs/HANDOFF.md` (cũ từ 2026-10-27), checkbox trong các plan | Việc 3.4: chỉ còn `docs/progress.yaml` |
| K6 | 12 worktree, 12 nhánh chưa merge (đã squash-merge hoặc là hướng đã bỏ); `master` đi trước `origin/main` 88 commit | Việc 0.2, 3.5 |
| K7 | Bác sĩ có ba đường góp ý: ghi chú từng dòng ở cổng, tab Ý kiến (`feedback_inbox.py`), chat Điều phối viên (`chat.py`) | Việc 3.6: gộp Ý kiến vào chat |
| K8 | `pnpm` không có trên máy (Node 26 không kèm Corepack) nên đường dựng sản xuất không gọi được Remotion | Việc 0.3 |

Cố ý **không** làm, đừng đề xuất lại:

- Không tách `dashboard.html` (1.719 dòng), `dashboard.py`, `produce.py`, `cli.py` thành
  nhiều file. Chúng chạy được; tách chỉ thêm rủi ro. Sau việc 3.1 chúng tự ngắn lại.
- Không gộp `factory.py`, `runner.py`, `factory_deps.py`; không gộp ba agent chấm
  (`script_review`, `visual_review`, `product_review`): mỗi cái một giai đoạn.
- Không xóa nhánh `legacy` hay code đọc project cũ trong `domain/`: rủi ro hỏng hash của
  project đang có, lợi ích nhỏ.
- Không dựng framework frontend, không thêm dependency cho app.

## 5. Kế hoạch chi tiết

Thứ tự: P0 trước. Sau đó P1 (codex) và các việc 3.1–3.4 (agy) chạy song song. P2 cần P0 và
P1. Việc 3.5, 3.6 và P4 sau P2.

### P0 — Giữ an toàn dữ liệu và môi trường (Claude tự làm)

- **0.1** Ở checkout chính: `git add profiles/doctor-feedback.yaml
  profiles/factory-standards.yaml`, commit `chore: record doctor feedback and standards`.
  Xong khi `git status` không còn hai file này.
- **0.2** Hỏi bác sĩ rồi merge nhánh `claude/project-review-plan-a5df66` vào `master` và
  `git push origin master:main`. Xong khi `git rev-list --count origin/main..master` in 0.
- **0.3** Hỏi bác sĩ rồi chạy `npm i -g pnpm@11`. Xong khi `healthvideo doctor` in
  `OK pnpm`. Nếu bác sĩ không muốn cài toàn máy: giao codex sửa `process.py` gọi thẳng
  `video/node_modules/@remotion/cli/remotion-cli.js` bằng `node`, như
  `factory_trials.py` dòng 554 đang làm.
- **0.4** Thêm dòng `.remotion/` vào `.gitignore`. Hỏi bác sĩ `New Recording.m4a` và
  `api-docs.zip` ở gốc repo là gì; nếu cần giữ thì chuyển vào `cache/` (đã ignore). Xóa
  thư mục thừa `.worktrees/preventive-health-video-mvp` (không phải worktree) và các thư
  mục chỉ còn `__pycache__`: `src/healthvideo/jev`, `src/healthvideo/video_ai`.
- **0.5** Tắt app đang chạy, mở lại bằng lối tắt Desktop "Xưởng video". Xong khi trang chủ
  có mục "Tiến độ hoàn thiện xưởng".

### P1 — Bắt lỗi bố cục trước cổng y khoa (codex, một brief, một nhánh)

Mục tiêu: storyboard đã qua `step submit-medical` thì `produce` không hỏng vì thời lượng.

Bốn lỗi cần bắt, và nơi ném lỗi hiện nay:

| Lỗi của gout | Nơi ném |
| --- | --- |
| `visual budget failed: chart_crop=2485/9858 frames outside 15-25%` | `domain/visual_budget.py:212` |
| `Scene S02: beat at 10.0 outside timed scene` | `render/beats.py:24` |
| `Scene S03: front-loaded entrances all within first 15%` | `render/word_timing.py:72` (`entrance_timing_qa`) |
| `CL02: duration 1243 frames must be between 1800 and 5400` | `domain/clip_plan.py:76`, `render/input.py:74` |

- **1.1** Hàm ước lượng thời lượng mỗi dòng lời đọc từ số ký tự. Tốc độ (ký tự/giây) lấy
  từ các WAV đã cache của đúng giọng trong `profiles/voice.yaml` (xem
  `workflows/produce.py::_synthesize_cached_line` và `audio/tts-usage.json`); chưa có
  cache thì dùng hằng số đo từ gout và ghi rõ trong code. Xong khi sai số trên gout ≤ 10%
  mỗi cảnh, có test.
- **1.2** `commands/operator.py::submit_medical` dựng timing ước lượng rồi gọi đúng các
  hàm kiểm ở bảng trên (dùng lại, không viết bản thứ hai), với biên hẹp hơn 1 điểm phần
  trăm mỗi đầu cho ngân sách hình (16–24%) và 10% cho thời lượng clip. Hỏng thì báo lỗi
  cho agent viết sửa, không tới cổng. Xong khi có test tái hiện từng lỗi trong bốn lỗi và
  cả bốn bị chặn trước cổng.
- **1.3** Sau TTS thật: beat lệch ra ngoài cảnh thì kẹp vào cuối cảnh; chữ dồn đầu cảnh
  đã tự dời từ `21f41af`. Thứ bác sĩ đã duyệt (lời đọc, cảnh nào thuộc clip nào) lệch thì
  vẫn chặn như cũ. Xong khi có test: cùng storyboard, thời lượng thật dài hơn ước lượng 8%
  vẫn dựng xong.

Không tổng hợp giọng thật trước cổng: một lần đọc trọn gout tốn 29.215 ký tự trên 98.123
credit vibi còn lại, và mất trắng nếu bác sĩ từ chối kịch bản.

### P2 — Video gout chuẩn

- **2.1** Bật xưởng. Gout đang ở `needs_medical_revision`; agent `revise_medical` sửa gộp
  một lần: tỷ lệ biểu đồ, beat S02, clip CL02, và yêu cầu đang xếp hàng trong
  `projects/gout-tinh-the-urat/chat.jsonl` (hình tinh thể S07 thành hình kim). Xong khi
  qua kiểm 1.2.
- **2.2** Bác sĩ duyệt cổng y khoa trong app, một lần PIN.
- **2.3** Xưởng dựng, dùng lại cache TTS theo dòng. Xong khi tới `awaiting_video_review`
  mà không mở lại cổng. Nếu `produce` vẫn hỏng vì bố cục: đó là lỗ hổng của P1, sửa P1,
  không vá storyboard bằng tay.
- **2.4** Bác sĩ xem trong app, góp ý qua chat cạnh video. Hai câu còn treo cần hỏi bác
  sĩ: "u-rát" đọc đúng chưa; dùng `speech-2.8-hd` hay turbo (nghe thử ở
  `cache/voice-test/clone/index.html`).
- **2.5** Mỗi điều bác sĩ chấp nhận ghi thành kiểm tự động: từ điển
  `profiles/pronunciation.vi.yaml`, lint `domain/script_style.py`, QA nhịp hình. Giao
  codex.
- **2.6** Xưởng đóng gói; bác sĩ đăng tay từ `revisions/<rev>/publish/`.

Sau hai vòng góp ý mà bác sĩ vẫn chưa ưng một hạng mục (giọng hoặc hình): dừng, bàn riêng
hạng mục đó với bác sĩ, không vá lẻ tiếp.

### P3 — Tinh gọn kết cấu (agy `gemini-4-carbon-high`, mỗi việc một commit)

- **3.1 Xóa khu nghiệm thu.** Xóa `workflows/factory_trials.py`,
  `tools/factory_trial_samples.py`, `docs/factory-acceptance-guide.md`, test của chúng,
  các route `/api/trials*` và `/api/standards/accepted` trong `dashboard.py`, nút
  "Nghiệm thu chuẩn" cùng mọi phần tử/hàm `fa-*` và `trial` trong `dashboard.html`.
  **Giữ** `workflow/standards.yaml` trong hash cổng (`gate_review.py:166`): project đang có
  đã ghi file này vào hash. `factory_standards.py` chỉ xóa phần chấp nhận theo giai đoạn;
  `pin_standards` mà `create_project_v2.py:46` gọi thì giữ, hoặc chuyển vào
  `standards.py`. Xong khi `grep -rn "factory_trials\|fa-elapsed" src tests` rỗng, pytest
  và Ruff sạch, app mở không lỗi console.
- **3.2 Xóa ElevenLabs và ASR thừa.** `tts/elevenlabs.py` còn được `cli.py`, `vibi.py`,
  `doctor.py`, `factory_deps.py`, `produce.py` nhắc tới: chuyển phần `vibi.py` dùng chung
  sang `vibi.py`, bỏ lựa chọn `elevenlabs` ở `produce --tts`, bỏ mục `elevenlabs` trong
  `doctor` và `.env.example`. `tts/asr.py` chỉ có `tests/tts/test_asr.py` dùng: kiểm
  `tools/` lần nữa rồi xóa cả hai. Xong khi `grep -rni elevenlabs src tests` rỗng và
  `healthvideo doctor` không còn dòng `elevenlabs`.
- **3.3 Bỏ skill thừa.** Giữ 13 thư mục trong `.agents/skills/`: `pyh`,
  `content-strategy`, `systematic-literature-review`, `youtube-scriptwriting`,
  `short-form-video`, `copy-editing`, `scripting-and-storyboarding`, `visual-style`,
  `remotion-best-practices`, `motion-design`, `video-understand`,
  `character-animation-qa`, `social`. Trước khi xóa 17 thư mục còn lại, grep tên từng cái
  trong `src`, `profiles`, `tests`, `.claude`; có chỗ dùng thì giữ. Cập nhật
  `skills-lock.json`. Xong khi `tests/test_company.py` đạt.
- **3.4 Gọn tài liệu.** Chuyển bảng "Tiến độ nhiệm vụ" của `README.md` sang
  `docs/archive/README-2026-11.md`, thay bằng một dòng trỏ tới `docs/progress.yaml`. Xóa
  `docs/HANDOFF.md` (file này thay nó). Chuyển
  `docs/superpowers/plans/2026-11-08-factory-company.md` và các plan 2026-10-22,
  2026-10-25 vào `docs/archive/plans/`. Sửa mục "Tài liệu" của `README.md` cho khớp. Xóa
  `topics/code-review.yaml` nếu `grep -rn "code-review" src` rỗng.
- **3.5 Xóa worktree và nhánh cũ** (Claude, sau khi bác sĩ xác nhận danh sách). Với
  `feat/m8-3-voicestudio`, `feat/script-voice` (hướng đã bỏ, chưa vào `master`): tạo tag
  `archive/<tên>` rồi mới xóa nhánh. Các nhánh `factory/*`, `feat/dashboard-app`,
  `backup/master-pre-m7-merge-20260917`: nội dung đã ở `master`, xóa bằng
  `git worktree remove` rồi `git branch -D`. Trước khi gỡ mỗi worktree, chạy
  `git -C <worktree> status --short`; có file lạ ngoài `report-codex-*.md` và
  `video/.vitest/` thì hỏi bác sĩ. Xong khi `git worktree list` còn một dòng.
- **3.6 Gộp Ý kiến vào chat** (sau P2). Một ô nhập duy nhất; Điều phối viên phân loại: sửa
  sản phẩm thì thành yêu cầu sửa như hiện nay, góp ý về xưởng thì ghi
  `topics/feedback.yaml` như `feedback_inbox.py` đang làm. Xóa tab Ý kiến. Hỏi bác sĩ
  trước khi làm vì đổi thói quen dùng.

### P4 — Chủ đề thứ hai và bàn giao

- **4.1** Bác sĩ thêm một chủ đề thật trong tab Hàng đợi.
- **4.2** Xưởng chạy A–Z. Claude không sửa tay; mỗi chỗ buộc phải can thiệp ghi một dòng
  vào `note` của việc 4.2 trong `docs/progress.yaml`. Xong khi tới `packaged` và bác sĩ
  chỉ làm ba việc: thêm chủ đề, nhập PIN hai lần, góp ý.
- **4.3** Sửa từng chỗ đã ghi (codex). Xong khi chủ đề thứ ba không cần can thiệp.
- **4.4** Clone repo ra thư mục mới, chạy `install/install.ps1`, `healthvideo doctor`
  không có FAIL ở mục bắt buộc. Kiểm `.agents/skills/pyh/SKILL.md` khớp với lệnh
  `healthvideo` hiện có.

## 6. Hoàn thiện là khi

1. Video gout được bác sĩ duyệt và đăng.
2. Một chủ đề thật đi từ hàng đợi tới `packaged` mà không ai sửa tay ngoài bác sĩ.
3. Cài mới trên checkout sạch, `doctor` không có FAIL ở mục bắt buộc.
4. `master` đã push, còn một worktree, `docs/progress.yaml` toàn `done`.
