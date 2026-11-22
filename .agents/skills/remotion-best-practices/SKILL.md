---
name: remotion-best-practices
description: Remotion React component rules for PYH headless editing without Studio or manual renders.
version: 4.0.536
---

# Remotion Best Practices (PYH-Scoped)

## Ràng buộc PYH (bắt buộc)
- **Bỏ** `Open the preview` (`npx remotion studio`), `New project setup`, `Render the video` (`npx remotion render`), `Creating a SaaS`, và **không** nạp cây `references/` mặc định.
- Xưởng PYH chạy headless trên Windows; sau khi sửa SVG/component trong `video/src/`, chạy `pnpm --dir video typecheck` và `pnpm --dir video test` theo phạm vi, rồi để Python dựng lại video.

## Preserve user changes

- Respect existing edits in `video/src/` and only modify the exact files/lines assigned to the task.
- Never overwrite unrelated anatomy components, shared theme tokens, or locked revision artifacts.

## React Markup Best Practices

- Derive every animated property (`opacity`, `transform`, `strokeDashoffset`, `viewBox` zoom) deterministically from `useCurrentFrame()` and `useVideoConfig()`.
- Never use CSS transitions/animations, `requestAnimationFrame`, `Date.now()`, or `Math.random()` inside Remotion components (causes frame-to-frame flicker during headless rendering).
- Keep SVG `<g data-layer="...">`, `FOCUS_REGIONS`, `LABELS`, and `CUE_ACTIONS` synchronized with `video/src/anatomy/library.json` and unit tests.
- Load `./remotion-markup/REFERENCE.md` only if a specific Remotion React markup API question arises.
