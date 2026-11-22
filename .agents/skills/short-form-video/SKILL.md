---
name: short-form-video
description: Design 9:16 vertical short-form clips with fast hooks, retention pacing, seamless loops, and safe zones.
version: 0.1.0
---

# Short-Form Video (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- Chỉ áp dụng cho thiết kế kế hoạch/cắt clip 9:16 từ các cảnh đã duyệt y khoa (`shorts-plan.yaml` / `clip-plan.yaml`).
- **Không** trì hoãn hoặc cắt bỏ điều kiện áp dụng / cảnh báo an toàn (`safety_caveat`) để câu view; **không** tự tạo composition Remotion mới hay chạy `npx remotion still/render` (Python điều phối render và QA).

## Story Structure & Retention Arc

- **One idea per clip**: Carry one clear takeaway/mechanism; do not pack multiple unrelated topics into a short.
- **Fast hook (0–2s)**: Open immediately on the core question or misconception—never start with slow fade-ins or filler intros.
- **No dead air**: Keep a visual beat change every ~2–4s through the body and avoid flat static stretches.

## Hook Grammar

Pick one honest hook shape matching the approved script:
- **Open loop**: Pose the exact question or paradox answered by the clip's payoff.
- **Misconception check**: Highlight a common mistake and immediately show the real mechanism.
- **Direct practical promise**: State the concrete thing the viewer will understand in 60–90 seconds.

## Loops & Re-watch

- When appropriate, write a `loop_bridge` so the closing thought connects cleanly back to the opening hook without fabricating new claims.

## 9:16 Safe Areas (1080×1920)

Compose critical text, labels, mascot, and captions inside the safe zone so platform UI never covers them:
- **Top**: keep clear **≥ 15%** (~288px) for platform header/search UI.
- **Bottom**: keep clear **≥ 22%** (~422px) for description, hashtags, and audio bar.
- **Right**: keep clear **~100–120px** for like / comment / share action buttons.
- **Mascot**: ≤ 28% frame width (`mascot_max_width_percent <= 28`), never covering anatomy/charts or captions.
- **Captions**: `bottom_center`, 1–2 lines, ≤ 24 chars/line, high contrast inside the safe zone.
