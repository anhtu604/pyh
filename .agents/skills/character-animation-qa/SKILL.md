---
name: character-animation-qa
description: Review PYH animation frames and rendered video outputs using existing contact sheets, schema checks, and FFprobe QA reports without Playwright.
license: MIT
---

# Character Animation QA (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- **Bỏ** `Playwright Pattern` và không mở trình duyệt/tạo script ngoài.
- Dùng trực tiếp các bằng chứng có sẵn của PYH: `review-frames/index.json`, `hook-transitions/index.json`, contact sheet PNG, `renders/scene-timing.json`, và `reviews/video-qa.json` (kèm FFprobe QA do Python sinh).
- Contact sheet chỉ chứng minh các khung hình đã chụp; **không** nhận đã xem chuyển động liên tục giữa các frame hoặc đã nghe âm thanh từ ảnh tĩnh.

## Review Layers

1. **Schema & alignment validation**: verify `storyboard.yaml`, `scene-timing.json`, and `video-qa.json` match the active render hash.
2. **Static asset checks**: verify mascot poses, SVG layers, and FLUX stills exist and fit palette/font rules.
3. **Contact sheet & hook-transition inspection**: open `review-frames/index.json` and `hook-transitions/index.json` contact sheets directly with the image viewer.
4. **Motion & rhythm check**: inspect `motion-report.json` / `video-qa.json` and compare adjacent sampled frames for clear visual progression without stating continuous playback was watched.
5. **Final MP4 metadata check**: rely on `ffprobe` / `video-qa.json` for stream presence, duration, resolution, and loudness/pronunciation QA flags.
6. **Agent visual review**: check for overlapping labels, clipped Vietnamese text, unreadable 720p typography, mascot covering anatomy/captions, or 9:16 safe-zone violations.

## Pass/Revise/Fail

- `pass`: all criteria ≥ 7, style/safe-zone clean, QA reports valid.
- `revise`: fixable SVG/post issue (`fixable: true`) with exact repo-relative `edits`.
- `fail`: missing/corrupt assets, blank render, or out-of-scope issue requiring script/storyboard/audio reopen.
