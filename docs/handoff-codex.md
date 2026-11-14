# Bàn giao cho codex (2026-11-14, từ Claude)

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
