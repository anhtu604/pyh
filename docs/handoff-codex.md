# Bàn giao cho codex (2026-11-14, từ Claude)

## Đổi ưu tiên theo yêu cầu bác sĩ 2026-11-14 — đọc trước phần lịch sử

- Bác sĩ dừng toàn bộ pilot để hoàn thiện xưởng, bắt đầu skill từng vai và model.
- Xưởng đã dừng, tiến trình chờ khởi động lại cũ đã hết hạn, queue rỗng. Hai
  project và log riêng giữ tại `cache/pilot-archive/2026-11-14/`; không xóa dữ liệu,
  không tự phục hồi pilot/đòi duyệt gout hoặc bật xưởng.
- Chuẩn nội dung: một người xem, một tầng chính TOFU/MOFU/BOFU, một lời hứa có
  giá trị diễn giải/thực hành. BOFU bác sĩ chọn: thực hành sức khỏe, khám khi cần,
  tin theo dõi kênh, không bán hàng. Không ép đủ ba tầng hoặc đọc lại giáo trình.
- Spec: `docs/superpowers/specs/2026-11-14-agent-editorial-standards-design.md`.
  Model/mẫu thử: `docs/reference/agent-model-evaluation.md`. Tiến độ hiện hành: R1.
- Vòng chuẩn hóa đầu đã sửa 11 skill, đồng bộ prompt và phân model trực tiếp.
  117 test liên quan đạt, Ruff sạch; review độc lập PASS phạm vi skill/prompt/config.
  Writer Sol và critic Carbon medium đã có mẫu thử ngắn; các vai khác chưa được
  kiểm năng lực toàn diện. Không coi đã nghiệm thu xưởng hoặc video.
- Skill/model là bước đầu, chưa khắc phục runtime treo/lỗi là dừng. Tiếp theo:
  retry/log/timeout có giới hạn, giữ cổng/cache; xem lại explain-first và thời lượng,
  tách yêu cầu kỹ thuật dựng khỏi công việc kể chuyện.

**Phần bên dưới là lịch sử trước khi đổi ưu tiên, không phải lệnh tiếp tục gout.**

Claude hết token; codex làm **dev lead** thay, theo `CLAUDE.md` mục 1, 3, 5 (chỗ ghi
"Claude" nay là codex). Tiến độ vẫn ghi ở `docs/progress.yaml`, commit `chore: progress`.
Push cần bác sĩ đồng ý (master đang đi trước `origin/main` vài commit).

## Gout đang ở đâu

- 11:10 bác sĩ duyệt cổng y khoa. Dựng hỏng 3 lần: 12:01 mất kết nối vibi; 12:28 ACE-Step
  (nhạc nền) sập `exit 3221225477`; 12:53 **`Clip CL01 render failed`**
  (`workflows/long_form.py:174`). Nguồn: `topics/logs/xuong.log`,
  `topics/logs/gout-tinh-the-urat/production-retry.yaml`.
- 13:35 bác sĩ bấm mở lại cổng; writer (codex) đang `revise_medical`. Bác sĩ sẽ phải
  duyệt lại. Đã dặn bác sĩ: lần sau dựng hỏng thì báo, đừng mở cổng.
- Lỗi CL01 chưa rõ nguyên nhân vì xưởng nền bỏ stdout của Remotion. Commit `25a7d32` cho
  `factory_deps._run_render_argv` ghi log dựng hỏng vào `topics/logs/render/*.log`.
- Một tác vụ nền của phiên Claude chờ gout về `awaiting_medical_review` và hết việc chạy,
  rồi `healthvideo xuong --stop` + `--background` để nạp `25a7d32`. Nếu phiên Claude đã
  đóng thì tác vụ đó chết theo: kiểm `topics/.xuong.lock` (`started_at` phải sau commit
  25a7d32); nếu xưởng còn chạy code cũ thì khởi động lại lúc gout chờ ở cổng, không giết
  agent đang chạy.

## Việc tiếp theo

1. Sau khi bác sĩ duyệt lại, theo dõi `produce`. Nếu CL01 hỏng tiếp: đọc
   `topics/logs/render/` và sửa gốc (ứng viên: Chrome/GPU hết bộ nhớ khi chạy cùng ACE-Step,
   hoặc dữ liệu clip mới sau khi kịch bản dài ra). Có test tái hiện trước khi sửa.
2. ACE-Step sập là lỗi truy cập bộ nhớ; nếu lặp lại, cân nhắc dọn GPU trước bước nhạc hoặc
   dựng không nhạc. Hỏi bác sĩ trước khi bỏ nhạc.
3. QA phát âm của bản dựng cũ (`renders/video-qa.json`) báo 71 lỗi chặn; xem lại khi có bản
   dựng mới. Câu treo cho bác sĩ ở 2.4: "u-rát", `speech-2.8-hd` hay turbo, hình kim S07.
4. Sau gout: 2.5, 2.6, 2.7, rồi 3.2 (agy làm ở `.claude/worktrees/p3-elevenlabs`, chưa rõ
   trạng thái), 3.5, 3.6, P4.

## Đã chốt trong phiên này (đừng làm lại)

- Phân model ở `profiles/company.yaml` (d856e99): vai nhẹ dùng `gemini-4-hydrogen-medium`;
  y khoa, kiểm duyệt, đạo diễn hình, thợ dựng dùng `gemini-pro-orchestrator`; writer dùng
  codex `gpt-6.1-sol`; không Opus, không astra. Kiểm duyệt kịch bản tối đa 2 vòng.
- Điều phối viên chat nhanh, tự `escalate` sang `coordinator_senior` khi khó.
- 10 nguyên tắc viết của bác sĩ: `profiles/doctor-feedback.yaml` mục `slug: chung`,
  tóm trong `.agents/skills/pyh-writer/SKILL.md`.
- Contact sheet FFmpeg đã gom 50 điều kiện mỗi nhóm (9b8f4ab).
